"""Premiacoes do ano, reputacao dos tecnicos e o mercado de tecnicos."""

from __future__ import annotations

import pytest

from fm import tecnicos as tec
from fm.carreira import Carreira
from fm.table import Row

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture(scope="module")
def um_ano():
    c = Carreira.nova(LIGAS, "Santos", seed=42)
    while not c.acabou:
        c.avancar()
    serie_a = c.estatisticas_por_comp["brasil_real"].por_jogador.values()
    mais_gols = max(x.gols for x in serie_a if x.jogador in c.world.players
                    and c.world.players[x.jogador].club_id in c.world.clubs)
    r = c.virar_o_ano()
    return c, r, mais_gols


def test_todo_clube_das_ligas_tem_tecnico_e_o_usuario_e_um_deles():
    c = Carreira.nova(LIGAS, "Santos", seed=42)
    for n in LIGAS:
        for k in c.world.leagues[c._id(n)].club_ids:
            assert tec.do_clube(c.tecnicos, k) is not None
    assert tec.do_clube(c.tecnicos, c.clube_id).usuario


def test_premios_saem_das_notas_e_da_artilharia(um_ano):
    c, r, mais_gols = um_ano
    p = r["premios"]
    assert len(p["bola_de_ouro"]) == 3
    assert len({x["jogador"] for x in p["bola_de_ouro"]}) == 3
    serie_a = p["ligas"]["brasil_real"]
    art = serie_a["artilheiro"]
    assert art["gols"] == mais_gols
    assert len(serie_a["selecao"]) == 11
    # o premio guarda nome e clube do dia: continua legivel mesmo se ele se aposentou
    for x in p["bola_de_ouro"] + [serie_a["craque"]]:
        assert x["nome"] and x["clube_nome"]


def test_a_reputacao_premia_quem_fez_mais_com_menos():
    tabela = [Row(club_id=k) for k in (3, 1, 2)]           # 3 terminou em 1o
    valores = {1: 300, 2: 200, 3: 100}                       # e era o mais pobre
    dados = tec.desempenho({"liga": tabela}, {"liga": 1}, valores)
    ts = {i: tec.Tecnico(id=i, nome=f"T{i}", nascimento=1980, reputacao=50.0, clube=i)
          for i in (1, 2, 3)}
    tec.atualizar_reputacoes(ts, dados, {}, {}, {"liga": "Liga"}, 2027)
    assert ts[3].reputacao > ts[1].reputacao
    assert ts[3].titulos and "Liga" in ts[3].titulos[0]


def test_as_vagas_da_ia_sao_ocupadas_na_primeira_data(um_ano):
    c, _, _ = um_ano
    assert c.vagas, "nenhuma demissao na IA num ano inteiro?"
    vagas = list(c.vagas)
    c.avancar()
    for k in vagas:
        if k == c.clube_id:
            continue
        assert tec.do_clube(c.tecnicos, k) is not None, c.world.clubs[k].name


def test_demitido_no_meio_do_ano_recebe_convite_e_troca_de_clube(tmp_path, monkeypatch):
    import fm.carreira as mod
    import fm.diretoria as diretoria
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)

    # a diretoria demite na 4a rodada -- a do primeiro clube, que ja tem 4 datas de
    # historico; a do clube novo, nao. O replay do save passa pelo mesmo ponto.
    def demite_na_quarta(ap, rodada, fim_da_temporada, posicao, clubes, rebaixado=False):
        return "teste" if rodada == 4 and len(ap.historico) >= 4 else None
    monkeypatch.setattr(diretoria, "decidir_demissao", demite_na_quarta)

    c = Carreira.nova(LIGAS, "Santos", seed=11)
    antigo = c.clube_id
    while not c.demitido:
        c.avancar()
    assert c.convites, "demitido e sem nenhuma porta"
    novo = c.convites[0]
    assert c.executar({"tipo": "assumir", "clube": novo}).get("ok")
    assert c.clube_id == novo and not c.demitido
    assert tec.do_clube(c.tecnicos, novo).usuario
    c.avancar()
    assert tec.do_clube(c.tecnicos, antigo) is not None   # a IA ocupou a vaga
    assert not tec.do_clube(c.tecnicos, antigo).usuario
    c.salvar("troca")

    d = Carreira.carregar("troca")
    assert d.clube_id == novo
    assert d.tecnicos[tec.USUARIO].reputacao == c.tecnicos[tec.USUARIO].reputacao


def test_convite_que_nao_esta_na_lista_e_recusado():
    c = Carreira.nova(LIGAS, "Santos", seed=11)
    outro = next(k for k in c.world.clubs if k != c.clube_id)
    assert "erro" in c.executar({"tipo": "assumir", "clube": outro})
