"""Os lances dos OUTROS jogos da rodada: quem marcou, em que minuto, cartoes e trocas.

O motor rapido resolve esses jogos so com o placar. Antes, os autores dos gols eram
sorteados depois do apito, direto na artilharia, e os cartoes, no caderno de disciplina.
A central da rodada precisa disso DURANTE a partida do usuario -- "57' Pedro marcou para o
Flamengo" --, entao os lances passam a ser gerados antes, num lugar so, e a artilharia e o
gancho passam a ler daqui. A tela e as estatisticas nunca discordam.

As substituicoes dos outros jogos sao so narrativas: o motor rapido nao tem minuto a
minuto, entao quem entra nao muda o placar (que ja saiu) nem conta jogo na estatistica.
Elas existem para a central parecer uma rodada de verdade, e o codigo diz isso.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fm.disciplina import sortear_cartoes
from fm.estatisticas import CHANCE_DE_ASSISTENCIA, PESO_DA_ASSISTENCIA, PESO_DO_GOL, _pesos
from fm.eventos import PESO_DO_BLOCO
from fm.lesoes import LESOES_POR_TIME, peso_do_desgaste
from fm.model import World

TROCAS_POR_TIME = (2, 5)          # quantas trocas cada time faz, no intervalo
JANELA_DE_TROCAS = (46, 88)       # entre que minutos


@dataclass(slots=True)
class Lance:
    minuto: int
    tipo: str               # gol, amarelo, vermelho, substituicao, lesao
    clube: int
    jogador: int | None
    segundo: int | None = None      # assistencia, ou quem entra


def _minuto(rng: np.random.Generator) -> int:
    """Minuto de um gol com a mesma curva do motor de eventos: mais no fim de cada tempo."""
    pesos = PESO_DO_BLOCO / PESO_DO_BLOCO.sum()
    largura = 90 // len(pesos)
    bloco = int(rng.choice(len(pesos), p=pesos))
    return int(bloco * largura + rng.integers(1, largura + 1))


def detalhar(world: World, r, rng: np.random.Generator,
             rng_lesoes: np.random.Generator | None = None) -> list[Lance]:
    """Os lances de um jogo do motor rapido, em ordem de minuto. Respeita o placar.

    As lesoes saem de `rng_lesoes`, um stream separado: sorteá-las no `rng` mudaria os
    autores dos gols e os cartoes de todos os saves."""
    lances: list[Lance] = []
    for clube, gols in ((r.home, r.goals_home), (r.away, r.goals_away)):
        if clube not in world.clubs:
            continue
        onze = [p.id for p in world.best_xi(clube)]
        if not onze:
            continue
        if gols:
            p_gol = _pesos(world, onze, PESO_DO_GOL)
            p_ass = _pesos(world, onze, PESO_DA_ASSISTENCIA)
            for autor in rng.choice(onze, size=int(gols), p=p_gol / p_gol.sum()):
                autor = int(autor)
                assist = None
                if rng.random() < CHANCE_DE_ASSISTENCIA:
                    sem_autor = p_ass.copy()
                    sem_autor[onze.index(autor)] = 0.0
                    if sem_autor.sum() > 0:
                        assist = int(rng.choice(onze, p=sem_autor / sem_autor.sum()))
                lances.append(Lance(_minuto(rng), "gol", clube, autor, assist))
        expulsos: set[int] = set()
        for pid, tipo in sortear_cartoes(world, onze, rng):
            lances.append(Lance(int(rng.integers(1, 91)), tipo, clube, pid))
            if tipo == "vermelho":
                expulsos.add(pid)
        # trocas narrativas: reservas do mesmo clube entram no lugar de titulares
        banco = [p.id for p in sorted(world.squad(clube), key=lambda p: -p.overall)
                 if p.id not in onze and p.id not in world.indisponiveis][:7]
        saem = [x for x in onze if x not in expulsos and world.players[x].position != "GK"]
        n = min(int(rng.integers(TROCAS_POR_TIME[0], TROCAS_POR_TIME[1] + 1)), len(banco), len(saem))
        for sai, entra in zip(rng.choice(saem, size=n, replace=False),
                              rng.choice(banco, size=n, replace=False), strict=True):
            lances.append(Lance(int(rng.integers(*JANELA_DE_TROCAS)), "substituicao", clube,
                                int(sai), int(entra)))
    if rng_lesoes is not None:
        _lesoes(world, r, rng_lesoes, lances)
    _coerencia(lances)
    lances.sort(key=lambda x: (x.minuto, {"gol": 0, "lesao": 1}.get(x.tipo, 2)))
    return lances


def _lesoes(world: World, r, rng: np.random.Generator, lances: list[Lance]) -> None:
    """Quem se machuca sai: reaproveita a troca narrativa se ele ja ia sair, senao entra
    um reserva do mesmo setor no minuto da lesao."""
    for clube in (r.home, r.away):
        if clube not in world.clubs:
            continue
        onze = [p.id for p in world.best_xi(clube)]
        n = int(rng.poisson(LESOES_POR_TIME))
        if not onze or n == 0:
            continue
        pesos = np.array([peso_do_desgaste(world.players[i].condition) for i in onze])
        for quem in rng.choice(onze, size=min(n, len(onze)), replace=False,
                               p=pesos / pesos.sum()):
            quem = int(quem)
            minuto = int(rng.integers(1, 91))
            troca = next((x for x in lances if x.tipo == "substituicao" and x.jogador == quem), None)
            if troca is not None:
                minuto = min(minuto, troca.minuto)
                troca.minuto = minuto
            else:
                usados = {x.segundo for x in lances if x.tipo == "substituicao"}
                banco = [p for p in sorted(world.squad(clube), key=lambda p: -p.overall)
                         if p.id not in onze and p.id not in usados
                         and p.id not in world.indisponiveis]
                if banco:
                    setor = world.players[quem].position
                    entra = next((p for p in banco if p.position == setor), banco[0])
                    lances.append(Lance(minuto, "substituicao", clube, quem, entra.id))
            lances.append(Lance(minuto, "lesao", clube, quem))


def _coerencia(lances: list[Lance]) -> None:
    """Ninguem marca, leva cartao ou sai depois de ter sido substituido ou expulso: o
    lance posterior e puxado para antes da saida. Barato e evita o absurdo na tela."""
    saida: dict[int, int] = {}
    for x in lances:
        if x.tipo in ("substituicao", "vermelho") and x.jogador is not None:
            saida[x.jogador] = min(saida.get(x.jogador, 99), x.minuto)
    for x in lances:
        limite = saida.get(x.jogador)
        if limite is not None and x.minuto > limite and x.tipo != "vermelho":
            if x.tipo == "substituicao" and x.minuto == limite:
                continue
            x.minuto = max(1, limite - 1)


def registrar(cadernos: list, world: World, r, lances: list[Lance]) -> None:
    """Soma os lances na estatistica: jogo e nota para os onze, gol, assistencia e
    cartao."""
    from fm.estatisticas import _notas_estimadas
    for clube in (r.home, r.away):
        if clube in world.clubs:
            feitos: dict[int, list[int]] = {}
            for p in world.best_xi(clube):
                feitos[p.id] = [0, 0]
                for c in cadernos:
                    c.linha(p.id).jogos += 1
            for x in lances:
                if x.tipo == "gol" and x.clube == clube:
                    if x.jogador in feitos:
                        feitos[x.jogador][0] += 1
                    if x.segundo in feitos:
                        feitos[x.segundo][1] += 1
            _notas_estimadas(cadernos, world, r, clube, feitos)
    for x in lances:
        if x.jogador is None:
            continue
        for c in cadernos:
            linha = c.linha(x.jogador)
            if x.tipo == "gol":
                linha.gols += 1
                if x.segundo is not None:
                    c.linha(x.segundo).assistencias += 1
            elif x.tipo == "amarelo":
                linha.amarelos += 1
            elif x.tipo == "vermelho":
                linha.vermelhos += 1


def lesionados(lances: list[Lance]) -> list[int]:
    return [x.jogador for x in lances if x.tipo == "lesao"]


def cartoes(lances: list[Lance]) -> list[tuple[int, str]]:
    return [(x.jogador, x.tipo) for x in lances if x.tipo in ("amarelo", "vermelho")]
