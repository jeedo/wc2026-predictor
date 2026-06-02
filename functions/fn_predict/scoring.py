"""Accuracy scoring: compare predictions against actual standings."""
from __future__ import annotations

from typing import Any


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
