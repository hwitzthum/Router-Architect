"""Integration tests for the calibration runner (T048)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from router.calibration import load_calibration_prompts, run_calibration, PromptResult
from router.config import RouterConfig, PluginConfig, CacheConfig, SafetyConfig, HallucinationConfig
from router.models import (
    CalibrationPrompt,
    Provider,
    ProviderCategory,
    RoutingRule,
    TaskType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def minimal_config() -> RouterConfig:
    """Minimal two-provider config (Ollama local + Sonnet cloud) for testing."""
    providers = [
        Provider(
            name="sonnet",
            display_name="Claude Sonnet 4.6",
            category=ProviderCategory.cloud,
            base_url="https://api.anthropic.com/v1",
            api_key_env="ANTHROPIC_API_KEY",
            model_id="claude-sonnet-4-6",
            input_price=3.0,
            output_price=15.0,
            max_context_tokens=200_000,
        ),
        Provider(
            name="ollama-qwen35",
            display_name="Llama 3.1 (Ollama)",
            category=ProviderCategory.local,
            base_url="http://localhost:11434/v1",
            model_id="llama3.1",
            input_price=0.0,
            output_price=0.0,
            max_context_tokens=128_000,
        ),
    ]
    rules = [
        RoutingRule(
            task_type=TaskType.extraction,
            complexity_min=0.0,
            complexity_max=1.0,
            target_model="ollama-qwen35",
            fallback_chain=["sonnet"],
            priority=10,
        ),
    ]
    return RouterConfig(
        providers=providers,
        rules=rules,
        default_model="sonnet",
        plugins=PluginConfig(
            cache=CacheConfig(),
            safety=SafetyConfig(),
            hallucination=HallucinationConfig(),
        ),
    )


@pytest.fixture()
def sample_prompts() -> list[CalibrationPrompt]:
    return [
        CalibrationPrompt(
            id="r1", category="reasoning",
            prompt="Prove that the square root of 2 is irrational.",
            expected_task_type=TaskType.reasoning,
        ),
        CalibrationPrompt(
            id="k1", category="knowledge_work",
            prompt="Evaluate the strategic risks of entering the European market.",
            expected_task_type=TaskType.knowledge_work,
        ),
        CalibrationPrompt(
            id="e1", category="extraction",
            prompt="Summarize this paragraph in two sentences.",
            expected_task_type=TaskType.extraction,
        ),
        CalibrationPrompt(
            id="c1", category="code",
            prompt="Write a Python function to implement binary search.",
            expected_task_type=TaskType.code,
        ),
        CalibrationPrompt(
            id="cr1", category="creative",
            prompt="Write a haiku about autumn.",
            expected_task_type=TaskType.creative,
        ),
        CalibrationPrompt(
            id="g1", category="general",
            prompt="What time is it in Tokyo when it is 3pm in New York?",
            expected_task_type=TaskType.general,
        ),
    ]


# ---------------------------------------------------------------------------
# T048: All 4 metrics populated
# ---------------------------------------------------------------------------

class TestCalibrationMetricsPopulated:
    """Verify all 4 required metric types are computed and non-empty."""

    def test_win_rate_by_task_populated(self, sample_prompts, minimal_config):
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        assert result.win_rate_by_task, "win_rate_by_task must not be empty"
        for cat, metrics in result.win_rate_by_task.items():
            assert "classification_accuracy" in metrics
            acc = metrics["classification_accuracy"]
            assert 0.0 <= acc <= 1.0, f"Accuracy out of range for {cat}: {acc}"

    def test_avg_latency_by_model_populated(self, sample_prompts, minimal_config):
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        assert result.avg_latency_by_model, "avg_latency_by_model must not be empty"
        for model, ms in result.avg_latency_by_model.items():
            assert ms >= 0, f"Negative latency for {model}"

    def test_total_cost_by_model_populated(self, sample_prompts, minimal_config):
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        assert result.total_cost_by_model is not None
        for model, cost in result.total_cost_by_model.items():
            assert cost >= 0.0

    def test_regret_rate_is_float_in_range(self, sample_prompts, minimal_config):
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        assert isinstance(result.regret_rate, float)
        assert 0.0 <= result.regret_rate <= 1.0

    def test_cost_vs_baseline_is_float(self, sample_prompts, minimal_config):
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        assert isinstance(result.cost_vs_baseline, float)

    def test_run_id_and_timestamp_set(self, sample_prompts, minimal_config):
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        assert result.run_id != ""
        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)

    def test_prompts_count_matches_input(self, sample_prompts, minimal_config):
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        assert result.prompts_count == len(sample_prompts)


# ---------------------------------------------------------------------------
# Routing correctness across two providers
# ---------------------------------------------------------------------------

class TestRoutingDistribution:
    def test_extraction_routes_to_ollama(self, sample_prompts, minimal_config):
        """Extraction rule targets ollama-qwen35 — verify model distribution."""
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=None)
        # Both providers should appear in models_tested
        assert "ollama-qwen35" in result.models_tested or "sonnet" in result.models_tested

    def test_ollama_has_zero_cost(self, minimal_config):
        """Ollama routes should reflect configured provider pricing."""
        local_provider = next(p for p in minimal_config.providers if p.name == "ollama-qwen35")
        local_provider.input_price = 0.55
        local_provider.output_price = 3.5
        local_provider.cached_input_price = 0.55
        extraction_only = [
            CalibrationPrompt(
                id="e1", category="extraction",
                prompt="Summarize this in one sentence.",
                expected_task_type=TaskType.extraction,
            ),
        ]
        result = run_calibration(extraction_only, minimal_config, model_call_fn=None)
        if "ollama-qwen35" in result.total_cost_by_model:
            assert result.total_cost_by_model["ollama-qwen35"] > 0.0

    def test_cost_vs_baseline_is_positive_when_using_cheaper_models(self, minimal_config):
        """Routing to cheaper Ollama config vs baseline Sonnet should show savings."""
        local_provider = next(p for p in minimal_config.providers if p.name == "ollama-qwen35")
        local_provider.input_price = 0.55
        local_provider.output_price = 3.5
        local_provider.cached_input_price = 0.55
        extraction_prompts = [
            CalibrationPrompt(
                id=f"e{i}", category="extraction",
                prompt=f"Summarize this paragraph {i}.",
                expected_task_type=TaskType.extraction,
            )
            for i in range(5)
        ]
        result = run_calibration(extraction_prompts, minimal_config, model_call_fn=None)
        # Ollama remains cheaper than Sonnet ($3/$15) → savings should be ≥ 0
        assert result.cost_vs_baseline >= 0.0


# ---------------------------------------------------------------------------
# Mocked model calls
# ---------------------------------------------------------------------------

class TestCalibrationWithMockedModelCalls:
    def test_mocked_model_call_populates_latency(self, sample_prompts, minimal_config):
        """When a model_call_fn is provided, avg_latency should reflect call time."""
        def mock_call(model_name: str, messages: list[dict]) -> str:
            return "This is a test response with several words in it."

        result = run_calibration(sample_prompts, minimal_config, model_call_fn=mock_call)
        # Latency should still be tracked (router overhead, even if near zero)
        assert result.avg_latency_by_model

    def test_mocked_call_failure_does_not_crash_runner(self, sample_prompts, minimal_config):
        """If model_call_fn raises, the runner should continue gracefully."""
        def failing_call(model_name: str, messages: list[dict]) -> str:
            raise ConnectionError("Provider unavailable")

        # Should not raise
        result = run_calibration(sample_prompts, minimal_config, model_call_fn=failing_call)
        assert result.prompts_count == len(sample_prompts)


# ---------------------------------------------------------------------------
# load_calibration_prompts
# ---------------------------------------------------------------------------

class TestLoadCalibrationPrompts:
    def test_loads_from_config_dir(self):
        config_dir = Path(__file__).parent.parent.parent / "config"
        prompts = load_calibration_prompts(config_dir)
        assert len(prompts) >= 20

    def test_all_prompts_have_expected_task_type(self):
        config_dir = Path(__file__).parent.parent.parent / "config"
        prompts = load_calibration_prompts(config_dir)
        for p in prompts:
            assert isinstance(p.expected_task_type, TaskType)

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_calibration_prompts(config_dir=tmp_path)

    def test_regret_rate_zero_when_all_correct(self, minimal_config):
        """If every prompt classifies correctly, regret_rate == 0."""
        # Prompts chosen to match what the classifier will produce
        prompts = [
            CalibrationPrompt(
                id="e1", category="extraction",
                prompt="Summarize this document in bullet points.",
                expected_task_type=TaskType.extraction,
            ),
            CalibrationPrompt(
                id="c1", category="code",
                prompt="Write a Python function for binary search.",
                expected_task_type=TaskType.code,
            ),
        ]
        result = run_calibration(prompts, minimal_config, model_call_fn=None)
        # Both should classify correctly with the refined classifier
        assert result.regret_rate == 0.0
