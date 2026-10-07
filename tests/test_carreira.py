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
    # 10 RODADAS de liga, nao 10 datas: quantas datas de copa cabem no meio depende da
    # agenda (a ida e a volta do mata-mata viraram datas separadas), e em data sem jogo o
    # elenco descansa
    onze = carreira.escalacao_atual()
    while carreira.rodada < 10:
        carreira.escalar(onze, Tatica(marcacao="forte"))
        carreira.avancar()
    com_forte = sum(carreira.world.players[j].condition for j in onze) / 11

    outra = Carreira.nova("brasil_real", "Santos", seed=42)
    onze2 = outra.escalacao_atual()
    while outra.rodada < 10:
        outra.escalar(onze2, Tatica(marcacao="leve"))
        outra.avancar()
    com_leve = sum(outra.world.players[j].condition for j in onze2) / 11
    # no calendario real a liga e semanal e o descanso entre rodadas e maior: a diferenca
    # caiu de ~4 para ~2,3 pontos, mas a pressao alta continua cobrando
    assert com_forte < com_leve - 1.5


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


def test_a_tatica_vale_para_os_proximos_jogos(carreira):
    """REGRESSAO: a tatica era gravada so para a rodada em que foi escolhida. Mudar para
    3-5-2, jogar e voltar ao menu devolvia o 4-3-3 -- era preciso escolher de novo antes
    de todo jogo."""
    desenho = ["GOL", "LE", "ZE", "ZD", "LD", "VC", "ME", "MCE", "MCD", "MD", "CA"]
    carreira.escalar(carreira.escalacao_atual(),
                     Tatica(formacao="4-5-1", estilo="ofensivo", desenho=desenho))
    for _ in range(3):
        _avancar_ate_a_liga(carreira)
    t = carreira.tatica_atual()
    assert (t.estilo, t.desenho, t.nome) == ("ofensivo", desenho, "4-1-4-1")
    # o onze automatico da rodada nova ocupa os pontos do desenho salvo
    onze = carreira.escalacao_atual()
    papeis = {carreira.world.players[i].position for i in onze[5:6]}
    assert papeis <= {"MF", "DF"}, "o volante do desenho foi ocupado por quem?"


def test_save_antigo_continua_jogando_no_padrao(tmp_path, carreira):
    """Save de antes da regra nao tem a marca: a rodada sem decisao segue no padrao, senao o
    replay jogaria com outra tatica e daria outro resultado."""
    carreira.tatica_persistente = False
    carreira.escalar(carreira.escalacao_atual(), Tatica(formacao="5-3-2"))
    _avancar_ate_a_liga(carreira)
    assert carreira.tatica_atual().formacao == "4-3-3"
    carreira.salvar("teste_pytest_antigo")
    try:
        recarregada = Carreira.carregar("teste_pytest_antigo")
        assert recarregada.tatica_persistente is False
    finally:
        from fm.carreira import SAVES_DIR
        (SAVES_DIR / "teste_pytest_antigo.json").unlink()


def test_mudanca_no_meio_do_jogo_nao_fica(carreira):
    """A tatica trocada durante a partida vale so nela: e gravada em `na_partida`, nao nas
    decisoes que valem para os proximos jogos."""
    carreira.escalar(carreira.escalacao_atual(), Tatica(formacao="4-4-2"))

    def no_intervalo(partida, minuto):
        return {"tatica": Tatica(formacao="3-4-3")} if minuto == 45 else None

    while carreira.compromisso[0] != "liga":
        carreira.avancar()
    carreira.avancar(substituicoes=no_intervalo)
    assert carreira.tatica_atual().formacao == "4-4-2"
    assert any(t for reg in carreira.na_partida.values() for _, t in reg.get("taticas", []))


# ------------------------------------------------------------------ o retrato do save

def _foto(c):
    w = c.world
    return (c.temporada, c.data, c.clube_id,
            sorted((r.home, r.away, r.goals_home, r.goals_away) for n in c.ligas
                   for r in c.jogos(n)),
            sorted((p.id, p.club_id, p.overall, p.morale, p.condition)
                   for p in w.players.values()),
            sorted((k, cl.balance, cl.reputation) for k, cl in w.clubs.items()))


def test_o_retrato_carrega_o_mesmo_mundo_que_o_replay(tmp_path, monkeypatch):
    """Carregar pelo retrato (o comeco da temporada) tem de dar EXATAMENTE o mundo do
    replay completo. Com as 40 ligas, o replay levava ~47 s por temporada."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=8)
    while not c.acabou:
        c.avancar()
    c.virar_o_ano()
    for _ in range(6):
        c.avancar()
    c.salvar("r")
    assert (tmp_path / "r.retrato").exists()
    (tmp_path / "r.ponto").unlink()      # o ponto do save tem teste proprio, abaixo

    chamadas = []
    original = mod.build_world
    monkeypatch.setattr(mod, "build_world", lambda *a, **k: chamadas.append(1) or original(*a, **k))
    rapido = Carreira.carregar("r")
    assert not chamadas, "com retrato valido o mundo nao e montado do zero"
    assert _foto(rapido) == _foto(c)

    # versao do jogo diferente: o retrato e ignorado e o replay completo roda
    monkeypatch.setattr(mod, "_IMPRESSAO", "outra-versao")
    completo = Carreira.carregar("r")
    assert chamadas, "retrato de outra versao do jogo nao pode valer"
    assert _foto(completo) == _foto(c)


def test_o_ponto_do_save_abre_sem_refazer_nada(tmp_path, monkeypatch):
    """O ponto e a carreira na hora do save: abrir por ele nao refaz nenhuma data, da o
    mesmo mundo do replay e o jogo segue igual pelos dois caminhos."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=8)
    for _ in range(20):
        c.avancar()
    c.salvar("p")
    assert (tmp_path / "p.ponto").exists()

    datas = []
    original = mod.Carreira.avancar
    monkeypatch.setattr(mod.Carreira, "avancar",
                        lambda self, *a, **k: datas.append(1) or original(self, *a, **k))
    pelo_ponto = Carreira.carregar("p")
    assert not datas, "com o ponto valido nenhuma data e refeita"
    assert _foto(pelo_ponto) == _foto(c)

    (tmp_path / "p.ponto").rename(tmp_path / "guardado")
    pelo_replay = Carreira.carregar("p")
    assert datas, "sem o ponto o replay roda"
    assert _foto(pelo_replay) == _foto(c)
    for x in (pelo_ponto, pelo_replay):
        for _ in range(3):
            x.avancar()
    assert _foto(pelo_ponto) == _foto(pelo_replay)

    # o ponto e de UM save: o mesmo arquivo com outro save ao lado nao vale
    (tmp_path / "guardado").rename(tmp_path / "p.ponto")
    texto = (tmp_path / "p.json").read_text(encoding="utf-8")
    (tmp_path / "p.json").write_text(texto.replace('"treinador": "', '"treinador": "X'),
                                     encoding="utf-8")
    datas.clear()
    Carreira.carregar("p")
    assert datas, "ponto de outro save nao pode valer"


def test_salvar_no_meio_da_partida_nao_grava_ponto(tmp_path, monkeypatch):
    """A partida ao vivo roda numa thread; salvar no intervalo pegaria meia data."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=8)
    c.salvar("m")
    assert (tmp_path / "m.ponto").exists()
    c._no_meio_da_data = True
    c.salvar("m")
    assert not (tmp_path / "m.ponto").exists(), "o ponto antigo tambem nao vale mais"
