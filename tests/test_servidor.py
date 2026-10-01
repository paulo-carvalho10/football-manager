"""A API que a interface do navegador consome.

Isto e a segunda casca do jogo, nao um segundo jogo: o que se protege aqui e que ela
entregue o MESMO estado que o terminal ve, e que nenhuma regra tenha vazado para dentro
dela. Se um valor so existe no JSON, ele foi inventado aqui -- e e' bug.
"""

from __future__ import annotations

import json

import pytest

from fm.carreira import Carreira
from fm.servidor import (
    Jogo,
    avancar,
    camisa_svg,
    escalar,
    estado,
    tabela,
    virar_o_ano,
)

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture
def jogo():
    return Jogo(Carreira.nova(LIGAS, "Flamengo", seed=42))


def test_o_estado_e_json_de_verdade(jogo):
    """Se nao serializa, a interface nao abre -- e o erro so aparece no navegador."""
    texto = json.dumps(estado(jogo), ensure_ascii=False)
    assert len(texto) > 1000
    de_volta = json.loads(texto)
    assert de_volta["clube"]["nome"] == "Flamengo"


def test_o_estado_bate_com_a_carreira(jogo):
    c, e = jogo.c, estado(jogo)
    assert e["temporada"] == c.temporada
    assert e["rodada"] == c.rodada
    assert e["caixa"] == c.clube.balance
    assert e["liga"] == c.liga
    assert len(e["elenco"]) == len(c.world.squad(c.clube_id))
    assert sum(1 for p in e["elenco"] if p["titular"]) == 11
    assert sorted(e["onze"]) == sorted(c.escalacao_atual())
    assert e["aprovacao"]["meta"] == c.aprovacao.meta.texto


def test_avancar_devolve_a_partida_e_o_estado_novo(jogo):
    antes = estado(jogo)["rodada"]
    r = avancar(jogo)
    assert r["estado"]["rodada"] == antes + 1 or r["tipo"] == "copa"
    if r["partida"]:
        p = r["partida"]
        assert p["gols_casa"] + p["gols_fora"] == sum(
            1 for e in p["eventos"] if e["tipo"] == "gol")
        assert len(p["estatisticas"]) == 6
        assert "Flamengo" in (p["casa"]["nome"], p["fora"]["nome"])
    json.dumps(r, ensure_ascii=False)


def test_escalar_pela_api_muda_o_onze(jogo):
    c = jogo.c
    elenco = sorted(c.world.squad(c.clube_id), key=lambda p: p.overall)
    piores = [p.id for p in elenco[:11]]
    r = escalar(jogo, {"onze": piores})
    assert "erro" not in r
    assert sorted(r["estado"]["onze"]) == sorted(piores)
    # a tatica tambem vem junto
    r = escalar(jogo, {"onze": piores, "estilo": "ofensivo", "marcacao": "forte"})
    assert r["estado"]["tatica"]["estilo"] == "ofensivo"
    assert r["estado"]["tatica"]["marcacao"] == "forte"


def test_escalacao_invalida_volta_como_erro_e_nao_como_excecao(jogo):
    """A interface precisa poder mostrar a mensagem; uma excecao viraria 500 e tela branca."""
    meus = [p.id for p in jogo.c.world.squad(jogo.c.clube_id)]
    curto = escalar(jogo, {"onze": meus[:3]})
    assert "11" in curto["erro"], curto["erro"]
    alheio = escalar(jogo, {"onze": [1, 2, 3]})
    assert "outro clube" in alheio["erro"], alheio["erro"]
    assert curto["estado"]["onze"], "o estado tem de continuar utilizavel"


def test_a_tabela_vem_ordenada_e_marca_o_usuario(jogo):
    t = tabela(jogo)
    assert len(t["linhas"]) == 20
    assert [linha["posicao"] for linha in t["linhas"]] == list(range(1, 21))
    assert sum(1 for linha in t["linhas"] if linha["eu"]) == 1
    outra = tabela(jogo, "brasil_b_real")
    assert outra["liga"] == "brasil_b_real"
    assert not any(linha["eu"] for linha in outra["linhas"])


def test_a_camisa_vem_como_svg(jogo):
    svg = camisa_svg(jogo, jogo.c.clube_id, "1")
    assert svg.lstrip().startswith("<svg")
    assert "</svg>" in svg
    casa, fora = svg, camisa_svg(jogo, jogo.c.clube_id, "2")
    assert casa != fora, "camisa 1 e 2 tem de diferir"


def test_virar_o_ano_pela_api(jogo):
    c = jogo.c
    assert "erro" in virar_o_ano(jogo), "nao pode virar antes de acabar"
    while not c.acabou:
        c.avancar()
    r = virar_o_ano(jogo)
    json.dumps(r, ensure_ascii=False)
    assert r["temporada"] == 2027
    assert r["campeoes"]["brasil_real"]
    assert r["estado"]["temporada"] == 2028
    assert "clima" in r and "balanco" in r


def test_a_api_nao_deixa_jogar_depois_de_demitido(jogo):
    jogo.c.aprovacao.demitido = True
    jogo.c.aprovacao.motivo = "teste"
    r = avancar(jogo)
    assert "erro" in r
    assert estado(jogo)["demitido"] is True


def test_uma_temporada_inteira_pela_api(jogo):
    """O caminho que o navegador percorre de verdade."""
    c = jogo.c
    partidas = 0
    while not c.acabou:
        r = avancar(jogo)
        assert "erro" not in r
        if r["partida"]:
            partidas += 1
    assert partidas >= 38
    fim = virar_o_ano(jogo)
    assert fim["estado"]["temporada"] == 2028
    assert fim["estado"]["rodada"] == 0


# ------------------------------------------------------------ as telas do brief

def test_o_topo_tem_o_que_a_barra_superior_mostra(jogo):
    e = estado(jogo)
    for campo in ("treinador", "data", "temporada", "caixa", "proximo"):
        assert campo in e, f"o topo precisa de {campo}"
    # a data e derivada da rodada, e cosmetica -- mas tem de ser uma data
    import re
    assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", e["data"])


def test_o_elenco_traz_as_colunas_da_tabela(jogo):
    """As colunas do brief: overall, potencial, condicao, moral, jogos, gols, contrato."""
    from fm.servidor import estado as ler
    p = ler(jogo)["elenco"][0]
    for campo in ("posicao", "idade", "overall", "potencial", "energia", "moral",
                  "jogos", "gols", "assistencias", "salario", "contrato"):
        assert campo in p, f"falta {campo} na linha do elenco"


def test_o_perfil_traz_os_atributos_numericos(jogo):
    from fm.servidor import jogador

    p = jogador(jogo, estado(jogo)["onze"][0])
    assert p["atributos"], "o perfil precisa dos atributos"
    assert len(p["atributos"]) >= 10
    assert all(isinstance(v, int) for v in p["atributos"].values())
    for campo in ("nacionalidade", "pe", "altura", "valor", "salario", "contrato"):
        assert campo in p
    assert set(p["temporada"]) == {"jogos", "gols", "assistencias",
                                   "amarelos", "vermelhos"}


def test_o_perfil_de_quem_nao_existe_nao_derruba(jogo):
    from fm.servidor import jogador
    assert "erro" in jogador(jogo, 999999)


def test_a_tela_inicial_responde_como_estou(jogo):
    from fm.servidor import inicio

    c = jogo.c
    for _ in range(12):
        c.avancar()
    d = inicio(jogo)
    assert d["campanha"]["jogos"] > 0
    assert d["ultimos"], "sem ultimos jogos depois de doze datas"
    assert all(u["resultado"] in "VED" for u in d["ultimos"])
    assert d["proximos"], "sem proximos jogos no meio da temporada"


def test_artilheiros_saem_do_campeonato_inteiro(jogo):
    """O motor rapido devolve so o placar: sem a amostragem por jogador nao existiria
    artilharia de campeonato, so a do clube do usuario."""
    from fm.servidor import estatisticas

    c = jogo.c
    while not c.acabou:
        c.avancar()
    d = estatisticas(jogo)
    assert len(d["artilheiros"]) >= 10
    clubes = {x["clube"] for x in d["artilheiros"]}
    assert len(clubes) > 3, "a artilharia so tem jogadores de um punhado de clubes"
    gols = [x["gols"] for x in d["artilheiros"]]
    assert gols == sorted(gols, reverse=True)
    assert gols[0] >= 10, f"o artilheiro do ano fez so {gols[0]} gols"


def test_o_calendario_cobre_a_temporada(jogo):
    from fm.servidor import calendario

    c = jogo.c
    # o ano abre em fevereiro com as preliminares das copas: o clube grande so estreia em
    # abril, entao anda ate ele ter jogado algumas vezes
    while len(c.jogos_do_usuario) < 4:
        c.avancar()
    d = calendario(jogo)
    assert d["atual"] == c.data
    ligas = [x for x in d["datas"] if x["tipo"] == "liga"]
    assert len(ligas) == c.rodadas_da_liga()
    assert [x["rodada"] for x in ligas] == list(range(1, c.rodadas_da_liga() + 1))
    dias = [x["dia"][6:] + x["dia"][3:5] + x["dia"][:2] for x in d["datas"]]
    assert dias == sorted(dias), "o calendario fora de ordem"
    assert any(x["resultado"] for x in d["datas"]), "nenhuma data jogada tem resultado"
    # data de copa que ja passou so aparece se o clube jogou nela
    assert all(x["resultado"] for x in d["datas"] if x["tipo"] == "copa" and x["passou"])


def test_o_calendario_nao_lista_copa_de_outro_clube():
    """REGRESSAO: com o mundo inteiro a agenda tem as datas de TODAS as copas, e o
    calendario do Real Madrid listava a Liga Europa -- para onde so vai quem cai na
    preliminar da Champions, fase que ele nem joga."""
    from fm.servidor import calendario

    c = Carreira.nova(["espanha_real", "espanha_b_real"], "Real Madrid", seed=2)
    nomes = {x["competicao"] for x in calendario(Jogo(c))["datas"] if x["tipo"] == "copa"}
    assert nomes == {c.copas["champions"].torneio.nome}


def test_as_financas_batem_com_o_motor(jogo):
    from fm.financas import folha_anual
    from fm.servidor import financas

    d = financas(jogo)
    assert d["caixa"] == jogo.c.clube.balance
    assert d["folha"] == folha_anual(jogo.c.world, jogo.c.clube_id)
    assert d["salarios"], "a folha precisa listar os maiores salarios"
    assert d["salarios"] == sorted(d["salarios"], key=lambda x: -x["salario"])


def test_dois_servidores_nao_dividem_a_mesma_porta():
    """REGRESSAO: no Windows um segundo `servir` subia na mesma porta e os pedidos caiam
    ora no servidor novo, ora no velho -- com tela nova e Python velho, a escalacao sumia."""
    import pytest
    from fm.servidor import Jogo, ServidorDoJogo, criar_handler
    primeiro = ServidorDoJogo(("127.0.0.1", 0), criar_handler(Jogo(None)))
    try:
        porta = primeiro.server_address[1]
        with pytest.raises(OSError):
            ServidorDoJogo(("127.0.0.1", porta), criar_handler(Jogo(None)))
    finally:
        primeiro.server_close()


def test_a_tela_e_fotografada_quando_o_servidor_sobe():
    from fm.servidor import fotografar_a_tela
    tela = fotografar_a_tela()
    for arquivo in ("index.html", "estilo.css", "base.js", "jogo.js", "partida.js", "menu.js"):
        assert arquivo in tela


def test_todo_clube_das_quatro_divisoes_tem_escudo():
    """Os escudos ficam fora do git (marca registrada): sem eles baixados, o teste pula."""
    import pytest
    from fm.config import load_league
    from fm.generate import build_world
    from fm.importer.escudos import ESCUDOS_DIR
    from fm.servidor import _escudos
    if not (ESCUDOS_DIR / "indice.json").exists():
        pytest.skip("escudos nao baixados: python -m fm.cli escudos --pack <pack>")
    w, _ = build_world([load_league(n) for n in
                        ("brasil_real", "brasil_b_real", "espanha_real", "espanha_b_real")],
                       seed=1)
    sem = [c.name for c in w.clubs.values() if c.name not in _escudos()]
    assert not sem, f"sem escudo: {sem}"


def test_o_desenho_livre_vai_e_volta_da_tela(jogo):
    """A tela manda o ponto de cada titular; o estado devolve o mesmo desenho, e trocar a
    formacao pronta recomeca do desenho dela."""
    desenho = ["GOL", "LE", "ZE", "ZD", "LD", "VC", "ME", "MCE", "MCD", "MD", "CA"]
    r = escalar(jogo, {"onze": estado(jogo)["onze"], "desenho": desenho})
    assert r.get("ok"), r
    t = r["estado"]["tatica"]
    assert t["desenho"] == desenho and t["nome"] == "4-1-4-1" and t["personalizado"]
    assert [x["ponto"] for x in t["posicoes"]] == desenho
    assert {x["id"] for x in r["estado"]["opcoes"]["pontos"]} >= set(desenho)
    # mudar so a mentalidade nao desfaz o desenho
    t = escalar(jogo, {"estilo": "ofensivo"})["estado"]["tatica"]
    assert t["desenho"] == desenho
    # a formacao pronta recomeca do desenho dela
    t = escalar(jogo, {"formacao": "3-5-2"})["estado"]["tatica"]
    assert t["nome"] == "3-5-2" and not t["personalizado"]


def test_desenho_invalido_volta_com_o_motivo(jogo):
    r = escalar(jogo, {"desenho": ["GOL", "LE", "ZD", "VE", "VC", "VD", "ME", "MD", "MEI",
                                   "CAE", "CAD"]})
    assert "defensores" in r["erro"]
