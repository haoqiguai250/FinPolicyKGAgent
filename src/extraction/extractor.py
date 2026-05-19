"""
Stage 3a: Schema 引导三元组抽取模块
将 Schema 定义注入 LLM Prompt，在闭域内抽取结构化三元组

流程：
1. 接收 chunk 文本
2. 将文本按句拆分并编号
3. 构造 Schema 引导的抽取 Prompt（含句子编号）
4. 调用 LLM 生成初始三元组 JSON
5. Schema 校验 + 后处理
"""

import json
import re
from typing import Optional

from loguru import logger

from src.extraction.schema import (
    Entity, Triple, SCHEMA_PROMPT,
    ENTITY_HIERARCHY,
)
from src.extraction.llm_client import get_llm_client, UniversalLLMClient
from src.ingestion.chunker import Chunk


# ── 句子拆分 ──

# 中文句末标点 + 换行
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。；！？\n])")


def split_into_sentences(text: str) -> list[str]:
    """
    将文本按句末标点拆分为句子列表

    Returns:
        非空句子列表（保留原始文本，不做 strip 以便精确定位）
    """
    parts = _SENTENCE_SPLIT_PATTERN.split(text)
    return [p for p in parts if p.strip()]


def number_sentences(text: str) -> tuple[str, list[str]]:
    """
    将文本按句拆分并添加编号标注

    Args:
        text: 原始文本

    Returns:
        (numbered_text, sentences):
        - numbered_text: 带编号的文本，如 "[1]第一句话。[2]第二句话。"
        - sentences: 句子列表（原始文本，无编号）
    """
    sentences = split_into_sentences(text)
    numbered_parts = []
    for i, sent in enumerate(sentences, 1):
        numbered_parts.append(f"[{i}]{sent}")
    numbered_text = "".join(numbered_parts)
    return numbered_text, sentences


# ── Prompt 模板 ──

EXTRACT_SYSTEM_PROMPT = """你是一个金融政策信息抽取专家。请从给定的政策文本中抽取结构化三元组。

{schema_prompt}

【抽取规则】
1. 只抽取文本中明确提及的实体和关系，不要推测
2. 每个实体必须指定类型（从允许的实体类型中选择）
3. 每个关系必须符合 Schema 约束（主语/宾语类型匹配）
4. 实体名称使用原文表述，不要自行改写
5. sets 关系必须附带具体数值
6. 注意区分政策语义："鼓励"≠"强制"、"原则上"≠"必须"
7. 如有已抽取实体上下文，避免重复抽取

【原文句子编号说明】
文本中每句话前有 [编号] 标记，如 [1]第一句话。[2]第二句话。
请在每个三元组中标注 source_sentence_index，表示该三元组的依据来自第几句（1-based）。
如果三元组依据涉及多句，取最关键的那句的编号。

【输出格式】
请输出 JSON，格式如下：
{{
  "entities": [
    {{"name": "实体名", "type": "EntityType", "attributes": {{}}}}
  ],
  "triples": [
    {{
      "subject": {{"name": "主语", "type": "EntityType"}},
      "relation": "关系类型",
      "object": {{"name": "宾语", "type": "EntityType"}},
      "source_text": "原文依据",
      "source_sentence_index": 1
    }}
  ]
}}
"""

EXTRACT_USER_PROMPT = """【待抽取文本】
{chunk_text}

【已抽取实体上下文】
{existing_entities}

请从上述政策文本中抽取结构化三元组，并标注每个三元组的 source_sentence_index。"""


class SchemaGuidedExtractor:
    """Schema 引导的三元组抽取器"""

    def __init__(self, llm_client: Optional[UniversalLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    def extract(
        self,
        chunk: Chunk,
        existing_entities: Optional[list[Entity]] = None,
    ) -> tuple[list[Entity], list[Triple]]:
        """
        从单个 chunk 中抽取三元组

        Args:
            chunk: 文本分块
            existing_entities: 已抽取的实体（避免重复）

        Returns:
            (entities, triples): 抽取到的实体和三元组
        """
        # 将 chunk 文本按句编号
        numbered_text, sentences = number_sentences(chunk.text)

        # 构造 Prompt
        entity_context = self._format_existing_entities(existing_entities or [])
        system = EXTRACT_SYSTEM_PROMPT.format(schema_prompt=SCHEMA_PROMPT)
        user = EXTRACT_USER_PROMPT.format(
            chunk_text=numbered_text,
            existing_entities=entity_context,
        )

        logger.info(f"抽取三元组: {chunk.chunk_id} ({len(chunk.text)} 字符, {len(sentences)} 句)")

        # 调用 LLM
        result = self.llm.chat_json(
            system_prompt=system,
            user_prompt=user,
            temperature=0.1,
        )

        # 解析结果（传入句子列表用于回溯原文）
        entities = self._parse_entities(result.get("entities", []), chunk.chunk_id)
        triples = self._parse_triples(
            result.get("triples", []), chunk.chunk_id, sentences
        )

        # Schema 校验
        valid_triples = []
        for t in triples:
            issues = t.validate()
            if issues:
                logger.warning(f"三元组校验不通过（已过滤）: {t.to_dict()} | 问题: {issues}")
            else:
                valid_triples.append(t)

        logger.info(f"抽取完成: {len(entities)} 个实体, {len(valid_triples)} 个三元组"
                     f"（过滤 {len(triples) - len(valid_triples)} 个不合规）")
        return entities, valid_triples

    def _format_existing_entities(self, entities: list[Entity]) -> str:
        """格式化已抽取实体列表"""
        if not entities:
            return "（无，这是首次抽取）"
        lines = [f"- {e.name} ({e.entity_type})" for e in entities]
        return "\n".join(lines)

    def _parse_entities(self, raw_list: list[dict], chunk_id: str) -> list[Entity]:
        """解析 LLM 输出的实体列表"""
        entities = []
        for item in raw_list:
            name = item.get("name", "").strip()
            etype = item.get("type", "").strip()
            attrs = item.get("attributes", {})

            if not name or not etype:
                continue

            # 安全兜底：category 必须是字符串（LLM 可能输出 list）
            if isinstance(attrs, dict) and "category" in attrs:
                cat = attrs["category"]
                if isinstance(cat, list):
                    attrs["category"] = cat[0] if cat else ""
                elif cat is None:
                    attrs["category"] = ""

            # 类型归一化：子类也接受
            entity = Entity(
                name=name,
                entity_type=etype,
                attributes=attrs if isinstance(attrs, dict) else {},
                source_chunk_id=chunk_id,
            )
            entities.append(entity)
        return entities

    def _parse_triples(
        self,
        raw_list: list[dict],
        chunk_id: str,
        sentences: Optional[list[str]] = None,
    ) -> list[Triple]:
        """
        解析 LLM 输出的三元组列表

        Args:
            raw_list: LLM 输出的原始三元组列表
            chunk_id: chunk ID
            sentences: 句子列表（用于回溯原文）
        """
        triples = []
        for item in raw_list:
            subj_raw = item.get("subject", {})
            obj_raw = item.get("object", {})
            relation = item.get("relation", "").strip()
            source_text = item.get("source_text", "")
            sentence_idx = item.get("source_sentence_index", -1)

            if not subj_raw or not obj_raw or not relation:
                continue

            subject = Entity(
                name=subj_raw.get("name", ""),
                entity_type=subj_raw.get("type", ""),
                source_chunk_id=chunk_id,
            )
            object_ = Entity(
                name=obj_raw.get("name", ""),
                entity_type=obj_raw.get("type", ""),
                source_chunk_id=chunk_id,
            )

            # 校验 sentence_index 合法性
            if isinstance(sentence_idx, int) and sentence_idx >= 1 and sentences and sentence_idx <= len(sentences):
                pass  # 合法
            elif isinstance(sentence_idx, str):
                # LLM 可能输出字符串形式的数字
                try:
                    sentence_idx = int(sentence_idx)
                    if not (sentence_idx >= 1 and sentences and sentence_idx <= len(sentences)):
                        sentence_idx = -1
                except ValueError:
                    sentence_idx = -1
            else:
                sentence_idx = -1

            triple = Triple(
                subject=subject,
                relation=relation,
                object_=object_,
                source_text=source_text,
                source_chunk_id=chunk_id,
                source_sentence_index=sentence_idx,
            )
            triples.append(triple)
        return triples
