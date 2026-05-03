"""
RAG 生成器

基于虚拟段落 + 用户问题，LLM 生成个性化建议
Strategy 在此阶段被 LLM 具体化（如"扩大融资能力" → "可通过XX银行信贷产品获得低息贷款"）
"""

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from src.extraction.llm_client import DeepSeekClient, get_llm_client
from src.decision.intent_recognizer import EnterpriseProfile


# ── Prompt ──

RAG_SYSTEM_PROMPT = """你是一个专业的金融政策顾问。请根据提供的政策信息和用户情况，给出个性化的政策建议。

要求：
1. 基于提供的政策信息，不要编造不存在的政策
2. 将策略具体化：如"扩大融资能力"应具体说明可以通过什么方式
3. 条理清晰，分点陈述
4. 语言专业但易于理解
5. 如果有多个政策，按关联度排序"""

RAG_USER_PROMPT = """【用户情况】
{profile_text}

【相关政策信息】
{context_text}

【用户问题】
{query}

请给出个性化的政策建议。"""


@dataclass
class RAGResult:
    """RAG 生成结果"""
    answer: str
    profile: EnterpriseProfile
    context_used: str

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "profile": self.profile.to_dict(),
            "context_length": len(self.context_used),
        }


class RAGGenerator:
    """RAG 生成器：虚拟段落 + 问题 → 个性化建议"""

    def __init__(self, llm_client: Optional[DeepSeekClient] = None):
        self.llm = llm_client or get_llm_client()

    def generate(
        self,
        query: str,
        profile: EnterpriseProfile,
        context: str,
    ) -> RAGResult:
        """
        生成个性化建议

        Args:
            query: 用户原始问题
            profile: 企业画像
            context: 虚拟段落（来自 PathToTextConverter）

        Returns:
            RAGResult
        """
        profile_text = self._format_profile(profile)

        try:
            answer = self.llm.chat(
                system_prompt=RAG_SYSTEM_PROMPT,
                user_prompt=RAG_USER_PROMPT.format(
                    profile_text=profile_text,
                    context_text=context,
                    query=query,
                ),
                temperature=0.3,  # 稍高温度以获得更具体的建议
            )

            return RAGResult(
                answer=answer or "抱歉，无法生成建议。",
                profile=profile,
                context_used=context,
            )

        except Exception as e:
            logger.error(f"RAG 生成异常: {e}")
            return RAGResult(
                answer=f"生成建议时出错: {e}",
                profile=profile,
                context_used=context,
            )

    @staticmethod
    def _format_profile(profile: EnterpriseProfile) -> str:
        """格式化企业画像"""
        parts = []
        if profile.region:
            parts.append(f"所在地区：{profile.region}")
        if profile.company_type:
            parts.append(f"企业类型：{profile.company_type}")
        if profile.industry:
            parts.append(f"所属行业：{profile.industry}")
        return "\n".join(parts) if parts else "未提供具体企业信息"
