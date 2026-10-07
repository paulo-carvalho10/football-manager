"""Datas FIFA, eliminatorias e Copa do Mundo.

O CICLO de uma Copa (a de 2030, a de 2034...) ocupa os quatro anos ate ela:

    Y-3  setembro a novembro    eliminatorias sul-americanas (rodadas 1 a 6)
    Y-2  marco a novembro       sul-americanas (7 a 16)
    Y-1  marco                  sul-americanas (17 e 18)
         marco a novembro       europeias (grupos)
    Y    meados de junho a      Copa do Mundo, 48 selecoes
         meados de julho

Cada ano tem cinco JANELAS FIFA (marco, junho, setembro, outubro, novembro), com dois
jogos: quinta e a terca seguinte. Nelas NADA de clube joga -- nem liga, nem copa
(fm.agenda recebe os bloqueios) --, e no ano da Copa o mes dela tambem para tudo. Foi a
escolha de 07/10/2026: o Brasileirao aperta com rodadas no meio da semana, mas ninguem
joga sem os convocados.

As outras confederacoes (Africa, Asia, Concacaf, Oceania) nao tem eliminatoria simulada:
as vagas delas vao as mais fortes do ranking na hora da Copa, e a vaga que a confederacao
nao preencher (a Asia tem duas selecoes no mundo do jogo) vai a melhor selecao que sobrou.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from fm.competition import Result, play_fixtures
from fm.match import effective_rating
from fm.model import World
from fm.selecoes import (
    CONFEDERACOES,
    SUSPENSAS,
    confederacao,
    convocar,
    convocar_todas,
    forca,
    id_da_selecao,
    mundo_das_selecoes,
    pais_da_selecao,
    ranking,
)

PRIMEIRA_COPA = 2030
# a segunda-feira (mais ou menos) em que cada janela abre: (mes, dia)
JANELAS = ((3, 23), (6, 1), (9, 7), (10, 5), (11, 9))
# os dias de jogo da Copa: tres rodadas de grupo e as cinco do mata-mata (32 ate a final)
DIAS_DA_COPA = ((6, 13), (6, 18), (6, 23), (6, 28), (7, 3), (7, 8), (7, 13), (7, 19))
BLOQUEIO_DA_COPA = ((6, 1), (7, 21))
SEDES = {2030: ("Espanha", "Portugal", "Marrocos"), 2034: ("Arábia Saudita",)}
# as vagas de 2026 em diante (48): 46 por confederacao e 2 da repescagem, que aqui vao as
# duas melhores selecoes que sobrarem
VAGAS = {"CONMEBOL": 6, "UEFA": 16, "CAF": 9, "AFC": 8, "CONCACAF": 6, "OFC": 1}
VAGAS_NA_COPA = 48
ELIMINATORIAS = {"eliminatorias_conmebol": "CONMEBOL", "eliminatorias_uefa": "UEFA"}
# grupos do mesmo tamanho e par (fm.competition.group_stage): de 4, em seis rodadas
POR_GRUPO_NA_UEFA = 4


def e_ano_de_copa(ano: int) -> bool:
    return ano >= PRIMEIRA_COPA and (ano - PRIMEIRA_COPA) % 4 == 0


def copa_do_ciclo(dia: date) -> int:
    """A Copa para a qual um dia de data FIFA conta: a do proprio ano ate ela acabar,
    depois a seguinte."""
    ano = dia.year
    if ano < PRIMEIRA_COPA:
        return PRIMEIRA_COPA
    resto = (ano - PRIMEIRA_COPA) % 4
    if resto == 0 and dia > date(ano, *BLOQUEIO_DA_COPA[1]):
        return ano + 4
    return ano + (4 - resto) % 4


def _quinta(d: date) -> date:
    return d + timedelta(days=(3 - d.weekday()) % 7)


def _janelas(ano: int) -> list[tuple[int, date, date]]:
    """(mes da janela, primeiro jogo, segundo jogo) de cada janela do ano. No ano da Copa,
    a de junho vira a Copa. O segundo jogo pode cair no mes seguinte (a de marco termina
    em abril): e pela janela, nao pelo mes do dia, que se sabe o que se joga."""
    fora = []
    for mes, dia in JANELAS:
        if mes == 6 and e_ano_de_copa(ano):
            continue
        primeiro = _quinta(date(ano, mes, dia))
        fora.append((mes, primeiro, primeiro + timedelta(days=5)))
    return fora


def datas_fifa(ano: int) -> list[date]:
    """Os dias de jogo das janelas do ano."""
    return [d for _, a, b in _janelas(ano) for d in (a, b)]


def janela_de(dia: date) -> int | None:
    """O mes da janela FIFA de um dia de jogo de selecao (None se nao for um)."""
    return next((mes for mes, a, b in _janelas(dia.year) if dia in (a, b)), None)


def dias_da_copa(ano: int) -> list[date]:
    return [date(ano, m, d) for m, d in DIAS_DA_COPA] if e_ano_de_copa(ano) else []


def bloqueios(ano: int) -> list[tuple[date, date]]:
    """Os periodos em que clube nao joga: cada janela, de segunda a quarta da semana
    seguinte (o domingo do meio esta dentro), e o mes da Copa."""
    fora = []
    datas = datas_fifa(ano)
    for i in range(0, len(datas), 2):
        fora.append((datas[i] - timedelta(days=3), datas[i + 1] + timedelta(days=1)))
    if e_ano_de_copa(ano):
        fora.append((date(ano, *BLOQUEIO_DA_COPA[0]), date(ano, *BLOQUEIO_DA_COPA[1])))
    return fora


def dias_de_selecao(ano: int) -> list[date]:
    return sorted(datas_fifa(ano) + dias_da_copa(ano))


def competicoes_do_dia(dia: date) -> list[str]:
    """O que pode ter jogo neste dia. Data que sobra (a eliminatoria ja acabou) passa vazia."""
    if dia in dias_da_copa(dia.year):
        return ["copa_do_mundo"]
    y = copa_do_ciclo(dia)
    janela = janela_de(dia)
    if janela is None:
        return []
    fora = []
    if ((dia.year == y - 3 and janela >= 9) or dia.year == y - 2
            or (dia.year == y - 1 and janela == 3)):
        fora.append("eliminatorias_conmebol")
    if dia.year == y - 1:
        fora.append("eliminatorias_uefa")
    return fora


@dataclass
class Fifa:
    """O estado das selecoes, que atravessa as temporadas: a carreira guarda um e o leva
    na virada do ano (as eliminatorias duram tres)."""
    # as competicoes em curso, e de que Copa (ano) cada uma e
    competicoes: dict = field(default_factory=dict)
    ciclo_de: dict[str, int] = field(default_factory=dict)
    # a ultima convocacao de cada selecao, e o mundo em que elas jogam
    convocacoes: dict[str, list[int]] = field(default_factory=dict)
    mundo: World | None = None
    ultima_convocacao: date | None = None
    # quem foi a cada Copa e o que aconteceu nela
    classificados: dict[int, list[str]] = field(default_factory=dict)
    historico: list[dict] = field(default_factory=list)
    resultados: dict[str, list[Result]] = field(default_factory=dict)
    # a competicao da partida da selecao do usuario que esta em campo (ou acabou de jogar)
    torneio_do_usuario: str | None = None

    # ------------------------------------------------------------ convocacao

    def convocar(self, world: World, dia: date, fora: set[int]) -> None:
        """A convocacao da IA, uma vez por janela (e uma para a Copa inteira)."""
        if self.ultima_convocacao is not None:
            mesma_copa = (dia in dias_da_copa(dia.year)
                          and self.ultima_convocacao in dias_da_copa(dia.year))
            if mesma_copa or (dia - self.ultima_convocacao).days < 10:
                return
        self.ultima_convocacao = dia
        self.convocacoes = convocar_todas(world, fora)
        # a selecao que deixou de ter elenco minimo (aposentadoria, goleiro a menos) no
        # meio de uma competicao termina o que esta disputando com quem tiver. REGRESSAO:
        # ela ficava com a convocacao antiga, e o aposentado na virada do ano derrubava
        # o jogo (KeyError no elenco)
        for a in self.competicoes.values():
            if a.acabou:
                continue
            for sid in a.vivos:
                pais = pais_da_selecao(sid)
                if pais not in self.convocacoes:
                    self.convocacoes[pais] = convocar(world, pais, fora)
        self.mundo = mundo_das_selecoes(world, self.convocacoes)
        ordem = ranking(self.mundo)
        for i, pais in enumerate(ordem):
            self.mundo.clubs[id_da_selecao(pais)].reputation = max(5, 99 - i)

    # ------------------------------------------------------------ competicoes

    def _tabelas(self) -> dict[str, list[int]]:
        """A ordem por forca de cada confederacao, sem as suspensas -- e de onde as
        eliminatorias tiram quem joga."""
        assert self.mundo is not None
        fora: dict[str, list[int]] = {}
        for pais in ranking(self.mundo):
            if pais in SUSPENSAS:
                continue
            conf = confederacao(pais)
            if conf:
                fora.setdefault(conf, []).append(id_da_selecao(pais))
        return fora

    def _comecar(self, nome: str, ciclo: int):
        from fm.copa import comecar
        from fm.torneio import carregar
        t = carregar(nome)
        tabelas = self._tabelas()
        sedes = set(SEDES.get(ciclo, ()))
        if nome in ELIMINATORIAS:
            conf = ELIMINATORIAS[nome]
            tabelas[conf] = [s for s in tabelas.get(conf, [])
                             if pais_da_selecao(s) not in sedes]
            if nome == "eliminatorias_uefa":
                # so quem fecha grupo inteiro: as mais fracas da Europa ficam de fora
                n = len(tabelas[conf]) // POR_GRUPO_NA_UEFA * POR_GRUPO_NA_UEFA
                tabelas[conf] = tabelas[conf][:n]
                t.fases[0] = {**t.fases[0], "grupos": max(1, n // POR_GRUPO_NA_UEFA)}
        else:
            tabelas["MUNDIAL"] = self.classificados_para_a_copa(ciclo)
        self.competicoes[nome] = comecar(self.mundo, t, tabelas)
        self.ciclo_de[nome] = ciclo
        self.resultados[nome] = []
        return self.competicoes[nome]

    def classificados_para_a_copa(self, ciclo: int) -> list[int]:
        """As 48 da Copa, da mais forte para a mais fraca (e assim que os potes saem)."""
        tabelas = self._tabelas()
        forca = {s: i for i, s in enumerate(id_da_selecao(p) for p in ranking(self.mundo))}
        dentro: list[int] = [id_da_selecao(p) for p in SEDES.get(ciclo, ())
                             if id_da_selecao(p) in self.mundo.clubs]
        for nome, conf in ELIMINATORIAS.items():
            vagas = VAGAS[conf] - sum(1 for s in dentro if confederacao(pais_da_selecao(s)) == conf)
            a = self.competicoes.get(nome)
            if a is not None and self.ciclo_de.get(nome) == ciclo:
                dentro += [s for s in self._classificacao(nome) if s not in dentro][:vagas]
            else:      # a carreira comecou com a eliminatoria em andamento: pelo ranking
                dentro += [s for s in tabelas.get(conf, []) if s not in dentro][:vagas]
        for conf in ("CAF", "AFC", "CONCACAF", "OFC"):
            vagas = VAGAS[conf] - sum(1 for s in dentro if confederacao(pais_da_selecao(s)) == conf)
            dentro += [s for s in tabelas.get(conf, []) if s not in dentro][:max(0, vagas)]
        # repescagem e vagas que sobraram: as melhores de qualquer lugar
        resto = [s for s in sorted(forca, key=forca.get) if s not in dentro
                 and pais_da_selecao(s) not in SUSPENSAS]
        dentro += resto[:VAGAS_NA_COPA - len(dentro)]
        self.classificados[ciclo] = [pais_da_selecao(s) for s in dentro]
        return sorted(dentro, key=lambda s: forca.get(s, 999))

    def _classificacao(self, nome: str) -> list[int]:
        """Quem a eliminatoria classifica, na ordem: na sul-americana, a tabela; na
        europeia, os primeiros de grupo e depois os segundos, pela campanha."""
        from fm.table import build_table
        a = self.competicoes[nome]
        if a.grupos:
            linhas = []
            for ids in a.grupos:
                do_grupo = [r for r in self.resultados[nome] if r.home in ids and r.away in ids]
                for pos, linha in enumerate(build_table(ids, do_grupo)):
                    linhas.append((pos, -linha.points,
                                   -(linha.goals_for - linha.goals_against),
                                   -linha.goals_for, linha.club_id))
            return [x[-1] for x in sorted(linhas)]
        ids = list(a.vivos) or [r.home for r in self.resultados[nome]]
        return [linha.club_id for linha in build_table(sorted(set(ids)), self.resultados[nome])]

    def _andamento(self, nome: str, dia: date):
        ciclo = copa_do_ciclo(dia)
        a = self.competicoes.get(nome)
        if a is not None and self.ciclo_de.get(nome) == ciclo:
            return a
        primeira = {"eliminatorias_conmebol": (ciclo - 3, 9), "eliminatorias_uefa": (ciclo - 1, 3)}
        if nome in primeira and (dia.year, janela_de(dia)) != primeira[nome]:
            return None       # so comeca na janela de abertura: no meio, fica para o ranking
        return self._comecar(nome, ciclo)

    # ------------------------------------------------------------ o dia de jogo

    def jogar(self, world: World, dia: date, rng, fora: set[int] = frozenset(),
              usuario: str | None = None, convocacao: list[int] | None = None,
              meu_jogo=None) -> tuple[list[Result], object | None]:
        """Os jogos de selecao do dia. Os da IA no motor rapido; o da selecao do usuario,
        se ela jogar, por `meu_jogo(mundo, jogo, andamento, outros)` -> (Result, Partida),
        que e a partida detalhada (e ao vivo) da carreira."""
        from fm.copa import proxima_etapa, registrar
        comps = competicoes_do_dia(dia)
        if not comps:
            return [], None
        self.convocar(world, dia, fora)
        sid = id_da_selecao(usuario) if usuario else None
        if sid is not None and sid in self.mundo.clubs:
            # a lista do treinador vale enquanto o jogador puder ir: do pais, num clube,
            # sem lesao. Sem onze na lista, a da IA.
            validos = [p for p in (convocacao or []) if p in world.players
                       and world.players[p].club_id in world.clubs
                       and world.players[p].nationality == usuario and p not in fora]
            if len(validos) >= 11:
                self.mundo.clubs[sid].player_ids = validos
        feitos: list[Result] = []
        detalhada = None
        for nome in comps:
            a = self._andamento(nome, dia)
            if a is None or a.acabou:
                continue
            etapa = proxima_etapa(self.mundo, a, rng, {})
            if etapa is None or not etapa.fixtures:
                continue
            t = a.torneio
            meu = next((f for f in etapa.fixtures if sid in (f.home, f.away)), None) \
                if sid is not None and meu_jogo is not None else None
            ratings = {s: float(effective_rating(forca(self.mundo, s)))
                       for f in etapa.fixtures for s in (f.home, f.away)}
            resultados = play_fixtures([f for f in etapa.fixtures if f is not meu],
                                       ratings, rng, t.style, t.mentality)
            if meu is not None:
                self.torneio_do_usuario = nome
                r, detalhada = meu_jogo(self.mundo, meu, a, resultados)
                resultados = [r, *resultados]
            registrar(self.mundo, a, resultados, rng, {})
            self.resultados[nome] += resultados
            feitos += resultados
            if nome == "copa_do_mundo" and a.acabou:
                self._fechar_a_copa(dia.year)
        return feitos, detalhada

    def joga_em(self, pais: str, dia: date) -> str | None:
        """A competicao em que a selecao entra em campo neste dia, ou None. Antes de a
        competicao comecar, a da confederacao dela (e a Copa, se ela se classificou)."""
        from fm.selecoes import confederacao as conf_de
        sid = id_da_selecao(pais)
        ciclo = copa_do_ciclo(dia)
        for nome in competicoes_do_dia(dia):
            a = self.competicoes.get(nome)
            if a is not None and self.ciclo_de.get(nome) == ciclo:
                if not a.acabou and sid in a.vivos:
                    return nome
                continue
            if pais in SUSPENSAS:
                continue
            if nome in ELIMINATORIAS and ELIMINATORIAS[nome] == conf_de(pais) \
                    and pais not in SEDES.get(ciclo, ()):
                return nome
            if nome == "copa_do_mundo" and pais in self.classificados.get(ciclo, [pais]):
                return nome
        return None

    def proximo_rival(self, pais: str, nome: str) -> int | None:
        """O adversario ja marcado (grupos e pontos corridos); no mata-mata, so no dia."""
        a = self.competicoes.get(nome)
        sid = id_da_selecao(pais)
        if a is None or not a.pendentes:
            return None
        f = next((f for f in a.pendentes[0] if sid in (f.home, f.away)), None)
        return None if f is None else (f.away if f.home == sid else f.home)

    def _fechar_a_copa(self, ano: int) -> None:
        a = self.competicoes["copa_do_mundo"]
        self.historico.append({
            "ano": ano,
            "campeao": pais_da_selecao(a.campeao) if a.campeao else None,
            "vice": pais_da_selecao(a.vice) if a.vice else None,
            "sedes": list(SEDES.get(ano, ())),
        })

    # ------------------------------------------------------------ para a tela

    def nome(self, sid: int) -> str:
        return pais_da_selecao(sid)


def confederacoes() -> list[str]:
    return list(CONFEDERACOES)
