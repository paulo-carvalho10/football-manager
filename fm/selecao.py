"""A seleção da rodada: os onze melhores de cada rodada de liga, num 4-3-3.

Cada jogador que entrou em campo recebe uma nota. Na partida do usuário ela sai dos
lances (fm.notas.notas_da_partida). Nas outras, que o motor rápido resolve só com o
placar, sai do placar e do que o caderno da rodada registrou para ele: gols, assistências
e a posição que ocupava.

A nota das outras partidas é ESTIMADA, e o texto da tela diz isso. É a mesma escala e as
mesmas regras da nota dos lances, só que sem os lances.
"""

from __future__ import annotations

from fm.estatisticas import Estatisticas
from fm.model import World
from fm.notas import nota_estimada, notas_da_partida
from fm.tatica import VAGAS, arrumar_no_campo

FORMACAO = "4-3-3"


def selecao_da_rodada(world: World, resultados: list, caderno: Estatisticas,
                      detalhada=None) -> dict:
    """{"onze": [...11 na ordem das vagas do 4-3-3...], "craque": id} da rodada."""
    notas: dict[int, float] = {}
    clube_de: dict[int, int] = {}
    if detalhada is not None:
        notas.update(notas_da_partida(world, detalhada))
        for pid in detalhada.entrada:
            clube_de[pid] = world.players[pid].club_id

    for r in resultados:
        if detalhada is not None and (r.home, r.away) == (detalhada.casa, detalhada.fora):
            continue
        for clube, meus, deles in ((r.home, r.goals_home, r.goals_away),
                                   (r.away, r.goals_away, r.goals_home)):
            if clube not in world.clubs:
                continue
            for p in world.best_xi(clube):
                linha = caderno.por_jogador.get(p.id)
                notas[p.id] = nota_estimada(p, meus, deles,
                                            linha.gols if linha else 0,
                                            linha.assistencias if linha else 0)
                clube_de[p.id] = clube

    if not notas:
        return {"onze": [], "craque": None}
    ordem = sorted(notas, key=lambda i: (-notas[i], -world.players[i].overall, i))
    vagas_por_setor: dict[str, int] = {}
    for _, setor, _, _, _ in VAGAS[FORMACAO]:
        vagas_por_setor[setor] = vagas_por_setor.get(setor, 0) + 1
    escolhidos = []
    for pid in ordem:
        setor = world.players[pid].position
        if vagas_por_setor.get(setor, 0) > 0:
            vagas_por_setor[setor] -= 1
            escolhidos.append(world.players[pid])
        if len(escolhidos) == len(VAGAS[FORMACAO]):
            break
    no_campo = arrumar_no_campo(escolhidos, FORMACAO)
    onze = []
    for p, vaga in zip(no_campo, VAGAS[FORMACAO]):
        linha = caderno.por_jogador.get(p.id)
        onze.append({"jogador": p.id, "clube": clube_de[p.id], "nota": notas[p.id],
                     "gols": linha.gols if linha else 0,
                     "assistencias": linha.assistencias if linha else 0,
                     "vaga": vaga[0]})
    return {"onze": onze, "craque": ordem[0]}
