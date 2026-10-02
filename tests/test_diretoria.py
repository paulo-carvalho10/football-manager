"""Aprovacao da torcida, da diretoria e o risco de demissao.

E a peca que faz a tabela ter consequencia. O que se protege aqui nao e a formula -- e o
comportamento: que a torcida reaja rapido e a diretoria devagar, que a meta seja justa com
o tamanho do clube, e que um tecnico competente nao seja demitido por azar.
"""

from __future__ import annotations

import contextlib

import pytest

from fm.carreira import Carreira
from fm.diretoria import (
    DEMISSAO_NO_ANO,
    Aprovacao,
    Meta,
    _nota_do_dinheiro,
    avaliar,
    decidir_demissao,
    definir_meta,
)
from fm.tatica import Tatica

LIGAS = ["brasil_real", "brasil_b_real"]


@pytest.fixture
def carreira():
    return Carreira.nova(LIGAS, "Santos", seed=42)


def _mover(aprovacao, vezes, **kw):
    for _ in range(vezes):
        avaliar(aprovacao, **kw)
    return aprovacao


# ------------------------------------------------------------------ a meta

def test_a_meta_acompanha_o_tamanho_do_clube(carreira):
    """Cobrar titulo de todo mundo demitiria o usuario de um clube pequeno por ser pequeno."""
    c = carreira
    from fm.config import load_league
    ids = list(c.world.leagues[load_league("brasil_real")["id"]].club_ids)
    grande = max(ids, key=lambda i: c.world.team_rating(i))
    pequeno = min(ids, key=lambda i: c.world.team_rating(i))

    meta_grande = definir_meta(c.world, grande, ids)
    meta_pequeno = definir_meta(c.world, pequeno, ids)
    assert meta_grande.posicao < meta_pequeno.posicao
    assert meta_grande.posicao <= 5, "o maior elenco da liga tem de brigar em cima"
    assert meta_pequeno.posicao >= len(ids) - 5, "o menor nao pode ser cobrado de titulo"
    assert meta_grande.texto and meta_pequeno.texto


def test_a_meta_e_definida_toda_temporada(carreira):
    c = carreira
    primeira = c.aprovacao.meta.posicao
    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    assert c.aprovacao.meta is not None
    assert isinstance(c.aprovacao.meta, Meta)
    del primeira


# ------------------------------------------------------------------ as duas aprovacoes

def test_a_torcida_reage_mais_rapido_que_a_diretoria():
    """E a diferenca de temperamento que produz as situacoes interessantes."""
    a = Aprovacao(torcida=60, diretoria=60, meta=Meta(6, "top 6"))
    _mover(a, 3, posicao=20, clubes=20, ultimos=["D"] * 6,
           campanhas=[(1, 6, False), (1, 7, False)],
           receita=40_000_000, folha=18_000_000)
    assert a.torcida < a.diretoria, "a diretoria nao pode desabar antes da torcida"
    assert a.torcida < 45


def test_ganhar_acalma_os_dois():
    a = Aprovacao(torcida=30, diretoria=30, meta=Meta(6, "top 6"))
    _mover(a, 6, posicao=2, clubes=20, ultimos=["V"] * 6,
           campanhas=[(6, 6, True), (5, 7, True)],
           receita=40_000_000, folha=18_000_000)
    assert a.torcida > 60 and a.diretoria > 55


def test_a_torcida_nao_liga_para_o_caixa():
    """Ela e' emocional: mesmos resultados, caixas opostos, mesma aprovacao."""
    comum = dict(posicao=8, clubes=20, ultimos=["V", "E", "V"],
                 campanhas=[(4, 6, True)])
    rico = _mover(Aprovacao(meta=Meta(8, "x")), 5, **comum,
                  receita=40_000_000, folha=10_000_000, caixa=90_000_000)
    quebrado = _mover(Aprovacao(meta=Meta(8, "x")), 5, **comum,
                      receita=40_000_000, folha=44_000_000, caixa=-30_000_000)
    assert abs(rico.torcida - quebrado.torcida) < 0.01
    # a margem e' modesta porque a diretoria tem inercia: cinco avaliacoes percorrem menos
    # da metade do caminho ate o alvo, de proposito
    assert rico.diretoria > quebrado.diretoria + 5, "a diretoria tem de ver o caixa"


def test_o_dinheiro_mal_usado_pesa_na_diretoria():
    saudavel = _nota_do_dinheiro(saldo=8_000_000, receita=40_000_000,
                                 caixa=50_000_000, folha=16_000_000)
    gastador = _nota_do_dinheiro(saldo=-15_000_000, receita=40_000_000,
                                 caixa=-20_000_000, folha=44_000_000)
    assert saudavel > 65, f"clube saudavel tirou so {saudavel:.1f}"
    assert gastador < 25, f"clube gastador tirou {gastador:.1f}"


def test_ir_bem_na_copa_conta(carreira):
    comum = dict(posicao=10, clubes=20, ultimos=["E"] * 4,
                 receita=40_000_000, folha=18_000_000)
    longe = _mover(Aprovacao(meta=Meta(10, "x")), 5, **comum,
                   campanhas=[(6, 6, True), (5, 6, True)])
    cedo = _mover(Aprovacao(meta=Meta(10, "x")), 5, **comum,
                  campanhas=[(1, 6, False), (1, 6, False)])
    assert longe.torcida > cedo.torcida
    assert longe.diretoria > cedo.diretoria


# ------------------------------------------------------------------ demissao

def test_rebaixamento_demite_sozinho():
    a = Aprovacao(torcida=90, diretoria=90, meta=Meta(16, "escapar"))
    assert decidir_demissao(a, rodada=38, fim_da_temporada=True, posicao=18,
                            clubes=20, rebaixado=True) == "rebaixamento"


def test_ninguem_e_demitido_na_terceira_rodada():
    """Carencia: uma temporada precisa tomar forma antes de virar julgamento."""
    a = Aprovacao(torcida=5, diretoria=5, meta=Meta(4, "top 4"))
    assert decidir_demissao(a, rodada=3, fim_da_temporada=False,
                            posicao=20, clubes=20) is None


def test_a_meta_cumprida_segura_o_emprego():
    a = Aprovacao(torcida=45, diretoria=DEMISSAO_NO_ANO + 1, meta=Meta(10, "top 10"))
    assert decidir_demissao(a, rodada=38, fim_da_temporada=True,
                            posicao=7, clubes=20) is None


def test_o_tecnico_ruim_e_demitido_e_o_bom_nao():
    """O teste que importa: o sistema tem de separar competencia de azar."""
    def carreira_de(clube, ruim, anos=3):
        c = Carreira.nova(LIGAS, clube, seed=42)
        for _ in range(anos):
            # os piores sao RECALCULADOS a cada temporada: depois do mercado e das
            # aposentadorias metade daqueles ids nao existe mais, a escalacao falha em
            # silencio e o time volta a jogar bem -- o teste passava a testar nada
            piores = [p.id for p in sorted(c.world.squad(c.clube_id),
                                           key=lambda p: p.overall)[:11]]
            while not c.acabou and not c.demitido:
                if ruim:
                    with contextlib.suppress(ValueError):
                        c.escalar(piores, Tatica(estilo="ofensivo", marcacao="leve"))
                else:
                    _automatica(c)
                c.avancar()
            if c.demitido:
                return True
            if not ruim:
                _renovar_os_principais(c)
            if c.virar_o_ano()["demitido"]:
                return True
        return False

    def _automatica(c):
        """O botao "Automatica" a cada data: reescala pelo cansaco. A escalacao do usuario
        vale ate ele mudar, e os mesmos onze em toda liga, Copa do Brasil e Libertadores
        afundam de cansaco -- quem rodava o time por ele era, sem querer, a janela da IA,
        que trocava o elenco na virada."""
        from fm.tatica import arrumar_no_campo
        t = c.tatica_atual()
        c.world.escalacao_fixa.pop(c.clube_id, None)
        onze = arrumar_no_campo(c.world.best_xi(c.clube_id, t.vagas), t.vagas_do_campo())
        with contextlib.suppress(ValueError):
            c.escalar([p.id for p in onze], t)

    def _renovar_os_principais(c):
        """O tecnico competente cuida do elenco. Antes a janela da IA repunha os jogadores
        do usuario sem pedir; desde que ela nao toca no elenco dele, quem nunca renova
        perde metade do time em tres anos -- e e demitido com razao."""
        from fm.negocios import interesse_em_renovar
        for p in sorted(c.world.squad(c.clube_id), key=lambda p: -p.overall)[:20]:
            if p.contract_until > c.temporada or p.loan_from is not None:
                continue
            pedido = interesse_em_renovar(c, p)["pretendido"]
            if pedido:
                c.executar({"tipo": "renovacao", "jogador": p.id, "salario": pedido,
                            "anos": 3})

    assert carreira_de("Palmeiras", ruim=True), "escalar os piores nao custou o emprego"
    assert not carreira_de("Palmeiras", ruim=False), "tecnico competente foi demitido"


def test_a_demissao_trava_o_jogo(carreira):
    c = carreira
    c.aprovacao.demitido = True
    c.aprovacao.motivo = "teste"
    assert c.demitido
    # o resumo do ano tem de registrar, para a tela poder contar
    while not c.acabou:
        c.avancar()
    r = c.virar_o_ano()
    assert r["demitido"] is True
    assert r["motivo_da_demissao"]


def test_o_clima_tem_nome(carreira):
    for t, d, esperado in ((90, 90, "idolatrado"), (70, 70, "tranquilo"),
                           (50, 70, "sob observacao"), (30, 70, "pressionado"),
                           (10, 70, "insustentavel")):
        assert Aprovacao(torcida=t, diretoria=d).clima == esperado


def test_o_resumo_do_ano_traz_o_veredito(carreira):
    c = carreira
    while not c.acabou:
        c.avancar()
    r = c.virar_o_ano()
    assert "clima" in r
    assert set(r["clima"]) == {"torcida", "diretoria", "meta", "bateu_a_meta"}
    assert 0 <= r["clima"]["torcida"] <= 100


def test_a_aprovacao_atravessa_o_save(carreira):
    """O save guarda semente e decisoes, nao o estado: a aprovacao tem de ser reconstruida
    pelo replay, exatamente. Se ela divergir, o usuario volta para um clube onde o clima e'
    outro -- e clima e' o que decide se ele ainda tem emprego."""
    c = carreira
    for _ in range(25):
        c.avancar()
    caminho = c.salvar("teste_diretoria_pytest")
    try:
        volta = Carreira.carregar("teste_diretoria_pytest")
        assert volta.aprovacao.torcida == c.aprovacao.torcida
        assert volta.aprovacao.diretoria == c.aprovacao.diretoria
        assert volta.aprovacao.meta.posicao == c.aprovacao.meta.posicao
        assert volta.demitido == c.demitido
    finally:
        caminho.unlink()


def test_cair_na_final_nao_e_o_mesmo_que_cair_na_primeira_fase():
    """REGRESSAO: a nota contava ELIMINACOES, e em qualquer copa 31 dos 32 clubes sao
    eliminados. A torcida de todo mundo terminava o ano deprimida, e um time que cumpriu a
    meta na liga fechava com 36% de aprovacao."""
    from fm.diretoria import _nota_das_copas

    final = _nota_das_copas([(6, 6, False)])
    primeira = _nota_das_copas([(1, 6, False)])
    campeao = _nota_das_copas([(6, 6, False)], titulos=1)
    assert campeao == 100.0
    assert final > primeira + 30
    assert primeira > 0, "ate quem cai cedo participou"
    assert _nota_das_copas([]) == 50.0, "sem copa, neutro"
