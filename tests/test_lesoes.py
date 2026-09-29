"""Lesao: quem se machuca sai de campo, fica fora por alguns jogos do clube e volta."""

from __future__ import annotations

import numpy as np

from fm.carreira import Carreira
from fm.eventos import simular_partida
from fm.lesoes import DepartamentoMedico, Lesao
from fm.match import Style

ESTILO = Style(goals_base=1.22, home_adv=0.36)


def _partidas(n, bancos=True):
    c = Carreira.nova("brasil_real", "Santos", seed=42)
    w, ids = c.world, c.world.leagues[c.liga_id].club_ids
    rng = np.random.default_rng(7)
    for _ in range(n):
        a, b = (int(x) for x in rng.choice(ids, 2, replace=False))
        yield w, simular_partida(
            w, a, b, [x.id for x in w.best_xi(a)], [x.id for x in w.best_xi(b)], rng, ESTILO,
            bancos={a: c.banco(a), b: c.banco(b)} if bancos else None)


def test_o_machucado_sai_de_campo_no_fim_do_bloco():
    vistos = 0
    for w, p in _partidas(150):
        for pid in p.lesionados:
            ev = next(e for e in p.eventos if e.tipo == "lesao" and e.jogador == pid)
            if ev.minuto > 85:
                continue                  # o ultimo bloco termina com o apito
            vistos += 1
            assert pid not in p.em_campo_casa + p.em_campo_fora
            troca = next(e for e in p.eventos if e.tipo == "substituicao" and e.jogador == pid)
            # entra alguem do mesmo setor sempre que o banco tem
            assert w.players[troca.segundo].position == w.players[pid].position
    assert vistos > 30


def test_sem_banco_o_time_fica_com_um_a_menos():
    for _, p in _partidas(150, bancos=False):
        for pid in p.lesionados:
            ev = next(e for e in p.eventos if e.tipo == "lesao" and e.jogador == pid)
            if ev.minuto <= 85:
                assert any(e.tipo == "lesao_sem_troca" and e.jogador == pid for e in p.eventos)
                return
    raise AssertionError("nenhuma lesao em 150 jogos")


def test_lesao_so_conta_jogo_do_clube_do_lesionado():
    c = Carreira.nova("brasil_real", "Santos", seed=4)
    pid = c.escalacao_atual()[5]
    med = DepartamentoMedico()
    med.lesionados[pid] = Lesao("lesão muscular", 2, 2)
    med.cumprir({-1}, c.world)                       # outro clube jogou
    assert med.lesionados[pid].jogos == 2
    med.cumprir({c.clube_id}, c.world)
    assert med.cumprir({c.clube_id}, c.world) == [pid]
    assert pid not in med.fora()


def test_o_lesionado_fica_fora_do_meu_onze_e_volta_depois():
    c = Carreira.nova("brasil_real", "Santos", seed=4)
    onze = c.escalacao_atual()
    machucado = onze[7]
    c.escalar(onze)
    c.medico.lesionados[machucado] = Lesao("entorse no tornozelo", 1, 1)
    _, partida = c.avancar()
    assert partida is not None
    assert machucado not in partida.entrada          # nem titular, nem banco
    assert machucado not in c.medico.fora()          # cumpriu o jogo
    _, partida = c.avancar()
    while partida is None:
        _, partida = c.avancar()
    assert machucado in partida.entrada or machucado in c.medico.fora()


def test_o_save_refaz_as_mesmas_lesoes(tmp_path, monkeypatch):
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova("brasil_real", "Santos", seed=9)
    for _ in range(12):
        c.avancar()
    assert c.medico.lesionados, "nenhuma lesao em 12 datas: a taxa mudou?"
    c.salvar("lesoes")
    d = Carreira.carregar("lesoes")
    assert {k: (v.tipo, v.jogos) for k, v in d.medico.lesionados.items()} == \
           {k: (v.tipo, v.jogos) for k, v in c.medico.lesionados.items()}
