import json

import httpx
import pytest
from app.ai.meta_client import (
    DEFAULT_META_API_BASE_URL,
    DEFAULT_META_MODEL,
    HttpMetaModelClient,
    MetaModelNotConfigured,
    MetaModelRequestError,
    MetaModelResponseError,
    MetaModelTimeoutError,
    UnconfiguredMetaModelClient,
    build_meta_client,
)
from app.config import Settings
from pydantic import SecretStr

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def completion_body(content: str = '{"ok": true}') -> dict[str, object]:
    return {
        "id": "chatcmpl_test",
        "model": "muse-spark-1.3-2026",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


async def complete(client: HttpMetaModelClient) -> object:
    try:
        return await client.complete_json(
            system_prompt="system",
            user_prompt="user",
            schema=SCHEMA,
            schema_name="test_schema",
        )
    finally:
        await client.aclose()


async def test_request_uses_strict_schema_and_returns_metadata() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=completion_body())

    client = HttpMetaModelClient(
        api_key="super-secret-key",
        transport=httpx.MockTransport(handler),
    )
    completion = await complete(client)

    assert requests[0].url == httpx.URL(f"{DEFAULT_META_API_BASE_URL}/chat/completions")
    assert requests[0].headers["Authorization"] == "Bearer super-secret-key"
    payload = json.loads(requests[0].content)
    assert payload["model"] == DEFAULT_META_MODEL
    assert payload["reasoning_effort"] == "minimal"
    assert payload["messages"][0] == {"role": "system", "content": "system"}
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["name"] == "test_schema"
    assert payload["response_format"]["json_schema"]["schema"] == SCHEMA

    assert completion.payload == {"ok": True}
    assert completion.model == "muse-spark-1.3-2026"
    assert completion.usage["total_tokens"] == 12
    assert completion.latency_ms >= 0


async def test_retry_after_retryable_status() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, headers={"Retry-After": "0"}, text="busy")
        return httpx.Response(200, json=completion_body())

    client = HttpMetaModelClient(
        api_key="key",
        max_retries=1,
        retry_backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    completion = await complete(client)

    assert calls == 2
    assert completion.payload == {"ok": True}


async def test_client_error_is_not_retried_and_does_not_echo_key() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, text="bad key super-secret-key")

    client = HttpMetaModelClient(
        api_key="super-secret-key",
        max_retries=2,
        retry_backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MetaModelRequestError) as error:
        await complete(client)

    assert calls == 1
    assert error.value.status_code == 401
    assert "super-secret-key" not in str(error.value)


async def test_timeout_raises_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = HttpMetaModelClient(
        api_key="key",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MetaModelTimeoutError):
        await complete(client)


async def test_invalid_model_content_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion_body("not-json"))

    client = HttpMetaModelClient(
        api_key="key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MetaModelResponseError):
        await complete(client)


async def test_truncated_output_raises_clear_response_error() -> None:
    body = completion_body()
    body["choices"] = [
        {
            "finish_reason": "length",
            "message": {"role": "assistant", "content": None, "refusal": None},
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = HttpMetaModelClient(api_key="key", transport=httpx.MockTransport(handler))
    with pytest.raises(MetaModelResponseError, match="truncated"):
        await complete(client)


async def test_content_parts_are_joined() -> None:
    body = completion_body()  # type: ignore[assignment]
    body["choices"] = [
        {
            "message": {
                "content": [
                    {"type": "text", "text": '{"ok": '},
                    {"type": "text", "text": "true}"},
                ]
            }
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = HttpMetaModelClient(api_key="key", transport=httpx.MockTransport(handler))
    completion = await complete(client)

    assert completion.payload == {"ok": True}


async def test_unconfigured_client_refuses_to_call() -> None:
    client = UnconfiguredMetaModelClient()

    assert client.is_configured is False
    with pytest.raises(MetaModelNotConfigured, match="not configured"):
        await client.complete_json(
            system_prompt="system",
            user_prompt="user",
            schema=SCHEMA,
            schema_name="test_schema",
        )
    await client.aclose()


async def test_build_client_uses_defaults_and_secret() -> None:
    settings = Settings(
        _env_file=None,
        meta_api_key=SecretStr("key"),
        meta_api_base_url=None,
        meta_model=None,
    )
    client = build_meta_client(settings)
    try:
        assert isinstance(client, HttpMetaModelClient)
        assert client.is_configured is True
    finally:
        await client.aclose()


async def test_build_client_is_unconfigured_without_key() -> None:
    settings = Settings(_env_file=None, meta_api_key=None)

    client = build_meta_client(settings)

    assert isinstance(client, UnconfiguredMetaModelClient)
    await client.aclose()
