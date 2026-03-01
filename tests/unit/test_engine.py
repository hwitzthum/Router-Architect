"""Unit tests for the decision engine (T025)."""

import pytest
from router.engine import route_request, resolve_available_model
from router.models import ClassificationResult, RoutingRule, TaskType
from router.providers import AllProvidersUnavailableError


def make_rules() -> list[RoutingRule]:
    return [
        RoutingRule(task_type=TaskType.reasoning, complexity_min=0.6, complexity_max=1.0,
                    target_model="gemini", fallback_chain=["sonnet"], priority=1),
        RoutingRule(task_type=TaskType.knowledge_work, complexity_min=0.0, complexity_max=1.0,
                    target_model="sonnet", fallback_chain=["gemini"], priority=2),
        RoutingRule(task_type=TaskType.code, complexity_min=0.7, complexity_max=1.0,
                    target_model="gemini", fallback_chain=["sonnet"], priority=3),
        RoutingRule(task_type=TaskType.code, complexity_min=0.0, complexity_max=0.7,
                    target_model="qwen", fallback_chain=["ollama-qwen35", "sonnet"], priority=4),
        RoutingRule(task_type=TaskType.extraction, complexity_min=0.0, complexity_max=1.0,
                    target_model="ollama-qwen35", fallback_chain=["qwen", "sonnet"], priority=5),
    ]


def clf(task_type: TaskType, complexity: float) -> ClassificationResult:
    return ClassificationResult(
        task_type=task_type, complexity=complexity,
        token_estimate=100, requires_tools=False, factuality_risk=False,
    )


class TestRouteRequest:
    def test_high_complexity_reasoning_routes_to_gemini(self):
        d = route_request(clf(TaskType.reasoning, 0.8), make_rules(), "sonnet")
        assert d.selected_model == "gemini"

    def test_low_complexity_reasoning_falls_through_to_default(self):
        # complexity 0.3 doesn't match the reasoning rule (min 0.6)
        d = route_request(clf(TaskType.reasoning, 0.3), make_rules(), "sonnet")
        assert d.selected_model == "sonnet"  # default

    def test_knowledge_work_routes_to_sonnet(self):
        d = route_request(clf(TaskType.knowledge_work, 0.5), make_rules(), "sonnet")
        assert d.selected_model == "sonnet"

    def test_high_complexity_code_routes_to_gemini(self):
        d = route_request(clf(TaskType.code, 0.8), make_rules(), "sonnet")
        assert d.selected_model == "gemini"

    def test_low_complexity_code_routes_to_qwen(self):
        d = route_request(clf(TaskType.code, 0.4), make_rules(), "sonnet")
        assert d.selected_model == "qwen"

    def test_extraction_routes_to_local(self):
        d = route_request(clf(TaskType.extraction, 0.3), make_rules(), "sonnet")
        assert d.selected_model == "ollama-qwen35"

    def test_unmatched_falls_back_to_default(self):
        d = route_request(clf(TaskType.creative, 0.5), make_rules(), "sonnet")
        assert d.selected_model == "sonnet"
        assert "default" in d.reason

    def test_fallback_chain_included(self):
        d = route_request(clf(TaskType.extraction, 0.3), make_rules(), "sonnet")
        assert "qwen" in d.fallback_chain
        assert "sonnet" in d.fallback_chain


class TestResolveAvailableModel:
    def test_primary_healthy(self):
        from router.models import RoutingDecision
        decision = RoutingDecision(
            selected_model="gemini",
            fallback_chain=["sonnet", "ollama-qwen35"],
            reason="test",
        )
        model, triggered = resolve_available_model(decision, lambda m: True)
        assert model == "gemini"
        assert triggered is False

    def test_primary_down_uses_first_fallback(self):
        from router.models import RoutingDecision
        decision = RoutingDecision(
            selected_model="gemini",
            fallback_chain=["sonnet", "ollama-qwen35"],
            reason="test",
        )
        # gemini is down, sonnet is up
        model, triggered = resolve_available_model(
            decision, lambda m: m != "gemini"
        )
        assert model == "sonnet"
        assert triggered is True

    def test_all_down_raises(self):
        from router.models import RoutingDecision
        decision = RoutingDecision(
            selected_model="gemini",
            fallback_chain=["sonnet"],
            reason="test",
        )
        with pytest.raises(AllProvidersUnavailableError):
            resolve_available_model(decision, lambda m: False)
