"""端到端测试：央行公告 PDF → 解析 → 分割 → 抽取 → 反思 → 存储 → 评估"""
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

from src.ingestion.parser import DoclingParser
from src.ingestion.chunker import SectionAwareChunker
from src.extraction.extractor import SchemaGuidedExtractor
from src.extraction.reflector import ReflectiveAgent
from src.storage.triplet_store import TripletStore
from src.evaluation.evaluator import Evaluator
from src.extraction.llm_client import get_llm_client
from loguru import logger


def main():
    # 使用项目根目录的绝对路径，避免工作目录不同导致找不到文件
    project_root = PROJECT_ROOT
    pdf_path = os.path.join(project_root, "data", "raw", "中国人民银行公告〔2026〕第10号.pdf")

    if not os.path.exists(pdf_path):
        print(f"PDF 文件不存在: {pdf_path}")
        return

    print("=" * 60)
    print("FinPolicyKGAgent 端到端测试")
    print("=" * 60)

    # ── Stage 1: Docling 文档解析 ──
    print("\n[Stage 1] Docling 文档解析...")
    parser = DoclingParser()
    doc_result = parser.parse(pdf_path)
    print(f"  标题: {doc_result.title}")
    print(f"  章节数: {len(doc_result.sections)}")
    print(f"  总字符: {len(doc_result.full_text)}")
    for i, s in enumerate(doc_result.sections):
        heading = s.get("heading", "")
        level = s.get("level", 0)
        print(f"  [{i}] L{level} | {heading}")

    # ── Stage 2: 章节感知分割 ──
    print("\n[Stage 2] 章节感知分割...")
    chunker = SectionAwareChunker()
    chunked_doc = chunker.chunk(doc_result)
    chunks = chunked_doc.chunks
    print(f"  分块数: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"  [{i}] {chunk.heading} | {len(chunk.text)} chars | tokens~{chunk.token_count}")

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

    # ── Stage 4: 存储 ──
    print("\n[Stage 4] 存储三元组...")
    output_path = store.save()
    print(f"  已保存: {output_path}")
    stats = store.compute_stats()
    print(f"  实体总数: {stats['total_entities']}")
    print(f"  三元组总数: {stats['total_triples']}")
    print(f"  实体类型分布: {stats['entity_type_distribution']}")
    print(f"  关系类型分布: {stats['relation_type_distribution']}")

    # ── Stage 5: 四层一体化评估 ──
    print("\n[Stage 5] 四层一体化评估...")

    # 获取 LLM 客户端（用于 L4 评估）
    llm_client = get_llm_client()
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

    print("\n" + "=" * 60)
    print("端到端测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
