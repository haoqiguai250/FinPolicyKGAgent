"""
从 JSON triplets 文件恢复 Neo4j 数据

用法：
    python scripts/restore_triplets.py --date 20260603

从 data/triplets/ 中读取指定日期的 JSON 文件，解析实体/三元组，写入 Neo4j
"""
import argparse
import json
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.neo4j_store import Neo4jStore
from src.storage.neo4j_store import Entity, Triple
from config.settings import settings
from src.core.logger import logger


def restore_from_triplets(neo4j_store: Neo4jStore, date_prefix: str):
    pattern = f"data/triplets/*{date_prefix}*.json"
    files = glob.glob(pattern)
    if not files:
        logger.error(f"未找到匹配 {pattern} 的三元组文件")
        return

    # 按 PDF 去重（同一 PDF 有多个文件时只取最大的）
    by_pdf: dict[str, str] = {}
    for f in files:
        basename = Path(f).name
        # 提取 PDF 名称（去掉时间戳）
        parts = basename.rsplit("_pdf_", 1)
        if len(parts) < 2:
            pdf_key = basename.rsplit(".pdf_", 1)[0]
        else:
            pdf_key = parts[0]
        if pdf_key not in by_pdf or Path(f).stat().st_size > Path(by_pdf[pdf_key]).stat().st_size:
            by_pdf[pdf_key] = f

    logger.info(f"找到 {len(files)} 个文件，去重后 {len(by_pdf)} 个 PDF")

    total_entities = 0
    total_triples = 0
    failed = 0

    for pdf_key, filepath in by_pdf.items():
        try:
            with open(filepath, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            entities_raw = data.get("entities", [])
            triples_raw = data.get("triples", [])

            if not entities_raw and not triples_raw:
                continue

            # 转换 Entity
            entities = []
            for e in entities_raw:
                entities.append(Entity(
                    name=e["name"],
                    entity_type=e["type"],
                    attributes=e.get("attributes", {}),
                    source_chunk_id=e.get("source_chunk_id", ""),
                ))

            # 转换 Triple
            triples = []
            for t in triples_raw:
                subj = t["subject"]
                obj = t["object"]
                triples.append(Triple(
                    subject=Entity(
                        name=subj["name"],
                        entity_type=subj.get("type", "Unknown"),
                    ),
                    relation=t["relation"],
                    object_=Entity(
                        name=obj["name"],
                        entity_type=obj.get("type", "Unknown"),
                    ),
                    confidence=t.get("confidence", 1.0),
                    source_text=t.get("source_text", ""),
                    source_chunk_id=t.get("source_chunk_id", ""),
                    source_sentence_index=t.get("source_sentence_index", -1),
                ))

            neo4j_store.add_entities(entities)
            neo4j_store.add_triples(triples)

            total_entities += len(entities)
            total_triples += len(triples)
            logger.debug(f"  ✅ {pdf_key[:50]}: {len(entities)} 实体, {len(triples)} 三元组")

        except Exception as e:
            failed += 1
            logger.error(f"  ❌ {pdf_key[:50]}: {e}")

    logger.info(f"\n恢复完成: {total_entities} 实体, {total_triples} 三元组, 失败 {failed}")


def main():
    parser = argparse.ArgumentParser(description="从 JSON triplets 恢复 Neo4j")
    parser.add_argument("--date", default="20260603", help="日期前缀 (如 20260603)")
    args = parser.parse_args()

    neo4j_store = Neo4jStore(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
    )

    try:
        restore_from_triplets(neo4j_store, args.date)
    finally:
        stats = neo4j_store.compute_stats()
        logger.info(f"Neo4j 最终状态: {stats['total_entities']} 实体, {stats['total_triples']} 三元组")
        neo4j_store.close()


if __name__ == "__main__":
    main()
