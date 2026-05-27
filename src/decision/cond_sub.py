"""
条件子节点（CondSub）与条件定义（CondDef）

CondSub：一个可执行的原子条件（field + operator + value），用于 EligibilityEngine 逐条核验
CondDef：一个描述性条件到 CondSub 的映射定义，预置在 KG 中
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CondOp(str, Enum):
    """条件运算符"""
    EQ = "=="          # 等于
    NEQ = "!="         # 不等于
    GT = ">"           # 大于
    GTE = ">="         # 大于等于
    LT = "<"           # 小于
    LTE = "<="         # 小于等于
    IN = "in"          # 属于（列表）
    NOT_IN = "not_in"  # 不属于
    CONTAINS = "contains"  # 包含（子字符串/元素）
    YEARS_SINCE = "years_since"  # 距今年数（用于 established_date）


@dataclass
class CondSub:
    """
    原子条件 — 可执行的比对指令

    示例：
        CondSub(field="annual_revenue", op=CondOp.GTE, value=500, is_hard=True)
        → 年营收 >= 500万

        CondSub(field="industry", op=CondOp.IN, value=["人工智能","物联网"], is_hard=True)
        → 行业属于 [人工智能, 物联网]
    """
    field: str                           # 画像字段名（对应 EnterpriseProfile 属性）
    op: CondOp                           # 运算符
    value: Any                           # 比对值
    is_hard: bool = True                 # 硬条件（fail→排除）/ 软条件（fail→降权）
    description: str = ""                # 人类可读描述
    source: str = ""                     # 来源（如"工信部联企业〔2011〕300号"）

    def evaluate(self, profile_value: Any) -> CondSubResult:
        """
        执行条件核验

        Args:
            profile_value: 企业画像中对应字段的值

        Returns:
            CondSubResult（pass/fail/unknown）
        """
        # 画像值为 None → unknown（无法判定）
        if profile_value is None:
            return CondSubResult(
                status="unknown",
                actual=profile_value,
                expected=self._format_expected(),
                reason=f"画像缺少 {self.field} 字段",
            )

        # 执行比对
        try:
            passed = self._compare(profile_value)
        except Exception as e:
            return CondSubResult(
                status="unknown",
                actual=profile_value,
                expected=self._format_expected(),
                reason=f"比对异常: {e}",
            )

        if passed:
            return CondSubResult(
                status="pass",
                actual=profile_value,
                expected=self._format_expected(),
                reason="满足条件",
            )
        else:
            return CondSubResult(
                status="fail",
                actual=profile_value,
                expected=self._format_expected(),
                reason=f"不满足: {self._format_expected()}，实际值: {profile_value}",
            )

    def _compare(self, profile_value: Any) -> bool:
        """执行具体比对逻辑"""
        if self.op == CondOp.EQ:
            return profile_value == self.value
        elif self.op == CondOp.NEQ:
            return profile_value != self.value
        elif self.op == CondOp.GT:
            return profile_value > self.value
        elif self.op == CondOp.GTE:
            return profile_value >= self.value
        elif self.op == CondOp.LT:
            return profile_value < self.value
        elif self.op == CondOp.LTE:
            return profile_value <= self.value
        elif self.op == CondOp.IN:
            if self.field == "region":
                return self._region_match(profile_value, self.value)
            return profile_value in self.value
        elif self.op == CondOp.NOT_IN:
            if self.field == "region":
                return not self._region_match(profile_value, self.value)
            return profile_value not in self.value
        elif self.op == CondOp.CONTAINS:
            if isinstance(profile_value, list):
                return self.value in profile_value
            return self.value in str(profile_value)
        elif self.op == CondOp.YEARS_SINCE:
            # value 是年数阈值，profile_value 是年数（float）
            return profile_value >= self.value
        else:
            raise ValueError(f"未知运算符: {self.op}")

    @staticmethod
    def _region_match(profile_region: str, allowed_regions: list[str]) -> bool:
        """
        region 模糊匹配：支持子串包含和"市/区"后缀变体

        例：profile_region="深圳市南山区" 匹配 allowed 中的 "深圳"、"深圳南山"、"南山区"
        """
        if profile_region in allowed_regions:
            return True
        # 反向检查：allowed 中的值是否是 profile_value 的子串
        for allowed in allowed_regions:
            if allowed in profile_region:
                return True
        # 正向检查：profile_value 是否是 allowed 的子串
        for allowed in allowed_regions:
            if profile_region in allowed:
                return True
        return False

    def _format_expected(self) -> str:
        """生成人类可读的期望值描述"""
        op_map = {
            CondOp.EQ: "=", CondOp.NEQ: "≠",
            CondOp.GT: ">", CondOp.GTE: "≥",
            CondOp.LT: "<", CondOp.LTE: "≤",
            CondOp.IN: "∈", CondOp.NOT_IN: "∉",
            CondOp.CONTAINS: "包含",
            CondOp.YEARS_SINCE: "≥",
        }
        op_str = op_map.get(self.op, str(self.op))
        val_str = str(self.value) if not isinstance(self.value, list) else "/".join(self.value[:5])
        return f"{self.field} {op_str} {val_str}"

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "op": self.op.value,
            "value": self.value,
            "is_hard": self.is_hard,
            "description": self.description,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CondSub:
        return cls(
            field=data["field"],
            op=CondOp(data["op"]),
            value=data["value"],
            is_hard=data.get("is_hard", True),
            description=data.get("description", ""),
            source=data.get("source", ""),
        )


@dataclass
class CondSubResult:
    """条件核验结果"""
    status: str          # "pass" / "fail" / "unknown"
    actual: Any          # 画像实际值
    expected: str        # 期望值描述
    reason: str          # 原因说明

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "actual": self.actual,
            "expected": self.expected,
            "reason": self.reason,
        }


@dataclass
class CondDef:
    """
    条件定义 — 将描述性条件映射为一组 CondSub

    示例：
        CondDef(
            condition_text="中小微企业",
            category="company_type",
            sub_conditions=[
                CondSub(field="annual_revenue", op=CondOp.LT, value=2000, ...),
                CondSub(field="employees", op=CondOp.LT, value=300, ...),
            ],
        )
    """
    condition_text: str                         # 原文条件描述（如"中小微企业"）
    category: str                               # 条件类别（region/industry/qualification/...）
    sub_conditions: list[CondSub] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)  # 同义表达（如["中小企业","小微企业"]）

    def expand(self) -> list[CondSub]:
        """展开为原子条件列表"""
        return self.sub_conditions

    def to_dict(self) -> dict:
        return {
            "condition_text": self.condition_text,
            "category": self.category,
            "sub_conditions": [cs.to_dict() for cs in self.sub_conditions],
            "aliases": self.aliases,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CondDef:
        return cls(
            condition_text=data["condition_text"],
            category=data["category"],
            sub_conditions=[CondSub.from_dict(cs) for cs in data.get("sub_conditions", [])],
            aliases=data.get("aliases", []),
        )
