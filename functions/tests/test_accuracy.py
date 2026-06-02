"""Tests for accuracy scoring — task 13."""
import pytest

from fn_predict.scoring import compute_accuracy, _group_winner_runnerup


# ---------------------------------------------------------------------------
# _group_winner_runnerup
# ---------------------------------------------------------------------------

def _standing(group: str, rank: int, name: str) -> dict:
    return {"group": group, "rank": rank, "team": {"name": name}, "points": (3 - rank) * 3}


def test_group_winner_runnerup_returns_top_two():
    standings = [
        _standing("A", 2, "Mexico"),
        _standing("A", 1, "Germany"),
        _standing("A", 3, "USA"),
        _standing("A", 4, "Poland"),
    ]
    winner, runner_up = _group_winner_runnerup(standings, "A")
    assert winner == "Germany"
    assert runner_up == "Mexico"


def test_group_winner_runnerup_missing_group_returns_none():
    result = _group_winner_runnerup([], "Z")
    assert result == (None, None)


# ---------------------------------------------------------------------------
# compute_accuracy — strict scoring
# ---------------------------------------------------------------------------

PREDICTIONS = [
    {"group": "A", "winner": "Germany", "runnerUp": "Mexico"},
    {"group": "B", "winner": "Brazil", "runnerUp": "Argentina"},
    {"group": "C", "winner": "France", "runnerUp": "England"},
]

STANDINGS = [
    _standing("A", 1, "Germany"),
    _standing("A", 2, "Mexico"),
    _standing("B", 1, "Brazil"),
    _standing("B", 2, "Argentina"),
    _standing("C", 1, "France"),
    _standing("C", 2, "Spain"),   # runner-up differs
]


def test_compute_accuracy_full_match():
    predictions_correct = [
        {"group": "A", "winner": "Germany", "runnerUp": "Mexico"},
        {"group": "B", "winner": "Brazil", "runnerUp": "Argentina"},
    ]
    standings = [
        _standing("A", 1, "Germany"), _standing("A", 2, "Mexico"),
        _standing("B", 1, "Brazil"), _standing("B", 2, "Argentina"),
    ]
    result = compute_accuracy(predictions_correct, standings)
    assert result["score"] == 2
    assert result["totalGroups"] == 2
    assert all(g["correct"] for g in result["groups"])


def test_compute_accuracy_partial_runnerup_miss():
    """If runner-up doesn't match, group scores 0."""
    result = compute_accuracy(PREDICTIONS, STANDINGS)
    group_c = next(g for g in result["groups"] if g["group"] == "C")
    assert group_c["correct"] is False
    assert result["score"] == 2  # A and B correct, C incorrect


def test_compute_accuracy_max_score():
    predictions = [{"group": chr(65 + i), "winner": f"W{i}", "runnerUp": f"R{i}"} for i in range(12)]
    standings = []
    for i in range(12):
        standings.append(_standing(chr(65 + i), 1, f"W{i}"))
        standings.append(_standing(chr(65 + i), 2, f"R{i}"))
    result = compute_accuracy(predictions, standings)
    assert result["score"] == 12


def test_compute_accuracy_zero_score():
    predictions = [{"group": "A", "winner": "Germany", "runnerUp": "Mexico"}]
    standings = [_standing("A", 1, "Brazil"), _standing("A", 2, "Argentina")]
    result = compute_accuracy(predictions, standings)
    assert result["score"] == 0
    assert result["groups"][0]["correct"] is False
