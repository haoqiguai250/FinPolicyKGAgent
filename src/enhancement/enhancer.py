"""
Enhancer Sidecar — 补图编排入口

Phase 1 完整流程：
1. 从 chunked.json 读取 chunks
2. 调用 ActionEligibilityExtractor 抽取 Action + Eligibility
3. 调用 StrategyMapper 规则映射 Strategy
4. 标准化 + 去重 + 写回 KG 存储（Neo4j + JSON 双写）
"""

import json
from pathlib import Path
from typing import Optional, Union

from loguru import logger

from src.extraction.schema import (
    Entity, Triple,
    REGION_HIERARCHY,
)
from src.extraction.llm_client import DeepSeekClient, get_llm_client
from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.enhancement.action_eligibility_extractor import (
    ActionEligibilityExtractor, ExtractionResult,
)
from src.enhancement.strategy_mapper import StrategyMapper
from config.settings import settings


class Enhancer:
    """补图编排器：Action + Eligibility + Strategy → KG（Neo4j + JSON 双写）"""

    def __init__(
        self,
        llm_client: Optional[DeepSeekClient] = None,
        neo4j_store: Optional[Neo4jStore] = None,
    ):
        self.llm = llm_client or get_llm_client()
        self.extractor = ActionEligibilityExtractor(self.llm)
        self.mapper = StrategyMapper()
        self._neo4j_store = neo4j_store  # 可选：同时写入 Neo4j

    def enhance_from_chunks_file(
        self,
        chunks_path: Path,
        store: Optional[TripletStore] = None,
        policy_name: str = "",
    ) -> TripletStore:
        """
        从 chunked.json 文件补图

        Args:
            chunks_path: chunked.json 文件路径
            store: 已有 TripletStore（None 则新建）
            policy_name: 政策名称

        Returns:
            增强后的 TripletStore
        """
        # 读取 chunks
        with open(chunks_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # chunked.json 可能是 dict 或 list
        if isinstance(data, dict):
            chunks = data.get("chunks", [])
            policy_name = policy_name or data.get("policy_name", "")
        elif isinstance(data, list):
            chunks = data
        else:
            logger.error(f"不支持的 chunked.json 格式: {type(data)}")
            chunks = []

        if not chunks:
            logger.warning(f"chunks 为空: {chunks_path}")
            return store or TripletStore(source_file=str(chunks_path))

        logger.info(f"读取 {len(chunks)} 个 chunks, policy={policy_name}")

        # 抽取
        extraction_results = self.extractor.extract_from_chunks(chunks)

        # 转换为 KG 实体和三元组
        if store is None:
            store = TripletStore(source_file=str(chunks_path), policy_id=policy_name)

        ent_added, tri_added = self._write_to_store(
            store, extraction_results, policy_name
        )

        # 双写 Neo4j
        if self._neo4j_store is not None:
            try:
                neo4j_ent, neo4j_tri = self._write_to_neo4j(
                    self._neo4j_store, extraction_results, policy_name
                )
                logger.info(f"Neo4j 双写: +{neo4j_ent} 实体, +{neo4j_tri} 三元组")
            except Exception as e:
                logger.error(f"Neo4j 双写失败（不影响 JSON 存储）: {e}")

        logger.info(f"补图完成: +{ent_added} 实体, +{tri_added} 三元组")
        return store

    def _write_to_store(
        self,
        store: TripletStore,
        results: list[ExtractionResult],
        policy_name: str,
    ) -> tuple[int, int]:
        """
        将抽取结果写回 TripletStore

        生成以下节点和边：
        - Policy ── provides ──→ ActionType
        - Policy ── has_eligibility ──→ Condition
        - ActionType ── leads_to ──→ Strategy
        - Region ── subregion_of ──→ Region（层级）

        Returns:
            (ent_added, tri_added): 新增的实体数和三元组数
        """
        # 记录写入前数量，用于计算增量
        ent_before = len(store.entities)
        tri_before = len(store.triples)

        # 收集去重后的 Action 大类
        action_type_set: dict[str, list[str]] = {}  # type → [raw1, raw2, ...]
        # 收集所有 eligibility
        all_eligibility: list[dict] = []

        # 先统计去重
        for r in results:
            for a in r.actions:
                cat = a["type"]
                raw = a["raw"]
                if cat not in action_type_set:
                    action_type_set[cat] = []
                if raw not in action_type_set[cat]:
                    action_type_set[cat].append(raw)

            if r.eligibility:
                all_eligibility.append(r.eligibility)

        # ── 写 ActionType 节点 + provides 边 ──
        policy_entity = Entity(name=policy_name, entity_type="Policy")
        for action_type, raws in action_type_set.items():
            action_entity = Entity(
                name=action_type,
                entity_type="ActionType",
                attributes={"category": action_type, "raw": raws},
            )
            store.add_entities([action_entity])

            # Policy → ActionType (provides)
            triple = Triple(
                subject=policy_entity,
                relation="provides",
                object_=action_entity,
                confidence=1.0,
                source_text=f"政策提供{action_type}措施",
            )
            store.add_triples([triple])

        # ── 写 Condition 节点 + has_eligibility 边 ──
        # 去重：同一 policy 的 condition 不重复
        seen_conditions = set()
        for elig in all_eligibility:
            for cat in ["region", "company_type", "industry"]:
                val = elig.get(cat)
                if not val:
                    continue
                cond_key = (cat, val)
                if cond_key in seen_conditions:
                    continue
                seen_conditions.add(cond_key)

                cond_entity = Entity(
                    name=val,
                    entity_type="Condition",
                    attributes={"category": cat, "value": val},
                )
                store.add_entities([cond_entity])

                # Policy → Condition (has_eligibility)
                triple = Triple(
                    subject=policy_entity,
                    relation="has_eligibility",
                    object_=cond_entity,
                    confidence=1.0,
                    source_text=f"政策适用于{cat}={val}",
                )
                store.add_triples([triple])

                # 如果是 region，写层级关系
                if cat == "region":
                    self._add_region_hierarchy(store, val)

        # ── 写 Strategy 节点 + leads_to 边 ──
        strategy_mappings = self.mapper.map_all(list(action_type_set.keys()))
        seen_strategies = set()
        for mapping in strategy_mappings:
            for strat_name in mapping.strategies:
                if strat_name in seen_strategies:
                    continue
                seen_strategies.add(strat_name)

                strat_entity = Entity(
                    name=strat_name,
                    entity_type="Strategy",
                    attributes={"name": strat_name},
                )
                store.add_entities([strat_entity])

                # ActionType → Strategy (leads_to)
                action_entity = Entity(name=mapping.action_type, entity_type="ActionType")
                triple = Triple(
                    subject=action_entity,
                    relation="leads_to",
                    object_=strat_entity,
                    confidence=1.0,
                    source_text=f"{mapping.action_type}措施可{strat_name}",
                )
                store.add_triples([triple])

        # 计算统计
        stats = store.compute_stats()
        # 返回增量而非总量（调用者已有 before 计数）
        return stats["total_entities"] - ent_before, stats["total_triples"] - tri_before

    def _write_to_neo4j(
        self,
        neo4j_store: Neo4jStore,
        results: list[ExtractionResult],
        policy_name: str,
    ) -> tuple[int, int]:
        """
        将抽取结果写入 Neo4j（MERGE 自动去重）

        生成与 _write_to_store 相同的节点和边
        """
        ent_before = neo4j_store.compute_stats()["total_entities"]
        tri_before = neo4j_store.compute_stats()["total_triples"]

        # 收集去重后的 Action 大类
        action_type_set: dict[str, list[str]] = {}
        all_eligibility: list[dict] = []

        for r in results:
            for a in r.actions:
                cat = a["type"]
                raw = a["raw"]
                if cat not in action_type_set:
                    action_type_set[cat] = []
                if raw not in action_type_set[cat]:
                    action_type_set[cat].append(raw)
            if r.eligibility:
                all_eligibility.append(r.eligibility)

        # ── 写 Policy 节点 ──
        policy_entity = Entity(name=policy_name, entity_type="Policy")
        neo4j_store.add_entities([policy_entity])

        # ── 写 ActionType 节点 + provides 边 ──
        for action_type, raws in action_type_set.items():
            action_entity = Entity(
                name=action_type,
                entity_type="ActionType",
                attributes={"category": action_type, "raw": raws},
            )
            neo4j_store.add_entities([action_entity])

            triple = Triple(
                subject=policy_entity,
                relation="provides",
                object_=action_entity,
                confidence=1.0,
                source_text=f"政策提供{action_type}措施",
            )
            neo4j_store.add_triples([triple])

        # ── 写 Condition 节点 + has_eligibility 边 ──
        seen_conditions = set()
        for elig in all_eligibility:
            for cat in ["region", "company_type", "industry"]:
                val = elig.get(cat)
                if not val:
                    continue
                cond_key = (cat, val)
                if cond_key in seen_conditions:
                    continue
                seen_conditions.add(cond_key)

                cond_entity = Entity(
                    name=val,
                    entity_type="Condition",
                    attributes={"category": cat, "value": val},
                )
                neo4j_store.add_entities([cond_entity])

                triple = Triple(
                    subject=policy_entity,
                    relation="has_eligibility",
                    object_=cond_entity,
                    confidence=1.0,
                    source_text=f"政策适用于{cat}={val}",
                )
                neo4j_store.add_triples([triple])

                if cat == "region":
                    self._add_region_hierarchy_neo4j(neo4j_store, val)

        # ── 写 Strategy 节点 + leads_to 边 ──
        strategy_mappings = self.mapper.map_all(list(action_type_set.keys()))
        seen_strategies = set()
        for mapping in strategy_mappings:
            for strat_name in mapping.strategies:
                if strat_name in seen_strategies:
                    continue
                seen_strategies.add(strat_name)

                strat_entity = Entity(
                    name=strat_name,
                    entity_type="Strategy",
                    attributes={"name": strat_name},
                )
                neo4j_store.add_entities([strat_entity])

                action_entity = Entity(name=mapping.action_type, entity_type="ActionType")
                triple = Triple(
                    subject=action_entity,
                    relation="leads_to",
                    object_=strat_entity,
                    confidence=1.0,
                    source_text=f"{mapping.action_type}措施可{strat_name}",
                )
                neo4j_store.add_triples([triple])

        stats = neo4j_store.compute_stats()
        return stats["total_entities"] - ent_before, stats["total_triples"] - tri_before

    @staticmethod
    def _add_region_hierarchy_neo4j(neo4j_store: Neo4jStore, region_name: str):
        """递归添加 Region 层级关系到 Neo4j"""
        region_entity = Entity(
            name=region_name,
            entity_type="Region",
            attributes={"name": region_name},
        )
        neo4j_store.add_entities([region_entity])

        current = region_name
        while current in REGION_HIERARCHY:
            parent = REGION_HIERARCHY[current]
            parent_entity = Entity(
                name=parent,
                entity_type="Region",
                attributes={"name": parent},
            )
            neo4j_store.add_entities([parent_entity])

            current_entity = Entity(name=current, entity_type="Region")
            triple = Triple(
                subject=current_entity,
                relation="subregion_of",
                object_=parent_entity,
                confidence=1.0,
            )
            neo4j_store.add_triples([triple])

            current = parent

    @staticmethod
    def _add_region_hierarchy(store: TripletStore, region_name: str):
        """递归添加 Region 层级关系"""
        # 添加当前 Region 节点
        region_entity = Entity(
            name=region_name,
            entity_type="Region",
            attributes={"name": region_name},
        )
        store.add_entities([region_entity])

        # 向上遍历层级
        current = region_name
        while current in REGION_HIERARCHY:
            parent = REGION_HIERARCHY[current]
            parent_entity = Entity(
                name=parent,
                entity_type="Region",
                attributes={"name": parent},
            )
            store.add_entities([parent_entity])

            # current ── subregion_of ──→ parent
            current_entity = Entity(name=current, entity_type="Region")
            triple = Triple(
                subject=current_entity,
                relation="subregion_of",
                object_=parent_entity,
                confidence=1.0,
            )
            store.add_triples([triple])

            current = parent


# ── 独立运行入口 ──

def run_enhance(chunks_path: str, output_path: Optional[str] = None):
    """独立运行补图"""
    chunks_path = Path(chunks_path)
    if not chunks_path.exists():
        logger.error(f"chunks 文件不存在: {chunks_path}")
        return

    enhancer = Enhancer()
    store = enhancer.enhance_from_chunks_file(chunks_path)

    if output_path:
        out = Path(output_path)
    else:
        out = settings.TRIPLETS_DIR / f"enhanced_{chunks_path.stem}.json"

    store.save(out)
    logger.info(f"增强结果已保存: {out}")
    return store


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python -m src.enhancement.enhancer <chunked.json路径> [输出路径]")
        sys.exit(1)
    run_enhance(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
