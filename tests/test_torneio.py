"""Competicoes de copa: entrada escalonada, rodadas e regras proprias de fase."""

from __future__ import annotations

import numpy as np
import pytest

from fm.competition import knockout_tie
from fm.config import load_league
from fm.generate import build_world
from fm.match import Mentality, Style
from fm.torneio import (
    _fase_mata_mata,
    carregar,
    disponiveis,
    resolver_entradas,
    simular,
)


@pytest.fixture(scope="module")
def mundo():
    ligas = [load_league(n) for n in ("brasil_real", "brasil_b_real")]
    world, _ = build_world(ligas, seed=11)
    tabelas = {}
    for cfg in ligas:
        liga = world.leagues[cfg["id"]]
        ordem = sorted(liga.club_ids,
                       key=lambda c: -world.clubs[c].designed_strength)
        tabelas[cfg["id"]] = ordem
        tabelas[liga.codigo] = ordem
    return world, tabelas


def test_todos_os_torneios_do_disco_carregam():
    assert disponiveis()
    for nome in disponiveis():
        t = carregar(nome)
        assert t.fases or t.qualificados_de
        assert t.style.goals_base > 0


def test_entrada_por_faixa_de_classificacao(mundo):
    world, tabelas = mundo
    entram = resolver_entradas(world, [{"liga": "BRA1", "de": 13, "ate": 20}], tabelas)
    assert len(entram) == 8
    assert entram == tabelas["BRA1"][12:20]


def test_quem_entra_depois_nao_joga_as_fases_anteriores(mundo):
    """A PROPRIEDADE do item: clube declarado na 3a fase nao pode cair na 1a."""
    world, tabelas = mundo
    t = carregar("copa_do_brasil")
    cedo = set(resolver_entradas(world, t.fases[0].get("entram", []), tabelas))
    tarde = set(resolver_entradas(world, t.fases[-1].get("entram", []), tabelas))
    assert cedo and tarde
    assert not (cedo & tarde), "clube entrando em duas fases diferentes"
    # os que entram tarde sao os mais fortes: e o ponto de entrar tarde
    forca = lambda ids: np.mean([world.clubs[c].designed_strength for c in ids])  # noqa: E731
    assert forca(tarde) > forca(cedo)


def test_rodadas_limita_a_fase(mundo):
    """Sem isso, uma fase rodava ate sobrar um e ninguem podia entrar no meio."""
    world, _ = mundo
    clubes = list(world.clubs)[:16]
    rng = np.random.default_rng(3)
    uma = _fase_mata_mata(world, clubes, {"rodadas": 1, "maos": 2}, rng, Style(),
                          Mentality.CUP)
    assert len(uma) == 8
    todas = _fase_mata_mata(world, clubes, {"maos": 2}, np.random.default_rng(3), Style(),
                            Mentality.CUP)
    # a fase que vai ate o fim devolve [campeao, vice]: fonte de classificacao precisa
    # do vice (o da Copa do Brasil leva vaga na pre-Libertadores)
    assert len(todas) == 2
    assert todas[0] != todas[1]


def test_bye_e_sorteado_e_nao_premia_o_mais_forte(mundo):
    """Dar o bye ao mais forte inflava o favorito de 12,6% para 40,8% dos titulos."""
    world, tabelas = mundo
    clubes = tabelas["BRA1"][:9]          # numero impar: alguem passa sem jogar
    forte = clubes[0]
    sobreviveu = sum(
        forte in _fase_mata_mata(world, list(clubes), {"rodadas": 1, "maos": 1},
                                 np.random.default_rng(seed), Style(), Mentality.CUP)
        for seed in range(60))
    assert sobreviveu < 58, "o mais forte quase sempre passou: bye nao esta sorteado"


def test_visitante_avanca_no_empate():
    """Regra das duas primeiras fases da Copa do Brasil, de nenhum outro torneio."""
    n = 40_000
    ratings = {1: 70.0, 2: 70.0}
    rng = np.random.default_rng(4)
    com = knockout_tie([1] * n, [2] * n, ratings, rng, Style(), Mentality.CUP, legs=1,
                       empate_favorece_visitante=True)
    sem = knockout_tie([1] * n, [2] * n, ratings, np.random.default_rng(4), Style(),
                       Mentality.CUP, legs=1)
    # `home_first` = 1 manda na unica partida em `sem`; com a regra, o empate vai para 1
    assert np.mean(com == 1) > np.mean(sem == 1) + 0.05


def test_copa_do_brasil_roda_de_ponta_a_ponta(mundo):
    world, tabelas = mundo
    t = carregar("copa_do_brasil")
    fim = simular(world, t, np.random.default_rng(9), elenco=[], tabelas=tabelas)
    assert len(fim) == 2, "copa tem de devolver campeao e vice"
    campeao, vice = fim
    assert campeao in world.clubs
    assert vice in world.clubs
    assert campeao != vice


def test_cascata_de_vagas_quando_o_campeao_da_copa_ja_esta_classificado(mundo):
    """A regra que o Paulo descreveu, e que a CBF confirma.

    Vaga direta: 1o ao 4o do Brasileirao + campeao da Copa do Brasil.
    Segunda fase (era a "pre" ate 30/09/2026): 5o e 6o do Brasileirao.

    Se o campeao da Copa for o 2o colocado, ele ja estava classificado: a 4a vaga direta
    desce para o 5o e as da segunda fase passam para o 6o e o 7o.
    """
    from fm.torneio import resolver_classificacao
    world, tabelas = mundo
    t = carregar("libertadores")
    bra = tabelas["BRA1"]
    liga_bra = world.clubs[bra[0]].league_id

    def do_brasileirao(clubes):
        return [bra.index(c) + 1 for c in clubes
                if world.clubs[c].league_id == liga_bra]

    # campeao da Copa fora do G4 (10o): nada cascateia
    fora = resolver_classificacao(world, t, tabelas,
                                  {"copa_do_brasil": [bra[9], bra[14]]})
    assert sorted(do_brasileirao(fora["grupos"])) == [1, 2, 3, 4, 10]
    assert sorted(do_brasileirao(fora["segunda"])) == [5, 6]

    # campeao da Copa e o 2o colocado: o 5o sobe para direta e a pre vira o 6o
    dentro = resolver_classificacao(world, t, tabelas,
                                    {"copa_do_brasil": [bra[1], bra[14]]})
    assert sorted(do_brasileirao(dentro["grupos"])) == [1, 2, 3, 4, 5]
    assert sorted(do_brasileirao(dentro["segunda"])) == [6, 7]


def test_ninguem_se_classifica_duas_vezes(mundo):
    from fm.torneio import resolver_classificacao
    world, tabelas = mundo
    t = carregar("libertadores")
    r = resolver_classificacao(world, t, tabelas,
                               {"copa_do_brasil": [tabelas["BRA1"][1], tabelas["BRA1"][3]]})
    todos = [c for lista in r.values() for c in lista]
    assert len(todos) == len(set(todos)), "clube ocupando duas vagas"


def test_liga_suica_reproduz_a_regra_do_sorteio():
    """Formato da Champions desde 2024-25. As quatro propriedades da regra real."""
    from collections import Counter

    from fm.competition import liga_suica
    ids = list(range(1, 37))
    fixtures = liga_suica(ids, adversarios=8, potes=4)

    assert len(fixtures) == 36 * 8 // 2
    jogos, casa, advs = Counter(), Counter(), {i: set() for i in ids}
    for f in fixtures:
        jogos[f.home] += 1
        jogos[f.away] += 1
        casa[f.home] += 1
        advs[f.home].add(f.away)
        advs[f.away].add(f.home)
    assert set(jogos.values()) == {8}, "cada clube joga 8 partidas"
    assert set(casa.values()) == {4}, "metade em casa"
    assert {len(v) for v in advs.values()} == {8}, "8 adversarios DIFERENTES"

    # os potes sao por forca; cada clube pega 2 de cada pote
    pote = {c: ids.index(c) // 9 for c in ids}
    por_clube = {tuple(sorted(Counter(pote[a] for a in advs[c]).values())) for c in ids}
    assert por_clube == {(2, 2, 2, 2)}, "2 adversarios de cada pote, como no sorteio real"

    # REGRESSAO: cada rodada tem cada clube UMA vez. O gerador antigo punha dois jogos do
    # mesmo clube na mesma rodada, e a fase de liga andava de duas em duas rodadas
    assert sorted({f.matchday for f in fixtures}) == list(range(1, 9))
    for rodada in range(1, 9):
        clubes = [c for f in fixtures if f.matchday == rodada for c in (f.home, f.away)]
        assert sorted(clubes) == ids, f"rodada {rodada}: clube repetido ou faltando"


@pytest.mark.parametrize("n", [36, 34, 32, 30, 24, 18, 16, 10, 6])
def test_liga_suica_em_qualquer_tamanho_de_mundo(n):
    """Mundo com menos clubes (so alguns paises marcados): a regra da rodada vale sempre,
    mesmo quando os potes nao dividem por igual."""
    from collections import Counter

    from fm.competition import liga_suica
    ids = list(range(100, 100 + n))
    k = min(8, n - 2)
    fixtures = liga_suica(ids, adversarios=k, potes=4)
    for rodada in range(1, k + 1):
        clubes = [c for f in fixtures if f.matchday == rodada for c in (f.home, f.away)]
        assert sorted(clubes) == ids
    pares = {frozenset((f.home, f.away)) for f in fixtures}
    assert len(pares) == len(fixtures), "adversario repetido"
    casa = Counter(f.home for f in fixtures)
    assert set(casa.values()) == {k // 2}, "metade em casa"


def test_liga_suica_recusa_pedido_impossivel():
    from fm.competition import liga_suica
    with pytest.raises(ValueError):
        liga_suica(list(range(10)), adversarios=7)      # impar
    with pytest.raises(ValueError):
        liga_suica(list(range(10)), adversarios=10)     # mais que o numero de rivais
    with pytest.raises(ValueError):
        liga_suica(list(range(9)), adversarios=4)       # numero impar de clubes


def test_isentos_pulam_a_fase(mundo):
    """1o ao 8o da fase de liga da Champions vao direto as oitavas, sem playoff."""
    world, tabelas = mundo
    clubes = tabelas["BRA1"][:12]
    sobrou = _fase_mata_mata(world, clubes, {"rodadas": 1, "maos": 2, "isentos": 8},
                             np.random.default_rng(2), Style(), Mentality.CUP)
    assert sobrou[:8] == clubes[:8], "os isentos tem de passar intactos e na ordem"
    assert len(sobrou) == 8 + 2, "os outros 4 viraram 2"


def test_champions_esta_no_formato_atual():
    """Guarda contra voltar ao formato de 8 grupos de 4, abolido em 2024-25."""
    t = carregar("champions")
    tipos = [f.get("tipo") for f in t.fases]
    assert "liga_suica" in tipos, "a Champions tem de usar fase de liga, nao grupos"
    assert "groups" not in tipos, "8 grupos de 4 acabou em 2024-25"
    liga = next(f for f in t.fases if f.get("tipo") == "liga_suica")
    assert liga["adversarios"] == 8
    assert liga["avancam"] == 24
    playoff = next(f for f in t.fases if f.get("isentos"))
    assert playoff["isentos"] == 8
    diretas = sum(r["vagas"] for r in t.classificacao_regras if r["entra_em"] == "liga")
    pre = sum(r["vagas"] for r in t.classificacao_regras if r["entra_em"] == "pre")
    assert diretas == 28
    assert pre == 16, "16 na pre, 8 passam: 28 + 8 = 36"


def test_funil_da_libertadores_para_a_sudamericana():
    """O 3o de cada grupo da Libertadores cai para o playoff da Sudamericana (contra os 2os
    dela), e quem perde a terceira fase vai para os grupos dela."""
    lib, sul = carregar("libertadores"), carregar("sudamericana")
    grupos = next(f for f in lib.fases if f.get("tipo") == "groups")
    assert grupos["exporta"] == [{"posicao": 3, "para": "terceiros"}]
    recebe = [r for r in sul.classificacao_regras
              if r["fonte"] == "libertadores:terceiros"]
    assert recebe and recebe[0]["entra_em"] == "playoff"
    assert recebe[0]["vagas"] == 8

    pre = next(f for f in lib.fases if f.get("exporta") and f.get("tipo") == "knockout")
    assert pre["nome"] == "Terceira fase"
    assert pre["exporta"] == [{"eliminados": True, "para": "eliminados_pre"}]
    assert any(r["fonte"] == "libertadores:eliminados_pre"
               for r in sul.classificacao_regras)


def test_a_fase_de_liga_da_champions_nao_derruba_ninguem():
    """Regressao da mudanca de 2024-25: o 3o de grupo NAO cai mais para a Europa League.

    Do 25o ao 36o da fase de liga todos estao eliminados. O unico funil europeu que
    sobrou e a qualificacao: quem perde a pre da Champions entra na Europa.
    """
    cl, el = carregar("champions"), carregar("europa_league")
    liga = next(f for f in cl.fases if f.get("tipo") == "liga_suica")
    assert not liga.get("exporta"), "a fase de liga nao pode derrubar ninguem"
    pre = next(f for f in cl.fases if f.get("rodadas") == 1)
    assert pre["exporta"] == [{"eliminados": True, "para": "eliminados_pre"}]
    assert any(r["fonte"] == "champions:eliminados_pre"
               for r in el.classificacao_regras)


def test_vaga_e_unica_na_temporada(mundo):
    """Quem pega vaga na Champions sai da lista da Europa. Sem isso o Real Madrid
    disputava as duas ao mesmo tempo."""
    from fm.torneio import resolver_classificacao
    world, tabelas = mundo
    ocupados: set[int] = set()
    a = resolver_classificacao(world, carregar("libertadores"), tabelas, {}, ocupados)
    b = resolver_classificacao(world, carregar("sudamericana"), tabelas, {}, ocupados)
    da_liberta = {c for lista in a.values() for c in lista}
    da_sula = {c for lista in b.values() for c in lista}
    assert da_liberta and da_sula
    assert not (da_liberta & da_sula), "clube em duas competicoes continentais"


def test_toda_fonte_entre_copas_tem_quem_exporte():
    """`fonte = "libertadores:terceiros"` e `aguarda` tem de bater com o `torneio:para` de
    alguem. REGRESSAO: a chave era so `para`, e a Champions e a Libertadores exportavam as
    duas para "eliminados_pre" -- o eliminado de uma caia na copa da outra."""
    from fm.torneio import TORNEIOS_DIR, carregar

    torneios = [carregar(p.stem) for p in TORNEIOS_DIR.glob("*.toml")]
    exportadas = {f"{t.id}:{r['para']}" for t in torneios for f in t.fases
                  for r in f.get("exporta", [])}
    pedidas = ({r["fonte"] for t in torneios for r in t.classificacao_regras
                if ":" in r.get("fonte", "")}
               | {f["aguarda"] for t in torneios for f in t.fases if f.get("aguarda")})
    assert pedidas, "nenhuma copa recebe clubes de outra?"
    assert pedidas <= exportadas, f"sem exportador: {pedidas - exportadas}"


def test_a_champions_tem_36_na_fase_de_liga_com_a_europa_inteira():
    """Com as ligas que faltavam (03/10/2026), a fase de liga fecha com 36 clubes de verdade:
    28 diretos e 8 da pre. Antes ficava com ~23 -- faltavam Holanda, Belgica, Escocia..."""
    from collections import Counter

    from fm.carreira import Carreira
    from fm.telas import NACIONAIS

    europa = [k for n in NACIONAIS if n.get("livre") and n["pais"] not in
              ("BRA", "ARG", "COL", "CHI", "URU", "ECU", "PAR", "PER", "BOL", "VEN")
              for k, _ in n["ligas"]]
    c = Carreira.nova(europa, "Celtic", seed=4)
    a = c.copas["champions"]
    assert {f: len(v) for f, v in a.classificados.items()} == {"liga": 28, "pre": 16}
    paises = Counter(c.world.clubs[k].country for v in a.classificados.values() for k in v)
    assert "RUS" not in paises, "a UEFA exclui os clubes russos desde 2022"
    assert {"NED", "BEL", "SCO", "TUR", "CZE"} <= set(paises)
