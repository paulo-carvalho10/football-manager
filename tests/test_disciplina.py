"""O gancho: cartao acumulado e vermelho tiram o jogador do proximo jogo da competicao."""

import numpy as np

from fm.carreira import Carreira
from fm.disciplina import AMARELOS_PARA_SUSPENSAO, Disciplina, sortear_cartoes


def _no_primeiro_jogo(seed: int, liga: str = "brasil_real", clube: str = "Santos") -> Carreira:
    """A carreira na vespera do primeiro jogo de LIGA do clube. O ano abre em fevereiro com
    as preliminares das copas (fm.agenda): o primeiro `avancar` ja nao e a 1a rodada."""
    c = Carreira.nova(liga, clube, seed=seed)
    while not c.acabou and not (c.compromisso[0] == "liga" and c.proxima_partida() is not None):
        c.avancar()
    return c


def test_tres_amarelos_suspendem_e_zeram_a_contagem():
    d = Disciplina()
    for _ in range(AMARELOS_PARA_SUSPENSAO - 1):
        assert d.registrar("liga", [(7, "amarelo")]) == []
    assert 7 in d.pendurados("liga")
    assert d.registrar("liga", [(7, "amarelo")]) == [7]
    assert 7 in d.suspensos("liga")
    assert d.amarelos["liga"][7] == 0


def test_vermelho_suspende_e_os_amarelos_do_expulso_nao_acumulam():
    d = Disciplina()
    d.registrar("liga", [(9, "amarelo"), (9, "vermelho")])
    assert 9 in d.suspensos("liga")
    assert d.amarelos["liga"].get(9, 0) == 0


def test_gancho_de_uma_competicao_nao_vale_na_outra():
    d = Disciplina()
    d.registrar("liga", [(5, "vermelho")])
    assert 5 in d.suspensos("liga")
    assert 5 not in d.suspensos("copa_do_brasil")


def test_o_gancho_so_e_cumprido_quando_o_clube_joga():
    c = Carreira.nova("brasil_real", "Santos", seed=4)
    pid = c.escalacao_atual()[4]
    c.disciplina.registrar("brasil_real", [(pid, "vermelho")])
    c.disciplina.cumprir("brasil_real", {-1}, c.world)          # outro clube jogou
    assert pid in c.disciplina.suspensos("brasil_real")
    c.disciplina.cumprir("brasil_real", {c.clube_id}, c.world)
    assert pid not in c.disciplina.suspensos("brasil_real")


def test_o_suspenso_fica_fora_do_meu_jogo_e_volta_no_seguinte():
    c = _no_primeiro_jogo(4)
    onze = c.escalacao_atual()
    suspenso = onze[6]
    c.escalar(onze)
    c.disciplina.registrar("brasil_real", [(suspenso, "vermelho")])
    _, partida = c.avancar()
    assert partida is not None
    assert suspenso not in partida.entrada, "o suspenso entrou em campo"
    assert len(partida.entrada) >= 11
    # cumprido o gancho, a escalacao escolhida volta inteira
    assert suspenso in c.escalacao_atual()
    assert suspenso not in c.disciplina.suspensos("brasil_real")


def test_adversario_tambem_cumpre_gancho():
    c = _no_primeiro_jogo(4)
    jogo = c.proxima_partida()
    rival = jogo.away if jogo.home == c.clube_id else jogo.home
    craque = max(c.world.squad(rival), key=lambda p: p.overall).id
    c.disciplina.registrar("brasil_real", [(craque, "vermelho")])
    _, partida = c.avancar()
    assert craque not in partida.entrada


def test_cartoes_sorteados_respeitam_a_regra_do_segundo_amarelo():
    c = Carreira.nova("brasil_real", "Santos", seed=4)
    onze = c.escalacao_atual()
    rng = np.random.default_rng(1)
    for _ in range(500):
        cartoes = sortear_cartoes(c.world, onze, rng)
        expulsos = [p for p, t in cartoes if t == "vermelho"]
        assert len(expulsos) == len(set(expulsos)), "expulso duas vezes"
        for p in expulsos:
            depois = cartoes[cartoes.index((p, "vermelho")) + 1:]
            assert p not in [x for x, _ in depois], "cartao depois de expulso"


def test_uma_temporada_tem_ganchos_para_todo_lado():
    """Nao e so o usuario que perde jogador: os adversarios tambem levam cartao."""
    c = Carreira.nova("brasil_real", "Santos", seed=6)
    # quinze rodadas DA LIGA: as datas de copa do comeco do ano nao contam
    while len(c.jogos("brasil_real")) < 15 * 10:
        c.avancar()
    caderno = c.estatisticas_por_comp["brasil_real"].por_jogador
    clubes_com_cartao = {c.world.players[p].club_id for p, x in caderno.items()
                         if x.amarelos or x.vermelhos}
    assert len(clubes_com_cartao) == 20
    jogos = len(c.jogos("brasil_real"))
    vermelhos = sum(x.vermelhos for x in caderno.values())
    assert 0.1 < vermelhos / jogos < 0.45


def test_suspenso_nao_entra_nem_como_substituto():
    """REGRESSAO: fora do onze, mas aparecia no banco ao vivo e o motor aceitava a troca."""
    c = _no_primeiro_jogo(4)
    onze = c.escalacao_atual()
    reserva = next(p.id for p in sorted(c.world.squad(c.clube_id), key=lambda p: -p.overall)
                   if p.id not in onze)
    c.disciplina.registrar("brasil_real", [(reserva, "vermelho")])

    def pedido(partida, minuto):
        meus = partida.em_campo_casa if partida.casa == c.clube_id else partida.em_campo_fora
        return {"trocas": [(meus[5], reserva)]} if minuto == 45 else None

    _, partida = c.avancar(substituicoes=pedido)
    assert reserva not in partida.entrada, "o suspenso entrou como substituto"


def test_o_banco_ao_vivo_nao_mostra_o_suspenso():
    from fm.ao_vivo import PartidaAoVivo
    c = _no_primeiro_jogo(4)
    onze = c.escalacao_atual()
    reserva = next(p.id for p in c.world.squad(c.clube_id) if p.id not in onze)
    c.disciplina.registrar("brasil_real", [(reserva, "vermelho")])
    av = PartidaAoVivo(c)
    av.comecar()
    r = av.retrato(lambda cid: {"id": cid, "nome": c.world.clubs[cid].name})
    assert reserva not in [j["id"] for j in r["banco"]]
    av.seguir(ate_o_fim=True)
