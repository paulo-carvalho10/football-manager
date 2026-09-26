"""Cartões e suspensões: o gancho.

As regras, como no futebol brasileiro e espanhol:

- vermelho (direto ou pelo segundo amarelo): 1 jogo de suspensão;
- 3 amarelos acumulados NA MESMA COMPETIÇÃO: 1 jogo, e a contagem zera;
- os amarelos de quem foi expulso na mesma partida não entram no acúmulo;
- a suspensão é cumprida na competição em que foi recebida: cartão do Brasileirão não
  tira ninguém da Copa do Brasil;
- tudo zera na virada do ano.

A partida do usuário tem cartões de verdade, pelos eventos. As outras são resolvidas pelo
motor rápido, que só devolve o placar, então os cartões delas são SORTEADOS aqui com as
mesmas taxas e pesos do motor de eventos -- sem isso os adversários nunca levariam
gancho e só o usuário teria desfalques.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fm.eventos import (AMARELOS_POR_TIME, CAUTELA_DO_AMARELADO, CHANCE_DE_VERMELHO,
                        PESO_DE_CARTAO)
from fm.model import World

AMARELOS_PARA_SUSPENSAO = 3
JOGOS_POR_VERMELHO = 1


@dataclass(slots=True)
class Disciplina:
    """O caderno de cartões do ano, por competição ("brasil_real", "libertadores"...)."""
    amarelos: dict[str, dict[int, int]] = field(default_factory=dict)
    suspensoes: dict[str, dict[int, int]] = field(default_factory=dict)

    def suspensos(self, competicao: str) -> set[int]:
        return {p for p, n in self.suspensoes.get(competicao, {}).items() if n > 0}

    def pendurados(self, competicao: str) -> set[int]:
        """A um amarelo do gancho."""
        return {p for p, n in self.amarelos.get(competicao, {}).items()
                if n == AMARELOS_PARA_SUSPENSAO - 1}

    def cumprir(self, competicao: str, clubes: set[int], world: World) -> None:
        """Quem estava suspenso e cujo clube jogou nesta data cumpriu um jogo."""
        susp = self.suspensoes.get(competicao, {})
        for pid in list(susp):
            p = world.players.get(pid)
            if p is None:
                susp.pop(pid)
                continue
            if p.club_id in clubes:
                susp[pid] -= 1
                if susp[pid] <= 0:
                    susp.pop(pid)

    def registrar(self, competicao: str, cartoes: list[tuple[int, str]]) -> list[int]:
        """Soma os cartoes de UMA partida. Devolve quem ficou suspenso por causa dela."""
        expulsos = {pid for pid, tipo in cartoes if tipo == "vermelho"}
        amarelos = self.amarelos.setdefault(competicao, {})
        susp = self.suspensoes.setdefault(competicao, {})
        novos: list[int] = []
        for pid in expulsos:
            susp[pid] = susp.get(pid, 0) + JOGOS_POR_VERMELHO
            novos.append(pid)
        for pid, tipo in cartoes:
            if tipo != "amarelo" or pid in expulsos:
                continue
            amarelos[pid] = amarelos.get(pid, 0) + 1
            if amarelos[pid] >= AMARELOS_PARA_SUSPENSAO:
                amarelos[pid] = 0
                susp[pid] = susp.get(pid, 0) + 1
                novos.append(pid)
        return novos


def cartoes_da_partida(partida) -> list[tuple[int, str]]:
    """Os cartoes de uma partida detalhada, na ordem em que aconteceram."""
    return [(e.jogador, e.tipo) for e in partida.eventos
            if e.tipo in ("amarelo", "vermelho") and e.jogador is not None]


def sortear_cartoes(world: World, onze: list[int],
                    rng: np.random.Generator) -> list[tuple[int, str]]:
    """Cartoes de um lado de uma partida do motor rapido, com as taxas do motor de eventos:
    em media AMARELOS_POR_TIME por jogo; o segundo amarelo e CHANCE_DE_VERMELHO viram
    vermelho."""
    if not onze:
        return []
    base = np.array([max(PESO_DE_CARTAO.get(world.players[i].position_detail, 0.5), 0.01)
                     for i in onze], dtype=float)
    saida: list[tuple[int, str]] = []
    amarelados: set[int] = set()
    expulsos: set[int] = set()
    for _ in range(int(rng.poisson(AMARELOS_POR_TIME))):
        pesos = base * np.array([CAUTELA_DO_AMARELADO if i in amarelados else 1.0
                                 for i in onze])
        quem = int(rng.choice(onze, p=pesos / pesos.sum()))
        if quem in expulsos:
            continue
        if quem in amarelados or rng.random() < CHANCE_DE_VERMELHO:
            saida.append((quem, "vermelho"))
            expulsos.add(quem)
        else:
            saida.append((quem, "amarelo"))
            amarelados.add(quem)
    return saida
