"""
CondDef/CondSub 初始化脚本 — 将预置条件定义写入 Neo4j

用法:
    python scripts/seed_cond_defs.py              # 写入全部14个预置条件
    python scripts/seed_cond_defs.py --dry-run    # 只打印，不实际写入
    python scripts/seed_cond_defs.py --reset      # 先清空再写入
"""

import argparse
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from src.storage.neo4j_store import Neo4jStore
from src.decision.cond_def import PRESET_COND_DEFS
from config.settings import settings


def seed_cond_defs(dry_run: bool = False, reset: bool = False) -> int:
    """
    将预置条件定义写入 Neo4j

    Args:
        dry_run: 只打印不写入
        reset: 先删除所有 CondDef/CondSub 再写入

    Returns:
        成功写入的 CondDef 数量
    """
    store = Neo4jStore(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
    )

    if reset and not dry_run:
        with store.driver.session(database=store.database) as session:
            # 先删 refines_to 关系，再删节点
            session.run("MATCH ()-[r:refines_to]->() DELETE r")
            session.run("MATCH (n:CondSub) DELETE n")
            session.run("MATCH (n:CondDef) DELETE n")
            logger.info("已清空所有 CondDef/CondSub 节点")

    # 确保约束存在
    store.ensure_constraints()

    success = 0
    for cond_def in PRESET_COND_DEFS:
        if dry_run:
            sub_count = len(cond_def.sub_conditions)
            subs = ", ".join(f"{s.field} {s.op.value} {s.value}" for s in cond_def.sub_conditions)
            print(f"  [{cond_def.category}] {cond_def.condition_text} ({sub_count} subs)")
            print(f"    → {subs}")
            success += 1
            continue

        if store.add_cond_def(cond_def):
            success += 1
        else:
            logger.warning(f"写入失败: {cond_def.condition_text}")

    mode = "DRY-RUN" if dry_run else "LIVE"
    logger.info(f"[{mode}] CondDef 写入: {success}/{len(PRESET_COND_DEFS)}")

    store.close()
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将预置条件定义写入 Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--reset", action="store_true", help="先清空再写入")
    args = parser.parse_args()

    count = seed_cond_defs(dry_run=args.dry_run, reset=args.reset)
    print(f"\n完成: {count}/{len(PRESET_COND_DEFS)} 个 CondDef 已处理")
