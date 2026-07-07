import base64
import os
import tempfile
from typing import Any

import requests

import config


class ImageService:
    def __init__(self):
        self.output_dir = os.path.join(tempfile.gettempdir(), "codex-imagegen-service")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, prompt: str) -> tuple[str, str]:
        img_bytes = self.generate_direct(prompt)
        output_path = self._save_to_temp(img_bytes)
        return output_path, output_path

    def generate_direct(self, prompt: str, model: str = "gpt-m2", size: str = "1024x1024") -> bytes:
        model_info = self._get_model_info(model)
        payload: dict[str, Any] = {
            "model": self._api_model(model_info),
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        if size:
            payload["size"] = size

        data = self._post_json("/images/generations", payload)
        return self._extract_image_bytes(data)

    def generate_with_image(self, prompt: str, ref_images: list, model: str = "gpt-m2") -> tuple[bytes, str]:
        model_info = self._get_model_info(model)
        data = self._post_multipart(
            "/images/edits",
            {"prompt": prompt, "model": self._api_model(model_info), "n": "1", "response_format": "url"},
            self._build_image_files(ref_images, "reference"),
        )
        return self._extract_image_bytes_and_url(data)

    def edit_image(self, image_sources, instruction: str, model: str = "gpt-m2") -> bytes:
        model_info = self._get_model_info(model)
        image_bytes_list = self._normalize_images(image_sources)
        data = self._post_multipart(
            "/images/edits",
            {"prompt": instruction, "model": self._api_model(model_info), "n": "1", "response_format": "b64_json"},
            self._build_image_files(image_bytes_list, "image"),
        )
        return self._extract_image_bytes(data)

    def cleanup(self, path: str):
        try:
            os.remove(path)
        except OSError:
            pass

    def _get_model_info(self, model: str) -> dict:
        return config.IMAGE_MODELS.get(model, config.IMAGE_MODELS[config.DEFAULT_IMAGE_MODEL])

    def _api_model(self, model_info: dict) -> str:
        return model_info.get("api_model") or config.GPT_API_IMAGE_MODEL

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {config.GPT_API_AUTH_KEY}"}

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict:
        response = requests.post(
            f"{config.GPT_API_BASE_URL}{path}",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=600,
        )
        return self._parse_response(response)

    def _post_multipart(self, path: str, data: dict[str, str], files: list[tuple[str, tuple[str, bytes, str]]]) -> dict:
        response = requests.post(
            f"{config.GPT_API_BASE_URL}{path}",
            headers=self._headers(),
            data=data,
            files=files,
            timeout=600,
        )
        return self._parse_response(response)

    def _parse_response(self, response: requests.Response) -> dict:
        if response.status_code != 200:
            raise RuntimeError(f"Image relay API error {response.status_code}: {response.text[:200]}")

        data = response.json()
        if "error" in data:
            error = data["error"]
            raise RuntimeError(error.get("message", str(error)) if isinstance(error, dict) else str(error))
        return data

    def _extract_image_bytes(self, data: dict) -> bytes:
        img_bytes, _ = self._extract_image_bytes_and_url(data)
        return img_bytes

    def _extract_image_bytes_and_url(self, data: dict) -> tuple[bytes, str]:
        items = data.get("data") or []
        if not items:
            raise RuntimeError("No image data in response")

        first = items[0]
        b64 = first.get("b64_json")
        if b64:
            return base64.b64decode(b64), first.get("url", "")

        url = first.get("url", "")
        if url:
            img_resp = requests.get(url, timeout=300)
            img_resp.raise_for_status()
            return img_resp.content, url

        raise RuntimeError("No image data (b64_json or url) in response")

    def _normalize_images(self, image_sources) -> list[bytes]:
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

        if not image_bytes_list:
            raise RuntimeError("No input image provided")
        return image_bytes_list

    def _build_image_files(self, images: list[bytes], prefix: str) -> list[tuple[str, tuple[str, bytes, str]]]:
        files = []
        for i, img_bytes in enumerate(images):
            field_name = "image" if i == 0 else "image[]"
            files.append((field_name, (f"{prefix}{i + 1}.png", img_bytes, "image/png")))
        return files

    def _save_to_temp(self, img_bytes: bytes) -> str:
        output_path = os.path.join(self.output_dir, f"gen_{os.getpid()}_{os.urandom(4).hex()}.png")
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        return output_path
