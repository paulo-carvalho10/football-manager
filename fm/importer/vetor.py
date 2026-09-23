"""Converte a camisa em pixel art para SVG, mantendo as cores e o desenho originais.

O sprite da Wikimedia vem em 38x59 por camada -- nitido no tamanho dele e uma escada
quando ampliado. Aqui ele vira vetor: cada cor vira uma regiao, cada regiao tem o contorno
tracado e simplificado, e o resultado escala para qualquer tamanho sem serrilhado.

Nao e' um vetorizador de foto. Funciona porque pixel art tem o que uma foto nao tem: um
numero pequeno de cores chapadas, sem gradiente e sem antialiasing -- entao o contorno de
cada cor e' exato, e o unico trabalho e' suavizar a escada sem perder a forma.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

Cor = tuple[int, int, int]
Ponto = tuple[float, float]

# Cores mais proximas do que isto (distancia euclidiana em RGB) sao a mesma cor. O sprite
# e' chapado, mas o redimensionamento de quem o desenhou deixa meio-tons nas bordas.
JUNTAR_ATE = 34.0
AREA_MINIMA = 3           # regiao menor que isto e ruido de compressao, nao desenho
TOLERANCIA = 0.62         # px: quanto o contorno pode se afastar do original ao simplificar
RAIO_DO_CANTO = 0.42      # px: arredondamento que tira a escada sem derreter a forma


@dataclass(slots=True)
class Camada:
    cor: Cor
    area: int
    d: str                # o atributo `d` do path


def _quantizar(pixels: np.ndarray, alfa: np.ndarray) -> tuple[np.ndarray, list[Cor]]:
    """Agrupa cores parecidas e devolve um mapa de indices.

    Sem isto cada meio-tom de borda vira uma regiao propria, e um sprite de 100x59 sai com
    quarenta camadas de um pixel cada.
    """
    visiveis = pixels[alfa]
    if not len(visiveis):
        return np.full(alfa.shape, -1, dtype=np.int32), []

    cores, contagem = np.unique(visiveis.reshape(-1, 3), axis=0, return_counts=True)
    ordem = np.argsort(-contagem)
    cores, contagem = cores[ordem], contagem[ordem]

    paleta: list[np.ndarray] = []
    destino: list[int] = []
    for cor in cores:
        for i, base in enumerate(paleta):
            if float(np.linalg.norm(cor.astype(float) - base.astype(float))) < JUNTAR_ATE:
                destino.append(i)
                break
        else:
            paleta.append(cor)
            destino.append(len(paleta) - 1)

    chave = {tuple(int(v) for v in c): destino[i] for i, c in enumerate(cores)}
    indices = np.full(alfa.shape, -1, dtype=np.int32)
    for (y, x) in zip(*np.where(alfa), strict=True):
        indices[y, x] = chave[tuple(int(v) for v in pixels[y, x])]
    return indices, [tuple(int(v) for v in c) for c in paleta]


def _contornos(mascara: np.ndarray) -> list[list[Ponto]]:
    """Traca a borda da regiao como loops fechados, em coordenadas de canto de pixel.

    A borda e' o conjunto de arestas entre um pixel de dentro e um de fora. Cada aresta e'
    orientada de modo que o interior fique sempre a esquerda, e ai os loops se fecham
    sozinhos: basta emendar cada aresta com a que comeca onde ela termina.
    """
    altura, largura = mascara.shape
    arestas: dict[Ponto, list[Ponto]] = defaultdict(list)
    for y, x in zip(*np.where(mascara), strict=True):
        if y == 0 or not mascara[y - 1, x]:
            arestas[(x, y)].append((x + 1, y))              # topo, para a direita
        if x + 1 == largura or not mascara[y, x + 1]:
            arestas[(x + 1, y)].append((x + 1, y + 1))      # direita, para baixo
        if y + 1 == altura or not mascara[y + 1, x]:
            arestas[(x + 1, y + 1)].append((x, y + 1))      # base, para a esquerda
        if x == 0 or not mascara[y, x - 1]:
            arestas[(x, y + 1)].append((x, y))              # esquerda, para cima

    loops: list[list[Ponto]] = []
    while arestas:
        inicio = next(iter(arestas))
        atual, loop = inicio, [inicio]
        while True:
            saidas = arestas.get(atual)
            if not saidas:
                break
            proximo = saidas.pop()
            if not saidas:
                del arestas[atual]
            if proximo == inicio:
                break
            loop.append(proximo)
            atual = proximo
        if len(loop) >= 4:
            loops.append(loop)
    return loops


def _sem_colineares(loop: list[Ponto]) -> list[Ponto]:
    fora: list[Ponto] = []
    n = len(loop)
    for i in range(n):
        a, b, c = loop[i - 1], loop[i], loop[(i + 1) % n]
        if (b[0] - a[0]) * (c[1] - a[1]) != (b[1] - a[1]) * (c[0] - a[0]):
            fora.append(b)
    return fora or loop


def _simplificar(loop: list[Ponto], tol: float) -> list[Ponto]:
    """Douglas-Peucker num anel fechado, partindo do par de pontos mais distante."""
    if len(loop) < 4:
        return loop
    pts = np.array(loop, dtype=float)
    inicio = int(np.argmax(((pts - pts.mean(0)) ** 2).sum(1)))
    pts = np.roll(pts, -inicio, axis=0)
    aberto = np.vstack([pts, pts[:1]])

    guardar = np.zeros(len(aberto), dtype=bool)
    guardar[0] = guardar[-1] = True
    pilha = [(0, len(aberto) - 1)]
    while pilha:
        i, j = pilha.pop()
        if j <= i + 1:
            continue
        a, b = aberto[i], aberto[j]
        seg = b - a
        norma = float(np.hypot(*seg))
        meio = aberto[i + 1:j]
        v = meio - a
        # produto cruzado 2D na mao: np.cross com vetores de 2 saiu no numpy 2
        dist = (np.hypot(*v.T) if norma < 1e-9
                else np.abs(seg[0] * v[:, 1] - seg[1] * v[:, 0]) / norma)
        k = int(np.argmax(dist))
        if dist[k] > tol:
            guardar[i + 1 + k] = True
            pilha += [(i, i + 1 + k), (i + 1 + k, j)]
    ficou = [tuple(p) for p, g in zip(aberto[:-1], guardar[:-1], strict=True) if g]
    return ficou if len(ficou) >= 3 else loop


def _para_path(loops: list[list[Ponto]], raio: float) -> str:
    """Emite o `d`, arredondando cada vertice para tirar a escada do pixel."""
    partes: list[str] = []
    for loop in loops:
        n = len(loop)
        if n < 3:
            continue
        pts = [np.array(p, dtype=float) for p in loop]
        d: list[str] = []
        for i in range(n):
            atual, anterior, proximo = pts[i], pts[i - 1], pts[(i + 1) % n]
            entra, sai = atual - anterior, proximo - atual
            le, ls = float(np.hypot(*entra)), float(np.hypot(*sai))
            if le < 1e-9 or ls < 1e-9:
                continue
            corte = min(raio, le / 2, ls / 2)
            a = atual - entra / le * corte
            b = atual + sai / ls * corte
            # uma casa decimal: em coordenadas de 0 a 100 isso e precisao de 0,1 pixel,
            # invisivel na tela e um quarto a menos de arquivo
            if not d:
                d.append(f"M{a[0]:.1f} {a[1]:.1f}")
            else:
                d.append(f"L{a[0]:.1f} {a[1]:.1f}")
            if corte > 0.01:
                d.append(f"Q{atual[0]:.1f} {atual[1]:.1f} {b[0]:.1f} {b[1]:.1f}")
        if d:
            partes.append(" ".join(d) + " Z")
    return " ".join(partes)


def vetorizar(imagem, tolerancia: float = TOLERANCIA,
              raio: float = RAIO_DO_CANTO) -> list[Camada]:
    """A imagem em camadas de cor, cada uma com o contorno pronto para virar `<path>`."""
    arr = np.asarray(imagem.convert("RGBA"))
    alfa = arr[:, :, 3] > 128
    indices, paleta = _quantizar(arr[:, :, :3], alfa)

    camadas: list[Camada] = []
    for i, cor in enumerate(paleta):
        mascara = indices == i
        area = int(mascara.sum())
        if area < AREA_MINIMA:
            continue
        loops = [_simplificar(_sem_colineares(loop), tolerancia)
                 for loop in _contornos(mascara)]
        d = _para_path([lp for lp in loops if len(lp) >= 3], raio)
        if d:
            camadas.append(Camada(cor=cor, area=area, d=d))
    # da maior para a menor: a cor dominante e o fundo, o detalhe vem por cima
    return sorted(camadas, key=lambda c: -c.area)


def svg(imagem, tolerancia: float = TOLERANCIA, raio: float = RAIO_DO_CANTO) -> str:
    """O SVG inteiro da camisa, pronto para embutir na tela."""
    largura, altura = imagem.size
    camadas = vetorizar(imagem, tolerancia, raio)
    corpos = "".join(
        f'<path d="{c.d}" fill="rgb({c.cor[0]},{c.cor[1]},{c.cor[2]})"'
        # o traco da propria cor fecha as frestas que a simplificacao abre entre vizinhos
        f' stroke="rgb({c.cor[0]},{c.cor[1]},{c.cor[2]})" stroke-width="0.12"/>'
        for c in camadas)
    return (f'<svg class="camisa" viewBox="0 0 {largura} {altura}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img">{corpos}</svg>')
