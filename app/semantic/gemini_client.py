from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class MissingGeminiAPIKeyError(RuntimeError):
    pass


class GeminiRateLimitError(RuntimeError):
    pass


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 60,
        max_rate_limit_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise MissingGeminiAPIKeyError(
                "GEMINI_API_KEY is missing. Set it in your environment before semantic enrichment."
            )
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.timeout_seconds = timeout_seconds
        self.max_rate_limit_retries = max_rate_limit_retries

    def generate_json(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        }
        body = json.dumps(payload).encode("utf-8")

        for attempt in range(self.max_rate_limit_retries + 1):
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    response_data = json.loads(response.read().decode("utf-8"))
                return self._extract_text(response_data)
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < self.max_rate_limit_retries:
                    time.sleep(2**attempt)
                    continue
                if exc.code == 429:
                    raise GeminiRateLimitError("Gemini API rate limit persisted after retries.") from exc
                error_body = exc.read().decode("utf-8", errors="replace")
                message = self._format_http_error(exc.code, error_body)
                raise RuntimeError(message) from exc

        raise GeminiRateLimitError("Gemini API rate limit persisted after retries.")

    def _format_http_error(self, status_code: int, error_body: str) -> str:
        message = error_body.strip()
        try:
            payload = json.loads(error_body)
            message = payload.get("error", {}).get("message") or message
        except json.JSONDecodeError:
            pass

        if len(message) > 300:
            message = message[:297].rstrip() + "..."
        return f"Gemini API request failed with HTTP {status_code} for model '{self.model}': {message}"

    @staticmethod
    def _extract_text(response_data: dict[str, Any]) -> str:
        candidates = response_data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini response did not include candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [part.get("text", "") for part in parts if part.get("text")]
        if not text_parts:
            raise RuntimeError("Gemini response did not include text.")
        return "\n".join(text_parts)
