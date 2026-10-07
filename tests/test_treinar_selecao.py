"""O usuario treinando uma selecao (07/10/2026): convite, convocacao, onze, a partida
dela (na tela ao vivo, como a do clube) e o save que refaz tudo."""

from __future__ import annotations

import pytest

from fm import servidor
from fm.carreira import Carreira
from fm.selecoes import convocar, id_da_selecao
from fm.servidor import Jogo


def _com_o_brasil(seed: int = 3) -> Carreira:
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=seed)
    c.convite_selecao = "Brasil"            # o convite vem da reputacao; aqui, na mao
    assert c.executar({"tipo": "assumir_selecao", "pais": "Brasil"}).get("ok")
    return c


def _ate_jogar_pela_selecao(c: Carreira):
    while True:
        _, partida = c.avancar()
        if partida is not None and c.ultimo_compromisso[0] == "selecao":
            return partida


def test_so_assume_a_selecao_que_convidou():
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    c.convite_selecao = "Uruguai"
    assert "erro" in c.executar({"tipo": "assumir_selecao", "pais": "Brasil"})
    assert c.executar({"tipo": "assumir_selecao", "pais": "Uruguai"}).get("ok")
    assert c.selecao_do_usuario == "Uruguai" and c.convite_selecao is None
    assert c.executar({"tipo": "deixar_selecao"}).get("ok")
    assert c.selecao_do_usuario is None


def test_a_convocacao_tem_regras():
    c = _com_o_brasil()
    w = c.world
    argentino = next(p.id for p in w.players.values() if p.nationality == "Argentina")
    lista = convocar(w, "Brasil")
    assert "erro" in c.executar({"tipo": "convocar_selecao", "jogadores": lista[:-1] + [argentino]})
    sem_goleiro = [p for p in lista if w.players[p].position != "GK"]
    assert "erro" in c.executar({"tipo": "convocar_selecao", "jogadores": sem_goleiro})
    assert "erro" in c.executar({"tipo": "convocar_selecao", "jogadores": lista[:10]})
    assert c.executar({"tipo": "convocar_selecao", "jogadores": lista}).get("ok")
    assert "erro" in c.executar({"tipo": "escalar_selecao", "onze": [argentino] + lista[:10]})


def test_a_selecao_joga_com_quem_o_treinador_escolheu():
    c = _com_o_brasil()
    w = c.world
    # uma convocacao "alternativa": os 26 seguintes da lista do pais, sem os titulares
    todos = sorted((p for p in w.players.values()
                    if p.nationality == "Brasil" and p.club_id in w.clubs),
                   key=lambda p: -p.overall)
    goleiros = [p.id for p in todos if p.position == "GK"][3:6]
    linha = [p.id for p in todos if p.position != "GK"][15:35]
    lista = goleiros + linha
    assert c.executar({"tipo": "convocar_selecao", "jogadores": lista}).get("ok")
    onze = [goleiros[0]] + linha[:10]
    assert c.executar({"tipo": "escalar_selecao", "onze": onze,
                       "tatica": {"formacao": "4-4-2", "estilo": "ofensivo"}}).get("ok")
    partida = _ate_jogar_pela_selecao(c)
    sid = id_da_selecao("Brasil")
    meus = [p for p, t in partida.time_de.items() if t == sid]
    assert set(meus) <= set(lista), "jogou alguem que nao foi convocado"
    titulares = [p for p in meus if partida.entrada[p] == 0]
    assert set(titulares) == set(onze)
    assert c.jogos_da_selecao, "o jogo da selecao nao ficou registrado"


def test_a_partida_da_selecao_e_ao_vivo_como_a_do_clube():
    c = _com_o_brasil()
    jogo = Jogo(c)
    while True:
        r = servidor.partida_iniciar(jogo, {})
        while not r.get("fim"):
            r = servidor.partida_seguir(jogo, {})
        if c.ultimo_compromisso[0] == "selecao":
            break
    sid = id_da_selecao("Brasil")
    assert sid in (r["casa"]["id"], r["fora"]["id"])
    assert r[r["meu_lado"]]["nome"] == "Brasil"
    assert len(r["escalacao_casa"]) >= 11 and len(r["escalacao_fora"]) >= 11
    assert len(r["banco"]) == 12
    assert r["rodada"], "os outros jogos do dia aparecem na rodada ao vivo"
    pos = servidor.pos_jogo(jogo)
    assert pos["comp_id"] == "fifa:eliminatorias_conmebol"
    linhas = [x for x in servidor.calendario(jogo)["datas"] if x["tipo"] == "selecao"]
    assert linhas[0]["resultado"] is not None and linhas[0]["rival"]["nome"] != "Brasil"
    # depois do jogo o clube volta a ser o time do treinador
    servidor.partida_iniciar(jogo, {})
    assert c.time_em_campo in (c.clube_id, sid)


def test_o_save_refaz_os_jogos_da_selecao(tmp_path, monkeypatch):
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)

    # o convite tem de sair do mesmo caminho no jogo e no replay (fm.carreira._montar):
    # forca-lo na mao, como os outros testes fazem, o replay nao refaria
    def convidar(self):
        self.convite_selecao = None if self.selecao_do_usuario else "Brasil"
    monkeypatch.setattr(mod.Carreira, "convidar_para_selecao", convidar)
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    assert c.executar({"tipo": "assumir_selecao", "pais": "Brasil"}).get("ok")
    lista = convocar(c.world, "Brasil")[::-1]          # outra ordem, mesma gente
    c.executar({"tipo": "convocar_selecao", "jogadores": lista})
    _ate_jogar_pela_selecao(c)
    _ate_jogar_pela_selecao(c)
    c.salvar("sel")
    (tmp_path / "sel.ponto").unlink()                  # forca o replay
    volta = Carreira.carregar("sel")
    placar = lambda x: sorted((k, r.home, r.away, r.goals_home, r.goals_away)  # noqa: E731
                              for k, r in x.jogos_da_selecao.items())
    assert placar(volta) == placar(c) and len(placar(c)) == 2
    assert volta.selecao_do_usuario == "Brasil"
    assert volta.convocacao_do_usuario == lista


def test_o_convite_vem_pela_reputacao():
    """Reputacao baixa: so as menores chamam. Alta: as grandes."""
    from fm import tecnicos as tec
    from fm.selecoes import convocar_todas, mundo_das_selecoes, ranking
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Cruzeiro", seed=3)
    ordem = ranking(mundo_das_selecoes(c.world, convocar_todas(c.world)))
    eu = c.tecnicos[tec.USUARIO]
    vistos_baixa, vistos_alta = set(), set()
    for ano in range(2027, 2047):
        c.temporada = ano
        eu.reputacao = 30
        c.convidar_para_selecao()
        if c.convite_selecao:
            vistos_baixa.add(c.convite_selecao)
        eu.reputacao = 92
        c.convidar_para_selecao()
        if c.convite_selecao:
            vistos_alta.add(c.convite_selecao)
    assert vistos_baixa and vistos_alta
    assert all(ordem.index(p) > len(ordem) - 6 for p in vistos_baixa)
    assert all(ordem.index(p) < 3 for p in vistos_alta)


@pytest.mark.parametrize("pais", ["Brasil"])
def test_a_tela_da_selecao(pais):
    c = _com_o_brasil()
    d = servidor.telas.selecao_nacional(c, lambda cid: servidor._clube(c, cid))
    assert d["minha"]["pais"] == pais
    assert len(d["minha"]["convocados"]) == 26
    assert d["minha"]["proximo"]["competicao"] == "Eliminatórias Sul-Americanas"
    assert d["ranking"][0]["posicao"] == 1
