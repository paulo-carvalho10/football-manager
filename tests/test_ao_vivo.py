"""A partida ao vivo: trocas e tatica no meio do jogo, e o save que lembra delas."""

from fm.carreira import MAX_TROCAS, Carreira, saves_disponiveis
from fm.notas import notas_da_partida


def _primeira_partida(c: Carreira, pedido):
    while True:
        _, partida = c.avancar(substituicoes=pedido)
        if partida is not None:
            return partida


def test_o_save_reproduz_trocas_e_tatica_feitas_no_meio_do_jogo(tmp_path, monkeypatch):
    """REGRESSAO: o replay jogava sem as substituicoes, e o placar carregado divergia."""
    import fm.carreira as mod
    monkeypatch.setattr(mod, "SAVES_DIR", tmp_path)
    c = Carreira.nova("brasil_real", "Santos", seed=3)

    def pedido(partida, minuto):
        if minuto != 45:
            return None
        meus = partida.em_campo_casa if partida.casa == c.clube_id else partida.em_campo_fora
        banco = [p.id for p in c.world.squad(c.clube_id) if p.id not in partida.entrada]
        return {"trocas": list(zip(meus[1:4], banco[:3])),
                "tatica": {"formacao": "4-4-2", "marcacao": "forte", "estilo": "ofensivo"}}

    jogada = _primeira_partida(c, pedido)
    # as tres pedidas; a troca de quem se machuca (fm.eventos) nao conta
    assert sum(1 for e in jogada.eventos
               if e.tipo == "substituicao" and "machucado" not in e.texto) == 3
    c.salvar("ao_vivo")
    assert "ao_vivo" in saves_disponiveis()

    carregada = Carreira.carregar("ao_vivo")
    # a primeira partida pode ser de copa: o ano abre em fevereiro com a Copa do Brasil
    jogos = list(carregada.jogos()) + [r for a in carregada.copas.values()
                                       for r in a.resultados_do_ano]
    resultados = {(r.home, r.away): (r.goals_home, r.goals_away) for r in jogos}
    assert resultados[(jogada.casa, jogada.fora)] == (jogada.gols_casa, jogada.gols_fora)
    assert carregada.na_partida == c.na_partida


def test_no_maximo_cinco_trocas_e_quem_saiu_nao_volta():
    c = Carreira.nova("brasil_real", "Santos", seed=5)
    saiu: list[int] = []

    def pedido(partida, minuto):
        meus = partida.em_campo_casa if partida.casa == c.clube_id else partida.em_campo_fora
        banco = [p.id for p in c.world.squad(c.clube_id) if p.id not in partida.entrada]
        # pede troca todo bloco, inclusive a volta de quem ja saiu
        pares = [(meus[-1], b) for b in saiu[:1] + banco[:1]]
        saiu.append(meus[-1])
        return {"trocas": pares}

    partida = _primeira_partida(c, pedido)
    trocas = [e for e in partida.eventos
              if e.tipo == "substituicao" and e.clube == c.clube_id]
    assert len(trocas) == MAX_TROCAS
    # entrar e depois sair e legitimo; sair e depois entrar, nao
    for i, t in enumerate(trocas):
        assert t.segundo not in {x.jogador for x in trocas[:i]}, "alguem saiu e voltou"
    assert len({t.segundo for t in trocas}) == len(trocas)


def test_notas_premiam_quem_decide_e_ficam_na_escala():
    c = Carreira.nova("brasil_real", "Santos", seed=8)
    for _ in range(6):
        _, partida = c.avancar()
        if partida is None:
            continue
        notas = notas_da_partida(c.world, partida)
        assert set(notas) == set(partida.entrada)
        assert all(3.0 <= n <= 10.0 for n in notas.values())
        expulsos = {e.jogador for e in partida.eventos if e.tipo == "vermelho"}
        for e in partida.eventos:
            # acima da linha de quem nao fez nada (6,0). Nao 6,5: gol com amarelo numa
            # derrota da 6,4, e esta certo
            if e.tipo == "gol" and e.jogador in notas and e.jogador not in expulsos:
                assert notas[e.jogador] > 6.0, "quem marcou saiu com nota de quem nao jogou"


def test_a_escalacao_automatica_poe_cada_um_na_sua_vaga():
    from fm.tatica import VAGAS
    c = Carreira.nova("brasil_real", "Flamengo", seed=2)
    for formacao in VAGAS:
        from fm.servidor import Jogo, escalar
        escalar(Jogo(c), {"formacao": formacao})
        onze = [c.world.players[i] for i in c.escalacao_atual()]
        setores = [v[1] for v in VAGAS[formacao]]
        assert onze[0].position == "GK", formacao
        fora = sum(p.position != s for p, s in zip(onze, setores))
        assert fora == 0, f"{formacao}: {fora} improvisados sem necessidade"


def test_quem_joga_de_centroavante_finaliza_como_centroavante():
    """A vaga vale no jogo: o zagueiro escalado de 9 passa a marcar gols."""
    import numpy as np
    from fm.eventos import simular_partida
    c = Carreira.nova("brasil_real", "Flamengo", seed=2)
    w = c.world
    casa, fora = c.clube_id, next(i for i in w.clubs if i != c.clube_id
                                   and i in w.leagues[next(iter(w.leagues))].club_ids)
    onze = c.escalacao_atual()
    zagueiro = onze[2]
    onze_fora = [p.id for p in w.best_xi(fora)]

    def gols_do(pid, papeis):
        rng = np.random.default_rng(9)
        total = 0
        for _ in range(300):
            p = simular_partida(w, casa, fora, onze, onze_fora, rng, papeis=papeis)
            total += sum(1 for e in p.eventos if e.tipo == "gol" and e.jogador == pid)
        return total

    assert gols_do(zagueiro, {zagueiro: "FW"}) > 3 * gols_do(zagueiro, {})
