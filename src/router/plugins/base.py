"""Base interface for all safety and quality plugins."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PluginOutcome(str, Enum):
    PASS = "pass"          # request is clean, proceed unchanged
    BLOCK = "block"        # request must not be forwarded to any model
    SANITIZE = "sanitize"  # request was modified; continue with sanitized messages


@dataclass
class PluginResult:
    outcome: PluginOutcome
    messages: list[dict]   # original or sanitized messages
    reason: str = ""       # human-readable explanation (used for BLOCK / SANITIZE)


class BasePlugin:
    """Abstract base for all pipeline plugins."""

    name: str = "base"
    enabled: bool = True

    def check(self, messages: list[dict]) -> PluginResult:
        """
        Inspect (and optionally modify) messages before they reach a model.

        Returns:
            PluginResult with outcome PASS, BLOCK, or SANITIZE.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.check() must be implemented")