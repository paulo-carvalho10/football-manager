"""As selecoes: quem existe, quem e convocado e quanto cada uma vale.

Uma selecao e o pais da NACIONALIDADE dos jogadores (fm.paises), nao o da liga: a do
Brasil e feita de quem joga na Europa tanto quanto de quem joga aqui. Por isso a carreira
carrega o mundo inteiro como pano de fundo (fm.carreira, `_carregar_ligas_de_fora`).

Os jogadores continuam nos clubes deles. Para jogar, cada selecao vira um `Club` num
MUNDO PROPRIO (`mundo_das_selecoes`), que divide os jogadores com o mundo dos clubes: o
motor de partidas e o de copa (fm.eventos, fm.copa) servem sem saber que e selecao, e
nada que percorre `world.clubs` -- mercado, financas, energia -- ve selecao nenhuma.

So vira selecao o pais com elenco no mundo: pelo menos 18 jogadores e 2 goleiros. Com as
40 ligas do jogo sao ~66; a Asia e a Concacaf tem poucas porque as ligas de la nao estao
no jogo, e a Copa do Mundo da as vagas que sobrarem a quem tiver.
"""

from __future__ import annotations

from fm.model import Club, League, World

# As confederacoes e os paises de cada uma. A ORDEM e o id da selecao (`id_da_selecao`):
# so se acrescenta pais NO FIM da lista da confederacao, senao o id dos outros muda.
CONFEDERACOES: dict[str, tuple[str, ...]] = {
    "CONMEBOL": ("Brasil", "Argentina", "Uruguai", "Colômbia", "Chile", "Equador",
                 "Paraguai", "Peru", "Bolívia", "Venezuela"),
    "UEFA": ("Espanha", "França", "Alemanha", "Itália", "Inglaterra", "Portugal", "Holanda",
             "Bélgica", "Croácia", "Dinamarca", "Suíça", "Áustria", "Noruega", "Suécia",
             "Sérvia", "Polônia", "Ucrânia", "Tchéquia", "Turquia", "Grécia", "Escócia",
             "Rússia", "Bósnia-Herzegovina", "Irlanda", "Eslováquia", "Kosovo", "Islândia",
             "Eslovênia", "Albânia", "Finlândia", "País de Gales", "Hungria", "Montenegro",
             "Geórgia", "Romênia", "Bulgária", "Irlanda do Norte", "Israel",
             "Macedônia do Norte", "Belarus", "Chipre", "Armênia", "Estônia", "Luxemburgo",
             "Lituânia", "Letônia", "Azerbaijão", "Cazaquistão", "Moldávia", "Malta",
             "Ilhas Faroe", "Andorra", "Gibraltar", "San Marino", "Liechtenstein"),
    "CAF": ("Marrocos", "Senegal", "Nigéria", "Costa do Marfim", "Gana", "Camarões", "Mali",
            "RD do Congo", "Argélia", "Burkina Faso", "Gâmbia", "Guiné", "Guiné-Bissau",
            "Cabo Verde", "Angola", "Tunísia", "Congo", "Mauritânia", "Comores",
            "África do Sul", "Egito", "Togo", "Gabão", "Quênia", "Zâmbia", "Madagascar",
            "Benin", "Zimbábue", "Serra Leoa", "Uganda", "República Central Africana",
            "Moçambique", "Tanzânia", "Ruanda", "Burundi", "Libéria", "Sudão", "Líbia",
            "Namíbia", "Guiné Equatorial"),
    "AFC": ("Japão", "Austrália", "Coreia do Sul", "Arábia Saudita", "Irã", "Iraque",
            "Síria", "Palestina", "Indonésia", "China", "Emirados Árabes Unidos", "Catar",
            "Uzbequistão", "Jordânia", "Omã", "Bahrein", "Vietnã", "Tailândia", "Líbano",
            "Kuwait"),
    "CONCACAF": ("Estados Unidos", "México", "Canadá", "Panamá", "Costa Rica", "Jamaica",
                 "Honduras", "Haiti", "Curaçao", "Suriname", "Trinidad e Tobago",
                 "República Dominicana", "Martinica", "Guadalupe", "El Salvador",
                 "Guatemala", "Nicarágua", "Cuba"),
    "OFC": ("Nova Zelândia",),
}
# fora das competicoes desde 2022 (a FIFA e a UEFA suspenderam): existem, nao disputam
SUSPENSAS = frozenset({"Rússia", "Belarus"})

MINIMO_DE_JOGADORES = 18
MINIMO_DE_GOLEIROS = 2
# 26, como na Copa de 2022 e na de 2026: o elenco que a tela de convocacao monta
CONVOCADOS = 26
QUOTA = {"GK": 3, "DF": 9, "MF": 8, "FW": 6}
ID_BASE = 900_000           # muito acima de qualquer clube ou jogador


def confederacao(pais: str) -> str | None:
    return next((c for c, paises in CONFEDERACOES.items() if pais in paises), None)


def id_da_selecao(pais: str) -> int:
    for k, (_, paises) in enumerate(CONFEDERACOES.items()):
        if pais in paises:
            return ID_BASE + 1000 * k + paises.index(pais)
    raise KeyError(f"{pais!r} nao esta em nenhuma confederacao")


def pais_da_selecao(sid: int) -> str:
    k, i = divmod(sid - ID_BASE, 1000)
    return list(CONFEDERACOES.values())[k][i]


def e_selecao(cid: int) -> bool:
    return cid >= ID_BASE


def _por_pais(world: World) -> dict[str, list]:
    """Os jogadores de cada pais que estao num clube (o aposentado nao conta)."""
    fora: dict[str, list] = {}
    for p in world.players.values():
        if p.club_id in world.clubs and p.nationality:
            fora.setdefault(p.nationality, []).append(p)
    return fora


def existentes(world: World) -> list[str]:
    """Os paises com elenco para uma selecao, na ordem das confederacoes."""
    gente = _por_pais(world)
    return [pais for paises in CONFEDERACOES.values() for pais in paises
            if len(gente.get(pais, [])) >= MINIMO_DE_JOGADORES
            and sum(1 for p in gente[pais] if p.position == "GK") >= MINIMO_DE_GOLEIROS]


def convocar(world: World, pais: str, fora: set[int] | frozenset[int] = frozenset(),
             gente: list | None = None) -> list[int]:
    """A convocacao da IA: os melhores do pais por posicao, na quota (3 goleiros, 9
    defensores, 8 meias, 6 atacantes). Quem esta em `fora` (machucado) nao vai. Se uma
    posicao nao tem gente, a vaga vai ao melhor que sobrou."""
    candidatos = sorted((p for p in (gente if gente is not None
                                     else _por_pais(world).get(pais, []))
                         if p.id not in fora),
                        key=lambda p: (-p.overall, p.id))
    escolhidos: list[int] = []
    falta = dict(QUOTA)
    for p in candidatos:
        if falta.get(p.position, 0) > 0:
            falta[p.position] -= 1
            escolhidos.append(p.id)
    resto = [p.id for p in candidatos if p.id not in escolhidos]
    escolhidos += resto[:CONVOCADOS - len(escolhidos)]
    return escolhidos


def convocar_todas(world: World, fora: set[int] | frozenset[int] = frozenset()
                   ) -> dict[str, list[int]]:
    gente = _por_pais(world)
    return {pais: convocar(world, pais, fora, gente.get(pais, []))
            for pais in existentes(world)}


def _cores(pais: str) -> tuple[str, str]:
    from fm.telas import NACIONAIS
    for n in NACIONAIS:
        if n.get("nome") == pais and n.get("cores"):
            return n["cores"][0], n["cores"][1]
    return "#3a4a5c", "#ffffff"


def mundo_das_selecoes(world: World, convocacoes: dict[str, list[int]],
                       reputacao: dict[str, int] | None = None) -> World:
    """Um mundo em que cada selecao e um clube, com os jogadores do mundo dos clubes.

    Os `players` sao o MESMO dicionario: o cansaco e a lesao valem nos dois mundos. As
    selecoes ficam numa liga por confederacao, com o codigo da confederacao -- e assim
    que um torneio de selecoes diz de onde vem quem joga."""
    view = World(season_year=world.season_year, players=world.players)
    for conf, paises in CONFEDERACOES.items():
        liga = League(id=f"selecoes_{conf.lower()}", name=conf, country=conf, tier=1,
                      codigo=conf)
        for pais in paises:
            if pais not in convocacoes:
                continue
            sid = id_da_selecao(pais)
            primaria, secundaria = _cores(pais)
            # country = a confederacao: o sorteio de potes evita dois do mesmo "pais"
            # no grupo, e na Copa a regra e nao juntar duas da mesma confederacao
            clube = Club(id=sid, name=pais, country=conf, league_id=liga.id,
                         reputation=(reputacao or {}).get(pais, 50),
                         designed_strength=0.0, color_primary=primaria,
                         color_secondary=secundaria,
                         player_ids=list(convocacoes[pais]))
            view.clubs[sid] = clube
            liga.club_ids.append(sid)
        view.leagues[liga.id] = liga
    for clube in view.clubs.values():
        clube.designed_strength = forca(view, clube.id)
    return view


FORCA_SEM_ELENCO = 40.0


def forca(view: World, sid: int) -> float:
    """O overall do onze da selecao. A que ficou sem onze (o pais perdeu os jogadores no
    meio de uma eliminatoria) entra em campo com o que da: a forca minima."""
    clube = view.clubs.get(sid)
    if clube is None or len(clube.player_ids) < 11:
        return FORCA_SEM_ELENCO
    return view.team_rating(sid)


def ranking(view: World) -> list[str]:
    """As selecoes da mais forte para a mais fraca, pelo onze titular."""
    return [c.name for c in sorted(view.clubs.values(),
                                   key=lambda c: (-c.designed_strength, c.id))]
