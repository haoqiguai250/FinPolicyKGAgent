"""全链路追溯路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.trace import trace_chunk, trace_entity

router = APIRouter()


class TraceChunkRequest(BaseModel):
    source_file: str
    chunk_id: str


class TraceEntityRequest(BaseModel):
    entity_name: str
    entity_type: str


@router.post("/trace/chunk")
async def trace_chunk_api(req: TraceChunkRequest):
    """按 Chunk ID 溯源到原文"""
    try:
        result = trace_chunk(req.source_file, req.chunk_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"未找到 chunk: {req.chunk_id}")
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"溯源失败: {str(e)}")


@router.post("/trace/entity")
async def trace_entity_api(req: TraceEntityRequest):
    """按实体名称+类型溯源到所有出现位置"""
    try:
        results = trace_entity(req.entity_name, req.entity_type)
        return [r.to_dict() for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"溯源失败: {str(e)}")
