"""Lesao: o jogador sai machucado de uma partida e fica fora por alguns jogos.

Mesmo mecanismo do gancho (fm.disciplina): o lesionado entra em `world.indisponiveis`
antes de cada data e so conta jogo cumprido quando o clube dele entra em campo. A
diferenca e que a lesao vale em todas as competicoes, e o tempo fora e sorteado pela
gravidade.

De onde vem: da partida detalhada do usuario (evento "lesao" do motor, fm.eventos) e dos
jogos do motor rapido (fm.central, num stream proprio). Nas duas, quem esta mais
desgastado se machuca mais -- e isso que faz a rotacao do elenco ser decisao de verdade.

A virada do ano cura todo mundo: a pre-temporada existe para isso, e a lesao longa que
atravessasse o ano exigiria um calendario de ferias que o jogo nao tem.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Lesoes que tiram o jogador de pelo menos um jogo, por time e partida. Com a duracao
# media abaixo (~2,9 jogos), cada clube tem perto de um jogador no departamento medico
# a qualquer momento.
LESOES_POR_TIME = 0.30

# (nome, minimo de jogos, maximo, peso)
TIPOS = (
    ("pancada", 1, 1, 0.30),
    ("desconforto muscular", 1, 2, 0.25),
    ("lesão muscular", 2, 4, 0.25),
    ("entorse no tornozelo", 3, 5, 0.10),
    ("lesão no joelho", 6, 12, 0.07),
    ("fratura", 10, 20, 0.03),
)


@dataclass(slots=True)
class Lesao:
    tipo: str
    jogos: int            # jogos que ainda vai perder
    total: int            # o tempo previsto quando se machucou


def peso_do_desgaste(rendimento: float) -> float:
    """Quem esta inteiro (100) pesa 1; quem esta no fim do gas (55) pesa 2,5."""
    return 1.0 + max(0.0, 100.0 - rendimento) / 30.0


def sortear_gravidade(rng: np.random.Generator) -> Lesao:
    pesos = np.array([t[3] for t in TIPOS])
    nome, minimo, maximo, _ = TIPOS[int(rng.choice(len(TIPOS), p=pesos / pesos.sum()))]
    jogos = int(rng.integers(minimo, maximo + 1))
    return Lesao(tipo=nome, jogos=jogos, total=jogos)


class DepartamentoMedico:
    def __init__(self) -> None:
        self.lesionados: dict[int, Lesao] = {}

    def fora(self) -> set[int]:
        return set(self.lesionados)

    def cumprir(self, clubes: set[int], world) -> list[int]:
        """Um jogo a menos para o lesionado cujo clube jogou. Devolve quem voltou."""
        voltaram = []
        for pid, les in list(self.lesionados.items()):
            p = world.players.get(pid)
            if p is None:
                del self.lesionados[pid]
                continue
            if p.club_id in clubes:
                les.jogos -= 1
                if les.jogos <= 0:
                    del self.lesionados[pid]
                    voltaram.append(pid)
        return voltaram

    def registrar(self, pids: list[int], rng: np.random.Generator) -> dict[int, Lesao]:
        """Os machucados da data. Ordem fixa (por id), para o sorteio da gravidade nao
        depender da ordem em que os jogos foram processados."""
        novas = {}
        for pid in sorted(set(pids)):
            les = sortear_gravidade(rng)
            atual = self.lesionados.get(pid)
            if atual is None or les.jogos > atual.jogos:
                self.lesionados[pid] = les
            novas[pid] = self.lesionados[pid]
        return novas
