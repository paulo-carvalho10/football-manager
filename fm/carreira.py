"""Estado de carreira: o jogo rodada a rodada.

O SAVE NAO GUARDA O MUNDO. Guarda a seed e as SUAS DECISOES -- clube, escalacao e tatica de
cada rodada. Carregar e reconstruir o mundo da seed e repetir as rodadas com as mesmas
decisoes. Isso so e possivel porque o motor e deterministico por seed desde o primeiro dia,
e e o que mantem o save pequeno (alguns KB em vez de dezenas de MB) e honesto: se o replay
divergisse, o determinismo estaria quebrado e o save seria a primeira vitima.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from pathlib import Path

from fm.calendario import dia_da_data
from fm.competition import Fixture, Result, play_fixtures, round_robin
from fm.config import load_league, style_of
from fm.eventos import Partida, simular_partida
from fm.generate import build_world
from fm.match import effective_rating
from fm.model import World
from fm.moeda import texto as texto_de_euros
from fm.moral import bonus as bonus_de_moral
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
# As primeiras divisoes de cada confederacao. Numa carreira que disputa as copas dela, as
# que a carreira NAO joga entram no mundo mesmo assim -- clubes e elencos reais, sem
# calendario: a temporada delas e simulada na virada do ano, e e a tabela simulada que
# classifica. Sem isto, a Libertadores de uma carreira no Brasil tinha so brasileiros e
# quatro convidados, e virava grupos de dois.
LIGAS_DA_CONFEDERACAO = {
    "CONMEBOL": ("brasil_real", "argentina_real", "colombia_real", "chile_real",
                 "uruguai_real", "equador_real", "paraguai_real", "peru_real",
                 "bolivia_real", "venezuela_real"),
    # a UEFA so serve de RANKING (a reserva da Supercopa da UEFA no primeiro ano): as ligas
    # dela nunca sao carregadas como pano de fundo, por isso nao entra em COPAS_DA_CONFEDERACAO
    "UEFA": ("espanha_real", "inglaterra_real", "italia_real", "alemanha_real", "franca_real",
             "portugal_real", "holanda_real", "belgica_real", "turquia_real", "grecia_real",
             "ucrania_real", "austria_real", "suica_real", "escocia_real", "dinamarca_real",
             "noruega_real", "suecia_real", "servia_real", "croacia_real", "polonia_real",
             "tchequia_real"),
}
COPAS_DA_CONFEDERACAO = {"libertadores": "CONMEBOL", "sudamericana": "CONMEBOL",
                         "recopa": "CONMEBOL"}

# A ordem importa: as vagas continentais sao distribuidas nesta ordem com `ocupados`
# compartilhado, entao a Champions escolhe antes da Liga Europa, e esta antes da
# Conference League. As supercopas e as copas nacionais nao disputam vaga com ninguem.
_UEFA = ("champions", "europa_league", "conference_league", "supercopa_uefa")
_CONMEBOL = ("libertadores", "sudamericana", "recopa")
COPAS_POR_PAIS = {
    "BRA": ("copa_do_brasil", "supercopa_do_brasil", *_CONMEBOL),
    "ESP": (*_UEFA, "copa_del_rey"),
    "ENG": (*_UEFA, "fa_cup"),
    "ITA": (*_UEFA, "coppa_italia"),
    "GER": (*_UEFA, "dfb_pokal"),
    "FRA": (*_UEFA, "coupe_de_france"),
    "POR": (*_UEFA, "taca_de_portugal"),
    "ARG": (*_CONMEBOL, "copa_argentina"),
    **{p: _CONMEBOL for p in ("COL", "CHI", "URU", "ECU", "PAR", "PER", "BOL", "VEN")},
    **{p: _UEFA
       for p in ("NED", "BEL", "TUR", "GRE", "UKR", "AUT", "SUI", "SCO", "DEN", "NOR", "SWE",
                 "SRB", "CRO", "POL", "CZE")},
    # a UEFA exclui os clubes russos desde 2022: a liga existe, as copas europeias nao
    "RUS": (),
}
COPAS = COPAS_POR_PAIS["BRA"]
# As copas continentais em que um clube so pode estar em UMA: a vaga em uma tira da outra.
DISPUTAM_VAGA = {"libertadores", "sudamericana", "champions", "europa_league",
                 "conference_league"}

MAX_TROCAS = 5
MAX_HUMANOS = 8         # tecnicos de carne e osso numa mesma carreira (o online)

# Quem esta com a vez DENTRO de uma conta da carreira. Ao jogar a data, a carreira passa
# por cada humano (`Carreira._como`) e os atalhos (`c.clube_id`...) leem o dele. A vez e
# da thread: a tela, que le a carreira de outra thread enquanto a partida ao vivo esta
# pausada, continua vendo o humano ativo. Fora do objeto para nao ir ao save (pickle).
_VEZ = threading.local()


def _vez(c: Carreira) -> int:
    pilha = getattr(_VEZ, "de", None)
    if pilha:
        i = pilha.get(id(c))
        if i is not None:
            return i
    return c.ativo


class TabelasPreguicosas(Mapping):
    """As tabelas por forca, calculadas so quando alguem olha.

    Ordenar os 700 clubes do mundo pela forca do onze custa ~0,1 s, e a copa so precisa
    disso no dia em que uma fase nova puxa clubes de uma liga -- nas outras datas o calculo
    era jogado fora. O resultado e o mesmo de calcular na hora da chamada: entre ela e a
    primeira consulta nenhuma partida e jogada.
    """

    def __init__(self, calcular: Callable[[], dict[str, list[int]]]) -> None:
        self._calcular = calcular
        self._tabelas: dict[str, list[int]] | None = None

    def _todas(self) -> dict[str, list[int]]:
        if self._tabelas is None:
            self._tabelas = self._calcular()
        return self._tabelas

    def __getitem__(self, chave: str) -> list[int]:
        return self._todas()[chave]

    def __iter__(self) -> Iterator[str]:
        return iter(self._todas())

    def __len__(self) -> int:
        return len(self._todas())

    def __bool__(self) -> bool:
        return True       # `tabelas or {}` nao pode forcar o calculo


# a tatica do marcador de decisao descartada (Carreira._descartar_decisao)
DESCARTADA = {"_descartada": True}


def _descartada(d: Decisao) -> bool:
    return d.tatica == DESCARTADA


def _ordem_da_decisao(chave: str) -> tuple[int, int, int]:
    """(temporada, rodada da janela, data em que foi tomada) de "2027:5@14"; a chave antiga
    "2027:5" e de antes da data, -1."""
    janela, _, data = str(chave).partition("@")
    temporada, rodada = janela.split(":")
    return int(temporada), int(rodada), int(data) if data else -1


@dataclass(slots=True)
class Decisao:
    escalacao: list[int] = field(default_factory=list)
    tatica: dict = field(default_factory=lambda: asdict(Tatica()))


@dataclass(slots=True)
class Humano:
    """Um tecnico de carne e osso: o clube, as decisoes e tudo o que so ele ve e decide.

    Era tudo campo da Carreira, porque a carreira tinha um usuario so. Para jogar online
    (ate oito no mesmo mundo) o que e de cada um mora aqui; a Carreira guarda a lista em
    `humanos` e expoe o ativo pelos nomes de sempre (`c.clube_id`, `c.convites`...).
    """

    clube_id: int
    decisoes: dict[str, Decisao] = field(default_factory=dict)
    # A sala de trofeus (fm.telas.sala_de_trofeus): os recordes dos jogos do tecnico e as
    # lendas de cada clube que ele dirigiu. Derivados do replay, como o resto: nao vao ao
    # save.
    recordes: dict = field(default_factory=dict)
    lendas: dict = field(default_factory=dict)
    aprovacao: object | None = None
    treinador: str = "Treinador"
    # O que o usuario fez DURANTE cada partida, por "temporada:data": trocas e mudancas de
    # tatica, com o minuto. Sem isto o replay do save jogava sem as substituicoes e o
    # placar carregado divergia do placar jogado.
    na_partida: dict[str, dict] = field(default_factory=dict)
    # Capitao e cobradores. O motor le os de falta, escanteio e penalti (penaltis,
    # penaltis2, penaltis3); o capitao e so a braçadeira.
    funcoes: dict[str, int] = field(default_factory=dict)
    # a lista de observacao do mercado
    observados: list[int] = field(default_factory=list)
    # A tatica escolhida vale ate a proxima mudanca, e nao so na rodada em que foi feita.
    # Saves de antes disto jogavam a rodada sem decisao no padrao, e o replay deles
    # precisa continuar jogando assim -- por isso a regra nova e uma marca do save.
    tatica_persistente: bool = True
    # A selecao que o usuario treina (o pais), o convite em aberto, e o que ele decidiu
    # para ela: a convocacao, o onze e a tatica (vazio = a IA decide). Tudo isso vem das
    # acoes gravadas (`executar`), entao o replay refaz igual.
    selecao_do_usuario: str | None = None
    convite_selecao: str | None = None
    convocacao_do_usuario: list[int] = field(default_factory=list)
    escalacao_da_selecao: list[int] = field(default_factory=list)
    tatica_da_selecao: dict = field(default_factory=dict)
    # a selecao que dispensou o usuario (nao se classificou para a Copa), para a mensagem
    demissao_da_selecao: str | None = None
    # o usuario saiu do clube por conta propria (a tela nao diz "voce foi demitido")
    pediu_demissao: bool = False
    # os jogos da selecao do usuario no ano, por data -- a parte dos do clube (a campanha
    # do clube nao mistura com a da selecao)
    jogos_da_selecao: dict = field(default_factory=dict)
    competicoes_da_selecao: dict = field(default_factory=dict)
    # o boletim da ultima data do usuario: [(id, tipo, jogos)] de quem se machucou e
    # [id] de quem voltou. E o que as mensagens do departamento medico mostram.
    boletim_medico: dict = field(default_factory=dict)
    propostas: list = field(default_factory=list)        # recebidas no ano (fm.negocios)
    movimentos: list[dict] = field(default_factory=list)  # historico de entradas e saidas
    # o onze que o usuario ESCOLHEU, guardado enquanto a data corre com o reserva no lugar
    # do suspenso -- depois da data ele volta, e o suspenso volta sozinho quando cumprir
    _onze_pretendido: list[int] = field(default_factory=list)
    # clubes que chamam o usuario agora (na virada ou depois de uma demissao) e as vagas
    # que a IA preenche na proxima data
    convites: list[int] = field(default_factory=list)
    # o clube em que a carreira COMECOU: o replay parte dele, e as trocas sao acoes
    clube_inicial: int | None = None
    # o jogo do usuario em cada data do ano: {data: Result}. O calendario e os ultimos
    # jogos leem daqui -- em ordem, e com as copas, que a tabela da liga nao tem
    jogos_do_usuario: dict = field(default_factory=dict)
    # o resumo de cada temporada que ele fechou (o que a tela de fim de ano mostrou)
    historico: list[dict] = field(default_factory=list)
    # Durante a partida da selecao, e ate a data seguinte: (id da selecao, mundo das
    # selecoes). E por aqui que a tela ao vivo, o banco e as trocas sabem qual e o "meu
    # time" -- no resto do tempo, o clube.
    _em_campo: tuple | None = field(default=None, repr=False, compare=False)
    # a partida dele na ultima data jogada (motor de eventos), para a tela; nao vai ao save
    partida_da_data: object = field(default=None, repr=False, compare=False)
    # o id dele em `tecnicos` (fm.tecnicos): o primeiro humano e o USUARIO de sempre
    tecnico_id: int = 0


@dataclass(slots=True)
class Carreira:
    """A carreira roda sobre a PIRAMIDE inteira, nao sobre uma liga.

    Acesso e rebaixamento exigem as divisoes no mesmo mundo: nao da para promover um clube
    para um lugar que nao existe. Por isso `ligas` e uma lista, todas avancam juntas rodada
    a rodada, e o clube do usuario pode mudar de divisao entre as temporadas.
    """

    seed: int
    ligas: list[str]
    temporada: int
    # Os tecnicos humanos (fm.carreira.Humano) e qual deles esta com o controle. No
    # jogo de um so, um humano; online, ate oito no mesmo mundo. Os nomes de antes
    # (clube_id, decisoes, convites...) continuam: sao atalhos para o humano ativo.
    humanos: list = field(default_factory=list)
    ativo: int = 0
    rodada: int = 0
    world: World | None = None
    calendarios: dict[str, list[Fixture]] = field(default_factory=dict)
    resultados: dict[str, list[Result]] = field(default_factory=dict)
    streams: Streams | None = None
    # A temporada e uma lista de DATAS, nao so de rodadas: domingo tem liga, quarta tem
    # copa. E o que faz poupar um titular ser uma decisao em vez de um detalhe.
    agenda: list[tuple[str, str]] = field(default_factory=list)
    data: int = 0
    # o calendario real de cada data (fm.agenda): o dia, a fase de copa para a qual ela foi
    # reservada e se e uma sobra do fim (so acontece se a copa atrasou)
    dias: list = field(default_factory=list)
    fases_da_agenda: list[int] = field(default_factory=list)
    reservas: list[bool] = field(default_factory=list)
    # cada liga tem as SUAS rodadas dentro da grade comum: {liga: {data de liga: rodada}}
    rodada_propria: dict[str, dict[int, int]] = field(default_factory=dict)
    ultimo_dia_de_energia: object = None
    # O retrato da carreira no comeco da temporada em curso (pickle), tirado na virada. O
    # `salvar` grava ao lado do save; o `carregar` parte dele e refaz so o ano em curso.
    retrato: bytes | None = field(default=None, repr=False)
    copas: dict = field(default_factory=dict)
    tabelas_do_ano_anterior: dict = field(default_factory=dict)
    # o funil entre torneios: quem cai da pre da Libertadores vai para a Sudamericana
    exportados: dict = field(default_factory=dict)
    # o que foi jogado na ultima data. A agenda pula datas de copa ja encerrada, entao
    # quem chama nao consegue deduzir isso do compromisso que leu antes de avancar.
    ultimo_compromisso: tuple[str, str] = ("", "")
    valor_de_elenco: dict = field(default_factory=dict)
    estatisticas: object | None = None
    # os outros jogos da data, ja resolvidos, enquanto a partida do usuario ainda corre:
    # e o painel "rodada ao vivo"
    parciais: list = field(default_factory=list)
    # os lances (gols com autor e minuto, cartoes, trocas) dos jogos do motor rapido na data
    # que esta sendo jogada, por (mandante, visitante). E a central da rodada.
    lances_da_data: dict = field(default_factory=dict)
    # quem decide o batedor na hora do penalti, so durante um avancar(); nao vai ao save
    _pedido_de_penalti: object = field(default=None, repr=False, compare=False)
    # no meio de um avancar() -- a partida ao vivo roda numa thread e pode ser salva no
    # intervalo: ai o estado e de meia data e nao vira ponto do save
    _no_meio_da_data: bool = field(default=False, repr=False, compare=False)
    # um caderno de artilharia por competicao ("brasil_real", "libertadores"...) no ano
    estatisticas_por_comp: dict = field(default_factory=dict)
    # {liga: {rodada: selecao}} -- a selecao de cada rodada de liga do ano (fm.selecao)
    selecoes: dict = field(default_factory=dict)
    # cartoes acumulados e suspensoes, por competicao (fm.disciplina)
    disciplina: object | None = None
    # as selecoes, as eliminatorias e a Copa do Mundo (fm.fifa): atravessa as temporadas
    fifa: object | None = None
    # quantos jogos de tecnico humano ja sairam na data FIFA em curso: o primeiro usa o
    # fluxo de sempre da partida da selecao, os outros um fluxo por jogo
    _humanos_na_data: int = field(default=0, repr=False, compare=False)
    # quem esta machucado e por quantos jogos (fm.lesoes). Como o gancho, nao vai ao
    # save: o replay refaz as mesmas lesoes.
    medico: object | None = None
    # Negocios do usuario (fm.negocios): compra, renovacao, venda e resposta a proposta,
    # cada um com a temporada e a data em que aconteceu. E isto que o save guarda e o
    # replay reaplica no mesmo ponto -- o resto dos negocios e deterministico.
    acoes: list[dict] = field(default_factory=list)
    # Os tecnicos do mundo (fm.tecnicos), o usuario com id 0. Gerados pela seed e
    # atualizados na virada: nao vao ao save, o replay refaz.
    tecnicos: dict = field(default_factory=dict)
    vagas: list[int] = field(default_factory=list)
    premios: dict = field(default_factory=dict)          # {temporada: premios do ano}
    # ligas no mundo sem calendario (LIGAS_DA_CONFEDERACAO): derivadas, nao vao ao save
    ligas_de_fora: list[str] = field(default_factory=list)

    @classmethod
    def nova(cls, ligas: list[str] | str, clube: str, seed: int = 2027,
             outros: list[str] | None = None,
             treinadores: list[str] | None = None) -> Carreira:
        """A carreira nova, com o clube do primeiro tecnico humano e, em `outros`, os dos
        demais (ate MAX_HUMANOS ao todo, cada um num clube). `treinadores` sao os nomes,
        na mesma ordem; quem chama pode troca-los antes da primeira data."""
        if isinstance(ligas, str):
            ligas = [ligas]
        cfgs = [load_league(n) for n in ligas]
        world, streams = build_world(cfgs, seed=seed)
        nomes_dos_clubes = [clube, *(outros or [])]
        if len(nomes_dos_clubes) > MAX_HUMANOS:
            raise ValueError(f"no maximo {MAX_HUMANOS} tecnicos por carreira")
        alvos = []
        for nome in nomes_dos_clubes:
            alvo = next((c for c in world.clubs.values()
                         if c.name.lower() == nome.lower()), None)
            if alvo is None:
                nomes = sorted(c.name for c in world.clubs.values())
                raise ValueError(f"clube {nome!r} nao esta em {ligas}. Ha: {nomes}")
            if any(a.id == alvo.id for a in alvos):
                raise ValueError(f"dois tecnicos no {alvo.name}: cada um tem o seu clube")
            alvos.append(alvo)
        humanos = [Humano(clube_id=a.id, tecnico_id=i) for i, a in enumerate(alvos)]
        for h, nome in zip(humanos, treinadores or [], strict=False):
            h.treinador = nome
        c = cls(seed=seed, ligas=list(ligas), temporada=world.season_year, humanos=humanos)
        c._montar(world, streams)
        return c

    def _montar(self, world: World, streams: Streams) -> None:
        from fm.tecnicos import gerar
        self.world = world
        self.streams = streams
        for h in self.humanos:
            if h.clube_inicial is None:
                h.clube_inicial = h.clube_id
        if self.fifa is None:
            from fm.fifa import Fifa
            self.fifa = Fifa()
        self._carregar_ligas_de_fora()
        self._novo_calendario()
        self.tecnicos = gerar(world, {self._id(n) for n in self.ligas},
                              streams.get("tecnicos"), self.temporada,
                              [h.clube_id for h in self.humanos],
                              [h.treinador for h in self.humanos])
        for i in range(len(self.humanos)):
            with self._como(i):
                self.convidar_para_selecao()

    # ---------------------------------------------------------------- os humanos

    @contextmanager
    def _como(self, i: int) -> Iterator[Humano]:
        """Faz a conta como o humano `i`: dentro do bloco, `c.clube_id`, `c.decisoes`... sao
        os dele. So nesta thread -- a tela continua vendo o ativo."""
        pilha = getattr(_VEZ, "de", None)
        if pilha is None:
            pilha = _VEZ.de = {}
        chave = id(self)
        antes = pilha.get(chave)
        pilha[chave] = i
        try:
            yield self.humanos[i]
        finally:
            if antes is None:
                pilha.pop(chave, None)
            else:
                pilha[chave] = antes

    @property
    def humano(self) -> Humano:
        """O humano da vez: o ativo, ou aquele por quem a carreira esta fazendo a conta."""
        return self.humanos[_vez(self)]

    def clubes_humanos(self) -> set[int]:
        """Os clubes de tecnico humano. A IA nao compra deles nem mexe no elenco deles."""
        return {h.clube_id for h in self.humanos}

    def _humanos_em_campo(self) -> list[int]:
        """Os humanos que dirigem um clube nesta data: todos. O demitido continua com o
        clube dele ate assumir outro -- e o que a carreira de um tecnico so sempre fez, e
        o que o teste de vinte temporadas (que avanca demitido) mede."""
        return list(range(len(self.humanos)))

    def _clubes_de_outros(self) -> set[int]:
        """Os clubes dos OUTROS humanos, demitidos inclusive: nenhum deles e convite."""
        return {h.clube_id for h in self.humanos if h is not self.humano}

    def _fluxo(self, *chave):
        """O fluxo aleatorio de uma decisao do humano da vez. O primeiro usa a chave de
        sempre (a carreira de um tecnico so nao muda); os outros, a dele."""
        tid = self.humano.tecnico_id
        return self.streams.get(*chave) if tid == 0 else self.streams.get(*chave, "tecnico", tid)

    def _gravar_acao(self, acao: dict) -> None:
        """A acao vai ao save com a data -- e com o humano que a fez, quando nao e o primeiro."""
        i = _vez(self)
        self.acoes.append({**acao, "temporada": self.temporada, "data": self.data,
                           **({"humano": i} if i else {})})

    def _novo_calendario(self) -> None:
        self.calendarios = {}
        self.resultados = {}
        for nome in self.ligas:
            lid = load_league(nome)["id"]
            rng = self.streams.get("calendario", self.temporada, lid)
            ids = list(world_ids := self.world.leagues[lid].club_ids)
            rng.shuffle(ids)                      # sorteio da tabela a cada temporada
            # turno e returno, salvo quando a liga diz outra coisa (a Argentina, com 30 e
            # 36 clubes, joga turno unico: senao seriam 58 e 70 rodadas)
            fases = load_league(nome).get("formato", {}).get("fases", [{}])
            voltas = int(fases[0].get("voltas", 2)) if fases else 2
            self.calendarios[nome] = round_robin(ids, legs=voltas)
            self.resultados[nome] = []
            assert world_ids is not None
        self.data = 0
        for h in self.humanos:
            h.jogos_do_usuario = {}
            h.jogos_da_selecao = {}
            h.competicoes_da_selecao = {}
            h.boletim_medico = {}
        self._montar_agenda()
        # o valor de elenco do INICIO do ano e o que paga a receita: sem congelar, comprar
        # jogador aumentaria o faturamento do mesmo ano e o clube rico viraria bola de neve
        from fm.financas import valor_do_elenco
        self.valor_de_elenco = {c.id: valor_do_elenco(self.world, c.id)
                                for c in self.world.clubs.values()}
        for i in range(len(self.humanos)):
            with self._como(i):
                self._nova_meta()
        from fm.estatisticas import Estatisticas
        self.estatisticas = Estatisticas(temporada=self.temporada)
        self.estatisticas_por_comp = {}
        self.selecoes = {}
        from fm.disciplina import Disciplina
        self.disciplina = Disciplina()      # gancho nao atravessa a virada do ano
        from fm.lesoes import DepartamentoMedico
        self.medico = DepartamentoMedico()  # a pre-temporada cura todo mundo
        self.world.indisponiveis = set()

    def _montar_agenda(self) -> None:
        """O calendario real da temporada (fm.agenda): ligas aos domingos, de abril a
        dezembro, e cada fase de copa na janela dela, no meio de semana.

        As copas nao tem numero fixo de etapas -- depende do sorteio e de quantos clubes o
        mundo tem importados -- entao cada fase reserva datas pela estimativa e a sobra e
        pulada. Se uma fase precisar de mais, ela usa as datas da fase seguinte, e no fim
        do ano ha duas datas de reserva por copa.
        """
        from fm.agenda import clubes_por_fase, etapas_por_fase, montar
        from fm.copa import comecar
        from fm.fifa import bloqueios, dias_de_selecao
        from fm.torneio import carregar, resolver_entradas

        self.copas = {}
        ocupados: set[int] = set()
        tabelas = self.tabelas_do_ano_anterior or self._tabelas_por_forca()
        for nome in self.copas_do_pais():
            try:
                t = carregar(nome)
            except FileNotFoundError:
                continue
            # So as copas que DISPUTAM vaga entre si dividem `ocupados` (quem esta na
            # Champions nao entra na Liga Europa). REGRESSAO: as supercopas tambem
            # dividiam, e a Recopa de 2028 ficou com Fortaleza x Sport em vez dos campeoes
            # -- que ja estavam na Libertadores; e quem entrava na Supercopa do Brasil
            # perdia a vaga na Libertadores.
            self.copas[nome] = comecar(self.world, t, tabelas,
                                       ocupados=ocupados if nome in DISPUTAM_VAGA else set())

        copas = {}
        for nome, a in self.copas.items():
            entram = [len(a.vivos) if k == 0 else 0 for k in range(len(a.torneio.fases))]
            for k, fase in enumerate(a.torneio.fases):
                entram[k] += len(resolver_entradas(self.world, fase.get("entram", []),
                                                   tabelas, a.classificados))
            n = clubes_por_fase(a.torneio, entram)
            copas[nome] = list(zip(a.torneio.fases, etapas_por_fase(a.torneio, n),
                                    strict=True))

        rodadas = {nome: max((f.matchday for f in cal), default=0)
                   for nome, cal in self.calendarios.items()}
        datas, mapa = montar(self.temporada, rodadas, copas,
                             dias_de_selecao(self.temporada), bloqueios(self.temporada))
        self.agenda = [(d.tipo, d.quem) for d in datas]
        self.dias = [d.dia for d in datas]
        self.fases_da_agenda = [d.fase for d in datas]
        self.reservas = [d.reserva for d in datas]
        # a rodada k de cada liga vai para a data de liga mapa[liga][k-1]: o `matchday` do
        # jogo passa a ser o numero da DATA DE LIGA, que e o que o relogio da carreira conta
        self.rodada_propria = {}
        for nome, cal in self.calendarios.items():
            global_de = {k + 1: g + 1 for k, g in enumerate(mapa.get(nome, []))}
            self.calendarios[nome] = [Fixture(f.home, f.away, global_de.get(f.matchday, f.matchday))
                                      for f in cal]
            self.rodada_propria[nome] = {g: k for k, g in global_de.items()}
        self.ultimo_dia_de_energia = None

    def dia(self, indice: int | None = None):
        """O dia de uma data da agenda (a proxima, se nao disser qual)."""
        i = self.data if indice is None else indice
        if not self.dias:
            return dia_da_data(self.temporada, i)
        if i < len(self.dias):
            return self.dias[i]
        from datetime import timedelta
        return self.dias[-1] + timedelta(days=4 * (i - len(self.dias) + 1))

    def rodada_da_liga(self, liga: str | None = None, data_de_liga: int | None = None) -> int:
        """A rodada DA LIGA (a 11a do Brasileirao) numa data de liga da grade -- ou, sem a
        data, quantas rodadas dela ja foram jogadas."""
        propria = self.rodada_propria.get(liga or self.liga, {})
        if data_de_liga is not None:
            return propria.get(data_de_liga, 0)
        return sum(1 for g in propria if g <= self.rodada)

    def copas_do_pais(self) -> tuple[str, ...]:
        """As competicoes de copa dos paises que esta carreira roda, sem repetir."""
        fora: list[str] = []
        for nome in self.ligas:
            for copa in COPAS_POR_PAIS.get(load_league(nome).get("pais", ""), ()):
                if copa not in fora:
                    fora.append(copa)
        return tuple(fora)

    def _nova_meta(self) -> None:
        """A diretoria cobra uma meta por temporada, pela forca do elenco."""
        from fm.diretoria import Aprovacao, definir_meta

        cfg = load_league(self.liga)
        meta = definir_meta(self.world, self.clube_id,
                            list(self.world.leagues[cfg["id"]].club_ids),
                            int(cfg.get("tier", 1)))
        if self.aprovacao is None:
            self.aprovacao = Aprovacao()
        self.aprovacao.meta = meta

    def _meus_ultimos(self, quantos: int) -> list[str]:
        """V/E/D dos ultimos jogos do clube, em qualquer competicao."""
        fora: list[str] = []
        jogos = list(self.jogos())
        for a in self.copas.values():
            jogos += a.resultados_do_ano
        for r in jogos[-quantos * 3:]:
            if self.clube_id not in (r.home, r.away):
                continue
            meus = r.goals_home if r.home == self.clube_id else r.goals_away
            deles = r.goals_away if r.home == self.clube_id else r.goals_home
            fora.append("V" if meus > deles else "E" if meus == deles else "D")
        return fora[-quantos:]

    def avaliar_clima(self) -> object:
        """Atualiza torcida e diretoria com a situacao de agora."""
        from fm.diretoria import JOGOS_DE_MEMORIA, avaliar
        from fm.financas import folha_anual, receita_anual

        cfg = load_league(self.liga)
        tabela = self.tabela()
        clubes = len(tabela)
        posicao = self.posicao() if tabela else clubes
        campanhas = [(a.etapas_vividas[self.clube_id], a.etapas_totais,
                      a.esta_vivo(self.clube_id) and not a.acabou)
                     for a in self.copas.values()
                     if self.clube_id in a.etapas_vividas and a.etapas_totais]
        titulos = sum(1 for a in self.copas.values() if a.campeao == self.clube_id)
        receita = receita_anual(self.world, self.clube_id, int(cfg.get("tier", 1)),
                                self.valor_de_elenco.get(self.clube_id))
        folha = folha_anual(self.world, self.clube_id)
        return avaliar(
            self.aprovacao, posicao=posicao, clubes=clubes,
            ultimos=self._meus_ultimos(JOGOS_DE_MEMORIA),
            campanhas=campanhas, titulos=titulos,
            saldo=receita - folha, receita=receita,
            caixa=self.clube.balance, folha=folha)

    def _checar_emprego(self, fim_da_temporada: bool = False,
                        rebaixado: bool = False) -> None:
        """Atualiza o clima e, se for o caso, encerra o trabalho no clube."""
        from fm.diretoria import decidir_demissao

        self.avaliar_clima()
        ap = self.aprovacao
        ap.historico.append((self.temporada, self.data, round(ap.torcida, 1),
                             round(ap.diretoria, 1)))
        tabela = self.tabela()
        motivo = decidir_demissao(
            self.aprovacao, rodada=self.rodada, fim_da_temporada=fim_da_temporada,
            posicao=self.posicao() if tabela else len(tabela),
            clubes=len(tabela) or 20, rebaixado=rebaixado)
        if motivo and not self.aprovacao.demitido:
            self.aprovacao.demitido = True
            self.aprovacao.motivo = motivo
            self._ao_ser_demitido(meio_do_ano=True)

    def pedir_demissao(self) -> dict:
        """O usuario sai do clube por conta propria: a reputacao cai menos que numa
        demissao, e chamam os mesmos clubes que chamariam um demitido no meio do ano. A
        selecao, se ele treinar uma, continua com ele."""
        if self.demitido:
            return {"erro": "voce ja nao esta no clube"}
        if self.aprovacao is None:
            self._nova_meta()
        self.aprovacao.demitido = True
        self.aprovacao.motivo = (f"Você pediu demissão do {self.clube.name}.")
        self.pediu_demissao = True
        self._ao_ser_demitido(meio_do_ano=True, pedida=True)
        return {"ok": True, "mensagem": self.aprovacao.motivo,
                "convites": list(self.convites)}

    def _ao_ser_demitido(self, meio_do_ano: bool, pedida: bool = False) -> None:
        """A demissao nao encerra a carreira: a reputacao cai e aparecem convites. No meio
        do ano quem chama sao os clubes em crise (o tecnico deles sai para o usuario
        entrar); na virada, as vagas que a IA abriu."""
        from fm import tecnicos as tec
        eu = self.tecnicos.get(self.humano.tecnico_id)
        if eu is None:
            return
        tec.ajustar(eu, tec.DEMISSAO_PEDIDA if pedida else tec.DEMISSAO)
        eu.clube = None
        if self.clube_id not in self.vagas:
            self.vagas.append(self.clube_id)
        if meio_do_ano:
            outros = self._clubes_de_outros()
            candidatos = [k for k in self._clubes_em_crise() if k not in outros]
            self.convites = tec.convites(self.world, self.tecnicos, candidatos, None, True,
                                         [k for k in self._clubes_da_ultima_divisao()
                                          if k not in outros],
                                         self._fluxo("convites", self.temporada, self.data),
                                         usuario=eu.id)

    def _clubes_em_crise(self) -> list[int]:
        """Os 40% de baixo de cada tabela, com tecnico do computador."""
        humanos = self.clubes_humanos()
        fora = []
        for nome in self.ligas:
            tabela = self.tabela(nome)
            corte = int(len(tabela) * 0.6)
            fora += [ln.club_id for ln in tabela[corte:] if ln.club_id not in humanos]
        return fora

    def _clubes_da_ultima_divisao(self) -> list[int]:
        ultima = max(self.ligas, key=lambda n: int(load_league(n).get("tier", 1)))
        return list(self.world.leagues[self._id(ultima)].club_ids)

    def _assumir(self, clube: int) -> None:
        """O usuario troca de clube. O tecnico que estava la fica desempregado; o clube
        que ele deixou ganha tecnico da IA na proxima data."""
        from fm import tecnicos as tec
        antigo = self.clube_id
        outro = tec.do_clube(self.tecnicos, clube)
        if outro is not None and not outro.usuario:
            outro.clube = None
        eu = self.tecnicos[self.humano.tecnico_id]
        eu.clube = clube
        # o clube tem tecnico de novo: o convite dele aos outros humanos acabou
        for h in self.humanos:
            if h is not self.humano and clube in h.convites:
                h.convites = [k for k in h.convites if k != clube]
        eu.passagens.append([self.temporada, self.world.clubs[clube].name])
        if antigo != clube and antigo not in self.vagas:
            self.vagas.append(antigo)
        self.vagas = [v for v in self.vagas if v != clube]
        for x in (antigo, clube):
            self.world.escalacao_fixa.pop(x, None)
            self.world.formacao_fixa.pop(x, None)
        self.clube_id = clube
        self._descartar_decisao()
        self.funcoes, self.observados, self._onze_pretendido = {}, [], []
        self.boletim_medico = {}
        for prop in self.propostas:
            if prop.status == "pendente":
                prop.status = "expirada"
        # diretoria nova, meta nova, clima zerado
        self.aprovacao = None
        self.pediu_demissao = False
        self._nova_meta()
        self.convites = []

    @property
    def demitido(self) -> bool:
        return bool(self.aprovacao and self.aprovacao.demitido)

    # ---------------------------------------------------------------- premios e tecnicos

    def _copas_ganhas(self) -> dict[int, list[str]]:
        fora: dict[int, list[str]] = {}
        for nome, a in self.copas.items():
            if a.campeao is not None:
                fora.setdefault(a.campeao, []).append(nome)
        return fora

    def _campanhas_nas_copas(self) -> dict[int, list[tuple[str, str]]]:
        """Quem chegou a final (o vice) e a semifinal sem ganhar, por copa."""
        fora: dict[int, list[tuple[str, str]]] = {}
        for nome, a in self.copas.items():
            if a.vice is not None:
                fora.setdefault(a.vice, []).append((nome, "final"))
            # a semifinal: a ultima rodada de mata-mata com quatro clubes
            semi = next((f for f in reversed(a.historico) if f.get("tipo") == "mata"
                         and len(f.get("pares", [])) == 2 and not f.get("poupados")), None)
            if semi is not None:
                for k in {x for par in semi["pares"] for x in par} - {a.campeao, a.vice}:
                    fora.setdefault(k, []).append((nome, "semi"))
        return fora

    def _premios_e_desempenho(self, tabelas: dict, cfgs: dict) -> tuple[dict, dict]:
        """Chamado na virada, ANTES do acesso e do mercado: os premios sao do ano que
        acabou, com os clubes de agora."""
        from fm import premios as pr
        from fm import tecnicos as tec
        from fm.telas import nome_da_liga
        tiers = {n: int(cfgs[n].get("tier", 1)) for n in self.ligas}
        dados = tec.desempenho(tabelas, tiers, self.valor_de_elenco)
        ligas = {n: {"nome": nome_da_liga(n), "tier": tiers[n],
                     "clubes": set(self.world.leagues[self._id(n)].club_ids),
                     "rodadas": self.rodadas_da_liga(n)} for n in self.ligas}
        campeoes = {n: t[0].club_id for n, t in tabelas.items() if t}
        for t in self.tecnicos.values():
            t.variacao = 0.0                 # a variacao mostrada e a DESTE ano
        do_ano: dict[str, int | None] = {}
        for n in self.ligas:
            melhor = max((d for d in dados.values() if d.liga == n),
                         key=lambda d: (d.saldo, -d.final), default=None)
            t = tec.do_clube(self.tecnicos, melhor.clube) if melhor else None
            do_ano[n] = t.id if t else None
            if t is not None:
                tec.ajustar(t, tec.TECNICO_DO_ANO)
        premios = pr.calcular(self.world, self.temporada, self.estatisticas,
                              self.estatisticas_por_comp, ligas, campeoes,
                              self._copas_ganhas(), do_ano)
        pr.aplicar_moral(self.world, premios)
        self.premios[self.temporada] = premios
        return premios, dados

    def _atualizar_tecnicos(self, dados: dict, mudancas, cfgs: dict) -> None:
        from fm import tecnicos as tec
        from fm.telas import nome_da_liga
        for m in mudancas:
            if m.clube in dados:
                dados[m.clube].subiu = m.subiu
                dados[m.clube].caiu = not m.subiu
        nomes_das_copas = {k: a.torneio.nome for k, a in self.copas.items()}
        # a variacao anterior (o premio de tecnico do ano) entra na conta do ano
        bonus = {t.id: t.variacao for t in self.tecnicos.values()}
        tec.atualizar_reputacoes(self.tecnicos, dados, self._copas_ganhas(), nomes_das_copas,
                                 {n: nome_da_liga(n) for n in self.ligas}, self.temporada,
                                 estatura={k: float(c.reputation)
                                           for k, c in self.world.clubs.items()},
                                 campanhas=self._campanhas_nas_copas())
        for t in self.tecnicos.values():
            t.variacao = round(t.variacao + bonus.get(t.id, 0.0), 1)

    def _mercado_de_tecnicos(self, dados: dict) -> None:
        """Fim da virada: a IA demite, cada humano demitido perde reputacao, e as vagas
        viram convites -- um humano por vez, na ordem deles."""
        from fm import tecnicos as tec
        self.vagas = tec.demissoes_da_ia(self.tecnicos, dados,
                                         self.streams.get("demissoes_da_ia", self.temporada))
        for i in range(len(self.humanos)):
            with self._como(i):
                self._convites_da_virada(dados)

    def _convites_da_virada(self, dados: dict) -> None:
        from fm import tecnicos as tec
        eu = self.humano.tecnico_id
        demitido = self.demitido
        if demitido:
            self._ao_ser_demitido(meio_do_ano=False)
        # o clube que acabou de demitir o usuario nao o chama de volta
        candidatos = [v for v in self.vagas if not (demitido and v == self.clube_id)]
        candidatos += tec.assediam(self.world, self.tecnicos, dados,
                                   None if demitido else self.clube_id, usuario=eu)
        outros = self._clubes_de_outros()
        candidatos = [k for k in candidatos if k not in outros]
        reserva = [k for k in self._clubes_da_ultima_divisao()
                   if k != self.clube_id and k not in outros]
        self.convites = tec.convites(self.world, self.tecnicos, candidatos,
                                     None if demitido else self.clube_id, demitido, reserva,
                                     self._fluxo("convites", self.temporada), usuario=eu)

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
        fontes: dict[str, list[int]] = {**self._ranking_da_confederacao(), **titulos}
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

    def _penaltis_se_empatou(self, andamento, partida: Partida, cobradores=None,
                             rng=None) -> None:
        """O jogo decisivo do usuario no mata-mata (a volta, ou o jogo unico) terminou com
        o agregado empatado: disputa de penaltis com quem terminou em campo. Fica na
        partida (a tela acompanha cobranca a cobranca) e no andamento (a apuracao usa).
        `cobradores` e `rng` vem de quem chama quando o jogo e de mais de um humano."""
        from fm.disputa import disputar
        t = andamento.torneio
        if andamento.fase >= len(t.fases):
            return
        fase = t.fases[andamento.fase]
        if fase.get("tipo") != "knockout" or fase.get("visitante_avanca_empate"):
            return
        par = next((tuple(p) for p in andamento.pares
                    if {partida.casa, partida.fora} == set(p)), None)
        if par is None:
            return
        jogos = [r for r in andamento.resultados if {r.home, r.away} == set(par)]
        if len(jogos) + 1 < int(fase.get("maos", 2)):
            return                                  # e a ida: ainda falta a volta
        gols = {par[0]: 0, par[1]: 0}
        for r in jogos:
            gols[r.home] += r.goals_home
            gols[r.away] += r.goals_away
        gols[partida.casa] += partida.gols_casa
        gols[partida.fora] += partida.gols_fora
        if gols[par[0]] != gols[par[1]]:
            return
        rng = rng or self.streams.get("disputa", self.temporada, self.data)
        partida.disputa = disputar(self.world, partida.casa, partida.fora,
                                   partida.em_campo_casa, partida.em_campo_fora, rng,
                                   cobradores if cobradores is not None
                                   else {self.clube_id: self.cobradores()})
        andamento.disputas[(int(par[0]), int(par[1]))] = partida.disputa

    def _repassar_exportados(self, andamento) -> None:
        """Quem um torneio mandou para outro (o eliminado da terceira fase da Libertadores
        vai para a Sul-Americana, o 3o do grupo para o playoff dela) entra na lista de
        classificados do destino. As regras dizem de onde: `fonte = "libertadores:terceiros"`.
        Antes isto nunca acontecia na carreira, e essas vagas ficavam vazias."""
        for regra in andamento.torneio.classificacao_regras:
            fonte = regra.get("fonte", "")
            if ":" not in fonte:
                continue
            chegaram = self.exportados.get(fonte, [])
            lista = andamento.classificados.setdefault(regra.get("entra_em", "grupos"), [])
            for cid in chegaram[:int(regra.get("vagas", len(chegaram)))]:
                if cid not in lista and cid not in andamento.vivos:
                    lista.append(cid)
                    # o 2o do grupo da Sul-Americana ja "entrou" nela -- e volta pelo
                    # playoff. A trava de quem ja entrou (fm.copa) e para outro caso
                    andamento.ja_entraram.discard(cid)

    def _esperando_outro_torneio(self, andamento) -> bool:
        """A proxima fase depende de quem outro torneio ainda nao mandou (`aguarda`)?
        So espera se o torneio que manda existe e ainda nao acabou -- nunca para sempre."""
        if andamento.pendentes or andamento.fase >= len(andamento.torneio.fases):
            return False
        chave = andamento.torneio.fases[andamento.fase].get("aguarda")
        if not chave or chave in self.exportados:
            return False
        return any(not a.acabou and a is not andamento
                   and any(f"{a.torneio.id}:{r.get('para')}" == chave for f in a.torneio.fases
                           for r in f.get("exporta", []))
                   for a in self.copas.values())

    def _premiar_copas(self) -> dict[int, int]:
        """Premiacao de copa por CAMPANHA: cada clube leva pelo quanto avancou.

        Antes so campeao e vice recebiam, e ai chegar as oitavas da Libertadores era
        prejuizo -- os jogos custavam e nada entrava.
        """
        from fm.financas import premio_de_campanha

        fora: dict[int, int] = {}
        for nome, a in self.copas.items():
            for cid, etapas in a.etapas_vividas.items():
                valor = premio_de_campanha(nome, etapas, a.etapas_totais,
                                           campeao=(cid == a.campeao),
                                           vice=(cid == a.vice))
                if valor:
                    fora[cid] = fora.get(cid, 0) + valor
        return fora

    def _carregar_ligas_de_fora(self) -> None:
        """Os clubes das ligas que a carreira nao joga: primeiro as da confederacao (os
        rivais da Libertadores), depois o resto do mundo (07/10/2026), porque a selecao e
        feita de quem joga em qualquer lugar -- a do Brasil sem quem esta na Europa nao e
        a do Brasil. Depois das ligas da carreira, com ids novos: os clubes e jogadores
        de sempre nao mudam de id."""
        from fm.generate import generate_league
        from fm.telas import NACIONAIS
        confederacoes = {COPAS_DA_CONFEDERACAO[c] for c in self.copas_do_pais()
                         if c in COPAS_DA_CONFEDERACAO}
        self.ligas_de_fora = [n for conf in sorted(confederacoes)
                              for n in LIGAS_DA_CONFEDERACAO[conf] if n not in self.ligas]
        self.ligas_de_fora += [liga for n in NACIONAIS for liga, _ in n["ligas"]
                               if liga and liga not in self.ligas
                               and liga not in self.ligas_de_fora]
        for nome in self.ligas_de_fora:
            cfg = load_league(nome)
            if cfg["id"] in self.world.leagues:
                continue
            proximo = [max(max(self.world.clubs, default=0),
                           max(self.world.players, default=0)) + 1]
            generate_league(self.world, cfg, self.streams, next_id=proximo)

    def _simular_ligas_de_fora(self) -> dict[str, list]:
        """A temporada das ligas de fora, inteira, no motor rapido: e a tabela delas que
        classifica para as copas do ano que vem. Fluxo proprio por liga e ano."""
        from fm.table import build_table
        fora = {}
        for nome in self.ligas_de_fora:
            cfg = load_league(nome)
            ids = list(self.world.leagues[cfg["id"]].club_ids)
            voltas = int((cfg.get("formato", {}).get("fases") or [{}])[0].get("voltas", 2))
            ratings = {k: float(effective_rating(self.world.team_rating(k))) for k in ids}
            rng = self.streams.get("liga_de_fora", self.temporada, cfg["id"])
            resultados = play_fixtures(round_robin(ids, legs=voltas), ratings, rng,
                                       style_of(cfg))
            fora[nome] = build_table(ids, resultados)
        return fora

    def _forca_memorizada(self) -> Callable[[int], float]:
        """`team_rating` com memoria, para UMA consulta: o ranking da confederacao e a
        tabela da liga perguntam a forca do mesmo clube, e cada pergunta escolhe o onze."""
        nivel: dict[int, float] = {}

        def forca(cid: int) -> float:
            if cid not in nivel:
                nivel[cid] = self.world.team_rating(cid)
            return nivel[cid]
        return forca

    def _ranking_da_confederacao(self, forca: Callable[[int], float] | None = None
                                 ) -> dict[str, list[int]]:
        """"CONMEBOL": os clubes de primeira divisao da confederacao, do mais forte ao mais
        fraco. E a reserva das vagas de campeao da Libertadores e da Sul-Americana no
        primeiro ano da carreira, quando ainda nao ha campeao."""
        forca = forca or self._forca_memorizada()
        fora = {}
        for conf, ligas in LIGAS_DA_CONFEDERACAO.items():
            ids = [k for n in ligas if n in self.ligas or n in self.ligas_de_fora
                   for k in self.world.leagues[load_league(n)["id"]].club_ids]
            if ids:
                fora[conf] = sorted(ids, key=lambda k: (-forca(k), k))
        return fora

    def _tabelas_por_forca(self) -> dict[str, list[int]]:
        """Sem temporada anterior, a ordem por forca do elenco faz as vezes de tabela."""
        forca = self._forca_memorizada()
        fora: dict[str, list[int]] = self._ranking_da_confederacao(forca)
        for nome in [*self.ligas, *self.ligas_de_fora]:
            cfg = load_league(nome)
            ordem = sorted(self.world.leagues[cfg["id"]].club_ids,
                           key=lambda cid: -forca(cid))
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

    def rodadas_da_liga(self, liga: str | None = None) -> int:
        """Quantas rodadas tem UMA divisao. `total_de_rodadas` e a grade inteira -- com a
        Championship junto, sao 46 datas de liga e a Serie A tem so 38 delas."""
        return len({f.matchday for f in self.calendarios[liga or self.liga]})

    @property
    def acabou(self) -> bool:
        return self.data >= len(self.agenda)

    @property
    def compromisso(self) -> tuple[str, str] | None:
        """O que acontece na proxima data: a liga, ou uma etapa de copa."""
        return self.agenda[self.data] if not self.acabou else None

    def _chave(self, rodada: int | None = None) -> str:
        return f"{self.temporada}:{self.rodada + 1 if rodada is None else rodada}"

    @property
    def time_em_campo(self) -> int:
        """O time do usuario na partida em curso: a selecao, na data dela; senao o clube."""
        return self._em_campo[0] if self._em_campo else self.clube_id

    @property
    def mundo_em_campo(self) -> World:
        return self._em_campo[1] if self._em_campo else self.world

    def tatica_da_selecao_atual(self) -> Tatica:
        return Tatica(**self.tatica_da_selecao) if self.tatica_da_selecao else Tatica()

    def tatica_atual(self) -> Tatica:
        """A tatica da proxima rodada: a decidida para ela ou, se nao houver, a ultima que
        o treinador deixou -- mudar para 3-5-2 antes de um jogo nao volta ao 4-3-3 no
        seguinte. A mudanca feita DURANTE a partida fica na partida (`na_partida`)."""
        d = self._decisao_vigente()
        if d is None and self.tatica_persistente:
            d = self._ultima_decisao()
        return Tatica(**d.tatica) if d else Tatica()

    # As decisoes valem por JANELA -- as datas ate a proxima rodada de liga, copas no meio
    # -- e cada uma guarda a data em que foi tomada: "2027:5@14". Antes a chave era so a
    # janela ("2027:5"), e reescalar entre um jogo de copa e a rodada seguinte apagava o
    # que valeu na copa: o save ficava com a ultima e o replay jogava a copa diferente
    # (08/10/2026). Saves antigos, sem "@", contam como tomados no comeco da janela.

    def _decisao_vigente(self) -> Decisao | None:
        """A ultima decisao desta janela tomada ate a data de agora (None se nao ha, ou se
        foi descartada por troca de clube ou venda de quem estava no onze)."""
        janela = (self.temporada, self.rodada + 1)
        tomadas = [(o, k) for k in self.decisoes
                   if (o := _ordem_da_decisao(k))[:2] == janela and o[2] <= self.data]
        if not tomadas:
            return None
        d = self.decisoes[max(tomadas)[1]]
        return None if _descartada(d) else d

    def _ultima_decisao(self) -> Decisao | None:
        """A que valeu por ultimo numa janela anterior: e a tatica que persiste."""
        agora = (self.temporada, self.rodada + 1)
        final_de: dict[tuple[int, int], tuple] = {}
        for k in self.decisoes:
            o = _ordem_da_decisao(k)
            if o[:2] < agora and (o[:2] not in final_de or (o, k) > final_de[o[:2]]):
                final_de[o[:2]] = (o, k)
        for janela in sorted(final_de, reverse=True):
            d = self.decisoes[final_de[janela][1]]
            if not _descartada(d):
                return d
        return None

    def _descartar_decisao(self) -> None:
        """A decisao da janela deixa de valer DAQUI EM DIANTE. Ela pode ja ter valido numa
        data de copa: por isso nao se apaga -- grava-se um marcador nesta data."""
        if self._decisao_vigente() is not None:
            self.decisoes[f"{self._chave()}@{self.data}"] = Decisao([], dict(DESCARTADA))

    def escalacao_atual(self) -> list[int]:
        """O onze na ORDEM das vagas da formacao (fm.tatica.VAGAS).

        A escolha do usuario vem como ele deixou. O que sai da escalacao automatica -- ou
        de um save antigo, anterior as vagas -- e arrumado no campo: sem isso o goleiro
        podia cair na vaga de centroavante so por ordem de overall.
        """
        from fm.tatica import arrumar_no_campo
        d = self._decisao_vigente()
        if d and d.escalacao:
            return list(d.escalacao)
        tatica = self.tatica_atual()
        xi = self.world.best_xi(self.clube_id, tatica.vagas)
        if self.clube_id in self.world.escalacao_fixa and xi and xi[0].position == "GK":
            return [p.id for p in xi]
        return [p.id for p in arrumar_no_campo(xi, tatica.vagas_do_campo())]

    def proximo_jogo(self) -> tuple[str, str, Fixture | None]:
        """(tipo, competicao, jogo) da proxima data em que o usuario entra em campo.

        Percorre a agenda para a frente porque datas de copa encerrada sao puladas e
        porque numa data de copa o clube pode nem jogar -- ele ja foi eliminado, ou passou
        sem jogar. O lobby precisa dizer "quarta tem Libertadores", nao "tem alguma coisa".
        """
        rodada = self.rodada
        for i in range(self.data, len(self.agenda)):
            tipo, quem = self.agenda[i]
            if tipo == "selecao":
                if self.selecao_do_usuario and self.fifa is not None:
                    nome = self.fifa.joga_em(self.selecao_do_usuario, self.dias[i])
                    if nome:
                        return tipo, nome, None
                continue
            if tipo == "liga":
                # a liga do usuario pode folgar nesta data da grade (o Paraguai, com 22
                # rodadas, nao joga todo domingo)
                rodada += 1
                jogo = self.proxima_partida(rodada)
                if jogo is not None:
                    return tipo, self.liga, jogo
                continue
            andamento = self.copas.get(quem)
            if andamento is None or andamento.acabou or not self._data_de_copa_vale(i):
                continue
            if andamento.esta_vivo(self.clube_id):
                return tipo, quem, None
        return "", "", None

    def proxima_partida(self, data_de_liga: int | None = None) -> Fixture | None:
        """O jogo do usuario numa data de liga da grade (a proxima, se nao disser qual)."""
        n = self.rodada + 1 if data_de_liga is None else data_de_liga
        return next((f for f in self.calendario
                     if f.matchday == n and self.clube_id in (f.home, f.away)), None)

    def proxima_partida_da_liga(self) -> Fixture | None:
        """O proximo jogo do usuario na liga, mesmo que a liga dele folgue na proxima data
        da grade."""
        return min((f for f in self.calendario
                    if f.matchday > self.rodada and self.clube_id in (f.home, f.away)),
                   key=lambda f: f.matchday, default=None)

    def _data_de_copa_vale(self, indice: int) -> bool:
        """A data de copa acontece? Ela foi reservada para uma fase: se a copa ja passou
        dela, a data e pulada; se ainda nao chegou (atrasou), a data a ajuda a recuperar.
        A sobra do fim so vale para copa atrasada."""
        tipo, quem = self.agenda[indice]
        a = self.copas.get(quem)
        if tipo != "copa" or a is None or a.acabou:
            return False
        fase = self.fases_da_agenda[indice] if indice < len(self.fases_da_agenda) else -1
        # a reserva do fim tem a fase da ultima: so vale para copa que ainda nao acabou
        return not (fase >= 0 and a.fase > fase)

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
        self.decisoes[f"{self._chave()}@{self.data}"] = Decisao(list(jogadores), asdict(tatica))

    def avancar(self, substituicoes=None, penaltis=None) -> tuple[list[Result], Partida | None]:
        """Joga a proxima DATA e para.

        Data de liga: uma rodada em todas as divisoes, porque a piramide anda junta -- sem
        isso as divisoes ficariam em temporadas diferentes e o acesso nao faria sentido.
        Data de copa: a etapa daquele torneio, com o jogo do usuario em detalhe.
        """
        if self.acabou:
            raise RuntimeError("a temporada acabou; chame virar_o_ano()")
        # convite nao respondido caduca quando a bola rola; a IA ocupa as vagas que sobraram
        for h in self.humanos:
            if not (h.aprovacao and h.aprovacao.demitido):
                h.convites = []
        if self.vagas:
            from fm.tecnicos import preencher_vagas
            preencher_vagas(self.world, self.tecnicos, self.vagas, self.streams,
                            self.temporada)
            self.vagas = []
        # proposta sem resposta ate o apito da proxima data caduca
        for h in self.humanos:
            for prop in h.propostas:
                if prop.status == "pendente":
                    prop.status = "expirada"
            h._em_campo = None
            h.partida_da_data = None
        # `substituicoes` e `penaltis` sao da tela do humano ATIVO: a partida dele e a que
        # passa ao vivo. Os outros jogam com as instrucoes que deixaram (e, no replay, com
        # o que fizeram na hora, gravado em `na_partida`).
        # `penaltis(partida, minuto, clube)` e chamado em todo penalti da minha partida,
        # dos dois lados (a tela pausa nos dois); so a resposta para o MEU clube vale
        self._pedido_de_penalti = penaltis
        self._no_meio_da_data = True
        try:
            saida = self._avancar_data(substituicoes)
            for i in range(len(self.humanos)):
                with self._como(i):
                    self._novas_propostas()
        finally:
            self._pedido_de_penalti = None
            self._no_meio_da_data = False
        return saida

    def _avancar_data(self, substituicoes=None) -> tuple[list[Result], Partida | None]:
        self.lances_da_data = {}      # os da data anterior ficaram ate agora para a tela
        while not self.acabou:
            tipo, quem = self.agenda[self.data]
            if tipo == "liga":
                self.ultimo_compromisso = (tipo, quem)
                return self._jogar_rodada(substituicoes)
            if tipo == "selecao":
                # data FIFA: as selecoes jogam e nenhum clube entra em campo. So para a
                # tela se a selecao do usuario jogou.
                self.ultimo_compromisso = (tipo, quem)
                saida = self._jogar_data_fifa(substituicoes)
                self.data += 1
                if saida is not None:
                    return saida
                continue
            # antes de jogar: durante a partida ao vivo, e daqui que a tela sabe qual e a
            # competicao (o sorteio da copa so acontece no dia)
            self.ultimo_compromisso = (tipo, quem)
            if not self._data_de_copa_vale(self.data):
                self.data += 1          # a copa ja passou da fase desta data
                continue
            saida = self._jogar_etapa_de_copa(quem, substituicoes)
            self.data += 1
            if saida is not None:
                self.ultimo_compromisso = (tipo, quem)
                return saida
            # torneio ja encerrado: a data reservada simplesmente nao acontece
        return [], None

    def _jogar_data_fifa(self, substituicoes=None) -> tuple[list[Result], Partida] | None:
        """Os jogos de selecao do dia (fm.fifa); os das selecoes dos humanos em detalhe.
        None (a data passa sem parar) quando nenhum humano jogou. A regra nao olha QUEM
        esta com o controle: se olhasse, o replay pararia em datas diferentes das do jogo e
        as acoes do save cairiam na data errada."""
        rng = self.streams.get("selecoes", self.temporada, self.data)
        fora = set(self.medico.lesionados) if self.medico else set()
        com_selecao = {h.selecao_do_usuario: h.convocacao_do_usuario
                       for h in self.humanos if h.selecao_do_usuario}

        def meu_jogo(mundo, f, andamento, outros):
            return self._partida_da_selecao(mundo, f, andamento, outros, substituicoes)

        self._humanos_na_data = 0
        resultados, _ = self.fifa.jogar(self.world, self.dia(), rng, fora,
                                        usuarios=com_selecao,
                                        meu_jogo=meu_jogo if com_selecao else None)
        for i in range(len(self.humanos)):
            with self._como(i):
                self._demitir_da_selecao_se_ficou_fora()
        if not self._humanos_na_data:
            return None
        return resultados, self.humanos[self.ativo].partida_da_data

    def _onze_da_selecao(self, mundo, sid: int, tatica: Tatica) -> list[int]:
        """O onze escolhido, se ele ainda vale (todos convocados); senao os melhores."""
        from fm.tatica import arrumar_no_campo
        convocados = set(mundo.clubs[sid].player_ids)
        escolhidos = [p for p in self.escalacao_da_selecao if p in convocados]
        if len(escolhidos) == 11:
            jogadores = [mundo.players[p] for p in escolhidos]
        else:
            mundo.escalacao_fixa.pop(sid, None)
            jogadores = mundo.best_xi(sid, tatica.vagas)
        return [p.id for p in arrumar_no_campo(jogadores, tatica.vagas_do_campo())]

    def _partida_da_selecao(self, mundo, f: Fixture, andamento, outros: list[Result],
                            substituicoes) -> tuple[Result, Partida]:
        """A partida das selecoes de tecnico humano neste jogo (uma, ou as duas quando dois
        humanos se enfrentam): o motor de eventos, como a do clube, com a convocacao, o
        onze e a tatica de cada um -- e a tela ao vivo, as trocas e o penalti do ativo."""
        from fm.central import detalhar
        from fm.selecoes import id_da_selecao
        from fm.tatica import confronto, papeis_em_campo
        lados = [(i, id_da_selecao(h.selecao_do_usuario)) for i, h in enumerate(self.humanos)
                 if h.selecao_do_usuario
                 and id_da_selecao(h.selecao_do_usuario) in (f.home, f.away)]
        taticas = {f.home: Tatica(), f.away: Tatica()}
        onzes: dict[int, list[int]] = {}
        papeis: dict[int, str] = {}
        for i, sid in lados:
            with self._como(i):
                taticas[sid] = self.tatica_da_selecao_atual()
                onzes[sid] = self._onze_da_selecao(mundo, sid, taticas[sid])
            mundo.escalacao_fixa[sid] = onzes[sid]
            papeis.update(papeis_em_campo(onzes[sid], taticas[sid].vagas_do_campo()))
        for lado in (f.home, f.away):
            if lado not in onzes:
                onzes[lado] = [p.id for p in mundo.best_xi(lado)]
        # os outros jogos do dia, para a rodada ao vivo: fluxo proprio, nada muda no placar
        rng_lances = self.streams.get("selecoes_lances", self.temporada, self.data)
        self.parciais = list(outros)
        self.lances_da_data = {(r.home, r.away): detalhar(mundo, r, rng_lances)
                               for r in outros}
        ma, md = confronto(taticas[f.home], taticas[f.away])
        chave = f"{self.temporada}:{self.data}"
        t = andamento.torneio
        for i, sid in lados:
            self.humanos[i]._em_campo = (sid, mundo)
        # o primeiro jogo de humano da data usa o fluxo de sempre; os outros, um por jogo
        primeiro = self._humanos_na_data == 0
        self._humanos_na_data += 1
        extra = () if primeiro else (f.home, f.away)
        partida = simular_partida(
            mundo, f.home, f.away, onzes[f.home], onzes[f.away],
            self.streams.get("partida_da_selecao", self.temporada, self.data, *extra),
            t.style, t.mentality, mult_casa=ma, mult_fora=md,
            substituicoes=self._decisor_de_trocas(lados, substituicoes, chave, f.home,
                                                  f.away, mundo, taticas),
            papeis=papeis,
            penaltis=self._decisor_de_penaltis([i for i, _ in lados], chave),
            bancos={f.home: self.banco(f.home, mundo), f.away: self.banco(f.away, mundo)},
            max_trocas=MAX_TROCAS)
        self._penaltis_se_empatou(
            andamento, partida,
            cobradores={self.humanos[i].clube_id: _cobradores_de(self.humanos[i])
                        for i, _ in lados},
            rng=self.streams.get("disputa", self.temporada, self.data, *extra))
        r = Result(f.home, f.away, partida.gols_casa, partida.gols_fora, f.matchday)
        for i, _ in lados:
            h = self.humanos[i]
            h.jogos_da_selecao[self.data] = r
            h.competicoes_da_selecao[self.data] = self.fifa.torneio_do_usuario
            h.partida_da_data = partida
        return r, partida

    def proximo_jogo_da_selecao(self) -> tuple[int, str] | None:
        """(indice da data, competicao) do proximo jogo da selecao do usuario no ano."""
        if not self.selecao_do_usuario or self.fifa is None:
            return None
        for i in range(self.data, len(self.agenda)):
            if self.agenda[i][0] == "selecao":
                nome = self.fifa.joga_em(self.selecao_do_usuario, self.dias[i])
                if nome:
                    return i, nome
        return None

    def _demitir_da_selecao_se_ficou_fora(self) -> None:
        """A selecao que nao se classificou para a Copa troca de treinador."""
        pais = self.selecao_do_usuario
        if not pais or self.fifa is None:
            return
        for ciclo, classificados in self.fifa.classificados.items():
            if ciclo == self.temporada and pais not in classificados \
                    and self.fifa.ciclo_de.get("copa_do_mundo") == ciclo:
                self.selecao_do_usuario = None
                self.convocacao_do_usuario, self.escalacao_da_selecao = [], []
                self.demissao_da_selecao = pais

    def _jogar_rodada(self, substituicoes=None) -> tuple[list[Result], Partida | None]:
        n = self.rodada + 1
        taticas = self._taticas_da_data()
        self._preparar_desfalques(self.ligas, taticas)
        meus_clubes = {self.humanos[i].clube_id: i for i in taticas}

        detalhadas: list[Partida] = []
        todos: list[Result] = []
        jogaram: set[int] = set()
        por_liga: dict[str, list[Result]] = {}

        for nome in self.ligas:
            cfg = load_league(nome)
            lid = cfg["id"]
            partidas = [f for f in self.calendarios[nome] if f.matchday == n]
            if not partidas:
                continue
            jogaram |= {f.home for f in partidas} | {f.away for f in partidas}
            ratings = {
                cid: float(effective_rating(self.world.team_rating(cid),
                                            fatigue=self.world.fatigue_penalty(cid),
                                            morale=bonus_de_moral(self.world, cid)))
                for cid in self.world.leagues[lid].club_ids
            }
            rng = self.streams.get("carreira", self.temporada, n, lid)
            style = style_of(cfg)

            humanas = [f for f in partidas if f.home in meus_clubes or f.away in meus_clubes]
            if humanas:
                # os outros ANTES dos humanos: enquanto a partida ao vivo pausa, a rodada ao
                # vivo ja tem o que mostrar
                outras = [f for f in partidas if all(f is not x for x in humanas)]
                r = play_fixtures(outras, ratings, rng, style)
                self.parciais = list(r)
                self._detalhar(r)      # a central da rodada ja tem quem marcou e quando
                feitas = self._partidas_humanas(humanas, rng, style, taticas, substituicoes)
                for f, d in zip(humanas, feitas, strict=True):
                    r.append(Result(f.home, f.away, d.gols_casa, d.gols_fora, n))
                    self._registrar_jogo_humano(r[-1], d, nome, meus_clubes)
                detalhadas += feitas
            else:
                r = play_fixtures(partidas, ratings, rng, style)
                self._detalhar(r)

            self.resultados[nome].extend(r)
            todos.extend(r)
            por_liga[nome] = r

        # FORA do laco das divisoes: dentro dele, a partida do usuario era contada uma vez
        # por divisao e o artilheiro terminava o ano com noventa jogos
        rng_est = self.streams.get("estatisticas", self.temporada, n)
        from fm.estatisticas import Estatisticas
        from fm.selecao import selecao_da_rodada
        comp_de = {(r.home, r.away): nome for nome, rs in por_liga.items() for r in rs}
        rodada = {nome: Estatisticas(temporada=self.temporada) for nome in por_liga}
        self._somar_estatisticas(todos, detalhadas, rng_est, comp_de, rodada)
        for nome, rs in por_liga.items():
            pares = {(x.home, x.away) for x in rs}
            minhas = [d for d in detalhadas if (d.casa, d.fora) in pares]
            self.selecoes.setdefault(nome, {})[n] = selecao_da_rodada(
                self.world, rs, rodada[nome], minhas)
            clubes = {x.home for x in rs} | {x.away for x in rs}
            self._cartoes_da_data(nome, rs, minhas, clubes)
        self._moral_da_data(todos, detalhadas)
        self._lesoes_da_data(todos, detalhadas)

        self._gastar_energia(jogaram, self._custos_de_energia(taticas))
        self._encerrar_desfalques(taticas)
        self.rodada = n
        self.data += 1
        self._checar_emprego_de_todos()
        return todos, self.humanos[self.ativo].partida_da_data

    def _taticas_da_data(self) -> dict[int, Tatica]:
        """{humano: tatica} de quem dirige um clube nesta data."""
        fora = {}
        for i in self._humanos_em_campo():
            with self._como(i):
                fora[i] = self.tatica_atual()
        return fora

    def _custos_de_energia(self, taticas: dict[int, Tatica]) -> dict[int, float]:
        return {self.humanos[i].clube_id: t.custo_de_energia for i, t in taticas.items()}

    def _checar_emprego_de_todos(self) -> None:
        for i in range(len(self.humanos)):
            with self._como(i):
                self._checar_emprego()

    def _registrar_jogo_humano(self, r: Result, partida: Partida, competicao: str,
                               meus_clubes: dict[int, int]) -> None:
        """O jogo entra no ano e nos recordes de cada humano que estava nele."""
        for clube in (r.home, r.away):
            i = meus_clubes.get(clube)
            if i is None:
                continue
            with self._como(i) as h:
                h.jogos_do_usuario[self.data] = r
                h.partida_da_data = partida
                self._anotar_recorde(r, competicao)

    def _partidas_humanas(self, jogos: list[Fixture], rng, style, taticas: dict[int, Tatica],
                          substituicoes) -> list[Partida]:
        """As partidas de clube com tecnico humano numa data, na ordem de `jogos`.

        O primeiro jogo usa o fluxo da rodada, como a partida do usuario sempre usou; os
        outros, um fluxo cada -- assim nenhum placar depende de qual humano estava com o
        controle. A do ativo roda por ultimo: e ela que pausa na tela ao vivo, e quando
        ela comeca os outros humanos ja jogaram."""
        def do_ativo(k: int) -> bool:
            return (self.ativo in taticas
                    and self.humanos[self.ativo].clube_id in (jogos[k].home, jogos[k].away))

        feitas: dict[int, Partida] = {}
        for k in sorted(range(len(jogos)), key=do_ativo):
            f = jogos[k]
            fluxo = rng if k == 0 else self.streams.get("partida_humana", self.temporada,
                                                         self.data, f.home, f.away)
            feitas[k] = self._partida_humana(f, fluxo, style, taticas, substituicoes)
        return [feitas[k] for k in range(len(jogos))]

    def caderno(self, competicao: str):
        """O caderno de artilharia de uma competicao no ano, criado na primeira vez."""
        from fm.estatisticas import Estatisticas
        if competicao not in self.estatisticas_por_comp:
            self.estatisticas_por_comp[competicao] = Estatisticas(temporada=self.temporada)
        return self.estatisticas_por_comp[competicao]

    def _somar_estatisticas(self, resultados, detalhadas, rng, comp_de,
                            rodada=None) -> None:
        """As partidas dos humanos entram pelos EVENTOS; as outras, por amostragem do placar.

        Sem a segunda metade nao existe artilharia de campeonato: os jogos dos outros
        clubes sao resolvidos pelo motor rapido, que devolve so o placar.
        """
        from fm.central import registrar as registrar_lances
        from fm.estatisticas import registrar_partida_detalhada, registrar_resultado

        if self.estatisticas is None:
            return
        rodada = rodada or {}
        pares = {(d.casa, d.fora) for d in detalhadas}

        def cadernos(r):
            # comp_de: o nome da copa (a etapa inteira e dela) ou {jogo: divisao}
            comp = comp_de if isinstance(comp_de, str) else comp_de.get((r.home, r.away))
            fora = [self.estatisticas]
            if comp:
                fora.append(self.caderno(comp))
                if comp in rodada:
                    fora.append(rodada[comp])
            return fora

        for r in resultados:
            if (r.home, r.away) not in pares:
                lances = self.lances_da_data.get((r.home, r.away))
                if lances is not None:
                    # os mesmos lances que a central da rodada mostrou
                    registrar_lances(cadernos(r), self.world, r, lances)
                else:
                    registrar_resultado(cadernos(r), self.world, r, rng)
        for d in detalhadas:
            minha = next((r for r in resultados if (r.home, r.away) == (d.casa, d.fora)),
                         None)
            alvo = cadernos(minha) if minha else [self.estatisticas]
            registrar_partida_detalhada(alvo, self.world, d)

    def _partida_humana(self, jogo: Fixture, rng, style, taticas: dict[int, Tatica],
                        substituicoes) -> Partida:
        """Um jogo de clube com tecnico humano -- de um lado, ou dos dois quando dois
        humanos se enfrentam: o motor de eventos com a tatica, o onze, os cobradores e o
        banco de cada um."""
        import math

        from fm.tatica import confronto, papeis_em_campo
        lados = [(i, self.humanos[i].clube_id) for i in taticas
                 if self.humanos[i].clube_id in (jogo.home, jogo.away)]
        por_clube = {jogo.home: Tatica(), jogo.away: Tatica()}
        for i, meu in lados:
            por_clube[meu] = taticas[i]
        ma, md = confronto(por_clube[jogo.home], por_clube[jogo.away])
        # a moral e a quimica, que no motor rapido entram no rating, aqui entram nos gols
        # esperados: um ponto de overall vale ~2,4% de gol na conta do motor (fm.match)
        dif = bonus_de_moral(self.world, jogo.home) - bonus_de_moral(self.world, jogo.away)
        ma, md = ma * math.exp(0.024 * dif), md * math.exp(-0.024 * dif)
        chave = f"{self.temporada}:{self.data}"
        papeis: dict[int, str] = {}
        cobradores: dict[int, list[int]] = {}
        batedores: dict[int, dict[str, int]] = {}
        for i, meu in lados:
            h = self.humanos[i]
            with self._como(i):
                onze = self.world.escalacao_fixa.get(meu) or self.escalacao_atual()
            papeis.update(papeis_em_campo(onze, taticas[i].vagas_do_campo()))
            cobradores[meu] = _cobradores_de(h)
            batedores[meu] = {k: h.funcoes[k] for k in ("faltas", "escanteios")
                              if k in h.funcoes}
        return simular_partida(
            self.world, jogo.home, jogo.away,
            [p.id for p in self.world.best_xi(jogo.home)],
            [p.id for p in self.world.best_xi(jogo.away)],
            rng, style, mult_casa=ma, mult_fora=md,
            substituicoes=self._decisor_de_trocas(lados, substituicoes, chave, jogo.home,
                                                  jogo.away, self.world, por_clube),
            papeis=papeis,
            cobradores=cobradores,
            batedores=batedores,
            penaltis=self._decisor_de_penaltis([i for i, _ in lados], chave),
            bancos={jogo.home: self.banco(jogo.home, self.world),
                    jogo.away: self.banco(jogo.away, self.world)},
            max_trocas=MAX_TROCAS)

    def banco(self, clube: int, mundo: World | None = None) -> list[int]:
        """Os reservas relacionados: 12, fora do onze e disponiveis, com o goleiro
        reserva sempre entre eles -- sem ele, goleiro machucado virava meia no gol. E o
        banco da tela ao vivo e o de onde sai quem entra no lugar do machucado."""
        if mundo is None or clube not in mundo.clubs:
            mundo = self.mundo_em_campo if clube in self.mundo_em_campo.clubs else self.world
        onze = {p.id for p in mundo.best_xi(clube)}
        livres = [p for p in sorted(mundo.squad(clube), key=lambda p: -p.overall)
                  if p.id not in onze and p.id not in mundo.indisponiveis]
        goleiro = next((p for p in livres if p.position == "GK"), None)
        resto = [p for p in livres if p is not goleiro]
        return ([goleiro.id] if goleiro else []) + [p.id for p in resto][:12 - bool(goleiro)]

    def cobradores(self) -> list[int]:
        return _cobradores_de(self.humano)

    def _decisor_de_penaltis(self, lados: list[int], chave: str):
        """Quem bate o penalti de cada humano no jogo. So o ativo tem a tela para
        perguntar; o outro (quando dois humanos se enfrentam) usa o que gravou."""
        decisores = [d for d in (self._na_marca(self.humanos[i], chave,
                                                self._pedido_de_penalti
                                                if i == self.ativo else None)
                                 for i in lados) if d is not None]
        if len(decisores) <= 1:
            return decisores[0] if decisores else None

        def decidir(partida, minuto, clube):
            # todos sao chamados: a tela do ativo pausa tambem no penalti do outro lado
            escolhas = [d(partida, minuto, clube) for d in decisores]
            return next((e for e in escolhas if e is not None), None)
        return decidir

    def _na_marca(self, h: Humano, chave: str, pedido):
        """Quem bate o penalti do time de `h`: o que a tela escolheu, gravado em
        `na_partida` para o replay escolher o mesmo. Sem escolha, vale a ordem de
        cobradores."""
        gravado = (h.na_partida.get(chave) or {}).get("penaltis", [])
        if pedido is None and not gravado:
            return None

        usados: set[int] = set()

        def decidir(partida, minuto, clube):
            if pedido is None:
                if clube != h.clube_id:
                    return None
                # na ordem gravada: dois penaltis no mesmo minuto nao pegam o mesmo batedor
                i = next((i for i, (m, _) in enumerate(gravado)
                          if m == minuto and i not in usados), None)
                if i is None:
                    return None
                usados.add(i)
                return gravado[i][1]
            escolha = pedido(partida, minuto, clube)
            if clube != h.clube_id or escolha is None:
                return None
            escolha = int(escolha)
            reg = h.na_partida.setdefault(chave, {"trocas": [], "taticas": []})
            reg.setdefault("penaltis", []).append([minuto, escolha])
            return escolha
        return decidir

    def _decisor_de_trocas(self, lados: list[tuple[int, int]], substituicoes, chave: str,
                           casa: int, fora: int, mundo: World, taticas: dict[int, Tatica]):
        """As trocas e mudancas de tatica de cada humano no jogo, juntas num `Ajuste`.
        `lados` = [(humano, time dele em campo)]; `taticas` = {time: tatica valendo},
        atualizado a cada mudanca, porque o confronto depende das duas."""
        from fm.eventos import Ajuste
        decisores = [d for d in (self._no_banco(self.humanos[i],
                                                substituicoes if i == self.ativo else None,
                                                chave, meu, meu == casa, mundo, taticas,
                                                casa, fora)
                                 for i, meu in lados) if d is not None]
        if len(decisores) <= 1:
            return decisores[0] if decisores else None

        def decidir(partida, minuto):
            ajuste = Ajuste()
            for d in decisores:
                a = d(partida, minuto)
                ajuste.trocas += a.trocas
                if a.mult_casa is not None:
                    ajuste.mult_casa, ajuste.mult_fora = a.mult_casa, a.mult_fora
            return ajuste
        return decidir

    def _no_banco(self, h: Humano, pedido, chave: str, meu: int, sou_casa: bool,
                  mundo: World, taticas: dict[int, Tatica], casa: int, fora: int):
        """O intermediario entre quem decide (terminal, tela ao vivo ou o save) e o motor.

        `pedido(partida, minuto)` pode devolver a lista antiga [(clube, sai, entra)] ou um
        dict {"trocas": [(sai, entra)], "tatica": Tatica | dict}. O que passar pelas regras
        -- so o proprio time (`meu`), no maximo MAX_TROCAS, quem jogou nao volta -- e
        gravado em `na_partida` de `h`, e e isso que o replay devolve. Sem pedido e sem
        registro, o motor joga sem banco, como sempre jogou.
        """
        from fm.eventos import Ajuste
        from fm.tatica import confronto

        gravado = h.na_partida.get(chave)
        if pedido is None and not gravado:
            return None

        def decidir(partida, minuto):
            if pedido is None:                    # replay: devolve o que foi feito
                trocas = [(s, e) for m, s, e in gravado.get("trocas", []) if m == minuto]
                nova = next((t for m, t in gravado.get("taticas", []) if m == minuto), None)
            else:
                resposta = pedido(partida, minuto) or []
                if isinstance(resposta, dict):
                    trocas = [tuple(t) for t in resposta.get("trocas", [])]
                    nova = resposta.get("tatica")
                else:
                    trocas = [(s, e) for cl, s, e in resposta if cl == meu]
                    nova = None
            feitas = sum(1 for e in partida.eventos
                         if e.tipo == "substituicao" and e.clube == meu)
            em_campo = partida.em_campo_casa if sou_casa else partida.em_campo_fora
            elenco = {p.id for p in mundo.squad(meu)}
            validas: list[tuple[int, int]] = []
            for sai, entra in trocas:
                if feitas + len(validas) >= MAX_TROCAS:
                    break
                ja_vai = {e for _, e in validas} | {s for s, _ in validas}
                # o suspenso tambem nao entra: a regra fica aqui, e nao so na tela, para
                # valer do terminal, do navegador e do replay do save
                if (sai in em_campo and entra in elenco and entra not in partida.entrada
                        and entra not in mundo.indisponiveis
                        and sai not in ja_vai and entra not in ja_vai):
                    validas.append((int(sai), int(entra)))
            ajuste = Ajuste(trocas=[(meu, s, e) for s, e in validas])
            t = None
            if nova is not None:
                t = nova if isinstance(nova, Tatica) else Tatica(**nova)
                t.validar()
                # o confronto e com a tatica que o outro lado tem AGORA: a padrao, se for
                # da IA; a do outro humano, se ele tambem mexeu
                taticas[meu] = t
                ajuste.mult_casa, ajuste.mult_fora = confronto(taticas[casa], taticas[fora])
            if pedido is not None and (validas or t is not None):
                reg = h.na_partida.setdefault(chave, {"trocas": [], "taticas": []})
                reg["trocas"] += [[minuto, s, e] for s, e in validas]
                if t is not None:
                    reg["taticas"].append([minuto, asdict(t)])
            return ajuste
        return decidir

    def _jogar_etapa_de_copa(self, nome: str, substituicoes=None
                             ) -> tuple[list[Result], Partida | None] | None:
        """Uma etapa de copa. None quando o torneio ja acabou e a data fica vazia."""
        from fm.copa import proxima_etapa, registrar

        andamento = self.copas.get(nome)
        if andamento is None:
            return None
        rng = self.streams.get("copa", self.temporada, self.data, nome)
        tabelas = self.tabelas_do_ano_anterior or TabelasPreguicosas(self._tabelas_por_forca)
        self._repassar_exportados(andamento)
        if self._esperando_outro_torneio(andamento):
            return None                 # a data desta copa passa sem jogo
        etapa = proxima_etapa(self.world, andamento, rng, tabelas)
        if etapa is None or not etapa.fixtures:
            return None

        taticas = self._taticas_da_data()
        self._preparar_desfalques([nome], taticas)
        meus_clubes = {self.humanos[i].clube_id: i for i in taticas}
        t = andamento.torneio
        # uma etapa tem no maximo um jogo de cada humano: no mata-mata de ida e volta a ida
        # e a volta sao datas diferentes (fm.copa), e as duas sao jogadas em detalhe
        humanas = [f for f in etapa.fixtures if f.home in meus_clubes or f.away in meus_clubes]
        jogos = [f for f in etapa.fixtures if all(f is not x for x in humanas)]
        resultados: list[Result] = []

        ratings = {cid: float(effective_rating(self.world.team_rating(cid),
                                               fatigue=self.world.fatigue_penalty(cid),
                                               morale=bonus_de_moral(self.world, cid)))
                   for cid in {f.home for f in etapa.fixtures} | {f.away for f in etapa.fixtures}}
        # os outros primeiro, como na liga: e o que a rodada ao vivo mostra
        outros = play_fixtures(jogos, ratings, rng, t.style, t.mentality)
        self.parciais = list(outros)
        self._detalhar(outros)
        detalhadas = self._partidas_humanas(humanas, rng, t.style, taticas, substituicoes)
        for k, (f, d) in enumerate(zip(humanas, detalhadas, strict=True)):
            cobradores = {self.humanos[i].clube_id: _cobradores_de(self.humanos[i])
                          for c, i in meus_clubes.items() if c in (f.home, f.away)}
            extra = () if k == 0 else (f.home, f.away)
            self._penaltis_se_empatou(andamento, d, cobradores=cobradores,
                                      rng=self.streams.get("disputa", self.temporada,
                                                           self.data, *extra))
            resultados.append(Result(f.home, f.away, d.gols_casa, d.gols_fora, f.matchday))
            self._registrar_jogo_humano(resultados[-1], d, nome, meus_clubes)
        resultados += outros
        registrar(self.world, andamento, resultados, rng, self.exportados)
        self._somar_estatisticas(resultados, detalhadas, rng, nome)

        jogaram = {f.home for f in etapa.fixtures} | {f.away for f in etapa.fixtures}
        self._cartoes_da_data(nome, resultados, detalhadas, jogaram)
        self._moral_da_data(resultados, detalhadas)
        self._lesoes_da_data(resultados, detalhadas)
        self._gastar_energia(jogaram, self._custos_de_energia(taticas))
        self._encerrar_desfalques(taticas)
        self._checar_emprego_de_todos()
        return resultados, self.humanos[self.ativo].partida_da_data

    # ---------------------------------------------------------------- negocios

    def _novas_propostas(self) -> None:
        """Depois de cada data, algum clube pode oferecer por um jogador do usuario.
        Stream proprio: nada no resto do mundo muda por existir ou nao uma proposta."""
        from fm.negocios import gerar_propostas
        if self.acabou or self.demitido:
            return
        rng = self._fluxo("propostas", self.temporada, self.data)
        self.propostas += gerar_propostas(self, rng)

    def propostas_pendentes(self) -> list:
        return [x for x in self.propostas if x.status == "pendente"]

    def _proposta(self, pid: str):
        return next((x for x in self.propostas if x.id == pid), None)

    def executar(self, acao: dict) -> dict:
        """Aplica um negocio do usuario e o grava para o replay.

        tipos: compra {jogador, preco, salario, anos}, renovacao {jogador, salario, anos},
        aceitar {proposta}, recusar {proposta}, contraproposta {proposta, valor},
        emprestimo_entrada {jogador}, emprestimo_saida {jogador, clube}.
        Revalida tudo aqui, nao so na tela: o save pode ser editado, e a regra tem de valer
        de qualquer caminho.
        """
        from fm import negocios as neg
        tipo = acao.get("tipo")
        w = self.world
        resultado: dict
        if tipo == "pedir_demissao":
            resultado = self.pedir_demissao()
            if "erro" not in resultado:
                self._gravar_acao(acao)
            return resultado
        if tipo in ("assumir_selecao", "recusar_selecao", "deixar_selecao",
                    "convocar_selecao", "escalar_selecao"):
            resultado = self._acao_da_selecao(tipo, acao)
            if "erro" not in resultado:
                self._gravar_acao(acao)
            return resultado
        if tipo == "assumir":
            clube = int(acao["clube"])
            if clube not in self.convites or any(
                    h.clube_id == clube for h in self.humanos if h is not self.humano):
                return {"erro": "esse clube nao esta mais chamando"}
            self._assumir(clube)
            self._gravar_acao(acao)
            return {"ok": True, "mensagem": f"Voce e o novo tecnico do {w.clubs[clube].name}."}
        if tipo == "compra":
            pid = int(acao["jogador"])
            p = w.players.get(pid)
            if p is None or p.club_id == self.clube_id:
                return {"erro": "jogador indisponivel"}
            oferta = neg.avaliar_oferta(self, pid, int(acao.get("preco", 0)))
            if oferta["resultado"] != "aceita":
                return {"erro": oferta["mensagem"]}
            valor = int(oferta["valor"])
            contrato = neg.avaliar_contrato(self, pid, int(acao["salario"]), int(acao["anos"]))
            if contrato["resultado"] != "aceita":
                return {"erro": contrato["mensagem"]}
            if self.clube.balance < valor:
                return {"erro": "caixa insuficiente para a transferencia"}
            folha = neg.folha_mensal(w, self.clube_id) + int(acao["salario"])
            if folha > neg.limite_da_folha(self):
                return {"erro": "a diretoria veta: a folha passaria do limite"}
            if len(self.clube.player_ids) >= neg.ELENCO_MAXIMO:
                return {"erro": f"o elenco ja tem {neg.ELENCO_MAXIMO} jogadores"}
            de = p.club_id
            neg.transferir(w, pid, self.clube_id, valor, int(acao["salario"]),
                           self.temporada + int(acao["anos"]))
            self._registrar_movimento("entrada", pid, de, valor)
            resultado = {"ok": True, "mensagem": f"{p.name} e o novo reforco do "
                                                 f"{self.clube.name}."}
        elif tipo == "emprestimo_entrada":
            pid = int(acao["jogador"])
            r = neg.avaliar_emprestimo(self, pid)
            if r["resultado"] != "aceita":
                return {"erro": r["mensagem"]}
            p = w.players[pid]
            if self.clube.balance < r["taxa"]:
                return {"erro": "caixa insuficiente para a taxa do emprestimo"}
            if neg.folha_mensal(w, self.clube_id) + p.wage > neg.limite_da_folha(self):
                return {"erro": "a diretoria veta: a folha passaria do limite"}
            if len(self.clube.player_ids) >= neg.ELENCO_MAXIMO:
                return {"erro": f"o elenco ja tem {neg.ELENCO_MAXIMO} jogadores"}
            dono = p.club_id
            self.clube.balance -= r["taxa"]
            w.clubs[dono].balance += r["taxa"]
            neg.emprestar(w, pid, self.clube_id)
            self._registrar_movimento("emprestimo_entrada", pid, dono, r["taxa"])
            resultado = {"ok": True, "mensagem": f"{p.name} chega emprestado do "
                                                 f"{w.clubs[dono].name} ate o fim da temporada."}
        elif tipo == "emprestimo_saida":
            pid, para = int(acao["jogador"]), int(acao["clube"])
            p = w.players.get(pid)
            if p is None or p.club_id != self.clube_id:
                return {"erro": "ele nao esta no seu elenco"}
            if p.loan_from is not None:
                return {"erro": f"{p.name} esta emprestado a voce: nao da para repassar"}
            if len(self.clube.player_ids) <= neg.ELENCO_MINIMO:
                return {"erro": f"o elenco nao pode ficar com menos de {neg.ELENCO_MINIMO}"}
            if para not in neg.interessados_no_emprestimo(self, pid):
                return {"erro": "esse clube nao tem mais interesse"}
            neg.emprestar(w, pid, para)
            self._registrar_movimento("emprestimo_saida", pid, para, 0)
            self._tirar_do_onze(pid)
            resultado = {"ok": True, "mensagem": f"{p.name} vai jogar emprestado no "
                                                 f"{w.clubs[para].name} ate o fim da temporada."}
        elif tipo == "renovacao":
            pid = int(acao["jogador"])
            if w.players[pid].loan_from is not None:
                return {"erro": "o contrato dele e com o clube dono, nao com voce"}
            r = neg.avaliar_renovacao(self, pid, int(acao["salario"]), int(acao["anos"]))
            if r["resultado"] != "aceita":
                return {"erro": r["mensagem"]}
            p = w.players[pid]
            p.wage = int(acao["salario"])
            p.contract_until = max(p.contract_until, self.temporada) + int(acao["anos"])
            resultado = {"ok": True, "mensagem": f"{p.name} renovou ate {p.contract_until}."}
        elif tipo in ("aceitar", "recusar", "contraproposta"):
            prop = self._proposta(acao.get("proposta", ""))
            if prop is None or prop.status != "pendente":
                return {"erro": "essa proposta nao esta mais de pe"}
            p = w.players.get(prop.jogador)
            if p is None or p.club_id != self.clube_id or p.loan_from is not None:
                prop.status = "expirada"
                return {"erro": "o jogador nao esta mais no clube"}
            if tipo == "recusar":
                prop.status = "recusada"
                resultado = {"ok": True, "mensagem": "Proposta recusada."}
            else:
                valor = prop.valor
                if tipo == "contraproposta":
                    r = neg.responder_contraproposta(prop, int(acao["valor"]))
                    if r["resultado"] != "aceita":
                        if r["resultado"] == "recusada":
                            prop.status = "recusada"
                            resultado = {"ok": True, "resultado": "recusada", "mensagem":
                                         f"O {w.clubs[prop.clube].name} recusou e desistiu."}
                        else:
                            prop.valor, prop.contra_usada = r["valor"], True
                            resultado = {"ok": True, "resultado": "nova_proposta",
                                         "valor": r["valor"], "mensagem":
                                         f"O {w.clubs[prop.clube].name} fez uma nova "
                                         f"proposta de {texto_de_euros(r['valor'])}."}
                        self._gravar_acao(acao)
                        return resultado
                    valor = r["valor"]
                if len(self.clube.player_ids) <= neg.ELENCO_MINIMO:
                    return {"erro": f"o elenco nao pode ficar com menos de {neg.ELENCO_MINIMO}"}
                comprador = prop.clube
                neg.transferir(w, p.id, comprador, valor,
                               int(p.wage * 1.15), self.temporada + 4)
                prop.status, prop.valor = "aceita", valor
                self._registrar_movimento("saida", p.id, comprador, valor)
                self._tirar_do_onze(p.id)
                resultado = {"ok": True, "resultado": "aceita", "mensagem":
                             f"{p.name} foi vendido ao {w.clubs[comprador].name} por "
                             f"{texto_de_euros(valor)}."}
        else:
            return {"erro": f"acao desconhecida {tipo!r}"}
        self._gravar_acao(acao)
        return resultado

    def _acao_da_selecao(self, tipo: str, acao: dict) -> dict:
        from fm.selecoes import CONVOCADOS, MINIMO_DE_JOGADORES
        pais = self.selecao_do_usuario
        if tipo == "assumir_selecao":
            if acao.get("pais") != self.convite_selecao or acao.get("pais") in (
                    self._selecoes_de_outros()):
                return {"erro": "essa selecao nao esta mais chamando"}
            self.selecao_do_usuario, self.convite_selecao = self.convite_selecao, None
            self.convocacao_do_usuario, self.escalacao_da_selecao = [], []
            self.tatica_da_selecao = {}
            for h in self.humanos:
                if h is not self.humano and h.convite_selecao == self.selecao_do_usuario:
                    h.convite_selecao = None
            return {"ok": True,
                    "mensagem": f"Voce agora treina a selecao: {self.selecao_do_usuario}."}
        if tipo == "recusar_selecao":
            self.convite_selecao = None
            return {"ok": True}
        if pais is None:
            return {"erro": "voce nao treina nenhuma selecao"}
        if tipo == "deixar_selecao":
            self.selecao_do_usuario = None
            self.convocacao_do_usuario, self.escalacao_da_selecao = [], []
            return {"ok": True, "mensagem": f"Voce deixou a selecao: {pais}."}
        if tipo == "convocar_selecao":
            ids = [int(x) for x in acao.get("jogadores", [])]
            w = self.world
            if len(set(ids)) != len(ids):
                return {"erro": "jogador repetido na convocacao"}
            if not MINIMO_DE_JOGADORES <= len(ids) <= CONVOCADOS:
                return {"erro": f"convoque de {MINIMO_DE_JOGADORES} a {CONVOCADOS} jogadores"}
            if any(i not in w.players or w.players[i].nationality != pais
                   or w.players[i].club_id not in w.clubs for i in ids):
                return {"erro": f"so jogadores com nacionalidade de {pais}"}
            if sum(1 for i in ids if w.players[i].position == "GK") < 2:
                return {"erro": "convoque pelo menos dois goleiros"}
            self.convocacao_do_usuario = ids
            self.escalacao_da_selecao = [p for p in self.escalacao_da_selecao if p in ids]
            return {"ok": True}
        # escalar_selecao: o onze (entre os convocados) e a tatica
        pedida = {k: v for k, v in (acao.get("tatica") or {}).items()
                  if k in ("formacao", "marcacao", "estilo")}
        tatica = Tatica(**{**asdict(Tatica()), **pedida})
        tatica.validar()
        onze = [int(x) for x in acao.get("onze", [])]
        if onze and (len(onze) != 11 or len(set(onze)) != 11):
            return {"erro": "o onze precisa de 11 jogadores diferentes"}
        convocados = set(self.convocacao_do_usuario) or set(
            (self.fifa.convocacoes.get(pais) if self.fifa else None) or [])
        if any(p not in convocados for p in onze):
            return {"erro": "so convocados podem ser escalados"}
        self.escalacao_da_selecao = onze
        self.tatica_da_selecao = {k: getattr(tatica, k) for k in ("formacao", "marcacao", "estilo")}
        return {"ok": True}

    def convidar_para_selecao(self) -> None:
        """O convite de uma selecao, pela reputacao do treinador. Uma vez por ano, na
        virada (e no comeco da carreira). A melhor selecao que aceita alguem do tamanho
        dele: a primeira do ranking pede reputacao 88; a ultima, 30."""
        from fm.selecoes import SUSPENSAS, convocar_todas, mundo_das_selecoes, ranking
        if self.selecao_do_usuario or self.demitido:
            self.convite_selecao = None
            return
        eu = self.tecnicos.get(self.humano.tecnico_id) if self.tecnicos else None
        if eu is None:
            return
        rng = self._fluxo("convite_selecao", self.temporada)
        mundo = (self.fifa.mundo if self.fifa is not None and self.fifa.mundo is not None
                 else mundo_das_selecoes(self.world, convocar_todas(self.world)))
        ordem = [p for p in ranking(mundo) if p not in SUSPENSAS]
        n = max(len(ordem) - 1, 1)
        # a selecao de outro humano nao chama: ela ja tem treinador
        ocupadas = self._selecoes_de_outros()
        aceitam = [p for i, p in enumerate(ordem)
                   if 88 - 58 * i / n <= eu.reputacao and p not in ocupadas]
        self.convite_selecao = None
        if aceitam and rng.random() < 0.6:
            self.convite_selecao = aceitam[int(rng.integers(min(3, len(aceitam))))]

    def _selecoes_de_outros(self) -> set[str]:
        return {h.selecao_do_usuario for h in self.humanos
                if h is not self.humano and h.selecao_do_usuario}

    def _registrar_movimento(self, sentido: str, pid: int, outro: int | None, valor: int):
        p = self.world.players[pid]
        self.movimentos.append({
            "temporada": self.temporada, "data": self.data, "sentido": sentido,
            "jogador": pid, "nome": p.name, "posicao": p.position, "overall": p.overall,
            "clube": self.world.clubs[outro].name if outro in self.world.clubs else "sem clube",
            "valor": valor})

    def _tirar_do_onze(self, pid: int) -> None:
        """Quem saiu nao pode continuar escalado: a proxima escalacao volta a automatica."""
        d = self._decisao_vigente()
        if d and pid in d.escalacao:
            self._descartar_decisao()
        if pid in self.world.escalacao_fixa.get(self.clube_id, []):
            self.world.escalacao_fixa.pop(self.clube_id, None)
        self.observados = [x for x in self.observados if x != pid]
        self.funcoes = {k: v for k, v in self.funcoes.items() if v != pid}

    def _aplicar_acoes_do_save(self, acoes: list[dict]) -> None:
        """Replay: reaplica as acoes gravadas exatamente na data em que foram feitas, cada
        uma pelo humano que a fez."""
        for a in acoes:
            if a.get("temporada") == self.temporada and a.get("data") == self.data:
                limpa = {k: v for k, v in a.items() if k not in ("temporada", "data", "humano")}
                with self._como(int(a.get("humano", 0))):
                    self.executar(limpa)

    # ---------------------------------------------------------------- o gancho

    def competicao_do_proximo(self) -> str | None:
        """A chave da competicao do proximo jogo do usuario: e nela que o gancho vale."""
        tipo, onde, _ = self.proximo_jogo()
        if tipo == "liga":
            return self.liga
        if tipo == "selecao":
            return f"fifa:{onde}"      # a chave da tabela da selecao (fm.telas.andamento_de)
        return onde or None

    def suspensos_do_proximo(self) -> set[int]:
        comp = self.competicao_do_proximo()
        return self.disciplina.suspensos(comp) if comp and self.disciplina else set()

    def _preparar_desfalques(self, competicoes: list[str], taticas: dict[int, Tatica]) -> None:
        """Tira os suspensos de campo antes da data: dos clubes da IA pelo best_xi, dos
        humanos (`taticas`, {humano: tatica}) trocando cada um pelo melhor reserva do mesmo
        setor, NA MESMA VAGA."""
        suspensos: set[int] = set()
        for comp in competicoes:
            suspensos |= self.disciplina.suspensos(comp)
        # o lesionado fica fora em qualquer competicao; a troca na escalacao e a mesma
        suspensos |= self.medico.fora(self.hoje())
        self.world.indisponiveis = suspensos
        for i, tatica in taticas.items():
            with self._como(i):
                self._onze_pretendido = self.escalacao_atual()
                self.world.escalacao_fixa[self.clube_id] = self._sem_suspensos(
                    self._onze_pretendido, tatica, suspensos)
                self.world.formacao_fixa[self.clube_id] = tatica.vagas

    def _sem_suspensos(self, onze: list[int], tatica: Tatica, suspensos: set[int]) -> list[int]:
        if not suspensos & set(onze):
            return list(onze)
        vagas = tatica.vagas_do_campo()
        banco = sorted((p for p in self.world.squad(self.clube_id)
                        if p.id not in onze and p.id not in suspensos),
                       key=lambda p: -p.effective_overall)
        novo = list(onze)
        for i, pid in enumerate(onze):
            if pid not in suspensos or not banco:
                continue
            setor = vagas[i][1] if i < len(vagas) else self.world.players[pid].position
            reserva = next((p for p in banco if p.position == setor), banco[0])
            banco.remove(reserva)
            novo[i] = reserva.id
        return novo

    def _encerrar_desfalques(self, taticas: dict[int, Tatica]) -> None:
        """Depois da data: ninguem mais esta indisponivel, e o onze de cada humano que
        jogou volta a ser o escolhido."""
        self.world.indisponiveis = set()
        for i in taticas:
            h = self.humanos[i]
            if h._onze_pretendido:
                self.world.escalacao_fixa[h.clube_id] = list(h._onze_pretendido)

    def _cartoes_da_data(self, comp: str, resultados, detalhadas, clubes: set[int]) -> None:
        """Cumpre os ganchos de quem jogou e soma os cartoes novos.

        A ordem importa: primeiro cumpre (quem estava suspenso ficou fora DESTA data),
        depois registra (o vermelho de hoje suspende o PROXIMO jogo). Os cartoes dos jogos
        do motor rapido saem de um stream proprio: sorteia-los no stream da partida
        mudaria os placares de todos os saves.
        """
        from fm.central import cartoes as cartoes_dos_lances
        from fm.disciplina import cartoes_da_partida

        self.disciplina.cumprir(comp, clubes, self.world)
        detalhada_de = _por_jogo(detalhadas)
        for r in resultados:
            detalhada = detalhada_de.get((r.home, r.away))
            if detalhada is not None:
                # os da partida detalhada ja entraram nos cadernos pelos eventos
                self.disciplina.registrar(comp, cartoes_da_partida(detalhada))
                continue
            # os dos outros jogos vem dos lances da central, que ja os somou nos cadernos
            lances = self.lances_da_data.get((r.home, r.away), [])
            self.disciplina.registrar(comp, cartoes_dos_lances(lances))

    def hoje(self) -> date:
        """O dia da proxima data da agenda (fm.agenda). E o "hoje" do lobby."""
        return self.dia(self.data)

    def _anotar_recorde(self, r: Result, competicao: str) -> None:
        """Os recordes da carreira do tecnico: maior vitoria, maior derrota, jogo com mais
        gols e as maiores sequencias (invicta e de vitorias)."""
        casa = r.home == self.clube_id
        pro, contra = (r.goals_home, r.goals_away) if casa else (r.goals_away, r.goals_home)
        rival = self.world.clubs[r.away if casa else r.home].name
        jogo = {"placar": f"{pro} x {contra}", "rival": rival, "casa": casa,
                "competicao": competicao, "temporada": self.temporada,
                "dia": self.dia(self.data).strftime("%d/%m/%Y"),
                "clube": self.clube.name, "margem": pro - contra, "gols": pro + contra}
        rec = self.recordes
        chaves = (("maior_vitoria", lambda j: (j["margem"], j["gols"]), pro > contra),
                  ("maior_derrota", lambda j: (-j["margem"], j["gols"]), pro < contra),
                  ("mais_gols", lambda j: (j["gols"], j["margem"]), True))
        for chave, ordem, vale in chaves:
            if vale and (chave not in rec or ordem(jogo) > ordem(rec[chave])):
                rec[chave] = jogo
        seq = rec.setdefault("_atual", {"invicto": 0, "vitorias": 0})
        seq["invicto"] = seq["invicto"] + 1 if pro >= contra else 0
        seq["vitorias"] = seq["vitorias"] + 1 if pro > contra else 0
        for chave in ("invicto", "vitorias"):
            melhor = rec.get(f"sequencia_{chave}", {"jogos": 0})
            if seq[chave] > melhor["jogos"]:
                rec[f"sequencia_{chave}"] = {"jogos": seq[chave], "ate": jogo["dia"],
                                             "temporada": self.temporada,
                                             "clube": self.clube.name}

    def _somar_lendas(self) -> None:
        """Na virada: o ano de cada jogador do clube entra na conta das lendas dele."""
        meus = {p.id for p in self.world.squad(self.clube_id)}
        for pid, linha in self.estatisticas.por_jogador.items():
            if pid not in meus or not linha.jogos:
                continue
            p = self.world.players[pid]
            chave = f"{self.clube_id}:{pid}"
            lenda = self.lendas.setdefault(chave, {
                "jogador": pid, "nome": p.name, "posicao": p.position,
                "clube": self.clube.name, "clube_id": self.clube_id,
                "jogos": 0, "gols": 0, "assistencias": 0, "temporadas": []})
            lenda["jogos"] += linha.jogos
            lenda["gols"] += linha.gols
            lenda["assistencias"] += linha.assistencias
            lenda["temporadas"].append(self.temporada)

    def _moral_da_data(self, resultados, detalhadas) -> None:
        """A moral de quem jogou e a quimica de cada clube depois da data (fm.moral). Antes
        da energia: o onze de cada clube ainda e o que entrou em campo."""
        from collections import Counter

        from fm.moral import depois_do_jogo
        fora = set(self.world.indisponiveis)
        detalhada_de = _por_jogo(detalhadas)
        for r in resultados:
            detalhada = detalhada_de.get((r.home, r.away))
            if detalhada is not None:
                entraram = set(detalhada.entrada)
                gols = Counter(e.jogador for e in detalhada.eventos if e.tipo == "gol")
            else:
                lances = self.lances_da_data.get((r.home, r.away), [])
                entraram = ({p.id for p in self.world.best_xi(r.home)}
                            | {p.id for p in self.world.best_xi(r.away)}
                            | {x.segundo for x in lances
                               if x.tipo == "substituicao" and x.segundo})
                gols = Counter(x.jogador for x in lances if x.tipo == "gol")
            depois_do_jogo(self.world, r.home, r.goals_home, r.goals_away, entraram, gols, fora)
            depois_do_jogo(self.world, r.away, r.goals_away, r.goals_home, entraram, gols, fora)

    def _lesoes_da_data(self, resultados, detalhadas) -> None:
        """Registra os machucados de hoje (gravidade num stream proprio) e da alta a quem
        ja pode jogar na data seguinte. Chamada ANTES de `self.data` andar."""
        from fm.central import lesionados
        hoje = self.hoje()
        voltaram = self.medico.dar_alta(self.dia(self.data + 1))
        novos: list[int] = []
        detalhada_de = _por_jogo(detalhadas)
        for r in resultados:
            detalhada = detalhada_de.get((r.home, r.away))
            if detalhada is not None:
                novos += detalhada.lesionados
            else:
                novos += lesionados(self.lances_da_data.get((r.home, r.away), []))
        novas = self.medico.registrar(novos, self.streams.get("gravidade", self.temporada,
                                                              self.data), hoje)
        for h in self.humanos:
            meus = {p.id for p in self.world.squad(h.clube_id)}
            h.boletim_medico = {
                "lesoes": [(pid, les.tipo, les.dias) for pid, les in novas.items()
                           if pid in meus],
                "voltaram": [pid for pid in voltaram if pid in meus],
            }

    def lesionados_do_clube(self, clube: int | None = None) -> dict:
        """{id: Lesao} de quem esta no departamento medico."""
        ids = {p.id for p in self.world.squad(clube or self.clube_id)}
        return {pid: les for pid, les in self.medico.lesionados.items() if pid in ids}

    def _detalhar(self, resultados) -> None:
        """Gera os lances dos jogos do motor rapido (fm.central). Stream por jogo: a ordem
        em que as divisoes sao jogadas nao muda quem marcou em cada partida."""
        from fm.central import detalhar
        for r in resultados:
            rng = self.streams.get("central", self.temporada, self.data, r.home, r.away)
            rng_les = self.streams.get("lesoes", self.temporada, self.data, r.home, r.away)
            self.lances_da_data[(r.home, r.away)] = detalhar(self.world, r, rng, rng_les)

    def _gastar_energia(self, jogaram: set[int], custos: dict[int, float]) -> None:
        """Energia entre rodadas.

        TODO MUNDO recupera; quem jogou paga o custo por cima. A recuperacao e
        proporcional ao quanto falta para 100, o que cria EQUILIBRIO: quem joga toda rodada
        estabiliza perto de 81%, nao desaba ate o piso. `custos` = {clube: fator da
        marcacao} dos clubes de tecnico humano; os da IA pagam 1.
        """
        # A recuperacao conta DIAS de descanso desde a ultima conta, e nao datas: no
        # calendario real ha semana com um jogo e semana com tres. A taxa antiga valia para
        # quatro dias, o intervalo fixo de antes.
        hoje = self.hoje()
        dias = (hoje - self.ultimo_dia_de_energia).days if self.ultimo_dia_de_energia else 4
        self.ultimo_dia_de_energia = hoje
        taxa = 1 - (1 - TAXA_DE_RECUPERACAO) ** (max(dias, 0) / 4)
        for club_id in self.world.clubs:
            onze = ({p.id for p in self.world.best_xi(club_id)}
                    if club_id in jogaram else set())
            # marcacao forte cansa mais: o preco aparece na rodada seguinte, nao nesta
            custo = CONDITION_COST * custos.get(club_id, 1.0)
            for p in self.world.squad(club_id):
                recupera = taxa * (100 - p.condition)
                delta = recupera - (custo if p.id in onze else 0.0)
                # min/max, nao np.clip: num numero solto o clip custa 20x mais, e aqui
                # ele rodava 4 milhoes de vezes por temporada com o mundo inteiro
                p.condition = int(min(max(p.condition + delta, 25), 100))

    # ---------------------------------------------------------------- virar o ano

    def numeros_do_ano(self) -> dict[str, int]:
        """Vitorias, empates e derrotas do usuario no ano, liga e copas juntas."""
        meus = [r for r in self.jogos() if self.clube_id in (r.home, r.away)]
        for a in self.copas.values():
            meus += [r for r in a.resultados_do_ano if self.clube_id in (r.home, r.away)]
        v = e = d = gp = gc = 0
        for r in meus:
            casa = r.home == self.clube_id
            pro, contra = ((r.goals_home, r.goals_away) if casa
                           else (r.goals_away, r.goals_home))
            gp, gc = gp + pro, gc + contra
            v, e, d = v + (pro > contra), e + (pro == contra), d + (pro < contra)
        return {"jogos": len(meus), "vitorias": v, "empates": e, "derrotas": d,
                "gols_pro": gp, "gols_contra": gc}

    def artilharia_do_ano(self, quantos: int = 10) -> dict[str, list[dict]]:
        """O top de cada competicao do ano, com nome e clube gravados por extenso: o
        jogador pode se aposentar, e o historico nao pode depender de ele existir."""
        fora = {}
        for comp, est in self.estatisticas_por_comp.items():
            linhas = []
            for x in est.artilheiros(self.world, quantos):
                p = self.world.players[x.jogador]
                clube = self.world.clubs[p.club_id].name if p.club_id in self.world.clubs else ""
                linhas.append({"jogador": x.jogador, "nome": p.name, "clube": clube,
                               "gols": x.gols, "assistencias": x.assistencias,
                               "jogos": x.jogos})
            fora[comp] = linhas
        return fora

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
        # antes de qualquer saida: o ano de quem jogou aqui vai para as lendas do clube
        humanos = range(len(self.humanos))
        for i in humanos:
            with self._como(i):
                self._somar_lendas()

        cfgs = {n: load_league(n) for n in self.ligas}
        tabelas = {n: self.tabela(n) for n in self.ligas}
        # a temporada das ligas de fora, com os elencos DESTE ano (antes de envelhecer e
        # do mercado): e ela que manda os clubes delas para as copas do ano que vem
        tabelas_de_fora = self._simular_ligas_de_fora()
        campeoes = {n: self.world.clubs[t[0].club_id].name for n, t in tabelas.items()}
        # o ano de cada humano, lido antes de as divisoes mudarem
        do_ano = []
        for i in humanos:
            with self._como(i):
                do_ano.append({"liga": self.liga, "posicao": self.posicao(),
                               "numeros": self.numeros_do_ano()})

        # A ordem e a regra. As contas fecham na divisao em que o ano foi jogado, e so
        # depois o clube troca de divisao; o mercado vem depois do envelhecimento para
        # negociar overalls deste ano, e a base entra por ultimo, tapando o que sobrou.
        # As tabelas e os campeoes de copa deste ano decidem quem disputa o que no ano que
        # vem -- e a cascata de vagas que ja estava escrita nos arquivos de torneio, agora
        # alimentada pela temporada de verdade em vez da forca desenhada.
        titulos = self._titulos_de_copa()
        premios_do_ano, dados = self._premios_e_desempenho(tabelas, cfgs)
        premios_de_copa = self._premiar_copas()
        de_humano = self.clubes_humanos()
        balancos = fechar_o_ano(self.world, tabelas, cfgs, extras=premios_de_copa,
                                jogos_extras=self._jogos_de_copa(),
                                valores=self.valor_de_elenco, clube_usuario=de_humano)
        mudancas = acesso_e_rebaixamento(self.world, self.ligas, tabelas, cfgs)
        self._atualizar_tecnicos(dados, mudancas, cfgs)
        rng = self.streams.get("virada", self.temporada)
        # o alvo de elenco e o tamanho ANTES das aposentadorias: cada clube repoe o que
        # perdeu e mantem a propria dimensao, em vez de convergir todo mundo para o mesmo
        alvos = {c.id: len(c.player_ids) for c in self.world.clubs.values()}
        # os emprestimos acabam antes de tudo: quem volta envelhece, renova ou sai no
        # clube dono, e a tela de fim de ano nao confunde a volta com garoto da base
        from fm.negocios import devolver_emprestimos
        voltas = devolver_emprestimos(self.world)
        # o elenco de cada humano antes da virada e, para dizer na tela POR QUE cada um
        # saiu, a idade e a posicao de cada jogador
        for i in humanos:
            elenco = self.world.squad(self.humanos[i].clube_id)
            do_ano[i]["antes"] = {p.id: (p.name, p.overall) for p in elenco}
            do_ano[i]["ficha_antes"] = {p.id: (p.age(self.temporada), p.position)
                                        for p in elenco}
        envelhecimento = envelhecer(self.world, rng, self.temporada)
        from fm.negocios import livres_que_se_aposentam, vencer_contratos
        for h in self.humanos:
            for prop in h.propostas:
                if prop.status == "pendente":
                    prop.status = "expirada"
        # contrato vencido acaba ANTES da janela: quem sai de graca ja pode ser disputado.
        # Stream proprio, para nao mexer no sorteio da janela e da base.
        contratos = vencer_contratos(self.world, self.temporada + 1, de_humano,
                                     self.streams.get("contratos", self.temporada))
        aposentados_livres = livres_que_se_aposentam(self.world, self.temporada + 1)
        # so as ligas que a carreira joga: as de fora sao pano de fundo (fm.mercado.janela)
        da_carreira = {k for n in self.ligas for k in self.world.leagues[self._id(n)].club_ids}
        # Os clubes dos humanos NAO entram na janela da IA, nem comprando nem vendendo. Ela
        # levava jogador do usuario (ate em venda forcada, com o caixa no vermelho) e punha
        # gente no elenco sem perguntar. Quem decide o elenco dele e ele: comprando no
        # mercado, aceitando ou recusando as propostas que chegam.
        da_carreira -= de_humano
        transferencias = janela(self.world, rng, self.temporada + 1, da_carreira)
        novos = repor_elencos(self.world, rng, self.temporada + 1, alvos=alvos)
        # a pre-temporada da moral: volta ao normal, e o elenco novo ainda nao se conhece
        from collections import Counter as _Contagem

        from fm.moral import na_virada
        na_virada(self.world, _Contagem(t.para for t in transferencias))

        def resumo_do_humano(ano: dict) -> dict:
            """O fim de ano do humano da vez: e isto que a tela de fim de ano mostra."""
            antes, ficha_antes = ano["antes"], ano["ficha_antes"]
            minha_posicao = ano["posicao"]
            agora = {p.id: p for p in self.world.squad(self.clube_id)}
            saidas = [nome for pid, (nome, _) in antes.items() if pid not in agora]
            # O motivo de cada saida. Antes a tela so dizia "N aposentadorias no mundo", e o
            # veterano do usuario sumia do elenco sem explicacao.
            meus_contratos = [x for x in contratos
                              if x["do_usuario"] and x["clube"] == self.clube_id]
            fim_de_contrato = {x["jogador"] for x in meus_contratos}
            saidas_do_clube = []
            for pid, (nome, ovr) in antes.items():
                if pid in agora:
                    continue
                idade, posicao = ficha_antes[pid]
                if pid not in self.world.players:
                    motivo = "aposentou-se"
                elif pid in fim_de_contrato:
                    motivo = "fim de contrato"
                else:
                    destino = self.world.players[pid].club_id
                    motivo = (f"foi para o {self.world.clubs[destino].name}"
                              if destino in self.world.clubs else "saiu do clube")
                saidas_do_clube.append({"nome": nome, "overall": ovr, "idade": idade,
                                        "posicao": posicao, "motivo": motivo})
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
            ano["mudanca"] = minha
            # a régua do ano: a diretoria cobra a meta que ela mesma deu em marco
            clima_final = {
                "torcida": round(self.aprovacao.torcida, 1),
                "diretoria": round(self.aprovacao.diretoria, 1),
                "meta": self.aprovacao.meta.texto if self.aprovacao.meta else "",
                "bateu_a_meta": bool(self.aprovacao.meta
                                     and minha_posicao <= self.aprovacao.meta.posicao),
            }
            return {
                "temporada": self.temporada,
                "campeoes": campeoes,
                "minha_liga": ano["liga"],
                "minha_posicao": minha_posicao,
                "meus_numeros": ano["numeros"],
                "clube": self.world.clubs[self.clube_id].name,
                "subi": bool(minha and minha.subiu),
                "cai": bool(minha and not minha.subiu),
                "promovidos": [self.world.clubs[m.clube].name for m in mudancas if m.subiu],
                "rebaixados": [self.world.clubs[m.clube].name for m in mudancas
                               if not m.subiu],
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
                "minha_campanha": {
                    n: ("campeao" if a.campeao == self.clube_id else
                        "vice" if a.vice == self.clube_id else
                        f"{a.etapas_vividas.get(self.clube_id, 0)} de "
                        f"{a.etapas_totais} etapas")
                    for n, a in self.copas.items()
                    if self.clube_id in a.etapas_vividas},
                "premios_de_copa": premios_de_copa.get(self.clube_id, 0),
                "clima": clima_final,
                "emprestimos_encerrados": [v for v in voltas
                                           if self.clube_id in (v["de"], v["para"])],
                "demitido": False,       # preenchido logo abaixo, depois da regua do ano
                "motivo_da_demissao": "",
                "aposentadorias_do_clube": saidas,
                "saidas_do_clube": saidas_do_clube,
                "destaques_do_clube": destaques,
                "contratos_encerrados": meus_contratos,
                "livres_aposentados": len(aposentados_livres),
                "movimentos": list(self.movimentos),
                # os artilheiros de cada competicao do ano ficam guardados: e o que a tela
                # de artilharia mostra das temporadas passadas
                "artilharia": self.artilharia_do_ano(),
                "base_do_clube": base,
            }

        resumos = []
        for i in humanos:
            with self._como(i):
                resumos.append(resumo_do_humano(do_ano[i]))
                self.historico.append(resumos[-1])

        self.temporada += 1
        self.world.season_year = self.temporada
        self.rodada = 0
        self.world.escalacao_fixa.clear()
        self.world.formacao_fixa.clear()
        for p in self.world.players.values():
            p.condition = 100
        from fm.diretoria import decidir_demissao
        for i in humanos:
            with self._como(i):
                ano, resumo = do_ano[i], resumos[i]
                minha = ano["mudanca"]
                motivo = decidir_demissao(
                    self.aprovacao, rodada=self.rodada, fim_da_temporada=True,
                    posicao=ano["posicao"], clubes=len(tabelas[ano["liga"]]),
                    rebaixado=bool(minha and not minha.subiu))
                if motivo and not self.aprovacao.demitido:
                    self.aprovacao.demitido = True
                    self.aprovacao.motivo = motivo
                resumo["demitido"] = self.aprovacao.demitido
                resumo["motivo_da_demissao"] = self.aprovacao.motivo
                resumo["premios"] = premios_do_ano
        self._mercado_de_tecnicos(dados)
        for i in humanos:
            resumos[i]["convites"] = list(self.humanos[i].convites)
        for i in humanos:
            with self._como(i):
                self.convidar_para_selecao()
                resumos[i]["convite_selecao"] = self.convite_selecao

        self.tabelas_do_ano_anterior = self._tabelas_para_classificacao(
            {**tabelas, **tabelas_de_fora}, titulos)
        self.exportados = {}
        self._novo_calendario()
        self.retrato = self._fotografar()
        return resumos[self.ativo]

    def _fotografar(self) -> bytes:
        """O estado inteiro, inclusive o ponto de cada gerador aleatorio: e o que faz o ano
        refeito a partir do retrato sair identico ao do replay completo."""
        import pickle
        anterior, self.retrato = self.retrato, None
        try:
            return pickle.dumps(self, protocol=5)
        finally:
            self.retrato = anterior

    def salvar(self, nome: str) -> Path:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        destino = SAVES_DIR / f"{nome}.json"
        _arquivo_do_ponto(nome).unlink(missing_ok=True)   # o ponto antigo nao vale mais
        primeiro, *outros = self.humanos
        conteudo = {
            "seed": self.seed, "ligas": self.ligas,
            **_humano_no_save(primeiro),
            "temporada_inicial": self.temporada - len(primeiro.historico),
            # `data`, nao `rodada`: a temporada anda por datas, e uma delas pode ser
            # copa. Guardar a rodada da liga perderia os jogos de copa no replay.
            "temporada": self.temporada, "data": self.data,
            "tatica_persistente": primeiro.tatica_persistente,
            "acoes": self.acoes,
        }
        if outros:
            # os outros tecnicos humanos (o online), com as decisoes de cada um; as acoes
            # deles estao em `acoes`, marcadas com o numero do humano
            conteudo["outros_humanos"] = [_humano_no_save(h) for h in outros]
            conteudo["ativo"] = self.ativo
        destino.write_text(json.dumps(conteudo, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        if self.retrato is not None:
            _gravar_retrato(nome, self.temporada, self.retrato,
                            json.loads(destino.read_text(encoding="utf-8")))
        if not self._no_meio_da_data:
            _gravar_ponto(nome, self, destino.read_text(encoding="utf-8"))
        return destino

    @classmethod
    def carregar(cls, nome: str) -> Carreira:
        origem = SAVES_DIR / f"{nome}.json"
        if not origem.exists():
            raise FileNotFoundError(f"save {nome!r} nao existe. Ha: {saves_disponiveis()}")
        texto = origem.read_text(encoding="utf-8")
        pronta = _do_ponto(nome, texto)
        if pronta is not None:
            return pronta
        d = _atualizar_save(json.loads(texto))
        no_save = [d, *d.get("outros_humanos", [])]
        atalho = _do_retrato(nome, d)
        if atalho is not None:
            # as decisoes do ano em curso vem do save; as de antes ja estao no retrato
            for h, x in zip(atalho.humanos, no_save, strict=True):
                _decisoes_do_save(h, x)
            atalho._refazer_ate(d)
            atalho.ativo = min(int(d.get("ativo", 0)), len(atalho.humanos) - 1)
            return atalho
        cfgs = [load_league(n) for n in d["ligas"]]
        world, streams = build_world(cfgs, seed=d["seed"])
        if any(x["clube_id"] not in world.clubs for x in no_save):
            # os packs foram refeitos depois do save: o mesmo seed gera outro mundo
            raise ValueError("o save e de uma versao antiga do jogo e o clube dele nao "
                             "existe mais neste mundo -- comece uma carreira nova")
        # o replay parte do clube em que a carreira comecou; as trocas vem nas acoes
        humanos = [Humano(clube_id=x.get("clube_inicial") or x["clube_id"], tecnico_id=i)
                   for i, x in enumerate(no_save)]
        c = cls(seed=d["seed"], ligas=list(d["ligas"]), temporada=d["temporada_inicial"],
                humanos=humanos)
        for h, x in zip(humanos, no_save, strict=True):
            _decisoes_do_save(h, x)
            h.clube_inicial = h.clube_id
            # save sem a marca e de antes da regra: a rodada sem decisao joga no padrao
            h.tatica_persistente = bool(d.get("tatica_persistente", False))
        c._montar(world, streams)
        c._refazer_ate(d)
        c.ativo = min(int(d.get("ativo", 0)), len(humanos) - 1)
        _gravar_retrato(nome, c.temporada, c.retrato, d)
        return c

    def _refazer_ate(self, d: dict) -> None:
        """REPLAY: as temporadas sao refeitas com as mesmas decisoes, da temporada em que a
        carreira esta ate a do save. Se isto divergir, o determinismo do motor quebrou -- e
        o save seria a primeira vitima. Os negocios entram no mesmo ponto em que foram
        feitos: antes da data seguinte."""
        acoes = d.get("acoes", [])
        while self.temporada < d["temporada"]:
            while not self.acabou:
                self._aplicar_acoes_do_save(acoes)
                self.avancar()
            self._aplicar_acoes_do_save(acoes)
            self.virar_o_ano()
        while self.data < d.get("data", d.get("rodada", 0)) and not self.acabou:
            self._aplicar_acoes_do_save(acoes)
            self.avancar()
        self._aplicar_acoes_do_save(acoes)

def _atalho(nome: str) -> property:
    def ler(self):
        return getattr(self.humanos[_vez(self)], nome)

    def escrever(self, valor):
        setattr(self.humanos[_vez(self)], nome, valor)
    return property(ler, escrever, doc=f"{nome} do tecnico humano da vez (Humano.{nome})")


CAMPOS_DO_HUMANO = tuple(f.name for f in fields(Humano) if f.name != "tecnico_id")
for _nome in CAMPOS_DO_HUMANO:
    setattr(Carreira, _nome, _atalho(_nome))


def _cobradores_de(h: Humano) -> list[int]:
    """A ordem de batedores de penalti que o tecnico deixou."""
    return [h.funcoes[k] for k in ("penaltis", "penaltis2", "penaltis3") if k in h.funcoes]


def _por_jogo(detalhadas) -> dict[tuple[int, int], Partida]:
    """{(mandante, visitante): partida} das partidas do motor de eventos da data."""
    return {(d.casa, d.fora): d for d in detalhadas or ()}


def _humano_no_save(h: Humano) -> dict:
    """O que o save guarda de cada tecnico humano: o clube e as decisoes. O resto o
    replay refaz."""
    return {"clube_id": h.clube_id, "clube_inicial": h.clube_inicial,
            "decisoes": {k: asdict(v) for k, v in h.decisoes.items()},
            "na_partida": h.na_partida, "treinador": h.treinador,
            "funcoes": h.funcoes, "observados": h.observados}


def _decisoes_do_save(h: Humano, x: dict) -> None:
    h.decisoes = {k: Decisao(**v) for k, v in x.get("decisoes", {}).items()}
    h.na_partida = x.get("na_partida", {})
    h.treinador = x.get("treinador", h.treinador)
    h.funcoes = x.get("funcoes", {})
    h.observados = x.get("observados", [])



# ---------------------------------------------------------------- o retrato do save
#
# Carregar e refazer a carreira inteira a partir da semente: com as 40 ligas, uns 47 s por
# temporada -- uma carreira de dez anos levava oito minutos para abrir. O retrato e a
# carreira no comeco da temporada do save; carregar parte dele e refaz so o ano em curso.
#
# O save continua sendo a semente e as decisoes, e o retrato e so um atalho: se ele nao
# bater com o save ou com a versao do jogo, e ignorado e o replay completo roda. A CHAVE
# junta o que muda o mundo: o codigo do motor, os dados das ligas e torneios, e as
# decisoes gravadas ANTES daquela temporada. Atualizar o jogo (a correcao do rebaixamento,
# por exemplo) invalida o retrato -- carregar um mundo feito pelo codigo antigo seria
# carregar o defeito junto.

_IMPRESSAO: str | None = None


def _impressao_digital() -> str:
    """O hash do que decide o mundo: o codigo do motor (fm/, sem a tela e o importador) e
    os dados de liga, pack, torneio, cor e ajuste."""
    global _IMPRESSAO
    if _IMPRESSAO is None:
        import hashlib
        raiz = Path(__file__).resolve().parent.parent
        arquivos = sorted(
            [p for p in (raiz / "fm").rglob("*.py")
             if "__pycache__" not in p.parts and "importer" not in p.parts
             and "web" not in p.parts]
            + [p for pasta in ("leagues", "packs", "torneios", "cores", "ajustes")
               for p in (raiz / "data" / pasta).glob("*.toml")])
        h = hashlib.sha256()
        for p in arquivos:
            h.update(str(p.relative_to(raiz)).encode())
            h.update(p.read_bytes())
        _IMPRESSAO = h.hexdigest()
    return _IMPRESSAO


def _chave_do_retrato(d: dict, temporada: int) -> str:
    """O que precisa ser igual para o retrato da `temporada` valer para o save `d`."""
    import hashlib

    def antes(chave: str) -> bool:
        return int(str(chave).split(":", 1)[0]) < temporada

    base = {
        "versao": _impressao_digital(), "temporada": temporada,
        "seed": d["seed"], "ligas": d["ligas"],
        "clube_inicial": d.get("clube_inicial") or d["clube_id"],
        "temporada_inicial": d["temporada_inicial"], "treinador": d.get("treinador"),
        "tatica_persistente": bool(d.get("tatica_persistente", False)),
        "decisoes": {k: v for k, v in d.get("decisoes", {}).items() if antes(k)},
        "na_partida": {k: v for k, v in d.get("na_partida", {}).items() if antes(k)},
        "acoes": [a for a in d.get("acoes", []) if a.get("temporada", 0) < temporada],
    }
    if d.get("outros_humanos"):
        # os outros tecnicos tambem decidem o mundo; sem eles, a chave e a de sempre
        base["outros_humanos"] = [
            {"clube_inicial": x.get("clube_inicial") or x["clube_id"],
             "treinador": x.get("treinador"),
             "decisoes": {k: v for k, v in x.get("decisoes", {}).items() if antes(k)},
             "na_partida": {k: v for k, v in x.get("na_partida", {}).items() if antes(k)}}
            for x in d["outros_humanos"]]
    return hashlib.sha256(json.dumps(base, sort_keys=True, default=str).encode()).hexdigest()


def _arquivo_do_retrato(nome: str) -> Path:
    return SAVES_DIR / f"{nome}.retrato"


def _gravar_retrato(nome: str, temporada: int, retrato: bytes | None, d: dict) -> None:
    """Grava o retrato ao lado do save. Falhar aqui nao pode derrubar o save: sem retrato,
    carregar so fica mais lento."""
    if retrato is None:
        return
    import gzip
    import pickle
    try:
        conteudo = pickle.dumps({"chave": _chave_do_retrato(d, temporada),
                                 "temporada": temporada, "estado": retrato}, protocol=5)
        _arquivo_do_retrato(nome).write_bytes(gzip.compress(conteudo, compresslevel=3))
    except OSError:
        pass


def _retrato_valido(nome: str, d: dict) -> bytes | None:
    """O estado guardado no retrato, se ele valer para este save; senao None."""
    import gzip
    import pickle
    arq = _arquivo_do_retrato(nome)
    if not arq.exists():
        return None
    try:
        dados = pickle.loads(gzip.decompress(arq.read_bytes()))
        if dados.get("temporada", 10**6) > d["temporada"]:
            return None
        if dados.get("chave") != _chave_do_retrato(d, dados["temporada"]):
            return None
        return dados["estado"]
    except Exception:                     # retrato corrompido ou de outra versao
        return None


def _do_retrato(nome: str, d: dict) -> Carreira | None:
    """A carreira do retrato, se ele valer para este save; senao None (replay completo)."""
    import pickle
    estado = _retrato_valido(nome, d)
    if estado is None:
        return None
    try:
        c = pickle.loads(estado)
    except Exception:
        return None
    c.retrato = estado
    return c


# ---------------------------------------------------------------- o ponto do save
#
# O retrato e o comeco da temporada; o save no meio dela ainda refazia todas as datas ate
# ali -- com o mundo inteiro, ~20 s para abrir um save de novembro. O PONTO e a carreira
# exatamente como estava na hora de salvar. Vale so para aquele save, naquela versao do
# jogo: a chave e o texto do save mais a impressao digital do motor. Qualquer diferenca e
# o caminho de sempre (retrato + replay), que da o mesmo mundo, so que mais devagar.


def _arquivo_do_ponto(nome: str) -> Path:
    return SAVES_DIR / f"{nome}.ponto"


def _chave_do_ponto(texto_do_save: str) -> str:
    import hashlib
    return hashlib.sha256((_impressao_digital() + texto_do_save).encode()).hexdigest()


def _gravar_ponto(nome: str, c: Carreira, texto_do_save: str) -> None:
    """Falhar aqui nao derruba o save: sem ponto, carregar so fica mais lento."""
    import gzip
    import pickle
    try:
        estado = c._fotografar()          # sem o retrato dentro: ele tem arquivo proprio
        conteudo = pickle.dumps({"chave": _chave_do_ponto(texto_do_save),
                                 "estado": estado}, protocol=5)
        _arquivo_do_ponto(nome).write_bytes(gzip.compress(conteudo, compresslevel=1))
    except (OSError, pickle.PicklingError, TypeError, AttributeError):
        _arquivo_do_ponto(nome).unlink(missing_ok=True)


def _do_ponto(nome: str, texto_do_save: str) -> Carreira | None:
    """A carreira do ponto, se ele for deste save e desta versao; senao None."""
    import gzip
    import pickle
    arq = _arquivo_do_ponto(nome)
    if not arq.exists():
        return None
    try:
        dados = pickle.loads(gzip.decompress(arq.read_bytes()))
        if dados.get("chave") != _chave_do_ponto(texto_do_save):
            return None
        c = pickle.loads(dados["estado"])
    except Exception:                     # ponto corrompido ou de outra versao
        return None
    # o retrato do comeco do ano volta do arquivo dele: e o que o proximo save regrava
    c.retrato = _retrato_valido(nome, _atualizar_save(json.loads(texto_do_save)))
    return c


def _atualizar_save(d: dict) -> dict:
    """Traz um save de formato antigo para o atual.

    O primeiro formato era de uma liga so ("liga") e chaveava as decisoes so pela rodada
    ("3"); o atual tem a piramide ("ligas") e chaveia por "temporada:rodada". Sem isto,
    abrir um save antigo derrubava o servidor e a tela ficava em "Carregando..." para
    sempre. O replay refaz o mundo com o motor de HOJE, entao os resultados podem nao
    ser os que foram jogados na epoca -- mas as decisoes do jogador sao as dele.
    """
    d = dict(d)
    if "ligas" not in d:
        d["ligas"] = [d["liga"]]
    d.setdefault("temporada_inicial", d["temporada"])
    d["decisoes"] = {(k if ":" in str(k) else f"{d['temporada_inicial']}:{k}"): v
                     for k, v in d.get("decisoes", {}).items()}
    return d


def saves_disponiveis() -> list[str]:
    return sorted(p.stem for p in SAVES_DIR.glob("*.json")) if SAVES_DIR.exists() else []
