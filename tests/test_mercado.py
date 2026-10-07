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


def test_a_receita_segue_o_tamanho_do_clube_e_a_divisao(carreira):
    """REGRESSAO: a receita saia so da reputacao, que satura em 100. Funcionava no Brasil e
    quebrava na Espanha, onde a folha varia 26 vezes dentro da primeira divisao -- o Real
    Madrid ficava com folha de 159M contra receita de 44M."""
    from fm.financas import valor_do_elenco

    c = carreira
    vivos = [x for x in c.world.clubs.values() if x.player_ids]
    grande = max(vivos, key=lambda x: valor_do_elenco(c.world, x.id))
    pequeno = min(vivos, key=lambda x: valor_do_elenco(c.world, x.id))
    assert receita_anual(c.world, grande.id, 1) > receita_anual(c.world, pequeno.id, 1) * 5
    # cair de divisao tem de doer no caixa, nao so na tabela
    assert receita_anual(c.world, grande.id, 2) < receita_anual(c.world, grande.id, 1) * 0.8
    assert premiacao(1, 20, 50_000_000) > premiacao(20, 20, 50_000_000) > 0


def test_a_receita_cobre_a_folha_nas_duas_piramides():
    """O teste que teria pego o bug: a proporcao entre o que entra e o que se paga de
    salario tem de fazer sentido no Brasil E na Espanha."""
    from fm.financas import folha_anual, valor_do_elenco

    for ligas, clube in ((["brasil_real", "brasil_b_real"], "Santos"),
                         (["espanha_real", "espanha_b_real"], "Real Madrid")):
        c = Carreira.nova(ligas, clube, seed=7)
        cfg = load_league(ligas[0])
        ids = c.world.leagues[cfg["id"]].club_ids
        razoes = [folha_anual(c.world, i)
                  / max(receita_anual(c.world, i, 1, valor_do_elenco(c.world, i)), 1)
                  for i in ids]
        assert max(razoes) < 1.0, (
            f"{ligas[0]}: algum clube paga mais salario do que fatura "
            f"(pior caso {max(razoes):.2f})")
        assert 0.2 < st.median(razoes) < 0.8, f"{ligas[0]}: folha/receita fora da faixa"


def test_o_dinheiro_esta_na_escala_do_futebol_real():
    """REGRESSAO: a receita era um terco da real (o Corinthians faturava 40M de euros; o de
    verdade, ~180M), e uma venda de 65M valia um ano e meio de faturamento -- o caixa de um
    grande pulava para 200M numa janela. Ordem de grandeza, nao numero exato."""
    from fm.financas import folha_anual, valor_do_elenco

    faixas = {"Flamengo": (100e6, 350e6), "Corinthians": (70e6, 300e6),
              "Real Madrid": (600e6, 1_600e6)}
    for ligas, clube in ((["brasil_real", "brasil_b_real"], "Flamengo"),
                         (["espanha_real", "espanha_b_real"], "Real Madrid")):
        c = Carreira.nova(ligas, clube, seed=7)
        for k, x in c.world.clubs.items():
            if x.name not in faixas:
                continue
            receita = receita_anual(c.world, k, 1, valor_do_elenco(c.world, k))
            lo, hi = faixas[x.name]
            assert lo < receita < hi, f"{x.name}: receita {receita / 1e6:.0f}M fora da escala real"
            # clube de futebol vive perto do zero: ninguem comeca com anos de receita guardados
            assert 0 < x.balance < receita, f"{x.name}: caixa inicial {x.balance / 1e6:.0f}M"
            assert 0.25 < folha_anual(c.world, k) / receita < 0.8


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


def test_o_dinheiro_circula(vinte_anos):
    """O caixa nao e' botao de dificuldade.

    Ja houve aqui um teste exigindo clubes no vermelho e um TETO de caixa, com o custo de
    operacao calibrado para machucar. O efeito era um mundo em que quase ninguem podia
    comprar ninguem. Clube que faz boa campanha PODE ficar rico, e nao ha limite -- e assim
    no futebol. O que se cobra e que o dinheiro exista e se mova, nao que falte.
    """
    c, _ = vinte_anos
    caixas = [cl.balance for cl in c.world.clubs.values()]
    assert st.median(caixas) > 0, "o mundo inteiro quebrou"
    # quem fatura mais tem mais: se o caixa nao separa os clubes, ele nao significa nada
    ricos = sorted(caixas)[-5:]
    pobres = sorted(caixas)[:5]
    assert st.mean(ricos) > st.mean(pobres) * 3, "o caixa e igual para todos"


def test_gastar_mal_ainda_afunda(carreira):
    """Sem aperto artificial, o que resta e a consequencia real: folha acima da receita
    consome o caixa. E a unica restricao que devia existir."""
    from fm.financas import folha_anual, receita_anual, valor_do_elenco

    c = carreira
    clube = c.clube
    caixa_antes = clube.balance
    # dobra a folha do elenco: agora ele paga muito mais do que fatura
    for pid in clube.player_ids:
        if pid in c.world.players:
            c.world.players[pid].wage *= 6
    folha = folha_anual(c.world, clube.id)
    receita = receita_anual(c.world, clube.id, 1, valor_do_elenco(c.world, clube.id))
    assert folha > receita, "o teste nao conseguiu montar um clube gastador"

    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    assert clube.balance < caixa_antes, "pagar folha impagavel nao custou nada"


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
    # como a carreira chama: so os clubes das ligas dela (o mundo inteiro e pano de fundo)
    da_carreira = {k for n in c.ligas for k in c.world.leagues[load_league(n)["id"]].club_ids}
    feitas = janela(c.world, rng, c.temporada, da_carreira)
    para_cima = [t for t in feitas
                 if t.jogador in de_b and c.world.clubs[t.para].league_id == a]
    assert para_cima, "nenhum jogador da segunda divisao subiu: o mercado e' de mao unica"


def test_o_caixa_parado_da_ia_vira_investimento():
    """REGRESSAO: o rico nao tinha onde gastar -- em 6 temporadas o caixa do mundo foi de 12
    a 40 bilhoes e o Manchester City guardava 2,2 anos de receita. O que passa de um ano de
    receita vira investimento na virada; o caixa do usuario nao e tocado."""
    from fm.financas import CAIXA_SEM_INVESTIR, Balanco, investimento

    assert investimento(50_000_000, 100_000_000) == 0
    assert investimento(250_000_000, 100_000_000) == int(250_000_000 - CAIXA_SEM_INVESTIR * 100_000_000)
    b = Balanco(clube=1, receita=100, premiacao=0, folha=50, operacao=40, investimento=30)
    assert b.saldo == -20

    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Palmeiras", seed=3)
    ids = c.world.leagues[c._id("brasil_real")].club_ids
    rico = next(k for k in ids if k != c.clube_id)
    c.world.clubs[rico].balance = 5_000_000_000
    c.clube.balance = 5_000_000_000
    while not c.acabou:
        c.avancar()
    resumo = c.virar_o_ano()
    assert resumo["balanco"].investimento == 0, "o caixa do usuario e decisao dele"
    assert c.world.clubs[rico].balance < 1_500_000_000, "o caixa parado da IA nao foi investido"
