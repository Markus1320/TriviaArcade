"""Talking to an LLM through the Ollama API: send a chat, get a checked JSON reply back.

The address and the key come from .env (OLLAMA_BASE_URL, OLLAMA_API_KEY), so a local
Ollama on your own GPU works the same way as the cloud (leave the key empty).

ask() takes a `chat` function that sends one request body and returns the reply text.
In use that is Ollama(...).chat; the tests pass a function that returns canned replies.
"""

import json
import re
from collections.abc import Callable
from typing import Any

import httpx2

# Sends one request body to the model and returns its reply text.
Chat = Callable[[dict[str, Any]], str]

# Added to the request when the reply was not usable, so the retry avoids the mistake.
RETRY_NOTE = (
    "\n\nYour previous attempt was rejected: {error}. "
    "Write a different reply that avoids this problem."
)


class LLMError(Exception):
    """No usable reply: the network, the provider, or two replies that failed the check."""


class UsageLimitReached(Exception):
    """The provider refuses calls until a usage limit resets (HTTP 429). Never retried:
    poolgen drops the walk in progress and waits."""


class Ollama:
    """The connection to an Ollama server. A class because it keeps the HTTP connection
    open between calls."""

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = httpx2.Client(timeout=timeout_seconds, headers=headers)
        self.url = base_url.rstrip("/") + "/api/chat"

    def chat(self, body: dict[str, Any]) -> str:
        try:
            response = self.http.post(self.url, json=body)
        except httpx2.HTTPError as error:
            raise LLMError(f"request failed: {type(error).__name__}: {error}") from error
        if response.status_code == 429:
            raise UsageLimitReached(response.text[:300])
        if response.status_code != 200:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:300]}")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as error:
            raise LLMError("the response has no message content") from error
        if not isinstance(content, str):
            raise LLMError("the message content is not text")
        return content

    def close(self) -> None:
        self.http.close()


def ask[T](
    chat: Chat,
    *,
    model: str,
    system: str,
    user: str,
    check: Callable[[dict[str, Any]], T],
    schema: dict[str, Any] | None = None,
    think: bool | str | None = None,
    temperature: float | None = None,
) -> tuple[T, str]:
    """Ask once, and once more if the reply is not usable. Returns the checked reply and
    the user message that produced it.

    check gets the reply as a dict and returns what the caller needs, or raises
    ValueError saying what is wrong; the retry then tells the model.
    schema asks Ollama for JSON of that shape (not every model keeps to it).
    think lets the model reason before it answers: True, or "low", "medium", "high".
    """
    errors = []
    message = user
    for _ in range(2):
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            "stream": False,
        }
        if schema is not None:
            body["format"] = schema
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        if think is not None:
            body["think"] = think
        try:
            reply = chat(body)
        except LLMError as error:
            errors.append(str(error))
            message = user  # a technical failure: the same request again
            continue
        try:
            return check(json_object(reply)), message
        except ValueError as error:
            errors.append(str(error))
            message = user + RETRY_NOTE.format(error=error)
    raise LLMError("; ".join(errors))


CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)


def json_object(reply: str) -> dict[str, Any]:
    """The JSON object in a reply. Some models wrap it in a Markdown code fence or add a
    sentence around it, so both are tolerated."""
    text = reply.strip()
    fenced = CODE_FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"the reply is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("the reply is not a JSON object")
    return data
