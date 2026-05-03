"""
图检索器

从企业画像出发，沿 KG 图遍历匹配推理路径：
Company → Condition ← Policy → ActionType → Strategy

当前基于 TripletStore JSON 实现，后续迁移 Neo4j 时替换
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from src.storage.triplet_store import TripletStore
from src.decision.intent_recognizer import EnterpriseProfile


# ── 数据结构 ──

@dataclass
class ReasoningPath:
    """推理路径：一条从 Condition 到 Strategy 的完整路径"""
    policy_name: str
    conditions: list[dict]         # [{category, value}]
    action_type: str
    action_raw: list[str]          # 原始短语
    strategies: list[str]

    def to_dict(self) -> dict:
        return {
            "policy": self.policy_name,
            "conditions": self.conditions,
            "action_type": self.action_type,
            "action_raw": self.action_raw,
            "strategies": self.strategies,
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
    """图遍历检索器"""

    def __init__(self, store: Optional[TripletStore] = None, store_path: Optional[Path] = None):
        """
        Args:
            store: 已加载的 TripletStore
            store_path: TripletStore JSON 文件路径（store 为 None 时从此加载）
        """
        if store:
            self.store = store
        elif store_path:
            self.store = TripletStore.load(store_path)
        else:
            raise ValueError("必须提供 store 或 store_path")

        # 构建索引加速查询
        self._build_indexes()

    def _build_indexes(self):
        """构建内存索引"""
        # 实体索引: (name, type) → entity dict
        self.entity_index: dict[tuple[str, str], dict] = {}
        for e in self.store.entities:
            key = (e["name"], e["type"])
            self.entity_index[key] = e

        # 关系索引：按关系类型分组
        self.triples_by_relation: dict[str, list[dict]] = {}
        for t in self.store.triples:
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

        # Region 层级索引 (subregion_of)
        self.region_parent: dict[str, str] = {}
        for t in self.triples_by_relation.get("subregion_of", []):
            child = t["subject"]["name"]
            parent = t["object"]["name"]
            self.region_parent[child] = parent

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

    def retrieve(self, profile: EnterpriseProfile) -> RetrievalResult:
        """
        基于企业画像进行图遍历检索

        推理路径：
        Company → Condition ← Policy → ActionType → Strategy

        Args:
            profile: 企业画像

        Returns:
            RetrievalResult
        """
        result = RetrievalResult(profile=profile)

        # 1. 构建企业的 Condition 集合（含 region 层级扩展）
        company_conditions = self._expand_conditions(profile)

        # 2. 找匹配的 Policy（Policy 的 Condition ⊆ 企业 Condition）
        matched_policies = self._match_policies(company_conditions)

        if not matched_policies:
            logger.info("未找到匹配政策")
            return result

        # 3. 对每个匹配 Policy，构建推理路径
        for policy_name in matched_policies:
            # 获取 Policy 的 Condition
            policy_conditions = self._get_policy_conditions(policy_name)

            # 获取 Policy 提供的 ActionType
            actions = self.policy_to_actions.get(policy_name, [])

            for action_triple in actions:
                action_type = action_triple["object"]["name"]
                strategies = self.action_to_strategies.get(action_type, [])
                raw_list = self.action_raw_map.get(action_type, [])

                path = ReasoningPath(
                    policy_name=policy_name,
                    conditions=policy_conditions,
                    action_type=action_type,
                    action_raw=raw_list,
                    strategies=strategies,
                )
                result.paths.append(path)
                result.matched_actions.append(action_type)
                result.matched_strategies.extend(strategies)

        # 去重
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

    def _expand_conditions(self, profile: EnterpriseProfile) -> set[tuple[str, str]]:
        """
        扩展企业 Condition 集合

        region 层级扩展：深圳 → {深圳, 广东, 中国}
        company_type/industry 精确匹配
        """
        conditions = set()

        # Region 层级扩展
        if profile.region:
            chain = profile.get_region_chain()
            for r in chain:
                conditions.add(("region", r))

        # CompanyType 精确匹配
        if profile.company_type:
            conditions.add(("company_type", profile.company_type))

        # Industry 精确匹配
        if profile.industry:
            conditions.add(("industry", profile.industry))

        return conditions

    def _match_policies(self, company_conditions: set[tuple[str, str]]) -> list[str]:
        """
        匹配政策：Policy 的 Condition 是企业 Condition 的子集

        即：政策要求的所有条件，企业都满足
        """
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

            # Policy 的条件 ⊆ 企业条件
            if not policy_conditions or policy_conditions.issubset(company_conditions):
                matched.append(policy_name)

        return matched

    def _get_policy_conditions(self, policy_name: str) -> list[dict]:
        """获取 Policy 的 Condition 列表"""
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
