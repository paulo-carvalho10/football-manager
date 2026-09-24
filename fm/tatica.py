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
    # mesmas vagas do 4-5-1; a diferenca e onde os meias jogam (dois volantes e tres
    # meias ofensivos), por isso o efeito fica entre o 4-5-1 e o 4-3-3
    "4-2-3-1": {"GK": 1, "DF": 4, "MF": 5, "FW": 1},
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

# --- CONFRONTO DE FORMACOES ---
# Nao e uma matriz de 15 numeros digitados a mao: o efeito e DERIVADO de dois fatos
# estruturais do par, entao qualquer formacao nova entra na conta sozinha.
#
#   vantagem de meio  = meias meus - meias dele    -> quem controla o jogo
#   pressao           = meus atacantes - zagueiros dele -> quem cria contra quantos
#
# Assim o 4-5-1 domina a posse do 4-3-3 mas nao finaliza; o 5-3-2 embuchai o 3-4-3; e
# 4-3-3 contra 5-3-2 vira jogo travado dos dois lados. Os pesos foram ajustados para o
# efeito ficar na MESMA ordem de grandeza da marcacao (cerca de 2 pontos de vitoria) --
# tatica tem de ser escolha, nao gabarito.
PESO_PONTA = 0.075
PESO_MEIO_CHEIO = 0.055
PESO_ABSORVE = 0.045
FORMACAO_PADRAO = "4-3-3"   # ancora da calibracao: o espelho dela da exatamente 1.0

# Formacao: (ataque, defesa), RELATIVO A FORMACAO PADRAO.
# O 4-3-3 vale exatamente (1.00, 1.00) por definicao: ele e a ancora da calibracao. Antes
# ele valia (1.05, 1.04) e, como o padrao tambem vale para quem nao escolheu tatica, TODO
# jogo saia com 9% mais gols que o motor calibrado -- em silencio.
EFEITO_FORMACAO: dict[str, tuple[float, float]] = {
    "4-4-2": (0.95, 0.96),
    "4-3-3": (1.00, 1.00),
    "4-5-1": (0.89, 0.90),
    "3-5-2": (0.98, 1.02),
    "5-3-2": (0.88, 0.87),
    "3-4-3": (1.04, 1.06),
    "4-2-3-1": (0.95, 0.95),
}


# --- AS VAGAS DO CAMPO ---
# Cada formacao e uma lista ordenada de vagas; a escalacao e uma lista de onze ids na
# MESMA ordem. Assim "quem joga de 9" e uma escolha do usuario, e nao um detalhe do desenho.
#
# (rotulo, setor, papel, x, y). O setor e o grupo de posicao que a vaga pede; o papel e o
# position_detail que o motor de eventos usa para decidir quem finaliza, da o passe e comete
# falta -- quem ocupa a vaga de centroavante chuta como centroavante. x e y sao a posicao no
# desenho, em % do campo, com o ataque em cima.
_LINHA_4 = [("LE", "DF", "FB", 12, 70), ("ZAG", "DF", "CB", 37, 74),
            ("ZAG", "DF", "CB", 63, 74), ("LD", "DF", "FB", 88, 70)]
_LINHA_3 = [("ZAG", "DF", "CB", 25, 73), ("ZAG", "DF", "CB", 50, 75),
            ("ZAG", "DF", "CB", 75, 73)]
_LINHA_5 = [("LE", "DF", "FB", 8, 64), ("ZAG", "DF", "CB", 29, 73),
            ("ZAG", "DF", "CB", 50, 75), ("ZAG", "DF", "CB", 71, 73),
            ("LD", "DF", "FB", 92, 64)]
_MEIO_3 = [("MC", "MF", "MF", 25, 49), ("VOL", "MF", "DM", 50, 56), ("MC", "MF", "MF", 75, 49)]
_MEIO_4 = [("ME", "MF", "WG", 12, 46), ("VOL", "MF", "DM", 37, 53),
           ("MC", "MF", "MF", 63, 53), ("MD", "MF", "WG", 88, 46)]
_MEIO_5 = [("ME", "MF", "WG", 10, 44), ("MC", "MF", "MF", 30, 50), ("VOL", "MF", "DM", 50, 57),
           ("MC", "MF", "AM", 70, 50), ("MD", "MF", "WG", 90, 44)]
_ATAQUE_3 = [("PE", "FW", "WG", 16, 24), ("CA", "FW", "FW", 50, 17), ("PD", "FW", "WG", 84, 24)]
_ATAQUE_2 = [("CA", "FW", "FW", 36, 20), ("CA", "FW", "FW", 64, 20)]
_ATAQUE_1 = [("CA", "FW", "FW", 50, 17)]
_GOL = [("GOL", "GK", "GK", 50, 89)]

VAGAS: dict[str, list[tuple[str, str, str, int, int]]] = {
    "4-3-3": _GOL + _LINHA_4 + _MEIO_3 + _ATAQUE_3,
    "4-4-2": _GOL + _LINHA_4 + _MEIO_4 + _ATAQUE_2,
    "4-5-1": _GOL + _LINHA_4 + _MEIO_5 + _ATAQUE_1,
    "3-5-2": _GOL + _LINHA_3 + _MEIO_5 + _ATAQUE_2,
    "5-3-2": _GOL + _LINHA_5 + _MEIO_3 + _ATAQUE_2,
    "3-4-3": _GOL + _LINHA_3 + _MEIO_4 + _ATAQUE_3,
    "4-2-3-1": _GOL + _LINHA_4 + [("VOL", "MF", "DM", 33, 59), ("VOL", "MF", "DM", 67, 59),
                                  ("ME", "MF", "WG", 15, 36), ("MEI", "MF", "AM", 50, 38),
                                  ("MD", "MF", "WG", 85, 36)] + _ATAQUE_1,
}


def arrumar_no_campo(jogadores: list, formacao: str) -> list:
    """Poe onze jogadores nas vagas da formacao, do jeito que um treinador poria.

    Custo de cada par (jogador, vaga): fora do setor pesa muito, papel diferente pesa um
    pouco, e o pe trocado na ponta pesa menos ainda -- o canhoto vai para a esquerda.
    Guloso sobre os pares ordenados por custo; com onze jogadores basta.
    """
    vagas = VAGAS[formacao]
    if len(jogadores) != len(vagas):
        return list(jogadores)
    pares = []
    for i, p in enumerate(jogadores):
        for j, (_, setor, papel, x, _) in enumerate(vagas):
            custo = (0 if p.position == setor else 10) + (0 if p.position_detail == papel else 1)
            if x < 40 and p.foot != "E" or x > 60 and p.foot == "E":
                custo += 0.3
            pares.append((custo, -p.overall, i, j))
    pares.sort()
    lugar: dict[int, int] = {}
    usados: set[int] = set()
    for _, _, i, j in pares:
        if i not in lugar and j not in usados:
            lugar[i] = j
            usados.add(j)
    ordem: list = [None] * len(vagas)
    for i, j in lugar.items():
        ordem[j] = jogadores[i]
    return ordem


def papeis_em_campo(ids: list[int], formacao: str) -> dict[int, str]:
    """{jogador: papel da vaga que ele ocupa}. Vazio se a lista nao casa com a formacao."""
    vagas = VAGAS.get(formacao, [])
    if len(ids) != len(vagas):
        return {}
    return {pid: vaga[2] for pid, vaga in zip(ids, vagas)}


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


def _interacao(va: dict[str, int], vb: dict[str, int]) -> float:
    """Vantagem de A sobre B que existe SO por causa do par.

    Por que produtos e nao diferencas: um termo do tipo `A - B` se decompoe em efeito de A
    menos efeito de B, ou seja, e efeito INDIVIDUAL disfarcado -- ele diz "esta formacao e
    melhor", nunca "esta formacao e dificil para aquela". Medi e a interacao pura dava
    0,2 ponto. Confronto de verdade e nao-aditivo, e sai de choques estruturais concretos.
    """
    ganho = 0.0
    # ponta contra linha de tres: sem lateral, quem tem tres atacantes ataca o corredor
    ganho += PESO_PONTA * max(0, va["FW"] - 2) * max(0, 4 - vb["DF"])
    # meio povoado contra meio curto: quem tem cinco meias sufoca quem tem tres
    ganho += PESO_MEIO_CHEIO * max(0, va["MF"] - 4) * max(0, 4 - vb["MF"])
    # defesa de cinco absorve ataque de tres e devolve no contra-ataque
    ganho += PESO_ABSORVE * max(0, va["DF"] - 4) * max(0, vb["FW"] - 2)
    return ganho


def confronto(a: Tatica, b: Tatica) -> tuple[float, float]:
    """(multiplicador dos gols de A, multiplicador dos gols de B) para ESTE par.

    Junta o efeito absoluto de cada tatica com o efeito do confronto entre as formacoes.
    Com as duas no padrao, devolve (1.0, 1.0): e a ancora da calibracao.
    """
    a_ata, a_def = a.multiplicadores()
    b_ata, b_def = b.multiplicadores()
    va, vb = FORMACOES[a.formacao], FORMACOES[b.formacao]
    return (a_ata * b_def * (1.0 + _interacao(va, vb)),
            b_ata * a_def * (1.0 + _interacao(vb, va)))
