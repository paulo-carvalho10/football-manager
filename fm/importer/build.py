"""Etapa 3: junta as fontes, aplica fm.ratings e escreve o pack. Roda offline sobre o cache."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fm.importer import transfermarkt as tm
from fm.ratings import converter_elenco

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
CORES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cores"
PACKS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "packs"


def carregar_cores(pack: str | None = None) -> dict[str, dict]:
    """Cores por nome de clube, de data/cores/*.toml.

    Fora do pack de proposito: o pack e gerado, entao cor editada nele sumiria na proxima
    importacao.

    O `packs` do arquivo delimita a que packs ele se aplica, porque nome de clube COLIDE
    entre paises: "Athletic Club" e o Bilbao na Espanha e o de Sao Joao del-Rei na Serie B
    do Brasil, e sem escopo o Bilbao saiu vestido de preto e amarelo. Arquivo sem `packs`
    vale para todos, que era o comportamento antigo.
    """
    import tomllib
    fora: dict[str, dict] = {}
    if not CORES_DIR.exists():
        return fora
    for arq in sorted(CORES_DIR.glob("*.toml")):
        with arq.open("rb") as fh:
            dados = tomllib.load(fh)
        escopo = dados.get("packs")
        if pack is not None and escopo and pack not in escopo:
            continue
        for c in dados.get("clubes", []):
            fora[c["nome"]] = c
    return fora


@dataclass(slots=True)
class ClubeMontado:
    nome: str
    forca: float
    valor_elenco: int
    id_cbf: str | None
    id_tm: str
    jogadores: list[dict]
    cores: dict | None = None   # a entrada inteira de data/cores/*.toml


def baixar_tudo(competicao: str = "bra_a") -> tuple[
        list[tm.TMClube], dict[str, list[tm.TMJogador]],
        dict[str, dict[str, dict[str, int]]]]:
    """Etapa 1+2: 1 pagina de liga + 2 por clube. Tudo cacheado em disco."""
    clubes = tm.extrair_clubes(tm.baixar_competicao(competicao))
    elencos = {c.verein_id: tm.extrair_elenco(tm.baixar_elenco(c.verein_id)) for c in clubes}
    stats = {c.verein_id: tm.extrair_estatisticas(tm.baixar_estatisticas(c.verein_id))
             for c in clubes}
    return clubes, elencos, stats


def baixar_passado(competicao: str, clubes) -> dict[str, dict[str, dict[str, int]]]:
    """Desempenho da temporada ANTERIOR, quando a liga tem uma configurada.

    Liga europeia em setembro tem 5 rodadas: nao da para saber quem e titular por isso.
    """
    temporada = tm.TEMPORADA_STATS.get(competicao)
    if not temporada:
        return {}
    return {c.verein_id: tm.extrair_estatisticas(
        tm.baixar_estatisticas(c.verein_id, temporada)) for c in clubes}


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
        if c.cores:
            L.append(f'cores = ["{c.cores["primaria"]}", "{c.cores["secundaria"]}"]')
            if camisa := c.cores.get("camisa"):
                L.append(f'camisa = ["{camisa[0]}", "{camisa[1]}"]')
            L.append(f'padrao = "{c.cores.get("padrao", "liso")}"')
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


BETAS_PADRAO = {"bra_a": 7.0, "bra_b": 4.0, "esp_1": 7.0, "esp_2": 5.0}

# Quem a importacao deixou de fora, por competicao. A CLI imprime -- descarte silencioso
# de pessoa real e pior que erro.
DESCARTADOS: dict[str, list[str]] = {}


def montar_mundo(betas: dict[str, float] | None = None) -> dict[str, list[ClubeMontado]]:
    """Monta varias competicoes juntas, para que o nivel ENTRE ligas saia do dado.

    Montar uma liga isolada obriga a chutar o nivel dela; montando todas de uma vez, o
    valor de elenco posiciona cada divisao em relacao as outras e a piramide fecha sozinha.
    """
    from fm.ratings import K_POS_POR_LIGA, forca_mundial, minutos_referencia

    betas = betas or BETAS_PADRAO
    baixado = {comp: baixar_tudo(comp) for comp in betas}
    valores = {comp: {c.verein_id: c.valor_elenco for c in clubes}
               for comp, (clubes, _, _) in baixado.items()}
    forcas = forca_mundial(valores, betas)

    mundo: dict[str, list[ClubeMontado]] = {}
    for comp, (clubes, elencos, stats) in baixado.items():
        # cada liga esta num ponto diferente da temporada: a referencia de minutos e dela
        cores = carregar_cores()
        passado = baixar_passado(comp, clubes)
        ref = minutos_referencia([{"minutos": s.get("minutos", 0)}
                                  for d in stats.values() for s in d.values()])
        ref_passado = minutos_referencia([{"minutos": s.get("minutos", 0)}
                                          for d in passado.values() for s in d.values()])
        montados = []
        descartados: list[str] = []
        for c in clubes:
            nome = NOME_PACK.get(c.verein_id) or tm.limpar_nome(c.nome)
            bruto = []
            for j in elencos[c.verein_id]:
                if not j.posicao:
                    # Posicao e informacao essencial e nao se chuta: chutar seria inventar
                    # dado sobre uma pessoa real. Sem ela, o jogador nao entra.
                    descartados.append(f"{j.nome} ({c.nome}): sem posicao na fonte")
                    continue
                st = stats[c.verein_id].get(j.spieler_id, {})
                ant = passado.get(c.verein_id, {}).get(j.spieler_id, {})
                minutos, min_ant = st.get("minutos", 0), ant.get("minutos", 0)
                # Quanto o jogador ja "entregou", normalizado pela temporada de CADA
                # fonte. Pega-se o maior: o veterano pontua pela temporada passada e o
                # reforco recem-chegado pontua pela atual.
                realizacao = max(
                    min(1.0, minutos / ref) if ref else 0.0,
                    min(1.0, min_ant / ref_passado) if ref_passado else 0.0)
                bruto.append({
                    "nome": j.nome, "posicao": j.posicao, "idade": j.idade,
                    "valor": j.valor, "gols": st.get("gols", 0) or ant.get("gols", 0),
                    "minutos": minutos or min_ant, "realizacao": realizacao,
                    "partidas": (round((minutos or min_ant) / MINUTOS_POR_JOGO)
                                 or st.get("jogos", 0) or ant.get("jogos", 0)),
                    "id_fonte": j.spieler_id,
                })
            forca = forcas[comp][c.verein_id]
            montados.append(ClubeMontado(
                nome=nome, forca=forca, valor_elenco=c.valor_elenco,
                id_cbf=ID_CBF.get(nome), id_tm=c.verein_id,
                cores=cores.get(nome),
                jogadores=converter_elenco(
                    bruto, forca, k_pos=K_POS_POR_LIGA.get(comp))))
        mundo[comp] = montados
        if descartados:
            DESCARTADOS[comp] = descartados
    return mundo


def aplicar_ajustes(pack: str, montados) -> list[str]:
    """Ajustes manuais do arquivo data/ajustes/<pack>.toml, aplicados apos a conversao."""
    from fm.importer.ajustes import aplicar
    return aplicar(pack, montados)


def reaplicar_cores(packs: list[Path] | None = None) -> dict[str, int]:
    """Reescreve `cores`, `camisa` e `padrao` nos packs ja gerados, a partir de
    data/cores/*.toml.

    Existe para separar a edicao visual da importacao. Trocar o padrao da camisa do Gremio
    nao deveria exigir rede, cache e uma re-importacao inteira do Transfermarkt -- e pack
    regerado tambem sobrescreveria qualquer ajuste manual de jogador.

    Mexe SO nas tres linhas de cor de cada clube, deixando o resto do arquivo intacto.
    """
    packs = packs or sorted(PACKS_DIR.glob("*.toml"))
    resumo: dict[str, int] = {}

    for caminho in packs:
        cores = carregar_cores(caminho.stem)
        linhas = caminho.read_text(encoding="utf-8").splitlines()
        fora: list[str] = []
        clube: dict | None = None
        trocados = 0
        for linha in linhas:
            if linha.startswith("nome = "):
                clube = cores.get(linha[7:].strip().strip('"'))
            elif linha.startswith("  "):
                clube = None                       # entrou nos jogadores
            if linha.startswith(("cores = ", "camisa = ", "padrao = ")):
                continue                           # as antigas saem; as novas entram abaixo
            fora.append(linha)
            if clube is not None and linha.startswith("valor_elenco = "):
                fora.append(f'cores = ["{clube["primaria"]}", "{clube["secundaria"]}"]')
                if camisa := clube.get("camisa"):
                    fora.append(f'camisa = ["{camisa[0]}", "{camisa[1]}"]')
                fora.append(f'padrao = "{clube.get("padrao", "liso")}"')
                trocados += 1
                clube = None
        caminho.write_text("\n".join(fora) + "\n", encoding="utf-8")
        resumo[caminho.stem] = trocados
    return resumo
