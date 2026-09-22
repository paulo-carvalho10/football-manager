"""Camada de apresentacao: o UNICO modulo do projeto autorizado a imprimir."""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from fm.calibration import report
from fm.competition import knockout_tie
from fm.config import available, load_league, mentality_of, style_of, targets_of
from fm.generate import build_world, strength_profile
from fm.match import Mentality
from fm.season import play_league_season

CABECALHO_PACK = """# {wettbewerb} -- GERADO por fm.importer. Nao editar a mao: rode o importador.
#
# Fonte: Transfermarkt (clube, posicao, idade, valor de mercado, jogos, minutos).
# ovr e pot sao DERIVADOS por fm/ratings.py a partir desses campos. Sao estimativa, nao
# rating oficial de ninguem, e a conta esta documentada no modulo.
#
# forca do clube = nivel_da_liga + {beta} * z(ln(valor de elenco) dentro da liga).
# O NIVEL da liga sai do valor medio de elenco na escala global de todas as competicoes
# importadas, com o melhor clube do mundo ancorado em 90 -- fazer z so por liga apagava a
# diferenca entre divisoes e o lanterna da Serie B saia mais forte que o da Serie A.
# O BETA e proprio desta liga e foi ajustado contra os [alvos] do arquivo dela.
verificado = false
fonte = "Transfermarkt {wettbewerb} (valores de mercado); ovr/pot derivados por fm.ratings"
"""


LEGEND = "* campeao | v rebaixado | onze = overall do titular | desen. = forca desenhada"


def _world(nome, seed):
    cfg = load_league(nome)
    world, streams = build_world([cfg], seed=seed)
    return cfg, world, streams


def cmd_temporada(args):
    cfg, world, streams = _world(args.liga, args.seed)
    nome, pais, cid = cfg["nome"], cfg["pais"], cfg["id"]
    rng = streams.get("match", world.season_year, cid)
    t0 = time.perf_counter()
    rep = play_league_season(world, cid, style_of(cfg), rng)
    dt = time.perf_counter() - t0

    print()
    print(f"{nome} {world.season_year}  ({pais}, seed {args.seed})")
    print("    clube                          P   J   V   E   D   GP   GC   SG   onze desen.")
    descem = int(cfg.get("formato", {}).get("acesso", {}).get("descem", 0))
    total = len(rep.table)
    for i, row in enumerate(rep.table, start=1):
        club = world.clubs[row.club_id]
        mark = "v" if i > total - descem else " "
        if i == 1:
            mark = "*"
        print(f"{mark}{i:2d} {club.name:28s} {row.points:3d} {row.played:3d} {row.wins:3d} "
              f"{row.draws:3d} {row.losses:3d} {row.goals_for:4d} {row.goals_against:4d} "
              f"{row.goal_diff:+4d}  {world.team_rating(club.id):5.1f} "
              f"{club.designed_strength:6.1f}")
    n = len(rep.results)
    gols = sum(r.goals_home + r.goals_away for r in rep.results)
    empates = sum(1 for r in rep.results if r.goals_home == r.goals_away)
    casa = sum(1 for r in rep.results if r.goals_home > r.goals_away)
    print()
    print(f"{n} partidas em {dt*1000:.0f} ms  |  {gols/n:.2f} gols/jogo  |  "
          f"casa {100*casa/n:.0f}%  empate {100*empates/n:.0f}%")
    print(LEGEND)


def cmd_calibrar(args):
    kw = {"seasons": args.temporadas, "seed": args.seed}
    alvo = "liga de referencia"
    if args.liga:
        cfg = load_league(args.liga)
        kw["style"] = style_of(cfg)
        kw["targets"] = targets_of(cfg)
        if args.usar_perfil_da_liga:
            kw["ratings"] = strength_profile(cfg, int(cfg["clubes"]))
            alvo = f"perfil de {args.liga}"
        else:
            alvo = f"liga de referencia, estilo de {args.liga}"

    t0 = time.perf_counter()
    metrics = report(**kw)
    dt = time.perf_counter() - t0

    print()
    print(f"PORTAO DE CALIBRACAO  --  {args.temporadas} temporadas, {alvo}")
    print("    metrica                          medido               alvo")
    for m in metrics:
        flag = "ok " if m.ok else "XX "
        print(f"{flag} {m.name:30s} {m.value:8.2f}   [{m.low:5.1f}, {m.high:5.1f}]")
    falhas = [m.name for m in metrics if not m.ok]
    partidas = args.temporadas * 380
    print()
    print(f"{partidas} partidas em {dt:.2f}s ({partidas/dt/1e6:.2f} M/s)")
    print("RESULTADO: mundo crivel" if not falhas else f"RESULTADO: FORA DA FAIXA {falhas}")


def cmd_perfis(args):
    print()
    print(f"CARATER EMERGENTE POR PERFIL DE FORCA  ({args.temporadas} temporadas cada)")
    print("mesmo motor, mesmas constantes -- muda so a distribuicao de overall dos clubes")
    print()
    print("liga                      campeao  lanterna  empate%   gols  marg3+%    gap"
          "  maior e campeao")
    for nome in available():
        cfg = load_league(nome)
        fases = cfg.get("formato", {}).get("fases", [{"tipo": "round_robin"}])
        if fases[0].get("tipo") != "round_robin":
            continue          # perfis compara ligas; copa nao tem tabela
        ratings = strength_profile(cfg, int(cfg["clubes"]))
        if len(ratings) % 2:
            continue
        m = {x.name: x.value for x in report(
            ratings=ratings, style=style_of(cfg), mentality=mentality_of(cfg),
            seasons=args.temporadas, seed=args.seed)}
        gap = m["pontos_do_campeao"] - m["pontos_do_lanterna"]
        rot = nome + " (" + cfg["pais"] + ")"
        print(f"{rot:24s} {m["pontos_do_campeao"]:8.1f} {m["pontos_do_lanterna"]:9.1f} "
              f"{m["empate_pct"]:8.1f} {m["gols_por_jogo"]:6.2f} "
              f"{m["margem_3_ou_mais_pct"]:8.1f} {gap:6.1f} "
              f"{m["melhor_elenco_campeao_pct"]:16.1f}%")


def cmd_copa(args):
    cfg = load_league(args.liga)
    ratings = strength_profile(cfg, int(cfg["clubes"]))
    n = len(ratings)
    if n & (n - 1):
        raise SystemExit(f"copa exige potencia de 2 clubes; {args.liga} tem {n}")
    style, mentality = style_of(cfg), mentality_of(cfg)
    rng = np.random.default_rng(args.seed)
    rounds = n.bit_length() - 1
    lut = dict(enumerate(ratings))

    print()
    print(f"COPA DE {n} CLUBES, {args.maos} mao(s), {args.edicoes} edicoes  --  {args.liga}")
    modos = (("mentalidade normal", Mentality.NORMAL), ("mentalidade copa", mentality))
    for rot, ment in modos:
        alive = np.tile(np.arange(n), (args.edicoes, 1))
        for _ in range(rounds):
            half = alive.shape[1] // 2
            a, b = alive[:, :half].ravel(), alive[:, half:].ravel()
            win = knockout_tie(list(b), list(a), lut, rng, style, ment, legs=args.maos)
            alive = win.reshape(args.edicoes, half)
            idx = np.arange(alive.shape[1])[None, :].repeat(args.edicoes, 0)
            alive = np.take_along_axis(alive, rng.permuted(idx, axis=1), axis=1)
        champs = alive.ravel()
        print(f"  {rot:20s} maior clube leva {100*np.mean(champs == 0):5.1f}% | "
              f"top-3 leva {100*np.mean(champs < 3):5.1f}%")


def cmd_elenco(args):
    cfg, world, _ = _world(args.liga, args.seed)
    club = world.clubs[sorted(world.clubs)[args.posicao - 1]]
    print()
    print(f"{club.name}  ({cfg["nome"]}, reputacao {club.reputation}, "
          f"desenhado {club.designed_strength:.1f}, onze {world.team_rating(club.id):.1f})")
    xi = {p.id for p in world.best_xi(club.id)}
    print("   pos  jogador                   ovr  pot  id  pe  cond     valor  salario   fim")
    for p in sorted(world.squad(club.id), key=lambda x: -x.effective_overall):
        titular = ">" if p.id in xi else " "
        print(f"{titular}  {p.position:4s} {p.name:24s} {p.overall:4d} {p.potential:4d} "
              f"{p.age(world.season_year):3d} {p.foot:>3s} {p.condition:5d} "
              f"{p.market_value/1e6:8.1f}M {p.wage/1e3:7.0f}k {p.contract_until:5d}")
    print("> = titular")


# nome do pack e liga que valida, por competicao
SAIDA_PADRAO = {
    "bra_a": ("brasil_serie_a", "brasil_real"),
    "bra_b": ("brasil_serie_b", "brasil_b_real"),
    "esp_1": ("espanha_primera", "espanha_real"),
    "esp_2": ("espanha_segunda", "espanha_b_real"),
}


def cmd_importar(args):
    """Baixa, deriva overall e escreve os packs. Etapas 1 + 2 + 3.

    Monta SEMPRE o mundo inteiro, mesmo para gravar um pack so: o nivel de uma liga em
    relacao as outras sai do valor de elenco de todas juntas. Rede so na primeira vez.
    """
    from pathlib import Path

    from fm.calibration import report
    from fm.importer.build import (
        BETAS_PADRAO,
        DESCARTADOS,
        aplicar_ajustes,
        escrever_pack,
        montar_mundo,
    )
    from fm.importer.transfermarkt import COMPETICOES

    alvos = sorted(COMPETICOES) if args.competicao == "todas" else [args.competicao]
    for c in alvos:
        if c not in COMPETICOES:
            raise SystemExit(f"competicao desconhecida; use 'todas' ou {sorted(COMPETICOES)}")

    print()
    print("IMPORTANDO " + ", ".join(alvos))
    print("rede so na primeira vez; depois tudo vem de data/cache/")
    mundo = montar_mundo()

    for comp in alvos:
        montados = mundo[comp]
        saida, liga = SAIDA_PADRAO[comp]
        for linha in aplicar_ajustes(saida, montados):
            print(f"    ajuste manual: {linha}")
        for linha in DESCARTADOS.get(comp, []):
            print(f"    descartado: {linha}")
        forcas = [c.forca for c in montados]
        n_jog = sum(len(c.jogadores) for c in montados)
        print()
        print(f"  {comp}: {len(montados)} clubes, {n_jog} jogadores, "
              f"forcas {max(forcas):.1f}..{min(forcas):.1f}")

        cfg = load_league(liga)
        ms = report(targets=targets_of(cfg), ratings=forcas, style=style_of(cfg),
                    seasons=args.temporadas, seed=2026)
        fora = [f"{m.name}={m.value:.2f} [{m.low}, {m.high}]" for m in ms if not m.ok]
        print(f"    portao de {liga}: "
              + ("todos os alvos ok" if not fora else f"FORA DA FAIXA {fora}"))

        destino = Path("data/packs") / f"{saida}.toml"
        escrever_pack(montados, destino, CABECALHO_PACK.format(
            wettbewerb=COMPETICOES[comp][1], beta=BETAS_PADRAO[comp]))
        print(f"    escrito {destino} ({destino.stat().st_size / 1024:.0f} KB)")


def _ordem_de_dependencia(nomes, carregar):
    """Copa antes de continental: um torneio que se alimenta de outro roda depois dele."""
    torneios = {n: carregar(n) for n in nomes}
    depende = {
        n: {r["fonte"] for r in t.classificacao_regras if r["fonte"] in torneios}
        | set(t.qualificados_de) & set(torneios)
        for n, t in torneios.items()
    }
    ordem, pendente = [], dict(depende)
    while pendente:
        prontos = sorted(n for n, d in pendente.items() if not (d - set(ordem)))
        if not prontos:                      # ciclo: resolve na ordem alfabetica
            prontos = [sorted(pendente)[0]]
        for n in prontos:
            ordem.append(n)
            pendente.pop(n)
    return ordem


def cmd_torneio(args):
    """Simula as competicoes de copa e continentais sobre o mundo das ligas importadas."""
    from fm.generate import build_world
    from fm.rng import Streams
    from fm.torneio import carregar, classificacao, disponiveis, simular

    ligas = [load_league(n) for n in available()
             if (load_league(n).get("formato", {}).get("fases", [{}])[0].get("tipo")
                 == "round_robin")]
    world, _ = build_world(ligas, seed=args.seed)
    streams = Streams(args.seed)

    # As vagas saem da CLASSIFICACAO, entao a temporada de cada liga roda primeiro.
    tabelas: dict[str, list[int]] = {}
    for cfg in ligas:
        liga = world.leagues[cfg["id"]]
        ordem = classificacao(world, liga, style_of(cfg),
                              streams.get("liga", cfg["id"], args.seed))
        tabelas[cfg["id"]] = ordem
        if liga.codigo:
            tabelas[liga.codigo] = ordem
    print(f"{len(ligas)} ligas simuladas -- as vagas saem da tabela final")

    alvos = disponiveis() if args.torneio == "todos" else [args.torneio]
    copas: dict[str, list[int]] = {}
    ocupados_por_edicao: dict[int, set[int]] = {}
    for nome in _ordem_de_dependencia(alvos, carregar):
        t = carregar(nome)
        elenco = None
        if t.qualificados_de:
            elenco = [copas[q][0] for q in t.qualificados_de if q in copas]
            if len(elenco) < 2:
                print()
                print(f"{t.nome}: faltam os campeoes de {t.qualificados_de}")
                continue

        titulos: dict[int, int] = {}
        canonico = None
        for ed in range(args.edicoes):
            rng = streams.get("torneio", nome, ed)
            saidas: dict[str, list[int]] = {}
            # a vaga e unica na temporada: quem ja pegou noutro torneio nao entra aqui
            reservados = set(ocupados_por_edicao.setdefault(ed, set()))
            fim = simular(world, t, rng,
                          elenco=list(elenco) if elenco is not None else None,
                          tabelas=tabelas, copas=copas, exportados=saidas,
                          ocupados=reservados)
            ocupados_por_edicao[ed] = reservados
            if not fim:
                break
            titulos[fim[0]] = titulos.get(fim[0], 0) + 1
            if canonico is None:
                canonico = fim
                # o funil: quem caiu deste torneio alimenta o de baixo
                for balde, clubes in saidas.items():
                    copas[f"{nome}:{balde}"] = clubes
        if canonico is None:
            print()
            print(f"{t.nome}: nao rodou (participantes de menos)")
            continue
        copas[nome] = canonico

        print()
        print(f"{t.nome}  --  campeao da temporada: {world.clubs[canonico[0]].name}"
              + (f", vice: {world.clubs[canonico[1]].name}" if len(canonico) > 1 else ""))
        print(f"   titulos em {args.edicoes} edicoes:")
        for cid, n in sorted(titulos.items(), key=lambda x: -x[1])[:6]:
            print(f"     {100*n/args.edicoes:5.1f}%  {world.clubs[cid].name}")


def cmd_diagnostico(args):
    """Roda os diagnosticos da conversao valor -> overall sobre um pack importado."""
    from fm.diagnostics import diagnosticar
    from fm.pack import load_pack

    pack = load_pack(args.pack)
    clubes = [{"nome": c.nome,
               "jogadores": [{"nome": j.nome, "ovr": j.ovr or 0, "posicao": j.pos,
                              "idade": j.idade, "valor": j.valor} for j in c.jogadores]}
              for c in pack.clubes]
    n = sum(len(c["jogadores"]) for c in clubes)
    print()
    print(f"DIAGNOSTICO DA CONVERSAO  --  pack {args.pack}, "
          f"{len(clubes)} clubes, {n} jogadores")
    print()
    for d in diagnosticar(clubes):
        if d.informativo:
            marca = "ok " if d.dentro_da_faixa else "!! "
        else:
            marca = "ok " if d.ok else "XX "
        print(f"{marca} {d.nome:30s} {d.valor:8.2f}   [{d.baixo}, {d.alto}]")
        if not d.dentro_da_faixa:
            print(f"      -> {d.explicacao}")


def main(argv=None):
    # console do Windows abre em cp1252 e engasga com acento -- e um jogo em portugues
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="fm", description="Motor de futebol -- carreira local")
    # --seed vale para todos os subcomandos, antes ou depois do nome do comando
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seed", type=int, default=2027)
    ap.add_argument("--seed", type=int, default=2027)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("temporada", parents=[common],
                       help="simula uma temporada e imprime a tabela")
    p.add_argument("--liga", default="brasil")
    p.set_defaults(func=cmd_temporada)

    p = sub.add_parser("calibrar", parents=[common], help="portao de qualidade: o mundo e crivel?")
    p.add_argument("--temporadas", type=int, default=1000)
    p.add_argument("--liga", default=None)
    p.add_argument("--usar-perfil-da-liga", action="store_true")
    p.set_defaults(func=cmd_calibrar)

    p = sub.add_parser("perfis", parents=[common], help="compara o carater emergente de cada liga")
    p.add_argument("--temporadas", type=int, default=800)
    p.set_defaults(func=cmd_perfis)

    p = sub.add_parser("copa", parents=[common], help="liga x copa: quanto o gigante ganha de cada")
    p.add_argument("--liga", default="copa_brasil")
    p.add_argument("--edicoes", type=int, default=20000)
    p.add_argument("--maos", type=int, default=2)
    p.set_defaults(func=cmd_copa)

    p = sub.add_parser("importar", parents=[common],
                       help="baixa uma competicao e gera o pack com ovr derivado")
    p.add_argument("--competicao", default="todas",
                   help="todas, bra_a, bra_b, esp_1 ou esp_2")
    p.add_argument("--temporadas", type=int, default=1500)
    p.set_defaults(func=cmd_importar)

    p = sub.add_parser("torneio", parents=[common],
                       help="simula Champions, Libertadores e Intercontinental")
    p.add_argument("--torneio", default="todos",
                   help="todos, champions, libertadores ou intercontinental")
    p.add_argument("--edicoes", type=int, default=2000)
    p.set_defaults(func=cmd_torneio)

    p = sub.add_parser("diagnostico", parents=[common],
                       help="valida a conversao valor -> overall de um pack")
    p.add_argument("--pack", default="brasil_serie_a")
    p.set_defaults(func=cmd_diagnostico)

    p = sub.add_parser("elenco", parents=[common], help="mostra o elenco de um clube")
    p.add_argument("--liga", default="brasil")
    p.add_argument("--posicao", type=int, default=1, help="1 = clube mais forte do arquivo")
    p.set_defaults(func=cmd_elenco)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
