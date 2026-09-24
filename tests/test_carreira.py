"""O loop de carreira: rodada a rodada, escalacao do usuario, tatica, energia e save."""

from __future__ import annotations

from itertools import groupby

import pytest

from fm.carreira import Carreira
from fm.competition import round_robin
from fm.tatica import FORMACOES, Tatica


@pytest.fixture
def carreira():
    return Carreira.nova("brasil_real", "Santos", seed=42)


def _avancar_ate_a_liga(c):
    """Avanca ate a proxima data de LIGA, jogando as de copa que vierem antes."""
    while not c.acabou and c.compromisso[0] != "liga":
        c.avancar()
    return c.avancar()


def test_avancar_joga_exatamente_uma_rodada(carreira):
    """O coracao do jogo: uma rodada por vez, nao a temporada inteira."""
    assert carreira.rodada == 0
    jogos_por_rodada = len(carreira.world.leagues[carreira.liga_id].club_ids) // 2
    resultados, partida = _avancar_ate_a_liga(carreira)
    assert carreira.rodada == 1
    assert len(resultados) == jogos_por_rodada
    assert partida is not None, "a partida do usuario tem de vir detalhada"
    assert partida.gols_casa + partida.gols_fora == len(
        [e for e in partida.eventos if e.tipo == "gol"])
    assert len(carreira.jogos()) == jogos_por_rodada
    _avancar_ate_a_liga(carreira)
    assert carreira.rodada == 2
    assert len(carreira.jogos()) == 2 * jogos_por_rodada


def test_a_escalacao_do_usuario_manda(carreira):
    """Inclusive quando e ruim: e o jogo dele."""
    elenco = sorted(carreira.world.squad(carreira.clube_id),
                    key=lambda p: p.overall)
    piores = [p.id for p in elenco[:11]]
    carreira.escalar(piores)
    assert carreira.escalacao_atual() == piores
    carreira.avancar()
    escalados = carreira.world.escalacao_fixa[carreira.clube_id]
    assert escalados == piores, "a IA reescolheu o onze do usuario"


def test_escalacao_invalida_e_recusada(carreira):
    with pytest.raises(ValueError, match="11 jogadores"):
        carreira.escalar([p.id for p in carreira.world.squad(carreira.clube_id)[:7]])
    outro = next(c for c in carreira.world.clubs if c != carreira.clube_id)
    alheios = [p.id for p in carreira.world.squad(outro)[:11]]
    with pytest.raises(ValueError, match="outro clube"):
        carreira.escalar(alheios)
    with pytest.raises(ValueError, match="formacao"):
        carreira.escalar(carreira.escalacao_atual(), Tatica(formacao="9-0-1"))


def test_save_e_replay_identico(tmp_path, carreira):
    """O save guarda seed e decisoes, nao o mundo. Se o replay divergir, o determinismo
    do motor quebrou -- e o save e a primeira vitima."""
    for _ in range(4):
        carreira.escalar(carreira.escalacao_atual(), Tatica(estilo="ofensivo"))
        carreira.avancar()
    caminho = carreira.salvar("teste_pytest")
    assert caminho.stat().st_size < 20_000, "save inchado: esta guardando o mundo?"

    recarregada = Carreira.carregar("teste_pytest")
    assert recarregada.rodada == carreira.rodada
    original = [(r.home, r.away, r.goals_home, r.goals_away) for r in carreira.jogos()]
    replay = [(r.home, r.away, r.goals_home, r.goals_away) for r in recarregada.jogos()]
    assert original == replay
    assert recarregada.posicao() == carreira.posicao()
    caminho.unlink()


def test_energia_estabiliza_e_nao_desaba(carreira):
    """Com escalacao FIXA os mesmos onze jogam sempre. Antes eles desciam ate o piso em
    seis rodadas; jogador de verdade estabiliza."""
    onze = carreira.escalacao_atual()
    medias = []
    for _ in range(20):
        carreira.escalar(onze)
        carreira.avancar()
        medias.append(sum(carreira.world.players[j].condition for j in onze) / 11)
    # a media das ultimas datas, nao a da ultima: se ela cai numa copa em que o clube
    # folgou, o onze aparece descansado (94%) e o teste media a folga, nao o equilibrio
    media = sum(medias[-8:]) / 8
    assert 70 < media < 92, f"energia de equilibrio fora do razoavel: {media:.0f}%"


def test_marcacao_forte_cansa_mais(carreira):
    onze = carreira.escalacao_atual()
    for _ in range(10):
        carreira.escalar(onze, Tatica(marcacao="forte"))
        carreira.avancar()
    com_forte = sum(carreira.world.players[j].condition for j in onze) / 11

    outra = Carreira.nova("brasil_real", "Santos", seed=42)
    onze2 = outra.escalacao_atual()
    for _ in range(10):
        outra.escalar(onze2, Tatica(marcacao="leve"))
        outra.avancar()
    com_leve = sum(outra.world.players[j].condition for j in onze2) / 11
    assert com_forte < com_leve - 3


def test_todas_as_formacoes_escalam_onze(carreira):
    for nome in FORMACOES:
        t = Tatica(formacao=nome)
        t.validar()
        assert sum(t.vagas.values()) == 11, f"{nome} nao soma 11"


def test_calendario_alterna_o_mando(carreira):
    """Regressao: o metodo do circulo decidia mando pela posicao e 19 dos 20 clubes
    jogavam um turno inteiro em casa e o outro inteiro fora."""
    ids = carreira.world.leagues[carreira.liga_id].club_ids
    fixtures = round_robin(ids, legs=2)
    rodadas = max(f.matchday for f in fixtures)
    for cid in ids:
        seq = []
        for r in range(1, rodadas + 1):
            jogo = next(f for f in fixtures if f.matchday == r and cid in (f.home, f.away))
            seq.append("C" if jogo.home == cid else "F")
        assert seq.count("C") == rodadas // 2, f"clube {cid} sem metade dos jogos em casa"
        maior = max(len(list(g)) for _, g in groupby(seq))
        assert maior <= 5, f"clube {cid} com {maior} jogos seguidos sem alternar mando"
