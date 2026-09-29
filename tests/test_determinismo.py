"""O save e semente + decisoes: o mesmo mundo tem de sair em QUALQUER processo.

O `hash()` de texto do Python muda a cada execucao (PYTHONHASHSEED). Usar ele para
sortear -- era o caso do elenco dos clubes convidados das copas -- faz o jogo carregado
virar outro a partir da primeira virada do ano, e nenhum teste de um processo so pega.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

DIGITAL = """
import hashlib
from fm.carreira import Carreira
c = Carreira.nova(["brasil_real", "brasil_b_real"], "Santos", seed=42)
h = hashlib.sha256()
for p in sorted(c.world.players.values(), key=lambda p: p.id):
    h.update(f"{p.id}|{p.name}|{p.club_id}|{p.overall}|{p.birth_year};".encode())
print(h.hexdigest())
"""


def _digital(semente_de_hash: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": semente_de_hash}
    saida = subprocess.run([sys.executable, "-c", DIGITAL], cwd=RAIZ, env=env,
                           capture_output=True, text=True, check=True)
    return saida.stdout.strip().splitlines()[-1]


def test_o_mundo_e_o_mesmo_em_qualquer_processo():
    assert _digital("1") == _digital("2")
