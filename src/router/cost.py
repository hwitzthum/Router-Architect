"""Cost computation, request logging (JSON Lines), and reporting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from router.models import CostSummary, RequestRecord

_LOG_FILE = Path(__file__).parent.parent.parent / "logs" / "requests.jsonl"


def _ensure_log_dir() -> None:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_request(record: RequestRecord, log_file: Optional[Path] = None) -> None:
    """Append a RequestRecord to the JSON Lines log file."""
    path = log_file or _LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": record.id,
        "timestamp": record.timestamp.isoformat(),
        "model_used": record.model_used,
        "task_type": record.classification.task_type.value,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cost": record.cost,
        "latency_ms": record.latency_ms,
        "router_overhead_ms": record.router_overhead_ms,
        "cache_hit": record.cache_hit,
        "fallback_triggered": record.fallback_triggered,
        "confidence": record.confidence,
    }
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    input_price: float,
    output_price: float,
    cached_input_tokens: int = 0,
    cached_input_price: float = 0.0,
) -> float:
    """
    Compute cost in USD from token counts and per-million prices.

    `cached_input_tokens` is a subset of `input_tokens` billed at `cached_input_price`.
    """
    cached_input_tokens = max(0, min(cached_input_tokens, input_tokens))
    uncached_input_tokens = max(0, input_tokens - cached_input_tokens)
    return (
        (uncached_input_tokens / 1_000_000) * input_price
        + (cached_input_tokens / 1_000_000) * cached_input_price
        + (output_tokens / 1_000_000) * output_price
    )


def get_cost_summary(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    baseline_model_input_price: float = 3.0,
    baseline_model_output_price: float = 15.0,
    log_file: Optional[Path] = None,
) -> CostSummary:
    """Aggregate cost data from the JSON Lines log."""
    path = log_file or _LOG_FILE
    if not path.exists():
        return CostSummary(
            total_cost=0.0,
            cost_by_model={},
            cost_by_task_type={},
            request_count=0,
            baseline_cost=0.0,
            savings_percentage=0.0,
        )

    cost_by_model: dict[str, float] = {}
    cost_by_task: dict[str, float] = {}
    total_cost = 0.0
    baseline_cost = 0.0
    count = 0
    cache_hits = 0

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            try:
                ts = datetime.fromisoformat(entry["timestamp"])
            except (KeyError, ValueError):
                continue
            if since and ts < since:
                continue
            if until and ts > until:
                continue

            cost = entry["cost"]
            model = entry["model_used"]
            task = entry["task_type"]
            in_tok = entry["input_tokens"]
            out_tok = entry["output_tokens"]

            total_cost += cost
            cost_by_model[model] = cost_by_model.get(model, 0.0) + cost
            cost_by_task[task] = cost_by_task.get(task, 0.0) + cost
            baseline_cost += compute_cost(
                in_tok, out_tok,
                baseline_model_input_price,
                baseline_model_output_price,
            )
            if entry.get("cache_hit", False):
                cache_hits += 1
            count += 1

    savings_pct = 0.0
    if baseline_cost > 0:
        savings_pct = round((baseline_cost - total_cost) / baseline_cost * 100, 2)

    cache_hit_rate = round(cache_hits / count, 4) if count > 0 else 0.0

    return CostSummary(
        total_cost=round(total_cost, 6),
        cost_by_model={k: round(v, 6) for k, v in cost_by_model.items()},
        cost_by_task_type={k: round(v, 6) for k, v in cost_by_task.items()},
        request_count=count,
        baseline_cost=round(baseline_cost, 6),
        savings_percentage=savings_pct,
        cache_hit_rate=cache_hit_rate,
    )


def get_request_timeline(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    model: Optional[str] = None,
    task_type: Optional[str] = None,
    cache_hit: Optional[bool] = None,
    fallback_triggered: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    log_file: Optional[Path] = None,
) -> dict:
    """
    Return request-log entries for timeline views with filtering and pagination.

    Response shape:
      {
        "total": <int>,   # number of filtered records before pagination
        "items": <list>   # paginated records (newest first)
      }
    """
    path = log_file or _LOG_FILE
    if not path.exists():
        return {"total": 0, "items": []}

    entries: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            try:
                ts = datetime.fromisoformat(entry["timestamp"])
            except (KeyError, ValueError):
                continue

            if since and ts < since:
                continue
            if until and ts > until:
                continue
            if model and entry.get("model_used") != model:
                continue
            if task_type and entry.get("task_type") != task_type:
                continue
            if cache_hit is not None and bool(entry.get("cache_hit", False)) != cache_hit:
                continue
            if (
                fallback_triggered is not None
                and bool(entry.get("fallback_triggered", False)) != fallback_triggered
            ):
                continue

            entries.append(entry)

    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    total = len(entries)
    page = entries[offset : offset + limit]
    return {"total": total, "items": page}
