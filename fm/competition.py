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
            for f in base:
                # o mando alterna a cada turno. REGRESSAO: todo turno extra invertia o
                # mando do primeiro, e no 3o turno (Escocia, Suica) quem mandou no 2o
                # mandava de novo
                casa, fora = (f.away, f.home) if leg % 2 else (f.home, f.away)
                fixtures.append(Fixture(casa, fora, f.matchday + deslocamento))
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
    taticas: dict | None = None,
) -> list[Result]:
    """Simula um lote de partidas de uma vez -- este e o caminho rapido.

    `taticas` mapeia clube -> Tatica. So os clubes com tatica escolhida aparecem ali; o
    resto joga no padrao. O par de multiplicadores sai de tatica.confronto, porque o efeito
    de uma formacao depende da que esta do outro lado.
    """
    if not fixtures:
        return []
    rh = np.array([ratings[f.home] for f in fixtures], dtype=float)
    ra = np.array([ratings[f.away] for f in fixtures], dtype=float)
    from fm.tatica import Tatica, confronto
    t = taticas or {}
    padrao = Tatica()
    # o confronto e o mesmo para o mesmo par de taticas: sem tatica escolhida (quase
    # todo jogo do mundo) e padrao contra padrao, e calcular de novo a cada partida era
    # o grosso da temporada simulada das ligas de fora
    ja: dict[tuple[int, int], tuple] = {}

    def par(a, b):
        chave = (id(a), id(b))
        if chave not in ja:
            ja[chave] = confronto(a, b)
        return ja[chave]

    pares = [par(t.get(f.home, padrao), t.get(f.away, padrao)) for f in fixtures]
    mc = np.array([p[0] for p in pares])
    mf = np.array([p[1] for p in pares])
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
    partidas contra 8 adversarios DIFERENTES, metade em casa, 2 de cada pote. Nao joga
    contra todos.

    Montada RODADA A RODADA, como o sorteio da UEFA: cada rodada e um emparelhamento em
    que cada clube joga UMA vez, contra quem ainda nao enfrentou, sem passar de 2
    adversarios do mesmo pote. A versao anterior (um grafo circulante) garantia os potes,
    mas punha dois jogos do mesmo clube na mesma rodada -- a fase de liga era jogada de
    duas em duas rodadas. E para 36 clubes em 4 potes nao ha divisao do circulante em
    rodadas: os deslocamentos que dao o adversario do mesmo pote formam ciclos impares.

    Quando os potes nao dividem por igual (mundo com menos clubes), a cota de pote e
    relaxada; se nem assim fechar, o metodo do circulo resolve. As tentativas vem de um
    sorteio com semente fixa: o mesmo mundo da o mesmo calendario. O mando sai de um
    circuito euleriano -- metade em casa, metade fora, para todos.
    """
    n = len(club_ids)
    if adversarios % 2 or adversarios >= n:
        raise ValueError(f"adversarios deve ser par e menor que {n}; veio {adversarios}")
    if n % 2:
        raise ValueError("liga suica exige numero par de clubes")

    # potes pela ordem recebida (a de forca): os `tamanho` primeiros sao o pote 1...
    tamanho = max(1, n // potes)
    pote = {c: min(i // tamanho, potes - 1) for i, c in enumerate(club_ids)}
    cota = -(-adversarios // potes)
    rodadas = (_rodadas_suicas(club_ids, adversarios, pote, cota, tentativas=40)
               or _rodadas_suicas(club_ids, adversarios, pote, adversarios, tentativas=40)
               or _rodadas_do_circulo(club_ids, adversarios))
    mandante = _mandos_equilibrados([par for r in rodadas for par in r])
    return [Fixture(a, b, numero) if mandante[(a, b)] else Fixture(b, a, numero)
            for numero, rodada in enumerate(rodadas, 1) for a, b in rodada]


def _rodadas_suicas(clubes: list[int], k: int, pote: dict[int, int], cota: int,
                    tentativas: int) -> list[list[tuple[int, int]]] | None:
    for t in range(tentativas):
        rng = np.random.default_rng([len(clubes), k, cota, t, *clubes])
        enfrentou: dict[int, set[int]] = {c: set() for c in clubes}
        por_pote: dict[int, dict[int, int]] = {c: {} for c in clubes}

        def pode(a: int, b: int) -> bool:
            return (b not in enfrentou[a] and por_pote[a].get(pote[b], 0) < cota
                    and por_pote[b].get(pote[a], 0) < cota)

        feitas = []
        for _ in range(k):
            rodada = _emparelhar(list(clubes), pode, rng, limite=4_000)
            if rodada is None:
                break
            for a, b in rodada:
                enfrentou[a].add(b)
                enfrentou[b].add(a)
                por_pote[a][pote[b]] = por_pote[a].get(pote[b], 0) + 1
                por_pote[b][pote[a]] = por_pote[b].get(pote[a], 0) + 1
            feitas.append(rodada)
        if len(feitas) == k:
            return feitas
    return None


def _emparelhar(livres: list[int], pode, rng, limite: int) -> list[tuple[int, int]] | None:
    """Emparelhamento perfeito de `livres` so com pares permitidos: busca em profundidade
    pelo clube com menos opcoes. None se nao achar dentro do limite de passos."""
    passos = [0]

    def buscar(restam: list[int]):
        if not restam:
            return []
        passos[0] += 1
        if passos[0] > limite:
            return None
        opcoes = {a: [b for b in restam if b != a and pode(a, b)] for a in restam}
        a = min(restam, key=lambda x: (len(opcoes[x]), x))
        candidatos = list(opcoes[a])
        rng.shuffle(candidatos)
        for b in candidatos:
            resto = buscar([x for x in restam if x != a and x != b])
            if resto is not None:
                return [(a, b)] + resto
        return None

    return buscar(livres)


def _rodadas_do_circulo(clubes: list[int], k: int) -> list[list[tuple[int, int]]]:
    """As k primeiras rodadas do metodo do circulo: sempre fecha, sem olhar pote."""
    fixo, gira = clubes[0], list(clubes[1:])
    rodadas = []
    for _ in range(k):
        lista = [fixo] + gira
        rodadas.append([(lista[i], lista[-1 - i]) for i in range(len(lista) // 2)])
        gira = gira[-1:] + gira[:-1]
    return rodadas


def _mandos_equilibrados(pares: list[tuple[int, int]]) -> dict[tuple[int, int], bool]:
    """Orienta cada jogo por um circuito euleriano: em grafo de grau par, cada clube sai
    (joga em casa) tantas vezes quanto entra. {par: True se o primeiro e mandante}."""
    vizinhos: dict[int, list[tuple[int, int]]] = {}
    for idx, (a, b) in enumerate(pares):
        vizinhos.setdefault(a, []).append((b, idx))
        vizinhos.setdefault(b, []).append((a, idx))
    usado = [False] * len(pares)
    mandante: dict[tuple[int, int], bool] = {}
    ponteiro = {v: 0 for v in vizinhos}
    for inicio in sorted(vizinhos):
        pilha = [inicio]
        while pilha:
            v = pilha[-1]
            lista = vizinhos[v]
            while ponteiro[v] < len(lista) and usado[lista[ponteiro[v]][1]]:
                ponteiro[v] += 1
            if ponteiro[v] == len(lista):
                pilha.pop()
                continue
            w, idx = lista[ponteiro[v]]
            usado[idx] = True
            mandante[pares[idx]] = pares[idx][0] == v     # v -> w: v manda
            pilha.append(w)
    return mandante
