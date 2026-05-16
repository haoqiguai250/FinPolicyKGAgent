"""
Stage 4: 三元组存储模块（Neo4j 版）

替代 TripletStore JSON 版本：
- MERGE 去重（天然支持跨文档实体去重）
- Cypher 路径查询（替代内存索引）
- DETACH DELETE 扰动（替代深拷贝）
- JSON 导出备份
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger
from neo4j import GraphDatabase, Driver, ManagedTransaction

from src.extraction.schema import Entity, Triple
from src.storage.cypher_queries import (
    CONSTRAINT_QUERIES,
    MERGE_NODE_TEMPLATE,
    MERGE_RELATION_TEMPLATE,
    COUNT_ALL_NODES,
    COUNT_ALL_RELATIONSHIPS,
    COUNT_TOTAL_NODES,
    COUNT_TOTAL_RELATIONSHIPS,
    EXPORT_ALL_NODES,
    EXPORT_ALL_RELATIONSHIPS,
)
from config.settings import settings


# ── Entity 类型 → Neo4j Label 映射 ──

# Schema 中的子类映射到父类 Label（Neo4j 用单 Label 简化查询）
_ENTITY_TYPE_TO_LABEL: dict[str, str] = {
    "Policy": "Policy",
    "MonetaryPolicy": "Policy",      # 子类 → 父类 Label
    "FiscalPolicy": "Policy",
    "RegulatoryPolicy": "Policy",
    "Institution": "Institution",
    "FinancialConcept": "FinancialConcept",
    "InterestRate": "FinancialConcept",
    "ReserveRatio": "FinancialConcept",
    "TaxRate": "FinancialConcept",
    "Quota": "FinancialConcept",
    "Market": "Market",
    "Instrument": "FinancialConcept",
    "Event": "Event",
    "Indicator": "Indicator",
    "Person": "Person",
    "Document": "Document",
    "ActionType": "ActionType",
    "Condition": "Condition",
    "Strategy": "Strategy",
    "Region": "Region",
    "CompanyType": "CompanyType",
    "Industry": "Industry",
}


def _get_label(entity_type: str) -> str:
    """将 Entity 类型映射到 Neo4j Label"""
    label = _ENTITY_TYPE_TO_LABEL.get(entity_type)
    if label is None:
        # 未知类型用原名，发出警告
        logger.warning(f"未知实体类型: {entity_type}，直接用作 Label")
        return entity_type
    return label


class Neo4jStore:
    """
    Neo4j 三元组存储

    接口与 TripletStore 兼容，内部使用 Cypher MERGE 去重
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self.database = database or settings.NEO4J_DATABASE

        self._driver: Optional[Driver] = None
        self._source_file: str = ""
        self._policy_id: str = ""
        self._extract_time: str = ""

    # ── 连接管理 ──

    @property
    def driver(self) -> Driver:
        """懒加载 Driver"""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            # 验证连接
            self._driver.verify_connectivity()
            logger.info(f"Neo4j 已连接: {self.uri}")
        return self._driver

    def close(self):
        """关闭连接"""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j 连接已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ── 初始化 ──

    def ensure_constraints(self):
        """创建唯一约束（幂等）"""
        with self.driver.session(database=self.database) as session:
            for label, query in CONSTRAINT_QUERIES.items():
                try:
                    session.run(query)
                    logger.debug(f"约束已确保: {label}")
                except Exception as e:
                    logger.warning(f"约束创建失败（可能已存在）: {label} - {e}")

    def clear_all(self):
        """⚠️ 清空所有数据（仅用于测试）"""
        with self.driver.session(database=self.database) as session:
            session.run("MATCH (n) DETACH DELETE n")
            logger.warning("已清空 Neo4j 所有数据")

    # ── 元数据 ──

    def set_metadata(self, source_file: str = "", policy_id: str = "", extract_time: str = ""):
        """设置元数据"""
        self._source_file = source_file
        self._policy_id = policy_id
        self._extract_time = extract_time or datetime.now().isoformat()

    @property
    def source_file(self) -> str:
        return self._source_file

    @property
    def policy_id(self) -> str:
        return self._policy_id

    # ── 写入 ──

    def add_entities(self, entities: list[Entity]) -> int:
        """
        批量添加实体（MERGE 去重，并行写入）

        每条 entity 在独立线程中 MERGE，Neo4j driver 支持并发 session。
        MERGE 幂等 + unique constraint 保证并行安全。

        Returns:
            新增实体数
        """
        if not entities:
            return 0

        def _merge_one(e: Entity) -> bool:
            """单条 entity MERGE，返回是否新建"""
            label = _get_label(e.entity_type)
            props = dict(e.attributes)
            props["name"] = e.name
            props["entity_type"] = e.entity_type
            if e.source_chunk_id:
                props["source_chunk_id"] = e.source_chunk_id
            # 为 Policy 节点添加 source_file，支持按来源筛选
            if label == "Policy" and self._source_file:
                props["source_file"] = self._source_file

            query = MERGE_NODE_TEMPLATE.format(label=label)
            with self.driver.session(database=self.database) as session:
                result = session.run(query, name=e.name, props=props)
                summary = result.consume()
                return summary.counters.nodes_created > 0

        added = 0
        max_workers = min(settings.CHUNK_PARALLEL_WORKERS, len(entities))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_merge_one, e): e for e in entities}
            for fut in as_completed(futures):
                try:
                    if fut.result():
                        added += 1
                except Exception as e:
                    entity = futures[fut]
                    logger.warning(f"Neo4j MERGE entity 失败: {entity.name} - {e}")

        logger.debug(f"add_entities: {added}/{len(entities)} 新增 (并行 {max_workers})")
        return added

    def add_triples(self, triples: list[Triple]) -> int:
        """
        批量添加三元组关系（MERGE 去重，并行写入）

        注意：调用前需确保 subject/object 节点已写入（add_entities 先于 add_triples）。
        每条 triple 在独立线程中 MERGE，MERGE 幂等保证并行安全。

        Returns:
            新增关系数
        """
        if not triples:
            return 0

        def _merge_one(t: Triple) -> bool:
            """单条 triple MERGE，返回是否新建"""
            subj_label = _get_label(t.subject.entity_type)
            obj_label = _get_label(t.object_.entity_type)
            rel_type = t.relation

            query = MERGE_RELATION_TEMPLATE.format(
                subj_label=subj_label,
                obj_label=obj_label,
                rel_type=rel_type,
            )
            rel_props = {
                "confidence": t.confidence,
            }
            if t.source_text:
                rel_props["source_text"] = t.source_text
            if t.source_chunk_id:
                rel_props["source_chunk_id"] = t.source_chunk_id

            with self.driver.session(database=self.database) as session:
                result = session.run(
                    query,
                    subj_name=t.subject.name,
                    obj_name=t.object_.name,
                    props=rel_props,
                )
                summary = result.consume()
                return summary.counters.relationships_created > 0

        added = 0
        max_workers = min(settings.CHUNK_PARALLEL_WORKERS, len(triples))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_merge_one, t): t for t in triples}
            for fut in as_completed(futures):
                try:
                    if fut.result():
                        added += 1
                except Exception as e:
                    triple = futures[fut]
                    logger.warning(f"Neo4j MERGE triple 失败: {triple.subject.name}-[{triple.relation}]->{triple.object_.name} - {e}")

        logger.debug(f"add_triples: {added}/{len(triples)} 新增 (并行 {max_workers})")
        return added

    # ── 统计 ──

    def compute_stats(self) -> dict:
        """计算统计信息"""
        with self.driver.session(database=self.database) as session:
            # 节点统计
            node_result = session.run(COUNT_ALL_NODES)
            entity_types = {}
            total_entities = 0
            for record in node_result:
                label = record["label"]
                count = record["count"]
                entity_types[label] = count
                total_entities += count

            # 关系统计
            rel_result = session.run(COUNT_ALL_RELATIONSHIPS)
            relation_types = {}
            total_triples = 0
            for record in rel_result:
                rel_type = record["rel_type"]
                count = record["count"]
                relation_types[rel_type] = count
                total_triples += count

        stats = {
            "total_entities": total_entities,
            "total_triples": total_triples,
            "entity_type_distribution": entity_types,
            "relation_type_distribution": relation_types,
        }

        # 统计政策文档数：从 RAW_DIR 统计 PDF 文件数
        try:
            pdf_count = len(list(settings.RAW_DIR.glob("*.pdf")))
            stats["policy_document_count"] = pdf_count
        except Exception as e:
            logger.warning(f"统计政策文档数失败: {e}")
            stats["policy_document_count"] = 0

        # 政策文档名称列表
        try:
            stats["policy_documents"] = sorted(
                p.stem for p in settings.RAW_DIR.glob("*.pdf")
            )
        except Exception as e:
            logger.warning(f"获取政策文档列表失败: {e}")
            stats["policy_documents"] = []

        return stats

    # ── 导出 JSON（备份） ──

    def save(self, output_path: Optional[Path] = None) -> Path:
        """
        导出到 JSON 文件（备份用）

        Neo4j 数据持久化由数据库自身管理，
        此方法将图数据导出为与 TripletStore 兼容的 JSON 格式
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = self._source_file or "neo4j_export"
            output_path = settings.EXPORTS_DIR / f"{name}_{timestamp}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = self._export_to_dict()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Neo4j 数据已导出: {output_path}")
        stats = data.get("stats", {})
        logger.info(
            f"统计: {stats.get('total_entities', 0)} 实体, "
            f"{stats.get('total_triples', 0)} 三元组"
        )
        return output_path

    def _export_to_dict(self) -> dict:
        """将 Neo4j 图数据导出为 TripletStore 兼容的 dict"""
        with self.driver.session(database=self.database) as session:
            # 导出节点
            node_result = session.run(EXPORT_ALL_NODES)
            entities = []
            for record in node_result:
                attrs = dict(record["attributes"])
                # 移除系统字段
                name = attrs.pop("name", record["name"])
                entity_type = attrs.pop("entity_type", record["type"])
                source_chunk_id = attrs.pop("source_chunk_id", "")
                entities.append({
                    "name": name,
                    "type": entity_type,
                    "attributes": attrs,
                    "source_chunk_id": source_chunk_id,
                })

            # 导出关系
            rel_result = session.run(EXPORT_ALL_RELATIONSHIPS)
            triples = []
            for record in rel_result:
                rel_props = dict(record["rel_props"])
                confidence = rel_props.pop("confidence", 1.0)
                source_text = rel_props.pop("source_text", "")
                triples.append({
                    "subject": {"name": record["subj_name"], "type": record["subj_type"]},
                    "relation": record["relation"],
                    "object": {"name": record["obj_name"], "type": record["obj_type"]},
                    "confidence": confidence,
                    "source_text": source_text,
                })

        stats = self.compute_stats()
        return {
            "source_file": self._source_file,
            "policy_id": self._policy_id,
            "extract_time": self._extract_time,
            "entities": entities,
            "triples": triples,
            "stats": stats,
        }

    # ── 从 JSON 加载 ──

    @classmethod
    def load_from_json(cls, path: Path, **kwargs) -> "Neo4jStore":
        """从 TripletStore JSON 文件导入到 Neo4j"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        store = cls(**kwargs)
        store.set_metadata(
            source_file=data.get("source_file", ""),
            policy_id=data.get("policy_id", ""),
            extract_time=data.get("extract_time", ""),
        )

        # 导入实体
        entities = [
            Entity(
                name=e["name"],
                entity_type=e["type"],
                attributes=e.get("attributes", {}),
                source_chunk_id=e.get("source_chunk_id", ""),
            )
            for e in data.get("entities", [])
        ]
        store.add_entities(entities)

        # 导入三元组
        triples = [
            Triple(
                subject=Entity(name=t["subject"]["name"], entity_type=t["subject"]["type"]),
                relation=t["relation"],
                object_=Entity(name=t["object"]["name"], entity_type=t["object"]["type"]),
                confidence=t.get("confidence", 1.0),
                source_text=t.get("source_text", ""),
            )
            for t in data.get("triples", [])
        ]
        store.add_triples(triples)

        logger.info(
            f"JSON 导入完成: {len(entities)} 实体, {len(triples)} 三元组"
        )
        return store

    # ── 合并（从另一个 store 导入） ──

    def merge_from_json_store(self, json_store_path: Path) -> dict:
        """从 TripletStore JSON 合并数据到 Neo4j（MERGE 自动去重）"""
        with open(json_store_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        ent_before = self.compute_stats()["total_entities"]
        tri_before = self.compute_stats()["total_triples"]

        # MERGE 自动去重，直接添加
        entities = [
            Entity(
                name=e["name"],
                entity_type=e["type"],
                attributes=e.get("attributes", {}),
                source_chunk_id=e.get("source_chunk_id", ""),
            )
            for e in data.get("entities", [])
        ]
        ent_added = self.add_entities(entities)

        triples = [
            Triple(
                subject=Entity(name=t["subject"]["name"], entity_type=t["subject"]["type"]),
                relation=t["relation"],
                object_=Entity(name=t["object"]["name"], entity_type=t["object"]["type"]),
                confidence=t.get("confidence", 1.0),
                source_text=t.get("source_text", ""),
            )
            for t in data.get("triples", [])
        ]
        tri_added = self.add_triples(triples)

        return {"entities_added": ent_added, "triples_added": tri_added}

    # ── 图扰动支持 ──

    def detach_delete_node(self, name: str, label: str) -> int:
        """
        删除节点及其所有关系（用于图扰动）

        Returns:
            删除的节点数
        """
        from src.storage.cypher_queries import DETACH_DELETE_NODE
        with self.driver.session(database=self.database) as session:
            result = session.run(DETACH_DELETE_NODE, name=name, label=label)
            record = result.single()
            deleted = record["deleted"] if record else 0
        logger.debug(f"DETACH DELETE {label}({name}): {deleted} 节点")
        return deleted

    def count_node_relationships(self, name: str, label: str) -> int:
        """查询节点参与的关系数"""
        from src.storage.cypher_queries import COUNT_NODE_RELATIONSHIPS
        with self.driver.session(database=self.database) as session:
            result = session.run(COUNT_NODE_RELATIONSHIPS, name=name, label=label)
            record = result.single()
            return record["rel_count"] if record else 0
