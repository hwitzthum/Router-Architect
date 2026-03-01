"""Jailbreak detection plugin — pattern-matching pre-routing filter."""

from __future__ import annotations

import re

from router.plugins.base import BasePlugin, PluginOutcome, PluginResult


# ---------------------------------------------------------------------------
# Known jailbreak patterns (case-insensitive)
# ---------------------------------------------------------------------------

_PATTERNS: list[str] = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(your\s+)?(previous\s+)?instructions",
    r"forget\s+(your\s+)?instructions",
    r"override\s+(your\s+)?instructions",
    r"your\s+new\s+instructions\s+are",
    r"you\s+are\s+now\s+(a\s+)?dan",
    r"pretend\s+you\s+(are|have)\s+no\s+restrict",
    r"act\s+as\s+if\s+you\s+have\s+no\s+restrict",
    r"you\s+have\s+no\s+restrictions",
    r"bypass\s+(your\s+)?(safety|training|filter)",
    r"\bjailbreak\b",
    r"ignore\s+the\s+above",
    r"do\s+anything\s+now",
    r"developer\s+mode\s+(on|enabled)",
    r"simulate\s+(an?\s+)?unrestrict",
    r"with\s+no\s+ethical\s+(guidelines|constraints|restrictions)",
    r"disable\s+(your\s+)?(safety|ethical|content)\s+(filter|guidelines|restrictions)",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _PATTERNS]


class JailbreakDetectionPlugin(BasePlugin):
    """
    Blocks requests that match known jailbreak patterns.

    Any match in any message (user or system) causes a BLOCK outcome.
    """

    name = "jailbreak_detection"

    def check(self, messages: list[dict]) -> PluginResult:
        full_text = " ".join(
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        )

        for pattern in _COMPILED:
            match = pattern.search(full_text)
            if match:
                return PluginResult(
                    outcome=PluginOutcome.BLOCK,
                    messages=messages,
                    reason=f"Jailbreak pattern detected: '{match.group(0)[:60]}'",
                )

        return PluginResult(outcome=PluginOutcome.PASS, messages=messages)