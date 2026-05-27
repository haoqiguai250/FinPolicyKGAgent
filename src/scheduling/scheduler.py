"""
智能排期引擎 — 申报优先级排序 + 日历视图

Phase 3 模块 G: 智能申报日历

排序权重:
- deadline 紧急度 (0-1, 越紧急越高)
- is_eligible (1=可申报, 0=不符合)
- estimated_amount_score (金额越大越高)
- materials_progress (完成度越高越好)
"""

import re
import json
from datetime import date, timedelta
from typing import Optional

from loguru import logger


class SmartScheduler:
    """智能申报排期引擎"""

    def __init__(self, db, neo4j_store=None):
        self.db = db
        self.neo4j_store = neo4j_store

    def schedule(self, enterprise_id: str) -> list[dict]:
        """
        为企业生成推荐申报顺序

        Args:
            enterprise_id: 企业ID

        Returns:
            排序后的申报机会列表，每个包含推荐序号 + 排序分数
        """
        opps = self.db.list_opportunities(enterprise_id=enterprise_id)

        if not opps:
            return []

        scored = []
        for opp in opps:
            score = self._compute_score(opp)
            opp["schedule_score"] = round(score, 3)
            scored.append(opp)

        # 按分数降序排列
        scored.sort(key=lambda x: x["schedule_score"], reverse=True)

        # 添加推荐序号
        for i, opp in enumerate(scored, 1):
            opp["recommendation_rank"] = i
            opp["recommendation_reason"] = self._generate_reason(opp)

        return scored

    def get_calendar_data(
        self,
        enterprise_id: str,
        month: Optional[str] = None,
    ) -> dict:
        """
        生成日历视图数据

        Args:
            enterprise_id: 企业ID
            month: 月份 (YYYY-MM), 不传则取当月

        Returns:
            日历数据：按日期分组的机会列表
        """
        opps = self.db.list_opportunities(enterprise_id=enterprise_id)

        today = date.today()
        if month:
            try:
                year, mon = int(month[:4]), int(month[5:7])
                target_start = date(year, mon, 1)
                if mon == 12:
                    target_end = date(year + 1, 1, 1) - timedelta(days=1)
                else:
                    target_end = date(year, mon + 1, 1) - timedelta(days=1)
            except (ValueError, IndexError):
                target_start = date(today.year, today.month, 1)
                target_end = None
        else:
            target_start = date(today.year, today.month, 1)
            target_end = None

        # 收集有截止日期的机会
        calendar_days = {}
        for opp in opps:
            deadline_str = opp.get("deadline", "")
            if not deadline_str or deadline_str in ("常年申报", "长期有效"):
                continue

            deadline = self._parse_date(deadline_str)
            if not deadline:
                continue

            # 如果指定了月份，只返回该月的
            if target_end and (deadline < target_start or deadline > target_end):
                continue

            day_key = deadline.isoformat()
            if day_key not in calendar_days:
                calendar_days[day_key] = []

            calendar_days[day_key].append({
                "opportunity_id": opp["opportunity_id"],
                "policy_name": opp["policy_name"],
                "status": opp["status"],
                "is_eligible": bool(opp["is_eligible"]),
                "deadline": deadline_str,
                "days_left": (deadline - today).days,
                "urgency": self._compute_urgency(deadline, today),
            })

        # 按日期排序
        sorted_days = sorted(calendar_days.items())

        return {
            "enterprise_id": enterprise_id,
            "month": month or f"{today.year}-{today.month:02d}",
            "total_deadlines": sum(len(v) for v in calendar_days.values()),
            "calendar": [
                {"date": d, "opportunities": opps_list}
                for d, opps_list in sorted_days
            ],
        }

    def _compute_score(self, opp: dict) -> float:
        """计算申报优先级分数"""
        # 1. deadline 紧急度 (0-1)
        deadline_score = 0.0
        deadline_str = opp.get("deadline", "")
        if deadline_str and deadline_str not in ("常年申报", "长期有效"):
            deadline = self._parse_date(deadline_str)
            if deadline:
                days_left = (deadline - date.today()).days
                if days_left < 0:
                    deadline_score = 0.0  # 已过期，不推荐
                elif days_left <= 7:
                    deadline_score = 1.0
                elif days_left <= 15:
                    deadline_score = 0.9
                elif days_left <= 30:
                    deadline_score = 0.7
                elif days_left <= 60:
                    deadline_score = 0.5
                elif days_left <= 90:
                    deadline_score = 0.3
                else:
                    deadline_score = 0.1
        else:
            deadline_score = 0.05  # 常年申报，不急

        # 2. 可申报性 (1 或 0)
        eligible_score = 1.0 if opp.get("is_eligible") else 0.0

        # 3. 金额评分 (0-1)
        amount_score = 0.3  # 默认
        amount_str = opp.get("estimated_amount", "")
        if amount_str:
            amount_num = self._extract_amount(amount_str)
            if amount_num is not None:
                if amount_num >= 100:
                    amount_score = 1.0
                elif amount_num >= 50:
                    amount_score = 0.8
                elif amount_num >= 10:
                    amount_score = 0.6
                else:
                    amount_score = 0.4

        # 4. 材料完成度 (0-1)
        progress = self.db.get_materials_progress(opp["opportunity_id"])
        material_score = progress["progress_pct"] / 100.0 if progress["total"] > 0 else 0.5

        # 状态权重：applying > discovered > submitted
        status_weight = {"discovered": 0.8, "applying": 1.0, "submitted": 0.5, "approved": 0.0, "rejected": 0.0}
        sw = status_weight.get(opp.get("status", "discovered"), 0.5)

        # 加权总分
        total = (
            deadline_score * 0.35 +
            eligible_score * 0.30 +
            amount_score * 0.15 +
            material_score * 0.10 +
            sw * 0.10
        )

        return total

    def _compute_urgency(self, deadline: date, today: date) -> str:
        """计算紧急程度"""
        days_left = (deadline - today).days
        if days_left < 0:
            return "overdue"
        elif days_left <= 7:
            return "high"
        elif days_left <= 30:
            return "medium"
        else:
            return "low"

    def _generate_reason(self, opp: dict) -> str:
        """生成推荐理由"""
        reasons = []
        if opp.get("is_eligible"):
            reasons.append("符合申报条件")
        else:
            reasons.append("条件不完全符合")

        deadline_str = opp.get("deadline", "")
        if deadline_str and deadline_str not in ("常年申报", "长期有效"):
            deadline = self._parse_date(deadline_str)
            if deadline:
                days_left = (deadline - date.today()).days
                if days_left < 0:
                    reasons.append("已过期")
                elif days_left <= 7:
                    reasons.append("7天内截止")
                elif days_left <= 30:
                    reasons.append("30天内截止")

        progress = self.db.get_materials_progress(opp["opportunity_id"])
        if progress["total"] > 0:
            reasons.append(f"材料完成{progress['progress_pct']:.0f}%")

        return "，".join(reasons)

    @staticmethod
    def _parse_date(date_str: str) -> Optional[date]:
        """解析日期字符串"""
        date_str = date_str.strip()
        try:
            return date.fromisoformat(date_str.replace("/", "-")[:10])
        except ValueError:
            pass
        if len(date_str) == 8 and date_str.isdigit():
            try:
                return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            except ValueError:
                pass
        m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", date_str)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_amount(amount_str: str) -> Optional[float]:
        """从金额描述中提取数值（万元）"""
        # 匹配 "最高500万元" / "给予200万" / "不超过1000万元"
        m = re.search(r"(\d+(?:\.\d+)?)\s*万", amount_str)
        if m:
            return float(m.group(1))
        # 匹配 "500元" / "1000元"
        m = re.search(r"(\d+(?:\.\d+)?)\s*元", amount_str)
        if m:
            return float(m.group(1)) / 10000  # 转万元
        # 匹配纯数字
        m = re.search(r"(\d+(?:\.\d+)?)", amount_str)
        if m:
            return float(m.group(1))
        return None
