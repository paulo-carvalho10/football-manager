"""As premiacoes do fim da temporada: Bola de Ouro e os premios de cada liga.

Tudo sai da MEDIA DAS NOTAS do ano (fm.estatisticas guarda a nota de cada jogo: a real na
partida do usuario, a estimada nos jogos do motor rapido) e dos cadernos de artilharia.
Nada e sorteado: o premio vai para quem jogou melhor, com um minimo de jogos para o reserva
de tres partidas brilhantes nao levar a Bola de Ouro.

A Bola de Ouro olha o ano inteiro (todas as competicoes) e soma um pouco pelos titulos,
como a de verdade; o premio de cada liga olha so a liga.

Efeito no mundo: moral. O valor de mercado e recalculado pelo overall na virada, entao um
bonus de valor sumiria no mesmo dia -- e o texto nao promete o que o jogo nao faz.
"""

from __future__ import annotations

from dataclasses import dataclass

from fm.model import World

MINIMO_DE_JOGOS = 0.45          # da quantidade de rodadas da liga
IDADE_DA_REVELACAO = 21
# a Bola de Ouro soma pelos titulos do clube (em pontos de media de nota)
BONUS_TITULO_DA_LIGA = 0.15
BONUS_TITULO_CONTINENTAL = 0.25
BONUS_OUTRA_COPA = 0.10
DESCONTO_DA_SEGUNDA_DIVISAO = 0.35
CONTINENTAIS = {"libertadores", "champions"}
MORAL = {"bola_de_ouro": 12, "craque": 8, "revelacao": 8, "outro": 5}
# a selecao do ano joga no 4-3-3
VAGAS_DA_SELECAO = {"GK": 1, "DF": 4, "MF": 3, "FW": 3}


@dataclass(slots=True)
class Candidato:
    jogador: int
    clube: int
    media: float
    jogos: int
    gols: int
    assistencias: int


def _candidatos(world: World, caderno, minimo: int, clubes: set[int] | None = None
                ) -> list[Candidato]:
    fora = []
    for linha in caderno.por_jogador.values():
        p = world.players.get(linha.jogador)
        if p is None or p.club_id not in world.clubs or linha.notas < minimo:
            continue
        if clubes is not None and p.club_id not in clubes:
            continue
        fora.append(Candidato(p.id, p.club_id, round(linha.media, 2), linha.notas,
                              linha.gols, linha.assistencias))
    return fora


def _melhor(cands: list[Candidato], chave) -> Candidato | None:
    return max(cands, key=lambda x: (chave(x), x.jogos, -x.jogador)) if cands else None


def _selecao(world: World, cands: list[Candidato]) -> list[int]:
    resta = dict(VAGAS_DA_SELECAO)
    escolhidos = []
    for x in sorted(cands, key=lambda x: (-x.media, -x.jogos, x.jogador)):
        setor = world.players[x.jogador].position
        if resta.get(setor, 0) > 0:
            resta[setor] -= 1
            escolhidos.append(x.jogador)
    ordem = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
    return sorted(escolhidos, key=lambda i: ordem.get(world.players[i].position, 9))


def calcular(world: World, temporada: int, caderno_do_ano, cadernos_das_ligas: dict,
             ligas: dict[str, dict], campeoes_das_ligas: dict[str, int],
             copas_ganhas: dict[int, list[str]], tecnico_do_ano: dict[str, int | None]
             ) -> dict:
    """`ligas`: {chave: {"nome", "tier", "clubes": set, "rodadas"}}. Devolve os premios em
    ids (a tela traduz), e os ids de quem ganhou algo com o tipo do premio."""
    rodadas_da_elite = max((d["rodadas"] for d in ligas.values() if d["tier"] == 1),
                           default=38)
    tier_do_clube = {k: d["tier"] for d in ligas.values() for k in d["clubes"]}

    # Bola de Ouro: o ano inteiro, com titulos e o peso da divisao
    def pontos(x: Candidato) -> float:
        extra = 0.0
        if x.clube in campeoes_das_ligas.values():
            extra += BONUS_TITULO_DA_LIGA
        for copa in copas_ganhas.get(x.clube, []):
            extra += BONUS_TITULO_CONTINENTAL if copa in CONTINENTAIS else BONUS_OUTRA_COPA
        if tier_do_clube.get(x.clube, 1) > 1:
            extra -= DESCONTO_DA_SEGUNDA_DIVISAO
        return x.media + extra

    todos = _candidatos(world, caderno_do_ano, int(rodadas_da_elite * MINIMO_DE_JOGOS))
    podio = sorted(todos, key=lambda x: (-pontos(x), -x.jogos, x.jogador))[:3]
    bola = [{**_item(world, x), "pontos": round(pontos(x), 2)} for x in podio]

    por_liga = {}
    for chave, d in ligas.items():
        caderno = cadernos_das_ligas.get(chave)
        if caderno is None:
            continue
        minimo = int(d["rodadas"] * MINIMO_DE_JOGOS)
        cands = _candidatos(world, caderno, minimo, d["clubes"])
        todos_da_liga = _candidatos(world, caderno, 1, d["clubes"])
        craque = _melhor(cands, lambda x: x.media)
        goleiro = _melhor([x for x in cands if world.players[x.jogador].position == "GK"],
                          lambda x: x.media)
        revelacao = _melhor([x for x in cands
                             if world.players[x.jogador].age(temporada) <= IDADE_DA_REVELACAO],
                            lambda x: x.media)
        artilheiro = _melhor([x for x in todos_da_liga if x.gols], lambda x: (x.gols, -x.jogos))
        garcom = _melhor([x for x in todos_da_liga if x.assistencias],
                         lambda x: (x.assistencias, -x.jogos))
        por_liga[chave] = {
            "nome": d["nome"],
            "craque": _item(world, craque), "goleiro": _item(world, goleiro),
            "revelacao": _item(world, revelacao), "artilheiro": _item(world, artilheiro),
            "garcom": _item(world, garcom),
            "selecao": [_item(world, next(x for x in cands if x.jogador == pid))
                        for pid in _selecao(world, cands)],
            "tecnico": tecnico_do_ano.get(chave),
        }
    return {"temporada": temporada, "bola_de_ouro": bola, "ligas": por_liga}


def _item(world: World, x: Candidato | None) -> dict | None:
    """O premio guarda nome, clube e posicao DO DIA: na mesma virada o jogador pode se
    aposentar ou mudar de clube, e o premio continua sendo daquele ano."""
    if x is None:
        return None
    p = world.players[x.jogador]
    return {"jogador": x.jogador, "nome": p.name, "posicao": p.position,
            "idade": p.age(world.season_year), "clube": x.clube,
            "clube_nome": world.clubs[x.clube].name, "media": x.media, "jogos": x.jogos,
            "gols": x.gols, "assistencias": x.assistencias}


def aplicar_moral(world: World, premios: dict) -> None:
    """Premio levanta a moral de quem ganhou (uma vez por jogador, o maior premio)."""
    ganho: dict[int, int] = {}
    if premios["bola_de_ouro"]:
        ganho[premios["bola_de_ouro"][0]["jogador"]] = MORAL["bola_de_ouro"]
    for liga in premios["ligas"].values():
        for chave in ("craque", "goleiro", "revelacao", "artilheiro", "garcom"):
            if liga[chave]:
                valor = MORAL.get(chave, MORAL["outro"])
                pid = liga[chave]["jogador"]
                ganho[pid] = max(ganho.get(pid, 0), valor)
        for x in liga["selecao"]:
            ganho[x["jogador"]] = max(ganho.get(x["jogador"], 0), MORAL["outro"])
    for pid, v in ganho.items():
        p = world.players.get(pid)
        if p is not None:
            p.morale = min(100, p.morale + v)
