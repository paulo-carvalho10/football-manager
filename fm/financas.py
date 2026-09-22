"""O dinheiro do clube: de onde vem, para onde vai e o que isso muda.

Sem isto o `balance` era um numero decorativo na tela do lobby. Com isto ele e a restricao
que faz a carreira ter escolhas: o elenco que voce monta e a folha que voce paga, e a
divisao em que voce joga decide quanto entra.

Escala. Os valores vem do Transfermarkt, em euros, e o salario importado ja sai numa
proporcao realista -- cerca de 11% do valor de mercado por ano. A receita foi ancorada
nisso: um grande da Serie A fatura o suficiente para pagar a folha e sobrar um reforco por
ano, e um pequeno fecha no zero. E o aperto que cria a decisao; caixa infinito nao decide
nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from fm.model import World
from fm.table import Row

# Receita = BASE * (reputacao/100)^EXPOENTE * fator da divisao. A lei de potencia e o que
# faz a distancia entre grande e pequeno ser abissal, como e no Brasil: o Palmeiras fatura
# dez vezes a Chapecoense, nao o dobro.
RECEITA_BASE = 45_000_000
EXPOENTE_REPUTACAO = 1.8
FATOR_POR_TIER = {1: 1.00, 2: 0.45, 3: 0.20, 4: 0.09}

# Premiacao da competicao, do campeao ao ultimo colocado. Some a receita fixa.
PREMIO_DO_CAMPEAO = {1: 12_000_000, 2: 3_000_000, 3: 900_000, 4: 300_000}
PREMIO_DO_LANTERNA = 0.12          # fracao do premio do campeao que o ultimo leva

# A reputacao e o que converte desempenho em dinheiro, e ela se move devagar: um titulo
# nao faz de ninguem um grande, e uma temporada ruim nao desfaz cem anos de historia. Mas
# a queda de divisao aparece no ano seguinte, porque e la que dai.
REPUTACAO_PASSO = 2.2              # pontos, no maximo, por temporada
REPUTACAO_PISO, REPUTACAO_TETO = 5, 97

MESES = 12
# Estrutura, categorias de base, viagem, encargos. Alto de proposito: com 0.28 nenhum clube
# do mundo terminava 20 temporadas no vermelho e o maior deles empilhava 485M sem uso, ou
# seja, o dinheiro nao restringia nada e as financas eram enfeite. Com 0.50, a mediana fecha
# o ano perto do zero e cerca de um quarto dos clubes vive endividado -- que e, alias, a
# situacao do futebol brasileiro.
CUSTO_DE_OPERACAO = 0.50


@dataclass(slots=True)
class Balanco:
    clube: int
    receita: int
    premiacao: int
    folha: int
    operacao: int

    @property
    def saldo(self) -> int:
        return self.receita + self.premiacao - self.folha - self.operacao


def folha_anual(world: World, clube_id: int) -> int:
    """O que o elenco custa por ano. O salario importado e mensal."""
    return sum(world.players[i].wage for i in world.clubs[clube_id].player_ids
               if i in world.players) * MESES


def receita_anual(world: World, clube_id: int, tier: int) -> int:
    """Bilheteria, socios, patrocinio e cota de TV, tudo num numero so.

    Depende da reputacao e da DIVISAO, nao da forca do elenco. De proposito: se a receita
    seguisse o elenco, comprar jogador aumentaria a receita e o clube rico viraria uma bola
    de neve sem freio. Reputacao muda devagar; divisao muda de uma vez -- e o rebaixamento
    tem de doer no caixa.
    """
    club = world.clubs[clube_id]
    return int(RECEITA_BASE * (club.reputation / 100.0) ** EXPOENTE_REPUTACAO
               * FATOR_POR_TIER.get(tier, 0.09))


def premiacao(posicao: int, clubes: int, tier: int) -> int:
    """Premio por onde o clube terminou, decrescendo do campeao ao lanterna."""
    topo = PREMIO_DO_CAMPEAO.get(tier, 300_000)
    if clubes <= 1:
        return topo
    fracao = 1.0 - (posicao - 1) / (clubes - 1) * (1.0 - PREMIO_DO_LANTERNA)
    return int(topo * fracao)


def mover_reputacao(world: World, tabelas: dict[str, list[Row]]) -> None:
    """Desempenho vira reputacao, que no ano seguinte vira receita. E o laco de realimentacao.

    Sem ele a receita e um numero colado no clube na criacao do mundo: quem passou dez anos
    na segunda divisao continuaria faturando como grande, e quem subiu nunca viraria um.

    O alvo de cada clube e a reputacao de QUEM TERMINOU NAQUELA POSICAO no ano anterior --
    ou seja, a propria distribuicao da divisao, redistribuida pela tabela. Isso a torna
    estacionaria por construcao: a temporada troca os clubes de lugar na hierarquia, nunca
    empurra a hierarquia inteira para cima. A primeira versao usava um alvo absoluto e
    puxava quase todo mundo junto; como a reputacao paga a receita E calibra a base, o
    mundo inteiro inflava -- o overall medio subia de 57 para 61 em vinte temporadas,
    acelerando depois da decima.
    """
    for tabela in tabelas.values():
        if len(tabela) < 2:
            continue
        escada = sorted((world.clubs[linha.club_id].reputation for linha in tabela),
                        reverse=True)
        for posicao, linha in enumerate(tabela):
            club = world.clubs[linha.club_id]
            passo = max(-REPUTACAO_PASSO, min(REPUTACAO_PASSO, escada[posicao] - club.reputation))
            club.reputation = int(round(
                max(REPUTACAO_PISO, min(REPUTACAO_TETO, club.reputation + passo))))


def fechar_o_ano(world: World, tabelas: dict[str, list[Row]],
                 cfgs: dict[str, dict]) -> dict[int, Balanco]:
    """Credita e debita o ano de cada clube. Chamado uma vez, na virada.

    Roda ANTES do acesso e do rebaixamento: o ano que acabou foi jogado na divisao antiga,
    e e ela que paga.
    """
    balancos: dict[int, Balanco] = {}
    for liga, tabela in tabelas.items():
        tier = int(cfgs[liga].get("tier", 1))
        for posicao, linha in enumerate(tabela, 1):
            cid = linha.club_id
            receita = receita_anual(world, cid, tier)
            b = Balanco(clube=cid, receita=receita,
                        premiacao=premiacao(posicao, len(tabela), tier),
                        folha=folha_anual(world, cid),
                        operacao=int(receita * CUSTO_DE_OPERACAO))
            world.clubs[cid].balance += b.saldo
            balancos[cid] = b
    mover_reputacao(world, tabelas)
    return balancos
