"""Lista curada de ligas nacionais a importar.

Por que curada e nao por corte de valor: o catalogo tem 789 competicoes e mistura copa,
estadual, base, reserva e turno isolado com liga nacional. Filtro por nome deixou passar
duas copas. Escolher os PAISES e depois pegar a 1a e a 2a divisao nacional de cada um e o
unico jeito de nao importar lixo.
"""

from __future__ import annotations

from fm.importer.catalogo import Competicao, deduplicar_turnos, e_liga_nacional

# (pais no catalogo, quantas divisoes). Asia so a primeira, como combinado.
PAISES = [
    # Europa -- as cinco grandes com duas divisoes
    ("Inglaterra", 2), ("Espanha", 2), ("Itália", 2), ("Alemanha", 2), ("França", 2),
    ("Portugal", 2), ("Holanda", 2), ("Bélgica", 2), ("Turquia", 2), ("Escócia", 2),
    ("Áustria", 2), ("Suiça", 2), ("Grécia", 2), ("Rússia", 2), ("Ucrânia", 1),
    ("Dinamarca", 2), ("Noruega", 2), ("Suécia", 2), ("Polônia", 2), ("Chéquia", 2),
    ("Croácia", 1), ("Sérvia", 1),
    # America
    # Brasil nao entra por valor: as quatro divisoes vem por codigo em CODIGOS_FIXOS,
    # senao o catalogo devolve campeonato estadual como se fosse divisao nacional.
    ("Brasil", 0),
    ("Argentina", 2), ("México", 2), ("Estados Unidos", 2), ("Colômbia", 2),
    ("Chile", 1), ("Uruguai", 1), ("Paraguai", 1), ("Equador", 1),
    # Peru nao aparece no catalogo do Transfermarkt por continente; fica de fora.
    # Asia -- so a primeira divisao
    ("Arábia Saudita", 1), ("Japão", 1), ("Coreia do Sul", 1), ("China", 1),
    ("Emirados Árabes Unidos", 1), ("Catar", 1),
    # Africa
    ("Egito", 1), ("África do Sul", 1), ("Marrocos", 1),
]

# Divisoes que entram por codigo, quando o catalogo nao as classifica direito.
# A Serie C e D do Brasil aparecem como nivel 3 e 4 e escapariam da regra.
CODIGOS_FIXOS = ("BRA1", "BRA2", "BRA3", "BRA4")


def escolher(todas: list[Competicao]) -> list[Competicao]:
    """Para cada pais, as N ligas nacionais de maior valor. Sem copa, sem estadual."""
    limpas = deduplicar_turnos([c for c in todas if c.clubes >= 8 and e_liga_nacional(c)])
    por_pais: dict[str, list[Competicao]] = {}
    for c in limpas:
        por_pais.setdefault(c.pais, []).append(c)

    escolhidas: dict[str, Competicao] = {}
    for pais, quantas in PAISES:
        candidatas = sorted(por_pais.get(pais, []), key=lambda x: -x.valor_total)
        for c in candidatas[:quantas]:
            escolhidas[c.codigo] = c
    for c in todas:
        if c.codigo in CODIGOS_FIXOS:
            escolhidas[c.codigo] = c
    return sorted(escolhidas.values(), key=lambda x: -x.valor_total)
