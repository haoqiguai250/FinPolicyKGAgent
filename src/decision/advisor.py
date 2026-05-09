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
    # ── LLM 直接生成结果（始终并行产出） ──
    llm_direct_result: RAGResult
    # ── 来源标记：kg_rag / llm_direct / both ──
    source: str = "both"
    perturbation_report: Optional[PerturbationReport] = None
    explanation: Optional[Explanation] = None

    def to_dict(self) -> dict:
        # ── 构建 reasoning_paths ──
        reasoning_paths = []
        for path in self.retrieval.paths:
            path_entry = path.to_dict()
            # 附加该路径的节点扰动信息（如果有）
            if self.perturbation_report:
                path_entry["perturbation_scores"] = [
                    {
                        "node": p["node"],
                        "display": p["display"],
                        "importance": p["importance"],
                        "reason": p["reason"],
                        "source_chunk_id": p["source_chunk_id"],
                        "source_text": p["source_text"],
                        "metric_scores": p.get("metric_scores", {}),
                    }
                    for p in self.perturbation_report.ranked_perturbations
                    # 只取属于当前路径的节点
                    if self._node_belongs_to(p, path)
                ]
            reasoning_paths.append(path_entry)

        # ── 双来源输出 ──
        kg_rag_answer = self.rag_result.answer if self.retrieval.paths else None
        llm_direct_answer = self.llm_direct_result.answer

        return {
            "query": self.query,
            "profile": self.profile.to_dict(),
            "source": self.source,
            "kg_rag_answer": kg_rag_answer,
            "llm_direct_answer": llm_direct_answer,
            "reasoning_paths": reasoning_paths,
            "matched_policies": self.retrieval.matched_policies,
            "matched_actions": self.retrieval.matched_actions,
            "matched_strategies": self.retrieval.matched_strategies,
            "explanation": self.explanation.to_dict() if self.explanation else None,
        }

    @staticmethod
    def _node_belongs_to(perturbed_node: dict, path: 'ReasoningPath') -> bool:
        """判断一个扰动节点是否属于某条 ReasoningPath"""
        node_info = perturbed_node.get("node", {})
        name = node_info.get("name", "")
        node_type = node_info.get("type", "")

        if node_type == "Policy":
            return path.policy_name == name
        elif node_type == "Condition":
            return any(c.get("value") == name for c in path.conditions)
        elif node_type == "ActionType":
            return path.action_type == name
        elif node_type == "Strategy":
            return name in path.strategies
        return False

    def to_summary(self) -> str:
        """生成人类可读的摘要"""
        lines = [
            f"📋 企业画像: {self._format_profile()}",
            f"",
        ]

        # ── KG-RAG 结果 ──
        if self.retrieval.paths:
            lines.append(f"💡 【KG-RAG 流程结果】(基于知识图谱推理)")
            lines.append(self.rag_result.answer)
            lines.append(f"")
            lines.append(f"📊 匹配概况:")
            lines.append(f"  - 政策: {', '.join(self.retrieval.matched_policies) or '无'}")
            lines.append(f"  - 措施: {', '.join(self.retrieval.matched_actions) or '无'}")
            lines.append(f"  - 策略: {', '.join(self.retrieval.matched_strategies) or '无'}")
        else:
            lines.append(f"⚠️ 【KG-RAG 流程结果】未匹配到相关政策")

        # ── LLM 直接结果 ──
        lines.append(f"")
        lines.append(f"🤖 【LLM 直接生成】(无知识图谱支撑，仅供参考)")
        lines.append(self.llm_direct_result.answer)

        # ── 解释分析 ──
        if self.explanation:
            lines.append(f"")
            lines.append(f"🔍 解释分析:")
            lines.append(self.explanation.summary)
            if self.explanation.detail_text:
                lines.append(self.explanation.detail_text)

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
        self.perturbator = Perturbator(
            self.retriever, self.generator, self.converter,
            llm_client=self.llm,
        )
        self.explanation_generator = ExplanationGenerator()

    def advise(self, query: str) -> AdvisorResult:
        """
        执行完整决策支持流程（双路生成）

        始终同时产出两条路径的结果：
        1. KG-RAG 流程：意图识别 → 图检索 → 路径转文本 → RAG 生成（+ 可选扰动分析）
        2. LLM 直接生成：直接将用户问题丢给 LLM

        Args:
            query: 用户自然语言查询

        Returns:
            AdvisorResult（含 kg_rag + llm_direct 双输出，source 标注来源）
        """
        logger.info(f"开始决策支持: {query}")

        # 1. 意图识别
        profile = self.intent_recognizer.recognize(query)

        # 2. 图检索
        retrieval = self.retriever.retrieve(profile)

        # 3. 路径转文本
        context = self.converter.convert(retrieval)

        # 4. RAG 生成（KG-RAG 路径）
        rag_result = self.generator.generate(query, profile, context)

        # 5. LLM 直接生成（始终执行，不依赖 KG 匹配结果）
        logger.info("执行 LLM 直接生成...")
        llm_direct_result = self.generator.generate_direct(query, profile)

        # 6 & 7. 解释层（KG 匹配时才触发扰动分析）
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
        elif not retrieval.paths:
            # KG 未匹配时生成友好提示
            available_policies = self._get_available_policies()
            explanation = self.explanation_generator.generate_no_match(available_policies)

        # 来源标记
        source = "both" if retrieval.paths else "llm_direct"

        result = AdvisorResult(
            query=query,
            profile=profile,
            retrieval=retrieval,
            context=context,
            rag_result=rag_result,
            llm_direct_result=llm_direct_result,
            source=source,
            perturbation_report=perturbation_report,
            explanation=explanation,
        )

        logger.info(
            f"决策支持完成: KG路径={len(retrieval.paths)}条, "
            f"来源={source}, 解释={'是' if explanation else '否'}"
        )
        return result

    def _get_available_policies(self) -> list[str]:
        """获取当前 KG 中已收录的政策列表（用于无匹配时的友好提示）"""
        policies = []
        try:
            if self.neo4j_store:
                from src.storage.cypher_queries import FIND_POLICIES_BY_CONDITIONS
                with self.neo4j_store.driver.session(database=self.neo4j_store.database) as session:
                    results = session.run(FIND_POLICIES_BY_CONDITIONS)
                    policies = [r["policy_name"] for r in results]
            elif self.retriever.store:
                # JSON 后端：从 policy_to_conditions 索引取
                policies = list(self.retriever.policy_to_conditions.keys())
        except Exception as e:
            logger.warning(f"获取已收录政策列表失败: {e}")
        return policies


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
