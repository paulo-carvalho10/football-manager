"""A camisa do clube no terminal.

O que quebra aqui e alinhamento, e alinhamento quebra em silencio: os codigos de cor
ocupam dezenas de bytes e zero colunas na tela, entao qualquer conta feita sobre len() da
string colorida entorta a fileira inteira sem levantar erro nenhum.
"""

from __future__ import annotations

import io
import re

import pytest

from fm.camisa import LARGURA, PADROES, camisa, legenda
from fm.carreira import Carreira
from fm.jogo import _desenhar_campo

ANSI = re.compile(r"\033\[[0-9;]*m")


def visivel(texto: str) -> int:
    return len(ANSI.sub("", texto))


@pytest.fixture(scope="module")
def carreira():
    return Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=42)


@pytest.mark.parametrize("cor", [True, False])
@pytest.mark.parametrize("padrao", PADROES)
def test_a_camisa_ocupa_as_colunas_que_diz_ocupar(padrao, cor):
    linhas = camisa("#E2231A", "#111111", padrao, cor=cor)
    assert len(linhas) == 3
    for linha in linhas:
        assert visivel(linha) == LARGURA, f"{visivel(linha)} colunas em vez de {LARGURA}"


def test_cada_padrao_desenha_uma_camisa_diferente():
    """Se dois padroes saem iguais, um deles nao esta sendo aplicado -- foi o que
    aconteceu com `aros` e `faixa`, que alternavam na mesma altura."""
    desenhos = {p: "".join(camisa("#E2231A", "#111111", p, cor=True)) for p in PADROES}
    assert len(set(desenhos.values())) == len(PADROES), "dois padroes sairam identicos"


def test_a_camisa_tem_forma_de_camisa():
    """Gola, manga e tronco. Um retangulo colorido nao e uma camisa."""
    from fm.camisa import _matriz
    grade = _matriz("#E2231A", "#111111", "liso")
    vazios_no_topo = sum(1 for p in grade[0] if p is None)
    assert vazios_no_topo >= 3, "sem entalhe de gola no topo"
    assert all(p is not None for p in grade[1]), "os ombros tem de ser a linha mais larga"
    pano = [sum(1 for p in linha if p is not None) for linha in grade]
    assert pano[1] > pano[-1], "a manga nao afina: a camisa saiu retangular"
    assert pano[-1] == 7, "o tronco tem de ter sete colunas"


def test_a_cor_do_clube_vai_para_a_camisa():
    """Pintar o Corinthians de verde, a cor do rival, e pior que nao pintar nada."""
    vermelha = "".join(camisa("#E2231A", "#111111", "aros", cor=True))
    assert "226;35;26" in vermelha, "a cor primaria nao chegou ao desenho"
    assert "17;17;17" in vermelha, "a cor secundaria nao chegou as mangas"
    preta = "".join(camisa("#111111", "#F2F2F2", "aros", cor=True))
    assert vermelha != preta, "dois clubes de cores diferentes sairam iguais"


def test_o_overall_fica_fora_da_camisa():
    """Numero no peito disputa espaco com o padrao e some numa camisa listrada."""
    for padrao in PADROES:
        desenho = ANSI.sub("", "".join(camisa("#E2231A", "#111111", padrao, cor=True)))
        assert not any(c.isdigit() for c in desenho), "sobrou numero dentro da camisa"


def test_cor_invalida_nao_derruba_a_tela():
    for ruim in ("", "#zzz", "nao-e-cor", "#12"):
        assert visivel(camisa(ruim, ruim, "listras", cor=True)[0]) == LARGURA
    # padrao que nao existe cai em liso em vez de derrubar a tela
    assert visivel(camisa("#E2231A", "#111111", "xadrez", cor=True)[0]) == LARGURA


def test_a_legenda_cabe_na_camisa():
    assert len(legenda("Neymar")) == LARGURA
    assert len(legenda("Benjamín Rollheiser")) == LARGURA
    # nome comprido encolhe para o ultimo sobrenome antes de ser cortado no meio
    assert "Rollheiser" in legenda("Benjamín Rollheiser")


def test_o_campo_fecha_as_bordas(carreira):
    """REGRESSAO: o nome podia crescer ate a celula inteira e ficava mais largo que o
    desenho, desencostando a coluna."""
    saida = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(saida):
        _desenhar_campo(carreira, carreira.escalacao_atual(), carreira.tatica_atual())
    linhas = [ln for ln in ANSI.sub("", saida.getvalue()).splitlines() if ln.strip()]
    larguras = {len(ln) for ln in linhas}
    assert len(larguras) == 1, f"o campo saiu com larguras diferentes: {sorted(larguras)}"
    for ln in linhas[1:-1]:
        assert ln.lstrip().startswith("|") and ln.rstrip().endswith("|")


def test_o_campo_mostra_os_onze_com_posicao_e_energia(carreira):
    saida = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(saida):
        _desenhar_campo(carreira, carreira.escalacao_atual(), carreira.tatica_atual())
    texto = ANSI.sub("", saida.getvalue())
    onze = [carreira.world.players[i] for i in carreira.escalacao_atual()]
    for p in onze:
        assert legenda(p.name).strip() in texto, f"{p.name} sumiu do campo"
    assert texto.count("%") == 11, "faltou energia de alguem"
    for grupo in ("GK", "DF", "MF", "FW"):
        assert grupo in texto


def test_o_goleiro_veste_outra_cor(carreira):
    """Regra do futebol, e ajuda a ler o campo de relance."""
    saida = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(saida):
        _desenhar_campo(carreira, carreira.escalacao_atual(), carreira.tatica_atual())
    linhas = saida.getvalue().splitlines()
    gol = next(i for i, ln in enumerate(linhas) if "gol" in ln)
    ataque = next(i for i, ln in enumerate(linhas) if "ataque" in ln)
    assert linhas[gol] != linhas[ataque]


# --------------------------------------------------------- o dado da camisa

def test_a_camisa_do_pack_chega_ao_clube(carreira):
    """A cadeia inteira: data/cores -> pack -> PackClub -> Club."""
    c = carreira
    corinthians = next(x for x in c.world.clubs.values() if x.name == "Corinthians")
    flamengo = next(x for x in c.world.clubs.values() if x.name == "Flamengo")
    gremio = next(x for x in c.world.clubs.values() if x.name == "Gremio")

    assert flamengo.kit_pattern == "aros"
    assert gremio.kit_pattern == "listras"
    # tema preto, uniforme branco: sao campos diferentes justamente por causa deste caso
    assert corinthians.color_primary.lower() == "#1a1a1a"
    assert corinthians.kit_body.lower() == "#f2f2f2"


def test_clube_sem_cor_nao_quebra_a_camisa(carreira):
    """A maioria do mundo nao tem entrada em data/cores. Tem de vestir o tema."""
    c = carreira
    for clube in c.world.clubs.values():
        pano = clube.kit_body or clube.color_primary
        detalhe = clube.kit_detail or clube.color_secondary
        assert pano and detalhe
        assert visivel(camisa(pano, detalhe, clube.kit_pattern, cor=True)[0]) == LARGURA


def test_as_cores_de_um_pais_nao_vazam_para_outro():
    """REGRESSAO: "Athletic Club" e o Bilbao na Espanha e o de Sao Joao del-Rei na Serie B.
    Sem escopo por pack, o Bilbao saiu vestido de preto e amarelo."""
    from fm.importer.build import carregar_cores

    brasileiras = carregar_cores("brasil_serie_b")
    espanholas = carregar_cores("espanha_primera")
    # desde 25/09/2026 o de Sao Joao del-Rei se chama "Athletic-MG": escudo e camisa sao
    # procurados pelo nome em qualquer divisao, e so o escopo das cores nao bastava
    assert "Athletic-MG" in brasileiras
    assert "Athletic Club" not in brasileiras
    # desde 28/09/2026 a Espanha tem cores (geradas): o Athletic dela e o Bilbao, vermelho
    # e branco -- nunca o preto e amarelo do Athletic-MG
    assert espanholas["Athletic Club"]["primaria"] != brasileiras["Athletic-MG"]["primaria"]


def test_reaplicar_cores_nao_toca_nos_jogadores(tmp_path):
    """O comando existe para nao ter de reimportar. Se ele mexesse no elenco, reimportar
    seria mais seguro -- e o ponto dele se perderia."""
    from fm.importer.build import PACKS_DIR, reaplicar_cores

    origem = PACKS_DIR / "brasil_serie_a.toml"
    copia = tmp_path / "brasil_serie_a.toml"
    copia.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")
    antes = origem.read_text(encoding="utf-8")

    reaplicar_cores([copia])
    depois = copia.read_text(encoding="utf-8")

    def so_jogadores(texto: str) -> list[str]:
        return [ln for ln in texto.splitlines() if ln.startswith("  ")]

    assert so_jogadores(antes) == so_jogadores(depois), "o elenco mudou"
    assert depois.count("[[clubes]]") == antes.count("[[clubes]]")
    # e e idempotente: rodar duas vezes nao duplica as linhas de cor
    reaplicar_cores([copia])
    assert copia.read_text(encoding="utf-8").count("padrao = ") == depois.count("padrao = ")
