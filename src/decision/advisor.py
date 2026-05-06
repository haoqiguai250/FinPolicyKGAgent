"""
决策支持总入口 — Advisor

完整流程：
1. IntentRecognizer: 自然语言 → 企业画像
2. GraphRetriever: 企业画像 → 图遍历 → 推理路径
3. PathToTextConverter: 推理路径 → 虚拟段落
4. RAGGenerator: 虚拟段落 + 问题 → 个性化建议
5. Perturbator: 节点扰动 → 重要性推断
6. ExplanationGenerator: 扰动报告 → 结构化解释

双输出：
- 个性化政策建议
- 可解释性分析

存储后端：
- Neo4j（推荐）：Cypher 路径查询 + DETACH DELETE 扰动
- JSON（兼容）：内存索引 + 深拷贝扰动
"""

import argparse
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Union

from loguru import logger

from src.extraction.llm_client import DeepSeekClient, get_reasoning_llm_client
from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.decision.intent_recognizer import IntentRecognizer, EnterpriseProfile
from src.decision.graph_retriever import GraphRetriever, RetrievalResult
from src.decision.path_to_text import PathToTextConverter
from src.decision.rag_generator import RAGGenerator, RAGResult
from src.decision.perturbator import Perturbator, PerturbationReport
from src.decision.explanation_generator import ExplanationGenerator, Explanation


@dataclass
class AdvisorResult:
    """决策支持完整结果"""
    query: str
    profile: EnterpriseProfile
    retrieval: RetrievalResult
    context: str
    rag_result: RAGResult
    perturbation_report: Optional[PerturbationReport] = None
    explanation: Optional[Explanation] = None

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "profile": self.profile.to_dict(),
            "answer": self.rag_result.answer,
            "matched_policies": self.retrieval.matched_policies,
            "matched_actions": self.retrieval.matched_actions,
            "matched_strategies": self.retrieval.matched_strategies,
            "explanation": self.explanation.to_dict() if self.explanation else None,
        }

    def to_summary(self) -> str:
        """生成人类可读的摘要"""
        lines = [
            f"📋 企业画像: {self._format_profile()}",
            f"",
            f"💡 政策建议:",
            self.rag_result.answer,
            f"",
            f"📊 匹配概况:",
            f"  - 政策: {', '.join(self.retrieval.matched_policies) or '无'}",
            f"  - 措施: {', '.join(self.retrieval.matched_actions) or '无'}",
            f"  - 策略: {', '.join(self.retrieval.matched_strategies) or '无'}",
        ]
        if self.explanation:
            lines.append(f"")
            lines.append(f"🔍 解释分析:")
            lines.append(self.explanation.summary)
        return "\n".join(lines)

    def _format_profile(self) -> str:
        parts = []
        if self.profile.region:
            parts.append(self.profile.region)
        if self.profile.company_type:
            parts.append(self.profile.company_type)
        if self.profile.industry:
            parts.append(self.profile.industry)
        return " | ".join(parts) if parts else "未指定"


class Advisor:
    """决策支持总入口

    支持两种存储后端：
    - Neo4jStore: Cypher 查询 + DETACH DELETE 扰动（推荐）
    - TripletStore: 内存索引 + 深拷贝扰动（兼容旧数据）
    """

    def __init__(
        self,
        store: Optional[TripletStore] = None,
        store_path: Optional[Path] = None,
        neo4j_store: Optional[Neo4jStore] = None,
        llm_client: Optional[DeepSeekClient] = None,
        enable_explanation: bool = True,
    ):
        """
        Args:
            store: 已加载的 TripletStore（JSON 后端）
            store_path: KG JSON 文件路径（JSON 后端）
            neo4j_store: 已连接的 Neo4jStore（Neo4j 后端，优先使用）
            llm_client: LLM 客户端
            enable_explanation: 是否启用解释层（扰动分析较耗时）
        """
        self.llm = llm_client or get_reasoning_llm_client()
        self.enable_explanation = enable_explanation
        self.neo4j_store = neo4j_store

        # 确定传给 GraphRetriever 的后端
        if neo4j_store:
            retriever_store = neo4j_store
            retriever_path = None
        else:
            retriever_store = store
            retriever_path = store_path

        # 构建模块链
        self.intent_recognizer = IntentRecognizer(self.llm)
        self.retriever = GraphRetriever(store=retriever_store, store_path=retriever_path)
        self.converter = PathToTextConverter()
        self.generator = RAGGenerator(self.llm)
        self.perturbator = Perturbator(self.retriever, self.generator, self.converter)
        self.explanation_generator = ExplanationGenerator()

    def advise(self, query: str) -> AdvisorResult:
        """
        执行完整决策支持流程

        Args:
            query: 用户自然语言查询

        Returns:
            AdvisorResult
        """
        logger.info(f"开始决策支持: {query}")

        # 1. 意图识别
        profile = self.intent_recognizer.recognize(query)

        # 2. 图检索
        retrieval = self.retriever.retrieve(profile)

        # 3. 路径转文本
        context = self.converter.convert(retrieval)

        # 4. RAG 生成
        rag_result = self.generator.generate(query, profile, context)

        # 5 & 6. 解释层（可选）
        perturbation_report = None
        explanation = None
        if self.enable_explanation and retrieval.paths:
            perturbation_report = self.perturbator.analyze(
                query=query,
                profile=profile,
                original_result=retrieval,
                original_answer=rag_result.answer,
            )
            explanation = self.explanation_generator.generate(perturbation_report)

        result = AdvisorResult(
            query=query,
            profile=profile,
            retrieval=retrieval,
            context=context,
            rag_result=rag_result,
            perturbation_report=perturbation_report,
            explanation=explanation,
        )

        logger.info(f"决策支持完成: {len(retrieval.paths)} 条路径, 解释={'是' if explanation else '否'}")
        return result


# ── 独立运行入口 ──

def run_advise(
    query: str,
    store_path: Optional[str] = None,
    output_path: Optional[str] = None,
    use_neo4j: bool = False,
):
    """独立运行决策支持

    Args:
        query: 用户查询
        store_path: KG JSON 文件路径（JSON 后端时必填）
        output_path: 结果输出路径
        use_neo4j: 是否使用 Neo4j 后端
    """
    neo4j_store = None
    store = None
    path = None

    if use_neo4j:
        try:
            from config.settings import settings
            neo4j_store = Neo4jStore(
                uri=settings.NEO4J_URI,
                user=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
                database=settings.NEO4J_DATABASE,
            )
            logger.info("Neo4j 后端已连接")
        except Exception as e:
            logger.error(f"Neo4j 连接失败，降级到 JSON: {e}")
            use_neo4j = False

    if not use_neo4j:
        if not store_path:
            logger.error("JSON 后端需指定 store_path")
            return
        path = Path(store_path)
        if not path.exists():
            logger.error(f"KG 文件不存在: {path}")
            return
        logger.info(f"JSON 后端: {path}")

    advisor = Advisor(store_path=path, neo4j_store=neo4j_store)
    result = advisor.advise(query)

    print(result.to_summary())

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存: {out}")

    # 关闭 Neo4j 连接
    if neo4j_store:
        neo4j_store.close()

    return result


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description="FinPolicyKG 决策支持")
    parser.add_argument("query", help="查询语句")
    parser.add_argument("--store", help="KG JSON 文件路径（JSON 后端时必填）")
    parser.add_argument("--output", help="结果输出路径")
    parser.add_argument("--neo4j", action="store_true", help="使用 Neo4j 后端")

    args = parser.parse_args()

    if not args.neo4j and not args.store:
        parser.error("JSON 后端需指定 --store 参数，或使用 --neo4j")

    run_advise(
        query=args.query,
        store_path=args.store,
        output_path=args.output,
        use_neo4j=args.neo4j,
    )
