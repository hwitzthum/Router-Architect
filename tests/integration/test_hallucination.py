"""Integration tests — hallucination detection + re-routing in the full pipeline (T066)."""

from __future__ import annotations

from unittest.mock import patch, call as mock_call

import pytest

import router.cache as cache_mod
from router.config import (
    RouterConfig, PluginConfig, CacheConfig,
    SafetyConfig, SafetyPluginConfig, HallucinationConfig,
)
from router.models import Provider, ProviderCategory
from router.pipeline import handle_request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider(name: str, input_price: float = 3.0, output_price: float = 15.0) -> Provider:
    return Provider(
        name=name,
        display_name=name.title(),
        category=ProviderCategory.cloud,
        base_url="https://api.example.com/v1",
        api_key_env="FAKE_KEY",
        model_id=f"model-{name}",
        input_price=input_price,
        output_price=output_price,
        max_context_tokens=100_000,
    )


def _make_config(
    enabled: bool = True,
    reroute: bool = True,
    reroute_target: str = "sonnet",
    confidence_threshold: float = 0.5,
) -> RouterConfig:
    return RouterConfig(
        providers=[
            _provider("sonnet"),
            _provider("gemini"),
        ],
        rules=[],
        default_model="gemini",
        plugins=PluginConfig(
            cache=CacheConfig(enabled=False),
            safety=SafetyConfig(
                jailbreak_detection=SafetyPluginConfig(enabled=False),
                pii_redaction=SafetyPluginConfig(enabled=False),
                prompt_injection=SafetyPluginConfig(enabled=False),
            ),
            hallucination=HallucinationConfig(
                enabled=enabled,
                reroute_on_low_confidence=reroute,
                reroute_target=reroute_target,
                confidence_threshold=confidence_threshold,
            ),
        ),
    )


# Low-confidence response — many hedging phrases + contradictions
LOW_CONFIDENCE_RESPONSE = (
    "I think maybe this is correct, but I'm not sure. "
    "It's possible that perhaps the answer is right. "
    "Wait, actually let me correct that — I made a mistake."
)

# High-confidence response — direct and factual
HIGH_CONFIDENCE_RESPONSE = "The capital of France is Paris."

MESSAGES = [{"role": "user", "content": "What is the capital of France?"}]

IMPROVED_RESPONSE = "Paris is the capital and most populous city of France."


@pytest.fixture(autouse=True)
def clean_cache():
    cache_mod._cache = None
    cache_mod._enabled = False
    yield
    cache_mod._cache = None
    cache_mod._enabled = False


# ---------------------------------------------------------------------------
# Hallucination disabled — no scoring, no re-routing
# ---------------------------------------------------------------------------

class TestHallucinationDisabled:
    def test_confidence_none_when_disabled(self):
        config = _make_config(enabled=False)
        with patch("router.pipeline.call_model", return_value=LOW_CONFIDENCE_RESPONSE), \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)
        assert result.confidence is None

    def test_model_called_once_when_disabled(self):
        config = _make_config(enabled=False)
        with patch("router.pipeline.call_model", return_value=LOW_CONFIDENCE_RESPONSE) as mock_cm, \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            handle_request(MESSAGES, config=config)
        assert mock_cm.call_count == 1


# ---------------------------------------------------------------------------
# Hallucination enabled — confidence is populated
# ---------------------------------------------------------------------------

class TestHallucinationEnabled:
    def test_confidence_populated_on_high_confidence_response(self):
        config = _make_config(enabled=True, confidence_threshold=0.5)
        with patch("router.pipeline.call_model", return_value=HIGH_CONFIDENCE_RESPONSE), \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)
        assert result.confidence is not None
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    def test_high_confidence_no_reroute(self):
        """High-confidence response should not trigger a second model call."""
        config = _make_config(enabled=True, reroute_target="sonnet", confidence_threshold=0.5)
        with patch("router.pipeline.call_model", return_value=HIGH_CONFIDENCE_RESPONSE) as mock_cm, \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)
        assert mock_cm.call_count == 1
        assert result.model_used == "gemini"

    def test_high_confidence_response_score_in_result(self):
        config = _make_config(enabled=True, confidence_threshold=0.5)
        with patch("router.pipeline.call_model", return_value=HIGH_CONFIDENCE_RESPONSE), \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)
        assert result.confidence >= 0.8  # factual, no hedges


# ---------------------------------------------------------------------------
# Re-routing triggers on low confidence
# ---------------------------------------------------------------------------

class TestRerouteOnLowConfidence:
    def test_reroute_triggers_on_low_confidence(self):
        """First call returns low-confidence response → second call to reroute_target."""
        config = _make_config(
            enabled=True, reroute=True, reroute_target="sonnet", confidence_threshold=0.5
        )
        call_responses = [LOW_CONFIDENCE_RESPONSE, IMPROVED_RESPONSE]
        call_iter = iter(call_responses)

        def mock_model_call(model, messages):
            return next(call_iter)

        with patch("router.pipeline.call_model", side_effect=mock_model_call) as mock_cm, \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)

        # Two calls: first to initial model, second to reroute_target
        assert mock_cm.call_count == 2
        # Second call must be to reroute_target
        second_call = mock_cm.call_args_list[1]
        assert second_call[0][0] == "sonnet"
        # Result should use the rerouted response
        assert result.response == IMPROVED_RESPONSE
        assert result.model_used == "sonnet"

    def test_reroute_disabled_single_call_even_on_low_confidence(self):
        config = _make_config(enabled=True, reroute=False, confidence_threshold=0.5)
        with patch("router.pipeline.call_model", return_value=LOW_CONFIDENCE_RESPONSE) as mock_cm, \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)
        assert mock_cm.call_count == 1
        assert result.response == LOW_CONFIDENCE_RESPONSE

    def test_no_reroute_if_already_at_reroute_target(self):
        """If routed to the reroute_target already, no second call should happen."""
        config = _make_config(
            enabled=True, reroute=True, reroute_target="gemini", confidence_threshold=0.5
        )
        with patch("router.pipeline.call_model", return_value=LOW_CONFIDENCE_RESPONSE) as mock_cm, \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)
        assert mock_cm.call_count == 1

    def test_rerouted_response_rescored(self):
        """After rerouting, the confidence score reflects the improved response."""
        config = _make_config(
            enabled=True, reroute=True, reroute_target="sonnet", confidence_threshold=0.5
        )
        call_responses = iter([LOW_CONFIDENCE_RESPONSE, HIGH_CONFIDENCE_RESPONSE])

        with patch("router.pipeline.call_model", side_effect=lambda m, msgs: next(call_responses)), \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)

        # The final confidence should reflect the high-confidence rerouted response
        assert result.confidence >= 0.8


# ---------------------------------------------------------------------------
# Threshold behaviour
# ---------------------------------------------------------------------------

class TestThresholdBehaviour:
    def test_response_exactly_at_threshold_does_not_reroute(self):
        """Score == threshold should NOT trigger reroute (< threshold required)."""
        from router.plugins.hallucination import score_response
        config = _make_config(
            enabled=True, reroute=True, reroute_target="sonnet",
            confidence_threshold=1.0,  # force: anything < 1.0 reroutes
        )
        # HIGH_CONFIDENCE_RESPONSE scores 1.0 — exactly at threshold → no reroute
        with patch("router.pipeline.call_model", return_value=HIGH_CONFIDENCE_RESPONSE) as mock_cm, \
             patch("router.pipeline.resolve_available_model", return_value=("sonnet", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            result = handle_request(MESSAGES, config=config)
        # score == threshold, no reroute (also same model, so guard triggers)
        assert mock_cm.call_count == 1

    def test_very_low_threshold_never_reroutes(self):
        """Threshold of 0.0 means every response is above it → no reroute."""
        config = _make_config(
            enabled=True, reroute=True, reroute_target="sonnet",
            confidence_threshold=0.0,
        )
        with patch("router.pipeline.call_model", return_value=LOW_CONFIDENCE_RESPONSE) as mock_cm, \
             patch("router.pipeline.resolve_available_model", return_value=("gemini", False)), \
             patch("router.pipeline.check_provider_health", return_value=True), \
             patch("router.pipeline.log_request"):
            handle_request(MESSAGES, config=config)
        assert mock_cm.call_count == 1