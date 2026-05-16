"""推送管理路由 — 企业画像配置 + 推送记录查询"""

import json
from pathlib import Path
from datetime import datetime, date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config.settings import settings
from src.core.logger import logger

router = APIRouter()


# ── 企业画像 ──

class EnterpriseProfile(BaseModel):
    region: str = ""
    company_type: str = ""
    industry: str = ""
    extra_note: str = ""


def _read_profile() -> dict:
    """读取企业画像文件"""
    profile_path: Path = settings.ENTERPRISE_PROFILE_FILE
    if not profile_path.exists():
        return {
            "region": "深圳市",
            "company_type": "科技型中小企业",
            "industry": "人工智能",
            "extra_note": "",
        }
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取企业画像失败: {e}")
        return {
            "region": "深圳市",
            "company_type": "科技型中小企业",
            "industry": "人工智能",
            "extra_note": "",
        }


def _write_profile(data: dict) -> None:
    """写入企业画像文件"""
    profile_path: Path = settings.ENTERPRISE_PROFILE_FILE
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


@router.get("/push/profile")
async def get_push_profile():
    """获取当前企业画像配置"""
    try:
        return _read_profile()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取企业画像失败: {str(e)}")


@router.put("/push/profile")
async def save_push_profile(profile: EnterpriseProfile):
    """保存/更新企业画像配置"""
    try:
        data = profile.model_dump()
        _write_profile(data)
        logger.info(f"企业画像已更新: {data}")
        return {"status": "ok", "message": "企业画像已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存企业画像失败: {str(e)}")


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
