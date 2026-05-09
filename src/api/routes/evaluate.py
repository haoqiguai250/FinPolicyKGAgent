"""评估报告路由"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.api.adapters import adapt_evaluation_data
from config.settings import settings

router = APIRouter()


@router.post("/evaluate")
async def evaluate():
    """获取评估报告数据（从已完成的 Pipeline 运行记录中读取）"""
    try:
        reports_dir = settings.RUN_LOGS_DIR
        return adapt_evaluation_data(reports_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取评估数据失败: {str(e)}")
