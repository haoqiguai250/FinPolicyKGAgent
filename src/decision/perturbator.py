"""
图扰动器 — KG-PQAM（基于知识图谱扰动的政策适配性量化评估模型）

节点级扰动，4 指标加权量化打分：
1. 收集所有推理路径上的独立节点（Policy、Condition、ActionType、Strategy）
2. 逐个删除节点 → 过滤所有包含该节点的路径 → 重新检索+生成 → 对比答案差异
3. 4 指标量化评分：
   - Δ字符重叠率（5%）：扰动后答案与原始答案的字符重叠差异
   - Δ实体保留率（10%）：扰动后 KG 实体在答案中的保留差异
   - Δ关键词覆盖率（10%）：扰动后关键词在答案中的覆盖差异
   - LLM 语义分（75%）：LLM 裁判对语义变化的主观评分
4. importance = 0.05×Δ字符重叠 + 0.10×Δ实体保留 + 0.10×Δ关键词覆盖 + 0.75×LLM语义分
5. 每个节点可溯源到原文 chunk（source_chunk_id）

执行方式：ThreadPoolExecutor 并行调 LLM
LLM 调用：1(原始) + N(并行扰动) + 1(裁判) = N+2 次

支持双后端：
- Neo4j — Cypher DELETE 关系（不影响节点）
- JSON — 深拷贝删单条三元组
"""

import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from config.settings import settings

from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.extraction.schema import Entity, Triple
from src.decision.graph_retriever import GraphRetriever, RetrievalResult, ReasoningPath
from src.decision.intent_recognizer import EnterpriseProfile
from src.decision.path_to_text import PathToTextConverter
from src.decision.rag_generator import RAGGenerator
from src.extraction.llm_client import DeepSeekClient, get_reasoning_llm_client


# ── 数据结构 ──

@dataclass
class PerturbationNode:
    """一个待扰动的图节点"""
    name: str              # 节点名
    type: str              # 节点类型：Policy / Condition / ActionType / Strategy
    source_chunk_id: str = ""
    source_text: str = ""

    @property
    def key(self) -> str:
        """唯一标识：name__type"""
        return f"{self.name}__{self.type}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "source_chunk_id": self.source_chunk_id,
            "source_text": self.source_text,
        }

    def display(self) -> str:
        return f"{self.type}({self.name})"


# ── 量化权重配置 ──

# KG-PQAM 4 指标权重
W_CHAR_OVERLAP = 0.05      # Δ字符重叠率
W_ENTITY_RETENTION = 0.10  # Δ实体保留率
W_KEYWORD_COVERAGE = 0.10  # Δ关键词覆盖率
W_LLM_SEMANTIC = 0.75      # LLM 语义分

# LLM 失败时权重重分配（前三个指标均分 LLM 的 75%）
W_FALLBACK_EACH = (W_CHAR_OVERLAP + W_ENTITY_RETENTION + W_KEYWORD_COVERAGE + W_LLM_SEMANTIC) / 3


@dataclass
class NodePerturbation:
    """单个节点扰动结果"""
    node: PerturbationNode
    perturbed_answer: str
    importance: float = 0.0     # KG-PQAM 综合量化分 0~1
    reason: str = ""            # LLM 裁判给出的原因
    metric_scores: dict = field(default_factory=dict)  # 4 指标分解
    # metric_scores 结构:
    # {
    #     "char_overlap_diff": float,       # Δ字符重叠率
    #     "entity_retention_diff": float,   # Δ实体保留率
    #     "keyword_coverage_diff": float,   # Δ关键词覆盖率
    #     "llm_semantic_score": float,      # LLM 语义分
    #     "weights": { ... },               # 使用的权重
    # }


@dataclass
class PerturbationReport:
    """扰动分析报告"""
    original_answer: str
    perturbations: list[NodePerturbation] = field(default_factory=list)
    ranked_perturbations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "original_answer_length": len(self.original_answer),
            "perturbation_count": len(self.perturbations),
            "ranked_perturbations": self.ranked_perturbations,
        }


# ── LLM 裁判 Prompt ──

JUDGE_SYSTEM_PROMPT = """你是一个知识图谱可解释性裁判。你需要判断每个知识图谱节点对最终答案的重要性。

评分标准：
- 1.0：删除此节点后，答案完全改变或无法生成（关键节点）
- 0.7-0.9：删除后答案显著缺失重要内容（重要节点）
- 0.3-0.6：删除后答案有部分变化但不影响核心结论（中等节点）
- 0.0-0.2：删除后答案几乎无变化（冗余节点）

你必须对每个节点给出：
1. importance_score（0~1 的浮点数）
2. reason（一句话解释为什么这个分数）

输出严格的 JSON 格式，不要有任何其他文字。"""

JUDGE_USER_PROMPT = """【原始答案】
{original_answer}

【扰动结果】
{perturbation_details}

【节点标识映射】
{key_mapping}

请对每个节点打分，输出 JSON 数组。注意：sub_path_key 字段必须使用上面【节点标识映射】中提供的 key 值，原样复制，不要修改：
```json
[
  {{
    "sub_path_key": "节点标识key",
    "importance_score": 0.0,
    "reason": "原因"
  }}
]
```"""


class Perturbator:
    """
    图扰动器（节点级 + LLM 裁判）

    核心逻辑：
    - 收集推理路径上的所有独立节点（去重）
    - 逐个删除节点 → 过滤包含该节点的所有路径 → 重新生成
    - 4 指标加权量化评分
    """

    def __init__(
        self,
        retriever: GraphRetriever,
        generator: RAGGenerator,
        converter: Optional[PathToTextConverter] = None,
        llm_client: Optional[DeepSeekClient] = None,
        max_workers: Optional[int] = None,
    ):
        self.retriever = retriever
        self.generator = generator
        self.converter = converter or PathToTextConverter()
        self.llm = llm_client or get_reasoning_llm_client()
        self._backend = retriever._backend
        self.max_workers = max_workers or settings.PERTURBATION_PARALLEL_WORKERS

    def analyze(
        self,
        query: str,
        profile: EnterpriseProfile,
        original_result: RetrievalResult,
        original_answer: str,
    ) -> PerturbationReport:
        """
        执行节点级图扰动分析

        1. 收集所有推理路径上的独立节点
        2. 并行：每删一个节点 → 重新检索+生成
        3. LLM 裁判：一次性对比原始答案 vs 所有扰动答案
        """
        report = PerturbationReport(original_answer=original_answer)

        # Step 1: 收集节点
        nodes = self._collect_nodes(original_result)
        if not nodes:
            logger.info("无节点可扰动")
            return report

        logger.info(f"开始节点扰动分析: {len(nodes)} 个节点 (后端: {self._backend})")

        # Step 2: 并行扰动 + LLM 生成
        perturbation_map: dict[str, NodePerturbation] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for node in nodes:
                future = executor.submit(
                    self._perturb_and_generate,
                    query=query,
                    profile=profile,
                    node=node,
                    original_result=original_result,
                )
                futures[future] = node

            for future in as_completed(futures):
                node = futures[future]
                try:
                    perturbed_answer = future.result()
                    perturbation_map[node.key] = NodePerturbation(
                        node=node,
                        perturbed_answer=perturbed_answer,
                    )
                except Exception as e:
                    logger.error(f"扰动节点 {node.display()} 失败: {e}")
                    perturbation_map[node.key] = NodePerturbation(
                        node=node,
                        perturbed_answer="[扰动失败]",
                    )

        if not perturbation_map:
            return report

        # Step 3: KG-PQAM 量化评分（4 指标加权求和）
        logger.info("执行 KG-PQAM 量化评分...")
        scored = self._score_and_quantify(original_answer, list(perturbation_map.values()), original_result)

        # 合并打分结果
        for p in scored:
            report.perturbations.append(p)

        # 按重要性排序
        report.ranked_perturbations = sorted(
            [
                {
                    "node": p.node.to_dict(),
                    "display": p.node.display(),
                    "importance": round(p.importance, 4),
                    "reason": p.reason,
                    "source_chunk_id": p.node.source_chunk_id,
                    "source_text": p.node.source_text,
                    "metric_scores": p.metric_scores,
                }
                for p in report.perturbations
            ],
            key=lambda x: x["importance"],
            reverse=True,
        )

        logger.info(f"节点扰动分析完成: {len(report.ranked_perturbations)} 个已排序")
        return report

    # ══════════════════════════════════════════
    # Step 1: 收集节点
    # ══════════════════════════════════════════

    def _collect_nodes(self, result: RetrievalResult) -> list[PerturbationNode]:
        """
        从检索路径中收集所有独立节点（去重）

        收集类型：Policy、Condition、ActionType、Strategy
        """
        seen: set[str] = set()
        nodes: list[PerturbationNode] = []

        for path in result.paths:
            # Policy 节点
            node = PerturbationNode(
                name=path.policy_name,
                type="Policy",
                source_chunk_id=getattr(path, "policy_chunk_id", ""),
                source_text=getattr(path, "policy_source_text", ""),
            )
            if node.key not in seen:
                seen.add(node.key)
                nodes.append(node)

            # Condition 节点
            for cond in path.conditions:
                val = cond.get("value", "")
                if val:
                    node = PerturbationNode(
                        name=val,
                        type="Condition",
                        source_chunk_id=cond.get("source_chunk_id", ""),
                        source_text=cond.get("source_text", ""),
                    )
                    if node.key not in seen:
                        seen.add(node.key)
                        nodes.append(node)

            # ActionType 节点
            if path.action_type:
                node = PerturbationNode(
                    name=path.action_type,
                    type="ActionType",
                    source_chunk_id=getattr(path, "provides_chunk_id", ""),
                    source_text=getattr(path, "provides_source_text", ""),
                )
                if node.key not in seen:
                    seen.add(node.key)
                    nodes.append(node)

            # Strategy 节点
            for strat in path.strategies:
                if strat:
                    node = PerturbationNode(
                        name=strat,
                        type="Strategy",
                        source_chunk_id=getattr(path, "leads_to_chunk_id", ""),
                        source_text=getattr(path, "leads_to_source_text", ""),
                    )
                    if node.key not in seen:
                        seen.add(node.key)
                        nodes.append(node)

        logger.info(f"收集到 {len(nodes)} 个去重节点")
        return nodes

    # ══════════════════════════════════════════
    # Step 2: 单节点扰动 + LLM 生成
    # ══════════════════════════════════════════

    def _perturb_and_generate(
        self,
        query: str,
        profile: EnterpriseProfile,
        node: PerturbationNode,
        original_result: RetrievalResult,
    ) -> str:
        """
        删除单个节点 → 过滤所有包含该节点的路径 → 重新检索+生成 → 返回扰动答案
        """
        # 过滤掉包含该节点的所有 ReasoningPath
        filtered_paths = self._filter_paths_by_node(original_result.paths, node)

        if not filtered_paths:
            return f"[删除节点 {node.display()} 后，无剩余推理路径可生成建议]"

        # 构建过滤后的 RetrievalResult
        filtered_result = RetrievalResult(
            profile=profile,
            paths=filtered_paths,
        )
        # 重新计算匹配列表
        filtered_result.matched_policies = sorted(set(p.policy_name for p in filtered_paths))
        filtered_result.matched_actions = sorted(set(p.action_type for p in filtered_paths))
        filtered_result.matched_strategies = sorted(
            s for p in filtered_paths for s in p.strategies
        )

        # 转文本 + RAG 生成
        context = self.converter.convert(filtered_result)
        rag_result = self.generator.generate(query, profile, context)

        logger.debug(f"扰动 {node.display()}: 答案长度 {len(rag_result.answer)}")
        return rag_result.answer

    @staticmethod
    def _filter_paths_by_node(
        paths: list[ReasoningPath],
        removed_node: PerturbationNode,
    ) -> list[ReasoningPath]:
        """
        过滤掉包含被删除节点的所有 ReasoningPath

        节点匹配规则：
        - Policy: path.policy_name == node.name
        - Condition: path.conditions 中存在 value == node.name
        - ActionType: path.action_type == node.name
        - Strategy: path.strategies 中包含 node.name
        """
        filtered = []
        node_name = removed_node.name
        node_type = removed_node.type

        for path in paths:
            # 检查路径是否包含被删节点
            if node_type == "Policy" and path.policy_name == node_name:
                continue
            elif node_type == "Condition" and any(
                c.get("value") == node_name for c in path.conditions
            ):
                continue
            elif node_type == "ActionType" and path.action_type == node_name:
                continue
            elif node_type == "Strategy" and node_name in path.strategies:
                continue

            filtered.append(path)

        return filtered

    # ══════════════════════════════════════════
    # Step 3: KG-PQAM 量化评分（4 指标加权求和）
    # ══════════════════════════════════════════

    def _score_and_quantify(
        self,
        original_answer: str,
        perturbations: list[NodePerturbation],
        original_result: RetrievalResult,
    ) -> list[NodePerturbation]:
        """
        KG-PQAM 量化评分：4 指标加权求和

        importance = 0.05×Δ字符重叠 + 0.10×Δ实体保留 + 0.10×Δ关键词覆盖 + 0.75×LLM语义分

        1. 先计算 3 个客观指标（无需 LLM）
        2. 再调用 LLM 裁判打语义分
        3. 加权求和得到最终 importance
        4. LLM 失败时，前三个指标权重均分（各 33.3%）
        """
        # 收集 KG 中的实体名和关键词
        entity_names, keywords = self._collect_kg_terms(original_result)

        # ── 1. 计算原始答案的基准值 ──
        orig_char_set = set(original_answer) if original_answer else set()
        orig_entity_hit = self._entity_hit_count(original_answer, entity_names)
        orig_keyword_hit = self._keyword_hit_count(original_answer, keywords)

        # ── 2. 逐条计算 3 个客观指标 ──
        for p in perturbations:
            perturbed = p.perturbed_answer

            # Δ字符重叠率：1 - (扰动后与原始的字符重叠率)
            char_diff = self._calc_char_overlap_diff(original_answer, perturbed)

            # Δ实体保留率：原始命中实体数 - 扰动后命中实体数 / 原始命中实体数
            entity_diff = self._calc_entity_retention_diff(
                orig_entity_hit, perturbed, entity_names
            )

            # Δ关键词覆盖率：原始命中关键词数 - 扰动后命中关键词数 / 原始命中关键词数
            keyword_diff = self._calc_keyword_coverage_diff(
                orig_keyword_hit, perturbed, keywords
            )

            # 先存入 metric_scores（LLM 分后面填）
            p.metric_scores = {
                "char_overlap_diff": round(char_diff, 4),
                "entity_retention_diff": round(entity_diff, 4),
                "keyword_coverage_diff": round(keyword_diff, 4),
                "llm_semantic_score": 0.0,  # 待 LLM 填入
                "weights": {
                    "char_overlap": W_CHAR_OVERLAP,
                    "entity_retention": W_ENTITY_RETENTION,
                    "keyword_coverage": W_KEYWORD_COVERAGE,
                    "llm_semantic": W_LLM_SEMANTIC,
                },
            }

        # ── 3. LLM 裁判打语义分 ──
        llm_ok = False
        try:
            llm_ok = self._llm_judge(original_answer, perturbations)
        except Exception as e:
            logger.error(f"LLM 裁判异常: {e}")

        # ── 4. 加权求和 ──
        for p in perturbations:
            ms = p.metric_scores
            if llm_ok:
                # 正常加权
                p.importance = round(
                    W_CHAR_OVERLAP * ms["char_overlap_diff"]
                    + W_ENTITY_RETENTION * ms["entity_retention_diff"]
                    + W_KEYWORD_COVERAGE * ms["keyword_coverage_diff"]
                    + W_LLM_SEMANTIC * ms["llm_semantic_score"],
                    4,
                )
            else:
                # LLM 失败：前三个指标均分（各 ≈ 0.333）
                p.importance = round(
                    W_FALLBACK_EACH * ms["char_overlap_diff"]
                    + W_FALLBACK_EACH * ms["entity_retention_diff"]
                    + W_FALLBACK_EACH * ms["keyword_coverage_diff"],
                    4,
                )
                ms["llm_semantic_score"] = None  # 标记 LLM 未评分
                ms["weights"] = {
                    "char_overlap": round(W_FALLBACK_EACH, 4),
                    "entity_retention": round(W_FALLBACK_EACH, 4),
                    "keyword_coverage": round(W_FALLBACK_EACH, 4),
                    "llm_semantic": 0.0,
                    "fallback": True,
                }
                if not p.reason:
                    p.reason = "LLM 裁判异常，仅用客观指标（权重均分）"

        return perturbations

    # ── 3 个客观指标计算 ──

    @staticmethod
    def _calc_char_overlap_diff(original: str, perturbed: str) -> float:
        """
        Δ字符重叠率：原始答案与扰动答案的字符重叠差异

        diff = 1 - |S_orig ∩ S_pert| / |S_orig ∪ S_pert|
        值域 [0, 1]，越大表示差异越大
        """
        if not original or not perturbed:
            return 1.0 if original else 0.0
        s_orig = set(original)
        s_pert = set(perturbed)
        union = s_orig | s_pert
        if not union:
            return 0.0
        intersection = s_orig & s_pert
        return 1.0 - len(intersection) / len(union)

    @staticmethod
    def _calc_entity_retention_diff(
        orig_hit: int, perturbed_answer: str, entity_names: list[str]
    ) -> float:
        """
        Δ实体保留率：原始答案命中实体数 - 扰动后命中实体数 / max(原始命中, 1)

        值域 [0, 1]，越大表示实体丢失越多
        """
        if orig_hit == 0:
            return 0.0
        pert_hit = sum(1 for e in entity_names if e in perturbed_answer)
        diff = (orig_hit - pert_hit) / orig_hit
        return max(0.0, min(1.0, diff))

    @staticmethod
    def _calc_keyword_coverage_diff(
        orig_hit: int, perturbed_answer: str, keywords: list[str]
    ) -> float:
        """
        Δ关键词覆盖率：原始答案命中关键词数 - 扰动后命中关键词数 / max(原始命中, 1)

        值域 [0, 1]，越大表示关键词覆盖下降越多
        """
        if orig_hit == 0:
            return 0.0
        pert_hit = sum(1 for kw in keywords if kw in perturbed_answer)
        diff = (orig_hit - pert_hit) / orig_hit
        return max(0.0, min(1.0, diff))

    # ── 辅助：实体/关键词命中计数 ──

    @staticmethod
    def _entity_hit_count(answer: str, entity_names: list[str]) -> int:
        """答案中命中了多少个实体名"""
        return sum(1 for e in entity_names if e in answer)

    @staticmethod
    def _keyword_hit_count(answer: str, keywords: list[str]) -> int:
        """答案中命中了多少个关键词"""
        return sum(1 for kw in keywords if kw in answer)

    # ── 从 RetrievalResult 提取实体名和关键词 ──

    @staticmethod
    def _collect_kg_terms(result: RetrievalResult) -> tuple[list[str], list[str]]:
        """
        从检索结果中收集：
        - entity_names: 所有实体名（Policy、Condition、ActionType、Strategy）
        - keywords: 去重关键词（来自 condition 值 + strategy 名 + action_type 名）

        用于计算实体保留率和关键词覆盖率
        """
        entity_set: set[str] = set()
        keyword_set: set[str] = set()

        for path in result.paths:
            # Policy 名
            if path.policy_name:
                entity_set.add(path.policy_name)

            # Condition 值 → 同时作为实体和关键词
            for cond in path.conditions:
                val = cond.get("value", "")
                if val:
                    entity_set.add(val)
                    keyword_set.add(val)

            # ActionType → 实体 + 关键词
            if path.action_type:
                entity_set.add(path.action_type)
                keyword_set.add(path.action_type)

            # Strategy → 实体 + 关键词
            for strat in path.strategies:
                if strat:
                    entity_set.add(strat)
                    keyword_set.add(strat)

        # 关键词额外加入 Action 6 大类的标准名（确保覆盖大类）
        ACTION_CATEGORIES = ["融资类", "财政类", "税收类", "风险类", "投资类", "人才类"]
        for cat in ACTION_CATEGORIES:
            keyword_set.add(cat)

        return list(entity_set), list(keyword_set)

    # ══════════════════════════════════════════
    # LLM 裁判（仅负责语义分，不再决定 importance）
    # ══════════════════════════════════════════

    def _llm_judge(
        self,
        original_answer: str,
        perturbations: list[NodePerturbation],
    ) -> bool:
        """
        LLM 裁判：一次性对比原始答案 vs 所有扰动答案，输出每个节点的语义变化分

        成功时将 llm_semantic_score 写入每个 perturbation.metric_scores
        返回 True 表示成功，False 表示失败
        """
        # 构建扰动详情 + 显式 key 映射
        details = []
        key_mapping_lines = []
        for i, p in enumerate(perturbations, 1):
            key = p.node.key
            details.append(
                f"节点{i} [key: {key}]: {p.node.display()}\n"
                f"  删除此节点后的答案: {p.perturbed_answer[:300]}{'...' if len(p.perturbed_answer) > 300 else ''}"
            )
            key_mapping_lines.append(f"  {key} → {p.node.display()}")

        perturbation_details = "\n\n".join(details)
        key_mapping = "\n".join(key_mapping_lines)

        user_prompt = JUDGE_USER_PROMPT.format(
            original_answer=original_answer,
            perturbation_details=perturbation_details,
            key_mapping=key_mapping,
        )

        try:
            response = self.llm.chat(
                system_prompt=JUDGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.1,
            )

            # 解析 LLM 返回的 JSON
            scores = self._parse_judge_response(response, perturbations)

            # 将语义分写入 perturbations
            for p in perturbations:
                key = p.node.key
                if key in scores:
                    p.metric_scores["llm_semantic_score"] = round(
                        float(scores[key].get("importance_score", 0.5)), 4
                    )
                    p.reason = scores[key].get("reason", "")
                else:
                    # LLM 漏打了，用默认值
                    p.metric_scores["llm_semantic_score"] = 0.5
                    p.reason = "LLM 裁判未评分，使用默认语义分"

            return True

        except Exception as e:
            logger.error(f"LLM 裁判异常: {e}")
            # 语义分留 0，_score_and_quantify 会走 fallback 权重重分配
            return False

    def _parse_judge_response(
        self,
        response: str,
        perturbations: list[NodePerturbation],
    ) -> dict[str, dict]:
        """解析 LLM 裁判返回的 JSON"""
        # 提取 JSON 部分
        text = response.strip()

        # 尝试从 markdown code block 中提取
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"LLM 裁判返回非法 JSON，尝试修复: {text[:200]}")
            # 尝试提取数组部分
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    items = json.loads(text[start:end])
                except json.JSONDecodeError:
                    logger.error("JSON 修复失败，所有节点使用默认分数")
                    return {}
            else:
                return {}

        # 构建 key → score 映射
        scores: dict[str, dict] = {}
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = item.get("sub_path_key", "")
                importance = item.get("importance_score", 0.5)
                reason = item.get("reason", "")

                if key:
                    scores[key] = {
                        "importance_score": float(importance),
                        "reason": reason,
                    }

        # 如果 key 没匹配上，按顺序匹配
        if len(scores) != len(perturbations):
            logger.warning(
                f"LLM 裁判返回 {len(scores)} 条评分，期望 {len(perturbations)} 条，"
                f"尝试按顺序匹配"
            )
            scores_fallback: dict[str, dict] = {}
            for i, item in enumerate(items if isinstance(items, list) else []):
                if i < len(perturbations):
                    key = perturbations[i].node.key
                    importance = item.get("importance_score", 0.5) if isinstance(item, dict) else 0.5
                    reason = item.get("reason", "") if isinstance(item, dict) else ""
                    scores_fallback[key] = {
                        "importance_score": float(importance),
                        "reason": reason,
                    }
            if len(scores_fallback) > len(scores):
                scores = scores_fallback

        return scores
