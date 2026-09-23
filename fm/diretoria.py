"""Aprovacao da torcida, aprovacao da diretoria e o risco de ser demitido.

E a peca que transforma a tabela em pressao. Sem ela, terminar em 3o e em 18o dava
exatamente no mesmo: o jogo seguia igual, o dinheiro entrava igual, ninguem reclamava.

As duas aprovacoes existem separadas porque olham para coisas diferentes, e e' justamente
a distancia entre elas que produz as situacoes boas: o time que ganha jogando feio tem
diretoria tranquila e torcida irritada; o que gasta demais para ganhar tem torcida
eufórica e diretoria preocupada.

- A TORCIDA e' emocional e de memoria curta. Ela pesa a sequencia recente, a posicao e
  estar vivo nas copas. Nao sabe e nao quer saber do caixa.
- A DIRETORIA e' fria e de memoria longa. Pesa a posicao contra a META que ela mesma
  definiu, a campanha nas copas e o USO DO DINHEIRO. Uma sequencia ruim quase nao a move.

Quem demite e' a diretoria. A torcida entra na conta dela, porque estadio vazio e protesto
tambem sao problema de quem administra -- mas com peso menor que o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fm.model import World

# --- meta ------------------------------------------------------------------
# A diretoria nao espera o titulo de quem e' o decimo elenco: ela espera perto do que a
# forca do clube indica, com uma folga. A folga e o que impede uma campanha mediana de um
# clube mediano de virar demissao.
FOLGA_DA_META = 0.12          # fracao da tabela, para baixo do posto por forca
FOLGA_MINIMA = 2              # em posicoes

# --- torcida ---------------------------------------------------------------
PESO_SEQUENCIA = 0.42         # os ultimos jogos, que e' do que ela fala
PESO_POSICAO_TORCIDA = 0.38
PESO_COPA_TORCIDA = 0.20
JOGOS_DE_MEMORIA = 6          # a memoria curta, em jogos

# --- diretoria -------------------------------------------------------------
PESO_POSICAO_DIRETORIA = 0.46
PESO_DINHEIRO = 0.26
PESO_COPA_DIRETORIA = 0.18
PESO_TORCIDA_NA_DIRETORIA = 0.10

# Quanto a aprovacao anda por avaliacao. Baixo de proposito: aprovacao que pula de 80 para
# 20 num jogo nao e' pressao, e' ruido -- e o usuario nao consegue reagir a ela.
INERCIA_TORCIDA = 0.22
INERCIA_DIRETORIA = 0.12

# --- demissao --------------------------------------------------------------
DEMISSAO_NO_ANO = 25.0        # abaixo disto, a diretoria nao espera o fim da temporada
DEMISSAO_NO_FIM = 45.0        # no balanco do ano a régua e' mais alta -- mas so vale
                              # para quem NAO cumpriu a meta, entao nao pune campanha boa
RODADAS_DE_CARENCIA = 8       # ninguem e' demitido antes de a temporada tomar forma


@dataclass(slots=True)
class Meta:
    """O que a diretoria cobra nesta temporada."""
    posicao: int
    texto: str


@dataclass(slots=True)
class Aprovacao:
    torcida: float = 60.0
    diretoria: float = 60.0
    meta: Meta | None = None
    demitido: bool = False
    motivo: str = ""
    historico: list[tuple[int, float, float]] = field(default_factory=list)

    @property
    def clima(self) -> str:
        """Uma linha que o lobby mostra sem precisar de numero."""
        pior = min(self.torcida, self.diretoria)
        if pior < 25:
            return "insustentavel"
        if pior < 40:
            return "pressionado"
        if pior < 60:
            return "sob observacao"
        if min(self.torcida, self.diretoria) < 80:
            return "tranquilo"
        return "idolatrado"


def definir_meta(world: World, clube_id: int, clubes_da_liga: list[int],
                 tier: int = 1) -> Meta:
    """Onde a diretoria espera terminar, pela forca do elenco.

    E' contra ESTE numero que a temporada e' julgada. Cobrar titulo de todo mundo faria o
    jogo demitir o usuario de um clube pequeno por ser pequeno.
    """
    ordem = sorted(clubes_da_liga, key=lambda c: -world.team_rating(c))
    n = len(ordem)
    posto = (ordem.index(clube_id) + 1) if clube_id in ordem else n
    folga = max(FOLGA_MINIMA, int(n * FOLGA_DA_META))
    alvo = min(n, posto + folga)

    if alvo <= 1:
        texto = "ser campeao"
    elif alvo <= max(4, n // 5):
        texto = f"terminar entre os {alvo} primeiros"
    elif alvo <= n // 2:
        texto = f"ficar na primeira metade (ate {alvo}o)"
    elif tier > 1:
        texto = f"nao brigar contra a queda (ate {alvo}o)"
    else:
        texto = f"escapar do rebaixamento (ate {alvo}o)"
    return Meta(posicao=alvo, texto=texto)


def _nota_da_posicao(posicao: int, meta: int, clubes: int) -> float:
    """0 a 100 pela posicao, com 50 exatamente em cima da meta.

    Bater a meta por uma posicao vale pouco; ficar dez atras dela vale muito pouco. A
    escala e linear dos dois lados da meta, mas com inclinacoes diferentes -- superar
    expectativa empolga menos do que frustra-la irrita.
    """
    if posicao <= meta:
        acima = (meta - posicao) / max(1, meta - 1)
        return 50 + 50 * acima
    atras = (posicao - meta) / max(1, clubes - meta)
    return max(0.0, 50 - 62 * atras)


def _nota_da_sequencia(ultimos: list[str]) -> float:
    """V/E/D dos ultimos jogos. Sem jogos, neutro."""
    if not ultimos:
        return 50.0
    pontos = sum({"V": 3, "E": 1}.get(r, 0) for r in ultimos)
    return 100.0 * pontos / (3 * len(ultimos))


def _nota_das_copas(campanhas: list[tuple[int, int, bool]], titulos: int = 0) -> float:
    """Ate ONDE o clube foi em cada copa, nao se foi eliminado.

    Contar eliminacoes deprimia a torcida de todo mundo: em qualquer copa 31 dos 32 clubes
    sao eliminados, entao a nota ficava baixa no fim de toda temporada e um time que
    cumpriu a meta na liga terminava o ano com 36% de aprovacao.

    Cada campanha entra como (etapas sobrevividas, etapas totais, ainda vivo). Chegar a
    semifinal e uma boa campanha, mesmo tendo acabado em eliminacao.
    """
    if titulos:
        return 100.0
    if not campanhas:
        return 50.0
    notas = []
    for vividas, totais, vivo in campanhas:
        avanco = (vividas / totais) if totais else 0.0
        nota = 25.0 + 70.0 * avanco
        if vivo:
            nota += 15.0            # ainda sonhando vale mais que ja saber o fim
        notas.append(min(100.0, nota))
    return max(0.0, min(100.0, sum(notas) / len(notas)))


def _nota_do_dinheiro(saldo: int, receita: int, caixa: int, folha: int) -> float:
    """Uso do dinheiro do clube, do ponto de vista de quem responde por ele.

    Nao e' "juntar dinheiro": um clube que fatura bem e nao investe tambem incomoda. O que
    a diretoria cobra e' nao gastar o que nao tem -- folha acima da receita e caixa
    negativo sao os dois pecados.
    """
    nota = 50.0
    if receita > 0:
        nota += 34.0 * max(-1.0, min(1.0, saldo / receita))
    if folha > 0 and receita > 0:
        excesso = folha / receita
        if excesso > 0.75:
            nota -= 40.0 * min(1.0, (excesso - 0.75) / 0.5)
        else:
            # folha folgada tambem conta a favor, nao so a apertada conta contra
            nota += 12.0 * (0.75 - excesso) / 0.75
    if folha > 0:
        # caixa medido em meses de folha: o que a diretoria olha e a reserva, nao o numero
        meses = caixa / (folha / 12)
        nota += 10.0 * max(-3.0, min(1.0, meses / 6))
    return max(0.0, min(100.0, nota))


def avaliar(aprovacao: Aprovacao, *, posicao: int, clubes: int,
            ultimos: list[str], campanhas: list[tuple[int, int, bool]] | None = None,
            titulos: int = 0, saldo: int = 0, receita: int = 0,
            caixa: int = 0, folha: int = 0) -> Aprovacao:
    """Move as duas aprovacoes em direcao ao que a temporada esta dizendo."""
    meta = aprovacao.meta.posicao if aprovacao.meta else max(1, clubes // 2)
    n_pos = _nota_da_posicao(posicao, meta, clubes)
    n_seq = _nota_da_sequencia(ultimos)
    n_copa = _nota_das_copas(campanhas or [], titulos)
    n_din = _nota_do_dinheiro(saldo, receita, caixa, folha)

    alvo_torcida = (PESO_SEQUENCIA * n_seq + PESO_POSICAO_TORCIDA * n_pos
                    + PESO_COPA_TORCIDA * n_copa)
    alvo_diretoria = (PESO_POSICAO_DIRETORIA * n_pos + PESO_DINHEIRO * n_din
                      + PESO_COPA_DIRETORIA * n_copa
                      + PESO_TORCIDA_NA_DIRETORIA * aprovacao.torcida)

    aprovacao.torcida += (alvo_torcida - aprovacao.torcida) * INERCIA_TORCIDA
    aprovacao.diretoria += (alvo_diretoria - aprovacao.diretoria) * INERCIA_DIRETORIA
    aprovacao.torcida = max(0.0, min(100.0, aprovacao.torcida))
    aprovacao.diretoria = max(0.0, min(100.0, aprovacao.diretoria))
    return aprovacao


def decidir_demissao(aprovacao: Aprovacao, *, rodada: int, fim_da_temporada: bool,
                     posicao: int, clubes: int, rebaixado: bool = False) -> str | None:
    """Devolve o motivo da demissao, ou None se o emprego esta mantido.

    Duas reguas: durante a temporada a diretoria so age no desespero, no fim do ano ela
    cobra a meta. Rebaixamento demite sozinho -- nao ha aprovacao que sobreviva a ele.
    """
    if aprovacao.demitido:
        return aprovacao.motivo
    if rebaixado:
        return "rebaixamento"
    if fim_da_temporada:
        meta = aprovacao.meta.posicao if aprovacao.meta else clubes // 2
        if posicao <= meta:
            # META CUMPRIDA PROTEGE O EMPREGO. Sem isto, um tecnico que entregou o que foi
            # pedido era demitido por uma aprovacao baixa herdada de um comeco ruim -- o
            # que quer dizer que a meta nao significava nada.
            return (None if aprovacao.diretoria > DEMISSAO_NO_ANO
                    else "nem cumprir a meta segurou a situacao")
        if aprovacao.diretoria < DEMISSAO_NO_FIM:
            return f"a meta era {meta}o lugar e o time terminou em {posicao}o"
        return None
    if rodada >= RODADAS_DE_CARENCIA and aprovacao.diretoria < DEMISSAO_NO_ANO:
        return f"sequencia insustentavel: {posicao}o lugar na rodada {rodada}"
    return None
