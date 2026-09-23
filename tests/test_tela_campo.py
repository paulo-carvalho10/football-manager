"""A tela de escalacao em grafico: campo, camisas e o onze posicionado.

O que se protege aqui e que o HTML gerado seja coerente com o mundo -- os onze que o
usuario escalou, nas cores do clube dele, dentro dos limites do campo. Um SVG torto nao
levanta excecao: ele so desenha errado, e isso ninguem ve num teste de tipo.
"""

from __future__ import annotations

import re

import pytest

from fm.carreira import Carreira
from fm.importer.camisas import carregar
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


def test_a_camisa_desenhada_usa_as_cores_do_clube():
    """Vale para quem NAO tem camisa importada -- que e a maior parte do mundo."""
    c = Carreira.nova(LIGAS, "Chapecoense", seed=42)
    if carregar(c.clube.name):
        pytest.skip("este clube ja tem camisa importada")
    html = escalacao_html(c)
    assert (c.clube.kit_body or c.clube.color_primary).lower() in html.lower()
    assert (c.clube.kit_detail or c.clube.color_secondary).lower() in html.lower()


def test_a_camisa_importada_ganha_da_desenhada():
    """A da Commons e o uniforme de verdade; a desenhada e o que cobre o resto do mundo."""
    c = Carreira.nova(LIGAS, "Flamengo", seed=42)
    importada = carregar("Flamengo")
    if not importada:
        pytest.skip("Flamengo ainda nao importado")
    html = escalacao_html(c)
    # um trecho de path da camisa importada tem de aparecer na tela
    trecho = re.search(r'd="(M[^"]{40,})"', importada).group(1)[:40]
    assert trecho in html


@pytest.mark.parametrize("clube", ["Gremio", "Chapecoense"])
def test_o_goleiro_nao_veste_a_mesma_camisa_da_linha(clube):
    """Regra do futebol, e ajuda a ler o campo. Com camisa importada ele usa a 2; sem ela,
    as cores do tema invertidas -- o que muda e a fonte, nao a regra."""
    html = escalacao_html(Carreira.nova(LIGAS, clube, seed=42))
    pecas = re.findall(r'<div class="jogador".*?</div>', html, re.S)
    assert len(pecas) == 11
    gol = next(p for p in pecas if ">GK " in p)
    linha = [p for p in pecas if ">GK " not in p]
    def desenho(peca):
        return re.sub(r'id="[^"]*"|url\(#[^)]*\)', "", peca.split("<span")[0])
    assert all(desenho(gol) != desenho(p) for p in linha), "o goleiro veste igual a linha"


@pytest.mark.parametrize("clube", ["Flamengo", "Chapecoense"])
def test_nenhum_id_se_repete_entre_camisas(clube):
    """Onze camisas na mesma pagina: id repetido faz todas usarem o recorte da primeira, e
    as cores de um jogador vazam para os outros. Vale para a desenhada e para a importada."""
    html = escalacao_html(Carreira.nova(LIGAS, clube, seed=42))
    ids = re.findall(r'id="([^"]+)"', html)
    repetidos = {i for i in ids if ids.count(i) > 1}
    assert not repetidos, f"ids repetidos: {sorted(repetidos)}"


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
