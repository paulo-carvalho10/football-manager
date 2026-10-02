"""O que as telas do PRANCHETA 11 pedem e o lobby antigo nao tinha.

Funcoes puras de Carreira (ou de mundo) para dict: nenhuma regra nova mora aqui. Quando
uma tela pede algo que o motor nao simula -- estadio, publico, lesao --, a funcao nao
inventa: o campo simplesmente nao existe, e a tela nao o desenha.
"""

from __future__ import annotations

from fm.carreira import Carreira
from fm.ratings import exibir
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
    # o resto da Conmebol: uma divisao cada (so a primeira foi importada), sem acesso e
    # rebaixamento. Sao as ligas de onde vem os clubes da Libertadores e da Sul-Americana.
    {"pais": "COL", "nome": "Colômbia", "cores": ["#fcd116", "#003893"], "livre": True,
     "ligas": [("colombia_real", "Liga BetPlay")]},
    {"pais": "CHI", "nome": "Chile", "cores": ["#d52b1e", "#0039a6"], "livre": True,
     "ligas": [("chile_real", "Liga de Primera")]},
    {"pais": "URU", "nome": "Uruguai", "cores": ["#0038a8", "#ffffff"], "livre": True,
     "ligas": [("uruguai_real", "Liga AUF")]},
    {"pais": "ECU", "nome": "Equador", "cores": ["#ffd100", "#034ea2"], "livre": True,
     "ligas": [("equador_real", "LigaPro")]},
    {"pais": "PAR", "nome": "Paraguai", "cores": ["#d52b1e", "#0038a8"], "livre": True,
     "ligas": [("paraguai_real", "Primera División")]},
    {"pais": "PER", "nome": "Peru", "cores": ["#d91023", "#ffffff"], "livre": True,
     "ligas": [("peru_real", "Liga 1")]},
    {"pais": "BOL", "nome": "Bolívia", "cores": ["#d52b1e", "#007934"], "livre": True,
     "ligas": [("bolivia_real", "División Profesional")]},
    {"pais": "VEN", "nome": "Venezuela", "cores": ["#cf142b", "#00247d"], "livre": True,
     "ligas": [("venezuela_real", "Liga FUTVE")]},
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
    **{p: ["Copa Libertadores", "Copa Sul-Americana"]
       for p in ("COL", "CHI", "URU", "ECU", "PAR", "PER", "BOL", "VEN")},
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
                "forca": exibir(world.team_rating(cid)),
                "ranking": forca.index(cid) + 1, "de": len(ids),
                "reputacao": club.reputation, "caixa": club.balance,
                "valor_do_elenco": valor_do_elenco(world, cid),
                "folha": folha_anual(world, cid),
                "jogadores": len(elenco),
                "idade_media": round(sum(p.age(world.season_year) for p in elenco)
                                     / max(len(elenco), 1), 1),
                "meta": meta.texto,
                "estrelas": [{"nome": p.name, "posicao": p.position,
                              "overall": exibir(p.overall)} for p in estrelas],
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
        # o filtro vem da tela, na escala das cartinhas
        if not idade_min <= idade <= idade_max or exibir(p.overall) < ovr_min:
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
             "detalhe": p.position_detail, "idade": idade, "overall": exibir(p.overall),
             "potencial": exibir(p.potential), "valor": p.market_value, "salario": p.wage,
             "contrato": p.contract_until, "pe": p.foot, "nacionalidade": p.nationality,
             "clube": None if livre else clube_json(p.club_id), "livre": livre,
             "liga": nome_da_liga_por_id(lg.id, lg.name) if lg else "",
             "observado": p.id in observados}
            for p, lg, idade, livre in fora[:250]],
    }


# ------------------------------------------------------------------ olheiro

VAGAS_DO_RELATORIO = 3        # os pontos mais fracos do time titular
POR_VAGA = 4                  # reforcos recomendados para cada um
PROMESSAS = 6
IDADE_DA_PROMESSA = 21


def olheiro(c: Carreira, clube_json) -> dict:
    """O relatorio do olheiro: onde o time titular e mais fraco e quem resolve.

    Olha a escalacao da proxima rodada, vaga por vaga (fm.tatica): o titular mais fraco e
    o improvisado fora de posicao sao as necessidades. Para cada uma, recomenda quem seria
    titular ali, cabe no caixa e na folha e topa vir (fm.negocios.recusa_por_ambicao). E
    separa as promessas: ate 21 anos, potencial para chegar ao nivel do time. So recomenda --
    quem fecha o negocio e o usuario, pelo fluxo de proposta de sempre.
    """
    from fm import negocios as neg
    from fm.mercado import RESERVA_DE_CAIXA

    w = c.world
    ano = c.temporada
    tatica = c.tatica_atual()
    vagas = tatica.vagas_do_campo()
    onze = [w.players[i] for i in c.escalacao_atual() if i in w.players]
    nivel = sum(p.overall for p in onze) / max(len(onze), 1)
    folha = neg.folha_mensal(w, c.clube_id)
    caixa_livre = c.clube.balance - folha * RESERVA_DE_CAIXA
    folha_livre = neg.limite_da_folha(c) - folha
    observados = set(c.observados)
    ligas_do_clube = {cid: lg for lg in w.leagues.values() for cid in lg.club_ids}

    # as necessidades: a vaga (rotulo, setor) e quem esta nela hoje
    pontos = []
    for p, (rotulo, setor, papel, _, _) in zip(onze, vagas, strict=False):
        improvisado = p.position != setor
        pontos.append((p.overall - (6 if improvisado else 0), rotulo, setor, papel, p,
                       improvisado))
    pontos.sort(key=lambda x: x[0])
    necessidades, vistos = [], set()
    for _, rotulo, setor, papel, p, improvisado in pontos:
        if (rotulo, setor) in vistos:
            continue
        vistos.add((rotulo, setor))
        necessidades.append((rotulo, setor, papel, p, improvisado))
        if len(necessidades) == VAGAS_DO_RELATORIO:
            break

    def custo(p) -> tuple[int, int]:
        """(transferencia, salario pedido). Sem contrato: so o salario."""
        livre = p.club_id not in w.clubs
        return (0 if livre else neg.pedido_do_vendedor(c, p)), neg.salario_pretendido(c, p)

    def cabe(preco: int, salario: int) -> bool:
        return preco <= caixa_livre and salario <= folha_livre

    def item(p, motivo: str, tipo: str, preco: int, salario: int) -> dict:
        livre = p.club_id not in w.clubs
        lg = ligas_do_clube.get(p.club_id)
        return {"id": p.id, "nome": p.name, "posicao": p.position, "detalhe": p.position_detail,
                "idade": p.age(ano), "overall": exibir(p.overall),
                "potencial": exibir(p.potential), "valor": p.market_value, "salario": p.wage,
                "contrato": p.contract_until, "pe": p.foot, "nacionalidade": p.nationality,
                "clube": None if livre else clube_json(p.club_id), "livre": livre,
                "liga": nome_da_liga_por_id(lg.id, lg.name) if lg else "",
                "observado": p.id in observados, "motivo": motivo, "tipo": tipo,
                "preco": preco, "salario_pedido": salario}

    candidatos = [p for p in w.players.values()
                  if p.club_id != c.clube_id and p.loan_from is None and p.market_value >= 0]
    ja_recomendados: set[int] = set()
    secoes = []
    for rotulo, setor, papel, titular, improvisado in necessidades:
        alvo = titular.overall + 2
        bons = sorted((p for p in candidatos if p.position == setor and p.overall >= alvo
                       and p.age(ano) <= 31 and p.id not in ja_recomendados),
                      key=lambda p: (p.position_detail != papel, -p.overall))
        recomendados = []
        for p in bons:
            if len(recomendados) == POR_VAGA:
                break
            preco, salario = custo(p)
            if not cabe(preco, salario) or neg.recusa_por_ambicao(c, p):
                continue
            ganho = exibir(p.overall) - exibir(titular.overall)
            motivo = (f"Titular de {rotulo} no lugar de {titular.name}"
                      + (" (improvisado)" if improvisado else f" ({exibir(titular.overall)})")
                      + f": +{ganho} de overall")
            recomendados.append(item(p, motivo, "reforco", preco, salario))
            ja_recomendados.add(p.id)
        secoes.append({"titulo": f"{rotulo}: {titular.name} ({exibir(titular.overall)})"
                                 + (" — improvisado" if improvisado else ""),
                       "jogadores": recomendados})

    promessas = []
    for p in sorted((p for p in candidatos if p.age(ano) <= IDADE_DA_PROMESSA
                     # pode chegar ao nivel do time titular: e o que faz dele uma aposta
                     and p.potential >= nivel - 1 and p.id not in ja_recomendados),
                    key=lambda p: -p.potential):
        if len(promessas) == PROMESSAS:
            break
        preco, salario = custo(p)
        if not cabe(preco, salario) or neg.recusa_por_ambicao(c, p):
            continue
        promessas.append(item(p, f"{p.age(ano)} anos, potencial {exibir(p.potential)}: "
                                 "pode virar titular", "promessa", preco, salario))
    secoes.append({"titulo": "Promessas", "jogadores": promessas})

    todos = [j for s in secoes for j in s["jogadores"]]
    return {"caixa": neg.resumo_do_caixa(c), "secoes": secoes, "jogadores": todos,
            "orcamento": {"transferencia": max(0, int(caixa_livre)),
                          "salario": max(0, int(folha_livre))}}


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

    # o vestiario (fm.moral): quem quer sair e o clima do grupo
    from fm.moral import INSATISFEITO, quimica, rotulo_da_quimica
    for p in c.world.squad(c.clube_id):
        if p.morale < INSATISFEITO:
            seguidos = c.world.banco_seguido.get(p.id, 0)
            motivo = (f"Está há {seguidos} jogos sem entrar em campo e quer sair do clube."
                      if seguidos >= 4 else
                      "Está abatido com a fase do time e não esconde que pensa em sair.")
            msg(f"insatisfeito:{c.temporada}:{p.id}", "Vestiário",
                f"{p.name} está insatisfeito",
                f"{motivo} Insatisfeito, ele não renova e atrai propostas; minutos em campo e "
                "vitórias devolvem a confiança.", "alerta")
    q = quimica(c.world, c.clube_id)
    if q < 40:
        msg(f"vestiario-ruim:{c.temporada}:{c.data // 8}", "Vestiário", "Clima pesado no grupo",
            f"O vestiário está {rotulo_da_quimica(q)}. Derrotas seguidas e jogadores "
            "insatisfeitos derrubam o rendimento em campo.", "alerta")
    elif q >= 85:
        msg(f"vestiario-bom:{c.temporada}:{c.data // 8}", "Vestiário", "Grupo fechado",
            "O elenco está fechado com o técnico: a boa fase dá confiança em campo.")

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
                 f"{les.dias_restantes(hoje)} dia{'s' if les.dias_restantes(hoje) != 1 else ''})"
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
            f"Destaque: {melhor.name} ({melhor.position}, {exibir(melhor.overall)}).")
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
        "rodada": c.rodada_da_liga(nome),
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
        vencedor, penaltis = None, None
        disputa = fase.get("disputas", {}).get(f"{casa}-{visita}")
        if len(jogos) >= fase["maos"]:
            # a mesma regra de fm.copa._apurar_mata_mata: empate vai para os penaltis, ou
            # fica com o visitante quando a fase diz isso
            if a != b:
                vencedor = casa if a > b else visita
            elif fase["visitante_avanca_empate"]:
                vencedor = visita
            elif disputa:
                vencedor, penaltis = disputa["vencedor"], disputa["gols"]
        fora.append({
            "casa": clube_json(casa), "fora": clube_json(visita),
            "jogos": [{"mandante": clube_json(r.home)["nome"], "gols_casa": r.goals_home,
                       "gols_fora": r.goals_away} for r in jogos],
            "agregado": [a, b] if jogos else None, "vencedor": vencedor,
            "penaltis": penaltis,
            "meu": c.clube_id in (casa, visita)})
    return fora


LETRAS = "ABCDEFGHIJKLMNOP"


def _fase_json(fase: dict, c: Carreira, clube_json, em_curso: bool) -> dict:
    base = {"tipo": fase["tipo"], "nome": fase["nome"], "em_curso": em_curso,
            "fase": fase.get("fase", -1)}
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
            "secoes": secoes_da_copa(c, a, fases, clube_json),
            "competicoes": competicoes(c)}


MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _periodo(fases: list[dict]) -> str:
    """"fev a mar", "ago a out", "nov": o pedaco do ano da secao (as janelas do arquivo)."""
    janelas = [f["janela"] for f in fases if f.get("janela")]
    if not janelas:
        return ""
    a, b = int(janelas[0][0][:2]), int(janelas[-1][1][:2])
    return MESES[a - 1] if a == b else f"{MESES[a - 1]} a {MESES[b - 1]}"


def secoes_da_copa(c: Carreira, a, fases_json: list[dict], clube_json) -> list[dict]:
    """A copa em secoes, na ordem do ano: as fases preliminares, os grupos (ou a fase de
    liga), o playoff e o mata-mata em chave. Toda secao aparece desde o comeco -- a dos
    grupos antes do sorteio diz quando ele acontece, a da chave mostra a arvore vazia.

    Era um chaveamento so por ordem de rodada, e as oitavas, quartas e final "a sortear"
    apareciam grudadas nas preliminares da Libertadores."""
    fases = a.torneio.fases
    tipo_de = []
    em_chave = False
    for f in fases:
        if f.get("tipo") == "knockout" and (f.get("chave") == "fixa" or em_chave):
            em_chave = True
            tipo_de.append("chave")
        elif f.get("tipo") == "knockout":
            tipo_de.append("mata")
        elif f.get("tipo") == "groups":
            tipo_de.append("grupos")
        else:
            tipo_de.append("liga")
    # a chave e uma secao so; as eliminatorias seguidas se juntam so quando vem antes dos
    # grupos (as tres preliminares da Libertadores). Na Copa do Brasil cada fase e uma aba.
    primeira_de_grupos = next((k for k, t in enumerate(tipo_de) if t in ("grupos", "liga")), None)
    blocos: list[list[int]] = []
    for k, t in enumerate(tipo_de):
        junta = bool(blocos) and tipo_de[blocos[-1][-1]] == t and (
            t == "chave" or (t == "mata" and primeira_de_grupos is not None
                             and k < primeira_de_grupos))
        if junta:
            blocos[-1].append(k)
        else:
            blocos.append([k])
    fora = []
    for ks in blocos:
        t = tipo_de[ks[0]]
        nome = fases[ks[0]].get("nome", "")
        if t == "chave":
            nome = "Mata-mata"
        elif len(ks) > 1:
            nome = ("Fases preliminares" if primeira_de_grupos is not None
                    and ks[-1] < primeira_de_grupos else " e ".join(fases[k].get("nome", "")
                                                                   for k in ks))
        dentro = [f for f in fases_json if f.get("fase") in ks]
        if a.acabou or a.fase > ks[-1]:
            estado = "encerrada"
        elif a.fase >= ks[0]:
            estado = "em_curso" if dentro or a.pendentes else "proxima"
        else:
            estado = "futura"
        secao = {"id": f"s{ks[0]}", "nome": nome, "tipo": t, "estado": estado,
                 "periodo": _periodo([fases[k] for k in ks]), "fases": dentro}
        if t == "chave":
            secao["rodadas"] = _arvore(a, ks, fases_json, clube_json)
        elif t in ("grupos", "liga") and not dentro:
            anterior = fases[ks[0] - 1].get("nome", "") if ks[0] > 0 else ""
            secao["aviso"] = (f"O sorteio sai depois da {anterior}." if anterior
                              else "O sorteio sai antes do primeiro jogo.")
        elif not dentro:
            secao["aviso"] = "Ainda não começou."
        fora.append(secao)
    return fora


def _arvore(a, ks: list[int], fases_json: list[dict], clube_json) -> list[dict]:
    """A chave inteira, da primeira rodada a final, com as vagas futuras como
    "Vencedor O1". Os confrontos ja jogados vem das fotos (placar, agregado, penaltis)."""
    from fm.copa import NOMES_DO_MATA_MATA
    n = len(a.chave)
    if not n:
        # antes do sorteio: a arvore vazia, pelo tamanho previsto (16 nas copas daqui)
        n = 16
    jogados = {}
    for f in fases_json:
        if f.get("fase") in ks:
            for x in f.get("confrontos", []):
                jogados[frozenset((x["casa"]["id"], x["fora"]["id"]))] = x
    rodadas = []
    vivos: list[int | None] = list(a.chave) if a.chave else [None] * n
    rotulos = ["a sortear"] * len(vivos)
    tamanho = len(vivos)
    while tamanho >= 2:
        nome = next((nm for teto, nm in NOMES_DO_MATA_MATA if tamanho <= teto), "Mata-mata")
        sigla = {"Oitavas de final": "O", "Quartas de final": "Q", "Semifinal": "S",
                 "Final": "F", "16 avos de final": "D"}.get(nome, "R")
        confrontos, proximos, proximos_rotulos = [], [], []
        for j in range(tamanho // 2):
            x, y = vivos[2 * j], vivos[2 * j + 1]
            card = jogados.get(frozenset((x, y))) if x is not None and y is not None else None
            if card is None:
                card = {"casa": clube_json(x) if x is not None else None,
                        "fora": clube_json(y) if y is not None else None,
                        "jogos": [], "agregado": None, "vencedor": None, "penaltis": None,
                        "meu": False,
                        "rotulo_casa": rotulos[2 * j], "rotulo_fora": rotulos[2 * j + 1]}
            card = {**card, "sigla": f"{sigla}{j + 1}" if sigla != "F" else "Final"}
            confrontos.append(card)
            proximos.append(card.get("vencedor"))
            proximos_rotulos.append(f"Vencedor {sigla}{j + 1}")
        rodadas.append({"nome": nome, "confrontos": confrontos})
        vivos, rotulos = proximos, proximos_rotulos
        tamanho //= 2
    return rodadas


# (copa, onde entra) -> (classe da cor, rotulo). A pre de cada copa tem cor propria.
FAIXA_DA_VAGA = {
    ("libertadores", "grupos"): ("lib", "Libertadores"),
    ("libertadores", "segunda"): ("pre", "Pré-Libertadores"),
    ("libertadores", "primeira"): ("pre", "Pré-Libertadores"),
    ("sudamericana", None): ("sula", "Sul-Americana"),
    ("champions", "liga"): ("lib", "Liga dos Campeões"),
    ("champions", "pre"): ("pre", "Pré-Champions"),
    ("europa_league", None): ("sula", "Liga Europa"),
}


def faixas_continentais(cfg: dict) -> list[dict]:
    """As faixas de vaga continental de uma liga, tiradas das REGRAS dos torneios (as
    mesmas que a virada do ano aplica), na ordem em que elas pegam os clubes. No
    Brasileirao: 1o ao 4o Libertadores, 5o e 6o pre-Libertadores, 7o ao 12o Sul-Americana.

    Era um numero fixo -- 6 no Brasil, 4 em qualquer outro lugar -- sem separar grupos de
    pre nem mostrar a Sul-Americana; a Argentina, com 6 vagas, aparecia com 4. Continua
    indicativa: campeao de copa ja classificado faz a vaga descer na tabela."""
    from fm.carreira import COPAS_POR_PAIS
    from fm.torneio import carregar

    codigos = {cfg.get("codigo"), cfg.get("id")} - {None}
    faixas: list[dict] = []
    pos = 0
    for copa in COPAS_POR_PAIS.get(cfg.get("pais", ""), ()):
        try:
            t = carregar(copa)
        except FileNotFoundError:
            continue
        for regra in t.classificacao_regras:
            if regra.get("fonte") not in codigos:
                continue
            classe, rotulo = (FAIXA_DA_VAGA.get((copa, regra.get("entra_em")))
                              or FAIXA_DA_VAGA.get((copa, None)) or ("lib", t.nome))
            n = int(regra.get("vagas", 1))
            if faixas and faixas[-1]["classe"] == classe and faixas[-1]["rotulo"] == rotulo:
                faixas[-1]["ate"] += n
            else:
                faixas.append({"de": pos + 1, "ate": pos + n, "classe": classe,
                               "rotulo": rotulo})
            pos += n
    return faixas


def _zonas(cfg: dict, n: int) -> dict:
    """Faixas da tabela. Acesso e rebaixamento vem do arquivo da liga -- sao as regras
    que a virada do ano aplica. As continentais vem das regras dos torneios."""
    acesso = cfg.get("formato", {}).get("acesso", {})
    faixas = faixas_continentais(cfg) if int(cfg.get("tier", 1)) == 1 else []
    return {"acesso": int(acesso.get("sobem", 0)),
            "continental": max((f["ate"] for f in faixas), default=0),
            "faixas": faixas,
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
    disputa = None
    if partida.disputa:
        d = partida.disputa
        disputa = {"gols_casa": d["gols"][partida.casa], "gols_fora": d["gols"][partida.fora],
                   "vencedor": d["vencedor"],
                   "cobrancas": [{"lado": "casa" if x["clube"] == partida.casa else "fora",
                                  "nome": jogadores[x["jogador"]].name
                                  if x["jogador"] in jogadores else "?",
                                  "convertido": x["convertido"]} for x in d["cobrancas"]]}
    return {
        "competicao": competicao, "impacto": impacto, "disputa": disputa,
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
    # `rodada` e a data de liga da grade (a chave das selecoes, para navegar); o numero que
    # a tela mostra e o da propria liga
    return {"liga": liga, "nome": nome_da_liga(liga), "rodada": rodada, "rodadas": rodadas,
            "rodada_da_liga": c.rodada_da_liga(liga, data_de_liga=rodada) or rodada,
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
