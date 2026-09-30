"""Calibra o overall de exibicao (fm.ratings.ESCALA_DE_EXIBICAO) contra as cartinhas.

Le um CSV de ratings do EA FC que a pessoa baixa para data/cache/ea_fc/ (fora do git) --
por exemplo o conjunto aberto github.com/mzafram2001/ea-fc (data/dataset_ea_fc_26.csv).
Casa os jogadores dos packs reais com os do CSV por nome, idade (+-1) e clube, e devolve a
tabela de conversao casando percentil com percentil.

Nada daqui entra no jogo: o CSV fica no cache, e o que se copia para fm/ratings.py sao so
os pontos da tabela.
"""

from __future__ import annotations

import csv
import re
import tomllib
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
CSV_PADRAO = RAIZ / "data" / "cache" / "ea_fc" / "dataset_ea_fc_26.csv"
PERCENTIS = (0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 99, 99.7, 100)
# palavras que nao identificam clube ("FC", "Club", "de")
RUIDO_DE_CLUBE = {"fc", "cf", "sc", "ac", "cd", "ca", "club", "de", "da", "do", "del",
                  "futebol", "football", "clube", "sport", "sociedade", "esporte", "se", "ec",
                  "afc", "sv", "fk"}


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", texto).strip()


def _tokens(texto: str) -> list[str]:
    return [x for x in _norm(texto).split() if x]


def _clube(texto: str) -> set[str]:
    return {x for x in _tokens(texto) if x not in RUIDO_DE_CLUBE and len(x) > 2}


def _ler_ea(caminho: Path) -> dict[str, list[dict]]:
    por_token: dict[str, list[dict]] = defaultdict(list)
    with caminho.open(encoding="utf-8-sig") as fh:
        for linha in csv.DictReader(fh):
            e = {"idade": int(linha["age"]), "overall": int(linha["overall"]),
                 "nomes": {_norm(linha.get(k, "")) for k in ("alias", "short_name", "long_name")}
                 - {""},
                 "tokens": set().union(*(_tokens(linha.get(k, ""))
                                         for k in ("alias", "short_name", "long_name"))),
                 "clube": _clube(linha["club_name"])}
            for t in e["tokens"]:
                por_token[t].append(e)
    return por_token


def _casar(nome: str, idade: int, clube: str, por_token) -> dict | None:
    """O jogador da EA com o mesmo nome (ou nome contido), idade +-1 e clube batendo.
    Empate e nome comum sem clube batendo ficam de fora: melhor nao casar que casar
    errado (o "Joao Pedro" do Bulo Bulo nao e o do Chelsea)."""
    tk = _tokens(nome)
    if not tk:
        return None
    alvo = _clube(clube)
    candidatos = {id(e): e for t in tk[-2:] for e in por_token.get(t, [])}.values()
    bons = []
    for e in candidatos:
        if abs(e["idade"] - idade) > 1 or not (alvo & e["clube"]):
            continue
        exato = _norm(nome) in e["nomes"]
        if exato or set(tk) <= e["tokens"]:
            bons.append(((exato, -abs(e["idade"] - idade)), e))
    if not bons:
        return None
    bons.sort(key=lambda x: x[0], reverse=True)
    if len(bons) > 1 and bons[0][0] == bons[1][0]:
        return None
    return bons[0][1]


def pares(caminho: Path = CSV_PADRAO) -> list[tuple[int, int]]:
    """(overall interno, overall da EA) de cada jogador casado nos packs reais."""
    por_token = _ler_ea(caminho)
    reais = sorted({tomllib.loads(p.read_text(encoding="utf-8"))["pack"]
                    for p in (RAIZ / "data" / "leagues").glob("*_real.toml")})
    saida = []
    for pack in reais:
        dados = tomllib.loads((RAIZ / "data" / "packs" / f"{pack}.toml")
                              .read_text(encoding="utf-8"))
        for c in dados["clubes"]:
            for j in c.get("jogadores", []):
                e = _casar(j["nome"], int(j.get("idade", 25)), c["nome"], por_token)
                if e is not None:
                    saida.append((int(j["ovr"]), e["overall"]))
    return saida


def tabela(dados: list[tuple[int, int]]) -> list[tuple[float, float]]:
    """Os pontos da conversao: percentil interno -> mesmo percentil da EA. As pontas da
    escala interna (40 e 95) ficam presas no piso e no teto das cartinhas."""
    nosso = np.array([a for a, _ in dados], float)
    ea = np.array([b for _, b in dados], float)
    xs = np.percentile(nosso, PERCENTIS)
    ys = np.percentile(ea, PERCENTIS)
    xs[0], ys[0] = 40.0, min(ys[0], 50.0)
    xs[-1], ys[-1] = 95.0, max(ys[-1], 91.0)
    xs, idx = np.unique(xs, return_index=True)
    ys = np.maximum.accumulate(ys[idx])
    return [(round(float(x), 1), round(float(y), 1)) for x, y in zip(xs, ys, strict=True)]


def avaliar(dados, pontos) -> dict:
    nosso = np.array([a for a, _ in dados], float)
    ea = np.array([b for _, b in dados], float)
    pred = np.interp(nosso, [x for x, _ in pontos], [y for _, y in pontos])
    return {"casados": len(dados), "erro_medio": float(np.mean(np.abs(pred - ea))),
            "vies": float(np.mean(pred - ea)),
            "ate_3": float(np.mean(np.abs(pred - ea) <= 3))}
