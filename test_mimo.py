"""
测试 MiMo LLM 连接
使用方法：
1. 在 .env 中填入 MIMO_API_KEY
2. 运行：python test_mimo.py
"""

import sys
import os
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger

# 检查 API Key 是否配置
from config.settings import settings
if not settings.MIMO_API_KEY or settings.MIMO_API_KEY == "your_mimo_key_here":
    print("❌ 错误：MIMO_API_KEY 未配置！请先在 .env 中填入真实的 API Key")
    sys.exit(1)

print(f"✅ 使用 MiMo 配置：")
print(f"   Base URL: {settings.MIMO_BASE_URL}")
print(f"   Model: {settings.MIMO_MODEL}")
print(f"   API Key: {settings.MIMO_API_KEY[:10]}...{settings.MIMO_API_KEY[-4:]}")
print()

# 测试 1: 基本连接测试
print("=" * 60)
print("测试 1: 基本连接测试（简单对话）")
print("=" * 60)

try:
    from src.extraction.llm_client import get_llm_client
    
    client = get_llm_client(provider="mimo")
    
    print("发送请求：'你好，请介绍一下自己'...")
    response = client.chat(
        system_prompt="You are MiMo, an AI assistant developed by Xiaomi.",
        user_prompt="你好，请介绍一下自己",
        max_tokens=512
    )
    
    print(f"✅ 成功！响应内容：")
    print("-" * 60)
    print(response)
    print("-" * 60)
    
except Exception as e:
    print(f"❌ 测试 1 失败：{e}")
    logger.exception("MiMo 基本连接测试失败")
    sys.exit(1)

# 测试 2: JSON 输出测试
print()
print("=" * 60)
print("测试 2: JSON 输出测试")
print("=" * 60)

try:
    from src.extraction.llm_client import get_llm_client
    
    client = get_llm_client(provider="mimo")
    
    print("发送请求：提取实体和三元组...")
    response_json = client.chat_json(
        system_prompt="你是一个知识图谱抽取助手。请严格以 JSON 格式输出，不要包含任何其他文字。",
        user_prompt="请从以下文本中抽取实体和三元组：小米公司成立于2010年，总部位于北京。",
        max_tokens=1024
    )
    
    print(f"✅ 成功！JSON 响应：")
    print("-" * 60)
    print(json.dumps(response_json, ensure_ascii=False, indent=2))
    print("-" * 60)
    
except Exception as e:
    print(f"❌ 测试 2 失败：{e}")
    logger.exception("MiMo JSON 输出测试失败")

# 测试 3: 全局切换测试（读 .env 中的 LLM_PROVIDER）
print()
print("=" * 60)
print("测试 3: 全局切换测试（读 .env 中的 LLM_PROVIDER）")
print("=" * 60)

try:
    # 临时修改 provider（模拟在 .env 中设置 LLM_PROVIDER=mimo）
    from config.settings import settings
    original_provider = settings.LLM_PROVIDER
    
    # 测试通过参数指定
    print(f"当前 settings.LLM_PROVIDER = {settings.LLM_PROVIDER}")
    print("测试：通过 get_llm_client(provider='mimo') 指定提供商...")
    
    client = get_llm_client(provider="mimo")
    response = client.chat(
        system_prompt="",
        user_prompt="用一句话介绍小米公司",
        max_tokens=256
    )
    
    print(f"✅ 成功！响应内容：{response}")
    
except Exception as e:
    print(f"❌ 测试 3 失败：{e}")
    logger.exception("MiMo 全局切换测试失败")

print()
print("=" * 60)
print("✅ 所有测试完成！MiMo 配置正常工作。")
print("=" * 60)
