"""A tela de escalacao em grafico: campo, camisas e o onze posicionado.

O que se protege aqui e que o HTML gerado seja coerente com o mundo -- os onze que o
usuario escalou, nas cores do clube dele, dentro dos limites do campo. Um SVG torto nao
levanta excecao: ele so desenha errado, e isso ninguem ve num teste de tipo.
"""

from __future__ import annotations

import re

import pytest

from fm.carreira import Carreira
from fm.tatica import FORMACOES, Tatica
from fm.tela_campo import escalacao_html, montar_onze

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture(scope="module")
def carreira():
    return Carreira.nova(LIGAS, "Flamengo", seed=42)


def test_o_onze_inteiro_entra_no_campo(carreira):
    c = carreira
    html = escalacao_html(c)
    assert html.count('class="jogador"') == 11
    assert html.count('class="camisa"') == 11
    for pid in c.escalacao_atual():
        assert c.world.players[pid].name.split()[-1] in html


@pytest.mark.parametrize("formacao", list(FORMACOES))
def test_toda_formacao_cabe_dentro_do_campo(carreira, formacao):
    """Coordenada fora de 0..100 poe jogador do lado de fora do gramado."""
    c = carreira
    tatica = Tatica(formacao=formacao)
    onze = [p.id for p in c.world.best_xi(c.clube_id, tatica.vagas)]
    jogadores = montar_onze(c, onze, tatica)
    assert len(jogadores) == 11
    for j in jogadores:
        assert 5 <= j.x <= 95, f"{formacao}: {j.nome} em x={j.x}"
        assert 5 <= j.y <= 96, f"{formacao}: {j.nome} em y={j.y}"
    # o goleiro e o mais recuado de todos, sempre
    gol = next(j for j in jogadores if j.posicao == "GK")
    assert gol.y == max(j.y for j in jogadores)
    assert len({(round(j.x, 1), round(j.y, 1)) for j in jogadores}) == 11, "dois no mesmo ponto"


def test_a_camisa_usa_as_cores_do_clube(carreira):
    c = carreira
    html = escalacao_html(c)
    clube = c.clube
    assert (clube.kit_body or clube.color_primary).lower() in html.lower()
    assert (clube.kit_detail or clube.color_secondary).lower() in html.lower()


def test_o_goleiro_veste_o_inverso():
    c = Carreira.nova(LIGAS, "Gremio", seed=42)
    html = escalacao_html(c)
    # a camisa do goleiro e a ultima peca e nao leva o padrao do clube
    goleiro = html.rsplit('class="jogador"', 1)[-1]
    assert "GK" in goleiro
    assert 'fill="' + c.clube.color_secondary in goleiro


def test_cada_camisa_tem_ids_proprios(carreira):
    """REGRESSAO em potencial: clipPath com id repetido faz onze camisas usarem o recorte
    da primeira, e as cores de um jogador vazam para os outros."""
    html = escalacao_html(carreira)
    ids = re.findall(r'<clipPath id="([^"]+)"', html)
    assert len(ids) == 11
    assert len(set(ids)) == 11, "ids de clipPath repetidos entre camisas"
    gradientes = re.findall(r'<linearGradient id="([^"]+)"', html)
    assert len(set(gradientes)) == 11


def test_o_nome_do_jogador_e_escapado():
    """Nome com & ou < viraria HTML quebrado -- e os packs tem nomes de tudo que e pais."""
    from fm.tela_campo import escalacao_html as gerar
    c = Carreira.nova(LIGAS, "Santos", seed=42)
    alvo = c.world.players[c.escalacao_atual()[0]]
    alvo.name = 'Zé <script>& "cia"'
    html = gerar(c)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_o_html_e_uma_pagina_completa(carreira):
    html = escalacao_html(carreira)
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "<title>" in html and carreira.clube.name in html
    assert html.count("{") == html.count("}"), "sobrou chave de format no HTML"
