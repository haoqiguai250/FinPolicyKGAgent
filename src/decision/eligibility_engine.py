"""
EligibilityEngine — 条件执行核验引擎

输入：企业画像 + KG 展开的原子条件列表（CondSub）
输出：逐条核验结果（pass/fail/unknown）+ 综合判定（is_eligible）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from src.decision.cond_sub import CondSub, CondSubResult
from src.decision.intent_recognizer import EnterpriseProfile
from src.decision.cond_def import expand_condition


@dataclass
class EligibilityCheck:
    """单条条件的核验结果"""
    condition_text: str                    # 原始条件描述
    status: str                            # "pass" / "fail" / "unknown"
    is_hard: bool                          # 硬/软条件
    sub_results: list[CondSubResult] = field(default_factory=list)  # 子条件核验详情
    reason: str = ""                       # 综合原因

    def to_dict(self) -> dict:
        return {
            "condition_text": self.condition_text,
            "status": self.status,
            "is_hard": self.is_hard,
            "sub_results": [sr.to_dict() for sr in self.sub_results],
            "reason": self.reason,
        }


@dataclass
class EligibilityResult:
    """一个政策的完整核验结果"""
    policy_name: str
    policy_id: str = ""
    is_eligible: bool = False              # 硬条件全部通过
    hard_pass_count: int = 0
    hard_fail_count: int = 0
    soft_pass_count: int = 0
    soft_fail_count: int = 0
    unknown_count: int = 0
    checks: list[EligibilityCheck] = field(default_factory=list)
    failed_hard_conditions: list[str] = field(default_factory=list)   # 硬条件失败项
    missing_fields: list[str] = field(default_factory=list)           # 缺失画像字段
    soft_score: float = 0.0               # 软条件通过率 0~1

    def to_dict(self) -> dict:
        return {
            "policy_name": self.policy_name,
            "policy_id": self.policy_id,
            "is_eligible": self.is_eligible,
            "hard_pass_count": self.hard_pass_count,
            "hard_fail_count": self.hard_fail_count,
            "soft_pass_count": self.soft_pass_count,
            "soft_fail_count": self.soft_fail_count,
            "unknown_count": self.unknown_count,
            "checks": [c.to_dict() for c in self.checks],
            "failed_hard_conditions": self.failed_hard_conditions,
            "missing_fields": self.missing_fields,
            "soft_score": self.soft_score,
        }


class EligibilityEngine:
    """
    条件执行核验引擎

    工作流程：
    1. 接收政策条件列表（Condition 文本）
    2. 每个条件调用 cond_def.expand_condition() 展开为 CondSub
    3. 逐个 CondSub 与企业画像比对
    4. 综合判定：硬条件全 pass → is_eligible=true
    """

    def __init__(self, profile: EnterpriseProfile, neo4j_store=None):
        self.profile = profile
        self._profile_dict = profile.to_dict()
        self._neo4j_store = neo4j_store
        # 预计算 established_date 的年数
        self._years_since_established = profile.get_years_since_established()

    def check_policy(
        self,
        policy_name: str,
        policy_id: str,
        conditions: list[str],
    ) -> EligibilityResult:
        """
        对一个政策执行完整核验

        Args:
            policy_name: 政策名称
            policy_id: 政策 ID
            conditions: 条件文本列表（如["中小微企业","深圳注册企业","年营收500万以上"]）

        Returns:
            EligibilityResult
        """
        result = EligibilityResult(
            policy_name=policy_name,
            policy_id=policy_id,
        )

        for cond_text in conditions:
            check = self._check_condition(cond_text)
            result.checks.append(check)

            # 统计
            if check.status == "pass":
                if check.is_hard:
                    result.hard_pass_count += 1
                else:
                    result.soft_pass_count += 1
            elif check.status == "fail":
                if check.is_hard:
                    result.hard_fail_count += 1
                    result.failed_hard_conditions.append(cond_text)
                else:
                    result.soft_fail_count += 1
            else:  # unknown
                result.unknown_count += 1
                # 收集缺失字段
                for sr in check.sub_results:
                    if sr.status == "unknown" and sr.reason:
                        field_name = sr.reason.replace("画像缺少 ", "").replace(" 字段", "")
                        if field_name not in result.missing_fields:
                            result.missing_fields.append(field_name)

        # 综合判定：硬条件全 pass
        result.is_eligible = result.hard_fail_count == 0

        # 软条件通过率
        total_soft = result.soft_pass_count + result.soft_fail_count
        if total_soft > 0:
            result.soft_score = result.soft_pass_count / total_soft
        else:
            result.soft_score = 1.0  # 没有软条件，默认满分

        logger.info(
            f"核验 {policy_name}: "
            f"eligible={result.is_eligible}, "
            f"hard={result.hard_pass_count}P/{result.hard_fail_count}F, "
            f"soft={result.soft_pass_count}P/{result.soft_fail_count}F, "
            f"unknown={result.unknown_count}"
        )

        return result

    def _check_condition(self, cond_text: str) -> EligibilityCheck:
        """
        核验单个条件

        Args:
            cond_text: 条件文本（如"中小微企业"）

        Returns:
            EligibilityCheck
        """
        # 展开条件（KG-first，传入 neo4j_store）
        cond_subs = expand_condition(cond_text, neo4j_store=self._neo4j_store)

        if not cond_subs:
            # 没有预置定义 → unknown
            return EligibilityCheck(
                condition_text=cond_text,
                status="unknown",
                is_hard=True,
                reason=f"条件\"{cond_text}\"无预置定义，无法核验",
            )

        # 对每个 CondSub 执行核验
        sub_results: list[CondSubResult] = []
        for cs in cond_subs:
            profile_value = self._get_profile_value(cs.field, cs.op)
            sr = cs.evaluate(profile_value)
            sub_results.append(sr)

        # 判定逻辑：
        # 硬条件 CondSub 全 pass → pass
        # 任一硬条件 fail → fail
        # 有 unknown 且无 fail → unknown
        # 软条件只影响 soft_score，不影响 pass/fail
        is_hard = any(cs.is_hard for cs in cond_subs)

        hard_results = [sr for cs, sr in zip(cond_subs, sub_results) if cs.is_hard]
        soft_results = [sr for cs, sr in zip(cond_subs, sub_results) if not cs.is_hard]

        if hard_results:
            hard_fails = sum(1 for sr in hard_results if sr.status == "fail")
            hard_unknowns = sum(1 for sr in hard_results if sr.status == "unknown")

            if hard_fails > 0:
                status = "fail"
                reason = f"硬条件不满足: " + "; ".join(
                    sr.reason for sr in hard_results if sr.status == "fail"
                )
            elif hard_unknowns > 0:
                status = "unknown"
                reason = f"硬条件无法判定: " + "; ".join(
                    sr.reason for sr in hard_results if sr.status == "unknown"
                )
            else:
                status = "pass"
                reason = "硬条件全部满足"
        else:
            # 纯软条件
            soft_fails = sum(1 for sr in soft_results if sr.status == "fail")
            if soft_fails > 0:
                status = "fail"
                reason = f"软条件不满足: " + "; ".join(
                    sr.reason for sr in soft_results if sr.status == "fail"
                )
            elif any(sr.status == "unknown" for sr in soft_results):
                status = "unknown"
                reason = "软条件无法判定"
            else:
                status = "pass"
                reason = "条件全部满足"

        return EligibilityCheck(
            condition_text=cond_text,
            status=status,
            is_hard=is_hard,
            sub_results=sub_results,
            reason=reason,
        )

    def _get_profile_value(self, field_name: str, op: CondOp) -> Any:
        """
        从画像中获取对应字段的值

        对于 YEARS_SINCE 运算符，返回已计算的年数而非原始日期
        """
        if op.value == "years_since":
            return self._years_since_established

        return self._profile_dict.get(field_name)
