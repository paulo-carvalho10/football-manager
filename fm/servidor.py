"""O jogo servido no navegador: uma API JSON sobre a mesma Carreira do terminal.

Isto e a SEGUNDA casca, nao um segundo jogo. `fm/jogo.py` diz, no cabecalho, que quando
existisse interface grafica ela trocaria aquele arquivo e mais nada -- e e' o que acontece
aqui: nenhuma regra mora neste modulo, so traducao de estado para JSON e de clique para
chamada de metodo.

Por que a biblioteca padrao e nao FastAPI: o jogo e local e de um jogador so, o volume e'
de dezenas de requisicoes por partida, e o motor continua dependendo apenas de numpy. No
dia em que existir multiplayer, este arquivo troca de servidor sem que a Carreira saiba.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from fm import telas
from fm.ratings import exibir
from fm.calendario import dia_da_data, texto
from fm.carreira import Carreira, saves_disponiveis
from fm.tatica import ESTILOS, FORMACOES, MARCACOES, VAGAS, Tatica, arrumar_no_campo

WEB = Path(__file__).resolve().parent / "web"
POSICAO_ORDEM = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}


class Jogo:
    """A carreira e o pouco de estado que so a interface precisa.

    A ultima partida fica guardada aqui porque o navegador pede o estado e a sumula em
    requisicoes separadas -- a Carreira nao tem por que saber disso. A carreira pode nao
    existir ainda: o jogo abre no menu, e ela nasce em "novo jogo" ou "jogos salvos".
    """

    def __init__(self, carreira: Carreira | None = None) -> None:
        self.c = carreira
        self.ultima_partida = None
        self.ultimos_resultados: list = []
        self.ultimo_resumo: dict | None = None
        self.ao_vivo = None                 # fm.ao_vivo.PartidaAoVivo, durante o jogo
        self.posicao_antes: int | None = None   # na tabela, antes da partida ao vivo
        self.competicao_ao_vivo = ("", "")
        self.pos_jogo: dict | None = None
        self.lidas: set[str] = set()
        # as ofertas que o usuario fez nesta sessao e a resposta de cada uma: a aba
        # "Negociacoes". Nao vai para o save -- o save guarda so o que virou negocio.
        self.negociacoes: list[dict] = []
        self.trava = threading.Lock()


# ------------------------------------------------------------------ escudos
# Os escudos baixados da CBF ficam em data/escudos/<id_fonte>.png, fora do git. O clube
# do mundo nao guarda o id da fonte; o pack guarda, entao o mapa sai dele uma vez.
_ESCUDOS: dict[str, Path] | None = None


def _escudos() -> dict[str, Path]:
    global _ESCUDOS
    if _ESCUDOS is None:
        from fm.config import load_league
        from fm.importer.escudos import ESCUDOS_DIR
        from fm.pack import load_pack
        from fm.telas import NACIONAIS
        _ESCUDOS = {}
        for n in NACIONAIS:
            for liga, _ in n["ligas"]:
                if not liga:
                    continue
                try:
                    pack = load_pack(load_league(liga)["pack"])
                except Exception:
                    continue
                for clube in pack.clubes:
                    arq = ESCUDOS_DIR / f"{clube.id_fonte}.png" if clube.id_fonte else None
                    if arq and arq.is_file():
                        _ESCUDOS[clube.nome] = arq
        # os demais vieram do Transfermarkt (fm.importer.escudos.baixar_do_transfermarkt),
        # listados num indice por nome de clube; o da CBF tem preferencia quando ha os dois
        from fm.importer.escudos import ler_indice
        for nome, arquivo in ler_indice().items():
            arq = ESCUDOS_DIR / arquivo
            if nome not in _ESCUDOS and arq.is_file():
                _ESCUDOS[nome] = arq
    return _ESCUDOS


# O "perfil" da tabela do elenco: o atributo em que o jogador mais se destaca, dito
# como o narrador diria. Derivado dos atributos, nao inventado.
PERFIS = {
    "finishing": "Finalizador", "passing": "Passador", "dribbling": "Driblador",
    "marking": "Marcador", "pace": "Velocista", "strength": "Forte",
    "technique": "Técnico", "positioning": "Posicionamento", "vision": "Armador",
    "aerial": "Jogo aéreo", "reflexes": "Reflexos",
}
PERFIS_DO_GOLEIRO = ("reflexes", "positioning", "aerial")


def _perfil(p) -> str:
    campos = PERFIS_DO_GOLEIRO if p.position == "GK" else tuple(
        k for k in PERFIS if k != "reflexes")
    return PERFIS[max(campos, key=lambda k: getattr(p, k, 0))]


def _jogador(c: Carreira, p, titular: bool) -> dict:
    return {
        "id": p.id, "nome": p.name, "posicao": p.position,
        "detalhe": p.position_detail, "pe": p.foot, "perfil": _perfil(p),
        "overall": exibir(p.overall), "potencial": exibir(p.potential),
        "idade": p.age(c.temporada), "energia": p.condition,
        "salario": p.wage, "valor": p.market_value, "titular": titular,
        "contrato": p.contract_until, "moral": p.morale,
        # 0 = acaba ao fim desta temporada; 1 = na seguinte (o aviso do elenco)
        "vence_em": p.contract_until - c.temporada,
        # emprestado A MIM: o nome do clube dono (volta para la no fim do ano)
        "emprestado_de": (c.world.clubs[p.loan_from].name
                          if p.loan_from in c.world.clubs else None),
        "lesao": _lesao_do(c, p.id),
        **_estatistica_do_jogador(c, p.id),
    }


def _lesao_do(c: Carreira, pid: int) -> dict | None:
    les = c.medico.lesionados.get(pid) if c.medico else None
    if les is None:
        return None
    return {"tipo": les.tipo, "dias": les.dias_restantes(c.hoje()),
            "volta": les.volta.strftime("%d/%m")}


def _clube(c: Carreira, cid: int) -> dict:
    return _clube_do_mundo(c.world, cid)


def _clube_do_mundo(world, cid: int) -> dict:
    club = world.clubs[cid]
    return {
        "id": club.id, "nome": club.name,
        "cor": club.color_primary, "cor2": club.color_secondary,
        "camisa": club.kit_body or club.color_primary,
        "camisa2": club.kit_detail or club.color_secondary,
        "padrao": club.kit_pattern,
        "escudo": club.name in _escudos(),
    }


def _nome_da_liga(chave: str) -> str:
    return telas.nome_da_liga(chave)


def _situacao_na_copa(c: Carreira, a) -> str:
    """Onde o usuario esta na copa. "fora" so para quem entrou e caiu: o clube que ainda
    vai entrar numa fase adiante (a Serie A entra na Copa do Brasil depois) nao esta fora."""
    from fm.torneio import resolver_entradas
    eu = c.clube_id
    if a.campeao == eu:
        return "campeão"
    if a.esta_vivo(eu):
        return "vivo"
    if eu in a.ja_entraram or eu in a.etapas_vividas:
        return "eliminado"
    if a.acabou:
        return "não disputou"
    tabelas = c.tabelas_do_ano_anterior or c._tabelas_por_forca()
    for fase in a.torneio.fases[a.fase + 1:]:
        try:
            if eu in resolver_entradas(c.world, fase.get("entram", []), tabelas,
                                       a.classificados):
                return f"entra na {fase.get('nome', 'fase seguinte')}"
        except (KeyError, ValueError):
            break
    return "não classificado"


def _disciplina_do(c: Carreira, pid: int, comp: str | None) -> dict:
    """Gancho e cartoes acumulados do jogador NA competicao do proximo jogo."""
    if not comp or c.disciplina is None:
        return {"suspenso": False, "pendurado": False, "amarelos_na_comp": 0}
    return {"suspenso": pid in c.disciplina.suspensos(comp),
            "pendurado": pid in c.disciplina.pendurados(comp),
            "amarelos_na_comp": c.disciplina.amarelos.get(comp, {}).get(pid, 0)}


def estado(jogo: Jogo) -> dict:
    """Tudo que o lobby precisa numa chamada so."""
    c = jogo.c
    comp_prox = c.competicao_do_proximo()
    suspensos_prox = c.suspensos_do_proximo()
    tatica = c.tatica_atual()
    onze = set(c.escalacao_atual())
    elenco = sorted(c.world.squad(c.clube_id),
                    key=lambda p: (POSICAO_ORDEM.get(p.position, 9), -p.overall))
    tipo, onde, jogo_ = c.proximo_jogo()

    proximo = None
    if tipo == "liga" and jogo_ is not None:
        rival = jogo_.away if jogo_.home == c.clube_id else jogo_.home
        proximo = {"tipo": "liga", "competicao": _nome_da_liga(c.liga),
                   "rival": _clube(c, rival),
                   "casa": jogo_.home == c.clube_id,
                   "rodada": c.rodada + 1}
    elif tipo == "copa":
        a = c.copas[onde]
        f, ida = _jogo_de_copa(c, a)
        proximo = {"tipo": "copa", "competicao": a.torneio.nome, "id": onde,
                   "fase": a.nome_da_fase, "vivos": len(a.vivos),
                   "rival": _clube(c, f.away if f.home == c.clube_id else f.home) if f else None,
                   "casa": bool(f and f.home == c.clube_id),
                   "volta": ida is not None, "ida": ida}

    tabela = c.tabela()
    minha = next((linha for linha in tabela if linha.club_id == c.clube_id), None)
    ap = c.aprovacao
    return {
        "clube": _clube(c, c.clube_id),
        "treinador": c.treinador, "data": data_do_jogo(c),
        "liga": c.liga, "temporada": c.temporada,
        "liga_nome": _nome_da_liga(c.liga),
        # a rodada DA DIVISAO do usuario: o relogio da carreira anda ate a mais longa
        "rodada": min(c.rodada, c.rodadas_da_liga()),
        "total_de_rodadas": c.rodadas_da_liga(),
        # `data` e a do calendario (texto); o indice na agenda e outra coisa
        "indice_da_data": c.data, "datas": len(c.agenda),
        "acabou": c.acabou, "demitido": c.demitido,
        "motivo": ap.motivo if ap else "",
        "posicao": c.posicao() if tabela else 0,
        "pontos": minha.points if minha else 0,
        "caixa": c.clube.balance, "reputacao": c.clube.reputation,
        "aprovacao": {
            "torcida": round(ap.torcida, 1) if ap else 0,
            "diretoria": round(ap.diretoria, 1) if ap else 0,
            "clima": ap.clima if ap else "", "meta": ap.meta.texto if ap and ap.meta else "",
        },
        "proximo": proximo,
        "tatica": {"formacao": tatica.formacao, "marcacao": tatica.marcacao,
                   "estilo": tatica.estilo, "vagas": tatica.vagas,
                   "posicoes": [{"rotulo": r, "setor": s, "papel": p, "x": x, "y": y}
                                for r, s, p, x, y in VAGAS[tatica.formacao]]},
        "opcoes": {"formacoes": sorted(FORMACOES), "marcacoes": sorted(MARCACOES),
                   "estilos": sorted(ESTILOS)},
        "elenco": [{**_jogador(c, p, p.id in onze), **_disciplina_do(c, p.id, comp_prox)}
                   for p in elenco],
        "gancho": {
            "competicao": telas.nome_da_competicao(c, comp_prox) if comp_prox else "",
            "suspensos": sorted(c.world.players[i].name for i in suspensos_prox
                                if c.world.players[i].club_id == c.clube_id),
            "no_onze": [c.world.players[i].name for i in onze if i in suspensos_prox],
        },
        "onze": list(c.escalacao_atual()),
        "reputacao_tecnico": _reputacao(c),
        "convites": [_convite(c, k) for k in c.convites],
        "lesionados": [c.world.players[i].name for i in c.lesionados_do_clube()],
        # os meus que estao jogando em outro clube ate o fim do ano
        "emprestados": [{"id": p.id, "nome": p.name, "posicao": p.position,
                         "overall": exibir(p.overall),
                         "clube": _clube(c, p.club_id)}
                        for p in c.world.players.values()
                        if p.loan_from == c.clube_id and p.club_id in c.world.clubs],
        "funcoes": c.funcoes,
        "observados": len(c.observados),
        "nao_lidas": sum(1 for m in telas.mensagens(c, data_do_jogo(c), jogo.lidas)
                         if not m["lida"]),
        "temporadas": len(c.historico) + 1,
        # a tela abre a janela de "proposta recebida" sozinha quando ha uma aqui
        "propostas_pendentes": [_proposta_json(c, x) for x in c.propostas_pendentes()],
        "copas": [
            {"id": nome, "nome": a.torneio.nome, "fase": a.nome_da_fase,
             "vivo": a.esta_vivo(c.clube_id), "acabou": a.acabou,
             "situacao": _situacao_na_copa(c, a),
             "campeao": _clube(c, a.campeao)["nome"] if a.campeao else None}
            for nome, a in c.copas.items()
        ],
    }


def tabela(jogo: Jogo, liga: str | None = None) -> dict:
    c = jogo.c
    linhas = c.tabela(liga)
    return {
        "liga": liga or c.liga,
        "ligas": list(c.ligas),
        "linhas": [
            {"posicao": i, "clube": _clube(c, linha.club_id),
             "pontos": linha.points, "jogos": linha.played, "vitorias": linha.wins,
             "empates": linha.draws, "derrotas": linha.losses,
             "gols_pro": linha.goals_for, "gols_contra": linha.goals_against,
             "saldo": linha.goal_diff, "eu": linha.club_id == c.clube_id}
            for i, linha in enumerate(linhas, 1)
        ],
    }


def _partida_para_json(c: Carreira, partida) -> dict | None:
    if partida is None:
        return None
    sc, sf = partida.stats_casa, partida.stats_fora
    return {
        "casa": _clube(c, partida.casa), "fora": _clube(c, partida.fora),
        "gols_casa": partida.gols_casa, "gols_fora": partida.gols_fora,
        "eventos": [
            {"minuto": e.minuto, "tipo": e.tipo, "texto": e.texto,
             "clube": _clube(c, e.clube)["nome"],
             "meu": e.clube == c.clube_id}
            for e in partida.eventos
        ],
        "estatisticas": [
            {"nome": "posse de bola", "casa": f"{sc.posse}%", "fora": f"{sf.posse}%"},
            {"nome": "finalizacoes", "casa": sc.finalizacoes, "fora": sf.finalizacoes},
            {"nome": "no gol", "casa": sc.no_gol, "fora": sf.no_gol},
            {"nome": "escanteios", "casa": sc.escanteios, "fora": sf.escanteios},
            {"nome": "desarmes", "casa": sc.desarmes, "fora": sf.desarmes},
            {"nome": "faltas", "casa": sc.faltas, "fora": sf.faltas},
        ],
    }


def avancar(jogo: Jogo) -> dict:
    """Joga a proxima data e devolve o que aconteceu."""
    c = jogo.c
    if c.demitido:
        return {"erro": "voce nao trabalha mais aqui"}
    if c.acabou:
        return {"erro": "a temporada acabou", "fim_de_temporada": True}

    resultados, partida = c.avancar()
    tipo, onde = c.ultimo_compromisso
    jogo.ultima_partida = partida
    jogo.ultimos_resultados = resultados
    competicao = c.liga if tipo == "liga" else (
        c.copas[onde].torneio.nome if onde in c.copas else "")
    return {
        "competicao": competicao, "tipo": tipo,
        "partida": _partida_para_json(c, partida),
        "outros": [
            {"casa": _clube(c, r.home), "fora": _clube(c, r.away),
             "gols_casa": r.goals_home, "gols_fora": r.goals_away}
            for r in resultados
            if partida is None or (r.home, r.away) != (partida.casa, partida.fora)
        ],
        "estado": estado(jogo),
    }


def escalar(jogo: Jogo, dados: dict) -> dict:
    c = jogo.c
    tatica = Tatica(
        formacao=dados.get("formacao", c.tatica_atual().formacao),
        marcacao=dados.get("marcacao", c.tatica_atual().marcacao),
        estilo=dados.get("estilo", c.tatica_atual().estilo))
    if isinstance(dados.get("funcoes"), dict):
        elenco = {p.id for p in c.world.squad(c.clube_id)}
        c.funcoes = {k: int(v) for k, v in dados["funcoes"].items()
                     if v and int(v) in elenco}
    onze = dados.get("onze")
    if not onze:
        c.world.escalacao_fixa.pop(c.clube_id, None)
        onze = [p.id for p in arrumar_no_campo(c.world.best_xi(c.clube_id, tatica.vagas),
                                               tatica.formacao)]
    try:
        c.escalar([int(x) for x in onze], tatica)
    except ValueError as e:
        return {"erro": str(e), "estado": estado(jogo)}
    return {"ok": True, "estado": estado(jogo)}


def virar_o_ano(jogo: Jogo) -> dict:
    c = jogo.c
    if not c.acabou:
        return {"erro": "a temporada ainda nao acabou"}
    resumo = c.virar_o_ano()
    jogo.ultimo_resumo = resumo
    return {
        "temporada": resumo["temporada"],
        "campeoes": resumo["campeoes"],
        "copas": resumo.get("copas", {}),
        "minhas_copas": resumo.get("minhas_copas", []),
        "minha_campanha": resumo.get("minha_campanha", {}),
        "posicao": resumo["minha_posicao"], "liga": resumo["minha_liga"],
        "liga_nome": _nome_da_liga(resumo["minha_liga"]),
        # as chaves de campeoes/copas sao ids internos; a tela mostra estes nomes
        "nomes": {**{n: _nome_da_liga(n) for n in c.ligas},
                  **{n: a.torneio.nome for n, a in c.copas.items()}},
        "subi": resumo["subi"], "cai": resumo["cai"],
        "promovidos": resumo["promovidos"], "rebaixados": resumo["rebaixados"],
        "clima": resumo.get("clima", {}),
        "premios": _premios_json(c, resumo.get("premios")),
        "reputacao_tecnico": _reputacao(c),
        "convites": [_convite(c, k) for k in resumo.get("convites", [])],
        "demitido": resumo.get("demitido", False),
        "motivo": resumo.get("motivo_da_demissao", ""),
        "balanco": asdict(resumo["balanco"]) if resumo.get("balanco") else None,
        "premios_de_copa": resumo.get("premios_de_copa", 0),
        "aposentaram": resumo["aposentaram"], "revelados": resumo["revelados"],
        "transferencias": resumo["transferencias"],
        "compras": [{"nome": t.nome, "overall": exibir(t.overall), "preco": t.preco,
                     "de": _clube(c, t.de)["nome"]}
                    for t in resumo.get("compras_do_clube", [])],
        "vendas": [{"nome": t.nome, "overall": exibir(t.overall), "preco": t.preco,
                    "para": _clube(c, t.para)["nome"]}
                   for t in resumo.get("vendas_do_clube", [])],
        # (nome, antes, depois, idade) e (nome, overall, potencial, idade): na escala da tela
        "destaques": [(n, exibir(a), exibir(d), i)
                      for n, a, d, i in resumo.get("destaques_do_clube", [])],
        "base": [(n, exibir(o), exibir(pt), i) for n, o, pt, i in resumo.get("base_do_clube", [])],
        "saidas": resumo.get("aposentadorias_do_clube", []),
        "estado": estado(jogo),
    }


def camisa_svg(jogo: Jogo, clube_id: int, numero: str = "1") -> str:
    """A camisa importada, se houver; senao o desenho parametrico."""
    from fm.importer.camisas import carregar
    from fm.tela_campo import _camisa_svg

    c = jogo.c
    club = c.world.clubs[clube_id]
    bruto = carregar(club.name, numero)
    if bruto:
        return bruto
    pano = club.kit_body or club.color_primary
    detalhe = club.kit_detail or club.color_secondary
    if numero == "2":
        pano, detalhe = detalhe, pano
    return _camisa_svg(pano, detalhe, club.kit_pattern, f"c{clube_id}{numero}")



# --------------------------------------------------------------------- telas novas

def data_do_jogo(c: Carreira) -> str:
    """O dia de hoje na carreira (fm.calendario): o da proxima data da agenda."""
    return texto(c.hoje())


def _estatistica_do_jogador(c: Carreira, pid: int) -> dict:
    est = c.estatisticas
    linha = est.por_jogador.get(pid) if est else None
    return {"jogos": linha.jogos if linha else 0,
            "gols": linha.gols if linha else 0,
            "assistencias": linha.assistencias if linha else 0,
            "amarelos": linha.amarelos if linha else 0,
            "vermelhos": linha.vermelhos if linha else 0}


def jogador(jogo: Jogo, pid: int) -> dict:
    """O perfil completo: identidade, contrato, atributos e a temporada."""
    c = jogo.c
    p = c.world.players.get(pid)
    if p is None:
        return {"erro": "jogador nao existe"}
    return {
        "id": p.id, "nome": p.name, "nacionalidade": p.nationality,
        "idade": p.age(c.temporada), "posicao": p.position,
        "posicao_detalhe": p.position_detail,
        "pe": "esquerdo" if p.foot == "E" else "direito",
        "altura": p.height_cm, "overall": exibir(p.overall),
        "potencial": exibir(p.potential),
        "valor": p.market_value, "salario": p.wage, "contrato": p.contract_until,
        "energia": p.condition, "moral": p.morale, "forma": p.form,
        "clube": _clube(c, p.club_id) if p.club_id in c.world.clubs else None,
        "emprestado_de": (c.world.clubs[p.loan_from].name
                          if p.loan_from in c.world.clubs else None),
        "lesao": _lesao_do(c, p.id),
        "atributos": {
            "finalizacao": p.finishing, "passe": p.passing, "drible": p.dribbling,
            "marcacao": p.marking, "velocidade": p.pace, "forca": p.strength,
            "resistencia": p.stamina, "tecnica": p.technique,
            "posicionamento": p.positioning, "visao": p.vision,
            "reflexos": p.reflexes, "jogo aereo": p.aerial,
        },
        "temporada": _estatistica_do_jogador(c, pid),
    }


def _resultado_curto(c: Carreira, r) -> dict:
    eu_em_casa = r.home == c.clube_id
    meus = r.goals_home if eu_em_casa else r.goals_away
    deles = r.goals_away if eu_em_casa else r.goals_home
    return {"casa": _clube(c, r.home)["nome"], "fora": _clube(c, r.away)["nome"],
            "clube_casa": _clube(c, r.home), "clube_fora": _clube(c, r.away),
            "gols_casa": r.goals_home, "gols_fora": r.goals_away,
            "resultado": "V" if meus > deles else "E" if meus == deles else "D"}


def inicio(jogo: Jogo) -> dict:
    """O painel de abertura: como esta a campanha, o que passou e o que vem."""
    c = jogo.c
    # na ordem das datas, liga e copa misturadas como foram jogadas
    meus = [c.jogos_do_usuario[k] for k in sorted(c.jogos_do_usuario)]
    tabela_ = c.tabela()
    linha = next((x for x in tabela_ if x.club_id == c.clube_id), None)

    futuros = []
    for f in c.calendario:
        if f.matchday > c.rodada and c.clube_id in (f.home, f.away):
            rival = f.away if f.home == c.clube_id else f.home
            futuros.append({"rival": _clube(c, rival)["nome"],
                            "cor": _clube(c, rival)["cor"],
                            "casa": f.home == c.clube_id, "rodada": f.matchday})
    futuros.sort(key=lambda x: x["rodada"])
    return {
        "campanha": {
            "posicao": c.posicao() if tabela_ else 0,
            "pontos": linha.points if linha else 0,
            "jogos": linha.played if linha else 0,
            "vitorias": linha.wins if linha else 0,
            "empates": linha.draws if linha else 0,
            "derrotas": linha.losses if linha else 0,
            "gols_pro": linha.goals_for if linha else 0,
            "gols_contra": linha.goals_against if linha else 0,
        },
        "ultimos": [_resultado_curto(c, r) for r in meus[-10:]][::-1],
        "proximos": futuros[:10],
    }


def estatisticas(jogo: Jogo) -> dict:
    c = jogo.c
    est = c.estatisticas
    if est is None:
        return {"artilheiros": [], "garcons": []}

    def linhas(lista):
        fora = []
        for x in lista:
            p = c.world.players[x.jogador]
            clube = _clube(c, p.club_id) if p.club_id in c.world.clubs else None
            fora.append({"nome": p.name, "posicao": p.position,
                         "clube": clube["nome"] if clube else "-",
                         "cor": clube["cor"] if clube else "#888",
                         "gols": x.gols, "assistencias": x.assistencias,
                         "jogos": x.jogos, "meu": p.club_id == c.clube_id})
        return fora
    return {"artilheiros": linhas(est.artilheiros(c.world, 25)),
            "garcons": linhas(est.garcons(c.world, 25))}


def financas(jogo: Jogo) -> dict:
    from fm.config import load_league
    from fm.financas import CUSTO_DE_OPERACAO, folha_anual, receita_anual

    c = jogo.c
    tier = int(load_league(c.liga).get("tier", 1))
    valor = c.valor_de_elenco.get(c.clube_id)
    receita = receita_anual(c.world, c.clube_id, tier, valor)
    folha = folha_anual(c.world, c.clube_id)
    operacao = int(receita * CUSTO_DE_OPERACAO)
    return {
        "caixa": c.clube.balance, "receita": receita, "folha": folha,
        "operacao": operacao, "saldo_previsto": receita - folha - operacao,
        "valor_do_elenco": valor or 0, "reputacao": c.clube.reputation,
        "salarios": sorted(
            [{"nome": p.name, "posicao": p.position, "salario": p.wage,
              "contrato": p.contract_until, "valor": p.market_value}
             for p in c.world.squad(c.clube_id)],
            key=lambda x: -x["salario"])[:14],
    }


def _rival(c: Carreira, casa: int, fora: int) -> dict:
    outro = fora if casa == c.clube_id else casa
    return {"nome": _clube(c, outro)["nome"], "clube": _clube(c, outro), "casa": casa == c.clube_id}


def calendario(jogo: Jogo) -> dict:
    """A agenda inteira da temporada, com o que ja foi jogado."""
    c = jogo.c
    jogados = {}
    for r in c.jogos():
        if c.clube_id in (r.home, r.away):
            jogados[r.matchday] = _resultado_curto(c, r)
    # a proxima data de cada copa: so nela o confronto sorteado pode aparecer
    proxima_da_copa: dict[str, int] = {}
    for i, (tipo, quem) in enumerate(c.agenda):
        if tipo == "copa" and i >= c.data:
            proxima_da_copa.setdefault(quem, i)
    linhas, rodada = [], 0
    for i, (tipo, quem) in enumerate(c.agenda):
        if tipo == "liga":
            rodada += 1
            f = next((x for x in c.calendario
                      if x.matchday == rodada and c.clube_id in (x.home, x.away)), None)
            rival = None
            if f is not None:
                rival = _rival(c, f.home, f.away)
            linhas.append({"ordem": i, "tipo": "liga", "competicao": c.liga,
                           "dia": texto(dia_da_data(c.temporada, i)),
                           "rodada": rodada, "rival": rival,
                           "resultado": jogados.get(rodada), "passou": i < c.data})
        else:
            a = c.copas.get(quem)
            # a copa: o jogo que o usuario fez nesta data, ou o proximo, se ja sorteado
            r = c.jogos_do_usuario.get(i)
            rival, resultado = None, None
            if r is not None:
                rival, resultado = _rival(c, r.home, r.away), _resultado_curto(c, r)
            elif a is not None and i >= c.data and i == proxima_da_copa.get(quem):
                f, _ = _jogo_de_copa(c, a)
                if f is not None:
                    rival = _rival(c, f.home, f.away)
            linhas.append({"ordem": i, "tipo": "copa",
                           "dia": texto(dia_da_data(c.temporada, i)),
                           "competicao": a.torneio.nome if a else quem,
                           "rodada": None, "rival": rival,
                           "resultado": resultado, "passou": i < c.data})
    return {"datas": linhas, "atual": c.data}


# ------------------------------------------------------------------ menu e nova carreira

def menu(jogo: Jogo) -> dict:
    c = jogo.c
    return {
        "versao": telas.VERSAO, "saves": saves_disponiveis(),
        "carreira": None if c is None else {
            "clube": _clube(c, c.clube_id), "treinador": c.treinador,
            "temporada": c.temporada, "data": data_do_jogo(c)},
    }


def clubes(q: dict) -> dict:
    ligas = [x for x in q.get("ligas", [""])[0].split(",") if x]
    try:
        seed = int(q.get("seed", ["2027"])[0])
    except ValueError:
        seed = 2027
    return telas.clubes(ligas, seed, _clube_do_mundo)


def nova(jogo: Jogo, corpo: dict) -> dict:
    livres = {i for n in telas.NACIONAIS if n["livre"] for i, _ in n["ligas"]}
    ligas = [x for x in corpo.get("ligas", []) if x in livres]
    if not ligas:
        return {"erro": "escolha pelo menos uma liga"}
    try:
        seed = int(corpo.get("seed") or 2027)
        c = Carreira.nova(ligas, str(corpo.get("clube", "")), seed=seed)
    except (ValueError, KeyError) as e:
        return {"erro": str(e)}
    c.treinador = (str(corpo.get("treinador") or "").strip() or "Treinador")[:40]
    _trocar_de_carreira(jogo, c)
    return {"ok": True, "estado": estado(jogo)}


def carregar(jogo: Jogo, corpo: dict) -> dict:
    try:
        c = Carreira.carregar(str(corpo.get("nome", "")))
    except FileNotFoundError as e:
        return {"erro": str(e)}
    except (KeyError, TypeError, ValueError) as e:
        return {"erro": f"Esse save não abre nesta versão do jogo: {e}"}
    _trocar_de_carreira(jogo, c)
    return {"ok": True, "estado": estado(jogo)}


def _trocar_de_carreira(jogo: Jogo, c: Carreira) -> None:
    if jogo.ao_vivo is not None and not jogo.ao_vivo.acabou:
        jogo.ao_vivo.seguir(ate_o_fim=True)      # nao deixa thread pendurada
    jogo.c = c
    jogo.ao_vivo = None
    jogo.pos_jogo = None
    jogo.lidas = set()


# ------------------------------------------------------------------ partida ao vivo

def _competicao_da_proxima(c: Carreira) -> tuple[str, str]:
    tipo, onde, _ = c.proximo_jogo()
    if tipo == "liga":
        from fm.config import load_league
        return tipo, f"{telas.nome_da_liga(c.liga)} · Rodada {c.rodada + 1}"
    if tipo == "copa":
        a = c.copas[onde]
        _, ida = _jogo_de_copa(c, a)
        extra = (f" · Volta (ida: {ida['casa']} {ida['gols_casa']} × {ida['gols_fora']} "
                 f"{ida['fora']})" if ida else "")
        return tipo, f"{a.torneio.nome} · {a.nome_da_fase}{extra}"
    return "", ""


def _competicao_em_campo(c: Carreira) -> tuple[str, str] | None:
    """O rotulo da partida em andamento, pelo que a carreira esta jogando AGORA. O
    previsto (_competicao_da_proxima) erra na copa: o sorteio so sai no dia, e a partida
    de copa aparecia como a proxima rodada da liga."""
    tipo, onde = c.ultimo_compromisso
    if tipo == "liga":
        return tipo, f"{telas.nome_da_liga(c.liga)} · Rodada {c.rodada + 1}"
    if tipo == "copa" and onde in c.copas:
        a = c.copas[onde]
        _, ida = _jogo_de_copa(c, a)
        extra = (f" · Volta (ida: {ida['casa']} {ida['gols_casa']} × {ida['gols_fora']} "
                 f"{ida['fora']})" if ida else "")
        return tipo, f"{a.torneio.nome} · {a.nome_da_fase}{extra}"
    return None


def _jogo_de_copa(c: Carreira, a) -> tuple:
    """O proximo jogo do usuario na copa, se ja sorteado, e o placar da ida quando ele
    e a volta. Antes do sorteio (a proxima rodada so e sorteada no dia) os dois sao None."""
    if not a.pendentes:
        return None, None
    f = next((x for x in a.pendentes[0] if c.clube_id in (x.home, x.away)), None)
    if f is None:
        return None, None
    ida = next((r for r in a.resultados if {r.home, r.away} == {f.home, f.away}), None)
    if ida is None:
        return f, None
    return f, {"casa": c.world.clubs[ida.home].name, "fora": c.world.clubs[ida.away].name,
               "gols_casa": ida.goals_home, "gols_fora": ida.goals_away}


def partida_iniciar(jogo: Jogo, corpo: dict | None = None) -> dict:
    """Comeca a proxima data com a partida do usuario ao vivo."""
    from fm.ao_vivo import PartidaAoVivo

    c = jogo.c
    if jogo.ao_vivo is not None and not jogo.ao_vivo.acabou:
        return partida_atual(jogo)               # recarregou a pagina no meio do jogo
    if c.demitido:
        return {"erro": "voce nao trabalha mais aqui"}
    if c.acabou:
        return {"erro": "a temporada acabou", "fim_de_temporada": True}
    jogo.pos_jogo = None
    # Data sem jogo do clube (copa de outro continente, fase em que ele nao esta) passa
    # direto ate a partida dele: com todos os paises no mundo eram ~50 interrupcoes por
    # temporada. Para antes se chegar proposta por um jogador (ela caduca na data
    # seguinte) ou se ele for demitido.
    puladas = 0
    while True:
        jogo.competicao_ao_vivo = _competicao_da_proxima(c)
        tipo, _, _ = c.proximo_jogo()
        # a posicao ANTES da rodada, para o fim de jogo dizer se subiu ou caiu
        jogo.posicao_antes = c.posicao() if tipo == "liga" and c.rodada > 0 else None
        propostas_antes = len(c.propostas_pendentes())
        jogo.ao_vivo = PartidaAoVivo(c)
        jogo.ao_vivo.perguntar_penalti = bool((corpo or {}).get("perguntar_penalti", True))
        jogo.ao_vivo.comecar()
        av = jogo.ao_vivo
        # a partida ja comecou: a competicao e a que esta em campo, nao a prevista
        jogo.competicao_ao_vivo = _competicao_em_campo(c) or jogo.competicao_ao_vivo
        sem_jogo = av.resultado is not None and av.resultado[1] is None
        if (not sem_jogo or c.acabou or c.demitido
                or len(c.propostas_pendentes()) > propostas_antes):
            break
        puladas += 1
    retrato = partida_atual(jogo)
    retrato["datas_puladas"] = puladas
    return retrato


def partida_seguir(jogo: Jogo, corpo: dict) -> dict:
    av = jogo.ao_vivo
    if av is None:
        return {"erro": "nao ha partida em andamento"}
    try:
        av.seguir(trocas=corpo.get("trocas"), tatica=corpo.get("tatica"),
                  ate_o_fim=bool(corpo.get("ate_o_fim")), penalti=corpo.get("penalti"))
    except (ValueError, TypeError) as e:
        return {"erro": str(e), **partida_atual(jogo)}
    return partida_atual(jogo)


def partida_atual(jogo: Jogo) -> dict:
    av = jogo.ao_vivo
    if av is None:
        return {"erro": "nao ha partida em andamento"}
    retrato = av.retrato(lambda cid: _clube(jogo.c, cid))
    tipo, competicao = jogo.competicao_ao_vivo
    retrato["competicao"] = competicao
    if retrato.get("sem_jogo") and av.resultado is not None:
        # data sem jogo do usuario: a tela mostra os resultados e segue
        retrato["resultados"] = [
            {"casa": _clube(jogo.c, r.home), "fora": _clube(jogo.c, r.away),
             "gols_casa": r.goals_home, "gols_fora": r.goals_away}
            for r in av.resultado[0]]
        tipo_, onde = jogo.c.ultimo_compromisso
        retrato["competicao"] = (jogo.c.copas[onde].torneio.nome
                                 if tipo_ == "copa" and onde in jogo.c.copas else competicao)
    if av.acabou and av.resultado is not None:
        resultados, partida = av.resultado
        jogo.ultima_partida, jogo.ultimos_resultados = partida, resultados
        if partida is not None and jogo.pos_jogo is None:
            jogo.pos_jogo = telas.pos_jogo(jogo.c, partida, resultados, competicao, tipo,
                                           lambda cid: _clube(jogo.c, cid),
                                           getattr(jogo, "posicao_antes", None))
        if jogo.pos_jogo is not None:
            retrato["impacto"] = jogo.pos_jogo.get("impacto")
        retrato["estado"] = estado(jogo)
    return retrato


def pos_jogo(jogo: Jogo) -> dict:
    return jogo.pos_jogo or {"erro": "nenhuma partida jogada ainda"}


# ------------------------------------------------------------------ transferencias

def _proposta_json(c: Carreira, prop) -> dict:
    p = c.world.players.get(prop.jogador)
    return {"id": prop.id, "status": prop.status, "valor": prop.valor,
            "temporada": prop.temporada, "clube": _clube(c, prop.clube),
            "contra_usada": prop.contra_usada,
            "jogador": None if p is None else {
                "id": p.id, "nome": p.name, "posicao": p.position,
                "overall": exibir(p.overall),
                "idade": p.age(c.temporada), "valor": p.market_value}}


def propostas(jogo: Jogo) -> dict:
    c = jogo.c
    ordem = {"pendente": 0}
    lista = sorted(c.propostas, key=lambda x: (ordem.get(x.status, 1), -x.temporada, -x.data))
    return {"propostas": [_proposta_json(c, x) for x in lista]}


def responder_proposta(jogo: Jogo, corpo: dict) -> dict:
    c = jogo.c
    acao = {"tipo": corpo.get("acao"), "proposta": corpo.get("proposta")}
    if corpo.get("acao") == "contraproposta":
        acao["valor"] = int(corpo.get("valor") or 0)
    r = c.executar(acao)
    prop = c._proposta(corpo.get("proposta", ""))
    return {**r, "proposta": _proposta_json(c, prop) if prop else None, "estado": estado(jogo)}


def oferta(jogo: Jogo, corpo: dict) -> dict:
    """O usuario oferece; o clube dono responde. Nao muda o mundo: so a aba Negociacoes."""
    from fm import negocios as neg
    c = jogo.c
    pid, valor = int(corpo.get("jogador", 0)), int(corpo.get("valor") or 0)
    r = neg.avaliar_oferta(c, pid, valor)
    p = c.world.players.get(pid)
    if p is not None and r["resultado"] != "erro":
        jogo.negociacoes.append({
            "jogador": pid, "nome": p.name, "posicao": p.position,
            "overall": exibir(p.overall),
            "clube": _clube(c, p.club_id) if p.club_id in c.world.clubs else None,
            "oferta": valor, "resultado": r["resultado"], "valor": r.get("valor"),
            "data": data_do_jogo(c)})
    return r


def contrato_info(jogo: Jogo, pid: int | None) -> dict:
    from fm import negocios as neg
    c = jogo.c
    p = c.world.players.get(pid or 0)
    if p is None:
        return {"erro": "jogador nao existe"}
    return {"jogador": pid, "nome": p.name, "pretendido": neg.salario_pretendido(c, p),
            "salario_atual": p.wage, "ambicao": neg.recusa_por_ambicao(c, p),
            "caixa": neg.resumo_do_caixa(c)}


def contratar(jogo: Jogo, corpo: dict) -> dict:
    """Contrato com o jogador depois do clube aceitar. Aceito, o negocio fecha."""
    from fm import negocios as neg
    c = jogo.c
    pid = int(corpo.get("jogador", 0))
    salario, anos = int(corpo.get("salario") or 0), int(corpo.get("anos") or 3)
    r = neg.avaliar_contrato(c, pid, salario, anos)
    if r["resultado"] != "aceita":
        return r
    feito = c.executar({"tipo": "compra", "jogador": pid, "preco": int(corpo.get("preco") or 0),
                        "salario": salario, "anos": anos})
    if "erro" in feito:
        return {"resultado": "erro", "mensagem": feito["erro"]}
    return {"resultado": "concluida", "mensagem": feito["mensagem"], "estado": estado(jogo)}


def renovacao_info(jogo: Jogo, pid: int | None) -> dict:
    from fm import negocios as neg
    c = jogo.c
    p = c.world.players.get(pid or 0)
    if p is None or p.club_id != c.clube_id:
        return {"erro": "jogador nao e do seu clube"}
    return {"jogador": pid, "nome": p.name, "contrato": p.contract_until,
            "salario_atual": p.wage, **neg.interesse_em_renovar(c, p)}


def renovar(jogo: Jogo, corpo: dict) -> dict:
    from fm import negocios as neg
    c = jogo.c
    pid = int(corpo.get("jogador", 0))
    salario, anos = int(corpo.get("salario") or 0), int(corpo.get("anos") or 1)
    r = neg.avaliar_renovacao(c, pid, salario, anos)
    if r["resultado"] != "aceita":
        return r
    feito = c.executar({"tipo": "renovacao", "jogador": pid, "salario": salario, "anos": anos})
    if "erro" in feito:
        return {"resultado": "erro", "mensagem": feito["erro"]}
    return {"resultado": "concluida", "mensagem": feito["mensagem"], "estado": estado(jogo)}


def emprestimo_info(jogo: Jogo, pid: int | None) -> dict:
    """Jogador de fora: a resposta do dono ao pedido. Jogador meu: quem o quer."""
    from fm import negocios as neg
    c = jogo.c
    p = c.world.players.get(pid or 0)
    if p is None:
        return {"erro": "jogador nao existe"}
    if p.club_id == c.clube_id:
        if p.loan_from is not None:
            return {"erro": f"{p.name} esta emprestado a voce: nao da para repassar"}
        return {"sentido": "saida", "jogador": p.id, "nome": p.name,
                "interessados": [_clube(c, k) for k in neg.interessados_no_emprestimo(c, p.id)]}
    return {"sentido": "entrada", "jogador": p.id, "nome": p.name,
            **neg.avaliar_emprestimo(c, p.id), "caixa": neg.resumo_do_caixa(c)}


def emprestar(jogo: Jogo, corpo: dict) -> dict:
    c = jogo.c
    pid = int(corpo.get("jogador", 0))
    if corpo.get("clube"):
        acao = {"tipo": "emprestimo_saida", "jogador": pid, "clube": int(corpo["clube"])}
    else:
        acao = {"tipo": "emprestimo_entrada", "jogador": pid}
    feito = c.executar(acao)
    if "erro" in feito:
        return {"resultado": "erro", "mensagem": feito["erro"]}
    return {"resultado": "concluida", "mensagem": feito["mensagem"], "estado": estado(jogo)}


def tabela_da_competicao(jogo: Jogo, q: dict) -> dict:
    """`?comp=auto` abre na competicao do proximo jogo; `?comp=<liga ou copa>` escolhe;
    sem nada (ou `?liga=`) e a tabela da divisao, como sempre foi."""
    c = jogo.c
    comp = q.get("comp", q.get("liga", [None]))[0]
    if comp == "auto":
        comp = c.competicao_do_proximo() or c.liga
    clube = lambda cid: _clube(c, cid)  # noqa: E731
    if comp in c.copas:
        return telas.copa(c, comp, clube)
    return telas.classificacao(c, comp, clube)


# ------------------------------------------------------------------ tecnicos e premios

def _nome_do_tecnico(c: Carreira, t) -> str:
    return c.treinador if t.usuario else t.nome     # o nome do usuario e o do menu


def _reputacao(c: Carreira) -> dict:
    from fm import tecnicos as tec
    eu = c.tecnicos.get(tec.USUARIO)
    if eu is None:
        return {}
    ordem = tec.ranking(c.tecnicos)
    return {"valor": round(eu.reputacao, 1), "variacao": eu.variacao,
            "posicao": ordem.index(eu) + 1, "de": len(ordem)}


def _convite(c: Carreira, clube: int) -> dict:
    """Um clube que chama o usuario, com o que pesa na escolha."""
    from fm import tecnicos as tec
    k = c.world.clubs[clube]
    liga = next((n for n in c.ligas if c._id(n) == k.league_id), c.liga)
    tabela = c.tabela(liga)
    pos = next((i for i, ln in enumerate(tabela, 1) if ln.club_id == clube), None)
    jogou = bool(tabela) and tabela[0].played > 0
    atual = tec.do_clube(c.tecnicos, clube)
    return {"clube": _clube(c, clube), "liga": _nome_da_liga(liga),
            "reputacao": k.reputation, "posicao": pos if jogou else None,
            "tecnico_atual": atual.nome if atual and not atual.usuario else None,
            "caixa": k.balance}


def tecnicos(jogo: Jogo) -> dict:
    """O ranking mundial de tecnicos: os 40 primeiros, e o usuario onde estiver."""
    from fm import tecnicos as tec
    c = jogo.c
    ordem = tec.ranking(c.tecnicos)
    linhas = []
    for i, t in enumerate(ordem, 1):
        if i > 40 and not t.usuario:
            continue
        linhas.append({"posicao": i, "nome": _nome_do_tecnico(c, t), "usuario": t.usuario,
                       "clube": _clube(c, t.clube) if t.clube in c.world.clubs else None,
                       "reputacao": round(t.reputacao, 1), "variacao": t.variacao,
                       "titulos": len(t.titulos), "idade": t.idade(c.temporada)})
    eu = c.tecnicos.get(tec.USUARIO)
    return {"ranking": linhas, "meus_titulos": eu.titulos if eu else [],
            "passagens": eu.passagens if eu else [], "reputacao": _reputacao(c)}


def _premios_json(c: Carreira, p: dict | None) -> dict | None:
    """Os premios com os tecnicos pelo nome (os jogadores ja vem com nome e clube do
    dia em que ganharam)."""
    if not p:
        return None
    ligas = {}
    for chave, d in p["ligas"].items():
        t = c.tecnicos.get(d["tecnico"]) if d.get("tecnico") is not None else None
        ligas[chave] = {**d, "tecnico": None if t is None else {
            "nome": _nome_do_tecnico(c, t), "usuario": t.usuario}}
    return {"temporada": p["temporada"], "bola_de_ouro": p["bola_de_ouro"], "ligas": ligas,
            "meu_clube": c.clube_id}


def premios(jogo: Jogo, temporada: int | None) -> dict:
    c = jogo.c
    anos = sorted(c.premios, reverse=True)
    escolhido = temporada if temporada in c.premios else (anos[0] if anos else None)
    return {"temporadas": anos, "temporada": escolhido,
            "premios": _premios_json(c, c.premios.get(escolhido)) if escolhido else None}


def assumir(jogo: Jogo, corpo: dict) -> dict:
    feito = jogo.c.executar({"tipo": "assumir", "clube": int(corpo.get("clube", 0))})
    if "erro" in feito:
        return {"erro": feito["erro"]}
    jogo.pos_jogo = None
    return {"ok": True, "mensagem": feito["mensagem"], "estado": estado(jogo)}


def _inteiro(q: dict, chave: str) -> int | None:
    try:
        return int(q.get(chave, [""])[0])
    except ValueError:
        return None


ROTAS_SEM_CARREIRA = {"/api/menu", "/api/catalogo", "/api/clubes"}

ROTAS_GET = {
    "/api/menu": lambda jogo, q: menu(jogo),
    "/api/catalogo": lambda jogo, q: telas.catalogo(),
    "/api/clubes": lambda jogo, q: clubes(q),
    "/api/mercado": lambda jogo, q: telas.mercado(jogo.c, q, lambda cid: _clube(jogo.c, cid)),
    "/api/propostas": lambda jogo, q: propostas(jogo),
    "/api/renovacao": lambda jogo, q: renovacao_info(jogo, _inteiro(q, "jogador")),
    "/api/contrato": lambda jogo, q: contrato_info(jogo, _inteiro(q, "jogador")),
    "/api/emprestimo": lambda jogo, q: emprestimo_info(jogo, _inteiro(q, "jogador")),
    "/api/tecnicos": lambda jogo, q: tecnicos(jogo),
    "/api/premios": lambda jogo, q: premios(jogo, _inteiro(q, "temporada")),
    "/api/negocios": lambda jogo, q: {"negociacoes": jogo.negociacoes[::-1],
                                      "movimentos": jogo.c.movimentos[::-1]},
    "/api/mensagens": lambda jogo, q: {
        "mensagens": telas.mensagens(jogo.c, data_do_jogo(jogo.c), jogo.lidas)},
    "/api/treinador": lambda jogo, q: telas.treinador(jogo.c),
    "/api/classificacao": lambda jogo, q: tabela_da_competicao(jogo, q),
    "/api/partida": lambda jogo, q: partida_atual(jogo),
    "/api/selecao": lambda jogo, q: telas.selecao(
        jogo.c, q.get("liga", [None])[0], _inteiro(q, "rodada"),
        lambda cid: _clube(jogo.c, cid)),
    "/api/artilharia": lambda jogo, q: telas.artilharia(
        jogo.c, q.get("comp", [None])[0], _inteiro(q, "temporada"),
        lambda cid: _clube(jogo.c, cid)),
    "/api/posjogo": lambda jogo, q: pos_jogo(jogo),
    "/api/estado": lambda jogo, q: estado(jogo),
    "/api/tabela": lambda jogo, q: tabela(jogo, q.get("liga", [None])[0]),
    "/api/inicio": lambda jogo, q: inicio(jogo),
    "/api/estatisticas": lambda jogo, q: estatisticas(jogo),
    "/api/financas": lambda jogo, q: financas(jogo),
    "/api/calendario": lambda jogo, q: calendario(jogo),
    "/api/jogador": lambda jogo, q: jogador(jogo, int(q.get("id", [0])[0])),
}
ROTAS_POST_SEM_CARREIRA = {"/api/nova", "/api/carregar", "/api/sair"}

ROTAS_POST = {
    "/api/nova": nova,
    "/api/carregar": carregar,
    "/api/observar": lambda jogo, corpo: telas.observar(jogo.c, int(corpo.get("id", 0))),
    "/api/oferta": oferta,
    "/api/contrato": contratar,
    "/api/renovacao": renovar,
    "/api/emprestimo": emprestar,
    "/api/assumir": assumir,
    "/api/propostas": responder_proposta,
    "/api/lida": lambda jogo, corpo: (jogo.lidas.update(corpo.get("ids", [])),
                                      {"ok": True})[1],
    "/api/partida/iniciar": lambda jogo, corpo: partida_iniciar(jogo, corpo),
    "/api/partida/seguir": partida_seguir,
    "/api/avancar": lambda jogo, corpo: avancar(jogo),
    "/api/escalar": escalar,
    "/api/virar": lambda jogo, corpo: virar_o_ano(jogo),
    "/api/salvar": lambda jogo, corpo: {
        "arquivo": str(jogo.c.salvar(corpo.get("nome", "carreira")))},
}


TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2"}


def fotografar_a_tela() -> dict[str, bytes]:
    """Os arquivos da tela, lidos UMA vez, quando o servidor sobe.

    Servir do disco a cada pedido juntava tela nova com Python velho: com o servidor
    aberto desde antes de uma atualizacao, o navegador recebia o JS novo, pedia campos
    que o Python carregado nao mandava, e a escalacao sumia. Com a foto, tela e servidor
    sao sempre da mesma versao -- atualizou o codigo, reinicia o servidor.
    """
    return {str(a.relative_to(WEB)).replace("\\", "/"): a.read_bytes()
            for a in WEB.rglob("*") if a.is_file()}


class ServidorDoJogo(ThreadingHTTPServer):
    """Sem SO_REUSEADDR: no Windows ele deixa DOIS servidores ouvirem a mesma porta, e os
    pedidos caem ora num, ora no outro. Um segundo `servir` tem de falhar, nao dividir."""
    allow_reuse_address = False

    def server_bind(self) -> None:
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def criar_handler(jogo: Jogo, tela: dict[str, bytes] | None = None):
    tela = tela if tela is not None else fotografar_a_tela()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):        # silencio: o terminal e' do usuario
            pass

        def _responder(self, corpo: bytes, tipo: str, codigo: int = 200) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            # sem cache: a tela tem de ser sempre a do servidor que esta rodando
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, dados: dict, codigo: int = 200) -> None:
            self._responder(json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                            "application/json; charset=utf-8", codigo)

        def do_GET(self) -> None:                                  # noqa: N802
            url = urlparse(self.path)
            caminho = url.path
            from urllib.parse import parse_qs
            q = parse_qs(url.query)

            if caminho.startswith("/api/escudo/"):
                nome = caminho.rsplit("/", 1)[-1]
                with jogo.trava:
                    arq = None
                    if jogo.c is not None and nome.isdigit():
                        club = jogo.c.world.clubs.get(int(nome))
                        arq = _escudos().get(club.name) if club else None
                    elif nome.startswith("n-"):     # pela escolha de clube, sem carreira
                        from urllib.parse import unquote
                        arq = _escudos().get(unquote(nome[2:]))
                if arq is None:
                    self._json({"erro": "sem escudo"}, 404)
                else:
                    self._responder(arq.read_bytes(), "image/png")
                return
            if caminho.startswith("/api/camisa/"):
                if jogo.c is None:
                    self._json({"erro": "sem carreira"}, 404)
                    return
                partes = caminho.rsplit("/", 2)
                with jogo.trava:
                    svg = camisa_svg(jogo, int(partes[-2]), partes[-1])
                self._responder(svg.encode("utf-8"), "image/svg+xml; charset=utf-8")
                return
            if caminho in ROTAS_GET:
                if jogo.c is None and caminho not in ROTAS_SEM_CARREIRA:
                    self._json({"erro": "sem carreira", "sem_carreira": True})
                    return
                with jogo.trava:
                    self._rodar(ROTAS_GET[caminho], jogo, q)
                return

            nome = "index.html" if caminho in ("/", "") else caminho.lstrip("/")
            if nome not in tela:
                self._json({"erro": "nao encontrado"}, 404)
                return
            self._responder(tela[nome],
                            TIPOS.get(Path(nome).suffix, "application/octet-stream"))

        def do_POST(self) -> None:                                 # noqa: N802
            caminho = urlparse(self.path).path
            if caminho not in ROTAS_POST:
                self._json({"erro": "nao encontrado"}, 404)
                return
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}
            if caminho == "/api/sair":
                # o navegador nao pode fechar a si mesmo; o servidor pode parar
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if jogo.c is None and caminho not in ROTAS_POST_SEM_CARREIRA:
                self._json({"erro": "sem carreira", "sem_carreira": True})
                return
            with jogo.trava:
                self._rodar(ROTAS_POST[caminho], jogo, corpo)

        def _rodar(self, rota, jogo, dados) -> None:
            """Erro dentro de uma rota volta como JSON e aparece na tela. Antes a conexao
            caia sem resposta e a pagina ficava esperando em silencio -- "nao funciona",
            sem pista nenhuma. O rastro completo vai para o terminal."""
            try:
                resposta = rota(jogo, dados)
            except Exception as e:  # noqa: BLE001 -- a fronteira com o navegador
                import traceback
                traceback.print_exc()
                self._json({"erro": f"erro interno: {type(e).__name__}: {e}"}, 500)
                return
            self._json(resposta)

    return Handler


def servir(carreira: Carreira | None = None, porta: int = 8000,
           abrir: bool = True) -> None:
    """Sobe o servidor e abre o navegador. Bloqueia ate Ctrl+C.

    Sem carreira, o jogo abre no menu principal: novo jogo ou jogo salvo.
    """
    jogo = Jogo(carreira)
    try:
        servidor = ServidorDoJogo(("127.0.0.1", porta), criar_handler(jogo))
    except OSError:
        print(f"  A porta {porta} ja esta em uso -- provavelmente o jogo ja esta aberto em")
        print("  outro terminal. Feche aquele (Ctrl+C) ou use outra porta: --porta 8001")
        return
    url = f"http://127.0.0.1:{porta}/"
    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"  PRANCHETA 11 -- {url}"
          + (f"  ({carreira.clube.name})" if carreira else ""))
    print("  Ctrl+C para encerrar")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  ate mais.")
    finally:
        servidor.server_close()
