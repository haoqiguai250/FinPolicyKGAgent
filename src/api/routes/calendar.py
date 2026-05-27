"""
日历与排期路由 — 智能申报日历 + 推荐排序

Phase 3 模块 G: 智能申报日历
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.core.logger import logger

router = APIRouter()


def _get_db():
    from src.api.server import get_db
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return db


def _get_neo4j_store():
    from src.api.server import get_neo4j_store
    store = get_neo4j_store()
    return store


@router.get("/enterprises/{enterprise_id}/schedule")
async def get_enterprise_schedule(enterprise_id: str):
    """获取企业推荐申报顺序"""
    db = _get_db()
    ent = db.get_enterprise(enterprise_id)
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    from src.scheduling.scheduler import SmartScheduler
    scheduler = SmartScheduler(db, neo4j_store=_get_neo4j_store())
    schedule = scheduler.schedule(enterprise_id)

    return {
        "enterprise_id": enterprise_id,
        "total": len(schedule),
        "schedule": schedule,
    }


@router.get("/calendar")
async def get_calendar(
    enterprise_id: str = Query(..., description="企业ID"),
    month: Optional[str] = Query(None, description="月份 YYYY-MM，不传取当月"),
):
    """获取日历视图数据"""
    db = _get_db()
    ent = db.get_enterprise(enterprise_id)
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    from src.scheduling.scheduler import SmartScheduler
    scheduler = SmartScheduler(db, neo4j_store=_get_neo4j_store())
    calendar_data = scheduler.get_calendar_data(enterprise_id, month=month)

    return calendar_data
