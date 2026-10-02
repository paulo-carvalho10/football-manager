"""Lesao: o jogador sai machucado de uma partida e fica fora por alguns DIAS.

O tempo fora e contado no calendario (fm.calendario), nao em jogos: a lesao tem um dia de
volta, e o jogador so pode ser escalado numa data a partir desse dia. Semana cheia de
jogos (liga no domingo, copa na quarta) pesa mais que semana so de liga -- como no
futebol de verdade.

Antes de cada data o lesionado entra em `world.indisponiveis`, como o suspenso
(fm.disciplina), e vale para todas as competicoes.

De onde vem: da partida detalhada do usuario (evento "lesao" do motor, fm.eventos) e dos
jogos do motor rapido (fm.central, num stream proprio). Nas duas, quem esta mais
desgastado se machuca mais -- e isso que faz a rotacao do elenco ser decisao de verdade.

A virada do ano cura todo mundo: a pre-temporada existe para isso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

# Lesoes que tiram o jogador de campo, por time e partida.
#
# Era 0,30, com media de 17 dias (medidos: 23). Batia com a literatura de lesao em jogo,
# mas no jogo pesava demais: no calendario real um clube de Libertadores faz ~50 jogos, e
# a tela ao vivo mostra tambem as lesoes do adversario -- a sensacao era de lesao em todo
# jogo. Medido numa temporada do Cruzeiro: 18 lesoes, 3 delas de mais de 40 dias.
LESOES_POR_TIME = 0.20

# (nome, minimo de dias, maximo, peso). Media perto de 12 dias: a maioria e pancada ou
# desconforto de uma semana; joelho e fratura ficaram raros, como devem ser.
TIPOS = (
    ("pancada", 2, 6, 0.40),
    ("desconforto muscular", 4, 10, 0.27),
    ("lesão muscular", 10, 21, 0.20),
    ("entorse no tornozelo", 12, 28, 0.08),
    ("lesão no joelho", 35, 75, 0.04),
    ("fratura", 50, 100, 0.01),
)


@dataclass(slots=True)
class Lesao:
    tipo: str
    volta: date           # a partir deste dia pode jogar de novo
    dias: int             # o tempo previsto quando se machucou

    def dias_restantes(self, hoje: date) -> int:
        return max(0, (self.volta - hoje).days)


def peso_do_desgaste(rendimento: float) -> float:
    """Quem esta inteiro (100) pesa 1; quem esta no fim do gas (55) pesa 2,5."""
    return 1.0 + max(0.0, 100.0 - rendimento) / 30.0


def sortear_gravidade(rng: np.random.Generator, hoje: date) -> Lesao:
    pesos = np.array([t[3] for t in TIPOS])
    nome, minimo, maximo, _ = TIPOS[int(rng.choice(len(TIPOS), p=pesos / pesos.sum()))]
    dias = int(rng.integers(minimo, maximo + 1))
    return Lesao(tipo=nome, volta=hoje + timedelta(days=dias), dias=dias)


class DepartamentoMedico:
    def __init__(self) -> None:
        self.lesionados: dict[int, Lesao] = {}

    def fora(self, dia: date) -> set[int]:
        """Quem nao pode jogar numa partida neste dia."""
        return {pid for pid, les in self.lesionados.items() if les.volta > dia}

    def dar_alta(self, dia: date) -> list[int]:
        """Tira do departamento quem ja pode jogar neste dia. Devolve quem saiu."""
        voltaram = [pid for pid, les in self.lesionados.items() if les.volta <= dia]
        for pid in voltaram:
            del self.lesionados[pid]
        return voltaram

    def registrar(self, pids: list[int], rng: np.random.Generator,
                  hoje: date) -> dict[int, Lesao]:
        """Os machucados do dia. Ordem fixa (por id), para o sorteio da gravidade nao
        depender da ordem em que os jogos foram processados."""
        novas = {}
        for pid in sorted(set(pids)):
            les = sortear_gravidade(rng, hoje)
            atual = self.lesionados.get(pid)
            if atual is None or les.volta > atual.volta:
                self.lesionados[pid] = les
            novas[pid] = self.lesionados[pid]
        return novas
