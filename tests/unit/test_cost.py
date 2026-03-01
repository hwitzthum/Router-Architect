"""Unit tests for cost computation and reporting (Phase 5 / US3 — T038)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from router.cost import compute_cost, get_cost_summary, log_request
from router.models import (
    ClassificationResult,
    CostSummary,
    RequestRecord,
    RoutingDecision,
    TaskType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    model: str = "sonnet",
    task_type: TaskType = TaskType.knowledge_work,
    input_tokens: int = 1_000,
    output_tokens: int = 500,
    cost: float = 0.01050,
    cache_hit: bool = False,
    fallback_triggered: bool = False,
    ts: datetime | None = None,
) -> RequestRecord:
    return RequestRecord(
        messages=[{"role": "user", "content": "test"}],
        classification=ClassificationResult(
            task_type=task_type,
            complexity=0.5,
            token_estimate=input_tokens,
        ),
        routing=RoutingDecision(
            selected_model=model,
            fallback_chain=[],
            reason="test",
        ),
        model_used=model,
        response="test response",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        latency_ms=200,
        router_overhead_ms=10,
        cache_hit=cache_hit,
        fallback_triggered=fallback_triggered,
        timestamp=ts or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# T038a: compute_cost — pricing math
# ---------------------------------------------------------------------------

class TestComputeCost:
    """Verify per-million-token pricing arithmetic."""

    def test_cloud_pricing_sonnet(self):
        # 1M input at $3/M + 1M output at $15/M = $18
        cost = compute_cost(1_000_000, 1_000_000, input_price=3.0, output_price=15.0)
        assert abs(cost - 18.0) < 1e-9

    def test_cloud_pricing_gemini(self):
        # 500k input at $2/M + 200k output at $12/M
        cost = compute_cost(500_000, 200_000, input_price=2.0, output_price=12.0)
        assert abs(cost - (1.0 + 2.4)) < 1e-9

    def test_cloud_pricing_partial_tokens(self):
        # 1_000 input at $3/M + 500 output at $15/M
        cost = compute_cost(1_000, 500, input_price=3.0, output_price=15.0)
        expected = (1_000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert abs(cost - expected) < 1e-9

    def test_self_hosted_zero_price(self):
        # vLLM / self-hosted has amortized cost but zero per-token charge
        cost = compute_cost(10_000, 5_000, input_price=0.0, output_price=0.0)
        assert cost == 0.0

    def test_local_ollama_zero_price(self):
        # Ollama local model — always free
        cost = compute_cost(100_000, 80_000, input_price=0.0, output_price=0.0)
        assert cost == 0.0

    def test_zero_tokens(self):
        cost = compute_cost(0, 0, input_price=3.0, output_price=15.0)
        assert cost == 0.0

    def test_output_only_cost(self):
        cost = compute_cost(0, 1_000_000, input_price=3.0, output_price=15.0)
        assert abs(cost - 15.0) < 1e-9

    def test_cached_input_pricing(self):
        # 1M input total, of which 300k cached at $0.3/M, rest at $3/M
        # + 500k output at $15/M
        cost = compute_cost(
            input_tokens=1_000_000,
            output_tokens=500_000,
            input_price=3.0,
            output_price=15.0,
            cached_input_tokens=300_000,
            cached_input_price=0.3,
        )
        expected = (700_000 / 1_000_000) * 3.0 + (300_000 / 1_000_000) * 0.3 + (500_000 / 1_000_000) * 15.0
        assert abs(cost - expected) < 1e-9

    def test_qwen_pricing(self):
        # Qwen: $0.60/M input, $3.60/M output
        cost = compute_cost(1_000_000, 1_000_000, input_price=0.60, output_price=3.60)
        assert abs(cost - 4.20) < 1e-9


# ---------------------------------------------------------------------------
# T038b: log_request + get_cost_summary — JSONL round-trip
# ---------------------------------------------------------------------------

class TestCostLoggingAndSummary:
    """Verify JSONL logging and cost aggregation."""

    def test_log_creates_file(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        record = _make_record()
        log_request(record, log_file=log_file)
        assert log_file.exists()

    def test_log_appends_valid_json_lines(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        r1 = _make_record(model="sonnet", cost=0.01)
        r2 = _make_record(model="gemini", cost=0.02)
        log_request(r1, log_file=log_file)
        log_request(r2, log_file=log_file)

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            entry = json.loads(line)
            assert "model_used" in entry
            assert "cost" in entry
            assert "timestamp" in entry

    def test_summary_empty_when_no_log(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        summary = get_cost_summary(log_file=log_file)
        assert summary.request_count == 0
        assert summary.total_cost == 0.0
        assert summary.savings_percentage == 0.0

    def test_summary_totals_multiple_models(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        # Sonnet: $3/M input, $15/M output → cost for 1k in + 500 out
        sonnet_cost = compute_cost(1_000, 500, 3.0, 15.0)
        # Qwen: $0.60/$3.60
        qwen_cost = compute_cost(1_000, 500, 0.60, 3.60)

        log_request(_make_record("sonnet", cost=sonnet_cost,
                                 input_tokens=1_000, output_tokens=500), log_file=log_file)
        log_request(_make_record("qwen", cost=qwen_cost,
                                 input_tokens=1_000, output_tokens=500), log_file=log_file)

        summary = get_cost_summary(log_file=log_file)
        assert summary.request_count == 2
        assert abs(summary.total_cost - (sonnet_cost + qwen_cost)) < 1e-9
        assert "sonnet" in summary.cost_by_model
        assert "qwen" in summary.cost_by_model

    def test_local_model_contributes_zero_cost(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        log_request(_make_record("ollama-qwen35", cost=0.0,
                                 input_tokens=5_000, output_tokens=2_000), log_file=log_file)
        log_request(_make_record("sonnet", cost=0.01,
                                 input_tokens=1_000, output_tokens=500), log_file=log_file)

        summary = get_cost_summary(log_file=log_file)
        assert summary.cost_by_model.get("ollama-qwen35", 0.0) == 0.0
        assert summary.cost_by_model["sonnet"] > 0.0

    def test_baseline_comparison_math(self, tmp_path: Path):
        """Baseline = all requests at Sonnet pricing; savings = delta %."""
        log_file = tmp_path / "requests.jsonl"
        # Route to Qwen instead of Sonnet — should show savings
        qwen_cost = compute_cost(1_000_000, 1_000_000, 0.60, 3.60)
        log_request(_make_record("qwen", cost=qwen_cost,
                                 input_tokens=1_000_000, output_tokens=1_000_000), log_file=log_file)

        summary = get_cost_summary(
            log_file=log_file,
            baseline_model_input_price=3.0,
            baseline_model_output_price=15.0,
        )
        # Baseline: $3.0 + $15.0 = $18.0; actual: $0.60 + $3.60 = $4.20
        assert abs(summary.baseline_cost - 18.0) < 0.01
        assert abs(summary.total_cost - 4.20) < 0.01
        expected_savings = round((18.0 - 4.20) / 18.0 * 100, 2)
        assert abs(summary.savings_percentage - expected_savings) < 0.01

    def test_savings_zero_when_only_baseline_model(self, tmp_path: Path):
        """Routing only to Sonnet → 0% savings."""
        log_file = tmp_path / "requests.jsonl"
        cost = compute_cost(1_000_000, 1_000_000, 3.0, 15.0)
        log_request(_make_record("sonnet", cost=cost,
                                 input_tokens=1_000_000, output_tokens=1_000_000), log_file=log_file)

        summary = get_cost_summary(
            log_file=log_file,
            baseline_model_input_price=3.0,
            baseline_model_output_price=15.0,
        )
        assert abs(summary.savings_percentage) < 0.01

    def test_cost_by_task_type_aggregation(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        log_request(_make_record(task_type=TaskType.reasoning, cost=0.05,
                                 input_tokens=1_000, output_tokens=500), log_file=log_file)
        log_request(_make_record(task_type=TaskType.reasoning, cost=0.03,
                                 input_tokens=1_000, output_tokens=500), log_file=log_file)
        log_request(_make_record(task_type=TaskType.extraction, cost=0.001,
                                 input_tokens=1_000, output_tokens=500), log_file=log_file)

        summary = get_cost_summary(log_file=log_file)
        assert abs(summary.cost_by_task_type["reasoning"] - 0.08) < 1e-9
        assert abs(summary.cost_by_task_type["extraction"] - 0.001) < 1e-9

    def test_time_filter_since(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        new_ts = datetime(2026, 2, 20, tzinfo=timezone.utc)

        log_request(_make_record(model="sonnet", cost=0.10,
                                 input_tokens=1_000, output_tokens=500, ts=old_ts), log_file=log_file)
        log_request(_make_record(model="qwen", cost=0.02,
                                 input_tokens=1_000, output_tokens=500, ts=new_ts), log_file=log_file)

        summary = get_cost_summary(
            since=datetime(2026, 2, 1, tzinfo=timezone.utc),
            log_file=log_file,
        )
        assert summary.request_count == 1
        assert "qwen" in summary.cost_by_model
        assert "sonnet" not in summary.cost_by_model

    def test_time_filter_until(self, tmp_path: Path):
        log_file = tmp_path / "requests.jsonl"
        old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        new_ts = datetime(2026, 3, 1, tzinfo=timezone.utc)

        log_request(_make_record(model="sonnet", cost=0.10,
                                 input_tokens=1_000, output_tokens=500, ts=old_ts), log_file=log_file)
        log_request(_make_record(model="qwen", cost=0.02,
                                 input_tokens=1_000, output_tokens=500, ts=new_ts), log_file=log_file)

        summary = get_cost_summary(
            until=datetime(2026, 2, 1, tzinfo=timezone.utc),
            log_file=log_file,
        )
        assert summary.request_count == 1
        assert "sonnet" in summary.cost_by_model

    def test_request_timeline_filters_and_pagination(self, tmp_path: Path):
        from router.cost import get_request_timeline

        log_file = tmp_path / "requests.jsonl"
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        t3 = datetime(2026, 1, 3, tzinfo=timezone.utc)

        log_request(
            _make_record(
                model="sonnet",
                task_type=TaskType.reasoning,
                cost=0.1,
                cache_hit=False,
                fallback_triggered=False,
                ts=t1,
            ),
            log_file=log_file,
        )
        log_request(
            _make_record(
                model="qwen",
                task_type=TaskType.code,
                cost=0.02,
                cache_hit=True,
                fallback_triggered=False,
                ts=t2,
            ),
            log_file=log_file,
        )
        log_request(
            _make_record(
                model="sonnet",
                task_type=TaskType.code,
                cost=0.03,
                cache_hit=False,
                fallback_triggered=True,
                ts=t3,
            ),
            log_file=log_file,
        )

        filtered = get_request_timeline(
            model="sonnet",
            task_type="code",
            fallback_triggered=True,
            log_file=log_file,
            limit=10,
            offset=0,
        )
        assert filtered["total"] == 1
        assert filtered["items"][0]["model_used"] == "sonnet"
        assert filtered["items"][0]["task_type"] == "code"
        assert filtered["items"][0]["fallback_triggered"] is True

        paged = get_request_timeline(log_file=log_file, limit=1, offset=0)
        assert paged["total"] == 3
        # Sorted newest-first, so t3 entry is first
        assert paged["items"][0]["timestamp"] == t3.isoformat()

        page2 = get_request_timeline(log_file=log_file, limit=1, offset=1)
        assert page2["total"] == 3
        assert page2["items"][0]["timestamp"] == t2.isoformat()


# ---------------------------------------------------------------------------
# T038c: 46% cost reduction scenario from the article
# ---------------------------------------------------------------------------

class TestCostReductionScenario:
    """Reproduce the article's 10M token/day savings calculation."""

    def test_46_percent_savings_scenario(self, tmp_path: Path):
        """
        Article: 10M output tokens/day. Route 60% to Qwen → 46% cost reduction.
        All-Sonnet baseline: $15/M output × 10M = $150/day
        After routing: 40% Sonnet ($60) + 60% Qwen ($3.60×6M = $21.60) = $81.60
        Savings: ($150 - $81.60) / $150 = 45.6% ≈ 46%
        """
        log_file = tmp_path / "requests.jsonl"

        # 4M tokens → Sonnet
        sonnet_cost = compute_cost(0, 4_000_000, 3.0, 15.0)
        log_request(_make_record("sonnet", cost=sonnet_cost,
                                 input_tokens=0, output_tokens=4_000_000), log_file=log_file)

        # 6M tokens → Qwen
        qwen_cost = compute_cost(0, 6_000_000, 0.60, 3.60)
        log_request(_make_record("qwen", cost=qwen_cost,
                                 input_tokens=0, output_tokens=6_000_000), log_file=log_file)

        summary = get_cost_summary(
            log_file=log_file,
            baseline_model_input_price=3.0,
            baseline_model_output_price=15.0,
        )

        # Baseline = 10M output × $15/M = $150
        assert abs(summary.baseline_cost - 150.0) < 0.01
        # Actual ≈ $81.60
        assert abs(summary.total_cost - 81.60) < 0.10
        # Savings ≈ 45.6%
        assert summary.savings_percentage > 44.0
        assert summary.savings_percentage < 47.0
