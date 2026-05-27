"""企业管理路由 — 多企业注册 + 画像管理"""

import json
import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from src.db.database import Database
from src.core.logger import logger

router = APIRouter()


# ── 请求模型 ──

class EnterpriseCreate(BaseModel):
    """企业创建请求"""
    name: str
    profile: dict = {}  # 画像 JSON（可选）


class ProfileUpdate(BaseModel):
    """画像更新请求（全量覆盖）"""
    region: Optional[str] = None
    company_type: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    annual_revenue: Optional[float] = None
    established_date: Optional[str] = None
    is_high_tech: Optional[bool] = None
    is_sme: Optional[bool] = None
    patents: Optional[int] = None
    qualifications: Optional[list[str]] = None
    registered_capital: Optional[float] = None
    rd_ratio: Optional[float] = None
    intent_summary: Optional[str] = None
    target_subsidy: Optional[str] = None
    extra_note: Optional[str] = None


class ProfileNLURequest(BaseModel):
    """自然语言补全画像请求"""
    text: str


# ── 辅助 ──

def _get_db() -> Database:
    """获取 Database 单例，不可用时抛 503"""
    from src.api.server import get_db
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return db


# ── API ──

@router.post("/enterprises")
async def create_enterprise(req: EnterpriseCreate):
    """注册企业"""
    db = _get_db()
    enterprise_id = str(uuid.uuid4())
    profile_json = json.dumps(req.profile, ensure_ascii=False)
    ent = db.create_enterprise(enterprise_id, req.name, profile_json)
    return ent


@router.get("/enterprises")
async def list_enterprises():
    """企业列表"""
    db = _get_db()
    return {"total": len(db.list_enterprises()), "enterprises": db.list_enterprises()}


@router.get("/enterprises/{enterprise_id}/profile")
async def get_enterprise_profile(enterprise_id: str):
    """获取企业画像"""
    db = _get_db()
    profile = db.get_enterprise_profile(enterprise_id)
    if not profile:
        ent = db.get_enterprise(enterprise_id)
        if not ent:
            raise HTTPException(status_code=404, detail="企业不存在")
    return {"enterprise_id": enterprise_id, "profile": profile}


@router.put("/enterprises/{enterprise_id}/profile")
async def update_enterprise_profile(enterprise_id: str, req: ProfileUpdate):
    """更新企业画像（全量覆盖）"""
    db = _get_db()
    ent = db.get_enterprise(enterprise_id)
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    # 合并：旧画像 + 新传入字段
    old_profile = db.get_enterprise_profile(enterprise_id)
    update_data = req.model_dump(exclude_none=True)
    old_profile.update(update_data)

    profile_json = json.dumps(old_profile, ensure_ascii=False)
    result = db.update_enterprise_profile(enterprise_id, profile_json)
    return {"enterprise_id": enterprise_id, "profile": old_profile, "updated_fields": list(update_data.keys())}


@router.post("/enterprises/{enterprise_id}/profile/nlu")
async def enterprise_profile_nlu(enterprise_id: str, req: ProfileNLURequest):
    """自然语言补全企业画像"""
    db = _get_db()
    ent = db.get_enterprise(enterprise_id)
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    from src.extraction.llm_client import get_llm_client
    llm = get_llm_client()

    prompt = f"""请从以下文本中提取企业画像信息，只提取文本中明确提到的字段。

文本：
{req.text}

请严格按以下 JSON 格式输出：
{{
  "region": "地区名或null",
  "company_type": "企业类型或null",
  "industry": "行业或null",
  "employees": 数字或null,
  "annual_revenue": 数字(万元)或null,
  "established_date": "YYYY-MM或null",
  "is_high_tech": true/false/null,
  "is_sme": true/false/null,
  "patents": 数字或null,
  "qualifications": ["资质1"]或[],
  "registered_capital": 数字(万元)或null,
  "rd_ratio": 数字(%)或null,
  "target_subsidy": "类型或null"
}}

不确定的字段填 null，不要编造。"""

    try:
        raw = llm.chat_json(
            system_prompt="你是一个企业信息提取助手，从文本中准确提取结构化企业画像。",
            user_prompt=prompt,
            temperature=0,
        )
        if not isinstance(raw, dict):
            raise HTTPException(status_code=500, detail="LLM 返回格式异常")

        # 合并到画像
        old_profile = db.get_enterprise_profile(enterprise_id)
        for key, value in raw.items():
            if value is not None:
                old_profile[key] = value

        profile_json = json.dumps(old_profile, ensure_ascii=False)
        db.update_enterprise_profile(enterprise_id, profile_json)
        return {"enterprise_id": enterprise_id, "profile": old_profile, "extracted": raw}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自然语言解析失败: {str(e)}")


@router.post("/enterprises/{enterprise_id}/recheck")
async def recheck_enterprise(enterprise_id: str):
    """画像变更后重核验所有 discovered 状态的 Opportunity"""
    db = _get_db()
    ent = db.get_enterprise(enterprise_id)
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    from src.api.server import get_advisor, get_neo4j_store
    advisor = get_advisor()
    if not advisor:
        raise HTTPException(status_code=503, detail="Advisor 未初始化")

    profile_data = db.get_enterprise_profile(enterprise_id)
    from src.decision.intent_recognizer import EnterpriseProfile
    profile = EnterpriseProfile(**{k: v for k, v in profile_data.items() if v is not None})

    # 找所有 discovered 状态的 Opportunity
    opps = db.list_opportunities(enterprise_id=enterprise_id, status="discovered")
    rechecked = []

    from src.decision.eligibility_engine import EligibilityEngine
    engine = EligibilityEngine(profile, neo4j_store=get_neo4j_store())

    for opp in opps:
        policy_name = opp["policy_name"]
        # 获取条件文本
        cond_texts = advisor.retriever.get_policy_condition_texts(policy_name)
        elig_result = engine.check_policy(
            policy_name=policy_name,
            policy_id=policy_name,
            conditions=cond_texts,
        )

        # 更新核验结果（不覆盖 status）
        checks_serialized = [c.to_dict() if hasattr(c, "to_dict") else c.__dict__ for c in elig_result.checks]
        db.upsert_opportunity({
            "opportunity_id": opp["opportunity_id"],
            "enterprise_id": enterprise_id,
            "policy_name": policy_name,
            "is_eligible": 1 if elig_result.is_eligible else 0,
            "eligibility_checks_json": json.dumps(checks_serialized, ensure_ascii=False),
            "hard_pass_count": elig_result.hard_pass_count,
            "hard_fail_count": elig_result.hard_fail_count,
            "soft_pass_count": elig_result.soft_pass_count,
            "unknown_count": elig_result.unknown_count,
        })
        rechecked.append({"policy_name": policy_name, "is_eligible": elig_result.is_eligible})

    return {"enterprise_id": enterprise_id, "rechecked_count": len(rechecked), "results": rechecked}
