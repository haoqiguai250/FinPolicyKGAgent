"""
截止日期扫描与提醒

功能：
1. 扫描 Neo4j 中所有 Policy 节点的 deadline 属性
2. 根据提前天数筛选即将截止的政策
3. 支持按企业画像过滤（只提醒可申报的政策）
4. 生成提醒列表（含紧急程度）

用法:
    from src.deadline.reminder import DeadlineReminder
    reminder = DeadlineReminder(neo4j_store)
    reminders = reminder.scan(days_ahead=30)
"""

from datetime import date, timedelta
from typing import Optional

from loguru import logger


class DeadlineReminder:
    """截止日期扫描与提醒"""

    def __init__(self, neo4j_store=None):
        self.neo4j_store = neo4j_store

    def scan(self, days_ahead: int = 30, region: str | None = None) -> list[dict]:
        """
        扫描即将截止的政策

        Args:
            days_ahead: 提前多少天提醒（默认30天）
            region: 可选，按地区过滤

        Returns:
            [{"policy_name", "deadline", "days_left", "urgency",
              "application_platform", "application_platform_url", "contact_department"}, ...]
        """
        if not self.neo4j_store:
            logger.warning("Neo4j 未连接，无法扫描截止日期")
            return []

        policies = self._fetch_policies_with_deadline(region)
        if not policies:
            return []

        today = date.today()
        cutoff = today + timedelta(days=days_ahead)
        reminders = []

        for p in policies:
            deadline_str = p.get("deadline", "")
            if not deadline_str or deadline_str in ("常年申报", "长期有效"):
                continue

            deadline = self._parse_date(deadline_str)
            if not deadline:
                continue

            if today <= deadline <= cutoff:
                days_left = (deadline - today).days
                reminders.append({
                    "policy_name": p.get("policy_name", ""),
                    "deadline": deadline.isoformat(),
                    "days_left": days_left,
                    "urgency": "high" if days_left <= 7 else "medium" if days_left <= 15 else "low",
                    "application_platform": p.get("application_platform", ""),
                    "application_platform_url": p.get("application_platform_url", ""),
                    "contact_department": p.get("contact_department", ""),
                })

        reminders.sort(key=lambda r: r["days_left"])
        logger.info(f"截止日期扫描完成: {len(reminders)}/{len(policies)} 条政策即将截止（{days_ahead}天内）")
        return reminders

    def _fetch_policies_with_deadline(self, region: str | None = None) -> list[dict]:
        """从 Neo4j 获取有 deadline 属性的 Policy"""
        try:
            with self.neo4j_store.driver.session(database=self.neo4j_store.database) as session:
                if region:
                    query = """
                    MATCH (p:Policy)-[:has_eligibility]->(c:Condition)
                    WHERE p.deadline IS NOT NULL AND c.name CONTAINS $region
                    RETURN p.name AS policy_name, p.deadline AS deadline,
                           p.application_platform AS application_platform,
                           p.application_platform_url AS application_platform_url,
                           p.contact_department AS contact_department
                    """
                    result = session.run(query, region=region)
                else:
                    query = """
                    MATCH (p:Policy)
                    WHERE p.deadline IS NOT NULL
                    RETURN p.name AS policy_name, p.deadline AS deadline,
                           p.application_platform AS application_platform,
                           p.application_platform_url AS application_platform_url,
                           p.contact_department AS contact_department
                    """
                    result = session.run(query)

                return [dict(record) for record in result]
        except Exception as e:
            logger.warning(f"查询 Policy deadline 失败: {e}")
            return []

    @staticmethod
    def _parse_date(date_str: str) -> Optional[date]:
        """解析日期字符串，支持多种格式"""
        date_str = date_str.strip()

        # YYYY-MM-DD / YYYY/MM/DD
        try:
            return date.fromisoformat(date_str.replace("/", "-")[:10])
        except ValueError:
            pass

        # YYYYMMDD
        if len(date_str) == 8 and date_str.isdigit():
            try:
                return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            except ValueError:
                pass

        # YYYY年MM月DD日
        import re
        m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", date_str)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        return None
