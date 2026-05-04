"""
图扰动器

基于图扰动的解释层核心：
逐个删除关键节点 → 重新生成建议 → 对比差异 → 推断重要性

支持两种后端：
1. Neo4j — DETACH DELETE + 重新 MERGE（无深拷贝，事务安全）
2. TripletStore JSON — 深拷贝（兼容旧数据）
"""

from dataclasses import dataclass, field
from typing import Optional, Union

from loguru import logger

from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.extraction.schema import Entity, Triple
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
    """
    图扰动器

    支持双后端：
    - Neo4j: DETACH DELETE + 重新 MERGE（高效，无 OOM 风险）
    - JSON: 深拷贝（兼容旧数据）
    """

    def __init__(
        self,
        retriever: GraphRetriever,
        generator: RAGGenerator,
        converter: Optional[PathToTextConverter] = None,
    ):
        self.retriever = retriever
        self.generator = generator
        self.converter = converter or PathToTextConverter()
        self._backend = retriever._backend

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
        """
        report = PerturbationReport(original_answer=original_answer)

        # 收集关键节点
        key_nodes = self._collect_key_nodes(original_result)

        if not key_nodes:
            logger.info("无关键节点可扰动")
            return report

        logger.info(f"开始扰动分析: {len(key_nodes)} 个关键节点 (后端: {self._backend})")

        for node_name, node_type in key_nodes:
            try:
                if self._backend == "neo4j":
                    success = self._perturb_neo4j(node_name, node_type)
                else:
                    success = self._perturb_json(node_name, node_type)

                if not success:
                    continue

                # 重新检索
                perturbed_retrieval = self.retriever.retrieve(profile)

                # 重新生成
                perturbed_context = self.converter.convert(perturbed_retrieval)
                perturbed_rag = self.generator.generate(query, profile, perturbed_context)
                perturbed_answer = perturbed_rag.answer

                # 计算重要性
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

                # Neo4j: 恢复节点
                if self._backend == "neo4j":
                    self._restore_neo4j_node(node_name, node_type)

            except Exception as e:
                logger.error(f"扰动 {node_type}({node_name}) 失败: {e}")
                # Neo4j: 确保恢复
                if self._backend == "neo4j":
                    self._restore_neo4j_node(node_name, node_type)

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
            nodes.add((path.policy_name, "Policy"))
            nodes.add((path.action_type, "ActionType"))
            for c in path.conditions:
                nodes.add((c["value"], "Condition"))
            for s in path.strategies:
                nodes.add((s, "Strategy"))
        return list(nodes)

    # ══════════════════════════════════════════
    # Neo4j 后端扰动
    # ══════════════════════════════════════════

    def _perturb_neo4j(self, node_name: str, node_type: str) -> bool:
        """
        Neo4j 扰动：DETACH DELETE 节点

        注意：扰动后需要重新检索+生成，然后 _restore_neo4j_node 恢复
        """
        neo4j_store = self.retriever.neo4j_store
        if neo4j_store is None:
            logger.error("Neo4j store 未初始化")
            return False

        # 检查节点是否有关系
        rel_count = neo4j_store.count_node_relationships(node_name, node_type)
        if rel_count == 0:
            logger.debug(f"节点 {node_type}({node_name}) 未参与任何关系，跳过")
            return False

        # 保存节点和关系数据用于恢复
        self._perturbed_backup = self._backup_neo4j_node(node_name, node_type)

        # DETACH DELETE
        neo4j_store.detach_delete_node(node_name, node_type)

        # 重建 GraphRetriever 索引（无需，Neo4j 实时查询）
        return True

    def _restore_neo4j_node(self, node_name: str, node_type: str):
        """恢复被扰动的 Neo4j 节点及其关系"""
        backup = getattr(self, '_perturbed_backup', None)
        if backup is None:
            return

        neo4j_store = self.retriever.neo4j_store
        if neo4j_store is None:
            return

        # 重新写入节点
        neo4j_store.add_entities([backup["entity"]])

        # 重新写入关系
        if backup["triples"]:
            neo4j_store.add_triples(backup["triples"])

        logger.debug(f"已恢复节点 {node_type}({node_name})")
        self._perturbed_backup = None

    def _backup_neo4j_node(self, node_name: str, node_type: str) -> dict:
        """备份 Neo4j 节点及其关系（用于扰动后恢复）"""
        neo4j_store = self.retriever.neo4j_store
        from src.storage.cypher_queries import EXPORT_ALL_NODES, EXPORT_ALL_RELATIONSHIPS

        entity = None
        triples = []

        with neo4j_store.driver.session(database=neo4j_store.database) as session:
            # 查找节点
            result = session.run(
                "MATCH (n) WHERE n.name = $name AND $label IN labels(n) "
                "RETURN labels(n)[0] AS type, n.name AS name, properties(n) AS props",
                name=node_name, label=node_type,
            )
            record = result.single()
            if record:
                props = dict(record["props"])
                name = props.pop("name", node_name)
                entity_type = props.pop("entity_type", node_type)
                source_chunk_id = props.pop("source_chunk_id", "")
                entity = Entity(
                    name=name,
                    entity_type=entity_type,
                    attributes=props,
                    source_chunk_id=source_chunk_id,
                )

            # 查找相关关系
            rel_result = session.run(
                "MATCH (s)-[r]->(o) "
                "WHERE s.name = $name OR o.name = $name "
                "RETURN labels(s)[0] AS s_type, s.name AS s_name, "
                "type(r) AS rel_type, properties(r) AS rel_props, "
                "labels(o)[0] AS o_type, o.name AS o_name",
                name=node_name,
            )
            for r in rel_result:
                rel_props = dict(r["rel_props"])
                confidence = rel_props.pop("confidence", 1.0)
                source_text = rel_props.pop("source_text", "")
                triples.append(Triple(
                    subject=Entity(name=r["s_name"], entity_type=r["s_type"]),
                    relation=r["rel_type"],
                    object_=Entity(name=r["o_name"], entity_type=r["o_type"]),
                    confidence=confidence,
                    source_text=source_text,
                ))

        return {"entity": entity, "triples": triples}

    # ══════════════════════════════════════════
    # JSON 后端扰动（原有逻辑）
    # ══════════════════════════════════════════

    def _perturb_json(self, node_name: str, node_type: str) -> bool:
        """
        JSON 扰动：创建深拷贝并过滤三元组

        Returns:
            True 如果扰动成功，创建新的 GraphRetriever
        """
        from copy import deepcopy

        store = self.retriever.store
        if store is None:
            return False

        # 深拷贝
        store_data = {
            "source_file": store.source_file,
            "policy_id": store.policy_id,
            "extract_time": store.extract_time,
            "entities": deepcopy(store.entities),
            "triples": deepcopy(store.triples),
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
            return False

        # 创建临时的 TripletStore 和 GraphRetriever
        perturbed_store = TripletStore(
            source_file=store_data["source_file"],
            policy_id=store_data["policy_id"],
            extract_time=store_data["extract_time"],
            entities=store_data["entities"],
            triples=store_data["triples"],
        )
        perturbed_store.compute_stats()

        # 替换 retriever 的 store（临时）
        self._original_store = self.retriever._json_store
        self.retriever._json_store = perturbed_store
        self.retriever._build_indexes()

        return True

    # ══════════════════════════════════════════
    # 共用方法
    # ══════════════════════════════════════════

    @staticmethod
    def _compute_importance(original: str, perturbed: str) -> float:
        """计算重要性分数"""
        if not original or not perturbed:
            return 1.0 if original else 0.0

        len_orig = len(original)
        len_pert = len(perturbed)
        len_diff = abs(len_orig - len_pert) / max(len_orig, 1)

        orig_words = set(original)
        pert_words = set(perturbed)
        if orig_words:
            overlap = len(orig_words & pert_words) / len(orig_words)
        else:
            overlap = 1.0

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
