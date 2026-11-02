"""Meta Model API adapter for strict-JSON proposal generation."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Protocol

import httpx

from app.config import Settings

DEFAULT_META_API_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_META_MODEL = "muse-spark-1.3"
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_ACCOUNT_RESTRICTION_HINTS = (
    "account is restricted",
    "payment method",
    "temporary hold",
    "billing",
    "update it to keep making requests",
)
logger = logging.getLogger(__name__)


class MetaModelError(RuntimeError):
    """Base error for a safe, typed model failure."""

    error_code = "MODEL_ERROR"


class MetaModelNotConfigured(MetaModelError):
    error_code = "MODEL_NOT_CONFIGURED"


class MetaModelTimeoutError(MetaModelError):
    error_code = "MODEL_TIMEOUT"


class MetaModelRequestError(MetaModelError):
    error_code = "MODEL_REQUEST_FAILED"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class MetaModelAccountError(MetaModelError):
    error_code = "MODEL_ACCOUNT_RESTRICTED"


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

    @property
    def model(self) -> str | None: ...

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        reasoning_effort: str | None = None,
    ) -> ModelCompletion: ...

    async def list_models(self) -> list[str]: ...

    async def aclose(self) -> None: ...


class UnconfiguredMetaModelClient:
    @property
    def is_configured(self) -> bool:
        return False

    @property
    def model(self) -> str | None:
        return None

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

    async def list_models(self) -> list[str]:
        return []

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
        timeout_seconds: float | None = None,
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
        self._base_url = base_url.rstrip("/")
        self._url = f"{self._base_url}/chat/completions"
        self._catalog_loaded = False
        self._available_models: list[str] = []
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds) if timeout_seconds else httpx.Timeout(None),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def model(self) -> str | None:
        return self._model

    async def list_models(self) -> list[str]:
        response = await self._client.get(f"{self._base_url}/models", timeout=10.0)
        if response.status_code >= 400:
            snippet = " ".join(response.text.split())[:300]
            raise MetaModelRequestError(
                f"The Meta model list request failed with HTTP {response.status_code}.",
                status_code=response.status_code,
                response_body=snippet,
            )
        try:
            body = response.json()
        except ValueError:
            return []
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return []
        return [
            str(item["id"])
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

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
        try:
            response = await self._post_with_retries(request_payload)
        except MetaModelRequestError as exc:
            response = await self._retry_after_missing_model(request_payload, exc)
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

    async def _retry_after_missing_model(
        self, payload: dict[str, Any], error: MetaModelRequestError
    ) -> httpx.Response:
        if error.status_code != 404:
            raise error
        body = (error.response_body or "").lower()
        if "model" not in body and "not found" not in body:
            raise error

        candidates: list[str] = []
        if self._model != DEFAULT_META_MODEL:
            candidates.append(DEFAULT_META_MODEL)

        last_error = error

        async def attempt(candidate: str) -> httpx.Response | None:
            nonlocal last_error
            logger.warning(
                "Meta model %r is not available for this API key; retrying with %r.",
                self._model,
                candidate,
            )
            try:
                response = await self._post_with_retries({**payload, "model": candidate})
            except MetaModelRequestError as exc:
                last_error = exc
                return None
            self._model = candidate
            return response

        for candidate in candidates:
            response = await attempt(candidate)
            if response is not None:
                return response

        # The default was also rejected (or already configured): ask the provider
        # which models this key can actually use.
        available = await self._load_available_models()
        chosen = _choose_model(available, exclude={self._model, *candidates})
        if chosen is not None:
            response = await attempt(chosen)
            if response is not None:
                return response

        available_hint = (
            f" Available models for this API key: {', '.join(available[:12])}."
            if available
            else ""
        )
        provider_hint = (
            f" Provider response: {last_error.response_body[:300]}"
            if last_error.response_body
            else ""
        )
        raise MetaModelRequestError(
            f"The configured Meta model {self._model!r} was not found or is not "
            "available for this API key. Set MECHANISM_AI_META_MODEL to a model your "
            f"key can access.{available_hint}{provider_hint}",
            status_code=last_error.status_code or 404,
            response_body=last_error.response_body,
        ) from last_error

    async def _load_available_models(self) -> list[str]:
        if self._catalog_loaded:
            return self._available_models
        self._catalog_loaded = True
        try:
            self._available_models = await self.list_models()
        except Exception as exc:  # noqa: BLE001 - discovery must never mask the model error
            logger.warning("Could not list Meta models: %s", exc)
            self._available_models = []
        if self._available_models:
            logger.info(
                "Available Meta models for this API key: %s",
                ", ".join(self._available_models[:20]),
            )
        return self._available_models

    async def _post_with_retries(self, payload: dict[str, Any]) -> httpx.Response:
        last_error: MetaModelError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(self._url, json=payload)
            except httpx.TimeoutException as exc:
                logger.warning(
                    "Meta model timeout at %s (attempt %s)", self._url, attempt + 1
                )
                last_error = MetaModelTimeoutError("The Meta model request timed out.")
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                logger.warning("Meta model connection error at %s: %s", self._url, exc)
                last_error = MetaModelRequestError(
                    "The Meta model request failed before a response was received."
                )
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc

            if response.status_code < 400:
                return response

            body_snippet = " ".join(response.text.split())[:400]
            if _is_account_restriction(response.status_code, body_snippet):
                logger.error(
                    "Meta API account restriction (HTTP %s): %s",
                    response.status_code,
                    body_snippet,
                )
                raise MetaModelAccountError(
                    "The Meta API account is restricted: "
                    f"{body_snippet or 'the provider rejected the request'}. "
                    "Update the payment method and billing details in the Meta API "
                    "dashboard, then retry. Free credits still require a valid payment "
                    "method for the provider's temporary hold."
                )
            logger.warning(
                "Meta model HTTP %s at %s (model=%s): %s",
                response.status_code,
                self._url,
                self._model,
                body_snippet,
            )
            last_error = MetaModelRequestError(
                f"The Meta model request failed with HTTP {response.status_code}.",
                status_code=response.status_code,
                response_body=body_snippet,
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
                # Do not let a provider Retry-After stall a demo run for minutes.
                delay = max(delay, min(float(retry_after), 5.0))
            except ValueError:
                pass
        await asyncio.sleep(delay)

    async def aclose(self) -> None:
        await self._client.aclose()


def _is_account_restriction(status_code: int, body: str) -> bool:
    if status_code == 402:
        return True
    lowered = body.lower()
    return any(hint in lowered for hint in _ACCOUNT_RESTRICTION_HINTS)


def _choose_model(available: list[str], *, exclude: set[str]) -> str | None:
    candidates = [model for model in available if model not in exclude]
    if not candidates:
        return None

    def score(model: str) -> tuple[int, str]:
        lowered = model.lower()
        if any(
            token in lowered
            for token in (
                "embed",
                "whisper",
                "tts",
                "audio",
                "image",
                "vision",
                "rerank",
                "voice",
                "transcribe",
                "speech",
                "video",
                "ocr",
                "sam-",
            )
        ):
            return (3, lowered)
        if "spark" in lowered:
            return (0, lowered)
        if "muse" in lowered:
            return (1, lowered)
        return (2, lowered)

    return min(candidates, key=score)


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
