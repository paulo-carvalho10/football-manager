"""Carregamento das competicoes. Toda regra vem de arquivo."""

from __future__ import annotations

import tomllib
from pathlib import Path

from fm.match import Mentality, Style

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "leagues"


def load_league(name: str) -> dict:
    path = DATA_DIR / f"{name}.toml"
    if not path.exists():
        disponiveis = sorted(p.stem for p in DATA_DIR.glob("*.toml"))
        raise FileNotFoundError(f"liga {name!r} nao encontrada. Disponiveis: {disponiveis}")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def available() -> list[str]:
    return sorted(p.stem for p in DATA_DIR.glob("*.toml"))


def style_of(cfg: dict) -> Style:
    e = cfg.get("estilo", {})
    return Style(goals_base=float(e.get("gols_base", 1.255)),
                 home_adv=float(e.get("mando", 0.30)))


def mentality_of(cfg: dict, fase: dict | None = None) -> Mentality:
    """Mentalidade da fase. Copa trava o jogo e comprime o gap."""
    src = (fase or {}).get("mentalidade") or cfg.get("mentalidade")
    if not src:
        tipo = (fase or {}).get("tipo")
        return Mentality.CUP if tipo == "knockout" else Mentality.NORMAL
    return Mentality(goals_mult=float(src.get("gols_mult", 1.0)),
                     compression=float(src.get("compressao", 0.0)),
                     home_mult=float(src.get("mando_mult", 1.0)))


def targets_of(cfg: dict) -> dict[str, tuple[float, float]]:
    """Alvos de calibracao proprios da liga, do bloco [alvos]. Ausentes caem na referencia."""
    return {k: (float(v[0]), float(v[1])) for k, v in cfg.get("alvos", {}).items()}
