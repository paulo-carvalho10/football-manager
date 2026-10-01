"""Lesao: quem se machuca sai de campo, fica fora alguns dias do calendario e volta."""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from fm.calendario import DIAS_POR_DATA, dia_da_data
from fm.carreira import Carreira
from fm.eventos import simular_partida
from fm.lesoes import DepartamentoMedico, Lesao
from fm.match import Style

ESTILO = Style(goals_base=1.22, home_adv=0.36)


def _no_primeiro_jogo(seed: int, liga: str = "brasil_real", clube: str = "Santos") -> Carreira:
    """A carreira na vespera do primeiro jogo de LIGA do clube. O ano abre em fevereiro com
    as preliminares das copas (fm.agenda): o primeiro `avancar` ja nao e a 1a rodada."""
    c = Carreira.nova(liga, clube, seed=seed)
    while not c.acabou and not (c.compromisso[0] == "liga" and c.proxima_partida() is not None):
        c.avancar()
    return c


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


def test_a_lesao_conta_dias_do_calendario():
    """Fora enquanto o dia da data for antes da volta; joga no proprio dia da volta."""
    med = DepartamentoMedico()
    hoje = dia_da_data(2027, 10)
    med.lesionados[7] = Lesao("lesão muscular", hoje + timedelta(days=10), 10)
    datas_fora = [i for i in range(10, 20) if 7 in med.fora(dia_da_data(2027, i))]
    # 10 dias com uma data a cada DIAS_POR_DATA: fora nesta e nas datas antes da volta
    assert datas_fora == list(range(10, 10 + -(-10 // DIAS_POR_DATA)))
    assert med.dar_alta(hoje + timedelta(days=9)) == []
    assert med.dar_alta(hoje + timedelta(days=10)) == [7]


def test_o_lesionado_fica_fora_do_meu_onze_e_volta_depois():
    c = _no_primeiro_jogo(4)
    onze = c.escalacao_atual()
    machucado = onze[7]
    c.escalar(onze)
    # volta no dia da data seguinte: perde so esta
    c.medico.lesionados[machucado] = Lesao("pancada", c.dia(c.data + 1), 4)
    _, partida = c.avancar()
    assert partida is not None
    assert machucado not in partida.entrada          # nem titular, nem banco
    assert machucado not in c.medico.fora(c.hoje())  # liberado
    _, partida = c.avancar()
    while partida is None:
        _, partida = c.avancar()
    assert machucado in partida.entrada or machucado in c.medico.lesionados


def test_o_save_refaz_as_mesmas_lesoes(tmp_path, monkeypatch):
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova("brasil_real", "Santos", seed=9)
    for _ in range(12):
        c.avancar()
    assert c.medico.lesionados, "nenhuma lesao em 12 datas: a taxa mudou?"
    c.salvar("lesoes")
    d = Carreira.carregar("lesoes")
    assert {k: (v.tipo, v.volta) for k, v in d.medico.lesionados.items()} == \
           {k: (v.tipo, v.volta) for k, v in c.medico.lesionados.items()}


def _reserva_lesionado(seed=4):
    c = _no_primeiro_jogo(seed)
    onze = c.escalacao_atual()
    reserva = next(p.id for p in sorted(c.world.squad(c.clube_id), key=lambda p: -p.overall)
                   if p.id not in onze)
    c.medico.lesionados[reserva] = Lesao("lesão muscular", c.hoje() + timedelta(days=20), 20)
    return c, reserva


def test_lesionado_nao_entra_nem_como_substituto():
    """O mesmo buraco que o suspenso tinha: fora do onze, mas aceito como troca."""
    c, reserva = _reserva_lesionado()

    def pedido(partida, minuto):
        meus = partida.em_campo_casa if partida.casa == c.clube_id else partida.em_campo_fora
        return {"trocas": [(meus[5], reserva)]} if minuto == 45 else None

    _, partida = c.avancar(substituicoes=pedido)
    assert reserva not in partida.entrada, "o lesionado entrou como substituto"


def test_o_banco_ao_vivo_nao_mostra_o_lesionado():
    from fm.ao_vivo import PartidaAoVivo
    c, reserva = _reserva_lesionado()
    av = PartidaAoVivo(c)
    av.comecar()
    r = av.retrato(lambda cid: {"id": cid, "nome": c.world.clubs[cid].name})
    assert reserva not in [j["id"] for j in r["banco"]]
    av.seguir(ate_o_fim=True)


def test_quem_se_machuca_na_partida_nao_volta_a_campo():
    """Machucou, saiu: pedir para ele entrar de novo no bloco seguinte nao pode valer."""
    c = _no_primeiro_jogo(4)
    pedidos = []

    def pedido(partida, minuto):
        meus = partida.em_campo_casa if partida.casa == c.clube_id else partida.em_campo_fora
        fora = [i for i in partida.lesionados
                if c.world.players[i].club_id == c.clube_id and i not in meus]
        if fora:
            pedidos.append(fora[0])
            return {"trocas": [(meus[3], fora[0])]}
        return None

    import fm.eventos as ev
    antes = ev.LESOES_POR_TIME
    ev.LESOES_POR_TIME = 4.0                   # lesao cedo e certa, so neste teste
    try:
        _, partida = c.avancar(substituicoes=pedido)
    finally:
        ev.LESOES_POR_TIME = antes
    assert pedidos, "ninguem do meu time se machucou antes do fim"
    for pid in pedidos:
        assert pid not in partida.em_campo_casa + partida.em_campo_fora
