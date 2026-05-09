"""
一次性脚本：给已有的 _chunked.json 文件补充 metadata.paragraph_location 字段
不需要重跑 pipeline，直接读取已有文件并补充

用法:
    python scripts/backfill_paragraph_location.py
    python scripts/backfill_paragraph_location.py --dry-run   # 只预览，不写入
"""

import json
import re
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.chunker import SectionAwareChunker


def backfill_chunked_file(chunked_path: Path, dry_run: bool = False) -> dict:
    """给单个 _chunked.json 补充 paragraph_location"""
    with open(chunked_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = len(data.get("chunks", []))
    updated = 0

    for chunk in data.get("chunks", []):
        metadata = chunk.get("metadata", {})
        # 已经有 paragraph_location 的跳过
        if metadata.get("paragraph_location"):
            continue

        heading = chunk.get("heading", "")
        text = chunk.get("text", "")

        clause_range = SectionAwareChunker._extract_clause_range(text)
        paragraph_location = SectionAwareChunker._build_paragraph_location(heading, clause_range)

        metadata["paragraph_location"] = paragraph_location
        chunk["metadata"] = metadata
        updated += 1

    if updated > 0 and not dry_run:
        with open(chunked_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return {"file": chunked_path.name, "total_chunks": total, "updated": updated}


def main():
    from config.settings import settings

    dry_run = "--dry-run" in sys.argv

    processed_dir = settings.PROCESSED_DIR
    if not processed_dir.exists():
        print(f"目录不存在: {processed_dir}")
        return

    chunked_files = list(processed_dir.glob("*_chunked.json"))
    if not chunked_files:
        print("未找到 _chunked.json 文件")
        return

    print(f"找到 {len(chunked_files)} 个 _chunked.json 文件")
    if dry_run:
        print("🔍 DRY RUN 模式（只预览，不写入）")
    print()

    total_updated = 0
    for cf in sorted(chunked_files):
        result = backfill_chunked_file(cf, dry_run=dry_run)
        if result["updated"] > 0:
            action = "将更新" if dry_run else "已更新"
            print(f"  {action}: {result['file']}  ({result['updated']}/{result['total_chunks']} chunks)")
            total_updated += result["updated"]
        else:
            print(f"  跳过: {result['file']}  (全部已有 paragraph_location)")

    print(f"\n{'将更新' if dry_run else '已更新'} {total_updated} 个 chunk 的 paragraph_location")


if __name__ == "__main__":
    main()
