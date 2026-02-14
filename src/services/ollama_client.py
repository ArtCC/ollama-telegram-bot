from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic

import httpx

from src.core.context_store import ConversationTurn

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaConnectionError(OllamaError):
    pass


@dataclass(frozen=True)
class OllamaResponse:
    text: str


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int,
        retries: int = 2,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._retries = retries

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        context_turns: list[ConversationTurn],
    ) -> OllamaResponse:
        started_at = monotonic()
        composed_prompt = self._compose_prompt(prompt=prompt, context_turns=context_turns)
        payload = {
            "model": model,
            "prompt": composed_prompt,
            "stream": False,
        }

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(f"{self._base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                text = str(data.get("response", "")).strip()
                if not text:
                    raise OllamaError("Empty response from Ollama")
                elapsed_ms = int((monotonic() - started_at) * 1000)
                logger.info(
                    "ollama_generate_ok model=%s prompt_chars=%d context_turns=%d elapsed_ms=%d",
                    model,
                    len(prompt),
                    len(context_turns),
                    elapsed_ms,
                )
                return OllamaResponse(text=text)
            except httpx.TimeoutException as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_generate_timeout_retry model=%s attempt=%d/%d",
                        model,
                        attempt + 1,
                        self._retries + 1,
                    )
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaTimeoutError("Ollama request timed out") from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_generate_connection_retry model=%s attempt=%d/%d",
                        model,
                        attempt + 1,
                        self._retries + 1,
                    )
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaConnectionError("Could not reach Ollama") from error
            except httpx.HTTPStatusError as error:
                detail = error.response.text[:300]
                logger.warning(
                    "ollama_generate_http_error model=%s status=%d",
                    model,
                    error.response.status_code,
                )
                raise OllamaError(
                    f"Ollama returned HTTP {error.response.status_code}: {detail}"
                ) from error

        if last_error:
            raise OllamaError("Unexpected Ollama failure") from last_error
        raise OllamaError("Unexpected Ollama failure")

    async def list_models(self) -> list[str]:
        started_at = monotonic()
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                models_raw = data.get("models", [])
                names = [str(item.get("name", "")).strip() for item in models_raw]
                models = [name for name in names if name]
                elapsed_ms = int((monotonic() - started_at) * 1000)
                logger.info("ollama_list_models_ok count=%d elapsed_ms=%d", len(models), elapsed_ms)
                return sorted(models)
            except httpx.TimeoutException as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_list_models_timeout_retry attempt=%d/%d",
                        attempt + 1,
                        self._retries + 1,
                    )
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaTimeoutError("Ollama request timed out") from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_list_models_connection_retry attempt=%d/%d",
                        attempt + 1,
                        self._retries + 1,
                    )
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaConnectionError("Could not reach Ollama") from error
            except httpx.HTTPStatusError as error:
                detail = error.response.text[:300]
                logger.warning("ollama_list_models_http_error status=%d", error.response.status_code)
                raise OllamaError(
                    f"Ollama returned HTTP {error.response.status_code}: {detail}"
                ) from error

        if last_error:
            raise OllamaError("Unexpected Ollama failure") from last_error
        raise OllamaError("Unexpected Ollama failure")

    @staticmethod
    def _compose_prompt(prompt: str, context_turns: list[ConversationTurn]) -> str:
        if not context_turns:
            return prompt

        context_lines: list[str] = []
        for turn in context_turns:
            role_label = "User" if turn.role == "user" else "Assistant"
            context_lines.append(f"{role_label}: {turn.content}")

        context_lines.append(f"User: {prompt}")
        context_lines.append("Assistant:")
        return "\n".join(context_lines)
