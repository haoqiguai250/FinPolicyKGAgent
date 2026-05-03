"""
图扰动器

基于图扰动的解释层核心：
逐个删除关键节点 → 重新生成建议 → 对比差异 → 推断重要性

实现 KG-RAG 论文方案中的 explainability 部分
"""

from dataclasses import dataclass, field
from typing import Optional
from copy import deepcopy

from loguru import logger

from src.storage.triplet_store import TripletStore
from src.decision.graph_retriever import GraphRetriever, RetrievalResult
from src.decision.intent_recognizer import EnterpriseProfile
from src.decision.path_to_text import PathToTextConverter
from src.decision.rag_generator import RAGGenerator


@dataclass
class PerturbationResult:
    """单个节点扰动结果"""
    node_name: str
    node_type: str
    original_answer: str
    perturbed_answer: str
    importance_score: float = 0.0  # 0~1，越高越重要
    change_description: str = ""


@dataclass
class PerturbationReport:
    """扰动分析报告"""
    original_answer: str
    perturbations: list[PerturbationResult] = field(default_factory=list)
    ranked_nodes: list[dict] = field(default_factory=list)  # 按重要性排序

    def to_dict(self) -> dict:
        return {
            "original_answer_length": len(self.original_answer),
            "perturbation_count": len(self.perturbations),
            "ranked_nodes": self.ranked_nodes,
        }


class Perturbator:
    """图扰动器"""

    def __init__(
        self,
        retriever: GraphRetriever,
        generator: RAGGenerator,
        converter: Optional[PathToTextConverter] = None,
    ):
        self.retriever = retriever
        self.generator = generator
        self.converter = converter or PathToTextConverter()

    def analyze(
        self,
        query: str,
        profile: EnterpriseProfile,
        original_result: RetrievalResult,
        original_answer: str,
    ) -> PerturbationReport:
        """
        执行图扰动分析

        对检索路径中的关键节点逐一删除，重新检索+生成，对比差异

        Args:
            query: 用户原始问题
            profile: 企业画像
            original_result: 原始检索结果
            original_answer: 原始 RAG 生成回答

        Returns:
            PerturbationReport
        """
        report = PerturbationReport(original_answer=original_answer)

        # 收集关键节点
        key_nodes = self._collect_key_nodes(original_result)

        if not key_nodes:
            logger.info("无关键节点可扰动")
            return report

        logger.info(f"开始扰动分析: {len(key_nodes)} 个关键节点")

        for node_name, node_type in key_nodes:
            try:
                # 创建扰动后的 store（删除该节点的所有相关三元组）
                perturbed_store = self._perturb_node(node_name, node_type)

                if perturbed_store is None:
                    continue

                # 重新检索
                perturbed_retriever = GraphRetriever(store=perturbed_store)
                perturbed_retrieval = perturbed_retriever.retrieve(profile)

                # 重新生成
                perturbed_context = self.converter.convert(perturbed_retrieval)
                perturbed_rag = self.generator.generate(query, profile, perturbed_context)
                perturbed_answer = perturbed_rag.answer

                # 计算重要性（基于答案差异度）
                importance = self._compute_importance(original_answer, perturbed_answer)

                # 生成变化描述
                change_desc = self._describe_change(
                    node_name, node_type, original_answer, perturbed_answer, importance
                )

                result = PerturbationResult(
                    node_name=node_name,
                    node_type=node_type,
                    original_answer=original_answer,
                    perturbed_answer=perturbed_answer,
                    importance_score=importance,
                    change_description=change_desc,
                )
                report.perturbations.append(result)

                logger.info(
                    f"扰动 {node_type}({node_name}): "
                    f"importance={importance:.2%}"
                )

            except Exception as e:
                logger.error(f"扰动 {node_type}({node_name}) 失败: {e}")

        # 按重要性排序
        report.ranked_nodes = sorted(
            [
                {
                    "name": p.node_name,
                    "type": p.node_type,
                    "importance": round(p.importance_score, 3),
                    "description": p.change_description,
                }
                for p in report.perturbations
            ],
            key=lambda x: x["importance"],
            reverse=True,
        )

        logger.info(f"扰动分析完成: {len(report.ranked_nodes)} 个节点已排序")
        return report

    def _collect_key_nodes(self, result: RetrievalResult) -> list[tuple[str, str]]:
        """收集检索路径中的关键节点"""
        nodes = set()
        for path in result.paths:
            # Policy 节点
            nodes.add((path.policy_name, "Policy"))
            # ActionType 节点
            nodes.add((path.action_type, "ActionType"))
            # Condition 节点
            for c in path.conditions:
                nodes.add((c["value"], "Condition"))
            # Strategy 节点
            for s in path.strategies:
                nodes.add((s, "Strategy"))
        return list(nodes)

    def _perturb_node(self, node_name: str, node_type: str) -> Optional[TripletStore]:
        """
        扰动：删除包含该节点的所有三元组

        Returns:
            扰动后的 TripletStore（深拷贝），或 None
        """
        # 深拷贝当前 store
        import json
        store_data = {
            "source_file": self.retriever.store.source_file,
            "policy_id": self.retriever.store.policy_id,
            "extract_time": self.retriever.store.extract_time,
            "entities": deepcopy(self.retriever.store.entities),
            "triples": deepcopy(self.retriever.store.triples),
            "stats": {},
        }

        # 过滤包含该节点的三元组
        original_count = len(store_data["triples"])
        store_data["triples"] = [
            t for t in store_data["triples"]
            if not (
                t["subject"]["name"] == node_name or
                t["object"]["name"] == node_name
            )
        ]
        removed = original_count - len(store_data["triples"])

        if removed == 0:
            logger.debug(f"节点 {node_type}({node_name}) 未参与任何三元组，跳过")
            return None

        # 创建新的 TripletStore
        perturbed = TripletStore(
            source_file=store_data["source_file"],
            policy_id=store_data["policy_id"],
            extract_time=store_data["extract_time"],
            entities=store_data["entities"],
            triples=store_data["triples"],
        )
        perturbed.compute_stats()
        return perturbed

    @staticmethod
    def _compute_importance(original: str, perturbed: str) -> float:
        """
        计算重要性分数

        基于答案长度和内容变化的简单度量：
        - 答案大幅缩短 → 重要（缺失关键信息）
        - 答案完全不同 → 重要
        - 答案几乎不变 → 次要

        后续可升级为 LLM 判定或语义相似度
        """
        if not original or not perturbed:
            return 1.0 if original else 0.0

        # 字符级差异率
        len_orig = len(original)
        len_pert = len(perturbed)
        len_diff = abs(len_orig - len_pert) / max(len_orig, 1)

        # 简单词重叠率
        orig_words = set(original)
        pert_words = set(perturbed)
        if orig_words:
            overlap = len(orig_words & pert_words) / len(orig_words)
        else:
            overlap = 1.0

        # 重要性 = 1 - 重叠率（差异越大越重要），同时考虑长度变化
        importance = (1 - overlap) * 0.7 + len_diff * 0.3
        return min(max(importance, 0.0), 1.0)

    @staticmethod
    def _describe_change(
        node_name: str,
        node_type: str,
        original: str,
        perturbed: str,
        importance: float,
    ) -> str:
        """生成变化描述"""
        if importance > 0.7:
            level = "关键"
        elif importance > 0.3:
            level = "重要"
        else:
            level = "次要"

        orig_len = len(original)
        pert_len = len(perturbed)
        change = f"回答从 {orig_len} 字变为 {pert_len} 字"

        return f"{level}节点: 删除{node_type}({node_name})后，{change}，重要性 {importance:.0%}"
