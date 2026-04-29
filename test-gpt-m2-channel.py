#!/usr/bin/env python3
"""测试 gpt-m2 本地渠道是否正常工作"""

import sys
import os
from pathlib import Path

base_dir = Path(__file__).parent
os.chdir(base_dir)

_env_file = base_dir / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(base_dir / 'telegram-bot'))

import config
from services import image

def main():
    print("🧪 测试 gpt-m2 本地渠道...\n")

    svc = image.ImageService()
    test_prompt = "a cute cat"

    models_to_test = [
        ("gpt-m2", "本地 chatgpt2api → gpt-image-2"),
        ("gpt-image-1.5", "OpenAI 官方 API"),
    ]

    for model_name, desc in models_to_test:
        print(f"测试 {model_name} ({desc})...", end=" ")
        try:
            data = svc.generate_direct(test_prompt, model=model_name)
            print(f"✅ 成功！生成了 {len(data):,} 字节的图片数据")
        except Exception as e:
            print(f"❌ 失败: {e}")

if __name__ == "__main__":
    main()
