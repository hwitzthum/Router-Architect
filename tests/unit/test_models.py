"""Unit tests for data models (T015)."""

import pytest
from pydantic import ValidationError

from router.models import (
    Provider,
    ProviderCategory,
    RoutingRule,
    TaskType,
    ClassificationResult,
    RoutingDecision,
    RequestRecord,
    RequestResult,
    CostSummary,
)


class TestProvider:
    def test_valid_cloud_provider(self):
        p = Provider(
            name="sonnet",
            display_name="Claude Sonnet 4.6",
            category=ProviderCategory.cloud,
            base_url="https://api.anthropic.com/v1",
            api_key_env="ANTHROPIC_API_KEY",
            model_id="claude-sonnet-4-6",
            input_price=3.0,
            output_price=15.0,
            cached_input_price=0.3,
            max_context_tokens=200_000,
            enabled=True,
        )
        assert p.name == "sonnet"
        assert p.category == ProviderCategory.cloud
        assert p.cached_input_price == 0.3

    def test_valid_local_provider(self):
        p = Provider(
            name="ollama-qwen35",
            display_name="Llama 3",
            category=ProviderCategory.local,
            base_url="http://localhost:11434/v1",
            api_key_env=None,
            model_id="qwen3.5:cloud",
            input_price=0.0,
            output_price=0.0,
            cached_input_price=0.0,
            max_context_tokens=8192,
            enabled=True,
        )
        assert p.input_price == 0.0
        assert p.api_key_env is None

    def test_local_provider_allows_nonzero_price(self):
        p = Provider(
            name="paid-local",
            display_name="Paid Local",
            category=ProviderCategory.local,
            base_url="http://localhost:11434/v1",
            api_key_env=None,
            model_id="qwen3.5:cloud",
            input_price=0.55,
            output_price=3.5,
            cached_input_price=0.55,
            max_context_tokens=8192,
            enabled=True,
        )
        assert p.input_price == 0.55
        assert p.output_price == 3.5
        assert p.cached_input_price == 0.55

    def test_local_provider_rejects_api_key_env(self):
        with pytest.raises(ValidationError, match="api_key_env"):
            Provider(
                name="bad-local",
                display_name="Bad",
                category=ProviderCategory.local,
                base_url="http://localhost:11434/v1",
                api_key_env="SOME_KEY",
                model_id="qwen3.5:cloud",
                input_price=0.0,
                output_price=0.0,
                cached_input_price=0.0,
                max_context_tokens=8192,
                enabled=True,
            )

    def test_negative_price_rejected(self):
        with pytest.raises(ValidationError, match="prices must be"):
            Provider(
                name="bad",
                display_name="Bad",
                category=ProviderCategory.cloud,
                base_url="https://example.com",
                api_key_env="KEY",
                model_id="model",
                input_price=-1.0,
                output_price=0.0,
                cached_input_price=0.0,
                max_context_tokens=1000,
                enabled=True,
            )

    def test_local_provider_allows_nonzero_cached_price(self):
        p = Provider(
            name="cached-local",
            display_name="Cached Local",
            category=ProviderCategory.local,
            base_url="http://localhost:11434/v1",
            api_key_env=None,
            model_id="qwen3.5:cloud",
            input_price=0.0,
            output_price=0.0,
            cached_input_price=0.2,
            max_context_tokens=8192,
            enabled=True,
        )
        assert p.cached_input_price == 0.2


class TestRoutingRule:
    def test_valid_rule(self):
        rule = RoutingRule(
            task_type=TaskType.reasoning,
            complexity_min=0.6,
            complexity_max=1.0,
            target_model="gemini",
            fallback_chain=["sonnet"],
            priority=1,
        )
        assert rule.target_model == "gemini"

    def test_complexity_out_of_range(self):
        with pytest.raises(ValidationError):
            RoutingRule(
                task_type=TaskType.reasoning,
                complexity_min=1.5,
                target_model="gemini",
                priority=1,
            )


class TestClassificationResult:
    def test_construction(self):
        r = ClassificationResult(
            task_type=TaskType.extraction,
            complexity=0.3,
            token_estimate=50,
            requires_tools=False,
            factuality_risk=False,
        )
        assert r.task_type == TaskType.extraction
        assert r.complexity == 0.3


class TestRequestResult:
    def test_construction(self):
        r = RequestResult(
            response="Hello",
            model_used="sonnet",
            task_type="knowledge_work",
            estimated_cost=0.001,
            latency_ms=500,
        )
        assert r.cache_hit is False
        assert r.fallback_triggered is False
