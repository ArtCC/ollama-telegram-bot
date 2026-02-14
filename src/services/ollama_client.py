from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from src.core.context_store import ConversationTurn


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
                return OllamaResponse(text=text)
            except httpx.TimeoutException as error:
                last_error = error
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaTimeoutError("Ollama request timed out") from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaConnectionError("Could not reach Ollama") from error
            except httpx.HTTPStatusError as error:
                detail = error.response.text[:300]
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
