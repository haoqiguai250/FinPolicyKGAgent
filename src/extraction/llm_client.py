"""
多提供商 LLM 客户端（Universal LLM Client）
支持 DeepSeek、OpenAI、MiMo（均兼容 OpenAI SDK 格式）

切换方式：
1. 全局切换：在 .env 中设置 LLM_PROVIDER=deepseek|openai|mimo
2. 代码中指定：get_llm_client(provider="mimo")

API 文档：
- DeepSeek: https://api.deepseek.com
- OpenAI: https://api.openai.com/v1
- MiMo: https://api.xiaomimimo.com/v1
"""

import json
import re
import time
from typing import Optional

from openai import OpenAI
from loguru import logger

from config.settings import settings


class UniversalLLMClient:
    """
    通用 LLM 客户端（OpenAI SDK 兼容模式）
    支持：DeepSeek / OpenAI / MiMo
    """

    MAX_RETRIES = 3           # 最大重试次数
    RETRY_DELAY = 3           # 重试基础间隔（秒）

    def __init__(
        self,
        provider: str = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        thinking_enabled: bool = False,
    ):
        """
        Args:
            provider: 提供商名称（deepseek/openai/mimo），默认读 settings.LLM_PROVIDER
            api_key: API Key（可选，不填则读配置）
            base_url: Base URL（可选，不填则读配置）
            model: 模型名（可选，不填则读配置）
            reasoning_effort: 推理深度（low/medium/high），仅部分模型支持
            thinking_enabled: 是否开启思维链（DeepSeek V4 特有）
        """
        self.provider = provider or settings.LLM_PROVIDER

        # 根据 provider 读取对应配置
        if self.provider == "deepseek":
            self.api_key = api_key or settings.DEEPSEEK_API_KEY
            self.base_url = base_url or settings.DEEPSEEK_BASE_URL
            self.model = model or settings.DEEPSEEK_MODEL
        elif self.provider == "openai":
            self.api_key = api_key or settings.OPENAI_API_KEY
            self.base_url = base_url or settings.OPENAI_BASE_URL
            self.model = model or settings.OPENAI_MODEL
        elif self.provider == "mimo":
            self.api_key = api_key or settings.MIMO_API_KEY
            self.base_url = base_url or settings.MIMO_BASE_URL
            self.model = model or settings.MIMO_MODEL
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        self.reasoning_effort = reasoning_effort
        self.thinking_enabled = thinking_enabled

        # 统一使用 OpenAI SDK
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        logger.info(f"LLM client init: provider={self.provider}, model={self.model}, "
                    f"reasoning_effort={self.reasoning_effort}, thinking={thinking_enabled}")

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        response_format: Optional[dict] = None,
    ) -> str:
        """
        调用 Chat Completions API（带重试）

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 生成温度
            max_tokens: 最大输出 tokens
            response_format: 响应格式（暂未使用）

        Returns:
            LLM 生成的文本
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }

                # reasoning 模型不支持 temperature
                if not self.reasoning_effort:
                    kwargs["temperature"] = temperature

                # 支持 reasoning_effort 参数（DeepSeek / MiMo 支持）
                if self.reasoning_effort:
                    kwargs["reasoning_effort"] = self.reasoning_effort

                # 开启思维链（DeepSeek V4 特有）
                if self.thinking_enabled:
                    kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

                response = self.client.chat.completions.create(**kwargs)

                # 从 Chat Completions 结果中提取文本
                result_text = response.choices[0].message.content
                if not result_text or not result_text.strip():
                    logger.warning(f"Empty response on attempt {attempt}, retrying...")
                    if attempt < self.MAX_RETRIES:
                        delay = self.RETRY_DELAY * (2 ** attempt)
                        logger.info(f"Waiting {delay}s before retry...")
                        time.sleep(delay)
                        continue
                    return ""

                logger.debug(f"LLM response length: {len(result_text)} chars")
                return result_text

            except Exception as e:
                last_error = e
                logger.warning(f"LLM API call failed (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)

        logger.error(f"All {self.MAX_RETRIES} attempts failed: {last_error}")
        raise last_error

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 16384,
    ) -> dict | list:
        """
        调用 LLM 并解析 JSON 响应（带重试）

        Returns:
            解析后的 dict 或 list
        """
        enhanced_system = system_prompt + "\n\n请严格以 JSON 格式输出，不要包含任何其他文字。"

        for attempt in range(1, self.MAX_RETRIES + 1):
            raw = self.chat(
                system_prompt=enhanced_system,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if not raw or not raw.strip():
                logger.warning(f"Empty LLM response on attempt {attempt}")
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue
                return {"entities": [], "triples": []}

            # 清理可能的 markdown 代码块包裹
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed (attempt {attempt}): {e}\nRaw: {raw[:300]}")
                # 尝试从响应中提取 JSON
                json_match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', cleaned)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass
                # 尝试修复截断的 JSON
                repaired = self._repair_truncated_json(cleaned)
                if repaired is not None:
                    logger.info("Successfully repaired truncated JSON")
                    return repaired

                if attempt < self.MAX_RETRIES:
                    logger.info(f"Retrying chat_json (attempt {attempt + 1})...")
                    time.sleep(self.RETRY_DELAY * (2 ** attempt))
                    continue

                logger.error(f"All JSON parse attempts failed, returning empty result")
                return {"entities": [], "triples": []}

    @staticmethod
    def _repair_truncated_json(text: str) -> Optional[dict]:
        """
        尝试修复被截断的 JSON
        常见情况：LLM 输出太长，JSON 在中途被切断
        策略：找到最后一个完整的对象/数组，补齐括号
        """
        start = text.find("{")
        if start == -1:
            return None

        substr = text[start:]

        for end_pos in range(len(substr), 0, -1):
            candidate = substr[:end_pos]
            last_char = candidate.rstrip()[-1] if candidate.rstrip() else ""
            if last_char in (",", ":", '"'):
                continue

            open_braces = candidate.count("{") - candidate.count("}")
            open_brackets = candidate.count("[") - candidate.count("]")

            if open_braces >= 0 and open_brackets >= 0:
                repaired = candidate + "]" * open_brackets + "}" * open_braces
                try:
                    result = json.loads(repaired)
                    if isinstance(result, dict) and ("entities" in result or "triples" in result):
                        return result
                except json.JSONDecodeError:
                    continue

        return None


# ── 全局单例（延迟初始化）──

_client_cache: dict = {}  # {provider: UniversalLLMClient}
_reasoning_client_cache: dict = {}


def get_llm_client(
    provider: str = None,
    reasoning_effort: Optional[str] = None,
    thinking_enabled: bool = False,
) -> UniversalLLMClient:
    """
    获取 LLM 客户端（工厂模式）

    Args:
        provider: 提供商（deepseek/openai/mimo），默认读 settings.LLM_PROVIDER
        reasoning_effort: 推理深度（low/medium/high）
        thinking_enabled: 是否开启思维链

    Returns:
        UniversalLLMClient 实例
    """
    provider = provider or settings.LLM_PROVIDER
    cache_key = f"{provider}_{reasoning_effort}_{thinking_enabled}"

    if cache_key not in _client_cache:
        _client_cache[cache_key] = UniversalLLMClient(
            provider=provider,
            reasoning_effort=reasoning_effort,
            thinking_enabled=thinking_enabled,
        )

    client = _client_cache[cache_key]

    # 如果 reasoning 参数发生变化，重新初始化
    if client.reasoning_effort != reasoning_effort or client.thinking_enabled != thinking_enabled:
        _client_cache[cache_key] = UniversalLLMClient(
            provider=provider,
            reasoning_effort=reasoning_effort,
            thinking_enabled=thinking_enabled,
        )
        client = _client_cache[cache_key]

    return client


def get_reasoning_llm_client(
    provider: str = None,
    reasoning_effort: str = "medium",
    thinking_enabled: bool = False,
) -> UniversalLLMClient:
    """
    获取带 reasoning 的 LLM 客户端（用于推理模块 + 评估）

    Args:
        provider: 提供商（deepseek/openai/mimo）
        reasoning_effort: 推理深度，默认 "medium"
        thinking_enabled: 是否开启思维链
    """
    provider = provider or settings.LLM_PROVIDER
    cache_key = f"reasoning_{provider}_{reasoning_effort}_{thinking_enabled}"

    if cache_key not in _reasoning_client_cache:
        _reasoning_client_cache[cache_key] = UniversalLLMClient(
            provider=provider,
            reasoning_effort=reasoning_effort,
            thinking_enabled=thinking_enabled,
        )

    client = _reasoning_client_cache[cache_key]

    if client.reasoning_effort != reasoning_effort or client.thinking_enabled != thinking_enabled:
        _reasoning_client_cache[cache_key] = UniversalLLMClient(
            provider=provider,
            reasoning_effort=reasoning_effort,
            thinking_enabled=thinking_enabled,
        )
        client = _reasoning_client_cache[cache_key]

    return client
