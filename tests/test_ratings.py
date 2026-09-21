"""Conversao valor de mercado -> overall, e os diagnosticos que a validam."""

from __future__ import annotations

from pathlib import Path

import pytest

from fm.diagnostics import diagnosticar
from fm.pack import load_pack
from fm.ratings import (
    BETA,
    K_POS,
    OVR_MAX,
    converter_elenco,
    correcao_idade,
    forca_dos_clubes,
    valor_qualidade,
)

FM_DIR = Path(__file__).resolve().parent.parent / "fm"


def _elenco(mudanca=None):
    base = [
        {"nome": "GK1", "posicao": "GK", "idade": 29, "valor": 3_500_000, "partidas": 34},
        {"nome": "GK2", "posicao": "GK", "idade": 33, "valor": 700_000, "partidas": 4},
        {"nome": "CB1", "posicao": "CB", "idade": 27, "valor": 6_000_000, "partidas": 33},
        {"nome": "CB2", "posicao": "CB", "idade": 31, "valor": 2_500_000, "partidas": 28},
        {"nome": "CB3", "posicao": "CB", "idade": 20, "valor": 4_000_000, "partidas": 6},
        {"nome": "FB1", "posicao": "FB", "idade": 26, "valor": 5_000_000, "partidas": 31},
        {"nome": "FB2", "posicao": "FB", "idade": 30, "valor": 3_000_000, "partidas": 29},
        {"nome": "DM1", "posicao": "DM", "idade": 28, "valor": 7_000_000, "partidas": 32},
        {"nome": "AM1", "posicao": "AM", "idade": 25, "valor": 14_000_000, "partidas": 30},
        {"nome": "MF1", "posicao": "MF", "idade": 23, "valor": 6_500_000, "partidas": 22},
        {"nome": "AM2", "posicao": "AM", "idade": 24, "valor": 25_000_000, "partidas": 31},
        {"nome": "WG1", "posicao": "WG", "idade": 22, "valor": 12_000_000, "partidas": 27},
        {"nome": "FW1", "posicao": "FW", "idade": 28, "valor": 11_000_000, "partidas": 30},
        {"nome": "WG2", "posicao": "WG", "idade": 18, "valor": 9_000_000, "partidas": 3},
        {"nome": "FW2", "posicao": "FW", "idade": 34, "valor": 1_200_000, "partidas": 18},
        {"nome": "MF2", "posicao": "MF", "idade": 26, "valor": 2_000_000, "partidas": 12},
    ]
    for j in base:
        j.update((mudanca or {}).get(j["nome"], {}))
    return base


def _por_nome(saida):
    return {j["nome"]: j for j in saida}


def test_ancora_no_forca_do_clube():
    """A media do melhor onze tem de cair exatamente no forca desenhado."""
    for forca in (58.0, 72.0, 82.0):
        s = converter_elenco(_elenco(), forca)
        xi = [j["ovr"] for j in s if j["titular"]]
        assert len(xi) == 11
        assert abs(sum(xi) / 11 - forca) < 1.0


def test_goleiro_barato_nao_vira_jogador_ruim():
    """O mercado paga menos por goleiro; a correcao de posicao equaliza a QUALIDADE."""
    s = _por_nome(converter_elenco(_elenco(), 82.0))
    assert s["GK1"]["valor"] < s["DM1"]["valor"]          # vale menos
    assert abs(s["GK1"]["ovr"] - s["DM1"]["ovr"]) <= 3    # mas joga igual
    assert s["GK1"]["titular"]


def test_sem_correcao_de_posicao_o_goleiro_afunda():
    """Prova que a correcao faz diferenca, e nao e enfeite."""
    com = _por_nome(converter_elenco(_elenco(), 82.0))["GK1"]["ovr"]
    original = dict(K_POS)
    try:
        K_POS.update(dict.fromkeys(K_POS, 1.0))
        sem = _por_nome(converter_elenco(_elenco(), 82.0))["GK1"]["ovr"]
    finally:
        K_POS.clear()
        K_POS.update(original)
    assert com > sem + 2


def test_veterano_nao_estoura_a_escala():
    """Com W=1 (dividir pelo multiplicador inteiro) um 33 anos de 10 mi virava OVR 94.

    O mercado desconta velho tambem porque ele DECLINOU, e essa parte nao pode ser
    devolvida como qualidade.
    """
    velho = _elenco()
    velho.append({"nome": "V", "posicao": "AM", "idade": 33, "valor": 10_000_000,
                  "partidas": 30})
    s = _por_nome(converter_elenco(velho, 82.0))
    assert s["V"]["ovr"] <= 91
    # o multiplicador e MENOR para o veterano (por isso dividir por ele infla a
    # qualidade-equivalente), mas amolecido por W e limitado por CORR_MAX
    assert correcao_idade(33) < correcao_idade(27)
    assert correcao_idade(36) >= 0.5                 # teto de 2x na inflacao


def test_jovem_tem_potencial_acima_do_overall():
    s = _por_nome(converter_elenco(_elenco(), 82.0))
    assert s["WG2"]["pot"] - s["WG2"]["ovr"] >= 8     # 18 anos, quase sem jogar
    assert s["FW2"]["pot"] == s["FW2"]["ovr"]         # 34 anos: nao cresce mais


def test_quem_ja_e_titular_quase_nao_leva_desconto_de_imaturidade():
    """Caso real: o mais valioso da Serie A, 21 anos, temporada inteira jogada."""
    dois = _elenco({"WG2": {"partidas": 30}})
    joga = _por_nome(converter_elenco(dois, 82.0))["WG2"]
    banco = _por_nome(converter_elenco(_elenco(), 82.0))["WG2"]
    assert joga["ovr"] > banco["ovr"] + 5


def test_nenhum_overall_absurdo():
    monstro = _elenco({"AM2": {"valor": 500_000_000}})
    s = converter_elenco(monstro, 82.0)
    assert max(j["ovr"] for j in s) <= OVR_MAX


def test_valor_qualidade_equaliza_posicao():
    """Mesmo valor bruto, posicoes diferentes -> qualidades diferentes, na ordem certa."""
    gk = valor_qualidade(10_000_000, "GK", 27)
    fw = valor_qualidade(10_000_000, "FW", 27)
    assert gk > fw


def test_forca_dos_clubes_media_nao_muda_ordem_nem_spread():
    """`media` so desloca: o motor usa DIFERENCA de forca, entao ela e cosmetica."""
    v = {"a": 200_000_000, "b": 100_000_000, "c": 20_000_000}
    f1 = forca_dos_clubes(v, 70.0, 6.0)
    f2 = forca_dos_clubes(v, 78.0, 6.0)
    assert [f1[k] + 8 for k in v] == [f2[k] for k in v]
    largo = forca_dos_clubes(v, 70.0, 12.0)
    assert (max(largo.values()) - min(largo.values())) > (max(f1.values()) - min(f1.values()))


def test_beta_e_positivo_e_a_hierarquia_segue_o_valor():
    s = converter_elenco(_elenco(), 72.0)
    caros = sorted(s, key=lambda j: -(j["valor"] or 0))
    assert BETA > 0
    assert caros[0]["ovr"] >= caros[-1]["ovr"]


@pytest.mark.parametrize("nome_pack", ["brasil_serie_a", "brasil_serie_b",
                                       "espanha_primera", "espanha_segunda"])
def test_diagnosticos_passam_nos_packs_reais(nome_pack):
    """Integracao: cada base importada de verdade sobrevive aos cinco diagnosticos."""
    pack = load_pack(nome_pack)
    clubes = [{"nome": c.nome,
               "jogadores": [{"nome": j.nome, "ovr": j.ovr or 0, "posicao": j.pos,
                              "idade": j.idade, "valor": j.valor} for j in c.jogadores]}
              for c in pack.clubes]
    fora = [f"{d.nome}={d.valor:.2f} fora de [{d.baixo}, {d.alto}]"
            for d in diagnosticar(clubes) if not d.ok]
    assert not fora, f"{nome_pack}: " + "; ".join(fora)


def test_piramide_primeira_divisao_e_mais_forte_que_segunda():
    """Normalizar cada liga por si apagava o nivel: o lanterna da Serie B saia mais forte
    que o da Serie A. O nivel entre divisoes vem do valor de elenco na escala global."""
    for primeira, segunda in (("brasil_serie_a", "brasil_serie_b"),
                              ("espanha_primera", "espanha_segunda")):
        fa = [c.forca for c in load_pack(primeira).clubes]
        fb = [c.forca for c in load_pack(segunda).clubes]
        assert min(fa) > min(fb), f"{primeira} vs {segunda}: piramide invertida"
        assert max(fa) > max(fb)


def test_motor_nao_depende_do_importador():
    """Regra de arquitetura: o jogo nao baixa pagina. Nada em fm/ importa bs4 ou urllib."""
    proibidos = []
    for path in FM_DIR.glob("*.py"):
        texto = path.read_text(encoding="utf-8")
        for termo in ("bs4", "BeautifulSoup", "urllib", "requests"):
            if termo in texto:
                proibidos.append(f"{path.name}: {termo}")
    assert not proibidos, f"dependencia de rede no motor: {proibidos}"


def test_teto_por_posicao_comprime_sem_perder_ordem():
    """Normalizar DENTRO do elenco inflava lateral de clube rico: num elenco onde todo
    mundo e caro, ate o lateral reserva subia a 90. O teto comprime em vez de cortar."""
    from fm.ratings import MARGEM_TETO, TETO_POR_POSICAO, aplicar_teto
    teto = TETO_POR_POSICAO["FB"]
    assert aplicar_teto(75.0, "FB") == 75.0                 # abaixo do limiar, intacto
    assert aplicar_teto(75.0, "CB") == 75.0                 # posicao sem teto, intacto
    assert aplicar_teto(120.0, "FB") <= teto                # nunca passa
    baixo = aplicar_teto(teto - MARGEM_TETO + 1, "FB")
    alto = aplicar_teto(teto - MARGEM_TETO + 4, "FB")
    assert baixo < alto <= teto                             # ordem preservada


def test_nenhum_lateral_passa_do_teto_nos_packs():
    for nome_pack in ("brasil_serie_a", "espanha_primera", "espanha_segunda",
                      "brasil_serie_b"):
        for c in load_pack(nome_pack).clubes:
            for j in c.jogadores:
                if j.pos == "FB":
                    assert j.ovr <= 87, f"{j.nome} ({nome_pack}) passou do teto: {j.ovr}"


def test_ajuste_manual_sobrevive_no_pack():
    """O pack e gerado; ajuste feito nele a mao sumiria. O de data/ajustes/ fica."""
    from fm.importer.ajustes import carregar
    ajustes = {a["nome"]: a for a in carregar("brasil_serie_a")}
    assert ajustes, "nenhum ajuste carregado"
    por_nome = {j.nome: j for c in load_pack("brasil_serie_a").clubes for j in c.jogadores}
    for nome, a in ajustes.items():
        assert nome in por_nome, f"ajuste de {nome} nao achou o jogador"
        for campo in ("ovr", "pot"):
            if campo in a:
                assert getattr(por_nome[nome], campo) == a[campo], \
                    f"{nome}.{campo} nao foi aplicado"
        assert a.get("motivo"), f"ajuste de {nome} sem motivo declarado"


def test_ajuste_sem_alvo_levanta_erro():
    """Nome digitado errado tem de doer na hora, nao virar silencio."""
    from types import SimpleNamespace

    import fm.importer.ajustes as mod
    from fm.importer.ajustes import aplicar
    original = mod.carregar
    mod.carregar = lambda _: [{"nome": "Jogador Que Nao Existe", "ovr": 99}]
    try:
        with pytest.raises(ValueError, match="sem alvo"):
            aplicar("qualquer", [SimpleNamespace(nome="Clube", jogadores=[])])
    finally:
        mod.carregar = original
