"""Tests for ModelOrchestrator – task detection and vision cache."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.services.model_orchestrator import (
    ModelOrchestrator,
    TASK_CODE,
    TASK_GENERAL,
    TASK_VISION,
)


def _make_client(models: list[str], vision_models: set[str] | None = None) -> MagicMock:
    client = MagicMock()
    client.list_models = AsyncMock(return_value=models)
    if vision_models is None:
        vision_models = set()
    client.supports_vision = AsyncMock(side_effect=lambda m: m in vision_models)
    return client


def test_detect_task_vision_when_images() -> None:
    client = _make_client([])
    orch = ModelOrchestrator(client)
    assert orch.detect_task("describe this", has_images=True) == TASK_VISION


def test_detect_task_code_for_programming_keywords() -> None:
    client = _make_client([])
    orch = ModelOrchestrator(client)
    assert orch.detect_task("Write a python function to sort a list", has_images=False) == TASK_CODE


def test_detect_task_general_for_normal_text() -> None:
    client = _make_client([])
    orch = ModelOrchestrator(client)
    assert orch.detect_task("What is the weather like?", has_images=False) == TASK_GENERAL


def test_select_model_general_returns_preferred() -> None:
    client = _make_client(["llama3.2"])
    orch = ModelOrchestrator(client)
    model, changed, found = asyncio.get_event_loop().run_until_complete(
        orch.select_model(TASK_GENERAL, "llama3.2")
    )
    assert model == "llama3.2"
    assert changed is False
    assert found is True


def test_select_model_vision_finds_alternative() -> None:
    client = _make_client(
        ["llama3.2", "llava:7b"],
        vision_models={"llava:7b"},
    )
    orch = ModelOrchestrator(client)
    model, changed, found = asyncio.get_event_loop().run_until_complete(
        orch.select_model(TASK_VISION, "llama3.2")
    )
    assert model == "llava:7b"
    assert changed is True
    assert found is True


def test_select_model_vision_no_vision_model() -> None:
    client = _make_client(["llama3.2", "codellama"], vision_models=set())
    orch = ModelOrchestrator(client)
    model, changed, found = asyncio.get_event_loop().run_until_complete(
        orch.select_model(TASK_VISION, "llama3.2")
    )
    assert model == "llama3.2"
    assert changed is False
    assert found is False


def test_select_model_code_finds_code_model() -> None:
    client = _make_client(["llama3.2", "deepseek-coder:7b"])
    orch = ModelOrchestrator(client)
    model, changed, found = asyncio.get_event_loop().run_until_complete(
        orch.select_model(TASK_CODE, "llama3.2")
    )
    assert model == "deepseek-coder:7b"
    assert changed is True
    assert found is True


def test_vision_cache_reused() -> None:
    client = _make_client(["llama3.2", "llava:7b"], vision_models={"llava:7b"})
    orch = ModelOrchestrator(client)

    loop = asyncio.get_event_loop()
    # First call populates cache
    loop.run_until_complete(orch.select_model(TASK_VISION, "llama3.2"))
    first_call_count = client.supports_vision.call_count

    # Second call should use cache
    loop.run_until_complete(orch.select_model(TASK_VISION, "llama3.2"))
    assert client.supports_vision.call_count == first_call_count  # No new calls
