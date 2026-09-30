"""O que as telas do PRANCHETA 11 pedem e o lobby antigo nao tinha.

Funcoes puras de Carreira (ou de mundo) para dict: nenhuma regra nova mora aqui. Quando
uma tela pede algo que o motor nao simula -- estadio, publico, lesao --, a funcao nao
inventa: o campo simplesmente nao existe, e a tela nao o desenha.
"""

from __future__ import annotations

from fm.carreira import Carreira
from fm.config import load_league

VERSAO = "0.11"

# ------------------------------------------------------------------ catalogo de ligas
# As oito ligas nacionais estao liberadas desde 28/09/2026 (decisao do Paulo: o cadeado da
# versao completa volta quando existir a versao paga de verdade). O campo `livre` continua
# aqui para isso.
NACIONAIS = [
    {"pais": "BRA", "nome": "Brasil", "cores": ["#009c3b", "#ffdf00"], "livre": True,
     "ligas": [("brasil_real", "Série A"), ("brasil_b_real", "Série B")]},
    {"pais": "ESP", "nome": "Espanha", "cores": ["#aa151b", "#f1bf00"], "livre": True,
     "ligas": [("espanha_real", "LaLiga"), ("espanha_b_real", "LaLiga 2")]},
    {"pais": "ENG", "nome": "Inglaterra", "cores": ["#ffffff", "#cf142b"], "livre": True,
     "ligas": [("inglaterra_real", "Premier League"), ("inglaterra_b_real", "Championship")]},
    {"pais": "ITA", "nome": "Itália", "cores": ["#009246", "#ce2b37"], "livre": True,
     "ligas": [("italia_real", "Serie A"), ("italia_b_real", "Serie B")]},
    {"pais": "GER", "nome": "Alemanha", "cores": ["#000000", "#dd0000"], "livre": True,
     "ligas": [("alemanha_real", "Bundesliga"), ("alemanha_b_real", "2. Bundesliga")]},
    {"pais": "FRA", "nome": "França", "cores": ["#0055a4", "#ef4135"], "livre": True,
     "ligas": [("franca_real", "Ligue 1"), ("franca_b_real", "Ligue 2")]},
    {"pais": "POR", "nome": "Portugal", "cores": ["#006600", "#ff0000"], "livre": True,
     "ligas": [("portugal_real", "Liga Portugal"), ("portugal_b_real", "Liga Portugal 2")]},
    {"pais": "ARG", "nome": "Argentina", "cores": ["#75aadb", "#ffffff"], "livre": True,
     "ligas": [("argentina_real", "Liga Profesional"), ("argentina_b_real", "Primera Nacional")]},
]
# Estaduais nao existem no motor. Nao sao "premium": sao trabalho por fazer.
ESTADUAIS = ["Paulista", "Carioca", "Mineiro", "Gaúcho", "Paranaense", "Baiano",
             "Pernambucano", "Catarinense", "Goiano", "Cearense"]
COPAS_POR_PAIS = {
    "BRA": ["Copa do Brasil", "Copa Libertadores", "Copa Sul-Americana"],
    "ESP": ["Liga dos Campeões", "Liga Europa"],
    "ENG": ["Liga dos Campeões", "Liga Europa"],
    "ITA": ["Liga dos Campeões", "Liga Europa"],
    "GER": ["Liga dos Campeões", "Liga Europa"],
    "FRA": ["Liga dos Campeões", "Liga Europa"],
    "POR": ["Liga dos Campeões", "Liga Europa"],
    "ARG": ["Copa Libertadores", "Copa Sul-Americana"],
}


# o nome que a tela mostra: o do arquivo da liga vem sem acento ("Serie A")
NOMES_DE_LIGA = {i: nome for n in NACIONAIS for i, nome in n["ligas"] if i}


def nome_da_liga(chave: str) -> str:
    return NOMES_DE_LIGA.get(chave) or load_league(chave).get("nome", chave)


_POR_ID: dict[str, str] = {}


def nome_da_liga_por_id(lid: str, padrao: str = "") -> str:
    """O mundo conhece a liga pelo id interno (bra_a_real); a tela, pelo nome."""
    if not _POR_ID:
        for chave in NOMES_DE_LIGA:
            _POR_ID[load_league(chave)["id"]] = NOMES_DE_LIGA[chave]
    return _POR_ID.get(lid, padrao or lid)


def catalogo() -> dict:
    return {
        "nacionais": [
            {"pais": n["pais"], "nome": n["nome"], "cores": n["cores"],
             "livre": n["livre"],
             "ligas": [{"id": i, "nome": nome, "divisao": d}
                       for d, (i, nome) in enumerate(n["ligas"], 1)]}
            for n in NACIONAIS],
        "estaduais": ESTADUAIS,
        "copas": COPAS_POR_PAIS,
        "versao": VERSAO,
    }


# ------------------------------------------------------------------ escolha do clube

_MUNDOS: dict[tuple, object] = {}


def _mundo(ligas: tuple[str, ...], seed: int):
    """O mundo e caro de montar (meio segundo) e a tela de clubes filtra muitas vezes."""
    from fm.generate import build_world
    chave = (ligas, seed)
    if chave not in _MUNDOS:
        _MUNDOS.clear()
        _MUNDOS[chave] = build_world([load_league(n) for n in ligas], seed=seed)[0]
    return _MUNDOS[chave]


def clubes(ligas: list[str], seed: int, clube_json) -> dict:
    """Os clubes que a carreira pode assumir, com o que pesa na escolha."""
    from fm.diretoria import definir_meta
    from fm.financas import folha_anual, valor_do_elenco

    livres = {i for n in NACIONAIS if n["livre"] for i, _ in n["ligas"]}
    ligas = [n for n in ligas if n in livres]
    if not ligas:
        return {"clubes": [], "jogadores": 0, "ligas": []}
    world = _mundo(tuple(ligas), seed)
    fora = []
    for nome in ligas:
        cfg = load_league(nome)
        ids = world.leagues[cfg["id"]].club_ids
        forca = sorted(ids, key=lambda i: -world.team_rating(i))
        for cid in ids:
            club = world.clubs[cid]
            elenco = world.squad(cid)
            meta = definir_meta(world, cid, ids, int(cfg.get("tier", 1)))
            estrelas = sorted(elenco, key=lambda p: -p.overall)[:3]
            fora.append({
                **clube_json(world, cid), "liga": nome, "liga_nome": nome_da_liga(nome),
                "pais": cfg.get("pais", ""), "divisao": int(cfg.get("tier", 1)),
                "forca": round(float(world.team_rating(cid)), 1),
                "ranking": forca.index(cid) + 1, "de": len(ids),
                "reputacao": club.reputation, "caixa": club.balance,
                "valor_do_elenco": valor_do_elenco(world, cid),
                "folha": folha_anual(world, cid),
                "jogadores": len(elenco),
                "idade_media": round(sum(p.age(world.season_year) for p in elenco)
                                     / max(len(elenco), 1), 1),
                "meta": meta.texto,
                "estrelas": [{"nome": p.name, "posicao": p.position,
                              "overall": p.overall} for p in estrelas],
            })
    return {"clubes": fora, "jogadores": len(world.players),
            "temporada": world.season_year,
            "ligas": [{"id": n, "nome": nome_da_liga(n)} for n in ligas]}


# ------------------------------------------------------------------ mercado

def mercado(c: Carreira, filtros: dict, clube_json) -> dict:
    """Todos os jogadores do mundo fora do seu elenco, filtrados.

    So leitura e lista de observacao: a negociacao (proposta, contraproposta, emprestimo)
    ainda nao existe no motor. Quem compra hoje e a janela automatica da virada do ano.
    """
    def num(chave, padrao):
        try:
            return int(filtros.get(chave, [padrao])[0])
        except (TypeError, ValueError):
            return padrao

    from fm import negocios as neg

    def texto(chave):
        return filtros.get(chave, [""])[0].strip().lower()

    pos = filtros.get("pos", [""])[0]
    nome = texto("nome")
    liga = filtros.get("liga", [""])[0]
    nacionalidade = texto("nacionalidade")
    clube_busca = texto("clube")
    situacao = filtros.get("situacao", [""])[0]
    if filtros.get("observados", [""])[0] == "1":
        situacao = "lista"
    idade_min, idade_max = num("idade_min", 15), num("idade_max", 45)
    ovr_min = num("ovr_min", 0)
    valor_max = num("valor_max", 0)
    salario_max = num("salario_max", 0)
    ano = c.temporada
    ligas_do_clube = {cid: lg for lg in c.world.leagues.values() for cid in lg.club_ids}
    observados = set(c.observados)
    # titulares de cada clube: quem NAO esta aqui e o que o clube aceita vender ("a venda")
    titulares: set[int] = set()
    if situacao == "a_venda":
        for cid in c.world.clubs:
            titulares |= {x.id for x in c.world.best_xi(cid)}

    fora = []
    for p in c.world.players.values():
        livre = p.club_id not in c.world.clubs
        if p.club_id == c.clube_id:
            continue
        if situacao == "lista" and p.id not in observados:
            continue
        if situacao == "sem_contrato" and not livre:
            continue
        if situacao == "terminando" and (livre or p.contract_until > ano):
            continue
        if situacao == "a_venda" and (livre or p.id in titulares):
            continue
        if pos and p.position != pos:
            continue
        idade = p.age(ano)
        if not idade_min <= idade <= idade_max or p.overall < ovr_min:
            continue
        if valor_max and p.market_value > valor_max:
            continue
        if salario_max and p.wage > salario_max:
            continue
        lg = ligas_do_clube.get(p.club_id)
        if liga and (lg is None or lg.id != liga):
            continue
        if nome and nome not in p.name.lower():
            continue
        if nacionalidade and nacionalidade not in (p.nationality or "").lower():
            continue
        if clube_busca and (livre or clube_busca not in c.world.clubs[p.club_id].name.lower()):
            continue
        fora.append((p, lg, idade, livre))
    fora.sort(key=lambda x: -x[0].overall)
    return {
        "total": len(fora),
        "caixa": neg.resumo_do_caixa(c),
        "ligas": [{"id": lg.id, "nome": nome_da_liga_por_id(lg.id, lg.name)}
                  for lg in c.world.leagues.values()],
        "jogadores": [
            {"id": p.id, "nome": p.name, "posicao": p.position,
             "detalhe": p.position_detail, "idade": idade, "overall": p.overall,
             "potencial": p.potential, "valor": p.market_value, "salario": p.wage,
             "contrato": p.contract_until, "pe": p.foot, "nacionalidade": p.nationality,
             "clube": None if livre else clube_json(p.club_id), "livre": livre,
             "liga": nome_da_liga_por_id(lg.id, lg.name) if lg else "",
             "observado": p.id in observados}
            for p, lg, idade, livre in fora[:250]],
    }


def observar(c: Carreira, pid: int) -> dict:
    if pid in c.observados:
        c.observados.remove(pid)
    elif pid in c.world.players:
        c.observados.append(pid)
    return {"observados": list(c.observados)}


# ------------------------------------------------------------------ mensagens

def mensagens(c: Carreira, data_texto: str, lidas: set[str]) -> list[dict]:
    """A caixa de entrada, montada do estado do clube a cada leitura.

    Nao e um historico gravado: e o que a diretoria, a torcida, o preparador e o olheiro
    diriam HOJE. Por isso cada mensagem tem uma chave estavel -- lida continua lida.
    """
    fora: list[dict] = []

    def msg(chave, remetente, assunto, texto, tipo="info"):
        fora.append({"id": chave, "remetente": remetente, "assunto": assunto,
                     "texto": texto, "tipo": tipo, "data": data_texto,
                     "lida": chave in lidas})

    ap = c.aprovacao
    if ap and ap.meta:
        msg(f"meta:{c.temporada}", "Diretoria", "Objetivo da temporada",
            f"A diretoria espera {ap.meta.texto}. Confiança atual: "
            f"{ap.diretoria:.0f}%.")
    if ap and ap.clima in ("pressionado", "insustentavel"):
        msg(f"pressao:{c.temporada}:{c.data // 4}", "Diretoria", "Cobrança",
            f"O ambiente está {ap.clima}. A diretoria quer reação imediata.", "alerta")
    if ap and ap.torcida < 40:
        msg(f"torcida:{c.temporada}:{c.data // 4}", "Torcida organizada", "Protesto",
            f"A aprovação da torcida caiu para {ap.torcida:.0f}%.", "alerta")
    elif ap and ap.torcida >= 80:
        msg(f"festa:{c.temporada}:{c.data // 4}", "Torcida", "Apoio total",
            f"A torcida está com o time: {ap.torcida:.0f}% de aprovação.")

    comp = c.competicao_do_proximo()
    if comp and c.disciplina is not None:
        meus = {p.id: p for p in c.world.squad(c.clube_id)}
        nome_comp = nome_da_competicao(c, comp)
        suspensos = [meus[i].name for i in c.disciplina.suspensos(comp) if i in meus]
        if suspensos:
            msg(f"suspensos:{c.temporada}:{c.data}:{','.join(sorted(suspensos))}",
                "Comissão técnica", "Desfalques por suspensão",
                f"Não podem jogar a próxima partida da {nome_comp}: {', '.join(suspensos)}. "
                "Se estiverem na escalação, entra o melhor reserva do mesmo setor.", "alerta")
        pendurados = [meus[i].name for i in c.disciplina.pendurados(comp) if i in meus]
        if pendurados:
            msg(f"pendurados:{c.temporada}:{c.data}:{','.join(sorted(pendurados))}",
                "Comissão técnica", "Pendurados",
                f"Com mais um amarelo na {nome_comp}, ficam fora do jogo seguinte: "
                f"{', '.join(pendurados)}.")

    if c.medico is not None:
        w = c.world
        hoje = c.hoje()
        for pid, tipo, dias in c.boletim_medico.get("lesoes", []):
            les = c.medico.lesionados.get(pid)
            if pid in w.players and les is not None:
                msg(f"lesao:{c.temporada}:{c.data}:{pid}", "Departamento médico",
                    f"Lesão: {w.players[pid].name}",
                    f"{w.players[pid].name} sofreu {tipo}: tempo de recuperação de cerca de "
                    f"{dias} dias, volta a partir de {les.volta.strftime('%d/%m')}. Até lá, "
                    "se estiver na escalação, entra o melhor reserva do mesmo setor.", "alerta")
        voltaram = [w.players[i].name for i in c.boletim_medico.get("voltaram", [])
                    if i in w.players]
        if voltaram:
            msg(f"alta:{c.temporada}:{c.data}", "Departamento médico", "Liberados",
                f"Recuperados e à disposição: {', '.join(voltaram)}.")
        ainda = [f"{w.players[i].name} (volta {les.volta.strftime('%d/%m')}, "
                 f"{les.dias_restantes(hoje)} dias)"
                 for i, les in sorted(c.lesionados_do_clube().items(),
                                      key=lambda x: x[1].volta)]
        if ainda:
            msg(f"dm:{c.temporada}:{c.data}", "Departamento médico", "Departamento médico",
                f"Em tratamento: {', '.join(ainda)}.")

    cansados = sorted((p for p in c.world.squad(c.clube_id) if p.condition < 70),
                      key=lambda p: p.condition)
    if cansados:
        nomes = ", ".join(f"{p.name} ({p.condition}%)" for p in cansados[:5])
        msg(f"fisico:{c.temporada}:{c.data}", "Preparação física", "Jogadores desgastados",
            f"Recomendo poupar: {nomes}.", "alerta")

    vencendo = [p for p in c.world.squad(c.clube_id) if p.contract_until <= c.temporada]
    if vencendo:
        nomes = ", ".join(p.name for p in sorted(vencendo, key=lambda p: -p.overall)[:6])
        msg(f"contratos:{c.temporada}", "Departamento jurídico", "Contratos no fim",
            f"{len(vencendo)} contrato(s) terminam nesta temporada: {nomes}.")

    for nome, a in c.copas.items():
        if c.clube_id in a.etapas_vividas or c.clube_id in a.vivos:
            if a.campeao == c.clube_id:
                msg(f"titulo:{c.temporada}:{nome}", "Diretoria", f"Campeão: {a.torneio.nome}",
                    "Título conquistado. A diretoria parabeniza toda a comissão.", "ok")
            elif not a.esta_vivo(c.clube_id) and a.etapas_vividas.get(c.clube_id):
                msg(f"fora:{c.temporada}:{nome}", "Imprensa", f"Eliminado: {a.torneio.nome}",
                    f"O clube se despediu da {a.torneio.nome} na fase {a.nome_da_fase}.",
                    "alerta")

    tipo, onde, jogo = c.proximo_jogo()
    if jogo is not None:
        rival = jogo.away if jogo.home == c.clube_id else jogo.home
        r = c.world.clubs[rival]
        ultimos = [x for x in c.jogos() if rival in (x.home, x.away)][-5:]
        forma = "".join(
            "V" if (x.goals_home > x.goals_away) == (x.home == rival)
            and x.goals_home != x.goals_away else
            "E" if x.goals_home == x.goals_away else "D" for x in ultimos) or "-"
        melhor = max(c.world.squad(rival), key=lambda p: p.overall)
        msg(f"olheiro:{c.temporada}:{c.rodada + 1}", "Olheiro", f"Relatório: {r.name}",
            f"Força do elenco {c.world.team_rating(rival):.0f}. Últimos jogos: {forma}. "
            f"Destaque: {melhor.name} ({melhor.position}, {melhor.overall}).")
    return fora


# ------------------------------------------------------------------ treinador

def treinador(c: Carreira) -> dict:
    anos = []
    titulos = []
    for r in c.historico:
        campeao = r["campeoes"].get(r["minha_liga"]) == r.get("clube")
        if campeao:
            titulos.append({"temporada": r["temporada"],
                            "nome": nome_da_liga(r["minha_liga"])})
        for copa in r.get("minhas_copas", []):
            titulos.append({"temporada": r["temporada"], "nome": _nome_da_copa(copa)})
        anos.append({"temporada": r["temporada"], "clube": r.get("clube", ""),
                     "liga": nome_da_liga(r["minha_liga"]),
                     "posicao": r["minha_posicao"], "subiu": r["subi"], "caiu": r["cai"],
                     "numeros": r.get("meus_numeros", {}),
                     "copas": r.get("minha_campanha", {})})
    agora = c.numeros_do_ano()
    total = {k: agora.get(k, 0) + sum(a["numeros"].get(k, 0) for a in anos)
             for k in agora}
    jogos = max(total["jogos"], 1)
    ap = c.aprovacao
    return {
        "nome": c.treinador, "clube": c.clube.name, "temporada": c.temporada,
        "temporadas": len(c.historico) + 1,
        "atual": {"temporada": c.temporada, "liga": nome_da_liga(c.liga),
                  "posicao": c.posicao() if c.tabela() else 0, "numeros": agora},
        "anos": anos[::-1], "titulos": titulos[::-1], "total": total,
        "aproveitamento": round(100 * (3 * total["vitorias"] + total["empates"])
                                / (3 * jogos), 1),
        "torcida": round(ap.torcida, 1) if ap else 0,
        "diretoria": round(ap.diretoria, 1) if ap else 0,
        "clima": ap.clima if ap else "",
        "curva": [{"data": d, "torcida": t, "diretoria": di}
                  for ano, d, t, di in (ap.historico if ap else []) if ano == c.temporada],
    }


def _nome_da_copa(chave: str) -> str:
    from fm.torneio import carregar
    try:
        return carregar(chave).nome
    except Exception:
        return chave


# ------------------------------------------------------------------ classificacao

def classificacao(c: Carreira, liga: str | None, clube_json) -> dict:
    """Tabela com casa/fora e ultimos cinco, e os numeros individuais da divisao."""
    nome = liga if liga in c.ligas else c.liga
    cfg = load_league(nome)
    ids = set(c.world.leagues[cfg["id"]].club_ids)
    jogos = c.jogos(nome)
    linhas = c.tabela(nome)

    def parcial(cid, onde):
        v = e = d = gp = gc = 0
        for r in jogos:
            if onde == "casa" and r.home != cid or onde == "fora" and r.away != cid:
                continue
            pro, contra = ((r.goals_home, r.goals_away) if r.home == cid
                           else (r.goals_away, r.goals_home))
            gp, gc = gp + pro, gc + contra
            v, e, d = v + (pro > contra), e + (pro == contra), d + (pro < contra)
        return {"pontos": 3 * v + e, "jogos": v + e + d, "vitorias": v, "empates": e,
                "derrotas": d, "gols_pro": gp, "gols_contra": gc}

    def ultimos(cid):
        meus = [r for r in jogos if cid in (r.home, r.away)][-5:]
        fora = []
        for r in meus:
            pro, contra = ((r.goals_home, r.goals_away) if r.home == cid
                           else (r.goals_away, r.goals_home))
            fora.append("V" if pro > contra else "E" if pro == contra else "D")
        return fora

    tabela = [{
        "posicao": i, "clube": clube_json(ln.club_id), "pontos": ln.points,
        "jogos": ln.played, "vitorias": ln.wins, "empates": ln.draws,
        "derrotas": ln.losses, "gols_pro": ln.goals_for, "gols_contra": ln.goals_against,
        "saldo": ln.goal_diff, "eu": ln.club_id == c.clube_id,
        "aproveitamento": round(100 * ln.points / (3 * ln.played)) if ln.played else 0,
        "ultimos": ultimos(ln.club_id),
        "casa": parcial(ln.club_id, "casa"), "fora": parcial(ln.club_id, "fora"),
    } for i, ln in enumerate(linhas, 1)]

    defesas = sorted(tabela, key=lambda x: (x["gols_contra"], -x["jogos"]))
    ataques = sorted(tabela, key=lambda x: -x["gols_pro"])

    individuais = {"artilheiros": [], "garcons": []}
    est = c.estatisticas_por_comp.get(nome)
    if est is not None:
        for chave, lista in (("artilheiros", est.artilheiros(c.world, 10)),
                             ("garcons", est.garcons(c.world, 10))):
            for x in lista:
                p = c.world.players[x.jogador]
                if p.club_id in c.world.clubs:
                    individuais[chave].append({
                        "nome": p.name, "clube": clube_json(p.club_id)["nome"],
                        "cor": clube_json(p.club_id)["cor"], "gols": x.gols,
                        "assistencias": x.assistencias, "jogos": x.jogos,
                        "meu": p.club_id == c.clube_id})
                if len(individuais[chave]) >= 10:
                    break

    zonas = _zonas(cfg, len(tabela))
    return {
        "tipo": "liga", "competicoes": competicoes(c),
        "liga": nome, "nome": nome_da_liga(nome),
        "ligas": [{"id": n, "nome": nome_da_liga(n)} for n in c.ligas],
        "rodada": min(c.rodada, c.rodadas_da_liga(nome)),
        "total_de_rodadas": c.rodadas_da_liga(nome),
        "linhas": tabela, "zonas": zonas,
        "melhores_defesas": [{"clube": x["clube"]["nome"], "gols": x["gols_contra"]}
                             for x in defesas[:5]],
        "piores_defesas": [{"clube": x["clube"]["nome"], "gols": x["gols_contra"]}
                           for x in defesas[::-1][:5]],
        "melhores_ataques": [{"clube": x["clube"]["nome"], "gols": x["gols_pro"]}
                             for x in ataques[:5]],
        **individuais,
    }


def competicoes(c: Carreira) -> list[dict]:
    """O que o seletor da tela de Tabela oferece: as divisoes e as copas do ano."""
    fora = [{"id": n, "nome": nome_da_liga(n), "tipo": "liga"} for n in c.ligas]
    fora += [{"id": k, "nome": a.torneio.nome, "tipo": "copa",
              "minha": c.clube_id in a.ja_entraram or c.clube_id in a.vivos}
             for k, a in c.copas.items()]
    return fora


def _linhas_curtas(ids: list[int], resultados, c: Carreira, clube_json) -> list[dict]:
    from fm.table import build_table
    return [{"posicao": i, "clube": clube_json(ln.club_id), "pontos": ln.points,
             "jogos": ln.played, "vitorias": ln.wins, "empates": ln.draws,
             "derrotas": ln.losses, "saldo": ln.goal_diff, "gols_pro": ln.goals_for,
             "eu": ln.club_id == c.clube_id}
            for i, ln in enumerate(build_table(ids, resultados), 1)]


def _confrontos(fase: dict, c: Carreira, clube_json) -> list[dict]:
    """Os pares de uma rodada do mata-mata, com ida, volta e agregado."""
    fora = []
    for casa, visita in fase["pares"]:
        jogos = [r for r in fase["resultados"] if {r.home, r.away} == {casa, visita}]
        a = sum(r.goals_home if r.home == casa else r.goals_away for r in jogos)
        b = sum(r.goals_home if r.home == visita else r.goals_away for r in jogos)
        vencedor = None
        if len(jogos) >= fase["maos"]:
            # a mesma regra de fm.copa._apurar_mata_mata: empate fica com o mandante da
            # ida, ou com o visitante quando a copa diz isso
            vencedor = casa if a > b else visita if b > a else (
                visita if fase["visitante_avanca_empate"] else casa)
        fora.append({
            "casa": clube_json(casa), "fora": clube_json(visita),
            "jogos": [{"mandante": clube_json(r.home)["nome"], "gols_casa": r.goals_home,
                       "gols_fora": r.goals_away} for r in jogos],
            "agregado": [a, b] if jogos else None, "vencedor": vencedor,
            "meu": c.clube_id in (casa, visita)})
    return fora


LETRAS = "ABCDEFGHIJKLMNOP"


def _fase_json(fase: dict, c: Carreira, clube_json, em_curso: bool) -> dict:
    base = {"tipo": fase["tipo"], "nome": fase["nome"], "em_curso": em_curso}
    if fase["tipo"] == "grupos":
        return {**base, "avancam": fase["avancam"], "grupos": [
            {"nome": f"Grupo {LETRAS[i]}" if i < len(LETRAS) else f"Grupo {i + 1}",
             "linhas": _linhas_curtas(g, [r for r in fase["resultados"]
                                          if r.home in g and r.away in g], c, clube_json)}
            for i, g in enumerate(fase["grupos"])]}
    if fase["tipo"] == "liga":
        return {**base, "avancam": fase["avancam"],
                "linhas": _linhas_curtas(fase["clubes"], fase["resultados"], c, clube_json)}
    return {**base, "confrontos": _confrontos(fase, c, clube_json),
            "poupados": [clube_json(k) for k in fase["poupados"]],
            "abre": fase.get("abre", False)}


def _rodadas_que_faltam(a, agora: dict | None) -> list[str]:
    """Os nomes das rodadas de mata-mata ainda por sortear, para o chaveamento ter as
    colunas vazias. Segue o formato do arquivo: grupos passam `avancam` por grupo, o
    playoff poupa os `isentos`, e a fase "todas" vai dividindo ate a final. Clube que so
    entra numa fase adiante (a Serie A na Copa do Brasil) nao da para prever: a conta
    para ai.

    `agora` None: nenhuma rodada em curso. Os vivos sao os de agora e a proxima rodada e
    a da fase `a.fase` -- que ja aponta para a seguinte quando a anterior acabou."""
    from fm.copa import nome_da_rodada
    fases = a.torneio.fases
    i = a.fase
    if agora is None:
        vivos = len(a.vivos)
    elif agora["tipo"] == "grupos":
        vivos, i = len(agora["grupos"]) * agora["avancam"], i + 1
    elif agora["tipo"] == "liga":
        vivos, i = agora["avancam"], i + 1
    else:
        vivos = len(agora["pares"]) + len(agora["poupados"])
        if str(fases[i].get("rodadas", "todas")) == "1":
            i += 1
    nomes = []
    for j, fase in enumerate(fases[i:], start=i):
        # quem entra na fase EM CURSO ja entrou; numa fase adiante, a conta nao fecha
        if fase.get("tipo") != "knockout" or (j > a.fase and fase.get("entram")):
            break
        isentos = min(int(fase.get("isentos", 0)), vivos)   # mundo pequeno: menos clubes
        rodadas = fase.get("rodadas", "todas")
        if str(rodadas) == "1":
            nomes.append(nome_da_rodada(fase.get("nome", ""), rodadas, vivos, 0))
            vivos = isentos + (vivos - isentos) // 2 + (vivos - isentos) % 2
            continue
        # "todas" vai ate sobrar um; um numero (o mata-mata da Libertadores tem 3, e a final
        # e outra fase) para nele -- descontando, na fase em curso, as rodadas ja jogadas
        restam = None if str(rodadas) == "todas" else int(rodadas)
        if restam is not None and j == a.fase:
            restam -= a.rodadas_da_fase_feitas + (1 if agora and agora["tipo"] == "mata" else 0)
        while vivos > 1 and (restam is None or restam > 0):
            nomes.append(nome_da_rodada(fase.get("nome", ""), rodadas, vivos, len(nomes)))
            vivos = vivos // 2 + vivos % 2
            if restam is not None:
                restam -= 1
    return nomes


def copa(c: Carreira, chave: str, clube_json) -> dict:
    """Uma copa inteira: as fases encerradas, a em curso e as que ainda vem."""
    from fm.copa import foto_da_fase
    a = c.copas[chave]
    fases = [_fase_json(f, c, clube_json, False) for f in a.historico]
    agora = foto_da_fase(a)
    # a fase em curso so aparece com jogo marcado (pendentes): antes do sorteio nao ha o
    # que mostrar, e quando a rodada acaba ela ja foi para o historico
    restantes: list[str] = []
    if agora is not None and not a.acabou and a.pendentes:
        fases.append(_fase_json(agora, c, clube_json, True))
        restantes = _rodadas_que_faltam(a, agora)
    elif a.historico and not a.acabou:
        # entre duas datas: o proximo mata-mata so e sorteado no dia do jogo
        restantes = _rodadas_que_faltam(a, None)
    individuais = []
    est = c.estatisticas_por_comp.get(chave)
    if est is not None:
        for x in est.artilheiros(c.world, 10):
            p = c.world.players.get(x.jogador)
            if p is not None and p.club_id in c.world.clubs:
                individuais.append({"nome": p.name, "clube": clube_json(p.club_id)["nome"],
                                    "gols": x.gols, "meu": p.club_id == c.clube_id})
    return {"tipo": "copa", "id": chave, "nome": a.torneio.nome,
            "fase_atual": a.nome_da_fase,
            "campeao": clube_json(a.campeao) if a.campeao in c.world.clubs else None,
            "fases": fases, "a_sortear": restantes, "artilheiros": individuais,
            "competicoes": competicoes(c)}


def _zonas(cfg: dict, n: int) -> dict:
    """Faixas da tabela. Acesso e rebaixamento vem do arquivo da liga -- sao as regras
    que a virada do ano aplica. A faixa continental e so indicativa: quem entra na
    Libertadores sai da cascata do torneio, que depende tambem dos campeoes de copa."""
    acesso = cfg.get("formato", {}).get("acesso", {})
    tier = int(cfg.get("tier", 1))
    continental = 0
    if tier == 1:
        continental = 6 if cfg.get("pais") == "BRA" else 4
    return {"acesso": int(acesso.get("sobem", 0)), "continental": continental,
            "rebaixamento": int(acesso.get("descem", 0))}


# ------------------------------------------------------------------ pos-jogo

def impacto_na_tabela(nome: str, antes: int | None, depois: int) -> str:
    """A frase do fim de jogo: o que o resultado fez com a posicao na tabela."""
    if antes is None:
        return f"Com esse resultado, o {nome} abre o campeonato na {depois}ª posição"
    if depois == 1:
        return (f"Com esse resultado, o {nome} segue na liderança" if antes == 1
                else f"Com esse resultado, o {nome} assume a liderança")
    if depois < antes:
        return f"Com esse resultado, o {nome} sobe para a {depois}ª posição"
    if depois > antes:
        return f"Com esse resultado, o {nome} cai para a {depois}ª posição"
    return f"Com esse resultado, o {nome} se mantém na {depois}ª posição"


def pos_jogo(c: Carreira, partida, resultados, competicao: str, tipo: str,
             clube_json, posicao_antes: int | None = None) -> dict:
    """A sumula do pos-jogo: notas, eventos e a rodada inteira."""
    from fm.notas import notas_da_partida

    notas = notas_da_partida(c.world, partida)
    jogadores = c.world.players

    def time(clube):
        ids = [pid for pid in partida.entrada if jogadores[pid].club_id == clube]
        ordem = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
        ids.sort(key=lambda i: (partida.entrada[i] > 0, ordem.get(jogadores[i].position, 9)))
        return [{"id": i, "nome": jogadores[i].name, "posicao": jogadores[i].position,
                 "nota": notas.get(i, 6.0), "entrou_aos": partida.entrada[i] or None,
                 "gols": sum(1 for e in partida.eventos
                             if e.tipo == "gol" and e.jogador == i),
                 "amarelo": any(e.tipo == "amarelo" and e.jogador == i
                                for e in partida.eventos),
                 "vermelho": any(e.tipo == "vermelho" and e.jogador == i
                                 for e in partida.eventos)}
                for i in ids]

    principais = [{"minuto": e.minuto, "tipo": e.tipo, "texto": e.texto,
                   "lado": "casa" if e.clube == partida.casa else "fora",
                   "assistencia": jogadores[e.segundo].name
                   if e.tipo == "gol" and e.segundo else None}
                  for e in partida.eventos
                  if e.tipo in ("gol", "amarelo", "vermelho", "substituicao",
                                "penalti_defendido", "penalti_fora", "lesao")]
    sc, sf = partida.stats_casa, partida.stats_fora
    melhor = max(notas, key=notas.get) if notas else None
    impacto = (impacto_na_tabela(c.world.clubs[c.clube_id].name, posicao_antes, c.posicao())
               if tipo == "liga" else None)
    return {
        "competicao": competicao, "impacto": impacto,
        "casa": clube_json(partida.casa), "fora": clube_json(partida.fora),
        "gols_casa": partida.gols_casa, "gols_fora": partida.gols_fora,
        "time_casa": time(partida.casa), "time_fora": time(partida.fora),
        "eventos": principais,
        "melhor_em_campo": {"nome": jogadores[melhor].name, "nota": notas[melhor]}
        if melhor else None,
        "estatisticas": [
            ["Posse de bola", sc.posse, sf.posse, "%"],
            ["Finalizações", sc.finalizacoes, sf.finalizacoes, ""],
            ["No gol", sc.no_gol, sf.no_gol, ""],
            ["Escanteios", sc.escanteios, sf.escanteios, ""],
            ["Faltas", sc.faltas, sf.faltas, ""],
            ["Impedimentos", sc.impedimentos, sf.impedimentos, ""],
            ["Desarmes", sc.desarmes, sf.desarmes, ""],
            ["Passes errados", sc.passes_errados, sf.passes_errados, ""],
            ["Amarelos", sc.amarelos, sf.amarelos, ""],
            ["Vermelhos", sc.vermelhos, sf.vermelhos, ""],
        ],
        "rodada": [{"casa": clube_json(r.home), "fora": clube_json(r.away),
                    "gols_casa": r.goals_home, "gols_fora": r.goals_away,
                    "meu": c.clube_id in (r.home, r.away)}
                   for r in resultados
                   if tipo != "liga" or _mesma_divisao(c, r, partida)],
    }


def _mesma_divisao(c: Carreira, r, partida) -> bool:
    """Na rodada de liga, so a divisao do usuario: as outras jogam a mesma data."""
    ids = None
    for lg in c.world.leagues.values():
        if partida.casa in lg.club_ids and partida.fora in lg.club_ids:
            ids = set(lg.club_ids)
    return ids is None or (r.home in ids and r.away in ids)


# ------------------------------------------------------------------ destaques

def nome_da_competicao(c: Carreira, chave: str) -> str:
    if chave in c.ligas:
        return nome_da_liga(chave)
    if chave in c.copas:
        return c.copas[chave].torneio.nome
    from fm.torneio import carregar
    try:
        return carregar(chave).nome
    except Exception:
        return chave


def selecao(c: Carreira, liga: str | None, rodada: int | None, clube_json) -> dict:
    """A selecao de uma rodada de liga, com a posicao de cada um no desenho."""
    from fm.selecao import FORMACAO
    from fm.tatica import VAGAS

    liga = liga if liga in c.ligas else c.liga
    rodadas = sorted(c.selecoes.get(liga, {}))
    if not rodadas:
        return {"liga": liga, "nome": nome_da_liga(liga), "rodadas": [], "onze": [],
                "ligas": [{"id": n, "nome": nome_da_liga(n)} for n in c.ligas]}
    rodada = rodada if rodada in rodadas else rodadas[-1]
    sel = c.selecoes[liga][rodada]
    vagas = {v[0]: v for v in VAGAS[FORMACAO]}
    onze = []
    for i, x in enumerate(sel["onze"]):
        p = c.world.players.get(x["jogador"])
        vaga = VAGAS[FORMACAO][i]
        onze.append({"id": x["jogador"], "nome": p.name if p else "?",
                     "posicao": p.position if p else "", "clube": clube_json(x["clube"]),
                     "nota": x["nota"], "gols": x["gols"],
                     "assistencias": x["assistencias"], "vaga": vaga[0],
                     "x": vaga[3], "y": vaga[4], "meu": x["clube"] == c.clube_id,
                     "craque": x["jogador"] == sel["craque"]})
    _ = vagas
    return {"liga": liga, "nome": nome_da_liga(liga), "rodada": rodada, "rodadas": rodadas,
            "ligas": [{"id": n, "nome": nome_da_liga(n)} for n in c.ligas],
            "onze": onze, "meus": sum(1 for x in onze if x["meu"])}


def artilharia(c: Carreira, comp: str | None, temporada: int | None, clube_json) -> dict:
    """Artilharia e assistencias de UMA competicao, no ano em curso ou num ano passado.

    O ano em curso vem do caderno vivo; os passados, do que a virada do ano gravou no
    historico (so os dez primeiros, e sem assistencias: e o que vale guardar).
    """
    anos = {r["temporada"]: r.get("artilharia", {}) for r in c.historico}
    temporada = temporada if temporada in anos else c.temporada
    if temporada == c.temporada:
        chaves = [k for k in list(c.ligas) + list(c.copas) if k in c.estatisticas_por_comp]
    else:
        chaves = list(anos[temporada])
    comp = comp if comp in chaves else (chaves[0] if chaves else None)

    artilheiros, garcons = [], []
    if comp and temporada == c.temporada:
        est = c.estatisticas_por_comp[comp]

        def linha(x):
            p = c.world.players[x.jogador]
            clube = clube_json(p.club_id) if p.club_id in c.world.clubs else None
            return {"id": x.jogador, "nome": p.name, "posicao": p.position, "clube": clube,
                    "gols": x.gols, "assistencias": x.assistencias, "jogos": x.jogos,
                    "meu": p.club_id == c.clube_id}
        artilheiros = [linha(x) for x in est.artilheiros(c.world, 25)]
        garcons = [linha(x) for x in est.garcons(c.world, 15)]
    elif comp:
        artilheiros = [{**x, "clube": {"nome": x["clube"]}, "meu": x["clube"] == c.clube.name}
                       for x in anos[temporada][comp]]

    # quem foi o artilheiro de cada competicao em cada ano ja encerrado
    campeoes = []
    for ano in sorted(anos, reverse=True):
        for chave, lista in anos[ano].items():
            if lista:
                campeoes.append({"temporada": ano, "competicao": nome_da_competicao(c, chave),
                                 "nome": lista[0]["nome"], "clube": lista[0]["clube"],
                                 "gols": lista[0]["gols"]})
    return {
        "temporada": temporada, "temporadas": sorted(set(anos) | {c.temporada}, reverse=True),
        "competicao": comp,
        "competicoes": [{"id": k, "nome": nome_da_competicao(c, k)} for k in chaves],
        "artilheiros": artilheiros, "garcons": garcons, "campeoes": campeoes,
    }
