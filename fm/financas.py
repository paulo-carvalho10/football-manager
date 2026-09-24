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

# Receita = BASE * (valor do elenco / REFERENCIA)^EXPOENTE * divisao * reputacao.
#
# A base e o VALOR DO ELENCO, nao a reputacao, e isso foi uma correcao cara de descobrir.
# Com a receita saindo so da reputacao, o modelo funcionava no Brasil e QUEBRAVA na
# Espanha: la a folha varia 26 vezes entre o maior e o menor clube da primeira divisao,
# enquanto a reputacao (52 a 99) so varia 3 vezes elevada a 1.8. O Real Madrid ficava com
# folha de 159M contra receita de 44M, e 39 dos 46 clubes viviam no vermelho. Nenhum
# expoente conserta isso: subir o expoente para alcancar o topo espanhol explodia a Serie B
# brasileira. O valor de elenco e a medida economica que atravessa as duas ligas.
#
# O freio contra bola de neve continua: o valor usado e o do INICIO da temporada, entao
# comprar jogador nao aumenta a receita do mesmo ano -- so a do ano que vem, depois de o
# clube ter pago pela compra. E o expoente abaixo de 1 amortece o resto.
RECEITA_POR_ELENCO = 26_000_000     # para um elenco de REFERENCIA_DE_ELENCO
REFERENCIA_DE_ELENCO = 100_000_000
EXPOENTE_ELENCO = 0.85

# A divisao ainda pesa, porque cota de TV despenca com o rebaixamento -- mas menos do que
# pesava antes, ja que o valor do elenco agora captura boa parte da diferenca sozinho.
FATOR_POR_TIER = {1: 1.00, 2: 0.72, 3: 0.50, 4: 0.35}

# A reputacao deixou de PAGAR a receita e passou a modula-la: e assim que desempenho e
# historia continuam valendo dinheiro sem que o topo da tabela dependa de um numero que
# satura em 100.
REPUTACAO_NA_RECEITA = (0.82, 0.36)   # piso e quanto a reputacao acrescenta

# Premiacao da competicao, do campeao ao ultimo colocado. Some a receita fixa.
PREMIO_DO_CAMPEAO = {1: 12_000_000, 2: 3_000_000, 3: 900_000, 4: 300_000}
PREMIO_DO_LANTERNA = 0.12          # fracao do premio do campeao que o ultimo leva

# A reputacao e o que converte desempenho em dinheiro, e ela se move devagar: um titulo
# nao faz de ninguem um grande, e uma temporada ruim nao desfaz cem anos de historia. Mas
# a queda de divisao aparece no ano seguinte, porque e la que dai.
REPUTACAO_PASSO = 2.2              # pontos, no maximo, por temporada
REPUTACAO_PISO, REPUTACAO_TETO = 5, 97

# Premiacao de copa. O valor e o TOTAL que o campeao acumula na campanha, e cada clube
# leva a fracao correspondente ao quanto avancou.
#
# Pagar so campeao e vice estava errado, e nao era simplificacao: a CONMEBOL paga US$ 3M
# so pela fase de grupos da Libertadores, 1,25M pelas oitavas, 1,7M pelas quartas. Do
# jeito antigo, quem caia nas oitavas recebia ZERO e ainda tinha pagado o custo dos jogos
# -- disputar a Libertadores e nao chegar a final era prejuizo puro, e nao havia razao
# financeira para buscar a vaga. Copa e premio de CAMPANHA, nao de titulo.
PREMIO_DE_COPA = {
    "libertadores": 9_000_000,
    "copa_do_brasil": 4_500_000,
    "sudamericana": 3_000_000,
    "champions": 24_000_000,
    "europa_league": 7_500_000,
    "intercontinental": 5_000_000,
}

# Quanto da campanha ja esta pago so por entrar, e como o resto se concentra no fim. Com
# expoente 2.5 a curva imita a real: a fase de grupos vale perto de 10% do total do
# campeao, e o salto grande fica entre a final e o titulo.
PREMIO_POR_PARTICIPACAO = 0.10
CONCENTRACAO_DO_PREMIO = 3.5
PREMIO_DO_VICE = 0.55            # o vice acumula perto da metade do campeao
TETO_DE_QUEM_NAO_DECIDE = 0.45   # quem nao chegou a final nao encosta no vice

# Disputar copa custa: viagem, logistica, elenco maior. Por jogo alem do calendario da
# liga.
CUSTO_POR_JOGO_EXTRA = 260_000


def premio_de_campanha(torneio: str, etapas_vividas: int, etapas_totais: int,
                       campeao: bool = False, vice: bool = False) -> int:
    """O que um clube leva pela campanha que fez, nao pelo lugar onde parou.

    `etapas_vividas` e quantas etapas ele sobreviveu; `etapas_totais` e quantas a
    competicao teve.

    Campeao e vice precisam de degrau PROPRIO porque sobrevivem o mesmo numero de etapas
    -- os dois chegam a final. So pela curva o vice levava 92% do campeao; na Libertadores
    de verdade ele acumula perto da metade.
    """
    base = PREMIO_DE_COPA.get(torneio, 0)
    if not base or etapas_totais <= 0:
        return 0
    if campeao:
        return base
    if vice:
        return int(base * PREMIO_DO_VICE)
    avanco = min(1.0, max(0, etapas_vividas) / etapas_totais)
    fracao = PREMIO_POR_PARTICIPACAO + (1 - PREMIO_POR_PARTICIPACAO) * (
        avanco ** CONCENTRACAO_DO_PREMIO)
    return int(base * min(fracao, TETO_DE_QUEM_NAO_DECIDE))


MESES = 12
# Estrutura, categorias de base, viagem, encargos.
#
# NAO e' um botao de dificuldade. Ja esteve em 0.62, calibrado para deixar a maioria dos
# clubes no vermelho porque "dinheiro que nao acaba nao decide nada" -- e o efeito era um
# mundo em que quase ninguem podia comprar ninguem. Um clube que faz uma boa campanha PODE
# acumular caixa, e nao ha teto: quem ganha muito fica rico, como no futebol.
#
# O que continua valendo: quem paga folha acima do que fatura afunda, e cair de divisao
# doi. O aperto vem de gastar mal, nao de uma taxa calibrada para machucar.
CUSTO_DE_OPERACAO = 0.46


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


def valor_do_elenco(world: World, clube_id: int) -> int:
    """Quanto vale o elenco. E a medida economica do clube, e a que escala entre ligas."""
    return sum(world.players[i].market_value
               for i in world.clubs[clube_id].player_ids if i in world.players)


def receita_anual(world: World, clube_id: int, tier: int,
                  valor: int | None = None) -> int:
    """Bilheteria, socios, patrocinio e cota de TV, tudo num numero so.

    `valor` e o elenco no INICIO da temporada. Passando None ele e medido agora, o que
    serve para consulta mas reintroduz a bola de neve se usado para fechar o ano.
    """
    club = world.clubs[clube_id]
    v = valor if valor is not None else valor_do_elenco(world, clube_id)
    escala = (max(v, 1_000_000) / REFERENCIA_DE_ELENCO) ** EXPOENTE_ELENCO
    piso, faixa = REPUTACAO_NA_RECEITA
    reputacao = piso + faixa * (club.reputation / 100.0)
    return int(RECEITA_POR_ELENCO * escala * FATOR_POR_TIER.get(tier, 0.35) * reputacao)


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
        passos = [max(-REPUTACAO_PASSO,
                      min(REPUTACAO_PASSO,
                          escada[posicao] - world.clubs[linha.club_id].reputation))
                  for posicao, linha in enumerate(tabela)]
        # O limite do passo quebra a conservacao: o pequeno que foi campeao sobe no
        # maximo o passo, o grande que caiu desce o passo, mas o meio da tabela anda
        # pouco -- a soma nao da zero e a divisao deriva enquanto converge. Descontar a
        # media dos passos devolve a estacionariedade que a docstring promete.
        vies = sum(passos) / len(passos)
        for linha, passo in zip(tabela, passos):
            club = world.clubs[linha.club_id]
            club.reputation = int(round(
                max(REPUTACAO_PISO, min(REPUTACAO_TETO, club.reputation + passo - vies))))


def fechar_o_ano(world: World, tabelas: dict[str, list[Row]],
                 cfgs: dict[str, dict],
                 extras: dict[int, int] | None = None,
                 jogos_extras: dict[int, int] | None = None,
                 valores: dict[int, int] | None = None) -> dict[int, Balanco]:
    """Credita e debita o ano de cada clube. Chamado uma vez, na virada.

    Roda ANTES do acesso e do rebaixamento: o ano que acabou foi jogado na divisao antiga,
    e e ela que paga.
    """
    balancos: dict[int, Balanco] = {}
    for liga, tabela in tabelas.items():
        tier = int(cfgs[liga].get("tier", 1))
        for posicao, linha in enumerate(tabela, 1):
            cid = linha.club_id
            receita = receita_anual(world, cid, tier, (valores or {}).get(cid))
            b = Balanco(clube=cid, receita=receita,
                        premiacao=(premiacao(posicao, len(tabela), tier)
                                   + (extras or {}).get(cid, 0)),
                        folha=folha_anual(world, cid),
                        operacao=0)
            # a operacao incide sobre TUDO que entra, premiacao inclusive: cobrando so
            # sobre a receita fixa, um bom ano de premios virava lucro limpo e o caixa
            # do mundo inteiro subia sem parar
            b.operacao = int((b.receita + b.premiacao) * CUSTO_DE_OPERACAO
                             + (jogos_extras or {}).get(cid, 0) * CUSTO_POR_JOGO_EXTRA)
            world.clubs[cid].balance += b.saldo
            balancos[cid] = b
    mover_reputacao(world, tabelas)
    return balancos
