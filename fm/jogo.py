"""As telas do jogo, no terminal.

Tres telas e um ciclo, como no genero: LOBBY (elenco, tabela, proximo jogo) -> ESCALAR
(onze, formacao, tatica) -> PARTIDA (seu jogo e o resto da rodada) -> volta ao lobby.

Isto e a casca. Nenhuma regra de jogo mora aqui -- tudo vem de fm.carreira. E de proposito:
quando existir interface grafica, ela troca este arquivo e mais nada.
"""

from __future__ import annotations

from fm.carreira import Carreira
from fm.tatica import ESTILOS, FORMACOES, MARCACOES, Tatica

LARGURA = 78
POSICAO_ORDEM = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}


def _linha(c: str = "-") -> str:
    return c * LARGURA


def _barra(valor: int, largura: int = 10) -> str:
    cheio = round(valor / 100 * largura)
    return "#" * cheio + "." * (largura - cheio)


def _dinheiro(v: int) -> str:
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    return f"{v/1000:.0f}k"


# ---------------------------------------------------------------- lobby

def tela_lobby(c: Carreira) -> None:
    clube = c.clube
    print()
    print(_linha("="))
    pos = f"{c.posicao()}o lugar" if c.resultados else "temporada nao comecou"
    pts = next((r.points for r in c.tabela() if r.club_id == c.clube_id), 0)
    print(f"  {clube.name.upper():<34s}{c.liga:>20s}  {c.temporada}")
    print(f"  {pos} | {pts} pts | rodada {c.rodada} de {c.total_de_rodadas}"
          f" | caixa {_dinheiro(clube.balance)}")
    print(_linha("="))

    jogo = c.proxima_partida()
    if jogo:
        mando = "em casa contra" if jogo.home == c.clube_id else "fora contra"
        rival = c.world.clubs[jogo.away if jogo.home == c.clube_id else jogo.home]
        t = c.tatica_atual()
        print(f"  PROXIMO  rodada {c.rodada + 1}: {mando} {rival.name} "
              f"(forca {rival.designed_strength:.0f})")
        print(f"  TATICA   {t.como_texto()}")
    else:
        print("  TEMPORADA ENCERRADA")
    print(_linha())

    print(f"  {'':2s}{'pos':4s}{'jogador':24s}{'ovr':>4}{'pot':>5}{'id':>4}"
          f"  {'energia':<14s}{'salario':>9}")
    elenco = sorted(c.world.squad(c.clube_id),
                    key=lambda p: (POSICAO_ORDEM.get(p.position, 9), -p.overall))
    titulares = set(c.escalacao_atual())
    for p in elenco[:24]:
        marca = ">" if p.id in titulares else " "
        print(f"  {marca:2s}{p.position:4s}{p.name:24s}{p.overall:4d}{p.potential:5d}"
              f"{p.age(c.temporada):4d}  {_barra(p.condition)} {p.condition:3d}%"
              f"{_dinheiro(p.wage):>9}")
    if len(elenco) > 24:
        print(f"  ... e mais {len(elenco) - 24} no elenco")
    print(_linha())
    print("  [1] Escalar   [2] Jogar rodada   [3] Tabela   [4] Elenco completo"
          "   [5] Salvar   [0] Sair")


# ---------------------------------------------------------------- tabela

def tela_tabela(c: Carreira) -> None:
    print()
    print(f"  {c.liga}  --  rodada {c.rodada} de {c.total_de_rodadas}")
    print(f"  {'':4s}{'clube':26s}{'P':>3}{'J':>3}{'V':>3}{'E':>3}{'D':>3}"
          f"{'GP':>4}{'GC':>4}{'SG':>5}")
    for i, r in enumerate(c.tabela(), 1):
        clube = c.world.clubs[r.club_id]
        marca = ">" if r.club_id == c.clube_id else " "
        print(f"  {marca}{i:3d}{clube.name:26s}{r.points:3d}{r.played:3d}{r.wins:3d}"
              f"{r.draws:3d}{r.losses:3d}{r.goals_for:4d}{r.goals_against:4d}"
              f"{r.goal_diff:+5d}")


# ---------------------------------------------------------------- escalacao

def _desenhar_campo(c: Carreira, onze: list[int], tatica: Tatica) -> None:
    """Campo em texto, com o onze distribuido por linha, como na tela de escalar."""
    jogadores = [c.world.players[i] for i in onze]
    por_grupo: dict[str, list] = {}
    for p in jogadores:
        por_grupo.setdefault(p.position, []).append(p)
    print()
    print("  " + "_" * (LARGURA - 4))
    for grupo, rotulo in (("FW", "ataque"), ("MF", "meio"), ("DF", "defesa"),
                          ("GK", "gol")):
        linha = por_grupo.get(grupo, [])
        if not linha:
            continue
        largura_util = LARGURA - 14
        celula = largura_util // max(len(linha), 1)
        # o nome encolhe conforme a linha enche: com 5 zagueiros ainda tem de caber
        limite = max(4, celula - 10)
        nomes = []
        for p in linha:
            curto = p.name if len(p.name) <= limite else p.name[:limite - 1] + "."
            nomes.append(f"{curto} {p.overall}/{p.condition}%")
        corpo = "".join(n.center(celula) for n in nomes)
        print(f"  |{rotulo:>7s} {corpo[:largura_util]:<{largura_util}s}|")
        print(f"  |{'':>7s} {'':<{largura_util}s}|")
    print("  " + "-" * (LARGURA - 4))


def tela_escalacao(c: Carreira) -> None:
    tatica = c.tatica_atual()
    onze = c.escalacao_atual()
    while True:
        _desenhar_campo(c, onze, tatica)
        vagas = ", ".join(f"{g} {n}" for g, n in tatica.vagas.items())
        print(f"  TATICA: {tatica.como_texto()}   ({vagas})")
        media = sum(c.world.players[i].condition for i in onze) / len(onze)
        print(f"  onze: overall medio {sum(c.world.players[i].overall for i in onze)/11:.1f}"
              f" | energia media {media:.0f}%")
        print(_linha())
        print("  RESERVAS")
        titulares = set(onze)
        reservas = sorted((p for p in c.world.squad(c.clube_id) if p.id not in titulares),
                          key=lambda p: (POSICAO_ORDEM.get(p.position, 9), -p.overall))
        for p in reservas[:12]:
            print(f"    {p.id:5d}  {p.position:4s}{p.name:24s}{p.overall:4d}"
                  f"  {_barra(p.condition)} {p.condition:3d}%")
        if len(reservas) > 12:
            print(f"    ... e mais {len(reservas) - 12}")
        print(_linha())
        print("  [t] trocar jogador   [f] formacao   [m] marcacao   [e] estilo")
        print("  [a] escalar automatico (melhores e mais inteiros)   [s] salvar e voltar")
        escolha = input("  > ").strip().lower()

        if escolha == "s":
            try:
                c.escalar(onze, tatica)
            except ValueError as e:
                print(f"  !! {e}")
                continue
            return
        if escolha == "a":
            c.world.escalacao_fixa.pop(c.clube_id, None)
            onze = [p.id for p in c.world.best_xi(c.clube_id, tatica.vagas)]
        elif escolha == "t":
            sai = input("  sai (id): ").strip()
            entra = input("  entra (id): ").strip()
            if sai.isdigit() and entra.isdigit() and int(sai) in onze:
                onze = [int(entra) if i == int(sai) else i for i in onze]
            else:
                print("  !! ids invalidos")
        elif escolha in ("f", "m", "e"):
            campo, opcoes = {"f": ("formacao", FORMACOES),
                             "m": ("marcacao", MARCACOES),
                             "e": ("estilo", ESTILOS)}[escolha]
            print("  opcoes: " + ", ".join(sorted(opcoes)))
            valor = input(f"  {campo}: ").strip()
            if valor in opcoes:
                setattr(tatica, campo, valor)
                if campo == "formacao":
                    c.world.escalacao_fixa.pop(c.clube_id, None)
                    onze = [p.id for p in c.world.best_xi(c.clube_id, tatica.vagas)]
            else:
                print("  !! opcao invalida")


# ---------------------------------------------------------------- partida

def tela_partida(c: Carreira) -> None:
    """A rodada: o seu jogo em destaque e todos os outros acontecendo junto."""
    jogo = c.proxima_partida()
    resultados = c.avancar()
    meu = next((r for r in resultados if c.clube_id in (r.home, r.away)), None)

    print()
    print(_linha("="))
    print(f"  RODADA {c.rodada}".center(LARGURA))
    print(_linha("="))
    if meu:
        casa, fora = c.world.clubs[meu.home], c.world.clubs[meu.away]
        print()
        print(f"  {casa.name:>30s}   {meu.goals_home}  x  {meu.goals_away}   "
              f"{fora.name}")
        venceu = ((meu.goals_home > meu.goals_away and meu.home == c.clube_id)
                  or (meu.goals_away > meu.goals_home and meu.away == c.clube_id))
        empatou = meu.goals_home == meu.goals_away
        print(f"  {'VITORIA' if venceu else 'EMPATE' if empatou else 'DERROTA':^{LARGURA-4}s}")
        print()
        t = c.tatica_atual() if jogo else None
        if t:
            print(f"  sua tatica: {t.como_texto()}")
    print(_linha())
    print("  OUTROS JOGOS DA RODADA")
    for r in resultados:
        if meu and r is meu:
            continue
        casa, fora = c.world.clubs[r.home], c.world.clubs[r.away]
        print(f"    {casa.name:>26s}  {r.goals_home} x {r.goals_away}  {fora.name}")
    print(_linha())
    tabela = c.tabela()
    print(f"  Voce esta em {c.posicao()}o lugar com "
          f"{next(r.points for r in tabela if r.club_id == c.clube_id)} pontos.")
    input("  [enter] volta ao lobby ")


# ---------------------------------------------------------------- ciclo

def jogar(c: Carreira) -> None:
    """O ciclo: lobby -> escalar -> partida -> lobby."""
    while True:
        tela_lobby(c)
        escolha = input("  > ").strip().lower()
        if escolha == "1":
            if c.acabou:
                print("  !! a temporada acabou")
                continue
            tela_escalacao(c)
        elif escolha == "2":
            if c.acabou:
                print("  !! a temporada acabou")
                continue
            tela_partida(c)
        elif escolha == "3":
            tela_tabela(c)
            input("  [enter] ")
        elif escolha == "4":
            elenco = sorted(c.world.squad(c.clube_id),
                            key=lambda p: (POSICAO_ORDEM.get(p.position, 9), -p.overall))
            print()
            for p in elenco:
                print(f"    {p.id:5d}  {p.position:4s}{p.name:24s}{p.overall:4d}"
                      f"{p.potential:5d}{p.age(c.temporada):4d}  {p.condition:3d}%"
                      f"{_dinheiro(p.market_value):>10}")
            input("  [enter] ")
        elif escolha == "5":
            nome = input("  nome do save: ").strip() or "carreira"
            destino = c.salvar(nome)
            print(f"  salvo em {destino}")
            input("  [enter] ")
        elif escolha == "0":
            print("  ate mais.")
            return
