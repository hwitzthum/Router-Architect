"""Integration tests for provider management (Phase 4 / US2)."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from router.models import Provider, ProviderCategory
from router import providers as registry_mod
from router.providers import (
    register_provider,
    remove_provider,
    get_provider,
    list_providers,
    load_providers_from_config,
    check_provider_health,
    check_ollama_health,
    call_model,
    UnknownProviderError,
    ModelCallError,
    ProviderUnavailableError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_registry():
    """Reset the provider registry and health monitor before and after each test."""
    registry_mod._registry.clear()
    registry_mod._clients.clear()
    registry_mod.reset_health_monitor()
    yield
    registry_mod._registry.clear()
    registry_mod._clients.clear()
    registry_mod.reset_health_monitor()


def _make_cloud(name: str = "sonnet") -> Provider:
    return Provider(
        name=name,
        display_name="Claude Sonnet 4.6",
        category=ProviderCategory.cloud,
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        model_id="claude-sonnet-4-6",
        input_price=3.0,
        output_price=15.0,
        max_context_tokens=200_000,
    )


def _make_local(name: str = "ollama-qwen35") -> Provider:
    return Provider(
        name=name,
        display_name="Llama 3.1 (Ollama)",
        category=ProviderCategory.local,
        base_url="http://localhost:11434/v1",
        api_key_env=None,
        model_id="llama3.1",
        input_price=0.0,
        output_price=0.0,
        max_context_tokens=128_000,
    )


def _make_self_hosted(name: str = "qwen") -> Provider:
    return Provider(
        name=name,
        display_name="Qwen 3.5 (vLLM)",
        category=ProviderCategory.self_hosted,
        base_url="http://localhost:8000/v1",
        api_key_env=None,
        model_id="qwen3.5",
        input_price=0.0,
        output_price=0.0,
        max_context_tokens=32_000,
    )


# ---------------------------------------------------------------------------
# T027: register_provider / remove_provider at runtime
# ---------------------------------------------------------------------------

class TestRuntimeRegistration:
    def test_register_single_provider(self):
        p = _make_cloud()
        register_provider(p)
        assert get_provider("sonnet") is p

    def test_register_overwrites_existing(self):
        p1 = _make_cloud()
        register_provider(p1)
        p2 = _make_cloud()
        p2 = p2.model_copy(update={"display_name": "Updated"})
        register_provider(p2)
        assert get_provider("sonnet").display_name == "Updated"

    def test_remove_provider(self):
        register_provider(_make_cloud())
        remove_provider("sonnet")
        with pytest.raises(UnknownProviderError):
            get_provider("sonnet")

    def test_remove_nonexistent_is_silent(self):
        remove_provider("does-not-exist")  # should not raise

    def test_list_providers_reflects_runtime_changes(self):
        assert list_providers() == []
        register_provider(_make_cloud())
        register_provider(_make_local())
        names = {p.name for p in list_providers()}
        assert names == {"sonnet", "ollama-qwen35"}
        remove_provider("sonnet")
        assert len(list_providers()) == 1

    def test_load_from_config_replaces_registry(self):
        register_provider(_make_cloud())
        load_providers_from_config([_make_local(), _make_self_hosted()])
        names = {p.name for p in list_providers()}
        assert names == {"ollama-qwen35", "qwen"}
        with pytest.raises(UnknownProviderError):
            get_provider("sonnet")

    def test_load_from_config_skips_disabled(self):
        p = _make_cloud()
        p = p.model_copy(update={"enabled": False})
        load_providers_from_config([p, _make_local()])
        assert len(list_providers()) == 1
        assert get_provider("ollama-qwen35").name == "ollama-qwen35"

    def test_fourth_provider_added_via_config(self):
        """Simulate adding a new provider via config without code changes."""
        initial = [_make_cloud(), _make_local()]
        load_providers_from_config(initial)
        assert len(list_providers()) == 2

        # Add a 4th provider via config-only (append to list, reload)
        extra = _make_self_hosted("gemini")
        extra = extra.model_copy(update={
            "display_name": "Gemini 3.1 Pro",
            "model_id": "gemini-3.1-pro",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "category": ProviderCategory.cloud,
            "input_price": 2.0,
            "output_price": 12.0,
        })
        load_providers_from_config(initial + [extra])
        assert len(list_providers()) == 3
        assert get_provider("gemini").model_id == "gemini-3.1-pro"


# ---------------------------------------------------------------------------
# T028: Ollama-specific availability detection
# ---------------------------------------------------------------------------

class TestOllamaHealth:
    def test_ollama_healthy_when_model_listed(self):
        provider = _make_local()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "llama3.1:latest"}]}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert check_ollama_health(provider) is True

    def test_ollama_unhealthy_when_model_not_listed(self):
        provider = _make_local()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "mistral:latest"}]}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert check_ollama_health(provider) is False

    def test_ollama_unhealthy_when_server_down(self):
        provider = _make_local()
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            assert check_ollama_health(provider) is False

    def test_check_provider_health_delegates_to_ollama(self):
        provider = _make_local()
        register_provider(provider)

        with patch("router.providers.check_ollama_health", return_value=True) as mock_check:
            result = check_provider_health("ollama-qwen35")
            mock_check.assert_called_once_with(provider, timeout=2.0)
            assert result is True

    def test_check_provider_health_ollama_unavailable_fallback(self):
        """When Ollama is unavailable, provider should report unhealthy."""
        provider = _make_local()
        register_provider(provider)

        with patch("router.providers.check_ollama_health", return_value=False):
            result = check_provider_health("ollama-qwen35")
            assert result is False

    def test_ollama_model_name_without_tag_matches(self):
        """Model name comparison should strip :tag suffix."""
        provider = _make_local()
        mock_response = MagicMock()
        # API returns name with tag, provider.model_id has no tag — should still match
        mock_response.read.return_value = b'{"models": [{"name": "llama3.1:8b"}]}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert check_ollama_health(provider) is True


class TestOpenAICompatibleHealth:
    def test_ping_openai_compatible_passes_timeout_through(self):
        provider = _make_cloud()
        mock_client = MagicMock()

        with patch("router.providers._make_client", return_value=mock_client) as mock_make_client:
            healthy = registry_mod._ping_openai_compatible(provider, timeout=1.5)

        assert healthy is True
        mock_make_client.assert_called_once_with(provider, timeout=1.5)
        mock_client.models.list.assert_called_once_with(timeout=1.5)

    def test_check_provider_health_passes_timeout_to_openai_ping(self):
        provider = _make_self_hosted()
        register_provider(provider)

        with patch("urllib.request.urlopen", side_effect=OSError("down")), \
             patch("router.providers._ping_openai_compatible", return_value=True) as mock_ping:
            healthy = check_provider_health("qwen", timeout=1.7)

        assert healthy is True
        mock_ping.assert_called_once_with(provider, 1.7)


class TestAnthropicProvider:
    def test_check_provider_health_uses_anthropic_ping(self):
        provider = _make_cloud()
        register_provider(provider)

        with patch("router.providers._ping_anthropic", return_value=True) as mock_ping, \
             patch("router.providers._ping_openai_compatible") as mock_openai_ping:
            healthy = check_provider_health("sonnet", timeout=1.2)

        assert healthy is True
        mock_ping.assert_called_once_with(provider, 1.2)
        mock_openai_ping.assert_not_called()

    def test_call_model_anthropic_parses_text_blocks(self):
        provider = _make_cloud()
        register_provider(provider)

        payload = (
            b'{"content":[{"type":"text","text":"Hello "},'
            b'{"type":"text","text":"world"}]}'
        )
        mock_response = MagicMock()
        mock_response.read.return_value = payload
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret"}), \
             patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            text = call_model("sonnet", [{"role": "user", "content": "Say hi"}])

        assert text == "Hello world"
        request = mock_urlopen.call_args[0][0]
        assert request.full_url.endswith("/messages")
        assert request.headers["X-api-key"] == "secret"
        assert request.headers["Anthropic-version"] == "2023-06-01"

    def test_call_model_anthropic_http_error_raises_model_call_error(self):
        provider = _make_cloud()
        register_provider(provider)

        error = urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=MagicMock(read=MagicMock(return_value=b'{"error":"bad key"}')),
        )
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret"}), \
             patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(ModelCallError) as exc:
                call_model("sonnet", [{"role": "user", "content": "test"}])

        assert "returned error 401" in str(exc.value)

    def test_call_model_anthropic_network_error_raises_unavailable(self):
        provider = _make_cloud()
        register_provider(provider)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret"}), \
             patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with pytest.raises(ProviderUnavailableError):
                call_model("sonnet", [{"role": "user", "content": "test"}])
