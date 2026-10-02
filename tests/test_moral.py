"""Moral do jogador e quimica do vestiario (fm.moral)."""

from __future__ import annotations

import statistics as st
from collections import Counter

import pytest

from fm import moral
from fm.carreira import Carreira


@pytest.fixture
def carreira():
    return Carreira.nova("brasil_real", "Santos", seed=7)


def _onze(c):
    return {p.id for p in c.world.best_xi(c.clube_id)}


def test_vitoria_levanta_derrota_abate_e_goleada_abala_mais(carreira):
    c = carreira
    onze = _onze(c)
    alvo = next(iter(onze))

    def depois(pro, contra):
        c.world.players[alvo].morale = moral.MORAL_NEUTRA
        moral.depois_do_jogo(c.world, c.clube_id, pro, contra, onze, Counter(), set())
        return c.world.players[alvo].morale

    vitoria, derrota, goleada = depois(2, 1), depois(0, 1), depois(0, 4)
    assert vitoria > moral.MORAL_NEUTRA > derrota > goleada


def test_gol_da_confianca(carreira):
    c = carreira
    onze = _onze(c)
    autor, outro = list(onze)[:2]
    for pid in (autor, outro):
        c.world.players[pid].morale = moral.MORAL_NEUTRA
    moral.depois_do_jogo(c.world, c.clube_id, 1, 1, onze, Counter({autor: 1}), set())
    assert c.world.players[autor].morale > c.world.players[outro].morale


def test_o_reserva_esquecido_fica_insatisfeito_e_um_jogo_no_banco_nao_pesa(carreira):
    """Uma rodada no banco nao e nada; uma duzia seguida, para quem esperava jogar, e."""
    c = carreira
    elenco = sorted(c.world.squad(c.clube_id), key=lambda p: -p.overall)
    esquecido = elenco[5]                       # entre os 14 que esperam jogar
    jogaram = {p.id for p in elenco[:14]} - {esquecido.id}
    esquecido.morale = moral.MORAL_NEUTRA
    moral.depois_do_jogo(c.world, c.clube_id, 1, 1, jogaram, Counter(), set())
    assert esquecido.morale >= moral.MORAL_NEUTRA - 3
    for _ in range(13):
        moral.depois_do_jogo(c.world, c.clube_id, 1, 1, jogaram, Counter(), set())
    assert esquecido.morale < moral.INSATISFEITO
    # jogou: a contagem do banco zera
    moral.depois_do_jogo(c.world, c.clube_id, 1, 1, jogaram | {esquecido.id}, Counter(), set())
    assert esquecido.id not in c.world.banco_seguido


def test_o_lesionado_nao_se_frustra_por_nao_jogar(carreira):
    c = carreira
    elenco = sorted(c.world.squad(c.clube_id), key=lambda p: -p.overall)
    machucado = elenco[3]
    jogaram = {p.id for p in elenco[:14]} - {machucado.id}
    machucado.morale = moral.MORAL_NEUTRA
    for _ in range(12):
        moral.depois_do_jogo(c.world, c.clube_id, 1, 1, jogaram, Counter(), {machucado.id})
    assert machucado.morale > moral.INSATISFEITO


def test_o_bonus_e_neutro_no_neutro_e_tem_teto(carreira):
    c = carreira
    onze = list(_onze(c))
    for pid in onze:
        c.world.players[pid].morale = moral.MORAL_NEUTRA
    c.world.quimica[c.clube_id] = moral.QUIMICA_NEUTRA
    assert moral.bonus(c.world, c.clube_id, onze) == 0
    for pid in onze:
        c.world.players[pid].morale = 99
    c.world.quimica[c.clube_id] = 99
    assert moral.bonus(c.world, c.clube_id, onze) == moral.TETO_DO_BONUS
    for pid in onze:
        c.world.players[pid].morale = 5
    c.world.quimica[c.clube_id] = 5
    assert moral.bonus(c.world, c.clube_id, onze) == -moral.TETO_DO_BONUS


def test_na_virada_a_moral_volta_e_muita_contratacao_custa_quimica(carreira):
    c = carreira
    outro = next(k for k in c.world.clubs if k != c.clube_id)
    c.world.quimica[c.clube_id] = c.world.quimica[outro] = 80
    p = c.world.squad(c.clube_id)[0]
    p.morale = 95
    moral.na_virada(c.world, Counter({c.clube_id: 8}))
    assert c.world.quimica[c.clube_id] < c.world.quimica[outro]
    assert moral.MORAL_NEUTRA < p.morale < 95


def test_uma_temporada_mexe_na_moral_sem_saturar(carreira):
    """REGRESSAO: com +1 de moral por jogo disputado e volta lenta ao normal, os titulares
    de quase todo clube saturavam perto de 90 -- e o melhor elenco foi campeao 0 vezes em
    16 temporadas, empatado pelo momento de quem embalava primeiro."""
    c = carreira
    while not c.acabou:
        c.avancar()
    ids = c.world.leagues[c._id("brasil_real")].club_ids
    medias = [st.mean(c.world.players[p.id].morale for p in c.world.best_xi(k)) for k in ids]
    assert 62 < st.mean(medias) < 80, "a moral do mundo saiu do lugar"
    quimicas = [moral.quimica(c.world, k) for k in ids]
    assert max(quimicas) - min(quimicas) >= 15, "a quimica nao separa os clubes"
