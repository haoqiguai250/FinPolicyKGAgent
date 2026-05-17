"""
解释生成器

基于 Perturbator 的节点级扰动分析报告，生成结构化解释

适配 KG-PQAM 量化评分：
- ranked_perturbations 含 metric_scores（4 指标分解）
- 详细文本中展示各节点的重要性和原因
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
    """解释生成器：节点级扰动报告 → 结构化解释"""

    def generate(self, report: PerturbationReport) -> Explanation:
        """
        从扰动报告生成结构化解释

        Args:
            report: 扰动分析报告（ranked_perturbations）

        Returns:
            Explanation
        """
        if not report.ranked_perturbations:
            return Explanation(
                summary="无法生成解释（无扰动数据）",
                key_factors=[],
                detail_text="",
            )

        # 分类节点
        critical = [n for n in report.ranked_perturbations if n["importance"] > 0.7]
        important = [n for n in report.ranked_perturbations if 0.3 < n["importance"] <= 0.7]
        minor = [n for n in report.ranked_perturbations if n["importance"] <= 0.3]

        # 生成摘要
        summary = self._generate_summary(critical, important, minor)

        # 生成详细文本
        detail = self._generate_detail(critical, important, minor)

        return Explanation(
            summary=summary,
            key_factors=report.ranked_perturbations,
            detail_text=detail,
        )

    def generate_no_match(self, available_policies: list[str] | None = None) -> Explanation:
        """
        KG 未匹配政策时生成友好提示

        Args:
            available_policies: 当前 KG 中已有的政策列表（用于推荐）

        Returns:
            Explanation（结构化友好提示）
        """
        summary = "当前知识图谱中未找到与您需求匹配的政策。以下建议由 LLM 直接生成，仅供参考。"

        detail_lines = [
            "⚠️ 未匹配到相关政策",
            "",
            "可能的原因：",
            "  1. 您的查询条件与知识图谱中的政策适用条件不匹配",
            "  2. 当前知识图谱尚未收录相关领域的政策",
            "  3. 查询表述可以更具体（如指定地区、行业、企业类型）",
        ]

        if available_policies:
            detail_lines.append("")
            detail_lines.append(f"📌 当前知识图谱中已收录 {len(available_policies)} 个政策：")
            for p in available_policies[:10]:
                detail_lines.append(f"  • {p}")
            if len(available_policies) > 10:
                detail_lines.append(f"  ... 等共 {len(available_policies)} 个")

        return Explanation(
            summary=summary,
            key_factors=[],
            detail_text="\n".join(detail_lines),
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
            names = [n.get("display", "未知") for n in critical[:3]]
            parts.append(f"最关键的节点是{'、'.join(names)}")
        if important:
            names = [n.get("display", "未知") for n in important[:3]]
            parts.append(f"重要的补充节点包括{'、'.join(names)}")
        if minor:
            parts.append(f"另有 {len(minor)} 个次要节点")

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
            lines.append("【关键节点】")
            for n in critical:
                display = n.get("display", "未知")
                importance = n.get("importance", 0)
                reason = n.get("reason", "")
                lines.append(f"  • {display}: 重要性 {importance:.2%} — {reason}")

        if important:
            lines.append("【重要节点】")
            for n in important:
                display = n.get("display", "未知")
                importance = n.get("importance", 0)
                reason = n.get("reason", "")
                lines.append(f"  • {display}: 重要性 {importance:.2%} — {reason}")

        if minor:
            lines.append(f"【次要节点】({len(minor)} 个)")
            for n in minor[:5]:  # 最多展示5个
                display = n.get("display", "未知")
                importance = n.get("importance", 0)
                lines.append(f"  • {display}: 重要性 {importance:.2%}")
            if len(minor) > 5:
                lines.append(f"  ... 等共 {len(minor)} 个")

        return "\n".join(lines)


def _format_metrics(metric: dict) -> str:
    """格式化 KG-PQAM 4 指标分解"""
    if not metric:
        return ""
    parts = []

    char_diff = metric.get("char_overlap_diff")
    entity_diff = metric.get("entity_retention_diff")
    keyword_diff = metric.get("keyword_coverage_diff")
    llm_score = metric.get("llm_semantic_score")
    weights = metric.get("weights", {})

    if char_diff is not None:
        w = weights.get("char_overlap", 0.10)
        parts.append(f"Δ字符重叠={char_diff:.2%}(×{w:.0%})")
    if entity_diff is not None:
        w = weights.get("entity_retention", 0.30)
        parts.append(f"Δ实体保留={entity_diff:.2%}(×{w:.0%})")
    if keyword_diff is not None:
        w = weights.get("keyword_coverage", 0.30)
        parts.append(f"Δ关键词覆盖={keyword_diff:.2%}(×{w:.0%})")
    if llm_score is not None:
        w = weights.get("llm_semantic", 0.30)
        parts.append(f"LLM语义={llm_score:.2%}(×{w:.0%})")
    elif weights.get("fallback"):
        parts.append("LLM语义=未评分(fallback)")

    if parts:
        return f"    [{', '.join(parts)}]"
    return ""
