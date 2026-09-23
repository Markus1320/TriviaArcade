"""LLMClient implementation for the Ollama API (cloud, authenticated by API key)."""

from typing import Any

import httpx2

from app.llm.client import ChatRequest, LLMError


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        http: httpx2.Client | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = http or httpx2.Client(timeout=timeout_seconds, headers=headers)
        self._chat_url = base_url.rstrip("/") + "/api/chat"

    def close(self) -> None:
        self._http.close()

    def chat(self, request: ChatRequest) -> str:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
        }
        if request.json_schema is not None:
            body["format"] = request.json_schema
        if request.temperature is not None:
            body["options"] = {"temperature": request.temperature}

        try:
            response = self._http.post(self._chat_url, json=body)
        except httpx2.HTTPError as error:
            raise LLMError(f"Ollama request failed: {type(error).__name__}: {error}") from error
        if response.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {response.status_code}: {response.text[:300]}")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as error:
            raise LLMError("Ollama response has no message content") from error
        if not isinstance(content, str):
            raise LLMError("Ollama message content is not text")
        return content
