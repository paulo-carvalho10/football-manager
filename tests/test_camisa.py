"""A camisa do clube no terminal.

O que quebra aqui e alinhamento, e alinhamento quebra em silencio: os codigos de cor
ocupam dezenas de bytes e zero colunas na tela, entao qualquer conta feita sobre len() da
string colorida entorta a fileira inteira sem levantar erro nenhum.
"""

from __future__ import annotations

import io
import re

import pytest

from fm.camisa import LARGURA, camisa, legenda
from fm.carreira import Carreira
from fm.jogo import _desenhar_campo

ANSI = re.compile(r"\033\[[0-9;]*m")


def visivel(texto: str) -> int:
    return len(ANSI.sub("", texto))


@pytest.fixture(scope="module")
def carreira():
    return Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=42)


@pytest.mark.parametrize("cor", [True, False])
def test_a_camisa_ocupa_as_colunas_que_diz_ocupar(cor):
    linhas = camisa("#E2231A", "#111111", "81", cor=cor)
    assert len(linhas) == 3
    for linha in linhas:
        assert visivel(linha) == LARGURA, f"{visivel(linha)} colunas em vez de {LARGURA}"


def test_o_overall_aparece_no_peito():
    assert "81" in ANSI.sub("", camisa("#E2231A", "#111111", "81", cor=True)[2])
    assert "7" in ANSI.sub("", camisa("#E2231A", "#111111", "7", cor=False)[2])


def test_a_cor_do_clube_vai_para_a_camisa():
    """Pintar o Corinthians de verde, a cor do rival, e pior que nao pintar nada."""
    vermelha = "".join(camisa("#E2231A", "#111111", "81", cor=True))
    assert "226;35;26" in vermelha, "a cor primaria nao chegou ao desenho"
    assert "17;17;17" in vermelha, "a cor secundaria nao chegou as mangas"
    preta = "".join(camisa("#111111", "#F2F2F2", "81", cor=True))
    assert vermelha != preta, "dois clubes de cores diferentes sairam iguais"


def test_o_texto_contrasta_com_o_fundo():
    """Nome escuro em camisa escura nao se le."""
    escura = "".join(camisa("#111111", "#F2F2F2", "81", cor=True))
    clara = "".join(camisa("#F2F2F2", "#111111", "81", cor=True))
    assert "38;2;240;240;240" in escura, "texto claro esperado sobre fundo escuro"
    assert "38;2;17;17;17" in clara, "texto escuro esperado sobre fundo claro"


def test_cor_invalida_nao_derruba_a_tela():
    for ruim in ("", "#zzz", "nao-e-cor", "#12"):
        assert visivel(camisa(ruim, ruim, "70", cor=True)[0]) == LARGURA


def test_a_legenda_cabe_na_camisa():
    assert len(legenda("Neymar")) == LARGURA
    assert len(legenda("Benjamín Rollheiser")) == LARGURA
    # nome comprido encolhe para o ultimo sobrenome antes de ser cortado no meio
    assert "Rollheiser" in legenda("Benjamín Rollheiser")


def test_o_campo_fecha_as_bordas(carreira):
    """REGRESSAO: o nome podia crescer ate a celula inteira e ficava mais largo que o
    desenho, desencostando a coluna."""
    saida = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(saida):
        _desenhar_campo(carreira, carreira.escalacao_atual(), carreira.tatica_atual())
    linhas = [ln for ln in ANSI.sub("", saida.getvalue()).splitlines() if ln.strip()]
    larguras = {len(ln) for ln in linhas}
    assert len(larguras) == 1, f"o campo saiu com larguras diferentes: {sorted(larguras)}"
    for ln in linhas[1:-1]:
        assert ln.lstrip().startswith("|") and ln.rstrip().endswith("|")


def test_o_campo_mostra_os_onze_com_posicao_e_energia(carreira):
    saida = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(saida):
        _desenhar_campo(carreira, carreira.escalacao_atual(), carreira.tatica_atual())
    texto = ANSI.sub("", saida.getvalue())
    onze = [carreira.world.players[i] for i in carreira.escalacao_atual()]
    for p in onze:
        assert legenda(p.name).strip() in texto, f"{p.name} sumiu do campo"
    assert texto.count("%") == 11, "faltou energia de alguem"
    for grupo in ("GK", "DF", "MF", "FW"):
        assert grupo in texto


def test_o_goleiro_veste_outra_cor(carreira):
    """Regra do futebol, e ajuda a ler o campo de relance."""
    saida = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(saida):
        _desenhar_campo(carreira, carreira.escalacao_atual(), carreira.tatica_atual())
    linhas = saida.getvalue().splitlines()
    gol = next(i for i, ln in enumerate(linhas) if "gol" in ln)
    ataque = next(i for i, ln in enumerate(linhas) if "ataque" in ln)
    assert linhas[gol] != linhas[ataque]
