"""Competicoes de copa: entrada escalonada, rodadas e regras proprias de fase."""

from __future__ import annotations

import numpy as np
import pytest

from fm.competition import knockout_tie
from fm.config import load_league
from fm.generate import build_world
from fm.match import Mentality, Style
from fm.torneio import (
    _fase_mata_mata,
    carregar,
    disponiveis,
    resolver_entradas,
    simular,
)


@pytest.fixture(scope="module")
def mundo():
    ligas = [load_league(n) for n in ("brasil_real", "brasil_b_real")]
    world, _ = build_world(ligas, seed=11)
    tabelas = {}
    for cfg in ligas:
        liga = world.leagues[cfg["id"]]
        ordem = sorted(liga.club_ids,
                       key=lambda c: -world.clubs[c].designed_strength)
        tabelas[cfg["id"]] = ordem
        tabelas[liga.codigo] = ordem
    return world, tabelas


def test_todos_os_torneios_do_disco_carregam():
    assert disponiveis()
    for nome in disponiveis():
        t = carregar(nome)
        assert t.fases or t.qualificados_de
        assert t.style.goals_base > 0


def test_entrada_por_faixa_de_classificacao(mundo):
    world, tabelas = mundo
    entram = resolver_entradas(world, [{"liga": "BRA1", "de": 13, "ate": 20}], tabelas)
    assert len(entram) == 8
    assert entram == tabelas["BRA1"][12:20]


def test_quem_entra_depois_nao_joga_as_fases_anteriores(mundo):
    """A PROPRIEDADE do item: clube declarado na 3a fase nao pode cair na 1a."""
    world, tabelas = mundo
    t = carregar("copa_do_brasil")
    cedo = set(resolver_entradas(world, t.fases[0].get("entram", []), tabelas))
    tarde = set(resolver_entradas(world, t.fases[-1].get("entram", []), tabelas))
    assert cedo and tarde
    assert not (cedo & tarde), "clube entrando em duas fases diferentes"
    # os que entram tarde sao os mais fortes: e o ponto de entrar tarde
    forca = lambda ids: np.mean([world.clubs[c].designed_strength for c in ids])  # noqa: E731
    assert forca(tarde) > forca(cedo)


def test_rodadas_limita_a_fase(mundo):
    """Sem isso, uma fase rodava ate sobrar um e ninguem podia entrar no meio."""
    world, _ = mundo
    clubes = list(world.clubs)[:16]
    rng = np.random.default_rng(3)
    uma = _fase_mata_mata(world, clubes, {"rodadas": 1, "maos": 2}, rng, Style(),
                          Mentality.CUP)
    assert len(uma) == 8
    todas = _fase_mata_mata(world, clubes, {"maos": 2}, np.random.default_rng(3), Style(),
                            Mentality.CUP)
    assert len(todas) == 1


def test_bye_e_sorteado_e_nao_premia_o_mais_forte(mundo):
    """Dar o bye ao mais forte inflava o favorito de 12,6% para 40,8% dos titulos."""
    world, tabelas = mundo
    clubes = tabelas["BRA1"][:9]          # numero impar: alguem passa sem jogar
    forte = clubes[0]
    sobreviveu = sum(
        forte in _fase_mata_mata(world, list(clubes), {"rodadas": 1, "maos": 1},
                                 np.random.default_rng(seed), Style(), Mentality.CUP)
        for seed in range(60))
    assert sobreviveu < 58, "o mais forte quase sempre passou: bye nao esta sorteado"


def test_visitante_avanca_no_empate():
    """Regra das duas primeiras fases da Copa do Brasil, de nenhum outro torneio."""
    n = 40_000
    ratings = {1: 70.0, 2: 70.0}
    rng = np.random.default_rng(4)
    com = knockout_tie([1] * n, [2] * n, ratings, rng, Style(), Mentality.CUP, legs=1,
                       empate_favorece_visitante=True)
    sem = knockout_tie([1] * n, [2] * n, ratings, np.random.default_rng(4), Style(),
                       Mentality.CUP, legs=1)
    # `home_first` = 1 manda na unica partida em `sem`; com a regra, o empate vai para 1
    assert np.mean(com == 1) > np.mean(sem == 1) + 0.05


def test_copa_do_brasil_roda_de_ponta_a_ponta(mundo):
    world, tabelas = mundo
    t = carregar("copa_do_brasil")
    campeao = simular(world, t, np.random.default_rng(9), elenco=[], tabelas=tabelas)
    assert len(campeao) == 1
    assert campeao[0] in world.clubs
