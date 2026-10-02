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
    assert r["secoes"][-1]["titulo"] == "Promessas"
    meus = {p.id for p in c.world.squad(c.clube_id)}
    titulares = {p.id: p for p in c.world.squad(c.clube_id)}
    indicados = [j for s in r["secoes"] for j in s["jogadores"]]
    assert indicados, "o olheiro nao achou ninguem"
    for j in indicados:
        assert j["id"] not in meus
        assert j["preco"] <= r["orcamento"]["transferencia"]
        assert j["salario_pedido"] <= r["orcamento"]["salario"]
    # cada reforco e melhor que o titular da vaga que ele resolve
    for secao in r["secoes"][:-1]:
        nome = secao["titulo"].split(": ", 1)[1].rsplit(" (", 1)[0]
        titular = next(p for p in titulares.values() if p.name == nome)
        for j in secao["jogadores"]:
            assert j["overall"] > exibir(titular.overall)
