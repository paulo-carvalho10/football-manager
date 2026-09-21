"""Classificacao. Critericos de desempate vem da competicao, nao do codigo."""

from __future__ import annotations

from dataclasses import dataclass

from fm.competition import Result

DEFAULT_TIEBREAK = ("points", "wins", "goal_diff", "goals_for")


@dataclass(slots=True)
class Row:
    club_id: int
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def points(self) -> int:
        return self.wins * 3 + self.draws

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against


def build_table(
    club_ids: list[int], results: list[Result],
    tiebreak: tuple[str, ...] = DEFAULT_TIEBREAK,
) -> list[Row]:
    rows = {cid: Row(cid) for cid in club_ids}
    for r in results:
        h, a = rows[r.home], rows[r.away]
        h.played += 1
        a.played += 1
        h.goals_for += r.goals_home
        h.goals_against += r.goals_away
        a.goals_for += r.goals_away
        a.goals_against += r.goals_home
        if r.goals_home > r.goals_away:
            h.wins += 1
            a.losses += 1
        elif r.goals_home < r.goals_away:
            a.wins += 1
            h.losses += 1
        else:
            h.draws += 1
            a.draws += 1
    return sorted(rows.values(), key=lambda r: tuple(-getattr(r, k) for k in tiebreak))
