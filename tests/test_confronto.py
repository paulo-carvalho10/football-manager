"""Confronto de formacoes: tatica tem de dar resultado, sem virar gabarito."""

from __future__ import annotations

import numpy as np
import pytest

from fm.competition import Fixture, play_fixtures
from fm.match import Style
from fm.tatica import FORMACOES, Tatica, confronto

ESTILO = Style(goals_base=1.22, home_adv=0.0)   # sem mando: isola a tatica
N = 30000


def _duelo(fa: str, fb: str, seed: int = 5):
    rng = np.random.default_rng(seed)
    r = play_fixtures([Fixture(1, 2, 1)] * N, {1: 72.0, 2: 72.0}, rng, ESTILO,
                      taticas={1: Tatica(formacao=fa), 2: Tatica(formacao=fb)})
    a = np.array([x.goals_home for x in r])
    b = np.array([x.goals_away for x in r])
    return 100 * np.mean(a > b), float((a + b).mean())


@pytest.fixture(scope="module")
def matriz():
    forms = list(FORMACOES)
    return forms, {(x, y): _duelo(x, y)[0] for x in forms for y in forms}


def test_a_formacao_padrao_e_neutra():
    """ANCORA DA CALIBRACAO. Quem nao escolheu tatica joga no padrao, entao se o espelho
    dele nao for 1.0 a liga inteira sai com media de gols diferente da calibrada -- foi o
    que aconteceu: valia 1.092 e todo jogo tinha 9% mais gols, em silencio."""
    assert confronto(Tatica(), Tatica()) == (1.0, 1.0)


def test_confronto_e_antissimetrico_no_espelho():
    for f in FORMACOES:
        a, b = confronto(Tatica(formacao=f), Tatica(formacao=f))
        assert abs(a - b) < 1e-9, f"{f} contra si mesma tem de ser simetrico"


def test_existe_contra_formacao_de_verdade(matriz):
    """A INTERACAO tem de dominar o efeito individual.

    Um termo do tipo `A - B` se decompoe em efeito de A menos efeito de B, ou seja, diz
    'esta formacao e melhor' e nunca 'esta formacao e dificil para aquela'. Medido assim,
    a interacao dava 0,2 ponto. Com choques estruturais em PRODUTO, ela domina.
    """
    forms, M = matriz
    media = np.mean(list(M.values()))
    lin = {f: np.mean([M[(f, x)] for x in forms]) for f in forms}
    col = {f: np.mean([M[(x, f)] for x in forms]) for f in forms}
    inter = {k: M[k] - lin[k[0]] - col[k[1]] + media for k in M}

    amp_inter = max(inter.values()) - min(inter.values())
    amp_indiv = max(lin.values()) - min(lin.values())
    assert amp_inter > 2.5, f"contra-formacao fraca demais: {amp_inter:.1f} pontos"
    assert amp_inter > amp_indiv, (
        f"o efeito individual ({amp_indiv:.1f}) domina o confronto ({amp_inter:.1f}): "
        "isso e 'formacao melhor', nao contra-formacao")


def test_nenhuma_formacao_e_botao_de_vencer(matriz):
    """Tatica e escolha com troca. Se uma formacao ganha de todas, virou gabarito."""
    forms, M = matriz
    for f in forms:
        media = np.mean([M[(f, x)] for x in forms if x != f])
        assert 32.0 < media < 41.0, f"{f} com media de vitoria fora da faixa: {media:.1f}%"
    assert max(M.values()) - min(M.values()) < 12.0, "amplitude grande demais"


def test_os_choques_previstos_acontecem(matriz):
    """Os tres choques que o modelo afirma, conferidos um a um."""
    _, M = matriz
    # ponta contra linha de tres: sem lateral, o corredor fica livre
    assert M[("4-3-3", "3-4-3")] > M[("3-4-3", "4-3-3")] + 2
    # defesa de cinco absorve ataque de tres
    assert M[("5-3-2", "4-3-3")] > M[("4-3-3", "5-3-2")] + 1
    # meio povoado sufoca meio curto
    assert M[("4-5-1", "4-3-3")] > M[("4-3-3", "4-5-1")] + 1


def test_o_confronto_muda_o_carater_do_jogo():
    """Nao e so quem ganha: o par decide se o jogo e travado ou aberto."""
    _, travado = _duelo("4-5-1", "5-3-2")
    _, aberto = _duelo("3-4-3", "3-4-3")
    assert aberto > travado + 0.6, f"{aberto:.2f} contra {travado:.2f} gols"
