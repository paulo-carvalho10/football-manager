"""Competicoes continentais: Champions, Libertadores e Intercontinental.

Os participantes sao FIXOS, como pedido -- mas nao como lista de nomes digitada a mao, e
sim como VAGAS POR LIGA. Dado o mundo, o campo e sempre o mesmo (por isso fixo), e no dia
em que existir carreira basta trocar "os N mais fortes da liga" por "os N primeiros da
tabela" para virar classificacao de verdade, sem mexer no resto.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fm.competition import Fixture, group_stage, knockout_tie, play_fixtures, round_robin
from fm.match import Mentality, Style
from fm.model import World
from fm.table import build_table

TORNEIOS_DIR = Path(__file__).resolve().parent.parent / "data" / "torneios"


@dataclass(slots=True)
class Torneio:
    id: str
    nome: str
    vagas: dict[str, int]
    fases: list[dict]
    style: Style
    mentality: Mentality
    qualificados_de: list[str] = field(default_factory=list)


def carregar(nome: str) -> Torneio:
    caminho = TORNEIOS_DIR / f"{nome}.toml"
    if not caminho.exists():
        disponiveis = sorted(p.stem for p in TORNEIOS_DIR.glob("*.toml"))
        raise FileNotFoundError(f"torneio {nome!r} nao existe. Ha: {disponiveis}")
    with caminho.open("rb") as fh:
        cfg = tomllib.load(fh)
    e = cfg.get("estilo", {})
    m = cfg.get("mentalidade", {})
    return Torneio(
        id=cfg["id"], nome=cfg["nome"], vagas=cfg.get("vagas", {}),
        fases=cfg.get("formato", {}).get("fases", []),
        style=Style(goals_base=float(e.get("gols_base", 1.28)),
                    home_adv=float(e.get("mando", 0.26))),
        mentality=Mentality(goals_mult=float(m.get("gols_mult", 1.0)),
                            compression=float(m.get("compressao", 0.0)),
                            home_mult=float(m.get("mando_mult", 1.0))),
        qualificados_de=list(cfg.get("qualificados_de", [])))


def participantes(world: World, vagas: dict[str, int]) -> list[int]:
    """As N vagas de cada liga vao para os N clubes mais fortes dela.

    Hoje "mais forte" e a forca desenhada. Com carreira, vira a posicao final na tabela --
    e so esta funcao muda.
    """
    # as vagas sao declaradas pelo CODIGO da competicao na fonte (BRA1, ES1...), nao pelo
    # id interno da liga, porque o codigo e o identificador estavel entre importacoes
    por_codigo = {lg.codigo: lg for lg in world.leagues.values() if lg.codigo}
    escolhidos: list[int] = []
    for liga_id, n in vagas.items():
        liga = por_codigo.get(liga_id) or world.leagues.get(liga_id)
        if liga is None:
            continue
        ordenados = sorted(liga.club_ids,
                           key=lambda cid: -world.clubs[cid].designed_strength)
        escolhidos += ordenados[:n]
    return escolhidos


def _grupos_possiveis(n: int, pedido: int) -> int:
    """Maior numero de grupos <= pedido que divide n.

    O torneio tem de rodar com mundo PARCIAL: enquanto as ligas nao estao todas
    importadas, o campo vem incompleto e travar em "nao divide" nao ajuda ninguem.
    """
    for g in range(min(pedido, n // 2), 0, -1):
        if n % g == 0 and n // g >= 2:
            return g
    return 1


def _fase_grupos(world, clubes, fase, rng, style, mentality):
    g = _grupos_possiveis(len(clubes), int(fase.get("grupos", 8)))
    grupos = group_stage(clubes, g, legs=int(fase.get("voltas", 2)))
    avancam, passa = int(fase.get("avancam", 2)), []
    ratings = {cid: world.team_rating(cid) for cid in clubes}
    for fixtures in grupos:
        ids = sorted({f.home for f in fixtures} | {f.away for f in fixtures})
        resultados = play_fixtures(fixtures, ratings, rng, style, mentality)
        passa += [linha.club_id for linha in build_table(ids, resultados)[:avancam]]
    return passa


def _fase_mata_mata(world, clubes, fase, rng, style, mentality):
    ratings = {cid: world.team_rating(cid) for cid in clubes}
    vivos = list(clubes)
    # mata-mata precisa de potencia de 2; com mundo parcial, os mais fortes passam direto
    while len(vivos) & (len(vivos) - 1):
        vivos = sorted(vivos, key=lambda c: -world.clubs[c].designed_strength)
        vivos = vivos[:1 << (len(vivos).bit_length() - 1)]
    while len(vivos) > 1:
        rng.shuffle(vivos)
        metade = len(vivos) // 2
        a, b = vivos[:metade], vivos[metade:2 * metade]
        vencedores = knockout_tie(b, a, ratings, rng, style, mentality,
                                  legs=int(fase.get("maos", 2)))
        vivos = [int(x) for x in vencedores] + vivos[2 * metade:]
    return vivos


def simular(world: World, torneio: Torneio, rng: np.random.Generator,
            elenco: list[int] | None = None) -> list[int]:
    """Roda o torneio e devolve os sobreviventes, do campeao para baixo."""
    clubes = elenco if elenco is not None else participantes(world, torneio.vagas)
    for fase in torneio.fases:
        tipo = fase.get("tipo")
        if tipo == "groups":
            clubes = _fase_grupos(world, clubes, fase, rng, torneio.style,
                                  torneio.mentality)
        elif tipo == "knockout":
            clubes = _fase_mata_mata(world, clubes, fase, rng, torneio.style,
                                     torneio.mentality)
        elif tipo == "round_robin":
            ratings = {cid: world.team_rating(cid) for cid in clubes}
            fixtures: list[Fixture] = round_robin(clubes, legs=int(fase.get("voltas", 2)))
            resultados = play_fixtures(fixtures, ratings, rng, torneio.style,
                                       torneio.mentality)
            tabela = build_table(clubes, resultados)
            clubes = [linha.club_id for linha in tabela[:int(fase.get("avancam", 1))]]
        else:
            raise ValueError(f"fase desconhecida em {torneio.id}: {tipo!r}")
    return clubes


def disponiveis() -> list[str]:
    return sorted(p.stem for p in TORNEIOS_DIR.glob("*.toml"))
