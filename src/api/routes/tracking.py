"""
进度追踪路由 — 状态检查 + 手动更新 + 历史
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.core.logger import logger

router = APIRouter()


class ManualUpdateRequest(BaseModel):
    """手动状态更新请求"""
    new_status: str  # approved / rejected
    note: str = ""


class BatchCheckRequest(BaseModel):
    """批量检查请求"""
    enterprise_id: Optional[str] = None


def _get_db():
    from src.api.server import get_db
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return db


@router.post("/opportunities/{opportunity_id}/track")
async def check_single_status(opportunity_id: str):
    """检查单个申请的审批状态"""
    db = _get_db()

    from src.decision.progress_tracker import ProgressTracker
    tracker = ProgressTracker(db)

    try:
        result = tracker.check_single(opportunity_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/track/batch")
async def batch_check_status(req: BatchCheckRequest):
    """批量检查已提交申请的状态"""
    db = _get_db()

    from src.decision.progress_tracker import ProgressTracker
    tracker = ProgressTracker(db)

    results = tracker.check_all_submitted(enterprise_id=req.enterprise_id)
    return {
        "total": len(results),
        "results": results,
    }


@router.get("/track/history/{opportunity_id}")
async def get_tracking_history(opportunity_id: str):
    """获取状态变更历史（复用 opportunity_events）"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")

    events = db.list_opportunity_events(opportunity_id)
    return {
        "opportunity_id": opportunity_id,
        "policy_name": opp["policy_name"],
        "current_status": opp["status"],
        "events": events,
    }


@router.post("/opportunities/{opportunity_id}/track/manual")
async def manual_status_update(opportunity_id: str, req: ManualUpdateRequest):
    """手动更新申请状态"""
    db = _get_db()

    from src.decision.progress_tracker import ProgressTracker
    tracker = ProgressTracker(db)

    try:
        result = tracker.update_status_manual(
            opportunity_id=opportunity_id,
            new_status=req.new_status,
            note=req.note,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
