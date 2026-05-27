"""推送管理路由 — 企业画像配置 + 推送记录查询 + 截止提醒"""

import json
from pathlib import Path
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config.settings import settings
from src.core.logger import logger

router = APIRouter()


# ── 企业画像（与 intent_recognizer.EnterpriseProfile 字段对齐） ──

class EnterpriseProfileRequest(BaseModel):
    """完整15字段企业画像 — 与 src.decision.intent_recognizer.EnterpriseProfile 对齐"""
    region: str | None = None
    company_type: str | None = None
    industry: str | None = None
    employees: int | None = None
    annual_revenue: float | None = None
    established_date: str | None = None
    is_high_tech: bool | None = None
    is_sme: bool | None = None
    patents: int | None = None
    qualifications: list[str] = []
    registered_capital: float | None = None
    rd_ratio: float | None = None
    intent_summary: str = ""
    target_subsidy: str | None = None
    extra_note: str = ""


# ── 推送偏好 ──

class PushPreference(BaseModel):
    """推送偏好配置"""
    enabled: bool = True
    deadline_remind_days: int = 30     # 提前几天提醒截止
    remind_missing_fields: bool = True  # 是否提醒缺失画像字段
    regions: list[str] = []             # 关注的地区（空=全部）


# ── 画像读写（兼容 SQLite + profile.json） ──

def _default_profile() -> dict:
    """返回默认画像"""
    return {
        "region": "深圳市",
        "company_type": "科技型中小企业",
        "industry": "人工智能",
        "employees": None,
        "annual_revenue": None,
        "established_date": None,
        "is_high_tech": None,
        "is_sme": None,
        "patents": None,
        "qualifications": [],
        "registered_capital": None,
        "rd_ratio": None,
        "intent_summary": "",
        "target_subsidy": None,
        "extra_note": "",
    }


def _read_profile(enterprise_id: Optional[str] = None) -> dict:
    """
    读取企业画像

    优先级：
    1. 如果有 enterprise_id 且 DB 可用 → 从 SQLite 读
    2. 否则 fallback 到 profile.json（保持兼容）
    """
    # 尝试从 SQLite 读取
    if enterprise_id:
        try:
            from src.api.server import get_db
            db = get_db()
            if db:
                profile = db.get_enterprise_profile(enterprise_id)
                if profile:
                    return profile
        except Exception as e:
            logger.warning(f"从 SQLite 读取企业画像失败 (enterprise_id={enterprise_id}): {e}")

    # Fallback: 从 profile.json 读取
    profile_path: Path = settings.ENTERPRISE_PROFILE_FILE
    if not profile_path.exists():
        return _default_profile()
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取企业画像失败: {e}")
        return _default_profile()


def _write_profile(data: dict, enterprise_id: Optional[str] = None) -> None:
    """
    写入企业画像

    优先级：
    1. 如果有 enterprise_id 且 DB 可用 → 写入 SQLite
    2. 否则 fallback 到 profile.json（保持兼容）
    """
    # 尝试写入 SQLite
    if enterprise_id:
        try:
            from src.api.server import get_db
            db = get_db()
            if db:
                profile_json = json.dumps(data, ensure_ascii=False)
                db.update_enterprise_profile(enterprise_id, profile_json)
                return
        except Exception as e:
            logger.warning(f"写入企业画像到 SQLite 失败 (enterprise_id={enterprise_id}): {e}")

    # Fallback: 写入 profile.json
    profile_path: Path = settings.ENTERPRISE_PROFILE_FILE
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _read_push_preferences() -> dict:
    """读取推送偏好"""
    pref_path = settings.PUSH_DIR / "preferences.json"
    if not pref_path.exists():
        return PushPreference().model_dump()
    try:
        return json.loads(pref_path.read_text(encoding="utf-8"))
    except Exception:
        return PushPreference().model_dump()


def _write_push_preferences(data: dict) -> None:
    """写入推送偏好"""
    settings.PUSH_DIR.mkdir(parents=True, exist_ok=True)
    pref_path = settings.PUSH_DIR / "preferences.json"
    pref_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/push/profile")
async def get_push_profile(
    enterprise_id: Optional[str] = Query(None, description="企业 ID（可选，传入则从 SQLite 读取）"),
):
    """获取当前企业画像配置"""
    try:
        return _read_profile(enterprise_id=enterprise_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取企业画像失败: {str(e)}")


@router.put("/push/profile")
async def save_push_profile(
    profile: EnterpriseProfileRequest,
    enterprise_id: Optional[str] = Query(None, description="企业 ID（可选，传入则写入 SQLite）"),
):
    """保存/更新企业画像配置（完整15字段，不会丢失字段）"""
    try:
        data = profile.model_dump()
        _write_profile(data, enterprise_id=enterprise_id)
        logger.info(f"企业画像已更新: enterprise_id={enterprise_id}, data={data}")
        return {"status": "ok", "message": "企业画像已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存企业画像失败: {str(e)}")


# ── 推送偏好 ──


@router.get("/push/preferences")
async def get_push_preferences():
    """获取推送偏好配置"""
    return _read_push_preferences()


@router.put("/push/preferences")
async def save_push_preferences(pref: PushPreference):
    """保存推送偏好配置"""
    try:
        data = pref.model_dump()
        _write_push_preferences(data)
        return {"status": "ok", "message": "推送偏好已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推送偏好保存失败: {str(e)}")


# ── 截止日期提醒 ──


@router.get("/push/deadlines")
async def get_deadline_reminders(
    days_ahead: int = Query(30, description="提前几天提醒", ge=1, le=365),
    enterprise_id: Optional[str] = Query(None, description="企业 ID（可选，传入则从 SQLite 读取画像地区）"),
):
    """
    获取即将截止的政策提醒

    扫描 Neo4j 中所有 Policy 的 deadline 属性，返回在 days_ahead 天内截止的政策列表
    """
    from src.api.server import get_neo4j_store
    from src.deadline.reminder import DeadlineReminder

    neo4j_store = get_neo4j_store()
    if not neo4j_store:
        raise HTTPException(status_code=503, detail="Neo4j 未连接")

    try:
        # 读取画像中的地区做过滤
        profile = _read_profile(enterprise_id=enterprise_id)
        region = profile.get("region")

        reminder = DeadlineReminder(neo4j_store)
        reminders = reminder.scan(days_ahead=days_ahead, region=region)
        return {
            "total": len(reminders),
            "reminders": reminders,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"截止日期扫描失败: {str(e)}")


# ── 推送记录 ──


def _load_push_records(target_date: str | None = None) -> list[dict]:
    """读取推送记录文件，可按日期过滤"""
    push_dir: Path = settings.PUSH_DIR
    if not push_dir.exists():
        return []

    records: list[dict] = []

    for fp in sorted(push_dir.glob("push_*.json")):
        # 文件名格式: push_YYYYMMDD.json
        if target_date and target_date not in fp.name:
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                records.extend(data)
            elif isinstance(data, dict):
                records.append(data)
        except Exception as e:
            logger.warning(f"读取推送记录 {fp.name} 失败: {e}")

    # 按推送时间倒序排列
    records.sort(key=lambda r: r.get("push_time", ""), reverse=True)
    return records


@router.get("/push/records")
async def get_push_records(date: str | None = Query(None, description="日期 YYYYMMDD，可选")):
    """获取推送记录列表

    - 不传 date: 返回全部推送记录
    - 传 date (如 20260516): 只返回该日期的记录
    """
    try:
        records = _load_push_records(target_date=date)
        return {
            "total": len(records),
            "records": records,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取推送记录失败: {str(e)}")
