"""A janela de transferencias: onde o dinheiro vira elenco.

E a peca que impede a hierarquia de congelar. Sem mercado, quem comecou forte continua
forte para sempre -- o campeao de 2027 e o de 2047, porque nada nunca troca de mao. Com
mercado, o clube que fatura mais compra melhor, o que cai de divisao perde os bons e o
garoto que explodiu na Serie B e levado por um grande.

O jogador tem vontade propria: so troca de clube se subir de vida -- clube mais forte, ou
a titularidade que ele nao tem hoje. Sem isso o mercado viraria um leilao em que o rico
compra o elenco inteiro do pobre e ninguem reclama.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from fm import moral
from fm.model import World

TITULARES_POR_GRUPO = {"GK": 1, "DF": 4, "MF": 3, "FW": 3}
RODADAS_DE_MERCADO = 4          # cada clube age quatro vezes por janela
ELENCO_MINIMO_PARA_VENDER = 20  # ninguem vende ate ficar sem time

# Preco. O valor de mercado e o ponto de partida; o resto e negociacao.
PREMIO_DE_PEDIDA = 1.25         # o vendedor sempre pede acima do valor
DESCONTO_CONTRATO_CURTO = 0.55  # a um ano do fim, sai por pouco mais da metade
PREMIO_POR_POTENCIAL = 0.030    # por ponto de potencial acima do overall atual
RESERVA_DE_CAIXA = 4            # meses de folha que o clube nao torra em reforco
# O insatisfeito (fm.moral) quer sair, e o clube sabe: vende ate titular, por menos, e ele
# aceita ir para um clube menor. E o que faz a moral mexer no mercado, e nao so no vestiario.
DESCONTO_DO_INSATISFEITO = 0.75
# O abatido (moral abaixo de 55) ainda nao quer sair, mas o clube ja aceita conversar.
# E bem mais comum que o insatisfeito -- e o que deixa a moral visivel no mercado.
DESCONTO_DO_ABATIDO = 0.90
MORAL_DO_ABATIDO = 55

# Quem esta no vermelho VENDE, e ai nao escolhe muito o preco. E o unico freio de verdade
# do lado forte do mercado: sem ele o clube grande so acumula, a base dele passa a revelar
# em cima de um elenco cada vez melhor e o nivel da primeira divisao sobe sem parar --
# medido, +0.24 ponto por temporada, acelerando na segunda decada.
DESCONTO_DE_URGENCIA = 0.80     # o clube endividado vende abaixo do que pediria
VENDAS_FORCADAS = 3             # no maximo, por clube e por janela

# Ambicao: o jogador so se mexe para subir de vida. Como quem esta a venda ja e reserva no
# clube atual, a vaga de titular no destino paga por um degrau pequeno para baixo -- mas so
# um degrau. Ninguem larga um grande para ser titular na segundona.
DESCIDA_TOLERADA = 4.0          # em pontos de team_rating
# Titular nao esta a venda -- a menos que bata a porta um clube de outro patamar. E assim
# que o craque da Serie B sobe e que o dinheiro do grande sai do caixa: sem isto o clube
# mais rico do mundo passava a carreira inteira vendendo reserva e empilhando 300M parados.
SALTO_PARA_LEVAR_TITULAR = 7.0
# ...quase ninguem. Todo ano uma minoria topa descer de patamar: o veterano atras de
# minutos, o reserva cansado do banco, o titular que quer ser o dono do time. Dificil, nao
# impossivel -- e a mesma regra vale para a IA, para a compra do usuario e para as
# propostas que ele recebe.
CHANCE_DE_TOPAR_DESCER = 0.02
EXTRA_DO_VETERANO = 0.05          # a partir de IDADE_DO_VETERANO
IDADE_DO_VETERANO = 31


def insatisfeito(p) -> bool:
    return p.morale < moral.INSATISFEITO


def abatido(p) -> bool:
    """Moral baixa, mas ainda nao insatisfeito (fm.moral.rotulo_da_moral)."""
    return not insatisfeito(p) and p.morale < MORAL_DO_ABATIDO


def topa_descer(p, temporada: int) -> bool:
    """Se o jogador aceita ir para um clube menor NESTE ano. Fixo por jogador e ano (nao
    usa o rng da janela): perguntar duas vezes da a mesma resposta."""
    chance = CHANCE_DE_TOPAR_DESCER
    if p.age(temporada) >= IDADE_DO_VETERANO:
        chance += EXTRA_DO_VETERANO
    return _sorteio_de_descer(p.id, temporada) < chance


@lru_cache(maxsize=65536)
def _sorteio_de_descer(pid: int, temporada: int) -> float:
    # a janela pergunta o mesmo jogador milhares de vezes (uma por comprador e rodada de
    # mercado); criar um gerador a cada pergunta custava 64 dos 72 segundos da virada
    return float(np.random.default_rng([pid, temporada, 5157]).random())
PREMIO_POR_TITULAR = 1.45       # tirar titular custa caro
SALARIO_DO_COMPRADOR = 1.15     # quem compra paga acima do que ele ganhava


@dataclass(slots=True)
class Transferencia:
    jogador: int
    nome: str
    de: int
    para: int
    preco: int
    overall: int


def _por_grupo(world: World, clube_id: int) -> dict[str, list]:
    elenco = [world.players[i] for i in world.clubs[clube_id].player_ids
              if i in world.players]
    fora: dict[str, list] = {}
    for p in elenco:
        fora.setdefault(p.position, []).append(p)
    for gente in fora.values():
        gente.sort(key=lambda p: -p.overall)
    return fora


def preco(world: World, jogador, temporada: int) -> int:
    """Quanto o dono pede. Contrato acabando derruba; potencial por explorar levanta."""
    valor = max(jogador.market_value, 50_000)
    pedida = valor * PREMIO_DE_PEDIDA
    restam = max(0, jogador.contract_until - temporada)
    if restam <= 1:
        pedida *= DESCONTO_CONTRATO_CURTO
    pedida *= 1 + PREMIO_POR_POTENCIAL * max(0, jogador.potential - jogador.overall)
    return int(pedida)


def _disponiveis(world: World, travados: set[int],
                 clubes: set[int] | None = None) -> dict[str, list[tuple]]:
    """Quem cada clube deixa sair: o que sobra da hierarquia, por posicao.

    Titular ninguem poe a venda. Quem esta atras dele na fila, sim -- e e por isso que o
    mercado funciona: o quarto zagueiro de um grande e titular num pequeno.
    """
    lista: dict[str, list[tuple]] = {}
    for clube in world.clubs.values():
        if clubes is not None and clube.id not in clubes:
            continue
        elenco = [i for i in clube.player_ids if i in world.players]
        if len(elenco) <= ELENCO_MINIMO_PARA_VENDER:
            continue
        for grupo, gente in _por_grupo(world, clube.id).items():
            titulares = TITULARES_POR_GRUPO.get(grupo, 3)
            for i, p in enumerate(gente):
                if p.id not in travados:
                    lista.setdefault(grupo, []).append((p, clube.id, i < titulares))
    return lista


def _buracos(world: World, clube_id: int) -> list[str]:
    """As posicoes do clube, da mais carente para a menos -- a ordem em que ele compra.

    Devolve a lista inteira, nao so a pior. Com so a pior, o clube mais forte do mundo
    nunca comprava nada: como ninguem a venda era melhor que os titulares dele naquela
    posicao, ele passava a janela parado, vendendo reserva e empilhando caixa. Grande de
    verdade reforca onde da, nao so onde doi.
    """
    nivel = world.team_rating(clube_id)
    folgas: list[tuple[float, str]] = []
    for grupo, gente in _por_grupo(world, clube_id).items():
        titulares = TITULARES_POR_GRUPO.get(grupo, 3)
        onze = gente[:titulares]
        if len(onze) < titulares:
            folgas.append((99.0, grupo))      # posicao descoberta: prioridade absoluta
            continue
        folgas.append((nivel - sum(p.overall for p in onze) / len(onze), grupo))
    return [g for _, g in sorted(folgas, reverse=True)]


def _endividados(world: World) -> dict[int, int]:
    """Quanto cada clube no vermelho precisa levantar nesta janela."""
    return {c.id: -c.balance for c in world.clubs.values() if c.balance < 0}


def janela(world: World, rng: np.random.Generator, temporada: int,
           clubes: set[int] | None = None) -> list[Transferencia]:
    """Uma janela inteira. Determinista dado o rng -- o save depende disso.

    `clubes`: quem participa (compra e vende). A carreira passa os clubes das ligas que
    ela joga: as ligas de fora (fm.carreira.LIGAS_DA_CONFEDERACAO) sao pano de fundo. Com
    elas na janela, os grandes compravam os melhores de la, os de la repunham com garotos
    novos, e o mundo ganhava talento de graca todo ano -- +0,27 de overall por temporada
    nos titulares da Serie A em 20 anos."""
    feitas: list[Transferencia] = []
    niveis = {c.id: world.team_rating(c.id) for c in world.clubs.values()
              if c.player_ids and (clubes is None or c.id in clubes)}
    # REGRESSAO: sem isto o mesmo jogador era comprado numa rodada de mercado e revendido na
    # seguinte, dentro da MESMA janela -- Natanael saiu do Atletico para o Santos e do
    # Santos para o Bahia no mesmo dia, pelo mesmo preco.
    travados: set[int] = set()

    for _ in range(RODADAS_DE_MERCADO):
        oferta = _disponiveis(world, travados, clubes)
        devem = _endividados(world)
        vendidos_por_clube: dict[int, int] = {}
        ordem = list(niveis)
        rng.shuffle(ordem)
        for comprador in ordem:
            clube = world.clubs[comprador]
            orcamento = clube.balance - sum(
                world.players[i].wage for i in clube.player_ids
                if i in world.players) * RESERVA_DE_CAIXA
            if orcamento <= 0:
                continue

            melhor, melhor_preco = None, 0
            for grupo in _buracos(world, comprador):
                titulares = TITULARES_POR_GRUPO.get(grupo, 3)
                meus = _por_grupo(world, comprador).get(grupo, [])
                corte = meus[titulares - 1].overall if len(meus) >= titulares else 0
                for p, dono, e_titular in oferta.get(grupo, []):
                    # `dono` e a lista do inicio da rodada: o jogador pode ja ter mudado de
                    # dono agora ha pouco, e por isso o travado tem de ser conferido AQUI
                    if p.id in travados or p.club_id != dono or dono == comprador:
                        continue
                    if p.overall <= corte:
                        continue
                    # so troca de escolhido quem e MELHOR que o atual: o resto nem precisa
                    # ter preco calculado (era o grosso dos 10 s da janela do mundo inteiro)
                    if melhor is not None and p.overall <= melhor.overall:
                        continue
                    salto = niveis[comprador] - niveis.get(dono, 0)
                    # o clube no vermelho nao esta em posicao de recusar: o titular dele sai
                    # para qualquer clube do mesmo patamar, nao so para quem esta acima
                    aperto = (SALTO_PARA_LEVAR_TITULAR if dono not in devem
                              else -DESCIDA_TOLERADA)
                    # na janela da IA so desce o veterano ou o titular que topa: soltar os
                    # reservas dos grandes para o resto inflava o mundo inteiro (+0,35 de
                    # overall por ano nos titulares da Serie A, medido em 20 temporadas)
                    desce = (((e_titular or p.age(temporada) >= IDADE_DO_VETERANO)
                              and topa_descer(p, temporada)) or insatisfeito(p))
                    if e_titular:
                        if salto < aperto and not desce:
                            continue
                    elif salto < -DESCIDA_TOLERADA and not desce:
                        continue
                    apertado = (dono in devem
                                and vendidos_por_clube.get(dono, 0) < VENDAS_FORCADAS)
                    valor = preco(world, p, temporada)
                    if insatisfeito(p):
                        valor = int(valor * DESCONTO_DO_INSATISFEITO)
                    elif e_titular:
                        valor = int(valor * PREMIO_POR_TITULAR)
                    if abatido(p):
                        valor = int(valor * DESCONTO_DO_ABATIDO)
                    if apertado:
                        valor = int(valor * DESCONTO_DE_URGENCIA)
                    if valor > orcamento:
                        continue
                    if melhor is None or p.overall > melhor.overall:
                        melhor, melhor_preco = p, valor
                if melhor is not None:
                    break            # reforcou a posicao mais carente; chega por esta vez
            if melhor is None:
                continue

            vendedor = world.clubs[melhor.club_id]
            vendedor.player_ids.remove(melhor.id)
            vendedor.balance += melhor_preco
            clube.player_ids.append(melhor.id)
            clube.balance -= melhor_preco
            melhor.club_id = comprador
            melhor.wage = int(melhor.wage * SALARIO_DO_COMPRADOR)
            melhor.contract_until = temporada + int(rng.integers(3, 6))
            feitas.append(Transferencia(melhor.id, melhor.name, vendedor.id, comprador,
                                        melhor_preco, melhor.overall))
            travados.add(melhor.id)
            vendidos_por_clube[vendedor.id] = vendidos_por_clube.get(vendedor.id, 0) + 1
            niveis[comprador] = world.team_rating(comprador)
            niveis[vendedor.id] = world.team_rating(vendedor.id)
    return feitas
