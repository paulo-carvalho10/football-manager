"""Estado de carreira: o jogo rodada a rodada.

O SAVE NAO GUARDA O MUNDO. Guarda a seed e as SUAS DECISOES -- clube, escalacao e tatica de
cada rodada. Carregar e reconstruir o mundo da seed e repetir as rodadas com as mesmas
decisoes. Isso so e possivel porque o motor e deterministico por seed desde o primeiro dia,
e e o que mantem o save pequeno (alguns KB em vez de dezenas de MB) e honesto: se o replay
divergisse, o determinismo estaria quebrado e o save seria a primeira vitima.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from fm.competition import Fixture, Result, play_fixtures, round_robin
from fm.config import load_league, style_of
from fm.eventos import Partida, simular_partida
from fm.generate import build_world
from fm.match import effective_rating
from fm.model import World
from fm.rng import Streams
from fm.season import CONDITION_COST, TAXA_DE_RECUPERACAO
from fm.table import Row, build_table
from fm.tatica import Tatica

SAVES_DIR = Path(__file__).resolve().parent.parent / "saves"

# As competicoes que a carreira disputa alem da liga. Todas ja existiam em data/torneios e
# rodavam isoladas num comando de CLI -- o que faltava era o relogio comum.
#
# Por PAIS, porque copa nao e universal: um mundo so com Espanha montava a Copa do Brasil
# vazia e reservava 33 datas que nunca aconteciam. A carreira pega as copas dos paises das
# divisoes que ela roda.
COPAS_POR_PAIS = {
    "BRA": ("copa_do_brasil", "libertadores", "sudamericana"),
    "ESP": ("champions", "europa_league"),
}
COPAS = COPAS_POR_PAIS["BRA"]


@dataclass(slots=True)
class Decisao:
    escalacao: list[int] = field(default_factory=list)
    tatica: dict = field(default_factory=lambda: asdict(Tatica()))


@dataclass(slots=True)
class Carreira:
    """A carreira roda sobre a PIRAMIDE inteira, nao sobre uma liga.

    Acesso e rebaixamento exigem as divisoes no mesmo mundo: nao da para promover um clube
    para um lugar que nao existe. Por isso `ligas` e uma lista, todas avancam juntas rodada
    a rodada, e o clube do usuario pode mudar de divisao entre as temporadas.
    """

    seed: int
    ligas: list[str]
    clube_id: int
    temporada: int
    rodada: int = 0
    decisoes: dict[str, Decisao] = field(default_factory=dict)
    world: World | None = None
    calendarios: dict[str, list[Fixture]] = field(default_factory=dict)
    resultados: dict[str, list[Result]] = field(default_factory=dict)
    historico: list[dict] = field(default_factory=list)
    streams: Streams | None = None
    # A temporada e uma lista de DATAS, nao so de rodadas: domingo tem liga, quarta tem
    # copa. E o que faz poupar um titular ser uma decisao em vez de um detalhe.
    agenda: list[tuple[str, str]] = field(default_factory=list)
    data: int = 0
    copas: dict = field(default_factory=dict)
    tabelas_do_ano_anterior: dict = field(default_factory=dict)
    # o funil entre torneios: quem cai da pre da Libertadores vai para a Sudamericana
    exportados: dict = field(default_factory=dict)
    # o que foi jogado na ultima data. A agenda pula datas de copa ja encerrada, entao
    # quem chama nao consegue deduzir isso do compromisso que leu antes de avancar.
    ultimo_compromisso: tuple[str, str] = ("", "")
    valor_de_elenco: dict = field(default_factory=dict)

    @classmethod
    def nova(cls, ligas: list[str] | str, clube: str, seed: int = 2027) -> Carreira:
        if isinstance(ligas, str):
            ligas = [ligas]
        cfgs = [load_league(n) for n in ligas]
        world, streams = build_world(cfgs, seed=seed)
        alvo = next((c for c in world.clubs.values()
                     if c.name.lower() == clube.lower()), None)
        if alvo is None:
            nomes = sorted(c.name for c in world.clubs.values())
            raise ValueError(f"clube {clube!r} nao esta em {ligas}. Ha: {nomes}")
        c = cls(seed=seed, ligas=list(ligas), clube_id=alvo.id,
                temporada=world.season_year)
        c._montar(world, streams)
        return c

    def _montar(self, world: World, streams: Streams) -> None:
        self.world = world
        self.streams = streams
        self._novo_calendario()

    def _novo_calendario(self) -> None:
        self.calendarios = {}
        self.resultados = {}
        for nome in self.ligas:
            lid = load_league(nome)["id"]
            rng = self.streams.get("calendario", self.temporada, lid)
            ids = list(world_ids := self.world.leagues[lid].club_ids)
            rng.shuffle(ids)                      # sorteio da tabela a cada temporada
            self.calendarios[nome] = round_robin(ids, legs=2)
            self.resultados[nome] = []
            assert world_ids is not None
        self.data = 0
        self._montar_agenda()
        # o valor de elenco do INICIO do ano e o que paga a receita: sem congelar, comprar
        # jogador aumentaria o faturamento do mesmo ano e o clube rico viraria bola de neve
        from fm.financas import valor_do_elenco
        self.valor_de_elenco = {c.id: valor_do_elenco(self.world, c.id)
                                for c in self.world.clubs.values()}

    def _montar_agenda(self) -> None:
        """Intercala as etapas de copa entre as rodadas de liga.

        As copas nao tem numero fixo de etapas -- depende do sorteio e de quantos clubes o
        mundo tem importados -- entao a agenda reserva espaco pela estimativa e, se sobrar
        data, ela e simplesmente pulada. Reservar a menos seria pior: a copa ficaria
        inacabada no fim do ano.
        """
        from fm.copa import comecar, etapas_previstas
        from fm.torneio import carregar

        self.copas = {}
        ocupados: set[int] = set()
        tabelas = self.tabelas_do_ano_anterior or self._tabelas_por_forca()
        for nome in self.copas_do_pais():
            try:
                t = carregar(nome)
            except FileNotFoundError:
                continue
            self.copas[nome] = comecar(self.world, t, tabelas, ocupados=ocupados)

        rodadas = self.total_de_rodadas
        # uma folga de duas datas por copa: sobrar data e de graca (ela e pulada), faltar
        # deixaria a competicao inacabada no fim do ano
        etapas = {nome: etapas_previstas(a.torneio) + 2
                  for nome, a in self.copas.items()}

        # Intercala os torneios em vez de enfileirar um depois do outro: assim a Copa do
        # Brasil e a Libertadores andam juntas, como numa temporada de verdade.
        fila: list[str] = []
        restam = dict(etapas)
        while any(restam.values()):
            for nome in etapas:
                if restam[nome] > 0:
                    fila.append(nome)
                    restam[nome] -= 1

        agenda: list[tuple[str, str]] = []
        if fila:
            por_rodada = len(fila) / max(rodadas, 1)
            devendo = 0.0
            for _ in range(rodadas):
                agenda.append(("liga", ""))
                devendo += por_rodada
                while devendo >= 1 and fila:
                    agenda.append(("copa", fila.pop(0)))
                    devendo -= 1
            agenda += [("copa", nome) for nome in fila]
        else:
            agenda = [("liga", "")] * rodadas
        self.agenda = agenda

    def copas_do_pais(self) -> tuple[str, ...]:
        """As competicoes de copa dos paises que esta carreira roda, sem repetir."""
        fora: list[str] = []
        for nome in self.ligas:
            for copa in COPAS_POR_PAIS.get(load_league(nome).get("pais", ""), ()):
                if copa not in fora:
                    fora.append(copa)
        return tuple(fora)

    def _titulos_de_copa(self) -> dict[str, list[int]]:
        """Campeao e vice de cada copa, na ordem em que as regras de vaga esperam."""
        fora: dict[str, list[int]] = {}
        for nome, a in self.copas.items():
            ordem = [c for c in (a.campeao, a.vice) if c is not None]
            if ordem:
                fora[nome] = ordem
        return fora

    def _tabelas_para_classificacao(self, tabelas: dict, titulos: dict[str, list[int]]
                                    ) -> dict[str, list[int]]:
        """As fontes de vaga do ano que vem: tabelas das ligas e vencedores de copa."""
        fontes: dict[str, list[int]] = dict(titulos)
        for nome, linhas in tabelas.items():
            cfg = load_league(nome)
            ordem = [linha.club_id for linha in linhas]
            fontes[cfg["id"]] = ordem
            if cfg.get("codigo"):
                fontes[cfg["codigo"]] = ordem
        return fontes

    def _jogos_de_copa(self) -> dict[int, int]:
        """Quantos jogos cada clube fez fora da liga. Ir longe custa viagem e elenco."""
        fora: dict[int, int] = {}
        for a in self.copas.values():
            for r in a.resultados_do_ano:
                fora[r.home] = fora.get(r.home, 0) + 1
                fora[r.away] = fora.get(r.away, 0) + 1
        return fora

    def _premiar_copas(self) -> dict[int, int]:
        """Premiacao de copa, por clube. E o que faz ir longe na Libertadores valer caixa."""
        from fm.financas import PREMIO_DE_COPA

        fora: dict[int, int] = {}
        for nome, a in self.copas.items():
            base = PREMIO_DE_COPA.get(nome, 0)
            if not base:
                continue
            if a.campeao is not None:
                fora[a.campeao] = fora.get(a.campeao, 0) + base
            if a.vice is not None:
                fora[a.vice] = fora.get(a.vice, 0) + int(base * 0.45)
        return fora

    def _tabelas_por_forca(self) -> dict[str, list[int]]:
        """Sem temporada anterior, a ordem por forca do elenco faz as vezes de tabela."""
        fora: dict[str, list[int]] = {}
        for nome in self.ligas:
            cfg = load_league(nome)
            ordem = sorted(self.world.leagues[cfg["id"]].club_ids,
                           key=lambda cid: -self.world.team_rating(cid))
            fora[cfg["id"]] = ordem
            if cfg.get("codigo"):
                fora[cfg["codigo"]] = ordem
        return fora

    @property
    def clube(self):
        return self.world.clubs[self.clube_id]

    @property
    def liga(self) -> str:
        """O arquivo de liga onde o clube do usuario esta AGORA (ele sobe e desce)."""
        atual = self.world.clubs[self.clube_id].league_id
        for nome in self.ligas:
            if load_league(nome)["id"] == atual:
                return nome
        return self.ligas[0]

    @property
    def liga_id(self) -> str:
        return load_league(self.liga)["id"]

    def _id(self, nome: str) -> str:
        return load_league(nome)["id"]

    @property
    def calendario(self) -> list[Fixture]:
        return self.calendarios[self.liga]

    def jogos(self, liga: str | None = None) -> list[Result]:
        """Resultados ja jogados numa divisao -- a do usuario, por omissao."""
        return self.resultados.get(liga or self.liga, [])

    @property
    def total_de_rodadas(self) -> int:
        return max((max((f.matchday for f in c), default=0)
                    for c in self.calendarios.values()), default=0)

    @property
    def acabou(self) -> bool:
        return self.data >= len(self.agenda)

    @property
    def compromisso(self) -> tuple[str, str] | None:
        """O que acontece na proxima data: a liga, ou uma etapa de copa."""
        return self.agenda[self.data] if not self.acabou else None

    def _chave(self, rodada: int | None = None) -> str:
        return f"{self.temporada}:{self.rodada + 1 if rodada is None else rodada}"

    def tatica_atual(self) -> Tatica:
        d = self.decisoes.get(self._chave())
        return Tatica(**d.tatica) if d else Tatica()

    def escalacao_atual(self) -> list[int]:
        d = self.decisoes.get(self._chave())
        if d and d.escalacao:
            return list(d.escalacao)
        return [p.id for p in self.world.best_xi(self.clube_id,
                                                 self.tatica_atual().vagas)]

    def proximo_jogo(self) -> tuple[str, str, Fixture | None]:
        """(tipo, competicao, jogo) da proxima data em que o usuario entra em campo.

        Percorre a agenda para a frente porque datas de copa encerrada sao puladas e
        porque numa data de copa o clube pode nem jogar -- ele ja foi eliminado, ou passou
        sem jogar. O lobby precisa dizer "quarta tem Libertadores", nao "tem alguma coisa".
        """
        for i in range(self.data, len(self.agenda)):
            tipo, quem = self.agenda[i]
            if tipo == "liga":
                jogo = self.proxima_partida()
                if jogo is not None:
                    return tipo, self.liga, jogo
                continue
            andamento = self.copas.get(quem)
            if andamento is None or andamento.acabou:
                continue
            if andamento.esta_vivo(self.clube_id):
                return tipo, quem, None
        return "", "", None

    def proxima_partida(self) -> Fixture | None:
        return next((f for f in self.calendario
                     if f.matchday == self.rodada + 1
                     and self.clube_id in (f.home, f.away)), None)

    def posicao_em(self, liga: str) -> list[Row]:
        return self.tabela(liga)

    def tabela(self, liga: str | None = None) -> list[Row]:
        nome = liga or self.liga
        return build_table(self.world.leagues[self._id(nome)].club_ids,
                           self.resultados[nome])

    def posicao(self) -> int:
        return next(i for i, r in enumerate(self.tabela(), 1) if r.club_id == self.clube_id)

    def escalar(self, jogadores: list[int], tatica: Tatica | None = None) -> None:
        """Registra a escalacao e a tatica da PROXIMA rodada."""
        tatica = tatica or self.tatica_atual()
        tatica.validar()
        elenco = {p.id for p in self.world.squad(self.clube_id)}
        fora = [p for p in jogadores if p not in elenco]
        if fora:
            raise ValueError(f"jogador de outro clube na escalacao: {fora}")
        if len(jogadores) != 11:
            raise ValueError(f"o onze precisa de 11 jogadores, vieram {len(jogadores)}")
        self.decisoes[self._chave()] = Decisao(list(jogadores), asdict(tatica))

    def avancar(self, substituicoes=None) -> tuple[list[Result], Partida | None]:
        """Joga a proxima DATA e para.

        Data de liga: uma rodada em todas as divisoes, porque a piramide anda junta -- sem
        isso as divisoes ficariam em temporadas diferentes e o acesso nao faria sentido.
        Data de copa: a etapa daquele torneio, com o jogo do usuario em detalhe.
        """
        if self.acabou:
            raise RuntimeError("a temporada acabou; chame virar_o_ano()")
        while not self.acabou:
            tipo, quem = self.agenda[self.data]
            if tipo == "liga":
                self.ultimo_compromisso = (tipo, quem)
                return self._jogar_rodada(substituicoes)
            saida = self._jogar_etapa_de_copa(quem, substituicoes)
            self.data += 1
            if saida is not None:
                self.ultimo_compromisso = (tipo, quem)
                return saida
            # torneio ja encerrado: a data reservada simplesmente nao acontece
        return [], None

    def _jogar_rodada(self, substituicoes=None) -> tuple[list[Result], Partida | None]:
        n = self.rodada + 1
        tatica = self.tatica_atual()
        self.world.escalacao_fixa[self.clube_id] = self.escalacao_atual()
        self.world.formacao_fixa[self.clube_id] = tatica.vagas

        meu_jogo = self.proxima_partida()
        detalhada: Partida | None = None
        todos: list[Result] = []
        jogaram: set[int] = set()

        for nome in self.ligas:
            cfg = load_league(nome)
            lid = cfg["id"]
            partidas = [f for f in self.calendarios[nome] if f.matchday == n]
            if not partidas:
                continue
            jogaram |= {f.home for f in partidas} | {f.away for f in partidas}
            ratings = {
                cid: float(effective_rating(self.world.team_rating(cid),
                                            fatigue=self.world.fatigue_penalty(cid)))
                for cid in self.world.leagues[lid].club_ids
            }
            rng = self.streams.get("carreira", self.temporada, n, lid)
            style = style_of(cfg)

            if meu_jogo is not None and meu_jogo in partidas:
                detalhada = self._minha_partida(meu_jogo, rng, style, tatica,
                                                substituicoes)
                outras = [f for f in partidas if f is not meu_jogo]
                r = play_fixtures(outras, ratings, rng, style)
                r.append(Result(meu_jogo.home, meu_jogo.away,
                                detalhada.gols_casa, detalhada.gols_fora, n))
            else:
                r = play_fixtures(partidas, ratings, rng, style)

            self.resultados[nome].extend(r)
            todos.extend(r)

        self._gastar_energia(jogaram, tatica)
        self.rodada = n
        self.data += 1
        return todos, detalhada

    def _minha_partida(self, jogo: Fixture, rng, style, tatica: Tatica,
                       substituicoes) -> Partida:
        from fm.tatica import confronto
        sou_casa = jogo.home == self.clube_id
        ma, md = (confronto(tatica, Tatica()) if sou_casa
                  else confronto(Tatica(), tatica))
        return simular_partida(
            self.world, jogo.home, jogo.away,
            [p.id for p in self.world.best_xi(jogo.home)],
            [p.id for p in self.world.best_xi(jogo.away)],
            rng, style, mult_casa=ma, mult_fora=md, substituicoes=substituicoes)

    def _jogar_etapa_de_copa(self, nome: str, substituicoes=None
                             ) -> tuple[list[Result], Partida | None] | None:
        """Uma etapa de copa. None quando o torneio ja acabou e a data fica vazia."""
        from fm.copa import proxima_etapa, registrar

        andamento = self.copas.get(nome)
        if andamento is None:
            return None
        rng = self.streams.get("copa", self.temporada, self.data, nome)
        tabelas = self.tabelas_do_ano_anterior or self._tabelas_por_forca()
        etapa = proxima_etapa(self.world, andamento, rng, tabelas)
        if etapa is None or not etapa.fixtures:
            return None

        tatica = self.tatica_atual()
        self.world.escalacao_fixa[self.clube_id] = self.escalacao_atual()
        self.world.formacao_fixa[self.clube_id] = tatica.vagas
        t = andamento.torneio
        meus = [f for f in etapa.fixtures
                if self.clube_id in (f.home, f.away)]
        detalhada: Partida | None = None
        jogos = list(etapa.fixtures)
        resultados: list[Result] = []

        if meus:
            # no mata-mata de ida e volta o usuario joga a ida em detalhe; a volta resolve
            # no motor rapido, senao uma data pediria duas partidas seguidas na tela
            meu = meus[0]
            detalhada = self._minha_partida(meu, rng, t.style, tatica, substituicoes)
            resultados.append(Result(meu.home, meu.away, detalhada.gols_casa,
                                     detalhada.gols_fora, meu.matchday))
            jogos = [f for f in jogos if f is not meu]

        ratings = {cid: float(effective_rating(self.world.team_rating(cid),
                                               fatigue=self.world.fatigue_penalty(cid)))
                   for cid in {f.home for f in etapa.fixtures} | {f.away for f in etapa.fixtures}}
        resultados += play_fixtures(jogos, ratings, rng, t.style, t.mentality)
        registrar(self.world, andamento, resultados, rng, self.exportados)

        jogaram = {f.home for f in etapa.fixtures} | {f.away for f in etapa.fixtures}
        self._gastar_energia(jogaram, tatica)
        return resultados, detalhada

    def _gastar_energia(self, jogaram: set[int], tatica: Tatica) -> None:
        """Energia entre rodadas.

        TODO MUNDO recupera; quem jogou paga o custo por cima. A recuperacao e
        proporcional ao quanto falta para 100, o que cria EQUILIBRIO: quem joga toda rodada
        estabiliza perto de 81%, nao desaba ate o piso.
        """
        for club_id in self.world.clubs:
            onze = ({p.id for p in self.world.best_xi(club_id)}
                    if club_id in jogaram else set())
            # marcacao forte cansa mais: o preco aparece na rodada seguinte, nao nesta
            custo = CONDITION_COST * (tatica.custo_de_energia
                                      if club_id == self.clube_id else 1.0)
            for p in self.world.squad(club_id):
                recupera = TAXA_DE_RECUPERACAO * (100 - p.condition)
                delta = recupera - (custo if p.id in onze else 0.0)
                p.condition = int(np.clip(p.condition + delta, 25, 100))

    # ---------------------------------------------------------------- virar o ano

    def virar_o_ano(self) -> dict:
        """Fecha a temporada e abre a proxima. E o que faz o jogo nao acabar na rodada 38.

        Ordem importa: as tabelas finais tem de ser lidas ANTES de mexer nas divisoes, e o
        envelhecimento vem depois do acesso para que o garoto promovido ja evolua no clube
        novo.
        """
        from fm.financas import fechar_o_ano
        from fm.mercado import janela
        from fm.temporada import acesso_e_rebaixamento, envelhecer, repor_elencos

        if not self.acabou:
            raise RuntimeError(f"faltam {self.total_de_rodadas - self.rodada} rodadas")

        cfgs = {n: load_league(n) for n in self.ligas}
        tabelas = {n: self.tabela(n) for n in self.ligas}
        campeoes = {n: self.world.clubs[t[0].club_id].name for n, t in tabelas.items()}
        minha_liga = self.liga
        minha_posicao = self.posicao()

        # A ordem e a regra. As contas fecham na divisao em que o ano foi jogado, e so
        # depois o clube troca de divisao; o mercado vem depois do envelhecimento para
        # negociar overalls deste ano, e a base entra por ultimo, tapando o que sobrou.
        # As tabelas e os campeoes de copa deste ano decidem quem disputa o que no ano que
        # vem -- e a cascata de vagas que ja estava escrita nos arquivos de torneio, agora
        # alimentada pela temporada de verdade em vez da forca desenhada.
        titulos = self._titulos_de_copa()
        premios_de_copa = self._premiar_copas()
        balancos = fechar_o_ano(self.world, tabelas, cfgs, extras=premios_de_copa,
                                jogos_extras=self._jogos_de_copa(),
                                valores=self.valor_de_elenco)
        mudancas = acesso_e_rebaixamento(self.world, self.ligas, tabelas, cfgs)
        rng = self.streams.get("virada", self.temporada)
        # o alvo de elenco e o tamanho ANTES das aposentadorias: cada clube repoe o que
        # perdeu e mantem a propria dimensao, em vez de convergir todo mundo para o mesmo
        alvos = {c.id: len(c.player_ids) for c in self.world.clubs.values()}
        antes = {p.id: (p.name, p.overall) for p in self.world.squad(self.clube_id)}
        envelhecimento = envelhecer(self.world, rng, self.temporada)
        transferencias = janela(self.world, rng, self.temporada + 1)
        novos = repor_elencos(self.world, rng, self.temporada + 1, alvos=alvos)

        # o que mudou no elenco do usuario -- e isto que a tela de fim de ano mostra
        agora = {p.id: p for p in self.world.squad(self.clube_id)}
        saidas = [nome for pid, (nome, _) in antes.items() if pid not in agora]
        destaques = sorted(
            ((p.name, antes[pid][1], p.overall, p.age(self.temporada + 1))
             for pid, p in agora.items()
             if pid in antes and p.overall > antes[pid][1]),
            key=lambda d: d[1] - d[2])[:6]
        # quem chegou comprado nao e da base -- a tela listava Alex Telles, 35 anos,
        # entre os garotos que subiram
        comprados = {t.jogador for t in transferencias if t.para == self.clube_id}
        base = sorted(
            ((p.name, p.overall, p.potential, p.age(self.temporada + 1))
             for pid, p in agora.items() if pid not in antes and pid not in comprados),
            key=lambda d: -d[2])[:6]

        minha = next((m for m in mudancas if m.clube == self.clube_id), None)
        resumo = {
            "temporada": self.temporada,
            "campeoes": campeoes,
            "minha_liga": minha_liga,
            "minha_posicao": minha_posicao,
            "subi": bool(minha and minha.subiu),
            "cai": bool(minha and not minha.subiu),
            "promovidos": [self.world.clubs[m.clube].name for m in mudancas if m.subiu],
            "rebaixados": [self.world.clubs[m.clube].name for m in mudancas if not m.subiu],
            **envelhecimento, "revelados": novos,
            "balanco": balancos.get(self.clube_id),
            "transferencias": len(transferencias),
            "compras_do_clube": [t for t in transferencias if t.para == self.clube_id],
            "vendas_do_clube": [t for t in transferencias if t.de == self.clube_id],
            "maiores_transferencias": sorted(transferencias, key=lambda t: -t.preco)[:6],
            "copas": {n: (self.world.clubs[a.campeao].name if a.campeao else None)
                      for n, a in self.copas.items()},
            "minhas_copas": [n for n, a in self.copas.items()
                             if a.campeao == self.clube_id],
            "premios_de_copa": premios_de_copa.get(self.clube_id, 0),
            "aposentadorias_do_clube": saidas,
            "destaques_do_clube": destaques,
            "base_do_clube": base,
        }
        self.historico.append(resumo)

        self.temporada += 1
        self.world.season_year = self.temporada
        self.rodada = 0
        self.world.escalacao_fixa.clear()
        self.world.formacao_fixa.clear()
        for p in self.world.players.values():
            p.condition = 100
        self.tabelas_do_ano_anterior = self._tabelas_para_classificacao(tabelas, titulos)
        self.exportados = {}
        self._novo_calendario()
        return resumo

    def salvar(self, nome: str) -> Path:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        destino = SAVES_DIR / f"{nome}.json"
        destino.write_text(json.dumps({
            "seed": self.seed, "ligas": self.ligas, "clube_id": self.clube_id,
            "temporada_inicial": self.temporada - len(self.historico),
            # `data`, nao `rodada`: a temporada anda por datas, e uma delas pode ser
            # copa. Guardar a rodada da liga perderia os jogos de copa no replay.
            "temporada": self.temporada, "data": self.data,
            "decisoes": {k: asdict(v) for k, v in self.decisoes.items()},
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        return destino

    @classmethod
    def carregar(cls, nome: str) -> Carreira:
        origem = SAVES_DIR / f"{nome}.json"
        if not origem.exists():
            raise FileNotFoundError(f"save {nome!r} nao existe. Ha: {saves_disponiveis()}")
        d = json.loads(origem.read_text(encoding="utf-8"))
        cfgs = [load_league(n) for n in d["ligas"]]
        world, streams = build_world(cfgs, seed=d["seed"])
        c = cls(seed=d["seed"], ligas=list(d["ligas"]), clube_id=d["clube_id"],
                temporada=d["temporada_inicial"])
        c.decisoes = {k: Decisao(**v) for k, v in d["decisoes"].items()}
        c._montar(world, streams)
        # REPLAY: as temporadas sao refeitas com as mesmas decisoes. Se isto divergir, o
        # determinismo do motor quebrou -- e o save seria a primeira vitima.
        while c.temporada < d["temporada"]:
            while not c.acabou:
                c.avancar()
            c.virar_o_ano()
        while c.data < d.get("data", d.get("rodada", 0)) and not c.acabou:
            c.avancar()
        return c


def saves_disponiveis() -> list[str]:
    return sorted(p.stem for p in SAVES_DIR.glob("*.json")) if SAVES_DIR.exists() else []
