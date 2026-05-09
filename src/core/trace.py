"""
溯源查询工具

用户点击 KG 节点 → 调用 trace_chunk() → 看到原文出处

链路：
  KG 节点 → triple.source_chunk_id → chunked.json → parsed.json → 具体段落
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from config.settings import settings
from loguru import logger


@dataclass
class TraceResult:
    """溯源结果"""
    chunk_id: str                          # chunk ID（如 chunk_002）
    source_file: str                       # 原始文件名
    paragraph_location: str                # 段落定位（如 "第一章优化产业空间配置 第一条~第四条"）
    heading: str                           # 章节标题
    clause_range: str                      # 条款范围（如 "第一条~第四条"）
    chunk_text: str                        # chunk 原文
    section_heading: str                   # 所属章节标题（来自 parsed.json）
    section_content: str                   # 完整章节内容（上下文）

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_file": self.source_file,
            "paragraph_location": self.paragraph_location,
            "heading": self.heading,
            "clause_range": self.clause_range,
            "chunk_text": self.chunk_text,
            "section_heading": self.section_heading,
            "section_content": self.section_content,
        }


def _find_chunked_file(source_file: str) -> Optional[Path]:
    """根据原始文件名找到对应的 _chunked.json"""
    stem = Path(source_file).stem
    chunked_path = settings.PROCESSED_DIR / f"{stem}_chunked.json"
    if chunked_path.exists():
        return chunked_path
    return None


def _find_parsed_file(source_file: str) -> Optional[Path]:
    """根据原始文件名找到对应的 _parsed.json"""
    stem = Path(source_file).stem
    parsed_path = settings.PROCESSED_DIR / f"{stem}_parsed.json"
    if parsed_path.exists():
        return parsed_path
    return None


def trace_chunk(source_file: str, chunk_id: str) -> Optional[TraceResult]:
    """
    溯源查询：从 chunk_id 追溯到原文段落

    Args:
        source_file: 原始文件名（如 "坪山区人民政府关于印发《深圳市坪山区关于支持实体经济发展的若干措施》.pdf"）
        chunk_id: chunk ID（如 "chunk_002"）

    Returns:
        TraceResult 或 None（找不到时）
    """
    # 1. 找到 chunked.json
    chunked_path = _find_chunked_file(source_file)
    if not chunked_path:
        logger.warning(f"找不到 chunked 文件: {source_file}")
        return None

    with open(chunked_path, "r", encoding="utf-8") as f:
        chunked_data = json.load(f)

    # 2. 在 chunks 中找到目标 chunk
    target_chunk = None
    for chunk in chunked_data.get("chunks", []):
        if chunk["chunk_id"] == chunk_id:
            target_chunk = chunk
            break

    if not target_chunk:
        logger.warning(f"找不到 chunk: {chunk_id} in {source_file}")
        return None

    # 3. 从 chunked.json 中获取基础信息
    heading = target_chunk.get("heading", "")
    paragraph_location = target_chunk.get("metadata", {}).get("paragraph_location", "")
    chunk_text = target_chunk.get("text", "")
    chapter_idx = target_chunk.get("chapter_idx", 0)

    # 从 paragraph_location 中提取条款范围
    clause_range = ""
    if paragraph_location and paragraph_location != heading:
        # paragraph_location = "heading clause_range"，去掉 heading 部分就是条款范围
        if paragraph_location.startswith(heading):
            clause_range = paragraph_location[len(heading):].strip()

    # 4. 找到 parsed.json，获取完整章节内容（上下文）
    section_heading = heading
    section_content = ""

    parsed_path = _find_parsed_file(source_file)
    if parsed_path and parsed_path.exists():
        with open(parsed_path, "r", encoding="utf-8") as f:
            parsed_data = json.load(f)

        sections = parsed_data.get("sections", [])
        if 0 <= chapter_idx < len(sections):
            section = sections[chapter_idx]
            section_heading = section.get("heading", heading)
            section_content = section.get("content", "")

    return TraceResult(
        chunk_id=chunk_id,
        source_file=source_file,
        paragraph_location=paragraph_location,
        heading=heading,
        clause_range=clause_range,
        chunk_text=chunk_text,
        section_heading=section_heading,
        section_content=section_content,
    )


def trace_entity(entity_name: str, entity_type: str) -> list[TraceResult]:
    """
    通过实体名溯源：查找该实体出现的所有原文段落

    Args:
        entity_name: 实体名称
        entity_type: 实体类型

    Returns:
        TraceResult 列表（可能来自多个 chunk/文件）
    """
    results = []
    triplets_dir = settings.TRIPLETS_DIR

    if not triplets_dir.exists():
        return results

    # 遍历所有三元组文件，找到包含该实体的 source_chunk_id
    seen_chunks = set()  # (source_file, chunk_id) 去重

    for triplet_file in triplets_dir.glob("*.json"):
        with open(triplet_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        source_file = data.get("source_file", "")
        if not source_file:
            continue

        # 在实体列表中查找
        for entity in data.get("entities", []):
            if entity.get("name") == entity_name and entity.get("type") == entity_type:
                chunk_id = entity.get("source_chunk_id", "")
                if chunk_id and (source_file, chunk_id) not in seen_chunks:
                    seen_chunks.add((source_file, chunk_id))
                    result = trace_chunk(source_file, chunk_id)
                    if result:
                        results.append(result)

        # 在三元组中查找（subject 或 object）
        for triple in data.get("triples", []):
            subj = triple.get("subject", {})
            obj = triple.get("object", {})
            if (subj.get("name") == entity_name and subj.get("type") == entity_type) or \
               (obj.get("name") == entity_name and obj.get("type") == entity_type):
                chunk_id = triple.get("source_chunk_id", "")
                if chunk_id and (source_file, chunk_id) not in seen_chunks:
                    seen_chunks.add((source_file, chunk_id))
                    result = trace_chunk(source_file, chunk_id)
                    if result:
                        results.append(result)

    return results


# ── CLI 测试入口 ──
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="溯源查询工具")
    parser.add_argument("--source-file", type=str, required=True, help="原始文件名")
    parser.add_argument("--chunk-id", type=str, required=True, help="chunk ID（如 chunk_002）")
    args = parser.parse_args()

    result = trace_chunk(args.source_file, args.chunk_id)
    if result:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("未找到溯源信息")
