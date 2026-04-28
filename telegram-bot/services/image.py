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

    def generate_direct(self, prompt: str, model: str = "gpt-image-2", size: str = "1024x1024") -> bytes:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        if model == "gpt-image-2":
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
            raise RuntimeError(f"API error {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))

        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64)

    def edit_image(self, image_source, instruction: str, model: str = "gpt-image-2") -> bytes:
        """Edit an image based on instruction. image_source can be a file path or bytes."""
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        if isinstance(image_source, str):
            with open(image_source, "rb") as f:
                image_bytes = f.read()
        else:
            image_bytes = image_source.getvalue() if hasattr(image_source, "getvalue") else image_source

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": "gpt-image-2/edit",
            "prompt": instruction,
            "images": [image_b64],
            "n": 1,
            "response_format": "b64_json",
        }

        response = requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(f"API error {response.status_code}: {response.text}")

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
