"""
Stage 5: 四层一体化评估体系

对应论文评估框架：
- L1: CheckRules（规则合规性评估）— 4条强制规则
- L2: Local Extraction Efficiency（本地抽取效率）— 覆盖率指标
- L3: Global Semantic Diversity（全局语义多样性）— 熵度量
- L4: LLM-as-a-Judge（大模型裁判评估）— 4维度打分
"""

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from src.extraction.schema import Entity, Triple, EntityType, RelationType, RELATION_CONSTRAINTS, ENTITY_HIERARCHY
from src.extraction.reflector import ReflectionResult
from src.storage.triplet_store import TripletStore


# ══════════════════════════════════════════
# 评估报告数据结构
# ══════════════════════════════════════════

@dataclass
class CheckRulesResult:
    """L1: 规则合规性评估结果"""
    total_triples: int = 0
    fully_compliant_count: int = 0       # 满足全部4条规则的三元组数
    compliance_rate: float = 0.0         # 完全合规率

    # 4条规则各自的违规数
    vague_reference_violations: int = 0   # 规则1: 主体引用明确
    entity_length_violations: int = 0     # 规则2: 实体长度≤15字符
    entity_type_violations: int = 0       # 规则3: 实体类型合规
    relation_type_violations: int = 0     # 规则4: 关系类型合规

    # 逐条详情
    violation_details: list[dict] = field(default_factory=list)


@dataclass
class LocalEfficiencyResult:
    """L2: 本地抽取效率评估结果"""
    avg_triples_per_chunk: float = 0.0   # 每块平均三元组数
    ecr: float = 0.0                     # 实体覆盖率 Entity Coverage Rate
    tcr: float = 0.0                     # 实体类型覆盖率 Type Coverage Rate
    rcr: float = 0.0                     # 关系覆盖率 Relation Coverage Rate
    tcr_normalized: float = 0.0          # 归一化实体类型覆盖率
    rcr_normalized: float = 0.0          # 归一化关系覆盖率


@dataclass
class SemanticDiversityResult:
    """L3: 全局语义多样性评估结果"""
    shannon_entropy_entity: float = 0.0       # 香农熵（实体类型分布）
    shannon_entropy_relation: float = 0.0     # 香农熵（关系类型分布）
    schema_normalized_entropy_entity: float = 0.0   # Schema归一化熵（实体）
    schema_normalized_entropy_relation: float = 0.0  # Schema归一化熵（关系）
    renyi_entropy_entity: float = 0.0         # Rényi熵（实体，α=2）
    renyi_entropy_relation: float = 0.0       # Rényi熵（关系，α=2）


@dataclass
class LLMJudgeResult:
    """L4: LLM-as-a-Judge 评估结果"""
    precision: float = 0.0       # 精确性 [0, 1]
    faithfulness: float = 0.0    # 忠实度 [0, 1]
    comprehensiveness: float = 0.0  # 完整性 [0, 1]
    relevance: float = 0.0       # 相关性 [0, 1]
    overall_score: float = 0.0   # 综合得分（4项均值）
    judge_reasoning: str = ""    # LLM 评审理由


@dataclass
class EvaluationReport:
    """四层一体化评估报告"""
    source_file: str = ""

    # L1: 规则合规性
    check_rules: CheckRulesResult = field(default_factory=CheckRulesResult)

    # L2: 本地抽取效率
    local_efficiency: LocalEfficiencyResult = field(default_factory=LocalEfficiencyResult)

    # L3: 全局语义多样性
    semantic_diversity: SemanticDiversityResult = field(default_factory=SemanticDiversityResult)

    # L4: LLM-as-a-Judge
    llm_judge: LLMJudgeResult = field(default_factory=LLMJudgeResult)

    # 反思效率
    reflection_iterations: int = 0
    reflection_converged: bool = False

    # 基础统计（兼容旧版）
    total_entities: int = 0
    total_triples: int = 0
    avg_confidence: float = 0.0
    entity_type_distribution: dict = field(default_factory=dict)
    relation_type_distribution: dict = field(default_factory=dict)

    def to_text(self) -> str:
        """生成可读的评估报告文本"""
        cr = self.check_rules
        le = self.local_efficiency
        sd = self.semantic_diversity
        lj = self.llm_judge

        lines = [
            f"═══════════════════════════════════════════════════",
            f"  FinPolicyKG 四层一体化评估报告",
            f"═══════════════════════════════════════════════════",
            f"文档: {self.source_file}",
            f"实体: {self.total_entities}  三元组: {self.total_triples}  置信度: {self.avg_confidence:.2f}",
            f"",
            f"【L1: CheckRules 规则合规性】",
            f"  完全合规率: {cr.compliance_rate:.1%} ({cr.fully_compliant_count}/{cr.total_triples})",
            f"  规则1 主体引用明确: {cr.vague_reference_violations} 违规",
            f"  规则2 实体长度≤15字符: {cr.entity_length_violations} 违规",
            f"  规则3 实体类型合规: {cr.entity_type_violations} 违规",
            f"  规则4 关系类型合规: {cr.relation_type_violations} 违规",
            f"",
            f"【L2: Local Extraction Efficiency 本地抽取效率】",
            f"  每块平均三元组数: {le.avg_triples_per_chunk:.2f}",
            f"  ECR 实体覆盖率: {le.ecr:.1%}",
            f"  TCR 实体类型覆盖率: {le.tcr:.1%}",
            f"  RCR 关系覆盖率: {le.rcr:.1%}",
            f"  TCR-N 归一化类型覆盖率: {le.tcr_normalized:.1%}",
            f"  RCR-N 归一化关系覆盖率: {le.rcr_normalized:.1%}",
            f"",
            f"【L3: Global Semantic Diversity 全局语义多样性】",
            f"  香农熵(实体): {sd.shannon_entropy_entity:.4f}",
            f"  香农熵(关系): {sd.shannon_entropy_relation:.4f}",
            f"  Schema归一化熵(实体): {sd.schema_normalized_entropy_entity:.4f}",
            f"  Schema归一化熵(关系): {sd.schema_normalized_entropy_relation:.4f}",
            f"  Rényi熵(实体, α=2): {sd.renyi_entropy_entity:.4f}",
            f"  Rényi熵(关系, α=2): {sd.renyi_entropy_relation:.4f}",
            f"",
            f"【L4: LLM-as-a-Judge 大模型裁判】",
            f"  精确性 Precision:       {lj.precision:.2f}",
            f"  忠实度 Faithfulness:     {lj.faithfulness:.2f}",
            f"  完整性 Comprehensiveness: {lj.comprehensiveness:.2f}",
            f"  相关性 Relevance:        {lj.relevance:.2f}",
            f"  综合得分:                {lj.overall_score:.2f}",
            f"",
            f"【反思效率】",
            f"  迭代轮次: {self.reflection_iterations}",
            f"  是否收敛: {'是' if self.reflection_converged else '否'}",
        ]
        if lj.judge_reasoning:
            lines.append(f"")
            lines.append(f"【LLM 评审理由】")
            lines.append(f"  {lj.judge_reasoning}")
        lines.append(f"═══════════════════════════════════════════════════")
        return "\n".join(lines)


# ══════════════════════════════════════════
# L1: CheckRules 规则合规性评估
# ══════════════════════════════════════════

# 模糊指代模式（中英文）
VAGUE_PATTERNS = [
    r"(?i)\bthe company\b", r"(?i)\bwe\b", r"(?i)\bour\b",
    r"本公司", r"该公司", r"此公司", r"该机构", r"本机构",
    r"该行", r"本行", r"我行", r"该单位", r"本单位",
]


class CheckRulesEvaluator:
    """L1: 规则合规性评估器 — 4条强制规则"""

    @staticmethod
    def _check_vague_reference(name: str) -> bool:
        """规则1: 主体引用明确 — 不允许模糊指代"""
        for pattern in VAGUE_PATTERNS:
            if re.search(pattern, name):
                return False  # 违规
        return True  # 合规

    @staticmethod
    def _check_entity_length(name: str, max_chars: int = 15) -> bool:
        """规则2: 实体名称长度≤15个字符（中文≈15字，英文≈15词）"""
        return len(name) <= max_chars

    @staticmethod
    def _check_entity_type(entity_type: str) -> bool:
        """规则3: 实体类型必须是预定义 Schema 里的类型"""
        try:
            EntityType(entity_type)
            return True
        except ValueError:
            return entity_type in ENTITY_HIERARCHY

    @staticmethod
    def _check_relation_type(relation: str) -> bool:
        """规则4: 关系类型必须是预定义 Schema 里的关系"""
        try:
            RelationType(relation)
            return True
        except ValueError:
            return False

    def evaluate(self, store: TripletStore) -> CheckRulesResult:
        """评估所有三元组的规则合规性"""
        result = CheckRulesResult()
        result.total_triples = len(store.triples)

        for t_data in store.triples:
            subj_name = t_data.get("subject", {}).get("name", "")
            obj_name = t_data.get("object", {}).get("name", "")
            subj_type = t_data.get("subject", {}).get("type", "")
            obj_type = t_data.get("object", {}).get("type", "")
            relation = t_data.get("relation", "")

            violations = []

            # 规则1: 主体引用明确
            r1_subj = self._check_vague_reference(subj_name)
            r1_obj = self._check_vague_reference(obj_name)
            if not r1_subj or not r1_obj:
                result.vague_reference_violations += 1
                violations.append("主体引用模糊")

            # 规则2: 实体长度≤15字符
            r2_subj = self._check_entity_length(subj_name)
            r2_obj = self._check_entity_length(obj_name)
            if not r2_subj or not r2_obj:
                result.entity_length_violations += 1
                violations.append("实体名称过长(>15字符)")

            # 规则3: 实体类型合规
            r3_subj = self._check_entity_type(subj_type)
            r3_obj = self._check_entity_type(obj_type)
            if not r3_subj or not r3_obj:
                result.entity_type_violations += 1
                violations.append(f"实体类型不合规: {subj_type if not r3_subj else obj_type}")

            # 规则4: 关系类型合规
            r4 = self._check_relation_type(relation)
            if not r4:
                result.relation_type_violations += 1
                violations.append(f"关系类型不合规: {relation}")

            # 全部4条通过才算完全合规
            if not violations:
                result.fully_compliant_count += 1

            if violations:
                result.violation_details.append({
                    "triple": f"{subj_name} --{relation}--> {obj_name}",
                    "violations": violations,
                })

        result.compliance_rate = (
            result.fully_compliant_count / result.total_triples
            if result.total_triples > 0 else 0.0
        )

        return result


# ══════════════════════════════════════════
# L2: Local Extraction Efficiency 本地抽取效率
# ══════════════════════════════════════════

class LocalEfficiencyEvaluator:
    """L2: 本地抽取效率评估器 — 覆盖率指标"""

    # Schema 预定义的实体类型和关系类型总数
    TOTAL_ENTITY_TYPES = len(EntityType)  # 16
    TOTAL_RELATION_TYPES = len(RelationType)  # 13

    def evaluate(
        self,
        store: TripletStore,
        num_chunks: int = 1,
    ) -> LocalEfficiencyResult:
        """
        评估抽取效率

        Args:
            store: 三元组存储
            num_chunks: 文本分块数量
        """
        result = LocalEfficiencyResult()

        # 每块平均三元组数
        result.avg_triples_per_chunk = (
            len(store.triples) / num_chunks if num_chunks > 0 else 0.0
        )

        # ECR: 实体覆盖率 = 有关系的实体数 / 总实体数
        entities_in_triples = set()
        for t in store.triples:
            entities_in_triples.add(t["subject"]["name"])
            entities_in_triples.add(t["object"]["name"])

        total_entities = len(store.entities)
        result.ecr = (
            len(entities_in_triples) / total_entities
            if total_entities > 0 else 0.0
        )

        # TCR: 实体类型覆盖率 = 出现的实体类型数 / Schema预定义实体类型数
        observed_entity_types = set()
        for e in store.entities:
            observed_entity_types.add(e["type"])

        result.tcr = (
            len(observed_entity_types) / self.TOTAL_ENTITY_TYPES
            if self.TOTAL_ENTITY_TYPES > 0 else 0.0
        )

        # RCR: 关系覆盖率 = 出现的关系类型数 / Schema预定义关系类型数
        observed_relation_types = set()
        for t in store.triples:
            observed_relation_types.add(t["relation"])

        result.rcr = (
            len(observed_relation_types) / self.TOTAL_RELATION_TYPES
            if self.TOTAL_RELATION_TYPES > 0 else 0.0
        )

        # TCR-N: 归一化实体类型覆盖率（考虑层级结构）
        # 子类和父类只计一次
        unique_base_types = set()
        for et in observed_entity_types:
            base = ENTITY_HIERARCHY.get(et, et)
            unique_base_types.add(base)

        # Schema 中的基础类型数
        base_schema_types = set()
        for et in EntityType:
            base_schema_types.add(et.value)
        for sub, parent in ENTITY_HIERARCHY.items():
            base_schema_types.discard(sub)

        result.tcr_normalized = (
            len(unique_base_types) / len(base_schema_types)
            if base_schema_types else 0.0
        )

        # RCR-N: 归一化关系覆盖率（只计有效关系，排除 valid_during 等空约束）
        valid_relations = {rt.value for rt in RelationType if RELATION_CONSTRAINTS.get(rt.value, ([], []))[1]}
        observed_valid = observed_relation_types & valid_relations

        result.rcr_normalized = (
            len(observed_valid) / len(valid_relations)
            if valid_relations else 0.0
        )

        return result


# ══════════════════════════════════════════
# L3: Global Semantic Diversity 全局语义多样性
# ══════════════════════════════════════════

class SemanticDiversityEvaluator:
    """L3: 全局语义多样性评估器 — 熵度量"""

    @staticmethod
    def _shannon_entropy(distribution: dict[str, int]) -> float:
        """
        计算香农熵 H = -Σ p_i * log2(p_i)

        Args:
            distribution: {类别: 频次}
        """
        total = sum(distribution.values())
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in distribution.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        return entropy

    @staticmethod
    def _max_entropy(n: int) -> float:
        """均匀分布时的最大熵 = log2(n)"""
        return math.log2(n) if n > 1 else 0.0

    @staticmethod
    def _renyi_entropy(distribution: dict[str, int], alpha: float = 2.0) -> float:
        """
        计算 Rényi 熵 H_α = 1/(1-α) * log2(Σ p_i^α)

        α=2 时：H_2 = -log2(Σ p_i^2)，即碰撞熵

        Args:
            distribution: {类别: 频次}
            alpha: Rényi 熵参数，默认2
        """
        total = sum(distribution.values())
        if total == 0:
            return 0.0

        sum_p_alpha = 0.0
        for count in distribution.values():
            if count > 0:
                p = count / total
                sum_p_alpha += p ** alpha

        if sum_p_alpha <= 0:
            return 0.0

        return (1.0 / (1.0 - alpha)) * math.log2(sum_p_alpha)

    def evaluate(self, store: TripletStore) -> SemanticDiversityResult:
        """评估全局语义多样性"""
        result = SemanticDiversityResult()

        # 实体类型分布
        entity_type_dist = {}
        for e in store.entities:
            et = e["type"]
            entity_type_dist[et] = entity_type_dist.get(et, 0) + 1

        # 关系类型分布
        relation_type_dist = {}
        for t in store.triples:
            rt = t["relation"]
            relation_type_dist[rt] = relation_type_dist.get(rt, 0) + 1

        # 香农熵
        result.shannon_entropy_entity = self._shannon_entropy(entity_type_dist)
        result.shannon_entropy_relation = self._shannon_entropy(relation_type_dist)

        # Schema 归一化熵 = H / H_max(Schema)
        # H_max = log2(Schema预定义类型数)
        h_max_entity = self._max_entropy(len(EntityType))
        h_max_relation = self._max_entropy(len(RelationType))

        result.schema_normalized_entropy_entity = (
            result.shannon_entropy_entity / h_max_entity if h_max_entity > 0 else 0.0
        )
        result.schema_normalized_entropy_relation = (
            result.shannon_entropy_relation / h_max_relation if h_max_relation > 0 else 0.0
        )

        # Rényi 熵 (α=2)
        result.renyi_entropy_entity = self._renyi_entropy(entity_type_dist, alpha=2.0)
        result.renyi_entropy_relation = self._renyi_entropy(relation_type_dist, alpha=2.0)

        return result


# ══════════════════════════════════════════
# L4: LLM-as-a-Judge 大模型裁判评估
# ══════════════════════════════════════════

JUDGE_SYSTEM_PROMPT = """你是一个金融政策知识图谱质量评审专家。请对以下知识图谱抽取结果进行4个维度的评分。

【评分维度】
1. Precision（精确性）: 实体是否清晰、唯一、无歧义？关系是否精确？
2. Faithfulness（忠实度）: 三元组是否忠实于原文事实？有没有编造或歪曲？
3. Comprehensiveness（完整性）: 是否把原文中的关键实体和关系都抽取出来了？有无遗漏？
4. Relevance（相关性）: 抽取的三元组是否与金融政策主题相关？有没有无关噪声？

【评分标准】
每个维度 0-10 分，10分最优。

【输出格式】严格输出以下 JSON：
{
  "precision": 评分,
  "faithfulness": 评分,
  "comprehensiveness": 评分,
  "relevance": 评分,
  "reasoning": "简短评审理由（100字以内）"
}"""

JUDGE_USER_PROMPT = """【原始政策文本】
{source_text}

【抽取的三元组】
{triples_json}

请对上述抽取结果进行4维度评分。"""


class LLMJudgeEvaluator:
    """L4: LLM-as-a-Judge 评估器"""

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: UniversalLLMClient 实例，为 None 时不执行 L4 评估
        """
        self.llm = llm_client

    def evaluate(
        self,
        store: TripletStore,
        source_text: str = "",
    ) -> LLMJudgeResult:
        """
        使用 LLM 对抽取结果进行裁判评分

        Args:
            store: 三元组存储
            source_text: 原始文本（用于忠实度评估）
        """
        result = LLMJudgeResult()

        if self.llm is None:
            logger.warning("L4 评估跳过: 未提供 LLM 客户端")
            return result

        if not store.triples:
            logger.warning("L4 评估跳过: 无三元组数据")
            return result

        # 构造评估输入
        import json
        triples_summary = json.dumps(
            store.triples, ensure_ascii=False, indent=2
        )

        # 如果原文太长，截断
        if len(source_text) > 3000:
            source_text = source_text[:3000] + "...(截断)"

        try:
            judge_result = self.llm.chat_json(
                system_prompt=JUDGE_SYSTEM_PROMPT,
                user_prompt=JUDGE_USER_PROMPT.format(
                    source_text=source_text or "（原文未提供）",
                    triples_json=triples_summary,
                ),
                temperature=0.1,
            )

            # 归一化到 [0, 1]
            result.precision = min(judge_result.get("precision", 0) / 10.0, 1.0)
            result.faithfulness = min(judge_result.get("faithfulness", 0) / 10.0, 1.0)
            result.comprehensiveness = min(judge_result.get("comprehensiveness", 0) / 10.0, 1.0)
            result.relevance = min(judge_result.get("relevance", 0) / 10.0, 1.0)
            result.judge_reasoning = judge_result.get("reasoning", "")

            # 综合得分 = 4项均值
            result.overall_score = (
                result.precision + result.faithfulness
                + result.comprehensiveness + result.relevance
            ) / 4.0

        except Exception as e:
            logger.error(f"L4 LLM-as-Judge 评估异常: {e}")

        return result


# ══════════════════════════════════════════
# 统一评估入口
# ══════════════════════════════════════════

class Evaluator:
    """四层一体化评估器"""

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: UniversalLLMClient 实例，为 None 时跳过 L4 评估
        """
        self.check_rules = CheckRulesEvaluator()
        self.local_efficiency = LocalEfficiencyEvaluator()
        self.semantic_diversity = SemanticDiversityEvaluator()
        self.llm_judge = LLMJudgeEvaluator(llm_client)

    def evaluate(
        self,
        store: TripletStore,
        reflection_result: Optional[ReflectionResult] = None,
        num_chunks: int = 1,
        source_text: str = "",
        enable_llm_judge: bool = True,
    ) -> EvaluationReport:
        """
        执行四层一体化评估

        Args:
            store: 三元组存储
            reflection_result: 反思迭代结果（可选）
            num_chunks: 文本分块数量
            source_text: 原始文本（用于 L4 忠实度评估）
            enable_llm_judge: 是否启用 L4 评估（需要 LLM 调用）

        Returns:
            EvaluationReport: 四层评估报告
        """
        report = EvaluationReport(source_file=store.source_file)

        # ── 基础统计 ──
        report.total_entities = len(store.entities)
        report.total_triples = len(store.triples)

        # 类型分布
        entity_types = {}
        for e in store.entities:
            et = e["type"]
            entity_types[et] = entity_types.get(et, 0) + 1
        report.entity_type_distribution = entity_types

        relation_types = {}
        for t in store.triples:
            rt = t["relation"]
            relation_types[rt] = relation_types.get(rt, 0) + 1
        report.relation_type_distribution = relation_types

        # 置信度
        confidences = [t.get("confidence", 1.0) for t in store.triples]
        report.avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # ── L1: CheckRules ──
        logger.info("评估 L1: CheckRules 规则合规性...")
        report.check_rules = self.check_rules.evaluate(store)

        # ── L2: Local Efficiency ──
        logger.info("评估 L2: Local Extraction Efficiency...")
        report.local_efficiency = self.local_efficiency.evaluate(store, num_chunks)

        # ── L3: Semantic Diversity ──
        logger.info("评估 L3: Global Semantic Diversity...")
        report.semantic_diversity = self.semantic_diversity.evaluate(store)

        # ── L4: LLM-as-a-Judge ──
        if enable_llm_judge and self.llm_judge.llm is not None:
            logger.info("评估 L4: LLM-as-a-Judge...")
            report.llm_judge = self.llm_judge.evaluate(store, source_text)
        else:
            logger.info("L4: LLM-as-a-Judge 跳过（未启用或无 LLM 客户端）")

        # ── 反思效率 ──
        if reflection_result:
            report.reflection_iterations = reflection_result.iterations
            report.reflection_converged = reflection_result.converged

        # 打印报告
        logger.info(f"\n{report.to_text()}")
        return report
