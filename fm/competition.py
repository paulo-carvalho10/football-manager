"""Primitivas de competicao, componiveis.

Nao existe "Brasileirao" em codigo. Existem tres fases -- pontos corridos, mata-mata e
grupos -- e um campeonato e' uma lista delas descrita em arquivo. Liga nova, copa nova ou
continental nova: arquivo novo, zero codigo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fm.match import Mentality, Style, penalty_shootout, simulate


@dataclass(frozen=True, slots=True)
class Fixture:
    home: int
    away: int
    matchday: int


@dataclass(slots=True)
class Result:
    home: int
    away: int
    goals_home: int
    goals_away: int
    matchday: int


def round_robin(club_ids: list[int], legs: int = 2) -> list[Fixture]:
    """Metodo do circulo para os confrontos, e mando distribuido em seguida.

    Os CONFRONTOS saem do circulo (cada clube enfrenta todos os outros uma vez por turno).
    O MANDO nao: decidi-lo pela posicao no circulo dava calendario absurdo -- 19 dos 20
    clubes jogavam um turno inteiro em casa e o outro inteiro fora. O mando e atribuido
    depois, por regra gulosa que equilibra o total e evita sequencia longa, que e o que
    um calendario de verdade faz.
    """
    ids = list(club_ids)
    if len(ids) % 2:
        raise ValueError("pontos corridos exige numero par de clubes")
    n = len(ids)

    rodadas: list[list[tuple[int, int]]] = []
    arr = ids[:]
    for _ in range(n - 1):
        rodadas.append([(arr[k], arr[n - 1 - k]) for k in range(n // 2)])
        arr = [arr[0], arr[-1], *arr[1:-1]]     # gira todos menos o primeiro

    em_casa: dict[int, int] = dict.fromkeys(ids, 0)
    ultimo: dict[int, str] = {}
    fixtures: list[Fixture] = []
    for r, pares in enumerate(rodadas, start=1):
        for a, b in pares:
            # manda quem tem menos jogos em casa; empatado, quem jogou fora na ultima
            peso_a = (em_casa[a], ultimo.get(a) == "C")
            peso_b = (em_casa[b], ultimo.get(b) == "C")
            casa, fora = (a, b) if peso_a <= peso_b else (b, a)
            em_casa[casa] += 1
            ultimo[casa], ultimo[fora] = "C", "F"
            fixtures.append(Fixture(casa, fora, r))

    if legs > 1:
        base = fixtures[:]
        for leg in range(1, legs):
            deslocamento = leg * (n - 1)
            for f in base:                      # returno: inverte o mando
                fixtures.append(Fixture(f.away, f.home, f.matchday + deslocamento))
    return fixtures


def group_stage(club_ids: list[int], n_groups: int, legs: int = 2) -> list[list[Fixture]]:
    """Fase de grupos = pontos corridos dentro de cada grupo. Serpentina por forca de entrada."""
    if len(club_ids) % n_groups:
        raise ValueError("clubes nao dividem igualmente nos grupos")
    groups: list[list[int]] = [[] for _ in range(n_groups)]
    for i, cid in enumerate(club_ids):                  # serpentina evita grupo da morte fixo
        row, col = divmod(i, n_groups)
        groups[col if row % 2 == 0 else n_groups - 1 - col].append(cid)
    return [round_robin(g, legs=legs) for g in groups]


def play_fixtures(
    fixtures: list[Fixture],
    ratings: dict[int, float],
    rng: np.random.Generator,
    style: Style,
    mentality: Mentality = Mentality.NORMAL,
    taticas: dict[int, tuple[float, float]] | None = None,
) -> list[Result]:
    """Simula um lote de partidas de uma vez -- este e o caminho rapido.

    `taticas` mapeia clube -> (multiplica os proprios gols, multiplica os do adversario).
    So os clubes com tatica escolhida aparecem ali; o resto joga no padrao.
    """
    if not fixtures:
        return []
    rh = np.array([ratings[f.home] for f in fixtures], dtype=float)
    ra = np.array([ratings[f.away] for f in fixtures], dtype=float)
    t = taticas or {}
    neutro = (1.0, 1.0)
    # os gols de cada lado sofrem o proprio ataque E a defesa do adversario
    mc = np.array([t.get(f.home, neutro)[0] * t.get(f.away, neutro)[1] for f in fixtures])
    mf = np.array([t.get(f.away, neutro)[0] * t.get(f.home, neutro)[1] for f in fixtures])
    gh, ga = simulate(rh, ra, rng, style, mentality, mult_casa=mc, mult_fora=mf)
    return [Result(f.home, f.away, int(x), int(y), f.matchday)
            for f, x, y in zip(fixtures, gh, ga, strict=True)]


def knockout_tie(
    home_first: list[int], away_first: list[int],
    ratings: dict[int, float], rng: np.random.Generator,
    style: Style, mentality: Mentality = Mentality.CUP, legs: int = 2,
    empate_favorece_visitante: bool = False,
) -> np.ndarray:
    """Resolve N confrontos de uma vez. Retorna o id de quem avanca.

    `home_first` recebe a primeira mao em casa. Em ida e volta o mando se alterna, o que da
    ao azarao um jogo em casa -- medido: eleva a zebra de 27,1% para 29,0% num gap de 14.

    `empate_favorece_visitante` existe para as duas primeiras fases da Copa do Brasil: jogo
    unico e quem visita avanca no empate. Nenhum outro torneio meu tem essa regra.
    """
    a = np.array(away_first, dtype=int)      # decide a volta em casa
    b = np.array(home_first, dtype=int)
    ra = np.array([ratings[i] for i in a], dtype=float)
    rb = np.array([ratings[i] for i in b], dtype=float)
    if legs == 1:
        ga, gb = simulate(ra, rb, rng, style, mentality)
    else:
        g1b, g1a = simulate(rb, ra, rng, style, mentality)   # mao 1: b em casa
        g2a, g2b = simulate(ra, rb, rng, style, mentality)   # mao 2: a em casa
        ga, gb = g1a + g2a, g1b + g2b
    tied = ga == gb
    a_wins = ga > gb
    if tied.any():
        if empate_favorece_visitante:
            # em jogo unico `a` manda; o visitante e `b`, e o empate passa para ele
            a_wins = np.where(tied, False, a_wins)
        else:
            shoot = penalty_shootout(ra, rb, rng)            # empate -> penaltis
            a_wins = np.where(tied, shoot, a_wins)
    return np.where(a_wins, a, b)


def liga_suica(club_ids: list[int], adversarios: int = 8, potes: int = 4) -> list[Fixture]:
    """Fase de liga no modelo suico: tabela unica e calendario PARCIAL.

    E o formato da Champions desde 2024-25: 36 clubes numa tabela so, cada um joga 8
    partidas contra 8 adversarios DIFERENTES, metade em casa. Nao joga contra todos.

    A construcao usa um grafo circulante e nao sorteio com repeticao, porque circulante
    garante de graca as tres propriedades que a regra exige:

    - cada clube enfrenta `adversarios` rivais distintos (grafo k-regular);
    - metade em casa e metade fora (orientacao por paridade do deslocamento);
    - INTERCALANDO os potes na ordem, cada clube pega exatamente 2 de cada pote --
      que e a regra do sorteio real, sem precisar de sorteio com retentativa.
    """
    n = len(club_ids)
    if adversarios % 2 or adversarios >= n:
        raise ValueError(f"adversarios deve ser par e menor que {n}; veio {adversarios}")
    if n % 2:
        raise ValueError("liga suica exige numero par de clubes")

    # intercala os potes: pote0[0], pote1[0], ..., pote0[1], pote1[1], ...
    tamanho = max(1, n // potes)
    grupos = [club_ids[i * tamanho:(i + 1) * tamanho] for i in range(potes)]
    grupos[-1] += club_ids[potes * tamanho:]
    ordem: list[int] = []
    for i in range(max(len(g) for g in grupos)):
        for g in grupos:
            if i < len(g):
                ordem.append(g[i])

    fixtures: list[Fixture] = []
    rodada = 0
    for d in range(1, adversarios // 2 + 1):
        for i in range(n):
            j = (i + d) % n
            # deslocamento impar: manda quem esta antes; par: manda quem esta depois.
            # E o que reparte 4 jogos em casa e 4 fora para todo mundo.
            casa, fora = (ordem[i], ordem[j]) if d % 2 else (ordem[j], ordem[i])
            fixtures.append(Fixture(casa, fora, rodada + 1))
        rodada += 2
    return fixtures
