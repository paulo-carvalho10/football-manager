"""Leitura dos arquivos de dados (TOML), com memoria.

O motor pede a mesma liga centenas de vezes por tela: so `/api/estado` lia o arquivo da
liga ~1000 vezes, e cada leitura e um parse de TOML. Aqui o parse acontece uma vez por
processo -- e de novo so se o arquivo mudar no disco (a chave e o mtime e o tamanho).

Os packs pesam mais: os 43 levam ~1,2 s de parse. Esses ficam tambem num cache em disco
(data/cache/packs, fora do git), e a carreira nova ou o save abrem sem esperar o parse.
"""

from __future__ import annotations

import copy
import pickle
import tomllib
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "packs"

_LIDOS: dict[Path, tuple[tuple[int, int], dict]] = {}


def _marca(caminho: Path) -> tuple[int, int]:
    st = caminho.stat()
    return st.st_mtime_ns, st.st_size


def _ler(caminho: Path, em_disco: bool) -> dict:
    marca = _marca(caminho)
    lido = _LIDOS.get(caminho)
    if lido is not None and lido[0] == marca:
        return lido[1]
    dados = _do_disco(caminho, marca) if em_disco else None
    if dados is None:
        with caminho.open("rb") as fh:
            dados = tomllib.load(fh)
        if em_disco:
            _para_o_disco(caminho, marca, dados)
    _LIDOS[caminho] = (marca, dados)
    return dados


def _do_disco(caminho: Path, marca: tuple[int, int]) -> dict | None:
    try:
        with (CACHE_DIR / f"{caminho.stem}.pickle").open("rb") as fh:
            guardada, dados = pickle.load(fh)
    except (OSError, pickle.UnpicklingError, EOFError, ValueError, TypeError):
        return None
    return dados if guardada == marca else None


def _para_o_disco(caminho: Path, marca: tuple[int, int], dados: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temporario = CACHE_DIR / f"{caminho.stem}.pickle.tmp"
        with temporario.open("wb") as fh:
            pickle.dump((marca, dados), fh, protocol=pickle.HIGHEST_PROTOCOL)
        temporario.replace(CACHE_DIR / f"{caminho.stem}.pickle")
    except OSError:
        pass                    # sem cache em disco o jogo so fica mais lento


def ler_toml(caminho: Path) -> dict:
    """O TOML como dict, numa COPIA: quem recebe pode mexer sem estragar a memoria."""
    return copy.deepcopy(_ler(caminho, em_disco=False))


def ler_pack(caminho: Path) -> dict:
    """O TOML de um pack, SEM copia (copiar 2 MB custaria o que o cache economiza): quem
    le um pack so monta objetos novos a partir dele, nunca o altera."""
    return _ler(caminho, em_disco=True)
