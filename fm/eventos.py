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

BLOCOS = 6              # 6 blocos de 15 minutos
MINUTOS_POR_BLOCO = 15

# Gol e mais provavel no fim de cada tempo: cansaco, espaco e desespero.
PESO_DO_BLOCO = np.array([0.82, 1.00, 1.10, 0.95, 1.05, 1.18])

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
AMARELOS_POR_TIME = 1.9
CHANCE_DE_VERMELHO = 0.035
DESARMES_BASE = 16.0
FALTAS_BASE = 12.0

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


def _sortear(rng, ids, world, pesos: dict[str, float]) -> int | None:
    if not ids:
        return None
    w = np.array([max(pesos.get(world.players[i].position_detail, 0.5), 0.01)
                  for i in ids], dtype=float)
    return int(rng.choice(ids, p=w / w.sum()))


def simular_partida(
    world: World, casa: int, fora: int, onze_casa: list[int], onze_fora: list[int],
    rng: np.random.Generator, style: Style | None = None,
    mentality: Mentality = Mentality.NORMAL,
    mult_casa: float = 1.0, mult_fora: float = 1.0,
    substituicoes=None,
) -> Partida:
    """Partida minuto a minuto.

    `substituicoes` e uma funcao chamada ao fim de cada bloco:
        f(partida, minuto) -> [(clube, sai, entra), ...]
    E por ela que o usuario troca jogador no meio do jogo, e por ela que a IA rodaria o
    elenco. Devolver lista vazia mantem os onze em campo.
    """
    p = Partida(casa=casa, fora=fora,
                em_campo_casa=list(onze_casa), em_campo_fora=list(onze_fora))
    entrada: dict[int, int] = {pid: 0 for pid in onze_casa + onze_fora}
    amarelados: set[int] = set()

    for bloco in range(BLOCOS):
        minuto_ini = bloco * MINUTOS_POR_BLOCO
        minuto_meio = minuto_ini + MINUTOS_POR_BLOCO // 2

        rc = _forca_em_campo(world, p.em_campo_casa, minuto_meio, entrada)
        rf = _forca_em_campo(world, p.em_campo_fora, minuto_meio, entrada)
        lc, lf = lambdas(rc, rf, style, mentality)
        peso = PESO_DO_BLOCO[bloco] / PESO_DO_BLOCO.sum()
        gc = rng.poisson(float(lc) * mult_casa * peso)
        gf = rng.poisson(float(lf) * mult_fora * peso)

        # Gols e cartoes do bloco sao sorteados JUNTOS e processados em ordem de
        # minuto. Separados, saiam fora de causalidade: um jogador levava vermelho aos
        # 51 e marcava aos 58, ja expulso.
        agenda = []
        for _ in range(int(gc)):
            agenda.append((int(minuto_ini + rng.integers(1, MINUTOS_POR_BLOCO + 1)),
                           "gol", casa))
        for _ in range(int(gf)):
            agenda.append((int(minuto_ini + rng.integers(1, MINUTOS_POR_BLOCO + 1)),
                           "gol", fora))
        for clube_lado in (casa, fora):
            for _ in range(int(rng.poisson(AMARELOS_POR_TIME / BLOCOS))):
                agenda.append((int(minuto_ini + rng.integers(1, MINUTOS_POR_BLOCO + 1)),
                               "cartao", clube_lado))
        agenda.sort(key=lambda x: x[0])

        for minuto, tipo, clube_lado in agenda:
            em_campo = p.em_campo_casa if clube_lado == casa else p.em_campo_fora
            if tipo == "gol":
                _marcar(p, world, rng, clube_lado, em_campo, minuto)
            else:
                _cartao(p, world, rng, clube_lado, em_campo, minuto, amarelados)

        if substituicoes and bloco < BLOCOS - 1:
            for clube, sai, entra in (substituicoes(p, minuto_ini + MINUTOS_POR_BLOCO) or []):
                lista = p.em_campo_casa if clube == casa else p.em_campo_fora
                if sai in lista and entra not in lista:
                    lista[lista.index(sai)] = entra
                    entrada[entra] = minuto_ini + MINUTOS_POR_BLOCO
                    p.eventos.append(Evento(
                        minuto_ini + MINUTOS_POR_BLOCO, "substituicao", clube,
                        jogador=sai, segundo=entra,
                        texto=f"{world.players[entra].name} entra no lugar de "
                              f"{world.players[sai].name}"))

    _fechar_estatisticas(p, rng)
    p.eventos.sort(key=lambda e: e.minuto)
    return p


def _marcar(p: Partida, world, rng, clube: int, em_campo: list[int], minuto: int) -> None:
    autor = _sortear(rng, em_campo, world, PESO_DE_GOL)
    candidatos = [i for i in em_campo if i != autor]
    assist = _sortear(rng, candidatos, world, PESO_DE_ASSISTENCIA) if candidatos else None
    if clube == p.casa:
        p.gols_casa += 1
    else:
        p.gols_fora += 1
    nome = world.players[autor].name if autor else "?"
    p.eventos.append(Evento(minuto, "gol", clube, jogador=autor, segundo=assist,
                            texto=f"GOL! {nome}"))


def _cartao(p: Partida, world, rng, clube: int, em_campo: list[int],
            minuto: int, amarelados: set[int]) -> None:
    quem = _sortear(rng, em_campo, world, PESO_DE_CARTAO)
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


def _fechar_estatisticas(p: Partida, rng) -> None:
    """Estatisticas derivadas do placar, nao sorteadas a esmo.

    Finalizacao vem do gol pela taxa de conversao, entao um 3 x 0 nunca sai com 2 chutes.
    """
    for gols, st in ((p.gols_casa, p.stats_casa), (p.gols_fora, p.stats_fora)):
        base = gols / CONVERSAO if gols else 0
        st.finalizacoes = max(1, int(round(rng.normal(base + 4.0, 2.6))))
        st.no_gol = max(gols, int(round(st.finalizacoes * NO_GOL)))
        st.desarmes = max(0, int(round(rng.normal(DESARMES_BASE, 3.4))))
        st.faltas = max(0, int(round(rng.normal(FALTAS_BASE, 3.0))))
        st.escanteios = max(0, int(round(st.finalizacoes * 0.42 + rng.normal(0, 1.4))))
    total = p.stats_casa.finalizacoes + p.stats_fora.finalizacoes
    posse = 50 if not total else int(round(100 * p.stats_casa.finalizacoes / total))
    p.stats_casa.posse = int(np.clip(posse, 28, 72))
    p.stats_fora.posse = 100 - p.stats_casa.posse
