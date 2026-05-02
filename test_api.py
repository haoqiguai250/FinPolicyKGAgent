"""快速测试 DeepSeek API 是否能连通（独立脚本，不依赖项目模块）"""
import os
from openai import OpenAI

# 读取 .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
with open(env_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()

api_key = os.environ.get("DEEPSEEK_API_KEY", "")
base_url = os.environ.get("DOUBAO_BASE_URL", "https://api.deepseek.com")
model = os.environ.get("DOUBAO_MODEL", "deepseek-v4-flash")

print(f"API Key: {api_key[:10]}..." if api_key else "API Key: 未设置!")
print(f"Base URL: {base_url}")
print(f"Model: {model}")

if not api_key or api_key == "sk-your-deepseek-key-here":
    print("[FAIL] Please set real DEEPSEEK_API_KEY in .env")
    exit(1)

try:
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": "Hello, just reply with 'OK'."}
        ],
        max_tokens=10,
    )
    content = response.choices[0].message.content
    print(f"Response: {content}")
    print("[OK] DeepSeek API connected!")
except Exception as e:
    print(f"[FAIL] Connection failed: {e}")
