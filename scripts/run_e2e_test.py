"""端到端测试：PDF → 解析 → 分割 → 抽取 → 反思 → 存储（Neo4j+JSON）→ 评估

用法:
  python scripts/run_e2e_test.py                                    # 完整 Pipeline（有反思）
  python scripts/run_e2e_test.py "政策.pdf"                         # 指定 PDF
  python scripts/run_e2e_test.py "政策.pdf" --no-reflect            # 无反思模式（跳过批判+修正，不补图不写Neo4j）
  python scripts/run_e2e_test.py --compare A.json B.json            # 对比两份运行日志
"""
import sys
import os
import json
import argparse

# 修复 Windows 控制台编码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from datetime import datetime

from src.ingestion.parser import DoclingParser
from src.ingestion.chunker import SectionAwareChunker
from src.extraction.extractor import SchemaGuidedExtractor
from src.extraction.reflector import ReflectiveAgent, ReflectionResult
from src.extraction.schema import Entity, Triple
from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.evaluation.evaluator import Evaluator
from src.extraction.llm_client import get_llm_client, get_reasoning_llm_client
from src.core.run_logger import PipelineRunLogger, JsonRunLogger
from loguru import logger

# 并行抽取的并发数（可调，默认跟随 settings）
MAX_EXTRACT_WORKERS = 16


# ══════════════════════════════════════════
#  对比报告生成
# ══════════════════════════════════════════

def _diff_val(a, b, fmt=".2f", pct=False):
    """计算差值并格式化"""
    diff = b - a
    sign = "+" if diff > 0 else ""
    if pct:
        return f"{diff*100:+.1f}pp"
    return f"{diff:{sign}{fmt}}"


def _diff_row(label, a, b, fmt=".2f", pct=False):
    """生成一行对比"""
    # 确保 fmt="d" 时值为整数，避免 float 导致格式化错误
    if fmt == "d":
        a, b = int(a), int(b)
    diff = _diff_val(a, b, fmt, pct)
    if pct:
        a_str = f"{a:.1%}"
        b_str = f"{b:.1%}"
    else:
        a_str = f"{a:{fmt}}"
        b_str = f"{b:{fmt}}"
    return f"| {label} | {a_str} | {b_str} | {diff} |"


def compare_two_runs(json_path1: str, json_path2: str):
    """对比两份运行日志 JSON，生成 Markdown 对比报告"""
    with open(json_path1, "r", encoding="utf-8") as f:
        data_a = json.load(f)
    with open(json_path2, "r", encoding="utf-8") as f:
        data_b = json.load(f)

    # 判断哪个是有反思、哪个是无反思
    # 约定：有反思的 stage3 里 total_iterations > chunk 数 → 有反思
    s3_a = data_a.get("stage3_extract", {})
    s3_b = data_b.get("stage3_extract", {})
    chunks_a = len(data_a.get("stage2_chunk", {}).get("chunks", []))
    chunks_b = len(data_b.get("stage2_chunk", {}).get("chunks", []))
    has_reflect_a = s3_a.get("total_iterations", 0) > chunks_a
    has_reflect_b = s3_b.get("total_iterations", 0) > chunks_b

    # 确保 data_a = 有反思，data_b = 无反思
    path_a, path_b = json_path1, json_path2
    if has_reflect_a and not has_reflect_b:
        label_a, label_b = "有反思", "无反思"
    elif has_reflect_b and not has_reflect_a:
        # 交换：A 是无反思，B 是有反思 → 调整为 A=有反思，B=无反思
        data_a, data_b = data_b, data_a
        path_a, path_b = json_path2, json_path1
        label_a, label_b = "有反思", "无反思"
    else:
        label_a, label_b = "运行A", "运行B"

    ev_a = data_a.get("stage5_evaluate", {})
    ev_b = data_b.get("stage5_evaluate", {})

    # ── 基础统计对比 ──
    lines = [
        "# 抽取对比报告：无反思 vs 有反思",
        "",
        f"- **{label_a}**: {path_a}",
        f"- **{label_b}**: {path_b}",
        f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. 基础统计",
        "",
        "| 指标 | 有反思 | 无反思 | 差异 |",
        "|------|--------|--------|------|",
        _diff_row("实体数", ev_a.get("total_entities", 0), ev_b.get("total_entities", 0), fmt="d"),
        _diff_row("三元组数", ev_a.get("total_triples", 0), ev_b.get("total_triples", 0), fmt="d"),
        _diff_row("平均置信度", ev_a.get("avg_confidence", 0), ev_b.get("avg_confidence", 0)),
    ]

    # ── L1 规则合规性 ──
    cr_a = ev_a.get("check_rules", {})
    cr_b = ev_b.get("check_rules", {})
    lines += [
        "",
        "## 2. L1 规则合规性",
        "",
        "| 指标 | 有反思 | 无反思 | 差异 |",
        "|------|--------|--------|------|",
        _diff_row("完全合规率", cr_a.get("compliance_rate", 0), cr_b.get("compliance_rate", 0), pct=True),
        _diff_row("主体引用违规", cr_a.get("vague_reference_violations", 0), cr_b.get("vague_reference_violations", 0), fmt="d"),
        _diff_row("实体长度违规", cr_a.get("entity_length_violations", 0), cr_b.get("entity_length_violations", 0), fmt="d"),
        _diff_row("实体类型违规", cr_a.get("entity_type_violations", 0), cr_b.get("entity_type_violations", 0), fmt="d"),
        _diff_row("关系类型违规", cr_a.get("relation_type_violations", 0), cr_b.get("relation_type_violations", 0), fmt="d"),
    ]

    # ── L2 抽取效率 ──
    le_a = ev_a.get("local_efficiency", {})
    le_b = ev_b.get("local_efficiency", {})
    lines += [
        "",
        "## 3. L2 本地抽取效率",
        "",
        "| 指标 | 有反思 | 无反思 | 差异 |",
        "|------|--------|--------|------|",
        _diff_row("每块平均三元组数", le_a.get("avg_triples_per_chunk", 0), le_b.get("avg_triples_per_chunk", 0)),
        _diff_row("ECR 实体覆盖率", le_a.get("ecr", 0), le_b.get("ecr", 0), pct=True),
        _diff_row("TCR 实体类型覆盖率", le_a.get("tcr", 0), le_b.get("tcr", 0), pct=True),
        _diff_row("RCR 关系覆盖率", le_a.get("rcr", 0), le_b.get("rcr", 0), pct=True),
        _diff_row("TCR-N 归一化类型覆盖率", le_a.get("tcr_normalized", 0), le_b.get("tcr_normalized", 0), pct=True),
        _diff_row("RCR-N 归一化关系覆盖率", le_a.get("rcr_normalized", 0), le_b.get("rcr_normalized", 0), pct=True),
    ]

    # ── L3 语义多样性 ──
    sd_a = ev_a.get("semantic_diversity", {})
    sd_b = ev_b.get("semantic_diversity", {})
    lines += [
        "",
        "## 4. L3 全局语义多样性",
        "",
        "| 指标 | 有反思 | 无反思 | 差异 |",
        "|------|--------|--------|------|",
        _diff_row("香农熵(实体)", sd_a.get("shannon_entropy_entity", 0), sd_b.get("shannon_entropy_entity", 0), fmt=".4f"),
        _diff_row("香农熵(关系)", sd_a.get("shannon_entropy_relation", 0), sd_b.get("shannon_entropy_relation", 0), fmt=".4f"),
        _diff_row("Schema归一化熵(实体)", sd_a.get("schema_normalized_entropy_entity", 0), sd_b.get("schema_normalized_entropy_entity", 0), fmt=".4f"),
        _diff_row("Schema归一化熵(关系)", sd_a.get("schema_normalized_entropy_relation", 0), sd_b.get("schema_normalized_entropy_relation", 0), fmt=".4f"),
        _diff_row("Renyi熵(实体)", sd_a.get("renyi_entropy_entity", 0), sd_b.get("renyi_entropy_entity", 0), fmt=".4f"),
        _diff_row("Renyi熵(关系)", sd_a.get("renyi_entropy_relation", 0), sd_b.get("renyi_entropy_relation", 0), fmt=".4f"),
    ]

    # ── L4 LLM 裁判 ──
    lj_a = ev_a.get("llm_judge", {})
    lj_b = ev_b.get("llm_judge", {})
    lines += [
        "",
        "## 5. L4 LLM-as-a-Judge",
        "",
        "| 指标 | 有反思 | 无反思 | 差异 |",
        "|------|--------|--------|------|",
        _diff_row("精确性 Precision", lj_a.get("precision", 0), lj_b.get("precision", 0)),
        _diff_row("忠实度 Faithfulness", lj_a.get("faithfulness", 0), lj_b.get("faithfulness", 0)),
        _diff_row("完整性 Comprehensiveness", lj_a.get("comprehensiveness", 0), lj_b.get("comprehensiveness", 0)),
        _diff_row("相关性 Relevance", lj_a.get("relevance", 0), lj_b.get("relevance", 0)),
        _diff_row("综合得分", lj_a.get("overall_score", 0), lj_b.get("overall_score", 0)),
    ]

    # ── LLM 评审理由 ──
    reason_a = lj_a.get("judge_reasoning", "")
    reason_b = lj_b.get("judge_reasoning", "")
    if reason_a or reason_b:
        lines += [
            "",
            "### LLM 评审理由",
            "",
            f"**有反思**: {reason_a or '无'}",
            "",
            f"**无反思**: {reason_b or '无'}",
        ]

    # ── 实体类型分布对比 ──
    ent_dist_a = ev_a.get("entity_type_distribution", {})
    ent_dist_b = ev_b.get("entity_type_distribution", {})
    all_ent_types = sorted(set(list(ent_dist_a.keys()) + list(ent_dist_b.keys())))
    lines += [
        "",
        "## 6. 实体类型分布对比",
        "",
        "| 类型 | 有反思 | 无反思 | 差异 |",
        "|------|--------|--------|------|",
    ]
    for etype in all_ent_types:
        ca = ent_dist_a.get(etype, 0)
        cb = ent_dist_b.get(etype, 0)
        diff = cb - ca
        sign = "+" if diff > 0 else ""
        lines.append(f"| {etype} | {ca} | {cb} | {sign}{diff} |")

    # ── 关系类型分布对比 ──
    rel_dist_a = ev_a.get("relation_type_distribution", {})
    rel_dist_b = ev_b.get("relation_type_distribution", {})
    all_rel_types = sorted(set(list(rel_dist_a.keys()) + list(rel_dist_b.keys())))
    lines += [
        "",
        "## 7. 关系类型分布对比",
        "",
        "| 类型 | 有反思 | 无反思 | 差异 |",
        "|------|--------|--------|------|",
    ]
    for rtype in all_rel_types:
        ca = rel_dist_a.get(rtype, 0)
        cb = rel_dist_b.get(rtype, 0)
        diff = cb - ca
        sign = "+" if diff > 0 else ""
        lines.append(f"| {rtype} | {ca} | {cb} | {sign}{diff} |")

    # ── 反思效率（仅展示有反思的数据）──
    lines += [
        "",
        "## 8. 反思效率",
        "",
    ]
    if has_reflect_a or has_reflect_b:
        ref_data = data_a.get("stage3_extract", {}) if has_reflect_a else data_b.get("stage3_extract", {})
        lines += [
            f"- **总迭代轮次**: {ref_data.get('total_iterations', 'N/A')}",
            f"- **是否全部收敛**: {'是' if ref_data.get('all_converged') else '否'}",
        ]
        # 逐 chunk 迭代详情
        details = ref_data.get("reflection_details", [])
        if details:
            lines += [
                "",
                "| Chunk | 迭代轮次 | 收敛 | 实体数 | 三元组数 |",
                "|-------|----------|------|--------|----------|",
            ]
            for d in details:
                lines.append(
                    f"| {d.get('chunk_index', 0) + 1} | "
                    f"{d.get('iterations', '')} | "
                    f"{'是' if d.get('converged') else '否'} | "
                    f"{d.get('entity_count', '')} | "
                    f"{d.get('triple_count', '')} |"
                )
    else:
        lines.append("无反思数据可展示。")

    # ── 小结 ──
    lines += [
        "",
        "---",
        "",
        "## 小结",
        "",
    ]
    # 自动总结关键发现
    ent_diff = ev_b.get("total_entities", 0) - ev_a.get("total_entities", 0)
    tri_diff = ev_b.get("total_triples", 0) - ev_a.get("total_triples", 0)
    l4_diff = lj_b.get("overall_score", 0) - lj_a.get("overall_score", 0)
    cr_diff = cr_b.get("compliance_rate", 0) - cr_a.get("compliance_rate", 0)

    findings = []
    if ent_diff != 0:
        findings.append(f"- 实体数：无反思比有反思{'多' if ent_diff > 0 else '少'} {abs(ent_diff)} 个")
    if tri_diff != 0:
        findings.append(f"- 三元组数：无反思比有反思{'多' if tri_diff > 0 else '少'} {abs(tri_diff)} 条")
    if l4_diff != 0:
        findings.append(f"- L4 综合得分：无反思比有反思{'高' if l4_diff > 0 else '低'} {abs(l4_diff):.2f} 分")
    if cr_diff != 0:
        findings.append(f"- L1 合规率：无反思比有反思{'高' if cr_diff > 0 else '低'} {abs(cr_diff)*100:.1f}pp")

    if not findings:
        findings.append("- 两种模式结果基本一致，反思阶段未带来显著差异")

    lines.extend(findings)

    # 保存
    report_text = "\n".join(lines)
    stem_a = Path(json_path1).stem
    stem_b = Path(json_path2).stem
    output_dir = Path(json_path1).parent
    output_path = output_dir / f"compare_{stem_a}_vs_{stem_b}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)
    print(f"\n对比报告已保存: {output_path}")
    return output_path


# ══════════════════════════════════════════
#  Pipeline 主流程
# ══════════════════════════════════════════

def run_pipeline(pdf_name: str, no_reflect: bool = False):
    """运行完整的 Pipeline（支持无反思模式）"""
    project_root = PROJECT_ROOT
    pdf_path = os.path.join(project_root, "data", "raw", pdf_name)

    if not os.path.exists(pdf_path):
        print(f"PDF 文件不存在: {pdf_path}")
        return

    mode_label = "无反思" if no_reflect else "有反思"

    # 初始化运行记录器
    run_log = PipelineRunLogger(source_file=pdf_name)
    json_log = JsonRunLogger(source_file=pdf_name)
    # 无反思模式：修改 JSON 日志文件名加后缀
    if no_reflect:
        original_path = json_log.log_path
        json_log.log_path = original_path.with_name(
            original_path.stem + "_no_reflect" + original_path.suffix
        )

    print("=" * 60)
    print(f"FinPolicyKGAgent 端到端测试 — [{mode_label}模式]")
    print("=" * 60)

    # ── Stage 1: Docling 文档解析 ──
    print("\n[Stage 1] Docling 文档解析...")
    run_log.log_stage1_input(Path(pdf_path))
    parser = DoclingParser()
    doc_result = parser.parse(pdf_path)
    print(f"  标题: {doc_result.title}")
    print(f"  章节数: {len(doc_result.sections)}")
    print(f"  总字符: {len(doc_result.full_text)}")
    for i, s in enumerate(doc_result.sections):
        heading = s.get("heading", "")
        level = s.get("level", 0)
        print(f"  [{i}] L{level} | {heading}")
    parsed_path = doc_result.save()
    print(f"  解析结果已保存: {parsed_path}")
    run_log.log_stage1_output(doc_result)
    json_log.log_stage1(doc_result)

    # ── Stage 2: 章节感知分割 ──
    print("\n[Stage 2] 章节感知分割...")
    run_log.log_stage2_input(doc_result)
    chunker = SectionAwareChunker()
    chunked_doc = chunker.chunk(doc_result)
    chunks = chunked_doc.chunks
    print(f"  分块数: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"  [{i}] {chunk.heading} | {len(chunk.text)} chars | tokens~{chunk.token_count}")
    chunked_path = chunked_doc.save()
    print(f"  分块结果已保存: {chunked_path}")
    run_log.log_stage2_output(chunked_doc)
    json_log.log_stage2(chunked_doc)

    # ── Stage 3: 三元组抽取 ──
    if no_reflect:
        print("\n[Stage 3] 一次性三元组抽取（无反思模式）...")
    else:
        print("\n[Stage 3] 反思式三元组抽取...")

    store = TripletStore(
        source_file=doc_result.source_file,
        policy_id=chunked_doc.policy_id,
        extract_time=datetime.now().isoformat(),
    )

    # 切换工作目录到项目根目录，确保数据存储路径正确
    os.chdir(PROJECT_ROOT)

    all_reflection_results = []
    print_lock = threading.Lock()

    if no_reflect:
        # ── 无反思模式：只用 SchemaGuidedExtractor 抽一次 ──
        extractor = SchemaGuidedExtractor()

        def _extract_chunk_no_reflect(idx, chunk):
            """单个 chunk 的抽取任务（无反思，线程安全）"""
            entities, triples = extractor.extract(chunk)
            result = ReflectionResult(
                entities=entities,
                triples=triples,
                iterations=1,
                converged=False,
            )
            with print_lock:
                print(f"\n  --- Chunk {idx+1}/{len(chunks)}: {chunk.heading} ---")
                print(f"  文本预览: {chunk.text[:80]}...")
                print(f"  完成: {len(entities)} 个实体, {len(triples)} 个三元组 (无反思)")
                for t in triples:
                    print(f"    ({t.subject.name}) -[{t.relation}]-> ({t.object_.name})")
            return idx, result

        print(f"  并行抽取（无反思）: {len(chunks)} 个 chunks, {MAX_EXTRACT_WORKERS} 并发")
        with ThreadPoolExecutor(max_workers=MAX_EXTRACT_WORKERS) as executor:
            futures = {
                executor.submit(_extract_chunk_no_reflect, i, chunk): i
                for i, chunk in enumerate(chunks)
            }
            results_map = {}
            for future in as_completed(futures):
                idx, result = future.result()
                results_map[idx] = result

        for i in range(len(chunks)):
            reflection_result = results_map[i]
            all_reflection_results.append(reflection_result)
            store.add_entities(reflection_result.entities)
            store.add_triples(reflection_result.triples)

    else:
        # ── 有反思模式：完整反思循环 ──
        reflector = ReflectiveAgent()

        def _extract_chunk(idx, chunk):
            """单个 chunk 的抽取任务（有反思，线程安全）"""
            result = reflector.extract_with_reflection(chunk)
            with print_lock:
                print(f"\n  --- Chunk {idx+1}/{len(chunks)}: {chunk.heading} ---")
                print(f"  文本预览: {chunk.text[:80]}...")
                print(f"  完成: {len(result.entities)} 个实体, {len(result.triples)} 个三元组, "
                      f"{result.iterations} 轮迭代, 收敛={'是' if result.converged else '否'}")
                for t in result.triples:
                    print(f"    ({t.subject.name}) -[{t.relation}]-> ({t.object_.name})")
            return idx, result

        print(f"  并行抽取（有反思）: {len(chunks)} 个 chunks, {MAX_EXTRACT_WORKERS} 并发")
        with ThreadPoolExecutor(max_workers=MAX_EXTRACT_WORKERS) as executor:
            futures = {
                executor.submit(_extract_chunk, i, chunk): i
                for i, chunk in enumerate(chunks)
            }
            results_map = {}
            for future in as_completed(futures):
                idx, result = future.result()
                results_map[idx] = result

        for i in range(len(chunks)):
            reflection_result = results_map[i]
            all_reflection_results.append(reflection_result)
            store.add_entities(reflection_result.entities)
            store.add_triples(reflection_result.triples)

    # 记录 Stage 3 输出
    run_log.log_stage3_summary(all_reflection_results)
    json_log.log_stage3(all_reflection_results)

    # ── Stage 4: 存储（JSON） ──
    print("\n[Stage 4] 存储三元组...")
    output_path = store.save()
    print(f"  JSON 已保存: {output_path}")
    stats = store.compute_stats()
    print(f"  实体总数: {stats['total_entities']}")
    print(f"  三元组总数: {stats['total_triples']}")
    print(f"  实体类型分布: {stats['entity_type_distribution']}")
    print(f"  关系类型分布: {stats['relation_type_distribution']}")

    if no_reflect:
        # 无反思模式：跳过 Neo4j 双写
        print("  [无反思模式] 跳过 Neo4j 双写")
        neo4j_store = None
    else:
        # 有反思模式：Neo4j 双写
        neo4j_store = None
        try:
            neo4j_store = Neo4jStore()
            neo4j_store.ensure_constraints()
            neo4j_store.set_metadata(
                source_file=doc_result.source_file,
                policy_id=chunked_doc.policy_id,
                extract_time=datetime.now().isoformat(),
            )
            json_entities = [
                Entity(
                    name=e["name"],
                    entity_type=e["type"],
                    attributes=e.get("attributes", {}),
                    source_chunk_id=e.get("source_chunk_id", ""),
                )
                for e in store.entities
            ]
            json_triples = [
                Triple(
                    subject=Entity(name=t["subject"]["name"], entity_type=t["subject"]["type"]),
                    relation=t["relation"],
                    object_=Entity(name=t["object"]["name"], entity_type=t["object"]["type"]),
                    confidence=t.get("confidence", 1.0),
                    source_text=t.get("source_text", ""),
                )
                for t in store.triples
            ]
            neo4j_store.add_entities(json_entities)
            neo4j_store.add_triples(json_triples)
            neo4j_stats = neo4j_store.compute_stats()
            print(f"  Neo4j 双写: {neo4j_stats['total_entities']} 实体, {neo4j_stats['total_triples']} 三元组")
        except Exception as e:
            logger.warning(f"Neo4j 双写失败（不影响 JSON 存储）: {e}")
            neo4j_store = None

    run_log.log_stage4_output(store)
    json_log.log_stage4(store)

    # ── Stage 5: 四层一体化评估 ──
    print("\n[Stage 5] 四层一体化评估...")
    llm_client = get_reasoning_llm_client()
    evaluator = Evaluator(llm_client=llm_client)

    last_reflection = all_reflection_results[-1] if all_reflection_results else None
    source_text = doc_result.full_text[:3000]

    report = evaluator.evaluate(
        store,
        reflection_result=last_reflection,
        num_chunks=len(chunks),
        source_text=source_text,
        enable_llm_judge=True,
    )
    print(report.to_text())
    run_log.log_stage5_output(report)
    json_log.log_stage5(report)

    if no_reflect:
        # 无反思模式：跳过补图
        print("\n[无反思模式] 跳过补图（Action + Eligibility + Strategy）")
    else:
        # ── 补图：Action + Eligibility + Strategy ──
        print("\n[补图] 抽取 Action + Eligibility + Strategy...")
        from src.enhancement.enhancer import Enhancer

        enhancer = Enhancer(neo4j_store=neo4j_store)
        enhanced_store = enhancer.enhance_from_chunks_file(
            chunks_path=Path(chunked_path),
            store=store,
            policy_name=doc_result.title,
        )
        ent_before = stats['total_entities']
        tri_before = stats['total_triples']
        new_stats = enhanced_store.compute_stats()
        ent_added = new_stats['total_entities'] - ent_before
        tri_added = new_stats['total_triples'] - tri_before
        print(f"  新增实体: {ent_added}, 新增三元组: {tri_added}")
        print(f"  补图后总计: {new_stats['total_entities']} 实体, {new_stats['total_triples']} 三元组")
        enhanced_output = enhanced_store.save()
        print(f"  补图结果已保存: {enhanced_output}")
        run_log.log_enhancement_output(enhanced_store, ent_added, tri_added)
        json_log.log_enhancement({
            "entities_added": ent_added,
            "triples_added": tri_added,
            "action_types": [e for e in enhanced_store.entities if e.get("type") == "ActionType"],
            "conditions": [e for e in enhanced_store.entities if e.get("type") == "Condition"],
            "strategies": [t for t in enhanced_store.triples if t.get("relation") == "leads_to"],
        })

    # 保存 JSON 运行记录
    json_log_path = json_log.save()
    print(f"\n  运行日志（Markdown）: {run_log.log_path}")
    print(f"  运行日志（JSON）: {json_log_path}")

    print("\n" + "=" * 60)
    print(f"端到端测试完成！[{mode_label}模式]")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="FinPolicyKGAgent 端到端测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python scripts/run_e2e_test.py                                    # 完整 Pipeline（有反思）
  python scripts/run_e2e_test.py "政策.pdf" --no-reflect            # 无反思模式
  python scripts/run_e2e_test.py --compare A.json B.json            # 对比两份运行日志""",
    )
    parser.add_argument(
        "pdf",
        nargs="?",
        default="深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）.pdf",
        help="PDF 文件名（在 data/raw/ 下）",
    )
    parser.add_argument(
        "--no-reflect",
        action="store_true",
        help="无反思模式：跳过批判+修正，只做初始抽取；不补图、不写 Neo4j",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("JSON1", "JSON2"),
        help="对比两份运行日志 JSON，生成对比报告（不跑 Pipeline）",
    )

    args = parser.parse_args()

    if args.compare:
        # 对比模式
        compare_two_runs(args.compare[0], args.compare[1])
    else:
        # Pipeline 模式
        run_pipeline(pdf_name=args.pdf, no_reflect=args.no_reflect)


if __name__ == "__main__":
    main()
