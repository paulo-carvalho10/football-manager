"""Cores de clube tiradas do escudo, para quem nao tem cor escrita a mao.

Os 40 do Brasil e os 42 da Espanha tem cores conferidas em data/cores/. Os 258 clubes das
ligas da versao completa nao tinham nenhuma e caiam na paleta generica -- o Liverpool saia
com a mesma cor do Bournemouth. O escudo ja esta em disco (data/escudos), e as cores dele
sao as do clube na imensa maioria dos casos.

Como: quantiza o escudo em poucas cores, ignora o transparente, e pega a mais frequente
COM cor (saturada) como primaria; a secundaria e a proxima bem diferente dela, podendo
ser branco ou preto. E estimativa, e o arquivo gerado diz isso -- quem quiser corrigir um
clube escreve a cor dele num arquivo a mao, que tem precedencia (ordem alfabetica: o
gerado comeca com "zz_").
"""

from __future__ import annotations

import colorsys
from pathlib import Path

from fm.importer.escudos import ESCUDOS_DIR, ler_indice

SAIDA = Path(__file__).resolve().parent.parent.parent / "data" / "cores" / "zz_gerado_dos_escudos.toml"
N_CORES = 6

# Onde a estimativa erra num clube grande e o erro salta aos olhos: o vermelho escuro do
# escudo do Benfica perde para a aguia dourada, o azul-celeste do City vira azul-marinho.
# Estas tem precedencia sobre o escudo.
CONHECIDAS = {
    "SL Benfica": ("#E30613", "#FFFFFF"), "Porto": ("#005CA9", "#FFFFFF"),
    "Braga": ("#E30613", "#FFFFFF"), "Manchester City": ("#6CABDD", "#FFFFFF"),
    "Manchester United": ("#DA291C", "#000000"), "Milan": ("#E61C2A", "#000000"),
    "Everton": ("#003399", "#FFFFFF"), "Tottenham Hotspur": ("#132257", "#FFFFFF"),
    "Paris Saint-Germain": ("#004170", "#DA291C"), "Aston Villa": ("#670E36", "#95BFE5"),
    "Newcastle United": ("#241F20", "#FFFFFF"), "Lazio": ("#87D8F7", "#FFFFFF"),
    "Roma": ("#8E1F2F", "#F0BC42"), "Atalanta BC": ("#1E71B8", "#000000"),
    "SG Eintracht Frankfurt": ("#E1000F", "#000000"),
    "Bayer 04 Leverkusen": ("#E32221", "#000000"), "Bayern Munique": ("#DC052D", "#FFFFFF"),
    "River Plate": ("#E30613", "#FFFFFF"), "Olympique Lyon": ("#1B3D8F", "#E30613"),
    # a Espanha nunca teve cores escritas a mao; entra aqui junto
    "Real Madrid": ("#FFFFFF", "#FEBE10"), "Barcelona": ("#A50044", "#004D98"),
    "Atlético Madrid": ("#CB3524", "#FFFFFF"), "Valencia": ("#FFFFFF", "#000000"),
    "Sevilla": ("#D81E05", "#FFFFFF"), "Villarreal": ("#FFE667", "#005187"),
    "Athletic Club": ("#EE2523", "#FFFFFF"), "Real Sociedad": ("#0067B1", "#FFFFFF"),
    "Real Betis": ("#0BB363", "#FFFFFF"),
}


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _saturacao(rgb) -> float:
    r, g, b = (x / 255 for x in rgb)
    _, luz, sat = colorsys.rgb_to_hls(r, g, b)
    return sat if 0.12 < luz < 0.9 else 0.0


def _distancia(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def cores_do_escudo(arquivo: Path) -> tuple[str, str]:
    from PIL import Image
    img = Image.open(arquivo).convert("RGBA")
    opacos = [p[:3] for p in img.getdata() if p[3] > 200]
    if not opacos:
        return "#2F8A4B", "#FFFFFF"
    base = Image.new("RGB", (len(opacos), 1))
    base.putdata(opacos)
    q = base.quantize(colors=N_CORES, method=Image.Quantize.MEDIANCUT)
    paleta = q.getpalette()[:N_CORES * 3]
    contagem = sorted(q.getcolors(), reverse=True)            # [(n, indice)]
    cores = [(n, tuple(paleta[i * 3:i * 3 + 3])) for n, i in contagem]
    total = sum(n for n, _ in cores)
    # primaria: a mais frequente com cor de verdade; sem nenhuma, a mais frequente
    # entre as que tem cor, pesa a VIVACIDADE junto com a frequencia: so pela frequencia o
    # canhao dourado do Arsenal ganhava do vermelho, e o Arsenal saia marrom
    com_cor = [(n * _saturacao(c) ** 2, c) for n, c in cores
               if _saturacao(c) > 0.25 and n / total > 0.08]
    primaria = max(com_cor)[1] if com_cor else cores[0][1]
    # secundaria: a proxima que se distingue bem da primaria (branco e preto valem)
    resto = [c for _, c in cores if _distancia(c, primaria) > 110]
    secundaria = resto[0] if resto else ((255, 255, 255) if sum(primaria) < 380 else (20, 20, 20))
    return _hex(primaria), _hex(secundaria)


def gerar(packs: list[str], ja_tem: set[str]) -> int:
    """Escreve o arquivo de cores para os clubes dos packs que ainda nao tem cor."""
    from fm.pack import load_pack
    indice = ler_indice()
    linhas = [
        "# GERADO por fm.importer.cores_do_escudo. Cores ESTIMADAS a partir do escudo de",
        "# cada clube (as duas mais presentes). Para corrigir um clube, escreva a cor dele",
        "# num arquivo a mao em data/cores/ -- o gerado nao sobrescreve cor ja conhecida.",
        "",
        f"packs = {sorted(packs)!r}".replace("'", '"'),
        'fonte = "cores dominantes do escudo (Transfermarkt), estimativa"',
        "verificado = false",
        "",
    ]
    feitos = 0
    for pack in packs:
        for clube in load_pack(pack).clubes:
            arq = indice.get(clube.nome)
            if clube.nome in ja_tem or not arq or not (ESCUDOS_DIR / arq).is_file():
                continue
            primaria, secundaria = (CONHECIDAS.get(clube.nome)
                                    or cores_do_escudo(ESCUDOS_DIR / arq))
            linhas += ["[[clubes]]", f'nome = "{clube.nome}"', f'primaria = "{primaria}"',
                       f'secundaria = "{secundaria}"', 'padrao = "liso"', ""]
            feitos += 1
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")
    return feitos
