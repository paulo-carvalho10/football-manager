"""Motor detalhado: a partida minuto a minuto.

Existe por causa de UMA coisa que o motor rapido nao consegue dar: substituicao no meio do
jogo tem de mudar o resultado. Para isso a partida e dividida em BLOCOS de 15 minutos, e a
cada bloco a forca de cada lado e recalculada a partir de quem esta em campo e do quanto
esses onze ja gastaram. Trocar um jogador cansado por um inteiro no segundo tempo muda os
gols esperados do bloco seguinte -- que e o ponto.

REGRA INEGOCIAVEL: este motor tem de produzir a MESMA distribuicao de placares que o
rapido. Se a partida do usuario tiver media de gols diferente do resto do mundo, a tabela
fica torta e o jogador sente sem saber por que. tests/test_eventos.py cobra isso.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fm.match import Mentality, Style, lambdas
from fm.model import World

# Blocos de 5 minutos. Eram 15, e isso bastava para o terminal, que so pergunta sobre
# trocas no intervalo e aos 60 e 75. A tela ao vivo pausa em qualquer minuto: com bloco
# de 15 a troca pedida aos 17' so entrava aos 30'. Os pesos sao os mesmos seis de antes,
# cada um repetido tres vezes, e a soma de Poissons e Poisson -- o placar tem a mesma
# distribuicao.
MINUTOS_POR_BLOCO = 5
BLOCOS = 90 // MINUTOS_POR_BLOCO

# Gol e mais provavel no fim de cada tempo: cansaco, espaco e desespero.
PESO_DO_BLOCO = np.repeat(np.array([0.82, 1.00, 1.10, 0.95, 1.05, 1.18]),
                          15 // MINUTOS_POR_BLOCO)

# Quanto cada posicao participa dos gols do time.
PESO_DE_GOL = {"FW": 4.2, "WG": 2.6, "AM": 2.0, "MF": 1.0, "DM": 0.45,
               "FB": 0.35, "CB": 0.45, "GK": 0.02}
PESO_DE_ASSISTENCIA = {"AM": 3.0, "WG": 2.8, "MF": 2.0, "FW": 1.6, "FB": 1.2,
                       "DM": 0.8, "CB": 0.3, "GK": 0.05}
# Quem comete falta e leva cartao.
PESO_DE_CARTAO = {"DM": 2.6, "CB": 2.2, "FB": 1.8, "MF": 1.4, "AM": 0.9,
                  "FW": 0.9, "WG": 0.8, "GK": 0.25}

CONVERSAO = 0.105       # gols por finalizacao
NO_GOL = 0.36           # fracao das finalizacoes que vao no gol
# Gol e sempre no gol, entao a chance de um chute SEM gol ir no alvo e menor que NO_GOL:
# (0.36/0.105 - 1) / (1/0.105 - 1) = 0.285. Assim o total continua batendo os 36%.
NO_GOL_SEM_GOL = 0.285
# chutes de longe e bloqueados, por time e jogo, fora do xG. Com 4.0 o jogo somava 32
# finalizacoes; o futebol de verdade fica perto de 25.
CHUTES_SEM_CHANCE = 1.5
AMARELOS_POR_TIME = 1.9
CHANCE_DE_VERMELHO = 0.035
# Quem ja tem amarelo segura a mao: a chance de ele cometer a proxima falta para cartao cai
# para este fator. Sem isso o volante amarelado continuava sendo sorteado como se nada
# tivesse acontecido, e saiam 0,42 vermelho por jogo -- o Brasileirao tem perto de 0,28.
CAUTELA_DO_AMARELADO = 0.3
# Penalti: perto de 0,28 por jogo no futebol de verdade, 3 em cada 4 convertidos.
PENALTIS_POR_TIME = 0.14
CONVERSAO_PENALTI = 0.76
DESARMES_BASE = 16.0
FALTAS_BASE = 12.0
IMPEDIMENTOS_BASE = 2.2
PASSES_ERRADOS_BASE = 58.0
ESCANTEIOS_POR_CHUTE = 0.42
# Nem toda falta vira linha no lance a lance: 24 faltas por jogo afogariam os gols.
FALTAS_NARRADAS = 0.35

# Desgaste DENTRO da partida. Duas parcelas, com pesos bem diferentes de proposito:
# o FOLEGO (stamina) pesa pouco, porque ele separa jogadores entre si e mexeria na
# calibracao; a ENERGIA COM QUE ENTROU pesa muito, porque e ela que faz a substituicao
# valer. Com os pesos antigos (0.22 para as duas) trocar tres cansados no minuto 60 mudava
# os gols sofridos de 0,52 para 0,48 -- ruido, nao decisao.
QUEDA_POR_FOLEGO = 0.18
QUEDA_POR_ENERGIA = 0.45
RENDIMENTO_MINIMO = 0.55


@dataclass(slots=True)
class Evento:
    minuto: int
    tipo: str                    # gol, amarelo, vermelho, substituicao
    clube: int
    jogador: int | None = None
    segundo: int | None = None   # assistencia, ou quem entra na substituicao
    texto: str = ""


@dataclass(slots=True)
class Estatisticas:
    posse: int = 50
    finalizacoes: int = 0
    no_gol: int = 0
    desarmes: int = 0
    faltas: int = 0
    escanteios: int = 0
    impedimentos: int = 0
    passes_errados: int = 0
    amarelos: int = 0
    vermelhos: int = 0


@dataclass(slots=True)
class Ajuste:
    """O que o treinador muda no fim de um bloco: trocas e, se quiser, a tatica.

    `mult_casa`/`mult_fora` None mantem os multiplicadores que estavam valendo. O motor
    nao conhece Tatica -- quem traduz tatica em multiplicador e quem chama.
    """
    trocas: list = field(default_factory=list)
    mult_casa: float | None = None
    mult_fora: float | None = None


@dataclass(slots=True)
class Partida:
    casa: int
    fora: int
    gols_casa: int = 0
    gols_fora: int = 0
    eventos: list[Evento] = field(default_factory=list)
    stats_casa: Estatisticas = field(default_factory=Estatisticas)
    stats_fora: Estatisticas = field(default_factory=Estatisticas)
    em_campo_casa: list[int] = field(default_factory=list)
    em_campo_fora: list[int] = field(default_factory=list)
    # minuto em que cada um entrou: e o que diz o desgaste e quem jogou
    entrada: dict[int, int] = field(default_factory=dict)
    minuto: int = 0             # ate onde a partida ja foi jogada
    # posse de cada bloco jogado; a da partida e a media
    posses: list[float] = field(default_factory=list)
    # {jogador: papel da vaga que ocupa}. Quem nao esta aqui joga pela propria posicao.
    papeis: dict[int, str] = field(default_factory=dict)

    @property
    def placar(self) -> str:
        return f"{self.gols_casa} x {self.gols_fora}"


def _rendimento(jogador, minuto: int) -> float:
    """Quanto o jogador rende neste minuto, de 0 a 1.

    Cai ao longo da partida conforme o folego dele e a energia com que entrou. E o que faz
    o banco valer: um reserva inteiro no minuto 60 rende mais que um titular esfalfado.
    """
    entrou_com = jogador.condition / 100.0
    folego = jogador.stamina / 100.0
    queda = (QUEDA_POR_FOLEGO * (1.0 - folego)
             + QUEDA_POR_ENERGIA * (1.0 - entrou_com))
    return max(RENDIMENTO_MINIMO, 1.0 - queda * (minuto / 90.0))


def _forca_em_campo(world: World, ids: list[int], minuto: int,
                    entrada: dict[int, int]) -> float:
    """Overall medio de quem esta em campo, descontado o desgaste ATE este minuto."""
    if not ids:
        return 40.0
    total = 0.0
    for pid in ids:
        p = world.players[pid]
        # quem entrou no minuto 60 so acumulou desgaste de 30 minutos
        jogados = minuto - entrada.get(pid, 0)
        total += p.overall * _rendimento(p, max(jogados, 0))
    return total / len(ids)


def _sortear(rng, ids, world, pesos: dict[str, float],
             papeis: dict[int, str] | None = None,
             cautelosos: set[int] | None = None) -> int | None:
    if not ids:
        return None
    papeis = papeis or {}
    cautelosos = cautelosos or set()
    w = np.array([max(pesos.get(papeis.get(i, world.players[i].position_detail), 0.5), 0.01)
                  * (CAUTELA_DO_AMARELADO if i in cautelosos else 1.0)
                  for i in ids], dtype=float)
    return int(rng.choice(ids, p=w / w.sum()))


def simular_partida(
    world: World, casa: int, fora: int, onze_casa: list[int], onze_fora: list[int],
    rng: np.random.Generator, style: Style | None = None,
    mentality: Mentality = Mentality.NORMAL,
    mult_casa: float = 1.0, mult_fora: float = 1.0,
    substituicoes=None, papeis: dict[int, str] | None = None,
    cobradores: dict[int, list[int]] | None = None, penaltis=None,
) -> Partida:
    """Partida minuto a minuto.

    `papeis` diz a vaga de cada jogador escalado (fm.tatica.VAGAS): o meia escalado de
    centroavante finaliza como centroavante. Nao mexe no total de gols do time, so em
    quem os faz.

    `substituicoes` e uma funcao chamada ao fim de cada bloco:
        f(partida, minuto) -> [(clube, sai, entra), ...]  ou  Ajuste
    E por ela que o usuario troca jogador e muda a tatica no meio do jogo -- e por ela que
    a tela ao vivo pausa: enquanto a funcao nao volta, a partida nao anda. Devolver lista
    vazia mantem tudo como esta.

    `cobradores` e a ordem de batedores de penalti de cada clube; `penaltis`, uma funcao
    f(partida, minuto, clube) -> id do batedor ou None, chamada NO MINUTO do penalti -- e
    por ela que a tela pausa e o treinador escolhe quem bate. None usa a ordem de
    cobradores, e sem ordem, o melhor finalizador em campo.
    """
    cobradores = cobradores or {}
    p = Partida(casa=casa, fora=fora,
                em_campo_casa=list(onze_casa), em_campo_fora=list(onze_fora))
    p.entrada = {pid: 0 for pid in onze_casa + onze_fora}
    p.papeis = dict(papeis or {})
    amarelados: set[int] = set()

    for bloco in range(BLOCOS):
        minuto_ini = bloco * MINUTOS_POR_BLOCO
        minuto_meio = minuto_ini + MINUTOS_POR_BLOCO // 2

        rc = _forca_em_campo(world, p.em_campo_casa, minuto_meio, p.entrada)
        rf = _forca_em_campo(world, p.em_campo_fora, minuto_meio, p.entrada)
        lc, lf = lambdas(rc, rf, style, mentality)
        peso = PESO_DO_BLOCO[bloco] / PESO_DO_BLOCO.sum()
        xg_c = float(lc) * mult_casa * peso
        xg_f = float(lf) * mult_fora * peso
        # O penalti sai de dentro do xG, nao por cima: o que ele converte em media e
        # descontado do jogo corrido, e a media de gols continua a do motor calibrado.
        pen = PENALTIS_POR_TIME / BLOCOS
        gc = int(rng.poisson(max(0.0, xg_c - pen * CONVERSAO_PENALTI)))
        gf = int(rng.poisson(max(0.0, xg_f - pen * CONVERSAO_PENALTI)))

        # Gols, cartoes e lances do bloco sao sorteados JUNTOS e processados em ordem de
        # minuto. Separados, saiam fora de causalidade: um jogador levava vermelho aos
        # 51 e marcava aos 58, ja expulso.
        agenda = []

        def agendar(tipo: str, clube_lado: int, vezes: int) -> None:
            for _ in range(vezes):
                agenda.append((int(minuto_ini + rng.integers(1, MINUTOS_POR_BLOCO + 1)),
                               tipo, clube_lado))

        agendar("gol", casa, gc)
        agendar("gol", fora, gf)
        for clube_lado in (casa, fora):
            agendar("cartao", clube_lado, int(rng.poisson(AMARELOS_POR_TIME / BLOCOS)))
            agendar("penalti", clube_lado, int(rng.poisson(pen)))
        # Os lances que nao sao gol saem do MESMO xG do bloco: quem finaliza muito e quem
        # tinha mais chance de marcar. A estatistica ao vivo conta estes lances, entao a
        # tela e a sumula nunca discordam.
        for clube_lado, xg, gols in ((casa, xg_c, gc), (fora, xg_f, gf)):
            chutes = int(rng.poisson(xg * (1.0 / CONVERSAO - 1.0)
                                     + CHUTES_SEM_CHANCE / BLOCOS))
            agendar("chute", clube_lado, chutes)
            agendar("escanteio", clube_lado,
                    int(rng.poisson((chutes + gols) * ESCANTEIOS_POR_CHUTE)))
            agendar("impedimento", clube_lado, int(rng.poisson(IMPEDIMENTOS_BASE / BLOCOS)))
            agendar("falta", clube_lado, int(rng.poisson(FALTAS_BASE / BLOCOS)))
        agenda.sort(key=lambda x: x[0])

        for minuto, tipo, clube_lado in agenda:
            em_campo = p.em_campo_casa if clube_lado == casa else p.em_campo_fora
            if tipo == "gol":
                _marcar(p, world, rng, clube_lado, em_campo, minuto)
            elif tipo == "cartao":
                _cartao(p, world, rng, clube_lado, em_campo, minuto, amarelados)
            elif tipo == "penalti":
                _penalti(p, world, rng, clube_lado, em_campo, minuto,
                         cobradores.get(clube_lado, []), penaltis)
            else:
                _lance(p, world, rng, tipo, clube_lado, em_campo, minuto)

        _estatisticas_do_bloco(p, rng, rc, rf)
        p.minuto = minuto_ini + MINUTOS_POR_BLOCO
        p.eventos.sort(key=lambda e: e.minuto)

        if substituicoes and bloco < BLOCOS - 1:
            ajuste = substituicoes(p, p.minuto) or []
            if not isinstance(ajuste, Ajuste):
                ajuste = Ajuste(trocas=list(ajuste))
            if ajuste.mult_casa is not None:
                mult_casa = ajuste.mult_casa
            if ajuste.mult_fora is not None:
                mult_fora = ajuste.mult_fora
            for clube, sai, entra in ajuste.trocas:
                lista = p.em_campo_casa if clube == casa else p.em_campo_fora
                # quem ja jogou nao entra de novo: sem isto o banco virava porta giratoria
                if sai in lista and entra not in p.entrada:
                    lista[lista.index(sai)] = entra
                    p.entrada[entra] = p.minuto
                    if sai in p.papeis:            # quem entra assume a vaga de quem saiu
                        p.papeis[entra] = p.papeis[sai]
                    p.eventos.append(Evento(
                        p.minuto, "substituicao", clube,
                        jogador=sai, segundo=entra,
                        texto=f"{world.players[entra].name} entra no lugar de "
                              f"{world.players[sai].name}"))

    _fechar_estatisticas(p)
    p.eventos.sort(key=lambda e: e.minuto)
    return p


def chance_de_converter(batedor, goleiro) -> float:
    """Batedor bom contra goleiro bom: a conta que a tela de escolha mostra."""
    mira = (batedor.finishing + batedor.technique) / 2
    reflexo = goleiro.reflexes if goleiro is not None else 60
    return float(np.clip(CONVERSAO_PENALTI + (mira - 75) * 0.005 - (reflexo - 75) * 0.004,
                         0.55, 0.93))


def _penalti(p: Partida, world, rng, clube: int, em_campo: list[int], minuto: int,
             ordem: list[int], decidir) -> None:
    if not em_campo:
        return
    escolha = None
    if decidir is not None:
        p.minuto = minuto            # a tela mostra a partida parada NESTE minuto
        escolha = decidir(p, minuto, clube)
    if escolha not in em_campo:
        escolha = next((x for x in ordem if x in em_campo), None)
    if escolha not in em_campo:
        escolha = max(em_campo, key=lambda i: world.players[i].finishing
                      + world.players[i].technique)
    rival = p.em_campo_fora if clube == p.casa else p.em_campo_casa
    goleiro = next((world.players[i] for i in rival if world.players[i].position == "GK"), None)
    batedor = world.players[escolha]
    nome_clube = world.clubs[clube].name
    p.eventos.append(Evento(minuto, "penalti", clube, jogador=escolha,
                            texto=f"PÊNALTI para o {nome_clube}! {batedor.name} vai cobrar"))
    st = p.stats_casa if clube == p.casa else p.stats_fora
    st.finalizacoes += 1
    if rng.random() < chance_de_converter(batedor, goleiro):
        if clube == p.casa:
            p.gols_casa += 1
        else:
            p.gols_fora += 1
        st.no_gol += 1
        p.eventos.append(Evento(minuto, "gol", clube, jogador=escolha,
                                texto=f"GOL! {batedor.name} (pênalti)"))
    elif rng.random() < 0.6 and goleiro is not None:
        st.no_gol += 1
        p.eventos.append(Evento(minuto, "penalti_defendido", clube, jogador=escolha,
                                segundo=goleiro.id,
                                texto=f"{goleiro.name} defende o pênalti de {batedor.name}!"))
    else:
        p.eventos.append(Evento(minuto, "penalti_fora", clube, jogador=escolha,
                                texto=f"{batedor.name} bate para fora!"))


def rendimento_em_campo(world: World, partida: Partida, pid: int) -> int:
    """O folego de quem esta em campo AGORA, em %: o que a tela ao vivo mostra."""
    p = world.players[pid]
    jogados = max(partida.minuto - partida.entrada.get(pid, 0), 0)
    return int(round(p.condition * _rendimento(p, jogados)))


def _marcar(p: Partida, world, rng, clube: int, em_campo: list[int], minuto: int) -> None:
    autor = _sortear(rng, em_campo, world, PESO_DE_GOL, p.papeis)
    candidatos = [i for i in em_campo if i != autor]
    assist = _sortear(rng, candidatos, world, PESO_DE_ASSISTENCIA, p.papeis) if candidatos else None
    if clube == p.casa:
        p.gols_casa += 1
    else:
        p.gols_fora += 1
    # gol e finalizacao no gol: sem isto um 2 x 0 saia com uma finalizacao no alvo
    st = p.stats_casa if clube == p.casa else p.stats_fora
    st.finalizacoes += 1
    st.no_gol += 1
    nome = world.players[autor].name if autor else "?"
    p.eventos.append(Evento(minuto, "gol", clube, jogador=autor, segundo=assist,
                            texto=f"GOL! {nome}"))


def _cartao(p: Partida, world, rng, clube: int, em_campo: list[int],
            minuto: int, amarelados: set[int]) -> None:
    quem = _sortear(rng, em_campo, world, PESO_DE_CARTAO, p.papeis, amarelados)
    if quem is None:
        return
    if quem in amarelados or rng.random() < CHANCE_DE_VERMELHO:
        p.eventos.append(Evento(minuto, "vermelho", clube, jogador=quem,
                                texto=f"VERMELHO em {world.players[quem].name}"))
        em_campo.remove(quem)
    else:
        amarelados.add(quem)
        p.eventos.append(Evento(minuto, "amarelo", clube, jogador=quem,
                                texto=f"amarelo em {world.players[quem].name}"))


def _lance(p: Partida, world, rng, tipo: str, clube: int, em_campo: list[int],
           minuto: int) -> None:
    """Chute, escanteio, impedimento ou falta: conta na estatistica e, quase sempre, narra."""
    st = p.stats_casa if clube == p.casa else p.stats_fora
    if tipo == "chute":
        quem = _sortear(rng, em_campo, world, PESO_DE_GOL, p.papeis)
        st.finalizacoes += 1
        nome = world.players[quem].name if quem else "?"
        if rng.random() < NO_GOL_SEM_GOL:
            st.no_gol += 1
            p.eventos.append(Evento(minuto, "defesa", clube, jogador=quem,
                                    texto=f"{nome} finaliza e o goleiro defende"))
        else:
            p.eventos.append(Evento(minuto, "chute", clube, jogador=quem,
                                    texto=f"{nome} finaliza para fora"))
    elif tipo == "escanteio":
        st.escanteios += 1
        p.eventos.append(Evento(minuto, "escanteio", clube,
                                texto=f"Escanteio para o {world.clubs[clube].name}"))
    elif tipo == "impedimento":
        quem = _sortear(rng, em_campo, world, PESO_DE_GOL, p.papeis)
        st.impedimentos += 1
        nome = world.players[quem].name if quem else "?"
        p.eventos.append(Evento(minuto, "impedimento", clube, jogador=quem,
                                texto=f"{nome} estava impedido"))
    elif tipo == "falta":
        quem = _sortear(rng, em_campo, world, PESO_DE_CARTAO, p.papeis)
        st.faltas += 1
        if quem and rng.random() < FALTAS_NARRADAS:
            p.eventos.append(Evento(minuto, "falta", clube, jogador=quem,
                                    texto=f"Falta de {world.players[quem].name}"))


def _estatisticas_do_bloco(p: Partida, rng, rc: float, rf: float) -> None:
    """Posse, desarmes e passes errados do bloco: o que nao vira lance narrado.

    A posse sai da diferenca de forca em campo -- o time melhor fica com a bola -- mais
    ruido, e a da partida e a media dos blocos, entao ela se move ao vivo.
    """
    posse = float(np.clip(50.0 + (rc - rf) * 0.9 + rng.normal(0, 5.0), 30, 70))
    p.posses.append(posse)
    for st, minha in ((p.stats_casa, posse), (p.stats_fora, 100 - posse)):
        st.desarmes += int(rng.poisson(DESARMES_BASE / BLOCOS))
        # quem fica menos com a bola erra mais passe
        st.passes_errados += int(rng.poisson(
            PASSES_ERRADOS_BASE / BLOCOS * (1.25 - minha / 200.0)))
    casa = int(round(sum(p.posses) / len(p.posses)))
    p.stats_casa.posse = int(np.clip(casa, 28, 72))
    p.stats_fora.posse = 100 - p.stats_casa.posse
    _fechar_estatisticas(p)


def _fechar_estatisticas(p: Partida) -> None:
    """Cartoes vem dos eventos: a estatistica e a sumula nao podem discordar."""
    for clube, st in ((p.casa, p.stats_casa), (p.fora, p.stats_fora)):
        st.amarelos = sum(1 for e in p.eventos if e.tipo == "amarelo" and e.clube == clube)
        st.vermelhos = sum(1 for e in p.eventos if e.tipo == "vermelho" and e.clube == clube)
