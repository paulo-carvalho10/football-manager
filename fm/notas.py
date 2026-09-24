"""Nota de cada jogador na partida, de 3 a 10.

Derivada dos EVENTOS e do placar, nao sorteada: quem marcou, quem deu o passe, quem levou
cartao, quanto o time sofreu. E o que a sumula do pos-jogo mostra ao lado de cada nome.
A escala e a do jornal esportivo brasileiro -- 6 e jogo normal, 7 e bom, 8 e destaque.
"""

from __future__ import annotations

from fm.model import World

BASE = 6.0
POR_GOL = 1.1
POR_ASSISTENCIA = 0.6
POR_FINALIZACAO_NO_ALVO = 0.12
AMARELO = -0.35
VERMELHO = -1.6
VITORIA = 0.35
DERROTA = -0.35
# defesa e goleiro respondem pelos gols sofridos; o ataque, nao
POR_GOL_SOFRIDO = {"GK": -0.45, "DF": -0.3}
SEM_SOFRER = {"GK": 0.8, "DF": 0.5}
# o overall pesa pouco: e so para o craque apagado nao empatar com o reserva apagado
PESO_DO_OVERALL = 0.015
MINUTOS_PARA_NOTA_CHEIA = 30


def notas_da_partida(world: World, partida) -> dict[int, float]:
    notas: dict[int, float] = {}
    saidas = {e.jogador: e.minuto for e in partida.eventos
              if e.tipo in ("substituicao", "vermelho")}
    for pid, entrou in partida.entrada.items():
        p = world.players[pid]
        casa = pid in _lado(partida, partida.casa, world)
        meus = partida.gols_casa if casa else partida.gols_fora
        deles = partida.gols_fora if casa else partida.gols_casa
        # o CONTEXTO (placar, gols sofridos) pesa pelo tempo em campo: vinte minutos
        # nao fazem nem estrago nem festa. O que o jogador FEZ conta inteiro.
        contexto = (p.overall - 70) * PESO_DO_OVERALL
        contexto += VITORIA if meus > deles else DERROTA if meus < deles else 0.0
        if p.position in POR_GOL_SOFRIDO:
            contexto += (SEM_SOFRER[p.position] if deles == 0
                         else POR_GOL_SOFRIDO[p.position] * max(deles - 1, 0))
        jogados = saidas.get(pid, 90) - entrou
        contexto *= min(1.0, max(jogados, 5) / MINUTOS_PARA_NOTA_CHEIA)
        nota = BASE + contexto
        for e in partida.eventos:
            if e.jogador == pid:
                if e.tipo == "gol":
                    nota += POR_GOL
                elif e.tipo == "defesa":
                    nota += POR_FINALIZACAO_NO_ALVO
                elif e.tipo == "amarelo":
                    nota += AMARELO
                elif e.tipo == "vermelho":
                    nota += VERMELHO
            if e.tipo == "gol" and e.segundo == pid:
                nota += POR_ASSISTENCIA
        notas[pid] = round(min(10.0, max(3.0, nota)), 1)
    return notas


def _lado(partida, clube: int, world: World) -> set[int]:
    return {pid for pid in partida.entrada if world.players[pid].club_id == clube}
