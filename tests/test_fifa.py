"""Selecoes, datas FIFA, eliminatorias e Copa do Mundo (07/10/2026)."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest

from fm.carreira import Carreira
from fm.fifa import (
    VAGAS_NA_COPA,
    bloqueios,
    competicoes_do_dia,
    datas_fifa,
    dias_da_copa,
    janela_de,
)
from fm.selecoes import (
    CONVOCADOS,
    QUOTA,
    SUSPENSAS,
    convocar,
    convocar_todas,
    existentes,
    id_da_selecao,
    mundo_das_selecoes,
    pais_da_selecao,
)


@pytest.fixture(scope="module")
def ate_a_copa():
    """Quatro temporadas, de 2027 ao fim de 2030: o ciclo inteiro da primeira Copa."""
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    while True:
        while not c.acabou:
            c.avancar()
        if c.temporada == 2030:
            return c
        c.virar_o_ano()


def test_cinco_janelas_por_ano_e_a_copa_no_lugar_da_de_junho():
    assert len(datas_fifa(2027)) == 10
    assert len(datas_fifa(2030)) == 8 and len(dias_da_copa(2030)) == 8
    assert all(d.weekday() in (1, 3) for d in datas_fifa(2028))   # quinta e terca
    # a segunda data de marco cai em abril, mas e da janela de marco
    assert [janela_de(d) for d in datas_fifa(2029)[:2]] == [3, 3]


def test_o_ciclo_da_copa_de_2030():
    assert competicoes_do_dia(datas_fifa(2027)[0]) == []                 # marco de 2027
    assert competicoes_do_dia(datas_fifa(2027)[4]) == ["eliminatorias_conmebol"]  # setembro
    assert set(competicoes_do_dia(datas_fifa(2029)[0])) == {"eliminatorias_conmebol",
                                                           "eliminatorias_uefa"}
    assert competicoes_do_dia(datas_fifa(2029)[4]) == ["eliminatorias_uefa"]
    assert competicoes_do_dia(date(2030, 6, 13)) == ["copa_do_mundo"]
    assert competicoes_do_dia(datas_fifa(2030)[-1]) == []                # a de 2034 ainda nao


def test_nenhum_clube_joga_em_data_fifa():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    for ano in (2027, 2030):
        c.temporada = ano
        c._montar_agenda()
        tipos = Counter(t for t, _ in c.agenda)
        assert tipos["selecao"] == len(datas_fifa(ano)) + len(dias_da_copa(ano))
        for (tipo, _), dia in zip(c.agenda, c.dias, strict=True):
            if tipo != "selecao":
                assert not any(a <= dia <= b for a, b in bloqueios(ano)), (tipo, dia)
        # o Brasileirao inteiro cabe, mesmo no ano da Copa
        assert max(f.matchday for f in c.calendarios["brasil_real"]) <= tipos["liga"]


def test_a_convocacao_e_dos_melhores_do_pais_na_quota():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    w = c.world
    br = convocar(w, "Brasil")
    assert len(br) == CONVOCADOS
    assert all(w.players[p].nationality == "Brasil" for p in br)
    assert Counter(w.players[p].position for p in br) == Counter(QUOTA)
    # a selecao do Brasil e feita de quem joga na Europa tambem: o mundo inteiro carrega
    fora_do_brasil = [p for p in br if w.clubs[w.players[p].club_id].country != "BRA"]
    assert len(fora_do_brasil) >= 10
    # o machucado nao vai
    sem_o_melhor = convocar(w, "Brasil", fora={br[0]})
    assert br[0] not in sem_o_melhor and len(sem_o_melhor) == CONVOCADOS


def test_o_mundo_das_selecoes_nao_mexe_no_dos_clubes():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    antes = {k: list(cl.player_ids) for k, cl in c.world.clubs.items()}
    v = mundo_das_selecoes(c.world, convocar_todas(c.world))
    assert len(v.clubs) == len(existentes(c.world)) >= 60
    assert v.players is c.world.players
    assert {k: list(cl.player_ids) for k, cl in c.world.clubs.items()} == antes
    assert not set(v.clubs) & set(c.world.clubs)
    brasil = id_da_selecao("Brasil")
    assert pais_da_selecao(brasil) == "Brasil"
    assert v.team_rating(brasil) > v.team_rating(id_da_selecao("Venezuela"))


def test_as_eliminatorias_sul_americanas_tem_18_rodadas(ate_a_copa):
    f = ate_a_copa.fifa
    resultados = f.resultados["eliminatorias_conmebol"]
    assert len(resultados) == 90
    jogos = Counter(s for r in resultados for s in (r.home, r.away))
    assert set(jogos.values()) == {18}


def test_as_europeias_sao_grupos_de_quatro(ate_a_copa):
    a = ate_a_copa.fifa.competicoes["eliminatorias_uefa"]
    assert a.grupos and all(len(g) == 4 for g in a.grupos)
    assert not {pais_da_selecao(s) for g in a.grupos for s in g} & set(SUSPENSAS)


def test_a_copa_tem_48_e_termina_com_campeao(ate_a_copa):
    f = ate_a_copa.fifa
    classificados = f.classificados[2030]
    assert len(classificados) == len(set(classificados)) == VAGAS_NA_COPA
    assert {"Espanha", "Portugal", "Marrocos"} <= set(classificados)     # as sedes
    assert not set(classificados) & SUSPENSAS
    # os seis primeiros da sul-americana estao la
    sul = f._classificacao("eliminatorias_conmebol")[:6]
    assert {pais_da_selecao(s) for s in sul} <= set(classificados)
    copa = f.competicoes["copa_do_mundo"]
    assert copa.acabou and copa.campeao
    assert len(f.resultados["copa_do_mundo"]) == 72 + 31        # grupos + mata-mata
    assert f.historico[-1]["ano"] == 2030
    assert f.historico[-1]["campeao"] in classificados


def test_o_replay_refaz_as_mesmas_selecoes(ate_a_copa, tmp_path, monkeypatch):
    """A Copa e a eliminatoria saem iguais no save carregado: o ciclo vive na carreira e
    usa fluxos proprios do gerador."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    for _ in range(25):
        c.avancar()
    c.salvar("ciclo")
    (tmp_path / "ciclo.ponto").unlink()
    volta = Carreira.carregar("ciclo")
    placar = lambda x: [(r.home, r.away, r.goals_home, r.goals_away)   # noqa: E731
                        for r in x.fifa.resultados["eliminatorias_conmebol"]]
    assert placar(volta) == placar(c) and placar(c)
