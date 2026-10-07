"""Os paises: o nome de cada um como o jogo mostra, e de onde vem.

A nacionalidade do jogador e o NOME do pais em portugues do Brasil ("Uruguai",
"Tchéquia"). Ela vem de duas fontes:

- **jogador real** (pack): a bandeira do plantel no Transfermarkt. O site escreve em
  portugues de Portugal ("Polónia", "Perú", "Irão"); `nome_do_pais` traz para o do Brasil.
- **jogador gerado** (preenchimento de elenco, base): o pais da liga do clube, pelo codigo
  dela ("BRA" -> "Brasil").
"""

from __future__ import annotations

# o codigo do pais da liga (data/leagues/*.toml, campo `pais`) -> o nome
NOME_DO_PAIS = {
    "BRA": "Brasil", "ESP": "Espanha", "ENG": "Inglaterra", "ITA": "Itália",
    "GER": "Alemanha", "FRA": "França", "POR": "Portugal", "ARG": "Argentina",
    "COL": "Colômbia", "CHI": "Chile", "URU": "Uruguai", "ECU": "Equador",
    "PAR": "Paraguai", "PER": "Peru", "BOL": "Bolívia", "VEN": "Venezuela",
    "NED": "Holanda", "BEL": "Bélgica", "TUR": "Turquia", "GRE": "Grécia",
    "UKR": "Ucrânia", "RUS": "Rússia", "AUT": "Áustria", "SUI": "Suíça",
    "SCO": "Escócia", "DEN": "Dinamarca", "NOR": "Noruega", "SWE": "Suécia",
    "SRB": "Sérvia", "CRO": "Croácia", "POL": "Polônia", "CZE": "Tchéquia",
}

# Transfermarkt (pt-PT) -> pt-BR. So os que mudam.
_DO_SITE = {
    "Polónia": "Polônia", "Perú": "Peru", "Eslovénia": "Eslovênia", "Roménia": "Romênia",
    "Macedónia do Norte": "Macedônia do Norte", "Irão": "Irã", "Quénia": "Quênia",
    "Zimbabué": "Zimbábue", "Arménia": "Armênia", "Estónia": "Estônia", "Suiça": "Suíça",
    "Curacao": "Curaçao", "Benim": "Benin", "Guiné Bissau": "Guiné-Bissau",
    "República Checa": "Tchéquia", "Letónia": "Letônia", "Mónaco": "Mônaco",
    "Moçambique": "Moçambique", "Vietname": "Vietnã", "Azerbaijão": "Azerbaijão",
    "Bielorrússia": "Belarus", "Cazaquistão": "Cazaquistão", "Usbequistão": "Uzbequistão",
    "Ilhas Faroé": "Ilhas Faroe", "Singapura": "Singapura", "Tanzânia": "Tanzânia",
    "Ruanda": "Ruanda", "Burundi": "Burundi", "Madagáscar": "Madagascar",
}


def nome_do_pais(texto: str | None) -> str | None:
    """O nome do site no nome que o jogo usa."""
    if not texto:
        return None
    texto = texto.strip()
    return _DO_SITE.get(texto, texto)


def pais_da_liga(codigo: str) -> str:
    """A nacionalidade de quem nasce num clube da liga (o jogador gerado)."""
    return NOME_DO_PAIS.get(codigo, codigo)
