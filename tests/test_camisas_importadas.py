"""A camisa da Wikimedia: vetorizacao e as regras que impedem vestir o clube errado.

Nada aqui toca a rede. O que se protege sao as decisoes que erram em silencio -- escolher a
temporada errada, casar o nome com outro clube, perder a licenca do arquivo.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image

from fm.importer.camisas import _ano, candidatos, escolher_temporada, montar
from fm.importer.vetor import svg, vetorizar


def _quadrado(cor=(226, 35, 26, 255), tamanho=12, fundo=(0, 0, 0, 0)):
    im = Image.new("RGBA", (tamanho + 8, tamanho + 8), fundo)
    for x in range(4, 4 + tamanho):
        for y in range(4, 4 + tamanho):
            im.putpixel((x, y), cor)
    return im


# ------------------------------------------------------------------ vetorizar

def test_uma_forma_solida_vira_uma_camada():
    camadas = vetorizar(_quadrado())
    assert len(camadas) == 1
    assert camadas[0].cor == (226, 35, 26)
    assert camadas[0].area == 144
    assert camadas[0].d.startswith("M") and camadas[0].d.rstrip().endswith("Z")


def test_o_svg_sai_com_as_cores_da_imagem():
    im = _quadrado()
    for x in range(4, 10):
        im.putpixel((x, 4), (17, 17, 17, 255))
    texto = svg(im)
    assert texto.startswith("<svg") and texto.rstrip().endswith("</svg>")
    assert "rgb(226,35,26)" in texto
    assert "rgb(17,17,17)" in texto
    assert f'viewBox="0 0 {im.width} {im.height}"' in texto


def test_o_furo_vira_um_segundo_contorno():
    """Uma camisa tem buracos -- a gola e o vao entre os bracos. Se o tracado perdesse o
    contorno interno, a cor de dentro sumiria por baixo da de fora."""
    im = _quadrado(tamanho=14)
    for x in range(8, 12):
        for y in range(8, 12):
            im.putpixel((x, y), (0, 0, 0, 0))
    d = vetorizar(im)[0].d
    assert d.count("M") == 2, "o furo no meio nao virou um segundo contorno"


def test_imagem_vazia_nao_quebra():
    assert vetorizar(Image.new("RGBA", (10, 10), (0, 0, 0, 0))) == []
    assert "<svg" in svg(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))


def test_cores_quase_iguais_viram_uma_so():
    """Sem juntar, cada meio-tom da borda vira uma camada de um pixel e o SVG incha."""
    im = _quadrado()
    im.putpixel((5, 5), (228, 37, 28, 255))     # variacao imperceptivel
    im.putpixel((6, 6), (17, 17, 17, 255))      # cor de verdade
    cores = {c.cor for c in vetorizar(im)}
    assert (228, 37, 28) not in cores
    assert len(cores) == 1, "a cor distinta tem area 1 e cai no corte de ruido"


# ------------------------------------------------------------------ escolha do arquivo

@pytest.mark.parametrize(("codigo", "esperado"), [
    ("26", 2026), ("2526", 2025), ("2223", 2022), ("05", 2005),
    ("92", 1992), ("61", 1961), ("99", 1999),
])
def test_a_temporada_e_lida_no_seculo_certo(codigo, esperado):
    """REGRESSAO: com corte fixo em 70, o arquivo do Gremio de 1961 virava 2061, ganhava de
    todos e o jogo vestia o clube com a camisa mais VELHA que existe."""
    assert _ano(codigo, hoje=2026) == esperado


def test_escolhe_a_temporada_mais_recente():
    nomes = ["Kit_body_gremio61h.png", "Kit_body_gremio26h.png",
             "Kit_body_gremio2223h.png", "Kit_body_gremio26a.png",
             "Kit_body_gremiotr.png", "Kit_body_outroclube26h.png"]
    assert escolher_temporada(nomes, "gremio", "h") == "26"
    assert escolher_temporada(nomes, "gremio", "a") == "26"
    assert escolher_temporada(nomes, "naoexiste", "h") is None


def test_o_palpite_de_nome_nao_inventa():
    """REGRESSAO: adivinhar por pedaco do nome casava "Vasco da Gama" com `gama`, que e o
    Gama-DF, e vestiria o "Gremio Novorizontino" com a camisa do Gremio de Porto Alegre.
    Vestir o clube errado nao levanta erro -- so aparece na tela."""
    assert candidatos("Vasco da Gama") == ["vascodagama"]
    assert candidatos("Gremio Novorizontino") == ["gremionovorizontino"]
    assert "gremio" not in candidatos("Gremio Novorizontino")
    assert "gama" not in candidatos("Vasco da Gama")
    assert candidatos("Flamengo") == ["flamengo"]


def test_os_apelidos_conferidos_estao_no_arquivo():
    """Cada um destes foi conferido baixando a camisa e olhando."""
    import tomllib

    from fm.importer.camisas import APELIDOS
    with APELIDOS.open("rb") as fh:
        dados = tomllib.load(fh)
    clubes = dados["clubes"]
    assert clubes["Internacional"] == "inter"
    assert clubes["Coritiba"] == "coxa"
    assert clubes["Athletico Paranaense"] == "cap"
    assert dados["verificado"] is True


# ------------------------------------------------------------------ montagem

def test_montar_cola_as_camadas_e_tira_o_fundo():
    """As imagens da Commons vem com fundo BRANCO SOLIDO, nao transparente."""
    pecas = [Image.new("RGBA", (31, 59), (255, 255, 255, 255)),
             Image.new("RGBA", (38, 59), (255, 255, 255, 255)),
             Image.new("RGBA", (31, 59), (255, 255, 255, 255))]
    for x in range(10, 28):
        for y in range(10, 50):
            pecas[1].putpixel((x, y), (226, 35, 26, 255))
    camisa = montar(pecas)
    assert camisa.size == (100, 59)
    assert camisa.getpixel((0, 0))[3] == 0, "o fundo branco continua opaco"
    assert camisa.getpixel((31 + 15, 30))[:3] == (226, 35, 26)


def test_o_branco_de_dentro_sobrevive():
    """A camisa do Corinthians e quase toda branca: apagar todo branco a esburacaria."""
    pecas = [Image.new("RGBA", (10, 20), (255, 255, 255, 255)) for _ in range(3)]
    meio = pecas[1]
    for x in range(10):
        for y in range(20):
            meio.putpixel((x, y), (17, 17, 17, 255))
    for x in range(3, 7):
        for y in range(6, 14):
            meio.putpixel((x, y), (255, 255, 255, 255))   # branco cercado de preto
    camisa = montar(pecas)
    assert camisa.getpixel((10 + 5, 10)) == (255, 255, 255, 255), "furou o branco de dentro"


def test_o_svg_da_camisa_nao_tem_script():
    texto = svg(_quadrado())
    assert "<script" not in texto.lower()
    assert re.fullmatch(r"[^<]*(<(svg|path|/svg)[^>]*>[^<]*)+", texto), "so svg e path"
