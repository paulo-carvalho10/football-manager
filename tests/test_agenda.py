"""O calendario real (fm.agenda): liga no domingo, copa no meio de semana, cada fase na
janela dela. Antes era uma fila de 4 em 4 dias, com a Libertadores entrando nos grupos em
setembro e uma temporada de dezenove meses no relogio."""

from __future__ import annotations

from datetime import date

import pytest

from fm.agenda import CONFLITOS, grade_das_ligas
from fm.carreira import Carreira
from fm.torneio import carregar


@pytest.fixture(scope="module")
def carreira():
    return Carreira.nova(["brasil_real", "brasil_b_real"], "Palmeiras", seed=21)


def test_a_temporada_vai_do_fim_de_janeiro_a_dezembro(carreira):
    """A Supercopa do Brasil abre o ano no fim de janeiro; o resto comeca em fevereiro."""
    c = carreira
    assert c.dias == sorted(c.dias)
    assert c.dias[0] >= date(c.temporada, 1, 20)
    assert c.agenda[0] == ("copa", "supercopa_do_brasil")
    assert c.dias[-1] <= date(c.temporada, 12, 31)


def test_liga_no_domingo_e_copa_no_meio_de_semana(carreira):
    c = carreira
    for (tipo, _), dia in zip(c.agenda, c.dias, strict=True):
        if tipo == "liga":
            assert dia.weekday() in (6, 2), dia      # domingo, ou quarta de rodada extra
        else:
            assert dia.weekday() in (1, 2, 3), dia   # terca a quinta
    # o Brasileirao: 38 rodadas de abril a dezembro, na ordem
    ligas = [d for (t, _), d in zip(c.agenda, c.dias, strict=True) if t == "liga"]
    assert ligas[0].month == 4 and ligas[-1].month == 12
    assert c.rodadas_da_liga() == 38


def test_cada_fase_da_libertadores_na_janela_dela(carreira):
    """A pre em fevereiro e marco, os grupos de abril ao comeco de junho, o mata-mata de
    agosto a outubro, a final no fim de novembro."""
    c = carreira
    t = carregar("libertadores")
    por_fase: dict[int, list[date]] = {}
    for (tipo, quem), dia, fase, reserva in zip(c.agenda, c.dias, c.fases_da_agenda,
                                                c.reservas, strict=True):
        if quem == "libertadores" and not reserva:
            por_fase.setdefault(fase, []).append(dia)
    meses = {k: {d.month for d in v} for k, v in por_fase.items()}
    # a janela FIFA de marco (fm.fifa) para tudo: a volta da terceira fase pode cair no
    # comeco de abril
    assert meses[0] | meses[1] <= {2, 3}
    assert meses[2] <= {3, 4}
    assert meses[3] <= {4, 5, 6}
    assert meses[4] <= {8, 9, 10, 11}
    assert meses[5] <= {11, 12}
    assert len(por_fase) == len(t.fases)


def test_copas_que_dividem_clube_nao_colam(carreira):
    """O grande brasileiro esta na Copa do Brasil e na Libertadores: as duas nunca no mesmo
    dia nem em dias seguidos. E a mesma copa nao joga duas vezes na mesma semana."""
    c = carreira
    dias: dict[str, list[date]] = {}
    for (tipo, quem), dia in zip(c.agenda, c.dias, strict=True):
        if tipo == "copa":
            dias.setdefault(quem, []).append(dia)
    for par in CONFLITOS:
        a, b = sorted(par)
        for x in dias.get(a, []):
            assert all(abs((x - y).days) > 1 for y in dias.get(b, [])), (a, b, x)
    for quem, ds in dias.items():
        assert all((y - x).days >= 6 for x, y in zip(ds, ds[1:])), quem


def test_cada_liga_tem_o_seu_calendario_na_grade():
    """A Championship (46 rodadas) usa quartas-feiras; o Paraguai (22) folga em domingos;
    as duas terminam no comeco de dezembro."""
    grade, mapa = grade_das_ligas(2027, {"ing": 46, "bra": 38, "par": 22})
    for liga, n in {"ing": 46, "bra": 38, "par": 22}.items():
        assert len(mapa[liga]) == n and mapa[liga] == sorted(set(mapa[liga]))
        ultima = grade[mapa[liga][-1]]
        assert ultima.month == 12, (liga, ultima)
    assert all(grade[i].weekday() == 6 for i in mapa["par"]), "o Paraguai so joga domingo"
