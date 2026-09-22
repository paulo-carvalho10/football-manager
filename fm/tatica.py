"""Taticas: formacao, marcacao e estilo de jogo.

Cada uma mexe nos lambdas do motor, entao nenhuma pode entrar sem numero. Os efeitos aqui
sao DELIBERADAMENTE modestos: tatica tem de ser escolha com troca (ganha de um lado, perde
do outro), nunca botao de vencer. Quem decide o jogo continua sendo o elenco.
"""

from __future__ import annotations

from dataclasses import dataclass

FORMACOES: dict[str, dict[str, int]] = {
    "4-4-2": {"GK": 1, "DF": 4, "MF": 4, "FW": 2},
    "4-3-3": {"GK": 1, "DF": 4, "MF": 3, "FW": 3},
    "4-5-1": {"GK": 1, "DF": 4, "MF": 5, "FW": 1},
    "3-5-2": {"GK": 1, "DF": 3, "MF": 5, "FW": 2},
    "5-3-2": {"GK": 1, "DF": 5, "MF": 3, "FW": 2},
    "3-4-3": {"GK": 1, "DF": 3, "MF": 4, "FW": 3},
}

# (ataque, defesa): multiplicam o gol esperado do proprio time e o do adversario.
# Retrancado cria menos e concede menos; ofensivo o contrario. A soma dos dois efeitos e
# proxima de zero de proposito -- estilo troca risco por risco, nao da vantagem de graca.
ESTILOS: dict[str, tuple[float, float]] = {
    "retrancado":   (0.84, 0.86),
    "defensivo":    (0.92, 0.93),
    "equilibrado":  (1.00, 1.00),
    "ofensivo":     (1.09, 1.08),
    "all-out":      (1.18, 1.20),
}

# (efeito no gol do adversario, custo de energia por jogo). Marcacao forte sufoca o rival
# e cansa mais -- o preco aparece na rodada seguinte, nao nesta.
MARCACOES: dict[str, tuple[float, float]] = {
    "leve":    (1.07, 0.85),
    "normal":  (1.00, 1.00),
    "forte":   (0.93, 1.22),
}

# Formacao: (ataque, defesa). Mais atacantes cria mais e concede mais.
EFEITO_FORMACAO: dict[str, tuple[float, float]] = {
    "4-4-2": (1.00, 1.00),
    "4-3-3": (1.05, 1.04),
    "4-5-1": (0.93, 0.94),
    "3-5-2": (1.03, 1.06),
    "5-3-2": (0.92, 0.90),
    "3-4-3": (1.09, 1.10),
}


@dataclass(slots=True)
class Tatica:
    formacao: str = "4-3-3"
    marcacao: str = "normal"
    estilo: str = "equilibrado"

    def validar(self) -> None:
        if self.formacao not in FORMACOES:
            raise ValueError(f"formacao {self.formacao!r}; use {sorted(FORMACOES)}")
        if self.marcacao not in MARCACOES:
            raise ValueError(f"marcacao {self.marcacao!r}; use {sorted(MARCACOES)}")
        if self.estilo not in ESTILOS:
            raise ValueError(f"estilo {self.estilo!r}; use {sorted(ESTILOS)}")

    @property
    def vagas(self) -> dict[str, int]:
        return FORMACOES[self.formacao]

    def multiplicadores(self) -> tuple[float, float]:
        """(quanto multiplica os proprios gols, quanto multiplica os gols do adversario)."""
        ea, ed = ESTILOS[self.estilo]
        fa, fd = EFEITO_FORMACAO[self.formacao]
        mrc = MARCACOES[self.marcacao][0]
        return ea * fa, ed * fd * mrc

    @property
    def custo_de_energia(self) -> float:
        return MARCACOES[self.marcacao][1]

    def como_texto(self) -> str:
        return f"{self.formacao}, marcacao {self.marcacao}, {self.estilo}"
