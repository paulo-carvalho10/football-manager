"""Motor rapido de partidas.

Poisson com diferenca de forca SATURADA. Calibrado em 1,5 milhao de partidas contra
distribuicoes reais (ver fm/calibration.py). As tres constantes abaixo sao o coracao do
jogo -- mexer nelas exige rodar o portao de calibracao de novo.

    z = (ovr_efetivo - PIVOT) / SCALE
    d = tanh((z_casa - z_fora) / SAT)          <- a saturacao: favorito para de crescer
    lambda_casa = gols_base * exp(+K*d + mando/2)
    lambda_fora = gols_base * exp(-K*d - mando/2)
    gols ~ Poisson(max(lambda, FLOOR))         <- FLOOR: ninguem e' nulo

Por que a saturacao: sem ela, um gap de 26 pontos de overall gera 22% de partidas com 3+
de margem (o real e' ~14%) e faz 9-0 aparecer. O tanh reproduz o que acontece de verdade:
time goleando administra, time perdendo se fecha.

Por que NAO ha ruido anonimo: a versao com mistura Gamma (Negative Binomial) foi testada e
o otimizador empurrou a dispersao para zero -- ela nao era necessaria e era o que gerava
goleada demais. Toda a variancia de uma partida deve vir de causa com NOME (desgaste,
moral, forma, classico), porque o jogador entende "meu time estava morto" e nao entende
"o multiplicador aleatorio deu 0,6".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

K = 0.58        # quanto a diferenca de forca separa os lambdas
SAT = 1.20      # escala da saturacao (em unidades de z)
FLOOR = 0.34    # gol esperado minimo: contra-ataque, penalti bobo, bola parada
PIVOT = 68.0    # overall considerado "medio" no mundo
SCALE = 20.0    # pontos de overall por unidade de z

MAX_FATIGUE_PENALTY = 8.0   # teto duro: desgaste inclina o jogo, nunca o decide


@dataclass(frozen=True, slots=True)
class Style:
    """Estilo de uma competicao. Vem do arquivo da liga, nunca do codigo."""

    goals_base: float = 1.255   # o `mu`: patamar de gols da liga
    home_adv: float = 0.30      # vantagem de casa em log-escala


@dataclass(frozen=True, slots=True)
class Mentality:
    """Mentalidade de uma fase. Mata-mata e classico comprimem o gap e travam o jogo."""

    goals_mult: float = 1.0   # copa: 0.90 (todo jogo vale a vida)
    compression: float = 0.0  # 0.20 em copa, 0.40 em classico: puxa os dois para a media
    home_mult: float = 1.0    # classico: mando vale menos

    # ClassVar, nao campo -- anotacao simples dentro de um dataclass viraria campo.
    NORMAL: ClassVar[Mentality]
    CUP: ClassVar[Mentality]
    DERBY: ClassVar[Mentality]


Mentality.NORMAL = Mentality()
Mentality.CUP = Mentality(goals_mult=0.90, compression=0.20)
Mentality.DERBY = Mentality(goals_mult=1.0, compression=0.40, home_mult=0.5)

DEFAULT_STYLE = Style()   # singleton: evita construir Style() em default de argumento


def to_z(rating: np.ndarray | float) -> np.ndarray:
    return (np.asarray(rating, dtype=float) - PIVOT) / SCALE


def effective_rating(
    base: np.ndarray | float,
    *,
    tactics: np.ndarray | float = 0.0,
    morale: np.ndarray | float = 0.0,
    fatigue: np.ndarray | float = 0.0,
) -> np.ndarray:
    """Overall efetivo do onze, em pontos de overall -- auditavel na tela do jogo.

    `fatigue` entra como PENALIDADE em pontos de overall, com teto. Medido: desgaste
    maximo leva a derrota do favorito (78 x 64) de 14,3% para 19,0% -- o jogador sente e
    planeja rotacao por isso, mas nunca vira sorteio.
    """
    pen = np.clip(np.asarray(fatigue, dtype=float), 0.0, MAX_FATIGUE_PENALTY)
    return np.asarray(base, dtype=float) + np.asarray(tactics) + np.asarray(morale) - pen


def lambdas(
    rating_home: np.ndarray | float,
    rating_away: np.ndarray | float,
    style: Style | None = None,
    mentality: Mentality = Mentality.NORMAL,
) -> tuple[np.ndarray, np.ndarray]:
    """Gols esperados de cada lado. Vetorizado: aceita milhares de partidas de uma vez."""
    style = style or DEFAULT_STYLE
    zh, za = to_z(rating_home), to_z(rating_away)
    if mentality.compression:
        mid = (zh + za) / 2.0
        keep = 1.0 - mentality.compression
        zh, za = mid + (zh - mid) * keep, mid + (za - mid) * keep
    d = np.tanh((zh - za) / SAT)
    mu = style.goals_base * mentality.goals_mult
    adv = (style.home_adv * mentality.home_mult) / 2.0
    lh = np.maximum(mu * np.exp(K * d + adv), FLOOR)
    la = np.maximum(mu * np.exp(-K * d - adv), FLOOR)
    return lh, la


def simulate(
    rating_home: np.ndarray | float,
    rating_away: np.ndarray | float,
    rng: np.random.Generator,
    style: Style | None = None,
    mentality: Mentality = Mentality.NORMAL,
) -> tuple[np.ndarray, np.ndarray]:
    """Placar final. Caminho rapido: milhares de partidas em milissegundos."""
    lh, la = lambdas(rating_home, rating_away, style, mentality)
    return rng.poisson(lh), rng.poisson(la)


def penalty_shootout(
    rating_home: np.ndarray | float,
    rating_away: np.ndarray | float,
    rng: np.random.Generator,
) -> np.ndarray:
    """True = a casa passa. Penalti e' quase moeda: a forca vale pouco, de proposito."""
    edge = 0.10 * np.tanh((to_z(rating_home) - to_z(rating_away)) / SAT)
    p = 0.50 + edge
    return rng.random(np.shape(np.broadcast_arrays(p, p)[0])) < p
