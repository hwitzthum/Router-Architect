"""Safety and quality plugins for the routing pipeline."""

from __future__ import annotations

from router.plugins.base import BasePlugin, PluginOutcome, PluginResult
from router.plugins.jailbreak import JailbreakDetectionPlugin
from router.plugins.pii import PIIRedactionPlugin


# ---------------------------------------------------------------------------
# Plugin chain runner
# ---------------------------------------------------------------------------

def run_plugin_chain(
    plugins: list[BasePlugin],
    messages: list[dict],
) -> PluginResult:
    """
    Execute plugins in order.

    - BLOCK: stop immediately and return the block result.
    - SANITIZE: continue pipeline with the sanitized messages.
    - PASS: continue unchanged.

    Returns the final PluginResult after all plugins have run.
    """
    current = messages
    sanitized = False
    last_reason = ""

    for plugin in plugins:
        result = plugin.check(current)
        if result.outcome == PluginOutcome.BLOCK:
            return result
        elif result.outcome == PluginOutcome.SANITIZE:
            current = result.messages
            sanitized = True
            last_reason = result.reason

    if sanitized:
        return PluginResult(outcome=PluginOutcome.SANITIZE, messages=current, reason=last_reason)
    return PluginResult(outcome=PluginOutcome.PASS, messages=current)


# ---------------------------------------------------------------------------
# Factory: build active plugin list from SafetyConfig
# ---------------------------------------------------------------------------

def build_plugin_chain(safety_config) -> list[BasePlugin]:
    """
    Instantiate enabled plugins from a SafetyConfig object.
    Order: jailbreak → PII redaction → (prompt injection placeholder).
    """
    plugins: list[BasePlugin] = []

    if safety_config.jailbreak_detection.enabled:
        plugins.append(JailbreakDetectionPlugin())

    if safety_config.pii_redaction.enabled:
        plugins.append(PIIRedactionPlugin())

    return plugins


__all__ = [
    "BasePlugin",
    "PluginOutcome",
    "PluginResult",
    "JailbreakDetectionPlugin",
    "PIIRedactionPlugin",
    "run_plugin_chain",
    "build_plugin_chain",
]