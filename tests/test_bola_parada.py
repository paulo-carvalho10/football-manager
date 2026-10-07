"""Bola parada (07/10/2026): falta direta e escanteio com efeito de verdade.

A media de gols nao muda (tests/test_eventos.py cobra isso); o que muda e quem faz e o
quanto o cobrador pesa."""

from __future__ import annotations

import numpy as np
import pytest

from fm.carreira import Carreira
from fm.central import detalhar
from fm.competition import Result
from fm.eventos import batedor_de, cruzamento, mira_na_falta, simular_partida
from fm.match import Style

ESTILO = Style(goals_base=1.22, home_adv=0.36)


@pytest.fixture(scope="module")
def mundo():
    c = Carreira.nova("brasil_real", "Santos", seed=42)
    return c.world, c.world.leagues[c.liga_id].club_ids, c.clube_id


def _jogos(world, ids, meu, n, seed, batedores=None):
    rng = np.random.default_rng(seed)
    rivais = [i for i in ids if i != meu]
    for _ in range(n):
        b = int(rng.choice(rivais))
        yield simular_partida(world, meu, b, [x.id for x in world.best_xi(meu)],
                              [x.id for x in world.best_xi(b)], rng, ESTILO,
                              batedores=batedores)


def _gols(p, clube, como):
    return [e for e in p.eventos
            if e.tipo == "gol" and e.clube == clube and e.texto.endswith(f"({como})")]


def test_sai_gol_de_falta_e_de_escanteio_na_medida(mundo):
    """Falta de vez em quando (perto de 4% dos gols), escanteio perto de 9%."""
    world, ids, meu = mundo
    jogos = list(_jogos(world, ids, meu, 1500, seed=3))
    total = sum(p.gols_casa + p.gols_fora for p in jogos)
    falta = sum(len(_gols(p, c, "falta")) for p in jogos for c in (p.casa, p.fora))
    escanteio = sum(len(_gols(p, c, "escanteio")) for p in jogos for c in (p.casa, p.fora))
    assert 0.02 < falta / total < 0.07
    assert 0.06 < escanteio / total < 0.13


def test_o_cobrador_de_falta_faz_diferenca(mundo):
    world, ids, meu = mundo
    xi = [p.id for p in world.best_xi(meu)]
    melhor = batedor_de(world, xi, None, mira_na_falta)
    pior = min((i for i in xi if world.players[i].position != "GK"),
               key=lambda i: mira_na_falta(world.players[i]))

    def de_falta(quem):
        return sum(len(_gols(p, meu, "falta"))
                   for p in _jogos(world, ids, meu, 1500, seed=4,
                                   batedores={meu: {"faltas": quem}}))
    assert de_falta(melhor) > 1.6 * de_falta(pior)


def test_quem_cobra_e_quem_o_treinador_escolheu(mundo):
    world, ids, meu = mundo
    xi = [p.id for p in world.best_xi(meu)]
    escolhido = next(i for i in xi if world.players[i].position == "DF")
    canto = next(i for i in xi if world.players[i].position == "FW")
    # quem sai machucado ou expulso nao cobra mais: ai cobra o melhor em campo
    faltas, escanteios = [], []
    for p in _jogos(world, ids, meu, 400, seed=5,
                    batedores={meu: {"faltas": escolhido, "escanteios": canto}}):
        for e in p.eventos:
            if e.clube != meu:
                continue
            if e.tipo in ("falta_defendida", "falta_fora") or e.texto.endswith("(falta)"):
                faltas.append(e.jogador == escolhido)
            if e.texto.endswith("(escanteio)"):
                escanteios.append(e.segundo == canto)   # o cobrador da a assistencia
                assert e.jogador != e.segundo
                assert world.players[e.jogador].position != "GK"
    assert len(faltas) > 100 and len(escanteios) > 20
    assert np.mean(faltas) > 0.9 and np.mean(escanteios) > 0.85


def test_a_carreira_manda_os_cobradores_da_tela(monkeypatch):
    import fm.carreira as mod
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=8)
    xi = [p.id for p in c.world.best_xi(c.clube_id)]
    c.funcoes = {"faltas": xi[3], "escanteios": xi[5]}
    visto = []
    original = mod.simular_partida
    monkeypatch.setattr(mod, "simular_partida",
                        lambda *a, **k: visto.append(k.get("batedores")) or original(*a, **k))
    while not visto:
        c.avancar()
    assert visto[0] == {c.clube_id: {"faltas": xi[3], "escanteios": xi[5]}}


def test_nos_outros_jogos_o_especialista_tambem_marca(mundo):
    """No motor rapido os gols ja sairam; a bola parada decide QUEM fez. O cobrador de
    escanteio da assistencias de bola parada, e o de falta marca a parte dele."""
    world, ids, meu = mundo
    rival = next(i for i in ids if i != meu)
    xi = [p.id for p in world.best_xi(meu)]
    canto = batedor_de(world, xi, None, cruzamento)
    rng = np.random.default_rng(6)
    gols = [x for _ in range(300)
            for x in detalhar(world, Result(meu, rival, 4, 0, 1), rng) if x.tipo == "gol"]
    assert len(gols) == 1200
    assist_do_canto = sum(1 for x in gols if x.segundo == canto)
    assert assist_do_canto / len(gols) > 0.07
