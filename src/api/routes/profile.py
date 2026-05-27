"""
企业画像管理路由

⚠️ Deprecated: 此模块保留兼容旧接口，新功能请使用 /api/enterprises 路由
- POST   /api/enterprises                         — 注册企业
- GET    /api/enterprises/{id}/profile             — 获取画像
- PUT    /api/enterprises/{id}/profile             — 更新画像
- POST   /api/enterprises/{id}/profile/nlu         — NLU 补全画像
- POST   /api/enterprises/{id}/recheck             — 画像变更后重核验
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.decision.intent_recognizer import EnterpriseProfile

router = APIRouter()

PROFILE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "enterprise_profile.json"


class ProfileUpdate(BaseModel):
    """画像更新请求（所有字段可选，只更新传入的字段）"""
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
    target_subsidy: Optional[str] = None


class ProfileNLURequest(BaseModel):
    """自然语言补全画像请求"""
    text: str


def _load_profile() -> dict:
    """从配置文件加载画像"""
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_profile(data: dict):
    """保存画像到配置文件"""
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("/profile", deprecated=True)
async def get_profile():
    """
    [Deprecated] 获取当前企业画像

    请使用 GET /api/enterprises/{enterprise_id}/profile
    """
    data = _load_profile()
    return {"profile": data}


@router.post("/profile", deprecated=True)
async def update_profile(req: ProfileUpdate):
    """
    [Deprecated] 更新企业画像（只更新传入的非 None 字段）

    请使用 PUT /api/enterprises/{enterprise_id}/profile
    """
    data = _load_profile()
    update_data = req.model_dump(exclude_none=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    data.update(update_data)
    _save_profile(data)
    return {"profile": data, "updated_fields": list(update_data.keys())}


@router.put("/profile", deprecated=True)
async def replace_profile(req: ProfileUpdate):
    """
    [Deprecated] 替换整个企业画像（全量覆盖）

    请使用 PUT /api/enterprises/{enterprise_id}/profile
    """
    data = req.model_dump()
    # 保留 extra_note 等非标准字段
    old_data = _load_profile()
    for key in ["extra_note", "intent_summary"]:
        if key in old_data and key not in data:
            data[key] = old_data[key]
    _save_profile(data)
    return {"profile": data}


@router.post("/profile/nlu", deprecated=True)
async def profile_nlu(req: ProfileNLURequest):
    """
    [Deprecated] 自然语言补全画像（用 LLM 从文本中提取画像字段）

    请使用 POST /api/enterprises/{enterprise_id}/profile/nlu
    """
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
  "annual_revenue": 数字(万元)或null",
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

        # 更新画像（只更新非 null 字段）
        data = _load_profile()
        for key, value in raw.items():
            if value is not None and key in [
                "region", "company_type", "industry", "employees",
                "annual_revenue", "established_date", "is_high_tech",
                "is_sme", "patents", "qualifications", "registered_capital",
                "rd_ratio", "target_subsidy",
            ]:
                data[key] = value

        _save_profile(data)
        return {"profile": data, "extracted": raw}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自然语言解析失败: {str(e)}")
