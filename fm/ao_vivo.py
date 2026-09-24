"""A partida ao vivo: o motor rodando numa thread que PARA a cada bloco de 5 minutos.

O motor ja tinha o gancho: `simular_partida` chama uma funcao ao fim de cada bloco e so
segue quando ela volta. A tela ao vivo e isso -- a funcao publica o retrato da partida e
espera a proxima ordem do navegador (seguir, trocar, mudar a tatica). Nada do placar e
decidido aqui; esta classe so segura o relogio.

Por que thread e nao gerador: a partida roda DENTRO de `Carreira.avancar`, que tambem joga
a rodada inteira, as copas, a energia e a diretoria. Transformar tudo isso em gerador
mexeria no motor inteiro para servir uma tela. A thread deixa o motor como esta.
"""

from __future__ import annotations

import threading

import numpy as np

from fm.carreira import MAX_TROCAS, Carreira
from fm.eventos import PESO_DO_BLOCO, rendimento_em_campo
from fm.tatica import Tatica

ESPERA_MAXIMA = 60.0   # segundos; se o motor nao responder nisso, algo quebrou


class PartidaAoVivo:
    def __init__(self, carreira: Carreira) -> None:
        self.c = carreira
        self.partida = None          # a Partida do motor, viva enquanto o jogo corre
        self.resultado = None        # (resultados, partida) quando a data termina
        self.erro: str | None = None
        self.compromisso = carreira.compromisso
        self.rodada = carreira.rodada + 1
        self.tatica = carreira.tatica_atual()
        self._pedido: dict | None = None
        self._ate_o_fim = False
        self._pronto = threading.Event()
        self._seguir = threading.Event()
        self._thread = threading.Thread(target=self._rodar, daemon=True)

    # ------------------------------------------------------------------ o relogio

    def comecar(self) -> None:
        self._thread.start()
        self._esperar()

    def seguir(self, trocas=None, tatica: dict | None = None, ate_o_fim: bool = False) -> None:
        if self.acabou:
            return
        self._pedido = {"trocas": [tuple(int(x) for x in t) for t in (trocas or [])]}
        if tatica:
            nova = Tatica(**{**self._tatica_dict(), **tatica})
            nova.validar()
            self._pedido["tatica"] = nova
            self.tatica = nova
        self._ate_o_fim = ate_o_fim
        self._pronto.clear()
        self._seguir.set()
        self._esperar()

    @property
    def acabou(self) -> bool:
        return self.resultado is not None or self.erro is not None

    def _esperar(self) -> None:
        if not self._pronto.wait(ESPERA_MAXIMA):
            self.erro = "o motor nao respondeu"

    def _rodar(self) -> None:
        try:
            self.resultado = self.c.avancar(substituicoes=self._no_fim_do_bloco)
            if self.resultado[1] is not None:
                self.partida = self.resultado[1]
        except Exception as e:           # a thread nao pode morrer calada
            self.erro = f"{type(e).__name__}: {e}"
        finally:
            self._pronto.set()

    def _no_fim_do_bloco(self, partida, minuto):
        """Chamada pelo motor. Publica o retrato e dorme ate o navegador mandar seguir."""
        self.partida = partida
        if self._ate_o_fim:
            return None
        self._seguir.clear()
        self._pronto.set()
        self._seguir.wait()
        pedido, self._pedido = self._pedido, None
        return pedido

    def _tatica_dict(self) -> dict:
        t = self.tatica
        return {"formacao": t.formacao, "marcacao": t.marcacao, "estilo": t.estilo}

    # ------------------------------------------------------------------ o retrato

    def retrato(self, clube_json) -> dict:
        """Tudo que a tela ao vivo desenha, ate o minuto em que o motor parou."""
        c, p = self.c, self.partida
        if self.erro:
            return {"erro": self.erro}
        if p is None:
            # a data passou sem jogo do usuario (copa em que ele ja caiu, ou folga)
            return {"sem_jogo": True, "fim": True}
        fim = self.resultado is not None
        minuto = 90 if fim else p.minuto
        meu_lado = "casa" if p.casa == c.clube_id else "fora"
        nomes = c.world.players

        def lado(clube: int) -> str:
            return "casa" if clube == p.casa else "fora"

        eventos = [{"minuto": e.minuto, "tipo": e.tipo, "lado": lado(e.clube),
                    "texto": e.texto, "jogador": e.jogador, "segundo": e.segundo}
                   for e in p.eventos if e.minuto <= minuto]
        amarelos = {e.jogador for e in p.eventos if e.tipo == "amarelo"}
        expulsos = {e.jogador for e in p.eventos if e.tipo == "vermelho"}
        sairam = {e.jogador for e in p.eventos if e.tipo == "substituicao"}

        def escalacao(clube: int, em_campo: list[int]) -> list[dict]:
            ids = [pid for pid in p.entrada if nomes[pid].club_id == clube]
            ordem = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
            fora = []
            for pid in sorted(ids, key=lambda i: (i not in em_campo,
                                                   ordem.get(nomes[i].position, 9))):
                j = nomes[pid]
                fora.append({
                    "id": pid, "nome": j.name, "posicao": j.position,
                    "overall": j.overall, "em_campo": pid in em_campo,
                    "energia": rendimento_em_campo(c.world, p, pid),
                    "amarelo": pid in amarelos, "expulso": pid in expulsos,
                    "saiu": pid in sairam, "entrou_aos": p.entrada[pid] or None,
                })
            return fora

        meus_em_campo = p.em_campo_casa if meu_lado == "casa" else p.em_campo_fora
        banco = [{"id": j.id, "nome": j.name, "posicao": j.position,
                  "overall": j.overall, "energia": j.condition}
                 for j in sorted(c.world.squad(c.clube_id), key=lambda x: -x.overall)
                 if j.id not in p.entrada][:12]
        feitas = sum(1 for e in p.eventos
                     if e.tipo == "substituicao" and e.clube == c.clube_id)
        sc, sf = p.stats_casa, p.stats_fora
        return {
            "fim": fim, "minuto": minuto,
            "tempo": "2º tempo" if minuto > 45 else "1º tempo",
            "intervalo": minuto == 45 and not fim,
            "casa": clube_json(p.casa), "fora": clube_json(p.fora),
            "gols_casa": sum(1 for e in eventos if e["tipo"] == "gol" and e["lado"] == "casa"),
            "gols_fora": sum(1 for e in eventos if e["tipo"] == "gol" and e["lado"] == "fora"),
            "meu_lado": meu_lado,
            "eventos": eventos,
            "estatisticas": [
                ["Posse de bola", f"{sc.posse}%", f"{sf.posse}%"],
                ["Finalizações", sc.finalizacoes, sf.finalizacoes],
                ["No gol", sc.no_gol, sf.no_gol],
                ["Escanteios", sc.escanteios, sf.escanteios],
                ["Faltas", sc.faltas, sf.faltas],
                ["Impedimentos", sc.impedimentos, sf.impedimentos],
                ["Desarmes", sc.desarmes, sf.desarmes],
                ["Passes errados", sc.passes_errados, sf.passes_errados],
                ["Cartões amarelos", sc.amarelos, sf.amarelos],
                ["Cartões vermelhos", sc.vermelhos, sf.vermelhos],
            ],
            "escalacao_casa": escalacao(p.casa, p.em_campo_casa),
            "escalacao_fora": escalacao(p.fora, p.em_campo_fora),
            "banco": banco,
            "em_campo": list(meus_em_campo),
            "trocas_feitas": feitas, "max_trocas": MAX_TROCAS,
            "tatica": self._tatica_dict(),
            "rodada": self._rodada_parcial(minuto, clube_json),
        }

    def _rodada_parcial(self, minuto: int, clube_json) -> list[dict]:
        """Os outros jogos da data, com o placar ATE este minuto.

        Os placares finais ja estao decididos pelo motor rapido, que nao tem minuto. O
        minuto de cada gol e sorteado aqui so para a tela, com a mesma curva do motor
        detalhado e semente fixa -- recarregar a pagina nao muda nada. E cosmetico: nenhuma
        regra le estes minutos.
        """
        c = self.c
        fora = []
        pesos = PESO_DO_BLOCO / PESO_DO_BLOCO.sum()
        largura = 90 // len(pesos)
        for r in c.parciais:
            rng = np.random.default_rng([c.seed, c.temporada, c.data, r.home, r.away])
            gols = sorted([("casa", int(b * largura + rng.integers(1, largura + 1)))
                           for b in rng.choice(len(pesos), r.goals_home, p=pesos)]
                          + [("fora", int(b * largura + rng.integers(1, largura + 1)))
                             for b in rng.choice(len(pesos), r.goals_away, p=pesos)],
                          key=lambda g: g[1])
            ate = [g for g in gols if g[1] <= minuto]
            fora.append({
                "casa": clube_json(r.home)["nome"], "fora": clube_json(r.away)["nome"],
                "gols_casa": sum(1 for g in ate if g[0] == "casa"),
                "gols_fora": sum(1 for g in ate if g[0] == "fora"),
                "mudou": bool(ate) and ate[-1][1] > minuto - 5,
            })
        return fora
