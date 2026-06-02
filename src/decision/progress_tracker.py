"""
进度追踪模块

检查已提交申请的审批状态，支持手动更新和未来自动抓取。
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from loguru import logger


class TrackingStrategy(ABC):
    """追踪策略抽象基类"""

    @abstractmethod
    def check_status(self, opportunity: dict) -> dict:
        """检查单个申请状态"""
        ...


class ManualTrackingStrategy(TrackingStrategy):
    """手动更新追踪策略"""

    def check_status(self, opportunity: dict) -> dict:
        """手动模式：返回当前状态，不做自动检测"""
        return {
            "current_status": opportunity.get("status", "unknown"),
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "manual",
            "message": "手动模式，需人工更新状态",
        }


class ProgressTracker:
    """进度追踪器"""

    def __init__(self, db, strategy: Optional[TrackingStrategy] = None):
        self.db = db
        self.strategy = strategy or ManualTrackingStrategy()

    def check_single(self, opportunity_id: str) -> dict:
        """
        检查单个申请状态

        Args:
            opportunity_id: 申报机会 ID

        Returns:
            状态检查结果
        """
        opp = self.db.get_opportunity(opportunity_id)
        if not opp:
            raise ValueError(f"申报机会不存在: {opportunity_id}")

        if opp["status"] not in ("submitted", "approved", "rejected"):
            raise ValueError(f"当前状态 '{opp['status']}' 不需要追踪，仅支持 submitted/approved/rejected")

        result = self.strategy.check_status(opp)
        result["opportunity_id"] = opportunity_id
        result["policy_name"] = opp.get("policy_name", "")

        logger.info(f"状态检查: {opportunity_id} → {result.get('current_status')}")
        return result

    def check_all_submitted(self, enterprise_id: Optional[str] = None) -> list[dict]:
        """
        批量检查已提交申请的状态

        Args:
            enterprise_id: 可选，限制检查某企业的申请

        Returns:
            检查结果列表
        """
        opps = self.db.list_opportunities(enterprise_id=enterprise_id, status="submitted")
        if not opps:
            return []

        results = []
        for opp in opps:
            try:
                result = self.check_single(opp["opportunity_id"])
                results.append(result)
            except Exception as e:
                logger.warning(f"检查 {opp['opportunity_id']} 失败: {e}")
                results.append({
                    "opportunity_id": opp["opportunity_id"],
                    "error": str(e),
                })

        logger.info(f"批量检查完成: {len(results)} 个申请")
        return results

    def update_status_manual(
        self,
        opportunity_id: str,
        new_status: str,
        note: str = "",
    ) -> dict:
        """
        手动更新申请状态

        Args:
            opportunity_id: 申报机会 ID
            new_status: 新状态 (approved / rejected)
            note: 备注说明
        """
        opp = self.db.update_opportunity_status(
            opportunity_id=opportunity_id,
            new_status=new_status,
            event_type="manual_update",
            note=note or f"手动更新为 {new_status}",
        )

        if not opp:
            raise ValueError(f"申报机会不存在: {opportunity_id}")

        logger.info(f"手动状态更新: {opportunity_id} → {new_status}")
        return opp

    def get_history(self, opportunity_id: str) -> list[dict]:
        """获取状态变更历史"""
        events = self.db.list_opportunity_events(opportunity_id)
        return events
