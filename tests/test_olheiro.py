"""O elenco do usuario so muda com ele: a janela da IA nao toca nele, e o olheiro so indica."""

from __future__ import annotations

import pytest

from fm.carreira import Carreira


@pytest.fixture(scope="module")
def virada():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Flamengo", seed=11)
    while not c.acabou:
        c.avancar()
    antes = {p.id for p in c.world.squad(c.clube_id)}
    resumo = c.virar_o_ano()
    return c, antes, resumo


def test_a_janela_da_ia_nao_compra_nem_vende_do_usuario(virada):
    """REGRESSAO: a janela da virada levava jogador do usuario (ate em venda forcada, com o
    caixa no vermelho) e punha gente no elenco dele sem perguntar."""
    c, antes, resumo = virada
    assert resumo["compras_do_clube"] == []
    assert resumo["vendas_do_clube"] == []
    # quem saiu, saiu por contrato vencido ou aposentadoria -- nunca vendido a outro clube
    for pid in antes - {p.id for p in c.world.squad(c.clube_id)}:
        p = c.world.players.get(pid)
        assert p is None or p.club_id is None, f"{p.name} foi parar no {p.club_id}"


def test_o_olheiro_indica_quem_melhora_o_time_e_cabe_no_bolso():
    from fm.servidor import _clube
    from fm.telas import exibir, olheiro

    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=1)
    r = olheiro(c, lambda k: _clube(c, k))
    assert [x["titulo"] for x in r["secoes"]][-2:] == ["Promessas", "Oportunidades"]
    meus = {p.id for p in c.world.squad(c.clube_id)}
    titulares = {p.id: p for p in c.world.squad(c.clube_id)}
    indicados = [j for s in r["secoes"] for j in s["jogadores"]]
    assert indicados, "o olheiro nao achou ninguem"
    for j in indicados:
        assert j["id"] not in meus
        assert j["preco"] <= r["orcamento"]["transferencia"]
        assert j["salario_pedido"] <= r["orcamento"]["salario"]
    # cada reforco e melhor que o titular da vaga que ele resolve
    for secao in r["secoes"][:-2]:
        nome = secao["titulo"].split(": ", 1)[1].rsplit(" (", 1)[0]
        titular = next(p for p in titulares.values() if p.name == nome)
        for j in secao["jogadores"]:
            assert j["overall"] > exibir(titular.overall)


# ------------------------------------------------------------------ a moral no mercado

def test_moral_baixa_barateia_e_o_insatisfeito_desce_de_patamar():
    """O jogador de moral baixa no clube dele sai mais barato: o abatido um pouco, o
    insatisfeito bastante -- e esse aceita ate clube menor, sendo titular."""
    from fm import negocios as neg
    from fm.moral import INSATISFEITO

    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Mirassol", seed=3)
    grande = max((k for k in c.world.leagues[c._id("brasil_real")].club_ids),
                 key=lambda k: c.world.team_rating(k))
    estrela = max(c.world.best_xi(grande), key=lambda p: p.overall)
    estrela.morale = 75
    normal = neg.pedido_do_vendedor(c, estrela)
    estrela.morale = 50
    assert neg.pedido_do_vendedor(c, estrela) < normal
    estrela.morale = INSATISFEITO - 5
    barato = neg.pedido_do_vendedor(c, estrela)
    # sem o premio de titular e com o desconto de quem quer sair
    assert barato <= normal * 0.7, "o insatisfeito titular tem de sair bem mais barato"
    assert neg.recusa_por_ambicao(c, estrela) is None, "insatisfeito topa clube menor"
    r = neg.avaliar_oferta(c, estrela.id, barato)
    assert r["resultado"] == "aceita" and "quer sair" in r["mensagem"]


# ------------------------------------------------------------------ sala de trofeus

def test_a_sala_de_trofeus_bate_com_a_temporada(virada):
    from fm.telas import sala_de_trofeus

    c, _, _ = virada
    d = sala_de_trofeus(c)
    resumo = c.historico[-1]
    titulos = {t["nome"] for t in d["tacas"] if t["temporada"] == resumo["temporada"]}
    if resumo["campeoes"].get(resumo["minha_liga"]) == resumo["clube"]:
        assert "Série A" in titulos
    recordes = {r["titulo"]: r for r in d["recordes"]}
    assert "Maior vitória" in recordes and "Maior invencibilidade" in recordes
    pro, contra = (int(x) for x in recordes["Maior vitória"]["valor"].split(" x "))
    assert pro > contra
    # as lendas: quem mais jogou fez a temporada quase inteira
    assert d["mais_jogos"] and d["mais_jogos"][0]["jogos"] > 30
    assert all(x["gols"] for x in d["artilheiros"])


def test_a_virada_diz_por_que_cada_um_saiu_do_elenco(virada):
    """REGRESSAO: o veterano do usuario sumia do elenco na virada e a tela so dizia
    "N aposentadorias no mundo". Agora cada saida vem com o motivo."""
    c, antes, resumo = virada
    saidas = resumo["saidas_do_clube"]
    assert {x["nome"] for x in saidas} == set(resumo["aposentadorias_do_clube"])
    for x in saidas:
        assert x["motivo"] in ("aposentou-se", "fim de contrato") or x["motivo"].startswith("foi para")
        if x["motivo"] == "aposentou-se":
            assert x["idade"] >= 32
