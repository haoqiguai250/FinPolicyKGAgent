"""
意图识别器

解析用户自然语言查询 → 结构化企业画像
企业画像用于图遍历的起始条件匹配
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from src.extraction.llm_client import DeepSeekClient, get_llm_client
from src.extraction.schema import CONDITION_ENUMS, REGION_HIERARCHY


# ── Prompt ──

INTENT_SYSTEM_PROMPT = """你是一个金融政策咨询意图分析器。请从用户的咨询问题中提取企业画像信息。

需要提取的字段：
1. **region**: 企业所在地区（中文省市名，如"深圳"、"广东"、"中国"）
2. **company_type**: 企业类型（仅限以下选项）
   {company_type_options}
3. **industry**: 所属行业（仅限以下选项）
   {industry_options}

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
  "intent_summary": "用户意图一句话概括"
}}

注意：
- 不确定的字段填 null
- 不要编造用户未提及的信息
- 地区匹配时考虑层级（如"深圳"同时也匹配"广东"和"中国"）"""

INTENT_USER_PROMPT = """请分析以下用户咨询：

{query}

请提取企业画像，严格按 JSON 格式输出。"""


@dataclass
class EnterpriseProfile:
    """企业画像"""
    region: Optional[str] = None
    company_type: Optional[str] = None
    industry: Optional[str] = None
    intent_summary: str = ""

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

    def to_dict(self) -> dict:
        return {
            "region": self.region,
            "company_type": self.company_type,
            "industry": self.industry,
            "intent_summary": self.intent_summary,
        }


class IntentRecognizer:
    """意图识别：自然语言 → 企业画像"""

    def __init__(self, llm_client: Optional[DeepSeekClient] = None):
        self.llm = llm_client or get_llm_client()
        self._system_prompt = self._build_system_prompt()

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
        try:
            raw = self.llm.chat_json(
                system_prompt=self._system_prompt,
                user_prompt=INTENT_USER_PROMPT.format(query=query),
                temperature=0.1,
            )

            if not isinstance(raw, dict):
                logger.warning(f"意图识别返回非 dict: {type(raw)}")
                return EnterpriseProfile(intent_summary=query)

            profile = EnterpriseProfile(
                region=raw.get("region") or None,
                company_type=raw.get("company_type") or None,
                industry=raw.get("industry") or None,
                intent_summary=raw.get("intent_summary", query),
            )

            # 校验枚举值
            if profile.company_type and profile.company_type not in CONDITION_ENUMS["company_type"]:
                logger.warning(f"company_type '{profile.company_type}' 不在枚举中，置为 null")
                profile.company_type = None
            if profile.industry and profile.industry not in CONDITION_ENUMS["industry"]:
                logger.warning(f"industry '{profile.industry}' 不在枚举中，置为 null")
                profile.industry = None

            logger.info(f"意图识别: {profile.to_dict()}")
            return profile

        except Exception as e:
            logger.error(f"意图识别异常: {e}")
            return EnterpriseProfile(intent_summary=query)
