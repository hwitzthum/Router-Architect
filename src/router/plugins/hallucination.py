"""Hallucination detection plugin — scores model response confidence (0.0–1.0)."""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Heuristic signal tables
# ---------------------------------------------------------------------------

# Hedging language: phrases that suggest uncertainty
_HEDGING_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bi('m| am) not sure\b",
        r"\bi('m| am) not certain\b",
        r"\bi don'?t know\b",
        r"\bi('m| am) unsure\b",
        r"\bit'?s? (possible|possible that|unclear|uncertain)\b",
        r"\bmight be\b",
        r"\bcould be\b",
        r"\bprobably\b",
        r"\bperhaps\b",
        r"\bmaybe\b",
        r"\bseems? (to|like|as though)\b",
        r"\bappears? (to|like|as though)\b",
        r"\bi believe\b",
        r"\bi think\b",
        r"\bin my (opinion|view|understanding)\b",
        r"\bto my knowledge\b",
        r"\bas far as i know\b",
        r"\bi can'?t (confirm|verify|be sure)\b",
        r"\bnot (entirely|completely|100%) (sure|certain|accurate)\b",
        r"\bapproximately\b",
        r"\baround\b",
        r"\broughly\b",
        r"\bsomewhere (around|between|near)\b",
        r"\bif i recall correctly\b",
        r"\bif memory serves\b",
        r"\bif i('m| am) not mistaken\b",
    ]
]

# Contradiction signals: phrases that indicate the response contradicts itself
_CONTRADICTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bon the other hand\b",
        r"\bhowever,? i (previously|earlier) (said|stated|mentioned)\b",
        r"\bconversely\b",
        r"\bthis contradicts\b",
        r"\bactually,? (that|this) (is|was) (wrong|incorrect|not right)\b",
        r"\bwait,? (actually|no)\b",
        r"\bcorrection:",
        r"\blet me (correct|clarify|revise) (that|myself)\b",
        r"\bi (made|made a) (mistake|error)\b",
        r"\bmy (previous|earlier) (answer|response|statement) (was )?incorrect\b",
    ]
]

# Unsupported claim signals: bold assertions with no backing
_UNSUPPORTED_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\beveryone knows\b",
        r"\bit'?s? (a )?well[- ]known (fact|that)\b",
        r"\bobviously\b",
        r"\bclearly\b",
        r"\bscientifically? proven\b",
        r"\bstudies (show|prove|have shown|have proven)\b",
        r"\bexperts (agree|say|believe)\b",
        r"\bit'?s? been (proven|established|confirmed) that\b",
        r"\bno one (would|could|should)\b",
        r"\bthe (only|best|worst) (way|option|solution) is\b",
        r"\bguaranteed to\b",
        r"\balways (works?|true|correct)\b",
        r"\bnever (fails?|wrong|incorrect)\b",
        r"\bwithout (a )?doubt\b",
    ]
]


# ---------------------------------------------------------------------------
# Public scoring API
# ---------------------------------------------------------------------------

def score_response(response: str) -> float:
    """
    Compute a confidence score for a model response.

    Returns a float in [0.0, 1.0]:
      1.0 = high confidence (no red flags)
      0.0 = very low confidence (many red flags)

    Scoring formula:
      - Each hedging phrase match:         -0.05 per match (capped at -0.40)
      - Each contradiction match:          -0.15 per match (capped at -0.30)
      - Each unsupported claim match:      -0.08 per match (capped at -0.24)
      All penalties combine; score is clamped to [0.0, 1.0].
    """
    hedging_hits = sum(len(p.findall(response)) for p in _HEDGING_PATTERNS)
    contradiction_hits = sum(len(p.findall(response)) for p in _CONTRADICTION_PATTERNS)
    unsupported_hits = sum(len(p.findall(response)) for p in _UNSUPPORTED_PATTERNS)

    penalty = (
        min(hedging_hits * 0.05, 0.40)
        + min(contradiction_hits * 0.15, 0.30)
        + min(unsupported_hits * 0.08, 0.24)
    )
    return max(0.0, round(1.0 - penalty, 4))