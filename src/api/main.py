"""
FinPolicyKG 端到端 Pipeline
文档解析 → 章节分割 → 反思式抽取 → 三元组存储 → 评估

用法:
    python -m src.api.main --input data/raw/xxx.pdf
    python -m src.api.main --input-dir data/raw/
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

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
from src.extraction.llm_client import get_llm_client, get_reasoning_llm_client


def run_pipeline(file_path: str | Path) -> dict:
    """
    对单个文档运行完整 Pipeline

    Returns:
        dict: 运行结果摘要
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    logger.info(f"{'='*60}")
    logger.info(f"FinPolicyKG Pipeline 启动: {file_path.name}")
    logger.info(f"{'='*60}")

    # ── 初始化运行记录器 ──
    run_log = PipelineRunLogger(source_file=file_path.name)
    json_log = JsonRunLogger(source_file=file_path.name)

    # ── Stage 1: 文档解析 ──
    logger.info("📌 Stage 1: 文档解析 (Docling)")
    run_log.log_stage1_input(file_path)
    parser = DoclingParser()
    parsed_doc = parser.parse_and_save(file_path)
    run_log.log_stage1_output(parsed_doc)
    json_log.log_stage1(parsed_doc)

    # ── Stage 2: 章节感知分割 ──
    logger.info("📌 Stage 2: 章节感知文本分割")
    run_log.log_stage2_input(parsed_doc)
    chunker = SectionAwareChunker()
    chunked_doc = chunker.chunk(parsed_doc)
    chunked_path = chunked_doc.save()  # 只保存一次，后续复用路径
    run_log.log_stage2_output(chunked_doc)
    json_log.log_stage2(chunked_doc)

    # ── Stage 3: 反思式智能体抽取 ──
    logger.info("📌 Stage 3: 反思式智能体抽取")
    agent = ReflectiveAgent()
    all_entities = []
    all_triples = []
    all_reflection_results = []

    for chunk in chunked_doc.chunks:
        reflection_result = agent.extract_with_reflection(chunk, all_entities)
        all_entities.extend(reflection_result.entities)
        all_triples.extend(reflection_result.triples)
        all_reflection_results.append(reflection_result)

    run_log.log_stage3_summary(all_reflection_results)
    json_log.log_stage3(all_reflection_results)

    # ── Stage 4: 三元组存储 ──
    logger.info("📌 Stage 4: 三元组存储")
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
        logger.info(f"Neo4j 双写: {neo4j_stats['total_entities']} 实体, {neo4j_stats['total_triples']} 三元组")
    except Exception as e:
        logger.warning(f"Neo4j 双写失败（不影响 JSON 存储）: {e}")
        neo4j_store = None

    run_log.log_stage4_output(store)
    json_log.log_stage4(store)

    # ── Stage 5: 评估 ──
    logger.info("📌 Stage 5: 多维度评估")
    evaluator = Evaluator(llm_client=get_reasoning_llm_client())

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
    logger.info("📌 补图: Action + Eligibility + Strategy")
    from src.enhancement.enhancer import Enhancer
    enhancer = Enhancer(neo4j_store=neo4j_store)
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

    # ── 保存 JSON 运行记录 ──
    json_log.save()

    # ── 结果摘要 ──
    summary = {
        "file": parsed_doc.source_file,
        "sections": len(parsed_doc.sections),
        "chunks": len(chunked_doc.chunks),
        "entities": len(store.entities),
        "triples": len(store.triples),
        "iterations": sum(r.iterations for r in all_reflection_results),
        "converged": all(r.converged for r in all_reflection_results),
        "policy_id": chunked_doc.policy_id,
    }

    logger.info(f"{'='*60}")
    logger.info(f"Pipeline 完成！摘要: {summary}")
    logger.info(f"{'='*60}")

    return summary


def main():
    """CLI 入口"""
    ensure_dirs()

    arg_parser = argparse.ArgumentParser(description="FinPolicyKG Pipeline")
    arg_parser.add_argument("--input", type=str, help="单个文档路径")
    arg_parser.add_argument("--input-dir", type=str, help="文档目录路径（批量处理）")
    args = arg_parser.parse_args()

    if args.input:
        run_pipeline(args.input)
    elif args.input_dir:
        dir_path = Path(args.input_dir)
        supported = {".pdf", ".docx", ".doc", ".html", ".htm"}
        files = sorted(f for f in dir_path.iterdir() if f.suffix.lower() in supported)
        logger.info(f"批量处理: {len(files)} 个文档")
        for f in files:
            try:
                run_pipeline(f)
            except Exception as e:
                logger.error(f"处理失败 [{f.name}]: {e}")
    else:
        logger.info("请使用 --input 或 --input-dir 指定文档路径")
        logger.info("示例: python -m src.api.main --input data/raw/xxx.pdf")


if __name__ == "__main__":
    main()
