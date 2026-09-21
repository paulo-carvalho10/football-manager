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


def cmd_diagnostico(args):
    """Roda os diagnosticos da conversao valor -> overall sobre um pack importado."""
    from fm.diagnostics import diagnosticar
    from fm.pack import load_pack

    pack = load_pack(args.pack)
    jogadores = []
    for c in pack.clubes:
        ordenados = sorted(c.jogadores, key=lambda j: -(j.ovr or 0))
        titulares = {id(j) for j in ordenados[:11]}
        for j in c.jogadores:
            jogadores.append({
                "nome": j.nome, "ovr": j.ovr or 0, "posicao": j.pos, "idade": j.idade,
                "valor": j.valor, "titular": id(j) in titulares})
    print()
    print(f"DIAGNOSTICO DA CONVERSAO  --  pack {args.pack}, {len(jogadores)} jogadores")
    print()
    for d in diagnosticar(jogadores):
        print(f"{'ok ' if d.ok else 'XX '} {d.nome:24s} {d.valor:8.2f}   "
              f"[{d.baixo}, {d.alto}]")
        if not d.ok:
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
