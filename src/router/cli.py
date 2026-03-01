"""CLI entry point for the AI model router."""

from __future__ import annotations

from pathlib import Path

import click
from dotenv import load_dotenv

from router.config import load_config
from router.providers import (
    check_provider_health,
    check_ollama_health,
    load_providers_from_config,
    list_providers,
    get_provider,
    UnknownProviderError,
)
from router.models import ProviderCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(config_dir: str | None = None) -> None:
    """Load providers from config into the registry."""
    cfg = load_config(config_dir=config_dir)
    load_providers_from_config(cfg.providers)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
@click.option("--config-dir", default=None, envvar="ROUTER_CONFIG_DIR",
              help="Path to config directory (default: repo-root/config)")
@click.pass_context
def cli(ctx: click.Context, config_dir: str | None) -> None:
    """AI Model Router — route LLM requests to the optimal provider."""
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir


# ---------------------------------------------------------------------------
# providers subgroup
# ---------------------------------------------------------------------------

@cli.group()
def providers() -> None:
    """Manage and inspect model providers."""


@providers.command("list")
@click.pass_context
def providers_list(ctx: click.Context) -> None:
    """List all configured providers with status."""
    _load(ctx.obj.get("config_dir"))
    all_providers = list_providers()

    if not all_providers:
        click.echo("No providers configured.")
        return

    # Header
    click.echo(f"{'NAME':<18} {'CATEGORY':<14} {'MODEL':<35} {'ENABLED':<9} {'HEALTH'}")
    click.echo("-" * 90)

    for p in sorted(all_providers, key=lambda x: x.name):
        health = check_provider_health(p.name)
        health_str = click.style("✓", fg="green") if health else click.style("✗", fg="red")
        enabled_str = "yes" if p.enabled else "no"
        click.echo(f"{p.name:<18} {p.category.value:<14} {p.model_id:<35} {enabled_str:<9} {health_str}")


@providers.command("check")
@click.argument("name")
@click.pass_context
def providers_check(ctx: click.Context, name: str) -> None:
    """Health-check a specific provider and show detailed status."""
    _load(ctx.obj.get("config_dir"))

    try:
        provider = get_provider(name)
    except UnknownProviderError:
        click.echo(f"Error: provider '{name}' not found in registry.", err=True)
        raise SystemExit(1)

    click.echo(f"Provider  : {provider.display_name} ({provider.name})")
    click.echo(f"Category  : {provider.category.value}")
    click.echo(f"Model     : {provider.model_id}")
    click.echo(f"Base URL  : {provider.base_url}")
    click.echo(f"Enabled   : {'yes' if provider.enabled else 'no'}")
    click.echo(
        f"Pricing   : ${provider.input_price}/M input · "
        f"${provider.output_price}/M output · "
        f"${provider.cached_input_price}/M cached input"
    )

    if provider.category == ProviderCategory.local:
        healthy = check_ollama_health(provider)
        click.echo(f"Ollama    : {'running ✓' if healthy else 'not running ✗'}")
        if healthy:
            click.echo(f"Model loaded: yes ({provider.model_id})")
    else:
        healthy = check_provider_health(name)
        click.echo(f"Health    : {'reachable ✓' if healthy else 'unreachable ✗'}")

    raise SystemExit(0 if healthy else 1)


# ---------------------------------------------------------------------------
# classify subcommand
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("prompt")
def classify(prompt: str) -> None:
    """Classify a prompt and show routing signals (no model call)."""
    from router.classifier import classify_request

    result = classify_request([{"role": "user", "content": prompt}])
    click.echo(f"Task type   : {result.task_type.value}")
    click.echo(f"Complexity  : {result.complexity:.2f}")
    click.echo(f"Token est.  : {result.token_estimate}")
    click.echo(f"Needs tools : {'yes' if result.requires_tools else 'no'}")
    click.echo(f"Factual risk: {'yes' if result.factuality_risk else 'no'}")


# ---------------------------------------------------------------------------
# cost subcommand
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--since", default=None, help="ISO date filter, e.g. 2026-01-01")
@click.option("--until", default=None, help="ISO date filter, e.g. 2026-12-31")
def cost(since: str | None, until: str | None) -> None:
    """Print cost summary from request logs."""
    from datetime import datetime, timezone
    from router.cost import get_cost_summary

    since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None
    until_dt = datetime.fromisoformat(until).replace(tzinfo=timezone.utc) if until else None

    summary = get_cost_summary(since=since_dt, until=until_dt)

    click.echo(f"\nCost Summary")
    click.echo(f"{'Requests':<20}: {summary.request_count}")
    click.echo(f"{'Total cost':<20}: ${summary.total_cost:.6f}")
    click.echo(f"{'Baseline (Sonnet)':<20}: ${summary.baseline_cost:.6f}")
    click.echo(f"{'Savings':<20}: {summary.savings_percentage:.1f}%")

    if summary.cost_by_model:
        click.echo("\nBy model:")
        for model, c in sorted(summary.cost_by_model.items()):
            click.echo(f"  {model:<20} ${c:.6f}")

    if summary.cost_by_task_type:
        click.echo("\nBy task type:")
        for task, c in sorted(summary.cost_by_task_type.items()):
            click.echo(f"  {task:<20} ${c:.6f}")


# ---------------------------------------------------------------------------
# calibrate subcommand
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--no-model-calls", is_flag=True, default=False,
              help="Classify-only mode — skip actual model calls (fast, no API keys needed)")
@click.option("--baseline", default=None,
              help="Path to a previous CalibrationResult JSON for before/after comparison")
@click.pass_context
def calibrate(ctx: click.Context, no_model_calls: bool, baseline: str | None) -> None:
    """Run the calibration suite and report routing quality metrics."""
    import json
    from router.calibration import load_calibration_prompts, run_calibration
    from router.config import load_config
    from router.providers import call_model, load_providers_from_config

    config_dir = ctx.obj.get("config_dir")
    cfg = load_config(config_dir=config_dir)
    load_providers_from_config(cfg.providers)
    prompts = load_calibration_prompts(config_dir=config_dir)

    click.echo(f"Running calibration on {len(prompts)} prompts...")
    if no_model_calls:
        click.echo("Mode: classify-only (no API calls)")
        fn = None
    else:
        click.echo("Mode: full routing (API calls enabled)")
        fn = call_model

    result = run_calibration(prompts, cfg, model_call_fn=fn)

    click.echo(f"\n{'='*55}")
    click.echo(f"  Calibration Report  [{result.run_id[:8]}]")
    click.echo(f"{'='*55}")
    click.echo(f"  Prompts tested : {result.prompts_count}")
    click.echo(f"  Models used    : {', '.join(result.models_tested)}")
    click.echo(f"  Regret rate    : {result.regret_rate:.1%}  (lower is better)")
    click.echo(f"  Cost savings   : {result.cost_vs_baseline:.1%} vs all-baseline")

    click.echo(f"\n  Classification accuracy by task type:")
    for cat, metrics in sorted(result.win_rate_by_task.items()):
        acc = metrics["classification_accuracy"]
        bar = "█" * int(acc * 20)
        click.echo(f"    {cat:<18} {acc:>6.1%}  {bar}")

    if result.avg_latency_by_model:
        click.echo(f"\n  Avg latency (ms) by model:")
        for model, ms in sorted(result.avg_latency_by_model.items()):
            click.echo(f"    {model:<20} {ms:>8.1f} ms")

    if any(v > 0 for v in result.total_cost_by_model.values()):
        click.echo(f"\n  Total cost by model:")
        for model, cost in sorted(result.total_cost_by_model.items()):
            click.echo(f"    {model:<20} ${cost:.6f}")

    # Optionally save result for future before/after comparison
    out_path = Path("logs") / f"calibration_{result.run_id[:8]}.json"
    out_path.parent.mkdir(exist_ok=True)
    with out_path.open("w") as f:
        json.dump({
            "run_id": result.run_id,
            "timestamp": result.timestamp.isoformat(),
            "prompts_count": result.prompts_count,
            "models_tested": result.models_tested,
            "win_rate_by_task": result.win_rate_by_task,
            "avg_latency_by_model": result.avg_latency_by_model,
            "total_cost_by_model": result.total_cost_by_model,
            "regret_rate": result.regret_rate,
            "cost_vs_baseline": result.cost_vs_baseline,
        }, f, indent=2)
    click.echo(f"\n  Saved to: {out_path}")

    # Before/after comparison
    if baseline:
        try:
            with open(baseline) as f:
                prev = json.load(f)
            click.echo(f"\n  Delta vs baseline [{prev['run_id'][:8]}]:")
            prev_regret = prev.get("regret_rate", 0)
            click.echo(f"    Regret rate: {prev_regret:.1%} → {result.regret_rate:.1%}  "
                       f"({result.regret_rate - prev_regret:+.1%})")
            prev_savings = prev.get("cost_vs_baseline", 0)
            click.echo(f"    Cost savings: {prev_savings:.1%} → {result.cost_vs_baseline:.1%}  "
                       f"({result.cost_vs_baseline - prev_savings:+.1%})")
        except Exception as e:
            click.echo(f"  Warning: could not load baseline file: {e}", err=True)


# ---------------------------------------------------------------------------
# route subcommand
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("prompt")
@click.pass_context
def route(ctx: click.Context, prompt: str) -> None:
    """Route a prompt to the best model and print the response."""
    _load(ctx.obj.get("config_dir"))
    from router.pipeline import handle_request

    result = handle_request([{"role": "user", "content": prompt}])
    click.echo(f"Response: {result.response}")
    click.echo(f"\n--- Metadata ---")
    click.echo(f"Model used:    {result.model_used}")
    click.echo(f"Task type:     {result.task_type}")
    click.echo(f"Cost:          ${result.estimated_cost:.6f}")
    click.echo(f"Latency:       {result.latency_ms}ms")
    click.echo(f"Cache hit:     {'yes' if result.cache_hit else 'no'}")
    if result.confidence is not None:
        click.echo(f"Confidence:    {result.confidence:.2f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
