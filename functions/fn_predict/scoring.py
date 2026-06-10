"""Accuracy scoring: compare predictions against actual standings."""
from __future__ import annotations

from typing import Any


def compute_knockout_accuracy(
    knockout_predictions: list[dict[str, Any]],
    finished_knockout_fixtures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score knockout predictions: 1 point per correctly predicted match winner."""
    fixture_lookup: dict[int, dict[str, Any]] = {
        f["fixtureId"]: f
        for f in finished_knockout_fixtures
        if f.get("status") == "FT"
    }
    matches_result: list[dict[str, Any]] = []
    score = 0

    for stage_pred in knockout_predictions:
        for match in stage_pred.get("matches", []):
            fixture_id = match.get("fixtureId")
            actual = fixture_lookup.get(fixture_id)
            if actual is None:
                continue

            home_score = actual.get("homeScore") or 0
            away_score = actual.get("awayScore") or 0
            if home_score > away_score:
                actual_winner = actual.get("homeTeam")
            elif away_score > home_score:
                actual_winner = actual.get("awayTeam")
            else:
                actual_winner = None  # draw (shouldn't happen in knockout)

            predicted_winner = match.get("predictedWinner")
            correct = bool(actual_winner and predicted_winner == actual_winner)
            if correct:
                score += 1

            matches_result.append({
                "fixtureId": fixture_id,
                "stage": match.get("stage"),
                "correct": correct,
                "predictedWinner": predicted_winner,
                "actualWinner": actual_winner,
            })

    return {
        "knockoutScore": score,
        "knockoutTotal": len(matches_result),
        "knockoutMatches": matches_result,
    }


def _group_winner_runnerup(
    standings: list[dict[str, Any]], group: str
) -> tuple[str | None, str | None]:
    group_rows = [s for s in standings if s.get("group") == group]
    group_rows.sort(key=lambda s: s.get("rank", 99))
    if len(group_rows) < 2:
        return None, None
    return group_rows[0]["team"]["name"], group_rows[1]["team"]["name"]


def compute_accuracy(
    predictions: list[dict[str, Any]],
    standings: list[dict[str, Any]],
) -> dict[str, Any]:
    groups_result: list[dict[str, Any]] = []
    score = 0

    for pred in predictions:
        group = pred["group"]
        actual_winner, actual_runner_up = _group_winner_runnerup(standings, group)
        correct = (
            pred.get("winner") == actual_winner
            and pred.get("runnerUp") == actual_runner_up
        )
        if correct:
            score += 1
        groups_result.append({
            "group": group,
            "correct": correct,
            "predictedWinner": pred.get("winner"),
            "actualWinner": actual_winner,
            "predictedRunnerUp": pred.get("runnerUp"),
            "actualRunnerUp": actual_runner_up,
        })

    return {
        "score": score,
        "totalGroups": len(predictions),
        "groups": groups_result,
    }
