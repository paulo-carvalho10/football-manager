"""Importadores de conteudo.

SEPARACAO DELIBERADA: este pacote e a UNICA parte do projeto que toca a rede, e a unica
que depende de beautifulsoup/lxml. O motor em fm/ depende so de numpy. Jogo nao baixa
pagina -- importador baixa pagina, grava arquivo, e o jogo le arquivo.

Tres etapas separadas de proposito:
  1. baixar   -> le a rede, grava HTML/JSON cru em data/cache/. So esta etapa usa rede.
  2. extrair  -> le o cache, devolve registros. Roda offline, quantas vezes quiser.
  3. montar   -> aplica fm.ratings e escreve o pack .toml.
Assim se pode iterar na conversao de overall sem rebaixar nada.
"""
