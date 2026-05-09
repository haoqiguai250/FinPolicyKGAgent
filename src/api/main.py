"""
FinPolicyKG 端到端 Pipeline
文档解析 → 章节分割 → 反思式抽取 → 三元组存储 → 评估

用法:
    python -m src.api.main --input data/raw/xxx.pdf
    python -m src.api.main --input-dir data/raw/          # 并行批量处理
"""

import argparse
import json
import sys
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import settings, ensure_dirs
from src.core.logger import logger
from src.core.run_logger import PipelineRunLogger, JsonRunLogger

from src.ingestion.parser import DoclingParser, parse_document
from src.ingestion.chunker import SectionAwareChunker, chunk_document
from src.extraction.reflector import ReflectiveAgent
from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.evaluation.evaluator import Evaluator
from src.extraction.llm_client import DeepSeekClient, get_llm_client, get_reasoning_llm_client

# ── 并行输出控制 ──
_print_lock = threading.Lock()


def _log_to_file(msg: str, log_path: Path):
    """追加写入独立日志文件"""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _console_print(msg: str):
    """线程安全的控制台输出"""
    with _print_lock:
        print(msg, flush=True)


def run_pipeline(file_path: str | Path, log_dir: Path | None = None, thinking_enabled: bool = False, skip_neo4j: bool = False, chunk_workers: int | None = None) -> dict:
    """
    对单个文档运行完整 Pipeline

    Args:
        file_path: 文档路径
        log_dir: 独立日志目录（并行模式下各 PDF 写各的日志文件）
        thinking_enabled: 是否开启 DeepSeek 思维链模式
        skip_neo4j: 是否跳过 Neo4j 双写

    Returns:
        dict: 运行结果摘要
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # ── 独立日志文件（并行模式下避免输出交叉）──
    task_log = None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_log = log_dir / f"{file_path.stem}_{timestamp}.log"
        _log_to_file(f"{'='*60}", task_log)
        _log_to_file(f"FinPolicyKG Pipeline 启动: {file_path.name}", task_log)
        _log_to_file(f"{'='*60}", task_log)

    def log(msg: str):
        """同时写独立日志 + 全局 logger"""
        if task_log:
            _log_to_file(msg, task_log)
        else:
            logger.info(msg)

    log(f"FinPolicyKG Pipeline 启动: {file_path.name}")
    if thinking_enabled:
        log("🧠 思维链模式: 已开启 (thinking_enabled=True)")
    if skip_neo4j:
        log("⏭️  Neo4j: 已跳过 (skip_neo4j=True)")
    workers = chunk_workers or settings.CHUNK_PARALLEL_WORKERS
    log(f"  Chunk 并行数: {workers}")

    # ── LLM 客户端 ──
    if thinking_enabled:
        extract_llm = DeepSeekClient(thinking_enabled=True)
        reason_llm = DeepSeekClient(reasoning_effort="medium", thinking_enabled=True)
    else:
        extract_llm = get_llm_client()
        reason_llm = get_reasoning_llm_client()

    # ── 初始化运行记录器 ──
    run_log = PipelineRunLogger(source_file=file_path.name)
    json_log = JsonRunLogger(source_file=file_path.name)

    # ── Stage 1: 文档解析 ──
    log("📌 Stage 1: 文档解析 (Docling)")
    run_log.log_stage1_input(file_path)
    parser = DoclingParser()
    parsed_doc = parser.parse_and_save(file_path)
    run_log.log_stage1_output(parsed_doc)
    json_log.log_stage1(parsed_doc)
    log(f"  标题: {parsed_doc.title} | 章节数: {len(parsed_doc.sections)}")

    # ── Stage 2: 章节感知分割 ──
    log("📌 Stage 2: 章节感知文本分割")
    run_log.log_stage2_input(parsed_doc)
    chunker = SectionAwareChunker()
    chunked_doc = chunker.chunk(parsed_doc)
    chunked_path = chunked_doc.save()  # 只保存一次，后续复用路径
    run_log.log_stage2_output(chunked_doc)
    json_log.log_stage2(chunked_doc)
    log(f"  分块数: {len(chunked_doc.chunks)}")

    # ── Stage 3: 反思式智能体抽取（并行）──
    log("📌 Stage 3: 反思式智能体抽取")
    agent = ReflectiveAgent(llm_client=extract_llm)
    all_entities = []
    all_triples = []
    all_reflection_results = []

    _chunk_results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        fut_map = {
            executor.submit(agent.extract_with_reflection, chunk, []): (i, chunk)
            for i, chunk in enumerate(chunked_doc.chunks)
        }
        for fut in as_completed(fut_map):
            i, chunk = fut_map[fut]
            try:
                result = fut.result(timeout=600)
                _chunk_results.append((i, result))
                log(f"  Chunk {i+1}/{len(chunked_doc.chunks)}: {len(result.entities)} 实体, {len(result.triples)} 三元组")
            except Exception as e:
                log(f"  Chunk {i+1}/{len(chunked_doc.chunks)} 处理失败: {e}")

    # 按原始 chunk 顺序排序
    _chunk_results.sort(key=lambda x: x[0])

    # 去重合并
    seen = set()
    for i, result in _chunk_results:
        for entity in result.entities:
            key = (entity.name, entity.entity_type)
            if key not in seen:
                seen.add(key)
                all_entities.append(entity)
        all_triples.extend(result.triples)
        all_reflection_results.append(result)

    run_log.log_stage3_summary(all_reflection_results)
    json_log.log_stage3(all_reflection_results)

    # ── Stage 4: 三元组存储 ──
    log("📌 Stage 4: 三元组存储")
    store = TripletStore(
        source_file=parsed_doc.source_file,
        policy_id=chunked_doc.policy_id,
        extract_time=datetime.now().isoformat(),
    )
    store.add_entities(all_entities)
    store.add_triples(all_triples)
    store.save()

    # Neo4j 双写
    neo4j_store = None
    if not skip_neo4j:
        try:
            neo4j_store = Neo4jStore()
            neo4j_store.ensure_constraints()
            neo4j_store.set_metadata(
                source_file=parsed_doc.source_file,
                policy_id=chunked_doc.policy_id,
                extract_time=datetime.now().isoformat(),
            )
            neo4j_store.add_entities(all_entities)
            neo4j_store.add_triples(all_triples)
            neo4j_stats = neo4j_store.compute_stats()
            log(f"  Neo4j 双写: {neo4j_stats['total_entities']} 实体, {neo4j_stats['total_triples']} 三元组")
        except Exception as e:
            log(f"  Neo4j 双写失败（不影响 JSON 存储）: {e}")
            neo4j_store = None
    else:
        log("  Neo4j: 已跳过")

    run_log.log_stage4_output(store)
    json_log.log_stage4(store)

    # ── Stage 5: 评估 ──
    log("📌 Stage 5: 多维度评估")
    evaluator = Evaluator(llm_client=reason_llm)

    # 取最后一个 reflection_result 用于反思效率指标
    last_reflection = all_reflection_results[-1] if all_reflection_results else None

    # 原文文本（用于 L4 忠实度评估）
    source_text = parsed_doc.full_text[:3000]  # 截断避免过长

    report = evaluator.evaluate(
        store,
        reflection_result=last_reflection,
        num_chunks=len(chunked_doc.chunks),
        source_text=source_text,
        enable_llm_judge=True,
    )
    run_log.log_stage5_output(report)
    json_log.log_stage5(report)

    # ── 补图：Action + Eligibility + Strategy ──
    log("📌 补图: Action + Eligibility + Strategy")
    from src.enhancement.enhancer import Enhancer
    enhancer = Enhancer(neo4j_store=neo4j_store, llm_client=extract_llm)
    ent_before = len(store.entities)
    tri_before = len(store.triples)
    enhanced_store = enhancer.enhance_from_chunks_file(
        chunks_path=Path(chunked_path),
        store=store,
        policy_name=parsed_doc.title,
    )
    ent_added = len(enhanced_store.entities) - ent_before
    tri_added = len(enhanced_store.triples) - tri_before
    enhanced_store.save()
    run_log.log_enhancement_output(enhanced_store, ent_added, tri_added)
    json_log.log_enhancement({
        "entities_added": ent_added,
        "triples_added": tri_added,
        "action_types": [e for e in enhanced_store.entities if e.get("type") == "ActionType"],
        "conditions": [e for e in enhanced_store.entities if e.get("type") == "Condition"],
        "strategies": [t for t in enhanced_store.triples if t.get("relation") == "leads_to"],
    })
    log(f"  补图: +{ent_added} 实体, +{tri_added} 三元组")

    # ── 保存 JSON 运行记录 ──
    json_log.save()

    # ── 结果摘要 ──
    summary = {
        "file": parsed_doc.source_file,
        "title": parsed_doc.title,
        "sections": len(parsed_doc.sections),
        "chunks": len(chunked_doc.chunks),
        "entities": len(store.entities),
        "triples": len(store.triples),
        "ent_added": ent_added,
        "tri_added": tri_added,
        "iterations": sum(r.iterations for r in all_reflection_results),
        "converged": all(r.converged for r in all_reflection_results),
        "policy_id": chunked_doc.policy_id,
        "log_file": str(task_log) if task_log else None,
    }

    log(f"{'='*60}")
    log(f"Pipeline 完成！实体: {summary['entities']} 三元组: {summary['triples']}")
    log(f"{'='*60}")

    return summary


def _run_pipeline_parallel(file_path: Path, log_dir: Path, thinking_enabled: bool = False, skip_neo4j: bool = False, chunk_workers: int | None = None) -> dict:
    """并行包装：控制台只打开始/完成，详细日志写独立文件"""
    _console_print(f"📄 开始处理 [{file_path.name}]...")
    try:
        result = run_pipeline(file_path, log_dir=log_dir, thinking_enabled=thinking_enabled, skip_neo4j=skip_neo4j, chunk_workers=chunk_workers)
        _console_print(f"✅ 完成 [{file_path.name}]  |  实体: {result['entities']}  三元组: {result['triples']}  |  日志: {result.get('log_file', '')}")
        return result
    except Exception as e:
        _console_print(f"❌ 失败 [{file_path.name}]: {e}")
        return {"file": file_path.name, "error": str(e)}


def main():
    """CLI 入口"""
    ensure_dirs()

    arg_parser = argparse.ArgumentParser(description="FinPolicyKG Pipeline")
    arg_parser.add_argument("--input", type=str, help="单个文档路径")
    arg_parser.add_argument("--input-dir", type=str, help="文档目录路径（批量并行处理）")
    arg_parser.add_argument("--workers", type=int, default=None, help=f"文档并行数（默认 {settings.PARALLEL_WORKERS}）")
    arg_parser.add_argument("--chunk-workers", type=int, default=None, help=f"chunk 并行数（默认 {settings.CHUNK_PARALLEL_WORKERS}）")
    arg_parser.add_argument("--thinking", action="store_true", help="开启 DeepSeek 思维链模式（所有 LLM 调用）")
    arg_parser.add_argument("--skip-neo4j", action="store_true", help="跳过 Neo4j 双写")
    args = arg_parser.parse_args()

    if args.input:
        # 单文件模式：直接跑，日志打控制台
        run_pipeline(args.input, thinking_enabled=args.thinking, skip_neo4j=args.skip_neo4j, chunk_workers=args.chunk_workers)

    elif args.input_dir:
        dir_path = Path(args.input_dir)
        supported = {".pdf", ".docx", ".doc", ".html", ".htm"}
        files = sorted(f for f in dir_path.iterdir() if f.suffix.lower() in supported)

        if not files:
            print("未找到可处理的文档")
            return

        workers = args.workers or min(settings.PARALLEL_WORKERS, len(files))
        log_dir = settings.LOGS_DIR / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        print(f"{'='*60}")
        print(f"批量并行处理: {len(files)} 个文档  |  并行数: {workers}")
        print(f"详细日志目录: {log_dir}")
        print(f"{'='*60}")

        start_time = datetime.now()
        results = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            fut_map = {executor.submit(_run_pipeline_parallel, f, log_dir, args.thinking, args.skip_neo4j, args.chunk_workers): f for f in files}
            for fut in as_completed(fut_map):
                results.append(fut.result())

        elapsed = (datetime.now() - start_time).total_seconds()

        # ── 汇总报告 ──
        report_path = settings.DATA_DIR / "output" / f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        succeeded = [r for r in results if "error" not in r]
        failed = [r for r in results if "error" in r]

        report = {
            "total_files": len(files),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "elapsed_seconds": round(elapsed, 1),
            "log_dir": str(log_dir),
            "results": results,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*60}")
        print(f"批量处理完成！耗时: {elapsed:.1f}s")
        print(f"  成功: {len(succeeded)}  失败: {len(failed)}")
        for r in succeeded:
            print(f"  ✅ {r.get('title', r.get('file', '?'))}  |  实体: {r.get('entities', '?')}  三元组: {r.get('triples', '?')}")
        for r in failed:
            print(f"  ❌ {r.get('file', '?')}  |  原因: {r.get('error', '?')}")
        print(f"详细日志: {log_dir}")
        print(f"汇总报告: {report_path}")
        print(f"{'='*60}")

    else:
        print("请使用 --input 或 --input-dir 指定文档路径")
        print("示例: python -m src.api.main --input data/raw/xxx.pdf")
        print("      python -m src.api.main --input-dir data/raw/")


if __name__ == "__main__":
    main()
