"""Disputa de penaltis: o desempate do mata-mata quando o agregado termina igual.

Cinco cobrancas para cada lado, alternadas; acaba antes se um lado nao alcanca mais o
outro. Empatou nas cinco, segue alternado ate um errar e o outro acertar. Batem os que
terminaram o jogo em campo: primeiro a ordem de batedores de Taticas (so do usuario),
depois os melhores finalizadores; o goleiro bate por ultimo. Se todos bateram, a fila
recomeca, como manda a regra.

A chance de cada cobranca e a do penalti de jogo (fm.eventos.chance_de_converter):
finalizacao e tecnica do batedor contra os reflexos do goleiro.

Duas saidas: `disputar`, com cada cobranca (para a tela acompanhar uma a uma), e
`vencedor_rapido`, a mesma disputa para os confrontos do motor rapido, que nao tem
jogadores em campo -- usa o onze de cada clube.
"""

from __future__ import annotations

import numpy as np

from fm.eventos import chance_de_converter
from fm.model import World

COBRANCAS = 5


def _fila(world: World, em_campo: list[int], ordem: list[int]) -> list[int]:
    """Quem bate, na ordem: os escolhidos, os melhores de linha, o goleiro por ultimo."""
    ps = [world.players[i] for i in em_campo if i in world.players]
    escolhidos = [i for i in ordem if i in em_campo]
    resto = sorted((p for p in ps if p.id not in escolhidos),
                   key=lambda p: (p.position == "GK", -(p.finishing + p.technique), p.id))
    return escolhidos + [p.id for p in resto]


def _goleiro(world: World, em_campo: list[int]):
    return next((world.players[i] for i in em_campo
                 if i in world.players and world.players[i].position == "GK"), None)


def disputar(world: World, casa: int, fora: int, em_campo_casa: list[int],
             em_campo_fora: list[int], rng: np.random.Generator,
             ordem: dict[int, list[int]] | None = None) -> dict:
    """A disputa inteira, cobranca por cobranca.

    Devolve {"cobrancas": [{"clube", "jogador", "convertido"}...], "gols": {casa, fora},
    "vencedor": clube, "primeiro": clube}.
    """
    ordem = ordem or {}
    lados = {casa: _fila(world, em_campo_casa, ordem.get(casa, [])),
             fora: _fila(world, em_campo_fora, ordem.get(fora, []))}
    goleiros = {casa: _goleiro(world, em_campo_fora), fora: _goleiro(world, em_campo_casa)}
    primeiro = casa if rng.random() < 0.5 else fora
    segundo = fora if primeiro == casa else casa
    gols = {casa: 0, fora: 0}
    batidas = {casa: 0, fora: 0}
    cobrancas = []

    def bater(clube: int) -> None:
        fila = lados[clube]
        pid = fila[batidas[clube] % len(fila)] if fila else None
        batidas[clube] += 1
        batedor = world.players.get(pid) if pid is not None else None
        chance = chance_de_converter(batedor, goleiros[clube]) if batedor else 0.7
        ok = bool(rng.random() < chance)
        gols[clube] += ok
        cobrancas.append({"clube": clube, "jogador": pid, "convertido": ok})

    def decidido() -> bool:
        """Nas cinco: acaba quando um lado nao alcanca o outro nem acertando o que falta."""
        restam = {k: COBRANCAS - batidas[k] for k in gols}
        return (gols[casa] + restam[casa] < gols[fora]
                or gols[fora] + restam[fora] < gols[casa])

    for _ in range(COBRANCAS):
        for clube in (primeiro, segundo):
            bater(clube)
            if decidido():
                break
        if decidido():
            break
    while gols[casa] == gols[fora]:               # alternadas
        bater(primeiro)
        bater(segundo)
    vencedor = casa if gols[casa] > gols[fora] else fora
    return {"cobrancas": cobrancas, "gols": gols, "vencedor": vencedor, "primeiro": primeiro}


def vencedor_rapido(world: World, casa: int, fora: int, rng: np.random.Generator) -> dict:
    """A mesma disputa para confronto do motor rapido: batem os onze de cada clube."""
    return disputar(world, casa, fora, [p.id for p in world.best_xi(casa)],
                    [p.id for p in world.best_xi(fora)], rng)
