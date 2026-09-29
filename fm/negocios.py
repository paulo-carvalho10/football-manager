"""Negocios do usuario: comprar, renovar, receber proposta, e o fim de contrato.

A janela automatica (fm.mercado) continua sendo como a IA mexe nos elencos na virada do
ano. Este modulo e o balcao do USUARIO, a qualquer momento da temporada: ele oferece, o
clube vendedor responde; ele oferece salario, o jogador responde; um clube de fora oferece,
ele responde.

Tudo aqui e DETERMINISTICO. A mesma proposta, no mesmo dia, recebe sempre a mesma
resposta -- o ruido de cada preco sai de um hash da semente com o jogador e o ano, nunca de
um sorteio corrente. Sem isso o save nao conseguiria refazer a carreira: ele guarda so as
decisoes do usuario e refaz o resto.

Simplicidade de proposito (o brief pede "Brasfoot moderno"): um preco, um salario, uma
duracao. Nada de clausula, luva ou porcentagem de revenda.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from fm.mercado import DESCIDA_TOLERADA, ELENCO_MINIMO_PARA_VENDER, preco
from fm.model import World
from fm.temporada import SALARIO_SOBRE_VALOR

# o quanto da receita anual a diretoria deixa ir para salario. Acima disso ela veta.
FRACAO_DA_RECEITA_PARA_FOLHA = 0.60
ELENCO_MAXIMO = 40
ELENCO_MINIMO = 16            # o usuario nao vende abaixo disso: nao da para escalar 11
FAIXA_DE_CONTRAPROPOSTA = 0.85  # oferta entre 85% e 100% do pedido: o clube contrapropoe
RUIDO_DE_PRECO = 0.08         # cada clube pede um pouco diferente pelo mesmo jogador
TOLERANCIA_DE_SALARIO = 0.97  # o jogador aceita ate 3% abaixo do que pediu
PASSO = 50_000                # os valores anunciados sao redondos

# Premio por tirar um TITULAR do clube dono. O PREMIO_POR_TITULAR do mercado (1.45) e o da
# IA arrancando titular de outro patamar; no balcao do usuario ele fazia o Kaio Jorge, de
# valor 25M, custar 57M.
PREMIO_DO_TITULAR = 1.15
# e o que um clube de fora paga a mais para levar um titular do usuario
PREMIO_PARA_LEVAR_TITULAR = 1.25

# Propostas recebidas: uma a cada ~10 datas, perto de sete por temporada. Com 0.07 uma
# temporada de teste passou 40 datas sem nenhuma.
CHANCE_DE_PROPOSTA_POR_DATA = 0.10
FOLGA_DO_COMPRADOR = (1.08, 1.40)   # quanto acima da oferta o comprador aceita ir


def _ruido(seed: int, *chaves: int) -> float:
    """Numero em [-1, 1] fixo para a combinacao -- o mesmo toda vez que for pedido."""
    return float(np.random.default_rng([seed, *chaves]).uniform(-1.0, 1.0))


def _redondo(valor: float) -> int:
    return int(round(valor / PASSO) * PASSO)


def _titular(world: World, p) -> bool:
    if p.club_id not in world.clubs:
        return False
    return p.id in {x.id for x in world.best_xi(p.club_id)}


# ---------------------------------------------------------------- dinheiro do usuario

def folha_mensal(world: World, clube_id: int) -> int:
    return sum(world.players[i].wage for i in world.clubs[clube_id].player_ids
               if i in world.players)


def limite_da_folha(c) -> int:
    """Teto mensal de salarios que a diretoria aceita: uma fracao da receita do ano."""
    from fm.config import load_league
    from fm.financas import receita_anual
    tier = int(load_league(c.liga).get("tier", 1))
    receita = receita_anual(c.world, c.clube_id, tier, c.valor_de_elenco.get(c.clube_id))
    return int(receita * FRACAO_DA_RECEITA_PARA_FOLHA / 12)


def resumo_do_caixa(c) -> dict:
    return {"caixa": c.clube.balance, "folha": folha_mensal(c.world, c.clube_id),
            "limite_da_folha": limite_da_folha(c),
            "elenco": len(c.world.clubs[c.clube_id].player_ids)}


# ---------------------------------------------------------------- comprar

def pedido_do_vendedor(c, p) -> int:
    """Quanto o dono pede. Base: o preco da janela automatica; titular custa mais."""
    base = preco(c.world, p, c.temporada)
    if _titular(c.world, p):
        base *= PREMIO_DO_TITULAR
    base *= 1 + RUIDO_DE_PRECO * _ruido(c.seed, p.id, c.temporada, 1)
    return max(PASSO, _redondo(base))


def avaliar_oferta(c, pid: int, valor: int) -> dict:
    """A resposta do clube dono a uma oferta do usuario. Nao muda nada no mundo."""
    p = c.world.players.get(pid)
    if p is None:
        return {"resultado": "erro", "mensagem": "jogador nao existe"}
    if p.club_id == c.clube_id:
        return {"resultado": "erro", "mensagem": "ele ja e do seu clube"}
    if p.club_id not in c.world.clubs:
        return {"resultado": "aceita", "valor": 0, "livre": True,
                "mensagem": f"{p.name} esta sem contrato: nao ha clube para negociar."}
    dono = c.world.clubs[p.club_id]
    if len(dono.player_ids) <= ELENCO_MINIMO_PARA_VENDER:
        return {"resultado": "recusada", "valor": None,
                "mensagem": f"O {dono.name} nao pretende vender: o elenco ja esta curto."}
    pedido = pedido_do_vendedor(c, p)
    if valor >= pedido:
        return {"resultado": "aceita", "valor": int(valor),
                "mensagem": f"O {dono.name} aceitou sua proposta de R$ {int(valor):,} por "
                            f"{p.name}.".replace(",", ".")}
    if valor >= pedido * FAIXA_DE_CONTRAPROPOSTA:
        return {"resultado": "contraproposta", "valor": pedido,
                "mensagem": f"O {dono.name} aceita negociar por R$ {pedido:,}."
                            .replace(",", ".")}
    return {"resultado": "recusada", "valor": None, "dica": _redondo(pedido * 1.02),
            "mensagem": f"O {dono.name} considera sua proposta abaixo do valor esperado."}


def salario_pretendido(c, p, destino: int | None = None) -> int:
    """O que o jogador pede por mes. Parte do salario justo pelo valor dele; clube de
    menos prestigio que o atual paga um adicional para convence-lo."""
    destino = destino if destino is not None else c.clube_id
    justo = p.market_value / SALARIO_SOBRE_VALOR
    base = max(p.wage * 1.10, justo)
    if p.club_id in c.world.clubs and destino in c.world.clubs:
        dif = c.world.clubs[p.club_id].reputation - c.world.clubs[destino].reputation
        base *= 1 + max(-0.10, min(0.35, dif / 100))
    base *= 1 + 0.05 * _ruido(c.seed, p.id, c.temporada, 2)
    return max(1_000, int(round(base / 1_000) * 1_000))


def recusa_por_ambicao(c, p) -> str | None:
    """Titular nao desce de patamar: nenhum salario compensa ir para um time bem pior."""
    if p.club_id not in c.world.clubs or not _titular(c.world, p):
        return None
    origem = c.world.team_rating(p.club_id)
    destino = c.world.team_rating(c.clube_id)
    if destino + DESCIDA_TOLERADA * 1.5 < origem:
        return (f"{p.name} prefere continuar no {c.world.clubs[p.club_id].name}: "
                "e titular num time bem mais forte.")
    return None


def avaliar_contrato(c, pid: int, salario: int, anos: int) -> dict:
    """A resposta do jogador a uma oferta de salario (contratacao)."""
    p = c.world.players[pid]
    if not 1 <= anos <= 5:
        return {"resultado": "erro", "mensagem": "contrato de 1 a 5 anos"}
    motivo = recusa_por_ambicao(c, p)
    if motivo:
        return {"resultado": "recusada", "mensagem": motivo, "definitiva": True}
    pretendido = salario_pretendido(c, p)
    if salario >= pretendido * TOLERANCIA_DE_SALARIO:
        return {"resultado": "aceita", "mensagem": f"{p.name} aceitou os termos."}
    return {"resultado": "recusada", "dica": pretendido,
            "mensagem": "O jogador considera o salario oferecido abaixo de suas expectativas."}


# ---------------------------------------------------------------- renovar

def interesse_em_renovar(c, p) -> dict:
    """alto / medio / baixo, com o motivo e o salario desejado. "baixo" nao renova:
    nao adianta subir o salario sem fim -- e o que da historia ao save."""
    justo = p.market_value / SALARIO_SOBRE_VALOR
    idade = p.age(c.temporada)
    nivel_do_time = c.world.team_rating(c.clube_id)
    titular = _titular(c.world, p)
    if (p.overall >= nivel_do_time + 8 and idade <= 29) or p.morale < 35:
        return {"nivel": "baixo", "motivo": "Deseja buscar novos desafios.",
                "pretendido": None}
    if p.wage < justo * 0.85 or (not titular and idade < 30):
        motivo = ("Gostaria de receber um salario maior." if p.wage < justo * 0.85
                  else "Quer mais minutos em campo.")
        pedido = max(p.wage * 1.15, justo * 1.10)
        return {"nivel": "medio", "motivo": motivo,
                "pretendido": int(round(pedido / 1_000) * 1_000)}
    pedido = max(p.wage * 1.05, justo)
    return {"nivel": "alto", "motivo": "Esta satisfeito no clube.",
            "pretendido": int(round(pedido / 1_000) * 1_000)}


def avaliar_renovacao(c, pid: int, salario: int, anos: int) -> dict:
    p = c.world.players[pid]
    if p.club_id != c.clube_id:
        return {"resultado": "erro", "mensagem": "ele nao e do seu clube"}
    if not 1 <= anos <= 4:
        return {"resultado": "erro", "mensagem": "renovacao de 1 a 4 anos"}
    interesse = interesse_em_renovar(c, p)
    if interesse["nivel"] == "baixo":
        return {"resultado": "recusada", "definitiva": True,
                "mensagem": f"{p.name} nao deseja renovar seu contrato neste momento."}
    if salario >= interesse["pretendido"] * TOLERANCIA_DE_SALARIO:
        return {"resultado": "aceita", "mensagem": f"{p.name} renovou."}
    return {"resultado": "recusada", "dica": interesse["pretendido"],
            "mensagem": "Salario abaixo do esperado."}


# ---------------------------------------------------------------- executar (muda o mundo)

def transferir(world: World, pid: int, para: int | None, preco_: int, salario: int,
               ate: int) -> None:
    """Move o jogador e o dinheiro. `para` None = fica sem clube."""
    p = world.players[pid]
    de = p.club_id
    if de in world.clubs:
        world.clubs[de].player_ids.remove(pid)
        world.clubs[de].balance += preco_
    if para is not None:
        world.clubs[para].player_ids.append(pid)
        world.clubs[para].balance -= preco_
    p.club_id = para
    p.wage = int(salario)
    p.contract_until = int(ate)


# ---------------------------------------------------------------- propostas recebidas

@dataclass(slots=True)
class Proposta:
    id: str
    jogador: int
    clube: int
    valor: int
    maximo: int                 # ate onde o comprador vai. Nunca aparece na tela.
    temporada: int
    data: int
    status: str = "pendente"    # pendente, aceita, recusada, expirada
    contra_usada: bool = False  # o comprador so melhora a oferta uma vez

    def para_dict(self) -> dict:
        return asdict(self)


def gerar_propostas(c, rng: np.random.Generator) -> list[Proposta]:
    """Um clube de fora oferece por um jogador do usuario. Quem compra: um clube que pode
    pagar e onde ele seria titular, ou um de outro patamar. Quanto: valor de mercado com
    premio de titular, mais uma folga que so o comprador conhece."""
    if rng.random() >= CHANCE_DE_PROPOSTA_POR_DATA:
        return []
    meus = [p for p in c.world.squad(c.clube_id) if p.market_value > 0]
    if len(meus) <= ELENCO_MINIMO:
        return []
    pesos = np.array([p.market_value ** 0.7 for p in meus], dtype=float)
    alvo = meus[int(rng.choice(len(meus), p=pesos / pesos.sum()))]
    base = alvo.market_value * (PREMIO_PARA_LEVAR_TITULAR if _titular(c.world, alvo) else 1.0)
    nivel = c.world.team_rating(c.clube_id)
    candidatos = [k for k in c.world.clubs.values()
                  if k.id != c.clube_id and k.balance >= base
                  and c.world.team_rating(k.id) >= nivel - 2]
    if not candidatos:
        return []
    comprador = candidatos[int(rng.integers(len(candidatos)))]
    valor = _redondo(base * rng.uniform(0.90, 1.15))
    maximo = _redondo(valor * rng.uniform(*FOLGA_DO_COMPRADOR))
    return [Proposta(id=f"{c.temporada}:{c.data}:{alvo.id}", jogador=alvo.id,
                     clube=comprador.id, valor=valor, maximo=maximo,
                     temporada=c.temporada, data=c.data)]


def responder_contraproposta(prop: Proposta, exigido: int) -> dict:
    """O comprador responde a exigencia do usuario: aceita, sobe uma vez, ou desiste."""
    if exigido <= prop.maximo:
        return {"resultado": "aceita", "valor": int(exigido)}
    if not prop.contra_usada and exigido <= prop.maximo * 1.25:
        return {"resultado": "nova_proposta", "valor": prop.maximo}
    return {"resultado": "recusada", "valor": None}


# ---------------------------------------------------------------- fim de contrato

IDADE_QUE_A_IA_NAO_RENOVA = 34


def vencer_contratos(world: World, temporada_nova: int, clube_usuario: int,
                     rng: np.random.Generator) -> list[dict]:
    """Na virada: contrato vencido acaba. A IA renova quase todos (o veterano de 34 ou mais
    sai); do usuario sai quem ele nao renovou. Quem sai fica SEM CLUBE, disponivel no
    mercado; quem passar um ano sem clube se aposenta na virada seguinte."""
    saidas: list[dict] = []
    for p in list(world.players.values()):
        if p.club_id is None:
            continue
        if p.contract_until >= temporada_nova:
            continue
        do_usuario = p.club_id == clube_usuario
        if not do_usuario and p.age(temporada_nova) < IDADE_QUE_A_IA_NAO_RENOVA:
            p.contract_until = temporada_nova + int(rng.integers(1, 4))
            continue
        clube = world.clubs.get(p.club_id)
        if clube is not None and len(clube.player_ids) <= ELENCO_MINIMO and not do_usuario:
            p.contract_until = temporada_nova + 1       # nao desmonta um elenco curto
            continue
        saidas.append({"jogador": p.id, "nome": p.name, "clube": p.club_id,
                       "do_usuario": do_usuario})
        if clube is not None:
            clube.player_ids.remove(p.id)
        p.club_id = None
    return saidas


def livres_que_se_aposentam(world: World, temporada_nova: int) -> list[int]:
    """Quem ja estava sem clube desde a virada anterior sai do jogo."""
    saem = [p.id for p in world.players.values()
            if p.club_id is None and p.contract_until < temporada_nova - 1]
    for pid in saem:
        del world.players[pid]
    return saem
