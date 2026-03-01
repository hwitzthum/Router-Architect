"""Integration-style contract tests for the FastAPI router surface."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import router.api as api_mod
from router.models import (
    ClassificationResult,
    CostSummary,
    Provider,
    ProviderCategory,
    RequestResult,
    TaskType,
)
from router.pipeline import AllModelsFailedError, RequestBlockedError


def _provider(name: str = "sonnet", enabled: bool = True) -> Provider:
    return Provider(
        name=name,
        display_name=name.title(),
        category=ProviderCategory.cloud,
        base_url="https://api.example.com/v1",
        api_key_env="FAKE_KEY",
        model_id=f"model-{name}",
        input_price=1.0,
        output_price=2.0,
        cached_input_price=0.1,
        max_context_tokens=100_000,
        enabled=enabled,
    )


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
        default_model="sonnet",
        providers=[_provider("sonnet", enabled=True), _provider("gemini", enabled=False)],
        plugins=SimpleNamespace(embedding=None),
    )


def test_health_endpoint(monkeypatch):
    client = TestClient(api_mod.app)
    monkeypatch.setattr(api_mod, "get_config", lambda: _cfg())

    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["default_model"] == "sonnet"
    assert payload["providers_configured"] == 2


def test_classify_endpoint(monkeypatch):
    client = TestClient(api_mod.app)
    monkeypatch.setattr(api_mod, "get_config", lambda: _cfg())
    monkeypatch.setattr(
        api_mod,
        "classify_request",
        lambda messages, embedding_config: ClassificationResult(
            task_type=TaskType.reasoning,
            complexity=0.77,
            token_estimate=42,
            requires_tools=True,
            factuality_risk=False,
        ),
    )

    response = client.post("/api/classify", json={"prompt": "Prove something."})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_type"] == "reasoning"
    assert payload["complexity"] == 0.77
    assert payload["token_estimate"] == 42
    assert payload["requires_tools"] is True


def test_classify_endpoint_requires_exactly_one_prompt_source():
    client = TestClient(api_mod.app)

    empty = client.post("/api/classify", json={})
    assert empty.status_code == 422

    both = client.post(
        "/api/classify",
        json={
            "prompt": "x",
            "messages": [{"role": "user", "content": "y"}],
        },
    )
    assert both.status_code == 422


def test_route_endpoint_success(monkeypatch):
    client = TestClient(api_mod.app)
    monkeypatch.setattr(
        api_mod,
        "handle_request",
        lambda messages: RequestResult(
            response="ok",
            model_used="sonnet",
            task_type="general",
            estimated_cost=0.001,
            latency_ms=12,
            cache_hit=False,
            fallback_triggered=False,
            confidence=None,
        ),
    )

    response = client.post("/api/route", json={"prompt": "hello"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["model_used"] == "sonnet"
    assert payload["response"] == "ok"


def test_route_endpoint_maps_block_to_403(monkeypatch):
    client = TestClient(api_mod.app)

    def _raise(_messages):
        raise RequestBlockedError("blocked")

    monkeypatch.setattr(api_mod, "handle_request", _raise)
    response = client.post("/api/route", json={"prompt": "hello"})
    assert response.status_code == 403


def test_route_endpoint_maps_unavailable_to_503(monkeypatch):
    client = TestClient(api_mod.app)

    def _raise(_messages):
        raise AllModelsFailedError("down")

    monkeypatch.setattr(api_mod, "handle_request", _raise)
    response = client.post("/api/route", json={"prompt": "hello"})
    assert response.status_code == 503


def test_providers_endpoint(monkeypatch):
    client = TestClient(api_mod.app)
    monkeypatch.setattr(api_mod, "get_config", lambda: _cfg())
    monkeypatch.setattr(api_mod, "check_provider_health", lambda name: name == "sonnet")

    response = client.get("/api/providers")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model"] == "sonnet"
    assert len(payload["providers"]) == 2
    assert payload["providers"][0]["name"] == "sonnet"
    assert payload["providers"][0]["cached_input_price"] == 0.1


def test_cost_endpoint_and_invalid_since(monkeypatch):
    client = TestClient(api_mod.app)
    monkeypatch.setattr(
        api_mod,
        "get_cost_summary",
        lambda since, until: CostSummary(
            total_cost=1.2,
            cost_by_model={"sonnet": 1.2},
            cost_by_task_type={"general": 1.2},
            request_count=4,
            baseline_cost=2.4,
            savings_percentage=50.0,
            cache_hit_rate=0.25,
        ),
    )

    ok = client.get("/api/cost")
    assert ok.status_code == 200
    assert ok.json()["request_count"] == 4

    bad = client.get("/api/cost?since=not-a-date")
    assert bad.status_code == 400


def test_requests_endpoint_forwards_filters(monkeypatch):
    client = TestClient(api_mod.app)
    captured = {}

    def _timeline(**kwargs):
        captured.update(kwargs)
        return {
            "total": 1,
            "items": [
                {
                    "id": "abc",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "model_used": "sonnet",
                    "task_type": "general",
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "cost": 0.0001,
                    "latency_ms": 12,
                    "cache_hit": False,
                    "fallback_triggered": False,
                }
            ],
        }

    monkeypatch.setattr(api_mod, "get_request_timeline", _timeline)
    response = client.get(
        "/api/requests?model=sonnet&task_type=general&cache_hit=false&fallback_triggered=false&limit=20&offset=5"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert captured["model"] == "sonnet"
    assert captured["task_type"] == "general"
    assert captured["cache_hit"] is False
    assert captured["fallback_triggered"] is False
    assert captured["limit"] == 20
    assert captured["offset"] == 5


def test_calibrate_endpoint(monkeypatch):
    client = TestClient(api_mod.app)
    monkeypatch.setattr(api_mod, "get_config", lambda: _cfg())
    monkeypatch.setattr(api_mod, "load_calibration_prompts", lambda: [])
    monkeypatch.setattr(
        api_mod,
        "run_calibration",
        lambda prompts, config, model_call_fn: SimpleNamespace(
            run_id="run-1",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            prompts_count=0,
            models_tested=["sonnet"],
            win_rate_by_task={},
            avg_latency_by_model={},
            total_cost_by_model={},
            regret_rate=0.0,
            cost_vs_baseline=0.0,
        ),
    )

    response = client.post("/api/calibrate", json={"no_model_calls": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-1"
    assert payload["prompts_count"] == 0
