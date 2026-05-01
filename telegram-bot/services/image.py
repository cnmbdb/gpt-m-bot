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

    def generate_direct(self, prompt: str, model: str = "gpt-m2", size: str = "1024x1024") -> bytes:
        model_info = self._get_model_info(model)
        provider = model_info.get("provider", "openai")

        if provider == "local":
            return self._generate_local(prompt, model_info)
        else:
            return self._generate_openai(prompt, model, size)

    def generate_with_image(self, prompt: str, ref_image: bytes, model: str = "gpt-m2") -> bytes:
        model_info = self._get_model_info(model)
        provider = model_info.get("provider", "openai")

        if provider == "local":
            return self._generate_local_with_image(prompt, ref_image, model_info)
        else:
            return self._generate_openai_with_image(prompt, ref_image, model)

    def _get_model_info(self, model: str) -> dict:
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
            import config
            return config.IMAGE_MODELS.get(model, {})
        except Exception:
            return {}

    def _generate_local(self, prompt: str, model_info: dict) -> bytes:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        base_url = config.GPT_API_BASE_URL
        auth_key = config.GPT_API_AUTH_KEY
        local_model = model_info.get("local_model", "gpt-image-2")

        response = requests.post(
            f"{base_url}/v1/images/generations",
            headers={
                "Authorization": f"Bearer {auth_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": local_model,
                "prompt": prompt,
                "n": 1,
                "response_format": "b64_json",
            },
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(f"Local API error {response.status_code}: {response.text[:200]}")

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

    def _generate_openai(self, prompt: str, model: str, size: str) -> bytes:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
        }
        if model in ("gpt-image-1.5", "dall-e-3"):
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

    def _generate_local_with_image(self, prompt: str, ref_image: bytes, model_info: dict) -> bytes:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        base_url = config.GPT_API_BASE_URL
        auth_key = config.GPT_API_AUTH_KEY
        local_model = model_info.get("local_model", "gpt-image-2")

        response = requests.post(
            f"{base_url}/v1/images/edits",
            headers={
                "Authorization": f"Bearer {auth_key}",
            },
            data={
                "model": local_model,
                "prompt": prompt,
                "n": 1,
                "response_format": "b64_json",
            },
            files={"image": ("reference.png", ref_image, "image/png")},
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(f"Local API error {response.status_code}: {response.text[:200]}")

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

    def _generate_openai_with_image(self, prompt: str, ref_image: bytes, model: str) -> bytes:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        supported = ("gpt-image-1", "gpt-image-1.5", "gpt-image-1-mini", "chatgpt-image-latest")
        actual = model if model in supported else "gpt-image-1"

        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            },
            data={
                "model": actual,
                "prompt": prompt,
                "n": 1,
            },
            files={"image": ("reference.png", ref_image, "image/png")},
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

    def edit_image(self, image_source, instruction: str, model: str = "gpt-m2") -> bytes:
        """Edit an image based on instruction. image_source can be a file path or bytes."""
        model_info = self._get_model_info(model)
        provider = model_info.get("provider", "openai")

        if isinstance(image_source, str):
            with open(image_source, "rb") as f:
                image_bytes = f.read()
        else:
            image_bytes = image_source.getvalue() if hasattr(image_source, "getvalue") else image_source

        if provider == "local":
            return self._edit_local(image_bytes, instruction, model_info)
        else:
            return self._edit_openai(image_bytes, instruction, model)

    def _edit_local(self, image_bytes: bytes, instruction: str, model_info: dict) -> bytes:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        base_url = config.GPT_API_BASE_URL
        auth_key = config.GPT_API_AUTH_KEY
        local_model = model_info.get("local_model", "gpt-image-2")

        response = requests.post(
            f"{base_url}/v1/images/edits",
            headers={"Authorization": f"Bearer {auth_key}"},
            data={"model": local_model, "prompt": instruction, "n": 1},
            files={"image": ("image.png", image_bytes, "image/png")},
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(f"Local edit error {response.status_code}: {response.text[:200]}")

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

        raise RuntimeError("No image data in response")

    def _edit_openai(self, image_bytes: bytes, instruction: str, model: str) -> bytes:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        supported = ("gpt-image-1", "gpt-image-1.5", "gpt-image-1-mini", "chatgpt-image-latest")
        actual = model if model in supported else "gpt-image-1"

        response = requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            data={"model": actual, "prompt": instruction, "n": 1},
            files={"image": ("image.png", image_bytes, "image/png")},
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

        raise RuntimeError("No image data in response")

    def cleanup(self, path: str):
        try:
            os.remove(path)
        except OSError:
            pass
