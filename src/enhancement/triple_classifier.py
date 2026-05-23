"""
三元组语义分级处理器

根据归一化后的三元组校验结果，将其分为6个处理级别：
PASS / PASS_PROMOTED / PASS_NORMALIZED / PASS_TRUNCATED / POOL / DROP

关键：分级必须在归一化+候选池注册之后执行
"""

from src.extraction.schema import Triple, ValidationIssues, RELATION_CONSTRAINTS
from src.enhancement.normalizer import RelationNormalizer
from src.enhancement.candidate_pool import CandidatePool
from config.settings import settings


def classify_triple(
    t: Triple,
    pool: CandidatePool,
    normalizer: RelationNormalizer,
    issues: ValidationIssues | None = None,
) -> str:
    """
    对三元组进行分级判定。

    必须在归一化+候选池注册之后调用，此时：
    1. 能归一化的关系已归一化（不会再因命名不同被分裂）
    2. 候选池计数已更新（classify 查到的 count 是准确的）

    Args:
        t: 待判定的三元组
        pool: 候选池实例
        normalizer: 归一化器实例
        issues: 可选的预计算校验结果（避免重复校验）

    Returns:
        处理级别字符串
    """
    if issues is None:
        issues = t.validate()

    # 完全合规
    if not issues.has_any():
        return "PASS"

    # --- 情况 1：关系类型未知但实体类型合法 ---
    if issues.relation_unknown and not issues.head_type_mismatch and not issues.tail_type_mismatch:
        # 查候选池计数（已在归一化+注册阶段更新）
        n = pool.count(t.relation, t.subject.entity_type, t.object_.entity_type)
        if n >= settings.AUTO_PROMOTE_THRESHOLD:
            return "PASS_PROMOTED"  # 自动转正入库
        return "POOL"               # 进候选池

    # --- 情况 2：关系类型已知但实体类型不匹配 ---
    if not issues.relation_unknown and (issues.head_type_mismatch or issues.tail_type_mismatch):
        if _can_normalize(t, normalizer, pool):
            return "PASS_NORMALIZED"  # 归一化后入库
        return "POOL"                 # 无法归一化，进候选池

    # --- 情况 3：混合问题（关系未知+类型不匹配）---
    if issues.relation_unknown and (issues.head_type_mismatch or issues.tail_type_mismatch):
        return "POOL"  # 降级到候选池，待人工判断

    # --- 情况 4：实体名过长等非关键问题 ---
    if (issues.entity_length_exceeded
            and not issues.relation_unknown
            and not issues.head_type_mismatch
            and not issues.tail_type_mismatch):
        return "PASS_TRUNCATED"  # 截断实体名后入库

    # --- 情况 5：明显错误 ---
    return "DROP"


def _can_normalize(
    t: Triple,
    normalizer: RelationNormalizer,
    pool: CandidatePool,
) -> bool:
    """
    判定三元组是否可通过归一化修复实体类型不匹配问题

    判定链：
    1. 关系名在映射表中 → 归一化后类型可能匹配
    2. 关系名在候选池 promoted 列表中 → 可归一化
    3. 都不命中 → 无法归一化
    """
    _, changed, _ = normalizer.normalize(t.relation)
    if changed:
        return True

    if pool.is_promoted(t.relation):
        return True

    return False


def _get_pool_reason(issues: ValidationIssues) -> str:
    """根据校验结果生成进池原因描述"""
    parts = []
    if issues.relation_unknown:
        parts.append("关系未知")
    if issues.head_type_mismatch:
        parts.append("主语类型不匹配")
    if issues.tail_type_mismatch:
        parts.append("宾语类型不匹配")
    if issues.relation_constraint_violation:
        parts.append("关系约束违反")
    return "；".join(parts) if parts else "未知原因"


# ── 级别定义常量 ──

LEVEL_PASS = "PASS"
LEVEL_PASS_PROMOTED = "PASS_PROMOTED"
LEVEL_PASS_NORMALIZED = "PASS_NORMALIZED"
LEVEL_PASS_TRUNCATED = "PASS_TRUNCATED"
LEVEL_POOL = "POOL"
LEVEL_DROP = "DROP"

# 各级别对应的置信度和来源标记
LEVEL_CONFIG = {
    LEVEL_PASS:             {"confidence": 1.0, "source": "extraction"},
    LEVEL_PASS_PROMOTED:    {"confidence": 0.7, "source": "auto_promoted"},
    LEVEL_PASS_NORMALIZED:  {"confidence": 0.8, "source": "normalized"},
    LEVEL_PASS_TRUNCATED:   {"confidence": 0.9, "source": "truncated"},
    LEVEL_POOL:             {"confidence": 0.4, "source": "pool"},
}
