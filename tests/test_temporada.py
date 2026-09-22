"""A virada do ano. O teste que impede o mundo de derreter sem ninguem notar.

O risco aqui nao e o erro que quebra: e a DERIVA. Um balanco errado entre quem sai e quem
chega nao levanta excecao nenhuma -- so faz o nivel do mundo escorregar meio ponto por
temporada, ate que na decima o motor esteja calibrado para um futebol que nao existe mais.
Por isso este arquivo mede 20 temporadas e compara o fim com o comeco.
"""

from __future__ import annotations

import statistics as st

import pytest

from fm.carreira import Carreira
from fm.config import load_league

LIGAS = ["brasil_real", "brasil_b_real"]


def _onzes(c: Carreira, liga: str = "brasil_real") -> list[float]:
    lid = load_league(liga)["id"]
    return [c.world.team_rating(cid) for cid in c.world.leagues[lid].club_ids]


@pytest.fixture(scope="module")
def vinte_temporadas():
    """Roda 20 anos uma vez so e serve a foto a todos os testes -- e caro."""
    c = Carreira.nova(LIGAS, "Santos", seed=7)
    inicio = _onzes(c)
    for _ in range(20):
        while not c.acabou:
            c.avancar()
        c.virar_o_ano()
    return c, inicio


def test_o_ano_vira_e_a_temporada_seguinte_comeca():
    c = Carreira.nova(LIGAS, "Santos", seed=42)
    with pytest.raises(RuntimeError, match="faltam"):
        c.virar_o_ano()
    while not c.acabou:
        c.avancar()
    resumo = c.virar_o_ano()
    assert c.temporada == 2028
    assert c.rodada == 0
    assert not c.acabou, "calendario novo nao foi montado"
    assert resumo["campeoes"]["brasil_real"]
    assert all(p.condition == 100 for p in c.world.players.values())


def test_quem_cai_troca_de_divisao_com_quem_sobe():
    c = Carreira.nova(LIGAS, "Santos", seed=42)
    a, b = (load_league(n)["id"] for n in LIGAS)
    while not c.acabou:
        c.avancar()
    tamanhos = (len(c.world.leagues[a].club_ids), len(c.world.leagues[b].club_ids))
    ultimos = {r.club_id for r in c.tabela("brasil_real")[-4:]}
    primeiros = {r.club_id for r in c.tabela("brasil_b_real")[:4]}
    c.virar_o_ano()
    assert ultimos <= set(c.world.leagues[b].club_ids), "rebaixado ficou na primeira"
    assert primeiros <= set(c.world.leagues[a].club_ids), "promovido ficou na segunda"
    assert (len(c.world.leagues[a].club_ids), len(c.world.leagues[b].club_ids)) == tamanhos
    for cid in ultimos | primeiros:
        liga = c.world.clubs[cid].league_id
        assert cid in c.world.leagues[liga].club_ids, "clube fora da propria liga"


def test_o_mundo_nao_derrete_em_vinte_temporadas(vinte_temporadas):
    """REGRESSAO: a base entregava garotos com potencial = 0.85x a forca do clube, entao
    cada geracao nascia 15% pior que a anterior e o onze medio da Serie A caia de 69.7
    para 59.2 em 20 anos -- silenciosamente, com todos os outros testes passando."""
    c, inicio = vinte_temporadas
    fim = _onzes(c)
    deriva = (st.mean(fim) - st.mean(inicio)) / 20
    assert abs(deriva) < 0.25, (
        f"o nivel do mundo deriva {deriva:+.2f} pontos por temporada: "
        f"{st.mean(inicio):.1f} -> {st.mean(fim):.1f}")
    assert 78 <= max(fim) <= 88, f"melhor onze do Brasil em {max(fim):.1f}"


def test_a_liga_nao_achata_nem_explode(vinte_temporadas):
    """O equilibrio da Serie A e' caracteristica da liga, nao acidente da criacao: tem de
    sobreviver a 20 anos de aposentadoria, base e troca de divisao."""
    c, inicio = vinte_temporadas
    fim = _onzes(c)
    assert st.pstdev(inicio) * 0.7 < st.pstdev(fim) < st.pstdev(inicio) * 1.4


def test_a_demografia_se_mantem(vinte_temporadas):
    """Sem base a idade media sobe ate o mundo ser um asilo; com base demais, um sub-20."""
    c, _ = vinte_temporadas
    idades = [c.temporada - p.birth_year for p in c.world.players.values()]
    assert 25 <= st.mean(idades) <= 28.5, f"idade media {st.mean(idades):.1f}"
    assert max(idades) < 42, "alguem nunca se aposenta"
    assert min(idades) <= 19, "a base parou de entregar"


def test_ninguem_passa_do_proprio_potencial(vinte_temporadas):
    c, _ = vinte_temporadas
    for p in c.world.players.values():
        assert p.overall <= p.potential, f"{p.name} passou do potencial"
        assert 30 <= p.overall <= 95


def test_os_elencos_nao_esvaziam(vinte_temporadas):
    """Aposentadoria tira gente todo ano; se a base nao repoe, em dez anos nao ha onze."""
    c, _ = vinte_temporadas
    for clube in c.world.clubs.values():
        elenco = [i for i in clube.player_ids if i in c.world.players]
        assert len(elenco) >= 18, f"{clube.name} com {len(elenco)} jogadores"
        gols = [i for i in elenco if c.world.players[i].position == "GK"]
        assert gols, f"{clube.name} sem goleiro"


def test_o_titulo_circula(vinte_temporadas):
    """Se um clube ganha 20 de 20, a carreira nao tem sentido: a forca esta congelada."""
    c, _ = vinte_temporadas
    titulos: dict[str, int] = {}
    for ano in c.historico:
        campeao = ano["campeoes"]["brasil_real"]
        titulos[campeao] = titulos.get(campeao, 0) + 1
    assert len(titulos) >= 4, f"so {len(titulos)} campeoes em 20 anos: {titulos}"
    assert max(titulos.values()) <= 10, f"dominio absoluto: {titulos}"


def test_save_atravessa_a_virada_do_ano(tmp_path):
    """O replay refaz as temporadas inteiras. Se a virada nao for deterministica, o save
    devolve um mundo diferente do que o usuario deixou."""
    c = Carreira.nova(LIGAS, "Santos", seed=42)
    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    for _ in range(3):
        c.avancar()

    caminho = c.salvar("teste_virada")
    try:
        volta = Carreira.carregar("teste_virada")
        assert volta.temporada == c.temporada == 2028
        assert volta.rodada == c.rodada == 3
        assert volta.liga == c.liga, "o clube voltou na divisao errada"
        assert [(r.home, r.away, r.goals_home, r.goals_away) for r in volta.jogos()] == \
               [(r.home, r.away, r.goals_home, r.goals_away) for r in c.jogos()]
        elenco = {p.id: p.overall for p in volta.world.squad(volta.clube_id)}
        assert elenco == {p.id: p.overall for p in c.world.squad(c.clube_id)}
    finally:
        caminho.unlink()
