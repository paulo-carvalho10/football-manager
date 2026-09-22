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
    seed: int
    liga: str
    clube_id: int
    temporada: int
    rodada: int = 0
    decisoes: dict[int, Decisao] = field(default_factory=dict)
    world: World | None = None
    calendario: list[Fixture] = field(default_factory=list)
    resultados: list[Result] = field(default_factory=list)
    streams: Streams | None = None

    @classmethod
    def nova(cls, liga: str, clube: str, seed: int = 2027) -> Carreira:
        cfg = load_league(liga)
        world, streams = build_world([cfg], seed=seed)
        alvo = next((c for c in world.clubs.values()
                     if c.name.lower() == clube.lower()), None)
        if alvo is None:
            nomes = sorted(c.name for c in world.clubs.values())
            raise ValueError(f"clube {clube!r} nao esta em {liga}. Ha: {nomes}")
        c = cls(seed=seed, liga=liga, clube_id=alvo.id, temporada=world.season_year)
        c._montar(world, streams)
        return c

    def _montar(self, world: World, streams: Streams) -> None:
        self.world = world
        self.streams = streams
        cfg = load_league(self.liga)
        self.calendario = round_robin(world.leagues[cfg["id"]].club_ids, legs=2)

    @property
    def clube(self):
        return self.world.clubs[self.clube_id]

    @property
    def liga_id(self) -> str:
        return load_league(self.liga)["id"]

    @property
    def total_de_rodadas(self) -> int:
        return max((f.matchday for f in self.calendario), default=0)

    @property
    def acabou(self) -> bool:
        return self.rodada >= self.total_de_rodadas

    def tatica_atual(self) -> Tatica:
        d = self.decisoes.get(self.rodada + 1)
        return Tatica(**d.tatica) if d else Tatica()

    def escalacao_atual(self) -> list[int]:
        d = self.decisoes.get(self.rodada + 1)
        if d and d.escalacao:
            return list(d.escalacao)
        return [p.id for p in self.world.best_xi(self.clube_id,
                                                 self.tatica_atual().vagas)]

    def proxima_partida(self) -> Fixture | None:
        return next((f for f in self.calendario
                     if f.matchday == self.rodada + 1
                     and self.clube_id in (f.home, f.away)), None)

    def tabela(self) -> list[Row]:
        return build_table(self.world.leagues[self.liga_id].club_ids, self.resultados)

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
        self.decisoes[self.rodada + 1] = Decisao(list(jogadores), asdict(tatica))

    def avancar(self, substituicoes=None) -> tuple[list[Result], Partida | None]:
        """Joga UMA rodada e para. E o coracao do jogo: rodada, volta ao lobby, rodada.

        A SUA partida passa pelo motor detalhado (minuto a minuto, com substituicao); o
        resto da rodada passa pelo rapido. Os dois foram calibrados um contra o outro, e ha
        teste cobrando isso -- se a sua partida tivesse media de gols diferente do resto do
        mundo, a tabela ficaria torta e voce sentiria sem saber por que.
        """
        if self.acabou:
            raise RuntimeError("a temporada acabou")
        n = self.rodada + 1
        cfg = load_league(self.liga)
        partidas = [f for f in self.calendario if f.matchday == n]

        tatica = self.tatica_atual()
        self.world.escalacao_fixa[self.clube_id] = self.escalacao_atual()
        self.world.formacao_fixa[self.clube_id] = tatica.vagas

        ratings = {
            cid: float(effective_rating(self.world.team_rating(cid),
                                        fatigue=self.world.fatigue_penalty(cid)))
            for cid in self.world.leagues[self.liga_id].club_ids
        }
        rng = self.streams.get("carreira", self.temporada, n)
        style = style_of(cfg)

        meu_jogo = next((f for f in partidas if self.clube_id in (f.home, f.away)), None)
        detalhada: Partida | None = None
        if meu_jogo is not None:
            ma, md = tatica.multiplicadores()
            sou_casa = meu_jogo.home == self.clube_id
            detalhada = simular_partida(
                self.world, meu_jogo.home, meu_jogo.away,
                [p.id for p in self.world.best_xi(meu_jogo.home)],
                [p.id for p in self.world.best_xi(meu_jogo.away)],
                rng, style,
                mult_casa=ma if sou_casa else md,
                mult_fora=md if sou_casa else ma,
                substituicoes=substituicoes)

        outras = [f for f in partidas if f is not meu_jogo]
        resultados = play_fixtures(outras, ratings, rng, style)
        if detalhada is not None:
            resultados.append(Result(meu_jogo.home, meu_jogo.away,
                                     detalhada.gols_casa, detalhada.gols_fora, n))
        self.resultados.extend(resultados)
        self._gastar_energia(partidas, tatica)
        self.rodada = n
        return resultados, detalhada

    def _gastar_energia(self, partidas: list[Fixture], tatica: Tatica) -> None:
        """Energia entre rodadas.

        TODO MUNDO recupera; quem jogou paga o custo por cima. Antes so o reserva
        recuperava, o que funcionava enquanto a IA rodava o elenco -- mas com escalacao
        FIXA os mesmos onze jogavam sempre e desabavam ate o piso em seis rodadas.
        Jogador de verdade descansa entre as partidas.
        """
        jogaram = {f.home for f in partidas} | {f.away for f in partidas}
        for club_id in self.world.leagues[self.liga_id].club_ids:
            onze = ({p.id for p in self.world.best_xi(club_id)}
                    if club_id in jogaram else set())
            # marcacao forte cansa mais: o preco aparece na rodada seguinte, nao nesta
            custo = CONDITION_COST * (tatica.custo_de_energia
                                      if club_id == self.clube_id else 1.0)
            for p in self.world.squad(club_id):
                recupera = TAXA_DE_RECUPERACAO * (100 - p.condition)
                delta = recupera - (custo if p.id in onze else 0.0)
                p.condition = int(np.clip(p.condition + delta, 25, 100))

    def salvar(self, nome: str) -> Path:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        destino = SAVES_DIR / f"{nome}.json"
        destino.write_text(json.dumps({
            "seed": self.seed, "liga": self.liga, "clube_id": self.clube_id,
            "temporada": self.temporada, "rodada": self.rodada,
            "decisoes": {str(k): asdict(v) for k, v in self.decisoes.items()},
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        return destino

    @classmethod
    def carregar(cls, nome: str) -> Carreira:
        origem = SAVES_DIR / f"{nome}.json"
        if not origem.exists():
            ha = sorted(p.stem for p in SAVES_DIR.glob("*.json")) \
                if SAVES_DIR.exists() else []
            raise FileNotFoundError(f"save {nome!r} nao existe. Ha: {ha}")
        d = json.loads(origem.read_text(encoding="utf-8"))
        cfg = load_league(d["liga"])
        world, streams = build_world([cfg], seed=d["seed"])
        c = cls(seed=d["seed"], liga=d["liga"], clube_id=d["clube_id"],
                temporada=d["temporada"])
        c.decisoes = {int(k): Decisao(**v) for k, v in d["decisoes"].items()}
        c._montar(world, streams)
        # REPLAY: as rodadas sao refeitas com as mesmas decisoes. Se isto divergir, o
        # determinismo do motor quebrou -- e o save seria a primeira vitima.
        for _ in range(d["rodada"]):
            c.avancar()
        return c


def saves_disponiveis() -> list[str]:
    return sorted(p.stem for p in SAVES_DIR.glob("*.json")) if SAVES_DIR.exists() else []
