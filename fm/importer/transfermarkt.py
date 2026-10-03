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
    # as ligas da versao completa (28/09/2026). Todas ja estavam no cache desde a
    # importacao das 59 ligas; faltava transforma-las em pack.
    "eng_1": ("premier-league", "GB1", "ENG"),
    "eng_2": ("championship", "GB2", "ENG"),
    "ita_1": ("serie-a", "IT1", "ITA"),
    "ita_2": ("serie-b", "IT2", "ITA"),
    "ger_1": ("bundesliga", "L1", "GER"),
    "ger_2": ("2-bundesliga", "L2", "GER"),
    "fra_1": ("ligue-1", "FR1", "FRA"),
    "fra_2": ("ligue-2", "FR2", "FRA"),
    "por_1": ("liga-portugal", "PO1", "POR"),
    "por_2": ("liga-portugal-2", "PO2", "POR"),
    "arg_1": ("liga-profesional-de-futbol", "ARG1", "ARG"),
    "arg_2": ("primera-nacional", "ARG2", "ARG"),
    # a America do Sul para a Libertadores (30/09/2026): so as primeiras divisoes. Os
    # codigos sao os do Apertura, que e a liga que o site lista com o elenco inteiro.
    "col_1": ("liga-dimayor-i", "COLP", "COL"),
    "chi_1": ("liga-de-primera", "CLPD", "CHI"),
    "uru_1": ("liga-auf-apertura", "URU1", "URU"),
    "ecu_1": ("ligapro-serie-a", "EC1N", "ECU"),
    "par_1": ("primera-division-apertura", "PR1A", "PAR"),
    "per_1": ("liga-1-apertura", "TDeA", "PER"),
    "bol_1": ("division-profesional", "BO1A", "BOL"),
    "ven_1": ("liga-futve-apertura", "VZ1A", "VEN"),
    # o resto da Europa para a Champions e a Liga Europa (03/10/2026): so as primeiras
    # divisoes. Quase todas ja estavam no cache desde a importacao das 59 ligas.
    "ned_1": ("eredivisie", "NL1", "NED"),
    "bel_1": ("jupiler-pro-league", "BE1", "BEL"),
    "tur_1": ("super-lig", "TR1", "TUR"),
    "gre_1": ("super-league-1", "GR1", "GRE"),
    "ukr_1": ("premier-liga", "UKR1", "UKR"),
    "rus_1": ("premier-liga", "RU1", "RUS"),
    "aut_1": ("bundesliga", "A1", "AUT"),
    "sui_1": ("super-league", "C1", "SUI"),
    "sco_1": ("scottish-premiership", "SC1", "SCO"),
    "den_1": ("superligaen", "DK1", "DEN"),
    "nor_1": ("eliteserien", "NO1", "NOR"),
    "swe_1": ("allsvenskan", "SE1", "SWE"),
    "srb_1": ("super-liga-srbije", "SER1", "SRB"),
    "cro_1": ("supersport-hnl", "KR1", "CRO"),
    "pol_1": ("pko-bp-ekstraklasa", "PL1", "POL"),
    "cze_1": ("chance-liga", "TS1", "CZE"),
}

# Temporada de onde tirar minutos jogados. As ligas nao estao no mesmo ponto do calendario:
# em setembro de 2026 o Brasileirao (ano civil) ja tinha 30 a 45 jogos, e as europeias
# (agosto a maio) tinham 5 rodadas. Cinco rodadas nao dizem nada sobre quem e titular,
# entao para a Europa usa-se a temporada ANTERIOR, ja completa.
TEMPORADA_STATS = {c: "2025" for c in ("esp_1", "esp_2", "eng_1", "eng_2", "ita_1", "ita_2",
                                        "ger_1", "ger_2", "fra_1", "fra_2", "por_1", "por_2",
                                        "ned_1", "bel_1", "tur_1", "gre_1", "ukr_1", "rus_1",
                                        "aut_1", "sui_1", "sco_1", "den_1", "srb_1", "cro_1",
                                        "pol_1", "cze_1")}
# Noruega e Suecia jogam no ano civil, como o Brasil: a temporada atual ja diz tudo.
# A Argentina joga no ano civil, como o Brasil: em setembro a temporada atual ja diz tudo.

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
    # America do Sul (30/09/2026): o nome como se fala no Brasil, e sem colidir com o
    # clube de mesmo nome de outro pais (Everton, Barcelona, Liverpool, Catolica)
    "Millonarios Bogotá": "Millonarios",
    "Atletico Bucaramanga": "Atlético Bucaramanga",
    "Rionegro Águilas": "Águilas Doradas",
    "Alianza": "Alianza Valledupar",
    "CSD Colo-Colo": "Colo-Colo",
    "Everton": "Everton de Viña",
    "Union La Calera": "Unión La Calera",
    "Club Nacional": "Nacional de Montevideo",   # o "Nacional" e o portugues
    "Defensor Sporting Club": "Defensor Sporting",
    "Liverpool FC Montevideo": "Liverpool Montevideo",
    "Racing Club de Montevideo": "Racing Montevideo",
    "Club Deportivo Maldonado": "Deportivo Maldonado",
    "Danubio Montevideo": "Danubio",
    "Barcelona SC Guayaquil": "Barcelona de Guayaquil",
    "Libertad": "Libertad de Loja",
    "Club Olimpia": "Olimpia",
    "Club Cerro Porteño": "Cerro Porteño",
    "Club Libertad Asuncion": "Libertad",
    "Club Guaraní": "Guaraní de Asunción",
    "Club Nacional Asunción": "Nacional Asunción",
    "Club Sportivo Trinidense": "Sportivo Trinidense",
    "Club Sportivo 2 de Mayo": "2 de Mayo",
    "Club Rubio Ñú (Asuncion)": "Rubio Ñu",
    "Club Sportivo San Lorenzo": "Sportivo San Lorenzo",
    "Universitario de Deportes": "Universitario",
    "Club Alianza Lima": "Alianza Lima",
    "Club Sporting Cristal": "Sporting Cristal",
    "FBC Melgar": "Melgar",
    "Cusco": "Cusco FC",
    "Club Cienciano": "Cienciano",
    "Sport Boys Association": "Sport Boys",
    "Alianza Atlético Sullana": "Alianza Atlético",
    "Club Juan Pablo II College": "Juan Pablo II",
    "Asociación Deportiva Tarma": "ADT Tarma",
    "Club Atlético Grau": "Atlético Grau",
    "Universidad Técnica de Cajamarca": "UTC Cajamarca",
    "Bolívar La Paz": "Bolívar",
    "Blooming Santa Cruz": "Blooming",
    "Club The Strongest": "The Strongest",
    "Club Deportivo Oriente Petrolero": "Oriente Petrolero",
    "Club Deportivo Guabirá": "Guabirá",
    "Club Always Ready": "Always Ready",
    "Club A.B.B.": "ABB",
    "Gualberto Villarroel San José": "San José",
    "Club Aurora": "Aurora",
    "Real Potosi": "Real Potosí",
    "Club Independiente Petrolero": "Independiente Petrolero",
    "Dvo. Rayo Zuliano": "Rayo Zuliano",
    "Zamora Futbol Club": "Zamora",
    "Universidad Central de Venezuela": "UCV",
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


def baixar_por_codigo(codigo: str) -> str:
    """Pagina da liga por codigo do Transfermarkt, sem precisar do slug do nome."""
    return get(f"{BASE}/liga/startseite/wettbewerb/{codigo}", f"tm/liga_{codigo}.html",
               delay=1.5)


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
