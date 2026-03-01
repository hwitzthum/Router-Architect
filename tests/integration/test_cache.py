"""Integration tests for semantic caching in the full pipeline (T054)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import router.cache as cache_mod
from router.cache import configure, reset
from router.config import RouterConfig, PluginConfig, CacheConfig, SafetyConfig, HallucinationConfig
from router.models import Provider, ProviderCategory, RoutingRule, TaskType
from router.pipeline import handle_request


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cache():
    """Guarantee a clean cache state before and after every test."""
    cache_mod._cache = None
    cache_mod._enabled = False
    yield
    cache_mod._cache = None
    cache_mod._enabled = False


@pytest.fixture()
def config_with_cache_enabled() -> RouterConfig:
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
        )
    ]
    return RouterConfig(
        providers=providers,
        rules=[],
        default_model="sonnet",
        plugins=PluginConfig(
            cache=CacheConfig(enabled=True, max_entries=100),
            safety=SafetyConfig(),
            hallucination=HallucinationConfig(),
        ),
    )


@pytest.fixture()
def config_with_cache_disabled() -> RouterConfig:
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
        )
    ]
    return RouterConfig(
        providers=providers,
        rules=[],
        default_model="sonnet",
        plugins=PluginConfig(
            cache=CacheConfig(enabled=False),
            safety=SafetyConfig(),
            hallucination=HallucinationConfig(),
        ),
    )


MESSAGES = [{"role": "user", "content": "What is the capital of France?"}]
MOCK_RESPONSE = "The capital of France is Paris."


# ---------------------------------------------------------------------------
# Cache hit / miss behaviour in the pipeline
# ---------------------------------------------------------------------------

class TestCachePipelineIntegration:
    def test_first_request_is_cache_miss(self, config_with_cache_enabled):
        configure(enabled=True, max_entries=100)
        with patch("router.pipeline.call_model", return_value=MOCK_RESPONSE), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config_with_cache_enabled)
        assert result.cache_hit is False
        assert result.model_used == "sonnet"

    def test_second_identical_request_is_cache_hit(self, config_with_cache_enabled):
        configure(enabled=True, max_entries=100)
        call_count = {"n": 0}

        def mock_call(model, messages):
            call_count["n"] += 1
            return MOCK_RESPONSE

        with patch("router.pipeline.call_model", side_effect=mock_call), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            r1 = handle_request(MESSAGES, config=config_with_cache_enabled)
            r2 = handle_request(MESSAGES, config=config_with_cache_enabled)

        assert r1.cache_hit is False
        assert r2.cache_hit is True
        # Model was only called once
        assert call_count["n"] == 1

    def test_cache_hit_returns_same_response(self, config_with_cache_enabled):
        configure(enabled=True, max_entries=100)
        with patch("router.pipeline.call_model", return_value=MOCK_RESPONSE), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            r1 = handle_request(MESSAGES, config=config_with_cache_enabled)
            r2 = handle_request(MESSAGES, config=config_with_cache_enabled)

        assert r1.response == r2.response == MOCK_RESPONSE

    def test_cache_hit_has_zero_cost(self, config_with_cache_enabled):
        configure(enabled=True, max_entries=100)
        with patch("router.pipeline.call_model", return_value=MOCK_RESPONSE), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            handle_request(MESSAGES, config=config_with_cache_enabled)
            r2 = handle_request(MESSAGES, config=config_with_cache_enabled)

        assert r2.estimated_cost == 0.0

    def test_cache_hit_is_logged_with_cache_metadata(self, config_with_cache_enabled):
        configure(enabled=True, max_entries=100)
        with patch("router.pipeline.call_model", return_value=MOCK_RESPONSE), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request") as mock_log:
            handle_request(MESSAGES, config=config_with_cache_enabled)
            handle_request(MESSAGES, config=config_with_cache_enabled)

        assert mock_log.call_count == 2
        first_record = mock_log.call_args_list[0].args[0]
        second_record = mock_log.call_args_list[1].args[0]
        assert first_record.cache_hit is False
        assert second_record.cache_hit is True
        assert second_record.model_used == "cache"

    def test_different_messages_are_separate_cache_entries(self, config_with_cache_enabled):
        configure(enabled=True, max_entries=100)
        msgs_a = [{"role": "user", "content": "Question A"}]
        msgs_b = [{"role": "user", "content": "Question B"}]
        call_count = {"n": 0}

        def mock_call(model, messages):
            call_count["n"] += 1
            return f"Answer {call_count['n']}"

        with patch("router.pipeline.call_model", side_effect=mock_call), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            handle_request(msgs_a, config=config_with_cache_enabled)
            r2 = handle_request(msgs_b, config=config_with_cache_enabled)

        assert r2.cache_hit is False
        assert call_count["n"] == 2  # both messages called the model


# ---------------------------------------------------------------------------
# Cache disabled via config
# ---------------------------------------------------------------------------

class TestCacheDisabledViaConfig:
    def test_disabled_cache_never_hits(self, config_with_cache_disabled):
        configure(enabled=False)
        call_count = {"n": 0}

        def mock_call(model, messages):
            call_count["n"] += 1
            return MOCK_RESPONSE

        with patch("router.pipeline.call_model", side_effect=mock_call), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            r1 = handle_request(MESSAGES, config=config_with_cache_disabled)
            r2 = handle_request(MESSAGES, config=config_with_cache_disabled)

        assert r1.cache_hit is False
        assert r2.cache_hit is False
        assert call_count["n"] == 2  # model called both times


# ---------------------------------------------------------------------------
# Cost reduction verification
# ---------------------------------------------------------------------------

class TestCacheCostReduction:
    def test_repeated_requests_reduce_total_cost(self, config_with_cache_enabled, tmp_path):
        """Send 5 identical requests — only 1 should incur cost."""
        from router.cost import get_cost_summary, log_request
        from router.models import RequestRecord, ClassificationResult, RoutingDecision

        configure(enabled=True, max_entries=100)
        log_file = tmp_path / "requests.jsonl"
        call_count = {"n": 0}

        def mock_call(model, messages):
            call_count["n"] += 1
            return MOCK_RESPONSE

        with patch("router.pipeline.call_model", side_effect=mock_call), \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request") as mock_log:
            for _ in range(5):
                handle_request(MESSAGES, config=config_with_cache_enabled)

        # Model called exactly once; cache served the other 4
        assert call_count["n"] == 1
        # All requests are logged (miss + hits) for accurate cache telemetry
        assert mock_log.call_count == 5

    def test_cache_hit_rate_in_cost_summary(self, tmp_path):
        """cache_hit field in logged records drives hit_rate in CostSummary."""
        from datetime import datetime, timezone
        from router.cost import get_cost_summary, log_request
        from router.models import (
            RequestRecord, ClassificationResult, RoutingDecision, TaskType
        )

        log_file = tmp_path / "requests.jsonl"

        def _make_rec(cache_hit: bool):
            return RequestRecord(
                messages=[{"role": "user", "content": "q"}],
                classification=ClassificationResult(
                    task_type=TaskType.general, complexity=0.2, token_estimate=5
                ),
                routing=RoutingDecision(
                    selected_model="sonnet", fallback_chain=[], reason="test"
                ),
                model_used="sonnet",
                response="answer",
                input_tokens=5,
                output_tokens=3,
                cost=0.0 if cache_hit else 0.001,
                latency_ms=10,
                router_overhead_ms=2,
                cache_hit=cache_hit,
                timestamp=datetime.now(timezone.utc),
            )

        # 1 miss + 3 hits
        log_request(_make_rec(cache_hit=False), log_file=log_file)
        log_request(_make_rec(cache_hit=True), log_file=log_file)
        log_request(_make_rec(cache_hit=True), log_file=log_file)
        log_request(_make_rec(cache_hit=True), log_file=log_file)

        summary = get_cost_summary(log_file=log_file)
        assert summary.request_count == 4
        assert abs(summary.cache_hit_rate - 0.75) < 1e-9
