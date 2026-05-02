"""
Stage 3b: 反思式智能体模块（核心借鉴 FinReflectKG）
提取 → 批判 → 修正 三步循环迭代，直至收敛

收敛条件：
- 批判 LLM 未发现新问题（输出 PASS）
- 达到最大迭代次数（默认 3 轮）
- 每轮三元组变更率低于阈值（<5%）
"""

import json
from typing import Optional
from dataclasses import dataclass, field

from loguru import logger

from src.extraction.schema import Entity, Triple
from src.extraction.extractor import SchemaGuidedExtractor
from src.extraction.llm_client import DeepSeekClient, get_llm_client
from src.ingestion.chunker import Chunk


# ── Prompt 模板 ──

CRITIQUE_SYSTEM_PROMPT = """你是一个金融政策知识图谱质量审核专家。请审核以下从政策文本中抽取的三元组。

【审核维度】
1. 完整性：是否有遗漏的实体或关系？
2. 准确性：关系方向和类型是否正确？
3. 一致性：是否存在自相矛盾的三元组？
4. 政策语义：是否误读了政策表述（如将"鼓励"误标为"强制"）？

【输出格式】
如果发现问题，请输出 JSON：
{{
  "passed": false,
  "issues": [
    {{
      "dimension": "完整性/准确性/一致性/政策语义",
      "description": "问题描述",
      "suggestion": "改进建议"
    }}
  ]
}}

如果没有问题，请输出：
{{"passed": true, "issues": []}}"""

CRITIQUE_USER_PROMPT = """【原文】
{chunk_text}

【抽取结果】
{triples_json}

请审核上述三元组。"""

REVISE_SYSTEM_PROMPT = """你是一个金融政策知识图谱修正专家。请根据审核反馈修正三元组。

修正规则：
1. 根据每个 issue 的 suggestion 进行修正
2. 修正时必须忠于原文，不得添加原文未提及的信息
3. 保持 Schema 约束
4. 输出与抽取阶段相同的 JSON 格式"""

REVISE_USER_PROMPT = """【原文】
{chunk_text}

【当前三元组】
{triples_json}

【审核反馈】
{critique_json}

请修正上述三元组。"""


@dataclass
class ReflectionResult:
    """反思迭代结果"""
    entities: list[Entity] = field(default_factory=list)
    triples: list[Triple] = field(default_factory=list)
    iterations: int = 0
    converged: bool = False
    iteration_log: list[dict] = field(default_factory=list)


class ReflectiveAgent:
    """反思式智能体：提取 → 批判 → 修正 循环"""

    MAX_ITERATIONS = 3           # 最大迭代次数
    CONVERGENCE_THRESHOLD = 0.05  # 变更率阈值 5%

    def __init__(
        self,
        extractor: Optional[SchemaGuidedExtractor] = None,
        llm_client: Optional[DeepSeekClient] = None,
    ):
        self.extractor = extractor or SchemaGuidedExtractor(llm_client)
        self.llm = llm_client or get_llm_client()

    def extract_with_reflection(
        self,
        chunk: Chunk,
        existing_entities: Optional[list[Entity]] = None,
    ) -> ReflectionResult:
        """
        对单个 chunk 执行反思式抽取

        Args:
            chunk: 文本分块
            existing_entities: 已有实体上下文

        Returns:
            ReflectionResult: 包含最终三元组和迭代日志
        """
        logger.info(f"开始反思式抽取: {chunk.chunk_id}")

        result = ReflectionResult()

        # ── Round 0: 初始抽取 ──
        entities, triples = self.extractor.extract(chunk, existing_entities)
        result.entities = entities
        result.triples = triples
        result.iterations = 1

        logger.info(f"Round 0 完成: {len(triples)} 个三元组")

        # ── 迭代循环 ──
        for round_num in range(1, self.MAX_ITERATIONS):
            # 批判
            critique = self._critique(chunk, triples)
            passed = critique.get("passed", False)
            issues = critique.get("issues", [])

            log_entry = {
                "round": round_num,
                "action": "critique",
                "passed": passed,
                "issue_count": len(issues),
                "issues": issues,
            }
            result.iteration_log.append(log_entry)

            if passed:
                logger.info(f"Round {round_num} 批判通过，收敛！")
                result.converged = True
                break

            logger.info(f"Round {round_num} 发现 {len(issues)} 个问题，进入修正")

            # 修正
            revised_entities, revised_triples = self._revise(
                chunk, entities, triples, critique
            )

            # 计算变更率
            change_rate = self._compute_change_rate(triples, revised_triples)
            log_entry_revise = {
                "round": round_num,
                "action": "revise",
                "change_rate": change_rate,
                "old_count": len(triples),
                "new_count": len(revised_triples),
            }
            result.iteration_log.append(log_entry_revise)

            entities = revised_entities
            triples = revised_triples
            result.iterations += 1

            # 变更率低于阈值，认为收敛
            if change_rate < self.CONVERGENCE_THRESHOLD:
                logger.info(f"Round {round_num} 变更率 {change_rate:.2%} < 阈值，收敛！")
                result.converged = True
                break

        # 达到最大迭代次数
        if not result.converged:
            logger.warning(f"达到最大迭代次数 {self.MAX_ITERATIONS}，强制停止")

        result.entities = entities
        result.triples = triples

        logger.info(f"反思式抽取完成: {len(result.triples)} 个三元组, "
                     f"{result.iterations} 轮迭代, 收敛={result.converged}")
        return result

    def _critique(self, chunk: Chunk, triples: list[Triple]) -> dict:
        """批判阶段：让 LLM 审核当前三元组"""
        triples_json = json.dumps(
            [t.to_dict() for t in triples],
            ensure_ascii=False, indent=2
        )

        try:
            result = self.llm.chat_json(
                system_prompt=CRITIQUE_SYSTEM_PROMPT,
                user_prompt=CRITIQUE_USER_PROMPT.format(
                    chunk_text=chunk.text,
                    triples_json=triples_json,
                ),
                temperature=0.1,
            )
            return result
        except Exception as e:
            logger.error(f"批判阶段异常: {e}")
            return {"passed": True, "issues": []}  # 异常时默认通过

    def _revise(
        self,
        chunk: Chunk,
        entities: list[Entity],
        triples: list[Triple],
        critique: dict,
    ) -> tuple[list[Entity], list[Triple]]:
        """修正阶段：根据批判反馈修正三元组"""
        triples_json = json.dumps(
            [t.to_dict() for t in triples],
            ensure_ascii=False, indent=2
        )
        critique_json = json.dumps(critique, ensure_ascii=False, indent=2)

        try:
            result = self.llm.chat_json(
                system_prompt=REVISE_SYSTEM_PROMPT,
                user_prompt=REVISE_USER_PROMPT.format(
                    chunk_text=chunk.text,
                    triples_json=triples_json,
                    critique_json=critique_json,
                ),
                temperature=0.1,
            )

            # 防御：LLM 可能返回 list 而非 dict
            if isinstance(result, list):
                logger.warning(f"修正阶段 LLM 返回了 list 而非 dict，尝试适配")
                # 尝试把 list 当作 triples 列表
                result = {"entities": [], "triples": result}

            if not isinstance(result, dict):
                logger.error(f"修正阶段 LLM 返回了非 dict/list 类型: {type(result)}")
                return entities, triples

            # 解析修正后的结果（复用 extractor 的解析逻辑）
            new_triples = self.extractor._parse_triples(
                result.get("triples", []), chunk.chunk_id
            )

            # Schema 校验
            valid_triples = []
            for t in new_triples:
                issues = t.validate()
                if issues:
                    logger.warning(f"修正后三元组仍不合规: {t.to_dict()} | {issues}")
                else:
                    valid_triples.append(t)

            # 实体从三元组 subject/object 中提取（修正阶段 LLM 不返回 entities 字段）
            seen_keys = {(e.name, e.entity_type) for e in entities}
            for t in valid_triples:
                for e_obj in (t.subject, t.object_):
                    key = (e_obj.name, e_obj.entity_type)
                    if key not in seen_keys:
                        entities.append(Entity(
                            name=e_obj.name,
                            entity_type=e_obj.entity_type,
                            attributes={},
                            source_chunk_id=chunk.chunk_id,
                        ))
                        seen_keys.add(key)

            return new_entities, valid_triples

        except Exception as e:
            logger.error(f"修正阶段异常，保留当前结果: {e}")
            return entities, triples

    @staticmethod
    def _compute_change_rate(
        old_triples: list[Triple],
        new_triples: list[Triple],
    ) -> float:
        """计算三元组变更率"""
        if not old_triples:
            return 1.0 if new_triples else 0.0

        old_set = {
            (t.subject.name, t.relation, t.object_.name) for t in old_triples
        }
        new_set = {
            (t.subject.name, t.relation, t.object_.name) for t in new_triples
        }

        changed = len(old_set.symmetric_difference(new_set))
        total = max(len(old_set), 1)
        return changed / total
