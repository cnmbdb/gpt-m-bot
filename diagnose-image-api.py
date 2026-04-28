#!/usr/bin/env python3
"""诊断脚本：检查 OpenAI Image API 可用性"""

import os
import json
import requests
from pathlib import Path

def load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

API_KEY = os.getenv("OPENAI_API_KEY", "")
TEST_PROMPT = "a cute cat"

if not API_KEY:
    print("❌ 错误：未找到 OPENAI_API_KEY")
    exit(1)

MODELS_TO_TEST = [
    ("gpt-image-2", {"n": 1}),
    ("chatgpt-image-latest", {"n": 1}),
    ("gpt-image-1", {"n": 1}),
    ("gpt-image-1.5", {"n": 1, "size": "1024x1024"}),
    ("gpt-image-1-mini", {"n": 1}),
    ("dall-e-3", {"n": 1, "size": "1024x1024"}),
]

def test_model(model: str, payload: dict) -> tuple[bool, str]:
    try:
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": model, "prompt": TEST_PROMPT, **payload},
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            has_b64 = "b64_json" in data.get("data", [{}])[0]
            has_url = "url" in data.get("data", [{}])[0]
            format_type = []
            if has_b64: format_type.append("b64_json")
            if has_url: format_type.append("url")
            return True, f"✅ 可用 (返回: {', '.join(format_type)})"
        else:
            error = response.json().get("error", {})
            msg = error.get("message", "未知错误")
            return False, f"❌ {msg[:100]}"
    except Exception as e:
        return False, f"❌ 请求失败: {str(e)[:100]}"

def check_api_key():
    print("=" * 60)
    print("📡 检查 API Key 有效性...")
    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            print("✅ API Key 有效\n")
            return True
        else:
            print(f"❌ API Key 无效 (HTTP {resp.status_code})")
            return False
    except Exception as e:
        print(f"❌ 无法连接到 OpenAI API: {e}")
        return False

def main():
    print("🔍 OpenAI Image API 诊断工具\n")

    if not check_api_key():
        exit(1)

    print("📋 测试可用模型...\n")
    print(f"{'模型':<25} | 状态")
    print("-" * 60)

    results = {}
    for model, extra_params in MODELS_TO_TEST:
        success, message = test_model(model, extra_params)
        status = "✅ 可用" if success else "❌ 不可用"
        if "Verify" in message or "verified" in message:
            status = "⚠️ 需验证"
        print(f"{model:<25} | {status}")
        if success or "验证" in message:
            print(f"{'':>27} | {message}")
        results[model] = success

    print("\n" + "=" * 60)
    print("📊 总结")
    print("=" * 60)

    available = [m for m, ok in results.items() if ok]
    unavailable = [m for m, ok in results.items() if not ok]

    if available:
        print(f"✅ 可用模型: {', '.join(available)}")
    if unavailable:
        print(f"❌ 不可用模型: {', '.join(unavailable)}")

    if not results.get("gpt-image-2") and not results.get("chatgpt-image-latest"):
        print("\n⚠️  如果需要使用 gpt-image-2 或 chatgpt-image-latest:")
        print("   请前往 https://platform.openai.com/settings/organization/general")
        print("   完成组织验证（通常需要 1-2 个工作日）")

    print("\n💡 建议:")
    if results.get("gpt-image-1"):
        print("   → 使用 gpt-image-1 作为主要模型（已修改代码支持）")
    if results.get("dall-e-3"):
        print("   → dall-e-3 作为备选方案（返回 URL 格式）")
    if not any(results.values()):
        print("   → API Key 可能没有图片生成权限，请检查订阅状态")

if __name__ == "__main__":
    main()
