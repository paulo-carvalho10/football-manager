"""Modelo de dados do mundo.

Entidades sao dataclasses legiveis. A simulacao em massa NAO itera sobre elas: ela consome
matrizes numpy montadas por rodada (ver fm/season.py). Ler objeto Python 40 mil vezes por
temporada e' o que mata um motor desses em Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field

POSITIONS = ("GK", "DF", "MF", "FW")

# Posicao detalhada (como vem das fontes) -> grupo usado pela formacao. O detalhe e
# guardado porque vale para tatica e para o premio de valor por posicao; o motor de
# escalacao so precisa dos quatro grupos.
POSICAO_DETALHE = {
    "GK": "GK",
    "CB": "DF", "FB": "DF", "DF": "DF",
    "DM": "MF", "MF": "MF", "AM": "MF",
    "WG": "FW", "FW": "FW",
}


def grupo_posicao(pos: str | None) -> str | None:
    return POSICAO_DETALHE.get(pos) if pos else None
MAX_FATIGUE_PENALTY = 8.0   # espelha fm.match.MAX_FATIGUE_PENALTY
FORMATION_442 = {"GK": 1, "DF": 4, "MF": 4, "FW": 2}
FORMATION_433 = {"GK": 1, "DF": 4, "MF": 3, "FW": 3}

# Padrao 4-3-3, nao 4-4-2: os elencos reais importados tem cerca de 9 atacantes/pontas e 9
# meias por clube. Com duas vagas de ataque, o jogador mais caro da liga ficava no banco --
# era a FORMACAO errada, nao o calculo de overall.
FORMATION_DEFAULT = FORMATION_433


@dataclass(slots=True)
class Player:
    id: int
    name: str
    nationality: str
    birth_year: int
    position: str            # grupo: GK/DF/MF/FW
    position_detail: str     # como veio da fonte: GK/CB/FB/DM/MF/AM/WG/FW
    foot: str
    height_cm: int
    # atributos 0-100
    finishing: int
    passing: int
    dribbling: int
    marking: int
    pace: int
    strength: int
    stamina: int
    technique: int
    positioning: int
    vision: int
    reflexes: int
    aerial: int
    overall: int
    potential: int
    # estado
    morale: int = 70
    form: int = 70
    condition: int = 100      # 100 = inteiro; cai com minutos e pouco descanso
    # contrato
    club_id: int | None = None
    wage: int = 0
    contract_until: int = 0
    market_value: int = 0

    def age(self, season_year: int) -> int:
        return season_year - self.birth_year

    @property
    def fatigue_points(self) -> float:
        """Desgaste em pontos de overall. condition 100 -> 0; condition 40 -> 8."""
        return max(0.0, (100.0 - self.condition) / 60.0 * MAX_FATIGUE_PENALTY)

    @property
    def effective_overall(self) -> float:
        """Overall descontado o desgaste. E' por isso que elenco profundo vale a pena."""
        return self.overall - self.fatigue_points


@dataclass(slots=True)
class Club:
    id: int
    name: str
    country: str
    league_id: str
    reputation: int             # 0-100: alimenta receita, propostas e mercado
    designed_strength: float    # forca alvo do perfil da liga (referencia de autoria)
    color_primary: str          # cor-TEMA do clube, para a interface
    color_secondary: str
    # A camisa e outra coisa. O Corinthians tem tema preto e camisa branca; o Sao Paulo,
    # tema vermelho e camisa branca com faixas. Usar a cor-tema como cor de pano vestia
    # metade da Serie A com o uniforme errado, entao a camisa tem os campos dela. Vazio
    # = a camisa e o tema, que e o caso da maioria.
    kit_body: str = ""
    kit_detail: str = ""
    kit_pattern: str = "liso"   # ver fm/camisa.PADROES
    player_ids: list[int] = field(default_factory=list)
    balance: int = 0


@dataclass(slots=True)
class League:
    id: str
    name: str
    country: str
    tier: int
    codigo: str | None = None   # codigo da competicao na fonte (ex.: BRA1). E por ele que
                                # os torneios continentais encontram a liga.
    club_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class World:
    season_year: int
    players: dict[int, Player] = field(default_factory=dict)
    clubs: dict[int, Club] = field(default_factory=dict)
    leagues: dict[str, League] = field(default_factory=dict)
    # Escalacao escolhida pelo usuario, por clube. Quando existe, ela manda: a IA nao
    # reescolhe o onze do time dele a cada rodada.
    escalacao_fixa: dict[int, list[int]] = field(default_factory=dict)
    formacao_fixa: dict[int, dict[str, int]] = field(default_factory=dict)

    def squad(self, club_id: int) -> list[Player]:
        return [self.players[p] for p in self.clubs[club_id].player_ids]

    def best_xi(self, club_id: int, formation: dict[str, int] | None = None) -> list[Player]:
        """Onze titular: melhor jogador disponivel respeitando as vagas da formacao.

        Se o usuario escalou o time dele, a escolha dele manda -- inclusive se ele
        escalou alguem cansado. E o jogo dele.
        """
        escolhidos = self.escalacao_fixa.get(club_id)
        if escolhidos:
            return [self.players[pid] for pid in escolhidos if pid in self.players]
        formation = formation or self.formacao_fixa.get(club_id) or FORMATION_DEFAULT
        # ordena pelo overall EFETIVO: jogador desgastado perde a vaga para o reserva
        # inteiro, e a rotacao passa a ser decisao de verdade.
        pool = sorted(self.squad(club_id), key=lambda p: -p.effective_overall)
        need = dict(formation)
        xi: list[Player] = []
        for p in pool:
            if need.get(p.position, 0) > 0:
                need[p.position] -= 1
                xi.append(p)
        # se faltou alguem de alguma posicao, completa com o melhor sobrando (jogador improvisado)
        if len(xi) < sum(formation.values()):
            rest = [p for p in pool if p not in xi]
            xi.extend(rest[: sum(formation.values()) - len(xi)])
        return xi

    def team_rating(self, club_id: int) -> float:
        """Overall base do onze. Ponto de entrada do motor de partidas."""
        xi = self.best_xi(club_id)
        return sum(p.overall for p in xi) / len(xi)

    def fatigue_penalty(self, club_id: int) -> float:
        """Desgaste do onze escalado, em pontos de overall -- auditavel na tela.

        Nota importante: o motor usa a DIFERENCA de forca, entao desgaste igual nos dois
        lados se cancela exatamente. Ele so mexe no jogo quando e' assimetrico -- calendario
        apertado, jogo no meio de semana, elenco curto. E' o comportamento desejado.
        """
        return sum(p.fatigue_points for p in self.best_xi(club_id)) / 11.0
