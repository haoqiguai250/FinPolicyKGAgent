"""决策查询路由"""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.server import get_advisor

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
