"""Artilharia e assistencias.

O motor de eventos sabe quem fez o gol -- mas so na partida do usuario. As outras sao
resolvidas pelo motor rapido, que devolve apenas o placar. O que se protege aqui e que a
amostragem respeite esse placar: se a soma dos artilheiros nao fechar com a tabela, a lista
e' ficcao.
"""

from __future__ import annotations

import numpy as np
import pytest

from fm.carreira import Carreira
from fm.competition import Result
from fm.estatisticas import Estatisticas, registrar_resultado

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture
def carreira():
    return Carreira.nova(LIGAS, "Flamengo", seed=42)


def test_a_soma_dos_gols_bate_com_o_placar(carreira):
    c = carreira
    est = Estatisticas(temporada=c.temporada)
    rng = np.random.default_rng(7)
    ids = list(c.world.clubs)[:2]
    for _ in range(40):
        registrar_resultado(est, c.world, Result(ids[0], ids[1], 3, 2, 1), rng)
    total = sum(x.gols for x in est.por_jogador.values())
    assert total == 40 * 5, f"{total} gols atribuidos para 200 marcados"


def test_atacante_faz_mais_gol_que_zagueiro(carreira):
    c = carreira
    est = Estatisticas(temporada=c.temporada)
    rng = np.random.default_rng(7)
    ids = list(c.world.clubs)[:2]
    for _ in range(300):
        registrar_resultado(est, c.world, Result(ids[0], ids[1], 2, 1, 1), rng)
    por_posicao = {}
    for x in est.por_jogador.values():
        p = c.world.players[x.jogador]
        por_posicao[p.position] = por_posicao.get(p.position, 0) + x.gols
    assert por_posicao.get("FW", 0) > por_posicao.get("MF", 0) > por_posicao.get("DF", 0)
    assert por_posicao.get("GK", 0) < por_posicao.get("DF", 1)


def test_ninguem_assiste_o_proprio_gol(carreira):
    """Um gol com assistencia do proprio autor apareceria na lista e ninguem entenderia."""
    c = carreira
    est = Estatisticas(temporada=c.temporada)
    rng = np.random.default_rng(3)
    ids = list(c.world.clubs)[:2]
    for _ in range(200):
        registrar_resultado(est, c.world, Result(ids[0], ids[1], 4, 0, 1), rng)
    gols = sum(x.gols for x in est.por_jogador.values())
    assist = sum(x.assistencias for x in est.por_jogador.values())
    assert 0 < assist < gols, "toda bola tem passe, ou nenhuma tem"


def test_a_temporada_inteira_produz_artilharia(carreira):
    c = carreira
    while not c.acabou:
        c.avancar()
    artilheiros = c.estatisticas.artilheiros(c.world, 10)
    assert len(artilheiros) == 10
    assert artilheiros[0].gols >= 10
    # e o caderno zera na virada do ano, como na vida real
    temporada_velha = c.estatisticas.temporada
    c.virar_o_ano()
    assert c.estatisticas.temporada == temporada_velha + 1
    assert not c.estatisticas.por_jogador


def test_os_jogos_batem_com_o_calendario(carreira):
    """REGRESSAO: a partida do usuario era somada uma vez por DIVISAO, e o artilheiro
    terminava a temporada com noventa jogos."""
    c = carreira
    while not c.acabou:
        c.avancar()
    meus = [x for x in c.estatisticas.por_jogador.values()
            if c.world.players.get(x.jogador)
            and c.world.players[x.jogador].club_id == c.clube_id]
    copas = sum(len(a.resultados_do_ano) for a in c.copas.values())
    assert max(x.jogos for x in meus) <= c.total_de_rodadas + copas
    assert max(x.jogos for x in meus) >= c.total_de_rodadas * 0.8
