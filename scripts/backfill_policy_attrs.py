"""
历史 Policy 节点申报属性补抽脚本（Phase 2 模块 B3）

功能：
  遍历 Neo4j 中已有的 Policy 节点，从对应的 chunk 原文用 LLM 补抽申报属性，
  写回 Policy 节点的 deadline/application_platform/required_materials 等字段。

用法：
  python scripts/backfill_policy_attrs.py                  # 正式运行
  python scripts/backfill_policy_attrs.py --dry-run         # 只预览，不写 Neo4j
  python scripts/backfill_policy_attrs.py --policy "政策名"  # 只处理指定政策
  python scripts/backfill_policy_attrs.py --force           # 强制覆盖已有属性

流程：
  1. 从 Neo4j 读取所有 Policy 节点（可过滤已有属性）
  2. 根据每个 Policy 的 source_file 找到对应的 chunked.json
  3. 拼接所有 chunk 文本作为原文
  4. 用 LLM 从原文抽取申报属性
  5. 写回 Neo4j Policy 节点
"""

import argparse
import json
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from config.settings import settings
from src.storage.neo4j_store import Neo4jStore
from src.extraction.llm_client import get_llm_client


# ── LLM 抽取 Prompt ──

BACKFILL_SYSTEM_PROMPT = """你是一个金融政策信息抽取专家。请从给定的政策原文中抽取申报相关的结构化信息。

只抽取以下字段，找不到的留空（null），不要编造：
- deadline: 申报截止日期（如 "2025-12-31"、"常年申报"）
- application_platform: 申报平台名称（如 "深圳市科技创新服务平台"）
- application_platform_url: 申报平台链接
- required_materials: 所需材料清单（数组，如 ["营业执照", "审计报告"]）
- application_steps: 申报流程步骤（数组，如 ["网上申报", "材料提交", "专家评审"]）
- estimated_amount: 预估补贴金额/资助标准（原文表述，如 "最高500万元"）
- contact_department: 联系部门（如 "深圳市科技创新委员会"）

请严格以 JSON 格式输出，不要包含任何其他文字。"""

BACKFILL_USER_PROMPT = """请从以下政策原文中抽取申报信息：

---
{policy_text}
---

请输出 JSON 格式，包含以下字段：
deadline, application_platform, application_platform_url, required_materials, application_steps, estimated_amount, contact_department"""


def find_chunked_file(source_file: str) -> Path | None:
    """根据 source_file 名找到对应的 chunked.json"""
    processed_dir = PROJECT_ROOT / "data" / "processed"
    # 去掉 .pdf 后缀，加 _chunked.json
    base_name = source_file
    if base_name.endswith(".pdf"):
        base_name = base_name[:-4]
    target = processed_dir / f"{base_name}_chunked.json"
    if target.exists():
        return target
    return None


def load_policy_text(chunked_path: Path) -> str:
    """从 chunked.json 中拼接所有 chunk 文本"""
    with open(chunked_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    chunks = data.get("chunks", [])
    texts = [c.get("text", "") for c in chunks if c.get("text")]
    return "\n\n".join(texts)


def extract_application_attrs(llm, policy_text: str) -> dict:
    """用 LLM 从原文抽取申报属性"""
    # 截断过长文本（避免超过 token 限制）
    max_chars = 8000
    if len(policy_text) > max_chars:
        policy_text = policy_text[:max_chars] + "\n\n[...原文已截断...]"

    user_prompt = BACKFILL_USER_PROMPT.format(policy_text=policy_text)
    result = llm.chat_json(
        system_prompt=BACKFILL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0,
    )
    if isinstance(result, dict):
        return result
    return {}


def write_back_attrs(store: Neo4jStore, policy_name: str, attrs: dict):
    """将抽取的属性写回 Neo4j Policy 节点"""
    # 只写非空属性
    updates = {k: v for k, v in attrs.items() if v is not None and v != "" and v != []}

    if not updates:
        logger.debug(f"无属性可写入: {policy_name}")
        return 0

    set_clauses = [f"p.{k} = ${k}" for k in updates]
    cypher = f"MATCH (p:Policy {{name: $name}}) SET {', '.join(set_clauses)}"

    try:
        with store.driver.session(database=store.database) as session:
            params = {"name": policy_name}
            params.update(updates)
            session.run(cypher, **params)
        logger.debug(f"写入成功: {policy_name} → {list(updates.keys())}")
        return len(updates)
    except Exception as e:
        logger.warning(f"写入失败: {policy_name} - {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="历史 Policy 申报属性补抽")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写 Neo4j")
    parser.add_argument("--policy", type=str, help="只处理指定政策名")
    parser.add_argument("--force", action="store_true", help="强制覆盖已有属性")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 个政策（0=不限）")
    args = parser.parse_args()

    logger.info(f"{'[DRY-RUN] ' if args.dry_run else ''}Policy 申报属性补抽启动")

    # 初始化
    store = Neo4jStore(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
    )
    llm = get_llm_client()

    # 查询所有 Policy
    with store.driver.session(database=store.database) as session:
        if args.policy:
            result = session.run(
                "MATCH (p:Policy {name: $name}) RETURN p.name AS name, p.source_file AS sf",
                name=args.policy,
            )
        else:
            result = session.run(
                "MATCH (p:Policy) RETURN p.name AS name, p.source_file AS sf"
            )
        policies = [(r["name"], r["sf"]) for r in result]

    logger.info(f"共 {len(policies)} 个 Policy 节点")

    # 过滤已有属性的政策（除非 --force）
    if not args.force:
        with store.driver.session(database=store.database) as session:
            result = session.run(
                "MATCH (p:Policy) WHERE p.deadline IS NOT NULL OR p.required_materials IS NOT NULL "
                "RETURN p.name AS name"
            )
            already_done = {r["name"] for r in result}
        policies = [(n, sf) for n, sf in policies if n not in already_done]
        logger.info(f"过滤已有属性后剩余 {len(policies)} 个待处理")

    if args.limit > 0:
        policies = policies[:args.limit]
        logger.info(f"限制处理前 {args.limit} 个")

    # 逐个处理
    stats = {"total": len(policies), "success": 0, "skipped": 0, "failed": 0, "attrs_written": 0}

    for i, (policy_name, source_file) in enumerate(policies, 1):
        logger.info(f"[{i}/{stats['total']}] 处理: {policy_name}")

        # 找 chunked.json
        if not source_file:
            logger.debug(f"  跳过: 无 source_file")
            stats["skipped"] += 1
            continue

        chunked_path = find_chunked_file(source_file)
        if not chunked_path:
            logger.debug(f"  跳过: 找不到 chunked 文件 ({source_file})")
            stats["skipped"] += 1
            continue

        # 加载原文
        try:
            policy_text = load_policy_text(chunked_path)
        except Exception as e:
            logger.warning(f"  加载原文失败: {e}")
            stats["failed"] += 1
            continue

        if not policy_text.strip():
            logger.debug(f"  跳过: 原文为空")
            stats["skipped"] += 1
            continue

        # LLM 抽取
        try:
            attrs = extract_application_attrs(llm, policy_text)
        except Exception as e:
            logger.warning(f"  LLM 抽取失败: {e}")
            stats["failed"] += 1
            continue

        if not attrs:
            logger.debug(f"  跳过: LLM 返回空")
            stats["skipped"] += 1
            continue

        # 显示抽取结果
        non_empty = {k: v for k, v in attrs.items() if v is not None and v != "" and v != []}
        if non_empty:
            logger.info(f"  抽取到 {len(non_empty)} 个属性: {list(non_empty.keys())}")
        else:
            logger.debug(f"  抽取结果全部为空")
            stats["skipped"] += 1
            continue

        # 写回 Neo4j
        if args.dry_run:
            logger.info(f"  [DRY-RUN] 将写入: {non_empty}")
            stats["success"] += 1
        else:
            written = write_back_attrs(store, policy_name, attrs)
            if written > 0:
                stats["success"] += 1
                stats["attrs_written"] += written
            else:
                stats["skipped"] += 1

        # 限速：避免 LLM API 过载
        time.sleep(1)

    # 汇总
    logger.info(f"{'[DRY-RUN] ' if args.dry_run else ''}补抽完成:")
    logger.info(f"  总数: {stats['total']}")
    logger.info(f"  成功: {stats['success']}")
    logger.info(f"  跳过: {stats['skipped']}")
    logger.info(f"  失败: {stats['failed']}")
    logger.info(f"  属性写入: {stats['attrs_written']} 个")

    store.close()


if __name__ == "__main__":
    main()
