"""Taticas: formacao, marcacao e estilo de jogo.

Cada uma mexe nos lambdas do motor, entao nenhuma pode entrar sem numero. Os efeitos aqui
sao DELIBERADAMENTE modestos: tatica tem de ser escolha com troca (ganha de um lado, perde
do outro), nunca botao de vencer. Quem decide o jogo continua sendo o elenco.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


# --- OS PONTOS DO CAMPO ---
# Como no Brasfoot: o campo tem pontos FIXOS, e montar o time e escolher em quais deles os
# dez de linha ficam. As formacoes prontas sao so desenhos iniciais sobre estes pontos, e a
# escalacao e uma lista de onze ids na MESMA ordem do desenho -- "quem joga de 9" e uma
# escolha do usuario, nao um detalhe da tela.
#
# id -> (rotulo, setor, papel, x, y). O setor e o grupo de posicao que o ponto pede; o
# papel e o position_detail que o motor de eventos usa para decidir quem finaliza, da o
# passe e comete falta -- quem ocupa a vaga de centroavante chuta como centroavante. x e y
# sao a posicao no desenho, em % do campo, com o ataque em cima.
PONTOS: dict[str, tuple[str, str, str, int, int]] = {
    "GOL": ("GOL", "GK", "GK", 50, 89),
    # defesa
    "LE":  ("LE",  "DF", "FB", 12, 70),
    "ZE":  ("ZAG", "DF", "CB", 31, 74),
    "ZC":  ("ZAG", "DF", "CB", 50, 76),
    "ZD":  ("ZAG", "DF", "CB", 69, 74),
    "LD":  ("LD",  "DF", "FB", 88, 70),
    "ALE": ("ALA", "DF", "FB", 9, 56),
    "ALD": ("ALA", "DF", "FB", 91, 56),
    # volantes
    "VE":  ("VOL", "MF", "DM", 32, 60),
    "VC":  ("VOL", "MF", "DM", 50, 61),
    "VD":  ("VOL", "MF", "DM", 68, 60),
    # meio
    "ME":  ("ME",  "MF", "WG", 12, 44),
    "MCE": ("MC",  "MF", "MF", 31, 48),
    "MCC": ("MC",  "MF", "MF", 50, 47),
    "MCD": ("MC",  "MF", "MF", 69, 48),
    "MD":  ("MD",  "MF", "WG", 88, 44),
    # meias ofensivos
    "MEE": ("MEI", "MF", "AM", 30, 35),
    "MEI": ("MEI", "MF", "AM", 50, 34),
    "MED": ("MEI", "MF", "AM", 70, 35),
    # ataque
    "PE":  ("PE",  "FW", "WG", 15, 23),
    "PD":  ("PD",  "FW", "WG", 85, 23),
    "CAE": ("CA",  "FW", "FW", 37, 19),
    "CA":  ("CA",  "FW", "FW", 50, 16),
    "CAD": ("CA",  "FW", "FW", 63, 19),
}

# As formacoes prontas, ponto a ponto e NA ORDEM das vagas. Os papeis sao os mesmos de
# antes dos pontos (o 4-4-2 com um volante e um meia, o 4-5-1 com um meia ofensivo): o
# motor de eventos foi medido com eles.
DESENHOS: dict[str, list[str]] = {
    "4-3-3":   ["GOL", "LE", "ZE", "ZD", "LD", "MCE", "VC", "MCD", "PE", "CA", "PD"],
    "4-4-2":   ["GOL", "LE", "ZE", "ZD", "LD", "ME", "VE", "MCD", "MD", "CAE", "CAD"],
    "4-5-1":   ["GOL", "LE", "ZE", "ZD", "LD", "ME", "MCE", "VC", "MED", "MD", "CA"],
    "3-5-2":   ["GOL", "ZE", "ZC", "ZD", "ME", "MCE", "VC", "MED", "MD", "CAE", "CAD"],
    "5-3-2":   ["GOL", "ALE", "ZE", "ZC", "ZD", "ALD", "MCE", "VC", "MCD", "CAE", "CAD"],
    "3-4-3":   ["GOL", "ZE", "ZC", "ZD", "ME", "VE", "MCD", "MD", "PE", "CA", "PD"],
    "4-2-3-1": ["GOL", "LE", "ZE", "ZD", "LD", "VE", "VD", "ME", "MEI", "MD", "CA"],
}

# Um desenho livre ainda tem de ser um time: tres a cinco defensores, um a tres atacantes.
LIMITES_DO_DESENHO = {"DF": (3, 5), "FW": (1, 3)}

# A lista de vagas de cada formacao pronta, no formato (rotulo, setor, papel, x, y).
VAGAS: dict[str, list[tuple[str, str, str, int, int]]] = {
    nome: [PONTOS[k] for k in desenho] for nome, desenho in DESENHOS.items()}

# O efeito das contagens que nenhuma formacao pronta tem, interpolado das vizinhas: tirar
# um zagueiro e por um meia vale o que vale entre 4-4-2 e 3-5-2; trocar um meia por um
# atacante, o que vale entre 4-4-2 e 4-3-3.
EFEITO_DE_CONTAGEM: dict[tuple[int, int, int], tuple[float, float]] = {
    (3, 6, 1): (0.92, 0.96),
    (5, 4, 1): (0.82, 0.81),
    (5, 2, 3): (0.93, 0.91),
}


def contagem(pontos: list[str]) -> dict[str, int]:
    fora = {"GK": 0, "DF": 0, "MF": 0, "FW": 0}
    for k in pontos:
        fora[PONTOS[k][1]] += 1
    return fora


def nome_do_desenho(pontos: list[str]) -> str:
    """O nome da formacao pronta, se o desenho for o dela; senao, pelas faixas do campo --
    defesa, volantes, meio, meias ofensivos, ataque: "4-1-4-1", "4-1-2-1-2"... Faixa
    vazia nao entra no nome."""
    pronta = next((n for n, d in DESENHOS.items() if set(d) == set(pontos)), None)
    if pronta:
        return pronta
    faixa = {"DF": 0, "DM": 1, "MF": 2, "WG": 2, "AM": 3, "FW": 4}
    linhas = [0] * 5
    for k in pontos:
        _, setor, papel, _, _ = PONTOS[k]
        if setor != "GK":
            linhas[4 if setor == "FW" else 0 if setor == "DF" else faixa[papel]] += 1
    return "-".join(str(n) for n in linhas if n)


def _papeis(pontos: list[str], papel: str) -> int:
    return sum(1 for k in pontos if PONTOS[k][2] == papel)


def efeito_do_desenho(pontos: list[str]) -> tuple[float, float]:
    """(ataque, defesa) do desenho. Contagem igual a de uma formacao pronta vale o efeito
    dela -- a calibracao foi feita nelas, e o 4-3-3 continua valendo exatamente (1, 1)."""
    v = contagem(pontos)
    chave = (v["DF"], v["MF"], v["FW"])
    prontas = [n for n, d in DESENHOS.items()
               if tuple(contagem(d)[s] for s in ("DF", "MF", "FW")) == chave]
    if not prontas:
        return EFEITO_DE_CONTAGEM.get(chave, (0.95, 0.95))
    # 4-5-1 e 4-2-3-1 tem as mesmas contagens: o que separa e o volante duplo
    prontas.sort(key=lambda n: (set(DESENHOS[n]) != set(pontos),
                                abs(_papeis(DESENHOS[n], "DM") - _papeis(pontos, "DM"))))
    return EFEITO_FORMACAO[prontas[0]]


def validar_desenho(pontos: list[str]) -> None:
    if len(pontos) != 11:
        raise ValueError(f"o desenho precisa de 11 pontos, vieram {len(pontos)}")
    fora = [k for k in pontos if k not in PONTOS]
    if fora:
        raise ValueError(f"ponto desconhecido: {fora}")
    if len(set(pontos)) != 11:
        raise ValueError("dois jogadores no mesmo ponto do campo")
    if pontos.count("GOL") != 1:
        raise ValueError("o time precisa de um goleiro, e so um")
    v = contagem(pontos)
    for setor, (lo, hi) in LIMITES_DO_DESENHO.items():
        if not lo <= v[setor] <= hi:
            nome = {"DF": "defensores", "FW": "atacantes"}[setor]
            raise ValueError(f"o time precisa de {lo} a {hi} {nome}; ficaria com {v[setor]}")


def arrumar_no_campo(jogadores: list, formacao) -> list:
    """Poe onze jogadores nas vagas da formacao, do jeito que um treinador poria.

    Custo de cada par (jogador, vaga): fora do setor pesa muito, papel diferente pesa um
    pouco, e o pe trocado na ponta pesa menos ainda -- o canhoto vai para a esquerda.
    Guloso sobre os pares ordenados por custo; com onze jogadores basta.
    """
    vagas = VAGAS[formacao] if isinstance(formacao, str) else formacao
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


def papeis_em_campo(ids: list[int], formacao) -> dict[int, str]:
    """{jogador: papel da vaga que ele ocupa}. Vazio se a lista nao casa com a formacao.
    `formacao` e o nome de uma pronta ou a lista de vagas (Tatica.vagas_do_campo)."""
    vagas = VAGAS.get(formacao, []) if isinstance(formacao, str) else formacao
    if len(ids) != len(vagas):
        return {}
    return {pid: vaga[2] for pid, vaga in zip(ids, vagas)}


@dataclass(slots=True)
class Tatica:
    formacao: str = "4-3-3"
    marcacao: str = "normal"
    estilo: str = "equilibrado"
    # o desenho livre: o ponto do campo (PONTOS) de cada vaga, na ordem do onze. Vazio e o
    # desenho da formacao pronta; `formacao` fica como a base de onde ele saiu.
    desenho: list[str] = field(default_factory=list)

    def validar(self) -> None:
        if self.formacao not in FORMACOES:
            raise ValueError(f"formacao {self.formacao!r}; use {sorted(FORMACOES)}")
        if self.marcacao not in MARCACOES:
            raise ValueError(f"marcacao {self.marcacao!r}; use {sorted(MARCACOES)}")
        if self.estilo not in ESTILOS:
            raise ValueError(f"estilo {self.estilo!r}; use {sorted(ESTILOS)}")
        if self.desenho:
            validar_desenho(self.desenho)

    @property
    def pontos(self) -> list[str]:
        return list(self.desenho) if self.desenho else list(DESENHOS[self.formacao])

    def vagas_do_campo(self) -> list[tuple[str, str, str, int, int]]:
        return [PONTOS[k] for k in self.pontos]

    @property
    def vagas(self) -> dict[str, int]:
        """Quantos de cada setor -- do desenho, nao do nome da formacao."""
        return contagem(self.pontos)

    @property
    def nome(self) -> str:
        return nome_do_desenho(self.pontos)

    def multiplicadores(self) -> tuple[float, float]:
        """(quanto multiplica os proprios gols, quanto multiplica os gols do adversario)."""
        ea, ed = ESTILOS[self.estilo]
        fa, fd = efeito_do_desenho(self.pontos)
        mrc = MARCACOES[self.marcacao][0]
        return ea * fa, ed * fd * mrc

    @property
    def custo_de_energia(self) -> float:
        return MARCACOES[self.marcacao][1]

    def como_texto(self) -> str:
        return f"{self.nome}, marcacao {self.marcacao}, {self.estilo}"


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
    va, vb = a.vagas, b.vagas
    return (a_ata * b_def * (1.0 + _interacao(va, vb)),
            b_ata * a_def * (1.0 + _interacao(vb, va)))
