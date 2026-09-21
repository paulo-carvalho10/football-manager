"""O PORTAO. Se este arquivo falha, o mundo deixou de ser crivel e nada mais importa.

Roda o caminho rapido contra intervalos de futebol real. Quebrar um alvo e build vermelho.
"""

from __future__ import annotations

import numpy as np

from fm.calibration import TARGETS, report
from fm.competition import knockout_tie
from fm.match import Mentality, Style


def test_portao_de_calibracao():
    metrics = report(seasons=400, seed=2026)
    fora = [f"{m.name}={m.value:.2f} fora de [{m.low}, {m.high}]" for m in metrics if not m.ok]
    assert not fora, "mundo deixou de ser crivel: " + "; ".join(fora)


def test_todos_os_alvos_sao_medidos():
    """Nao pode existir alvo declarado que ninguem mede."""
    assert {m.name for m in report(seasons=5)} == set(TARGETS)


def test_orcamento_de_performance():
    """Uma rodada mundial tem que caber em 1 segundo. Aqui medimos 100 mil partidas."""
    import time
    rng = np.random.default_rng(1)
    r = np.random.default_rng(2).uniform(55, 85, 100_000)
    from fm.match import simulate
    t0 = time.perf_counter()
    simulate(r, r[::-1], rng)
    assert time.perf_counter() - t0 < 1.0


def _zebra(legs, mentality, seed=9, n=120_000):
    """Fracao de duelos em que o time de 64 elimina o de 78."""
    rng = np.random.default_rng(seed)
    fav, azarao = 1, 2
    ratings = {fav: 78.0, azarao: 64.0}
    winners = knockout_tie([azarao] * n, [fav] * n, ratings, rng, Style(), mentality, legs=legs)
    return float(np.mean(winners == azarao))


def test_zebra_em_mata_mata_existe_e_e_rara():
    z = _zebra(2, Mentality.CUP)
    assert 0.22 < z < 0.36


def test_mentalidade_copa_aumenta_a_zebra():
    assert _zebra(2, Mentality.CUP) > _zebra(2, Mentality.NORMAL) + 0.02


def test_ida_e_volta_ajuda_o_azarao_mais_que_jogo_unico():
    """Em ida e volta o pequeno ganha um jogo em casa. Medido: 29,0% contra 27,1%."""
    assert _zebra(2, Mentality.CUP) > _zebra(1, Mentality.CUP)


def test_copa_e_menos_previsivel_que_liga():
    """O gigante leva menos copa do que liga -- e isso NAO usa aleatoriedade extra.

    Em 38 jogos o melhor elenco regride para a media e aparece no topo. Em 4 duelos, nao
    da tempo. E por isso que copa e a competicao da esperanca.
    """
    from fm.calibration import measure
    espanha = [88, 86, 82, 75, 73, 72, 70, 69, 68, 67, 66, 65, 64, 63, 61, 60, 58, 57, 55, 53]
    liga = measure(espanha, seasons=400, seed=4)["melhor_elenco_campeao_pct"] / 100.0

    rng = np.random.default_rng(4)
    n_edicoes = 20_000
    ratings = dict(enumerate(espanha[:16]))
    alive = np.tile(np.arange(16), (n_edicoes, 1))
    for _ in range(4):
        half = alive.shape[1] // 2
        a, b = alive[:, :half].ravel(), alive[:, half:].ravel()
        win = knockout_tie(list(b), list(a), ratings, rng, Style(), Mentality.CUP, legs=2)
        alive = win.reshape(n_edicoes, half)
        idx = np.arange(alive.shape[1])[None, :].repeat(n_edicoes, 0)
        alive = np.take_along_axis(alive, rng.permuted(idx, axis=1), axis=1)
    copa = float(np.mean(alive.ravel() == 0))

    assert copa < liga, f"copa {copa:.3f} deveria ser menos previsivel que liga {liga:.3f}"
