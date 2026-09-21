"""Transfermarkt: posicao, idade, valor de mercado e valor total de elenco.

robots.txt do site permite (`User-agent: *` -> `Allow: /`). Ainda assim, uma requisicao por
clube com intervalo de 1,5 s e tudo cacheado em disco: 21 paginas no total, uma vez.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from bs4 import BeautifulSoup

from fm.importer.http import get

BASE = "https://www.transfermarkt.com.br"

# Competicoes suportadas: slug da URL + codigo do site + pais no modelo.
COMPETICOES = {
    "bra_a": ("campeonato-brasileiro-serie-a", "BRA1", "BRA"),
    "bra_b": ("campeonato-brasileiro-serie-b", "BRA2", "BRA"),
    "esp_1": ("laliga", "ES1", "ESP"),
    "esp_2": ("laliga2", "ES2", "ESP"),
}

# Temporada de onde tirar minutos jogados. As ligas nao estao no mesmo ponto do calendario:
# em setembro de 2026 o Brasileirao (ano civil) ja tinha 30 a 45 jogos, e as europeias
# (agosto a maio) tinham 5 rodadas. Cinco rodadas nao dizem nada sobre quem e titular,
# entao para a Europa usa-se a temporada ANTERIOR, ja completa.
TEMPORADA_STATS = {"esp_1": "2025", "esp_2": "2025"}

# Siglas de tipo de clube que nao fazem parte do nome. "Real" NAO entra: Real Madrid,
# Real Betis e Real Sociedad sao nomes de verdade.
SIGLAS = {
    "CR", "SE", "SC", "EC", "FC", "CF", "UD", "CD", "RC", "RCD", "SD", "CA", "FR",
    "AD", "AC", "AS", "SS", "CS", "FBPA", "SAF", "B", "II",
}

# Nomes que a limpeza automatica erraria.
NOME_ESPECIAL = {
    "RB Bragantino": "Red Bull Bragantino",
    "Clube do Remo": "Remo",
    "Atlético de Madrid": "Atlético Madrid",
    "Athletic Bilbao": "Athletic Club",
    "Real Betis Balompié": "Real Betis",
    "RC Celta de Vigo": "Celta de Vigo",
    "Deportivo Alavés": "Alavés",
    "Deportivo de La Coruña": "Deportivo La Coruña",
}


def limpar_nome(nome: str) -> str:
    """Tira as siglas de tipo de clube das pontas: 'SE Palmeiras' -> 'Palmeiras'."""
    nome = nome.replace(" ", " ").replace("&nbsp;", " ").strip()
    if nome in NOME_ESPECIAL:
        return NOME_ESPECIAL[nome]
    partes = nome.split()
    while len(partes) > 1 and partes[0].upper().strip(".") in SIGLAS:
        partes.pop(0)
    while len(partes) > 1 and partes[-1].upper().strip(".") in SIGLAS:
        partes.pop()
    limpo = " ".join(partes)
    return NOME_ESPECIAL.get(limpo, limpo)

# Rotulos de posicao do site -> grupos de premio de valor (ver fm/ratings.py).
POSICAO_MAP = {
    "goleiro": "GK",
    "zagueiro": "CB",
    "lateral dir.": "FB", "lateral esq.": "FB",
    "lateral-direito": "FB", "lateral direito": "FB",
    "lateral-esquerdo": "FB", "lateral esquerdo": "FB",
    "volante": "DM",
    "meia central": "MF", "meio-campo central": "MF", "meio-campista central": "MF",
    "meia ofensivo": "AM", "meia-atacante": "AM", "meio-campo ofensivo": "AM",
    "meia direita": "AM", "meia esquerda": "AM",
    "ponta direita": "WG", "ponta-direita": "WG",
    "ponta esquerda": "WG", "ponta-esquerda": "WG",
    "centroavante": "FW", "atacante": "FW", "seg. atacante": "FW", "segundo atacante": "FW",
}


@dataclass(slots=True)
class TMClube:
    nome: str
    verein_id: str
    valor_elenco: int
    jogadores_no_plantel: int
    idade_media: float


@dataclass(slots=True)
class TMJogador:
    nome: str
    spieler_id: str
    posicao: str | None       # grupo (GK/CB/FB/DM/MF/AM/WG/FW)
    posicao_site: str
    idade: int | None
    valor: int | None
    nacionalidade: str | None
    contrato_ate: str | None
    camisa: str | None


def normalizar(nome: str) -> str:
    """Chave de casamento entre fontes: sem acento, sem pontuacao, minusculo."""
    n = unicodedata.normalize("NFKD", nome)
    n = "".join(c for c in n if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", n.lower()).strip()


def parse_valor(texto: str) -> int | None:
    """'€ 7.00 mi.' -> 7000000 | '€ 75 mil' -> 75000 | '-' -> None."""
    t = texto.replace("\xa0", " ").strip()
    m = re.search(r"([\d.,]+)\s*(mil|mi|bi)\b", t, re.I)   # mil ANTES de mi
    if not m:
        return None
    num = float(m.group(1).replace(".", "").replace(",", ".")) if "," in m.group(1) \
        else float(m.group(1))
    fator = {"mil": 1_000, "mi": 1_000_000, "bi": 1_000_000_000}[m.group(2).lower()]
    # '7.00 mi' -> o ponto e decimal; '1.970 mil' -> o ponto e milhar. Heuristica: se ha
    # exatamente 2 casas depois do ponto, e decimal.
    if re.fullmatch(r"\d+\.\d{2}", m.group(1)):
        num = float(m.group(1))
    return int(round(num * fator))


def baixar_liga(slug: str = "campeonato-brasileiro-serie-a", wettbewerb: str = "BRA1") -> str:
    url = f"{BASE}/{slug}/startseite/wettbewerb/{wettbewerb}"
    return get(url, f"tm/liga_{wettbewerb}.html", delay=1.5)


def baixar_competicao(chave: str) -> str:
    slug, wettbewerb, _ = COMPETICOES[chave]
    return baixar_liga(slug, wettbewerb)


def extrair_clubes(html: str) -> list[TMClube]:
    sopa = BeautifulSoup(html, "lxml")
    tabela = sopa.select_one("table.items")
    if tabela is None:
        raise RuntimeError("tabela de clubes nao encontrada na pagina da liga")
    clubes: list[TMClube] = []
    for tr in tabela.select("tbody > tr"):
        a = tr.select_one("a[href*='/startseite/verein/']")
        if a is None:
            continue
        tds = tr.find_all("td", recursive=False)
        cels = [td.get_text(" ", strip=True) for td in tds]
        vid = re.search(r"/startseite/verein/(\d+)", a["href"]).group(1)
        nome = (a.get("title") or a.get_text(strip=True)).replace("\xa0", "").strip()
        if any(c.verein_id == vid for c in clubes):
            continue
        # colunas: ['', nome, plantel, idade media, estrangeiros, valor medio, valor total]
        numeros = [c for c in cels if re.fullmatch(r"[\d.,]+", c.strip())]
        clubes.append(TMClube(
            nome=nome, verein_id=vid,
            valor_elenco=parse_valor(cels[-1]) or 0,
            jogadores_no_plantel=int(numeros[0]) if numeros else 0,
            idade_media=float(numeros[1].replace(",", ".")) if len(numeros) > 1 else 0.0))
    return clubes


def baixar_elenco(verein_id: str) -> str:
    url = f"{BASE}/clube/kader/verein/{verein_id}"
    return get(url, f"tm/elenco_{verein_id}.html", delay=1.5)


ROTULOS_DESCONHECIDOS: set[str] = set()   # rotulo novo do site nao pode passar calado


def extrair_elenco(html: str) -> list[TMJogador]:
    sopa = BeautifulSoup(html, "lxml")
    tabela = sopa.select_one("table.items")
    if tabela is None:
        return []
    jogadores: list[TMJogador] = []
    for tr in tabela.select("tbody > tr"):
        classes = tr.get("class") or []
        if not classes or classes[0] not in ("odd", "even"):
            continue
        a = tr.select_one("td.hauptlink a[href*='/profil/spieler/']") \
            or tr.select_one("a[href*='/profil/spieler/']")
        if a is None:
            continue
        tds = tr.find_all("td", recursive=False)
        cels = [td.get_text(" ", strip=True) for td in tds]
        pos_td = tr.select_one("table.inline-table tr:nth-of-type(2) td")
        pos_site = pos_td.get_text(strip=True) if pos_td else ""
        if pos_site and pos_site.lower() not in POSICAO_MAP:
            ROTULOS_DESCONHECIDOS.add(pos_site)
        # colunas do plantel: [camisa, nome+posicao, idade, nacionalidade, contrato, valor]
        # A idade e a coluna 2. Varrer as celulas procurando "2 digitos" pegava o numero da
        # CAMISA (o 21 do Bertinato virava idade 21 em vez de 28).
        idade = None
        if len(cels) > 2 and re.fullmatch(r"\d{2}", cels[2].strip()):
            v = int(cels[2])
            if 15 <= v <= 50:
                idade = v
        bandeiras = [img.get("title") for img in tr.select("img.flaggenrahmen") if img.get("title")]
        contrato = next(
            (c for c in cels if re.fullmatch(r"\d{2}/\d{2}/\d{4}", c.strip())), None)
        sid = re.search(r"/profil/spieler/(\d+)", a["href"]).group(1)
        jogadores.append(TMJogador(
            nome=a.get_text(strip=True), spieler_id=sid,
            posicao=POSICAO_MAP.get(pos_site.lower()), posicao_site=pos_site,
            idade=idade, valor=parse_valor(cels[-1]),
            nacionalidade=bandeiras[0] if bandeiras else None,
            contrato_ate=contrato, camisa=cels[0] if cels and cels[0].strip() else None))
    return jogadores


def baixar_estatisticas(verein_id: str, temporada: str | None = None) -> str:
    """Desempenho da temporada. Join por spieler_id: sem casar nomes entre fontes."""
    if temporada:
        url = f"{BASE}/clube/leistungsdaten/verein/{verein_id}/plus/1/saison_id/{temporada}"
        return get(url, f"tm/stats_{verein_id}_{temporada}.html", delay=1.5)
    url = f"{BASE}/clube/leistungsdaten/verein/{verein_id}"
    return get(url, f"tm/stats_{verein_id}.html", delay=1.5)


def extrair_estatisticas(html: str) -> dict[str, dict[str, int]]:
    """{spieler_id: {jogos, gols, minutos}}.

    A visao simples tem 8 colunas e a detalhada (plus/1, usada para temporada passada) tem
    15. Jogos e gols ficam nos indices 5 e 6 nas duas, e minutos e sempre a ULTIMA coluna
    -- por isso cels[-1], e nao um indice fixo.
    """
    sopa = BeautifulSoup(html, "lxml")
    tabela = sopa.select_one("table.items")
    if tabela is None:
        return {}

    def num(txt: str) -> int:
        d = re.sub(r"[^\d]", "", txt or "")
        return int(d) if d else 0

    saida: dict[str, dict[str, int]] = {}
    for tr in tabela.select("tbody > tr"):
        a = tr.select_one("a[href*='/profil/spieler/']")
        if a is None:
            continue
        cels = [td.get_text(" ", strip=True) for td in tr.find_all("td", recursive=False)]
        if len(cels) < 8:
            continue
        sid = re.search(r"/profil/spieler/(\d+)", a["href"]).group(1)
        saida[sid] = {"jogos": num(cels[5]), "gols": num(cels[6]),
                      "minutos": num(cels[-1])}
    return saida
