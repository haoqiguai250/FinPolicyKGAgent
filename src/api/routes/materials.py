"""
申报材料路由 — 材料清单逐项管理

Phase 3 模块 F: 申报材料工作台
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.logger import logger

router = APIRouter()


class MaterialStatusUpdate(BaseModel):
    """材料状态更新"""
    status: Optional[str] = None  # preparing / ready / submitted / waived
    notes: Optional[str] = None


class MaterialsGenerateRequest(BaseModel):
    """LLM 生成材料清单请求"""
    pass


def _get_db():
    from src.api.server import get_db
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return db


@router.get("/opportunities/{opportunity_id}/materials")
async def list_materials(opportunity_id: str):
    """获取申报材料清单 + 完成度"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")

    materials = db.list_materials(opportunity_id)
    progress = db.get_materials_progress(opportunity_id)

    return {
        "opportunity_id": opportunity_id,
        "policy_name": opp["policy_name"],
        "materials": materials,
        "progress": progress,
    }


@router.patch("/materials/{material_id}")
async def update_material(material_id: str, req: MaterialStatusUpdate):
    """更新单条材料状态/备注"""
    db = _get_db()
    mat = db.get_material(material_id)
    if not mat:
        raise HTTPException(status_code=404, detail="材料项不存在")

    updated = db.update_material(
        material_id=material_id,
        status=req.status,
        notes=req.notes,
    )
    return updated


@router.post("/opportunities/{opportunity_id}/materials/generate")
async def generate_materials(opportunity_id: str, req: MaterialsGenerateRequest):
    """KG 无材料清单时，用 LLM 生成建议材料清单"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")

    # 检查是否已有材料
    existing = db.list_materials(opportunity_id)
    if existing:
        raise HTTPException(status_code=400, detail=f"已有 {len(existing)} 条材料，无需生成")

    # 读取政策信息
    policy_name = opp["policy_name"]
    from src.api.server import get_neo4j_store
    neo4j_store = get_neo4j_store()

    policy_desc = ""
    if neo4j_store:
        try:
            from src.storage.cypher_queries import FIND_POLICY_APPLICATION_DATA
            with neo4j_store.driver.session(database=neo4j_store.database) as session:
                result = session.run(FIND_POLICY_APPLICATION_DATA, policy_name=policy_name)
                record = result.single()
                if record:
                    policy_desc = json.dumps(
                        {k: v for k, v in dict(record).items() if v is not None},
                        ensure_ascii=False,
                    )
        except Exception as e:
            logger.warning(f"读取政策信息失败: {e}")

    # 读取企业画像
    enterprise_id = opp["enterprise_id"]
    profile = db.get_enterprise_profile(enterprise_id)

    # LLM 生成
    from src.extraction.llm_client import get_llm_client
    llm = get_llm_client()

    prompt = f"""基于以下政策信息和企业画像，生成该政策的申报材料清单。

政策名称: {policy_name}
政策信息: {policy_desc or '暂无'}
企业画像: {json.dumps(profile, ensure_ascii=False)}

请列出申报该政策所需的全部材料，每条材料一行。
严格按 JSON 数组格式输出：
["材料1", "材料2", "材料3"]

注意：
- 材料名称要具体（如"营业执照副本（加盖公章）"而非"营业执照"）
- 一般性材料包括：营业执照、财务审计报告、税务证明等
- 根据政策特点补充专项材料"""

    try:
        raw = llm.chat_json(
            system_prompt="你是一个政策申报顾问，根据政策要求和企业情况，精准列出所需的申报材料。",
            user_prompt=prompt,
            temperature=0.3,
        )

        if not isinstance(raw, list):
            raise HTTPException(status_code=500, detail="LLM 返回格式异常，期望数组")

        # 写入 DB
        materials_data = [{"material_name": m, "source": "llm"} for m in raw if isinstance(m, str)]
        if not materials_data:
            raise HTTPException(status_code=500, detail="LLM 未生成有效材料")

        created = db.add_materials(opportunity_id, materials_data)
        progress = db.get_materials_progress(opportunity_id)

        return {
            "opportunity_id": opportunity_id,
            "generated_count": len(created),
            "materials": created,
            "progress": progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"材料清单生成失败: {str(e)}")


@router.get("/opportunities/{opportunity_id}/materials/progress")
async def get_materials_progress(opportunity_id: str):
    """获取材料完成度"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")

    progress = db.get_materials_progress(opportunity_id)
    return {
        "opportunity_id": opportunity_id,
        **progress,
    }
