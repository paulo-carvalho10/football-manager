"""Virar o ano: acesso, rebaixamento e a passagem do tempo sobre os jogadores.

Sem isto o jogo acaba na rodada 38. Com isto a piramide vira carreira: o clube sobe e
desce, o garoto de potencial 88 vira um 88, o veterano se aposenta e a base entrega gente
nova. E o que faz o Road to Glory existir.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fm.generate import _market_value
from fm.model import World
from fm.table import Row

# --- evolucao ---------------------------------------------------------------
# Quanto o jogador anda por temporada em direcao ao potencial (ou para baixo, no fim).
# Jovem evolui rapido, mas so ate onde o potencial permite; depois dos 30 comeca a cair.
PICO = 29
VELOCIDADE_JOVEM = 0.42       # fracao da distancia ate o potencial, por temporada
QUEDA_POR_ANO = 0.85          # pontos de overall perdidos por ano acima do pico
QUEDA_ACELERA = 0.22          # e a queda acelera

IDADE_MINIMA_APOSENTAR = 33
CHANCE_APOSENTADORIA = {33: 0.06, 34: 0.12, 35: 0.22, 36: 0.36, 37: 0.55, 38: 0.75}

# --- base -------------------------------------------------------------------
IDADE_DA_BASE = (17, 19)
# A base precisa de CAUDA. Com um sorteio uniforme a categoria de base nunca entrega um
# craque, e quando os importados se aposentam ninguem repoe o topo: em 20 temporadas o
# melhor jogador do mundo caia de 84 para 77. A maioria dos garotos vira reserva mediano,
# mas de vez em quando sai uma joia -- e clube grande produz joia com mais frequencia.
# O CENTRO desta faixa e o que decide se o mundo se mantem de pe. Ela nao e' estetica:
# a media dela e o fator pelo qual cada geracao substitui a anterior. Com (0.70, 1.00) a
# media e 0.85, cada geracao nascia 15% pior que a de antes e o onze medio da Serie A caia
# de 69.7 para 59.2 em 20 temporadas. Centrada em 0.99, a deriva fica em -0.01/ano.
POTENCIAL_DA_BASE = (0.88, 1.10)   # fracao da forca do elenco atual, sorteada
CHANCE_DE_JOIA = 0.05              # no clube mais forte do mundo; escala com a forca
JOIA_MULTIPLICADOR = (1.12, 1.34)
TETO_DA_BASE = 90                  # a base nao entrega um 92 pronto; o resto e evolucao
ELENCO_MINIMO, ELENCO_MAXIMO = 24, 32

# Quanto cada papel no elenco vale como "minutos jogados". Nao rastreamos minuto a minuto
# dos 40 clubes, mas a hierarquia por overall dentro da posicao diz quem jogou: e o mesmo
# raciocinio de titular/reserva que ratings.py ja usa para imputar valor.
PESO_TITULAR, PESO_RODAGEM, PESO_BANCO = 1.0, 0.6, 0.25
TITULARES_POR_GRUPO = {"GK": 1, "DF": 4, "MF": 3, "FW": 3}  # o 4-3-3 padrao


@dataclass(slots=True)
class MudancaDeDivisao:
    clube: int
    de: str
    para: str
    subiu: bool


def _quantos(cfg: dict, chave: str) -> int:
    return int(cfg.get("formato", {}).get("acesso", {}).get(chave, 0))


def acesso_e_rebaixamento(
    world: World, ligas: list[str], tabelas: dict[str, list[Row]], cfgs: dict[str, dict],
) -> list[MudancaDeDivisao]:
    """Troca clubes entre divisoes vizinhas, pela tabela final.

    As divisoes sao pareadas por `tier`. Quem desce da ultima divisao nao vai a lugar
    nenhum -- nao existe degrau abaixo neste mundo -- e simplesmente fica.
    """
    por_tier = sorted(ligas, key=lambda n: int(cfgs[n].get("tier", 1)))
    mudancas: list[MudancaDeDivisao] = []

    for cima, baixo in zip(por_tier, por_tier[1:], strict=False):
        descem = _quantos(cfgs[cima], "descem")
        sobem = _quantos(cfgs[baixo], "sobem")
        n = min(descem, sobem)
        if n <= 0:
            continue
        id_cima, id_baixo = cfgs[cima]["id"], cfgs[baixo]["id"]
        rebaixados = [r.club_id for r in tabelas[cima][-n:]]
        promovidos = [r.club_id for r in tabelas[baixo][:n]]

        for cid in rebaixados:
            world.leagues[id_cima].club_ids.remove(cid)
            world.leagues[id_baixo].club_ids.append(cid)
            world.clubs[cid].league_id = id_baixo
            mudancas.append(MudancaDeDivisao(cid, cima, baixo, subiu=False))
        for cid in promovidos:
            world.leagues[id_baixo].club_ids.remove(cid)
            world.leagues[id_cima].club_ids.append(cid)
            world.clubs[cid].league_id = id_cima
            mudancas.append(MudancaDeDivisao(cid, baixo, cima, subiu=True))
    return mudancas


def minutos_por_papel(world: World) -> dict[int, float]:
    """Quanto cada jogador jogou, deduzido da posicao dele na hierarquia do elenco.

    ATENCAO: nao use `condition` para isto. Condition e a energia que SOBROU no fim da
    temporada -- quem mais jogou termina com ela mais baixa. Usa-la como proxy de minutos
    inverte o sinal e faz o titular evoluir menos que o reserva.
    """
    peso: dict[int, float] = {}
    for clube in world.clubs.values():
        elenco = [world.players[i] for i in clube.player_ids if i in world.players]
        por_grupo: dict[str, list] = {}
        for p in elenco:
            por_grupo.setdefault(p.position, []).append(p)
        for grupo, gente in por_grupo.items():
            gente.sort(key=lambda p: p.overall, reverse=True)
            titulares = TITULARES_POR_GRUPO.get(grupo, 3)
            for i, p in enumerate(gente):
                peso[p.id] = (PESO_TITULAR if i < titulares
                              else PESO_RODAGEM if i < titulares * 2 else PESO_BANCO)
    return peso


def envelhecer(world: World, rng: np.random.Generator, temporada: int,
               minutos: dict[int, float] | None = None) -> dict[str, int]:
    """Um ano passa: idade sobe, jovem evolui, veterano cai, alguns se aposentam.

    A evolucao anda uma FRACAO da distancia ate o potencial, entao ninguem salta de 60 para
    88 numa temporada -- e ninguem fica parado. Quem jogou mais evolui mais: minuto em
    campo e o que faz o jovem virar jogador.
    """
    contagem = {"evoluiram": 0, "cairam": 0, "aposentaram": 0}
    aposentados: list[int] = []
    minutos = minutos_por_papel(world) if minutos is None else minutos

    for p in world.players.values():
        idade = temporada - p.birth_year
        if idade >= IDADE_MINIMA_APOSENTAR:
            chance = CHANCE_APOSENTADORIA.get(idade, 0.9 if idade > 38 else 0.0)
            # quem ainda e bom para o nivel dele segura mais um ano
            chance *= 1.35 if p.overall < 60 else 0.8
            if rng.random() < chance:
                aposentados.append(p.id)
                contagem["aposentaram"] += 1
                continue

        if idade < PICO and p.potential > p.overall:
            # minutos viram evolucao: quem joga aprende
            uso = minutos.get(p.id, PESO_RODAGEM)
            passo = (p.potential - p.overall) * VELOCIDADE_JOVEM * (0.55 + 0.45 * uso)
            ganho = max(1, int(round(passo))) if passo > 0.4 else 0
            if ganho:
                p.overall = min(p.potential, p.overall + ganho)
                contagem["evoluiram"] += 1
        elif idade > PICO:
            anos = idade - PICO
            perda = QUEDA_POR_ANO + QUEDA_ACELERA * (anos - 1)
            novo = max(35, int(round(p.overall - perda)))
            if novo < p.overall:
                p.overall = novo
                p.potential = p.overall
                contagem["cairam"] += 1

    for p in world.players.values():
        if p.id not in aposentados:
            p.market_value = _market_value(p.overall, p.potential, temporada - p.birth_year)

    for pid in aposentados:
        clube = world.players[pid].club_id
        if clube in world.clubs and pid in world.clubs[clube].player_ids:
            world.clubs[clube].player_ids.remove(pid)
        del world.players[pid]
    return contagem


def repor_elencos(world: World, rng: np.random.Generator, temporada: int,
                  alvos: dict[int, int] | None = None) -> int:
    """Gera garotos da base para os clubes que ficaram curtos.

    Sem isto o mundo esvazia: aposentadoria tira gente todo ano e ninguem entra. O garoto
    nasce fraco e com potencial proporcional a forca do clube -- base de clube grande
    entrega jogador melhor, que e como funciona.
    """
    from fm.generate import SQUAD_QUOTA, _make_player
    from fm.model import grupo_posicao

    novos = 0
    proximo = max(world.players, default=0) + 1
    # A forca que rege a base e a do elenco ATUAL, nao a projetada na criacao do mundo.
    # Com a projetada, quem decaiu continuaria revelando joia como nos bons tempos e a
    # hierarquia do mundo nunca mudaria de verdade.
    forca = {c.id: world.team_rating(c.id) for c in world.clubs.values() if c.player_ids}
    forca_do_topo = max(forca.values(), default=85.0)
    for clube in world.clubs.values():
        elenco = [world.players[i] for i in clube.player_ids if i in world.players]
        alvo = (alvos or {}).get(clube.id, ELENCO_MINIMO)
        faltam = int(np.clip(alvo, ELENCO_MINIMO, ELENCO_MAXIMO)) - len(elenco)
        if faltam <= 0:
            continue
        # repoe onde a quota esta mais vazia
        tem: dict[str, int] = {}
        for p in elenco:
            g = grupo_posicao(p.position_detail) or p.position
            tem[g] = tem.get(g, 0) + 1
        buracos = sorted(SQUAD_QUOTA, key=lambda g: tem.get(g, 0) - SQUAD_QUOTA[g])

        for k in range(faltam):
            grupo = buracos[k % len(buracos)]
            idade = int(rng.integers(*IDADE_DA_BASE))
            fator = float(rng.uniform(*POTENCIAL_DA_BASE))
            nivel = forca.get(clube.id, clube.designed_strength)
            if rng.random() < CHANCE_DE_JOIA * (nivel / forca_do_topo):
                fator *= float(rng.uniform(*JOIA_MULTIPLICADOR))
            potencial = int(np.clip(round(nivel * fator), 45, TETO_DA_BASE))
            overall = int(np.clip(round(potencial - rng.integers(10, 26)), 35, potencial))
            p = _make_player(proximo, rng, clube.country, temporada, overall, grupo,
                             idade, clube.id)
            p.potential = potencial
            world.players[proximo] = p
            clube.player_ids.append(proximo)
            proximo += 1
            novos += 1
    return novos
