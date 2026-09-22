"""Escudos dos clubes.

A CBF serve o escudo por Codigo_Clube, e esse codigo ja esta gravado em `id_fonte` de cada
clube do pack -- entao nao ha nada para importar a mao: e uma passada do importador.

Os arquivos ficam em data/escudos/, FORA do git. Escudo e marca registrada; o repositorio
nao distribui o ativo, o jogo baixa na primeira execucao. Quem nao tiver escudo cai no
gerado a partir das cores, que continua existindo.
"""

from __future__ import annotations

import io
from pathlib import Path

from fm.importer.http import CACHE_DIR
from fm.pack import load_pack

ESCUDOS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "escudos"
URL_CBF = "https://conteudo.cbf.com.br/clubes/{id}/escudo.jpg"
LADO = 96          # tudo normalizado no mesmo tamanho: a interface fica limpa
MARGEM = 2
CORES_NA_PALETA = 48


def _recortar_e_normalizar(bruto: bytes) -> bytes:
    """Tira a moldura branca, encaixa num quadrado e devolve PNG com fundo transparente.

    Os arquivos da CBF vem em tamanhos diferentes e com fundo branco; sem normalizar, a
    interface fica com escudos de alturas diferentes e retangulos brancos sobre o tema
    escuro do clube.
    """
    from PIL import Image
    img = Image.open(io.BytesIO(bruto)).convert("RGBA")
    pixels = img.load()
    largura, altura = img.size
    for x in range(largura):
        for y in range(altura):
            r, g, b, a = pixels[x, y]
            if r > 243 and g > 243 and b > 243:
                pixels[x, y] = (r, g, b, 0)
    caixa = img.getbbox()
    if caixa:
        img = img.crop(caixa)
    lado = max(img.size)
    quadro = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    quadro.paste(img, ((lado - img.size[0]) // 2, (lado - img.size[1]) // 2))
    quadro = quadro.resize((LADO - 2 * MARGEM, LADO - 2 * MARGEM), Image.LANCZOS)
    final = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    final.paste(quadro, (MARGEM, MARGEM))
    # Paleta em vez de cor real: escudo e desenho chapado, nao fotografia. Em 96px nao
    # ha diferenca visivel, e o peso importa quando os 20 escudos viajam embutidos numa
    # pagina. FASTOCTREE porque e o unico metodo que o Pillow aceita com transparencia.
    final = final.quantize(colors=CORES_NA_PALETA, method=Image.FASTOCTREE)
    saida = io.BytesIO()
    final.save(saida, "PNG", optimize=True)
    return saida.getvalue()


def baixar(pack: str = "brasil_serie_a", delay: float = 0.4) -> dict[str, Path]:
    """Baixa e normaliza o escudo de cada clube do pack que tenha id_fonte."""
    import time
    import urllib.request

    from fm.importer.http import UA
    ESCUDOS_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "escudos").mkdir(parents=True, exist_ok=True)
    saida: dict[str, Path] = {}
    for clube in load_pack(pack).clubes:
        if not clube.id_fonte:
            continue
        destino = ESCUDOS_DIR / f"{clube.id_fonte}.png"
        if destino.exists():
            saida[clube.nome] = destino
            continue
        bruto_path = CACHE_DIR / "escudos" / f"{clube.id_fonte}.jpg"
        if not bruto_path.exists():
            req = urllib.request.Request(URL_CBF.format(id=clube.id_fonte),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                bruto_path.write_bytes(r.read())
            time.sleep(delay)
        destino.write_bytes(_recortar_e_normalizar(bruto_path.read_bytes()))
        saida[clube.nome] = destino
    return saida
