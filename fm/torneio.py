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

from fm.competition import (
    Fixture,
    group_stage,
    knockout_tie,
    liga_suica,
    play_fixtures,
    round_robin,
)
from fm.match import Mentality, Style
from fm.model import World
from fm.table import build_table

TORNEIOS_DIR = Path(__file__).resolve().parent.parent / "data" / "torneios"


@dataclass(slots=True)
class Torneio:
    id: str
    nome: str
    vagas: dict[str, int]
    classificacao_regras: list[dict]
    convidados: list[dict]
    fases: list[dict]
    style: Style
    mentality: Mentality
    qualificados_de: list[str] = field(default_factory=list)
    # datas a mais na agenda da carreira, para fases que esperam outro torneio (aguarda)
    folga_de_datas: int = 0


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
        classificacao_regras=list(cfg.get("classificacao", [])),
        convidados=list(cfg.get("convidados", [])),
        fases=cfg.get("formato", {}).get("fases", []),
        style=Style(goals_base=float(e.get("gols_base", 1.28)),
                    home_adv=float(e.get("mando", 0.26))),
        mentality=Mentality(goals_mult=float(m.get("gols_mult", 1.0)),
                            compression=float(m.get("compressao", 0.0)),
                            home_mult=float(m.get("mando_mult", 1.0))),
        qualificados_de=list(cfg.get("qualificados_de", [])),
        folga_de_datas=int(cfg.get("folga_de_datas", 0)))


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
    # o elenco sai do NOME, por um fluxo estavel. Era `hash(nome)`, e o hash de texto do
    # Python muda a cada processo: o Bolivar ganhava outro elenco toda vez que o jogo
    # abria, e o save carregado divergia do jogado a partir da primeira virada do ano
    _build_squad(world, clube, PackClub(nome=dados["nome"], forca=forca), forca,
                 Streams(0).get("convidado", dados["nome"]), proximo,
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
        # pontos corridos exige numero PAR de clubes por grupo
        if n % g == 0 and n // g >= 2 and (n // g) % 2 == 0:
            return g
    return 0


def _fase_grupos(world, clubes, fase, rng, style, mentality, exportados=None):
    clubes = list(clubes)
    g = _grupos_possiveis(len(clubes), int(fase.get("grupos", 8)))
    if g == 0 and len(clubes) > 2:
        # nao ha divisao valida: o mais fraco fica de fora e tenta de novo
        clubes = sorted(clubes, key=lambda c: -world.clubs[c].designed_strength)[:-1]
        g = _grupos_possiveis(len(clubes), int(fase.get("grupos", 8)))
    if g == 0:
        return clubes
    grupos = group_stage(clubes, g, legs=int(fase.get("voltas", 2)))
    avancam, passa = int(fase.get("avancam", 2)), []
    ratings = {cid: world.team_rating(cid) for cid in clubes}
    for fixtures in grupos:
        ids = sorted({f.home for f in fixtures} | {f.away for f in fixtures})
        tabela = build_table(ids, play_fixtures(fixtures, ratings, rng, style, mentality))
        passa += [linha.club_id for linha in tabela[:avancam]]
        # o 3o de cada grupo da Libertadores cai para a Sudamericana: e daqui que ele sai
        for regra in fase.get("exporta", []):
            pos = int(regra.get("posicao", 0))
            if pos and pos <= len(tabela) and exportados is not None:
                exportados.setdefault(regra["para"], []).append(tabela[pos - 1].club_id)
    return passa


def _fase_mata_mata(world, clubes, fase, rng, style, mentality, exportados=None):
    """Roda `rodadas` rodadas de mata-mata. Sem isso ninguem pode entrar no meio.

    O padrao continua sendo "ate sobrar um", porque Champions e Libertadores acabam em
    campeao. Mas Copa do Brasil precisa parar depois de uma rodada para os clubes de
    Libertadores entrarem na terceira fase.
    """
    ratings = {cid: world.team_rating(cid) for cid in clubes}
    # `isentos`: os N primeiros da ordem de entrada pulam esta fase e voltam depois.
    # E como o 1o ao 8o da fase de liga da Champions vao direto as oitavas.
    isentos = int(fase.get("isentos", 0))
    poupados, clubes = list(clubes[:isentos]), list(clubes[isentos:])
    vivos, perdedores = list(clubes), []
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
        perdedores = [int(x) for x in (np.array(a) + np.array(b) - vencedores)]
        # quem perde a pre da Champions entra na Europa League: e daqui que ele sai
        for regra in fase.get("exporta", []):
            if regra.get("eliminados") and exportados is not None:
                exportados.setdefault(regra["para"], []).extend(perdedores)
        vivos = [int(x) for x in vencedores] + bye
        restantes -= 1
    if len(vivos) == 1 and perdedores and not poupados:
        # o ultimo eliminado e o vice: fontes de classificacao precisam dele
        vivos = vivos + [perdedores[-1]]
    return poupados + vivos


def _fase_liga_suica(world, clubes, fase, rng, style, mentality):
    """Tabela unica com calendario parcial. Devolve os `avancam` primeiros, em ordem."""
    clubes = list(clubes)
    if len(clubes) % 2:
        clubes = sorted(clubes, key=lambda c: -world.clubs[c].designed_strength)[:-1]
    # os potes sao por forca, como na vida real
    clubes = sorted(clubes, key=lambda c: -world.clubs[c].designed_strength)
    advs = min(int(fase.get("adversarios", 8)), len(clubes) - 1)
    advs -= advs % 2
    if len(clubes) < 4 or advs < 2:
        # campo pequeno demais para calendario parcial: joga todo mundo contra todo mundo.
        # Acontece com mundo parcial, enquanto as ligas nao estao todas importadas.
        if len(clubes) < 2:
            return clubes
        fixtures = round_robin(clubes, legs=1)
    elif advs >= len(clubes) - 1:
        fixtures = round_robin(clubes, legs=1)
    else:
        fixtures = liga_suica(clubes, adversarios=advs, potes=int(fase.get("potes", 4)))
    ratings = {cid: world.team_rating(cid) for cid in clubes}
    resultados = play_fixtures(fixtures, ratings, rng, style, mentality)
    tabela = build_table(clubes, resultados)
    return [linha.club_id for linha in tabela[:int(fase.get("avancam", len(clubes)))]]


def resolver_entradas(world: World, entradas: list[dict],
                      tabelas: dict[str, list[int]],
                      classificados: dict[str, list[int]] | None = None) -> list[int]:
    """Clubes que entram NESTA fase, por posicao na tabela da liga de origem.

    `{ liga = "BRA1", de = 13, ate = 20 }` = do 13o ao 20o do Brasileirao. E assim que a
    Copa do Brasil pega a Serie A inteira em fases diferentes e que o pre-Libertadores pega
    quem ficou logo abaixo da zona de classificacao direta.
    """
    por_codigo = {lg.codigo: lg for lg in world.leagues.values() if lg.codigo}
    saida: list[int] = []
    for e in entradas:
        if "classificacao" in e:
            saida += (classificados or {}).get(e["classificacao"], [])
            continue
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
            tabelas: dict[str, list[int]] | None = None,
            copas: dict[str, list[int]] | None = None,
            exportados: dict[str, list[int]] | None = None,
            ocupados: set[int] | None = None) -> list[int]:
    """Roda o torneio e devolve [campeao, vice]."""
    tabelas = tabelas or {}
    classificados = (resolver_classificacao(world, torneio, tabelas, copas, ocupados)
                     if torneio.classificacao_regras or torneio.convidados else {})
    if elenco is not None:
        clubes = elenco
    elif classificados:
        clubes = []
    else:
        clubes = participantes(world, torneio, tabelas)
    for fase in torneio.fases:
        # quem entra so nesta fase se junta a quem sobreviveu da anterior
        novos = resolver_entradas(world, fase.get("entram", []), tabelas, classificados)
        clubes = list(clubes) + [c for c in novos if c not in clubes]
        tipo = fase.get("tipo")
        if tipo == "groups":
            clubes = _fase_grupos(world, clubes, fase, rng, torneio.style,
                                  torneio.mentality)
        elif tipo == "knockout":
            clubes = _fase_mata_mata(world, clubes, fase, rng, torneio.style,
                                     torneio.mentality, exportados)
        elif tipo == "liga_suica":
            clubes = _fase_liga_suica(world, clubes, fase, rng, torneio.style,
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


def resolver_classificacao(
    world: World, torneio: Torneio, tabelas: dict[str, list[int]],
    copas: dict[str, list[int]] | None = None,
    ocupados: set[int] | None = None,
) -> dict[str, list[int]]:
    """Distribui as vagas por ordem de prioridade, com CASCATA.

    Cada regra pede N vagas de uma fonte ordenada (tabela de liga ou copa) e leva os N
    primeiros que AINDA NAO se classificaram. A cascata cai fora disso de graca: se o
    campeao da Copa do Brasil ja e o 2o do Brasileirao, a regra do Brasileirao pula ele e
    desce -- entao a vaga direta chega ao 5o e a da pre-Libertadores passa do 5o para o 6o.
    E exatamente o que acontece na vida real.
    """
    copas = copas or {}
    # `ocupados` e COMPARTILHADO entre os torneios da temporada: quem pegou vaga na
    # Champions sai da lista da Europa. Sem isso o Real Madrid disputava as duas.
    ja: set[int] = ocupados if ocupados is not None else set()
    saida: dict[str, list[int]] = {}
    for regra in torneio.classificacao_regras:
        # `reservas` = fontes alternativas, na ordem: vale a primeira que tiver clubes. E o
        # caso do campeao da Libertadores no primeiro ano da carreira: ainda nao existe, e a
        # vaga vai para o clube mais forte do continente em vez de sumir
        ordem = []
        for fonte in [regra["fonte"], *regra.get("reservas", [])]:
            ordem = (copas.get(fonte) or tabelas.get(fonte)
                     or tabelas.get(_liga_por_codigo(world, fonte)))
            if ordem:
                break
        if not ordem:
            continue
        destino = regra.get("entra_em", "grupos")
        levados = []
        for cid in ordem:
            if len(levados) >= int(regra.get("vagas", 1)):
                break
            if cid not in ja:
                ja.add(cid)
                levados.append(cid)
        saida.setdefault(destino, []).extend(levados)
    for dados in torneio.convidados:
        cid = clube_convidado(world, dados)
        if cid not in ja:
            ja.add(cid)
            saida.setdefault(dados.get("entra_em", "grupos"), []).append(cid)
    return saida


def _liga_por_codigo(world: World, codigo: str) -> str:
    for lg in world.leagues.values():
        if lg.codigo == codigo:
            return lg.id
    return codigo
