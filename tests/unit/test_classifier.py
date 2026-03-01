"""Unit tests for the task classifier (T024)."""

import pytest
from router.classifier import classify_request
from router.models import TaskType


def msg(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


class TestTaskTypeClassification:
    # Reasoning
    def test_logic_puzzle(self):
        r = classify_request(msg("Solve this logic puzzle: all A are B, all B are C, are all A therefore C?"))
        assert r.task_type == TaskType.reasoning

    def test_math_proof(self):
        r = classify_request(msg("Prove that the square root of 2 is irrational."))
        assert r.task_type == TaskType.reasoning

    def test_step_by_step_reasoning(self):
        r = classify_request(msg("Walk me through the logical steps to derive Bayes theorem."))
        assert r.task_type == TaskType.reasoning

    # Code
    def test_write_function(self):
        r = classify_request(msg("Write a Python function to implement binary search."))
        assert r.task_type == TaskType.code

    def test_debug_code(self):
        r = classify_request(msg("Debug this code: def fib(n): return fib(n-1) + fib(n-2)"))
        assert r.task_type == TaskType.code

    def test_refactor(self):
        r = classify_request(msg("Refactor this function to use type hints and be more Pythonic."))
        assert r.task_type == TaskType.code

    # Extraction
    def test_summarize(self):
        r = classify_request(msg("Summarize this paragraph in two sentences: The fox jumped over the dog."))
        assert r.task_type == TaskType.extraction

    def test_translate(self):
        r = classify_request(msg("Translate the following text to French: Good morning!"))
        assert r.task_type == TaskType.extraction

    def test_extract_entities(self):
        r = classify_request(msg("Extract all names, dates, and dollar amounts from this document."))
        assert r.task_type == TaskType.extraction

    # Knowledge work
    def test_business_strategy(self):
        r = classify_request(msg("Evaluate the business strategy of a startup competing with Stripe."))
        assert r.task_type == TaskType.knowledge_work

    def test_market_analysis(self):
        r = classify_request(msg("Analyze the key risks of entering the European market for a SaaS product."))
        assert r.task_type == TaskType.knowledge_work

    # Creative
    def test_poem(self):
        r = classify_request(msg("Write a poem about autumn leaves falling in the park."))
        assert r.task_type == TaskType.creative

    def test_brainstorm(self):
        r = classify_request(msg("Brainstorm 10 original product ideas combining AI with household objects."))
        assert r.task_type == TaskType.creative

    # General
    def test_general_question(self):
        r = classify_request(msg("What time is it in Tokyo when it is 3pm in New York?"))
        assert r.task_type == TaskType.general


class TestComplexityScoring:
    def test_extraction_is_low_complexity(self):
        r = classify_request(msg("Summarize this in one sentence: The cat sat on the mat."))
        assert r.complexity <= 0.4

    def test_reasoning_is_high_complexity(self):
        r = classify_request(msg(
            "Prove step by step that there are infinitely many prime numbers. "
            "First, assume there are finitely many. Then derive a contradiction. "
            "Finally, conclude the proof."
        ))
        assert r.complexity >= 0.6

    def test_long_prompt_increases_complexity(self):
        short = classify_request(msg("Write a function."))
        long_text = "Write a function. " * 50
        long = classify_request(msg(long_text))
        assert long.complexity >= short.complexity


class TestFlags:
    def test_requires_tools_for_json(self):
        r = classify_request(msg("Extract the following and return as JSON: name, age, email."))
        assert r.requires_tools is True

    def test_factuality_risk_for_cite(self):
        r = classify_request(msg("Cite your sources and verify the accuracy of these facts."))
        assert r.factuality_risk is True

    def test_no_flags_by_default(self):
        r = classify_request(msg("Write a poem about the ocean."))
        assert r.requires_tools is False
        assert r.factuality_risk is False


class TestTokenEstimate:
    def test_estimate_is_positive(self):
        r = classify_request(msg("Hello world"))
        assert r.token_estimate > 0

    def test_longer_prompt_higher_estimate(self):
        short = classify_request(msg("Hi"))
        long = classify_request(msg("This is a much longer prompt with many more words " * 10))
        assert long.token_estimate > short.token_estimate
