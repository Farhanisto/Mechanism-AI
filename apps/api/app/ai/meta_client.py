"""Meta Model API adapter for strict-JSON proposal generation."""

import asyncio
import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Protocol

import httpx

from app.config import Settings

DEFAULT_META_API_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_META_MODEL = "muse-spark-1.3"
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class MetaModelError(RuntimeError):
    """Base error for a safe, typed model failure."""

    error_code = "MODEL_ERROR"


class MetaModelNotConfigured(MetaModelError):
    error_code = "MODEL_NOT_CONFIGURED"


class MetaModelTimeoutError(MetaModelError):
    error_code = "MODEL_TIMEOUT"


class MetaModelRequestError(MetaModelError):
    error_code = "MODEL_REQUEST_FAILED"

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MetaModelResponseError(MetaModelError):
    error_code = "MODEL_INVALID_OUTPUT"


@dataclass(frozen=True)
class ModelCompletion:
    payload: dict[str, Any]
    model: str
    latency_ms: float
    usage: dict[str, Any] = field(default_factory=dict)


class MetaModelClient(Protocol):
    @property
    def is_configured(self) -> bool: ...

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        reasoning_effort: str | None = None,
    ) -> ModelCompletion: ...

    async def aclose(self) -> None: ...


class UnconfiguredMetaModelClient:
    @property
    def is_configured(self) -> bool:
        return False

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        reasoning_effort: str | None = None,
    ) -> ModelCompletion:
        raise MetaModelNotConfigured(
            "The Meta model adapter is not configured. Set "
            "MECHANISM_AI_META_API_KEY before enabling AI steps."
        )

    async def aclose(self) -> None:
        return None


class HttpMetaModelClient:
    """OpenAI-compatible Chat Completions client with strict JSON output."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_META_MODEL,
        base_url: str = DEFAULT_META_API_BASE_URL,
        reasoning_effort: str = "minimal",
        timeout_seconds: float = 45.0,
        max_retries: int = 1,
        max_output_tokens: int = 8192,
        retry_backoff_seconds: float = 0.25,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_retries = max_retries
        self._max_output_tokens = max_output_tokens
        self._retry_backoff_seconds = retry_backoff_seconds
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    @property
    def is_configured(self) -> bool:
        return True

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        reasoning_effort: str | None = None,
    ) -> ModelCompletion:
        request_payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
            "reasoning_effort": reasoning_effort or self._reasoning_effort,
            "max_completion_tokens": self._max_output_tokens,
            "temperature": 0.2,
        }

        started = perf_counter()
        response = await self._post_with_retries(request_payload)
        latency_ms = (perf_counter() - started) * 1000.0

        try:
            body = response.json()
        except ValueError as exc:
            raise MetaModelResponseError(
                "The Meta model response was not valid JSON."
            ) from exc
        if not isinstance(body, dict):
            raise MetaModelResponseError("The Meta model response had an unexpected shape.")

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise MetaModelResponseError("The Meta model response contained no choices.")
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            raise MetaModelResponseError("The Meta model response contained no message.")
        if message.get("refusal"):
            raise MetaModelResponseError("The Meta model declined the structured-output request.")
        if choice.get("finish_reason") == "length":
            raise MetaModelResponseError(
                "The Meta model output was truncated before completing the JSON object."
            )

        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        if not isinstance(content, str) or not content.strip():
            raise MetaModelResponseError("The Meta model returned empty structured output.")

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise MetaModelResponseError(
                "The Meta model output did not match the requested JSON schema."
            ) from exc
        if not isinstance(payload, dict):
            raise MetaModelResponseError(
                "The Meta model output must be a JSON object matching the schema."
            )

        usage = body.get("usage")
        response_model = body.get("model")
        return ModelCompletion(
            payload=payload,
            model=response_model if isinstance(response_model, str) else self._model,
            latency_ms=latency_ms,
            usage=usage if isinstance(usage, dict) else {},
        )

    async def _post_with_retries(self, payload: dict[str, Any]) -> httpx.Response:
        last_error: MetaModelError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(self._url, json=payload)
            except httpx.TimeoutException as exc:
                last_error = MetaModelTimeoutError("The Meta model request timed out.")
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = MetaModelRequestError(
                    "The Meta model request failed before a response was received."
                )
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc

            if response.status_code < 400:
                return response

            last_error = MetaModelRequestError(
                f"The Meta model request failed with HTTP {response.status_code}.",
                status_code=response.status_code,
            )
            if (
                response.status_code in _RETRYABLE_STATUS_CODES
                and attempt < self._max_retries
            ):
                await self._backoff(attempt, retry_after=response.headers.get("Retry-After"))
                continue
            raise last_error

        if last_error is not None:
            raise last_error
        raise MetaModelRequestError("The Meta model request failed.")

    async def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        delay = self._retry_backoff_seconds * (2**attempt)
        if retry_after is not None:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        await asyncio.sleep(delay)

    async def aclose(self) -> None:
        await self._client.aclose()


def build_meta_client(settings: Settings) -> MetaModelClient:
    if settings.meta_api_key is None:
        return UnconfiguredMetaModelClient()
    return HttpMetaModelClient(
        api_key=settings.meta_api_key.get_secret_value(),
        model=settings.meta_model or DEFAULT_META_MODEL,
        base_url=settings.meta_api_base_url or DEFAULT_META_API_BASE_URL,
        reasoning_effort=settings.meta_reasoning_effort,
        timeout_seconds=settings.meta_timeout_seconds,
        max_retries=settings.meta_max_retries,
        max_output_tokens=settings.meta_max_output_tokens,
    )
