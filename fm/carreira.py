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
from datetime import date
from pathlib import Path

import numpy as np

from fm.calendario import dia_da_data
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
    "ENG": ("champions", "europa_league"),
    "ITA": ("champions", "europa_league"),
    "GER": ("champions", "europa_league"),
    "FRA": ("champions", "europa_league"),
    "POR": ("champions", "europa_league"),
    "ARG": ("libertadores", "sudamericana"),
}
COPAS = COPAS_POR_PAIS["BRA"]

MAX_TROCAS = 5


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
    aprovacao: object | None = None
    estatisticas: object | None = None
    treinador: str = "Treinador"
    # O que o usuario fez DURANTE cada partida, por "temporada:data": trocas e mudancas de
    # tatica, com o minuto. Sem isto o replay do save jogava sem as substituicoes e o
    # placar carregado divergia do placar jogado.
    na_partida: dict[str, dict] = field(default_factory=dict)
    # os outros jogos da data, ja resolvidos, enquanto a partida do usuario ainda corre:
    # e o painel "rodada ao vivo"
    parciais: list = field(default_factory=list)
    # os lances (gols com autor e minuto, cartoes, trocas) dos jogos do motor rapido na data
    # que esta sendo jogada, por (mandante, visitante). E a central da rodada.
    lances_da_data: dict = field(default_factory=dict)
    # Capitao e cobradores. Os de penalti (penaltis, penaltis2, penaltis3) o motor le;
    # capitao, faltas e escanteios ainda nao: nao ha bola parada alem do penalti.
    funcoes: dict[str, int] = field(default_factory=dict)
    # quem decide o batedor na hora do penalti, so durante um avancar(); nao vai ao save
    _pedido_de_penalti: object = field(default=None, repr=False, compare=False)
    # a lista de observacao do mercado
    observados: list[int] = field(default_factory=list)
    # um caderno de artilharia por competicao ("brasil_real", "libertadores"...) no ano
    estatisticas_por_comp: dict = field(default_factory=dict)
    # {liga: {rodada: selecao}} -- a selecao de cada rodada de liga do ano (fm.selecao)
    selecoes: dict = field(default_factory=dict)
    # cartoes acumulados e suspensoes, por competicao (fm.disciplina)
    disciplina: object | None = None
    # quem esta machucado e por quantos jogos (fm.lesoes). Como o gancho, nao vai ao
    # save: o replay refaz as mesmas lesoes.
    medico: object | None = None
    # o boletim da ultima data do usuario: [(id, tipo, jogos)] de quem se machucou e
    # [id] de quem voltou. E o que as mensagens do departamento medico mostram.
    boletim_medico: dict = field(default_factory=dict)
    # Negocios do usuario (fm.negocios): compra, renovacao, venda e resposta a proposta,
    # cada um com a temporada e a data em que aconteceu. E isto que o save guarda e o
    # replay reaplica no mesmo ponto -- o resto dos negocios e deterministico.
    acoes: list[dict] = field(default_factory=list)
    propostas: list = field(default_factory=list)        # recebidas no ano (fm.negocios)
    movimentos: list[dict] = field(default_factory=list)  # historico de entradas e saidas
    # o onze que o usuario ESCOLHEU, guardado enquanto a data corre com o reserva no lugar
    # do suspenso -- depois da data ele volta, e o suspenso volta sozinho quando cumprir
    _onze_pretendido: list[int] = field(default_factory=list)
    # Os tecnicos do mundo (fm.tecnicos), o usuario com id 0. Gerados pela seed e
    # atualizados na virada: nao vao ao save, o replay refaz.
    tecnicos: dict = field(default_factory=dict)
    # clubes que chamam o usuario agora (na virada ou depois de uma demissao) e as vagas
    # que a IA preenche na proxima data
    convites: list[int] = field(default_factory=list)
    vagas: list[int] = field(default_factory=list)
    premios: dict = field(default_factory=dict)          # {temporada: premios do ano}
    # o clube em que a carreira COMECOU: o replay parte dele, e as trocas sao acoes
    clube_inicial: int | None = None

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
        from fm.tecnicos import gerar
        self.world = world
        self.streams = streams
        if self.clube_inicial is None:
            self.clube_inicial = self.clube_id
        self._novo_calendario()
        self.tecnicos = gerar(world, {self._id(n) for n in self.ligas},
                              streams.get("tecnicos"), self.temporada, self.clube_id,
                              self.treinador)

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
        self._montar_agenda()
        # o valor de elenco do INICIO do ano e o que paga a receita: sem congelar, comprar
        # jogador aumentaria o faturamento do mesmo ano e o clube rico viraria bola de neve
        from fm.financas import valor_do_elenco
        self.valor_de_elenco = {c.id: valor_do_elenco(self.world, c.id)
                                for c in self.world.clubs.values()}
        self._nova_meta()
        from fm.estatisticas import Estatisticas
        self.estatisticas = Estatisticas(temporada=self.temporada)
        self.estatisticas_por_comp = {}
        self.selecoes = {}
        from fm.disciplina import Disciplina
        self.disciplina = Disciplina()      # gancho nao atravessa a virada do ano
        from fm.lesoes import DepartamentoMedico
        self.medico = DepartamentoMedico()  # a pre-temporada cura todo mundo
        self.boletim_medico = {}
        self.world.indisponiveis = set()

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

    def _ao_ser_demitido(self, meio_do_ano: bool) -> None:
        """A demissao nao encerra a carreira: a reputacao cai e aparecem convites. No meio
        do ano quem chama sao os clubes em crise (o tecnico deles sai para o usuario
        entrar); na virada, as vagas que a IA abriu."""
        from fm import tecnicos as tec
        eu = self.tecnicos.get(tec.USUARIO)
        if eu is None:
            return
        tec.ajustar(eu, tec.DEMISSAO)
        eu.clube = None
        if self.clube_id not in self.vagas:
            self.vagas.append(self.clube_id)
        if meio_do_ano:
            candidatos = self._clubes_em_crise()
            self.convites = tec.convites(self.world, self.tecnicos, candidatos, None, True,
                                         self._clubes_da_ultima_divisao(),
                                         self.streams.get("convites", self.temporada, self.data))

    def _clubes_em_crise(self) -> list[int]:
        """Os 40% de baixo de cada tabela, com tecnico do computador."""
        fora = []
        for nome in self.ligas:
            tabela = self.tabela(nome)
            corte = int(len(tabela) * 0.6)
            fora += [ln.club_id for ln in tabela[corte:] if ln.club_id != self.clube_id]
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
        eu = self.tecnicos[tec.USUARIO]
        eu.clube = clube
        eu.passagens.append([self.temporada, self.world.clubs[clube].name])
        if antigo != clube and antigo not in self.vagas:
            self.vagas.append(antigo)
        self.vagas = [v for v in self.vagas if v != clube]
        for x in (antigo, clube):
            self.world.escalacao_fixa.pop(x, None)
            self.world.formacao_fixa.pop(x, None)
        self.clube_id = clube
        self.decisoes.pop(self._chave(), None)
        self.funcoes, self.observados, self._onze_pretendido = {}, [], []
        self.boletim_medico = {}
        for prop in self.propostas:
            if prop.status == "pendente":
                prop.status = "expirada"
        # diretoria nova, meta nova, clima zerado
        self.aprovacao = None
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
                                 {n: nome_da_liga(n) for n in self.ligas}, self.temporada)
        for t in self.tecnicos.values():
            t.variacao = round(t.variacao + bonus.get(t.id, 0.0), 1)

    def _mercado_de_tecnicos(self, dados: dict) -> None:
        """Fim da virada: a IA demite, o usuario (se demitido) perde reputacao, e as vagas
        viram convites para ele."""
        from fm import tecnicos as tec
        self.vagas = tec.demissoes_da_ia(self.tecnicos, dados)
        demitido = self.demitido
        if demitido:
            self._ao_ser_demitido(meio_do_ano=False)
        # o clube que acabou de demitir o usuario nao o chama de volta
        candidatos = [v for v in self.vagas if not (demitido and v == self.clube_id)]
        reserva = [k for k in self._clubes_da_ultima_divisao() if k != self.clube_id]
        self.convites = tec.convites(self.world, self.tecnicos, candidatos,
                                     None if demitido else self.clube_id, demitido, reserva,
                                     self.streams.get("convites", self.temporada))

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

    def rodadas_da_liga(self, liga: str | None = None) -> int:
        """Quantas rodadas tem UMA divisao. `total_de_rodadas` e a da mais longa -- com a
        Espanha junto, a Segunda tem 42 e a Serie A aparecia como "rodada 4/42"."""
        return max((f.matchday for f in self.calendarios[liga or self.liga]), default=0)

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
        """O onze na ORDEM das vagas da formacao (fm.tatica.VAGAS).

        A escolha do usuario vem como ele deixou. O que sai da escalacao automatica -- ou
        de um save antigo, anterior as vagas -- e arrumado no campo: sem isso o goleiro
        podia cair na vaga de centroavante so por ordem de overall.
        """
        from fm.tatica import arrumar_no_campo
        d = self.decisoes.get(self._chave())
        if d and d.escalacao:
            return list(d.escalacao)
        tatica = self.tatica_atual()
        xi = self.world.best_xi(self.clube_id, tatica.vagas)
        if self.clube_id in self.world.escalacao_fixa and xi and xi[0].position == "GK":
            return [p.id for p in xi]
        return [p.id for p in arrumar_no_campo(xi, tatica.formacao)]

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

    def avancar(self, substituicoes=None, penaltis=None) -> tuple[list[Result], Partida | None]:
        """Joga a proxima DATA e para.

        Data de liga: uma rodada em todas as divisoes, porque a piramide anda junta -- sem
        isso as divisoes ficariam em temporadas diferentes e o acesso nao faria sentido.
        Data de copa: a etapa daquele torneio, com o jogo do usuario em detalhe.
        """
        if self.acabou:
            raise RuntimeError("a temporada acabou; chame virar_o_ano()")
        # convite nao respondido caduca quando a bola rola; a IA ocupa as vagas que sobraram
        if not self.demitido:
            self.convites = []
        if self.vagas:
            from fm.tecnicos import preencher_vagas
            preencher_vagas(self.world, self.tecnicos, self.vagas, self.streams,
                            self.temporada)
            self.vagas = []
        # proposta sem resposta ate o apito da proxima data caduca
        for prop in self.propostas:
            if prop.status == "pendente":
                prop.status = "expirada"
        # `penaltis(partida, minuto, clube)` e chamado em todo penalti da minha partida,
        # dos dois lados (a tela pausa nos dois); so a resposta para o MEU clube vale
        self._pedido_de_penalti = penaltis
        try:
            saida = self._avancar_data(substituicoes)
        finally:
            self._pedido_de_penalti = None
        self._novas_propostas()
        return saida

    def _avancar_data(self, substituicoes=None) -> tuple[list[Result], Partida | None]:
        self.lances_da_data = {}      # os da data anterior ficaram ate agora para a tela
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
        self._preparar_desfalques(self.ligas, tatica)

        meu_jogo = self.proxima_partida()
        detalhada: Partida | None = None
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
                                            fatigue=self.world.fatigue_penalty(cid)))
                for cid in self.world.leagues[lid].club_ids
            }
            rng = self.streams.get("carreira", self.temporada, n, lid)
            style = style_of(cfg)

            if meu_jogo is not None and meu_jogo in partidas:
                # os outros ANTES do meu: enquanto a minha partida pausa, a rodada ao vivo
                # ja tem o que mostrar
                outras = [f for f in partidas if f is not meu_jogo]
                r = play_fixtures(outras, ratings, rng, style)
                self.parciais = list(r)
                self._detalhar(r)      # a central da rodada ja tem quem marcou e quando
                detalhada = self._minha_partida(meu_jogo, rng, style, tatica,
                                                substituicoes)
                r.append(Result(meu_jogo.home, meu_jogo.away,
                                detalhada.gols_casa, detalhada.gols_fora, n))
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
        self._somar_estatisticas(todos, detalhada, rng_est, comp_de, rodada)
        for nome, rs in por_liga.items():
            minha = detalhada if detalhada is not None and any(
                (x.home, x.away) == (detalhada.casa, detalhada.fora) for x in rs) else None
            self.selecoes.setdefault(nome, {})[n] = selecao_da_rodada(
                self.world, rs, rodada[nome], minha)
            clubes = {x.home for x in rs} | {x.away for x in rs}
            self._cartoes_da_data(nome, rs, minha, clubes)
        self._lesoes_da_data(todos, detalhada)

        self._gastar_energia(jogaram, tatica)
        self._encerrar_desfalques()
        self.rodada = n
        self.data += 1
        self._checar_emprego()
        return todos, detalhada

    def caderno(self, competicao: str):
        """O caderno de artilharia de uma competicao no ano, criado na primeira vez."""
        from fm.estatisticas import Estatisticas
        if competicao not in self.estatisticas_por_comp:
            self.estatisticas_por_comp[competicao] = Estatisticas(temporada=self.temporada)
        return self.estatisticas_por_comp[competicao]

    def _somar_estatisticas(self, resultados, detalhada, rng, comp_de,
                            rodada=None) -> None:
        """A partida do usuario entra pelos EVENTOS; as outras, por amostragem do placar.

        Sem a segunda metade nao existe artilharia de campeonato: os jogos dos outros
        clubes sao resolvidos pelo motor rapido, que devolve so o placar.
        """
        from fm.central import registrar as registrar_lances
        from fm.estatisticas import registrar_partida_detalhada, registrar_resultado

        if self.estatisticas is None:
            return
        rodada = rodada or {}

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
            se_e_minha = detalhada is not None and (r.home, r.away) == (
                detalhada.casa, detalhada.fora)
            if not se_e_minha:
                lances = self.lances_da_data.get((r.home, r.away))
                if lances is not None:
                    # os mesmos lances que a central da rodada mostrou
                    registrar_lances(cadernos(r), self.world, r, lances)
                else:
                    registrar_resultado(cadernos(r), self.world, r, rng)
        if detalhada is not None:
            minha = next((r for r in resultados
                          if (r.home, r.away) == (detalhada.casa, detalhada.fora)), None)
            alvo = cadernos(minha) if minha else [self.estatisticas]
            registrar_partida_detalhada(alvo, self.world, detalhada)

    def _minha_partida(self, jogo: Fixture, rng, style, tatica: Tatica,
                       substituicoes) -> Partida:
        from fm.tatica import confronto
        sou_casa = jogo.home == self.clube_id
        ma, md = (confronto(tatica, Tatica()) if sou_casa
                  else confronto(Tatica(), tatica))
        chave = f"{self.temporada}:{self.data}"
        from fm.tatica import papeis_em_campo
        papeis = papeis_em_campo(self.world.escalacao_fixa.get(self.clube_id)
                                 or self.escalacao_atual(), tatica.formacao)
        return simular_partida(
            self.world, jogo.home, jogo.away,
            [p.id for p in self.world.best_xi(jogo.home)],
            [p.id for p in self.world.best_xi(jogo.away)],
            rng, style, mult_casa=ma, mult_fora=md,
            substituicoes=self._no_banco(substituicoes, chave, sou_casa),
            papeis=papeis,
            cobradores={self.clube_id: self.cobradores()},
            penaltis=self._na_marca(chave),
            bancos={jogo.home: self.banco(jogo.home), jogo.away: self.banco(jogo.away)},
            max_trocas=MAX_TROCAS)

    def banco(self, clube: int) -> list[int]:
        """Os reservas relacionados: 12, fora do onze e disponiveis, com o goleiro
        reserva sempre entre eles -- sem ele, goleiro machucado virava meia no gol. E o
        banco da tela ao vivo e o de onde sai quem entra no lugar do machucado."""
        onze = {p.id for p in self.world.best_xi(clube)}
        livres = [p for p in sorted(self.world.squad(clube), key=lambda p: -p.overall)
                  if p.id not in onze and p.id not in self.world.indisponiveis]
        goleiro = next((p for p in livres if p.position == "GK"), None)
        resto = [p for p in livres if p is not goleiro]
        return ([goleiro.id] if goleiro else []) + [p.id for p in resto][:12 - bool(goleiro)]

    def cobradores(self) -> list[int]:
        return [self.funcoes[k] for k in ("penaltis", "penaltis2", "penaltis3")
                if k in self.funcoes]

    def _na_marca(self, chave: str):
        """Quem bate o penalti do meu time: o que a tela escolheu, gravado em `na_partida`
        para o replay escolher o mesmo. Sem escolha, vale a ordem de cobradores."""
        pedido = self._pedido_de_penalti
        gravado = (self.na_partida.get(chave) or {}).get("penaltis", [])
        if pedido is None and not gravado:
            return None

        usados: set[int] = set()

        def decidir(partida, minuto, clube):
            if pedido is None:
                if clube != self.clube_id:
                    return None
                # na ordem gravada: dois penaltis no mesmo minuto nao pegam o mesmo batedor
                i = next((i for i, (m, _) in enumerate(gravado)
                          if m == minuto and i not in usados), None)
                if i is None:
                    return None
                usados.add(i)
                return gravado[i][1]
            escolha = pedido(partida, minuto, clube)
            if clube != self.clube_id or escolha is None:
                return None
            escolha = int(escolha)
            reg = self.na_partida.setdefault(chave, {"trocas": [], "taticas": []})
            reg.setdefault("penaltis", []).append([minuto, escolha])
            return escolha
        return decidir

    def _no_banco(self, pedido, chave: str, sou_casa: bool):
        """O intermediario entre quem decide (terminal, tela ao vivo ou o save) e o motor.

        `pedido(partida, minuto)` pode devolver a lista antiga [(clube, sai, entra)] ou um
        dict {"trocas": [(sai, entra)], "tatica": Tatica | dict}. O que passar pelas regras
        -- so o proprio clube, no maximo MAX_TROCAS, quem jogou nao volta -- e gravado em
        `na_partida`, e e isso que o replay devolve. Sem pedido e sem registro, o motor
        joga sem banco, como sempre jogou.
        """
        from fm.eventos import Ajuste
        from fm.tatica import confronto

        gravado = self.na_partida.get(chave)
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
                    trocas = [(s, e) for cl, s, e in resposta if cl == self.clube_id]
                    nova = None
            feitas = sum(1 for e in partida.eventos
                         if e.tipo == "substituicao" and e.clube == self.clube_id)
            em_campo = partida.em_campo_casa if sou_casa else partida.em_campo_fora
            elenco = {p.id for p in self.world.squad(self.clube_id)}
            validas: list[tuple[int, int]] = []
            for sai, entra in trocas:
                if feitas + len(validas) >= MAX_TROCAS:
                    break
                ja_vai = {e for _, e in validas} | {s for s, _ in validas}
                # o suspenso tambem nao entra: a regra fica aqui, e nao so na tela, para
                # valer do terminal, do navegador e do replay do save
                if (sai in em_campo and entra in elenco and entra not in partida.entrada
                        and entra not in self.world.indisponiveis
                        and sai not in ja_vai and entra not in ja_vai):
                    validas.append((int(sai), int(entra)))
            ajuste = Ajuste(trocas=[(self.clube_id, s, e) for s, e in validas])
            t = None
            if nova is not None:
                t = nova if isinstance(nova, Tatica) else Tatica(**nova)
                t.validar()
                ma, md = (confronto(t, Tatica()) if sou_casa
                          else confronto(Tatica(), t))
                ajuste.mult_casa, ajuste.mult_fora = ma, md
            if pedido is not None and (validas or t is not None):
                reg = self.na_partida.setdefault(chave, {"trocas": [], "taticas": []})
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
        tabelas = self.tabelas_do_ano_anterior or self._tabelas_por_forca()
        etapa = proxima_etapa(self.world, andamento, rng, tabelas)
        if etapa is None or not etapa.fixtures:
            return None

        tatica = self.tatica_atual()
        self._preparar_desfalques([nome], tatica)
        t = andamento.torneio
        meus = [f for f in etapa.fixtures
                if self.clube_id in (f.home, f.away)]
        detalhada: Partida | None = None
        jogos = list(etapa.fixtures)
        resultados: list[Result] = []

        ratings = {cid: float(effective_rating(self.world.team_rating(cid),
                                               fatigue=self.world.fatigue_penalty(cid)))
                   for cid in {f.home for f in etapa.fixtures} | {f.away for f in etapa.fixtures}}
        # no mata-mata de ida e volta o usuario joga a ida em detalhe; a volta resolve
        # no motor rapido, senao uma data pediria duas partidas seguidas na tela
        meu = meus[0] if meus else None
        if meu is not None:
            jogos = [f for f in jogos if f is not meu]
        # os outros primeiro, como na liga: e o que a rodada ao vivo mostra
        outros = play_fixtures(jogos, ratings, rng, t.style, t.mentality)
        self.parciais = list(outros)
        self._detalhar(outros)
        if meu is not None:
            detalhada = self._minha_partida(meu, rng, t.style, tatica, substituicoes)
            resultados.append(Result(meu.home, meu.away, detalhada.gols_casa,
                                     detalhada.gols_fora, meu.matchday))
        resultados += outros
        registrar(self.world, andamento, resultados, rng, self.exportados)
        self._somar_estatisticas(resultados, detalhada, rng, nome)

        jogaram = {f.home for f in etapa.fixtures} | {f.away for f in etapa.fixtures}
        self._cartoes_da_data(nome, resultados, detalhada, jogaram)
        self._lesoes_da_data(resultados, detalhada)
        self._gastar_energia(jogaram, tatica)
        self._encerrar_desfalques()
        self._checar_emprego()
        return resultados, detalhada

    # ---------------------------------------------------------------- negocios

    def _novas_propostas(self) -> None:
        """Depois de cada data, algum clube pode oferecer por um jogador do usuario.
        Stream proprio: nada no resto do mundo muda por existir ou nao uma proposta."""
        from fm.negocios import gerar_propostas
        if self.acabou or self.demitido:
            return
        rng = self.streams.get("propostas", self.temporada, self.data)
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
        if tipo == "assumir":
            clube = int(acao["clube"])
            if clube not in self.convites:
                return {"erro": "esse clube nao esta mais chamando"}
            self._assumir(clube)
            self.acoes.append({**acao, "temporada": self.temporada, "data": self.data})
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
                                         f"proposta de R$ {r['valor']:,}.".replace(",", ".")}
                        self.acoes.append({**acao, "temporada": self.temporada,
                                           "data": self.data})
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
                             f"R$ {valor:,}.".replace(",", ".")}
        else:
            return {"erro": f"acao desconhecida {tipo!r}"}
        self.acoes.append({**acao, "temporada": self.temporada, "data": self.data})
        return resultado

    def _registrar_movimento(self, sentido: str, pid: int, outro: int | None, valor: int):
        p = self.world.players[pid]
        self.movimentos.append({
            "temporada": self.temporada, "data": self.data, "sentido": sentido,
            "jogador": pid, "nome": p.name, "posicao": p.position, "overall": p.overall,
            "clube": self.world.clubs[outro].name if outro in self.world.clubs else "sem clube",
            "valor": valor})

    def _tirar_do_onze(self, pid: int) -> None:
        """Quem saiu nao pode continuar escalado: a proxima escalacao volta a automatica."""
        d = self.decisoes.get(self._chave())
        if d and pid in d.escalacao:
            del self.decisoes[self._chave()]
        if pid in self.world.escalacao_fixa.get(self.clube_id, []):
            self.world.escalacao_fixa.pop(self.clube_id, None)
        self.observados = [x for x in self.observados if x != pid]
        self.funcoes = {k: v for k, v in self.funcoes.items() if v != pid}

    def _aplicar_acoes_do_save(self, acoes: list[dict]) -> None:
        """Replay: reaplica as acoes gravadas exatamente na data em que foram feitas."""
        for a in acoes:
            if a.get("temporada") == self.temporada and a.get("data") == self.data:
                limpa = {k: v for k, v in a.items() if k not in ("temporada", "data")}
                self.executar(limpa)

    # ---------------------------------------------------------------- o gancho

    def competicao_do_proximo(self) -> str | None:
        """A chave da competicao do proximo jogo do usuario: e nela que o gancho vale."""
        tipo, onde, _ = self.proximo_jogo()
        if tipo == "liga":
            return self.liga
        return onde or None

    def suspensos_do_proximo(self) -> set[int]:
        comp = self.competicao_do_proximo()
        return self.disciplina.suspensos(comp) if comp and self.disciplina else set()

    def _preparar_desfalques(self, competicoes: list[str], tatica: Tatica) -> None:
        """Tira os suspensos de campo antes da data: dos adversarios pelo best_xi, do
        usuario trocando cada um pelo melhor reserva do mesmo setor, NA MESMA VAGA."""
        suspensos: set[int] = set()
        for comp in competicoes:
            suspensos |= self.disciplina.suspensos(comp)
        # o lesionado fica fora em qualquer competicao; a troca na escalacao e a mesma
        suspensos |= self.medico.fora(self.hoje())
        self.world.indisponiveis = suspensos
        self._onze_pretendido = self.escalacao_atual()
        self.world.escalacao_fixa[self.clube_id] = self._sem_suspensos(
            self._onze_pretendido, tatica, suspensos)
        self.world.formacao_fixa[self.clube_id] = tatica.vagas

    def _sem_suspensos(self, onze: list[int], tatica: Tatica, suspensos: set[int]) -> list[int]:
        from fm.tatica import VAGAS
        if not suspensos & set(onze):
            return list(onze)
        vagas = VAGAS.get(tatica.formacao, [])
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

    def _encerrar_desfalques(self) -> None:
        """Depois da data: ninguem mais esta indisponivel, e o onze volta a ser o escolhido."""
        self.world.indisponiveis = set()
        if self._onze_pretendido:
            self.world.escalacao_fixa[self.clube_id] = list(self._onze_pretendido)

    def _cartoes_da_data(self, comp: str, resultados, detalhada, clubes: set[int]) -> None:
        """Cumpre os ganchos de quem jogou e soma os cartoes novos.

        A ordem importa: primeiro cumpre (quem estava suspenso ficou fora DESTA data),
        depois registra (o vermelho de hoje suspende o PROXIMO jogo). Os cartoes dos jogos
        do motor rapido saem de um stream proprio: sorteia-los no stream da partida
        mudaria os placares de todos os saves.
        """
        from fm.central import cartoes as cartoes_dos_lances
        from fm.disciplina import cartoes_da_partida

        self.disciplina.cumprir(comp, clubes, self.world)
        for r in resultados:
            if detalhada is not None and (r.home, r.away) == (detalhada.casa, detalhada.fora):
                # os da partida detalhada ja entraram nos cadernos pelos eventos
                self.disciplina.registrar(comp, cartoes_da_partida(detalhada))
                continue
            # os dos outros jogos vem dos lances da central, que ja os somou nos cadernos
            lances = self.lances_da_data.get((r.home, r.away), [])
            self.disciplina.registrar(comp, cartoes_dos_lances(lances))

    def hoje(self) -> date:
        """O dia da proxima data da agenda (fm.calendario). E o "hoje" do lobby."""
        return dia_da_data(self.temporada, self.data)

    def _lesoes_da_data(self, resultados, detalhada) -> None:
        """Registra os machucados de hoje (gravidade num stream proprio) e da alta a quem
        ja pode jogar na data seguinte. Chamada ANTES de `self.data` andar."""
        from fm.central import lesionados
        hoje = self.hoje()
        voltaram = self.medico.dar_alta(dia_da_data(self.temporada, self.data + 1))
        novos: list[int] = []
        for r in resultados:
            if detalhada is not None and (r.home, r.away) == (detalhada.casa, detalhada.fora):
                novos += detalhada.lesionados
            else:
                novos += lesionados(self.lances_da_data.get((r.home, r.away), []))
        novas = self.medico.registrar(novos, self.streams.get("gravidade", self.temporada,
                                                              self.data), hoje)
        meus = {p.id for p in self.world.squad(self.clube_id)}
        self.boletim_medico = {
            "lesoes": [(pid, les.tipo, les.dias) for pid, les in novas.items() if pid in meus],
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

        cfgs = {n: load_league(n) for n in self.ligas}
        tabelas = {n: self.tabela(n) for n in self.ligas}
        campeoes = {n: self.world.clubs[t[0].club_id].name for n, t in tabelas.items()}
        minha_liga = self.liga
        minha_posicao = self.posicao()
        meus_numeros = self.numeros_do_ano()

        # A ordem e a regra. As contas fecham na divisao em que o ano foi jogado, e so
        # depois o clube troca de divisao; o mercado vem depois do envelhecimento para
        # negociar overalls deste ano, e a base entra por ultimo, tapando o que sobrou.
        # As tabelas e os campeoes de copa deste ano decidem quem disputa o que no ano que
        # vem -- e a cascata de vagas que ja estava escrita nos arquivos de torneio, agora
        # alimentada pela temporada de verdade em vez da forca desenhada.
        titulos = self._titulos_de_copa()
        premios_do_ano, dados = self._premios_e_desempenho(tabelas, cfgs)
        premios_de_copa = self._premiar_copas()
        balancos = fechar_o_ano(self.world, tabelas, cfgs, extras=premios_de_copa,
                                jogos_extras=self._jogos_de_copa(),
                                valores=self.valor_de_elenco)
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
        antes = {p.id: (p.name, p.overall) for p in self.world.squad(self.clube_id)}
        envelhecimento = envelhecer(self.world, rng, self.temporada)
        from fm.negocios import livres_que_se_aposentam, vencer_contratos
        for prop in self.propostas:
            if prop.status == "pendente":
                prop.status = "expirada"
        # contrato vencido acaba ANTES da janela: quem sai de graca ja pode ser disputado.
        # Stream proprio, para nao mexer no sorteio da janela e da base.
        contratos = vencer_contratos(self.world, self.temporada + 1, self.clube_id,
                                     self.streams.get("contratos", self.temporada))
        aposentados_livres = livres_que_se_aposentam(self.world, self.temporada + 1)
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
        # a régua do ano: a diretoria cobra a meta que ela mesma deu em marco
        clima_final = {
            "torcida": round(self.aprovacao.torcida, 1),
            "diretoria": round(self.aprovacao.diretoria, 1),
            "meta": self.aprovacao.meta.texto if self.aprovacao.meta else "",
            "bateu_a_meta": bool(self.aprovacao.meta
                                 and minha_posicao <= self.aprovacao.meta.posicao),
        }
        resumo = {
            "temporada": self.temporada,
            "campeoes": campeoes,
            "minha_liga": minha_liga,
            "minha_posicao": minha_posicao,
            "meus_numeros": meus_numeros,
            "clube": self.world.clubs[self.clube_id].name,
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
            "destaques_do_clube": destaques,
            "contratos_encerrados": [x for x in contratos if x["do_usuario"]],
            "livres_aposentados": len(aposentados_livres),
            "movimentos": list(self.movimentos),
            # os artilheiros de cada competicao do ano ficam guardados: e o que a tela de
            # artilharia mostra das temporadas passadas
            "artilharia": self.artilharia_do_ano(),
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
        from fm.diretoria import decidir_demissao
        motivo = decidir_demissao(
            self.aprovacao, rodada=self.rodada, fim_da_temporada=True,
            posicao=minha_posicao, clubes=len(tabelas[minha_liga]),
            rebaixado=bool(minha and not minha.subiu))
        if motivo and not self.aprovacao.demitido:
            self.aprovacao.demitido = True
            self.aprovacao.motivo = motivo
        resumo["demitido"] = self.aprovacao.demitido
        resumo["motivo_da_demissao"] = self.aprovacao.motivo
        resumo["premios"] = premios_do_ano
        self._mercado_de_tecnicos(dados)
        resumo["convites"] = list(self.convites)

        self.tabelas_do_ano_anterior = self._tabelas_para_classificacao(tabelas, titulos)
        self.exportados = {}
        self._novo_calendario()
        return resumo

    def salvar(self, nome: str) -> Path:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        destino = SAVES_DIR / f"{nome}.json"
        destino.write_text(json.dumps({
            "seed": self.seed, "ligas": self.ligas, "clube_id": self.clube_id,
            "clube_inicial": self.clube_inicial,
            "temporada_inicial": self.temporada - len(self.historico),
            # `data`, nao `rodada`: a temporada anda por datas, e uma delas pode ser
            # copa. Guardar a rodada da liga perderia os jogos de copa no replay.
            "temporada": self.temporada, "data": self.data,
            "decisoes": {k: asdict(v) for k, v in self.decisoes.items()},
            "na_partida": self.na_partida,
            "treinador": self.treinador,
            "funcoes": self.funcoes,
            "observados": self.observados,
            "acoes": self.acoes,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        return destino

    @classmethod
    def carregar(cls, nome: str) -> Carreira:
        origem = SAVES_DIR / f"{nome}.json"
        if not origem.exists():
            raise FileNotFoundError(f"save {nome!r} nao existe. Ha: {saves_disponiveis()}")
        d = _atualizar_save(json.loads(origem.read_text(encoding="utf-8")))
        cfgs = [load_league(n) for n in d["ligas"]]
        world, streams = build_world(cfgs, seed=d["seed"])
        if d["clube_id"] not in world.clubs:
            # os packs foram refeitos depois do save: o mesmo seed gera outro mundo
            raise ValueError("o save e de uma versao antiga do jogo e o clube dele nao "
                             "existe mais neste mundo -- comece uma carreira nova")
        # o replay parte do clube em que a carreira comecou; as trocas vem nas acoes
        c = cls(seed=d["seed"], ligas=list(d["ligas"]),
                clube_id=d.get("clube_inicial") or d["clube_id"],
                temporada=d["temporada_inicial"])
        c.decisoes = {k: Decisao(**v) for k, v in d["decisoes"].items()}
        c.na_partida = d.get("na_partida", {})
        c.treinador = d.get("treinador", c.treinador)
        c.clube_inicial = c.clube_id
        c.funcoes = d.get("funcoes", {})
        c.observados = d.get("observados", [])
        c._montar(world, streams)
        acoes = d.get("acoes", [])
        # REPLAY: as temporadas sao refeitas com as mesmas decisoes. Se isto divergir, o
        # determinismo do motor quebrou -- e o save seria a primeira vitima. Os negocios
        # entram no mesmo ponto em que foram feitos: antes da data seguinte.
        while c.temporada < d["temporada"]:
            while not c.acabou:
                c._aplicar_acoes_do_save(acoes)
                c.avancar()
            c._aplicar_acoes_do_save(acoes)
            c.virar_o_ano()
        while c.data < d.get("data", d.get("rodada", 0)) and not c.acabou:
            c._aplicar_acoes_do_save(acoes)
            c.avancar()
        c._aplicar_acoes_do_save(acoes)
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
