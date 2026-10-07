"""Execucao de uma temporada de liga.

Avanca RODADA POR RODADA, nao a temporada de uma vez. Essa escolha custa nada em
performance (cada rodada e' um lote vetorizado) e e' o que vai permitir, sem reescrever
nada, parar na rodada do usuario para simular a partida dele em detalhe.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from fm.competition import Fixture, Result, play_fixtures, round_robin
from fm.match import Mentality, Style, effective_rating
from fm.model import World
from fm.table import Row, build_table

CONDITION_COST = 12          # o que um jogo tira de quem joga os 90
CONDITION_RECOVERY = 9       # (mantido: outros modulos ainda usam)
# Recuperacao PROPORCIONAL ao quanto falta para 100. E o que cria EQUILIBRIO: quem joga
# toda rodada estabiliza perto de 82%, nao desaba ate o piso. Com recuperacao fixa, um
# titular perdia 3 por rodada sem parar e terminava a temporada no chao -- o que nunca
# acontece com jogador de verdade.
TAXA_DE_RECUPERACAO = 0.65


@dataclass(slots=True)
class SeasonReport:
    league_id: str
    table: list[Row]
    results: list[Result]


def _ratings(world: World, club_ids: list[int]) -> dict[int, float]:
    """Overall efetivo de cada clube nesta rodada: base do onze menos desgaste."""
    return {
        cid: float(effective_rating(world.team_rating(cid),
                                    fatigue=world.fatigue_penalty(cid)))
        for cid in club_ids
    }


def _apply_condition(world: World, fixtures: list[Fixture]) -> None:
    """Todo mundo recupera; quem jogou paga o custo por cima."""
    played = {f.home for f in fixtures} | {f.away for f in fixtures}
    for club_id in world.clubs:
        xi = {p.id for p in world.best_xi(club_id)} if club_id in played else set()
        for p in world.squad(club_id):
            recupera = TAXA_DE_RECUPERACAO * (100 - p.condition)
            delta = recupera - (CONDITION_COST if p.id in xi else 0)
            p.condition = int(min(max(p.condition + delta, 25), 100))


def play_league_season(
    world: World, league_id: str, style: Style, rng: np.random.Generator,
    *, legs: int = 2, mentality: Mentality = Mentality.NORMAL,
    track_condition: bool = True,
) -> SeasonReport:
    league = world.leagues[league_id]
    fixtures = round_robin(league.club_ids, legs=legs)
    by_matchday: dict[int, list[Fixture]] = defaultdict(list)
    for f in fixtures:
        by_matchday[f.matchday].append(f)

    results: list[Result] = []
    for matchday in sorted(by_matchday):
        rodada = by_matchday[matchday]
        ratings = _ratings(world, league.club_ids)
        results.extend(play_fixtures(rodada, ratings, rng, style, mentality))
        if track_condition:
            _apply_condition(world, rodada)

    return SeasonReport(league_id, build_table(league.club_ids, results), results)
