"""Motor detalhado: calibracao contra o rapido e o efeito da substituicao."""

from __future__ import annotations

import numpy as np
import pytest

from fm.carreira import Carreira
from fm.eventos import BLOCOS, Partida, simular_partida
from fm.match import Style, simulate

ESTILO = Style(goals_base=1.22, home_adv=0.36)


@pytest.fixture(scope="module")
def mundo():
    c = Carreira.nova("brasil_real", "Santos", seed=42)
    return c.world, c.world.leagues[c.liga_id].club_ids, c.clube_id


def _rodar_eventos(world, ids, n, seed=1):
    rng = np.random.default_rng(seed)
    casa, fora = [], []
    for _ in range(n):
        a, b = rng.choice(ids, 2, replace=False)
        p = simular_partida(world, int(a), int(b),
                            [x.id for x in world.best_xi(int(a))],
                            [x.id for x in world.best_xi(int(b))], rng, ESTILO)
        casa.append(p.gols_casa)
        fora.append(p.gols_fora)
    return np.array(casa), np.array(fora)


def test_eventos_produzem_a_mesma_distribuicao_do_rapido(mundo):
    """REGRA INEGOCIAVEL. Se a partida do usuario tiver media de gols diferente do resto
    do mundo, a tabela fica torta e o jogador sente sem saber por que."""
    world, ids, _ = mundo
    n = 3000
    ev_c, ev_f = _rodar_eventos(world, ids, n)

    rng = np.random.default_rng(1)
    ra, rb = [], []
    for _ in range(n):
        a, b = rng.choice(ids, 2, replace=False)
        ra.append(world.team_rating(int(a)))
        rb.append(world.team_rating(int(b)))
    rp_c, rp_f = simulate(np.array(ra), np.array(rb), rng, ESTILO)

    assert abs((ev_c + ev_f).mean() - (rp_c + rp_f).mean()) < 0.12
    for corte in (lambda m: m > 0, lambda m: m == 0, lambda m: m < 0):
        a = np.mean(corte(ev_c - ev_f))
        b = np.mean(corte(rp_c - rp_f))
        assert abs(a - b) < 0.035, f"casa/empate/fora divergiu: {a:.3f} vs {b:.3f}"


def test_substituir_cansado_melhora_o_fim_do_jogo(mundo):
    """A razao de este motor existir."""
    world, ids, meu = mundo
    rival = next(i for i in ids if i != meu)
    elenco = sorted(world.squad(meu), key=lambda p: -p.overall)
    onze = [p.id for p in elenco[:11]]
    banco = [p.id for p in elenco[11:14]]
    antes = {p.id: p.condition for p in elenco}
    for pid in onze:
        world.players[pid].condition = 45
    for pid in banco:
        world.players[pid].condition = 100
    onze_rival = [p.id for p in world.best_xi(rival)]

    def trocar(p, minuto):
        if minuto != 60:
            return []
        saem = sorted(p.em_campo_casa, key=lambda i: world.players[i].overall)[:3]
        return [(meu, s, e) for s, e in zip(saem, banco, strict=False)]

    def saldo(fn, n=2500):
        rng = np.random.default_rng(7)
        total = 0
        for _ in range(n):
            p = simular_partida(world, meu, rival, list(onze), list(onze_rival),
                                rng, ESTILO, substituicoes=fn)
            total += p.gols_casa - p.gols_fora
        return total / n

    sem, com = saldo(None), saldo(trocar)
    for pid, v in antes.items():
        world.players[pid].condition = v
    assert com > sem + 0.02, f"substituir nao mudou nada: {sem:.3f} -> {com:.3f}"


def test_eventos_batem_com_o_placar(mundo):
    world, ids, _ = mundo
    rng = np.random.default_rng(3)
    for _ in range(200):
        a, b = rng.choice(ids, 2, replace=False)
        p = simular_partida(world, int(a), int(b),
                            [x.id for x in world.best_xi(int(a))],
                            [x.id for x in world.best_xi(int(b))], rng, ESTILO)
        gols = [e for e in p.eventos if e.tipo == "gol"]
        assert len(gols) == p.gols_casa + p.gols_fora
        assert sum(1 for e in gols if e.clube == p.casa) == p.gols_casa
        for e in p.eventos:
            assert 0 < e.minuto <= BLOCOS * 15
            if e.tipo == "gol":
                assert e.jogador is not None
                assert e.jogador != e.segundo, "jogador deu assistencia para si mesmo"
        assert p.eventos == sorted(p.eventos, key=lambda e: e.minuto)


def test_estatisticas_sao_coerentes_com_o_placar(mundo):
    """Um 3 x 0 nao pode sair com duas finalizacoes."""
    world, ids, _ = mundo
    rng = np.random.default_rng(5)
    for _ in range(300):
        a, b = rng.choice(ids, 2, replace=False)
        p = simular_partida(world, int(a), int(b),
                            [x.id for x in world.best_xi(int(a))],
                            [x.id for x in world.best_xi(int(b))], rng, ESTILO)
        for gols, st in ((p.gols_casa, p.stats_casa), (p.gols_fora, p.stats_fora)):
            assert st.no_gol >= gols, "gols acima das finalizacoes no gol"
            assert st.finalizacoes >= st.no_gol
        assert p.stats_casa.posse + p.stats_fora.posse == 100


def test_vermelho_tira_o_jogador_de_campo(mundo):
    world, ids, _ = mundo
    rng = np.random.default_rng(11)
    achou = False
    for _ in range(400):
        a, b = rng.choice(ids, 2, replace=False)
        p: Partida = simular_partida(world, int(a), int(b),
                                     [x.id for x in world.best_xi(int(a))],
                                     [x.id for x in world.best_xi(int(b))], rng, ESTILO)
        for e in p.eventos:
            if e.tipo == "vermelho":
                achou = True
                em_campo = p.em_campo_casa if e.clube == p.casa else p.em_campo_fora
                assert e.jogador not in em_campo
    assert achou, "nenhum vermelho em 400 partidas: a chance esta zerada?"


def test_cartoes_respeitam_a_causalidade(mundo):
    """Ninguem leva amarelo depois de ja ter sido expulso."""
    world, ids, _ = mundo
    rng = np.random.default_rng(13)
    for _ in range(600):
        a, b = rng.choice(ids, 2, replace=False)
        p = simular_partida(world, int(a), int(b),
                            [x.id for x in world.best_xi(int(a))],
                            [x.id for x in world.best_xi(int(b))], rng, ESTILO)
        expulso_em: dict[int, int] = {}
        for e in p.eventos:
            if e.tipo == "vermelho":
                expulso_em[e.jogador] = e.minuto
            elif e.tipo in ("amarelo", "gol") and e.jogador in expulso_em:
                assert e.minuto < expulso_em[e.jogador], (
                    f"{e.tipo} aos {e.minuto}' de quem foi expulso aos "
                    f"{expulso_em[e.jogador]}'")
