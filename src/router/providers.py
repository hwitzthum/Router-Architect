"""Provider registry, health checks, and unified model calling interface."""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from typing import Optional

from openai import OpenAI, APIConnectionError, APIStatusError

from router.models import Provider, ProviderCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProviderUnavailableError(Exception):
    """Raised when a provider cannot be reached within the timeout."""

class ModelCallError(Exception):
    """Raised when a model API returns an error response."""

class UnknownProviderError(Exception):
    """Raised when a requested provider name is not in the registry."""

class AllProvidersUnavailableError(Exception):
    """Raised when every provider in a fallback chain is unreachable."""

_ANTHROPIC_VERSION = "2023-06-01"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, Provider] = {}
_registry_lock = threading.RLock()
_clients: dict[str, OpenAI] = {}


def register_provider(provider: Provider) -> None:
    """Add or overwrite a provider in the registry."""
    with _registry_lock:
        _registry[provider.name] = provider


def remove_provider(name: str) -> None:
    """Remove a provider from the registry. Silent if not found."""
    with _registry_lock:
        _registry.pop(name, None)
        _clients.pop(name, None)


def get_provider(name: str) -> Provider:
    with _registry_lock:
        if name not in _registry:
            raise UnknownProviderError(f"Provider '{name}' not found in registry")
        return _registry[name]


def list_providers() -> list[Provider]:
    with _registry_lock:
        return list(_registry.values())


def load_providers_from_config(providers: list[Provider]) -> None:
    """Populate the registry from a list of Provider objects (from config)."""
    with _registry_lock:
        _registry.clear()
        _clients.clear()
        for p in providers:
            if p.enabled:
                _registry[p.name] = p


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

_health_cache: dict[str, bool] = {}
_health_cache_lock = threading.Lock()
_health_monitor_running = False


def reset_health_monitor() -> None:
    """Reset health monitor state — used in tests."""
    global _health_monitor_running
    _health_monitor_running = False
    with _health_cache_lock:
        _health_cache.clear()


def start_health_monitor(providers: list[Provider], interval: float = 10.0) -> None:
    """Start a background daemon thread that periodically updates health status."""
    global _health_monitor_running
    if _health_monitor_running:
        return

    enabled = [p for p in providers if p.enabled]
    if not enabled:
        return

    def _monitor() -> None:
        import time
        while True:
            for p in enabled:
                healthy = _check_provider_health_sync(p.name)
                with _health_cache_lock:
                    _health_cache[p.name] = healthy
            time.sleep(interval)

    _health_monitor_running = True
    t = threading.Thread(target=_monitor, daemon=True)
    t.start()
    logger.info("Health monitor started (interval=%.1fs, providers=%d)", interval, len(enabled))


def check_provider_health(name: str, timeout: float = 2.0) -> bool:
    """Return True if the provider is reachable. Uses cached status when monitor is running."""
    if _health_monitor_running:
        with _health_cache_lock:
            if name in _health_cache:
                return _health_cache[name]
    return _check_provider_health_sync(name, timeout)


def _check_provider_health_sync(name: str, timeout: float = 2.0) -> bool:
    """Synchronous health check (used by monitor and as fallback)."""
    try:
        provider = get_provider(name)
    except UnknownProviderError:
        return False

    if _is_anthropic_provider(provider):
        return _ping_anthropic(provider, timeout)

    if provider.category == ProviderCategory.local:
        return check_ollama_health(provider, timeout=timeout)

    try:
        req = urllib.request.Request(provider.base_url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return _ping_openai_compatible(provider, timeout)


def check_ollama_health(provider: Provider, model: Optional[str] = None, timeout: float = 2.0) -> bool:
    """
    Ollama-specific health check:
    1. Confirm the Ollama HTTP server is running at base_url.
    2. Confirm the target model is loaded (in the /api/tags model list).
    """
    target_model = model or provider.model_id

    # Step 1: check server is up via /api/tags (Ollama native endpoint)
    try:
        tags_url = provider.base_url.rstrip("/").replace("/v1", "") + "/api/tags"
        with urllib.request.urlopen(tags_url, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return False

    # Step 2: confirm the target model is in the list
    models = data.get("models", [])
    loaded_names = {m.get("name", "").split(":")[0] for m in models}
    return target_model.split(":")[0] in loaded_names


def _ping_openai_compatible(provider: Provider, timeout: float) -> bool:
    """Try listing models via the OpenAI-compatible endpoint as a health check."""
    try:
        client = _make_client(provider, timeout=timeout)
        # models.list() is lightweight and works on all OpenAI-compatible servers
        client.models.list(timeout=timeout)
        return True
    except Exception:
        return False


def _ping_anthropic(provider: Provider, timeout: float) -> bool:
    """Health check for Anthropic's native API."""
    try:
        api_key = _resolve_api_key(provider)
        models_url = provider.base_url.rstrip("/") + "/models"
        req = urllib.request.Request(
            models_url,
            method="GET",
            headers={
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Unified model calling
# ---------------------------------------------------------------------------

def _is_anthropic_provider(provider: Provider) -> bool:
    return "api.anthropic.com" in provider.base_url.lower()


def _resolve_api_key(provider: Provider) -> str:
    api_key = "local"
    if provider.api_key_env:
        api_key = os.environ.get(provider.api_key_env, "")
        if not api_key:
            raise ProviderUnavailableError(
                f"API key env var '{provider.api_key_env}' is not set for provider '{provider.name}'"
            )
    return api_key


def _make_client(provider: Provider, timeout: Optional[float] = None) -> OpenAI:
    api_key = _resolve_api_key(provider)
    if timeout is None:
        return OpenAI(base_url=provider.base_url, api_key=api_key)
    return OpenAI(base_url=provider.base_url, api_key=api_key, timeout=timeout)


def _get_client(provider: Provider) -> OpenAI:
    """Return a cached OpenAI client for the provider, creating one if needed."""
    if provider.name not in _clients:
        _clients[provider.name] = _make_client(provider)
    return _clients[provider.name]


def call_model(model_name: str, messages: list[dict]) -> str:
    """
    Call a model through the unified OpenAI-compatible interface.

    Raises ProviderUnavailableError on connection failure.
    Raises ModelCallError on API-level errors.
    """
    provider = get_provider(model_name)
    if _is_anthropic_provider(provider):
        return _call_anthropic_model(model_name, provider, messages)

    client = _get_client(provider)

    try:
        response = client.chat.completions.create(
            model=provider.model_id,
            messages=messages,
            max_tokens=provider.max_output_tokens,
        )
        return response.choices[0].message.content or ""
    except APIConnectionError as e:
        raise ProviderUnavailableError(
            f"Cannot connect to provider '{model_name}' at {provider.base_url}: {e}"
        ) from e
    except APIStatusError as e:
        raise ModelCallError(
            f"Provider '{model_name}' returned error {e.status_code}: {e.message}"
        ) from e


def _call_anthropic_model(model_name: str, provider: Provider, messages: list[dict]) -> str:
    """Call Anthropic's native messages API using required auth headers."""
    api_key = _resolve_api_key(provider)
    endpoint = provider.base_url.rstrip("/") + "/messages"

    system_parts: list[str] = []
    anthropic_messages: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        anthropic_messages.append({"role": role, "content": content})

    if not anthropic_messages:
        anthropic_messages.append({"role": "user", "content": ""})

    payload: dict[str, object] = {
        "model": provider.model_id,
        "max_tokens": provider.max_output_tokens,
        "messages": anthropic_messages,
    }
    if system_parts:
        payload["system"] = "\n".join(system_parts)

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read(300).decode("utf-8", errors="replace")
        raise ModelCallError(
            f"Provider '{model_name}' returned error {e.code}: {error_body}"
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderUnavailableError(
            f"Cannot connect to provider '{model_name}' at {provider.base_url}: {e}"
        ) from e

    parts = data.get("content", [])
    text_chunks = [
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    return "".join(text_chunks)
