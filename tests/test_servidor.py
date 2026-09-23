"""A API que a interface do navegador consome.

Isto e a segunda casca do jogo, nao um segundo jogo: o que se protege aqui e que ela
entregue o MESMO estado que o terminal ve, e que nenhuma regra tenha vazado para dentro
dela. Se um valor so existe no JSON, ele foi inventado aqui -- e e' bug.
"""

from __future__ import annotations

import json

import pytest

from fm.carreira import Carreira
from fm.servidor import (
    Jogo,
    avancar,
    camisa_svg,
    escalar,
    estado,
    tabela,
    virar_o_ano,
)

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture
def jogo():
    return Jogo(Carreira.nova(LIGAS, "Flamengo", seed=42))


def test_o_estado_e_json_de_verdade(jogo):
    """Se nao serializa, a interface nao abre -- e o erro so aparece no navegador."""
    texto = json.dumps(estado(jogo), ensure_ascii=False)
    assert len(texto) > 1000
    de_volta = json.loads(texto)
    assert de_volta["clube"]["nome"] == "Flamengo"


def test_o_estado_bate_com_a_carreira(jogo):
    c, e = jogo.c, estado(jogo)
    assert e["temporada"] == c.temporada
    assert e["rodada"] == c.rodada
    assert e["caixa"] == c.clube.balance
    assert e["liga"] == c.liga
    assert len(e["elenco"]) == len(c.world.squad(c.clube_id))
    assert sum(1 for p in e["elenco"] if p["titular"]) == 11
    assert sorted(e["onze"]) == sorted(c.escalacao_atual())
    assert e["aprovacao"]["meta"] == c.aprovacao.meta.texto


def test_avancar_devolve_a_partida_e_o_estado_novo(jogo):
    antes = estado(jogo)["rodada"]
    r = avancar(jogo)
    assert r["estado"]["rodada"] == antes + 1 or r["tipo"] == "copa"
    if r["partida"]:
        p = r["partida"]
        assert p["gols_casa"] + p["gols_fora"] == sum(
            1 for e in p["eventos"] if e["tipo"] == "gol")
        assert len(p["estatisticas"]) == 6
        assert "Flamengo" in (p["casa"]["nome"], p["fora"]["nome"])
    json.dumps(r, ensure_ascii=False)


def test_escalar_pela_api_muda_o_onze(jogo):
    c = jogo.c
    elenco = sorted(c.world.squad(c.clube_id), key=lambda p: p.overall)
    piores = [p.id for p in elenco[:11]]
    r = escalar(jogo, {"onze": piores})
    assert "erro" not in r
    assert sorted(r["estado"]["onze"]) == sorted(piores)
    # a tatica tambem vem junto
    r = escalar(jogo, {"onze": piores, "estilo": "ofensivo", "marcacao": "forte"})
    assert r["estado"]["tatica"]["estilo"] == "ofensivo"
    assert r["estado"]["tatica"]["marcacao"] == "forte"


def test_escalacao_invalida_volta_como_erro_e_nao_como_excecao(jogo):
    """A interface precisa poder mostrar a mensagem; uma excecao viraria 500 e tela branca."""
    meus = [p.id for p in jogo.c.world.squad(jogo.c.clube_id)]
    curto = escalar(jogo, {"onze": meus[:3]})
    assert "11" in curto["erro"], curto["erro"]
    alheio = escalar(jogo, {"onze": [1, 2, 3]})
    assert "outro clube" in alheio["erro"], alheio["erro"]
    assert curto["estado"]["onze"], "o estado tem de continuar utilizavel"


def test_a_tabela_vem_ordenada_e_marca_o_usuario(jogo):
    t = tabela(jogo)
    assert len(t["linhas"]) == 20
    assert [linha["posicao"] for linha in t["linhas"]] == list(range(1, 21))
    assert sum(1 for linha in t["linhas"] if linha["eu"]) == 1
    outra = tabela(jogo, "brasil_b_real")
    assert outra["liga"] == "brasil_b_real"
    assert not any(linha["eu"] for linha in outra["linhas"])


def test_a_camisa_vem_como_svg(jogo):
    svg = camisa_svg(jogo, jogo.c.clube_id, "1")
    assert svg.lstrip().startswith("<svg")
    assert "</svg>" in svg
    casa, fora = svg, camisa_svg(jogo, jogo.c.clube_id, "2")
    assert casa != fora, "camisa 1 e 2 tem de diferir"


def test_virar_o_ano_pela_api(jogo):
    c = jogo.c
    assert "erro" in virar_o_ano(jogo), "nao pode virar antes de acabar"
    while not c.acabou:
        c.avancar()
    r = virar_o_ano(jogo)
    json.dumps(r, ensure_ascii=False)
    assert r["temporada"] == 2027
    assert r["campeoes"]["brasil_real"]
    assert r["estado"]["temporada"] == 2028
    assert "clima" in r and "balanco" in r


def test_a_api_nao_deixa_jogar_depois_de_demitido(jogo):
    jogo.c.aprovacao.demitido = True
    jogo.c.aprovacao.motivo = "teste"
    r = avancar(jogo)
    assert "erro" in r
    assert estado(jogo)["demitido"] is True


def test_uma_temporada_inteira_pela_api(jogo):
    """O caminho que o navegador percorre de verdade."""
    c = jogo.c
    partidas = 0
    while not c.acabou:
        r = avancar(jogo)
        assert "erro" not in r
        if r["partida"]:
            partidas += 1
    assert partidas >= 38
    fim = virar_o_ano(jogo)
    assert fim["estado"]["temporada"] == 2028
    assert fim["estado"]["rodada"] == 0
