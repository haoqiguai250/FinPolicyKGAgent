"""申报机会路由 — Opportunity 持久化 + 状态机 + 时间线"""

import hashlib
import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.models import ApplicationOpportunity, EligibilityCheckBrief
from src.core.logger import logger

router = APIRouter()


class StatusUpdate(BaseModel):
    """状态推进请求"""
    new_status: str  # applying / submitted / approved / rejected
    note: str = ""


class OpportunityRefresh(BaseModel):
    """重核验请求"""
    pass


class CreateOpportunityRequest(BaseModel):
    """轻量创建 Opportunity（演示模式用）"""
    enterprise_id: str
    policy_name: str
    estimated_amount: str = ""
    department: str = ""
    deadline: str = ""


def _get_db():
    """获取 Database 单例，不可用时抛 503"""
    from src.api.server import get_db
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return db


@router.get("/opportunities")
async def list_opportunities(
    enterprise_id: Optional[str] = Query(None, description="企业ID"),
    status: Optional[str] = Query(None, description="状态筛选"),
):
    """按条件筛选申报机会列表"""
    db = _get_db()
    opps = db.list_opportunities(enterprise_id=enterprise_id, status=status)
    # 解析 JSON 字段
    for opp in opps:
        for key in ("eligibility_checks_json", "required_materials_json", "application_steps_json"):
            if key in opp and isinstance(opp[key], str):
                try:
                    opp[key] = json.loads(opp[key])
                except (json.JSONDecodeError, TypeError):
                    opp[key] = []
    return {"total": len(opps), "opportunities": opps}


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(opportunity_id: str):
    """获取单个申报机会详情"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")
    for key in ("eligibility_checks_json", "required_materials_json", "application_steps_json"):
        if key in opp and isinstance(opp[key], str):
            try:
                opp[key] = json.loads(opp[key])
            except (json.JSONDecodeError, TypeError):
                opp[key] = []
    return opp


@router.patch("/opportunities/{opportunity_id}/status")
async def update_opportunity_status(opportunity_id: str, req: StatusUpdate):
    """推进申报机会状态（discovered→applying→submitted→approved/rejected）"""
    db = _get_db()
    try:
        opp = db.update_opportunity_status(
            opportunity_id=opportunity_id,
            new_status=req.new_status,
            note=req.note,
        )
        if not opp:
            raise HTTPException(status_code=404, detail="申报机会不存在")
        return opp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/opportunities/{opportunity_id}/timeline")
async def get_opportunity_timeline(opportunity_id: str):
    """获取申报机会操作时间线"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")
    events = db.list_opportunity_events(opportunity_id)
    return {"opportunity_id": opportunity_id, "policy_name": opp["policy_name"], "events": events}


@router.post("/opportunities/{opportunity_id}/refresh")
async def refresh_opportunity(opportunity_id: str):
    """重新核验申报机会（画像变更后）"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")

    from src.api.server import get_advisor, get_neo4j_store
    advisor = get_advisor()
    if not advisor:
        raise HTTPException(status_code=503, detail="Advisor 未初始化")

    # 读取企业画像
    profile_data = db.get_enterprise_profile(opp["enterprise_id"])
    if not profile_data:
        raise HTTPException(status_code=400, detail="企业画像为空，无法核验")

    from src.decision.intent_recognizer import EnterpriseProfile
    profile = EnterpriseProfile(**{k: v for k, v in profile_data.items() if v is not None})

    # 重新核验
    from src.decision.eligibility_engine import EligibilityEngine
    engine = EligibilityEngine(profile, neo4j_store=get_neo4j_store())
    cond_texts = advisor.retriever.get_policy_condition_texts(opp["policy_name"])
    elig_result = engine.check_policy(
        policy_name=opp["policy_name"],
        policy_id=opp["policy_name"],
        conditions=cond_texts,
    )

    # 更新核验结果（不覆盖 status）
    db.upsert_opportunity({
        "opportunity_id": opportunity_id,
        "enterprise_id": opp["enterprise_id"],
        "policy_name": opp["policy_name"],
        "is_eligible": 1 if elig_result.is_eligible else 0,
        "eligibility_checks_json": json.dumps(
            [c.to_dict() if hasattr(c, "to_dict") else c.__dict__ for c in elig_result.checks],
            ensure_ascii=False,
        ),
        "hard_pass_count": elig_result.hard_pass_count,
        "hard_fail_count": elig_result.hard_fail_count,
        "soft_pass_count": elig_result.soft_pass_count,
        "unknown_count": elig_result.unknown_count,
    })

    return {
        "opportunity_id": opportunity_id,
        "is_eligible": elig_result.is_eligible,
        "hard_pass_count": elig_result.hard_pass_count,
        "hard_fail_count": elig_result.hard_fail_count,
    }


@router.delete("/opportunities/{opportunity_id}")
async def delete_opportunity(opportunity_id: str):
    """删除申报机会（仅 discovered/applying 状态可删）"""
    db = _get_db()
    try:
        deleted = db.delete_opportunity(opportunity_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="申报机会不存在")
        return {"status": "ok", "message": "已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/opportunities")
async def create_opportunity(req: CreateOpportunityRequest):
    """轻量创建申报机会（演示模式用）"""
    db = _get_db()
    import hashlib as _hashlib
    opp_id = "opp_" + _hashlib.md5((req.policy_name + req.enterprise_id).encode()).hexdigest()[:12]
    opp = db.upsert_opportunity({
        "opportunity_id": opp_id,
        "enterprise_id": req.enterprise_id,
        "policy_name": req.policy_name,
        "status": "discovered",
        "is_eligible": True,
        "eligibility_checks_json": "[]",
        "estimated_amount": req.estimated_amount,
        "source_department": req.department,
        "deadline": req.deadline,
    })
    opp["opportunity_id"] = opp_id
    return opp
