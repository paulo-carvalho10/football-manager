"""Moral do jogador e quimica do vestiario.

A moral existia no jogador desde o comeco e quase nada a movia: era sorteada na criacao do
mundo e ficava parada. Agora ela anda a cada jogo, e o que ela faz e o que o futebol faz:

- Vencer levanta, perder abate, goleada sofrida abala de verdade. Gol da confianca.
- O jogador que espera jogar (um dos 14 melhores do elenco) e fica no banco se frustra; o
  garoto do fundo do elenco nao se importa tanto. Quem passa muito tempo frustrado fica
  INSATISFEITO: pede para sair, nao renova e atrai propostas.
- A QUIMICA do vestiario e do clube: sobe com sequencia boa, cai com derrota, com gente
  insatisfeita e com muita contratacao de uma vez (na virada do ano).

O efeito no jogo e um bonus em pontos de overall, como o desgaste (fm.match.effective_
rating), com teto: e o que faz o time embalado embalar e o rebaixado desmoronar -- a
dinamica de colapso que faltava (o lanterna simulado terminava com ~30 pontos; o real, com
16 a 21). Modesto de proposito: o elenco continua decidindo.

Nada aqui sorteia: e conta sobre resultados, e o replay do save refaz igual.
"""

from __future__ import annotations

from collections import Counter

from fm.model import World

MORAL_NEUTRA = 70          # a media do mundo na criacao (fm.generate sorteia 60 a 85)
MORAL_MINIMA, MORAL_MAXIMA = 5, 99
QUIMICA_NEUTRA = 60
QUIMICA_MINIMA, QUIMICA_MAXIMA = 5, 99

# o resultado, para quem jogou; quem ficou de fora sente a metade
PELA_VITORIA, PELO_EMPATE, PELA_DERROTA = 4.0, 0.5, -4.0
GOLEADA = 3                # margem que conta como goleada
PELA_GOLEADA_FEITA, PELA_GOLEADA_SOFRIDA = 2.0, -4.0
POR_GOL = 3.0              # confianca do artilheiro, ate dois gols por jogo
# Jogar nao da moral por si: so evita a frustracao do banco. Com +1 por jogo os titulares
# de quase todo clube saturavam perto de 90, e o time que embalava primeiro chegava ao teto
# e empatava com o melhor elenco -- medido: o melhor elenco foi campeao 0 vezes em 16.
POR_JOGAR = 0.0
# Esperava jogar e nao jogou: pesa mais a cada jogo seguido no banco. Uma rodada nao e
# nada; uma duzia seguida (mes e meio no calendario real) deixa o jogador insatisfeito.
# Um peso fixo nao chegava la -- a moral volta ao normal rapido demais para uma
# frustracao constante acumular.
FRUSTRADO_NO_BANCO = -1.0
FRUSTRACAO_POR_JOGO_SEGUIDO = -0.8
FRUSTRACAO_MAXIMA = -10.0
NO_FUNDO_DO_ELENCO = -0.5
QUEM_ESPERA_JOGAR = 14     # os 14 melhores do elenco esperam minutos
# A moral lembra uns seis jogos: e a FASE, nao a temporada. Com 5% ela saturava.
VOLTA_AO_NORMAL = 0.15

INSATISFEITO = 35          # abaixo disto o jogador quer sair

# A quimica e lenta (anda a temporada inteira) e suave: e o clima, nao a fase.
QUIMICA_PELA_VITORIA, QUIMICA_PELA_DERROTA = 1.0, -1.0
QUIMICA_PELA_GOLEADA_SOFRIDA = -1.0
QUIMICA_POR_INSATISFEITO = -0.5
QUIMICA_VOLTA_AO_NORMAL = 0.04
QUIMICA_POR_CONTRATADO = -2.5      # na virada: elenco novo ainda nao se conhece
QUIMICA_TETO_DE_CONTRATADOS = 20.0

# o efeito no jogo, em pontos de overall
PESO_DA_MORAL = 0.08       # moral media 85 no onze: +1,2; 40: -2,4
PESO_DA_QUIMICA = 0.05     # quimica 90: +1,5; 30: -1,5
TETO_DO_BONUS = 4.0


def _limitar(v: float, lo: int, hi: int) -> int:
    return int(round(max(lo, min(hi, v))))


def quimica(world: World, clube: int) -> int:
    return world.quimica.get(clube, QUIMICA_NEUTRA)


def bonus(world: World, clube: int, onze: list[int] | None = None) -> float:
    """Quanto a moral do onze e a quimica do clube valem em pontos de overall."""
    ids = onze if onze is not None else [p.id for p in world.best_xi(clube)]
    morais = [world.players[i].morale for i in ids if i in world.players]
    m = sum(morais) / len(morais) if morais else MORAL_NEUTRA
    b = (PESO_DA_MORAL * (m - MORAL_NEUTRA)
         + PESO_DA_QUIMICA * (quimica(world, clube) - QUIMICA_NEUTRA))
    return max(-TETO_DO_BONUS, min(TETO_DO_BONUS, b))


def depois_do_jogo(world: World, clube: int, pro: int, contra: int,
                   jogaram: set[int], gols: Counter, fora_de_combate: set[int]) -> None:
    """A moral do elenco e a quimica do clube depois de um jogo dele.

    `jogaram`: quem entrou em campo; `gols`: {jogador: gols}; `fora_de_combate`: lesionado
    e suspenso -- esses nao se frustram por nao jogar.
    """
    if pro > contra:
        resultado = PELA_VITORIA + (PELA_GOLEADA_FEITA if pro - contra >= GOLEADA else 0.0)
    elif pro < contra:
        resultado = PELA_DERROTA + (PELA_GOLEADA_SOFRIDA if contra - pro >= GOLEADA else 0.0)
    else:
        resultado = PELO_EMPATE
    elenco = sorted(world.squad(clube), key=lambda p: -p.overall)
    esperam = {p.id for p in elenco[:QUEM_ESPERA_JOGAR]}
    for p in elenco:
        if p.id in jogaram:
            world.banco_seguido.pop(p.id, None)
            delta = resultado + POR_JOGAR + POR_GOL * min(gols.get(p.id, 0), 2)
        elif p.id in fora_de_combate:
            delta = resultado / 2
        elif p.id in esperam:
            seguidos = world.banco_seguido.get(p.id, 0) + 1
            world.banco_seguido[p.id] = seguidos
            delta = resultado / 2 + max(FRUSTRACAO_MAXIMA, FRUSTRADO_NO_BANCO
                                        + FRUSTRACAO_POR_JOGO_SEGUIDO * seguidos)
        else:
            delta = resultado / 2 + NO_FUNDO_DO_ELENCO
        m = p.morale + delta
        m += (MORAL_NEUTRA - m) * VOLTA_AO_NORMAL
        p.morale = _limitar(m, MORAL_MINIMA, MORAL_MAXIMA)

    q = float(quimica(world, clube))
    if pro > contra:
        q += QUIMICA_PELA_VITORIA
    elif pro < contra:
        q += QUIMICA_PELA_DERROTA + (QUIMICA_PELA_GOLEADA_SOFRIDA
                                     if contra - pro >= GOLEADA else 0.0)
    q += QUIMICA_POR_INSATISFEITO * sum(1 for p in elenco if p.morale < INSATISFEITO)
    q += (QUIMICA_NEUTRA - q) * QUIMICA_VOLTA_AO_NORMAL
    world.quimica[clube] = _limitar(q, QUIMICA_MINIMA, QUIMICA_MAXIMA)


def na_virada(world: World, contratados: Counter) -> None:
    """A pre-temporada: a moral volta boa parte do caminho ao normal e o elenco novo ainda
    nao se conhece -- muita contratacao de uma vez custa quimica."""
    world.banco_seguido.clear()
    for p in world.players.values():
        p.morale = _limitar(MORAL_NEUTRA + (p.morale - MORAL_NEUTRA) * 0.4,
                            MORAL_MINIMA, MORAL_MAXIMA)
    for clube in world.clubs:
        q = QUIMICA_NEUTRA + (quimica(world, clube) - QUIMICA_NEUTRA) * 0.7
        q += max(-QUIMICA_TETO_DE_CONTRATADOS, QUIMICA_POR_CONTRATADO * contratados.get(clube, 0))
        world.quimica[clube] = _limitar(q, QUIMICA_MINIMA, QUIMICA_MAXIMA)


def rotulo_da_moral(m: int) -> str:
    if m < INSATISFEITO:
        return "insatisfeito"
    if m < 55:
        return "abatido"
    if m < 78:
        return "normal"
    if m < 88:
        return "confiante"
    return "embalado"


def rotulo_da_quimica(q: int) -> str:
    if q < 35:
        return "rachado"
    if q < 50:
        return "instável"
    if q < 70:
        return "normal"
    if q < 85:
        return "unido"
    return "fechado com o técnico"
