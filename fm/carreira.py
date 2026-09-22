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
        return self.rodada >= self.total_de_rodadas

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
        """Joga UMA rodada em TODAS as divisoes e para.

        A piramide inteira anda junta: sem isso as divisoes ficariam em temporadas
        diferentes e o acesso no fim do ano nao faria sentido.
        """
        if self.acabou:
            raise RuntimeError("a temporada acabou; chame virar_o_ano()")
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
                from fm.tatica import Tatica, confronto
                sou_casa = meu_jogo.home == self.clube_id
                ma, md = (confronto(tatica, Tatica()) if sou_casa
                          else confronto(Tatica(), tatica))
                detalhada = simular_partida(
                    self.world, meu_jogo.home, meu_jogo.away,
                    [p.id for p in self.world.best_xi(meu_jogo.home)],
                    [p.id for p in self.world.best_xi(meu_jogo.away)],
                    rng, style, mult_casa=ma, mult_fora=md,
                    substituicoes=substituicoes)
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
        return todos, detalhada

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
        balancos = fechar_o_ano(self.world, tabelas, cfgs)
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
        self._novo_calendario()
        return resumo

    def salvar(self, nome: str) -> Path:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        destino = SAVES_DIR / f"{nome}.json"
        destino.write_text(json.dumps({
            "seed": self.seed, "ligas": self.ligas, "clube_id": self.clube_id,
            "temporada_inicial": self.temporada - len(self.historico),
            "temporada": self.temporada, "rodada": self.rodada,
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
        for _ in range(d["rodada"]):
            c.avancar()
        return c


def saves_disponiveis() -> list[str]:
    return sorted(p.stem for p in SAVES_DIR.glob("*.json")) if SAVES_DIR.exists() else []
