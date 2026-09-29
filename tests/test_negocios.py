"""O balcao do usuario: comprar, renovar, vender por proposta, e o contrato que acaba."""

from fm import negocios as neg
from fm.carreira import Carreira


def _nova(seed=3, clube="Santos"):
    return Carreira.nova(["brasil_real", "brasil_b_real"], clube, seed=seed)


def _alvo(c, nome_clube="Cruzeiro"):
    cid = next(k for k, v in c.world.clubs.items() if v.name == nome_clube)
    return max(c.world.squad(cid), key=lambda p: p.overall)


def test_a_resposta_do_vendedor_depende_so_da_oferta():
    c = _nova()
    p = _alvo(c)
    pedido = neg.pedido_do_vendedor(c, p)
    assert neg.avaliar_oferta(c, p.id, pedido)["resultado"] == "aceita"
    assert neg.avaliar_oferta(c, p.id, int(pedido * 0.9))["resultado"] == "contraproposta"
    assert neg.avaliar_oferta(c, p.id, int(pedido * 0.5))["resultado"] == "recusada"
    # deterministico: perguntar de novo da a mesma coisa
    assert neg.pedido_do_vendedor(c, p) == pedido


def test_comprar_move_jogador_dinheiro_e_salario():
    c = _nova()
    p = _alvo(c, "Juventude")
    pedido = neg.pedido_do_vendedor(c, p)
    salario = neg.salario_pretendido(c, p)
    caixa, dono = c.clube.balance, p.club_id
    caixa_dono = c.world.clubs[dono].balance
    r = c.executar({"tipo": "compra", "jogador": p.id, "preco": pedido,
                    "salario": salario, "anos": 3})
    assert r.get("ok"), r
    assert p.club_id == c.clube_id and p.id in c.clube.player_ids
    assert c.clube.balance == caixa - pedido
    assert c.world.clubs[dono].balance == caixa_dono + pedido
    assert p.wage == salario and p.contract_until == c.temporada + 3


def test_salario_baixo_e_recusado_com_dica():
    c = _nova()
    p = _alvo(c, "Juventude")
    r = neg.avaliar_contrato(c, p.id, int(neg.salario_pretendido(c, p) * 0.7), 3)
    assert r["resultado"] == "recusada" and r["dica"] == neg.salario_pretendido(c, p)


def test_titular_de_time_muito_mais_forte_nao_desce():
    c = _nova(clube="Chapecoense")
    p = _alvo(c, "Palmeiras")
    r = neg.avaliar_contrato(c, p.id, p.wage * 10, 5)
    assert r["resultado"] == "recusada" and r.get("definitiva")


def test_quem_quer_sair_nao_renova_por_dinheiro_nenhum():
    c = _nova()
    p = max(c.world.squad(c.clube_id), key=lambda x: x.overall)
    p.morale = 10                                   # insatisfeito
    assert neg.interesse_em_renovar(c, p)["nivel"] == "baixo"
    r = c.executar({"tipo": "renovacao", "jogador": p.id, "salario": p.wage * 50, "anos": 3})
    assert "erro" in r


def test_proposta_recebida_aceita_vende_o_jogador():
    c = _nova()
    while not c.propostas_pendentes():
        c.avancar()
    prop = c.propostas_pendentes()[0]
    caixa = c.clube.balance
    r = c.executar({"tipo": "aceitar", "proposta": prop.id})
    assert r.get("ok"), r
    assert c.world.players[prop.jogador].club_id == prop.clube
    assert c.clube.balance == caixa + prop.valor
    assert prop.id and prop.status == "aceita"
    assert c.movimentos[-1]["sentido"] == "saida"


def test_contraproposta_acima_do_teto_vira_nova_oferta_uma_vez_so():
    c = _nova()
    while not c.propostas_pendentes():
        c.avancar()
    prop = c.propostas_pendentes()[0]
    r = c.executar({"tipo": "contraproposta", "proposta": prop.id,
                    "valor": int(prop.maximo * 1.1)})
    assert r["resultado"] == "nova_proposta" and prop.valor == prop.maximo
    r = c.executar({"tipo": "contraproposta", "proposta": prop.id,
                    "valor": int(prop.maximo * 1.1)})
    assert r["resultado"] == "recusada" and prop.status == "recusada"


def test_proposta_sem_resposta_caduca_na_data_seguinte():
    c = _nova()
    while not c.propostas_pendentes():
        c.avancar()
    prop = c.propostas_pendentes()[0]
    c.avancar()
    assert prop.status == "expirada"


def test_o_save_refaz_compra_renovacao_e_venda(tmp_path, monkeypatch):
    """REGRA DO PROJETO: o save guarda decisoes. Negocio feito no meio do ano tem de
    voltar no mesmo ponto, senao a carreira carregada diverge da jogada."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = _nova(seed=11)
    for _ in range(2):
        c.avancar()
    p = _alvo(c, "Juventude")
    c.executar({"tipo": "compra", "jogador": p.id, "preco": neg.pedido_do_vendedor(c, p),
                "salario": neg.salario_pretendido(c, p), "anos": 2})
    renovado = next(x for x in c.world.squad(c.clube_id)
                    if neg.interesse_em_renovar(c, x)["nivel"] != "baixo")
    pedido = neg.interesse_em_renovar(c, renovado)["pretendido"]
    assert c.executar({"tipo": "renovacao", "jogador": renovado.id, "salario": pedido,
                       "anos": 2}).get("ok")
    while not c.propostas_pendentes():
        c.avancar()
    venda = c.propostas_pendentes()[0]
    c.executar({"tipo": "aceitar", "proposta": venda.id})
    for _ in range(3):
        c.avancar()
    c.salvar("negocios")

    d = Carreira.carregar("negocios")
    assert sorted(d.clube.player_ids) == sorted(c.clube.player_ids)
    assert d.clube.balance == c.clube.balance
    assert d.world.players[renovado.id].contract_until == renovado.contract_until
    assert [(r.home, r.away, r.goals_home, r.goals_away) for r in d.jogos()] == \
           [(r.home, r.away, r.goals_home, r.goals_away) for r in c.jogos()]


def test_contrato_vencido_sai_de_graca_e_vira_agente_livre():
    c = _nova()
    p = min(c.world.squad(c.clube_id), key=lambda x: x.overall)
    p.contract_until = c.temporada                     # acaba neste ano
    while not c.acabou:
        c.avancar()
    r = c.virar_o_ano()
    assert p.id in [x["jogador"] for x in r["contratos_encerrados"]]
    assert c.world.players[p.id].club_id is None
    assert p.id not in c.clube.player_ids
