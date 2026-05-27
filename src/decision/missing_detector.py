"""
MissingInfoDetector — 缺失信息检测器

扫描 EligibilityResult，收集所有 unknown 状态对应的缺失画像字段，
生成用户友好的提示信息。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.decision.eligibility_engine import EligibilityResult


# 字段名 → 中文提示映射
FIELD_LABELS: dict[str, str] = {
    "region": "企业所在地区",
    "company_type": "企业类型",
    "industry": "所属行业",
    "employees": "员工人数",
    "annual_revenue": "年营收（万元）",
    "established_date": "成立时间",
    "is_high_tech": "是否高新技术企业",
    "is_sme": "是否中小微企业",
    "patents": "专利/知识产权数量",
    "qualifications": "资质列表",
    "registered_capital": "注册资本（万元）",
    "rd_ratio": "研发费用占比（%）",
    "target_subsidy": "目标补贴类型",
}


@dataclass
class MissingField:
    """缺失字段信息"""
    field_name: str              # 字段名
    label: str                   # 中文标签
    affected_policies: int = 0   # 影响的政策数量
    priority: str = "medium"     # high/medium/low

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "label": self.label,
            "affected_policies": self.affected_policies,
            "priority": self.priority,
        }


@dataclass
class MissingInfoReport:
    """缺失信息报告"""
    total_policies_checked: int = 0
    policies_with_unknowns: int = 0
    missing_fields: list[MissingField] = field(default_factory=list)
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "total_policies_checked": self.total_policies_checked,
            "policies_with_unknowns": self.policies_with_unknowns,
            "missing_fields": [mf.to_dict() for mf in self.missing_fields],
            "suggestion": self.suggestion,
        }


class MissingInfoDetector:
    """
    缺失信息检测器

    从多个 EligibilityResult 中汇总缺失字段，生成补全建议
    """

    def detect(self, results: list[EligibilityResult]) -> MissingInfoReport:
        """
        检测缺失信息

        Args:
            results: 多个政策的核验结果

        Returns:
            MissingInfoReport
        """
        report = MissingInfoReport()
        report.total_policies_checked = len(results)

        # 统计每个缺失字段影响的政策数
        field_affected_count: dict[str, int] = {}

        for r in results:
            if r.unknown_count > 0:
                report.policies_with_unknowns += 1

            for field_name in r.missing_fields:
                field_affected_count[field_name] = field_affected_count.get(field_name, 0) + 1

        # 构建缺失字段列表，按影响政策数排序
        for field_name, count in sorted(field_affected_count.items(), key=lambda x: -x[1]):
            label = FIELD_LABELS.get(field_name, field_name)

            # 优先级判定
            if count >= 3:
                priority = "high"
            elif count >= 1:
                priority = "medium"
            else:
                priority = "low"

            report.missing_fields.append(MissingField(
                field_name=field_name,
                label=label,
                affected_policies=count,
                priority=priority,
            ))

        # 生成建议文案
        if report.missing_fields:
            high_fields = [f.label for f in report.missing_fields if f.priority == "high"]
            medium_fields = [f.label for f in report.missing_fields if f.priority == "medium"]

            parts = []
            if high_fields:
                parts.append(f"强烈建议补充：{', '.join(high_fields)}")
            if medium_fields:
                parts.append(f"建议补充：{', '.join(medium_fields)}")

            report.suggestion = "。".join(parts) + "。补充后可提高政策匹配准确率。"
        else:
            report.suggestion = "企业画像信息完整，无需补充。"

        return report
