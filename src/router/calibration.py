"""Calibration runner — measures routing quality against a prompt suite."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import yaml

from router.classifier import classify_request
from router.cost import compute_cost
from router.engine import route_request
from router.models import CalibrationPrompt, CalibrationResult, TaskType, estimate_tokens
from router.providers import ProviderUnavailableError, ModelCallError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_calibration_prompts(config_dir: Optional[Path] = None) -> list[CalibrationPrompt]:
    """Load calibration prompts from config/calibration_prompts.yaml."""
    if config_dir is None:
        config_dir = Path(__file__).parent.parent.parent / "config"
    path = Path(config_dir) / "calibration_prompts.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Calibration prompts not found: {path}")

    with path.open() as f:
        data = yaml.safe_load(f) or {}

    prompts = []
    for item in data.get("prompts", []):
        prompts.append(CalibrationPrompt(
            id=item["id"],
            category=item["category"],
            prompt=item["prompt"],
            expected_task_type=TaskType(item["expected_task_type"]),
            expected_best_model=item.get("expected_best_model"),
        ))
    return prompts


# ---------------------------------------------------------------------------
# Per-prompt result
# ---------------------------------------------------------------------------

@dataclass
class PromptResult:
    prompt_id: str
    category: str
    expected_task_type: TaskType
    actual_task_type: TaskType
    correct_classification: bool
    routed_model: str
    input_tokens: int
    output_tokens: int
    cost: float
    router_overhead_ms: int
    model_latency_ms: int   # 0 if no model was called


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_calibration(
    prompts: list[CalibrationPrompt],
    config,                              # RouterConfig
    model_call_fn: Optional[Callable] = None,
) -> CalibrationResult:
    """
    Run calibration against a prompt suite.

    Args:
        prompts:        CalibrationPrompt list from config.
        config:         RouterConfig (providers, rules, default_model).
        model_call_fn:  Optional callable(model_name, messages) -> str.
                        When None, routing is computed but no model is called
                        (classify-only mode — safe for unit/integration tests).

    Returns:
        CalibrationResult with all 5 metrics populated.
    """
    prompt_results: list[PromptResult] = []
    providers_by_name = {p.name: p for p in config.providers}

    for cp in prompts:
        messages = [{"role": "user", "content": cp.prompt}]

        # --- Classify and route ---
        t0 = time.monotonic()
        classification = classify_request(messages)
        decision = route_request(classification, config.rules, config.default_model)
        router_overhead_ms = int((time.monotonic() - t0) * 1000)

        routed_model = decision.selected_model

        # --- Optionally call the model ---
        model_latency_ms = 0
        response_text = ""
        if model_call_fn is not None:
            t1 = time.monotonic()
            try:
                response_text = model_call_fn(routed_model, messages)
            except (ProviderUnavailableError, ModelCallError, ConnectionError, TimeoutError) as exc:
                logger.warning("Model call failed for %s: %s", routed_model, exc)
                response_text = ""
            model_latency_ms = int((time.monotonic() - t1) * 1000)

        # --- Cost estimate ---
        input_tokens = classification.token_estimate
        output_tokens = estimate_tokens(response_text) if response_text else 0
        provider = providers_by_name.get(routed_model)
        cost = (
            compute_cost(input_tokens, output_tokens, provider.input_price, provider.output_price)
            if provider else 0.0
        )

        prompt_results.append(PromptResult(
            prompt_id=cp.id,
            category=cp.category,
            expected_task_type=cp.expected_task_type,
            actual_task_type=classification.task_type,
            correct_classification=classification.task_type == cp.expected_task_type,
            routed_model=routed_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            router_overhead_ms=router_overhead_ms,
            model_latency_ms=model_latency_ms,
        ))

    return _compute_metrics(prompt_results, config)


# ---------------------------------------------------------------------------
# Metrics computation (T045)
# ---------------------------------------------------------------------------

def _compute_metrics(results: list[PromptResult], config) -> CalibrationResult:
    # win_rate_by_task — proxy: classification accuracy per task type
    categories: dict[str, list[bool]] = {}
    for r in results:
        cat = r.expected_task_type.value
        categories.setdefault(cat, []).append(r.correct_classification)

    win_rate_by_task: dict[str, dict[str, float]] = {}
    for cat, hits in categories.items():
        rate = sum(hits) / len(hits)
        win_rate_by_task[cat] = {"classification_accuracy": round(rate, 3)}

    # avg_latency_by_model
    latency_by_model: dict[str, list[int]] = {}
    for r in results:
        latency_by_model.setdefault(r.routed_model, []).append(
            r.model_latency_ms + r.router_overhead_ms
        )
    avg_latency_by_model = {
        m: round(sum(lats) / len(lats), 1)
        for m, lats in latency_by_model.items()
    }

    # total_cost_by_model
    cost_by_model: dict[str, float] = {}
    for r in results:
        cost_by_model[r.routed_model] = cost_by_model.get(r.routed_model, 0.0) + r.cost

    # regret_rate — fraction of prompts with wrong classification (would re-route)
    wrong = sum(1 for r in results if not r.correct_classification)
    regret_rate = round(wrong / len(results), 3) if results else 0.0

    # cost_vs_baseline — savings fraction vs all-Sonnet
    baseline_provider = next(
        (p for p in config.providers if p.name == config.default_model), None
    )
    if baseline_provider:
        baseline_total = sum(
            compute_cost(
                r.input_tokens, r.output_tokens,
                baseline_provider.input_price, baseline_provider.output_price,
            )
            for r in results
        )
    else:
        baseline_total = 0.0

    actual_total = sum(r.cost for r in results)
    cost_vs_baseline = (
        round((baseline_total - actual_total) / baseline_total, 3)
        if baseline_total > 0 else 0.0
    )

    models_tested = sorted(set(r.routed_model for r in results))

    return CalibrationResult(
        run_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        prompts_count=len(results),
        models_tested=models_tested,
        win_rate_by_task=win_rate_by_task,
        avg_latency_by_model=avg_latency_by_model,
        total_cost_by_model={k: round(v, 6) for k, v in cost_by_model.items()},
        regret_rate=regret_rate,
        cost_vs_baseline=cost_vs_baseline,
    )