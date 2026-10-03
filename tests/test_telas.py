"""A API das telas do PRANCHETA 11: menu, carreira nova, partida ao vivo e as telas do clube.

Chama as funcoes do servidor direto, sem HTTP: o que interessa aqui e o contrato do JSON e
as regras que a tela confia que o servidor aplica (freemium, limite de trocas, replay).
"""

import json

import pytest

from fm import servidor, telas
from fm.carreira import Carreira


@pytest.fixture
def vazio():
    return servidor.Jogo(None)


@pytest.fixture
def jogo():
    j = servidor.Jogo(None)
    r = servidor.nova(j, {"ligas": ["brasil_real", "brasil_b_real"], "clube": "Flamengo",
                          "treinador": "Teste"})
    assert r.get("ok"), r
    return j


def test_o_menu_abre_sem_carreira(vazio):
    m = servidor.menu(vazio)
    assert m["carreira"] is None
    assert m["versao"] == telas.VERSAO
    json.dumps(m)


def test_o_catalogo_libera_as_oito_ligas_e_cada_uma_tem_pack():
    """Liberadas em 28/09/2026. Liga liberada sem pack quebraria a criacao de carreira."""
    from fm.config import load_league
    from fm.pack import load_pack
    cat = telas.catalogo()
    # as oito de 28/09/2026 e, desde 01/10/2026, o resto da Conmebol
    assert {n["pais"] for n in cat["nacionais"] if n["livre"]} == {
        "BRA", "ESP", "ENG", "ITA", "GER", "FRA", "POR", "ARG",
        "COL", "CHI", "URU", "ECU", "PAR", "PER", "BOL", "VEN",
        # e, desde 03/10/2026, o resto da Europa
        "NED", "BEL", "TUR", "GRE", "UKR", "RUS", "AUT", "SUI", "SCO", "DEN", "NOR", "SWE",
        "SRB", "CRO", "POL", "CZE"}
    for n in cat["nacionais"]:
        for liga in n["ligas"]:
            assert load_pack(load_league(liga["id"])["pack"]).clubes


def test_liga_bloqueada_nao_entra_pela_api(vazio):
    """O cadeado nao e so visual: a API recusa o que nao esta na versao base."""
    r = servidor.nova(vazio, {"ligas": ["premier_league"], "clube": "Arsenal"})
    assert "erro" in r
    assert vazio.c is None
    assert servidor.clubes({"ligas": ["premier_league"]})["clubes"] == []


def test_a_escolha_de_clube_traz_o_que_pesa_na_decisao():
    d = servidor.clubes({"ligas": ["brasil_real,brasil_b_real"], "seed": ["2027"]})
    assert len(d["clubes"]) == 40
    c = next(x for x in d["clubes"] if x["nome"] == "Flamengo")
    for campo in ("forca", "ranking", "reputacao", "caixa", "valor_do_elenco", "folha",
                  "meta", "estrelas", "liga_nome"):
        assert campo in c
    assert c["liga_nome"] == "Série A"


def test_nova_carreira_pelo_menu(jogo):
    e = servidor.estado(jogo)
    assert e["clube"]["nome"] == "Flamengo"
    assert e["treinador"] == "Teste"
    assert e["liga_nome"] == "Série A"


def _iniciar_ate_ter_jogo(jogo) -> dict:
    """O ano abre com datas de copa sem o clube; `partida_iniciar` pula elas, mas para se
    chegar proposta por um jogador. Insiste ate a bola rolar."""
    r = servidor.partida_iniciar(jogo)
    while r.get("sem_jogo"):
        r = servidor.partida_iniciar(jogo)
    return r


def test_partida_ao_vivo_do_apito_ao_pos_jogo(jogo):
    c = jogo.c
    r = _iniciar_ate_ter_jogo(jogo)
    data_do_jogo = c.data
    assert r["minuto"] == 5 and not r["fim"]
    assert r["trocas_feitas"] == 0 and r["max_trocas"] == 5
    assert len(r["rodada"]) >= 9, "a rodada ao vivo tem os outros jogos da divisao"
    sai, entra = r["em_campo"][3], r["banco"][0]["id"]

    r = servidor.partida_seguir(jogo, {"trocas": [[sai, entra]],
                                       "tatica": {"estilo": "ofensivo"}})
    assert r["minuto"] == 10
    assert r["trocas_feitas"] == 1
    assert r["tatica"]["estilo"] == "ofensivo"

    r = servidor.partida_seguir(jogo, {"ate_o_fim": True})
    assert r["fim"] and r["minuto"] == 90
    assert c.data == data_do_jogo + 1, "a data andou"
    p = servidor.pos_jogo(jogo)
    notas = [j["nota"] for j in p["time_casa"] + p["time_fora"]]
    assert all(3.0 <= n <= 10.0 for n in notas)
    assert p["melhor_em_campo"]["nota"] == max(notas)
    json.dumps(p)
    # a troca feita ao vivo ficou gravada para o replay do save
    assert c.na_partida[f"{c.temporada}:{data_do_jogo}"]["trocas"][0][1:] == [sai, entra]


def test_recarregar_a_pagina_no_meio_do_jogo_retoma(jogo):
    _iniciar_ate_ter_jogo(jogo)
    servidor.partida_seguir(jogo, {})
    r = servidor.partida_iniciar(jogo)
    assert r["minuto"] == 10, "iniciar de novo tem de retomar, nao comecar outra data"
    servidor.partida_seguir(jogo, {"ate_o_fim": True})


def test_mercado_filtra_e_nao_lista_o_proprio_elenco(jogo):
    c = jogo.c
    d = telas.mercado(c, {"pos": ["FW"], "ovr_min": ["75"]}, lambda cid: servidor._clube(c, cid))
    assert d["total"] > 0
    meus = {p.id for p in c.world.squad(c.clube_id)}
    for j in d["jogadores"]:
        assert j["posicao"] == "FW" and j["overall"] >= 75
        assert j["id"] not in meus
    alvo = d["jogadores"][0]["id"]
    telas.observar(c, alvo)
    so = telas.mercado(c, {"observados": ["1"]}, lambda cid: servidor._clube(c, cid))
    assert [j["id"] for j in so["jogadores"]] == [alvo]


def test_mensagens_tem_chave_estavel_e_marcam_lidas(jogo):
    c = jogo.c
    a = telas.mensagens(c, "hoje", set())
    b = telas.mensagens(c, "hoje", {a[0]["id"]})
    assert [m["id"] for m in a] == [m["id"] for m in b]
    assert b[0]["lida"] and not a[0]["lida"]


def test_classificacao_tem_zonas_do_arquivo_da_liga(jogo):
    c = jogo.c
    for _ in range(3):
        c.avancar()
    d = telas.classificacao(c, None, lambda cid: servidor._clube(c, cid))
    assert len(d["linhas"]) == 20
    assert d["zonas"]["rebaixamento"] == 4
    for linha in d["linhas"]:
        assert linha["casa"]["jogos"] + linha["fora"]["jogos"] == linha["jogos"]
        assert len(linha["ultimos"]) <= 5


def test_funcoes_ficam_no_save(tmp_path, monkeypatch):
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    j = servidor.Jogo(Carreira.nova("brasil_real", "Santos", seed=4))
    capitao = j.c.escalacao_atual()[5]
    servidor.escalar(j, {"onze": j.c.escalacao_atual(), "funcoes": {"capitao": capitao}})
    j.c.salvar("funcoes")
    assert Carreira.carregar("funcoes").funcoes == {"capitao": capitao}


def test_a_copa_diz_quando_o_clube_ainda_vai_entrar(jogo):
    """REGRESSAO: a tela dizia "fora" para a Libertadores de quem entra na fase de grupos."""
    situacoes = {x["id"]: x["situacao"] for x in servidor.estado(jogo)["copas"]}
    assert situacoes["libertadores"].startswith("entra")


def test_o_treinador_acumula_a_curva_de_confianca(jogo):
    c = jogo.c
    for _ in range(4):
        c.avancar()
    t = telas.treinador(c)
    assert len(t["curva"]) == 4
    assert t["total"]["jogos"] == t["atual"]["numeros"]["jogos"]


def test_artilharia_por_competicao_fecha_com_a_tabela(jogo):
    """Gol de copa nao e gol de campeonato: o caderno da liga soma exatamente a tabela."""
    c = jogo.c
    while c.rodada < 6:          # o ano abre com copas: anda ate a liga ter rodadas
        c.avancar()
    gols_da_liga = sum(r.goals_home + r.goals_away for r in c.jogos("brasil_real"))
    caderno = c.estatisticas_por_comp["brasil_real"]
    assert sum(x.gols for x in caderno.por_jogador.values()) == gols_da_liga
    total = sum(x.gols for x in c.estatisticas.por_jogador.values())
    por_comp = sum(sum(x.gols for x in e.por_jogador.values())
                   for e in c.estatisticas_por_comp.values())
    assert por_comp == total
    a = telas.artilharia(c, "brasil_real", None, lambda cid: servidor._clube(c, cid))
    assert a["artilheiros"] and a["artilheiros"][0]["gols"] >= a["artilheiros"][-1]["gols"]


def test_selecao_da_rodada_e_um_433_de_quem_jogou(jogo):
    from fm.tatica import VAGAS
    c = jogo.c
    while c.rodada < 2:
        c.avancar()
    s = telas.selecao(c, "brasil_real", None, lambda cid: servidor._clube(c, cid))
    assert len(s["onze"]) == 11
    setores = [v[1] for v in VAGAS["4-3-3"]]
    assert [j["posicao"] for j in s["onze"]] == setores
    ids = set(c.world.leagues[next(iter(c.world.leagues))].club_ids)
    assert all(j["clube"]["id"] in ids for j in s["onze"]), "so clubes da divisao"
    assert sum(j["craque"] for j in s["onze"]) == 1


def test_a_artilharia_fica_guardada_na_virada_do_ano(jogo):
    c = jogo.c
    while not c.acabou:
        c.avancar()
    ano = c.temporada
    c.virar_o_ano()
    a = telas.artilharia(c, "brasil_real", ano, lambda cid: servidor._clube(c, cid))
    assert a["temporada"] == ano and len(a["artilheiros"]) == 10
    assert any(x["temporada"] == ano for x in a["campeoes"])


def test_save_de_formato_antigo_da_erro_claro_e_nao_derruba(tmp_path, monkeypatch):
    """REGRESSAO: um save de antes da piramide ("liga" em vez de "ligas") derrubava o
    pedido e a tela ficava em "Carregando..." para sempre."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    (tmp_path / "velho.json").write_text(json.dumps({
        "seed": 42, "liga": "brasil_real", "clube_id": 999999, "temporada": 2027,
        "rodada": 3, "decisoes": {"1": {"escalacao": [], "tatica": {}}}}), encoding="utf-8")
    r = servidor.carregar(servidor.Jogo(None), {"nome": "velho"})
    assert "erro" in r and "versão" in r["erro"]


def test_erro_dentro_de_uma_rota_volta_como_json():
    """Excecao numa rota vira resposta 500 com a mensagem, nunca conexao cortada."""
    import threading
    import urllib.error
    import urllib.request
    from fm.servidor import ROTAS_GET, Jogo, ServidorDoJogo, criar_handler

    ROTAS_GET["/api/teste-quebra"] = lambda jogo, q: 1 / 0
    srv = ServidorDoJogo(("127.0.0.1", 0), criar_handler(Jogo(None)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        from fm.servidor import ROTAS_SEM_CARREIRA
        ROTAS_SEM_CARREIRA.add("/api/teste-quebra")
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/teste-quebra"
        try:
            urllib.request.urlopen(url, timeout=5)
            raise AssertionError("devia ter dado 500")
        except urllib.error.HTTPError as e:
            assert e.code == 500
            assert "ZeroDivisionError" in json.loads(e.read())["erro"]
    finally:
        srv.shutdown()
        srv.server_close()
        ROTAS_GET.pop("/api/teste-quebra", None)
        ROTAS_SEM_CARREIRA.discard("/api/teste-quebra")
