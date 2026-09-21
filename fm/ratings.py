"""Valor de mercado -> overall e potencial.

PRINCIPIO: o valor de mercado da a HIERARQUIA; o forca do clube da o NIVEL. Valor e bom
para dizer quem e melhor que quem e ruim para dizer "isto e um 82", porque o Brasileirao e
globalmente mais barato que a Europa. Cada um faz o que faz bem.

    1. valor_qualidade = valor / (K_POS[pos] * A(idade)^W)
    2. z  = padroniza ln(valor_qualidade) DENTRO do elenco, limitado a +-CLAMP
    3. POT = forca_clube + BETA * z
    4. OVR = POT - teto_crescimento(idade) * (1 - 0.6 * min(1, partidas/20))
    5. desloca tudo para a media do melhor onze cair exatamente no forca_clube

Por que W < 1: o mercado desconta jogador velho por dois motivos -- pouca carreira restante
(nao e falta de qualidade hoje, deve ser devolvido) e declinio real (E falta de qualidade
hoje, nao deve ser devolvido). Dividir pelo multiplicador inteiro credita ao veterano uma
qualidade que ele nao tem: media com W=1 dava OVR 94 para um 33 anos de 10 milhoes. Com
W=0.5 mais teto de CORR_MAX, da 90 -- mais velho continua melhor HOJE com o mesmo valor,
que e correto, sem estourar a escala.

As constantes sao ajustaveis contra dados, nao gosto: ver fm/diagnostics.py.
"""

from __future__ import annotations

import numpy as np

from fm.model import FORMATION_DEFAULT
from fm.model import POSICAO_DETALHE as GRUPO_POSICAO

# Premio de posicao: quanto o mercado paga A MAIS pela mesma qualidade.
K_POS = {"FW": 1.35, "WG": 1.30, "AM": 1.18, "MF": 1.05, "DM": 0.95,
         "FB": 0.90, "CB": 0.85, "GK": 0.65}
K_POS_PADRAO = 1.00


# Multiplicador de valor para qualidade CONSTANTE. Referencia: 27 anos = 1.00.
IDADE_MULT = {17: 1.45, 18: 1.45, 19: 1.42, 20: 1.40, 21: 1.36, 22: 1.30, 23: 1.24,
              24: 1.18, 25: 1.12, 26: 1.06, 27: 1.00, 28: 0.92, 29: 0.80, 30: 0.68,
              31: 0.55, 32: 0.45, 33: 0.35, 34: 0.27, 35: 0.20, 36: 0.15, 37: 0.12}

# Quanto o jogador ainda pode crescer, em pontos de overall.
TETO_CRESCIMENTO = {17: 20, 18: 18, 19: 16, 20: 14, 21: 12, 22: 10, 23: 8,
                    24: 6, 25: 4, 26: 2, 27: 1}

W = 0.5           # amolece a correcao de idade
CORR_MAX = 2.0    # a idade nunca infla o valor-qualidade mais que isto
BETA = 5.0        # pontos de overall por desvio-padrao de log-valor no elenco
CLAMP = 2.4       # limite em desvios: impede que um fora-de-serie vire 99
REALIZACAO_JOGOS = 20     # partidas para considerar o jogador "ja entregue"
REALIZACAO_PESO = 0.8     # quanto jogar reduz o desconto de imaturidade
# 0.8 e nao 0.6 por medicao: com 0.6, o jogador mais valioso da Serie A (21 anos, 38 mi,
# temporada inteira jogada) ficava no BANCO do proprio clube. Quem ja joga como titular
# entregou qualidade, e o desconto de imaturidade tem de quase sumir. Com 0.8, os 10 mais
# caros da liga sao todos titulares.
OVR_MIN, OVR_MAX = 40, 95

# Quando o valor nao existe (jogador sem cotacao), usa-se este piso para nao zerar o log.
VALOR_PISO = 25_000


def idade_mult(idade: int | None) -> float:
    if idade is None:
        return 1.0
    return IDADE_MULT.get(int(np.clip(idade, 17, 37)), 0.12)


def correcao_idade(idade: int | None) -> float:
    return max(idade_mult(idade) ** W, 1.0 / CORR_MAX)


def teto_crescimento(idade: int | None) -> float:
    if idade is None:
        return 0.0
    return float(TETO_CRESCIMENTO.get(int(idade), 0))


def valor_qualidade(valor: int | None, posicao: str | None, idade: int | None) -> float:
    """Valor equivalente em QUALIDADE: tira o premio de posicao e parte do efeito idade."""
    v = max(int(valor or VALOR_PISO), VALOR_PISO)
    k = K_POS.get(posicao or "", K_POS_PADRAO)
    return v / (k * correcao_idade(idade))


def converter_elenco(
    jogadores: list[dict], forca_clube: float, formacao=None,
) -> list[dict]:
    """Recebe dicts com posicao/idade/valor/partidas e devolve os mesmos com ovr e pot.

    Nao faz I/O e nao depende de rede: da para reajustar constante e rodar de novo sobre o
    cache quantas vezes quiser.
    """
    if not jogadores:
        return []
    if formacao is None:
        formacao = tuple(FORMATION_DEFAULT[g] for g in ("GK", "DF", "MF", "FW"))
    q = np.log([valor_qualidade(j.get("valor"), j.get("posicao"), j.get("idade"))
                for j in jogadores])
    desvio = q.std() or 1.0
    z = np.clip((q - q.mean()) / desvio, -CLAMP, CLAMP)
    pot_prov = forca_clube + BETA * z
    realizacao = np.array([min(1.0, (j.get("partidas") or 0) / REALIZACAO_JOGOS)
                           for j in jogadores])
    gap = np.array([teto_crescimento(j.get("idade")) for j in jogadores]) * (
        1.0 - REALIZACAO_PESO * realizacao)
    ovr_prov = pot_prov - gap

    # ancora: a media do melhor onze tem de cair no forca desenhado do clube
    grupos = [GRUPO_POSICAO.get(j.get("posicao") or "", "MF") for j in jogadores]
    falta = dict(zip(("GK", "DF", "MF", "FW"), formacao, strict=True))
    xi: list[int] = []
    for k in np.argsort(-ovr_prov):
        g = grupos[int(k)]
        if falta.get(g, 0) > 0:
            falta[g] -= 1
            xi.append(int(k))
    alpha = forca_clube - (ovr_prov[xi].mean() if xi else ovr_prov.mean())

    ovr = np.clip(np.round(ovr_prov + alpha), OVR_MIN, OVR_MAX).astype(int)
    pot = np.clip(np.round(pot_prov + alpha), ovr, OVR_MAX).astype(int)
    saida = []
    for i, j in enumerate(jogadores):
        novo = dict(j)
        novo["ovr"] = int(ovr[i])
        novo["pot"] = int(pot[i])
        novo["titular"] = i in xi
        saida.append(novo)
    return saida


def forca_dos_clubes(
    valores_elenco: dict[str, int], media_liga: float, beta_clube: float,
) -> dict[str, float]:
    """Valor total de elenco -> forca do clube.

    Dois parametros por liga (media e beta) ajustados contra os [alvos] declarados no
    arquivo da liga. E o que remove o chute editorial do pack.
    """
    ids = list(valores_elenco)
    v = np.log([max(valores_elenco[i], 1) for i in ids])
    z = (v - v.mean()) / (v.std() or 1.0)
    return {i: float(media_liga + beta_clube * zi) for i, zi in zip(ids, z, strict=True)}
