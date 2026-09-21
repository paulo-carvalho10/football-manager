"""Etapa 3: junta as fontes, aplica fm.ratings e escreve o pack. Roda offline sobre o cache."""

from __future__ import annotations

from dataclasses import dataclass

from fm.importer import transfermarkt as tm
from fm.ratings import converter_elenco, forca_dos_clubes

# verein_id do Transfermarkt -> nome do clube no pack (nome popular da CBF).
# Mapeamento explicito de proposito: 20 linhas auditaveis valem mais que uma heuristica
# que um dia troca Athletico por Atletico sem ninguem perceber.
NOME_PACK = {
    "1023": "Palmeiras", "614": "Flamengo", "609": "Cruzeiro", "199": "Corinthians",
    "978": "Vasco da Gama", "537": "Botafogo", "2462": "Fluminense", "10010": "Bahia",
    "221": "Santos", "8793": "Red Bull Bragantino", "330": "Atletico Mineiro",
    "585": "Sao Paulo", "210": "Gremio", "6600": "Internacional",
    "679": "Athletico Paranaense", "776": "Coritiba", "2125": "Vitoria",
    "3876": "Mirassol", "10997": "Remo", "17776": "Chapecoense",
}

# Codigo_Clube da CBF, para cruzar com a fonte oficial depois.
ID_CBF = {
    "Flamengo": "20016", "Palmeiras": "20002", "Cruzeiro": "59849", "Botafogo": "60175",
    "Sao Paulo": "20005", "Atletico Mineiro": "62194", "Fluminense": "20014",
    "Internacional": "20011", "Corinthians": "20001", "Gremio": "20013",
    "Bahia": "61377", "Vasco da Gama": "60646", "Red Bull Bragantino": "20007",
    "Santos": "20008", "Athletico Paranaense": "20052", "Mirassol": "20385",
    "Vitoria": "20018", "Coritiba": "61590", "Chapecoense": "20086", "Remo": "20022",
}

MINUTOS_POR_JOGO = 90


@dataclass(slots=True)
class ClubeMontado:
    nome: str
    forca: float
    valor_elenco: int
    id_cbf: str | None
    id_tm: str
    jogadores: list[dict]


def baixar_tudo() -> tuple[list[tm.TMClube], dict[str, list[tm.TMJogador]],
                           dict[str, dict[str, dict[str, int]]]]:
    """Etapa 1+2: 41 paginas (1 liga + 20 elencos + 20 desempenhos), tudo cacheado."""
    clubes = tm.extrair_clubes(tm.baixar_liga())
    elencos = {c.verein_id: tm.extrair_elenco(tm.baixar_elenco(c.verein_id)) for c in clubes}
    stats = {c.verein_id: tm.extrair_estatisticas(tm.baixar_estatisticas(c.verein_id))
             for c in clubes}
    return clubes, elencos, stats


def montar(media_liga: float, beta_clube: float) -> list[ClubeMontado]:
    clubes, elencos, stats = baixar_tudo()
    forcas = forca_dos_clubes({c.verein_id: c.valor_elenco for c in clubes},
                              media_liga=media_liga, beta_clube=beta_clube)
    montados: list[ClubeMontado] = []
    for c in clubes:
        nome = NOME_PACK.get(c.verein_id, c.nome)
        bruto = []
        for j in elencos[c.verein_id]:
            st = stats[c.verein_id].get(j.spieler_id, {})
            minutos = st.get("minutos", 0)
            bruto.append({
                "nome": j.nome, "posicao": j.posicao, "idade": j.idade, "valor": j.valor,
                # o desconto de imaturidade usa partidas; minuto/90 e mais honesto que
                # "apareceu na sumula", entao converte-se minutos em jogos equivalentes
                "partidas": round(minutos / MINUTOS_POR_JOGO) if minutos else st.get("jogos", 0),
                "gols": st.get("gols", 0), "minutos": minutos,
                "id_fonte": j.spieler_id, "contrato_ate": j.contrato_ate,
                "nacionalidade": j.nacionalidade,
            })
        montados.append(ClubeMontado(
            nome=nome, forca=forcas[c.verein_id], valor_elenco=c.valor_elenco,
            id_cbf=ID_CBF.get(nome), id_tm=c.verein_id,
            jogadores=converter_elenco(bruto, forcas[c.verein_id])))
    return montados


def _esc(txt: str) -> str:
    return txt.replace("\\", "\\\\").replace('"', '\\"')


def escrever_pack(montados: list[ClubeMontado], destino, cabecalho: str) -> int:
    """Escreve o pack .toml. Jogadores ordenados por overall, para leitura humana."""
    L = [cabecalho.rstrip(), ""]
    n_jogadores = 0
    for c in sorted(montados, key=lambda x: -x.forca):
        L.append("[[clubes]]")
        L.append(f'nome = "{_esc(c.nome)}"')
        L.append(f"forca = {c.forca:.1f}")
        if c.id_cbf:
            L.append(f'id_fonte = "{c.id_cbf}"')
        L.append(f"valor_elenco = {c.valor_elenco}")
        for j in sorted(c.jogadores, key=lambda x: (-x["ovr"], x["nome"])):
            n_jogadores += 1
            L.append("")
            L.append("  [[clubes.jogadores]]")
            L.append(f'  nome = "{_esc(j["nome"])}"')
            if j.get("posicao"):
                L.append(f'  pos = "{j["posicao"]}"')
            if j.get("idade") is not None:
                L.append(f'  idade = {j["idade"]}')
            L.append(f'  ovr = {j["ovr"]}')
            L.append(f'  pot = {j["pot"]}')
            if j.get("valor") is not None:
                L.append(f'  valor = {j["valor"]}')
            if j.get("partidas"):
                L.append(f'  partidas = {j["partidas"]}')
            if j.get("minutos"):
                L.append(f'  minutos = {j["minutos"]}')
            if j.get("gols"):
                L.append(f'  gols = {j["gols"]}')
            if j.get("id_fonte"):
                L.append(f'  id_fonte = "{j["id_fonte"]}"')
        L.append("")
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    return n_jogadores
