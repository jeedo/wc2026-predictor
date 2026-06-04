"""Group assignment derivation from World Cup fixture data."""
from typing import Any


def derive_groups_from_fixtures(fixtures: list[dict[str, Any]]) -> dict[str, str]:
    """Derive group assignments from matchday 1 fixtures.

    Teams that play each other in matchday 1 belong to the same group.
    Returns dict mapping team name -> group letter (A-L).
    """
    # Get all matchday 1 fixtures
    md1_fixtures = [f for f in fixtures if f.get("matchday") == 1]

    team_to_group: dict[str, str] = {}
    group_count = 0

    for fixture in md1_fixtures:
        home = fixture.get("homeTeam", "")
        away = fixture.get("awayTeam", "")

        if not home or not away:
            continue

        home_group = team_to_group.get(home)
        away_group = team_to_group.get(away)

        if home_group and away_group:
            # Both already assigned - skip
            continue
        elif home_group:
            # Assign away to home's group
            team_to_group[away] = home_group
        elif away_group:
            # Assign home to away's group
            team_to_group[home] = away_group
        else:
            # Both unassigned - create new group
            group_letter = chr(ord('A') + group_count)
            team_to_group[home] = group_letter
            team_to_group[away] = group_letter
            group_count += 1

    return team_to_group
