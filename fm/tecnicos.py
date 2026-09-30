"""Os tecnicos do mundo: reputacao, ranking, demissao e vaga.

Cada clube das ligas da carreira tem um tecnico, e o usuario e um deles (id 0). A
reputacao anda na virada do ano pelo que o tecnico FEZ COM O QUE TINHA: terminar acima do
que a folha do elenco prometia sobe, abaixo desce. Titulo, acesso e rebaixamento pesam por
cima. Por isso o tecnico de um clube pequeno que briga la em cima sobe mais que o do rico
que so cumpriu a obrigacao.

A reputacao e o que abre portas: os clubes chamam tecnicos do tamanho deles (ate
MARGEM_DO_CONVITE abaixo da propria reputacao). Clube do computador que foi mal demite na
virada; a vaga vira convite para o usuario, se ele couber, e o resto e preenchido pelos
desempregados.

Tudo deterministico: tecnicos gerados por fluxo nomeado, reputacao por conta. A unica
escolha e do usuario (aceitar um convite), e ela vai para o save como acao.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fm.model import World
from fm.names import FIRST_NAMES, SURNAMES

USUARIO = 0
# o tecnico novo comeca baixo; um clube grande que o contrata empresta um pouco do nome
REPUTACAO_INICIAL_DO_USUARIO = 30.0
PESO_DO_PRIMEIRO_CLUBE = 0.15
MARGEM_DO_CONVITE = 12        # o clube aceita tecnico ate 12 pontos abaixo da reputacao dele
CONVITES_MOSTRADOS = 3          # demitido: ate 3 portas
CONVITES_EMPREGADO = 2          # empregado: no maximo 2 por virada, para nao virar spam
CHANCE_DO_MAIOR = 0.70          # clube maior que o meu chama quase sempre que cabe
CHANCE_DO_MENOR = 0.20          # o menor tambem pode chamar; cabe ao usuario ver se compensa
DESEMPREGADOS_INICIAIS = 10

# o que mexe na reputacao na virada
PESO_DO_DESEMPENHO = 14.0     # terminar N% da tabela acima do esperado vale 14*N/100
TITULO_DA_LIGA = {1: 6.0, 2: 3.0}
ACESSO = 4.0
REBAIXAMENTO = -6.0
DEMISSAO = -5.0
TECNICO_DO_ANO = 3.0
TITULO_DE_COPA = {"libertadores": 8.0, "champions": 8.0, "sudamericana": 4.0,
                  "europa_league": 4.0, "copa_do_brasil": 4.0, "intercontinental": 3.0}
VOLTA_A_MEDIA = 0.04          # a reputacao escorrega devagar para 45 sem resultado novo
# a IA demite quem caiu ou terminou este tanto da tabela abaixo do esperado
TOLERANCIA_DA_IA = 0.35


@dataclass(slots=True)
class Tecnico:
    id: int
    nome: str
    nascimento: int
    reputacao: float
    clube: int | None
    usuario: bool = False
    titulos: list[str] = field(default_factory=list)
    passagens: list[list] = field(default_factory=list)   # [temporada, nome do clube]
    variacao: float = 0.0                                 # a da ultima virada

    def idade(self, temporada: int) -> int:
        return temporada - self.nascimento


def _nome(rng: np.random.Generator, pais: str) -> str:
    primeiros = FIRST_NAMES.get(pais) or FIRST_NAMES["BRA"]
    sobrenomes = SURNAMES.get(pais) or SURNAMES["BRA"]
    return f"{rng.choice(primeiros)} {rng.choice(sobrenomes)}"


def _novo(tid: int, rng: np.random.Generator, pais: str, temporada: int,
          reputacao: float, clube: int | None) -> Tecnico:
    return Tecnico(id=tid, nome=_nome(rng, pais), nascimento=temporada - int(rng.integers(36, 66)),
                   reputacao=float(np.clip(reputacao, 5, 95)), clube=clube)


def gerar(world: World, ligas: set[str], rng: np.random.Generator, temporada: int,
          clube_usuario: int, nome_usuario: str) -> dict[int, Tecnico]:
    """Um tecnico por clube das ligas da carreira, mais alguns desempregados."""
    tecnicos = {USUARIO: Tecnico(id=USUARIO, nome=nome_usuario, nascimento=temporada - 40,
                                 reputacao=REPUTACAO_INICIAL_DO_USUARIO
                                 + PESO_DO_PRIMEIRO_CLUBE * world.clubs[clube_usuario].reputation,
                                 clube=clube_usuario,
                                 usuario=True,
                                 passagens=[[temporada, world.clubs[clube_usuario].name]])}
    proximo = 1
    for clube in sorted(world.clubs.values(), key=lambda k: k.id):
        if clube.league_id not in ligas or clube.id == clube_usuario:
            continue
        rep = clube.reputation * 0.75 + 12 + rng.normal(0, 7)
        t = _novo(proximo, rng, clube.country, temporada, rep, clube.id)
        t.passagens.append([temporada, clube.name])
        tecnicos[proximo] = t
        proximo += 1
    pais = world.clubs[clube_usuario].country
    for _ in range(DESEMPREGADOS_INICIAIS):
        tecnicos[proximo] = _novo(proximo, rng, pais, temporada, rng.uniform(15, 55), None)
        proximo += 1
    return tecnicos


def do_clube(tecnicos: dict[int, Tecnico], clube: int) -> Tecnico | None:
    return next((t for t in tecnicos.values() if t.clube == clube), None)


def ranking(tecnicos: dict[int, Tecnico]) -> list[Tecnico]:
    return sorted(tecnicos.values(), key=lambda t: (-t.reputacao, t.id))


# ---------------------------------------------------------------- a virada do ano

@dataclass(slots=True)
class Desempenho:
    clube: int
    liga: str
    tier: int
    esperado: int        # posicao pela folha do elenco no comeco do ano
    final: int
    clubes: int
    campeao: bool = False
    subiu: bool = False
    caiu: bool = False

    @property
    def saldo(self) -> float:
        """Quanto da tabela acima (+) ou abaixo (-) do esperado, de -1 a 1."""
        return (self.esperado - self.final) / max(self.clubes - 1, 1)


def desempenho(tabelas: dict[str, list], tiers: dict[str, int],
               valores: dict[int, int]) -> dict[int, Desempenho]:
    """O esperado e a ordem do valor de elenco do INICIO do ano: e o que a diretoria e a
    imprensa sabiam antes de a bola rolar."""
    fora = {}
    for liga, tabela in tabelas.items():
        ids = [ln.club_id for ln in tabela]
        pela_folha = sorted(ids, key=lambda k: (-valores.get(k, 0), k))
        for final, k in enumerate(ids, 1):
            fora[k] = Desempenho(clube=k, liga=liga, tier=tiers.get(liga, 1),
                                 esperado=pela_folha.index(k) + 1, final=final,
                                 clubes=len(ids), campeao=final == 1)
    return fora


def atualizar_reputacoes(tecnicos: dict[int, Tecnico], dados: dict[int, Desempenho],
                         copas: dict[int, list[str]], nomes_das_copas: dict[str, str],
                         nomes_das_ligas: dict[str, str], temporada: int) -> None:
    """A virada da reputacao. `copas` = {clube: [copas que ganhou]}."""
    for t in tecnicos.values():
        delta = (45.0 - t.reputacao) * VOLTA_A_MEDIA
        d = dados.get(t.clube) if t.clube is not None else None
        if d is not None:
            delta += PESO_DO_DESEMPENHO * d.saldo
            if d.campeao:
                delta += TITULO_DA_LIGA.get(d.tier, 2.0)
                t.titulos.append(f"{temporada} · {nomes_das_ligas.get(d.liga, d.liga)}")
            delta += ACESSO if d.subiu else 0.0
            delta += REBAIXAMENTO if d.caiu else 0.0
        for copa in copas.get(t.clube, []) if t.clube is not None else []:
            delta += TITULO_DE_COPA.get(copa, 3.0)
            t.titulos.append(f"{temporada} · {nomes_das_copas.get(copa, copa)}")
        t.variacao = round(delta, 1)
        t.reputacao = float(np.clip(t.reputacao + delta, 1, 99))


def ajustar(t: Tecnico, delta: float) -> None:
    t.variacao = round(t.variacao + delta, 1)
    t.reputacao = float(np.clip(t.reputacao + delta, 1, 99))


def demissoes_da_ia(tecnicos: dict[int, Tecnico], dados: dict[int, Desempenho]) -> list[int]:
    """Os clubes do computador que trocam de tecnico. Devolve as vagas."""
    vagas = []
    for t in sorted(tecnicos.values(), key=lambda t: t.id):
        if t.usuario or t.clube is None or t.clube not in dados:
            continue
        d = dados[t.clube]
        if d.caiu or -d.saldo >= TOLERANCIA_DA_IA:
            vagas.append(t.clube)
            t.clube = None
    return vagas


def preencher_vagas(world: World, tecnicos: dict[int, Tecnico], vagas: list[int],
                    streams, temporada: int) -> list[tuple[int, int]]:
    """O clube mais tradicional escolhe primeiro: o melhor desempregado que ele aceita
    (ate MARGEM_DO_CONVITE abaixo dele). Sem ninguem, sobe um tecnico novo."""
    feitas = []
    for clube in sorted(set(vagas), key=lambda k: (-world.clubs[k].reputation, k)):
        if do_clube(tecnicos, clube) is not None:
            continue
        rep = world.clubs[clube].reputation
        livres = [t for t in tecnicos.values() if t.clube is None and not t.usuario
                  and t.reputacao >= rep - MARGEM_DO_CONVITE - 10]
        if livres:
            escolhido = max(livres, key=lambda t: (t.reputacao, -t.id))
        else:
            rng = streams.get("tecnico_novo", temporada, clube)
            tid = max(tecnicos) + 1
            escolhido = _novo(tid, rng, world.clubs[clube].country, temporada,
                              rep * 0.6 + 10, None)
            tecnicos[tid] = escolhido
        escolhido.clube = clube
        escolhido.passagens.append([temporada, world.clubs[clube].name])
        feitas.append((clube, escolhido.id))
    return feitas


def convites(world: World, tecnicos: dict[int, Tecnico], candidatos: list[int],
             clube_atual: int | None, precisa: bool, reserva: list[int],
             rng: np.random.Generator) -> list[int]:
    """Os clubes que chamam o usuario.

    `candidatos`: clubes com vaga (ou em crise, no meio do ano), que so chamam se a
    reputacao do usuario couber. Demitido (`precisa`), todos os que cabem chamam, ate
    CONVITES_MOSTRADOS, e se ninguem couber o menor clube de `reserva` chama mesmo assim
    -- a carreira nao acaba por falta de porta. Empregado, clube maior chama quase
    sempre e menor de vez em quando, ate CONVITES_EMPREGADO: e o usuario que decide se
    descer compensa.
    """
    eu = tecnicos[USUARIO]
    atual = world.clubs[clube_atual].reputation if clube_atual in world.clubs else -1
    cabem = sorted((k for k in set(candidatos) if k != clube_atual
                    and world.clubs[k].reputation <= eu.reputacao + MARGEM_DO_CONVITE),
                   key=lambda k: (-world.clubs[k].reputation, k))
    if precisa:
        fora = cabem[:CONVITES_MOSTRADOS]
        if not fora:
            sobra = [k for k in reserva if k != clube_atual]
            if sobra:
                fora = [min(sobra, key=lambda k: (world.clubs[k].reputation, k))]
        return fora
    fora = []
    for k in cabem:                     # um sorteio por clube, na mesma ordem sempre
        chance = CHANCE_DO_MAIOR if world.clubs[k].reputation > atual else CHANCE_DO_MENOR
        if rng.random() < chance:
            fora.append(k)
    return fora[:CONVITES_EMPREGADO]
