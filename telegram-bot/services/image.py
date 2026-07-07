import base64
import json
import logging
import os
import re
import tempfile
import time
from io import BytesIO
from typing import Any

import requests
from PIL import Image, UnidentifiedImageError

import config

logger = logging.getLogger(__name__)


class ImageService:
    RETRY_ATTEMPTS = 3
    RETRY_STATUS_CODES = {520, 522, 523, 524}

    def __init__(self):
        self.output_dir = os.path.join(tempfile.gettempdir(), "codex-imagegen-service")
        os.makedirs(self.output_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.trust_env = False

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
        logger.info("Image relay edit request: references=%d model=%s", len(ref_images), self._api_model(model_info))
        data = self._post_multipart(
            "/images/edits",
            {"prompt": prompt, "model": self._api_model(model_info), "response_format": "b64_json"},
            self._build_image_files(ref_images, "reference"),
        )
        return self._extract_image_bytes_and_url(data)

    def edit_image(self, image_sources, instruction: str, model: str = "gpt-m2") -> bytes:
        model_info = self._get_model_info(model)
        image_bytes_list = self._normalize_images(image_sources)
        logger.info("Image relay edit request: images=%d model=%s", len(image_bytes_list), self._api_model(model_info))
        data = self._post_multipart(
            "/images/edits",
            {"prompt": instruction, "model": self._api_model(model_info), "response_format": "b64_json"},
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
        response = self._request(
            "post",
            path,
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
        )
        return self._parse_response(response)

    def _post_multipart(self, path: str, data: dict[str, str], files: list[tuple[str, tuple[str, bytes, str]]]) -> dict:
        response = self._request(
            "post",
            path,
            headers=self._headers(),
            data=data,
            files=files,
        )
        return self._parse_response(response)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        last_error = None
        last_response = None
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                response = self.session.request(
                    method,
                    f"{config.GPT_API_BASE_URL}{path}",
                    timeout=600,
                    **kwargs,
                )
                if response.status_code not in self.RETRY_STATUS_CODES:
                    return response
                last_response = response
                logger.warning(
                    "Image relay returned retryable status attempt=%d/%d path=%s status=%s",
                    attempt + 1,
                    self.RETRY_ATTEMPTS,
                    path,
                    response.status_code,
                )
                if attempt == self.RETRY_ATTEMPTS - 1:
                    break
                time.sleep(2 * (attempt + 1))
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.RequestException,
            ) as e:
                last_error = e
                logger.warning(
                    "Image relay request failed attempt=%d/%d path=%s error=%r",
                    attempt + 1,
                    self.RETRY_ATTEMPTS,
                    path,
                    e,
                )
                if attempt == self.RETRY_ATTEMPTS - 1:
                    break
                time.sleep(2 * (attempt + 1))
        if last_response is not None:
            return last_response
        raise last_error

    def _parse_response(self, response: requests.Response) -> dict:
        if response.status_code != 200:
            if response.status_code == 524:
                raise RuntimeError("图片中转站生成超时（HTTP 524），请稍后重试。")
            if response.status_code in self.RETRY_STATUS_CODES:
                raise RuntimeError(f"图片中转站暂时不可用（HTTP {response.status_code}），请稍后重试。")
            raise RuntimeError(f"Image relay API error {response.status_code}: {response.text[:200]}")

        try:
            data = response.json()
        except json.JSONDecodeError:
            body = (response.text or "").strip()
            snippet = body[:120] if body else "空响应"
            raise RuntimeError(f"图片中转站返回了非 JSON 响应：{snippet}")
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
            data_url = self._decode_data_url(url)
            if data_url:
                return data_url, url
            img_resp = self.session.get(url, timeout=300)
            img_resp.raise_for_status()
            return img_resp.content, url

        raise RuntimeError("No image data (b64_json or url) in response")

    def _decode_data_url(self, url: str) -> bytes | None:
        match = re.match(r"^data:image/[^;]+;base64,(.+)$", url, re.DOTALL)
        if not match:
            return None
        return base64.b64decode(match.group(1))

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
            files.append(("image", (f"{prefix}{i + 1}.png", self._to_png(img_bytes), "image/png")))
        return files

    def _to_png(self, img_bytes: bytes) -> bytes:
        try:
            with Image.open(BytesIO(img_bytes)) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                output = BytesIO()
                img.save(output, format="PNG")
                return output.getvalue()
        except UnidentifiedImageError:
            return img_bytes

    def _save_to_temp(self, img_bytes: bytes) -> str:
        output_path = os.path.join(self.output_dir, f"gen_{os.getpid()}_{os.urandom(4).hex()}.png")
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        return output_path
