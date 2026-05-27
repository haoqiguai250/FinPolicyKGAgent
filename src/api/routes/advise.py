"""决策查询路由"""

import asyncio
import hashlib
import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.server import get_advisor, get_db
from src.api.models import ApplicationOpportunity, EligibilityCheckBrief, OpportunitiesResponse

router = APIRouter()


class AdviseRequest(BaseModel):
    query: str
    fast_mode: bool = False


@router.post("/advise")
async def advise(req: AdviseRequest):
    """决策查询接口（支持 fast_mode 快速模式）"""
    advisor = get_advisor()
    if not advisor:
        raise HTTPException(status_code=503, detail="Advisor 服务未初始化，请检查 Neo4j 和 LLM 配置")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, advisor.advise, req.query, req.fast_mode)
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"决策查询失败: {str(e)}")


@router.post("/advise/plans")
async def advise_plans(req: AdviseRequest):
    """
    申报方案接口 — 只返回 ApplicationPlan + MissingInfo

    比 /advise 更轻量：跳过扰动分析，专注条件核验和申报方案
    """
    advisor = get_advisor()
    if not advisor:
        raise HTTPException(status_code=503, detail="Advisor 服务未初始化")

    try:
        loop = asyncio.get_event_loop()
        # fast_mode=True 跳过扰动分析
        result = await loop.run_in_executor(None, advisor.advise, req.query, True)
        return {
            "query": result.query,
            "profile": result.profile.to_dict(),
            "application_plans": [p.to_dict() for p in result.application_plans],
            "missing_info": result.missing_info.to_dict() if result.missing_info else None,
            "matched_policies": result.retrieval.matched_policies,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"申报方案查询失败: {str(e)}")


@router.post("/advise/opportunities")
async def advise_opportunities(
    req: AdviseRequest,
    enterprise_id: Optional[str] = Query(None, description="企业ID（持久化时需要）"),
):
    """
    申报机会接口 — 返回 ApplicationOpportunity 列表

    这是模块 C 企业申报工作台的核心数据源。
    与 /advise/plans 的区别：
    - 返回 ApplicationOpportunity 而非 ApplicationPlan
    - 包含运营状态（status）、截止提醒、机会ID
    - 计算截止日期紧急程度
    """
    advisor = get_advisor()
    if not advisor:
        raise HTTPException(status_code=503, detail="Advisor 服务未初始化")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, advisor.advise, req.query, True)

        # 将 ApplicationPlan 转换为 ApplicationOpportunity
        opportunities = []
        today = date.today()
        for plan in result.application_plans:
            # 构建条件核验简要信息
            checks = []
            if plan.eligibility_result:
                for c in plan.eligibility_result.checks:
                    checks.append(EligibilityCheckBrief(
                        condition_text=c.condition_text,
                        status=c.status,
                        is_hard=c.is_hard,
                        reason=c.reason,
                    ))

            # 计算截止日期紧急程度
            days_until_deadline = None
            deadline_urgency = None
            if plan.deadline and plan.deadline not in ("常年申报", "长期有效"):
                try:
                    deadline_str = plan.deadline.strip().replace("/", "-")[:10]
                    deadline_date = date.fromisoformat(deadline_str)
                    days_until_deadline = (deadline_date - today).days
                    if 0 <= days_until_deadline <= 7:
                        deadline_urgency = "high"
                    elif 0 <= days_until_deadline <= 15:
                        deadline_urgency = "medium"
                    elif 0 <= days_until_deadline <= 30:
                        deadline_urgency = "low"
                except (ValueError, TypeError):
                    pass

            # 生成 opportunity_id（基于 policy_name + enterprise_id，不再依赖 query）
            oid = hashlib.md5(f"{plan.policy_name}:{enterprise_id}".encode()).hexdigest()[:12]

            opp = ApplicationOpportunity(
                opportunity_id=oid,
                policy_name=plan.policy_name,
                policy_id=plan.policy_id,
                enterprise_id=enterprise_id or "",
                is_eligible=plan.is_eligible,
                eligibility_checks=checks,
                hard_pass_count=plan.eligibility_result.hard_pass_count if plan.eligibility_result else 0,
                hard_fail_count=plan.eligibility_result.hard_fail_count if plan.eligibility_result else 0,
                soft_pass_count=plan.eligibility_result.soft_pass_count if plan.eligibility_result else 0,
                unknown_count=plan.eligibility_result.unknown_count if plan.eligibility_result else 0,
                required_materials=plan.required_materials,
                application_steps=plan.application_steps,
                deadline=plan.deadline,
                platform_url=plan.platform_url,
                platform_name=plan.platform_name,
                source_department=plan.source_department,
                estimated_amount=plan.estimated_amount,
                match_explanation=plan.match_explanation,
                suggestions=plan.suggestions,
                status="discovered",
                created_at=today.isoformat(),
                days_until_deadline=days_until_deadline,
                deadline_urgency=deadline_urgency,
                effective_date=plan.effective_date,
                expiry_date=plan.expiry_date,
                policy_status=plan.policy_status,
            )
            opportunities.append(opp)

        # 持久化：如果有 enterprise_id 且 DB 可用 → 先存 DB
        db = get_db()
        if enterprise_id and db:
            for opp in opportunities:
                try:
                    # 序列化核验结果
                    eligibility_checks_json = json.dumps(
                        [c.model_dump() for c in opp.eligibility_checks],
                        ensure_ascii=False,
                    )
                    required_materials_json = json.dumps(
                        opp.required_materials, ensure_ascii=False,
                    )
                    application_steps_json = json.dumps(
                        opp.application_steps, ensure_ascii=False,
                    )
                    db.upsert_opportunity({
                        "opportunity_id": opp.opportunity_id,
                        "enterprise_id": enterprise_id,
                        "policy_name": opp.policy_name,
                        "is_eligible": 1 if opp.is_eligible else 0,
                        "eligibility_checks_json": eligibility_checks_json,
                        "hard_pass_count": opp.hard_pass_count,
                        "hard_fail_count": opp.hard_fail_count,
                        "soft_pass_count": opp.soft_pass_count,
                        "unknown_count": opp.unknown_count,
                        "deadline": opp.deadline,
                        "deadline_urgency": opp.deadline_urgency or "",
                        "days_until_deadline": opp.days_until_deadline,
                        "estimated_amount": opp.estimated_amount,
                        "platform_name": opp.platform_name,
                        "platform_url": opp.platform_url,
                        "source_department": opp.source_department,
                        "match_explanation": opp.match_explanation,
                        "suggestions": opp.suggestions,
                        "required_materials_json": required_materials_json,
                        "application_steps_json": application_steps_json,
                    })
                    # 材料展开：如果有 required_materials，逐条写入 material_checklist
                    if opp.required_materials:
                        materials = [
                            {"material_name": m, "source": "kg"}
                            for m in opp.required_materials
                        ]
                        db.add_materials(opp.opportunity_id, materials)
                except Exception as e:
                    logger.warning(f"持久化 Opportunity {opp.opportunity_id} 失败: {e}")

        # 提取缺失字段
        missing_fields = []
        if result.missing_info:
            missing_fields = [f.label for f in result.missing_info.missing_fields]

        eligible_count = sum(1 for o in opportunities if o.is_eligible)
        ineligible_count = len(opportunities) - eligible_count

        return OpportunitiesResponse(
            total=len(opportunities),
            eligible_count=eligible_count,
            ineligible_count=ineligible_count,
            missing_fields=missing_fields,
            opportunities=opportunities,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"申报机会查询失败: {str(e)}")
