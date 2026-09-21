"""Aleatoriedade deterministica.

Regra do projeto: nenhum modulo cria RNG por conta propria. Todo sorteio pede um fluxo
nomeado a partir da seed da carreira. Fluxos nomeados sao independentes entre si, entao
adicionar uma feature nova (ex.: lesoes) NAO desloca os resultados das partidas ja
simuladas com a mesma seed -- que e' o que torna save, teste e replay reproduzveis.
"""

from __future__ import annotations

import numpy as np


class Streams:
    """Fabrica de geradores nomeados derivados de uma seed unica."""

    def __init__(self, seed: int) -> None:
        self.seed = int(seed)
        self._seq = np.random.SeedSequence(self.seed)
        self._cache: dict[str, np.random.Generator] = {}

    def get(self, *parts: object) -> np.random.Generator:
        """Fluxo para um proposito. `get("match", season, matchday)` e' sempre o mesmo fluxo."""
        key = "/".join(str(p) for p in parts)
        gen = self._cache.get(key)
        if gen is None:
            # spawn_key transforma o nome em coordenada: fluxos diferentes nao se cruzam.
            child = np.random.SeedSequence(self.seed, spawn_key=_hash_key(key))
            gen = np.random.default_rng(child)
            self._cache[key] = gen
        return gen


def _hash_key(key: str) -> tuple[int, ...]:
    """Converte um nome em coordenadas estaveis entre execucoes (hash() do Python varia)."""
    h = 0
    for ch in key:
        h = (h * 1_000_003 + ord(ch)) & 0xFFFF_FFFF_FFFF_FFFF
    return (h & 0xFFFF_FFFF, h >> 32)
