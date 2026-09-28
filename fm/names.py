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
    # 28/09/2026: os seis paises da versao completa. Nomes comuns de cada lingua, para os
    # garotos que sobem da base -- um ingles da base nao pode sair chamado Kaique.
    "ENG": [
        "Adam", "Alfie", "Ben", "Callum", "Charlie", "Connor", "Dan", "Ethan", "Finley",
        "George", "Harry", "Harvey", "Jack", "Jacob", "Jake", "James", "Joe", "Jordan",
        "Josh", "Kieran", "Leo", "Lewis", "Liam", "Luke", "Mason", "Max", "Nathan",
        "Oliver", "Owen", "Reece", "Ryan", "Sam", "Scott", "Tom", "Tyler", "Will",
    ],
    "ITA": [
        "Alessandro", "Andrea", "Antonio", "Christian", "Daniele", "Davide", "Emanuele",
        "Fabio", "Federico", "Filippo", "Francesco", "Gabriele", "Giacomo", "Gianluca",
        "Giorgio", "Giovanni", "Giuseppe", "Leonardo", "Lorenzo", "Luca", "Manuel",
        "Marco", "Matteo", "Mattia", "Michele", "Nicolo", "Paolo", "Pietro", "Riccardo",
        "Roberto", "Samuele", "Simone", "Stefano", "Tommaso", "Valerio",
    ],
    "GER": [
        "Alexander", "Andreas", "Benedikt", "Christian", "Daniel", "David", "Dominik",
        "Elias", "Felix", "Finn", "Florian", "Jan", "Jannik", "Jonas", "Julian", "Kai",
        "Leon", "Lukas", "Marcel", "Marco", "Mats", "Maximilian", "Moritz", "Niklas",
        "Nico", "Pascal", "Patrick", "Philipp", "Robin", "Sebastian", "Stefan", "Timo",
        "Tobias", "Yannick",
    ],
    "FRA": [
        "Adrien", "Alexandre", "Antoine", "Arthur", "Baptiste", "Benjamin", "Clement",
        "Corentin", "Damien", "Enzo", "Florian", "Hugo", "Jordan", "Julien", "Kevin",
        "Lucas", "Maxime", "Mathis", "Nathan", "Nicolas", "Pierre", "Quentin", "Raphael",
        "Romain", "Theo", "Thomas", "Valentin", "Yanis", "Yoann",
    ],
    "POR": [
        "Afonso", "Andre", "Bernardo", "Bruno", "Diogo", "Duarte", "Fabio", "Francisco",
        "Goncalo", "Guilherme", "Joao", "Jorge", "Jose", "Leonardo", "Luis", "Manuel",
        "Martim", "Miguel", "Nuno", "Paulo", "Pedro", "Rafael", "Ricardo", "Rodrigo",
        "Rui", "Salvador", "Simao", "Tiago", "Tomas", "Vasco", "Vitor",
    ],
    "ARG": [
        "Agustin", "Alan", "Alexis", "Ariel", "Axel", "Bautista", "Braian", "Cristian",
        "Damian", "Diego", "Emiliano", "Enzo", "Esteban", "Ezequiel", "Facundo", "Franco",
        "Gaston", "Gonzalo", "Ignacio", "Joaquin", "Juan", "Julian", "Leandro", "Lautaro",
        "Lucas", "Marcos", "Matias", "Maximiliano", "Nahuel", "Nicolas", "Pablo",
        "Ramiro", "Santiago", "Thiago", "Tomas",
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
    "ENG": [
        "Barnes", "Bennett", "Brooks", "Carter", "Clarke", "Cole", "Cooper", "Davies",
        "Edwards", "Evans", "Fisher", "Foster", "Gray", "Green", "Hall", "Harris",
        "Hughes", "Hunt", "Jackson", "Johnson", "Kelly", "King", "Lewis", "Marshall",
        "Mitchell", "Moore", "Morgan", "Parker", "Phillips", "Price", "Reed", "Robinson",
        "Shaw", "Stevens", "Taylor", "Turner", "Walker", "Ward", "Webb", "Wright",
    ],
    "ITA": [
        "Barbieri", "Bellini", "Bernardi", "Bianchi", "Bruno", "Caputo", "Colombo",
        "Conti", "Costa", "D'Angelo", "De Luca", "Esposito", "Fabbri", "Ferrara",
        "Ferrari", "Fontana", "Gallo", "Greco", "Leone", "Lombardi", "Mancini", "Marino",
        "Martini", "Moretti", "Pellegrini", "Rinaldi", "Rizzo", "Romano", "Russo",
        "Santoro", "Serra", "Testa", "Valentini", "Villa", "Vitale",
    ],
    "GER": [
        "Bauer", "Becker", "Braun", "Busch", "Fischer", "Frank", "Hahn", "Hartmann",
        "Hoffmann", "Huber", "Jung", "Kaiser", "Keller", "Klein", "Koch", "Kraus",
        "Lang", "Lehmann", "Maier", "Meyer", "Muller", "Neumann", "Richter", "Roth",
        "Schafer", "Schmidt", "Schneider", "Schulz", "Schwarz", "Vogel", "Wagner",
        "Weber", "Werner", "Wolf", "Zimmermann",
    ],
    "FRA": [
        "Bernard", "Bertrand", "Blanc", "Bonnet", "Chevalier", "David", "Dubois",
        "Dupont", "Durand", "Fontaine", "Fournier", "Garnier", "Girard", "Guerin",
        "Lambert", "Laurent", "Lefebvre", "Leroy", "Martin", "Mercier", "Michel",
        "Moreau", "Morel", "Perrin", "Petit", "Renaud", "Richard", "Robert", "Roux",
        "Simon", "Thomas", "Vincent",
    ],
    "POR": [
        "Almeida", "Antunes", "Barbosa", "Brito", "Carvalho", "Coelho", "Correia",
        "Costa", "Cruz", "Dias", "Fernandes", "Ferreira", "Gomes", "Goncalves", "Henriques",
        "Lopes", "Machado", "Marques", "Martins", "Mendes", "Monteiro", "Moreira", "Neves",
        "Nunes", "Pereira", "Pinto", "Ramos", "Ribeiro", "Rocha", "Santos", "Silva",
        "Sousa", "Teixeira", "Vieira",
    ],
    "ARG": [
        "Acosta", "Aguero", "Alvarez", "Benitez", "Cabral", "Castro", "Diaz", "Dominguez",
        "Fernandez", "Figueroa", "Flores", "Gimenez", "Gomez", "Gonzalez", "Herrera",
        "Juarez", "Ledesma", "Lopez", "Medina", "Molina", "Morales", "Ojeda", "Ortiz",
        "Paez", "Peralta", "Ponce", "Quiroga", "Ramirez", "Rios", "Romero", "Ruiz",
        "Sosa", "Suarez", "Torres", "Vazquez",
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

# No Brasil uma boa parte dos atletas e conhecida por um nome so. Sem isso, todo elenco
# gerado fica com cara de lista telefonica.
NICKNAMES = {
    "BRA": [
        "Alemao", "Baiano", "Betinho", "Bolinha", "Cacau", "Caju", "Cebolinha", "Ceara",
        "Dede", "Didi", "Dodo", "Edinho", "Fabinho", "Gabi", "Gerson", "Giba", "Grafite",
        "Guga", "Jadson", "Jean", "Juninho", "Kaka", "Kleber", "Leo", "Lico", "Lulinha",
        "Mancha", "Marquinhos", "Matheuzinho", "Nenem", "Neto", "Nino", "Paulinho",
        "Pedrinho", "Pepe", "Piriquito", "Rafinha", "Reinaldo", "Renatinho", "Rominho",
        "Ronaldinho", "Sandrinho", "Serginho", "Souza", "Tati", "Tiquinho", "Vitinho",
        "Wendel", "Zeca", "Zezinho",
    ],
}
