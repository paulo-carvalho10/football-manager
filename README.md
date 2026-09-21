# football-manager

Motor de simulacao de futebol para um jogo de carreira. Local primeiro, sem online, sem
interface grafica e sem versao paga: primeiro o mundo precisa ser **crivel**.

    # uma temporada completa do Brasil
    python -m fm.cli temporada --liga brasil --seed 42

    # o portao de qualidade: 2000 temporadas contra alvos de futebol real
    python -m fm.cli calibrar --temporadas 2000

    # prova que o carater da liga vem do DADO, nao do motor
    python -m fm.cli perfis

    # liga x copa: o gigante ganha menos copa que liga
    python -m fm.cli copa --liga copa_brasil

    # um elenco gerado
    python -m fm.cli elenco --liga espanha --posicao 1

Ambiente: `uv venv --python 3.12` e `uv pip install numpy pytest ruff`.
Testes: `python -m pytest`. Lint: `ruff check .`

## A pergunta que decide o projeto

Nao e se a interface esta bonita. E se a **tabela final e crivel**. Por isso o portao de
calibracao (`fm/calibration.py`) e a peca central: ele roda milhares de temporadas e
compara onze metricas com intervalos de futebol real. Quebrar um alvo e build vermelho.

Medido em 760 mil partidas, liga de referencia de 20 clubes em returno duplo:

| metrica | medido | alvo |
|---|---|---|
| gols por jogo | 2,60 | 2,55 - 2,80 |
| 0-0 | 7,5% | 6,5 - 9,5% |
| casa / empate / fora | 46,1 / 24,7 / 29,2 | 43-47 / 23-27 / 28-31 |
| margem 3+ | 14,3% | 11,5 - 15,5% |
| margem 4+ | 4,8% | 3,5 - 6,0% |
| pontos do campeao | 76,1 | 74 - 81 |
| pontos do lanterna | 28,8 | 22 - 31 |
| melhor elenco e campeao | 34,6% | 33 - 46% |

Aquela ultima linha e a alma do genero. Se o melhor elenco e campeao em 90% das
temporadas, o jogo e uma planilha. Se e em 10%, e um dado.

**AVISO HONESTO:** os intervalos vieram da ordem de grandeza conhecida das grandes ligas,
nao de um dataset conferido. Antes de congelar, puxar as tabelas reais (sao publicas e
pequenas) e re-derivar. E o primeiro item da lista de pendencias.

## O motor

```
z = (ovr_efetivo - 68) / 20
d = tanh((z_casa - z_fora) / 1.20)          <- saturacao
lambda_casa = gols_base * exp(+0.58*d + mando/2)
lambda_fora = gols_base * exp(-0.58*d - mando/2)
gols ~ Poisson(lambda)
```

Tres decisoes valem explicacao:

**A saturacao (`tanh`) e o que impede o 9-0.** Sem ela, um gap de 26 pontos de overall
gera 22% de partidas com 3+ de margem, contra ~14% real. O `tanh` reproduz o que acontece
de verdade: time goleando administra o resultado, time perdendo se fecha. Efeito colateral
util: o lado fraco nunca cai abaixo de ~0,60 gol esperado, entao **em 82 x 56 o pequeno
ainda vence 9,3% das vezes e o jogo ainda termina 0-0 em 5%**.

**Nao existe ruido anonimo.** A versao com mistura Gamma (Negative Binomial) foi testada e
o otimizador empurrou a dispersao para zero: ela nao era necessaria e era justamente o que
gerava goleada demais. Toda a variancia de uma partida vem de causa com **nome** --
desgaste, moral, forma, classico, mando. O jogador entende "meu time estava morto, jogou
quarta e domingo"; ele nao entende "o multiplicador aleatorio deu 0,6".

**Desgaste em pontos de overall, com teto.** `condition` cai com minutos e sobe com
descanso; o onze perde `(100-condition)/60 * 8` pontos de overall, no maximo 8. Como o
motor usa a **diferenca** de forca, desgaste igual nos dois lados se cancela exatamente --
ele so mexe no jogo quando e assimetrico. Medido: desgaste maximo leva a derrota do
favorito (78 x 64) de 14,3% para 19,0%. O jogador sente e planeja rotacao, mas nunca vira
sorteio.

## O carater da liga e CONTEUDO, nao codigo

Nao existe `if country == "BRA"` em nenhum lugar. Brasil e Espanha rodam com as mesmas
constantes de motor; o que muda e a **distribuicao de overall dos clubes**, declarada no
arquivo da liga. Saida de `python -m fm.cli perfis`:

| liga | campeao | lanterna | empate% | gols | margem3+ | maior clube e campeao |
|---|---|---|---|---|---|---|
| brasil (linear 77..59) | 73,3 | 31,4 | 25,8% | 2,46 | 12,7% | 24,2% |
| espanha (88, 86, 82 + 75..53) | 82,3 | 27,8 | 23,8% | 2,65 | 15,7% | 41,2% |

Os seis tracos que distinguem as duas ligas -- equilibrio, empates, pontuacao do campeao,
gap entre topo e meio, previsibilidade dos confrontos desiguais, concentracao de titulos
-- **emergem do dado**. `tests/test_world.py::test_carater_da_liga_vem_do_dado` guarda essa
propriedade.

Por-liga, so dois numeros de estilo existem, e ambos tem justificativa:

- `gols_base` -- o Brasileirao e mais travado que as ligas inglesas.
- `mando` -- distancias continentais do Brasil: quem voa 3.000 km chega pior (0,36 contra
  0,28 da Espanha).

## Data packs: de onde vem o conteudo

O mundo tem duas fontes possiveis, e o motor e identico nas duas:

| fonte | como | usado quando |
|---|---|---|
| **pack** (`data/packs/*.toml`) | `pack = "brasil"` no arquivo da liga | nomes reais de clube |
| **geracao** | bloco `[forca]` no arquivo da liga | mundo ficticio proprio |

Um pack traz nome, forca e -- opcionalmente -- a escalacao nominal do clube. O que faltar
para fechar 24 jogadores e gerado em volta da forca declarada, entao um pack pode ser
preenchido aos poucos. O formato esta em `data/packs/_exemplo_escalacao.toml`.

`pack_offset` fatia o pack por forca, e e assim que a piramide sai sem uma linha de codigo
novo: `pack_offset = 0` da a Serie A, `pack_offset = 20` da a Serie B do mesmo arquivo.
`test_divisoes_nao_compartilham_clube` garante que as fatias sao disjuntas.

**Os packs deste repo sao estimativa editorial escrita de memoria, marcada
`verificado = false`.** Composicao de divisao muda todo ano e os valores de forca sao
opiniao. `test_pack_nao_verificado_esta_declarado_como_tal` impede que um pack nao
conferido se passe por dado conferido.

## Alvos por liga

Aplicar os alvos da liga de referencia a toda liga e **erro**. O Brasileirao tem mando mais
forte (logo menos vitoria fora), mais empate e campeao com menos pontos -- por motivos
reais, nao por bug. Cada liga declara o que e realista para ela num bloco `[alvos]`; o que
nao declarar cai na referencia. `test_cada_liga_passa_nos_seus_proprios_alvos` cobra todas.

O caso mais bonito e a Serie B: mesmos parametros de motor, elencos quase equivalentes, e o
resultado e campeao com 68 pontos e **o melhor elenco do papel sendo campeao em apenas
14% das temporadas**. A Serie B ser maluca nao foi programado -- e consequencia de a liga
ser achatada.

| liga | campeao | lanterna | empate% | gols | margem3+ | maior clube e campeao |
|---|---|---|---|---|---|---|
| Serie A | 73,5 | 32,6 | 25,6% | 2,52 | 13,3% | 33,8% |
| Serie B | 68,5 | 35,3 | 26,8% | 2,37 | 11,4% | 14,1% |
| La Liga | 79,2 | 30,4 | 24,7% | 2,61 | 14,5% | 41,7% |


## Base real: Serie A do Brasil

    python -m fm.cli temporada   --liga brasil_real
    python -m fm.cli diagnostico --pack brasil_serie_a
    python -m fm.cli calibrar    --liga brasil_real --usar-perfil-da-liga

20 clubes, 669 jogadores reais. Nada disso e digitado a mao: `fm/importer/` baixa 41
paginas (1 da liga + 20 elencos + 20 de desempenho), cacheia tudo em `data/cache/` e gera
`data/packs/brasil_serie_a.toml`.

Fontes: Transfermarkt (clube, posicao, idade, valor de mercado, jogos e minutos) e CBF
(`Codigo_Clube`, composicao oficial da divisao).

O importador tem tres etapas separadas de proposito -- **baixar**, **extrair**, **montar**.
So a primeira usa rede. Assim da para reajustar uma constante de conversao e rodar de novo
sobre o cache sem baixar nada. Regra de arquitetura, guardada por
`test_motor_nao_depende_do_importador`: **o jogo nao baixa pagina**. `fm/` depende so de
numpy; beautifulsoup e lxml vivem em `fm/importer/`.

## De valor de mercado a overall

Nao existe fonte aberta de overall. Existe de valor de mercado -- e overall da para
derivar, de forma explicavel, em `fm/ratings.py`:

```
1. valor_qualidade = valor / ( K_POS[posicao] x A(idade)^W )
2. z   = padroniza ln(valor_qualidade) DENTRO do elenco, limitado a +-2,4
3. POT = forca_clube + 5,0 x z
4. OVR = POT - teto_crescimento(idade) x (1 - 0,8 x min(1, partidas/20))
5. desloca tudo para a media do melhor onze cair no forca_clube
```

O principio: **o valor da a hierarquia, o forca do clube da o nivel.** Valor diz bem quem e
melhor que quem e diz mal "isto e um 82", porque o Brasileirao e globalmente mais barato
que a Europa. O forca vem do valor TOTAL do elenco, com dois parametros por liga ajustados
contra os `[alvos]`.

Tres coisas que so apareceram medindo:

**O premio de posicao nao e enfeite.** O mercado paga por goleiro cerca de metade do que
paga por um meia de qualidade equivalente. Sem `K_POS`, o goleiro titular sai 5 pontos
abaixo do resto do onze; com ele, a diferenca media na liga real e **+0,5**.

**Dividir pelo multiplicador de idade inteiro estoura a escala.** O mercado desconta
veterano por dois motivos -- pouca carreira restante (nao e falta de qualidade hoje) e
declinio real (e). Devolvendo tudo, um jogador de 33 anos valendo 10 milhoes virava OVR 94.
Dai `W = 0,5` e um teto de 2x.

**O desconto de imaturidade estava forte demais.** Com peso 0,6, o jogador mais valioso da
Serie A (21 anos, 38 milhoes, temporada inteira jogada) ficava no BANCO do proprio clube.
Quem ja e titular entregou qualidade; com 0,8, os dez mais caros da liga sao todos
titulares.

## Diagnosticos: o que separa constante ajustada de constante bonita

`python -m fm.cli diagnostico` mede cinco coisas sobre a base real:

| diagnostico | medido | faixa |
|---|---|---|
| goleiro titular vs titulares de linha | +0,5 | -1,5 a 1,5 |
| dos 10 mais caros, quantos sao titulares | 10 | 9 a 10 |
| idade media dos titulares | 28,1 | 26,5 a 29,5 |
| idade media dos 50 melhores overalls | 27,9 | 26 a 30 |
| desvio-padrao de overall da liga | 10,5 | 8 a 13 |

**Um diagnostico ruim custou caro e vale registrar.** A primeira versao olhava a media de
overall por faixa de idade e acusava o modelo de favorecer veterano, porque a media subia
ate os 30-32 anos. Era **composicao de elenco**: clube dispensa veterano ruim e segura
garoto ruim, entao sobram 75 jogadores de 18-20 anos (quase todos da base, sem valor) e so
37 acima de 36. A media por idade mede quem o clube guarda, nao quem o modelo valoriza. O
diagnostico honesto e a idade de QUEM JOGA.

## O dado real tambem corrigiu o motor

A formacao padrao era 4-4-2. Os elencos reais tem cerca de **9 atacantes e pontas por
clube** contra 2 vagas -- e o jogador mais caro da liga ficava fora do onze. Era a formacao
errada, nao o calculo. O padrao agora e 4-3-3.

## Mata-mata

Competicao e uma lista de fases (`round_robin`, `knockout`, `groups`) descrita em arquivo.
Copa recebe `[mentalidade]` com `gols_mult = 0.90` e `compressao = 0.20`: o "todo jogo vale
a vida" deixa o jogo travado (gols 2,54 -> 2,29; 0-0 7,8% -> 10,1%) e comprime o gap,
porque o pequeno se fecha.

Medido em copa de 16 clubes, ida e volta, 30 mil edicoes com o perfil brasileiro:

| | maior clube leva | top-3 leva |
|---|---|---|
| mentalidade normal | 18,3% | 47,7% |
| mentalidade copa | 15,8% | 41,8% |

E o ponto importante: **a imprevisibilidade da copa nao usa aleatoriedade extra**. Em 38
jogos o melhor elenco regride para a media e aparece no topo; em 4 duelos, nao da tempo.
E por isso que copa e a competicao da esperanca e liga e a competicao do dinheiro.

## Regras de arquitetura (com teste que guarda cada uma)

1. **O motor nao faz I/O.** Nenhum `print` nem `input` dentro de `fm/`, exceto `fm/cli.py`.
   Guardado por `test_motor_nao_faz_io`.
2. **Determinismo por seed, em fluxos nomeados.** Nada cria RNG por conta propria: tudo
   pede um fluxo a `fm.rng.Streams`. Adicionar lesoes amanha nao desloca as partidas de
   hoje. Guardado por `test_fluxos_nomeados_sao_independentes`.
3. **Regra de competicao vem de arquivo**, nunca de `if` espalhado pelo codigo.
4. **Conteudo vem de pack externo, e o motor roda sem nenhum pack.** Clubes e jogadores
   podem vir de `data/packs/*.toml` (nomes reais) ou ser gerados (mundo ficticio). Trocar
   um pelo outro e editar uma linha do arquivo da liga. Guardado por
   `test_motor_roda_sem_pack` -- e o que mantem a porta do licenciamento aberta.
5. **Avanco rodada por rodada**, nao temporada de uma vez -- e o que vai permitir parar na
   partida do usuario e simula-la em detalhe sem reescrever nada.

## Performance

2,7 milhoes de partidas por segundo no caminho rapido (uma temporada de 380 jogos sai em
~0,14 s). Orcamento declarado: **uma rodada mundial em menos de 1 segundo**, guardado por
`test_orcamento_de_performance`.

## Pendencias, em ordem

1. **Conferir os packs e re-derivar os alvos com dados reais.** Composicao das divisoes,
   forca dos clubes e faixas dos alvos sao todos estimativa de memoria hoje
   (`verificado = false`). Sao dados publicos e pequenos.
2. **Escalacoes reais.** O formato ja aceita (`[[clubes.jogadores]]`), mas os elencos nao
   estao preenchidos: jogadores sao gerados a partir de bancos de nomes e apelidos
   brasileiros e espanhois, nao sao atletas reais. Preencher exige uma fonte de dados --
   digitada ou importada.
3. **Dinamica de colapso.** Falta espiral de moral, elenco desmontado no meio da temporada
   e lesao acumulada -- e o que faz clube rebaixado real terminar com 16-21 pontos. Sem
   isso, o lanterna simulado fica na casa dos 30 e o alvo esta alargado com essa
   justificativa escrita no arquivo. Re-apertar depois do M4/M5.
4. **Separar ataque e defesa.** Hoje o clube tem um overall unico. Com dois lambdas
   independentes (`z_ataque_casa` contra `z_defesa_fora`) aparecem o 4-3 entre dois times
   ofensivos e o 0-0 entre dois defensivos -- variedade de estilo, nao so de forca.
5. **Motor detalhado por eventos** para a partida do usuario, calibrado contra o rapido
   (se as partidas do usuario tiverem media de gols diferente do resto do mundo, a tabela
   fica torta e o jogador sente).
6. **Carreira**: multiplas temporadas, piramide de divisoes, acesso e rebaixamento,
   envelhecimento, evolucao por potencial, regens, save/load.
7. **Financas com realimentacao.** Sem isso o carater da liga **decai**: depois de 30
   temporadas toda liga vira o mesmo mingau achatado e a Espanha deixa de ser a Espanha. O
   laco e reputacao -> receita -> folha -> elenco -> titulo -> reputacao. Teste de longo
   prazo a escrever: rodar 30 temporadas e conferir que o gap 1o-10o da Espanha nao caiu
   abaixo de 25.
8. **Mercado de transferencias** com IA de clube.
9. Interface. Por ultimo, de proposito.
