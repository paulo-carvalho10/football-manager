"""Emprestimo: pegar um reserva de outro clube, emprestar um garoto, e a volta no fim do ano."""

from __future__ import annotations

from fm import negocios as neg
from fm.carreira import Carreira


def _nova(seed=3):
    return Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=seed)


def _clube(c, nome):
    return next(k for k, v in c.world.clubs.items() if v.name == nome)


def _reserva(c, nome="Palmeiras"):
    cid = _clube(c, nome)
    onze = {p.id for p in c.world.best_xi(cid)}
    return max((p for p in c.world.squad(cid) if p.id not in onze), key=lambda p: p.overall)


def test_titular_nao_e_emprestado_e_reserva_e():
    c = _nova()
    cid = _clube(c, "Palmeiras")
    titular = max(c.world.best_xi(cid), key=lambda p: p.overall)
    assert neg.avaliar_emprestimo(c, titular.id)["resultado"] == "recusada"
    r = neg.avaliar_emprestimo(c, _reserva(c).id)
    assert r["resultado"] == "aceita"
    assert r["taxa"] >= 0 and r["ate"] == c.temporada


def test_garoto_vem_sem_taxa():
    c = _nova()
    for p in c.world.players.values():
        if p.club_id in c.world.clubs and p.club_id != c.clube_id \
                and p.age(c.temporada) <= neg.IDADE_SEM_TAXA:
            assert neg.taxa_de_emprestimo(c, p) == 0
            break


def test_pegar_emprestado_move_jogador_taxa_e_salario_mas_nao_o_dono():
    c = _nova()
    p = _reserva(c)
    dono, taxa = p.club_id, neg.avaliar_emprestimo(c, p.id)["taxa"]
    caixa, folha = c.clube.balance, neg.folha_mensal(c.world, c.clube_id)
    r = c.executar({"tipo": "emprestimo_entrada", "jogador": p.id})
    assert r.get("ok"), r
    assert p.club_id == c.clube_id and p.loan_from == dono
    assert c.clube.balance == caixa - taxa
    assert neg.folha_mensal(c.world, c.clube_id) == folha + p.wage
    # nao e dele: nem renova, nem vende
    assert "erro" in c.executar({"tipo": "renovacao", "jogador": p.id,
                                 "salario": p.wage, "anos": 2})


def test_emprestar_vai_para_onde_ele_joga_e_volta_na_virada():
    c = _nova()
    garoto = min(c.world.squad(c.clube_id), key=lambda p: p.overall)
    medio = sorted(c.world.squad(c.clube_id), key=lambda p: p.overall)[len(c.clube.player_ids) // 2]
    alvos = neg.interessados_no_emprestimo(c, medio.id)
    assert alvos, "ninguem quer um jogador mediano da Serie A?"
    for k in alvos:
        assert neg._jogaria(c.world, medio, k)
    assert c.executar({"tipo": "emprestimo_saida", "jogador": medio.id,
                       "clube": alvos[0]}).get("ok")
    assert medio.club_id == alvos[0] and medio.loan_from == c.clube_id
    assert medio.id not in c.clube.player_ids
    # o clube que nao esta na lista e recusado
    outro = next(k for k in c.world.clubs if k not in alvos and k != c.clube_id)
    r = c.executar({"tipo": "emprestimo_saida", "jogador": garoto.id, "clube": outro})
    assert "erro" in r
    while not c.acabou:
        c.avancar()
    resumo = c.virar_o_ano()
    assert medio.club_id == c.clube_id and medio.loan_from is None \
        or medio.id not in c.world.players or medio.club_id is None   # aposentou ou saiu
    assert any(v["jogador"] == medio.id for v in resumo["emprestimos_encerrados"])


def test_o_save_refaz_os_emprestimos(tmp_path, monkeypatch):
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = _nova(seed=11)
    c.avancar()
    chega = _reserva(c, "Flamengo")
    assert c.executar({"tipo": "emprestimo_entrada", "jogador": chega.id}).get("ok")
    c.avancar()
    sai = sorted(c.world.squad(c.clube_id), key=lambda p: p.overall)[len(c.clube.player_ids) // 2]
    alvo = neg.interessados_no_emprestimo(c, sai.id)[0]
    assert c.executar({"tipo": "emprestimo_saida", "jogador": sai.id, "clube": alvo}).get("ok")
    for _ in range(3):
        c.avancar()
    c.salvar("emprestimos")
    d = Carreira.carregar("emprestimos")
    assert sorted(d.clube.player_ids) == sorted(c.clube.player_ids)
    assert d.world.players[sai.id].club_id == alvo
    assert d.world.players[chega.id].loan_from == chega.loan_from
    assert d.clube.balance == c.clube.balance
