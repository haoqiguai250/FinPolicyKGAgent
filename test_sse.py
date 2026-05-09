"""测试 SSE 流式端点"""
import requests
import json

url = "http://127.0.0.1:8000/api/advise/stream"
params = {"query": "科技企业", "fast_mode": True}

print(f"请求: {url}")
print(f"参数: {params}")
print("-" * 50)

try:
    with requests.get(url, params=params, stream=True, timeout=30) as r:
        print(f"状态码: {r.status_code}")
        print(f"响应头: {dict(r.headers)}")
        print("-" * 50)
        
        if r.status_code == 200:
            for line in r.iter_lines(decode_unicode=True):
                if line:
                    print(line)
        else:
            print(f"错误: {r.text}")
except Exception as e:
    print(f"异常: {e}")
