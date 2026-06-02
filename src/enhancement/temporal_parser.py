"""
时序解析器

处理政策文本中的模糊时间表达，将时间属性注入三元组。

支持的模糊表达：
- "自发布之日起施行" → 使用政策发布日期
- "自公布之日起施行" → 使用政策发布日期
- "即日起" → 使用当前日期
- "有效期X年" → 从发布日期精确计算到期日
- "长期有效" → 哨兵值 2099-12-31

无法解析的时间 → 留空，不硬猜
"""

import re
from datetime import datetime, date
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

# 长期有效模式
_PERMANENT_PATTERNS = ["长期有效", "无期限", "永久有效", "持续有效"]

# 有效期模式：有效期X年 / 有效期X个月
_VALIDITY_YEAR_PATTERN = re.compile(r"有效期[为]?(\d+)年")
_VALIDITY_MONTH_PATTERN = re.compile(r"有效期[为]?(\d+)[个]?月")

# ISO 日期模式
_ISO_DATE_PATTERN = re.compile(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日号]?")

# ── 废止检测：上下文感知 ──

# 本政策被废止的模式
_REPEAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"本(?:政策|办法|规定|条例)\s*(?:已|被|同时)?\s*(?:废止|废除|取消)"),
    re.compile(r"(?:废止|废除|取消)\s*本(?:政策|办法|规定|条例)"),
    re.compile(r"(?:自本(?:法|政策|办法).*?施行之日起).*(?:废止|废除|取消)"),
    re.compile(r"(?:同时|一并)\s*(?:废止|废除|取消)"),
]

# 排除：本政策是废止的主语（废止了旧规定），不是被废止的对象
_REPEAL_EXCLUSION = re.compile(
    r"本(?:政策|办法|规定|条例)\s*(?:废止|废除|取消)\s*(?:了|旧|原|其)"
)


def _check_repeal_status(text: str) -> str | None:
    """
    检测文本中是否表明该政策本身被废止

    上下文感知：
    - "本政策已废止" → repealed
    - "废止本政策" → repealed
    - "本政策废止了旧规定" → None（本政策是废止者，不是被废止者）
    """
    if _REPEAL_EXCLUSION.search(text):
        return None
    for pattern in _REPEAL_PATTERNS:
        if pattern.search(text):
            return "repealed"
    return None


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

    # 3. 长期有效模式
    for pattern in _PERMANENT_PATTERNS:
        if pattern in text:
            result["expiry_date"] = "2099-12-31"
            result["status"] = "active"
            break

    # 4. 有效期模式（精确日期计算）
    year_match = _VALIDITY_YEAR_PATTERN.search(text)
    month_match = _VALIDITY_MONTH_PATTERN.search(text)

    base_date_str = result.get("effective_date") or publish_date
    if base_date_str and not result.get("expiry_date"):
        try:
            base_date = datetime.strptime(base_date_str, "%Y-%m-%d").date()
            if year_match:
                years = int(year_match.group(1))
                try:
                    from dateutil.relativedelta import relativedelta
                    result["expiry_date"] = (base_date + relativedelta(years=years)).isoformat()
                except ImportError:
                    # fallback: 近似计算
                    result["expiry_date"] = (base_date.replace(year=base_date.year + years)).isoformat()
            elif month_match:
                months = int(month_match.group(1))
                try:
                    from dateutil.relativedelta import relativedelta
                    result["expiry_date"] = (base_date + relativedelta(months=months)).isoformat()
                except ImportError:
                    # fallback: 近似计算
                    total_months = base_date.month + months
                    new_year = base_date.year + (total_months - 1) // 12
                    new_month = (total_months - 1) % 12 + 1
                    import calendar
                    max_day = calendar.monthrange(new_year, new_month)[1]
                    new_day = min(base_date.day, max_day)
                    result["expiry_date"] = f"{new_year:04d}-{new_month:02d}-{new_day:02d}"
        except ValueError:
            pass

    # 5. 废止状态检测（上下文感知）
    repeal_status = _check_repeal_status(text)
    if repeal_status:
        result["status"] = repeal_status

    # 默认 status
    if result["status"] is None and result["effective_date"]:
        result["status"] = "active"

    return result


def temporal_enrichment(
    triple: Triple,
    publish_date: str | None = None,
    source_text: str | None = None,
    chunk_text: str | None = None,
) -> None:
    """
    将时序属性注入三元组

    如果三元组的 subject 是 Policy，从 source_text 中解析时间信息
    并注入到 subject 的 attributes 中。

    优先从 source_text 解析，若未解析到时间信息则 fallback 到 chunk_text。

    Args:
        triple: 待注入的三元组
        publish_date: 政策发布日期（ISO 格式）
        source_text: 原文依据（单句）
        chunk_text: chunk 全文（fallback）
    """
    if triple.subject.entity_type != "Policy":
        return

    text = source_text or triple.source_text
    if not text and not chunk_text:
        return

    # 如果 attributes 中已有完整时间信息，不覆盖
    attrs = triple.subject.attributes
    if attrs.get("effective_date") and attrs.get("expiry_date"):
        return

    # 优先从 source_text 解析
    parsed = parse_temporal_expressions(text, publish_date)

    # fallback：source_text 未解析到时间信息时，尝试 chunk 全文
    if chunk_text and not parsed.get("effective_date") and not parsed.get("expiry_date"):
        parsed_chunk = parse_temporal_expressions(chunk_text, publish_date)
        for key in ("effective_date", "expiry_date", "status"):
            if parsed_chunk.get(key) and not parsed.get(key):
                parsed[key] = parsed_chunk[key]

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
