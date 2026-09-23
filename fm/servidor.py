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

from fm.carreira import Carreira
from fm.tatica import ESTILOS, FORMACOES, MARCACOES, Tatica

WEB = Path(__file__).resolve().parent / "web"
POSICAO_ORDEM = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}


class Jogo:
    """A carreira e o pouco de estado que so a interface precisa.

    A ultima partida fica guardada aqui porque o navegador pede o estado e a sumula em
    requisicoes separadas -- a Carreira nao tem por que saber disso.
    """

    def __init__(self, carreira: Carreira) -> None:
        self.c = carreira
        self.ultima_partida = None
        self.ultimos_resultados: list = []
        self.ultimo_resumo: dict | None = None
        self.trava = threading.Lock()


def _jogador(c: Carreira, p, titular: bool) -> dict:
    return {
        "id": p.id, "nome": p.name, "posicao": p.position,
        "overall": p.overall, "potencial": p.potential,
        "idade": p.age(c.temporada), "energia": p.condition,
        "salario": p.wage, "valor": p.market_value, "titular": titular,
        "contrato": p.contract_until, "moral": p.morale,
        **_estatistica_do_jogador(c, p.id),
    }


def _clube(c: Carreira, cid: int) -> dict:
    club = c.world.clubs[cid]
    return {
        "id": club.id, "nome": club.name,
        "cor": club.color_primary, "cor2": club.color_secondary,
        "camisa": club.kit_body or club.color_primary,
        "camisa2": club.kit_detail or club.color_secondary,
        "padrao": club.kit_pattern,
    }


def estado(jogo: Jogo) -> dict:
    """Tudo que o lobby precisa numa chamada so."""
    c = jogo.c
    tatica = c.tatica_atual()
    onze = set(c.escalacao_atual())
    elenco = sorted(c.world.squad(c.clube_id),
                    key=lambda p: (POSICAO_ORDEM.get(p.position, 9), -p.overall))
    tipo, onde, jogo_ = c.proximo_jogo()

    proximo = None
    if tipo == "liga" and jogo_ is not None:
        rival = jogo_.away if jogo_.home == c.clube_id else jogo_.home
        proximo = {"tipo": "liga", "competicao": c.liga,
                   "rival": _clube(c, rival),
                   "casa": jogo_.home == c.clube_id,
                   "rodada": c.rodada + 1}
    elif tipo == "copa":
        a = c.copas[onde]
        proximo = {"tipo": "copa", "competicao": a.torneio.nome, "id": onde,
                   "fase": a.nome_da_fase, "vivos": len(a.vivos), "rival": None}

    tabela = c.tabela()
    minha = next((linha for linha in tabela if linha.club_id == c.clube_id), None)
    ap = c.aprovacao
    return {
        "clube": _clube(c, c.clube_id),
        "treinador": c.treinador, "data": data_do_jogo(c),
        "liga": c.liga, "temporada": c.temporada,
        "rodada": c.rodada, "total_de_rodadas": c.total_de_rodadas,
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
                   "estilo": tatica.estilo, "vagas": tatica.vagas},
        "opcoes": {"formacoes": sorted(FORMACOES), "marcacoes": sorted(MARCACOES),
                   "estilos": sorted(ESTILOS)},
        "elenco": [_jogador(c, p, p.id in onze) for p in elenco],
        "onze": list(c.escalacao_atual()),
        "copas": [
            {"id": nome, "nome": a.torneio.nome, "fase": a.nome_da_fase,
             "vivo": a.esta_vivo(c.clube_id), "acabou": a.acabou,
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
    onze = dados.get("onze")
    if not onze:
        c.world.escalacao_fixa.pop(c.clube_id, None)
        onze = [p.id for p in c.world.best_xi(c.clube_id, tatica.vagas)]
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
        "subi": resumo["subi"], "cai": resumo["cai"],
        "promovidos": resumo["promovidos"], "rebaixados": resumo["rebaixados"],
        "clima": resumo.get("clima", {}),
        "demitido": resumo.get("demitido", False),
        "motivo": resumo.get("motivo_da_demissao", ""),
        "balanco": asdict(resumo["balanco"]) if resumo.get("balanco") else None,
        "premios_de_copa": resumo.get("premios_de_copa", 0),
        "aposentaram": resumo["aposentaram"], "revelados": resumo["revelados"],
        "transferencias": resumo["transferencias"],
        "compras": [{"nome": t.nome, "overall": t.overall, "preco": t.preco,
                     "de": _clube(c, t.de)["nome"]}
                    for t in resumo.get("compras_do_clube", [])],
        "vendas": [{"nome": t.nome, "overall": t.overall, "preco": t.preco,
                    "para": _clube(c, t.para)["nome"]}
                   for t in resumo.get("vendas_do_clube", [])],
        "destaques": resumo.get("destaques_do_clube", []),
        "base": resumo.get("base_do_clube", []),
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

# O motor conta RODADAS, nao dias. A data e derivada para dar o clima de temporada que um
# manager tem -- e cosmetica, e nenhuma regra depende dela.
INICIO_DA_TEMPORADA = (4, 6)        # a temporada abre em 6 de abril
DIAS_POR_DATA = 4


def data_do_jogo(c: Carreira) -> str:
    from datetime import date, timedelta
    mes, dia = INICIO_DA_TEMPORADA
    return (date(c.temporada, mes, dia)
            + timedelta(days=c.data * DIAS_POR_DATA)).strftime("%d/%m/%Y")


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
        "altura": p.height_cm, "overall": p.overall, "potencial": p.potential,
        "valor": p.market_value, "salario": p.wage, "contrato": p.contract_until,
        "energia": p.condition, "moral": p.morale, "forma": p.form,
        "clube": _clube(c, p.club_id) if p.club_id in c.world.clubs else None,
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
            "gols_casa": r.goals_home, "gols_fora": r.goals_away,
            "resultado": "V" if meus > deles else "E" if meus == deles else "D"}


def inicio(jogo: Jogo) -> dict:
    """O painel de abertura: como esta a campanha, o que passou e o que vem."""
    c = jogo.c
    meus = [r for r in c.jogos() if c.clube_id in (r.home, r.away)]
    for a in c.copas.values():
        meus += [r for r in a.resultados_do_ano if c.clube_id in (r.home, r.away)]
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


def calendario(jogo: Jogo) -> dict:
    """A agenda inteira da temporada, com o que ja foi jogado."""
    c = jogo.c
    jogados = {}
    for r in c.jogos():
        if c.clube_id in (r.home, r.away):
            jogados[r.matchday] = _resultado_curto(c, r)
    linhas, rodada = [], 0
    for i, (tipo, quem) in enumerate(c.agenda):
        if tipo == "liga":
            rodada += 1
            f = next((x for x in c.calendario
                      if x.matchday == rodada and c.clube_id in (x.home, x.away)), None)
            rival = None
            if f is not None:
                outro = f.away if f.home == c.clube_id else f.home
                rival = {"nome": _clube(c, outro)["nome"], "casa": f.home == c.clube_id}
            linhas.append({"ordem": i, "tipo": "liga", "competicao": c.liga,
                           "rodada": rodada, "rival": rival,
                           "resultado": jogados.get(rodada), "passou": i < c.data})
        else:
            a = c.copas.get(quem)
            linhas.append({"ordem": i, "tipo": "copa",
                           "competicao": a.torneio.nome if a else quem,
                           "rodada": None, "rival": None,
                           "resultado": None, "passou": i < c.data})
    return {"datas": linhas, "atual": c.data}


ROTAS_GET = {
    "/api/estado": lambda jogo, q: estado(jogo),
    "/api/tabela": lambda jogo, q: tabela(jogo, q.get("liga", [None])[0]),
    "/api/inicio": lambda jogo, q: inicio(jogo),
    "/api/estatisticas": lambda jogo, q: estatisticas(jogo),
    "/api/financas": lambda jogo, q: financas(jogo),
    "/api/calendario": lambda jogo, q: calendario(jogo),
    "/api/jogador": lambda jogo, q: jogador(jogo, int(q.get("id", [0])[0])),
}
ROTAS_POST = {
    "/api/avancar": lambda jogo, corpo: avancar(jogo),
    "/api/escalar": escalar,
    "/api/virar": lambda jogo, corpo: virar_o_ano(jogo),
    "/api/salvar": lambda jogo, corpo: {
        "arquivo": str(jogo.c.salvar(corpo.get("nome", "carreira")))},
}


def criar_handler(jogo: Jogo):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):        # silencio: o terminal e' do usuario
            pass

        def _responder(self, corpo: bytes, tipo: str, codigo: int = 200) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
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

            if caminho.startswith("/api/camisa/"):
                partes = caminho.rsplit("/", 2)
                with jogo.trava:
                    svg = camisa_svg(jogo, int(partes[-2]), partes[-1])
                self._responder(svg.encode("utf-8"), "image/svg+xml; charset=utf-8")
                return
            if caminho in ROTAS_GET:
                with jogo.trava:
                    self._json(ROTAS_GET[caminho](jogo, q))
                return

            arquivo = WEB / ("index.html" if caminho in ("/", "") else caminho.lstrip("/"))
            if not arquivo.is_file() or WEB not in arquivo.resolve().parents:
                self._json({"erro": "nao encontrado"}, 404)
                return
            tipos = {".html": "text/html; charset=utf-8", ".css": "text/css",
                     ".js": "application/javascript; charset=utf-8",
                     ".svg": "image/svg+xml"}
            self._responder(arquivo.read_bytes(),
                            tipos.get(arquivo.suffix, "application/octet-stream"))

        def do_POST(self) -> None:                                 # noqa: N802
            caminho = urlparse(self.path).path
            if caminho not in ROTAS_POST:
                self._json({"erro": "nao encontrado"}, 404)
                return
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}
            with jogo.trava:
                self._json(ROTAS_POST[caminho](jogo, corpo))

    return Handler


def servir(carreira: Carreira, porta: int = 8000, abrir: bool = True) -> None:
    """Sobe o servidor e abre o navegador. Bloqueia ate Ctrl+C."""
    jogo = Jogo(carreira)
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), criar_handler(jogo))
    url = f"http://127.0.0.1:{porta}/"
    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"  {carreira.clube.name} -- {url}")
    print("  Ctrl+C para encerrar")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  ate mais.")
    finally:
        servidor.server_close()
