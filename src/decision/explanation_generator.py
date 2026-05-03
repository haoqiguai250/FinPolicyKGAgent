"""
解释生成器

基于 Perturbator 的扰动分析报告，生成结构化解释
"""

from dataclasses import dataclass

from loguru import logger

from src.decision.perturbator import PerturbationReport


@dataclass
class Explanation:
    """结构化解释"""
    summary: str                          # 总体摘要
    key_factors: list[dict]               # 关键因素（排序后）
    detail_text: str                      # 详细解释文本

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "key_factors": self.key_factors,
            "detail_text": self.detail_text,
        }


class ExplanationGenerator:
    """解释生成器：扰动报告 → 结构化解释"""

    def generate(self, report: PerturbationReport) -> Explanation:
        """
        从扰动报告生成结构化解释

        Args:
            report: 扰动分析报告

        Returns:
            Explanation
        """
        if not report.ranked_nodes:
            return Explanation(
                summary="无法生成解释（无扰动数据）",
                key_factors=[],
                detail_text="",
            )

        # 分类节点
        critical = [n for n in report.ranked_nodes if n["importance"] > 0.7]
        important = [n for n in report.ranked_nodes if 0.3 < n["importance"] <= 0.7]
        minor = [n for n in report.ranked_nodes if n["importance"] <= 0.3]

        # 生成摘要
        summary = self._generate_summary(critical, important, minor)

        # 生成详细文本
        detail = self._generate_detail(critical, important, minor)

        return Explanation(
            summary=summary,
            key_factors=report.ranked_nodes,
            detail_text=detail,
        )

    @staticmethod
    def _generate_summary(
        critical: list[dict],
        important: list[dict],
        minor: list[dict],
    ) -> str:
        """生成总体摘要"""
        parts = []

        if critical:
            names = [f"{n['type']}({n['name']})" for n in critical[:3]]
            parts.append(f"最关键的因素是{'、'.join(names)}")
        if important:
            names = [f"{n['type']}({n['name']})" for n in important[:3]]
            parts.append(f"重要的补充因素包括{'、'.join(names)}")
        if minor:
            parts.append(f"另有 {len(minor)} 个次要因素")

        return "。".join(parts) + "。" if parts else "无显著影响因素。"

    @staticmethod
    def _generate_detail(
        critical: list[dict],
        important: list[dict],
        minor: list[dict],
    ) -> str:
        """生成详细解释"""
        lines = []

        if critical:
            lines.append("【关键因素】")
            for n in critical:
                lines.append(f"  • {n['type']}({n['name']}): 重要性 {n['importance']:.0%} — {n['description']}")

        if important:
            lines.append("【重要因素】")
            for n in important:
                lines.append(f"  • {n['type']}({n['name']}): 重要性 {n['importance']:.0%} — {n['description']}")

        if minor:
            lines.append(f"【次要因素】({len(minor)} 个)")
            for n in minor[:5]:  # 最多展示5个
                lines.append(f"  • {n['type']}({n['name']}): 重要性 {n['importance']:.0%}")
            if len(minor) > 5:
                lines.append(f"  ... 等共 {len(minor)} 个")

        return "\n".join(lines)
