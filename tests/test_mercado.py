"""Transferencias e dinheiro. As duas pecas que impedem a hierarquia de congelar.

O que este arquivo protege nao e' a ausencia de excecao -- e' a economia. Um mercado que
nao restringe, um caixa que so cresce e uma receita que nunca muda produzem um jogo que
roda perfeitamente e nao decide nada.
"""

from __future__ import annotations

import statistics as st

import pytest

from fm.carreira import Carreira
from fm.config import load_league
from fm.financas import fechar_o_ano, folha_anual, mover_reputacao, premiacao, receita_anual
from fm.mercado import janela

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture
def carreira():
    return Carreira.nova(LIGAS, "Santos", seed=42)


@pytest.fixture(scope="module")
def vinte_anos():
    c = Carreira.nova(LIGAS, "Santos", seed=7)
    total = 0
    for _ in range(20):
        while not c.acabou:
            c.avancar()
        total += c.virar_o_ano()["transferencias"]
    return c, total


def test_o_jogador_so_pertence_a_um_clube(carreira):
    """O invariante que uma transferencia mal feita quebra primeiro."""
    c = carreira
    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    for clube in c.world.clubs.values():
        for pid in clube.player_ids:
            if pid in c.world.players:
                assert c.world.players[pid].club_id == clube.id
    todos = [pid for clube in c.world.clubs.values() for pid in clube.player_ids]
    assert len(todos) == len(set(todos)), "jogador em dois elencos"


def test_ninguem_e_revendido_na_mesma_janela(carreira):
    """REGRESSAO: Natanael saiu do Atletico para o Santos e do Santos para o Bahia na mesma
    janela, pelo mesmo preco. A lista de disponiveis era montada no inicio de cada rodada de
    mercado e nao acompanhava as trocas feitas dentro dela."""
    c = carreira
    for _ in range(3):
        while not c.acabou:
            c.avancar()
        rng = c.streams.get("teste_mercado", c.temporada)
        feitas = janela(c.world, rng, c.temporada)
        ids = [t.jogador for t in feitas]
        assert len(ids) == len(set(ids)), "o mesmo jogador trocou de clube duas vezes"
        c.virar_o_ano()


def test_o_dinheiro_do_comprador_vai_para_o_vendedor(carreira):
    c = carreira
    while not c.acabou:
        c.avancar()
    caixa = {cl.id: cl.balance for cl in c.world.clubs.values()}
    rng = c.streams.get("teste_mercado", c.temporada)
    feitas = janela(c.world, rng, c.temporada)
    assert feitas, "nenhuma transferencia: o mercado esta parado"
    esperado = dict.fromkeys(caixa, 0)
    for t in feitas:
        esperado[t.para] -= t.preco
        esperado[t.de] += t.preco
    for cid, delta in esperado.items():
        assert c.world.clubs[cid].balance == caixa[cid] + delta
    assert sum(t.preco for t in feitas) > 0


def test_ninguem_compra_o_que_nao_pode_pagar(carreira):
    c = carreira
    while not c.acabou:
        c.avancar()
    rng = c.streams.get("teste_mercado", c.temporada)
    janela(c.world, rng, c.temporada)
    for clube in c.world.clubs.values():
        assert clube.balance > -folha_anual(c.world, clube.id), (
            f"{clube.name} gastou muito alem do que tinha")


def test_a_receita_segue_a_reputacao_e_a_divisao(carreira):
    c = carreira
    grande = max(c.world.clubs.values(), key=lambda x: x.reputation)
    pequeno = min((x for x in c.world.clubs.values() if x.player_ids),
                  key=lambda x: x.reputation)
    assert receita_anual(c.world, grande.id, 1) > receita_anual(c.world, pequeno.id, 1) * 5
    # cair de divisao tem de doer no caixa, nao so na tabela
    assert receita_anual(c.world, grande.id, 2) < receita_anual(c.world, grande.id, 1) * 0.6
    assert premiacao(1, 20, 1) > premiacao(20, 20, 1) > 0


def test_a_reputacao_e_estacionaria(carreira):
    """REGRESSAO: o alvo era absoluto e puxava a divisao inteira para cima. Como reputacao
    paga a receita e calibra a base, o mundo todo inflava junto. O alvo agora e a propria
    distribuicao da divisao, redistribuida pela tabela: a temporada troca os clubes de
    lugar na hierarquia, nunca levanta a hierarquia."""
    c = carreira
    while not c.acabou:
        c.avancar()
    tabelas = {n: c.tabela(n) for n in c.ligas}
    antes = {n: sorted(c.world.clubs[r.club_id].reputation for r in t)
             for n, t in tabelas.items()}
    for _ in range(6):
        mover_reputacao(c.world, tabelas)
    for liga, escada in antes.items():
        agora = sorted(c.world.clubs[r.club_id].reputation for r in tabelas[liga])
        assert abs(st.mean(agora) - st.mean(escada)) < 1.5, (
            f"{liga}: reputacao media saiu de {st.mean(escada):.1f} para {st.mean(agora):.1f}")


def test_o_campeao_ganha_mais_que_o_lanterna(carreira):
    c = carreira
    while not c.acabou:
        c.avancar()
    cfgs = {n: load_league(n) for n in c.ligas}
    tabelas = {n: c.tabela(n) for n in c.ligas}
    balancos = fechar_o_ano(c.world, tabelas, cfgs)
    campeao = balancos[tabelas["brasil_real"][0].club_id]
    lanterna = balancos[tabelas["brasil_real"][-1].club_id]
    assert campeao.premiacao > lanterna.premiacao
    assert campeao.receita > 0 and campeao.folha > 0


def test_o_dinheiro_aperta(vinte_anos):
    """Caixa que so cresce nao decide nada. Antes desta calibracao nenhum clube terminava
    20 temporadas no vermelho e o maior empilhava 485M sem uso."""
    c, _ = vinte_anos
    caixas = [cl.balance for cl in c.world.clubs.values()]
    no_vermelho = sum(1 for x in caixas if x < 0)
    assert no_vermelho >= 2, "ninguem sente o dinheiro: as financas viraram enfeite"
    assert no_vermelho <= len(caixas) // 2, "o mundo inteiro quebrou"
    assert max(caixas) < 250_000_000, f"caixa parado de {max(caixas)/1e6:.0f}M"


def test_o_mercado_nao_para(vinte_anos):
    """Um mercado que seca congela a hierarquia tanto quanto um que nao existe."""
    c, total = vinte_anos
    assert total / 20 > 20, f"so {total/20:.0f} transferencias por temporada"


def test_o_craque_sobe_e_o_reserva_desce(carreira):
    """O fluxo que da sentido a piramide: quem se destaca na divisao de baixo e levado, e
    quem nao joga no grande vai jogar noutro lugar."""
    c = carreira
    a, b = (load_league(n)["id"] for n in c.ligas)
    while not c.acabou:
        c.avancar()
    de_b = {pid for cid in c.world.leagues[b].club_ids
            for pid in c.world.clubs[cid].player_ids}
    rng = c.streams.get("teste_mercado", c.temporada)
    feitas = janela(c.world, rng, c.temporada)
    para_cima = [t for t in feitas
                 if t.jogador in de_b and c.world.clubs[t.para].league_id == a]
    assert para_cima, "nenhum jogador da segunda divisao subiu: o mercado e' de mao unica"
