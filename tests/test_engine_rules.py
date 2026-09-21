"""Guardas de arquitetura. Estas regras sao decisoes de projeto, nao estilo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fm.match import FLOOR, K, Mentality, Style, effective_rating, lambdas, simulate

FM_DIR = Path(__file__).resolve().parent.parent / "fm"


def test_motor_nao_faz_io():
    """Nenhum modulo do motor imprime nem le. Quem fala com o usuario e a camada cli."""
    proibidos = []
    for path in FM_DIR.glob("*.py"):
        if path.name == "cli.py":
            continue
        texto = path.read_text(encoding="utf-8")
        for termo in ("print(", "input("):
            if termo in texto:
                proibidos.append(f"{path.name}: {termo}")
    assert not proibidos, f"I/O dentro do motor: {proibidos}"


def test_desgaste_igual_se_cancela():
    """Propriedade central: o motor usa a DIFERENCA, entao desgaste simetrico nao muda nada.

    E por isso que desgaste so importa quando e assimetrico -- calendario apertado,
    elenco curto, jogo no meio de semana.
    """
    base = lambdas(78, 64)
    penalizado = lambdas(effective_rating(78, fatigue=5), effective_rating(64, fatigue=5))
    assert np.allclose(base, penalizado)


def test_desgaste_assimetrico_ajuda_o_azarao():
    lh_base, la_base = lambdas(78, 64)
    lh_pen, la_pen = lambdas(effective_rating(78, fatigue=6), 64)
    assert lh_pen < lh_base       # favorito desgastado cria menos
    assert la_pen > la_base       # e concede mais


def test_teto_do_desgaste():
    """Desgaste inclina o jogo, nunca o decide: a penalidade tem teto duro."""
    assert effective_rating(78, fatigue=99) == pytest.approx(70.0)


def test_piso_de_gols_ninguem_e_nulo():
    """Mesmo num massacre o time fraco tem chance real de marcar (e de segurar o 0-0).

    Quem garante isso NAO e o FLOOR: e a saturacao. Com tanh, d nunca passa de 1, entao o
    lado fraco nunca cai abaixo de mu*exp(-K - mando/2) ~ 0.60 gol esperado, qualquer que
    seja o tamanho do gap. O FLOOR e so uma rede para estilo de liga extremo
    (ver test_floor_e_rede_para_estilo_extremo).
    """
    _, la = lambdas(92, 40)
    # assintota da saturacao: tanh tende a 1, entao lambda tende a este valor por cima
    assintota = Style().goals_base * np.exp(-K - Style().home_adv / 2)
    assert assintota < la < assintota * 1.03
    assert la > FLOOR
    # e aumentar mais o gap quase nao muda: o azarao tem um patamar garantido
    _, la_extremo = lambdas(99, 20)
    assert la_extremo > assintota * 0.999
    rng = np.random.default_rng(1)
    gh, ga = simulate(np.full(200_000, 92.0), np.full(200_000, 40.0), rng)
    assert (ga > 0).mean() > 0.25          # o pequeno marca em mais de 1 jogo em 4
    assert ((gh + ga) == 0).mean() > 0.005  # e o 0-0 nunca zera
    assert (gh - ga >= 7).mean() < 0.02     # mas 7-0 continua raro


def test_floor_e_rede_para_estilo_extremo():
    """O FLOOR existe para configuracao maluca de liga, nao para o jogo normal."""
    magro = Style(goals_base=0.5, home_adv=0.30)
    _, la = lambdas(92, 40, magro)
    assert la == pytest.approx(FLOOR)


def test_saturacao_limita_a_goleada():
    """Sem tanh, um gap gigante viraria 9-0. Com ele, o favorito para de crescer."""
    l_gap16 = lambdas(78, 62)[0]
    l_gap32 = lambdas(86, 54)[0]
    assert l_gap32 < l_gap16 * 1.35        # dobrar o gap nao dobra o ataque


def test_mentalidade_copa_trava_o_jogo():
    rng = np.random.default_rng(7)
    r = np.full(200_000, 72.0)
    liga = simulate(r, r, rng, Style(), Mentality.NORMAL)
    copa = simulate(r, r, rng, Style(), Mentality.CUP)
    gols_liga = (liga[0] + liga[1]).mean()
    gols_copa = (copa[0] + copa[1]).mean()
    assert gols_copa < gols_liga
    assert ((copa[0] + copa[1]) == 0).mean() > ((liga[0] + liga[1]) == 0).mean()
