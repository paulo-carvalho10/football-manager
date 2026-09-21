"""Data packs: conteudo externo, motor independente."""

from __future__ import annotations

import pytest

from fm.calibration import report
from fm.config import available, load_league, style_of, targets_of
from fm.generate import build_world, league_clubs, strength_profile
from fm.pack import available_packs, load_pack


def test_packs_do_disco_carregam():
    assert available_packs()
    for nome in available_packs():
        pack = load_pack(nome)
        assert pack.clubes
        assert all(40 <= c.forca <= 99 for c in pack.clubes)


def test_pack_inexistente_da_erro_util():
    with pytest.raises(FileNotFoundError, match="Disponiveis"):
        load_pack("pack_que_nao_existe")


def test_todo_pack_declara_procedencia():
    """Honestidade de dado: nenhum pack pode existir sem dizer de onde veio.

    Nao se exige uma frase especifica -- exige-se que `fonte` esteja preenchida com algo
    util. Pack sem procedencia declarada e dado orfao: ninguem sabe se da para confiar.
    """
    for nome in available_packs():
        pack = load_pack(nome)
        assert isinstance(pack.verificado, bool)
        assert pack.fonte and pack.fonte != "(sem fonte declarada)", f"{nome} sem fonte"
        assert len(pack.fonte) >= 20, f"{nome}: fonte vaga demais ({pack.fonte!r})"


def test_motor_roda_sem_pack():
    """A PROPRIEDADE QUE IMPORTA: sem nenhum pack, o mundo continua sendo gerado.

    E isso que mantem a porta do licenciamento aberta -- trocar o conteudo por pack proprio
    e apagar um arquivo, nao reescrever o motor.
    """
    cfg = dict(id="ficticia", nome="Liga Ficticia", pais="BRA", clubes=20, tier=1,
               forca=dict(perfil="linear", topo=77, base=59))
    assert league_clubs(cfg) is None
    world, _ = build_world([cfg], seed=3)
    assert len(world.clubs) == 20
    assert len(world.players) == 480


def test_pack_define_nome_e_forca_do_clube():
    cfg = load_league("brasil")
    do_pack = {c.nome: c.forca for c in league_clubs(cfg)}
    world, _ = build_world([cfg], seed=3)
    for club in world.clubs.values():
        assert club.name in do_pack
        assert club.designed_strength == do_pack[club.name]


def test_divisoes_nao_compartilham_clube():
    """pack_offset fatia por forca: Serie A e Serie B saem disjuntas do mesmo pack."""
    a = {c.nome for c in league_clubs(load_league("brasil"))}
    b = {c.nome for c in league_clubs(load_league("brasil_b"))}
    assert len(a) == len(b) == 20
    assert not (a & b)


def test_escalacao_nominal_do_pack_e_respeitada():
    pack = load_pack("_exemplo_escalacao")
    cfg = dict(id="ex", nome="Exemplo", pais="BRA", clubes=2, tier=1,
               pack="_exemplo_escalacao")
    world, _ = build_world([cfg], seed=3)
    nomes = {p.name for p in world.players.values()}
    for club in pack.clubes:
        for j in club.jogadores:
            assert j.nome in nomes
    modelo = next(c for c in world.clubs.values() if c.name == "Clube Modelo")
    meia = next(p for p in world.squad(modelo.id) if p.name == "Meia Modelo")
    assert (meia.overall, meia.potential, meia.position) == (76, 89, "MF")
    assert len(world.squad(modelo.id)) == 24      # o resto foi gerado em volta


def test_cada_liga_passa_nos_seus_proprios_alvos():
    """Portao por liga: cada arquivo declara o que e realista PARA ELE.

    Aplicar os alvos da liga de referencia a toda liga seria erro -- o Brasileirao tem
    mando mais forte e campeao com menos pontos por motivos reais.
    """
    for nome in available():
        cfg = load_league(nome)
        fases = cfg.get("formato", {}).get("fases", [{"tipo": "round_robin"}])
        if fases[0].get("tipo") != "round_robin":
            continue
        metrics = report(targets=targets_of(cfg), ratings=strength_profile(cfg, 20),
                         style=style_of(cfg), seasons=400, seed=2026)
        fora = [f"{m.name}={m.value:.2f} fora de [{m.low}, {m.high}]"
                for m in metrics if not m.ok]
        assert not fora, f"{nome}: " + "; ".join(fora)
