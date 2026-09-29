"""Estatisticas por jogador ao longo da temporada: jogos, gols, assistencias, cartoes.

O motor de eventos ja sabe quem fez o gol e quem deu o passe -- mas so na partida do
usuario, porque as outras sao resolvidas pelo motor rapido, que devolve apenas o placar.
Sem artilharia de campeonato o jogo fica sem uma das listas que mais se olha num manager.

A saida e' DISTRIBUIR os gols dos outros jogos entre os jogadores do clube, por posicao e
overall. Nao e' simulacao de cada lance: e' uma amostragem que respeita o placar real, e
por isso a soma dos gols dos artilheiros bate exatamente com a tabela. O atacante do
Palmeiras faz mais gols que o zagueiro porque a chance dele e' maior, nao porque alguem
decidiu antes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fm.competition import Result
from fm.model import World

# Peso de cada grupo na hora de sortear quem marcou. Medido de olho em campeonatos reais:
# atacantes fazem perto de metade dos gols, meias um terco, defensores o resto.
PESO_DO_GOL = {"FW": 1.00, "MF": 0.42, "DF": 0.13, "GK": 0.004}
# E de quem deu a assistencia. Meias assistem mais do que fazem.
PESO_DA_ASSISTENCIA = {"FW": 0.62, "MF": 1.00, "DF": 0.34, "GK": 0.02}
CHANCE_DE_ASSISTENCIA = 0.68      # nem todo gol tem passe para gol
PESO_DO_OVERALL = 2.2             # quanto o craque puxa a artilharia para si


@dataclass(slots=True)
class Linha:
    jogador: int
    jogos: int = 0
    gols: int = 0
    assistencias: int = 0
    amarelos: int = 0
    vermelhos: int = 0
    # a soma das notas de cada jogo e quantas: a media e o que as premiacoes do ano leem
    nota_total: float = 0.0
    notas: int = 0

    @property
    def media(self) -> float:
        return self.nota_total / self.notas if self.notas else 0.0

    def dar_nota(self, nota: float) -> None:
        self.nota_total += nota
        self.notas += 1


@dataclass(slots=True)
class Estatisticas:
    """Um caderno por temporada. Zera na virada do ano, como na vida real."""
    temporada: int
    por_jogador: dict[int, Linha] = field(default_factory=dict)

    def linha(self, jogador: int) -> Linha:
        if jogador not in self.por_jogador:
            self.por_jogador[jogador] = Linha(jogador=jogador)
        return self.por_jogador[jogador]

    def artilheiros(self, world: World, quantos: int = 20) -> list[Linha]:
        vivos = [x for x in self.por_jogador.values()
                 if x.gols and x.jogador in world.players]
        return sorted(vivos, key=lambda x: (-x.gols, -x.assistencias))[:quantos]

    def garcons(self, world: World, quantos: int = 20) -> list[Linha]:
        vivos = [x for x in self.por_jogador.values()
                 if x.assistencias and x.jogador in world.players]
        return sorted(vivos, key=lambda x: (-x.assistencias, -x.gols))[:quantos]


def _pesos(world: World, onze: list[int], tabela: dict[str, float]) -> np.ndarray:
    """Chance relativa de cada jogador do onze, por posicao e qualidade."""
    base = np.array([tabela.get(world.players[i].position, 0.1) for i in onze], dtype=float)
    over = np.array([world.players[i].overall for i in onze], dtype=float)
    if not len(over):
        return base
    relativo = (over - over.mean()) / max(over.std(), 1.0)
    return np.clip(base * np.exp(relativo * PESO_DO_OVERALL / 4.0), 1e-6, None)


def _cadernos(est) -> list[Estatisticas]:
    """Um caderno ou varios. Varios = o da temporada, o da competicao e o da rodada, todos
    somando o MESMO sorteio: o artilheiro da copa e o do ano nao podem discordar sobre
    quem fez o gol."""
    return list(est) if isinstance(est, (list, tuple)) else [est]


def registrar_partida_detalhada(est, world: World, partida) -> None:
    """Os eventos ja dizem quem fez e quem deu: aqui e' so somar."""
    from fm.notas import notas_da_partida
    notas = notas_da_partida(world, partida)
    for caderno in _cadernos(est):
        _somar_detalhada(caderno, world, partida)
        for pid, nota in notas.items():
            caderno.linha(pid).dar_nota(nota)


def _somar_detalhada(est: Estatisticas, world: World, partida) -> None:
    # `entrada` e todo mundo que pisou em campo: quem saiu no intervalo ou foi expulso
    # tambem jogou. Contar so quem terminou em campo apagava o jogo deles.
    for pid in (partida.entrada or partida.em_campo_casa + partida.em_campo_fora):
        est.linha(pid).jogos += 1
    for e in partida.eventos:
        if e.jogador is None:
            continue
        if e.tipo == "gol":
            est.linha(e.jogador).gols += 1
            if e.segundo is not None:
                est.linha(e.segundo).assistencias += 1
        elif e.tipo == "amarelo":
            est.linha(e.jogador).amarelos += 1
        elif e.tipo == "vermelho":
            est.linha(e.jogador).vermelhos += 1


def registrar_resultado(est, world: World, r: Result,
                        rng: np.random.Generator) -> None:
    """Distribui os gols de um placar entre os jogadores dos dois clubes.

    Respeita o placar: a soma da artilharia fecha com a tabela, sempre.
    """
    cadernos = _cadernos(est)
    for clube, gols in ((r.home, r.goals_home), (r.away, r.goals_away)):
        if clube not in world.clubs:
            continue
        onze = [p.id for p in world.best_xi(clube)]
        if not onze:
            continue
        for pid in onze:
            for c in cadernos:
                c.linha(pid).jogos += 1
        feitos: dict[int, list[int]] = {pid: [0, 0] for pid in onze}   # gols, assist.
        if gols:
            p_gol = _pesos(world, onze, PESO_DO_GOL)
            marcadores = rng.choice(onze, size=int(gols), p=p_gol / p_gol.sum())
            p_ass = _pesos(world, onze, PESO_DA_ASSISTENCIA)
            for autor in marcadores:
                feitos[int(autor)][0] += 1
                for c in cadernos:
                    c.linha(int(autor)).gols += 1
                if rng.random() < CHANCE_DE_ASSISTENCIA:
                    # quem assiste nao pode ser quem marcou
                    sem_autor = p_ass.copy()
                    sem_autor[onze.index(int(autor))] = 0.0
                    if sem_autor.sum() > 0:
                        quem = rng.choice(onze, p=sem_autor / sem_autor.sum())
                        feitos[int(quem)][1] += 1
                        for c in cadernos:
                            c.linha(int(quem)).assistencias += 1
        _notas_estimadas(cadernos, world, r, clube, feitos)


def _notas_estimadas(cadernos, world: World, r: Result, clube: int,
                     feitos: dict[int, list[int]]) -> None:
    """A nota de cada titular de um jogo do motor rapido (fm.notas.nota_estimada), com o
    que ele fez NESTE jogo."""
    from fm.notas import nota_estimada
    meus, deles = ((r.goals_home, r.goals_away) if clube == r.home
                   else (r.goals_away, r.goals_home))
    for pid, (g, a) in feitos.items():
        nota = nota_estimada(world.players[pid], meus, deles, g, a)
        for c in cadernos:
            c.linha(pid).dar_nota(nota)
