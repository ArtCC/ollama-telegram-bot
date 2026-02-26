"""Model orchestrator: selects the best available local Ollama model for a task.

Task types
----------
- ``vision``  — message includes images; needs a vision-capable model
- ``code``    — prompt contains programming keywords; prefers a code-specialised model
- ``general`` — everything else; the user's preferred model is returned unchanged

The orchestrator caches the available model list for :data:`_MODELS_CACHE_TTL` seconds
and re-uses the vision capability cache already maintained by :class:`OllamaClient`.
"""
from __future__ import annotations

import logging
from time import monotonic

from src.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# ── Task constants ────────────────────────────────────────────────────────────
TASK_VISION = "vision"
TASK_CODE = "code"
TASK_GENERAL = "general"

# ── Code-task heuristics ──────────────────────────────────────────────────────
# Substrings that, when found in the lowercase prompt, signal a coding request.
_CODE_KEYWORDS: frozenset[str] = frozenset(
    [
        # Generic programming terms
        "function",
        "class",
        "method",
        "variable",
        "loop",
        "algorithm",
        "compile",
        "syntax",
        "runtime",
        "debug",
        "refactor",
        "optimize",
        "def ",
        "import ",
        "return ",
        "if ",
        "else ",
        "for ",
        "while ",
        "error",
        "exception",
        "traceback",
        "stack trace",
        "null pointer",
        # Languages / ecosystems
        "python",
        "javascript",
        "typescript",
        "java",
        "kotlin",
        "swift",
        "rust",
        "golang",
        "go ",
        "c++",
        "c#",
        "php",
        "ruby",
        "bash",
        "sql",
        "html",
        "css",
        "json",
        "yaml",
        "xml",
        # Spanish
        "función",
        "clase",
        "código",
        "programa",
        "depurar",
        "depuración",
        "excepción",
        # German
        "funktion",
        "klasse",
        "fehler",
        "programm",
        # French
        "fonction",
        "classe",
        "erreur",
        "programme",
        # Italian
        "funzione",
        "codice",
        "programma",
    ]
)

# Name fragments that identify a model as code-specialised.
_CODE_MODEL_PATTERNS: tuple[str, ...] = (
    "code",
    "coder",
    "codegen",
    "codellama",
    "starcoder",
    "deepseek-coder",
    "qwen-coder",
    "wizard-coder",
    "phind",
    "magicoder",
    "codegemma",
    "codestral",
    "devstral",
)

# How long (seconds) to keep the available-model list cache.
_MODELS_CACHE_TTL: float = 60.0


def _is_code_model(name: str) -> bool:
    lower = name.lower()
    return any(p in lower for p in _CODE_MODEL_PATTERNS)


class ModelOrchestrator:
    """Selects the best available local model for a given task."""

    def __init__(self, ollama_client: OllamaClient) -> None:
        self._client = ollama_client
        self._models_cache: list[str] = []
        self._models_cache_at: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def detect_task(self, prompt: str, has_images: bool) -> str:
        """Return the task type inferred from the message."""
        if has_images:
            return TASK_VISION
        text = prompt.lower()
        if any(kw in text for kw in _CODE_KEYWORDS):
            return TASK_CODE
        return TASK_GENERAL

    async def select_model(
        self,
        task: str,
        preferred_model: str,
    ) -> tuple[str, bool, bool]:
        """Return ``(selected_model, changed, found_suitable)``.

        Parameters
        ----------
        task:
            One of :data:`TASK_VISION`, :data:`TASK_CODE`, :data:`TASK_GENERAL`.
        preferred_model:
            The user's currently active model.

        Returns
        -------
        selected_model:
            The model that should be used for this request.
        changed:
            ``True`` when ``selected_model != preferred_model``.
        found_suitable:
            ``True`` when a model that fits the task was found.
            Only ever ``False`` for :data:`TASK_VISION` when no vision model is
            installed locally — the caller should warn the user.
        """
        if task == TASK_GENERAL:
            return preferred_model, False, True

        models = await self._get_models()

        if task == TASK_VISION:
            # Preferred model already supports vision? Keep it.
            preferred_vision = await self._client.supports_vision(preferred_model)
            if preferred_vision is True:
                logger.debug(
                    "orchestrator VISION preferred_model=%s already supports vision",
                    preferred_model,
                )
                return preferred_model, False, True

            # Scan for a vision-capable model.
            for model in models:
                if model == preferred_model:
                    continue
                cap = await self._client.supports_vision(model)
                if cap is True:
                    logger.info(
                        "orchestrator VISION selected=%s preferred=%s",
                        model,
                        preferred_model,
                    )
                    return model, True, True

            logger.warning(
                "orchestrator VISION no_vision_model_found preferred=%s available=%d",
                preferred_model,
                len(models),
            )
            return preferred_model, False, False

        if task == TASK_CODE:
            # Preferred model already matches code pattern? Keep it.
            if _is_code_model(preferred_model):
                logger.debug(
                    "orchestrator CODE preferred_model=%s already a code model",
                    preferred_model,
                )
                return preferred_model, False, True

            # Scan for a code-specialised model.
            for model in models:
                if _is_code_model(model):
                    logger.info(
                        "orchestrator CODE selected=%s preferred=%s",
                        model,
                        preferred_model,
                    )
                    return model, True, True

            # No dedicated code model found — use preferred with a soft notice.
            logger.info(
                "orchestrator CODE no_code_model_found preferred=%s",
                preferred_model,
            )
            return preferred_model, False, False

        return preferred_model, False, True

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _get_models(self) -> list[str]:
        now = monotonic()
        if (now - self._models_cache_at) < _MODELS_CACHE_TTL and self._models_cache:
            return self._models_cache
        try:
            self._models_cache = await self._client.list_models()
            self._models_cache_at = now
            logger.debug(
                "orchestrator models_cache_refreshed count=%d",
                len(self._models_cache),
            )
        except Exception as err:
            logger.warning("orchestrator models_cache_refresh_failed error=%s", err)
        return self._models_cache
