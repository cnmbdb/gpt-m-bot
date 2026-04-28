#!/usr/bin/env python3
"""快速测试图片生成"""

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
    print("🧪 测试图片生成...\n")

    if not config.OPENAI_API_KEY:
        print("❌ 未找到 OPENAI_API_KEY")
        return

    svc = image.ImageService()
    test_prompt = "a cute cat"

    models_to_test = [
        ("gpt-image-1.5", {"size": "1024x1024"}),
        ("gpt-image-1-mini", {}),
        ("dall-e-3", {"size": "1024x1024"}),
    ]

    for model_name, extra in models_to_test:
        print(f"测试 {model_name}...", end=" ")
        try:
            data = svc.generate_direct(test_prompt, model=model_name, **extra)
            print(f"✅ 成功！生成了 {len(data)} 字节的图片数据")
        except Exception as e:
            print(f"❌ 失败: {e}")

if __name__ == "__main__":
    main()
