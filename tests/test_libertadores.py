"""A Libertadores e a Sul-Americana no formato real, numa carreira que so joga o Brasil."""

from __future__ import annotations

from collections import Counter

import pytest

from fm.carreira import Carreira

PAISES = {"BRA", "ARG", "COL", "CHI", "URU", "ECU", "PAR", "PER", "BOL", "VEN"}


@pytest.fixture(scope="module")
def ano():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Palmeiras", seed=21)
    inicio = {k: {b: list(v) for b, v in a.classificados.items()} for k, a in c.copas.items()}
    while not c.acabou:
        c.avancar()
    return c, inicio


def test_os_outros_paises_existem_mesmo_sem_liga_jogavel(ano):
    c, _ = ano
    assert set(c.ligas_de_fora) >= {"argentina_real", "colombia_real", "bolivia_real"}
    for nome in c.ligas_de_fora:
        assert c.world.leagues[c._id(nome)].club_ids


def test_libertadores_tem_47_clubes_de_10_paises(ano):
    c, inicio = ano
    liberta = inicio["libertadores"]
    assert {b: len(v) for b, v in liberta.items()} == {"grupos": 28, "segunda": 13, "primeira": 6}
    paises = Counter(c.world.clubs[k].country for v in liberta.values() for k in v)
    assert set(paises) == PAISES
    for pais in PAISES - {"BRA", "ARG"}:
        assert paises[pais] >= 4, pais          # 4 cada (5 se herdou a vaga de campeao)


def test_o_formato_e_o_real(ano):
    c, _ = ano
    a = c.copas["libertadores"]
    assert a.acabou and a.campeao is not None
    fases = [(h["nome"], h["tipo"], len(h.get("pares", [])), len(h.get("grupos", [])))
             for h in a.historico]
    assert fases == [
        ("Primeira fase", "mata", 3, 0), ("Segunda fase", "mata", 8, 0),
        ("Terceira fase", "mata", 4, 0), ("Fase de grupos", "grupos", 0, 8),
        ("Oitavas de final", "mata", 8, 0), ("Quartas de final", "mata", 4, 0),
        ("Semifinal", "mata", 2, 0), ("Final", "mata", 1, 0)]
    grupos = next(h for h in a.historico if h["tipo"] == "grupos")
    assert all(len(g) == 4 for g in grupos["grupos"])
    final = a.historico[-1]
    assert final["maos"] == 1 and len(final["resultados"]) == 1      # jogo unico


def test_a_sul_americana_recebe_quem_cai_da_libertadores(ano):
    c, _ = ano
    s = c.copas["sudamericana"]
    assert s.acabou and s.campeao is not None
    playoff = next(h for h in s.historico if h["nome"] == "Playoff")
    assert len(playoff["pares"]) == 8                      # 8 segundos x 8 terceiros
    terceiros = set(c.exportados.get("libertadores:terceiros", []))
    no_playoff = {k for par in playoff["pares"] for k in par}
    assert terceiros and terceiros <= no_playoff
    grupos = next(h for h in s.historico if h["tipo"] == "grupos")
    assert sum(len(g) for g in grupos["grupos"]) == 32
    assert set(c.exportados.get("libertadores:eliminados_pre", [])) <= {k for g in grupos["grupos"] for k in g}


def test_o_campeao_da_sul_americana_vai_para_a_libertadores(ano):
    c, _ = ano
    campeao = c.copas["sudamericana"].campeao
    c.virar_o_ano()
    liberta = c.copas["libertadores"].classificados
    assert campeao in liberta.get("grupos", [])
    assert sum(len(v) for v in liberta.values()) == 47
