"""Portao de qualidade: o mundo e' crivel?

Esta e' a peca central do projeto. A pergunta que decide o jogo nao e' se a interface esta
bonita, e' se a TABELA FINAL e' crivel. Os alvos abaixo sao intervalos de futebol real; o
caminho rapido roda milhares de temporadas contra eles e o build quebra se sair da faixa.

AVISO: os intervalos vieram da ordem de grandeza conhecida das grandes ligas, NAO de um
dataset conferido. Antes de congelar, puxar as tabelas reais (sao publicas e pequenas) e
re-derivar. Ver README.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fm.match import DEFAULT_STYLE, Mentality, Style, simulate

# liga de referencia: 20 clubes, returno duplo, overall 56..82
REFERENCE_RATINGS = [82, 80, 78, 77, 75, 74, 73, 72, 71, 70,
                     69, 68, 67, 66, 65, 64, 62, 60, 58, 56]

TARGETS: dict[str, tuple[float, float]] = {
    "gols_por_jogo": (2.55, 2.80),
    "zero_a_zero_pct": (6.5, 9.5),
    "vitoria_casa_pct": (43.0, 47.5),
    "empate_pct": (23.5, 26.5),
    "vitoria_fora_pct": (27.5, 31.0),
    "margem_3_ou_mais_pct": (11.5, 15.5),
    "margem_4_ou_mais_pct": (3.5, 6.0),
    "cinco_ou_mais_gols_pct": (9.0, 12.5),
    "pontos_do_campeao": (74.0, 81.0),
    "pontos_do_lanterna": (22.0, 31.0),
    "melhor_elenco_campeao_pct": (33.0, 46.0),
}


@dataclass(slots=True)
class Metric:
    name: str
    value: float
    low: float
    high: float

    @property
    def ok(self) -> bool:
        return self.low <= self.value <= self.high


def measure(
    ratings: list[float] | None = None, *, seasons: int = 1000, seed: int = 2026,
    style: Style | None = None, mentality: Mentality = Mentality.NORMAL, voltas: int = 2,
) -> dict[str, float]:
    """Roda `seasons` temporadas no caminho rapido e devolve as metricas agregadas.

    `voltas=1` e turno unico (a Argentina, com 30 e 36 clubes): cada par joga uma vez.
    """
    ratings = list(ratings or REFERENCE_RATINGS)
    style = style or DEFAULT_STYLE
    n = len(ratings)
    rng = np.random.default_rng(seed)
    r = np.array(ratings, dtype=float)
    iu, ju = np.triu_indices(n, 1)
    if voltas == 1:
        home, away = iu, ju                  # turno unico: cada par joga uma vez
    else:
        home = np.concatenate([iu, ju])      # returno duplo: todo par joga nos dois mandos
        away = np.concatenate([ju, iu])
    rh, ra = r[home], r[away]

    tot_goals = tot_matches = 0
    zeros = home_w = draws = away_w = m3 = m4 = g5 = 0
    champ_pts: list[int] = []
    last_pts: list[int] = []
    best_titles = 0

    for _ in range(seasons):
        gh, ga = simulate(rh, ra, rng, style, mentality)
        margin, total = gh - ga, gh + ga
        tot_goals += int(total.sum())
        tot_matches += total.size
        zeros += int((total == 0).sum())
        home_w += int((margin > 0).sum())
        draws += int((margin == 0).sum())
        away_w += int((margin < 0).sum())
        m3 += int((np.abs(margin) >= 3).sum())
        m4 += int((np.abs(margin) >= 4).sum())
        g5 += int((total >= 5).sum())

        pts = np.zeros(n, dtype=int)
        gd = np.zeros(n, dtype=int)
        np.add.at(pts, home, np.where(margin > 0, 3, np.where(margin == 0, 1, 0)))
        np.add.at(pts, away, np.where(margin < 0, 3, np.where(margin == 0, 1, 0)))
        np.add.at(gd, home, margin)
        np.add.at(gd, away, -margin)
        order = np.lexsort((-gd, -pts))
        champ_pts.append(int(pts[order[0]]))
        last_pts.append(int(pts[order[-1]]))
        if order[0] == int(np.argmax(r)):
            best_titles += 1

    pc = 100.0 / tot_matches
    return {
        "gols_por_jogo": tot_goals / tot_matches,
        "zero_a_zero_pct": zeros * pc,
        "vitoria_casa_pct": home_w * pc,
        "empate_pct": draws * pc,
        "vitoria_fora_pct": away_w * pc,
        "margem_3_ou_mais_pct": m3 * pc,
        "margem_4_ou_mais_pct": m4 * pc,
        "cinco_ou_mais_gols_pct": g5 * pc,
        "pontos_do_campeao": float(np.mean(champ_pts)),
        "pontos_do_lanterna": float(np.mean(last_pts)),
        "melhor_elenco_campeao_pct": 100.0 * best_titles / seasons,
    }


def resolve_targets(overrides: dict[str, tuple[float, float]] | None = None):
    """Alvos da liga de referencia, com sobrescrita por liga.

    Aplicar os alvos da referencia a uma liga de estilo diferente e erro: o Brasileirao tem
    mando maior (menos vitoria fora) e liga mais aberta (campeao com menos pontos) por
    motivos reais. Cada liga declara os seus em [alvos], e o que ela nao declarar cai na
    referencia.
    """
    alvos = dict(TARGETS)
    for k, v in (overrides or {}).items():
        if k not in TARGETS:
            raise ValueError(f"alvo desconhecido {k!r}; validos: {sorted(TARGETS)}")
        alvos[k] = (float(v[0]), float(v[1]))
    return alvos


def report(targets: dict[str, tuple[float, float]] | None = None, **kwargs) -> list[Metric]:
    alvos = resolve_targets(targets)
    values = measure(**kwargs)
    return [Metric(k, values[k], *alvos[k]) for k in alvos]
