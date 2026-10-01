"""A Libertadores como na Conmebol: grupos sorteados por potes e mata-mata em chave fixa."""

from __future__ import annotations

import pytest

from fm.carreira import Carreira


@pytest.fixture(scope="module")
def ano():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Palmeiras", seed=21)
    while not c.acabou:
        c.avancar()
    return c, None


def test_os_grupos_saem_dos_potes_sem_repetir_pais(ano):
    """REGRESSAO: a serpentina recebia a lista fora de ordem e virava sorteio puro --
    tres brasileiros grandes no mesmo grupo e um grupo sem ninguem. Agora cada grupo leva
    um de cada pote (pelo ranking), e dois do mesmo pais nao caem juntos."""
    c, _ = ano
    a = c.copas["libertadores"]
    grupos = next(h for h in a.historico if h["tipo"] == "grupos")["grupos"]
    todos = sorted((k for g in grupos for k in g), key=lambda k: -c.world.clubs[k].reputation)
    pote1 = set(todos[:len(grupos)])
    for g in grupos:
        assert len(set(g) & pote1) == 1, "cada grupo tem exatamente um cabeca de chave"
        paises = [c.world.clubs[k].country for k in g]
        assert len(paises) == len(set(paises)), f"pais repetido no grupo: {paises}"


def test_a_chave_e_fixa_ate_a_final(ano):
    """Como na Conmebol: nas oitavas, 1o de grupo contra 2o de OUTRO grupo; dai em diante
    o vencedor do confronto 1 pega o do 2, e a volta e na casa da melhor campanha."""
    c, _ = ano
    a = c.copas["libertadores"]
    assert len(a.chave) == 16
    rodadas = [h for h in a.historico if h["tipo"] == "mata" and h["fase"] >= 4]
    assert [len(h["pares"]) for h in rodadas] == [8, 4, 2, 1]
    oitavas = rodadas[0]["pares"]
    for ida, volta in oitavas:
        # a volta e do cabeca (o 1o do grupo), e os dois sao de grupos diferentes
        assert a.campanha[volta]["pos"] == 1 and a.campanha[ida]["pos"] == 2
        assert a.campanha[volta]["grupo"] != a.campanha[ida]["grupo"]
    vencedores = []
    for h in rodadas:
        pares = [set(p) for p in h["pares"]]
        if vencedores:
            # cada confronto junta os vencedores de dois confrontos vizinhos da rodada anterior
            esperados = [set(vencedores[i:i + 2]) for i in range(0, len(vencedores), 2)]
            assert pares == esperados
        vencedores = [x for p in h["pares"] for x in p if x in _passaram(a, h)]
    assert vencedores == [a.campeao]


def _passaram(a, rodada) -> set[int]:
    """Quem passou de uma rodada do historico: o do placar agregado ou o dos penaltis."""
    gols: dict[int, int] = {}
    for r in rodada["resultados"]:
        gols[r.home] = gols.get(r.home, 0) + r.goals_home
        gols[r.away] = gols.get(r.away, 0) + r.goals_away
    fora = set()
    for x, y in rodada["pares"]:
        if gols.get(x, 0) != gols.get(y, 0):
            fora.add(x if gols.get(x, 0) > gols.get(y, 0) else y)
        else:
            fora.add(rodada["disputas"][f"{x}-{y}"]["vencedor"])
    return fora
