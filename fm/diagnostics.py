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

from fm.model import FORMATION_DEFAULT, grupo_posicao


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


def titulares_do_clube(jogadores: list[dict]) -> set[int]:
    """Onze provavel respeitando a formacao -- nao os 11 maiores overalls.

    Sem isso o diagnostico acusa injustica que nao existe: um clube com quatro zagueiros
    de 86 nao escala os quatro.
    """
    falta = dict(FORMATION_DEFAULT)
    escolhidos: set[int] = set()
    for j in sorted(jogadores, key=lambda x: -(x.get("ovr") or 0)):
        g = grupo_posicao(j.get("posicao")) or "MF"
        if falta.get(g, 0) > 0:
            falta[g] -= 1
            escolhidos.add(id(j))
    return escolhidos


def diagnosticar(clubes: list[dict]) -> list[Diagnostico]:
    """`clubes`: [{"nome": ..., "jogadores": [dicts com ovr, posicao, idade, valor]}]."""
    if not clubes:
        return []
    jogadores: list[dict] = []
    mais_caro_titular = 0
    clubes_contados = 0
    for c in clubes:
        js = c["jogadores"]
        if not js:
            continue
        xi = titulares_do_clube(js)
        for j in js:
            jogadores.append({**j, "titular": id(j) in xi})
        # So jogadores em IDADE DE PICO: no jogador jovem o valor e potencial, nao
        # qualidade de hoje. Em segunda divisao o mais caro do clube e quase sempre um
        # garoto emprestado por clube grande -- um caso real tinha 22 anos, 5 milhoes e
        # 28 MINUTOS jogados. Ele nao ser titular esta certo, e contar isso como erro
        # fazia o diagnostico acusar o modelo por um fato do dado.
        pico = [j for j in js if 24 <= (j.get("idade") or 0) <= 31
                and (j.get("valor") or 0) > 0]
        if pico:
            caro = max(pico, key=lambda x: x["valor"])
            clubes_contados += 1
            mais_caro_titular += int(id(caro) in xi)
    tit = [j for j in jogadores if j.get("titular")]
    gk = [j["ovr"] for j in tit if j.get("posicao") == "GK"]
    linha = [j["ovr"] for j in tit if j.get("posicao") != "GK"]
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
            "mais_caro_em_idade_de_pico_titular",
            100.0 * mais_caro_titular / max(clubes_contados, 1), 80.0, 100.0,
            "O jogador mais caro de cada clube ENTRE OS DE 24 A 31 ANOS deve ser titular "
            "dele. Duas armadilhas ja corrigidas aqui: olhar os dez mais caros da LIGA "
            "punia concentracao (9 dos 10 mais caros de La Liga sao do Real Madrid e do "
            "Barcelona, e nenhum clube escala 11 craques), e nao filtrar idade punia o "
            "emprestimo de garoto caro, cujo valor e potencial e nao titularidade."),
        Diagnostico(
            "idade_media_titulares",
            float(np.mean(idades_tit)) if idades_tit else 0.0, 26.5, 30.5,
            "Idade de quem JOGA -- nao a media por faixa etaria, que mede composicao de "
            "elenco. Titular muito velho significa W alto demais (veterano recebendo "
            "qualidade que o desconto de idade escondia). Teto em 30,5 e nao 29,5 porque "
            "segunda divisao e genuinamente mais velha: e para onde vai o veterano."),
        Diagnostico(
            "idade_dos_50_melhores",
            float(np.mean([j["idade"] for j in top_ovr if j.get("idade")])), 26.0, 30.0,
            "Os melhores overalls nao podem ser um asilo nem uma escolinha."),
        Diagnostico(
            "desvio_de_overall", float(np.std([j["ovr"] for j in jogadores])), 7.0, 13.0,
            "Espalhamento da liga. Baixo demais achata tudo; alto demais cria 95 e 40 na "
            "mesma divisao. Faixa comeca em 7 e nao em 8 porque segunda divisao e "
            "genuinamente mais achatada -- o dinheiro nela e mais parecido entre clubes."),
    ]
