from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from time import monotonic
from typing import Any

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
        cloud_base_url: str,
        timeout_seconds: int,
        api_key: str | None = None,
        auth_scheme: str = "Bearer",
        retries: int = 2,
    ) -> None:
        self._base_url = base_url
        self._cloud_base_url = cloud_base_url
        self._timeout = timeout_seconds
        self._retries = retries
        self._api_key = api_key
        self._auth_scheme = auth_scheme
        self._vision_capability_cache: dict[str, bool] = {}

    def _is_cloud_model(self, model: str) -> bool:
        return model.strip().lower().endswith("-cloud")

    def can_use_cloud_model(self, model: str) -> bool:
        return self._is_cloud_model(model) and bool(self._api_key)

    def _target_base_url(self, model: str | None = None) -> str:
        if model and self.can_use_cloud_model(model):
            return self._cloud_base_url
        return self._base_url

    def _request_headers(self, model: str | None = None) -> dict[str, str] | None:
        if model and self.can_use_cloud_model(model):
            return {"Authorization": f"{self._auth_scheme} {self._api_key}"}
        if model is None and self._api_key and self._base_url == self._cloud_base_url:
            return {"Authorization": f"{self._auth_scheme} {self._api_key}"}
        if not self._api_key:
            return None
        return None

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        context_turns: list[ConversationTurn],
        images: list[str] | None = None,
        keep_alive: str | None = None,
    ) -> OllamaResponse:
        started_at = monotonic()
        # Per /api/generate spec: extract the system turn and pass it as a dedicated
        # top-level field; remaining turns build the conversational prompt.
        system_turns = [t for t in context_turns if t.role == "system"]
        non_system_turns = [t for t in context_turns if t.role != "system"]
        system_content = system_turns[-1].content if system_turns else None
        composed_prompt = self._compose_prompt(prompt=prompt, context_turns=non_system_turns)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": composed_prompt,
            "stream": False,
        }
        if system_content:
            payload["system"] = system_content
        if images:
            payload["images"] = images
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout, headers=self._request_headers()) as client:
                    response = await client.post(
                        f"{self._target_base_url(model)}/api/generate",
                        json=payload,
                    )
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

    async def list_web_models(self) -> list[str]:
        started_at = monotonic()
        last_error: Exception | None = None
        library_url = "https://ollama.com/library"
        pattern = re.compile(r'href="/library/([a-zA-Z0-9][a-zA-Z0-9._:-]*)"')

        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(library_url)
                response.raise_for_status()

                matches = pattern.findall(response.text)
                models: list[str] = []
                seen: set[str] = set()
                for item in matches:
                    name = item.strip()
                    if not name:
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    models.append(name)

                elapsed_ms = int((monotonic() - started_at) * 1000)
                logger.info("ollama_list_web_models_ok count=%d elapsed_ms=%d", len(models), elapsed_ms)
                return models
            except httpx.TimeoutException as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_list_web_models_timeout_retry attempt=%d/%d",
                        attempt + 1,
                        self._retries + 1,
                    )
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaTimeoutError("Ollama web models request timed out") from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_list_web_models_connection_retry attempt=%d/%d",
                        attempt + 1,
                        self._retries + 1,
                    )
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaConnectionError("Could not reach Ollama web catalog") from error
            except httpx.HTTPStatusError as error:
                detail = error.response.text[:300]
                logger.warning("ollama_list_web_models_http_error status=%d", error.response.status_code)
                raise OllamaError(
                    f"Ollama web catalog returned HTTP {error.response.status_code}: {detail}"
                ) from error

        if last_error:
            raise OllamaError("Unexpected Ollama web catalog failure") from last_error
        raise OllamaError("Unexpected Ollama web catalog failure")

    async def chat(
        self,
        *,
        model: str,
        prompt: str,
        context_turns: list[ConversationTurn],
        keep_alive: str,
        response_format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        prompt_images: list[str] | None = None,
    ) -> OllamaResponse:
        started_at = monotonic()
        messages = self._compose_messages(prompt=prompt, context_turns=context_turns, prompt_images=prompt_images)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
        }
        if response_format is not None:
            payload["format"] = response_format
        if options:
            payload["options"] = options

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._request_headers(model),
                ) as client:
                    response = await client.post(
                        f"{self._target_base_url(model)}/api/chat",
                        json=payload,
                    )
                response.raise_for_status()
                data = response.json()
                message = data.get("message") or {}
                text = str(message.get("content", "")).strip()
                if not text:
                    raise OllamaError("Empty chat response from Ollama")

                elapsed_ms = int((monotonic() - started_at) * 1000)
                logger.info(
                    "ollama_chat_ok model=%s prompt_chars=%d context_turns=%d elapsed_ms=%d keep_alive=%s structured=%s",
                    model,
                    len(prompt),
                    len(context_turns),
                    elapsed_ms,
                    keep_alive,
                    response_format is not None,
                )
                return OllamaResponse(text=text)
            except httpx.TimeoutException as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_chat_timeout_retry model=%s attempt=%d/%d",
                        model,
                        attempt + 1,
                        self._retries + 1,
                    )
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaTimeoutError("Ollama chat request timed out") from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < self._retries:
                    logger.warning(
                        "ollama_chat_connection_retry model=%s attempt=%d/%d",
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
                    "ollama_chat_http_error model=%s status=%d",
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
                async with httpx.AsyncClient(timeout=self._timeout, headers=self._request_headers()) as client:
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

    async def supports_vision(self, model: str) -> bool | None:
        if model in self._vision_capability_cache:
            return self._vision_capability_cache[model]

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers=self._request_headers(model),
            ) as client:
                response = await client.post(
                    f"{self._target_base_url(model)}/api/show",
                    json={"model": model},
                )
            response.raise_for_status()
            data = response.json()
            capabilities = data.get("capabilities")

            if isinstance(capabilities, list):
                normalized = {str(item).strip().lower() for item in capabilities}
                if "vision" in normalized:
                    self._vision_capability_cache[model] = True
                    return True
                if normalized:
                    self._vision_capability_cache[model] = False
                    return False

            model_info = data.get("model_info") if isinstance(data, dict) else None
            if isinstance(model_info, dict):
                model_info_keys = " ".join(model_info.keys()).lower()
                if "vision" in model_info_keys or "clip" in model_info_keys:
                    self._vision_capability_cache[model] = True
                    return True

            logger.info(
                "ollama_show_capabilities_unknown model=%s payload_keys=%s",
                model,
                ",".join(sorted(data.keys())) if isinstance(data, dict) else "n/a",
            )
            return None
        except Exception as error:
            logger.warning("ollama_show_capabilities_failed model=%s error=%s", model, error)
            return None

    async def chat_with_image(
        self,
        *,
        model: str,
        prompt: str,
        images: list[str],
        context_turns: list[ConversationTurn],
        keep_alive: str,
    ) -> OllamaResponse:
        started_at = monotonic()
        messages = self._compose_messages(prompt=prompt, context_turns=context_turns, prompt_images=images)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
        }

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._request_headers(model),
                ) as client:
                    response = await client.post(
                        f"{self._target_base_url(model)}/api/chat",
                        json=payload,
                    )
                response.raise_for_status()
                data = response.json()
                message = data.get("message") or {}
                text = str(message.get("content", "")).strip()
                if not text:
                    raise OllamaError("Empty image chat response from Ollama")

                elapsed_ms = int((monotonic() - started_at) * 1000)
                logger.info(
                    "ollama_chat_image_ok model=%s prompt_chars=%d context_turns=%d elapsed_ms=%d",
                    model,
                    len(prompt),
                    len(context_turns),
                    elapsed_ms,
                )
                if self._looks_like_missing_image_response(text):
                    logger.warning(
                        "ollama_chat_image_suspect_no_image model=%s fallback=generate_with_image",
                        model,
                    )
                    return await self._generate_with_image(
                        model=model,
                        prompt=prompt,
                        images=images,
                        context_turns=context_turns,
                        keep_alive=keep_alive,
                    )
                return OllamaResponse(text=text)
            except httpx.TimeoutException as error:
                last_error = error
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaTimeoutError("Ollama image chat request timed out") from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaConnectionError("Could not reach Ollama") from error
            except httpx.HTTPStatusError as error:
                detail = error.response.text[:300]
                if error.response.status_code in {400, 404, 422}:
                    logger.warning(
                        "ollama_chat_image_http_fallback_generate model=%s status=%d",
                        model,
                        error.response.status_code,
                    )
                    return await self._generate_with_image(
                        model=model,
                        prompt=prompt,
                        images=images,
                        context_turns=context_turns,
                        keep_alive=keep_alive,
                    )
                raise OllamaError(
                    f"Ollama returned HTTP {error.response.status_code}: {detail}"
                ) from error

        if last_error:
            raise OllamaError("Unexpected Ollama failure") from last_error
        raise OllamaError("Unexpected Ollama failure")

    async def _generate_with_image(
        self,
        *,
        model: str,
        prompt: str,
        images: list[str],
        context_turns: list[ConversationTurn],
        keep_alive: str | None = None,
    ) -> OllamaResponse:
        started_at = monotonic()
        # Extract system turn for dedicated /api/generate system field
        system_turns = [t for t in context_turns if t.role == "system"]
        non_system_turns = [t for t in context_turns if t.role != "system"]
        system_content = system_turns[-1].content if system_turns else None
        composed_prompt = self._compose_prompt(prompt=prompt, context_turns=non_system_turns)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": composed_prompt,
            "images": images,
            "stream": False,
        }
        if system_content:
            payload["system"] = system_content
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._request_headers(model),
                ) as client:
                    response = await client.post(
                        f"{self._target_base_url(model)}/api/generate",
                        json=payload,
                    )
                response.raise_for_status()
                data = response.json()
                text = str(data.get("response", "")).strip()
                if not text:
                    raise OllamaError("Empty image generate response from Ollama")

                elapsed_ms = int((monotonic() - started_at) * 1000)
                logger.info(
                    "ollama_generate_image_ok model=%s prompt_chars=%d context_turns=%d elapsed_ms=%d",
                    model,
                    len(prompt),
                    len(context_turns),
                    elapsed_ms,
                )
                return OllamaResponse(text=text)
            except httpx.TimeoutException as error:
                last_error = error
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise OllamaTimeoutError("Ollama image generate request timed out") from error
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
    def _looks_like_missing_image_response(text: str) -> bool:
        """Return True only when the model explicitly states it cannot access an image.

        Patterns are intentionally narrow to avoid false positives on valid
        image-analysis responses that happen to mention the word "image".
        Covers English, Spanish, French, German and Italian.
        """
        normalized = text.strip().lower()
        if not normalized:
            return False

        patterns = (
            # English — model asks user to send an image it cannot see
            r"\b(send|upload|attach|provide)\b.{0,40}\b(image|photo|picture)\b",
            r"\b(cannot|can't|unable to)\b.{0,30}\b(see|view|access|process)\b.{0,40}\b(image|photo|picture)\b",
            r"\bno\s+(image|photo|picture)\s+(was\s+)?(provided|attached|found|included)\b",
            r"\bi\s+(do\s+not|don't)\s+(see|have|receive)\b.{0,30}\b(image|photo|picture)\b",
            # Spanish
            r"\b(env[ií]a?|adjunta?|proporciona?|comparte?)\b.{0,40}\b(imagen|foto|fotograf[ií]a)\b",
            r"\bno\s+puedo\b.{0,30}\b(ver|acceder|procesar)\b.{0,40}\b(imagen|foto)\b",
            r"\bno\s+(se\s+ha\s+|hay\s+)?(proporcionado|adjuntado|enviado)\b.{0,30}\b(imagen|foto)\b",
            r"\bno\s+(veo|tengo|recibo)\b.{0,30}\b(imagen|foto)\b",
            # German
            r"\b(sende?|lade?\s+hoch|h[äa]nge?\s+an)\b.{0,40}\b(bild|foto|abbildung)\b",
            r"\bkann\s+kein\b.{0,30}\b(bild|foto|abbildung)\b",
            r"\b(kein|keine)\s+(bild|foto|abbildung)\b.{0,30}\b(vorhanden|gefunden|angeh[äa]ngt)\b",
            # French
            r"\b(envoyer|joindre|fournir|partager)\b.{0,40}\b(image|photo)\b",
            r"\bne\s+(peux|suis)\s+pas\b.{0,30}\b(voir|acc[eé]der|traiter)\b.{0,40}\b(image|photo)\b",
            r"\baucune?\s+(image|photo)\b.{0,30}\b(fournie?|jointe?|trouv[ée]e?)\b",
            # Italian
            r"\b(invia|allega|fornisci|condividi)\b.{0,40}\b(immagine|foto)\b",
            r"\bnon\s+posso\b.{0,30}\b(vedere|accedere|elaborare)\b.{0,40}\b(immagine|foto)\b",
            r"\bnessuna?\s+(immagine|foto)\b.{0,30}\b(fornita|allegata|trovata)\b",
        )
        return any(re.search(pattern, normalized) for pattern in patterns)

    @staticmethod
    def _compose_prompt(prompt: str, context_turns: list[ConversationTurn]) -> str:
        if not context_turns:
            return prompt

        context_lines: list[str] = []
        for turn in context_turns:
            if turn.role == "system":
                role_label = "System"
            elif turn.role == "tool":
                role_label = "Tool"
            elif turn.role == "user":
                role_label = "User"
            else:
                role_label = "Assistant"
            context_lines.append(f"{role_label}: {turn.content}")

        context_lines.append(f"User: {prompt}")
        context_lines.append("Assistant:")
        return "\n".join(context_lines)

    @staticmethod
    def _compose_messages(
        prompt: str,
        context_turns: list[ConversationTurn],
        prompt_images: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Build the messages list for /api/chat.

        Per the Ollama spec, ``images`` are accepted per message object.
        Vision models only process images that appear in the conversation;
        in practice the current user turn is where images should be placed.
        History turns carry text-only content to provide descriptive context.
        """
        messages: list[dict[str, Any]] = []
        for turn in context_turns:
            if turn.role not in {"system", "user", "assistant", "tool"}:
                continue
            messages.append({"role": turn.role, "content": turn.content})

        current_msg: dict[str, Any] = {"role": "user", "content": prompt}
        if prompt_images:
            current_msg["images"] = prompt_images
        messages.append(current_msg)
        return messages

