"""Disputa de penaltis: as regras da cobranca e o desempate do mata-mata nas copas."""

from __future__ import annotations

import numpy as np
import pytest

from fm.carreira import Carreira
from fm.disputa import COBRANCAS, disputar


@pytest.fixture(scope="module")
def mundo():
    c = Carreira.nova("brasil_real", "Santos", seed=42)
    ids = c.world.leagues[c.liga_id].club_ids
    return c.world, ids


def test_as_regras_da_disputa(mundo):
    world, ids = mundo
    a, b = ids[0], ids[1]
    onze_a = [p.id for p in world.best_xi(a)]
    onze_b = [p.id for p in world.best_xi(b)]
    for seed in range(200):
        d = disputar(world, a, b, onze_a, onze_b, np.random.default_rng(seed))
        batidas = {a: 0, b: 0}
        for k in d["cobrancas"]:
            batidas[k["clube"]] += 1
        assert d["gols"][d["vencedor"]] > d["gols"][b if d["vencedor"] == a else a]
        # alternadas: nunca um lado bate duas a mais que o outro
        assert abs(batidas[a] - batidas[b]) <= 1
        assert d["cobrancas"][0]["clube"] == d["primeiro"]
        if max(batidas.values()) > COBRANCAS:            # alternadas: mesmo numero
            assert batidas[a] == batidas[b]
        # nas cinco, acaba assim que um lado nao alcanca mais o outro
        if max(batidas.values()) < COBRANCAS:
            perdedor = b if d["vencedor"] == a else a
            assert d["gols"][perdedor] + (COBRANCAS - batidas[perdedor]) < d["gols"][d["vencedor"]]


def test_a_mesma_semente_da_a_mesma_disputa(mundo):
    world, ids = mundo
    a, b = ids[2], ids[3]
    onze_a, onze_b = [p.id for p in world.best_xi(a)], [p.id for p in world.best_xi(b)]
    d1 = disputar(world, a, b, onze_a, onze_b, np.random.default_rng(7))
    d2 = disputar(world, a, b, onze_a, onze_b, np.random.default_rng(7))
    assert d1 == d2


def test_empate_no_agregado_vai_para_os_penaltis():
    """Toda rodada de mata-mata (fora das fases de 'visitante avanca') com agregado igual
    tem disputa, e quem avanca e quem venceu a disputa."""
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Palmeiras", seed=21)
    while not c.acabou:
        c.avancar()
    def clubes_da_fase(h) -> set[int]:
        if h["tipo"] == "mata":
            return {k for p in h["pares"] for k in p} | set(h["poupados"])
        if h["tipo"] == "grupos":
            return {k for g in h["grupos"] for k in g}
        return set(h["clubes"])

    vistos = 0
    for a in c.copas.values():
        for i, h in enumerate(a.historico):
            if h["tipo"] != "mata" or h["visitante_avanca_empate"]:
                continue
            depois = set().union(*(clubes_da_fase(x) for x in a.historico[i + 1:]))
            for casa, fora in h["pares"]:
                jogos = [r for r in h["resultados"] if {r.home, r.away} == {casa, fora}]
                g = {casa: 0, fora: 0}
                for r in jogos:
                    g[r.home] += r.goals_home
                    g[r.away] += r.goals_away
                if g[casa] != g[fora]:
                    continue
                vistos += 1
                d = h["disputas"].get(f"{casa}-{fora}")
                assert d is not None, f"{a.torneio.nome}: empate sem disputa"
                perdedor = fora if d["vencedor"] == casa else casa
                assert perdedor not in depois, f"{a.torneio.nome}: quem perdeu seguiu"
                if i + 1 < len(a.historico):
                    assert d["vencedor"] in depois, f"{a.torneio.nome}: quem venceu sumiu"
                else:
                    assert a.campeao == d["vencedor"]
    assert vistos > 0, "nenhum empate no agregado num ano inteiro?"
