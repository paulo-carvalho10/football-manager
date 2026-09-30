"""A moeda de cada pais, so para a tela.

O motor inteiro conta em EURO: e a moeda do Transfermarkt, de onde vem o valor de mercado,
e e nela que o futebol fecha transferencia entre paises. O dinheiro do CLUBE -- caixa,
receita, folha, salario, premio -- aparece na moeda do pais dele, como no balanco de
verdade: o Corinthians fatura em reais, o Arsenal em libras.

Cambio fixo. Oscilacao de cambio seria uma regra de jogo (o clube brasileiro que vende em
euro ganha quando o real cai), e regra de jogo nao se esconde na camada de exibicao.
"""

from __future__ import annotations

# codigo -> (simbolo, unidades da moeda por 1 euro)
MOEDAS: dict[str, tuple[str, float]] = {
    "EUR": ("€", 1.0),
    "BRL": ("R$", 6.2),
    "GBP": ("£", 0.85),
    "USD": ("US$", 1.08),
}

# O resto da America do Sul fecha contrato e balanco em dolar (a Argentina, com o peso
# desvalorizando todo mes, inclusive); a Europa fora da Inglaterra, em euro.
MOEDA_DO_PAIS = {
    "BRA": "BRL", "ENG": "GBP",
    "ARG": "USD", "URU": "USD", "PAR": "USD", "CHI": "USD", "COL": "USD", "PER": "USD",
    "ECU": "USD", "BOL": "USD", "VEN": "USD",
}


def moeda_do_pais(pais: str | None) -> str:
    return MOEDA_DO_PAIS.get(pais or "", "EUR")


def do_euro(valor: float, moeda: str) -> int:
    """Euros do motor -> moeda do clube."""
    return int(round(valor * MOEDAS[moeda][1]))


def para_euro(valor: float, moeda: str) -> int:
    """Moeda do clube (o que o usuario digitou) -> euros do motor."""
    return int(round(valor / MOEDAS[moeda][1]))


def json_da_moeda(pais: str | None) -> dict:
    codigo = moeda_do_pais(pais)
    simbolo, taxa = MOEDAS[codigo]
    return {"codigo": codigo, "simbolo": simbolo, "taxa": taxa}


def texto(valor: float, moeda: str = "EUR") -> str:
    """Para as mensagens do servidor: `valor` em euros, escrito na moeda pedida."""
    simbolo = MOEDAS[moeda][0]
    v = abs(valor * MOEDAS[moeda][1])
    sinal = "−" if valor < 0 else ""
    if v >= 1e9:
        corpo = f"{v / 1e9:.2f} bi".replace(".", ",")
    elif v >= 1e6:
        corpo = f"{v / 1e6:.1f} mi".replace(".", ",")
    elif v >= 1e3:
        corpo = f"{round(v / 1e3)} mil"
    else:
        corpo = f"{round(v)}"
    return f"{sinal}{simbolo} {corpo}"
