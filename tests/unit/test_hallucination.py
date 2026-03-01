"""Unit tests for hallucination detection — confidence scoring heuristics."""

import pytest
from router.plugins.hallucination import score_response


# ---------------------------------------------------------------------------
# High-confidence responses (score should be >= 0.8)
# ---------------------------------------------------------------------------

class TestHighConfidenceResponses:
    def test_clean_factual_statement(self):
        response = "The capital of France is Paris."
        assert score_response(response) >= 0.8

    def test_technical_explanation(self):
        response = (
            "Python's GIL (Global Interpreter Lock) prevents multiple threads "
            "from executing Python bytecodes simultaneously. This simplifies "
            "memory management at the cost of multi-core CPU utilisation."
        )
        assert score_response(response) >= 0.8

    def test_direct_code_response(self):
        response = (
            "def add(a, b):\n    return a + b\n\n"
            "This function takes two numbers and returns their sum."
        )
        assert score_response(response) >= 0.8

    def test_empty_response_scores_one(self):
        # Nothing to penalise → perfect confidence
        assert score_response("") == 1.0

    def test_single_word_response(self):
        assert score_response("Yes") == 1.0

    def test_long_factual_response(self):
        response = (
            "SQL stands for Structured Query Language. "
            "It is used to manage and manipulate relational databases. "
            "Common operations include SELECT, INSERT, UPDATE, and DELETE."
        )
        assert score_response(response) >= 0.8


# ---------------------------------------------------------------------------
# Hedging language lowers confidence
# ---------------------------------------------------------------------------

class TestHedgingPenalties:
    def test_single_i_think(self):
        score = score_response("I think the answer is 42.")
        assert score < 1.0
        assert score >= 0.9  # only one small penalty

    def test_multiple_hedges_reduce_score(self):
        response = (
            "I think this might be correct, but I'm not sure. "
            "Perhaps you could verify, maybe with another source."
        )
        low = score_response(response)
        high = score_response("The answer is 42.")
        assert low < high

    def test_probably_reduces_score(self):
        assert score_response("This probably works.") < 1.0

    def test_maybe_reduces_score(self):
        assert score_response("Maybe try restarting the server.") < 1.0

    def test_i_believe_reduces_score(self):
        assert score_response("I believe the API changed in version 3.") < 1.0

    def test_seems_reduces_score(self):
        assert score_response("It seems like the bug is in the parser.") < 1.0

    def test_approximately_reduces_score(self):
        assert score_response("The value is approximately 3.14.") < 1.0

    def test_if_recall_correctly_reduces_score(self):
        assert score_response("If I recall correctly, it was 2019.") < 1.0

    def test_hedging_cap_at_040(self):
        # 8+ hedges should not push score below 0.6 from hedging alone
        many_hedges = " ".join(["I think maybe perhaps probably"] * 10)
        score = score_response(many_hedges)
        assert score >= 0.6   # cap at -0.40 means floor at 0.60

    def test_as_far_as_i_know(self):
        assert score_response("As far as I know, it was deprecated.") < 1.0

    def test_not_entirely_sure(self):
        assert score_response("I'm not entirely sure about this.") < 1.0


# ---------------------------------------------------------------------------
# Contradiction signals lower confidence significantly
# ---------------------------------------------------------------------------

class TestContradictionPenalties:
    def test_wait_actually_reduces_score(self):
        response = "The function returns True. Wait, actually it returns False."
        assert score_response(response) < 0.9

    def test_correction_prefix_reduces_score(self):
        assert score_response("Correction: my earlier answer was wrong.") < 0.9

    def test_let_me_correct_reduces_score(self):
        assert score_response("Let me correct that — the value should be 0.") < 0.9

    def test_made_a_mistake_reduces_score(self):
        assert score_response("I made a mistake in the previous step.") < 0.9

    def test_multiple_contradictions_heavy_penalty(self):
        response = (
            "The method returns a string. "
            "Wait, actually it returns an int. "
            "Let me correct that — it returns a bool."
        )
        score = score_response(response)
        assert score < 0.75


# ---------------------------------------------------------------------------
# Unsupported claim signals
# ---------------------------------------------------------------------------

class TestUnsupportedClaimPenalties:
    def test_obviously_reduces_score(self):
        assert score_response("Obviously, this is the best approach.") < 1.0

    def test_clearly_reduces_score(self):
        assert score_response("Clearly, Python is the best language.") < 1.0

    def test_studies_show_reduces_score(self):
        assert score_response("Studies show this method is superior.") < 1.0

    def test_experts_agree_reduces_score(self):
        assert score_response("Experts agree that TDD is always better.") < 1.0

    def test_guaranteed_to_reduces_score(self):
        assert score_response("This is guaranteed to fix the issue.") < 1.0

    def test_never_fails_reduces_score(self):
        assert score_response("This approach never fails.") < 1.0

    def test_always_works_reduces_score(self):
        assert score_response("The algorithm always works correctly.") < 1.0


# ---------------------------------------------------------------------------
# Combined penalties
# ---------------------------------------------------------------------------

class TestCombinedPenalties:
    def test_low_confidence_hedging_plus_unsupported(self):
        response = (
            "I think maybe this is clearly the best approach. "
            "Obviously everyone knows this is probably correct."
        )
        assert score_response(response) < 0.65

    def test_score_never_below_zero(self):
        worst_case = (
            "I'm not sure maybe probably perhaps I think "
            "Wait, actually let me correct that mistake. "
            "Obviously clearly everyone knows studies show experts agree "
            "guaranteed never fails always works without a doubt."
        )
        assert score_response(worst_case) >= 0.0

    def test_score_never_above_one(self):
        assert score_response("Paris is the capital of France.") <= 1.0

    def test_return_value_is_float(self):
        result = score_response("Some response text.")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_case_insensitive_matching(self):
        lower = score_response("i think this is right")
        upper = score_response("I THINK THIS IS RIGHT")
        mixed = score_response("I Think This Is Right")
        assert lower == upper == mixed

    def test_multiline_response(self):
        response = "Line 1 is correct.\nI think line 2 might be wrong.\nLine 3 is fine."
        score = score_response(response)
        assert score < 1.0
        assert score >= 0.9

    def test_partial_word_not_matched(self):
        # "maybe" should match but "unmaybelike" should not cause double-counting
        response = "Maybe this works."
        score1 = score_response(response)
        score2 = score_response("This works.")
        assert score1 < score2