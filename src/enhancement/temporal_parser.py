"""
时序解析器

处理政策文本中的模糊时间表达，将时间属性注入三元组。

支持的模糊表达：
- "自发布之日起施行" → 使用政策发布日期
- "自公布之日起施行" → 使用政策发布日期
- "即日起" → 使用当前日期
- "有效期X年" → 从发布日期计算到期日

无法解析的时间 → 留空，不硬猜
"""

import re
from datetime import datetime, date, timedelta
from typing import Optional

from loguru import logger

from src.extraction.schema import Triple


# ── 模糊日期模式 ──

FUZZY_DATE_PATTERNS: dict[str, str] = {
    "自发布之日起施行": "use_publish_date",
    "自公布之日起施行": "use_publish_date",
    "自公布之日起": "use_publish_date",
    "自发布之日起": "use_publish_date",
    "即日起": "use_today",
    "即日起施行": "use_today",
    "即日起执行": "use_today",
}

# 有效期模式：有效期X年 / 有效期X个月
_VALIDITY_YEAR_PATTERN = re.compile(r"有效期[为]?(\d+)年")
_VALIDITY_MONTH_PATTERN = re.compile(r"有效期[为]?(\d+)[个]?月")

# ISO 日期模式
_ISO_DATE_PATTERN = re.compile(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日号]?")


def parse_temporal_expressions(
    text: str,
    publish_date: str | None = None,
) -> dict:
    """
    从文本中解析时间信息

    Args:
        text: 政策文本
        publish_date: 政策发布日期（ISO 格式），用于解析"自发布之日起"

    Returns:
        解析结果 dict，包含 effective_date, expiry_date, status 等
    """
    result = {
        "effective_date": None,
        "expiry_date": None,
        "status": None,
    }

    if not text:
        return result

    # 1. 尝试匹配精确日期
    iso_match = _ISO_DATE_PATTERN.search(text)
    if iso_match:
        try:
            year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            result["effective_date"] = f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            pass

    # 2. 模糊日期模式
    for pattern, strategy in FUZZY_DATE_PATTERNS.items():
        if pattern in text:
            if strategy == "use_publish_date" and publish_date:
                result["effective_date"] = publish_date
            elif strategy == "use_today":
                result["effective_date"] = date.today().isoformat()
            break

    # 3. 有效期模式
    year_match = _VALIDITY_YEAR_PATTERN.search(text)
    month_match = _VALIDITY_MONTH_PATTERN.search(text)

    base_date_str = result.get("effective_date") or publish_date
    if base_date_str:
        try:
            base_date = datetime.strptime(base_date_str, "%Y-%m-%d").date()
            if year_match:
                years = int(year_match.group(1))
                result["expiry_date"] = (base_date + timedelta(days=365 * years)).isoformat()
            elif month_match:
                months = int(month_match.group(1))
                result["expiry_date"] = (base_date + timedelta(days=30 * months)).isoformat()
        except ValueError:
            pass

    # 4. 废止状态检测
    if "废止" in text or "废除" in text or "取消" in text:
        # 检查是否是"本文废止XXX"的格式（不是"XXX废止本文"）
        if re.search(r"(废止|废除|取消了?)", text):
            result["status"] = "repealed"

    # 默认 status
    if result["status"] is None and result["effective_date"]:
        result["status"] = "active"

    return result


def temporal_enrichment(
    triple: Triple,
    publish_date: str | None = None,
    source_text: str | None = None,
) -> None:
    """
    将时序属性注入三元组

    如果三元组的 subject 是 Policy，从 source_text 中解析时间信息
    并注入到 subject 的 attributes 中。

    Args:
        triple: 待注入的三元组
        publish_date: 政策发布日期（ISO 格式）
        source_text: 原文依据
    """
    if triple.subject.entity_type != "Policy":
        return

    text = source_text or triple.source_text
    if not text:
        return

    # 如果 attributes 中已有时间信息，不覆盖
    attrs = triple.subject.attributes
    if attrs.get("effective_date") and attrs.get("expiry_date"):
        return

    parsed = parse_temporal_expressions(text, publish_date)

    # 只填充缺失的字段
    if parsed.get("effective_date") and not attrs.get("effective_date"):
        attrs["effective_date"] = parsed["effective_date"]
    if parsed.get("expiry_date") and not attrs.get("expiry_date"):
        attrs["expiry_date"] = parsed["expiry_date"]
    if parsed.get("status") and not attrs.get("status"):
        attrs["status"] = parsed["status"]


def compute_policy_status(expiry_date: str | None, status: str | None) -> str:
    """
    计算政策的当前状态

    Args:
        expiry_date: 失效日期（ISO 格式）
        status: 已标注的状态

    Returns:
        "active" | "repealed" | "expiring_soon" | null
    """
    if status == "repealed":
        return "repealed"

    if expiry_date:
        try:
            exp = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            today = date.today()
            if exp < today:
                return "repealed"  # 已过期
            elif (exp - today).days <= 90:
                return "expiring_soon"  # 即将过期
        except ValueError:
            pass

    if status == "active":
        return "active"

    return ""  # 无状态信息
