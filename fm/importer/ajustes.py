"""Ajustes manuais sobre um pack gerado.

O pack e regerado a cada importacao, entao correcao feita a mao nele desaparece. As que
moram aqui sobrevivem. Ajuste que nao casa com ninguem levanta erro: nome digitado errado
tem de doer na hora, nao virar silencio.
"""

from __future__ import annotations

import tomllib
import unicodedata
from pathlib import Path

AJUSTES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ajustes"

CAMPOS = ("ovr", "pot", "posicao", "idade")


def _chave(texto: str) -> str:
    n = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


def carregar(pack: str) -> list[dict]:
    caminho = AJUSTES_DIR / f"{pack}.toml"
    if not caminho.exists():
        return []
    with caminho.open("rb") as fh:
        return tomllib.load(fh).get("jogadores", [])


def aplicar(pack: str, montados) -> list[str]:
    """Aplica os ajustes de `pack` em `montados`. Devolve o relato do que mudou."""
    ajustes = carregar(pack)
    if not ajustes:
        return []
    relato = []
    for a in ajustes:
        alvo_nome, alvo_clube = _chave(a["nome"]), _chave(a.get("clube", ""))
        achados = [
            (c, j) for c in montados if not alvo_clube or _chave(c.nome) == alvo_clube
            for j in c.jogadores if _chave(j["nome"]) == alvo_nome
        ]
        if not achados:
            raise ValueError(
                f"ajuste sem alvo em {pack}: {a['nome']!r} "
                f"({a.get('clube', 'qualquer clube')}) nao existe no pack")
        if len(achados) > 1:
            raise ValueError(
                f"ajuste ambiguo em {pack}: {a['nome']!r} casou com {len(achados)} "
                f"jogadores; informe `clube`")
        clube, jogador = achados[0]
        mudou = []
        for campo in CAMPOS:
            if campo in a and jogador.get(campo) != a[campo]:
                mudou.append(f"{campo} {jogador.get(campo)} -> {a[campo]}")
                jogador[campo] = a[campo]
        if jogador.get("pot") is not None and jogador.get("ovr") is not None:
            jogador["pot"] = max(jogador["pot"], jogador["ovr"])
        relato.append(f"{jogador['nome']} ({clube.nome}): " + ", ".join(mudou)
                      if mudou else f"{jogador['nome']} ({clube.nome}): sem mudanca")
    return relato
