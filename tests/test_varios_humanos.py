"""Online, etapa 2: varios tecnicos humanos na mesma carreira, no mesmo computador.

Cada humano tem o seu clube, as suas decisoes, propostas, convites e diretoria; a partida
de cada um sai do motor de eventos com o que ELE decidiu. So o ativo tem a tela ao vivo;
os outros jogam com as instrucoes que deixaram. O save guarda as decisoes de todos, e o
replay refaz o mesmo mundo seja quem for que estava com o controle em cada data.
"""

from __future__ import annotations

import re
import threading

import numpy as np
import pytest

from fm import tecnicos as tec
from fm.carreira import Carreira
from fm.tatica import Tatica

LIGAS = ["brasil_real", "brasil_b_real"]


def _dois(seed: int = 8) -> Carreira:
    return Carreira.nova(LIGAS, "Santos", seed=seed, outros=["Palmeiras"],
                         treinadores=["Ana", "Beto"])


def _foto(c):
    w = c.world
    return (c.temporada, c.data,
            [h.clube_id for h in c.humanos],
            sorted((r.home, r.away, r.goals_home, r.goals_away) for n in c.ligas
                   for r in c.jogos(n)),
            sorted((p.id, p.club_id, p.overall, p.morale, p.condition)
                   for p in w.players.values()),
            sorted((k, cl.balance, cl.reputation) for k, cl in w.clubs.items()),
            [sorted((k, r.goals_home, r.goals_away) for k, r in h.jogos_do_usuario.items())
             for h in c.humanos])


def _ate_a_liga(c, **kw):
    while not c.acabou and c.compromisso[0] != "liga":
        c.avancar()
    return c.avancar(**kw)


def test_cada_humano_tem_o_seu_clube_e_o_seu_tecnico():
    c = _dois()
    santos, palmeiras = (h.clube_id for h in c.humanos)
    assert c.world.clubs[santos].name == "Santos"
    assert c.world.clubs[palmeiras].name == "Palmeiras"
    assert [h.tecnico_id for h in c.humanos] == [0, 1]
    assert c.tecnicos[0].clube == santos and c.tecnicos[0].nome == "Ana"
    assert c.tecnicos[1].clube == palmeiras and c.tecnicos[1].nome == "Beto"
    assert [t.id for t in c.tecnicos.values() if t.usuario] == [0, 1]
    # cada clube tem um tecnico so: o da IA do Palmeiras nao foi gerado
    assert sum(1 for t in c.tecnicos.values() if t.clube == palmeiras) == 1
    # os atalhos sao do ativo
    assert c.clube_id == santos
    c.ativo = 1
    assert c.clube_id == palmeiras and c.treinador == "Beto"
    assert c.clubes_humanos() == {santos, palmeiras}


def test_nao_cabem_dois_no_mesmo_clube_nem_mais_de_oito():
    with pytest.raises(ValueError, match="dois tecnicos"):
        Carreira.nova(LIGAS, "Santos", seed=8, outros=["santos"])
    with pytest.raises(ValueError, match="no maximo"):
        Carreira.nova(LIGAS, "Santos", seed=8, outros=["x"] * 8)


def test_a_vez_e_da_thread():
    """Ao jogar a data, a carreira faz a conta como cada humano. A tela le a carreira de
    outra thread enquanto a partida ao vivo esta pausada -- e tem de ver o ativo."""
    c = _dois()
    vistos = []
    with c._como(1):
        assert c.clube_id == c.humanos[1].clube_id
        t = threading.Thread(target=lambda: vistos.append(c.clube_id))
        t.start()
        t.join()
    assert vistos == [c.humanos[0].clube_id]
    assert c.clube_id == c.humanos[0].clube_id


def test_a_partida_de_cada_humano_usa_as_decisoes_dele():
    c = _dois()
    c.ativo = 1
    reservas = sorted(c.world.squad(c.clube_id), key=lambda p: p.overall)
    goleiro = next(p for p in reservas if p.position == "GK")
    linha = [p for p in reservas if p.position != "GK"][:10]
    onze = [goleiro.id] + [p.id for p in linha]
    c.escalar(onze, Tatica(formacao="4-4-2", estilo="defensivo"))
    c.ativo = 0
    _ate_a_liga(c)
    ana, beto = c.humanos
    assert ana.partida_da_data is not None and beto.partida_da_data is not None
    assert c.data - 1 in ana.jogos_do_usuario and c.data - 1 in beto.jogos_do_usuario
    entrou = set(beto.partida_da_data.entrada)
    assert set(onze) <= entrou, "o Palmeiras jogou sem o onze que o tecnico dele escolheu"
    # a tatica do Beto continua valendo nos proximos jogos dele, e so nos dele
    c.ativo = 1
    assert c.tatica_atual().formacao == "4-4-2"
    c.ativo = 0
    assert c.tatica_atual().formacao == "4-3-3"


def test_humano_contra_humano_e_uma_partida_so():
    c = _dois()
    for _ in range(80):
        _ate_a_liga(c)
        ana, beto = c.humanos
        if ana.partida_da_data is not None and ana.partida_da_data is beto.partida_da_data:
            break
    else:
        pytest.fail("Santos e Palmeiras nao se enfrentaram")
    p = ana.partida_da_data
    assert {p.casa, p.fora} == {ana.clube_id, beto.clube_id}
    assert ana.jogos_do_usuario[c.data - 1] is beto.jogos_do_usuario[c.data - 1]
    # o jogo entrou uma vez so na tabela
    duplicados = [r for r in c.jogos("brasil_real")
                  if {r.home, r.away} == {ana.clube_id, beto.clube_id}]
    assert len(duplicados) == len({(r.home, r.away) for r in duplicados})


def test_so_o_ativo_tem_a_tela_ao_vivo():
    c = _dois()
    c.ativo = 1
    chamadas = []

    def trocas(partida, minuto):
        chamadas.append(partida)
        return []

    _ate_a_liga(c, substituicoes=trocas)
    assert chamadas, "a partida do ativo nao passou pela tela"
    assert all(p is c.humanos[1].partida_da_data for p in chamadas)


def test_o_save_refaz_o_mundo_seja_quem_for_que_estava_com_o_controle(tmp_path,
                                                                       monkeypatch):
    """O controle passa de mao em mao, os dois decidem e um deles pede demissao e troca de
    clube. O save guarda tudo isso e o replay -- que nao sabe quem estava com o controle
    em cada data -- refaz o mesmo mundo."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = _dois()
    for k in range(14):
        c.ativo = k % 2
        c.escalar(c.escalacao_atual(),
                  Tatica(estilo="ofensivo" if k % 2 else "defensivo"))
        if k == 7:
            assert c.executar({"tipo": "pedir_demissao"}).get("ok")
            assert c.humanos[1].convites
        if k == 9:
            assert c.ativo == 1
            assert c.executar({"tipo": "assumir", "clube": c.convites[0]}).get("ok")
        c.avancar()
    assert any(a.get("humano") == 1 for a in c.acoes)
    assert c.humanos[1].clube_id != c.humanos[1].clube_inicial
    c.salvar("dois")
    (tmp_path / "dois.ponto").unlink()

    for ativo in (0, 1):
        texto = (tmp_path / "dois.json").read_text(encoding="utf-8")
        (tmp_path / "dois.json").write_text(
            re.sub(r'"ativo": \d', f'"ativo": {ativo}', texto), encoding="utf-8")
        d = Carreira.carregar("dois")
        assert d.ativo == ativo
        assert _foto(d) == _foto(c)
        assert d.acoes == c.acoes
        assert [h.decisoes for h in d.humanos] == [h.decisoes for h in c.humanos]


def test_o_retrato_vale_com_dois_humanos(tmp_path, monkeypatch):
    """Carregar pelo retrato do comeco do ano da o mesmo mundo, com as decisoes do ano em
    curso de cada humano vindas do save."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = _dois()
    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    c.ativo = 1
    c.escalar(c.escalacao_atual(), Tatica(formacao="3-5-2"))
    for _ in range(5):
        c.avancar()
    c.salvar("r")
    (tmp_path / "r.ponto").unlink()
    chamadas = []
    original = mod.build_world
    monkeypatch.setattr(mod, "build_world", lambda *a, **k: chamadas.append(1) or original(*a, **k))
    d = Carreira.carregar("r")
    assert not chamadas, "com retrato valido o mundo nao e montado do zero"
    assert _foto(d) == _foto(c)
    assert d.humanos[1].decisoes == c.humanos[1].decisoes


def test_proposta_compra_e_convite_nunca_envolvem_o_clube_de_outro_humano():
    c = _dois()
    santos, palmeiras = (h.clube_id for h in c.humanos)
    # a IA nao faz proposta em nome do Palmeiras, e o Santos nao compra do Palmeiras
    for _ in range(40):
        c.avancar()
    for h in c.humanos:
        assert all(p.clube not in (santos, palmeiras) for p in h.propostas)
    craque = max(c.world.squad(palmeiras), key=lambda p: p.overall)
    r = c.executar({"tipo": "compra", "jogador": craque.id, "preco": 10**9,
                    "salario": craque.wage * 3, "anos": 3})
    assert "erro" in r and "humano" in r["erro"]
    # o clube de outro humano nao chama ninguem
    candidatos = [palmeiras] + [k for k in c.world.clubs if k not in (santos, palmeiras)][:5]
    c.tecnicos[0].reputacao = 99
    for rng_seed in range(5):
        chamam = tec.convites(c.world, c.tecnicos, candidatos, None, True, [],
                              np.random.default_rng(rng_seed), usuario=0)
        assert palmeiras not in chamam


def test_ninguem_assume_o_clube_de_outro_humano_nem_demitido():
    """O demitido continua com o clube dele ate assumir outro: o clube nao vira convite
    de outro humano, e mesmo um convite forjado e recusado."""
    c = _dois()
    c.ativo = 1
    assert c.executar({"tipo": "pedir_demissao"}).get("ok")
    palmeiras = c.humanos[1].clube_id
    c.ativo = 0
    assert c._clubes_de_outros() == {palmeiras}
    c.convites = [palmeiras]
    assert "erro" in c.executar({"tipo": "assumir", "clube": palmeiras})
    assert c.clube_id != palmeiras


def test_a_virada_fecha_o_ano_de_cada_humano():
    c = _dois()
    c.ativo = 1
    while not c.acabou:
        c.avancar()
    resumo = c.virar_o_ano()
    ana, beto = c.humanos
    assert len(ana.historico) == len(beto.historico) == 1
    assert resumo is beto.historico[-1]
    assert ana.historico[-1]["clube"] == "Santos"
    assert beto.historico[-1]["clube"] == "Palmeiras"
    assert ana.historico[-1]["minha_posicao"] != beto.historico[-1]["minha_posicao"] or (
        ana.historico[-1]["minha_liga"] != beto.historico[-1]["minha_liga"])
    # a janela da IA nao mexe no elenco de nenhum humano
    for r in (ana.historico[-1], beto.historico[-1]):
        assert not r["compras_do_clube"] and not r["vendas_do_clube"]


def test_duas_selecoes_de_humanos_na_mesma_data():
    """Cada humano pode treinar uma selecao; quando as duas jogam no mesmo dia, cada uma
    sai do motor de eventos com o tecnico dela."""
    c = _dois()
    ana, beto = c.humanos
    ana.selecao_do_usuario, beto.selecao_do_usuario = "Brasil", "Argentina"
    classico = []
    for _ in range(2):              # as eliminatorias poem os dois frente a frente em 2028
        while not c.acabou:
            c.avancar()
            p = ana.partida_da_data
            if p is not None and p is beto.partida_da_data:
                classico.append(c.data - 1)
        assert ana.jogos_da_selecao and beto.jogos_da_selecao
        for data in set(ana.jogos_da_selecao) & set(beto.jogos_da_selecao):
            a, b = ana.jogos_da_selecao[data], beto.jogos_da_selecao[data]
            assert a is b or {a.home, a.away}.isdisjoint({b.home, b.away})
        c.virar_o_ano()
    assert classico, "Brasil x Argentina nao saiu como uma partida dos dois tecnicos"


# ---------------------------------------------------------------- a tela (fm.servidor)

class _Navegador:
    """Um navegador falando com o servidor de verdade, com o cookie dele."""

    def __init__(self, porta: int) -> None:
        self.porta, self.cookie = porta, ""

    def pedir(self, rota: str, corpo: dict | None = None) -> dict:
        import http.client
        import json
        con = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=120)
        cab = {"Cookie": self.cookie} if self.cookie else {}
        if corpo is None:
            con.request("GET", rota, headers=cab)
        else:
            cab["Content-Type"] = "application/json"
            con.request("POST", rota, body=json.dumps(corpo), headers=cab)
        r = con.getresponse()
        if r.getheader("Set-Cookie"):
            self.cookie = r.getheader("Set-Cookie").split(";")[0]
        dados = json.loads(r.read())
        con.close()
        return dados


@pytest.fixture
def servidor_de_dois():
    from fm.servidor import Jogo, ServidorDoJogo, criar_handler
    jogo = Jogo(_dois())
    srv = ServidorDoJogo(("127.0.0.1", 0), criar_handler(jogo, tela={}))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield jogo, srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_cada_navegador_ve_so_o_seu_clube_e_a_data_roda_com_todos_prontos(servidor_de_dois):
    jogo, porta = servidor_de_dois
    ana, beto, estranho = _Navegador(porta), _Navegador(porta), _Navegador(porta)
    assert estranho.pedir("/api/estado")["sou"] is None
    assert ana.pedir("/api/sou", {"humano": 0})["estado"]["clube"]["nome"] == "Santos"
    assert beto.pedir("/api/sou", {"humano": 1})["estado"]["clube"]["nome"] == "Palmeiras"
    # cada um, no seu navegador, ve o proprio clube -- ao mesmo tempo
    e_ana, e_beto = ana.pedir("/api/estado"), beto.pedir("/api/estado")
    assert (e_ana["sou"], e_ana["clube"]["nome"]) == (0, "Santos")
    assert (e_beto["sou"], e_beto["clube"]["nome"]) == (1, "Palmeiras")
    assert e_ana["elenco"] != e_beto["elenco"]
    # escalar mexe so no time de quem escalou
    assert beto.pedir("/api/escalar", {"formacao": "3-5-2"}).get("ok")
    assert beto.pedir("/api/estado")["tatica"]["formacao"] == "3-5-2"
    assert ana.pedir("/api/estado")["tatica"]["formacao"] == "4-3-3"
    # nada de partida ao vivo nem de "pronto" sem saber quem e
    assert "erro" in ana.pedir("/api/partida/iniciar", {})
    assert "erro" in estranho.pedir("/api/pronto", {"pronto": True})

    data = e_ana["indice_da_data"]
    r = ana.pedir("/api/pronto", {"pronto": True})
    assert r["rodou"] is False
    assert [h["pronto"] for h in r["estado"]["humanos"]] == [True, False]
    assert beto.pedir("/api/estado")["indice_da_data"] == data, "rodou sem o Beto"
    r = beto.pedir("/api/pronto", {"pronto": True})
    assert r["rodou"] is True and r["estado"]["rodadas"] == 1
    assert r["estado"]["indice_da_data"] > data
    assert not any(h["pronto"] for h in r["estado"]["humanos"])
    # quem jogou ve o pos-jogo do SEU jogo; quem nao jogou, nenhum
    for nav, h in ((ana, jogo.c.humanos[0]), (beto, jogo.c.humanos[1])):
        pos = nav.pedir("/api/posjogo")
        if h.partida_da_data is None:
            assert "erro" in pos
        else:
            assert h.clube_id in (pos["casa"]["id"], pos["fora"]["id"])
    assert any(h.partida_da_data is not None for h in jogo.c.humanos)


def test_o_ano_vira_com_todos_prontos_e_cada_um_ve_o_seu(servidor_de_dois):
    jogo, porta = servidor_de_dois
    while not jogo.c.acabou:
        jogo.c.avancar()
    ana, beto = _Navegador(porta), _Navegador(porta)
    ana.pedir("/api/sou", {"humano": 0})
    beto.pedir("/api/sou", {"humano": 1})
    assert "erro" in ana.pedir("/api/virar", {}), "com varios, o ano vira pelo Pronto"
    ana.pedir("/api/pronto", {"pronto": True})
    r = beto.pedir("/api/pronto", {"pronto": True})
    assert r["rodou"] and r["estado"]["ultima"] == "virada"
    fim_ana, fim_beto = ana.pedir("/api/virada"), beto.pedir("/api/virada")
    assert fim_ana["estado"]["clube"]["nome"] == "Santos"
    assert fim_beto["estado"]["clube"]["nome"] == "Palmeiras"
    assert fim_ana["temporada"] == fim_beto["temporada"] == 2027


def test_o_ranking_de_tecnicos_mostra_o_nome_de_cada_humano():
    from fm.servidor import Jogo, tecnicos
    jogo = Jogo(_dois())
    nomes = {x["nome"] for x in tecnicos(jogo)["ranking"]}
    assert {"Ana", "Beto"} <= nomes


def test_o_novo_jogo_cria_a_carreira_de_varios():
    from fm.servidor import Jogo, nova
    jogo = Jogo()
    r = nova(jogo, {"ligas": LIGAS, "clube": "Santos", "treinador": "Ana", "seed": 8,
                    "outros": [{"clube": "Palmeiras", "treinador": "Beto"},
                               {"clube": "Sport Recife", "treinador": ""}]})
    assert r.get("ok"), r
    assert [h["treinador"] for h in r["estado"]["humanos"]] == ["Ana", "Beto", "Treinador 3"]
    assert [h["clube"]["nome"] for h in r["estado"]["humanos"]] == [
        "Santos", "Palmeiras", "Sport Recife"]


def test_um_tecnico_em_uso_nao_pode_ser_escolhido_em_outro_aparelho(servidor_de_dois):
    """A trava contra o engano: dois aparelhos virarem o mesmo tecnico."""
    import time
    jogo, porta = servidor_de_dois
    ana, outro = _Navegador(porta), _Navegador(porta)
    assert ana.pedir("/api/sou", {"humano": 0})["ok"]
    r = outro.pedir("/api/sou", {"humano": 0})
    assert "erro" in r and "outro aparelho" in r["erro"]
    e = outro.pedir("/api/estado")
    assert e["sou"] is None
    assert [h["em_uso"] for h in e["humanos"]] == [True, False]
    # para a propria Ana o tecnico dela nao aparece como "em uso", e recarregar a pagina
    # (o mesmo cookie) continua sendo ela
    e = ana.pedir("/api/estado")
    assert e["sou"] == 0 and not e["humanos"][0]["em_uso"]

    # trocar de tecnico solta o antigo na hora
    assert ana.pedir("/api/sou", {"humano": 1})["ok"]
    assert outro.pedir("/api/sou", {"humano": 0})["ok"]

    # o aparelho que sumiu perde o tecnico depois do prazo; quando volta, nao e mais ninguem
    nav_da_ana, _ = jogo.donos[1]
    jogo.donos[1] = (nav_da_ana, time.monotonic() - 1000)
    terceiro = _Navegador(porta)
    assert terceiro.pedir("/api/sou", {"humano": 1})["ok"]
    assert ana.pedir("/api/estado")["sou"] is None
    assert ana.pedir("/api/prontos")["sou"] is None
