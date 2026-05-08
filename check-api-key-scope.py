#!/usr/bin/env python3
"""检查 API Key 的访问范围和权限"""

import os
import requests
import json
from datetime import datetime

API_KEY = os.getenv("OPENAI_API_KEY", "")

def check_key_type():
    """检查 API Key 类型"""
    print("=" * 60)
    print("🔍 API Key 类型分析")
    print("=" * 60)

    if API_KEY.startswith("sk-proj-"):
        print("✅ 类型: 项目级 API Key (Project API Key)")
        print("📝 说明: 这种 key 绑定到特定项目，可能有访问限制")
    elif API_KEY.startswith("sk-") and "proj" not in API_KEY:
        print("✅ 类型: 用户级 API Key (User API Key)")
        print("📝 说明: 这种 key 通常有更高的访问权限")
    else:
        print("❓ 类型: 未知")

def check_account():
    """检查账户信息"""
    print("\n" + "=" * 60)
    print("👤 账户信息")
    print("=" * 60)

    headers = {"Authorization": f"Bearer {API_KEY}"}

    # 尝试获取账户信息
    try:
        resp = requests.get("https://api.openai.com/v1/account", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ 账户ID: {data.get('id', 'N/A')}")
            print(f"✅ 账户对象: {data.get('object', 'N/A')}")
        else:
            print(f"❌ 无法获取账户信息 (HTTP {resp.status_code})")
    except Exception as e:
        print(f"❌ 请求失败: {e}")

    # 尝试获取订阅信息
    try:
        resp = requests.get("https://api.openai.com/v1/dashboard/billing/subscription", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ 订阅状态: {data.get('status', 'N/A')}")
            plan = data.get('plan', {})
            print(f"✅ 计划名称: {plan.get('title', 'N/A')}")
        else:
            print(f"⚠️  无法获取订阅信息 (HTTP {resp.status_code})")
    except Exception as e:
        print(f"⚠️  订阅查询失败: {e}")

def check_model_access():
    """检查模型访问权限"""
    print("\n" + "=" * 60)
    print("🤖 可用模型检查")
    print("=" * 60)

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    models_to_check = [
        ("gpt-4o", "GPT-4o 聊天模型"),
        ("gpt-4o-mini", "GPT-4o-mini 聊天模型"),
        ("gpt-image-2", "GPT Image 2 图片生成"),
        ("gpt-image-1", "GPT Image 1 图片生成"),
        ("gpt-image-1.5", "GPT Image 1.5 图片生成"),
        ("dall-e-3", "DALL-E 3 图片生成"),
    ]

    for model_id, description in models_to_check:
        try:
            # 检查模型是否存在
            resp = requests.get(f"https://api.openai.com/v1/models/{model_id}", headers=headers, timeout=10)
            if resp.status_code == 200:
                print(f"✅ {description} - 模型存在")

                # 如果是图片模型，尝试实际调用
                if "image" in model_id or "dall" in model_id:
                    test_payload = {
                        "model": model_id,
                        "prompt": "a cat",
                        "n": 1
                    }
                    if "dall" in model_id:
                        test_payload["size"] = "1024x1024"

                    test_resp = requests.post(
                        "https://api.openai.com/v1/images/generations",
                        headers=headers,
                        json=test_payload,
                        timeout=60
                    )

                    if test_resp.status_code == 200:
                        print(f"   └── ✅ 可成功调用!")
                    else:
                        error = test_resp.json().get("error", {})
                        msg = error.get("message", "未知错误")
                        if "verified" in msg.lower() or "verify" in msg.lower():
                            print(f"   └── ⚠️  需要组织验证")
                        else:
                            print(f"   └── ❌ {msg[:80]}")
            else:
                print(f"❌ {description} - 模型不可用 (HTTP {resp.status_code})")
        except Exception as e:
            print(f"⚠️  {description} - 检查失败: {e}")

def check_organization():
    """检查组织设置"""
    print("\n" + "=" * 60)
    print("🏢 组织设置")
    print("=" * 60)

    print("💡 请手动检查以下内容:")
    print("   1. 访问 https://platform.openai.com/settings/organization/general")
    print("   2. 查看是否有 'Verified' 标签")
    print("   3. 如果没有，点击 'Verify Organization'")
    print("   4. 检查组织名称、域名等是否完整")

    print("\n💡 同时检查项目设置:")
    print("   1. 访问 https://platform.openai.com/settings/projects")
    print("   2. 找到创建 API Key 的项目")
    print("   3. 检查 Model Access 部分")
    print("   4. 查找 gpt-image-2 或 gpt-image-1")

def main():
    print("🔍 OpenAI API Key 深度诊断工具\n")
    print(f"⏰ 诊断时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    check_key_type()
    check_account()
    check_model_access()
    check_organization()

    print("\n" + "=" * 60)
    print("📋 诊断总结")
    print("=" * 60)
    print("""
根据诊断结果，你有以下选项：

选项 1: 如果有 "需要组织验证" 警告
   → 访问 https://platform.openai.com/settings/organization/general
   → 完成组织验证

选项 2: 如果是项目级 Key 权限不足
   → 创建新的用户级 API Key (sk-... 格式)
   → 替换 .env 中的 OPENAI_API_KEY

选项 3: 如果 gpt-image-2 完全不可用
   → 继续使用 gpt-image-1.5 (已测试可用)
   → 等待 OpenAI 开放权限

选项 4: 如果急需 gpt-image-2
   → 联系 OpenAI 支持: https://help.openai.com
   → 说明情况并请求访问权限
""")

if __name__ == "__main__":
    main()
