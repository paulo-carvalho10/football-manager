"""A camisa do clube desenhada no terminal, nas cores e no padrao dele.

Isto e apresentacao pura: devolve linhas de texto e nao imprime nada, entao continua
valendo a regra de que so cli.py e jogo.py falam com a tela.

O desenho e uma MATRIZ DE PIXELS, nao caracteres escolhidos a mao. Cada linha de texto
carrega dois pixels -- o de cima no caractere meio-bloco `U+2580`, o de baixo na cor de
fundo -- o que dobra a resolucao vertical e e o que permite a silhueta ter ombro, manga e
barra em vez de ser um retangulo. Com isso o padrao do clube aparece: as listras do Gremio,
os aros do Flamengo, a faixa diagonal do Vasco.

A cor importa mais do que parece. Ver o proprio elenco escalado com a camisa do clube e o
que faz a tela ser SUA e nao uma planilha -- e pintar o Corinthians de verde, a cor do
rival, e pior do que nao pintar nada.
"""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"
MEIO = "▀"          # meio-bloco superior: frente = pixel de cima, fundo = o de baixo

# A silhueta em pixels. Onze colunas de largura -- o que cabe com cinco zagueiros numa
# fileira de 78 -- e seis de altura, desenhadas em tres linhas de texto.
LARGURA, ALTURA = 11, 6
MANGA, TRONCO = 2, 7     # duas colunas de manga de cada lado, sete de tronco

Cor = tuple[int, int, int]
Pixel = Cor | None       # None = fora da camisa, o fundo do terminal aparece

PADROES = ("liso", "listras", "aros", "faixa", "diagonal")


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


def _rgb(hexa: str) -> Cor:
    h = (hexa or "#888888").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 136, 136, 136


GOLA = MANGA + TRONCO // 2


def _e_tronco(x: int) -> bool:
    return MANGA <= x < MANGA + TRONCO


def _e_manga(x: int, y: int) -> bool:
    """A manga: cheia no ombro e afunilando um pixel, que e o que lhe da forma.

    Sem o afunilamento a camisa vira um T de ombro reto -- parece um simbolo, nao uma
    camisa.
    """
    if _e_tronco(x):
        return False
    if y <= 1:
        return True
    return y == 2 and x in (MANGA - 1, MANGA + TRONCO)


def _dentro(x: int, y: int) -> bool:
    """A silhueta: onde ha pano."""
    if _e_manga(x, y):
        return True
    if not _e_tronco(x):
        return False
    return y > 0 or abs(x - GOLA) > 1      # em cima, o entalhe da gola


def _cor_do_pano(x: int, y: int, padrao: str, corpo: Cor, detalhe: Cor) -> Cor:
    """O padrao do clube, resolvido pixel a pixel."""
    if padrao == "listras":                       # verticais: Gremio, Botafogo, Coritiba
        return corpo if ((x - MANGA) // 2) % 2 == 0 else detalhe
    if padrao == "aros":                          # horizontais e estreitos: Flamengo
        return corpo if y % 2 == 0 else detalhe
    if padrao == "faixa":                         # uma faixa no peito: Sao Paulo
        return detalhe if y in (2, 3) else corpo
    if padrao == "diagonal":                       # a faixa do Vasco e do Bahia
        return detalhe if 0 <= (x - MANGA) + y - 3 <= 2 else corpo
    return corpo


def _matriz(primaria: str, secundaria: str, padrao: str) -> list[list[Pixel]]:
    corpo, detalhe = _rgb(primaria), _rgb(secundaria)
    grade: list[list[Pixel]] = []
    for y in range(ALTURA):
        linha: list[Pixel] = []
        for x in range(LARGURA):
            if not _dentro(x, y):
                linha.append(None)
            elif _e_manga(x, y):
                linha.append(detalhe)
            else:
                linha.append(_cor_do_pano(x, y, padrao, corpo, detalhe))
            # a gola: so os ombros que sobram ao lado do entalhe, nunca a fileira toda --
            # pintar o ombro inteiro de detalhe fazia a camisa parecer uma ombreira
            if (y == 0 and _e_tronco(x) and abs(x - GOLA) <= 2
                    and linha[-1] is not None):
                linha[-1] = detalhe
        grade.append(linha)
    return grade


def _desenhar(grade: list[list[Pixel]]) -> list[str]:
    """Duas linhas de pixel por linha de texto, via meio-bloco."""
    linhas = []
    for y in range(0, len(grade), 2):
        cima, baixo = grade[y], grade[y + 1]
        fora, atual = [], None
        for x in range(LARGURA):
            c, b = cima[x], baixo[x]
            if c is None and b is None:
                fora.append(RESET + " " if atual else " ")
                atual = None
                continue
            frente = c or (0, 0, 0)
            codigo = f"\033[38;2;{frente[0]};{frente[1]};{frente[2]}m"
            codigo += (f"\033[48;2;{b[0]};{b[1]};{b[2]}m" if b else "\033[49m")
            fora.append(codigo + (MEIO if c else " "))
            atual = True
        linhas.append("".join(fora) + RESET)
    return linhas


def camisa(primaria: str, secundaria: str, padrao: str = "liso",
           cor: bool | None = None) -> list[str]:
    """A camisa do clube: tres linhas de texto, onze colunas de largura.

    O overall NAO vai aqui dentro. Numero no peito disputa espaco com o padrao e some numa
    camisa listrada; embaixo, junto de posicao e energia, ele se le sempre.
    """
    if (suporta_cor() if cor is None else cor):
        return _desenhar(_matriz(primaria, secundaria, padrao))
    # Sem cor a silhueta tem de se ler sozinha: contorno em ASCII, mesmas 11 colunas.
    marca = {"listras": "|", "aros": "=", "faixa": "-", "diagonal": "/"}.get(padrao, " ")
    return ["  ." + "-" * (TRONCO - 2) + ".  ",
            "|_|" + marca * (TRONCO - 2) + "|_|",
            "  |" + marca * (TRONCO - 2) + "|  "]


def legenda(nome: str, largura: int = LARGURA) -> str:
    """O nome embaixo da camisa, encurtado ate caber sem empurrar a coluna ao lado."""
    if len(nome) > largura:
        partes = nome.split()
        nome = partes[-1] if len(partes[-1]) <= largura else nome[:largura - 1] + "."
    return nome.center(largura)[:largura]
