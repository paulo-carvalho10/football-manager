"""O calendario real da temporada: liga no fim de semana, copa no meio de semana.

Antes a agenda era uma fila de datas de 4 em 4 dias, com UMA etapa de UMA copa por data. Com
o mundo inteiro marcado eram cinco copas revezando na fila: 143 datas, uma temporada de
dezenove meses no relogio, e a Libertadores so entrava na fase de grupos em setembro --
quando chegava a vez dela.

Agora cada fase de copa tem a JANELA real dela (`janela = ["04-01", "05-28"]` no arquivo
do torneio): a pre-Libertadores em fevereiro, os grupos de abril a maio, o mata-mata de
agosto a outubro, a final no fim de novembro. As ligas jogam aos domingos de abril a
dezembro; a que tem mais rodadas do que domingos (a Championship, 46) usa quartas-feiras.
Cada liga tem o PROPRIO calendario dentro da grade comum: o Brasileirao, com 38 rodadas,
termina em dezembro como a Championship -- e o Paraguai, com 22, folga em alguns domingos.

Nada aqui decide resultado. E so QUANDO cada coisa acontece -- e isso passou a valer regra
com a lesao contada em dias e a energia recuperada pelos dias de descanso.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

# Brasileirao: do comeco de abril ao comeco de dezembro, aos domingos.
INICIO_DAS_LIGAS = (4, 5)
FIM_DAS_LIGAS = (12, 6)

# Copas que podem ter o MESMO clube ao mesmo tempo nao jogam no mesmo dia nem em dias
# colados: o grande brasileiro esta na Copa do Brasil e na Libertadores no mesmo ano. As
# outras dividem o dia a vontade -- Libertadores e Sul-Americana, Champions e Liga Europa
# nunca tem o mesmo clube na mesma semana.
CONFLITOS = {frozenset({"copa_do_brasil", "libertadores"}),
             frozenset({"copa_do_brasil", "sudamericana"})}

# O dia da semana preferido de cada copa (0 = segunda), na ordem de tentativa.
DIAS_PREFERIDOS = {
    "libertadores": (2, 1, 3), "sudamericana": (3, 1, 2), "copa_do_brasil": (2, 3, 1),
    "champions": (1, 2, 3), "europa_league": (3, 2, 1),
}
DIAS_DE_MEIO_DE_SEMANA = (1, 2, 3)     # terca, quarta, quinta
INTERVALO_DA_COPA = 6                  # dias minimos entre duas etapas da mesma copa
RESERVAS_NO_FIM = 2                    # datas de sobra por copa, so usadas se ela atrasar


@dataclass(slots=True)
class Data:
    dia: date
    tipo: str               # "liga" ou "copa"
    quem: str = ""          # a copa ("" na liga)
    fase: int = -1          # a fase da copa para a qual a data foi reservada
    reserva: bool = False   # sobra no fim: so acontece se a copa atrasou


def _dia(temporada: int, mes_dia: str | tuple[int, int]) -> date:
    if isinstance(mes_dia, str):
        mes, dia = (int(x) for x in mes_dia.split("-"))
    else:
        mes, dia = mes_dia
    return date(temporada, mes, dia)


def _proximo(d: date, dia_da_semana: int) -> date:
    return d + timedelta(days=(dia_da_semana - d.weekday()) % 7)


def _espalhar(n: int, total: int) -> list[int]:
    """n indices distintos em range(total), espalhados com as duas pontas incluidas."""
    if n <= 0:
        return []
    if n == 1:
        return [total - 1]
    return sorted({round(i * (total - 1) / (n - 1)) for i in range(n)})


def grade_das_ligas(temporada: int, rodadas: dict[str, int]
                    ) -> tuple[list[date], dict[str, list[int]]]:
    """(datas da grade, {liga: indice na grade de cada rodada, em ordem}).

    A grade sao os domingos da janela das ligas, mais quartas-feiras espalhadas se alguma
    liga tiver mais rodadas do que domingos. Cada liga escolhe as SUAS datas: primeiro os
    domingos, espalhados; as quartas so entram para quem precisa delas.
    """
    inicio = _proximo(_dia(temporada, INICIO_DAS_LIGAS), 6)
    fim = _dia(temporada, FIM_DAS_LIGAS)
    domingos = []
    d = inicio
    while d <= fim:
        domingos.append(d)
        d += timedelta(days=7)
    maior = max(rodadas.values(), default=0)
    extras_pedidas = max(0, maior - len(domingos))
    # quartas entre o segundo e o penultimo domingo, espalhadas
    quartas_possiveis = [x + timedelta(days=3) for x in domingos[1:-1]]
    quartas = [quartas_possiveis[i] for i in _espalhar(min(extras_pedidas, len(quartas_possiveis)),
                                                      len(quartas_possiveis))]
    grade = sorted(domingos + quartas)
    pos = {d: i for i, d in enumerate(grade)}
    mapa: dict[str, list[int]] = {}
    for liga, n in rodadas.items():
        if n <= len(domingos):
            escolhidas = [domingos[i] for i in _espalhar(n, len(domingos))]
        else:
            escolhidas = domingos + [quartas[i] for i in _espalhar(n - len(domingos), len(quartas))]
        # se faltar data na grade (liga enorme), as ultimas rodadas ficam nas ultimas datas
        indices = sorted(pos[d] for d in escolhidas)
        while len(indices) < n:
            indices.append(indices[-1] + 1 if indices else 0)
        mapa[liga] = indices[:n]
    while grade and len(grade) <= max((max(v) for v in mapa.values() if v), default=-1):
        grade.append(grade[-1] + timedelta(days=7))
    return grade, mapa


def _alvos_da_fase(inicio: date, fim: date, fase: dict, etapas: int) -> list[date]:
    """Os dias-alvo de cada etapa dentro da janela. Mata-mata: as rodadas espalhadas pela
    janela e as maos de cada confronto em semanas seguidas. Grupos e liga: espalhadas."""
    span = max(0, (fim - inicio).days)
    if fase.get("tipo") == "knockout":
        maos = int(fase.get("maos", 2))
        rodadas = max(1, math.ceil(etapas / maos))
        alvos = []
        for r in range(rodadas):
            base = inicio + timedelta(days=round(r * span / rodadas)) if rodadas > 1 else inicio
            alvos += [base + timedelta(days=7 * m) for m in range(maos)]
        return alvos[:etapas]
    if etapas == 1:
        return [inicio]
    return [inicio + timedelta(days=round(j * span / (etapas - 1))) for j in range(etapas)]


def montar(temporada: int, rodadas: dict[str, int],
           copas: dict[str, list[tuple[dict, int]]]) -> tuple[list[Data], dict[str, list[int]]]:
    """A agenda da temporada e o mapa das rodadas de cada liga na grade.

    `rodadas` e {liga: quantas rodadas}; `copas` e {copa: [(fase, etapas previstas)]}, com a
    janela de cada fase no proprio dict da fase. Devolve as datas em ordem cronologica e
    {liga: [indice da DATA DE LIGA (0, 1, 2...) de cada rodada]}.
    """
    grade, mapa = grade_das_ligas(temporada, rodadas)
    usados_liga = set(grade)
    ocupado: dict[str, set[date]] = {}        # por copa: os dias com etapa
    datas: list[Data] = [Data(dia=d, tipo="liga") for d in grade]

    def livre(d: date, copa: str) -> bool:
        if d.weekday() not in DIAS_DE_MEIO_DE_SEMANA or d in usados_liga:
            return False
        # a copa que divide clube com esta nao pode estar no dia nem colada nele
        for outra, dias in ocupado.items():
            if outra != copa and frozenset({copa, outra}) in CONFLITOS and any(
                    d + timedelta(days=k) in dias for k in (-1, 0, 1)):
                return False
        return d not in ocupado.get(copa, set())

    def encaixar(alvo: date, copa: str, depois_de: date | None) -> date:
        piso = max(alvo, depois_de + timedelta(days=INTERVALO_DA_COPA)) if depois_de else alvo
        semana = piso - timedelta(days=piso.weekday())
        for _ in range(60):
            for wd in DIAS_PREFERIDOS.get(copa, DIAS_DE_MEIO_DE_SEMANA):
                d = semana + timedelta(days=wd)
                if d >= piso and livre(d, copa):
                    return d
            semana += timedelta(days=7)
        return piso      # nao deve acontecer: sobra o dia pedido

    # quem abre primeiro escolhe primeiro: a pre-Libertadores antes da Champions
    def abertura(nome: str) -> date:
        fases = copas[nome]
        return min((_dia(temporada, f["janela"][0]) for f, _ in fases if f.get("janela")),
                   default=date(temporada, 12, 31))

    for nome in sorted(copas, key=lambda n: (abertura(n), n)):
        ultimo: date | None = None
        for k, (fase, etapas) in enumerate(copas[nome]):
            if etapas <= 0:
                continue
            janela = fase.get("janela")
            if janela:
                inicio, fim = _dia(temporada, janela[0]), _dia(temporada, janela[1])
            else:            # fase sem janela: logo depois da anterior
                inicio = (ultimo or _dia(temporada, (2, 1))) + timedelta(days=7)
                fim = inicio + timedelta(days=7 * etapas)
            for alvo in _alvos_da_fase(inicio, fim, fase, etapas):
                d = encaixar(alvo, nome, ultimo)
                ocupado.setdefault(nome, set()).add(d)
                datas.append(Data(dia=d, tipo="copa", quem=nome, fase=k))
                ultimo = d
        # a sobra do fim: so acontece se a copa atrasou (fase com mais etapas que o previsto)
        for _ in range(RESERVAS_NO_FIM):
            if ultimo is None:
                break
            d = encaixar(ultimo + timedelta(days=7), nome, ultimo)
            ocupado.setdefault(nome, set()).add(d)
            datas.append(Data(dia=d, tipo="copa", quem=nome, fase=len(copas[nome]) - 1,
                              reserva=True))
            ultimo = d

    datas.sort(key=lambda x: (x.dia, x.tipo != "copa", x.quem))
    return datas, mapa


def etapas_por_fase(torneio, clubes_por_fase: list[int]) -> list[int]:
    """Quantas datas cada fase ocupa. `clubes_por_fase` e a estimativa de quantos clubes
    disputam cada fase -- so importa no mata-mata "todas" (a Copa do Brasil a partir da
    terceira fase), em que o numero de rodadas depende de quantos sobraram."""
    fora = []
    for k, fase in enumerate(torneio.fases):
        tipo = fase.get("tipo")
        n = clubes_por_fase[k] if k < len(clubes_por_fase) else 0
        if tipo == "groups":
            grupos = int(fase.get("grupos", 8))
            tamanho = max(2, round(n / grupos)) if n else 4
            fora.append((tamanho - 1) * int(fase.get("voltas", 2)))
        elif tipo == "liga_suica":
            fora.append(int(fase.get("adversarios", 8)))
        elif tipo == "round_robin":
            fora.append(max(1, (n - 1)) * int(fase.get("voltas", 1)) if n else 6)
        else:
            pedido = fase.get("rodadas", "todas")
            rodadas = (max(1, math.ceil(math.log2(max(n, 2)))) if pedido == "todas"
                       else int(pedido))
            fora.append(rodadas * int(fase.get("maos", 2)))
    return fora


def clubes_por_fase(torneio, entrantes_por_fase: list[int]) -> list[int]:
    """Quantos clubes disputam cada fase: os que sobraram da anterior mais os que entram.
    Estimativa: a vaga que vem de outra copa (`aguarda`) nao entra na conta."""
    fora, sobraram = [], 0
    for k, fase in enumerate(torneio.fases):
        n = sobraram + (entrantes_por_fase[k] if k < len(entrantes_por_fase) else 0)
        fora.append(n)
        tipo = fase.get("tipo")
        if tipo == "groups":
            sobraram = int(fase.get("grupos", 8)) * int(fase.get("avancam", 2))
        elif tipo in ("liga_suica", "round_robin"):
            sobraram = int(fase.get("avancam", n))
        else:
            pedido = fase.get("rodadas", "todas")
            rodadas = (math.ceil(math.log2(max(n, 2))) if pedido == "todas" else int(pedido))
            sobraram = max(1, math.ceil(n / 2 ** rodadas)) + int(fase.get("isentos", 0))
    return fora
