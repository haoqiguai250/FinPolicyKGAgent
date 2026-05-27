"""
Enhancer Sidecar — 补图编排入口

Phase 1 完整流程：
1. 从 chunked.json 读取 chunks
2. 调用 ActionEligibilityExtractor 抽取 Action + Eligibility
3. 调用 StrategyMapper 规则映射 Strategy
4. 标准化 + 去重 + 写回 KG 存储（Neo4j + JSON 双写）
5. Phase 4.1: 创建 MasterPolicy 文档级主节点 + contains 边 + 申报属性聚合
"""

import json
import re
from pathlib import Path
from typing import Optional, Union

from loguru import logger

from src.extraction.schema import (
    Entity, Triple,
    REGION_HIERARCHY,
)
from src.extraction.llm_client import get_llm_client
from src.extraction.extractor import split_into_sentences
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
        llm_client=None,
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

        # 抽取（并行）
        extraction_results = self.extractor.extract_from_chunks(
            chunks, max_workers=settings.CHUNK_PARALLEL_WORKERS
        )

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
                    self._neo4j_store, extraction_results, policy_name,
                    chunks=chunks
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

        # 收集去重后的 Action 大类，同时记录 chunk_id 和 sentence_index
        action_type_set: dict[str, list[str]] = {}  # type → [raw1, raw2, ...]
        action_type_chunk_id: dict[str, str] = {}    # type → 最早出现的 chunk_id
        action_type_source_text: dict[str, str] = {} # type → 最早出现的原文片段
        action_type_sentence_index: dict[str, int] = {} # type → 最早出现的 sentence_index
        # 收集所有 eligibility（带 chunk_id 和 sentence_index）
        all_eligibility: list[dict] = []

        # 先统计去重
        for r in results:
            for a in r.actions:
                cat = a["type"]
                raw = a["raw"]
                ssi = a.get("source_sentence_index", -1)
                if cat not in action_type_set:
                    action_type_set[cat] = []
                if raw not in action_type_set[cat]:
                    action_type_set[cat].append(raw)
                # 记录最早出现的 chunk_id 和 sentence_index
                if cat not in action_type_chunk_id and r.chunk_id:
                    action_type_chunk_id[cat] = r.chunk_id
                    action_type_source_text[cat] = f"政策提供{cat}措施"  # 兜底，Neo4j 侧会用原文替代
                    action_type_sentence_index[cat] = ssi

            if r.eligibility:
                # 把 chunk_id 和 sentence_index 带进 eligibility
                elig_with_chunk = {
                    **r.eligibility,
                    "_chunk_id": r.chunk_id,
                    "_source_sentence_index": r.eligibility.get("source_sentence_index", -1),
                }
                all_eligibility.append(elig_with_chunk)

        # ── 写 ActionType 节点 + provides 边 ──
        policy_entity = Entity(name=policy_name, entity_type="Policy")
        for action_type, raws in action_type_set.items():
            chunk_id = action_type_chunk_id.get(action_type, "")
            ssi = action_type_sentence_index.get(action_type, -1)
            action_entity = Entity(
                name=action_type,
                entity_type="ActionType",
                attributes={"category": action_type, "raw": raws},
                source_chunk_id=chunk_id,
            )
            store.add_entities([action_entity])

            # Policy → ActionType (provides)
            triple = Triple(
                subject=policy_entity,
                relation="provides",
                object_=action_entity,
                confidence=1.0,
                source_text=f"政策提供{action_type}措施",
                source_chunk_id=chunk_id,
                source_sentence_index=ssi,
            )
            store.add_triples([triple])

        # ── 写 Condition 节点 + has_eligibility 边 ──
        # 去重：同一 policy 的 condition 不重复，但记录 chunk_id
        seen_conditions = set()
        for elig in all_eligibility:
            chunk_id = elig.pop("_chunk_id", "")
            elig_ssi = elig.pop("_source_sentence_index", -1)
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
                    source_chunk_id=chunk_id,
                )
                store.add_entities([cond_entity])

                # Policy → Condition (has_eligibility)
                triple = Triple(
                    subject=policy_entity,
                    relation="has_eligibility",
                    object_=cond_entity,
                    confidence=1.0,
                    source_text=f"政策适用于{cat}={val}",
                    source_chunk_id=chunk_id,
                    source_sentence_index=elig_ssi,
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
                    source_chunk_id="rule",  # Strategy 由规则生成，标记为 "rule"
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
                    source_chunk_id="rule",
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
        chunks: list = None,
    ) -> tuple[int, int]:
        """
        将抽取结果写入 Neo4j（MERGE 自动去重）

        生成与 _write_to_store 相同的节点和边，附带 source_chunk_id
        Phase 4.1 改进：
        - ① provides source_text 用原文句子替代模板
        - ③ 创建 MasterPolicy 文档级主节点 + contains 边 + 申报属性聚合
        """
        ent_before = neo4j_store.compute_stats()["total_entities"]
        tri_before = neo4j_store.compute_stats()["total_triples"]

        # 构建 chunk_id → chunk text 的映射（用于原文反查）
        chunk_text_map: dict[str, str] = {}
        if chunks:
            for chunk in chunks:
                chunk_id = chunk.get("chunk_id", "") if isinstance(chunk, dict) else getattr(chunk, "chunk_id", "")
                chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else getattr(chunk, "text", "")
                if chunk_id and chunk_text:
                    chunk_text_map[chunk_id] = chunk_text

        # 收集去重后的 Action 大类，同时记录 chunk_id 和 sentence_index
        action_type_set: dict[str, list[str]] = {}
        action_type_chunk_id: dict[str, str] = {}
        action_type_sentence_index: dict[str, int] = {}
        all_eligibility: list[dict] = []

        for r in results:
            for a in r.actions:
                cat = a["type"]
                raw = a["raw"]
                ssi = a.get("source_sentence_index", -1)
                if cat not in action_type_set:
                    action_type_set[cat] = []
                if raw not in action_type_set[cat]:
                    action_type_set[cat].append(raw)
                if cat not in action_type_chunk_id and r.chunk_id:
                    action_type_chunk_id[cat] = r.chunk_id
                    action_type_sentence_index[cat] = ssi
            if r.eligibility:
                elig_with_chunk = {
                    **r.eligibility,
                    "_chunk_id": r.chunk_id,
                    "_source_sentence_index": r.eligibility.get("source_sentence_index", -1),
                }
                all_eligibility.append(elig_with_chunk)

        # ── 写 Policy 节点 ──
        policy_entity = Entity(name=policy_name, entity_type="Policy")
        neo4j_store.add_entities([policy_entity])

        # ── ① 写 ActionType 节点 + provides 边（source_text 用原文句子） ──
        for action_type, raws in action_type_set.items():
            chunk_id = action_type_chunk_id.get(action_type, "")
            ssi = action_type_sentence_index.get(action_type, -1)

            # 从 chunk 原文反查 source_sentence_text
            source_sentence_text = ""
            if chunk_id and ssi >= 1 and chunk_id in chunk_text_map:
                try:
                    sentences = split_into_sentences(chunk_text_map[chunk_id])
                    if ssi <= len(sentences):
                        source_sentence_text = sentences[ssi - 1].strip()
                except Exception as e:
                    logger.debug(f"反查原文句子失败: chunk_id={chunk_id}, ssi={ssi}: {e}")

            # 兜底：没有反查到就用模板
            provides_source_text = source_sentence_text or f"政策提供{action_type}措施"

            action_entity = Entity(
                name=action_type,
                entity_type="ActionType",
                attributes={"category": action_type, "raw": raws},
                source_chunk_id=chunk_id,
            )
            neo4j_store.add_entities([action_entity])

            # provides 边附带 source_sentence_text
            triple = Triple(
                subject=policy_entity,
                relation="provides",
                object_=action_entity,
                confidence=1.0,
                source_text=provides_source_text,
                source_chunk_id=chunk_id,
                source_sentence_index=ssi,
            )
            # 在写入时额外添加 source_sentence_text 属性
            neo4j_store.add_triples([triple])
            # 额外写入 source_sentence_text 到关系属性
            if source_sentence_text:
                try:
                    with neo4j_store.driver.session(database=neo4j_store.database) as session:
                        session.run(
                            """MATCH (s:Policy {name: $policy_name})-[r:provides]->(o:ActionType {name: $action_type})
                            SET r.source_sentence_text = $source_sentence_text""",
                            policy_name=policy_name,
                            action_type=action_type,
                            source_sentence_text=source_sentence_text,
                        )
                except Exception as e:
                    logger.debug(f"写入 source_sentence_text 失败: {e}")

        # ── 写 Condition 节点 + has_eligibility 边 ──
        seen_conditions = set()
        for elig in all_eligibility:
            chunk_id = elig.pop("_chunk_id", "")
            elig_ssi = elig.pop("_source_sentence_index", -1)
            for cat in ["region", "company_type", "industry"]:
                val = elig.get(cat)
                if not val:
                    continue
                # Phase 4.1: role 过滤 — 只保留 applicant 角色的 eligibility
                # role 为空时也跳过（兜底：LLM 没输出 role 视为不可信）
                role = elig.get(f"{cat}_role", "")
                if role != "applicant":
                    logger.debug(f"  跳过非 applicant 条件: {cat}={val}, role={role or '(空)'}")
                    continue
                cond_key = (cat, val)
                if cond_key in seen_conditions:
                    continue
                seen_conditions.add(cond_key)

                cond_entity = Entity(
                    name=val,
                    entity_type="Condition",
                    attributes={"category": cat, "value": val},
                    source_chunk_id=chunk_id,
                )
                neo4j_store.add_entities([cond_entity])

                triple = Triple(
                    subject=policy_entity,
                    relation="has_eligibility",
                    object_=cond_entity,
                    confidence=1.0,
                    source_text=f"政策适用于{cat}={val}",
                    source_chunk_id=chunk_id,
                    source_sentence_index=elig_ssi,
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
                    source_chunk_id="rule",
                )
                neo4j_store.add_entities([strat_entity])

                action_entity = Entity(name=mapping.action_type, entity_type="ActionType")
                triple = Triple(
                    subject=action_entity,
                    relation="leads_to",
                    object_=strat_entity,
                    confidence=1.0,
                    source_text=f"{mapping.action_type}措施可{strat_name}",
                    source_chunk_id="rule",
                )
                neo4j_store.add_triples([triple])

        # ══════════════════════════════════════════
        # ③ Phase 4.1: MasterPolicy 文档级主节点
        # ══════════════════════════════════════════
        self._create_master_policy(neo4j_store, policy_name)

        stats = neo4j_store.compute_stats()
        return stats["total_entities"] - ent_before, stats["total_triples"] - tri_before

    def _create_master_policy(
        self,
        neo4j_store: Neo4jStore,
        doc_title: str,
    ):
        """
        ③ MasterPolicy 文档级主节点

        同一 source_file 的所有子 Policy 节点：
        - 创建 MasterPolicy 节点（is_master=true, name=doc_title）
        - 创建 contains 边：MasterPolicy → 子 Policy
        - 从子 Policy 聚合申报属性到 MasterPolicy

        这样 Advisor 匹配到 MasterPolicy 就能一步拿到所有申报数据。
        """
        source_file = neo4j_store.source_file
        if not source_file:
            logger.debug("无 source_file，跳过 MasterPolicy 创建")
            return

        try:
            with neo4j_store.driver.session(database=neo4j_store.database) as session:
                # 1. 查找同 source_file 的所有子 Policy
                child_policies = session.run(
                    """MATCH (p:Policy)
                    WHERE p.source_file = $source_file AND (p.is_master IS NULL OR p.is_master = false)
                    RETURN p.name AS name""",
                    source_file=source_file,
                ).data()

                if not child_policies:
                    logger.debug(f"source_file={source_file} 无子 Policy，跳过 MasterPolicy")
                    return

                child_names = [r["name"] for r in child_policies]

                # 2. 创建 MasterPolicy 节点（MERGE 幂等）
                session.run(
                    """MERGE (mp:Policy {name: $master_name})
                    SET mp.is_master = true,
                        mp.source_file = $source_file,
                        mp.policy_type = 'MasterPolicy'
                    """,
                    master_name=doc_title,
                    source_file=source_file,
                )
                logger.info(f"MasterPolicy 创建: {doc_title}, 子 Policy 数: {len(child_names)}")

                # 3. 创建 contains 边：MasterPolicy → 子 Policy
                for child_name in child_names:
                    session.run(
                        """MATCH (mp:Policy {name: $master_name})
                        MATCH (cp:Policy {name: $child_name})
                        MERGE (mp)-[:contains]->(cp)
                        """,
                        master_name=doc_title,
                        child_name=child_name,
                    )

                # 4. 聚合子 Policy 的申报属性到 MasterPolicy
                #    - estimated_amount: 取含数字的最具体值
                #    - required_materials: 合并去重
                #    - application_steps: 合并去重
                #    - deadline: 优先取第一个非空值
                #    - application_platform / application_platform_url: 取第一个非空值
                #    - contact_department: 取第一个非空值
                #    - effective_date / expiry_date / status: 传播到 MasterPolicy
                session.run(
                    """MATCH (mp:Policy {name: $master_name})-[:contains]->(cp:Policy)
                    WHERE cp.source_file = $source_file
                    WITH mp, collect(cp) AS children
                    WITH mp,
                         // estimated_amount: 优先含数字的值，否则取最长
                         CASE
                           WHEN [c IN children WHERE c.estimated_amount IS NOT NULL
                                 AND size(apoc.text.replace(c.estimated_amount, '[0-9零一二三四五六七八九十百千万亿]', '')) < size(c.estimated_amount)] IS NOT NULL
                           THEN head([c IN children WHERE c.estimated_amount IS NOT NULL
                                 AND size(apoc.text.replace(c.estimated_amount, '[0-9零一二三四五六七八九十百千万亿]', '')) < size(c.estimated_amount)]).estimated_amount
                           ELSE head([c IN children WHERE c.estimated_amount IS NOT NULL]).estimated_amount
                         END AS best_amount,
                         // 其他字段：取第一个非空值
                         head([c IN children WHERE c.deadline IS NOT NULL]).deadline AS best_deadline,
                         head([c IN children WHERE c.application_platform IS NOT NULL]).application_platform AS best_platform,
                         head([c IN children WHERE c.application_platform_url IS NOT NULL]).application_platform_url AS best_platform_url,
                         head([c IN children WHERE c.contact_department IS NOT NULL]).contact_department AS best_dept,
                         head([c IN children WHERE c.effective_date IS NOT NULL]).effective_date AS best_effective,
                         head([c IN children WHERE c.expiry_date IS NOT NULL]).expiry_date AS best_expiry,
                         head([c IN children WHERE c.status IS NOT NULL]).status AS best_status,
                         // required_materials + application_steps: 合并去重
                         reduce(arr = [], c IN children |
                           CASE WHEN c.required_materials IS NOT NULL
                                THEN arr + c.required_materials
                                ELSE arr END
                         ) AS all_materials,
                         reduce(arr = [], c IN children |
                           CASE WHEN c.application_steps IS NOT NULL
                                THEN arr + c.application_steps
                                ELSE arr END
                         ) AS all_steps
                    SET mp.estimated_amount = COALESCE(mp.estimated_amount, best_amount),
                        mp.deadline = COALESCE(mp.deadline, best_deadline),
                        mp.application_platform = COALESCE(mp.application_platform, best_platform),
                        mp.application_platform_url = COALESCE(mp.application_platform_url, best_platform_url),
                        mp.contact_department = COALESCE(mp.contact_department, best_dept),
                        mp.effective_date = COALESCE(mp.effective_date, best_effective),
                        mp.expiry_date = COALESCE(mp.expiry_date, best_expiry),
                        mp.status = COALESCE(mp.status, best_status),
                        mp.required_materials = CASE WHEN size(all_materials) > 0 THEN all_materials ELSE mp.required_materials END,
                        mp.application_steps = CASE WHEN size(all_steps) > 0 THEN all_steps ELSE mp.application_steps END
                    """,
                    master_name=doc_title,
                    source_file=source_file,
                )

                # 5. 将子 Policy 的 provides / has_eligibility 边复制到 MasterPolicy
                #    这样 Advisor 匹配 MasterPolicy 时也能看到补贴和条件
                session.run(
                    """MATCH (mp:Policy {name: $master_name})-[:contains]->(cp:Policy)-[r:provides]->(a:ActionType)
                    WHERE NOT EXISTS ((mp)-[:provides]->(a))
                    MERGE (mp)-[:provides]->(a)
                    SET mp_provides = properties(r)
                    """,
                    master_name=doc_title,
                )
                session.run(
                    """MATCH (mp:Policy {name: $master_name})-[:contains]->(cp:Policy)-[r:has_eligibility]->(c:Condition)
                    WHERE NOT EXISTS ((mp)-[:has_eligibility]->(c))
                    MERGE (mp)-[:has_eligibility]->(c)
                    SET mp_elig = properties(r)
                    """,
                    master_name=doc_title,
                )

                logger.info(f"MasterPolicy 属性聚合完成: {doc_title}")

        except Exception as e:
            # APOC 可能不可用，用简单版聚合逻辑兜底
            logger.warning(f"MasterPolicy APOC 聚合失败，降级到简单逻辑: {e}")
            self._create_master_policy_simple(neo4j_store, doc_title, source_file)

    def _create_master_policy_simple(
        self,
        neo4j_store: Neo4jStore,
        doc_title: str,
        source_file: str,
    ):
        """MasterPolicy 简单版聚合（不依赖 APOC）"""
        try:
            with neo4j_store.driver.session(database=neo4j_store.database) as session:
                # 查找子 Policy
                child_policies = session.run(
                    """MATCH (p:Policy)
                    WHERE p.source_file = $source_file AND (p.is_master IS NULL OR p.is_master = false)
                    RETURN p.name AS name""",
                    source_file=source_file,
                ).data()

                if not child_policies:
                    return

                child_names = [r["name"] for r in child_policies]

                # 创建 MasterPolicy
                session.run(
                    """MERGE (mp:Policy {name: $master_name})
                    SET mp.is_master = true,
                        mp.source_file = $source_file,
                        mp.policy_type = 'MasterPolicy'
                    """,
                    master_name=doc_title,
                    source_file=source_file,
                )

                # contains 边
                for child_name in child_names:
                    session.run(
                        """MATCH (mp:Policy {name: $master_name})
                        MATCH (cp:Policy {name: $child_name})
                        MERGE (mp)-[:contains]->(cp)
                        """,
                        master_name=doc_title,
                        child_name=child_name,
                    )

                # 逐字段聚合（简单版：逐个子 Policy 读取属性，取最佳值）
                for attr in ["estimated_amount", "deadline", "application_platform",
                             "application_platform_url", "contact_department",
                             "effective_date", "expiry_date", "status",
                             "required_materials", "application_steps"]:
                    values = []
                    for child_name in child_names:
                        result = session.run(
                            f"MATCH (p:Policy {{name: $name}}) RETURN p.{attr} AS val",
                            name=child_name,
                        ).single()
                        if result and result["val"] is not None:
                            values.append(result["val"])

                    # 选取最佳值：含数字优先（对于 amount），否则取第一个
                    best_val = None
                    if attr == "estimated_amount" and values:
                        # 优先含数字的
                        numeric_vals = [v for v in values if re.search(r'\d', str(v))]
                        best_val = numeric_vals[0] if numeric_vals else values[0]
                    elif values:
                        best_val = values[0]

                    if best_val is not None:
                        # 对 list 类型（required_materials, application_steps）做合并
                        if attr in ("required_materials", "application_steps"):
                            # 收集所有 list 值并合并
                            all_vals = []
                            for v in values:
                                if isinstance(v, list):
                                    all_vals.extend(v)
                                elif isinstance(v, str):
                                    all_vals.append(v)
                            # 去重
                            seen = set()
                            unique_vals = []
                            for v in all_vals:
                                if v not in seen:
                                    seen.add(v)
                                    unique_vals.append(v)
                            if unique_vals:
                                best_val = unique_vals
                            else:
                                continue

                        if best_val is not None:
                            session.run(
                                f"""MATCH (mp:Policy {{name: $master_name}})
                                SET mp.{attr} = $val""",
                                master_name=doc_title,
                                val=best_val,
                            )

                # 复制 provides / has_eligibility 边到 MasterPolicy
                session.run(
                    """MATCH (mp:Policy {name: $master_name})-[:contains]->(cp:Policy)-[r:provides]->(a:ActionType)
                    WHERE NOT EXISTS ((mp)-[:provides]->(a))
                    MERGE (mp)-[:provides]->(a)
                    """,
                    master_name=doc_title,
                )
                session.run(
                    """MATCH (mp:Policy {name: $master_name})-[:contains]->(cp:Policy)-[r:has_eligibility]->(c:Condition)
                    WHERE NOT EXISTS ((mp)-[:has_eligibility]->(c))
                    MERGE (mp)-[:has_eligibility]->(c)
                    """,
                    master_name=doc_title,
                )

                logger.info(f"MasterPolicy 简单聚合完成: {doc_title}")

        except Exception as e:
            logger.error(f"MasterPolicy 简单聚合也失败: {e}")

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
