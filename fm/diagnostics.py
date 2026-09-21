"""Diagnosticos da conversao valor -> overall.

As constantes de fm/ratings.py so valem se resistirem a estes numeros medidos sobre a base
real. Sao o que separa "constante ajustada contra dado" de "constante que eu achei bonita".

CUIDADO COM DIAGNOSTICO CONFUNDIDO: a primeira versao deste modulo olhava a media de
overall por faixa de idade e acusava o modelo de favorecer veterano, porque a media subia
ate 30-32 anos. Era COMPOSICAO DE ELENCO, nao vies: clube dispensa veterano ruim e segura
garoto ruim, entao sobram 75 jogadores de 18-20 anos (quase todos da base, sem valor) e so
37 acima de 36. A media por idade mede quem o clube guarda, nao quem o modelo valoriza. O
diagnostico honesto e a idade de QUEM JOGA.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class Diagnostico:
    nome: str
    valor: float
    baixo: float
    alto: float
    explicacao: str

    @property
    def ok(self) -> bool:
        return self.baixo <= self.valor <= self.alto


def diagnosticar(jogadores: list[dict]) -> list[Diagnostico]:
    """`jogadores`: dicts ja convertidos (com ovr, posicao, idade, valor, titular)."""
    if not jogadores:
        return []
    tit = [j for j in jogadores if j.get("titular")]
    gk = [j["ovr"] for j in tit if j.get("posicao") == "GK"]
    linha = [j["ovr"] for j in tit if j.get("posicao") != "GK"]
    por_valor = sorted(jogadores, key=lambda x: -(x.get("valor") or 0))
    idades_tit = [j["idade"] for j in tit if j.get("idade")]
    top_ovr = sorted(jogadores, key=lambda x: -x["ovr"])[:50]

    return [
        Diagnostico(
            "goleiro_vs_linha", float(np.mean(gk) - np.mean(linha)) if gk and linha else 0.0,
            -1.5, 1.5,
            "O mercado paga bem menos por goleiro. Se a correcao de posicao estiver errada, "
            "os goleiros titulares saem sistematicamente abaixo dos titulares de linha. "
            "Ajuste K_POS['GK'] ate este numero ficar perto de zero."),
        Diagnostico(
            "top10_caros_titulares", float(sum(1 for j in por_valor[:10] if j.get("titular"))),
            9, 10,
            "Os dez jogadores mais caros da liga tem de ser titulares. Se nao forem, o "
            "desconto de imaturidade esta forte demais (REALIZACAO_PESO) ou a formacao "
            "nao cabe no elenco real."),
        Diagnostico(
            "idade_media_titulares",
            float(np.mean(idades_tit)) if idades_tit else 0.0, 26.5, 29.5,
            "Idade de quem JOGA -- nao a media por faixa etaria, que mede composicao de "
            "elenco. Titular muito velho significa W alto demais (veterano recebendo "
            "qualidade que o desconto de idade escondia)."),
        Diagnostico(
            "idade_dos_50_melhores",
            float(np.mean([j["idade"] for j in top_ovr if j.get("idade")])), 26.0, 30.0,
            "Os melhores overalls nao podem ser um asilo nem uma escolinha."),
        Diagnostico(
            "desvio_de_overall", float(np.std([j["ovr"] for j in jogadores])), 8.0, 13.0,
            "Espalhamento da liga. Baixo demais achata tudo; alto demais cria 95 e 40 na "
            "mesma divisao."),
    ]
