"""As copas de 06/10/2026: copas nacionais, supercopas e a Conference League."""

from __future__ import annotations

import pytest

from fm.carreira import Carreira
from fm.copa import FILIAL

LIGAS = ["inglaterra_real", "inglaterra_b_real", "portugal_real", "portugal_b_real"]


@pytest.fixture(scope="module")
def dois_anos():
    c = Carreira.nova(LIGAS, "Arsenal", seed=5)
    while not c.acabou:
        c.avancar()
    primeiro = {n: (a.campeao, a.vice) for n, a in c.copas.items()}
    c.virar_o_ano()
    return c, primeiro


def test_as_copas_nacionais_terminam_com_campeao_da_propria_liga(dois_anos):
    c, primeiro = dois_anos
    for copa, pais in (("fa_cup", "ENG"), ("taca_de_portugal", "POR")):
        campeao, vice = primeiro[copa]
        assert campeao is not None, f"{copa} sem campeao"
        assert c.world.clubs[campeao].country == pais
        assert c.world.clubs[vice].country == pais


def test_time_b_nao_disputa_a_copa_nacional(dois_anos):
    """REGRESSAO: o Porto B chegou a final da Taca de Portugal."""
    c, _ = dois_anos
    taca = c.copas["taca_de_portugal"]
    for fase in c.copas["taca_de_portugal"].torneio.fases:
        assert fase.get("sem_filiais")
    assert all(not FILIAL.search(c.world.clubs[k].name) for k in taca.ja_entraram)


def test_a_supercopa_e_dos_campeoes_e_nao_gasta_vaga(dois_anos):
    """REGRESSAO: as supercopas dividiam as vagas com as continentais -- a Supercopa da
    UEFA ficava com quem sobrava depois da Champions, e quem jogava a supercopa perdia a
    vaga continental."""
    c, primeiro = dois_anos
    sup = c.copas["supercopa_uefa"]
    entraram = {k for v in sup.classificados.values() for k in v}
    assert entraram == {primeiro["champions"][0], primeiro["europa_league"][0]}
    champions = {k for v in c.copas["champions"].classificados.values() for k in v}
    europa = {k for v in c.copas["europa_league"].classificados.values() for k in v}
    # o campeao da Champions joga a supercopa E volta a Champions pela liga dele
    campeao = primeiro["champions"][0]
    pais = c.world.clubs[campeao].country
    if pais in ("ENG", "POR"):
        assert campeao in champions | europa


def test_a_conference_league_nao_repete_clube_das_outras(dois_anos):
    c, _ = dois_anos
    conf = {k for v in c.copas["conference_league"].classificados.values() for k in v}
    champions = {k for v in c.copas["champions"].classificados.values() for k in v}
    europa = {k for v in c.copas["europa_league"].classificados.values() for k in v}
    assert conf and not conf & (champions | europa)
