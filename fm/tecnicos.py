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
# ...e mais, se ele vem de temporada forte: o clube olha o momento, nao so o nome. Cada
# ponto que a reputacao subiu na ultima virada alarga a margem em MOMENTO (08/10/2026).
# Sem isto, quem fazia campanha acima do esperado levava 9 ou 10 anos para chegar a um
# gigante; o mediano (que nao sobe) continua com a margem de sempre.
MOMENTO = 1.5
MOMENTO_MAXIMO = 12.0           # o campeao surpresa chama a atencao dos grandes, mas nao
                                # salta do Bragantino direto para o Manchester United
# Depois de uma temporada forte (a reputacao subiu ao menos isto), um clube MAIOR cujo
# tecnico ficou abaixo do esperado pode demiti-lo para trazer o usuario -- o grande nao
# espera vaga para contratar quem esta em alta.
ALTA_PARA_ASSEDIO = 5.0
CONVITES_MOSTRADOS = 3          # demitido: ate 3 portas
CONVITES_EMPREGADO = 2          # empregado: no maximo 2 por virada, para nao virar spam
CHANCE_DO_MAIOR = 0.70          # clube maior que o meu chama quase sempre que cabe
CHANCE_DO_MENOR = 0.20          # o menor tambem pode chamar; cabe ao usuario ver se compensa
DESEMPREGADOS_INICIAIS = 10

# o que mexe na reputacao na virada
PESO_DO_DESEMPENHO = 16.0     # terminar N% da tabela acima do esperado vale 16*N/100
TITULO_DA_LIGA = {1: 6.0, 2: 3.0}
ACESSO = 4.0
REBAIXAMENTO = -6.0
DEMISSAO = -5.0
DEMISSAO_PEDIDA = -2.0        # sair por conta propria pega menos mal que ser mandado embora
TECNICO_DO_ANO = 3.0
# (08/10/2026) A campanha conta, nao so o titulo. Antes, ser vice com o 3o elenco do pais
# rendia +0,1 -- o esperado pela folha era isso mesmo -- e a reputacao do usuario passava
# a carreira entre 33 e 42, longe dos 60-70 que os clubes grandes pedem.
COLOCACAO_NA_ELITE = {2: 3.0, 3: 2.0, 4: 2.0}   # na primeira divisao, sem contar o titulo
QUARTO_DE_CIMA = 1.0                            # o resto do quarto de cima da tabela
FINALISTA = 0.4                                 # da copa: fracao do valor do titulo
SEMIFINALISTA = 0.2
TITULO_DE_COPA = {"libertadores": 8.0, "champions": 8.0, "sudamericana": 4.0,
                  "europa_league": 4.0, "copa_do_brasil": 4.0, "intercontinental": 3.0}
VOLTA_A_MEDIA = 0.06          # a reputacao escorrega devagar para o alvo sem resultado novo
# O alvo nao e 45 para todo mundo: e a media entre 45 e a reputacao do clube que o tecnico
# dirige. Fazer o trabalho direito num clube grande faz o tecnico grande, aos poucos; no
# pequeno, o teto e mais baixo. Desempregado volta para 45.
MEDIA_DO_TECNICO = 45.0
PESO_DO_CLUBE_NO_ALVO = 0.5
# A IA demite por chance, e a chance cresce com o quanto o clube ficou abaixo do esperado:
# nada ate TOLERANCIA_DA_IA, quase certo a partir de TOLERANCIA_DA_IA + FAIXA_DA_IA. Quem
# caiu sai sempre. O GRANDE cobra mais: um dos favoritos (esperado no topo) que fica fora do
# G-4 balanca mesmo sem afundar. (08/10/2026) Era regra fixa -- 35% da tabela abaixo do
# esperado, uns sete lugares --, e em oito anos Palmeiras e Flamengo nunca trocaram de
# tecnico: o usuario nunca via convite de clube grande.
TOLERANCIA_DA_IA = 0.05
FAIXA_DA_IA = 0.35
CHANCE_MAXIMA_DA_IA = 0.9
COBRANCA_DO_GRANDE = 0.15        # o favorito fora do G-4 conta como este tanto abaixo
FAVORITOS = 3


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


def alvo_da_reputacao(t: Tecnico, estatura: dict[int, float] | None) -> float:
    if t.clube is None or not estatura or t.clube not in estatura:
        return MEDIA_DO_TECNICO
    return ((1 - PESO_DO_CLUBE_NO_ALVO) * MEDIA_DO_TECNICO
            + PESO_DO_CLUBE_NO_ALVO * estatura[t.clube])


def pela_colocacao(d: Desempenho) -> float:
    """A colocacao na primeira divisao, alem do titulo (que tem o premio dele)."""
    if d.tier != 1 or d.campeao:
        return 0.0
    if d.final in COLOCACAO_NA_ELITE:
        return COLOCACAO_NA_ELITE[d.final]
    return QUARTO_DE_CIMA if d.final <= d.clubes / 4 else 0.0


def atualizar_reputacoes(tecnicos: dict[int, Tecnico], dados: dict[int, Desempenho],
                         copas: dict[int, list[str]], nomes_das_copas: dict[str, str],
                         nomes_das_ligas: dict[str, str], temporada: int,
                         estatura: dict[int, float] | None = None,
                         campanhas: dict[int, list[tuple[str, str]]] | None = None) -> None:
    """A virada da reputacao. `copas` = {clube: [copas que ganhou]}; `estatura` =
    {clube: reputacao}; `campanhas` = {clube: [(copa, "final" | "semi")]} de quem chegou
    longe sem ganhar."""
    for t in tecnicos.values():
        delta = (alvo_da_reputacao(t, estatura) - t.reputacao) * VOLTA_A_MEDIA
        d = dados.get(t.clube) if t.clube is not None else None
        if d is not None:
            delta += PESO_DO_DESEMPENHO * d.saldo
            if d.campeao:
                delta += TITULO_DA_LIGA.get(d.tier, 2.0)
                t.titulos.append(f"{temporada} · {nomes_das_ligas.get(d.liga, d.liga)}")
            delta += pela_colocacao(d)
            delta += ACESSO if d.subiu else 0.0
            delta += REBAIXAMENTO if d.caiu else 0.0
        for copa in copas.get(t.clube, []) if t.clube is not None else []:
            delta += TITULO_DE_COPA.get(copa, 3.0)
            t.titulos.append(f"{temporada} · {nomes_das_copas.get(copa, copa)}")
        for copa, ate in (campanhas or {}).get(t.clube, []) if t.clube is not None else []:
            delta += TITULO_DE_COPA.get(copa, 3.0) * (FINALISTA if ate == "final"
                                                       else SEMIFINALISTA)
        t.variacao = round(delta, 1)
        t.reputacao = float(np.clip(t.reputacao + delta, 1, 99))


def ajustar(t: Tecnico, delta: float) -> None:
    t.variacao = round(t.variacao + delta, 1)
    t.reputacao = float(np.clip(t.reputacao + delta, 1, 99))


def chance_de_demitir(d: Desempenho) -> float:
    if d.caiu:
        return 1.0
    pressao = -d.saldo
    if d.tier == 1 and d.esperado <= FAVORITOS and not d.campeao and d.final > 4:
        pressao += COBRANCA_DO_GRANDE
    return float(np.clip((pressao - TOLERANCIA_DA_IA) / FAIXA_DA_IA, 0.0, CHANCE_MAXIMA_DA_IA))


def demissoes_da_ia(tecnicos: dict[int, Tecnico], dados: dict[int, Desempenho],
                    rng: np.random.Generator | None = None) -> list[int]:
    """Os clubes do computador que trocam de tecnico. Devolve as vagas. Sem `rng`, so
    quem caiu ou tem chance maxima sai (o comportamento deterministico de teste)."""
    vagas = []
    for t in sorted(tecnicos.values(), key=lambda t: t.id):
        if t.usuario or t.clube is None or t.clube not in dados:
            continue
        chance = chance_de_demitir(dados[t.clube])
        sorteio = rng.random() if rng is not None else 1.0 - 1e-9
        if chance >= 1.0 or sorteio < chance:
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


def assediam(world: World, tecnicos: dict[int, Tecnico], dados: dict[int, Desempenho],
             clube_atual: int | None) -> list[int]:
    """Os clubes maiores que o do usuario, com tecnico da IA abaixo do esperado, que podem
    troca-lo pelo usuario em alta. Vazio se ele nao vem de temporada forte."""
    eu = tecnicos[USUARIO]
    if clube_atual is None or eu.variacao < ALTA_PARA_ASSEDIO:
        return []
    meu = world.clubs[clube_atual].reputation
    fora = []
    for t in tecnicos.values():
        if t.usuario or t.clube is None or t.clube not in dados:
            continue
        if world.clubs[t.clube].reputation > meu and dados[t.clube].saldo < 0:
            fora.append(t.clube)
    return fora


def margem_do_convite(t: Tecnico) -> float:
    return MARGEM_DO_CONVITE + min(MOMENTO * max(0.0, t.variacao), MOMENTO_MAXIMO)


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
                    and world.clubs[k].reputation <= eu.reputacao + margem_do_convite(eu)),
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
