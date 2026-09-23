"""OllamaClient against a mocked HTTP transport; no network access."""

import json
from collections.abc import Callable

import httpx2
import pytest

from app.llm.client import ChatRequest, LLMError
from app.llm.ollama import OllamaClient

REQUEST = ChatRequest(
    model="some-model",
    system="system text",
    user="user text",
    json_schema={"type": "boolean"},
    temperature=0.0,
)


def make_client(handler: Callable[[httpx2.Request], httpx2.Response]) -> OllamaClient:
    http = httpx2.Client(
        transport=httpx2.MockTransport(handler), headers={"Authorization": "Bearer test-key"}
    )
    return OllamaClient("https://ollama.invalid/", "test-key", 5, http=http)


def test_chat_sends_expected_body_and_returns_content() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"message": {"role": "assistant", "content": "true"}})

    assert make_client(handler).chat(REQUEST) == "true"
    request = seen[0]
    assert str(request.url) == "https://ollama.invalid/api/chat"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "some-model"
    assert body["stream"] is False
    assert body["format"] == {"type": "boolean"}
    assert body["options"] == {"temperature": 0.0}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_optional_fields_are_omitted() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"message": {"content": "{}"}})

    make_client(handler).chat(ChatRequest(model="m", system="s", user="u"))
    body = json.loads(seen[0].content)
    assert "format" not in body
    assert "options" not in body


def test_api_key_is_sent_as_bearer_token() -> None:
    client = OllamaClient("https://ollama.invalid", "secret", 5)
    assert client._http.headers["Authorization"] == "Bearer secret"
    client.close()


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx2.Response(401, json={"error": "unauthorized"}), "HTTP 401"),
        (httpx2.Response(200, text="not json"), "no message content"),
        (httpx2.Response(200, json={"done": True}), "no message content"),
        (httpx2.Response(200, json={"message": {"content": 5}}), "not text"),
    ],
)
def test_errors_raise_llm_error(response: httpx2.Response, message: str) -> None:
    with pytest.raises(LLMError, match=message):
        make_client(lambda _: response).chat(REQUEST)


def test_transport_errors_raise_llm_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(LLMError, match="ConnectError"):
        make_client(handler).chat(REQUEST)
