"""Catalogo de competicoes do Transfermarkt.

A lista de ligas e DADO, nao constante digitada a mao: o site agrupa as competicoes de
cada continente por divisao, e daqui sai codigo, nome, pais, nivel, numero de clubes e
valor total. Com isso se escolhe o que importar por regra (ate a segunda divisao, Asia so
a primeira) em vez de por lista manual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from fm.importer.http import get

CONTINENTES = ("europa", "amerika", "asien", "afrika")

# Cabecalhos de secao da tabela -> nivel da divisao.
NIVEL = {
    "primeira divisão": 1, "primeira divisao": 1,
    "segunda divisão": 2, "segunda divisao": 2,
    "terceira divisão": 3, "terceira divisao": 3,
    "quarta divisão": 4, "quarta divisao": 4,
}


@dataclass(slots=True)
class Competicao:
    codigo: str
    nome: str
    pais: str
    continente: str
    nivel: int
    clubes: int
    jogadores: int
    valor_total: int

    @property
    def paginas(self) -> int:
        """Quantas paginas o importador vai buscar: 1 da liga + 2 por clube."""
        return 1 + 2 * self.clubes


def _valor(txt: str) -> int:
    m = re.search(r"([\d.,]+)\s*(mil|mi|bi)", txt or "", re.I)
    if not m:
        return 0
    num = float(m.group(1)) if re.fullmatch(r"\d+\.\d{2}", m.group(1)) \
        else float(m.group(1).replace(".", "").replace(",", "."))
    return int(num * {"mil": 1e3, "mi": 1e6, "bi": 1e9}[m.group(2).lower()])


def _paginas_do_continente(html: str) -> int:
    return max(
        [1] + [int(m) for m in re.findall(r"\?page=(\d+)", html)])


def baixar_pagina(continente: str, pagina: int) -> str:
    sufixo = "" if pagina == 1 else f"?page={pagina}"
    return get(f"https://www.transfermarkt.com.br/wettbewerbe/{continente}{sufixo}",
               f"tm/cat_{continente}" + ("" if pagina == 1 else f"_p{pagina}") + ".html",
               delay=1.5)


def extrair(html: str, continente: str) -> list[Competicao]:
    sopa = BeautifulSoup(html, "lxml")
    tabela = sopa.select_one("table.items")
    if tabela is None:
        return []
    saida, nivel_atual = [], 1
    for tr in tabela.select("tbody > tr"):
        texto = tr.get_text(" ", strip=True).strip().lower()
        link = tr.select_one("a[href*='/wettbewerb/']")
        if link is None:
            if texto in NIVEL:                     # linha de cabecalho de secao
                nivel_atual = NIVEL[texto]
            continue
        cod = re.search(r"/wettbewerb/([A-Z0-9]+)", link["href"])
        if cod is None:
            continue
        cels = [td.get_text(" ", strip=True) for td in tr.find_all("td", recursive=False)]
        cels = [c for c in cels if c]
        numeros = [c for c in cels if re.fullmatch(r"[\d.]+", c.strip())]
        bandeira = tr.select_one("img.flaggenrahmen")
        saida.append(Competicao(
            codigo=cod.group(1),
            nome=(link.get("title") or link.get_text(strip=True)
                  or (cels[0] if cels else "")).strip(),
            pais=(bandeira.get("title") if bandeira else "") or "",
            continente=continente, nivel=nivel_atual,
            clubes=int(numeros[0]) if numeros else 0,
            jogadores=int(numeros[1].replace(".", "")) if len(numeros) > 1 else 0,
            valor_total=_valor(cels[-1] if cels else "")))
    return saida


def catalogo_completo() -> list[Competicao]:
    todas: list[Competicao] = []
    for cont in CONTINENTES:
        primeira = baixar_pagina(cont, 1)
        n = _paginas_do_continente(primeira)
        todas += extrair(primeira, cont)
        for p in range(2, n + 1):
            todas += extrair(baixar_pagina(cont, p), cont)
    vistos, unicas = set(), []
    for c in todas:
        if c.codigo not in vistos:
            vistos.add(c.codigo)
            unicas.append(c)
    return unicas


# O catalogo mistura copa, campeonato estadual e categoria de base com liga nacional, e o
# "nivel" que ele mostra e a secao da PAGINA, nao o degrau real da piramide: o Campeonato
# Paulista (128 clubes) aparece como nivel 1 e a Serie D como nivel 4. Por isso a selecao
# nao pode ser so por nivel.
PADRAO_NAO_LIGA = re.compile(
    r"copa|copinha|cup|coupe|beker|kypello|pokal|cupa|kup|taça|taca|supercopa|"
    r"super cup|campeón de campeones|campeon de campeones|fase final|play-?off|"
    r"sub-?\d|u-?\d\d|youth|juvenil|júnior|junior|feminin|women|amateur|amador|"
    r"reserve|reserva|promo|relegation|estadual|regional|interior|"
    r"paulista|carioca|mineiro|gaúcho|gaucho|baiano|pernambucano|paranaense|paraense|"
    r"catarinense|goiano|cearense|potiguar|sergipano|alagoano|paraibano|piauiense|"
    r"maranhense",
    re.I)

# Preferencia dentro de um par de turnos: Apertura e o turno de abertura, entao fica ele.
# NAO se exclui Apertura/Clausura por nome -- isso apagava a primeira divisao inteira da
# Argentina, do Mexico, do Uruguai, da Colombia e do Paraguai, e sobrava so a segunda.
ORDEM_TURNO = ("apertura", "dimayor i", "primera división apertura")
PENALIZA_TURNO = ("clausura", "intermedio", "dimayor ii", " ii")


def _rank_turno(c: Competicao) -> int:
    # PENALIZA antes de ORDEM, senao "dimayor ii" casa com "dimayor i" por substring
    nome = (c.nome or "").lower()
    if any(t in nome for t in PENALIZA_TURNO):
        return 2
    if any(t in nome for t in ORDEM_TURNO):
        return 0
    return 1


def deduplicar_turnos(comps: list[Competicao]) -> list[Competicao]:
    """Apertura e Clausura sao a MESMA liga contada duas vezes: mesmos clubes, mesmo valor.

    Importar as duas duplicaria cada clube no mundo. Agrupa por pais + nivel + numero de
    clubes + valor total e fica com um turno so.
    """
    grupos: dict[tuple, list] = {}
    for c in comps:
        grupos.setdefault((c.pais, c.nivel, c.clubes, c.valor_total), []).append(c)
    return [sorted(g, key=_rank_turno)[0] for g in grupos.values()]


def e_liga_nacional(c: Competicao) -> bool:
    """Copa, estadual, base e turno isolado (Apertura/Clausura) nao sao liga nacional.

    Filtrar por nome e fragil e por isso NAO basta: o catalogo tem 789 competicoes e a
    unica selecao confiavel e uma lista curada de paises. Isto so tira o lixo obvio.
    """
    return not PADRAO_NAO_LIGA.search(c.nome or "")


def selecionar(
    todas: list[Competicao], *, valor_minimo: float = 0.0,
    codigos_extra: tuple[str, ...] = (),
) -> list[Competicao]:
    """Escolhe o que importar.

    `valor_minimo` filtra por valor total de elenco da liga -- e o unico sinal de
    relevancia que o catalogo oferece. `codigos_extra` entra de qualquer jeito, para as
    divisoes que se quer inteiras mesmo sendo pobres (Serie C e D do Brasil).
    """
    escolhidas = [
        c for c in todas
        if c.clubes >= 8
        and c.nivel <= (1 if c.continente == "asien" else 2)
        and c.valor_total >= valor_minimo
        and e_liga_nacional(c)
    ]
    ja = {c.codigo for c in escolhidas}
    escolhidas += [c for c in todas if c.codigo in codigos_extra and c.codigo not in ja]
    return escolhidas
