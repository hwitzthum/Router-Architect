"""Full routing pipeline: classify → route → call → track cost → return."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from router.classifier import classify_request
from router.config import RouterConfig, load_config
from router.cost import compute_cost, log_request
from router.engine import route_request, resolve_available_model
from router.models import (
    ClassificationResult,
    RequestRecord,
    RequestResult,
    RoutingDecision,
    TaskType,
    estimate_tokens,
)
from router.providers import (
    check_provider_health,
    call_model,
    load_providers_from_config,
    start_health_monitor,
    ProviderUnavailableError,
    ModelCallError,
    UnknownProviderError,
)
from router.plugins import build_plugin_chain, run_plugin_chain, PluginOutcome
from router.plugins.hallucination import score_response
import router.cache as _cache_mod


class RequestBlockedError(Exception):
    """Raised when a safety plugin blocks a request."""

# Module-level config (loaded once, can be reloaded)
_config: Optional[RouterConfig] = None
_config_lock = threading.Lock()


def _maybe_initialize_embedding_corpus(config: RouterConfig) -> None:
    """Pre-compute embedding corpus at startup if embedding plugin is enabled."""
    if not config.plugins.embedding.enabled:
        return
    try:
        from router.calibration import load_calibration_prompts
        from router.embeddings import EmbeddingClient, initialize_corpus
        prompts = load_calibration_prompts()
        client = EmbeddingClient(
            base_url=config.plugins.embedding.base_url,
            model=config.plugins.embedding.model,
        )
        initialize_corpus(prompts, client)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Embedding corpus init failed (falling back to keyword-only): %s", exc
        )


def get_config() -> RouterConfig:
    global _config
    if _config is None:
        with _config_lock:
            if _config is None:  # double-checked locking
                from dotenv import load_dotenv
                load_dotenv()
                _config = load_config()
                load_providers_from_config(_config.providers)
                start_health_monitor(_config.providers)
                _cache_mod.configure(
                    enabled=_config.plugins.cache.enabled,
                    max_entries=_config.plugins.cache.max_entries,
                )
                _maybe_initialize_embedding_corpus(_config)
    return _config


def reload_config(config_dir: Optional[Path] = None) -> RouterConfig:
    """Force a config reload (useful for testing and runtime config changes)."""
    global _config
    with _config_lock:
        _config = load_config(config_dir)
        load_providers_from_config(_config.providers)
        start_health_monitor(_config.providers)
        _cache_mod.configure(
            enabled=_config.plugins.cache.enabled,
            max_entries=_config.plugins.cache.max_entries,
        )
        _maybe_initialize_embedding_corpus(_config)
    return _config


class AllModelsFailedError(Exception):
    """Raised when every model in the primary + fallback chain errors out."""


def _call_with_fallback(
    model_used: str,
    fallback_chain: list[str],
    messages: list[dict],
) -> tuple[str, str, bool]:
    """
    Try calling `model_used`, with one retry on transient connection errors,
    then walk through `fallback_chain` on persistent failure.

    Returns (response_text, final_model_used, fallback_triggered).
    Raises AllModelsFailedError if every option fails.
    """
    # De-duplicate while preserving order so we don't retry the same model
    # multiple times when health resolution already picked a fallback model.
    candidates: list[str] = []
    seen: set[str] = set()
    for candidate in [model_used] + list(fallback_chain):
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    fallback_triggered = False

    for i, candidate in enumerate(candidates):
        try:
            text = call_model(candidate, messages)
            # Treat empty response as a soft error — retry next in chain
            if not text.strip() and i < len(candidates) - 1:
                fallback_triggered = True
                continue
            if i > 0:
                fallback_triggered = True
            return text or "", candidate, fallback_triggered
        except ProviderUnavailableError:
            # Retry same candidate once before moving on
            if i == 0:
                try:
                    text = call_model(candidate, messages)
                    if text.strip():
                        return text, candidate, fallback_triggered
                except (ProviderUnavailableError, ModelCallError):
                    pass
            fallback_triggered = True
            continue
        except ModelCallError:
            fallback_triggered = True
            continue

    raise AllModelsFailedError(
        f"All models failed: {candidates}"
    )


def _estimate_output_tokens(text: str) -> int:
    return estimate_tokens(text)


def _compute_cost(
    input_tokens: int,
    output_tokens: int,
    model_name: str,
    config: RouterConfig,
) -> float:
    providers_by_name = {p.name: p for p in config.providers}
    provider = providers_by_name.get(model_name)
    if provider is None:
        return 0.0
    # Provider-side cached token usage is not yet tracked per request, so this
    # defaults to standard input pricing unless cached token counts are added.
    return compute_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_price=provider.input_price,
        output_price=provider.output_price,
        cached_input_price=provider.cached_input_price,
    )


def handle_request(
    messages: list[dict],
    config: Optional[RouterConfig] = None,
) -> RequestResult:
    """
    Full routing pipeline:
      cache? → classify → route → health check / fallback → call model → cost → return.
    """
    if config is None:
        config = get_config()

    router_start = time.monotonic()

    # 0a. Safety plugin chain — run before cache and classification
    plugin_chain = build_plugin_chain(config.plugins.safety)
    if plugin_chain:
        plugin_result = run_plugin_chain(plugin_chain, messages)
        if plugin_result.outcome == PluginOutcome.BLOCK:
            raise RequestBlockedError(plugin_result.reason)
        # SANITIZE: continue with the cleaned messages
        messages = plugin_result.messages

    # 0b. Cache lookup — return immediately on hit (skip classification)
    cached_response = _cache_mod.lookup(messages)
    if cached_response is not None:
        router_overhead_ms = int((time.monotonic() - router_start) * 1000)
        try:
            log_request(RequestRecord(
                messages=messages,
                classification=ClassificationResult(
                    task_type=TaskType.general,
                    complexity=0.0,
                    token_estimate=0,
                ),
                routing=RoutingDecision(
                    selected_model="cache",
                    fallback_chain=[],
                    reason="cache hit",
                ),
                model_used="cache",
                response=cached_response,
                input_tokens=0,
                output_tokens=_estimate_output_tokens(cached_response),
                cost=0.0,
                latency_ms=router_overhead_ms,
                router_overhead_ms=router_overhead_ms,
                cache_hit=True,
                fallback_triggered=False,
                confidence=None,
            ))
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to persist request log entry: %s", exc
            )
        return RequestResult(
            response=cached_response,
            model_used="cache",
            task_type="cached",
            estimated_cost=0.0,
            latency_ms=router_overhead_ms,
            cache_hit=True,
            fallback_triggered=False,
        )

    # 1. Classify
    classification = classify_request(messages, embedding_config=config.plugins.embedding)

    # 2. Route
    decision = route_request(classification, config.rules, config.default_model)

    router_overhead_ms = int((time.monotonic() - router_start) * 1000)

    # 3. Resolve healthy provider (with fallback)
    model_used, fallback_triggered = resolve_available_model(
        decision,
        health_check_fn=check_provider_health,
    )

    # 4. Call model (with retry + fallback on errors / empty response)
    total_start = time.monotonic()
    response_text, model_used, call_fallback = _call_with_fallback(
        model_used, decision.fallback_chain, messages
    )
    latency_ms = int((time.monotonic() - total_start) * 1000)
    fallback_triggered = fallback_triggered or call_fallback

    # 5. Hallucination detection — optionally re-route on low confidence
    hall_cfg = config.plugins.hallucination
    confidence: Optional[float] = None
    if hall_cfg.enabled:
        confidence = score_response(response_text)
        if (
            hall_cfg.reroute_on_low_confidence
            and confidence < hall_cfg.confidence_threshold
            and hall_cfg.reroute_target != model_used
        ):
            reroute_start = time.monotonic()
            try:
                rerouted_text = call_model(hall_cfg.reroute_target, messages)
            except (ProviderUnavailableError, ModelCallError, UnknownProviderError):
                rerouted_text = ""
            latency_ms += int((time.monotonic() - reroute_start) * 1000)
            if rerouted_text.strip():
                response_text = rerouted_text
                model_used = hall_cfg.reroute_target
            # Re-score whichever response we ended up with
            confidence = score_response(response_text)

    # 5b. Cache store — save response for future identical requests
    _cache_mod.store(messages, response_text)

    # 6. Cost tracking
    input_tokens = classification.token_estimate
    output_tokens = _estimate_output_tokens(response_text)
    cost = _compute_cost(input_tokens, output_tokens, model_used, config)

    # 7. Log
    record = RequestRecord(
        messages=messages,
        classification=classification,
        routing=decision,
        model_used=model_used,
        response=response_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        latency_ms=latency_ms,
        router_overhead_ms=router_overhead_ms,
        fallback_triggered=fallback_triggered,
        confidence=confidence,
    )
    try:
        log_request(record)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to persist request log entry: %s", exc
        )

    return RequestResult(
        response=response_text,
        model_used=model_used,
        task_type=classification.task_type.value,
        estimated_cost=round(cost, 6),
        latency_ms=latency_ms,
        fallback_triggered=fallback_triggered,
        confidence=confidence,
    )
