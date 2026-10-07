"""A nacionalidade real (07/10/2026): base das selecoes. Antes, todo jogador era do pais
da liga do clube -- o Arrascaeta era brasileiro."""

from __future__ import annotations

from fm.carreira import Carreira
from fm.importer.nacionalidades import injetar
from fm.pack import load_pack
from fm.paises import nome_do_pais


def test_o_jogador_real_tem_o_pais_dele():
    c = Carreira.nova(["brasil_real"], "Flamengo", seed=1)
    paises = {p.name: p.nationality for p in c.world.squad(c.clube_id)}
    assert paises["Giorgian de Arrascaeta"] == "Uruguai"
    assert paises["Erick Pulgar"] == "Chile"
    assert "Brasil" in paises.values()


def test_todo_jogador_dos_packs_tem_nacionalidade():
    for pack in ("brasil_serie_a", "espanha_primera", "inglaterra_premier"):
        jogadores = [j for c in load_pack(pack).clubes for j in c.jogadores]
        assert jogadores
        assert sum(1 for j in jogadores if j.nacionalidade) / len(jogadores) > 0.99


def test_o_gerado_e_do_pais_da_liga():
    """Preenchimento de elenco e base nascem no pais do clube, com o nome por extenso."""
    c = Carreira.nova(["espanha_real"], "Real Madrid", seed=1)
    gerados = [p for p in c.world.players.values()
               if p.club_id in c.world.clubs and not p.name.strip() == ""
               and p.nationality in ("ESP", "Espanha")]
    assert gerados
    assert all(p.nationality != "ESP" for p in c.world.players.values())


def test_o_site_em_portugues_de_portugal_vira_do_brasil():
    assert nome_do_pais("Polónia") == "Polônia"
    assert nome_do_pais("República Checa") == "Tchéquia"
    assert nome_do_pais("Uruguai") == "Uruguai"
    assert nome_do_pais(None) is None


def test_injetar_e_idempotente(tmp_path):
    pack = tmp_path / "x.toml"
    pack.write_text('[[clubes]]\nnome = "A"\nforca = 70\nid_fonte = "9"\n\n'
                    '  [[clubes.jogadores]]\n  nome = "Fulano"\n  id_fonte = "123"\n',
                    encoding="utf-8")
    for _ in range(2):
        assert injetar([pack], {"123": "Uruguai", "9": "Brasil"}) == {"x": (1, 1)}
    texto = pack.read_text(encoding="utf-8")
    assert texto.count("nacionalidade") == 1
    assert 'nacionalidade = "Uruguai"' in texto
