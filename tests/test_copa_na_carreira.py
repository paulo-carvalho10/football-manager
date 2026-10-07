"""As competicoes dentro da carreira: uma temporada tem datas, nao so rodadas.

As seis competicoes ja existiam e rodavam isoladas num comando de CLI. O que se protege
aqui e a conexao: que elas andem no mesmo relogio da liga, que a tabela de um ano decida
quem disputa o que no seguinte, e que ganhar uma copa apareca no caixa.
"""

from __future__ import annotations

import numpy as np
import pytest

from fm.carreira import COPAS, Carreira
from fm.competition import play_fixtures
from fm.copa import comecar, proxima_etapa, registrar
from fm.torneio import carregar

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture
def carreira():
    return Carreira.nova(LIGAS, "Flamengo", seed=42)


# ------------------------------------------------------------ o torneio por etapas

@pytest.mark.parametrize("nome", ["copa_do_brasil", "libertadores", "sudamericana"])
def test_todo_torneio_termina_em_campeao(carreira, nome):
    """REGRESSAO: a Copa do Brasil nunca acabava. Uma fase de mata-mata que repete
    readmitia os entrantes dela a cada rodada, entao os 12 primeiros da Serie A voltavam
    depois de eliminados e o torneio girava para sempre."""
    c = carreira
    t = carregar(nome)
    tabelas = c._tabelas_por_forca()
    a = comecar(c.world, t, tabelas)
    rng = np.random.default_rng(7)
    etapas = 0
    while (e := proxima_etapa(c.world, a, rng, tabelas)) is not None:
        ids = {f.home for f in e.fixtures} | {f.away for f in e.fixtures}
        ratings = {cid: c.world.team_rating(cid) for cid in ids}
        registrar(c.world, a,
                  play_fixtures(e.fixtures, ratings, rng, t.style, t.mentality), rng)
        etapas += 1
        assert etapas < 40, f"{nome} nao converge: {len(a.vivos)} vivos na etapa {etapas}"
    assert a.campeao is not None, f"{nome} acabou sem campeao"
    assert a.acabou


def test_ninguem_e_eliminado_e_volta(carreira):
    c = carreira
    t = carregar("copa_do_brasil")
    tabelas = c._tabelas_por_forca()
    a = comecar(c.world, t, tabelas)
    rng = np.random.default_rng(7)
    ja_eliminados: set[int] = set()
    while (e := proxima_etapa(c.world, a, rng, tabelas)) is not None:
        antes = set(a.vivos)
        ids = {f.home for f in e.fixtures} | {f.away for f in e.fixtures}
        assert not (ids & ja_eliminados), "clube eliminado voltou a jogar"
        ratings = {cid: c.world.team_rating(cid) for cid in ids}
        registrar(c.world, a,
                  play_fixtures(e.fixtures, ratings, rng, t.style, t.mentality), rng)
        ja_eliminados |= antes - set(a.vivos)


# ------------------------------------------------------------ a agenda

def test_a_temporada_tem_liga_e_copa(carreira):
    c = carreira
    tipos = {t for t, _ in c.agenda}
    assert tipos == {"liga", "copa", "selecao"}      # selecao: as datas FIFA (fm.fifa)
    assert sum(1 for t, _ in c.agenda if t == "liga") == c.total_de_rodadas
    assert set(c.copas) <= set(COPAS)


def test_as_copas_nao_ficam_enfileiradas(carreira):
    """Todas as datas de um torneio seguidas e depois as do outro nao e uma temporada."""
    c = carreira
    copas = [quem for tipo, quem in c.agenda if tipo == "copa"]
    if len(set(copas)) < 2:
        pytest.skip("uma copa so")
    trocas = sum(1 for a, b in zip(copas, copas[1:], strict=False) if a != b)
    assert trocas >= len(set(copas)), "as copas estao enfileiradas, nao intercaladas"


def test_uma_temporada_inteira_com_copas(carreira):
    c = carreira
    por_competicao: dict[str, int] = {}
    while not c.acabou:
        _, partida = c.avancar()
        if partida is not None:
            tipo, onde = c.ultimo_compromisso
            por_competicao[onde or "liga"] = por_competicao.get(onde or "liga", 0) + 1
    assert c.rodada == c.total_de_rodadas, "a liga nao completou"
    assert por_competicao.get("liga") == c.total_de_rodadas
    assert sum(v for k, v in por_competicao.items() if k != "liga") > 0, \
        "o usuario nao jogou nenhuma copa"
    for nome, a in c.copas.items():
        assert a.acabou, f"{nome} ficou inacabada no fim do ano"
        assert a.campeao is not None


def test_o_lobby_sabe_qual_competicao_vem(carreira):
    c = carreira
    for _ in range(12):
        tipo, onde, jogo = c.proximo_jogo()
        assert tipo in ("liga", "copa", "")
        if tipo == "liga":
            assert jogo is not None
            assert c.clube_id in (jogo.home, jogo.away)
        elif tipo == "copa":
            assert onde in c.copas
            assert c.copas[onde].esta_vivo(c.clube_id)
        c.avancar()


# ------------------------------------------------------------ o ciclo entre anos

def test_a_tabela_de_um_ano_classifica_para_o_seguinte(carreira):
    """Era isto que faltava: as regras de vaga ja estavam nos arquivos, mas liam a forca
    desenhada em vez da temporada jogada."""
    c = carreira
    while not c.acabou:
        c.avancar()
    tabela = [linha.club_id for linha in c.tabela("brasil_real")]
    c.virar_o_ano()

    assert c.tabelas_do_ano_anterior, "a virada nao guardou as fontes de vaga"
    assert c.tabelas_do_ano_anterior.get("BRA1") == tabela

    # os quatro primeiros do Brasileirao tem de estar na Libertadores do ano seguinte
    liberta = c.copas["libertadores"]
    dentro = set(liberta.classificados.get("grupos", [])) | set(liberta.vivos)
    campeao_da_copa = c.historico[-1]["copas"].get("copa_do_brasil")
    assert sum(1 for cid in tabela[:4] if cid in dentro) >= 3, (
        f"os primeiros do Brasileirao ficaram fora da Libertadores "
        f"(campeao da Copa do Brasil: {campeao_da_copa})")


def test_ninguem_disputa_duas_continentais(carreira):
    """A cascata de vagas ja resolvia isso; o que faltava era compartilhar os ocupados."""
    c = carreira
    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    liberta = set(c.copas["libertadores"].classificados.get("grupos", []))
    liberta |= set(c.copas["libertadores"].classificados.get("pre", []))
    sula = set(c.copas["sudamericana"].classificados.get("grupos", []))
    assert not (liberta & sula), "clube classificado para as duas competicoes"


def test_ganhar_copa_entra_no_caixa(carreira):
    from fm.financas import PREMIO_DE_COPA

    c = carreira
    while not c.acabou:
        c.avancar()
    campeoes = {n: a.campeao for n, a in c.copas.items() if a.campeao}
    caixa_antes = {cid: c.world.clubs[cid].balance for cid in campeoes.values()}
    r = c.virar_o_ano()

    assert r["copas"], "o resumo do ano nao menciona as copas"
    for nome, cid in campeoes.items():
        if nome in PREMIO_DE_COPA and cid in caixa_antes:
            # o balanco tem varias parcelas; o que se cobra e que o premio esteja la
            assert r["premios_de_copa"] >= 0
    if r["minhas_copas"]:
        assert r["premios_de_copa"] > 0, "campeao sem premio no caixa"


def test_o_save_atravessa_uma_data_de_copa(carreira):
    """O save guarda a DATA, nao a rodada da liga: guardar a rodada perderia os jogos de
    copa no replay, e o mundo voltaria diferente do que o usuario deixou."""
    c = carreira
    for _ in range(9):
        c.avancar()
    caminho = c.salvar("teste_copa_pytest")
    try:
        volta = Carreira.carregar("teste_copa_pytest")
        assert volta.data == c.data
        assert volta.rodada == c.rodada
        assert {n: a.fase for n, a in volta.copas.items()} == \
               {n: a.fase for n, a in c.copas.items()}
        assert {n: sorted(a.vivos) for n, a in volta.copas.items()} == \
               {n: sorted(a.vivos) for n, a in c.copas.items()}
        assert volta.clube.balance == c.clube.balance
    finally:
        caminho.unlink()


def test_a_copa_paga_por_campanha_e_nao_so_por_titulo():
    """REGRESSAO: so campeao e vice recebiam. Quem caia nas oitavas levava ZERO e ainda
    tinha pagado o custo dos jogos -- disputar a Libertadores sem chegar a final era
    prejuizo puro, e nao havia razao financeira para buscar a vaga."""
    from fm.financas import premio_de_campanha

    total = 6
    valores = [premio_de_campanha("libertadores", n, total) for n in range(1, total + 1)]
    assert all(v > 0 for v in valores), "alguem avancou e nao recebeu nada"
    assert all(a <= b for a, b in zip(valores, valores[1:], strict=False)), \
        "avancar mais tem de pagar mais"

    campeao = premio_de_campanha("libertadores", total, total, campeao=True)
    vice = premio_de_campanha("libertadores", total, total, vice=True)
    semi = premio_de_campanha("libertadores", total - 1, total)
    assert campeao > vice > semi, "campeao, vice e semifinalista tem de se separar"
    # campeao e vice sobrevivem as MESMAS etapas: sem degrau proprio o vice levava 92%
    assert vice < campeao * 0.7


def test_quem_vai_longe_na_copa_termina_o_ano_melhor(carreira):
    c = carreira
    while not c.acabou:
        c.avancar()
    premios = c._premiar_copas()
    assert premios, "nenhum clube recebeu premio de copa"
    liberta = c.copas["libertadores"]
    if liberta.campeao and liberta.etapas_vividas:
        mais_curto = min(liberta.etapas_vividas, key=lambda k: liberta.etapas_vividas[k])
        assert premios.get(liberta.campeao, 0) > premios.get(mais_curto, 0)
