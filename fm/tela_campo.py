"""A tela de escalacao em grafico: campo, camisas e o onze posicionado pela formacao.

Existe porque onze colunas de terminal nunca vao dar uma camisa decente. O desenho em
meio-bloco de `fm/camisa.py` continua servindo quem joga no terminal, mas a camisa com
gola, manga, listra e sombra precisa de resolucao de verdade -- e aqui ela e SVG, gerado a
partir das mesmas cores e do mesmo padrao que o terminal usa, vindos de data/cores.

Isto e apresentacao pura: devolve uma string de HTML e nao escreve nem abre nada. Quem
grava e abre e o cli.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from fm.carreira import Carreira
from fm.tatica import Tatica

# Onde cada linha fica no campo, de 0 (linha de fundo adversaria) a 100 (o proprio gol).
# Sao as alturas do 4-3-3; formacao com mais linhas aperta os intervalos proporcionalmente.
ALTURA_DA_LINHA = {"GK": 91.0, "DF": 72.0, "MF": 48.0, "FW": 22.0}
MARGEM_LATERAL = 13.0      # os pontas nao colam na linha de fundo

# A silhueta da camisa, em coordenadas de 0..100 por 0..104. Ombro, manga que desce e
# afina, e tronco reto -- o contorno e um path so, e os padroes sao recortados por ele.
CAMISA_PATH = (
    "M36 4 L42 4 A9 7 0 0 0 58 4 L64 4 "            # ombros, com o recorte da gola
    "Q68 4 71 6 L97 24 Q100 26 98 29 L89 43 "       # manga direita, descendo
    "Q87 46 84 44 L79 40 L79 99 "                   # punho e costura do tronco
    "Q79 102 76 102 L24 102 Q21 102 21 99 "         # barra
    "L21 40 L16 44 Q13 46 11 43 L2 29 "             # manga esquerda, subindo
    "Q0 26 3 24 L29 6 Q32 4 36 4 Z"
)
# A gola e uma FITA rasa que acompanha o recorte. Um V fundo virava dois chifres separados
# por um bico escuro -- uma camisa de verdade tem a linha do ombro quase reta.
GOLA_PATH = "M42 4 A9 7 0 0 0 58 4 L61 4 A12 10 0 0 1 39 4 Z"


@dataclass(slots=True)
class Jogador:
    nome: str
    posicao: str
    overall: int
    energia: int
    x: float
    y: float


def _posicoes(vagas: dict[str, int]) -> dict[str, list[float]]:
    """Distribui cada linha na largura do campo.

    Uma linha de quatro nao e quatro pontos igualmente espacados: os laterais abrem mais
    que os zagueiros, senao a defesa fica com cara de fileira de soldados.
    """
    fora: dict[str, list[float]] = {}
    for grupo, n in vagas.items():
        if n <= 0:
            fora[grupo] = []
        elif n == 1:
            fora[grupo] = [50.0]
        else:
            largura = 100.0 - 2 * MARGEM_LATERAL
            passo = largura / (n - 1)
            fora[grupo] = [MARGEM_LATERAL + i * passo for i in range(n)]
    return fora


def _escalar_alturas(vagas: dict[str, int]) -> dict[str, float]:
    """Formacao com linha de cinco precisa de mais folga vertical que uma de tres."""
    alturas = dict(ALTURA_DA_LINHA)
    if vagas.get("MF", 0) >= 5:
        alturas["MF"] = 52.0
        alturas["FW"] = 20.0
    if vagas.get("DF", 0) >= 5:
        alturas["DF"] = 74.0
    if vagas.get("FW", 0) >= 3:
        alturas["FW"] = 24.0
    return alturas


def montar_onze(c: Carreira, onze: list[int], tatica: Tatica) -> list[Jogador]:
    """Coloca o onze do usuario no campo, cada grupo na sua linha."""
    alturas = _escalar_alturas(tatica.vagas)
    colunas = _posicoes(tatica.vagas)
    por_grupo: dict[str, list] = {}
    for pid in onze:
        p = c.world.players[pid]
        por_grupo.setdefault(p.position, []).append(p)

    fora: list[Jogador] = []
    for grupo, gente in por_grupo.items():
        gente.sort(key=lambda p: -p.overall)
        xs = colunas.get(grupo) or _posicoes({grupo: len(gente)})[grupo]
        for i, p in enumerate(gente):
            fora.append(Jogador(
                nome=p.name, posicao=p.position, overall=p.overall,
                energia=p.condition,
                x=xs[i] if i < len(xs) else 50.0,
                y=alturas.get(grupo, 50.0)))
    return fora


def _camisa_svg(pano: str, detalhe: str, padrao: str, ident: str) -> str:
    """Uma camisa. O padrao e recortado pela silhueta, entao nunca vaza para fora dela."""
    listras = []
    if padrao == "listras":
        listras = [f'<rect x="{x}" y="-2" width="9" height="112" fill="{detalhe}"/>'
                   for x in range(6, 100, 18)]
    elif padrao == "aros":
        # o manto rubro-negro tem sete ou oito aros, nao quatro faixas largas
        listras = [f'<rect x="-2" y="{y}" width="104" height="7" fill="{detalhe}"/>'
                   for y in range(6, 104, 14)]
    elif padrao == "faixa":
        listras = [f'<rect x="0" y="40" width="100" height="16" fill="{detalhe}"/>',
                   f'<rect x="0" y="60" width="100" height="16" fill="{detalhe}"/>']
    elif padrao == "diagonal":
        listras = [f'<path d="M-20 88 L74 -14 L98 8 L4 110 Z" fill="{detalhe}"/>']

    return f'''<svg class="camisa" viewBox="-2 -2 104 112" role="img">
  <defs>
    <clipPath id="c{ident}"><path d="{CAMISA_PATH}"/></clipPath>
    <linearGradient id="v{ident}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#000" stop-opacity=".22"/>
      <stop offset=".22" stop-color="#000" stop-opacity="0"/>
      <stop offset=".72" stop-color="#000" stop-opacity="0"/>
      <stop offset="1" stop-color="#000" stop-opacity=".26"/>
    </linearGradient>
  </defs>
  <g clip-path="url(#c{ident})">
    <rect x="-2" y="-2" width="104" height="112" fill="{pano}"/>
    {"".join(listras)}
    <rect x="-2" y="-2" width="104" height="112" fill="url(#v{ident})"/>
    <path d="{GOLA_PATH}" fill="{detalhe}"/>
    <path d="M22 3 L22 103" stroke="#000" stroke-opacity=".13" stroke-width="3"/>
    <path d="M78 3 L78 103" stroke="#000" stroke-opacity=".13" stroke-width="3"/>
  </g>
  <path d="{CAMISA_PATH}" fill="none" stroke="#0d1a12" stroke-opacity=".42"
        stroke-width="1.6" stroke-linejoin="round"/>
</svg>'''


def _campo_svg() -> str:
    """As linhas do campo. Meio-campo embaixo do onze, area e circulo, como na tela."""
    linha = 'fill="none" stroke="#ffffff" stroke-opacity=".38" stroke-width=".5"'
    return f'''<svg class="linhas" viewBox="0 0 100 100" preserveAspectRatio="none"
     aria-hidden="true">
  <rect x="2" y="2" width="96" height="96" {linha}/>
  <line x1="2" y1="50" x2="98" y2="50" {linha}/>
  <circle cx="50" cy="50" r="11" {linha}/>
  <circle cx="50" cy="50" r="0.9" fill="#ffffff" fill-opacity=".38"/>
  <rect x="26" y="83" width="48" height="15" {linha}/>
  <rect x="38" y="93" width="24" height="5" {linha}/>
  <rect x="26" y="2" width="48" height="15" {linha}/>
  <rect x="38" y="2" width="24" height="5" {linha}/>
  <path d="M38 83 A 13 13 0 0 1 62 83" {linha}/>
  <path d="M38 17 A 13 13 0 0 0 62 17" {linha}/>
</svg>'''


def escalacao_html(c: Carreira, onze: list[int] | None = None,
                   tatica: Tatica | None = None) -> str:
    """A tela inteira, pronta para gravar em disco e abrir."""
    tatica = tatica or c.tatica_atual()
    onze = onze or c.escalacao_atual()
    clube = c.clube
    pano = clube.kit_body or clube.color_primary
    detalhe = clube.kit_detail or clube.color_secondary
    gk_pano, gk_detalhe = detalhe, pano

    jogadores = montar_onze(c, onze, tatica)
    pecas = []
    for i, j in enumerate(jogadores):
        goleiro = j.posicao == "GK"
        svg = _camisa_svg(gk_pano if goleiro else pano,
                          gk_detalhe if goleiro else detalhe,
                          "liso" if goleiro else clube.kit_pattern, str(i))
        pecas.append(
            f'<div class="jogador" style="left:{j.x}%;top:{j.y}%">'
            f'{svg}'
            f'<span class="nome">{html.escape(j.nome)}</span>'
            f'<span class="dados">{j.posicao} {j.overall} - E:{j.energia}</span>'
            f'</div>')

    media = sum(c.world.players[i].overall for i in onze) / len(onze)
    energia = sum(c.world.players[i].condition for i in onze) / len(onze)
    return _PAGINA.format(
        clube=html.escape(clube.name), liga=html.escape(c.liga),
        temporada=c.temporada, rodada=c.rodada, total=c.total_de_rodadas,
        tatica=html.escape(tatica.como_texto()), media=f"{media:.1f}",
        energia=f"{energia:.0f}", campo=_campo_svg(), jogadores="".join(pecas),
        tema=clube.color_primary)


_PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{clube} - escalacao</title>
<style>
  :root {{ --tema:{tema}; --grama:#3f8a43; --grama2:#39803d; }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; padding:20px 16px 40px; background:#14231a; color:#e8efe9;
    font:15px/1.5 "Segoe UI",system-ui,sans-serif;
  }}
  .topo {{
    max-width:900px; margin:0 auto 16px; display:flex; flex-wrap:wrap; gap:10px 18px;
    align-items:baseline; border-left:5px solid var(--tema); padding-left:14px;
  }}
  .topo h1 {{ margin:0; font-size:23px; letter-spacing:-.01em; }}
  .topo span {{ color:#9db3a4; font-size:13.5px; }}
  .campo {{
    position:relative; max-width:900px; margin:0 auto; aspect-ratio:3/4;
    border-radius:8px; overflow:hidden; box-shadow:0 10px 40px #0006;
    background:repeating-linear-gradient(180deg,
      var(--grama) 0 6.25%, var(--grama2) 6.25% 12.5%);
  }}
  .linhas {{ position:absolute; inset:0; width:100%; height:100%; }}
  .jogador {{
    position:absolute; transform:translate(-50%,-50%); width:13%; min-width:64px;
    display:flex; flex-direction:column; align-items:center; text-align:center;
  }}
  .camisa {{ width:100%; height:auto; filter:drop-shadow(0 3px 4px #0007); }}
  .nome {{
    margin-top:3px; font-weight:700; font-size:13px; color:#fff; line-height:1.15;
    text-shadow:0 1px 3px #000, 0 0 2px #000;
    white-space:nowrap; max-width:150%; overflow:hidden; text-overflow:ellipsis;
  }}
  .dados {{
    font-size:12px; color:#f2f6f3; text-shadow:0 1px 3px #000, 0 0 2px #000;
    font-variant-numeric:tabular-nums;
  }}
  @media (max-width:620px) {{
    .campo {{ aspect-ratio:2/3; }}
    .jogador {{ min-width:52px; }}
    .nome {{ font-size:11px; }} .dados {{ font-size:10px; }}
  }}
</style></head><body>
  <div class="topo">
    <h1>{clube}</h1>
    <span>{liga} &middot; {temporada} &middot; rodada {rodada} de {total}</span>
    <span>{tatica}</span>
    <span>onze: overall {media} &middot; energia {energia}%</span>
  </div>
  <div class="campo">{campo}{jogadores}</div>
</body></html>
"""
