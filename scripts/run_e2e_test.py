"""端到端测试：PDF → 解析 → 分割 → 抽取 → 反思 → 存储（Neo4j+JSON）→ 评估"""
import sys
import os

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

from src.ingestion.parser import DoclingParser
from src.ingestion.chunker import SectionAwareChunker
from src.extraction.extractor import SchemaGuidedExtractor
from src.extraction.reflector import ReflectiveAgent
from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.evaluation.evaluator import Evaluator
from src.extraction.llm_client import get_llm_client, get_reasoning_llm_client
from src.core.run_logger import PipelineRunLogger, JsonRunLogger
from loguru import logger


def main():
    # 使用项目根目录的绝对路径，避免工作目录不同导致找不到文件
    project_root = PROJECT_ROOT

    # 支持命令行指定 PDF 文件名，默认使用瞪羚企业政策
    if len(sys.argv) > 1:
        pdf_name = sys.argv[1]
    else:
        pdf_name = "深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）.pdf"
    pdf_path = os.path.join(project_root, "data", "raw", pdf_name)

    if not os.path.exists(pdf_path):
        print(f"PDF 文件不存在: {pdf_path}")
        return

    # 初始化运行记录器
    run_log = PipelineRunLogger(source_file=pdf_name)
    json_log = JsonRunLogger(source_file=pdf_name)

    print("=" * 60)
    print("FinPolicyKGAgent 端到端测试")
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
    # 保存解析结果到 data/processed/
    parsed_path = doc_result.save()
    print(f"  解析结果已保存: {parsed_path}")
    # 记录 Stage 1 输出
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
    # 保存分块结果到 data/processed/
    chunked_path = chunked_doc.save()
    print(f"  分块结果已保存: {chunked_path}")
    # 记录 Stage 2 输出
    run_log.log_stage2_output(chunked_doc)
    json_log.log_stage2(chunked_doc)

    # ── Stage 3: 反思式三元组抽取 ──
    print("\n[Stage 3] 反思式三元组抽取...")
    reflector = ReflectiveAgent()
    store = TripletStore(
        source_file=doc_result.source_file,
        policy_id=chunked_doc.policy_id,
        extract_time=__import__("datetime").datetime.now().isoformat(),
    )

    # 切换工作目录到项目根目录，确保数据存储路径正确
    os.chdir(PROJECT_ROOT)

    all_reflection_results = []

    for i, chunk in enumerate(chunks):  # 跑全部 chunk
        print(f"\n  --- Chunk {i+1}/{len(chunks)}: {chunk.heading} ---")
        print(f"  文本预览: {chunk.text[:80]}...")

        # 反思式抽取（包含初次抽取 + 批判 + 修正循环）
        print(f"  开始反思式抽取...")
        reflection_result = reflector.extract_with_reflection(chunk)
        all_reflection_results.append(reflection_result)

        entities = reflection_result.entities
        triples = reflection_result.triples
        iterations = reflection_result.iterations
        converged = reflection_result.converged

        print(f"  完成: {len(entities)} 个实体, {len(triples)} 个三元组, "
              f"{iterations} 轮迭代, 收敛={'是' if converged else '否'}")

        # 打印三元组
        for t in triples:
            print(f"    ({t.subject.name}) -[{t.relation}]-> ({t.object_.name})")

        # 存入 store
        store.add_entities(entities)
        store.add_triples(triples)

    # 记录 Stage 3 输出
    run_log.log_stage3_summary(all_reflection_results)
    json_log.log_stage3(all_reflection_results)

    # ── Stage 4: 存储 ──
    print("\n[Stage 4] 存储三元组...")
    output_path = store.save()
    print(f"  JSON 已保存: {output_path}")
    stats = store.compute_stats()
    print(f"  实体总数: {stats['total_entities']}")
    print(f"  三元组总数: {stats['total_triples']}")
    print(f"  实体类型分布: {stats['entity_type_distribution']}")
    print(f"  关系类型分布: {stats['relation_type_distribution']}")

    # Neo4j 双写
    neo4j_store = None
    try:
        neo4j_store = Neo4jStore()
        neo4j_store.ensure_constraints()
        neo4j_store.set_metadata(
            source_file=doc_result.source_file,
            policy_id=chunked_doc.policy_id,
            extract_time=__import__("datetime").datetime.now().isoformat(),
        )
        # 将 JSON store 中的所有实体和三元组写入 Neo4j
        json_entities = [
            __import__("src.extraction.schema", fromlist=["Entity"]).Entity(
                name=e["name"],
                entity_type=e["type"],
                attributes=e.get("attributes", {}),
                source_chunk_id=e.get("source_chunk_id", ""),
            )
            for e in store.entities
        ]
        json_triples = [
            __import__("src.extraction.schema", fromlist=["Triple"]).Triple(
                subject=__import__("src.extraction.schema", fromlist=["Entity"]).Entity(
                    name=t["subject"]["name"], entity_type=t["subject"]["type"]
                ),
                relation=t["relation"],
                object_=__import__("src.extraction.schema", fromlist=["Entity"]).Entity(
                    name=t["object"]["name"], entity_type=t["object"]["type"]
                ),
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

    # 记录 Stage 4 输出
    run_log.log_stage4_output(store)
    json_log.log_stage4(store)

    # ── Stage 5: 四层一体化评估 ──
    print("\n[Stage 5] 四层一体化评估...")

    # 获取 LLM 客户端（用于 L4 评估，需要 reasoning）
    llm_client = get_reasoning_llm_client()
    evaluator = Evaluator(llm_client=llm_client)

    # 汇总所有 reflection_result
    last_reflection = all_reflection_results[-1] if all_reflection_results else None

    # 原文文本（用于 L4 忠实度评估）
    source_text = doc_result.full_text[:3000]  # 截断避免过长

    report = evaluator.evaluate(
        store,
        reflection_result=last_reflection,
        num_chunks=len(chunks),  # 实际处理的 chunk 数
        source_text=source_text,
        enable_llm_judge=True,      # 启用 L4 评估
    )
    print(report.to_text())
    # 记录 Stage 5 输出
    run_log.log_stage5_output(report)
    json_log.log_stage5(report)

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
    # 保存补图结果
    enhanced_output = enhanced_store.save()
    print(f"  补图结果已保存: {enhanced_output}")
    # 记录补图输出
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
    print("端到端测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
