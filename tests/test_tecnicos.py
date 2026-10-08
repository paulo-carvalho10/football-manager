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


# ---------------------------------------------------------------- 08/10/2026

def test_vice_com_o_terceiro_elenco_sobe_de_reputacao():
    """REGRESSAO: a reputacao so contava superar o esperado pela folha. Vice com o 3o
    elenco rendia +0,1, e o usuario nunca chegava ao tamanho que os grandes pedem."""
    tabela = [Row(club_id=k) for k in (1, 3, 2, 4, 5, 6, 7, 8)]   # 3 foi vice
    valores = {1: 900, 2: 800, 3: 700, 4: 100, 5: 90, 6: 80, 7: 70, 8: 60}
    dados = tec.desempenho({"liga": tabela}, {"liga": 1}, valores)
    t = tec.Tecnico(id=3, nome="T", nascimento=1980, reputacao=45.0, clube=3)
    tec.atualizar_reputacoes({3: t}, dados, {}, {}, {"liga": "Liga"}, 2027,
                             estatura={3: 76.0})
    assert t.variacao >= 4.0


def test_o_tamanho_do_clube_puxa_a_reputacao():
    """Sem resultado novo, o tecnico de grande tende para cima e o de pequeno para baixo."""
    grande = tec.Tecnico(id=1, nome="G", nascimento=1980, reputacao=50.0, clube=1)
    pequeno = tec.Tecnico(id=2, nome="P", nascimento=1980, reputacao=50.0, clube=2)
    tec.atualizar_reputacoes({1: grande, 2: pequeno}, {}, {}, {}, {}, 2027,
                             estatura={1: 85.0, 2: 20.0})
    assert grande.reputacao > 50.0 > pequeno.reputacao


def test_finalista_e_semifinalista_de_copa_ganham_reputacao():
    t = tec.Tecnico(id=1, nome="T", nascimento=1980, reputacao=45.0, clube=1)
    nada = tec.Tecnico(id=2, nome="N", nascimento=1980, reputacao=45.0, clube=2)
    tec.atualizar_reputacoes({1: t, 2: nada}, {}, {}, {}, {}, 2027,
                             campanhas={1: [("libertadores", "final")]})
    assert t.reputacao - nada.reputacao == pytest.approx(
        tec.TITULO_DE_COPA["libertadores"] * tec.FINALISTA)


def test_o_grande_que_fica_fora_do_g4_balanca():
    """REGRESSAO: em oito anos, Palmeiras e Flamengo nunca trocaram de tecnico -- e o
    usuario nunca via convite de clube grande."""
    favorito = tec.Desempenho(clube=1, liga="l", tier=1, esperado=1, final=6, clubes=20)
    mediano = tec.Desempenho(clube=2, liga="l", tier=1, esperado=10, final=11, clubes=20)
    assert tec.chance_de_demitir(favorito) > 0.3
    assert tec.chance_de_demitir(mediano) < 0.02          # um lugar abaixo: quase nada
    caiu = tec.Desempenho(clube=3, liga="l", tier=1, esperado=12, final=18, clubes=20,
                          caiu=True)
    assert tec.chance_de_demitir(caiu) == 1.0


def test_pedir_demissao_abre_convites_e_o_save_refaz(tmp_path, monkeypatch):
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova(LIGAS, "Santos", seed=11)
    for _ in range(8):
        c.avancar()
    antes = c.tecnicos[tec.USUARIO].reputacao
    r = c.executar({"tipo": "pedir_demissao"})
    assert r.get("ok") and c.demitido and c.pediu_demissao
    assert c.convites, "pediu demissao e ninguem chamou: a carreira trava"
    assert c.tecnicos[tec.USUARIO].reputacao == pytest.approx(antes + tec.DEMISSAO_PEDIDA)
    assert "erro" in c.executar({"tipo": "pedir_demissao"})
    novo = c.convites[0]
    assert c.executar({"tipo": "assumir", "clube": novo}).get("ok")
    assert c.clube_id == novo and not c.demitido and not c.pediu_demissao
    c.avancar()
    c.salvar("demissao")
    (tmp_path / "demissao.ponto").unlink()
    d = Carreira.carregar("demissao")
    assert d.clube_id == novo
    assert d.tecnicos[tec.USUARIO].reputacao == c.tecnicos[tec.USUARIO].reputacao
