"""Data packs: de onde vem o conteudo do mundo.

Um pack e um arquivo com os clubes de um pais -- nome, forca e, opcionalmente, a escalacao
nominal. Ele fica FORA do motor, em data/packs/, e e substituivel: pack proprio, pack real,
pack de mod da comunidade. O motor nunca depende de nenhum pack especifico para rodar
(ver tests/test_packs.py::test_motor_roda_sem_pack) -- essa e a unica propriedade que
precisa continuar valendo, e ela e o que mantem a porta do licenciamento aberta.

Formato:

    fonte = "Composicao da Serie A 2026"       # de onde veio, para auditoria
    verificado = false                          # true so depois de conferir na fonte

    [[clubes]]
    nome  = "Clube Exemplo"
    forca = 76                                  # overall do onze titular
    apelido = "CEX"                             # opcional
    cores = ["#c8102e", "#ffffff"]              # opcional
    # Escalacao nominal e OPCIONAL. O que faltar para 24 jogadores e gerado.
    [[clubes.jogadores]]
    nome = "Nome do Jogador"
    pos  = "MF"
    idade = 26
    ovr  = 80
    pot  = 84
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"

VALID_POSITIONS = ("GK", "DF", "MF", "FW")


@dataclass(slots=True)
class PackPlayer:
    nome: str
    pos: str
    idade: int
    ovr: int
    pot: int | None = None


@dataclass(slots=True)
class PackClub:
    nome: str
    forca: float
    apelido: str | None = None
    cores: tuple[str, str] | None = None
    jogadores: list[PackPlayer] = field(default_factory=list)


@dataclass(slots=True)
class Pack:
    id: str
    fonte: str
    verificado: bool
    clubes: list[PackClub]

    def top(self, n: int) -> list[PackClub]:
        """Os n clubes mais fortes -- e assim que a primeira divisao e montada do pack."""
        if n > len(self.clubes):
            raise ValueError(
                f"pack {self.id!r} tem {len(self.clubes)} clubes, a liga pediu {n}")
        return sorted(self.clubes, key=lambda c: -c.forca)[:n]

    def slice(self, start: int, n: int) -> list[PackClub]:
        """Fatia por forca: divisoes de baixo saem daqui (start=20 para a segunda divisao)."""
        ordenado = sorted(self.clubes, key=lambda c: -c.forca)
        fatia = ordenado[start:start + n]
        if len(fatia) < n:
            raise ValueError(
                f"pack {self.id!r}: faltam clubes para a fatia {start}..{start + n}")
        return fatia


def load_pack(name: str) -> Pack:
    path = PACKS_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(
            f"pack {name!r} nao encontrado. Disponiveis: {available_packs()}")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    clubes = []
    for c in raw.get("clubes", []):
        jogadores = []
        for j in c.get("jogadores", []):
            if j["pos"] not in VALID_POSITIONS:
                raise ValueError(f"posicao invalida {j['pos']!r} em {c['nome']}")
            jogadores.append(PackPlayer(
                nome=j["nome"], pos=j["pos"], idade=int(j["idade"]),
                ovr=int(j["ovr"]), pot=int(j["pot"]) if "pot" in j else None))
        cores = c.get("cores")
        clubes.append(PackClub(
            nome=c["nome"], forca=float(c["forca"]), apelido=c.get("apelido"),
            cores=(cores[0], cores[1]) if cores else None, jogadores=jogadores))

    if not clubes:
        raise ValueError(f"pack {name!r} nao tem clubes")
    nomes = [c.nome for c in clubes]
    if len(set(nomes)) != len(nomes):
        raise ValueError(f"pack {name!r} tem clube repetido")
    return Pack(id=name, fonte=raw.get("fonte", "(sem fonte declarada)"),
                verificado=bool(raw.get("verificado", False)), clubes=clubes)


def available_packs() -> list[str]:
    return sorted(p.stem for p in PACKS_DIR.glob("*.toml"))
