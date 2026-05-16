"""
图检索器

从企业画像出发，沿 KG 图遍历匹配推理路径：
Company → Condition ← Policy → ActionType → Strategy

支持两种后端：
1. Neo4jStore — Cypher 查询（推荐，跨文档去重+高效路径遍历）
2. TripletStore — 内存索引（兼容旧数据，单文件场景）
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Union

from loguru import logger

from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.decision.intent_recognizer import EnterpriseProfile


# ── 数据结构 ──

@dataclass
class SubPathTriple:
    """子路径三元组（单条边，含溯源信息）"""
    subject_name: str
    subject_type: str
    relation: str
    object_name: str
    object_type: str
    source_chunk_id: str = ""
    source_text: str = ""

    def to_dict(self) -> dict:
        return {
            "subject": f"{self.subject_type}({self.subject_name})",
            "relation": self.relation,
            "object": f"{self.object_type}({self.object_name})",
            "source_chunk_id": self.source_chunk_id,
            "source_text": self.source_text,
        }


@dataclass
class ReasoningPath:
    """推理路径：一条从 Condition 到 Strategy 的完整路径"""
    policy_name: str
    conditions: list[dict]         # [{category, value, source_chunk_id?, source_text?}]
    action_type: str
    action_raw: list[str]          # 原始短语
    strategies: list[str]
    # ── 子路径明细（每条边含溯源） ──
    sub_paths: list[SubPathTriple] = field(default_factory=list)
    # ── 边级溯源快捷字段（由 retriever 填充） ──
    provides_chunk_id: str = ""
    provides_source_text: str = ""
    leads_to_chunk_id: str = ""
    leads_to_source_text: str = ""

    def to_dict(self) -> dict:
        return {
            "policy": self.policy_name,
            "conditions": self.conditions,
            "action_type": self.action_type,
            "action_raw": self.action_raw,
            "strategies": self.strategies,
            "sub_paths": [sp.to_dict() for sp in self.sub_paths],
        }


@dataclass
class RetrievalResult:
    """检索结果"""
    profile: EnterpriseProfile
    paths: list[ReasoningPath] = field(default_factory=list)
    matched_policies: list[str] = field(default_factory=list)
    matched_actions: list[str] = field(default_factory=list)
    matched_strategies: list[str] = field(default_factory=list)


class GraphRetriever:
    """
    图遍历检索器（统一入口）

    自动检测存储后端：
    - 传入 Neo4jStore → 使用 Cypher 查询
    - 传入 TripletStore → 使用内存索引（兼容旧数据）
    """

    def __init__(
        self,
        store: Optional[Union[TripletStore, Neo4jStore]] = None,
        store_path: Optional[Path] = None,
        neo4j_store: Optional[Neo4jStore] = None,
    ):
        """
        Args:
            store: 已加载的 TripletStore 或 Neo4jStore
            store_path: TripletStore JSON 文件路径（store 为 None 时从此加载）
            neo4j_store: Neo4jStore 实例（优先级最高）
        """
        self._neo4j_store: Optional[Neo4jStore] = None
        self._json_store: Optional[TripletStore] = None

        if neo4j_store:
            self._neo4j_store = neo4j_store
            self._backend = "neo4j"
        elif isinstance(store, Neo4jStore):
            self._neo4j_store = store
            self._backend = "neo4j"
        elif isinstance(store, TripletStore):
            self._json_store = store
            self._backend = "json"
            self._build_indexes()
        elif store_path:
            self._json_store = TripletStore.load(store_path)
            self._backend = "json"
            self._build_indexes()
        else:
            raise ValueError("必须提供 store / neo4j_store / store_path")

        logger.info(f"GraphRetriever 初始化，后端: {self._backend}")

    @property
    def store(self) -> Optional[TripletStore]:
        """兼容旧代码：返回 TripletStore（仅 JSON 后端有值）"""
        return self._json_store

    @property
    def neo4j_store(self) -> Optional[Neo4jStore]:
        """返回 Neo4jStore"""
        return self._neo4j_store

    # ══════════════════════════════════════════
    # 检索入口（统一接口）
    # ══════════════════════════════════════════

    def retrieve(self, profile: EnterpriseProfile, source_files: list[str] = None) -> RetrievalResult:
        """
        基于企业画像进行图遍历检索

        推理路径：
        Company → Condition ← Policy → ActionType → Strategy

        Args:
            profile: 企业画像
            source_files: 可选，限制只检索这些来源文件对应的政策（如新抓取的 PDF 路径）
        """
        if self._backend == "neo4j":
            return self._retrieve_neo4j(profile, source_files=source_files)
        else:
            return self._retrieve_json(profile, source_files=source_files)

    # ══════════════════════════════════════════
    # Neo4j 后端实现
    # ══════════════════════════════════════════

    def _retrieve_neo4j(self, profile: EnterpriseProfile, source_files: list[str] = None) -> RetrievalResult:
        """Neo4j Cypher 查询检索"""
        result = RetrievalResult(profile=profile)

        # 1. 构建企业 Condition 集合
        company_conditions = self._expand_conditions(profile)
        if not company_conditions:
            logger.info("企业画像无有效条件")
            return result

        # 拆分 condition 为 category → values 映射
        cond_map: dict[str, list[str]] = {}
        for category, value in company_conditions:
            cond_map.setdefault(category, []).append(value)

        # 2. Cypher 查询所有 Policy 的 Condition
        all_policies = self._find_all_policies_with_conditions()

        # 如果指定了 source_files，只保留新抓取政策
        if source_files:
            filtered_names = self._find_policy_names_by_source_files(source_files)
            if not filtered_names:
                logger.info("新抓取的政策中无匹配 (source_files 未找到任何 Policy)")
                return result
            all_policies = {k: v for k, v in all_policies.items() if k in filtered_names}
            if not all_policies:
                logger.info("新抓取的政策中无匹配 (无政策满足条件)")
                return result
            logger.info(f"过滤后: {len(all_policies)} 个新政策参与匹配")

        # 3. 匹配：Policy 的 Condition 与企业 Condition 有交集（至少一个条件命中）
        matched_policies = []
        for policy_name, policy_conds in all_policies.items():
            policy_cond_set = set(
                (c["category"], c["value"]) for c in policy_conds
                if c.get("category")  # 跳过 category 为 None 的条件
            )
            # 无有效条件 → 直接匹配（兜底）
            # 有交集 → 匹配（宽松模式，不要求全部命中）
            if not policy_cond_set or policy_cond_set & company_conditions:
                matched_policies.append(policy_name)

        if not matched_policies:
            logger.info("未找到匹配政策")
            return result

        # 4. 构建推理路径
        for policy_name in matched_policies:
            policy_conditions = self._neo4j_get_policy_conditions(policy_name)
            actions = self._neo4j_get_policy_actions(policy_name)

            for action_type, action_raw, provides_chunk_id in actions:
                strategies = self._neo4j_get_action_strategies(action_type)
                raw_list = action_raw if isinstance(action_raw, list) else [action_raw] if action_raw else []

                # ── 构建 sub_paths（含 source_chunk_id 全链路溯源） ──
                sub_paths = []
                # Policy → Condition (has_eligibility)
                for cond in policy_conditions:
                    sub_paths.append(SubPathTriple(
                        subject_name=policy_name, subject_type="Policy",
                        relation="has_eligibility",
                        object_name=cond.get("value", ""), object_type="Condition",
                        source_chunk_id=cond.get("source_chunk_id", ""),
                        source_text=cond.get("source_text", ""),
                    ))
                # Policy → ActionType (provides)
                sub_paths.append(SubPathTriple(
                    subject_name=policy_name, subject_type="Policy",
                    relation="provides",
                    object_name=action_type, object_type="ActionType",
                    source_chunk_id=provides_chunk_id,
                ))
                # ActionType → Strategy (leads_to)
                for strat_name, leads_to_chunk_id in strategies:
                    sub_paths.append(SubPathTriple(
                        subject_name=action_type, subject_type="ActionType",
                        relation="leads_to",
                        object_name=strat_name, object_type="Strategy",
                        source_chunk_id=leads_to_chunk_id,
                    ))

                path = ReasoningPath(
                    policy_name=policy_name,
                    conditions=policy_conditions,
                    action_type=action_type,
                    action_raw=raw_list,
                    strategies=[s[0] for s in strategies],
                    sub_paths=sub_paths,
                    provides_chunk_id=provides_chunk_id,
                )
                result.paths.append(path)
                result.matched_actions.append(action_type)
                result.matched_strategies.extend(s[0] for s in strategies)

        result.matched_policies = sorted(set(matched_policies))
        result.matched_actions = sorted(set(result.matched_actions))
        result.matched_strategies = sorted(set(result.matched_strategies))

        logger.info(
            f"检索完成: {len(result.paths)} 条路径, "
            f"{len(result.matched_policies)} 个政策, "
            f"{len(result.matched_actions)} 类措施, "
            f"{len(result.matched_strategies)} 个策略"
        )
        return result

    def _find_all_policies_with_conditions(self) -> dict[str, list[dict]]:
        """从 Neo4j 查询所有 Policy 及其 Condition"""
        from src.storage.cypher_queries import FIND_POLICIES_BY_CONDITIONS
        policies = {}
        with self._neo4j_store.driver.session(database=self._neo4j_store.database) as session:
            results = session.run(FIND_POLICIES_BY_CONDITIONS)
            for record in results:
                policy_name = record["policy_name"]
                policy_conds = record["policy_conds"]
                policies[policy_name] = policy_conds
        return policies

    def _find_policy_names_by_source_files(self, source_files: list[str]) -> set[str]:
        """根据 source_file 列表查询对应的 Policy 名称"""
        names = set()
        with self._neo4j_store.driver.session(database=self._neo4j_store.database) as session:
            for sf in source_files:
                result = session.run(
                    "MATCH (p:Policy) WHERE p.source_file = $source_file RETURN p.name AS name",
                    source_file=sf,
                )
                for record in result:
                    names.add(record["name"])
        return names

    def _neo4j_get_policy_conditions(self, policy_name: str) -> list[dict]:
        """从 Neo4j 查询 Policy 的 Condition"""
        from src.storage.cypher_queries import FIND_POLICY_CONDITIONS
        with self._neo4j_store.driver.session(database=self._neo4j_store.database) as session:
            results = session.run(FIND_POLICY_CONDITIONS, policy_name=policy_name)
            return [{"category": r["category"], "value": r["value"]} for r in results]

    def _neo4j_get_policy_actions(self, policy_name: str) -> list[tuple[str, list, str]]:
        """从 Neo4j 查询 Policy 的 ActionType，返回 (action_type, action_raw, provides_chunk_id)"""
        from src.storage.cypher_queries import FIND_POLICY_ACTIONS
        actions = []
        with self._neo4j_store.driver.session(database=self._neo4j_store.database) as session:
            results = session.run(FIND_POLICY_ACTIONS, policy_name=policy_name)
            for record in results:
                action_type = record["action_type"]
                action_raw = record["action_raw"] or []
                if isinstance(action_raw, str):
                    action_raw = [action_raw]
                provides_chunk_id = record.get("provides_chunk_id", "")
                actions.append((action_type, action_raw, provides_chunk_id))
        return actions

    def _neo4j_get_action_strategies(self, action_type: str) -> list[tuple[str, str]]:
        """从 Neo4j 查询 ActionType 的 Strategy，返回 [(strategy, leads_to_chunk_id), ...]"""
        from src.storage.cypher_queries import FIND_ACTION_STRATEGIES
        strategies = []
        with self._neo4j_store.driver.session(database=self._neo4j_store.database) as session:
            results = session.run(FIND_ACTION_STRATEGIES, action_type=action_type)
            for record in results:
                strategy = record["strategy"]
                leads_to_chunk_id = record.get("leads_to_chunk_id", "")
                strategies.append((strategy, leads_to_chunk_id))
        return strategies

    # ══════════════════════════════════════════
    # JSON 后端实现（保留兼容）
    # ══════════════════════════════════════════

    def _build_indexes(self):
        """构建内存索引（JSON 后端）"""
        store = self._json_store
        # 实体索引: (name, type) → entity dict
        self.entity_index: dict[tuple[str, str], dict] = {}
        for e in store.entities:
            key = (e["name"], e["type"])
            self.entity_index[key] = e

        # 关系索引：按关系类型分组
        self.triples_by_relation: dict[str, list[dict]] = {}
        for t in store.triples:
            rel = t["relation"]
            if rel not in self.triples_by_relation:
                self.triples_by_relation[rel] = []
            self.triples_by_relation[rel].append(t)

        # Policy → ActionType 索引 (provides)
        self.policy_to_actions: dict[str, list[dict]] = {}
        for t in self.triples_by_relation.get("provides", []):
            policy_name = t["subject"]["name"]
            if policy_name not in self.policy_to_actions:
                self.policy_to_actions[policy_name] = []
            self.policy_to_actions[policy_name].append(t)

        # Policy → Condition 索引 (has_eligibility)
        self.policy_to_conditions: dict[str, list[dict]] = {}
        for t in self.triples_by_relation.get("has_eligibility", []):
            policy_name = t["subject"]["name"]
            if policy_name not in self.policy_to_conditions:
                self.policy_to_conditions[policy_name] = []
            self.policy_to_conditions[policy_name].append(t)

        # ActionType → Strategy 索引 (leads_to)
        self.action_to_strategies: dict[str, list[str]] = {}
        for t in self.triples_by_relation.get("leads_to", []):
            if t["subject"]["type"] == "ActionType":
                action_name = t["subject"]["name"]
                if action_name not in self.action_to_strategies:
                    self.action_to_strategies[action_name] = []
                self.action_to_strategies[action_name].append(t["object"]["name"])

        # Region 层级索引 (subregion_of) — 正向：子→父
        self.region_parent: dict[str, str] = {}
        # 反向：父→[子1, 子2, ...]（用于向下扩展）
        self.region_children: dict[str, list[str]] = {}
        for t in self.triples_by_relation.get("subregion_of", []):
            child = t["subject"]["name"]
            parent = t["object"]["name"]
            self.region_parent[child] = parent
            self.region_children.setdefault(parent, []).append(child)

        # ActionType → raw 列表
        self.action_raw_map: dict[str, list[str]] = {}
        for key, e in self.entity_index.items():
            if key[1] == "ActionType":
                raw = e.get("attributes", {}).get("raw", [])
                if isinstance(raw, str):
                    raw = [raw]
                self.action_raw_map[key[0]] = raw

        logger.info(
            f"索引构建完成: {len(self.entity_index)} 实体, "
            f"{len(self.policy_to_actions)} Policy→Action, "
            f"{len(self.policy_to_conditions)} Policy→Condition, "
            f"{len(self.action_to_strategies)} Action→Strategy"
        )

    def _retrieve_json(self, profile: EnterpriseProfile, source_files: list[str] = None) -> RetrievalResult:
        """JSON 内存索引检索（原有逻辑）"""
        result = RetrievalResult(profile=profile)

        # 1. 构建企业的 Condition 集合（含 region 层级扩展）
        company_conditions = self._expand_conditions(profile)

        # 2. 找匹配的 Policy
        matched_policies = self._match_policies(company_conditions)

        if not matched_policies:
            logger.info("未找到匹配政策")
            return result

        # 3. 对每个匹配 Policy，构建推理路径
        for policy_name in matched_policies:
            policy_conditions = self._get_policy_conditions(policy_name)
            actions = self.policy_to_actions.get(policy_name, [])

            for action_triple in actions:
                action_type = action_triple["object"]["name"]
                strategies = self.action_to_strategies.get(action_type, [])
                raw_list = self.action_raw_map.get(action_type, [])

                # ── 构建 sub_paths ──
                sub_paths = []
                # Policy → Condition (has_eligibility)
                for cond in policy_conditions:
                    sub_paths.append(SubPathTriple(
                        subject_name=policy_name, subject_type="Policy",
                        relation="has_eligibility",
                        object_name=cond.get("value", ""), object_type="Condition",
                        source_chunk_id=cond.get("source_chunk_id", ""),
                        source_text=cond.get("source_text", ""),
                    ))
                # Policy → ActionType (provides)
                sub_paths.append(SubPathTriple(
                    subject_name=policy_name, subject_type="Policy",
                    relation="provides",
                    object_name=action_type, object_type="ActionType",
                    source_chunk_id=action_triple.get("source_chunk_id", ""),
                    source_text=action_triple.get("source_text", ""),
                ))
                # ActionType → Strategy (leads_to) — 规则生成，标记 "rule"
                for strat in strategies:
                    sub_paths.append(SubPathTriple(
                        subject_name=action_type, subject_type="ActionType",
                        relation="leads_to",
                        object_name=strat, object_type="Strategy",
                        source_chunk_id="rule",
                    ))

                path = ReasoningPath(
                    policy_name=policy_name,
                    conditions=policy_conditions,
                    action_type=action_type,
                    action_raw=raw_list,
                    strategies=strategies,
                    sub_paths=sub_paths,
                )
                result.paths.append(path)
                result.matched_actions.append(action_type)
                result.matched_strategies.extend(strategies)

        result.matched_policies = sorted(set(matched_policies))
        result.matched_actions = sorted(set(result.matched_actions))
        result.matched_strategies = sorted(set(result.matched_strategies))

        logger.info(
            f"检索完成: {len(result.paths)} 条路径, "
            f"{len(result.matched_policies)} 个政策, "
            f"{len(result.matched_actions)} 类措施, "
            f"{len(result.matched_strategies)} 个策略"
        )
        return result

    # ══════════════════════════════════════════
    # 共用方法
    # ══════════════════════════════════════════

    def _expand_conditions(self, profile: EnterpriseProfile) -> set[tuple[str, str]]:
        """
        扩展企业 Condition 集合

        region 双向扩展：
        - 向上：深圳 → 广东 → 中国（原有）
        - 向下：深圳 → 坪山区、南山区...（新增，查 subregion_of 反向）

        company_type/industry 精确匹配
        """
        conditions = set()

        # Region 双向扩展
        if profile.region:
            # 向上扩展
            chain = profile.get_region_chain()
            for r in chain:
                conditions.add(("region", r))

            # 向下扩展：查找 region 的所有子区域
            sub_regions = self._get_sub_regions(profile.region)
            for sr in sub_regions:
                conditions.add(("region", sr))

        # CompanyType 精确匹配
        if profile.company_type:
            conditions.add(("company_type", profile.company_type))

        # Industry 精确匹配
        if profile.industry:
            conditions.add(("industry", profile.industry))

        return conditions

    def _get_sub_regions(self, region_name: str) -> list[str]:
        """
        查找 region 的所有子区域（向下扩展，递归）

        深圳 → 坪山区、南山区... → 坪山街道...
        """
        sub_regions = []
        visited = set()

        def _recurse(parent: str):
            if parent in visited:
                return
            visited.add(parent)
            children = self._query_sub_regions(parent)
            for child in children:
                sub_regions.append(child)
                _recurse(child)

        _recurse(region_name)
        return sub_regions

    def _query_sub_regions(self, parent_name: str) -> list[str]:
        """从存储后端查询 parent 的直接子区域"""
        if self._backend == "neo4j" and self._neo4j_store:
            try:
                with self._neo4j_store.driver.session(database=self._neo4j_store.database) as session:
                    result = session.run(
                        "MATCH (child:Region)-[:subregion_of]->(:Region {name: $parent}) "
                        "RETURN child.name AS name",
                        parent=parent_name,
                    )
                    return [r["name"] for r in result if r["name"]]
            except Exception as e:
                logger.warning(f"Neo4j 子区域查询失败: {e}")
                return []
        elif self._backend == "json" and hasattr(self, "region_children"):
            return self.region_children.get(parent_name, [])
        return []

    # JSON 后端专用方法
    def _match_policies(self, company_conditions: set[tuple[str, str]]) -> list[str]:
        """匹配政策：Policy 的 Condition 与企业 Condition 有交集（至少一个条件命中）"""
        matched = []
        for policy_name, policy_triples in self.policy_to_conditions.items():
            policy_conditions = set()
            for t in policy_triples:
                cond_name = t["object"]["name"]
                cond_key = self._get_entity_key(t["object"]["name"], t["object"]["type"])
                cond_entity = self.entity_index.get(cond_key, {})
                category = cond_entity.get("attributes", {}).get("category", "")
                if category:
                    policy_conditions.add((category, cond_name))

            # 无有效条件 → 直接匹配（兜底）
            # 有交集 → 匹配（宽松模式，不要求全部命中）
            if not policy_conditions or policy_conditions & company_conditions:
                matched.append(policy_name)

        return matched

    def _get_policy_conditions(self, policy_name: str) -> list[dict]:
        """获取 Policy 的 Condition 列表（JSON 后端）"""
        conditions = []
        for t in self.policy_to_conditions.get(policy_name, []):
            cond_name = t["object"]["name"]
            cond_key = self._get_entity_key(cond_name, t["object"]["type"])
            cond_entity = self.entity_index.get(cond_key, {})
            category = cond_entity.get("attributes", {}).get("category", "")
            conditions.append({"category": category, "value": cond_name})
        return conditions

    def _get_entity_key(self, name: str, entity_type: str) -> tuple[str, str]:
        return (name, entity_type)
