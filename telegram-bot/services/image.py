import os
import subprocess
import tempfile
import base64
import requests
import json
import time
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
            timeout=600,
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

    def generate_with_image(self, prompt: str, ref_images: list, model: str = "gpt-m2") -> tuple[bytes, str]:
        """Returns (image_bytes, image_path). Use local path for Telegram to avoid timeout."""
        model_info = self._get_model_info(model)
        provider = model_info.get("provider", "openai")

        if provider == "local":
            img_bytes = self._generate_local_with_image(prompt, ref_images, model_info)
            path = self._save_to_temp(img_bytes)
            return img_bytes, path
        else:
            img_bytes = self._generate_openai_with_image(prompt, ref_images, model)
            path = self._save_to_temp(img_bytes)
            return img_bytes, path

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
            timeout=600,
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
            img_resp = requests.get(url, timeout=600)
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
            timeout=600,
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
            img_resp = requests.get(url, timeout=300)
            img_resp.raise_for_status()
            return img_resp.content

        raise RuntimeError("No image data (b64_json or url) in response")

    def _generate_local_with_image(self, prompt: str, ref_images: list, model_info: dict) -> bytes:
        import sys, os, base64
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        base_url = config.GPT_API_BASE_URL
        auth_key = config.GPT_API_AUTH_KEY
        local_model = model_info.get("local_model", "gpt-image-2")

        # 构建 multipart 请求：图片作为文件上传，prompt 等作为 form 字段
        files = []
        for i, img_data in enumerate(ref_images):
            # 第一张用 image，后续用 image[]（gpt-api 格式）
            field_name = "image" if i == 0 else "image[]"
            files.append((field_name, (f"reference{i+1}.png", img_data, "image/png")))

        print(f"[DEBUG] 调用API: {base_url}/v1/images/edits, 参考图片数: {len(ref_images)}")

        response = requests.post(
            f"{base_url}/v1/images/edits",
            headers={"Authorization": f"Bearer {auth_key}"},
            data={"prompt": prompt, "model": local_model, "n": "1", "response_format": "url"},
            files=files,
            timeout=600,
        )

        print(f"[DEBUG] API响应状态: {response.status_code}")
        print(f"[DEBUG] 响应内容: {response.text[:500]}")

        if response.status_code != 200:
            raise RuntimeError(f"Local API error {response.status_code}: {response.text[:200]}")

        data = response.json()
        print(f"[DEBUG] API响应数据keys: {list(data.keys())}")

        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))

        url = data["data"][0].get("url")
        print(f"[DEBUG] url存在: {bool(url)}")

        if url:
            # url = http://127.0.0.1:3000/images/2026/05/04/xxx.png
            # GPT_API_IMAGES_DIR = /Users/a2333/IDE/gpt-huatu/gpt-api/data/images
            # local_path = /Users/a2333/IDE/gpt-huatu/gpt-api/data/images/2026/05/04/xxx.png
            local_path = url.replace(f"{base_url}/images/", f"{config.GPT_API_IMAGES_DIR}/")
            img_file = local_path
            if os.path.exists(img_file):
                print(f"[DEBUG] 图片本地路径: {img_file}")
                return open(img_file, "rb").read(), img_file
            raise RuntimeError(f"图片文件不存在: {img_file}")

        b64 = data["data"][0].get("b64_json")
        print(f"[DEBUG] b64_json存在: {bool(b64)}, 长度: {len(b64) if b64 else 0}")

        if not b64:
            raise RuntimeError("No image data (url or b64_json) in response")

        img_bytes = base64.b64decode(b64)
        path = self._save_to_temp(img_bytes)
        print(f"[DEBUG] 图片已保存: {path}")
        return img_bytes, path

    def _save_to_temp(self, img_bytes: bytes) -> str:
        import tempfile, hashlib
        file_hash = hashlib.md5(img_bytes[:1024]).hexdigest()
        filename = f"gen_{int(time.time())}_{file_hash}.png"
        out_dir = os.path.join(tempfile.gettempdir(), "codex-imagegen-service")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, filename)
        with open(path, "wb") as f:
            f.write(img_bytes)
        return path

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
            timeout=600,
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
            img_resp = requests.get(url, timeout=300)
            img_resp.raise_for_status()
            return img_resp.content

        raise RuntimeError("No image data (b64_json or url) in response")

    def edit_image(self, image_sources, instruction: str, model: str = "gpt-m2") -> bytes:
        """Edit an image based on instruction. image_sources can be a list of bytes or a single bytes/image object."""
        model_info = self._get_model_info(model)
        provider = model_info.get("provider", "openai")

        if not isinstance(image_sources, list):
            image_sources = [image_sources]

        image_bytes_list = []
        for img in image_sources:
            if isinstance(img, str):
                with open(img, "rb") as f:
                    image_bytes_list.append(f.read())
            elif hasattr(img, "getvalue"):
                image_bytes_list.append(img.getvalue())
            elif isinstance(img, bytes):
                image_bytes_list.append(img)

        if provider == "local":
            return self._edit_local(image_bytes_list, instruction, model_info)
        else:
            return self._edit_openai(image_bytes_list, instruction, model)

    def _edit_local(self, image_bytes_list: list, instruction: str, model_info: dict) -> bytes:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        import config

        base_url = config.GPT_API_BASE_URL
        auth_key = config.GPT_API_AUTH_KEY
        local_model = model_info.get("local_model", "gpt-image-2")

        files = []
        for i, img_bytes in enumerate(image_bytes_list):
            field_name = "image" if i == 0 else "image[]"
            files.append((field_name, (f"image{i+1}.png", img_bytes, "image/png")))

        print(f"[DEBUG] _edit_local: {base_url}/v1/images/edits, 图片数: {len(image_bytes_list)}")

        response = requests.post(
            f"{base_url}/v1/images/edits",
            headers={"Authorization": f"Bearer {auth_key}"},
            data={"prompt": instruction, "model": local_model, "n": "1", "response_format": "url"},
            files=files,
            timeout=600,
        )

        print(f"[DEBUG] _edit_local 响应状态: {response.status_code}")

        if response.status_code != 200:
            raise RuntimeError(f"Local edit error {response.status_code}: {response.text[:200]}")

        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))

        url = data["data"][0].get("url")
        print(f"[DEBUG] _edit_local url: {url}")

        if url:
            local_path = url.replace(f"{base_url}/images/", f"{config.GPT_API_IMAGES_DIR}/")
            img_file = local_path
            if os.path.exists(img_file):
                print(f"[DEBUG] _edit_local 本地读取: {img_file}")
                return open(img_file, "rb").read()
            raise RuntimeError(f"图片文件不存在: {img_file}")

        b64 = data["data"][0].get("b64_json")
        print(f"[DEBUG] _edit_local b64_json: {bool(b64)}")
        if b64:
            return base64.b64decode(b64)

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
            timeout=600,
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
            img_resp = requests.get(url, timeout=300)
            img_resp.raise_for_status()
            return img_resp.content

        raise RuntimeError("No image data in response")

    def cleanup(self, path: str):
        try:
            os.remove(path)
        except OSError:
            pass
