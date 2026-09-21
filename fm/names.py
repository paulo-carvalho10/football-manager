"""Bancos de nomes ficticios.

Regra de licenciamento do projeto: o motor NUNCA depende de ativo oficial. Clubes e
jogadores sao gerados. Pacote com nome real, se um dia existir, e' mod de terceiro,
carregado de fora e nunca hospedado aqui. tests/test_licensing.py guarda essa regra.
"""

from __future__ import annotations

FIRST_NAMES = {
    "BRA": [
        "Adriano", "Alisson", "Anderson", "Bruno", "Caio", "Carlos", "Cleber", "Danilo",
        "Diego", "Douglas", "Eder", "Eduardo", "Emerson", "Everton", "Fabio", "Felipe",
        "Fernando", "Gabriel", "Geraldo", "Gilberto", "Gustavo", "Heitor", "Henrique",
        "Igor", "Ivan", "Joao", "Jonas", "Jorge", "Juliano", "Kaique", "Leandro", "Lucas",
        "Luiz", "Marcelo", "Marcos", "Mateus", "Mauricio", "Murilo", "Nelson", "Otavio",
        "Pedro", "Rafael", "Renan", "Ricardo", "Roberto", "Rodrigo", "Ronaldo", "Samuel",
        "Sergio", "Thiago", "Tomas", "Vinicius", "Vitor", "Wagner", "Wesley", "Yuri",
    ],
    "ESP": [
        "Adrian", "Alberto", "Alejandro", "Alvaro", "Andres", "Antonio", "Borja", "Carlos",
        "Cesar", "Daniel", "David", "Diego", "Eduardo", "Enrique", "Fernando", "Francisco",
        "Gonzalo", "Guillermo", "Hector", "Hugo", "Ignacio", "Inigo", "Isaac", "Ivan",
        "Jaime", "Javier", "Jesus", "Joaquin", "Jorge", "Jose", "Juan", "Julen", "Julio",
        "Lucas", "Luis", "Manuel", "Marcos", "Mario", "Martin", "Miguel", "Nicolas",
        "Oscar", "Pablo", "Pedro", "Rafael", "Raul", "Ricardo", "Roberto", "Rodrigo",
        "Ruben", "Samuel", "Santiago", "Sergio", "Tomas", "Victor", "Xabi",
    ],
}

SURNAMES = {
    "BRA": [
        "Alencar", "Almeida", "Alves", "Andrade", "Aragao", "Azevedo", "Barbosa", "Barros",
        "Batista", "Bezerra", "Braga", "Camargo", "Cardoso", "Carvalho", "Castro",
        "Cavalcanti", "Coelho", "Correia", "Costa", "Cunha", "Dantas", "Duarte", "Esteves",
        "Farias", "Ferreira", "Fonseca", "Freitas", "Furtado", "Galvao", "Gomes",
        "Guimaraes", "Leite", "Lima", "Lopes", "Macedo", "Machado", "Maia", "Marinho",
        "Medeiros", "Mendes", "Moraes", "Moreira", "Nogueira", "Nunes", "Oliveira",
        "Pacheco", "Peixoto", "Pereira", "Pinheiro", "Queiroz", "Ramalho", "Rezende",
        "Ribeiro", "Rocha", "Sampaio", "Siqueira", "Tavares", "Teixeira", "Vasconcelos",
        "Xavier",
    ],
    "ESP": [
        "Aguirre", "Alonso", "Arrieta", "Bermejo", "Blanco", "Cabrera", "Calderon",
        "Campos", "Carmona", "Carrasco", "Cortes", "Delgado", "Duran", "Escobar",
        "Esteban", "Fuentes", "Gallardo", "Garrido", "Gil", "Granados", "Herrera",
        "Higuera", "Ibarra", "Iglesias", "Jimeno", "Lorenzo", "Lozano", "Maldonado",
        "Marquez", "Medina", "Mendoza", "Merino", "Molina", "Montero", "Navarro", "Olmedo",
        "Ortega", "Pardo", "Pastor", "Quintana", "Reyes", "Rivas", "Robledo", "Roldan",
        "Salazar", "Sandoval", "Segura", "Sierra", "Solano", "Tejada", "Ubeda", "Valdes",
        "Vargas", "Vega", "Velasco", "Ventura", "Zamora",
    ],
}

# Toponimos inventados + sufixo. Distintos de proposito: o teste de licenciamento
# confere que nada aqui colide com nome de clube real.
CLUB_ROOTS = {
    "BRA": [
        "Itapere", "Carangua", "Marfim", "Serrado", "Araticum", "Jurumirim", "Taquaral",
        "Mangueiral", "Cachoeirao", "Paranapua", "Itanhanga", "Corumbiara", "Tucunare",
        "Jatoba", "Pindaiba", "Ubata", "Guaracema", "Piraquira", "Sobradao", "Aracatu",
        "Tapajara", "Muritiba", "Camboriu", "Itaguacu",
    ],
    "ESP": [
        "Valdealba", "Montecruz", "Penaflor", "Riosanto", "Castilnuevo", "Vallehermoso",
        "Puertonegro", "Altamar", "Sierradoro", "Campoverde", "Torrellana", "Miravalles",
        "Sanlucas", "Penarroja", "Olivares", "Fuenteclara", "Navalcruz", "Montelirio",
        "Arenalonga", "Costanegra", "Ribadoro", "Sotoverde", "Encinar", "Lagunilla",
    ],
}

CLUB_PATTERNS = {
    "BRA": ["{r} FC", "{r} Esporte Clube", "Atletico {r}", "{r} AA", "Uniao {r}", "{r} SC"],
    "ESP": ["CD {r}", "{r} CF", "UD {r}", "Atletico {r}", "Racing {r}", "{r} CD"],
}

# Guarda de licenciamento: nenhum nome gerado pode cair nesta lista.
REAL_CLUBS_BLOCKLIST = {
    "flamengo", "palmeiras", "corinthians", "sao paulo", "santos", "gremio",
    "internacional", "cruzeiro", "atletico mineiro", "botafogo", "vasco da gama",
    "fluminense", "bahia", "sport", "ceara", "fortaleza", "goias", "coritiba",
    "athletico paranaense", "chapecoense", "juventude", "america mineiro", "vitoria",
    "ponte preta", "guarani", "parana", "figueirense", "avai", "nautico", "remo",
    "paysandu", "criciuma", "vila nova", "atletico goianiense", "cuiaba", "bragantino",
    "real madrid", "barcelona", "atletico madrid", "sevilla", "valencia", "villarreal",
    "real sociedad", "athletic club", "real betis", "celta de vigo", "espanyol",
    "getafe", "osasuna", "rayo vallecano", "mallorca", "girona", "alaves", "cadiz",
    "granada", "levante", "elche", "almeria", "las palmas", "deportivo la coruna",
    "zaragoza", "sporting gijon", "racing santander", "malaga", "eibar", "leganes",
    "valladolid", "huesca", "tenerife", "oviedo", "albacete", "burgos", "cartagena",
}
