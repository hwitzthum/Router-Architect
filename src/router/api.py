"""FastAPI surface for the router pipeline and operational telemetry."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from router.calibration import load_calibration_prompts, run_calibration
from router.classifier import classify_request
from router.cost import get_cost_summary, get_request_timeline
from router.pipeline import (
    AllModelsFailedError,
    RequestBlockedError,
    get_config,
    handle_request,
)
from router.providers import (
    AllProvidersUnavailableError,
    call_model,
    check_provider_health,
)


class ChatMessage(BaseModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class PromptEnvelope(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[list[ChatMessage]] = None

    @model_validator(mode="after")
    def require_prompt_or_messages(self) -> "PromptEnvelope":
        has_prompt = bool((self.prompt or "").strip())
        has_messages = bool(self.messages)
        if has_prompt == has_messages:
            raise ValueError("Provide exactly one of 'prompt' or 'messages'")
        return self

    def as_messages(self) -> list[dict]:
        if self.prompt is not None:
            return [{"role": "user", "content": self.prompt}]
        return [m.model_dump() for m in self.messages or []]


class CalibrateEnvelope(BaseModel):
    no_model_calls: bool = True


def _parse_iso_datetime(value: Optional[str], label: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid '{label}' datetime: {value}. Use ISO-8601 format.",
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def create_app() -> FastAPI:
    app = FastAPI(
        title="Router Architecture API",
        version="0.1.0",
        description="HTTP API for model routing, provider health, and calibration.",
    )

    cors_origins = os.getenv(
        "ROUTER_UI_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/api/health")
    def health() -> dict:
        cfg = get_config()
        return {
            "status": "ok",
            "default_model": cfg.default_model,
            "providers_configured": len(cfg.providers),
        }

    @app.post("/api/classify")
    def classify(payload: PromptEnvelope) -> dict:
        cfg = get_config()
        classification = classify_request(
            payload.as_messages(),
            embedding_config=cfg.plugins.embedding,
        )
        return {
            "task_type": classification.task_type.value,
            "complexity": classification.complexity,
            "token_estimate": classification.token_estimate,
            "requires_tools": classification.requires_tools,
            "factuality_risk": classification.factuality_risk,
        }

    @app.post("/api/route")
    def route(payload: PromptEnvelope) -> dict:
        try:
            result = handle_request(payload.as_messages())
        except RequestBlockedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (AllProvidersUnavailableError, AllModelsFailedError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return {
            "response": result.response,
            "model_used": result.model_used,
            "task_type": result.task_type,
            "estimated_cost": result.estimated_cost,
            "latency_ms": result.latency_ms,
            "cache_hit": result.cache_hit,
            "fallback_triggered": result.fallback_triggered,
            "confidence": result.confidence,
        }

    @app.get("/api/providers")
    def providers() -> dict:
        cfg = get_config()
        providers_out = []
        for provider in cfg.providers:
            providers_out.append(
                {
                    "name": provider.name,
                    "display_name": provider.display_name,
                    "category": provider.category.value,
                    "model_id": provider.model_id,
                    "base_url": provider.base_url,
                    "enabled": provider.enabled,
                    "healthy": check_provider_health(provider.name) if provider.enabled else False,
                    "input_price": provider.input_price,
                    "output_price": provider.output_price,
                    "cached_input_price": provider.cached_input_price,
                    "max_context_tokens": provider.max_context_tokens,
                }
            )
        return {
            "default_model": cfg.default_model,
            "providers": providers_out,
        }

    @app.get("/api/cost")
    def cost(
        since: Optional[str] = Query(default=None),
        until: Optional[str] = Query(default=None),
    ) -> dict:
        summary = get_cost_summary(
            since=_parse_iso_datetime(since, "since"),
            until=_parse_iso_datetime(until, "until"),
        )
        return {
            "total_cost": summary.total_cost,
            "cost_by_model": summary.cost_by_model,
            "cost_by_task_type": summary.cost_by_task_type,
            "request_count": summary.request_count,
            "baseline_cost": summary.baseline_cost,
            "savings_percentage": summary.savings_percentage,
            "cache_hit_rate": summary.cache_hit_rate,
        }

    @app.post("/api/calibrate")
    def calibrate(payload: CalibrateEnvelope) -> dict:
        cfg = get_config()
        prompts = load_calibration_prompts()
        result = run_calibration(
            prompts,
            cfg,
            model_call_fn=None if payload.no_model_calls else call_model,
        )
        return {
            "run_id": result.run_id,
            "timestamp": result.timestamp.isoformat(),
            "prompts_count": result.prompts_count,
            "models_tested": result.models_tested,
            "win_rate_by_task": result.win_rate_by_task,
            "avg_latency_by_model": result.avg_latency_by_model,
            "total_cost_by_model": result.total_cost_by_model,
            "regret_rate": result.regret_rate,
            "cost_vs_baseline": result.cost_vs_baseline,
        }

    @app.get("/api/requests")
    def requests(
        since: Optional[str] = Query(default=None),
        until: Optional[str] = Query(default=None),
        model: Optional[str] = Query(default=None),
        task_type: Optional[str] = Query(default=None),
        cache_hit: Optional[bool] = Query(default=None),
        fallback_triggered: Optional[bool] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        return get_request_timeline(
            since=_parse_iso_datetime(since, "since"),
            until=_parse_iso_datetime(until, "until"),
            model=model,
            task_type=task_type,
            cache_hit=cache_hit,
            fallback_triggered=fallback_triggered,
            limit=limit,
            offset=offset,
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.getenv("ROUTER_API_HOST", "0.0.0.0")
    port = int(os.getenv("ROUTER_API_PORT", "8001"))
    reload = os.getenv("ROUTER_API_RELOAD", "0").lower() in {"1", "true", "yes"}
    uvicorn.run("router.api:app", host=host, port=port, reload=reload)
