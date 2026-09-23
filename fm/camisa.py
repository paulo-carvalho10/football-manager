"""A camisa do clube desenhada no terminal, nas cores dele.

Isto e apresentacao pura: devolve linhas de texto e nao imprime nada, entao continua
valendo a regra de que so cli.py e jogo.py falam com a tela.

A cor importa mais do que parece. Ver o proprio elenco escalado com a camisa do clube e o
que faz a tela ser SUA e nao uma planilha -- e pintar o Corinthians de verde, a cor do
rival, e pior do que nao pintar nada.
"""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"

# A silhueta, em 11 colunas: tres de manga, cinco de tronco, tres de manga. Abaixo dos
# ombros as mangas acabam e sobra so o tronco, que e como uma camisa e.
LARGURA = 11
MANGA, TRONCO = 3, 5


def suporta_cor() -> bool:
    """Cor verdadeira so quando ha um terminal de verdade do outro lado.

    Respeita NO_COLOR (a convencao) e desliga sozinho quando a saida esta sendo
    redirecionada para arquivo ou pipe -- e onde os codigos ANSI viram lixo.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FM_COR") == "1":
        return True
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _rgb(hexa: str) -> tuple[int, int, int]:
    h = (hexa or "#888888").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 136, 136, 136


def _luminancia(rgb: tuple[int, int, int]) -> float:
    r, g, b = (v / 255 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sobre(fundo: tuple[int, int, int]) -> tuple[int, int, int]:
    """Preto ou branco, o que ler melhor em cima desta cor."""
    return (17, 17, 17) if _luminancia(fundo) > 0.55 else (240, 240, 240)


def _pinta(texto: str, fundo: tuple[int, int, int],
           frente: tuple[int, int, int] | None = None) -> str:
    f = frente or _sobre(fundo)
    return (f"\033[48;2;{fundo[0]};{fundo[1]};{fundo[2]}m"
            f"\033[38;2;{f[0]};{f[1]};{f[2]}m{texto}{RESET}")


def camisa(primaria: str, secundaria: str, numero: str = "",
           cor: bool | None = None) -> list[str]:
    """Tres linhas de 11 colunas: ombros com gola, peito e tronco.

    `numero` vai no peito -- aqui e o overall, que e o que o jogador quer ler de relance.
    """
    usar_cor = suporta_cor() if cor is None else cor
    corpo, detalhe = _rgb(primaria), _rgb(secundaria)
    peito = f"{numero:^{TRONCO}}"[:TRONCO]

    if not usar_cor:
        # Sem cor a silhueta tem de se ler sozinha: contorno em ASCII, mesmas 11 colunas.
        gola_seca = ("-" * TRONCO)[:TRONCO // 2] + "v" + ("-" * TRONCO)[TRONCO // 2 + 1:]
        return ["  ." + gola_seca + ".  ",
                "|_|" + " " * TRONCO + "|_|",
                "  |" + peito + "|  "]

    gola = " " * ((TRONCO - 1) // 2) + "v" + " " * (TRONCO // 2)
    return [
        _pinta(" " * MANGA, detalhe) + _pinta(gola[:TRONCO], corpo, _sobre(corpo))
        + _pinta(" " * MANGA, detalhe),
        _pinta(" " * MANGA, detalhe) + _pinta(" " * TRONCO, corpo)
        + _pinta(" " * MANGA, detalhe),
        " " * MANGA + _pinta(peito, corpo) + " " * MANGA,
    ]


def legenda(nome: str, largura: int = LARGURA) -> str:
    """O nome embaixo da camisa, encurtado ate caber sem empurrar a coluna ao lado."""
    if len(nome) > largura:
        partes = nome.split()
        nome = partes[-1] if len(partes[-1]) <= largura else nome[:largura - 1] + "."
    return nome.center(largura)[:largura]
