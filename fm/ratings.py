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

# O premio de posicao e propriedade do MERCADO, e mercados diferem. Medido: com o K de
# goleiro do Brasil (0.65), os goleiros da Segunda espanhola saiam 2,3 pontos ACIMA dos
# titulares de linha -- naquele mercado o desconto de goleiro e menor. Cada liga pode
# sobrescrever o que o diagnostico cobrar.
K_POS_POR_LIGA: dict[str, dict[str, float]] = {
    "esp_2": {**K_POS, "GK": 0.82},
}


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
REALIZACAO_JOGOS = 20     # partidas para considerar o jogador "ja entregue" (fallback)
# CUIDADO com limiar absoluto: as ligas nao estao no mesmo ponto da temporada. Em setembro
# de 2026 o Brasileirao ja tinha 30 a 45 jogos e La Liga tinha 5 rodadas -- com limiar fixo
# de 20 jogos, TODA a Espanha era tratada como "ainda nao entregou" e os craques novos (o
# mais caro da liga, 19 anos, 671 minutos) caiam para o banco do proprio clube. A conversao
# usa `minutos_referencia`, que e calculado por liga, quando ele e informado.
REALIZACAO_PESO = 0.8     # quanto jogar reduz o desconto de imaturidade
# 0.8 e nao 0.6 por medicao: com 0.6, o jogador mais valioso da Serie A (21 anos, 38 mi,
# temporada inteira jogada) ficava no BANCO do proprio clube. Quem ja joga como titular
# entregou qualidade, e o desconto de imaturidade tem de quase sumir. Com 0.8, os 10 mais
# caros da liga sao todos titulares.
OVR_MIN, OVR_MAX = 40, 95

# Quanto um jogador pode ficar ABAIXO da forca do clube. Minutos sao evidencia de qualidade
# independente do preco, e num elenco de Serie B a diferenca entre 300 mil e 500 mil e ruido
# de mercado, nao informacao.
QUEDA_MAXIMA_RESERVA = 16.0
QUEDA_MAXIMA_TITULAR = 8.0

# Mas o piso NAO vale igual para todo mundo, e essa foi a licao: aplicado cego a idade ele
# achatou a liga (desvio de overall caiu de 7,6 para 6,98 na Serie B).
#
#   garoto da base com valor baixo esta CERTO -- ele ainda nao e bom, e o potencial e que
#   carrega a historia dele;
#   veterano em queda com valor baixo tambem esta certo -- ele ja foi;
#   o piso existe para o jogador em IDADE DE PICO que joga muito e mesmo assim o mercado
#   nao precifica. Esse era o unico caso realmente errado.
PESO_DO_PISO_POR_IDADE = {17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0, 21: 0.15, 22: 0.4, 23: 0.7,
                          24: 1.0, 25: 1.0, 26: 1.0, 27: 1.0, 28: 1.0, 29: 1.0, 30: 1.0,
                          31: 0.9, 32: 0.7, 33: 0.45, 34: 0.25, 35: 0.1}


def peso_do_piso(idade: int | None) -> float:
    if idade is None:
        return 0.6
    return PESO_DO_PISO_POR_IDADE.get(int(idade), 0.0 if idade < 20 else 0.05)

# Teto por posicao. A normalizacao e DENTRO do elenco, entao num clube onde todo mundo e
# caro (Real Madrid, 1,46 bi) ate o lateral reserva sobe: Cucurella, Alexander-Arnold e
# Koundé saiam todos com 90, alto demais para a posicao. Nao e corte seco -- acima do
# limiar o valor e comprimido, para nao perder a ordem entre eles.
TETO_POR_POSICAO = {"FB": 87.0}
COMPRESSAO_TETO = 0.45      # quanto do excedente sobra acima do limiar
MARGEM_TETO = 5.0           # o limiar fica este tanto abaixo do teto


def aplicar_teto(valor: float, posicao: str | None) -> float:
    """Comprime suavemente o que passa do teto da posicao, preservando a ordem."""
    teto = TETO_POR_POSICAO.get(posicao or "")
    if teto is None or valor <= teto - MARGEM_TETO:
        return valor
    limiar = teto - MARGEM_TETO
    return min(teto, limiar + (valor - limiar) * COMPRESSAO_TETO)

# Quando o valor nao existe, usa-se este piso para nao zerar o log -- mas so como ultimo
# recurso: antes disso, os MINUTOS estimam o valor que falta.
VALOR_PISO = 25_000
# Desconto de quem nao tem cotacao: joga tanto quanto um cotado de valor X, mas o mercado
# nao o precificou, entao vale menos que ele.
DESCONTO_SEM_COTACAO = 0.55


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


def valor_qualidade(valor: int | None, posicao: str | None, idade: int | None,
                    k_pos: dict[str, float] | None = None) -> float:
    """Valor equivalente em QUALIDADE: tira o premio de posicao e parte do efeito idade."""
    v = max(int(valor or VALOR_PISO), VALOR_PISO)
    k = (k_pos or K_POS).get(posicao or "", K_POS_PADRAO)
    return v / (k * correcao_idade(idade))


def minutos_referencia(jogadores: list[dict], percentil: float = 85.0) -> float:
    """Quanto e "uma temporada inteira" NESTA liga, neste momento.

    Percentil alto dos minutos de quem jogou. Assim a mesma conta vale para uma liga na
    5a rodada e para outra na 35a.
    """
    mins = [j.get("minutos") or 0 for j in jogadores if (j.get("minutos") or 0) > 0]
    if not mins:
        return 0.0
    return max(float(np.percentile(mins, percentil)), 90.0)


def converter_elenco(
    jogadores: list[dict], forca_clube: float, formacao=None,
    referencia_minutos: float | None = None,
    k_pos: dict[str, float] | None = None,
) -> list[dict]:
    """Recebe dicts com posicao/idade/valor/partidas e devolve os mesmos com ovr e pot.

    Nao faz I/O e nao depende de rede: da para reajustar constante e rodar de novo sobre o
    cache quantas vezes quiser.
    """
    if not jogadores:
        return []
    if formacao is None:
        formacao = tuple(FORMATION_DEFAULT[g] for g in ("GK", "DF", "MF", "FW"))
    jogadores = imputar_valores(jogadores)
    q = np.log([valor_qualidade(j.get("valor"), j.get("posicao"), j.get("idade"), k_pos)
                for j in jogadores])
    desvio = q.std() or 1.0
    z = np.clip((q - q.mean()) / desvio, -CLAMP, CLAMP)
    pot_prov = forca_clube + BETA * z
    if any("realizacao" in j for j in jogadores):
        # o importador ja calculou (pode combinar duas temporadas)
        realizacao = np.array([float(j.get("realizacao") or 0.0) for j in jogadores])
    elif referencia_minutos:
        realizacao = np.array([min(1.0, (j.get("minutos") or 0) / referencia_minutos)
                               for j in jogadores])
    else:
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

    posicoes = [j.get("posicao") for j in jogadores]
    ovr_teto = np.array([aplicar_teto(v, p) for v, p in zip(ovr_prov + alpha, posicoes,
                                                            strict=True)])
    pot_teto = np.array([aplicar_teto(v, p) for v, p in zip(pot_prov + alpha, posicoes,
                                                            strict=True)])
    # piso por minutos, pesado pela idade: quem esta no pico e joga nao despenca; garoto
    # da base e veterano em queda continuam livres para estar la embaixo, porque para eles
    # o valor baixo e informacao verdadeira
    piso = []
    for r, j in zip(realizacao, jogadores, strict=True):
        peso = peso_do_piso(j.get("idade"))
        if peso <= 0.01:
            piso.append(-1e9)
            continue
        queda = (QUEDA_MAXIMA_TITULAR * r + QUEDA_MAXIMA_RESERVA * (1 - r)) / peso
        piso.append(forca_clube - queda)
    piso = np.array(piso)
    ovr = np.clip(np.round(np.maximum(ovr_teto, piso)), OVR_MIN, OVR_MAX).astype(int)
    pot = np.clip(np.round(pot_teto), ovr, OVR_MAX).astype(int)
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


BETA_GLOBAL = 7.0      # escala usada para posicionar uma liga em relacao as outras
TOPO_DO_MUNDO = 90.0   # o melhor clube do mundo importado vale isto


def forca_mundial(
    valores_por_liga: dict[str, dict[str, int]],
    betas: dict[str, float],
    *, beta_global: float = BETA_GLOBAL, topo: float = TOPO_DO_MUNDO,
    referencia: set[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Valor de elenco -> forca, para VARIAS ligas de uma vez.

    Duas escalas, e e por isso que esta funcao existe:

    - ENTRE ligas, o nivel sai do valor medio de elenco na escala global. Normalizar cada
      liga por si so apaga a diferenca de nivel: fazendo z por liga, o lanterna da Serie B
      (3,3 mi) saia MAIS FORTE que o lanterna da Serie A (20 mi), o que quebra a piramide.
    - DENTRO da liga, o spread usa o beta proprio dela, ajustado contra os [alvos] daquela
      liga. Um beta global unico achata a Serie A: a diferenca de dinheiro dentro dela e
      pequena perto da diferenca entre paises, e a disputa de titulo fica aleatoria demais.

    No fim tudo e deslocado para que o melhor clube do mundo caia em `topo`. A escala de
    overall e limitada (40 a 95), entao ela precisa de uma ancora no topo -- senao o Real
    Madrid, com elenco de 1,46 bilhao, estoura o teto e leva os jogadores junto.

    `referencia`: as ligas que definem a REGUA (media, desvio e a ancora do topo). As
    outras sao medidas contra ela sem move-la. Sem isto, importar oito ligas
    sul-americanas baratas puxava a media global para baixo e mudava a forca de todos os
    clubes ja existentes -- o mundo inteiro, e a calibracao junto, por causa da Bolivia.
    """
    ln = {liga: np.log(np.array(list(v.values()), dtype=float))
          for liga, v in valores_por_liga.items()}
    regua = [liga for liga in ln if referencia is None or liga in referencia]
    todos = np.concatenate([ln[liga] for liga in regua])
    mu, sd = todos.mean(), todos.std() or 1.0

    def calcular(desloc: float) -> dict[str, np.ndarray]:
        out = {}
        for liga, v in ln.items():
            nivel = beta_global * (v.mean() - mu) / sd + desloc
            out[liga] = nivel + betas[liga] * (v - v.mean()) / (v.std() or 1.0)
        return out

    desloc = 0.0
    for _ in range(60):     # converge o deslocamento que poe o topo do mundo no alvo
        desloc += (topo - max(x.max() for liga, x in calcular(desloc).items()
                              if liga in regua)) * 0.6
    resultado = calcular(desloc)
    return {liga: dict(zip(valores_por_liga[liga], resultado[liga], strict=True))
            for liga in valores_por_liga}


def imputar_valores(jogadores: list[dict]) -> list[dict]:
    """Estima o valor de quem nao tem cotacao, a partir dos MINUTOS jogados.

    Sem isto, jogador sem cotacao caia no piso e virava overall 40 e poucos -- inclusive
    quem jogou a temporada inteira. Medido na base real: 237 de 2.403 sem valor, e 38 deles
    com mais de 600 minutos. O pior caso tinha 2.218 minutos pelo Ceara e overall 45.

    Minutos sao evidencia de qualidade independente do preco: quem joga 2.200 minutos numa
    liga profissional nao e um 45. A estimativa casa o percentil de minutos do jogador com
    o percentil de valor do elenco, e aplica desconto -- ele joga como um cotado de X, mas
    o mercado nao o precificou.
    """
    com = [j for j in jogadores if (j.get("valor") or 0) > 0]
    sem = [j for j in jogadores if not (j.get("valor") or 0)]
    if not sem or len(com) < 4:
        return jogadores

    valores = np.sort([j["valor"] for j in com])
    minutos_todos = np.array([j.get("minutos") or 0 for j in jogadores], dtype=float)
    saida = []
    for j in jogadores:
        if (j.get("valor") or 0) > 0:
            saida.append(j)
            continue
        meus = j.get("minutos") or 0
        pct = float(np.mean(minutos_todos <= meus)) if minutos_todos.size else 0.5
        estimado = float(np.quantile(valores, np.clip(pct, 0.0, 1.0)))
        novo = dict(j)
        novo["valor"] = max(int(estimado * DESCONTO_SEM_COTACAO), VALOR_PISO)
        novo["valor_estimado"] = True
        saida.append(novo)
    return saida
