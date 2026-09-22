"""Baixa o mundo inteiro. Retomavel: tudo que ja esta em data/cache/ nao e rebaixado."""
import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fm.importer import transfermarkt as tm
from fm.importer.catalogo import catalogo_completo
from fm.importer.selecao import escolher
from fm.ratings import minutos_referencia

# Ligas de calendario agosto-maio estao na 5a rodada em setembro: 5 rodadas nao dizem quem
# e titular. Onde a referencia de minutos vier baixa, busca-se tambem a temporada anterior.
MIN_REFERENCIA = 1200

sel = escolher(catalogo_completo())
print(f"{len(sel)} ligas, {sum(c.clubes for c in sel)} clubes", flush=True)
t0 = time.perf_counter()
feitas = falhas = extras = 0

for n, c in enumerate(sel, 1):
    try:
        clubes = tm.extrair_clubes(tm.baixar_por_codigo(c.codigo))
        if not clubes:
            print(f"[{n}/{len(sel)}] {c.codigo}: sem clubes na pagina", flush=True)
            falhas += 1
            continue
        stats_todos = []
        for cl in clubes:
            tm.baixar_elenco(cl.verein_id)
            st = tm.extrair_estatisticas(tm.baixar_estatisticas(cl.verein_id))
            stats_todos += [{"minutos": s.get("minutos", 0)} for s in st.values()]
        ref = minutos_referencia(stats_todos)
        if ref < MIN_REFERENCIA:
            for cl in clubes:
                tm.baixar_estatisticas(cl.verein_id, "2025")
                extras += 1
        feitas += 1
        dt = time.perf_counter() - t0
        print(f"[{n}/{len(sel)}] {c.codigo:6s} {len(clubes):3d} clubes  ref={ref:5.0f}min"
              f"{'  +temporada passada' if ref < MIN_REFERENCIA else ''}"
              f"   {dt/60:5.1f}min decorridos", flush=True)
    except Exception as e:
        falhas += 1
        print(f"[{n}/{len(sel)}] {c.codigo}: ERRO {type(e).__name__}: {e}", flush=True)

print(f"\nFIM: {feitas} ligas ok, {falhas} falhas, {extras} paginas de temporada passada")
print(f"tempo total: {(time.perf_counter()-t0)/60:.1f} min", flush=True)
