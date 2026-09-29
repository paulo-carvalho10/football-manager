"""Penalti: frequencia e conversao do futebol real, o batedor escolhido e o replay."""

from __future__ import annotations

import numpy as np
import pytest

from fm.carreira import Carreira
from fm.eventos import simular_partida
from fm.match import Style

ESTILO = Style(goals_base=1.22, home_adv=0.36)


@pytest.fixture(scope="module")
def mundo():
    c = Carreira.nova("brasil_real", "Santos", seed=42)
    return c.world, c.world.leagues[c.liga_id].club_ids


def _jogos(world, ids, n, **kw):
    rng = np.random.default_rng(3)
    for _ in range(n):
        a, b = (int(x) for x in rng.choice(ids, 2, replace=False))
        yield simular_partida(world, a, b, [x.id for x in world.best_xi(a)],
                              [x.id for x in world.best_xi(b)], rng, ESTILO, **kw)


def test_penaltis_por_jogo_e_conversao_do_futebol_real(mundo):
    world, ids = mundo
    marcados = cobrados = 0
    n = 600
    for p in _jogos(world, ids, n):
        pens = [i for i, e in enumerate(p.eventos) if e.tipo == "penalti"]
        cobrados += len(pens)
        marcados += sum(1 for i in pens if p.eventos[i + 1].tipo == "gol")
        # o gol de penalti conta no placar como qualquer outro
        assert sum(e.tipo == "gol" for e in p.eventos) == p.gols_casa + p.gols_fora
    assert 0.18 < cobrados / n < 0.40
    assert 0.62 < marcados / cobrados < 0.88


def test_o_batedor_escolhido_e_quem_bate(mundo):
    world, ids = mundo
    pedidos = []

    def decidir(partida, minuto, clube):
        em_campo = partida.em_campo_casa if clube == partida.casa else partida.em_campo_fora
        escolha = sorted(em_campo)[0]
        pedidos.append(escolha)
        return escolha

    batedores = []
    for p in _jogos(world, ids, 200, penaltis=decidir):
        batedores += [e.jogador for e in p.eventos if e.tipo == "penalti"]
    assert batedores and batedores == pedidos


def test_a_escolha_do_batedor_volta_igual_no_save(tmp_path, monkeypatch):
    monkeypatch.setattr("fm.carreira.SAVES_DIR", tmp_path)
    c = Carreira.nova("brasil_real", "Santos", seed=11)
    escolhas = []

    def goleiro_bate(partida, minuto, clube):
        # o pior batedor possivel, para o replay nao acertar por acaso
        if clube != c.clube_id:
            return None
        em_campo = partida.em_campo_casa if clube == partida.casa else partida.em_campo_fora
        gk = next(i for i in em_campo if c.world.players[i].position == "GK")
        escolhas.append(gk)
        return gk

    # joga ate sair um penalti a favor, e mais uma data para o replay ter o que seguir
    for _ in range(45):
        if c.acabou:
            break
        c.avancar(penaltis=goleiro_bate)
        if escolhas:
            c.avancar(penaltis=goleiro_bate)
            break
    if not escolhas:
        pytest.skip("nenhum penalti a favor nestas datas")
    c.salvar("pen")
    d = Carreira.carregar("pen")
    assert d.na_partida == c.na_partida
    assert any("penaltis" in v for v in d.na_partida.values())
    assert d.tabela() == c.tabela()
