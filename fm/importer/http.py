"""Busca com cache em disco. Etapa 1 -- a unica que usa rede."""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

_ultimo: dict[str, float] = {}


def get(url: str, cache_key: str, *, delay: float = 1.0, timeout: int = 90) -> str:
    """Devolve o corpo da URL, servindo do cache quando possivel.

    `delay` e o intervalo minimo entre dois acessos ao mesmo host -- educacao basica com
    quem esta servindo o dado de graca.
    """
    destino = CACHE_DIR / cache_key
    if destino.exists() and destino.stat().st_size > 0:
        return destino.read_text(encoding="utf-8", errors="replace")

    host = url.split("/")[2]
    espera = delay - (time.monotonic() - _ultimo.get(host, 0.0))
    if espera > 0:
        time.sleep(espera)

    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            bruto = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                bruto = gzip.decompress(bruto)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} em {url}") from e
    finally:
        _ultimo[host] = time.monotonic()

    texto = bruto.decode("utf-8", errors="replace")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return texto


def get_json(url: str, cache_key: str, **kw) -> dict:
    return json.loads(get(url, cache_key, **kw))
