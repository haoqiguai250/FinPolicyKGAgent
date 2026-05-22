"""
Stage 3a: Schema 引导三元组抽取模块
将 Schema 定义注入 LLM Prompt，在闭域内抽取结构化三元组

流程：
1. 接收 chunk 文本
2. 将文本按句拆分并编号
3. 构造 Schema 引导的抽取 Prompt（含句子编号）
4. 调用 LLM 生成初始三元组 JSON
5. Ontology Governance Layer 4步处理：
   - Step 1: 关系归一化（normalize_relation）
   - Step 2: 候选池注册（candidate_pool.add_or_merge）
   - Step 3: 语义分级处理（classify_triple）
   - Step 4: 时序属性注入（temporal_enrichment）
"""

import json
import re
from typing import Optional

from loguru import logger

from src.extraction.schema import (
    Entity, Triple, SCHEMA_PROMPT,
    ENTITY_HIERARCHY, ValidationIssues,
    RELATION_CONSTRAINTS,
)
from src.extraction.llm_client import get_llm_client, UniversalLLMClient
from src.ingestion.chunker import Chunk
from src.enhancement.normalizer import RelationNormalizer
from src.enhancement.candidate_pool import CandidatePool
from src.enhancement.triple_classifier import (
    classify_triple, _get_pool_reason, LEVEL_CONFIG,
    LEVEL_PASS, LEVEL_PASS_PROMOTED, LEVEL_PASS_NORMALIZED,
    LEVEL_PASS_TRUNCATED, LEVEL_POOL, LEVEL_DROP,
)
from src.enhancement.temporal_parser import temporal_enrichment
from config.settings import settings


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
        # 初始化本体治理层组件
        self.normalizer = RelationNormalizer()
        self.pool = CandidatePool(normalizer=self.normalizer)

    def extract(
        self,
        chunk: Chunk,
        existing_entities: Optional[list[Entity]] = None,
        source_file: str = "",
    ) -> tuple[list[Entity], list[Triple]]:
        """
        从单个 chunk 中抽取三元组

        Args:
            chunk: 文本分块
            existing_entities: 已抽取的实体（避免重复）
            source_file: 来源文件名（候选池注册需要）

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

        # ── Ontology Governance Layer 4步处理 ──
        valid_triples = self._apply_governance(triples, source_file)

        logger.info(f"抽取完成: {len(entities)} 个实体, {len(valid_triples)} 个三元组"
                     f"（治理层过滤 {len(triples) - len(valid_triples)} 个）")
        return entities, valid_triples

    def _apply_governance(
        self,
        raw_triples: list[Triple],
        source_file: str = "",
    ) -> list[Triple]:
        """
        Ontology Governance Layer 完整处理流程

        执行顺序（关键！）：归一化 → 候选池注册 → 分级处理 → 时序注入

        Args:
            raw_triples: LLM 输出的原始三元组
            source_file: 来源文件名

        Returns:
            经治理层处理后的合法三元组
        """
        validated = []
        stats = {"pass": 0, "promoted": 0, "normalized": 0, "truncated": 0, "pool": 0, "drop": 0}

        for t in raw_triples:
            # ---- Step 1: 关系归一化（最先执行）----
            original_relation = t.relation
            t.relation, was_normalized, norm_level = self.normalizer.normalize(t.relation)

            # 弱归一：双写，保留原始关系名到 raw_relation
            if was_normalized and norm_level == "weak":
                t.raw_relation = original_relation

            # ---- Step 2: 候选池注册（分级前注册，确保计数可用）----
            if t.relation not in RELATION_CONSTRAINTS:
                # 未知关系，注册到候选池
                self.pool.add_or_merge(
                    raw_relation=t.relation,
                    head_type=t.subject.entity_type,
                    tail_type=t.object_.entity_type,
                    example=f"{t.subject.name} → {t.relation} → {t.object_.name}",
                    source_file=source_file,
                )

            # ---- Step 3: 语义分级处理 ----
            issues = t.validate()
            level = classify_triple(t, self.pool, self.normalizer, issues)

            if level == LEVEL_PASS:
                t.confidence = LEVEL_CONFIG[LEVEL_PASS]["confidence"]
                t.source = LEVEL_CONFIG[LEVEL_PASS]["source"]
                validated.append(t)
                stats["pass"] += 1

            elif level == LEVEL_PASS_PROMOTED:
                t.confidence = LEVEL_CONFIG[LEVEL_PASS_PROMOTED]["confidence"]
                t.source = LEVEL_CONFIG[LEVEL_PASS_PROMOTED]["source"]
                validated.append(t)
                stats["promoted"] += 1

            elif level == LEVEL_PASS_NORMALIZED:
                t.confidence = LEVEL_CONFIG[LEVEL_PASS_NORMALIZED]["confidence"]
                t.source = LEVEL_CONFIG[LEVEL_PASS_NORMALIZED]["source"]
                validated.append(t)
                stats["normalized"] += 1

            elif level == LEVEL_PASS_TRUNCATED:
                t.raw_head = t.subject.name  # 保留原始名称
                t.raw_tail = t.object_.name
                t.subject.name = t.subject.name[:settings.MAX_ENTITY_LENGTH]
                t.object_.name = t.object_.name[:settings.MAX_ENTITY_LENGTH]
                t.confidence = LEVEL_CONFIG[LEVEL_PASS_TRUNCATED]["confidence"]
                t.source = LEVEL_CONFIG[LEVEL_PASS_TRUNCATED]["source"]
                validated.append(t)
                stats["truncated"] += 1

            elif level == LEVEL_POOL:
                self.pool.add_pooled_triple(t.to_dict(), reason=_get_pool_reason(issues))
                stats["pool"] += 1

            elif level == LEVEL_DROP:
                logger.debug(f"DROP 三元组: {t.to_dict()} | 原因: {issues.details}")
                stats["drop"] += 1

        # ---- Step 4: 时序属性注入 ----
        for t in validated:
            temporal_enrichment(t, source_text=t.source_text)

        # ---- Step 5: 批量结束后检查自动转正 ----
        self.pool.check_auto_promote()

        logger.info(
            f"治理层处理: PASS={stats['pass']} PROMOTED={stats['promoted']} "
            f"NORMALIZED={stats['normalized']} TRUNCATED={stats['truncated']} "
            f"POOL={stats['pool']} DROP={stats['drop']}"
        )

        return validated

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

            # 提取实体 attributes（含时序信息 effective_date/expiry_date/status）
            subj_attrs = subj_raw.get("attributes", {})
            if not isinstance(subj_attrs, dict):
                subj_attrs = {}
            obj_attrs = obj_raw.get("attributes", {})
            if not isinstance(obj_attrs, dict):
                obj_attrs = {}

            # 安全兜底：category 必须是字符串
            for attrs in (subj_attrs, obj_attrs):
                if "category" in attrs:
                    cat = attrs["category"]
                    if isinstance(cat, list):
                        attrs["category"] = cat[0] if cat else ""
                    elif cat is None:
                        attrs["category"] = ""

            subject = Entity(
                name=subj_raw.get("name", ""),
                entity_type=subj_raw.get("type", ""),
                attributes=subj_attrs,
                source_chunk_id=chunk_id,
            )
            object_ = Entity(
                name=obj_raw.get("name", ""),
                entity_type=obj_raw.get("type", ""),
                attributes=obj_attrs,
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
