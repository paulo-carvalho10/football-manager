"""A tela de Tabela das copas: grupos, fase de liga e o chaveamento do mata-mata."""

from __future__ import annotations

import pytest

from fm import telas
from fm.carreira import Carreira


def _json(c):
    return lambda cid: {"id": cid, "nome": c.world.clubs[cid].name}


@pytest.fixture(scope="module")
def ano_inteiro():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Palmeiras", seed=21)
    meio = None
    while not c.acabou:
        c.avancar()
        a = c.copas.get("libertadores")
        if meio is None and a is not None and a.historico \
                and a.historico[-1]["tipo"] == "grupos":
            # a Libertadores no comeco do mata-mata: guarda a tela como estava
            meio = telas.copa(c, "libertadores", _json(c))
    return c, meio


def test_toda_copa_encerrada_tem_campeao_que_venceu_a_final(ano_inteiro):
    c, _ = ano_inteiro
    for chave, a in c.copas.items():
        if not a.acabou or a.campeao is None:
            continue
        d = telas.copa(c, chave, _json(c))
        matas = [f for f in d["fases"] if f["tipo"] == "mata"]
        if not matas:
            continue
        final = matas[-1]["confrontos"]
        assert len(final) == 1, f"{chave}: a ultima rodada deveria ser um jogo so"
        assert final[0]["vencedor"] == a.campeao, chave


def test_cada_confronto_encerrado_tem_um_vencedor_e_ele_segue(ano_inteiro):
    c, _ = ano_inteiro
    d = telas.copa(c, "copa_do_brasil", _json(c))
    matas = [f for f in d["fases"] if f["tipo"] == "mata"]
    assert len(matas) >= 4
    for anterior, seguinte in zip(matas, matas[1:]):
        vencedores = {x["vencedor"] for x in anterior["confrontos"]}
        assert None not in vencedores
        na_seguinte = {x["casa"]["id"] for x in seguinte["confrontos"]} | \
                      {x["fora"]["id"] for x in seguinte["confrontos"]} | \
                      {k["id"] for k in seguinte["poupados"]}
        # quem venceu joga a rodada seguinte (a Serie A so entra depois: pode haver mais)
        assert vencedores <= na_seguinte


def test_os_grupos_da_libertadores_ficam_depois_que_o_mata_mata_comeca(ano_inteiro):
    _, meio = ano_inteiro
    assert meio is not None, "a Libertadores nao chegou ao mata-mata"
    grupos = next(f for f in meio["fases"] if f["tipo"] == "grupos")
    # quantos grupos depende de quantos clubes o mundo tem (so com o Brasil carregado sao
    # menos): o que a tela tem de garantir e a fase inteira, com todos os jogos
    assert len(grupos["grupos"]) >= 2
    tamanhos = {len(g["linhas"]) for g in grupos["grupos"]}
    assert len(tamanhos) == 1
    jogos = {ln["jogos"] for g in grupos["grupos"] for ln in g["linhas"]}
    assert len(jogos) == 1 and jogos.pop() >= tamanhos.pop() - 1
    # e o chaveamento ja sabe as rodadas que faltam
    assert meio["a_sortear"][-1] == "Final"
