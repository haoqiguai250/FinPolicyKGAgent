"""
决策支持端到端测试（不调 LLM，用 mock 数据）

验证完整的 Phase 1 + Phase 2 + Phase 3 流程：
1. 补图：从 mock chunks 抽取 → 写入 TripletStore
2. 查询：图遍历检索 → 路径转文本 → RAG 生成
3. 解释：图扰动 → 重要性推断 → 解释生成
"""

import json
from pathlib import Path

from src.extraction.schema import Entity, Triple
from src.storage.triplet_store import TripletStore
from src.enhancement.action_eligibility_extractor import ActionEligibilityExtractor, ExtractionResult
from src.enhancement.strategy_mapper import StrategyMapper
from src.enhancement.enhancer import Enhancer
from src.decision.intent_recognizer import EnterpriseProfile
from src.decision.graph_retriever import GraphRetriever, RetrievalResult
from src.decision.path_to_text import PathToTextConverter
from src.decision.perturbator import Perturbator
from src.decision.explanation_generator import ExplanationGenerator


def test_schema_extension():
    """测试 Schema 扩展"""
    from src.extraction.schema import EntityType, RelationType, ACTION_CATEGORIES, ACTION_KEYWORD_MAP

    # 新实体类型
    assert EntityType("ActionType") == EntityType.ACTION_TYPE
    assert EntityType("Condition") == EntityType.CONDITION
    assert EntityType("Strategy") == EntityType.STRATEGY
    assert EntityType("Region") == EntityType.REGION
    assert EntityType("CompanyType") == EntityType.COMPANY_TYPE
    assert EntityType("Industry") == EntityType.INDUSTRY

    # 新关系类型
    assert RelationType("provides") == RelationType.PROVIDES
    assert RelationType("has_eligibility") == RelationType.HAS_ELIGIBILITY
    assert RelationType("subregion_of") == RelationType.SUBREGION_OF

    # Action 关键词映射
    assert ACTION_KEYWORD_MAP["贷款"] == "融资类"
    assert ACTION_KEYWORD_MAP["补贴"] == "财政类"
    assert ACTION_KEYWORD_MAP["减税"] == "税收类"

    print("✅ Schema 扩展测试通过")


def test_strategy_mapper():
    """测试 Strategy 规则映射"""
    mapper = StrategyMapper()

    # 单类映射
    strategies = mapper.map_action_to_strategies("融资类")
    assert "扩大融资能力" in strategies
    assert "扩产" in strategies

    strategies = mapper.map_action_to_strategies("税收类")
    assert strategies == ["提高利润"]

    # 批量映射（去重）
    results = mapper.map_all(["融资类", "财政类", "融资类"])
    assert len(results) == 2  # 融资类去重后只出现一次
    print(f"  批量映射结果: {[(r.action_type, r.strategies) for r in results]}")

    print("✅ Strategy 规则映射测试通过")


def test_enhancer_mock():
    """测试 Enhancer 补图（用 mock ExtractionResult，不调 LLM）"""
    # 构建 mock 抽取结果
    results = [
        ExtractionResult(
            chunk_id="chunk_1",
            policy_name="《深圳市中小企业融资支持政策》",
            actions=[
                {"raw": "信贷支持", "type": "融资类"},
                {"raw": "贷款贴息", "type": "融资类"},
                {"raw": "减税降费", "type": "税收类"},
            ],
            eligibility={
                "region": "深圳",
                "company_type": "中小企业",
                "industry": None,
            },
        ),
    ]

    # 创建空 TripletStore
    store = TripletStore(source_file="test", policy_id="test_policy")

    # 手动执行 Enhancer._write_to_store
    enhancer = Enhancer.__new__(Enhancer)
    enhancer.mapper = StrategyMapper()
    ent_added, tri_added = enhancer._write_to_store(
        store, results, "《深圳市中小企业融资支持政策》"
    )

    # 验证写入结果
    stats = store.compute_stats()
    print(f"  实体数: {stats['total_entities']}")
    print(f"  三元组数: {stats['total_triples']}")
    print(f"  实体类型分布: {stats['entity_type_distribution']}")
    print(f"  关系类型分布: {stats['relation_type_distribution']}")

    # 验证关键结构
    entity_types = {e["type"] for e in store.entities}
    assert "ActionType" in entity_types
    assert "Condition" in entity_types
    assert "Strategy" in entity_types
    assert "Region" in entity_types

    relation_types = {t["relation"] for t in store.triples}
    assert "provides" in relation_types
    assert "has_eligibility" in relation_types
    assert "leads_to" in relation_types
    assert "subregion_of" in relation_types

    print("✅ Enhancer 补图测试通过")
    return store


def test_graph_retriever(store: TripletStore):
    """测试图检索"""
    retriever = GraphRetriever(store=store)

    # 构建企业画像
    profile = EnterpriseProfile(
        region="深圳",
        company_type="中小企业",
        industry="制造业",
    )

    # 检索
    result = retriever.retrieve(profile)
    print(f"  匹配政策: {result.matched_policies}")
    print(f"  匹配措施: {result.matched_actions}")
    print(f"  匹配策略: {result.matched_strategies}")
    print(f"  推理路径数: {len(result.paths)}")

    for path in result.paths:
        print(f"    {path.policy_name} → {path.action_type} → {path.strategies}")

    # 验证
    assert len(result.matched_policies) > 0, "应该匹配到政策"
    assert "融资类" in result.matched_actions, "应该匹配到融资类措施"
    assert "税收类" in result.matched_actions, "应该匹配到税收类措施"

    print("✅ 图检索测试通过")
    return result


def test_path_to_text(retrieval_result: RetrievalResult):
    """测试路径转文本"""
    converter = PathToTextConverter()
    text = converter.convert(retrieval_result)
    print(f"  虚拟段落:\n{text}")

    assert "融资类" in text, "应包含融资类"
    assert "税收类" in text, "应包含税收类"

    print("✅ 路径转文本测试通过")
    return text


def test_perturbator(retrieval_result: RetrievalResult, store: TripletStore):
    """测试图扰动"""
    from src.decision.rag_generator import RAGGenerator
    from unittest.mock import MagicMock

    # Mock RAGGenerator（不调 LLM）
    mock_generator = MagicMock(spec=RAGGenerator)
    from src.decision.rag_generator import RAGResult

    profile = EnterpriseProfile(region="深圳", company_type="中小企业")
    mock_generator.generate.return_value = RAGResult(
        answer="您可以通过信贷支持获得低息贷款，同时享受减税降费政策。",
        profile=profile,
        context_used="mock",
    )

    retriever = GraphRetriever(store=store)
    perturbator = Perturbator(retriever, mock_generator, PathToTextConverter())

    report = perturbator.analyze(
        query="深圳中小企业能享受什么政策",
        profile=profile,
        original_result=retrieval_result,
        original_answer="您可以通过信贷支持获得低息贷款，同时享受减税降费政策。",
    )

    print(f"  扰动节点数: {len(report.perturbations)}")
    for node in report.ranked_perturbations[:3]:
        print(f"    {node['type']}({node['name']}): 重要性={node['importance']}")

    assert len(report.perturbations) > 0, "应有扰动结果"

    # 生成解释
    expl_gen = ExplanationGenerator()
    explanation = expl_gen.generate(report)
    print(f"  解释摘要: {explanation.summary}")

    print("✅ 图扰动 + 解释测试通过")


def main():
    print("=" * 60)
    print("决策支持端到端测试")
    print("=" * 60)

    test_schema_extension()
    test_strategy_mapper()

    store = test_enhancer_mock()
    retrieval = test_graph_retriever(store)
    test_path_to_text(retrieval)
    test_perturbator(retrieval, store)

    print()
    print("=" * 60)
    print("🎉 全部测试通过！决策支持链路验证完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
