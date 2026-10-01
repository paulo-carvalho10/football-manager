"""Um torneio em ANDAMENTO dentro da carreira, jogado etapa por etapa.

`fm/torneio.py` resolve uma competicao inteira de uma vez -- e o certo para responder
"quem ganharia a Libertadores neste mundo". Mas a carreira e rodada a rodada: o clube do
usuario joga quarta pela copa e domingo pela liga, e a decisao de poupar um titular na
quarta so existe se as duas coisas estiverem na mesma linha do tempo.

Este modulo quebra o torneio em ETAPAS. Uma etapa e uma rodada de grupos, uma rodada de
liga suica ou um confronto de mata-mata (ida e volta juntos, que e como se conta na
tabela: "as oitavas"). A cada etapa a carreira pergunta quais jogos existem, joga o do
usuario em detalhe e resolve o resto no motor rapido.

O formato continua vindo dos mesmos arquivos de data/torneios. Nada de regra foi
duplicado: o que muda e quem controla o relogio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fm.competition import Fixture, Result, group_stage, liga_suica, round_robin
from fm.model import World
from fm.table import build_table
from fm.torneio import Torneio, resolver_classificacao, resolver_entradas

# Quantas etapas cada tipo de fase ocupa no calendario, quando nao da para saber antes.
ETAPAS_DE_MATA_MATA = {"todas": 4}


@dataclass(slots=True)
class Etapa:
    """Um compromisso do torneio: os jogos que acontecem numa data."""
    torneio: str
    nome: str
    fixtures: list[Fixture]
    fase: int
    rodada_da_fase: int


@dataclass(slots=True)
class Andamento:
    """O torneio do comeco ao fim, com o relogio por fora."""
    torneio: Torneio
    vivos: list[int]
    classificados: dict[str, list[int]] = field(default_factory=dict)
    fase: int = 0
    rodada_da_fase: int = 0
    pendentes: list[list[Fixture]] = field(default_factory=list)
    resultados: list[Result] = field(default_factory=list)
    grupos: list[list[int]] = field(default_factory=list)
    campeao: int | None = None
    vice: int | None = None
    eliminados_na_fase: list[int] = field(default_factory=list)
    # todos os resultados da competicao, nao so os da fase em curso: e por eles que as
    # financas sabem quantos jogos cada clube fez alem da liga
    resultados_do_ano: list[Result] = field(default_factory=list)
    # o chaveamento do mata-mata em curso: quem enfrenta quem, e quem passou sem jogar
    pares: list[tuple[int, int]] = field(default_factory=list)
    poupados: list[int] = field(default_factory=list)
    # quem ja entrou no torneio alguma vez. Sem isto, uma fase de mata-mata que repete
    # readmite os entrantes dela a cada rodada: os 12 primeiros da Serie A voltavam para a
    # Copa do Brasil depois de eliminados e o torneio nunca terminava.
    ja_entraram: set[int] = field(default_factory=set)
    rodadas_da_fase_feitas: int = 0
    # quantas etapas cada clube sobreviveu. E por aqui que a premiacao sabe ate onde cada
    # um chegou -- cair nas oitavas tem de pagar mais que cair na primeira fase.
    etapas_vividas: dict[int, int] = field(default_factory=dict)
    etapas_totais: int = 0
    # as fases ja encerradas, como ficaram: os grupos com os jogos, a fase de liga, cada
    # rodada do mata-mata com os pares. O resto do Andamento so guarda a fase em curso --
    # sem isto a tela nao tinha como mostrar os grupos depois que o mata-mata comecava.
    historico: list[dict] = field(default_factory=list)
    # as disputas de penaltis da rodada de mata-mata em curso, por par (mandante da ida,
    # visitante): a do usuario vem pronta da carreira (acompanhada cobranca a cobranca);
    # as outras sao simuladas na apuracao
    disputas: dict = field(default_factory=dict)
    # A campanha de cada clube na fase de grupos (ou de liga): grupo, posicao, pontos,
    # saldo, gols e se e cabeca de chave no mata-mata. E por ela que a chave e sorteada
    # (1o de grupo contra 2o) e que a melhor campanha decide em casa.
    campanha: dict[int, dict] = field(default_factory=dict)
    # A chave fixa do mata-mata, como na Conmebol: um sorteio so nas oitavas e o caminho
    # ate a final fica decidido -- o vencedor do confronto 1 pega o do 2, e assim por
    # diante. `chave` e a ordem das oitavas; vazia enquanto nao houve sorteio.
    chave: list[int] = field(default_factory=list)

    @property
    def acabou(self) -> bool:
        return self.fase >= len(self.torneio.fases) and not self.pendentes

    @property
    def nome_da_fase(self) -> str:
        if self.fase < len(self.torneio.fases):
            return self.torneio.fases[self.fase].get("nome", f"fase {self.fase + 1}")
        return "encerrado"

    def esta_vivo(self, clube: int) -> bool:
        return clube in self.vivos


def comecar(world: World, torneio: Torneio, tabelas: dict[str, list[int]],
            copas: dict[str, list[int]] | None = None,
            ocupados: set[int] | None = None) -> Andamento:
    """Resolve quem disputa e deixa o torneio parado na primeira fase."""
    from fm.torneio import participantes

    classificados = (resolver_classificacao(world, torneio, tabelas, copas, ocupados)
                     if torneio.classificacao_regras or torneio.convidados else {})
    vivos = [] if classificados else participantes(world, torneio, tabelas)
    return Andamento(torneio=torneio, vivos=list(vivos), classificados=classificados)


def chave_de_exportacao(andamento: Andamento, regra: dict) -> str:
    """`torneio:para`, a mesma grafia das regras (`fonte = "libertadores:terceiros"`).

    REGRESSAO: a chave era so `para`, e a Champions e a Libertadores exportam as duas para
    "eliminados_pre". Com o mundo inteiro na carreira, o eliminado da pre-Libertadores ia
    parar na Liga Europa e o da pre-Champions na Sul-Americana."""
    return f"{andamento.torneio.id}:{regra['para']}"


def _entrantes(world: World, andamento: Andamento, fase: dict,
               tabelas: dict[str, list[int]]) -> list[int]:
    novos = resolver_entradas(world, fase.get("entram", []), tabelas,
                              andamento.classificados)
    entram = [c for c in novos
              if c not in andamento.vivos and c not in andamento.ja_entraram]
    andamento.ja_entraram.update(entram)
    andamento.ja_entraram.update(andamento.vivos)
    return entram


def _rodadas_de(fixtures: list[Fixture]) -> list[list[Fixture]]:
    """Agrupa por matchday, preservando a ordem."""
    por_rodada: dict[int, list[Fixture]] = {}
    for f in fixtures:
        por_rodada.setdefault(f.matchday, []).append(f)
    return [por_rodada[k] for k in sorted(por_rodada)]


def _montar_fase(world: World, andamento: Andamento, rng: np.random.Generator,
                 tabelas: dict[str, list[int]]) -> None:
    """Prepara os jogos da fase atual sem jogar nenhum."""
    fase = andamento.torneio.fases[andamento.fase]
    andamento.vivos += _entrantes(world, andamento, fase, tabelas)
    andamento.resultados = []
    andamento.grupos = []
    andamento.rodada_da_fase = 0
    tipo = fase.get("tipo")

    if tipo == "groups":
        from fm.torneio import _grupos_possiveis
        clubes = list(andamento.vivos)
        g = _grupos_possiveis(len(clubes), int(fase.get("grupos", 8)))
        if g == 0 and len(clubes) > 2:
            clubes = sorted(clubes, key=lambda c: -world.clubs[c].designed_strength)[:-1]
            g = _grupos_possiveis(len(clubes), int(fase.get("grupos", 8)))
        if g == 0:
            andamento.pendentes = []
            return
        if fase.get("potes"):
            clubes = _sortear_potes(world, clubes, g, rng)
        grupos = group_stage(clubes, g, legs=int(fase.get("voltas", 2)))
        andamento.grupos = [sorted({f.home for f in gr} | {f.away for f in gr})
                            for gr in grupos]
        andamento.vivos = [c for gr in andamento.grupos for c in gr]
        todos = [f for gr in grupos for f in gr]
        andamento.pendentes = _rodadas_de(todos)

    elif tipo == "liga_suica":
        clubes = list(andamento.vivos)
        if len(clubes) % 2:
            clubes = sorted(clubes, key=lambda c: -world.clubs[c].designed_strength)[:-1]
        clubes = sorted(clubes, key=lambda c: -world.clubs[c].designed_strength)
        advs = min(int(fase.get("adversarios", 8)), len(clubes) - 1)
        advs -= advs % 2
        if len(clubes) < 4 or advs < 2 or advs >= len(clubes) - 1:
            fixtures = round_robin(clubes, legs=1) if len(clubes) >= 2 else []
        else:
            fixtures = liga_suica(clubes, adversarios=advs, potes=int(fase.get("potes", 4)))
        andamento.vivos = clubes
        andamento.pendentes = _rodadas_de(fixtures)

    elif tipo == "round_robin":
        fixtures = round_robin(list(andamento.vivos), legs=int(fase.get("voltas", 2)))
        andamento.pendentes = _rodadas_de(fixtures)

    elif tipo == "knockout":
        andamento.pendentes = _sortear_confronto(andamento, fase, rng)
    else:
        raise ValueError(f"fase desconhecida em {andamento.torneio.id}: {tipo!r}")


def _sortear_potes(world: World, clubes: list[int], grupos: int,
                   rng: np.random.Generator) -> list[int]:
    """O sorteio dos grupos como o da Conmebol: os clubes vao para potes pelo ranking (aqui,
    a reputacao), cada grupo leva um de cada pote, e dois do mesmo pais nao caem juntos
    quando da para evitar.

    REGRESSAO: a lista chegava aqui fora de ordem e a serpentina de `group_stage` -- que
    supoe a lista ordenada por forca -- virava um sorteio puro. Palmeiras, Flamengo e
    Cruzeiro podiam cair no mesmo grupo, outro grupo ficava sem ninguem, e um azarao
    peruano chegava a final com frequencia muito acima da do elenco dele.

    Devolve a lista na ordem que `group_stage` espera: linha r (o pote) na serpentina.
    """
    ordem = sorted(clubes, key=lambda c: (-world.clubs[c].reputation,
                                          -world.clubs[c].designed_strength, c))
    potes = [ordem[i:i + grupos] for i in range(0, len(ordem), grupos)]
    pais = {c: world.clubs[c].country for c in clubes}
    melhor, choques_do_melhor = None, None
    for _ in range(200):
        montagem = [[] for _ in range(grupos)]
        for pote in potes:
            membros = [int(x) for x in rng.permutation(pote)]
            for gi, c in enumerate(membros):
                montagem[gi].append(c)
        choques = sum(len(g) - len({pais[c] for c in g}) for g in montagem)
        if choques_do_melhor is None or choques < choques_do_melhor:
            melhor, choques_do_melhor = montagem, choques
        if choques == 0:
            break
    # a serpentina de group_stage manda a linha impar ao contrario: compensa aqui
    saida = []
    for r in range(len(potes)):
        linha = [melhor[gi][r] if r < len(melhor[gi]) else None for gi in range(grupos)]
        if r % 2:
            linha = linha[::-1]
        saida += [c for c in linha if c is not None]
    return saida


def _campanha(andamento: Andamento, c: int) -> tuple:
    """A chave de ordenacao da campanha: melhor primeiro."""
    x = andamento.campanha.get(c)
    if not x:
        return (1, 0, 0, 0, 0)
    return (0 if x.get("cabeca") else 1, x.get("pos", 99), -x.get("pts", 0),
            -x.get("sg", 0), -x.get("gp", 0))


def _confronto_da_chave(andamento: Andamento, fase: dict,
                        rng: np.random.Generator) -> list[list[Fixture]]:
    """A rodada do mata-mata na chave fixa. Na primeira, o sorteio: cada cabeca de chave
    (1o de grupo) pega um nao-cabeca de OUTRO grupo. Dai em diante nao ha sorteio: os
    vencedores seguem na ordem da chave. A volta e na casa de quem fez a melhor campanha."""
    vivos = list(andamento.vivos)
    if not andamento.chave:
        cabecas = [c for c in vivos if (andamento.campanha.get(c) or {}).get("cabeca")]
        outros = [c for c in vivos if c not in cabecas]
        if len(cabecas) != len(outros):
            # sem campanha (ou ela nao divide em duas metades): a metade de cima e cabeca
            ordem = sorted(vivos, key=lambda c: _campanha(andamento, c))
            cabecas, outros = ordem[:len(ordem) // 2], ordem[len(ordem) // 2:]
        cabecas = [int(x) for x in rng.permutation(cabecas)]
        restam = [int(x) for x in rng.permutation(outros)]
        chave: list[int] = []
        for cab in cabecas:
            grupo = (andamento.campanha.get(cab) or {}).get("grupo", -1)
            rival = next((o for o in restam if grupo < 0
                          or (andamento.campanha.get(o) or {}).get("grupo", -2) != grupo),
                         restam[0])
            restam.remove(rival)
            chave += [rival, cab]
        andamento.chave = chave
        vivos = chave
    if len(vivos) % 2:
        return []
    maos = int(fase.get("maos", 2))
    pares = []
    for i in range(0, len(vivos), 2):
        x, y = vivos[i], vivos[i + 1]
        # (mandante da ida, mandante da volta): a melhor campanha decide em casa
        melhor, pior = sorted((x, y), key=lambda c: _campanha(andamento, c))
        pares.append((pior, melhor))
    andamento.vivos = list(vivos)
    andamento.pares = pares
    andamento.poupados = []
    ida = [Fixture(home=a, away=b, matchday=1) for a, b in pares]
    if maos == 2:
        return [ida, [Fixture(home=b, away=a, matchday=2) for a, b in pares]]
    return [ida]


def _sortear_confronto(andamento: Andamento, fase: dict,
                       rng: np.random.Generator) -> list[list[Fixture]]:
    """Uma rodada de mata-mata: sorteia os pares e devolve ida (e volta) como UMA etapa.

    O bye vai ao sorteio, nunca ao mais forte. Dar o bye ao maior inflava o favorito da
    Copa do Brasil de 12,6% para 40,8% dos titulos so por ele nunca jogar a rodada impar.

    Fase com `chave = "fixa"` (e tudo depois dela) segue a chave: fm.copa._confronto_da_chave.
    """
    if fase.get("chave") == "fixa" or andamento.chave:
        return _confronto_da_chave(andamento, fase, rng)
    isentos = int(fase.get("isentos", 0))
    poupados, disputam = andamento.vivos[:isentos], list(andamento.vivos[isentos:])
    if len(disputam) < 2:
        andamento.vivos = poupados + disputam
        andamento.pares, andamento.poupados = [], []   # senao a rodada anterior "repetia"
        return []

    if len(disputam) % 2:
        rng.shuffle(disputam)
        bye, disputam = disputam[:1], disputam[1:]
    else:
        bye = []
    rng.shuffle(disputam)
    metade = len(disputam) // 2
    a, b = disputam[:metade], disputam[metade:]

    maos = int(fase.get("maos", 2))
    ida = [Fixture(home=int(x), away=int(y), matchday=1) for x, y in zip(b, a, strict=True)]
    andamento.vivos = poupados + bye + [int(x) for x in a] + [int(x) for x in b]
    andamento.pares = [(int(x), int(y)) for x, y in zip(b, a, strict=True)]
    andamento.poupados = list(poupados) + [int(x) for x in bye]
    if maos == 2:
        # ida e volta em DATAS diferentes: entre uma e outra o treinador ve o placar da
        # ida, mexe no time, e o suspenso da ida cumpre o gancho na volta. Eram uma etapa
        # so, e a volta era jogada no motor rapido junto com a ida.
        volta = [Fixture(home=int(y), away=int(x), matchday=2)
                 for x, y in zip(b, a, strict=True)]
        return [ida, volta]
    return [ida]


def proxima_etapa(world: World, andamento: Andamento, rng: np.random.Generator,
                  tabelas: dict[str, list[int]]) -> Etapa | None:
    """Os jogos do proximo compromisso, ou None se o torneio acabou."""
    while not andamento.pendentes:
        if andamento.fase >= len(andamento.torneio.fases):
            return None
        _montar_fase(world, andamento, rng, tabelas)
        if not andamento.pendentes:
            _encerrar_fase(world, andamento, rng)
            if andamento.acabou:
                return None
    return Etapa(torneio=andamento.torneio.id, nome=andamento.nome_da_fase,
                 fixtures=list(andamento.pendentes[0]), fase=andamento.fase,
                 rodada_da_fase=andamento.rodada_da_fase)


def registrar(world: World, andamento: Andamento, resultados: list[Result],
              rng: np.random.Generator,
              exportados: dict[str, list[int]] | None = None) -> None:
    """Aplica os resultados da etapa e avanca a fase quando ela termina."""
    andamento.resultados += resultados
    andamento.resultados_do_ano += resultados
    andamento.etapas_totais += 1
    for cid in andamento.vivos:
        andamento.etapas_vividas[cid] = andamento.etapas_totais
    andamento.pendentes.pop(0)
    andamento.rodada_da_fase += 1
    if not andamento.pendentes:
        _encerrar_fase(world, andamento, rng, exportados)


def _encerrar_fase(world: World, andamento: Andamento, rng: np.random.Generator,
                   exportados: dict[str, list[int]] | None = None) -> None:
    """Apura a fase e decide se ela repete ou se o torneio anda.

    Mata-mata e o unico tipo que pode repetir: `rodadas = "todas"` quer dizer "ate sobrar
    um", e cada repeticao e uma nova etapa no calendario.
    """
    if andamento.fase >= len(andamento.torneio.fases):
        return
    fase = andamento.torneio.fases[andamento.fase]
    tipo = fase.get("tipo")
    andamento.pendentes = []
    if tipo == "knockout":
        # apura ANTES da foto: e na apuracao que saem as disputas de penaltis, e o
        # chaveamento mostra o placar delas
        _apurar_mata_mata(andamento, fase, exportados, world, rng)
    registro = foto_da_fase(andamento)
    if registro is not None:
        andamento.historico.append(registro)
    andamento.disputas = {}

    if tipo == "groups" and andamento.grupos:
        avancam, passa = int(fase.get("avancam", 2)), []
        for gi, ids in enumerate(andamento.grupos):
            do_grupo = [r for r in andamento.resultados
                        if r.home in ids and r.away in ids]
            tabela = build_table(ids, do_grupo)
            passa += [linha.club_id for linha in tabela[:avancam]]
            for pos, linha in enumerate(tabela, 1):
                andamento.campanha[linha.club_id] = {
                    "grupo": gi, "pos": pos, "pts": linha.points,
                    "sg": linha.goals_for - linha.goals_against, "gp": linha.goals_for,
                    "cabeca": pos == 1}
            for regra in fase.get("exporta", []):
                pos = int(regra.get("posicao", 0))
                if pos and pos <= len(tabela) and exportados is not None:
                    exportados.setdefault(chave_de_exportacao(andamento, regra),
                                          []).append(tabela[pos - 1].club_id)
        andamento.eliminados_na_fase = [c for c in andamento.vivos if c not in passa]
        andamento.vivos = passa

    elif tipo in ("liga_suica", "round_robin"):
        tabela = build_table(andamento.vivos, andamento.resultados)
        n = int(fase.get("avancam", len(andamento.vivos)))
        passa = [linha.club_id for linha in tabela[:n]]
        # cabeca de chave: quem vai direto ao mata-mata (os isentos do playoff seguinte)
        seguinte = (andamento.torneio.fases[andamento.fase + 1]
                    if andamento.fase + 1 < len(andamento.torneio.fases) else {})
        direto = int(seguinte.get("isentos", n // 2))
        for pos, linha in enumerate(tabela, 1):
            andamento.campanha[linha.club_id] = {
                "grupo": -1, "pos": pos, "pts": linha.points,
                "sg": linha.goals_for - linha.goals_against, "gp": linha.goals_for,
                "cabeca": pos <= direto}
        andamento.eliminados_na_fase = [c for c in andamento.vivos if c not in passa]
        andamento.vivos = passa

    elif tipo == "knockout":
        andamento.rodadas_da_fase_feitas += 1
        pedido = fase.get("rodadas", "todas")
        repete = (len(andamento.vivos) > 1 if pedido == "todas"
                  else andamento.rodadas_da_fase_feitas < int(pedido))
        if repete:
            return          # mesma fase, proxima rodada -- o calendario ganha outra data

    andamento.fase += 1
    andamento.rodada_da_fase = 0
    andamento.rodadas_da_fase_feitas = 0
    if andamento.fase >= len(andamento.torneio.fases) and andamento.vivos:
        andamento.campeao = andamento.vivos[0]
        if andamento.vice is None:
            if len(andamento.vivos) > 1:
                andamento.vice = andamento.vivos[1]
            elif andamento.eliminados_na_fase:
                andamento.vice = andamento.eliminados_na_fase[-1]


def foto_da_fase(andamento: Andamento) -> dict | None:
    """A fase em curso como ela esta agora: o que a tela desenha e o que o historico
    guarda quando a fase acaba. Resultados parciais valem (a fase pode estar no meio)."""
    if andamento.fase >= len(andamento.torneio.fases):
        return None
    fase = andamento.torneio.fases[andamento.fase]
    tipo = fase.get("tipo")
    nome = fase.get("nome", f"fase {andamento.fase + 1}")
    resultados = list(andamento.resultados)
    if tipo == "groups":
        if not andamento.grupos:
            return None
        return {"tipo": "grupos", "nome": nome, "fase": andamento.fase,
                "grupos": [list(g) for g in andamento.grupos],
                "resultados": resultados, "avancam": int(fase.get("avancam", 2))}
    if tipo in ("liga_suica", "round_robin"):
        return {"tipo": "liga", "nome": nome, "fase": andamento.fase,
                "clubes": list(andamento.vivos),
                "resultados": resultados,
                "avancam": int(fase.get("avancam", len(andamento.vivos)))}
    if tipo == "knockout":
        if not andamento.pares:
            return None
        rodadas = fase.get("rodadas", "todas")
        clubes = 2 * len(andamento.pares) + len(andamento.poupados)
        return {"tipo": "mata", "fase": andamento.fase,
                "nome": nome_da_rodada(nome, rodadas, clubes,
                                       andamento.rodadas_da_fase_feitas),
                "pares": [list(p) for p in andamento.pares],
                "poupados": list(andamento.poupados), "resultados": resultados,
                "maos": int(fase.get("maos", 2)),
                "visitante_avanca_empate": bool(fase.get("visitante_avanca_empate", False)),
                "disputas": {f"{a}-{b}": {"gols": [d["gols"][a], d["gols"][b]],
                                          "vencedor": d["vencedor"]}
                             for (a, b), d in andamento.disputas.items()},
                # clube novo entrando: a tela comeca um chaveamento novo aqui
                "abre": bool(fase.get("entram")) and andamento.rodadas_da_fase_feitas == 0}
    return None


# (ate quantos clubes disputam a rodada, nome). Por clubes e nao por pares: num mundo com
# numero impar de clubes um passa direto, e 5 pares + 1 isento sao oitavas, nao "5 pares".
NOMES_DO_MATA_MATA = ((2, "Final"), (4, "Semifinal"), (8, "Quartas de final"),
                      (16, "Oitavas de final"), (32, "16 avos de final"))


def nome_da_rodada(nome_da_fase: str, rodadas, clubes: int, feitas: int) -> str:
    """Fase de uma rodada so ("Playoff") fica com o nome dela; a fase que vai "ate sobrar
    um" ganha o nome pelo tamanho: oitavas, quartas, semi, final."""
    if str(rodadas) == "1":
        return nome_da_fase
    return next((nome for teto, nome in NOMES_DO_MATA_MATA if clubes <= teto),
                f"{nome_da_fase} · {feitas + 1}ª rodada")


def _apurar_mata_mata(andamento: Andamento, fase: dict,
                      exportados: dict[str, list[int]] | None,
                      world: World | None = None,
                      rng: np.random.Generator | None = None) -> None:
    pares, poupados = andamento.pares, andamento.poupados
    if not pares:
        return
    gols: dict[int, int] = {}
    for r in andamento.resultados:
        gols[r.home] = gols.get(r.home, 0) + r.goals_home
        gols[r.away] = gols.get(r.away, 0) + r.goals_away

    visitante = bool(fase.get("visitante_avanca_empate", False))
    vencedores, perdedores = [], []
    for casa, fora in pares:
        a, b = gols.get(int(casa), 0), gols.get(int(fora), 0)
        if a > b:
            ganhou, perdeu = casa, fora
        elif b > a:
            ganhou, perdeu = fora, casa
        elif visitante:
            # a regra de fases iniciais da Copa do Brasil: jogo unico, empate e do visitante
            ganhou, perdeu = fora, casa
        else:
            # empate no agregado: penaltis. O do usuario ja foi disputado na carreira;
            # os outros saem aqui, com os onze de cada clube
            chave = (int(casa), int(fora))
            if chave not in andamento.disputas and world is not None and rng is not None:
                from fm.disputa import vencedor_rapido
                andamento.disputas[chave] = vencedor_rapido(world, int(casa), int(fora), rng)
            d = andamento.disputas.get(chave)
            if d is not None:
                ganhou = d["vencedor"]
                perdeu = fora if ganhou == casa else casa
            else:
                ganhou, perdeu = casa, fora
        vencedores.append(int(ganhou))
        perdedores.append(int(perdeu))

    for regra in fase.get("exporta", []):
        if regra.get("eliminados") and exportados is not None:
            exportados.setdefault(chave_de_exportacao(andamento, regra),
                                  []).extend(perdedores)

    andamento.eliminados_na_fase = perdedores
    andamento.vivos = list(poupados) + vencedores
    if len(andamento.vivos) == 1 and perdedores:
        andamento.vice = perdedores[-1]


def etapas_previstas(torneio: Torneio) -> int:
    """Quantas datas o torneio ocupa no calendario, por estimativa.

    Serve so para espalhar os compromissos pela temporada. Se a conta errar, a agenda
    aperta ou sobra espaco -- nao muda resultado nenhum.
    """
    total = 0
    for fase in torneio.fases:
        tipo = fase.get("tipo")
        if tipo == "groups":
            # um grupo de quatro joga tres adversarios, ida e volta: seis rodadas
            total += 3 * int(fase.get("voltas", 2))
        elif tipo == "liga_suica":
            total += int(fase.get("adversarios", 8))
        elif tipo == "round_robin":
            total += 6
        else:
            pedido = fase.get("rodadas", "todas")
            rodadas = ETAPAS_DE_MATA_MATA["todas"] if pedido == "todas" else int(pedido)
            total += rodadas * int(fase.get("maos", 2))      # ida e volta: duas datas
    return max(total, 1)
