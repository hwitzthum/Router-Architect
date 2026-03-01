"""PII redaction plugin — regex-based detection and placeholder substitution."""

from __future__ import annotations

import copy
import re

from router.plugins.base import BasePlugin, PluginOutcome, PluginResult


# ---------------------------------------------------------------------------
# PII patterns with placeholder labels
# ---------------------------------------------------------------------------

_PII_RULES: list[tuple[str, str]] = [
    # Email addresses
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "[EMAIL]"),
    # US Social Security Numbers  (NNN-NN-NNNN)
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    # Credit card numbers (4×4 digit groups, various separators)
    (r"\b(?:\d{4}[\s\-]?){3}\d{4}\b", "[CC]"),
    # US phone numbers — many formats
    (r"\b(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b", "[PHONE]"),
    # UK National Insurance numbers
    (r"\b[A-Z]{2}\d{6}[A-D]\b", "[NI]"),
    # IPv4 addresses (often inadvertent PII in logs)
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]"),
]

_COMPILED_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern), placeholder)
    for pattern, placeholder in _PII_RULES
]


def redact(text: str) -> tuple[str, list[str]]:
    """
    Replace PII in *text* with placeholders.

    Returns:
        (redacted_text, list_of_redacted_types)
    """
    redacted = text
    found: list[str] = []
    for pattern, placeholder in _COMPILED_RULES:
        new_text, n = pattern.subn(placeholder, redacted)
        if n:
            found.append(placeholder)
            redacted = new_text
    return redacted, found


class PIIRedactionPlugin(BasePlugin):
    """
    Redacts emails, phone numbers, SSNs, credit card numbers, and IPs
    from all message content before forwarding to a model.

    Outcome is SANITIZE when any PII is found, PASS otherwise.
    """

    name = "pii_redaction"

    def check(self, messages: list[dict]) -> PluginResult:
        # Quick scan: check if any PII exists before expensive deepcopy
        full_text = " ".join(
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        )
        _, quick_found = redact(full_text)
        if not quick_found:
            return PluginResult(outcome=PluginOutcome.PASS, messages=messages)

        # PII detected — deep copy and redact per-message
        sanitized = copy.deepcopy(messages)
        all_found: list[str] = []

        for msg in sanitized:
            if isinstance(msg.get("content"), str):
                new_content, found = redact(msg["content"])
                if found:
                    msg["content"] = new_content
                    all_found.extend(found)

        types = sorted(set(all_found))
        return PluginResult(
            outcome=PluginOutcome.SANITIZE,
            messages=sanitized,
            reason=f"Redacted PII: {', '.join(types)}",
        )