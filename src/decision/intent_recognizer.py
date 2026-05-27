"""
意图识别器

解析用户自然语言查询 → 结构化企业画像
企业画像用于图遍历的起始条件匹配
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from src.extraction.llm_client import get_llm_client, UniversalLLMClient
from src.extraction.schema import CONDITION_ENUMS, REGION_HIERARCHY


# ── Prompt ──

INTENT_SYSTEM_PROMPT = """你是一个金融政策申报助手，负责从用户的咨询中提取企业画像信息。

需要提取的字段：
1. **region**: 企业所在地区（中文省市名，如"深圳"、"广东"、"中国"）
2. **company_type**: 企业类型（仅限以下选项）
   {company_type_options}
3. **industry**: 所属行业（仅限以下选项）
   {industry_options}
4. **employees**: 员工人数（整数，如 35）
5. **annual_revenue**: 年营收（万元，如 800 表示 800 万）
6. **established_date**: 成立时间（YYYY-MM 或 YYYY 格式，如"2022-03"）
7. **is_high_tech**: 是否高新技术企业（true/false/null）
8. **is_sme**: 是否中小微企业（true/false/null）
9. **patents**: 专利/知识产权数量（整数）
10. **qualifications**: 资质列表（如["专精特新","瞪羚企业"]，没有则 []）
11. **registered_capital**: 注册资本（万元）
12. **rd_ratio**: 研发费用占比（%，如 5.2 表示 5.2%）
13. **target_subsidy**: 目标补贴类型（融资/税收/人才/研发/财政/投资，null 则不限定）

已知地区层级关系：
- 深圳 ⊂ 广东 ⊂ 中国
- 北京 ⊂ 中国
- 上海 ⊂ 中国
- 广州 ⊂ 广东
- 杭州 ⊂ 浙江 ⊂ 中国
- 成都 ⊂ 四川 ⊂ 中国

【输出格式】严格 JSON：
{{
  "region": "地区名或null",
  "company_type": "企业类型枚举或null",
  "industry": "行业枚举或null",
  "employees": 数字或null,
  "annual_revenue": 数字或null,
  "established_date": "YYYY-MM或null",
  "is_high_tech": true/false/null,
  "is_sme": true/false/null,
  "patents": 数字或null,
  "qualifications": ["资质1","资质2"],
  "registered_capital": 数字或null,
  "rd_ratio": 数字或null,
  "intent_summary": "用户意图一句话概括",
  "target_subsidy": "目标类型或null"
}}

注意：
- 不确定的字段填 null，不要编造用户未提及的信息
- 地区匹配时考虑层级（如"深圳"同时也匹配"广东"和"中国"）
- 营收/注册资本单位统一为"万元"
- qualifications 是数组，没有则为空数组 []"""

INTENT_USER_PROMPT = """请分析以下用户咨询，提取完整的企业画像：

{query}

请严格按 JSON 格式输出，所有字段都必须包含（缺失填 null）。"""


@dataclass
class EnterpriseProfile:
    """企业画像 — Phase 1 扩展版（15 字段）"""
    # ── 基础信息（原有） ──
    region: Optional[str] = None              # 企业所在地区
    company_type: Optional[str] = None        # 企业类型
    industry: Optional[str] = None            # 所属行业
    # ── 规模信息（新增） ──
    employees: Optional[int] = None           # 员工人数
    annual_revenue: Optional[float] = None    # 年营收（万元）
    established_date: Optional[str] = None    # 成立时间（YYYY-MM 或 YYYY）
    # ── 资质信息（新增） ──
    is_high_tech: Optional[bool] = None       # 是否高新技术企业
    is_sme: Optional[bool] = None             # 是否中小微企业
    patents: Optional[int] = None             # 专利数量
    qualifications: list[str] = field(default_factory=list)  # 资质列表（如专精特新、瞪羚企业）
    # ── 经营信息（新增） ──
    registered_capital: Optional[float] = None  # 注册资本（万元）
    rd_ratio: Optional[float] = None            # 研发费用占比（%）
    # ── 意图信息（原有） ──
    intent_summary: str = ""                  # 意图摘要
    target_subsidy: Optional[str] = None      # 目标补贴类型（融资/税收/人才/研发...）

    # 扩展匹配：region 层级链（用于图遍历）
    def get_region_chain(self) -> list[str]:
        """获取 region 层级链（含自身），如 ["深圳", "广东", "中国"]"""
        if not self.region:
            return []
        chain = [self.region]
        current = self.region
        while current in REGION_HIERARCHY:
            parent = REGION_HIERARCHY[current]
            chain.append(parent)
            current = parent
        return chain

    def get_years_since_established(self) -> Optional[float]:
        """计算企业成立年数，返回 None 如果未填写或无法解析"""
        if not self.established_date:
            return None
        import re
        from datetime import datetime
        try:
            # 支持 YYYY-MM 或 YYYY
            m = re.match(r"(\d{4})(?:-(\d{1,2}))?", self.established_date)
            if not m:
                return None
            year = int(m.group(1))
            month = int(m.group(2) or 1)
            established = datetime(year, month, 1)
            now = datetime.now()
            return (now - established).days / 365.25
        except Exception:
            return None

    def to_dict(self) -> dict:
        return {
            "region": self.region,
            "company_type": self.company_type,
            "industry": self.industry,
            "employees": self.employees,
            "annual_revenue": self.annual_revenue,
            "established_date": self.established_date,
            "is_high_tech": self.is_high_tech,
            "is_sme": self.is_sme,
            "patents": self.patents,
            "qualifications": self.qualifications,
            "registered_capital": self.registered_capital,
            "rd_ratio": self.rd_ratio,
            "intent_summary": self.intent_summary,
            "target_subsidy": self.target_subsidy,
        }

    def to_query(self) -> str:
        """自动拼成 Advisor 查询问题"""
        parts = [p for p in [self.region, self.company_type, self.industry] if p]
        if not parts:
            return "能享受什么政策补贴？"
        return f"{' '.join(parts)} 能享受什么政策补贴？"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "EnterpriseProfile":
        """从 JSON 文件加载企业画像"""
        from config.settings import settings as _settings
        path = path or _settings.ENTERPRISE_PROFILE_FILE
        if not path.exists():
            logger.warning(f"企业画像文件不存在: {path}，使用空画像")
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = cls(
            region=data.get("region"),
            company_type=data.get("company_type"),
            industry=data.get("industry"),
            employees=data.get("employees"),
            annual_revenue=data.get("annual_revenue"),
            established_date=data.get("established_date"),
            is_high_tech=data.get("is_high_tech"),
            is_sme=data.get("is_sme"),
            patents=data.get("patents"),
            qualifications=data.get("qualifications", []),
            registered_capital=data.get("registered_capital"),
            rd_ratio=data.get("rd_ratio"),
            intent_summary=data.get("intent_summary", ""),
            target_subsidy=data.get("target_subsidy"),
        )
        logger.info(f"加载企业画像: {profile.to_query()}")
        return profile


class IntentRecognizer:
    """意图识别：自然语言 → 企业画像"""

    def __init__(self, llm_client: Optional[UniversalLLMClient] = None):
        # 意图识别必须用非 reasoning 客户端，否则 temperature 不生效导致结果不确定
        # 如果传入的是 reasoning 客户端，则忽略，使用默认的非 reasoning 客户端
        if llm_client and not llm_client.reasoning_effort:
            self.llm = llm_client
        else:
            self.llm = get_llm_client()
        self._system_prompt = self._build_system_prompt()
        # query → profile 缓存，同一 query 绝对返回同一 profile
        self._cache: dict[str, EnterpriseProfile] = {}

    def _build_system_prompt(self) -> str:
        company_type_options = "、".join(CONDITION_ENUMS["company_type"])
        industry_options = "、".join(CONDITION_ENUMS["industry"])
        return INTENT_SYSTEM_PROMPT.format(
            company_type_options=company_type_options,
            industry_options=industry_options,
        )

    def recognize(self, query: str) -> EnterpriseProfile:
        """
        识别用户查询中的企业画像

        Args:
            query: 用户自然语言查询

        Returns:
            EnterpriseProfile
        """
        # 缓存命中：同一 query 返回相同 profile，保证确定性
        cache_key = query.strip()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.info(f"意图识别命中缓存: {cached.to_dict()}")
            return cached

        try:
            raw = self.llm.chat_json(
                system_prompt=self._system_prompt,
                user_prompt=INTENT_USER_PROMPT.format(query=query),
                temperature=0,  # 意图识别必须 0 温度，确保确定性
            )

            if not isinstance(raw, dict):
                logger.warning(f"意图识别返回非 dict: {type(raw)}")
                return EnterpriseProfile(intent_summary=query)

            profile = EnterpriseProfile(
                region=raw.get("region") or None,
                company_type=raw.get("company_type") or None,
                industry=raw.get("industry") or None,
                employees=raw.get("employees") if isinstance(raw.get("employees"), int) else None,
                annual_revenue=raw.get("annual_revenue") if isinstance(raw.get("annual_revenue"), (int, float)) else None,
                established_date=raw.get("established_date") or None,
                is_high_tech=raw.get("is_high_tech") if isinstance(raw.get("is_high_tech"), bool) else None,
                is_sme=raw.get("is_sme") if isinstance(raw.get("is_sme"), bool) else None,
                patents=raw.get("patents") if isinstance(raw.get("patents"), int) else None,
                qualifications=raw.get("qualifications") if isinstance(raw.get("qualifications"), list) else [],
                registered_capital=raw.get("registered_capital") if isinstance(raw.get("registered_capital"), (int, float)) else None,
                rd_ratio=raw.get("rd_ratio") if isinstance(raw.get("rd_ratio"), (int, float)) else None,
                intent_summary=raw.get("intent_summary", query),
                target_subsidy=raw.get("target_subsidy") or None,
            )

            # 校验枚举值
            if profile.company_type and profile.company_type not in CONDITION_ENUMS["company_type"]:
                logger.warning(f"company_type '{profile.company_type}' 不在枚举中，置为 null")
                profile.company_type = None
            if profile.industry and profile.industry not in CONDITION_ENUMS["industry"]:
                logger.warning(f"industry '{profile.industry}' 不在枚举中，置为 null")
                profile.industry = None

            logger.info(f"意图识别(LLM): {profile.to_dict()}")
            self._cache[cache_key] = profile
            return profile

        except Exception as e:
            logger.error(f"意图识别异常: {e}")
            profile = EnterpriseProfile(intent_summary=query)
            self._cache[cache_key] = profile
            return profile
