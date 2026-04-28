import os
import subprocess
import tempfile
import base64
import requests
import json
from typing import Optional

import config


class ImageService:
    def __init__(self):
        self.script = config.GEN_SCRIPT
        self.output_dir = os.path.join(tempfile.gettempdir(), "codex-imagegen-service")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, prompt: str) -> tuple[str, str]:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        output_path = os.path.join(self.output_dir, f"gen_{os.getpid()}_{os.urandom(4).hex()}.png")

        result = subprocess.run(
            ["node", self.script, prompt, output_path],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "OPENAI_API_KEY": config.OPENAI_API_KEY}
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())

        if not os.path.exists(output_path):
            raise RuntimeError(f"Output file not created: {result.stdout}")

        return output_path, result.stdout.strip()

    def generate_direct(self, prompt: str, model: str = "gpt-image-1", size: str = "1024x1024") -> bytes:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
        }
        if model == "gpt-image-1.5":
            payload["size"] = size

        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(f"API error {response.status_code}: {response.text[:200]}")

        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))

        b64 = data["data"][0].get("b64_json")
        if b64:
            return base64.b64decode(b64)
        
        url = data["data"][0].get("url")
        if url:
            img_resp = requests.get(url, timeout=60)
            img_resp.raise_for_status()
            return img_resp.content
        
        raise RuntimeError("No image data (b64_json or url) in response")

    def edit_image(self, image_source, instruction: str, model: str = "gpt-image-1") -> bytes:
        """Edit an image based on instruction. image_source can be a file path or bytes."""
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        if isinstance(image_source, str):
            with open(image_source, "rb") as f:
                image_bytes = f.read()
        else:
            image_bytes = image_source.getvalue() if hasattr(image_source, "getvalue") else image_source

        actual_model = model if model not in ("gpt-image-2",) else "gpt-image-1"
        # 支持的模型: gpt-image-1, gpt-image-1.5, gpt-image-1-mini
        if actual_model not in ("gpt-image-1", "gpt-image-1.5", "gpt-image-1-mini", "chatgpt-image-latest"):
            actual_model = "gpt-image-1"

        response = requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            data={"model": actual_model, "prompt": instruction, "n": 1},
            files={"image": ("image.png", image_bytes, "image/png")},
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(f"API error {response.status_code}: {response.text[:200]}")

        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))

        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64)

    def cleanup(self, path: str):
        try:
            os.remove(path)
        except OSError:
            pass
