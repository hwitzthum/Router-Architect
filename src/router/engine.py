"""Decision engine: maps ClassificationResult → RoutingDecision, with fallback."""

from __future__ import annotations

from typing import Callable

from router.models import ClassificationResult, RoutingDecision, RoutingRule


def route_request(
    classification: ClassificationResult,
    rules: list[RoutingRule],
    default_model: str,
) -> RoutingDecision:
    """
    Evaluate routing rules in priority order against a ClassificationResult.
    Returns the first matching rule's RoutingDecision, or a default if none match.
    """
    for rule in rules:  # already sorted by priority in config loader
        if rule.task_type != classification.task_type:
            continue
        if not (rule.complexity_min <= classification.complexity <= rule.complexity_max):
            continue
        return RoutingDecision(
            selected_model=rule.target_model,
            fallback_chain=list(rule.fallback_chain),
            reason=(
                f"Matched rule: task_type={rule.task_type.value}, "
                f"complexity={classification.complexity:.2f} in "
                f"[{rule.complexity_min}, {rule.complexity_max}], "
                f"priority={rule.priority}"
            ),
        )

    # No rule matched — use configured default
    return RoutingDecision(
        selected_model=default_model,
        fallback_chain=[],
        reason=f"No rule matched; using default model '{default_model}'",
    )


def resolve_available_model(
    decision: RoutingDecision,
    health_check_fn: Callable[[str], bool],
) -> tuple[str, bool]:
    """
    Walk the selected model and its fallback chain to find a healthy provider.

    Returns (model_name, fallback_triggered).
    Raises AllProvidersUnavailableError if none are reachable.
    """
    from router.providers import AllProvidersUnavailableError

    candidates = [decision.selected_model] + decision.fallback_chain

    for i, model in enumerate(candidates):
        if health_check_fn(model):
            fallback_triggered = i > 0
            return model, fallback_triggered

    raise AllProvidersUnavailableError(
        f"All providers unavailable: {candidates}"
    )
