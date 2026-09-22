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
TOLERANCIA_BRANCO = 238


def _fundo_transparente(img):
    """Apaga so o branco LIGADO A BORDA, por preenchimento a partir dos cantos.

    Apagar todo pixel branco, que era o que eu fazia, esburaca o escudo por dentro: o do
    Santos e majoritariamente branco e sobrava so o contorno. Fundo e o branco conectado
    a moldura; branco cercado por desenho e parte do escudo.
    """
    from collections import deque
    largura, altura = img.size
    pix = img.load()

    def e_fundo(x, y):
        r, g, b, a = pix[x, y]
        claro = min(r, g, b) > TOLERANCIA_BRANCO
        return a > 0 and claro

    fila = deque()
    visto = set()
    for x in range(largura):
        for y in (0, altura - 1):
            if e_fundo(x, y):
                fila.append((x, y))
    for y in range(altura):
        for x in (0, largura - 1):
            if e_fundo(x, y):
                fila.append((x, y))
    while fila:
        x, y = fila.popleft()
        if (x, y) in visto or not (0 <= x < largura and 0 <= y < altura):
            continue
        visto.add((x, y))
        if not e_fundo(x, y):
            continue
        r, g, b, _ = pix[x, y]
        pix[x, y] = (r, g, b, 0)
        fila.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return img


def _recortar_e_normalizar(bruto: bytes) -> bytes:
    """Escudo normalizado: fundo transparente, proporcao preservada, tamanho unico.

    Os arquivos da CBF vem em tamanhos diferentes e com fundo branco; sem normalizar, a
    interface fica com escudos de alturas diferentes e retangulos brancos sobre o tema
    escuro dos clubes de preto.
    """
    from PIL import Image
    img = Image.open(io.BytesIO(bruto)).convert("RGBA")
    img = _fundo_transparente(img)
    caixa = img.getbbox()
    if caixa:
        img = img.crop(caixa)

    # cabe dentro do quadro SEM esticar: a proporcao do escudo e preservada
    util = LADO - 2 * MARGEM
    escala = min(util / img.size[0], util / img.size[1])
    novo = (max(1, round(img.size[0] * escala)), max(1, round(img.size[1] * escala)))
    img = img.resize(novo, Image.LANCZOS)

    final = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    final.paste(img, ((LADO - novo[0]) // 2, (LADO - novo[1]) // 2), img)
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
