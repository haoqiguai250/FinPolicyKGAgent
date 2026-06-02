"""
文档生成路由 — 材料文档自动生成 + 下载
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.core.logger import logger

router = APIRouter()


class DocumentGenerateRequest(BaseModel):
    """文档生成请求"""
    doc_type: str = "docx"  # docx / pdf
    material_ids: list[str] = []  # 指定材料 ID，空 = 全部


def _get_db():
    from src.api.server import get_db
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return db


@router.post("/opportunities/{opportunity_id}/documents/generate")
async def generate_documents(opportunity_id: str, req: DocumentGenerateRequest):
    """为申报机会自动生成材料文档"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")

    # 获取材料清单
    materials = db.list_materials(opportunity_id)
    if not materials:
        raise HTTPException(status_code=400, detail="材料清单为空，请先生成材料清单")

    # 筛选指定材料
    if req.material_ids:
        materials = [m for m in materials if m["material_id"] in req.material_ids]
        if not materials:
            raise HTTPException(status_code=400, detail="指定的材料 ID 不存在")

    # 获取企业画像
    profile = db.get_enterprise_profile(opp["enterprise_id"])

    # 生成文档
    from src.decision.material_generator import MaterialDocumentGenerator
    generator = MaterialDocumentGenerator()

    doc_records = generator.generate_document(
        opportunity=opp,
        materials=materials,
        enterprise_profile=profile,
        doc_type=req.doc_type,
    )

    # 写入 DB
    saved = []
    for rec in doc_records:
        try:
            saved_doc = db.add_generated_document(rec)
            saved.append(saved_doc)
        except Exception as e:
            logger.warning(f"保存文档记录失败: {e}")

    # 更新材料状态为 ready
    for mat in materials:
        try:
            db.update_material(mat["material_id"], status="ready")
        except Exception:
            pass

    return {
        "opportunity_id": opportunity_id,
        "generated_count": len(saved),
        "documents": saved,
    }


@router.get("/opportunities/{opportunity_id}/documents")
async def list_documents(opportunity_id: str):
    """列出申报机会的已生成文档"""
    db = _get_db()
    opp = db.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="申报机会不存在")

    docs = db.list_generated_documents(opportunity_id)
    return {
        "opportunity_id": opportunity_id,
        "total": len(docs),
        "documents": docs,
    }


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str):
    """下载已生成的文档（防路径穿越）"""
    db = _get_db()
    doc = db.get_generated_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    file_path = doc.get("file_path", "")
    if not file_path:
        raise HTTPException(status_code=404, detail="文件路径为空")

    # 防路径穿越：解析为绝对路径，确保在输出目录内
    from config.settings import settings
    output_dir = settings.MATERIALS_OUTPUT_DIR.resolve()
    resolved = Path(file_path).resolve()

    if not str(resolved).startswith(str(output_dir)):
        raise HTTPException(status_code=403, detail="非法文件路径")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 检测 MIME 类型
    if doc["doc_type"] == "pdf":
        media_type = "application/pdf"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(
        path=str(resolved),
        filename=doc["doc_name"],
        media_type=media_type,
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除已生成的文档"""
    db = _get_db()
    doc = db.get_generated_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 删除物理文件
    file_path = doc.get("file_path", "")
    if file_path:
        try:
            resolved = Path(file_path).resolve()
            from config.settings import settings
            output_dir = settings.MATERIALS_OUTPUT_DIR.resolve()
            if str(resolved).startswith(str(output_dir)) and resolved.exists():
                resolved.unlink()
        except Exception as e:
            logger.warning(f"删除文件失败: {e}")

    # 删除 DB 记录
    with db.get_conn() as conn:
        conn.execute("DELETE FROM generated_documents WHERE doc_id = ?", (doc_id,))

    return {"status": "ok", "message": "文档已删除"}
