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
    id_fonte = "20016"                          # opcional: id na fonte (CBF, API, ...)
    apelido = "CEX"                             # opcional
    cores = ["#c8102e", "#ffffff"]              # opcional
    camisa = ["#ffffff", "#c8102e"]             # opcional: pano e detalhe, se difere do tema
    padrao = "listras"                          # opcional: liso, listras, aros, faixa, diagonal
    # Escalacao nominal e OPCIONAL. O que faltar para 24 jogadores e gerado.
    [[clubes.jogadores]]
    nome = "Nome do Jogador"        # unico campo obrigatorio
    nascimento = "2000-01-16"       # ou `idade = 26`
    pos  = "MF"                     # opcional: sem ele o gerador decide pela quota
    ovr  = 80                       # opcional: sem ele vem da curva, pela ordem no pack
    pot  = 84                       # opcional
    nome_completo = "..."           # opcional
    id_fonte = "622924"             # opcional
    partidas = 31                   # opcional: e por aqui que se ordena o elenco
    gols = 7                        # opcional
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from fm.arquivos import ler_pack
from fm.model import POSICAO_DETALHE

PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"

VALID_POSITIONS = tuple(POSICAO_DETALHE)


@dataclass(slots=True)
class PackPlayer:
    """Jogador nominal de um pack.

    So `nome` e obrigatorio. Isso e deliberado: identidade (nome, nascimento, clube) vem de
    fonte publica, mas posicao e overall nao existem em fonte aberta. O que faltar e
    preenchido pelo gerador -- posicao pela quota da formacao e overall pela curva de
    qualidade do elenco, na ORDEM em que o jogador aparece no pack. Por isso o importador
    grava os jogadores ordenados por partidas disputadas: quem joga mais entra mais alto.
    """

    nome: str
    pos: str | None = None
    idade: int | None = None
    nascimento: str | None = None      # ISO (1990-12-30); tem precedencia sobre `idade`
    ovr: int | None = None
    pot: int | None = None
    nome_completo: str | None = None
    id_fonte: str | None = None
    partidas: int | None = None
    gols: int | None = None
    minutos: int | None = None
    valor: int | None = None       # valor de mercado em EUR: permite recalcular ovr/pot
                                   # a partir do pack, sem precisar do cache de rede

    def age_in(self, season_year: int) -> int | None:
        if self.nascimento:
            return season_year - int(self.nascimento[:4])
        return self.idade


@dataclass(slots=True)
class PackClub:
    nome: str
    forca: float
    apelido: str | None = None
    cores: tuple[str, str] | None = None
    camisa: tuple[str, str] | None = None   # pano e detalhe; None = usa as cores do tema
    padrao: str | None = None     # padrao da camisa; None = liso
    id_fonte: str | None = None   # id do clube na fonte do pack (ex.: Codigo_Clube da CBF)
    valor_elenco: int | None = None   # valor total do elenco em EUR (base do forca)
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


def _int(fonte: dict, chave: str) -> int | None:
    v = fonte.get(chave)
    return int(v) if v is not None else None


def load_pack(name: str) -> Pack:
    path = PACKS_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(
            f"pack {name!r} nao encontrado. Disponiveis: {available_packs()}")
    raw = ler_pack(path)

    clubes = []
    for c in raw.get("clubes", []):
        jogadores = []
        for j in c.get("jogadores", []):
            pos = j.get("pos")
            if pos is not None and pos not in VALID_POSITIONS:
                raise ValueError(
                    f"posicao invalida {pos!r} em {c['nome']}; use {VALID_POSITIONS} "
                    f"ou omita o campo para o gerador decidir")
            nasc = j.get("nascimento")
            if nasc is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(nasc)):
                raise ValueError(f"nascimento deve ser ISO (AAAA-MM-DD), veio {nasc!r}")
            jogadores.append(PackPlayer(
                nome=j["nome"], pos=pos, idade=_int(j, "idade"),
                nascimento=str(nasc) if nasc else None, ovr=_int(j, "ovr"), pot=_int(j, "pot"),
                nome_completo=j.get("nome_completo"), id_fonte=j.get("id_fonte"),
                partidas=_int(j, "partidas"), gols=_int(j, "gols"), minutos=_int(j, "minutos"),
                valor=_int(j, "valor")))
        cores = c.get("cores")
        clubes.append(PackClub(
            nome=c["nome"], forca=float(c["forca"]), apelido=c.get("apelido"),
            cores=(cores[0], cores[1]) if cores else None,
            camisa=(camisa[0], camisa[1]) if (camisa := c.get("camisa")) else None,
            padrao=c.get("padrao"),
            id_fonte=c.get("id_fonte"),
            valor_elenco=int(c["valor_elenco"]) if "valor_elenco" in c else None,
            jogadores=jogadores))

    if not clubes:
        raise ValueError(f"pack {name!r} nao tem clubes")
    nomes = [c.nome for c in clubes]
    if len(set(nomes)) != len(nomes):
        raise ValueError(f"pack {name!r} tem clube repetido")
    return Pack(id=name, fonte=raw.get("fonte", "(sem fonte declarada)"),
                verificado=bool(raw.get("verificado", False)), clubes=clubes)


def available_packs() -> list[str]:
    return sorted(p.stem for p in PACKS_DIR.glob("*.toml"))
