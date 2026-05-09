"""
Action + Eligibility 抽取器

从 chunked.json 读取 chunks，一次 LLM 调用同时抽取：
1. Action（措施）→ 标准化为 6 大类 ActionType
2. Eligibility（适用条件）→ 标准化为 Condition 枚举

结果写回 KG（TripletStore），作为节点和边
"""

import json
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger

from src.extraction.schema import (
    Entity, Triple,
    ACTION_CATEGORIES, ACTION_KEYWORD_MAP,
    CONDITION_ENUMS, REGION_HIERARCHY,
)
from src.extraction.llm_client import DeepSeekClient, get_llm_client


# ── Prompt 模板 ──

ACTION_ELIGIBILITY_SYSTEM_PROMPT = """你是一个金融政策分析专家。请从政策文本中抽取以下两类信息：

1. **措施 (Action)**：政策提供的具体支持措施，如贷款、补贴、减税等
2. **适用条件 (Eligibility)**：政策适用的对象条件，包括地区、企业类型、行业

【措施 6 大类定义】
{action_categories_text}

【适用条件枚举】
企业类型（仅限以下选项，不匹配则为 null）:
{company_type_options}

行业（仅限以下选项，不匹配则为 null）:
{industry_options}

地区（中文省市名，如"深圳"、"广东"、"中国"等）

【输出格式】严格 JSON：
{{
  "actions": [
    {{"raw": "原始短语", "type": "6大类之一"}}
  ],
  "eligibility": {{
    "region": "地区名或null",
    "company_type": "企业类型枚举之一或null",
    "industry": "行业枚举之一或null"
  }}
}}

注意：
- actions 列表可为空（文本无措施时）
- eligibility 中不匹配的字段填 null
- 不要编造文本中未提及的信息
"""

ACTION_ELIGIBILITY_USER_PROMPT = """请从以下政策文本中抽取措施和适用条件：

【政策文本】
{chunk_text}

请严格按 JSON 格式输出。"""


@dataclass
class ExtractionResult:
    """单 chunk 抽取结果"""
    chunk_id: str
    policy_name: str = ""
    actions: list[dict] = field(default_factory=list)       # [{raw, type}]
    eligibility: dict = field(default_factory=dict)         # {region, company_type, industry}
    raw_llm_output: str = ""


class ActionEligibilityExtractor:
    """Action + Eligibility 一次抽取 + 标准化"""

    def __init__(self, llm_client: Optional[DeepSeekClient] = None):
        self.llm = llm_client or get_llm_client()
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """构建包含枚举定义的 system prompt"""
        # 格式化 Action 类别
        cat_lines = []
        for cat, keywords in ACTION_CATEGORIES.items():
            cat_lines.append(f"  {cat}: {'/'.join(keywords)}")
        action_categories_text = "\n".join(cat_lines)

        company_type_options = "、".join(CONDITION_ENUMS["company_type"])
        industry_options = "、".join(CONDITION_ENUMS["industry"])

        return ACTION_ELIGIBILITY_SYSTEM_PROMPT.format(
            action_categories_text=action_categories_text,
            company_type_options=company_type_options,
            industry_options=industry_options,
        )

    def extract_from_chunk(self, chunk_text: str, chunk_id: str = "") -> ExtractionResult:
        """
        从单个 chunk 抽取 Action + Eligibility

        Args:
            chunk_text: chunk 文本
            chunk_id: chunk 标识

        Returns:
            ExtractionResult
        """
        result = ExtractionResult(chunk_id=chunk_id)

        try:
            raw = self.llm.chat_json(
                system_prompt=self._system_prompt,
                user_prompt=ACTION_ELIGIBILITY_USER_PROMPT.format(chunk_text=chunk_text),
                temperature=0.1,
            )

            # 防御：确保返回 dict
            if not isinstance(raw, dict):
                logger.warning(f"chunk {chunk_id}: LLM 返回非 dict，跳过")
                return result

            # 解析 actions
            actions_raw = raw.get("actions", [])
            if isinstance(actions_raw, list):
                for a in actions_raw:
                    if isinstance(a, dict) and "raw" in a:
                        action_type = self._standardize_action(a.get("raw", ""), a.get("type", ""))
                        if action_type:
                            result.actions.append({
                                "raw": a["raw"],
                                "type": action_type,
                            })
                    elif isinstance(a, str):
                        # LLM 有时直接返回字符串
                        action_type = self._standardize_action(a, "")
                        if action_type:
                            result.actions.append({"raw": a, "type": action_type})

            # 解析 eligibility
            elig = raw.get("eligibility", {})
            if isinstance(elig, dict):
                result.eligibility = {
                    "region": self._standardize_region(elig.get("region")),
                    "company_type": self._standardize_enum(
                        elig.get("company_type"), "company_type"
                    ),
                    "industry": self._standardize_enum(
                        elig.get("industry"), "industry"
                    ),
                }
            else:
                result.eligibility = {"region": None, "company_type": None, "industry": None}

            result.raw_llm_output = json.dumps(raw, ensure_ascii=False)

        except Exception as e:
            logger.error(f"chunk {chunk_id} 抽取失败: {e}")

        return result

    def extract_from_chunks(self, chunks: list[dict], max_workers: int = 32) -> list[ExtractionResult]:
        """
        批量从 chunks 抽取（并行）

        Args:
            chunks: chunked.json 中的 chunks 列表，每个需含 text 和 chunk_id
            max_workers: 最大并行数

        Returns:
            抽取结果列表（按原始 chunk 顺序）
        """
        total = len(chunks)
        print_lock = threading.Lock()

        def _extract_one(idx: int, chunk: dict) -> tuple[int, ExtractionResult]:
            chunk_id = chunk.get("chunk_id", f"chunk_{idx+1}")
            chunk_text = chunk.get("text", "")
            if not chunk_text.strip():
                return idx, None
            result = self.extract_from_chunk(chunk_text, chunk_id)
            result.policy_name = chunk.get("policy_name", "")
            with print_lock:
                logger.info(f"抽取 chunk {idx+1}/{total}: {chunk_id}")
            return idx, result

        logger.info(f"并行补图抽取: {total} chunks, {max_workers} 并发")
        _results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_map = {
                executor.submit(_extract_one, i, chunk): i
                for i, chunk in enumerate(chunks)
            }
            for fut in as_completed(fut_map):
                idx, result = fut.result()
                if result is not None:
                    _results[idx] = result

        # 按原始顺序排列
        results = [_results[i] for i in sorted(_results.keys())]

        logger.info(f"批量抽取完成: {total} chunks, {len(results)} 个有结果")
        return results

    # ── 标准化方法 ──

    @staticmethod
    def _standardize_action(raw_text: str, llm_type: str) -> Optional[str]:
        """
        将原始短语标准化为 6 大类

        优先级：
        1. 如果 LLM 给出的 type 是合法 6 大类，直接用
        2. 否则用关键词映射
        3. 都不匹配则尝试模糊匹配
        """
        # 1. LLM 给出的 type 直接匹配
        if llm_type in ACTION_CATEGORIES:
            return llm_type

        # 2. 关键词映射
        raw_lower = raw_text.strip()
        for keyword, category in ACTION_KEYWORD_MAP.items():
            if keyword in raw_lower:
                return category

        # 3. 模糊匹配（包含关系）
        for cat, keywords in ACTION_CATEGORIES.items():
            for kw in keywords:
                if kw in raw_lower or raw_lower in kw:
                    return cat

        # 无法匹配
        if raw_text:
            logger.debug(f"Action 无法标准化: '{raw_text}' (llm_type={llm_type})")
        return None

    @staticmethod
    def _standardize_region(region_text: Optional[str]) -> Optional[str]:
        """标准化地区，校验是否在层级定义中"""
        if not region_text or region_text == "null":
            return None
        region_text = region_text.strip()
        # 在层级定义中直接匹配
        if region_text in REGION_HIERARCHY or region_text in REGION_HIERARCHY.values():
            return region_text
        # "中国" 作为顶级
        if region_text == "中国":
            return "中国"
        # 不在定义中的地区，仍然保留（后续可扩展层级定义）
        logger.debug(f"Region 不在层级定义中但仍保留: '{region_text}'")
        return region_text

    @staticmethod
    def _standardize_enum(value: Optional[str], category: str) -> Optional[str]:
        """标准化枚举值（company_type / industry）"""
        if not value or value == "null":
            return None
        value = value.strip()
        allowed = CONDITION_ENUMS.get(category, [])
        # 精确匹配
        if value in allowed:
            return value
        # 模糊匹配（包含关系）
        for opt in allowed:
            if opt in value or value in opt:
                return opt
        # 不匹配
        logger.debug(f"Condition {category} 值 '{value}' 不在枚举中，标记为 null")
        return None
