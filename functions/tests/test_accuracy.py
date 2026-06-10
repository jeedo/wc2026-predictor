"""Tests for accuracy scoring — task 13."""
import pytest

from fn_predict.scoring import compute_accuracy, _group_winner_runnerup, compute_knockout_accuracy


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


# ---------------------------------------------------------------------------
# compute_knockout_accuracy (issue #32)
# ---------------------------------------------------------------------------

def _knockout_pred(fixture_id: int, stage: str, predicted_winner: str) -> dict:
    return {
        "stage": stage,
        "matches": [
            {
                "fixtureId": fixture_id,
                "stage": stage,
                "homeTeam": "TeamA",
                "awayTeam": "TeamB",
                "predictedWinner": predicted_winner,
                "predictedHomeScore": 2,
                "predictedAwayScore": 1,
                "confidence": "high",
            }
        ],
    }


def _knockout_fixture(fixture_id: int, stage: str, home: str, away: str, home_score: int, away_score: int) -> dict:
    return {
        "fixtureId": fixture_id,
        "stage": stage,
        "homeTeam": home,
        "awayTeam": away,
        "homeScore": home_score,
        "awayScore": away_score,
        "status": "FT",
    }


def test_compute_knockout_accuracy_correct_prediction():
    """Correct winner prediction scores 1 point."""
    knockout_preds = [_knockout_pred(537417, "LAST_32", "Germany")]
    # Germany wins 2-1
    knockout_preds[0]["matches"][0]["homeTeam"] = "Germany"
    knockout_preds[0]["matches"][0]["awayTeam"] = "Mexico"
    finished = [_knockout_fixture(537417, "LAST_32", "Germany", "Mexico", 2, 1)]

    result = compute_knockout_accuracy(knockout_preds, finished)
    assert result["knockoutScore"] == 1
    assert result["knockoutTotal"] == 1
    assert result["knockoutMatches"][0]["correct"] is True
    assert result["knockoutMatches"][0]["actualWinner"] == "Germany"


def test_compute_knockout_accuracy_wrong_prediction():
    """Incorrect winner prediction scores 0."""
    knockout_preds = [_knockout_pred(537417, "LAST_32", "Mexico")]
    knockout_preds[0]["matches"][0]["homeTeam"] = "Germany"
    knockout_preds[0]["matches"][0]["awayTeam"] = "Mexico"
    finished = [_knockout_fixture(537417, "LAST_32", "Germany", "Mexico", 2, 0)]

    result = compute_knockout_accuracy(knockout_preds, finished)
    assert result["knockoutScore"] == 0
    assert result["knockoutMatches"][0]["correct"] is False
    assert result["knockoutMatches"][0]["actualWinner"] == "Germany"
    assert result["knockoutMatches"][0]["predictedWinner"] == "Mexico"


def test_compute_knockout_accuracy_skips_unfinished():
    """Unfinished knockout fixtures are not counted."""
    knockout_preds = [_knockout_pred(537417, "LAST_32", "Germany")]
    knockout_preds[0]["matches"][0]["homeTeam"] = "Germany"
    knockout_preds[0]["matches"][0]["awayTeam"] = "Mexico"
    # Not finished
    unfinished = [
        {"fixtureId": 537417, "homeTeam": "Germany", "awayTeam": "Mexico",
         "homeScore": None, "awayScore": None, "status": "NS"}
    ]

    result = compute_knockout_accuracy(knockout_preds, unfinished)
    assert result["knockoutScore"] == 0
    assert result["knockoutTotal"] == 0


def test_compute_knockout_accuracy_multiple_stages():
    """Multiple knockout stages are all evaluated."""
    knockout_preds = [
        _knockout_pred(1, "LAST_32", "Germany"),
        _knockout_pred(2, "LAST_16", "Brazil"),
    ]
    knockout_preds[0]["matches"][0]["homeTeam"] = "Germany"
    knockout_preds[0]["matches"][0]["awayTeam"] = "Mexico"
    knockout_preds[1]["matches"][0]["homeTeam"] = "Brazil"
    knockout_preds[1]["matches"][0]["awayTeam"] = "USA"
    finished = [
        _knockout_fixture(1, "LAST_32", "Germany", "Mexico", 2, 0),
        _knockout_fixture(2, "LAST_16", "USA", "Brazil", 1, 0),
    ]

    result = compute_knockout_accuracy(knockout_preds, finished)
    assert result["knockoutScore"] == 1   # Germany correct, Brazil incorrect
    assert result["knockoutTotal"] == 2


def test_compute_knockout_accuracy_empty_input():
    """Empty predictions return zero score."""
    result = compute_knockout_accuracy([], [])
    assert result["knockoutScore"] == 0
    assert result["knockoutTotal"] == 0
    assert result["knockoutMatches"] == []
