"""Integration test for the full pipeline with mocked provider calls (T026)."""

from __future__ import annotations

import pytest
from unittest.mock import patch
from pathlib import Path

from router.pipeline import handle_request, reload_config, _call_with_fallback
from router.models import TaskType
from router.providers import ProviderUnavailableError


CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


@pytest.fixture(autouse=True)
def reset_config():
    reload_config(CONFIG_DIR)
    yield


class TestPipelineRouting:
    @patch("router.pipeline.check_provider_health", return_value=True)
    @patch("router.pipeline.call_model", return_value="Gemini answer")
    def test_reasoning_routes_to_gemini(self, mock_call, mock_health):
        result = handle_request([{"role": "user", "content": (
            "Prove step by step that there are infinitely many prime numbers. "
            "First assume finitely many primes. Then derive a contradiction. "
            "Finally conclude the logical proof."
        )}])
        assert result.model_used == "gemini"
        assert result.response == "Gemini answer"
        assert result.task_type == TaskType.reasoning.value

    @patch("router.pipeline.check_provider_health", return_value=True)
    @patch("router.pipeline.call_model", return_value="Local answer")
    def test_extraction_routes_to_local(self, mock_call, mock_health):
        result = handle_request([{"role": "user", "content":
            "Summarize this paragraph in two sentences: The AI revolution is here."}])
        assert result.model_used == "ollama-qwen35"
        assert result.task_type == TaskType.extraction.value

    @patch("router.pipeline.check_provider_health", return_value=True)
    @patch("router.pipeline.call_model", return_value="Answer")
    def test_result_includes_cost_and_latency(self, mock_call, mock_health):
        result = handle_request([{"role": "user", "content":
            "Summarize: The cat sat on the mat."}])
        assert isinstance(result.estimated_cost, float)
        assert result.estimated_cost >= 0.0
        assert result.latency_ms >= 0

    @patch("router.pipeline.call_model", return_value="Fallback answer")
    def test_fallback_triggered_when_primary_down(self, mock_call):
        def health_check(name: str) -> bool:
            return name != "gemini"

        with patch("router.pipeline.check_provider_health", side_effect=health_check):
            result = handle_request([{"role": "user", "content": (
                "Prove step by step that there are infinitely many prime numbers. "
                "First assume finitely many. Then derive a contradiction. Finally conclude."
            )}])

        assert result.fallback_triggered is True
        assert result.model_used != "gemini"

    @patch("router.pipeline.check_provider_health", return_value=True)
    @patch("router.pipeline.call_model", return_value="Paid local answer")
    def test_local_ollama_uses_configured_pricing(self, mock_call, mock_health):
        result = handle_request([{"role": "user", "content":
            "Translate this to French: Hello world."}])
        if result.model_used == "ollama-qwen35":
            assert result.estimated_cost > 0.0

    @patch("router.pipeline.check_provider_health", return_value=True)
    @patch("router.pipeline.call_model", return_value="Answer despite log failure")
    @patch("router.pipeline.log_request", side_effect=PermissionError("read-only filesystem"))
    def test_request_succeeds_when_logging_fails(self, mock_log, mock_call, mock_health):
        result = handle_request([{"role": "user", "content":
            "Summarize this sentence in five words: AI routing reduces cost."}])
        assert result.response == "Answer despite log failure"
        assert result.model_used in {"sonnet", "gemini", "ollama-qwen35", "qwen"}


class TestFallbackExecution:
    @patch("router.pipeline.call_model")
    def test_call_with_fallback_deduplicates_candidates(self, mock_call):
        """
        If model_used is also present in fallback_chain, it should only appear once
        in candidate iteration (with the built-in primary retry still preserved).
        """
        calls: list[str] = []

        def _side_effect(model: str, messages: list[dict]) -> str:
            calls.append(model)
            if model == "sonnet":
                raise ProviderUnavailableError("down")
            return "Recovered on fallback"

        mock_call.side_effect = _side_effect

        response, model_used, fallback_triggered = _call_with_fallback(
            "sonnet",
            ["sonnet", "ollama-qwen35"],
            [{"role": "user", "content": "hello"}],
        )

        assert response == "Recovered on fallback"
        assert model_used == "ollama-qwen35"
        assert fallback_triggered is True
        assert calls == ["sonnet", "sonnet", "ollama-qwen35"]
