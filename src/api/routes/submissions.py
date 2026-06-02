"""
申报提交路由 — 准备申报包 + 确认提交
"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.logger import logger

router = APIRouter()


class PrepareRequest(BaseModel):
    """准备申报包请求"""
    pass


class ConfirmRequest(BaseModel):
    """确认提交请求"""
    confirmed_by: str = ""  # 确认人


def _get_db():
    from src.api.server import get_db
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return db


@router.post("/opportunities/{opportunity_id}/submit/prepare")
async def prepare_submission(opportunity_id: str, req: PrepareRequest):
    """准备申报包（校验材料 → 冻结快照）"""
    db = _get_db()

    from src.decision.submission_engine import SubmissionEngine
    engine = SubmissionEngine(db)

    try:
        package = engine.prepare_submission(opportunity_id)
        # 解析 JSON 字段
        for key in ("materials_checklist_json", "documents_json"):
            if key in package and isinstance(package[key], str):
                try:
                    package[key] = json.loads(package[key])
                except (json.JSONDecodeError, TypeError):
                    package[key] = []
        for key in ("profile_snapshot_json", "policy_snapshot_json"):
            if key in package and isinstance(package[key], str):
                try:
                    package[key] = json.loads(package[key])
                except (json.JSONDecodeError, TypeError):
                    package[key] = {}
        return package
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/opportunities/{opportunity_id}/submit/confirm")
async def confirm_submission(opportunity_id: str, req: ConfirmRequest):
    """人工确认提交"""
    db = _get_db()

    from src.decision.submission_engine import SubmissionEngine
    engine = SubmissionEngine(db)

    try:
        result = engine.execute_submission(
            opportunity_id=opportunity_id,
            confirmed_by=req.confirmed_by,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/opportunities/{opportunity_id}/submit/package")
async def get_submission_package(opportunity_id: str):
    """查看申报包详情"""
    db = _get_db()
    package = db.get_submission_package(opportunity_id)
    if not package:
        raise HTTPException(status_code=404, detail="申报包不存在，请先准备申报包")

    # 解析 JSON 字段
    for key in ("materials_checklist_json", "documents_json"):
        if key in package and isinstance(package[key], str):
            try:
                package[key] = json.loads(package[key])
            except (json.JSONDecodeError, TypeError):
                package[key] = []
    for key in ("profile_snapshot_json", "policy_snapshot_json"):
        if key in package and isinstance(package[key], str):
            try:
                package[key] = json.loads(package[key])
            except (json.JSONDecodeError, TypeError):
                package[key] = {}

    return package
