"""A nacionalidade dos jogadores dos packs, tirada do cache do Transfermarkt.

O importador sempre leu a bandeira do plantel (`TMJogador.nacionalidade`), mas o pack nao
tinha onde guarda-la e todo jogador virava do pais da liga: o Arrascaeta era brasileiro.
Isto escreve `nacionalidade = "..."` em cada jogador dos packs JA montados, casando pelo
`id_fonte` (o id do jogador no Transfermarkt). Roda offline: so le o cache de elencos.

Nao refaz o pack: refazer recalcularia overall, potencial e ajustes, e o mundo mudaria.
A importacao nova (fm.importer.build) ja grava a nacionalidade direto.
"""

from __future__ import annotations

import re
from pathlib import Path

from fm.importer.http import CACHE_DIR
from fm.pack import PACKS_DIR
from fm.paises import nome_do_pais

_ID = re.compile(r'^  id_fonte = "(\d+)"\s*$')
_NACIONALIDADE = re.compile(r"^  nacionalidade = ")


def do_cache() -> dict[str, str]:
    """{id do jogador no Transfermarkt: pais}, de todos os elencos baixados."""
    from fm.importer.transfermarkt import extrair_elenco
    mapa: dict[str, str] = {}
    for arq in sorted((CACHE_DIR / "tm").glob("elenco_*.html")):
        for j in extrair_elenco(arq.read_text(encoding="utf-8")):
            pais = nome_do_pais(j.nacionalidade)
            if pais:
                mapa[j.spieler_id] = pais
    return mapa


def _esc(txt: str) -> str:
    return txt.replace("\\", "\\\\").replace('"', '\\"')


def injetar(packs: list[Path] | None = None,
            mapa: dict[str, str] | None = None) -> dict[str, tuple[int, int]]:
    """Escreve a nacionalidade nos packs. Devolve {pack: (com nacionalidade, jogadores)}.
    Idempotente: a linha antiga sai antes de a nova entrar."""
    mapa = do_cache() if mapa is None else mapa
    fora: dict[str, tuple[int, int]] = {}
    for pack in packs or sorted(PACKS_DIR.glob("*.toml")):
        linhas = pack.read_text(encoding="utf-8").splitlines()
        novas: list[str] = []
        com = total = 0
        for linha in linhas:
            if _NACIONALIDADE.match(linha):
                continue
            novas.append(linha)
            m = _ID.match(linha)
            if m:
                total += 1
                pais = mapa.get(m.group(1))
                if pais:
                    com += 1
                    novas.append(f'  nacionalidade = "{_esc(pais)}"')
        if total:
            pack.write_text("\n".join(novas) + "\n", encoding="utf-8")
            fora[pack.stem] = (com, total)
    return fora
