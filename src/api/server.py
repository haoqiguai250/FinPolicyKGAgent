"""
FinPolicyKG FastAPI 服务

用法:
    python -m src.api.main --serve
    python -m src.api.main --serve --port 8000 --host 0.0.0.0
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import settings
from src.core.logger import logger

# 全局服务实例（lifespan 中初始化）
_neo4j_store = None
_advisor = None


def get_neo4j_store():
    """获取 Neo4jStore 单例"""
    return _neo4j_store


def get_advisor():
    """获取 Advisor 单例"""
    return _advisor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化服务，关闭时清理"""
    global _neo4j_store, _advisor

    logger.info("🚀 FinPolicyKG API 服务启动中...")

    # 初始化 Neo4jStore
    try:
        from src.storage.neo4j_store import Neo4jStore
        _neo4j_store = Neo4jStore()
        stats = _neo4j_store.compute_stats()
        logger.info(f"  Neo4j 连接成功: {stats['total_entities']} 实体, {stats['total_triples']} 三元组")
    except Exception as e:
        logger.warning(f"  Neo4j 初始化失败（KG 相关接口不可用）: {e}")
        _neo4j_store = None

    # 初始化 Advisor
    try:
        from src.decision.advisor import Advisor
        from src.extraction.llm_client import get_reasoning_llm_client
        llm = get_reasoning_llm_client()
        _advisor = Advisor(neo4j_store=_neo4j_store, llm_client=llm, enable_explanation=True)
        logger.info("  Advisor 初始化成功")
    except Exception as e:
        logger.warning(f"  Advisor 初始化失败（决策查询接口不可用）: {e}")
        _advisor = None

    logger.info("✅ FinPolicyKG API 服务就绪")

    yield

    # 清理
    if _neo4j_store:
        try:
            _neo4j_store.close()
        except Exception:
            pass
    logger.info("👋 FinPolicyKG API 服务已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="FinPolicyKG API",
        description="金融政策知识图谱智能体 — RESTful API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — 开发环境允许前端跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    from src.api.routes import advise, kg, trace, evaluate, push
    app.include_router(advise.router, prefix="/api", tags=["决策查询"])
    app.include_router(kg.router, prefix="/api", tags=["知识图谱"])
    app.include_router(trace.router, prefix="/api", tags=["全链路追溯"])
    app.include_router(evaluate.router, prefix="/api", tags=["评估报告"])
    app.include_router(push.router, prefix="/api", tags=["推送管理"])

    # 健康检查
    @app.get("/api/health")
    async def health_check():
        return {
            "status": "ok",
            "neo4j": _neo4j_store is not None,
            "advisor": _advisor is not None,
        }

    return app
