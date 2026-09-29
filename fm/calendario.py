"""O dia do calendario de cada data da agenda.

A agenda da carreira e uma lista de DATAS (rodada de liga ou etapa de copa), uma depois
da outra. O dia de cada uma sai daqui: a temporada abre em 6 de abril e cada data fica
DIAS_POR_DATA dias depois da anterior. Era so cosmetico, na tela; passou a valer regra
quando a lesao comecou a ser contada em dias -- por isso saiu do servidor e mora aqui.
"""

from __future__ import annotations

from datetime import date, timedelta

INICIO_DA_TEMPORADA = (4, 6)        # mes, dia
DIAS_POR_DATA = 4


def dia_da_data(temporada: int, indice: int) -> date:
    mes, dia = INICIO_DA_TEMPORADA
    return date(temporada, mes, dia) + timedelta(days=indice * DIAS_POR_DATA)


def texto(d: date) -> str:
    return d.strftime("%d/%m/%Y")
