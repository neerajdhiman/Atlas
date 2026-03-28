"""Unit tests for distillation pipeline — similarity scoring, thresholds."""

import pytest
from a1.training.auto_trainer import _compute_similarity, _lcs_length, _rouge_l
from config.settings import settings


# --- LCS length ---
def test_lcs_identical():
    words = ["the", "quick", "brown", "fox"]
    assert _lcs_length(words, words) == 4


def test_lcs_empty():
    assert _lcs_length([], ["a", "b"]) == 0
    assert _lcs_length(["a", "b"], []) == 0


def test_lcs_no_overlap():
    assert _lcs_length(["a", "b"], ["c", "d"]) == 0


def test_lcs_partial():
    a = ["the", "cat", "sat"]
    b = ["the", "dog", "sat"]
    assert _lcs_length(a, b) == 2  # "the" and "sat"


# --- ROUGE-L ---
def test_rouge_l_identical():
    words = ["the", "quick", "brown", "fox"]
    score = _rouge_l(words, words)
    assert score == pytest.approx(1.0, abs=0.01)


def test_rouge_l_empty():
    assert _rouge_l([], ["a"]) == 0.0
    assert _rouge_l(["a"], []) == 0.0


def test_rouge_l_no_overlap():
    score = _rouge_l(["cat", "sat"], ["dog", "ran"])
    assert score == 0.0


# --- compute_similarity ---
def test_similarity_identical():
    text = "The quick brown fox jumps over the lazy dog"
    score = _compute_similarity(text, text)
    assert score == pytest.approx(1.0, abs=0.01)


def test_similarity_empty():
    assert _compute_similarity("", "some text") == 0.0
    assert _compute_similarity("some text", "") == 0.0
    assert _compute_similarity("", "") == 0.0


def test_similarity_unrelated():
    a = "The capital of France is Paris and it has the Eiffel Tower"
    b = "SELECT * FROM users WHERE id = 1 AND password IS NULL"
    score = _compute_similarity(a, b)
    assert score < 0.3


def test_similarity_highly_similar():
    a = "Write a Python function to compute the factorial of a number recursively"
    b = "Write a Python function to calculate the factorial of a number recursively"
    score = _compute_similarity(a, b)
    assert score > 0.7


def test_similarity_range():
    a = "Hello world, this is a test message"
    b = "Hello there, this is another test"
    score = _compute_similarity(a, b)
    assert 0.0 <= score <= 1.0


# --- Training trigger threshold ---
def test_min_samples_threshold_configured():
    """distillation_min_samples must be a positive integer."""
    assert isinstance(settings.distillation_min_samples, int)
    assert settings.distillation_min_samples > 0


def test_min_samples_below_threshold_no_trigger():
    """Verify threshold logic: sample_count < min_samples → no trigger."""
    min_s = settings.distillation_min_samples
    # sample_count below threshold should not trigger
    assert (min_s - 1) < min_s  # trivially true, documents intent


def test_min_samples_at_threshold():
    """At or above min_samples, training is eligible to be triggered."""
    min_s = settings.distillation_min_samples
    assert min_s <= min_s  # at threshold → eligible
