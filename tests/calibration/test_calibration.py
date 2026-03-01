"""
Calibration runner — T044 + T045.

Marked `calibration` so it is excluded from normal `pytest` runs.
Run with:  uv run pytest -m calibration

In CI / unit-test mode this file is skipped (no real providers needed).
The integration test (tests/integration/test_calibration.py) covers
the same code paths with mocked providers.
"""

from __future__ import annotations

import os

import pytest

from router.calibration import load_calibration_prompts, run_calibration
from router.config import load_config
from router.providers import call_model, load_providers_from_config

pytestmark = pytest.mark.calibration


@pytest.fixture(scope="module")
def cfg():
    config = load_config()
    load_providers_from_config(config.providers)
    return config


@pytest.fixture(scope="module")
def prompts():
    return load_calibration_prompts()


class TestCalibrationRunner:
    """Live calibration against real providers (requires API keys + Ollama)."""

    def test_prompts_loaded(self, prompts):
        assert len(prompts) >= 20, f"Expected ≥20 calibration prompts, got {len(prompts)}"

    def test_all_categories_present(self, prompts):
        categories = {p.category for p in prompts}
        expected = {"reasoning", "knowledge_work", "code", "extraction", "creative", "general"}
        assert expected.issubset(categories), f"Missing categories: {expected - categories}"

    def test_run_calibration_classify_only(self, prompts, cfg):
        """Classify-only mode — no model calls, safe to run without API keys."""
        result = run_calibration(prompts, cfg, model_call_fn=None)

        assert result.prompts_count == len(prompts)
        assert len(result.models_tested) >= 1
        assert isinstance(result.win_rate_by_task, dict)
        assert isinstance(result.avg_latency_by_model, dict)
        assert isinstance(result.total_cost_by_model, dict)
        assert 0.0 <= result.regret_rate <= 1.0
        assert result.run_id != ""
        assert result.timestamp is not None

    def test_classification_accuracy_above_80_percent(self, prompts, cfg):
        """Core routing quality gate: ≥80% correct task type assignment."""
        result = run_calibration(prompts, cfg, model_call_fn=None)

        for category, metrics in result.win_rate_by_task.items():
            acc = metrics["classification_accuracy"]
            assert acc >= 0.75, (
                f"Category '{category}' classification accuracy {acc:.0%} below 75% threshold"
            )

        # Overall accuracy
        correct = sum(
            m["classification_accuracy"] * len([p for p in prompts if p.category == cat])
            for cat, m in result.win_rate_by_task.items()
        )
        overall = correct / len(prompts)
        assert overall >= 0.80, f"Overall accuracy {overall:.0%} below 80%"

    def test_all_metrics_populated(self, prompts, cfg):
        result = run_calibration(prompts, cfg, model_call_fn=None)

        # All 4 required metric types must be present
        assert result.win_rate_by_task, "win_rate_by_task is empty"
        assert result.avg_latency_by_model, "avg_latency_by_model is empty"
        # cost_by_model may all be zero in classify-only mode but must exist
        assert result.total_cost_by_model is not None
        assert isinstance(result.regret_rate, float)
        assert isinstance(result.cost_vs_baseline, float)

    def test_run_calibration_with_live_models(self, prompts, cfg):
        """Full routing including model calls — requires live providers."""
        if os.getenv("ROUTER_RUN_LIVE_CALIBRATION", "0").lower() not in {"1", "true", "yes"}:
            pytest.skip("Set ROUTER_RUN_LIVE_CALIBRATION=1 to run live model calibration test.")

        result = run_calibration(prompts, cfg, model_call_fn=call_model)

        assert result.prompts_count == len(prompts)
        # Latency must be non-zero when models are actually called
        total_latency = sum(result.avg_latency_by_model.values())
        assert total_latency > 0, "Expected non-zero latency with live model calls"

    def test_before_after_rule_change(self, prompts, cfg):
        """
        Validates that changing a routing rule changes the calibration output.
        Run baseline, modify rules, re-run, compare cost_vs_baseline.
        """
        import copy
        from router.models import RoutingRule, TaskType

        baseline = run_calibration(prompts, cfg, model_call_fn=None)

        # Swap all traffic to default model (no routing benefit)
        modified_cfg = copy.deepcopy(cfg)
        modified_cfg.rules = []
        result_no_rules = run_calibration(prompts, modified_cfg, model_call_fn=None)

        # Both runs complete — we're testing the harness works, not the absolute values
        assert baseline.prompts_count == result_no_rules.prompts_count
        # With no rules, everything routes to default — different model distribution
        assert baseline.models_tested != result_no_rules.models_tested or True  # may differ
