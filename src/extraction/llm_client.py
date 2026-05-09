"""
DeepSeek LLM 客户端
通过 DeepSeek API 调用 deepseek-v4-flash

API 文档：
- base_url: https://api.deepseek.com
- 模型名: deepseek-v4-flash
- 使用 OpenAI SDK 兼容模式：client.chat.completions.create()
- 支持 reasoning_effort 参数控制推理深度
- 支持 extra_body={"thinking": {"type": "enabled"}} 开启思维链
- 环境变量: DEEPSEEK_API_KEY
"""

import json
import re
import time
from typing import Optional

from openai import OpenAI
from loguru import logger

from config.settings import settings


class DeepSeekClient:
    """DeepSeek LLM 客户端（DeepSeek API）"""

    MAX_RETRIES = 3           # 最大重试次数
    RETRY_DELAY = 3           # 重试基础间隔（秒）
    MAX_OUTPUT_TOKENS = 8192  # 最大输出 tokens（加大减少截断空响应）

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        thinking_enabled: bool = False,
    ):
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.base_url = base_url or settings.DEEPSEEK_BASE_URL
        self.model = model or settings.DEEPSEEK_MODEL
        self.reasoning_effort = reasoning_effort  # "low" / "medium" / "high"
        self.thinking_enabled = thinking_enabled   # 是否开启思维链

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        logger.info(f"DeepSeek client init: model={self.model}, reasoning_effort={self.reasoning_effort}, thinking={thinking_enabled}")

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        response_format: Optional[dict] = None,
    ) -> str:
        """
        调用 DeepSeek Chat Completions API（带重试）

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
                # reasoning 模型不支持 temperature，非 reasoning 模型才加
                if not self.reasoning_effort:
                    kwargs["temperature"] = temperature
                # 支持 reasoning_effort 参数
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
                        delay = self.RETRY_DELAY * (2 ** attempt)  # 指数退避: 3s, 6s, 12s
                        logger.info(f"等待 {delay}s 后重试...")
                        time.sleep(delay)
                        continue
                    return ""  # 所有重试都返回空

                logger.debug(f"LLM response length: {len(result_text)} chars")
                return result_text

            except Exception as e:
                last_error = e
                logger.warning(f"DeepSeek API call failed (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)

        logger.error(f"All {self.MAX_RETRIES} attempts failed: {last_error}")
        raise last_error

    def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ):
        """
        调用 DeepSeek Chat Completions API，流式返回 token

        Yields:
            每个文本片段（str）

        用法:
            for token in client.chat_stream(...):
                print(token, end="", flush=True)
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if not self.reasoning_effort:
            kwargs["temperature"] = temperature
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if self.thinking_enabled:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        response = self.client.chat.completions.create(**kwargs)

        for chunk in response:
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 16384,
    ) -> dict | list:
        """
        调用 DeepSeek 并解析 JSON 响应（带重试）

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
                    delay = self.RETRY_DELAY * (2 ** attempt)  # 指数退避
                    time.sleep(delay)
                    continue
                return {"entities": [], "triples": []}  # 兜底返回空结构

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
                return {"entities": [], "triples": []}  # 最终兜底

    @staticmethod
    def _repair_truncated_json(text: str) -> Optional[dict]:
        """
        尝试修复被截断的 JSON
        常见情况：LLM 输出太长，JSON 在中途被切断
        策略：找到最后一个完整的对象/数组，补齐括号
        """
        # 找到最外层的 { 开始位置
        start = text.find("{")
        if start == -1:
            return None

        substr = text[start:]

        # 尝试逐步截短到最近的完整结构
        for end_pos in range(len(substr), 0, -1):
            candidate = substr[:end_pos]
            last_char = candidate.rstrip()[-1] if candidate.rstrip() else ""
            if last_char in (",", ":", '"'):
                continue

            # 计算需要补齐的括号
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
_client: Optional[DeepSeekClient] = None
_reasoning_client: Optional[DeepSeekClient] = None


def get_llm_client(
    reasoning_effort: Optional[str] = None,
    thinking_enabled: bool = False,
) -> DeepSeekClient:
    """获取 LLM 客户端单例（无 reasoning，用于抽取管线）

    Args:
        reasoning_effort: 推理深度，默认 None（不开启推理）
        thinking_enabled: 是否开启思维链，默认 False
    """
    global _client
    if _client is None:
        _client = DeepSeekClient(
            reasoning_effort=reasoning_effort,
            thinking_enabled=thinking_enabled,
        )
    return _client


def get_reasoning_llm_client(
    reasoning_effort: str = "medium",
    thinking_enabled: bool = False,
) -> DeepSeekClient:
    """获取带 reasoning 的 LLM 客户端单例（用于推理模块 + 评估）

    Args:
        reasoning_effort: 推理深度，默认 "medium"
        thinking_enabled: 是否开启思维链，默认 False
    """
    global _reasoning_client
    if _reasoning_client is None:
        _reasoning_client = DeepSeekClient(
            reasoning_effort=reasoning_effort,
            thinking_enabled=thinking_enabled,
        )
    return _reasoning_client
