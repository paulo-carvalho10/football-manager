"""Competicoes continentais: Champions, Libertadores e Intercontinental.

Os participantes sao FIXOS, como pedido -- mas nao como lista de nomes digitada a mao, e
sim como VAGAS POR LIGA. Dado o mundo, o campo e sempre o mesmo (por isso fixo), e no dia
em que existir carreira basta trocar "os N mais fortes da liga" por "os N primeiros da
tabela" para virar classificacao de verdade, sem mexer no resto.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fm.competition import Fixture, group_stage, knockout_tie, play_fixtures, round_robin
from fm.match import Mentality, Style
from fm.model import World
from fm.table import build_table

TORNEIOS_DIR = Path(__file__).resolve().parent.parent / "data" / "torneios"


@dataclass(slots=True)
class Torneio:
    id: str
    nome: str
    vagas: dict[str, int]
    convidados: list[dict]
    fases: list[dict]
    style: Style
    mentality: Mentality
    qualificados_de: list[str] = field(default_factory=list)


def carregar(nome: str) -> Torneio:
    caminho = TORNEIOS_DIR / f"{nome}.toml"
    if not caminho.exists():
        disponiveis = sorted(p.stem for p in TORNEIOS_DIR.glob("*.toml"))
        raise FileNotFoundError(f"torneio {nome!r} nao existe. Ha: {disponiveis}")
    with caminho.open("rb") as fh:
        cfg = tomllib.load(fh)
    e = cfg.get("estilo", {})
    m = cfg.get("mentalidade", {})
    return Torneio(
        id=cfg["id"], nome=cfg["nome"], vagas=cfg.get("vagas", {}),
        convidados=list(cfg.get("convidados", [])),
        fases=cfg.get("formato", {}).get("fases", []),
        style=Style(goals_base=float(e.get("gols_base", 1.28)),
                    home_adv=float(e.get("mando", 0.26))),
        mentality=Mentality(goals_mult=float(m.get("gols_mult", 1.0)),
                            compression=float(m.get("compressao", 0.0)),
                            home_mult=float(m.get("mando_mult", 1.0))),
        qualificados_de=list(cfg.get("qualificados_de", [])))


def classificacao(world: World, liga, style: Style,
                  rng: np.random.Generator) -> list[int]:
    """Tabela final da liga, SIMULADA. Devolve os clubes em ordem de classificacao."""
    from fm.season import play_league_season
    rep = play_league_season(world, liga.id, style, rng, track_condition=False)
    return [linha.club_id for linha in rep.table]


def clube_convidado(world: World, dados: dict) -> int:
    """Cria no mundo um clube que nao pertence a nenhuma liga importada.

    E para os participantes de paises cuja liga nao foi importada: nao ha tabela de onde
    classificar, entao eles entram FIXOS, com a forca declarada no arquivo do torneio.
    """
    for c in world.clubs.values():
        if c.name == dados["nome"]:
            return c.id
    from fm.generate import _build_squad
    from fm.model import Club
    from fm.pack import PackClub
    from fm.rng import Streams

    club_id = max(world.clubs, default=0) + 1
    forca = float(dados["forca"])
    clube = Club(id=club_id, name=dados["nome"], country=dados.get("pais", "???"),
                 league_id="", reputation=int(np.clip((forca - 45) * 2.6, 5, 99)),
                 designed_strength=forca, color_primary="#333333",
                 color_secondary="#dddddd")
    proximo = [max(world.players, default=0) + 1]
    _build_squad(world, clube, PackClub(nome=dados["nome"], forca=forca), forca,
                 Streams(hash(dados["nome"]) & 0xFFFF).get("convidado"), proximo,
                 dados.get("pais_jogadores", "BRA"), world.season_year)
    world.clubs[club_id] = clube
    return club_id


def participantes(world: World, torneio: Torneio,
                  tabelas: dict[str, list[int]] | None = None) -> list[int]:
    """Quem disputa o torneio.

    Duas origens, de proposito diferentes:

    - **Liga importada**: as N vagas vao para os N primeiros da CLASSIFICACAO daquela liga.
      Se ninguem simulou a temporada ainda, cai na forca desenhada como aproximacao, mas o
      caminho normal e a tabela.
    - **Liga nao importada**: nao ha tabela de onde classificar, entao o clube entra FIXO,
      declarado em [[convidados]] com nome e forca.
    """
    tabelas = tabelas or {}
    por_codigo = {lg.codigo: lg for lg in world.leagues.values() if lg.codigo}
    escolhidos: list[int] = []
    for liga_id, n in torneio.vagas.items():
        liga = por_codigo.get(liga_id) or world.leagues.get(liga_id)
        if liga is None:
            continue
        ordem = tabelas.get(liga_id) or tabelas.get(liga.id) or sorted(
            liga.club_ids, key=lambda cid: -world.clubs[cid].designed_strength)
        escolhidos += ordem[:n]
    for dados in torneio.convidados:
        escolhidos.append(clube_convidado(world, dados))
    return escolhidos


def _grupos_possiveis(n: int, pedido: int) -> int:
    """Maior numero de grupos <= pedido que divide n.

    O torneio tem de rodar com mundo PARCIAL: enquanto as ligas nao estao todas
    importadas, o campo vem incompleto e travar em "nao divide" nao ajuda ninguem.
    """
    for g in range(min(pedido, n // 2), 0, -1):
        if n % g == 0 and n // g >= 2:
            return g
    return 1


def _fase_grupos(world, clubes, fase, rng, style, mentality):
    g = _grupos_possiveis(len(clubes), int(fase.get("grupos", 8)))
    grupos = group_stage(clubes, g, legs=int(fase.get("voltas", 2)))
    avancam, passa = int(fase.get("avancam", 2)), []
    ratings = {cid: world.team_rating(cid) for cid in clubes}
    for fixtures in grupos:
        ids = sorted({f.home for f in fixtures} | {f.away for f in fixtures})
        resultados = play_fixtures(fixtures, ratings, rng, style, mentality)
        passa += [linha.club_id for linha in build_table(ids, resultados)[:avancam]]
    return passa


def _fase_mata_mata(world, clubes, fase, rng, style, mentality):
    """Roda `rodadas` rodadas de mata-mata. Sem isso ninguem pode entrar no meio.

    O padrao continua sendo "ate sobrar um", porque Champions e Libertadores acabam em
    campeao. Mas Copa do Brasil precisa parar depois de uma rodada para os clubes de
    Libertadores entrarem na terceira fase.
    """
    ratings = {cid: world.team_rating(cid) for cid in clubes}
    vivos = list(clubes)
    pedido = fase.get("rodadas", "todas")
    restantes = float("inf") if pedido == "todas" else int(pedido)
    visitante = bool(fase.get("visitante_avanca_empate", False))

    while len(vivos) > 1 and restantes > 0:
        if len(vivos) % 2:
            # numero impar: alguem passa sem jogar, e o sorteio decide QUEM.
            # Dar o bye ao mais forte inflava o favorito -- numa copa de campo reduzido o
            # Palmeiras subia para 40,8% dos titulos so por nunca jogar a rodada impar.
            vivos = list(vivos)
            rng.shuffle(vivos)
            bye, vivos = vivos[:1], vivos[1:]
        else:
            bye = []
        rng.shuffle(vivos)
        metade = len(vivos) // 2
        a, b = vivos[:metade], vivos[metade:]
        vencedores = knockout_tie(b, a, ratings, rng, style, mentality,
                                  legs=int(fase.get("maos", 2)),
                                  empate_favorece_visitante=visitante)
        vivos = [int(x) for x in vencedores] + bye
        restantes -= 1
    return vivos


def resolver_entradas(world: World, entradas: list[dict],
                      tabelas: dict[str, list[int]]) -> list[int]:
    """Clubes que entram NESTA fase, por posicao na tabela da liga de origem.

    `{ liga = "BRA1", de = 13, ate = 20 }` = do 13o ao 20o do Brasileirao. E assim que a
    Copa do Brasil pega a Serie A inteira em fases diferentes e que o pre-Libertadores pega
    quem ficou logo abaixo da zona de classificacao direta.
    """
    por_codigo = {lg.codigo: lg for lg in world.leagues.values() if lg.codigo}
    saida: list[int] = []
    for e in entradas:
        if "convidado" in e:
            saida.append(clube_convidado(world, e["convidado"]))
            continue
        chave = e["liga"]
        liga = por_codigo.get(chave) or world.leagues.get(chave)
        if liga is None:
            continue
        ordem = tabelas.get(chave) or tabelas.get(liga.id) or sorted(
            liga.club_ids, key=lambda cid: -world.clubs[cid].designed_strength)
        saida += ordem[int(e.get("de", 1)) - 1:int(e.get("ate", len(ordem)))]
    return saida


def simular(world: World, torneio: Torneio, rng: np.random.Generator,
            elenco: list[int] | None = None,
            tabelas: dict[str, list[int]] | None = None) -> list[int]:
    """Roda o torneio e devolve os sobreviventes, do campeao para baixo."""
    tabelas = tabelas or {}
    clubes = elenco if elenco is not None else participantes(world, torneio, tabelas)
    for fase in torneio.fases:
        # quem entra so nesta fase se junta a quem sobreviveu da anterior
        novos = resolver_entradas(world, fase.get("entram", []), tabelas)
        clubes = list(clubes) + [c for c in novos if c not in clubes]
        tipo = fase.get("tipo")
        if tipo == "groups":
            clubes = _fase_grupos(world, clubes, fase, rng, torneio.style,
                                  torneio.mentality)
        elif tipo == "knockout":
            clubes = _fase_mata_mata(world, clubes, fase, rng, torneio.style,
                                     torneio.mentality)
        elif tipo == "round_robin":
            ratings = {cid: world.team_rating(cid) for cid in clubes}
            fixtures: list[Fixture] = round_robin(clubes, legs=int(fase.get("voltas", 2)))
            resultados = play_fixtures(fixtures, ratings, rng, torneio.style,
                                       torneio.mentality)
            tabela = build_table(clubes, resultados)
            clubes = [linha.club_id for linha in tabela[:int(fase.get("avancam", 1))]]
        else:
            raise ValueError(f"fase desconhecida em {torneio.id}: {tipo!r}")
    return clubes


def disponiveis() -> list[str]:
    return sorted(p.stem for p in TORNEIOS_DIR.glob("*.toml"))
