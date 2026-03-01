"""Refined classifier tests — 20+ prompts, 80%+ accuracy required (T042)."""

from __future__ import annotations

import pytest
from router.classifier import classify_request
from router.models import TaskType


def msg(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


# ---------------------------------------------------------------------------
# 20+ classification accuracy tests spanning all 6 task types
# ---------------------------------------------------------------------------

ACCURACY_CASES: list[tuple[str, TaskType]] = [
    # --- Reasoning (6) ---
    ("Prove that the square root of 2 is irrational.",
     TaskType.reasoning),
    ("Solve this logic puzzle: if all mammals breathe air and whales breathe air, are whales mammals?",
     TaskType.reasoning),
    ("Calculate the compound interest on a $10,000 investment at 5% for 10 years.",
     TaskType.reasoning),
    ("Compute the eigenvalues of a 2x2 matrix [[3,1],[0,2]].",
     TaskType.reasoning),
    ("Determine whether the following argument is valid: All A are B; some B are C; therefore some A are C.",
     TaskType.reasoning),
    ("Given that f(x) = x^2 and g(x) = 2x + 1, find f(g(3)) step by step.",
     TaskType.reasoning),
    # --- Knowledge work (5) ---
    ("Evaluate the strategic risks of a SaaS company expanding into the European market.",
     TaskType.knowledge_work),
    ("What are best practices for securing a REST API in production?",
     TaskType.knowledge_work),
    ("Provide an executive summary of the competitive landscape for electric vehicles.",
     TaskType.knowledge_work),
    ("Analyze the ROI implications of migrating a monolith to microservices.",
     TaskType.knowledge_work),
    ("Research and compare the pros and cons of Agile vs Waterfall for a regulated industry.",
     TaskType.knowledge_work),
    # --- Code (5) ---
    ("Write a Python function to implement binary search.",
     TaskType.code),
    ("Debug this TypeScript code: the map function is returning undefined.",
     TaskType.code),
    ("Refactor this class to follow the single-responsibility principle.",
     TaskType.code),
    ("Write unit tests for this authentication module.",
     TaskType.code),
    ("How do I deploy a Docker container to Kubernetes with a rolling update strategy?",
     TaskType.code),
    # --- Extraction (5) ---
    ("Summarize the following article in three bullet points.",
     TaskType.extraction),
    ("Translate this paragraph to Spanish: The quick brown fox jumps over the lazy dog.",
     TaskType.extraction),
    ("What are the key takeaways from the following meeting notes?",
     TaskType.extraction),
    ("Enumerate all the steps mentioned in this process document.",
     TaskType.extraction),
    ("Extract all dates, names, and dollar amounts from this contract.",
     TaskType.extraction),
    # --- Creative (3) ---
    ("Write a haiku about the passage of time.",
     TaskType.creative),
    ("Draft a compelling product tagline for an AI-powered writing assistant.",
     TaskType.creative),
    ("Brainstorm 10 original startup ideas combining blockchain with healthcare.",
     TaskType.creative),
    # --- General (2) ---
    ("What time is it in Tokyo when it is 3pm in New York?",
     TaskType.general),
    ("How many days are in a leap year?",
     TaskType.general),
]


class TestClassificationAccuracy:
    """Assert overall accuracy >= 80% across 26 diverse prompts."""

    def _classify_all(self) -> list[tuple[str, TaskType, TaskType]]:
        results = []
        for prompt, expected in ACCURACY_CASES:
            got = classify_request(msg(prompt)).task_type
            results.append((prompt, expected, got))
        return results

    def test_overall_accuracy_at_least_80_percent(self):
        results = self._classify_all()
        correct = sum(1 for _, exp, got in results if exp == got)
        accuracy = correct / len(results)
        failing = [(p, exp.value, got.value) for p, exp, got in results if exp != got]
        assert accuracy >= 0.80, (
            f"Accuracy {accuracy:.0%} below 80% threshold. Failures:\n"
            + "\n".join(f"  [{got}≠{exp}] {p[:80]}" for p, exp, got in failing)
        )

    # Individual spot-checks for high-value cases
    def test_calculate_routes_to_reasoning(self):
        r = classify_request(msg("Calculate the compound interest on $10,000 at 5%."))
        assert r.task_type == TaskType.reasoning

    def test_compute_routes_to_reasoning(self):
        r = classify_request(msg("Compute the eigenvalues of this matrix."))
        assert r.task_type == TaskType.reasoning

    def test_best_practices_routes_to_knowledge(self):
        r = classify_request(msg("What are best practices for managing a distributed remote engineering team?"))
        assert r.task_type == TaskType.knowledge_work

    def test_executive_summary_routes_to_knowledge(self):
        r = classify_request(msg("Write an executive summary of the competitive landscape."))
        assert r.task_type == TaskType.knowledge_work

    def test_key_takeaways_routes_to_extraction(self):
        r = classify_request(msg("What are the key takeaways from this report?"))
        assert r.task_type == TaskType.extraction

    def test_enumerate_routes_to_extraction(self):
        r = classify_request(msg("Enumerate all steps mentioned in the following document."))
        assert r.task_type == TaskType.extraction

    def test_tagline_routes_to_creative(self):
        r = classify_request(msg("Draft a compelling tagline for our AI startup."))
        assert r.task_type == TaskType.creative

    def test_docker_kubernetes_routes_to_code(self):
        r = classify_request(msg("How do I deploy a Docker container to Kubernetes?"))
        assert r.task_type == TaskType.code


# ---------------------------------------------------------------------------
# Complexity scoring edge cases (T040)
# ---------------------------------------------------------------------------

class TestComplexityScoringRefined:
    def test_extraction_is_low(self):
        r = classify_request(msg("Summarize this in one sentence: The cat sat on the mat."))
        assert r.complexity <= 0.4

    def test_simple_extraction_lower_than_complex_reasoning(self):
        simple = classify_request(msg("Translate: hello"))
        hard = classify_request(msg(
            "Prove step by step that there are infinitely many prime numbers. "
            "First assume finitely many, then derive a contradiction, then conclude."
        ))
        assert hard.complexity > simple.complexity

    def test_multi_step_prompt_raises_complexity(self):
        single = classify_request(msg("Solve the equation x^2 = 4."))
        multi = classify_request(msg(
            "First, compute all prime factors of 360. Then calculate the GCD with 180. "
            "Next, prove the result using the Euclidean algorithm. Finally, conclude."
        ))
        assert multi.complexity > single.complexity

    def test_long_prompt_higher_than_short(self):
        short = classify_request(msg("Write a function."))
        long = classify_request(msg(("Write a function. " * 50).strip()))
        assert long.complexity >= short.complexity

    def test_reasoning_base_is_higher_than_extraction_base(self):
        r_reasoning = classify_request(msg("Prove this theorem."))
        r_extraction = classify_request(msg("Summarize this text."))
        assert r_reasoning.complexity > r_extraction.complexity

    def test_multiple_questions_raises_complexity(self):
        single = classify_request(msg("What is the capital of France?"))
        multi = classify_request(msg(
            "What is the capital? What is the population? "
            "What is the GDP? What are the major industries? "
            "What is the history of the region?"
        ))
        assert multi.complexity >= single.complexity

    def test_complexity_capped_at_1(self):
        very_long = classify_request(msg(
            "Prove step by step first then second then third "
            "additionally finally " * 100
        ))
        assert very_long.complexity <= 1.0

    def test_complexity_minimum_is_positive(self):
        r = classify_request(msg("Hi"))
        assert r.complexity >= 0.0


# ---------------------------------------------------------------------------
# Flag detection
# ---------------------------------------------------------------------------

class TestFlagDetectionRefined:
    def test_json_sets_requires_tools(self):
        r = classify_request(msg("Return the result as JSON with fields name and age."))
        assert r.requires_tools is True

    def test_csv_sets_requires_tools(self):
        r = classify_request(msg("Convert this data to CSV format."))
        assert r.requires_tools is True

    def test_workflow_sets_requires_tools(self):
        r = classify_request(msg("Design a workflow for the approval process."))
        assert r.requires_tools is True

    def test_verify_sets_factuality_risk(self):
        r = classify_request(msg("Verify this statistical claim with evidence from peer-reviewed sources."))
        assert r.factuality_risk is True

    def test_data_sets_factuality_risk(self):
        r = classify_request(msg("Back up your answer with scientific data."))
        assert r.factuality_risk is True

    def test_creative_prompt_has_no_flags(self):
        r = classify_request(msg("Write a haiku about spring."))
        assert r.requires_tools is False
        assert r.factuality_risk is False