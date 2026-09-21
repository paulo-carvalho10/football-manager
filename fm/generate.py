"""Geracao procedural do mundo.

O CARATER DA LIGA VIVE AQUI, nao no motor. Medido com parametros de motor identicos, so
mudando a distribuicao de overall dos clubes:

    Brasil   (77..59 achatado)   -> campeao 72 pts, 26% empates, gap 1o-10o = 20
    Espanha  (88,86,82 + 75..53) -> campeao 82 pts, 24% empates, gap = 30, top3 leva 95%
    Franca   (90 + 77..54)       -> campeao 82 pts, mas o maior clube leva 80% dos titulos

Ou seja: os seis tracos que distinguem Brasil de Espanha sao CONTEUDO. O motor nao sabe em
que pais esta -- nada de `if country == "BRA"`.
"""

from __future__ import annotations

import numpy as np

from fm.model import Club, League, Player, World
from fm.names import CLUB_PATTERNS, CLUB_ROOTS, FIRST_NAMES, SURNAMES
from fm.rng import Streams

SQUAD_SIZE = 24

# Ordem das posicoes no elenco ordenado por overall. Os 11 primeiros formam um 4-4-2 valido,
# entao o melhor onze contem de fato os melhores jogadores.
SQUAD_SHAPE = (
    "GK", "DF", "DF", "MF", "DF", "MF", "FW", "MF", "DF", "MF", "FW",   # titulares
    "GK", "DF", "MF", "FW", "DF", "MF", "FW", "DF", "MF", "GK", "MF", "DF", "FW",
)

# Curva de qualidade do elenco (delta de overall, decrescente).
SQUAD_CURVE = np.array(
    [6, 5, 4, 3, 3, 2, 2, 1, 1, 0, 0, -2, -3, -4, -4, -5, -6, -7, -8, -9, -10, -11, -13, -15],
    dtype=float,
)

AGE_SHAPE = (
    28, 27, 29, 26, 30, 25, 27, 24, 31, 26, 23,
    33, 22, 28, 21, 32, 20, 25, 19, 29, 24, 18, 22, 34,
)

COLORS = [
    ("#1b4d3e", "#f2f2f2"), ("#8b1a1a", "#ffffff"), ("#123a6b", "#ffd700"),
    ("#0f0f0f", "#e8e8e8"), ("#1f6f3f", "#ffcc00"), ("#5b2c6f", "#ffffff"),
    ("#b33c00", "#1a1a1a"), ("#00566b", "#ffffff"), ("#7a0026", "#d9d9d9"),
    ("#2e4600", "#f5f5f5"),
]


def strength_profile(cfg: dict, n: int) -> list[float]:
    """Traduz o perfil de forca do arquivo da liga numa lista de overalls de clube."""
    f = cfg["forca"]
    perfil = f.get("perfil", "linear")
    if perfil == "linear":
        return list(np.linspace(f["topo"], f["base"], n))
    if perfil == "gigantes":
        destaques = [float(x) for x in f["destaques"]]
        resto = n - len(destaques)
        if resto < 1:
            raise ValueError("perfil 'gigantes': destaques nao podem preencher a liga toda")
        return destaques + list(np.linspace(f["topo"], f["base"], resto))
    raise ValueError(f"perfil de forca desconhecido: {perfil!r}")


def _attributes(rng: np.random.Generator, overall: int, position: str) -> dict[str, int]:
    """Atributos coerentes com a posicao, com media presa ao overall."""
    bias = {
        "GK": {"reflexes": 14, "positioning": 6, "aerial": 4, "finishing": -22,
               "dribbling": -18, "pace": -10},
        "DF": {"marking": 10, "strength": 7, "aerial": 6, "positioning": 4,
               "finishing": -12, "dribbling": -6, "reflexes": -20},
        "MF": {"passing": 9, "vision": 8, "stamina": 6, "technique": 5,
               "aerial": -5, "reflexes": -20},
        "FW": {"finishing": 12, "dribbling": 8, "pace": 7, "technique": 4,
               "marking": -14, "reflexes": -20},
    }[position]
    keys = ("finishing", "passing", "dribbling", "marking", "pace", "strength", "stamina",
            "technique", "positioning", "vision", "reflexes", "aerial")
    return {k: int(np.clip(round(overall + bias.get(k, 0) + rng.normal(0, 4)), 20, 99))
            for k in keys}


def _market_value(overall: int, potential: int, age: int) -> int:
    """Valor de mercado aproximado. Sera recalibrado no modulo de financas (M5)."""
    base = 0.7e6 * float(np.exp((overall - 50) / 8.0))
    if age <= 21:
        curve = 1.35
    elif age <= 27:
        curve = 1.0 + max(0, potential - overall) * 0.03
    elif age <= 30:
        curve = 0.75
    else:
        curve = max(0.15, 0.75 - (age - 30) * 0.15)
    return int(base * curve)


def _make_player(pid, rng, country, season_year, overall, position, age, club_id) -> Player:
    name = f"{rng.choice(FIRST_NAMES[country])} {rng.choice(SURNAMES[country])}"
    if age <= 22:
        potential = int(min(95, overall + rng.integers(6, 22)))
    elif age <= 26:
        potential = int(min(95, overall + rng.integers(0, 8)))
    else:
        potential = overall
    value = _market_value(overall, potential, age)
    return Player(
        id=pid, name=str(name), nationality=country, birth_year=season_year - age,
        position=position, foot="E" if rng.random() < 0.22 else "D",
        height_cm=int(rng.normal(190 if position == "GK" else 180, 6)),
        overall=overall, potential=potential,
        morale=int(rng.integers(60, 85)), form=int(rng.integers(55, 85)),
        club_id=club_id, wage=int(value / 110),
        contract_until=season_year + int(rng.integers(1, 5)),
        market_value=value, **_attributes(rng, overall, position),
    )


def generate_league(world: World, cfg: dict, streams: Streams, *, next_id: list[int]) -> League:
    """Cria a liga, seus clubes e seus elencos dentro de `world`."""
    country = cfg["pais"]
    n = int(cfg["clubes"])
    rng = streams.get("generate", cfg["id"])

    roots = list(CLUB_ROOTS[country])
    rng.shuffle(roots)
    patterns = CLUB_PATTERNS[country]

    league = League(id=cfg["id"], name=cfg["nome"], country=country, tier=int(cfg.get("tier", 1)))
    xi_offset = SQUAD_CURVE[:11].mean()

    for i, strength in enumerate(strength_profile(cfg, n)):
        club_id = next_id[0]
        next_id[0] += 1
        prim, sec = COLORS[i % len(COLORS)]
        reputation = int(np.clip(round((strength - 45) * 2.6), 5, 99))
        club = Club(
            id=club_id, name=patterns[i % len(patterns)].format(r=roots[i % len(roots)]),
            country=country, league_id=league.id, reputation=reputation,
            designed_strength=float(strength), color_primary=prim, color_secondary=sec,
            balance=int(reputation ** 2 * 12_000),
        )
        for slot in range(SQUAD_SIZE):
            ovr = int(np.clip(
                round(strength + SQUAD_CURVE[slot] - xi_offset + rng.normal(0, 1.2)), 35, 95))
            pid = next_id[0]
            next_id[0] += 1
            world.players[pid] = _make_player(
                pid, rng, country, world.season_year, ovr,
                SQUAD_SHAPE[slot], AGE_SHAPE[slot], club_id)
            club.player_ids.append(pid)
        world.clubs[club_id] = club
        league.club_ids.append(club_id)

    world.leagues[league.id] = league
    return league


def build_world(configs: list[dict], seed: int, season_year: int = 2027) -> tuple[World, Streams]:
    world = World(season_year=season_year)
    streams = Streams(seed)
    next_id = [1]
    for cfg in configs:
        generate_league(world, cfg, streams, next_id=next_id)
    return world, streams
