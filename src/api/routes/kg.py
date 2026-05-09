"""知识图谱路由"""

from fastapi import APIRouter, HTTPException

from src.api.server import get_neo4j_store
from src.api.adapters import adapt_graph_data

router = APIRouter()


@router.get("/kg/stats")
async def kg_stats():
    """获取知识图谱统计信息"""
    store = get_neo4j_store()
    if not store:
        raise HTTPException(status_code=503, detail="Neo4j 服务未连接")

    try:
        return store.compute_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/kg/graph")
async def kg_graph():
    """获取知识图谱全量数据（节点+边）"""
    store = get_neo4j_store()
    if not store:
        raise HTTPException(status_code=503, detail="Neo4j 服务未连接")

    try:
        raw = store._export_to_dict()
        return adapt_graph_data(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取图谱数据失败: {str(e)}")
