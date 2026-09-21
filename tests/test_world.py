"""Determinismo, competicoes e licenciamento."""

from __future__ import annotations

import re

import numpy as np
import pytest

from fm.competition import round_robin
from fm.config import available, load_league, mentality_of, style_of
from fm.generate import build_world, strength_profile
from fm.names import CLUB_PATTERNS, CLUB_ROOTS, REAL_CLUBS_BLOCKLIST
from fm.rng import Streams
from fm.season import play_league_season


def _temporada(seed, liga="brasil"):
    cfg = load_league(liga)
    world, streams = build_world([cfg], seed=seed)
    rng = streams.get("match", world.season_year, cfg["id"])
    rep = play_league_season(world, cfg["id"], style_of(cfg), rng)
    return [(world.clubs[r.club_id].name, r.points) for r in rep.table]


def test_mesma_seed_mesmo_mundo():
    assert _temporada(99) == _temporada(99)


def test_seed_diferente_mundo_diferente():
    assert _temporada(99) != _temporada(100)


def test_fluxos_nomeados_sao_independentes():
    """Adicionar uma feature nova nao pode deslocar as partidas ja simuladas."""
    s = Streams(7)
    partidas = s.get("match", 2027).integers(0, 10_000, 5).tolist()
    s.get("lesoes", 2027).integers(0, 10_000, 500)     # feature nova consumindo numeros
    assert Streams(7).get("match", 2027).integers(0, 10_000, 5).tolist() == partidas


def test_pontos_corridos_e_valido():
    ids = list(range(1, 21))
    fixtures = round_robin(ids, legs=2)
    assert len(fixtures) == 380
    assert max(f.matchday for f in fixtures) == 38
    for cid in ids:
        assert sum(1 for f in fixtures if f.home == cid) == 19
        assert sum(1 for f in fixtures if f.away == cid) == 19
    pares = {(f.home, f.away) for f in fixtures}
    assert len(pares) == 380       # cada par exatamente uma vez em cada mando


def test_pontos_corridos_exige_numero_par():
    with pytest.raises(ValueError):
        round_robin([1, 2, 3])


def test_soma_de_pontos_fecha():
    """Toda partida distribui 3 pontos (vitoria) ou 2 (empate). Guarda contra bug de tabela."""
    cfg = load_league("brasil")
    world, streams = build_world([cfg], seed=5)
    rng = streams.get("match", 1, "x")
    rep = play_league_season(world, cfg["id"], style_of(cfg), rng)
    empates = sum(1 for r in rep.results if r.goals_home == r.goals_away)
    esperado = 3 * (len(rep.results) - empates) + 2 * empates
    assert sum(r.points for r in rep.table) == esperado


def test_elenco_bate_com_a_forca_desenhada():
    """A geracao tem que entregar o clube que o arquivo da liga pediu, com tolerancia baixa."""
    for liga in ("brasil", "espanha"):
        cfg = load_league(liga)
        world, _ = build_world([cfg], seed=11)
        for club in world.clubs.values():
            assert abs(world.team_rating(club.id) - club.designed_strength) < 2.5


def test_carater_da_liga_vem_do_dado():
    """Brasil tem que sair mais equilibrado que Espanha SEM mudar constante do motor."""
    from fm.calibration import measure
    bra, esp = load_league("brasil"), load_league("espanha")
    m_bra = measure(strength_profile(bra, 20), style=style_of(bra), seasons=250, seed=3)
    m_esp = measure(strength_profile(esp, 20), style=style_of(esp), seasons=250, seed=3)
    assert m_bra["pontos_do_campeao"] < m_esp["pontos_do_campeao"] - 5
    assert m_bra["empate_pct"] > m_esp["empate_pct"]
    assert m_bra["melhor_elenco_campeao_pct"] < m_esp["melhor_elenco_campeao_pct"]


def test_nenhum_clube_gerado_colide_com_clube_real():
    """Guarda de licenciamento: o motor nunca depende de ativo oficial."""
    gerados = set()
    for pais, roots in CLUB_ROOTS.items():
        for r in roots:
            for pat in CLUB_PATTERNS[pais]:
                gerados.add(pat.format(r=r).lower())
    assert not (gerados & REAL_CLUBS_BLOCKLIST)
    # nem como palavra inteira dentro do nome (substring simples daria falso positivo:
    # "sport" aparece dentro de "esporte")
    for nome in gerados:
        for real in REAL_CLUBS_BLOCKLIST:
            assert not re.search(rf"{re.escape(real)}", nome), f"{nome} contem {real}"


def test_todas_as_ligas_do_disco_carregam():
    for nome in available():
        cfg = load_league(nome)
        assert strength_profile(cfg, int(cfg["clubes"]))
        assert style_of(cfg).goals_base > 0
        assert 0.0 <= mentality_of(cfg).compression < 1.0


def test_desgaste_aparece_ao_longo_da_temporada():
    cfg = load_league("brasil")
    world, streams = build_world([cfg], seed=21)
    antes = np.mean([p.condition for p in world.players.values()])
    play_league_season(world, cfg["id"], style_of(cfg),
                       streams.get("match", 1, "y"))
    depois = np.mean([p.condition for p in world.players.values()])
    assert depois < antes
