"""Importa as camisas dos clubes da Wikimedia Commons e as guarda como SVG.

De onde vem. A Commons hospeda as camisas que a Wikipedia usa nos infoboxes de temporada,
com API aberta e nome padronizado: `Kit_body_flamengo26h.png` e a camisa 1 de 2026,
`Kit_body_corinthians2526a.png` e a 2 de 2025/26. Sao tres camadas -- manga esquerda,
corpo, manga direita -- de 38x59 pixels cada.

Por que SVG e nao o PNG. Ampliado, o sprite vira uma escada, e ainda carrega o ruido de
quem o desenhou. Vetorizado (fm/importer/vetor.py) ele escala para qualquer tamanho, sai
com as cores chapadas e fica mais limpo que o original.

Licenca: varia por arquivo -- vi CC0 e CC BY-SA 4.0 no mesmo campeonato. Autor e licenca
sao gravados no indice ao lado de cada camisa. Nao e' burocracia: sem isso a informacao se
perde, e ai nao da para distribuir o jogo sem refazer a importacao inteira.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
CAMISAS_DIR = RAIZ / "data" / "camisas"
APELIDOS = RAIZ / "data" / "camisas" / "apelidos.toml"

API = "https://commons.wikimedia.org/w/api.php"
# A Wikimedia pede um User-Agent que identifique a ferramenta. Ela tambem devolve 429
# com facilidade, e ai o jeito e esperar o Retry-After, nao insistir.
UA = "football-manager/0.1 (jogo de gerenciamento, uso pessoal) python-urllib"
PAUSA = 1.6               # entre chamadas: a Commons serve de graca, e devolve
                          # 429 quando a gente abusa

CAMADAS = ("left_arm", "body", "right_arm")
TENTATIVAS_DE_TEMPORADA = 4   # quantos anos recuar atras de uma camisa com as tres camadas
# `h` e a camisa 1, `a` a 2. O `t` (terceira) existe mas nao entra aqui.
TIPOS = {"1": "h", "2": "a"}
NOME_CANONICO = re.compile(r"^Kit_(?:body|left_arm|right_arm)_(.+?)(\d{2}|\d{4})(h|a)\.png$")


@dataclass(slots=True)
class CamisaBaixada:
    clube: str
    numero: str           # "1" ou "2"
    arquivo: Path
    temporada: str
    autor: str
    licenca: str
    origem: str


def _chamar(**params) -> dict:
    params.setdefault("format", "json")
    params.setdefault("maxlag", "5")
    url = API + "?" + urllib.parse.urlencode(params)
    for tentativa in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                dados = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and tentativa < 3:
                # o Retry-After manda; sem ele, recuo exponencial com um piso generoso
                espera = float(e.headers.get("Retry-After") or 0) or 5 * (2 ** tentativa)
                time.sleep(min(espera, 60))
                continue
            raise
        if "error" in dados and dados["error"].get("code") == "maxlag":
            time.sleep(2 ** tentativa)
            continue
        time.sleep(PAUSA)
        return dados
    raise RuntimeError("Commons nao respondeu depois de quatro tentativas")


def _ano(temporada: str, hoje: int | None = None) -> int:
    """'2526' e 2025/26; '26' e 2026; '61' e 1961.

    O corte nao pode ser um numero fixo: com 70 o arquivo do Gremio de 1961 virava 2061 e
    ganhava de todos os outros, e o jogo vestia o clube com a camisa mais VELHA que existe.
    A regra que funciona e temporal -- se dois digitos caem no futuro, sao do seculo passado.
    """
    from datetime import date
    limite = (hoje or date.today().year) + 1
    n = int(temporada[:2])
    ano = 2000 + n
    return ano if ano <= limite else 1900 + n


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def candidatos(nome: str) -> list[str]:
    """Como o clube pode estar escrito na Commons, do mais provavel ao menos."""
    base = _sem_acento(nome).lower()
    limpo = re.sub(r"[^a-z0-9]", "", base)
    palavras = re.sub(r"[^a-z0-9 ]", "", base).split()
    # SO o nome inteiro, sem espaco. Palpite com pedaco do nome veste o clube errado:
    # "Vasco da Gama" casava com `gama`, que e o Gama-DF, e "Gremio Novorizontino" casaria
    # com `gremio`, que e o de Porto Alegre. Quem nao casar assim vai para apelidos.toml.
    del palavras
    return [limpo] if len(limpo) >= 3 else []


def _listar(prefixo: str) -> list[str]:
    nomes, cont = [], {}
    while True:
        d = _chamar(action="query", list="allimages", aiprefix=f"Kit_body_{prefixo}",
                    ailimit=500, aisort="name", **cont)
        nomes += [i["name"] for i in d.get("query", {}).get("allimages", [])]
        if "continue" not in d or len(nomes) > 2000:
            return nomes
        cont = d["continue"]


def temporadas(nomes: list[str], prefixo: str, tipo: str) -> list[str]:
    """As temporadas deste clube e tipo, da mais recente para a mais antiga."""
    achados = set()
    for n in nomes:
        m = NOME_CANONICO.match(n)
        if m and m.group(1) == prefixo and m.group(3) == tipo:
            achados.add((_ano(m.group(2)), m.group(2)))
    return [t for _, t in sorted(achados, reverse=True)]


def escolher_temporada(nomes: list[str], prefixo: str, tipo: str) -> str | None:
    """A temporada mais recente com nome canonico, para este clube e este tipo."""
    achadas = temporadas(nomes, prefixo, tipo)
    return achadas[0] if achadas else None


def _info(titulos: list[str]) -> dict[str, dict]:
    d = _chamar(action="query", titles="|".join("File:" + t for t in titulos),
                prop="imageinfo", iiprop="url|extmetadata")
    fora = {}
    for pag in d.get("query", {}).get("pages", {}).values():
        if "imageinfo" not in pag:
            continue
        info = pag["imageinfo"][0]
        meta = info.get("extmetadata", {})
        # o MediaWiki devolve o titulo com ESPACO no lugar do underscore; sem desfazer
        # isso a chave nunca bate com o nome do arquivo que pedimos
        fora[pag["title"].split(":", 1)[1].replace(" ", "_")] = {
            "url": info["url"],
            "autor": re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip(),
            "licenca": meta.get("LicenseShortName", {}).get("value", "desconhecida"),
            "pagina": "https://commons.wikimedia.org/wiki/" + pag["title"].replace(" ", "_"),
        }
    return fora


def _baixar_png(url: str) -> bytes:
    """O mesmo cuidado da API vale aqui: upload.wikimedia tambem devolve 429."""
    for tentativa in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                dados = r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and tentativa < 3:
                espera = float(e.headers.get("Retry-After") or 0) or 5 * (2 ** tentativa)
                time.sleep(min(espera, 60))
                continue
            raise
        time.sleep(PAUSA)
        return dados
    raise RuntimeError(f"nao consegui baixar {url}")


def montar(pecas: list) -> object:
    """Cola manga esquerda + corpo + manga direita e tira o fundo branco.

    As imagens da Commons NAO tem transparencia: o fundo vem branco solido. O preenchimento
    a partir da borda que os escudos ja usam resolve isso sem esburacar a camisa por dentro
    -- a do Corinthians e quase toda branca.
    """
    from PIL import Image

    from fm.importer.escudos import _fundo_transparente

    largura = sum(p.width for p in pecas)
    altura = max(p.height for p in pecas)
    camisa = Image.new("RGBA", (largura, altura), (255, 255, 255, 255))
    x = 0
    for p in pecas:
        camisa.paste(p, (x, 0), p)
        x += p.width
    return _fundo_transparente(camisa)


def baixar_clube(nome: str, prefixo: str | None = None) -> list[CamisaBaixada]:
    """As camisas 1 e 2 de um clube, ja vetorizadas em SVG."""
    from PIL import Image

    from fm.importer.vetor import svg

    for tentativa in (prefixo,) if prefixo else candidatos(nome):
        nomes = _listar(tentativa)
        if any(NOME_CANONICO.match(n) and NOME_CANONICO.match(n).group(1) == tentativa
               for n in nomes):
            prefixo = tentativa
            break
    else:
        return []

    CAMISAS_DIR.mkdir(parents=True, exist_ok=True)
    fora: list[CamisaBaixada] = []
    for numero, tipo in TIPOS.items():
        # A temporada mais nova nem sempre tem as tres camadas: a camisa do Palmeiras de
        # 2026 so tem o corpo, porque a manga lisa a Wikipedia resolve por COR, nao por
        # imagem. Uma camisa completa do ano passado vale mais que uma sem mangas deste.
        escolhida, infos, titulos = None, {}, []
        for temporada in temporadas(nomes, prefixo, tipo)[:TENTATIVAS_DE_TEMPORADA]:
            titulos = [f"Kit_{c}_{prefixo}{temporada}{tipo}.png" for c in CAMADAS]
            infos = _info(titulos)
            if len(infos) == len(CAMADAS):
                escolhida = temporada
                break
        if not escolhida:
            continue
        temporada = escolhida
        import io as _io
        pecas = [Image.open(_io.BytesIO(_baixar_png(infos[t]["url"]))).convert("RGBA")
                 for t in titulos]
        camisa = montar(pecas)
        destino = CAMISAS_DIR / f"{_sem_acento(nome).lower().replace(' ', '-')}-{numero}.svg"
        destino.write_text(svg(camisa), encoding="utf-8")
        principal = infos[titulos[1]]
        fora.append(CamisaBaixada(
            clube=nome, numero=numero, arquivo=destino, temporada=temporada,
            autor=principal["autor"] or "desconhecido",
            licenca=principal["licenca"], origem=principal["pagina"]))
    return fora


def _apelidos() -> dict[str, str]:
    if not APELIDOS.exists():
        return {}
    import tomllib
    with APELIDOS.open("rb") as fh:
        return tomllib.load(fh).get("clubes", {})


def _indice_atual() -> dict[tuple[str, str], CamisaBaixada]:
    arq = CAMISAS_DIR / "indice.toml"
    if not arq.exists():
        return {}
    import tomllib
    with arq.open("rb") as fh:
        dados = tomllib.load(fh)
    fora = {}
    for c in dados.get("camisas", []):
        caminho = CAMISAS_DIR / c["arquivo"]
        if caminho.exists():
            fora[(c["clube"], c["numero"])] = CamisaBaixada(
                clube=c["clube"], numero=c["numero"], arquivo=caminho,
                temporada=c["temporada"], autor=c["autor"], licenca=c["licenca"],
                origem=c["origem"])
    return fora


def baixar(clubes: list[str], refazer: bool = False
           ) -> tuple[list[CamisaBaixada], list[str]]:
    """Baixa o que falta e grava o indice com autor e licenca de cada arquivo.

    Quem ja tem arquivo e entrada no indice e pulado -- sem isso, acrescentar um clube
    custava reimportar os vinte, e a Commons nao merece isso.
    """
    apelidos = _apelidos()
    ja_tem = {} if refazer else _indice_atual()
    baixadas: list[CamisaBaixada] = list(ja_tem.values())
    faltaram: list[str] = []
    for nome in clubes:
        if not refazer and (nome, "1") in ja_tem and (nome, "2") in ja_tem:
            continue
        achadas = baixar_clube(nome, apelidos.get(nome))
        if achadas:
            baixadas = [b for b in baixadas if b.clube != nome] + achadas
        else:
            faltaram.append(nome)

    linhas = [
        "# GERADO por fm.importer.camisas. Nao editar a mao.",
        "#",
        "# Camisas da Wikimedia Commons, vetorizadas. Autor e licenca ficam aqui porque",
        "# variam por arquivo e sem eles nao da para distribuir o jogo depois.",
        "",
        'fonte = "Wikimedia Commons (Kit_body / Kit_left_arm / Kit_right_arm)"',
        "",
    ]
    for c in sorted(baixadas, key=lambda x: (x.clube, x.numero)):
        linhas += [
            "[[camisas]]",
            f'clube = "{c.clube}"',
            f'numero = "{c.numero}"',
            f'arquivo = "{c.arquivo.name}"',
            f'temporada = "{c.temporada}"',
            f'autor = "{c.autor.replace(chr(34), chr(39))}"',
            f'licenca = "{c.licenca}"',
            f'origem = "{c.origem}"',
            "",
        ]
    (CAMISAS_DIR / "indice.toml").write_text("\n".join(linhas), encoding="utf-8")
    return baixadas, faltaram


def carregar(nome_do_clube: str, numero: str = "1") -> str | None:
    """O SVG da camisa, se ela tiver sido importada."""
    arq = CAMISAS_DIR / f"{_sem_acento(nome_do_clube).lower().replace(' ', '-')}-{numero}.svg"
    return arq.read_text(encoding="utf-8") if arq.exists() else None
