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
4. **Nenhum ativo oficial.** Clubes e jogadores gerados; `test_nenhum_clube_gerado_colide_
   com_clube_real` confere contra uma blocklist de clubes reais.
5. **Avanco rodada por rodada**, nao temporada de uma vez -- e o que vai permitir parar na
   partida do usuario e simula-la em detalhe sem reescrever nada.

## Performance

2,7 milhoes de partidas por segundo no caminho rapido (uma temporada de 380 jogos sai em
~0,14 s). Orcamento declarado: **uma rodada mundial em menos de 1 segundo**, guardado por
`test_orcamento_de_performance`.

## Pendencias, em ordem

1. **Re-derivar os alvos com dados reais** das tabelas publicas. Hoje sao a ordem de
   grandeza, nao dado conferido. Suspeita conhecida: a taxa de empates do Brasileirao real
   parece ser mais alta (~28%) do que o `gols_base` sozinho produz (~26%).
2. **Separar ataque e defesa.** Hoje o clube tem um overall unico. Com dois lambdas
   independentes (`z_ataque_casa` contra `z_defesa_fora`) aparecem o 4-3 entre dois times
   ofensivos e o 0-0 entre dois defensivos -- variedade de estilo, nao so de forca.
3. **Motor detalhado por eventos** para a partida do usuario, calibrado contra o rapido
   (se as partidas do usuario tiverem media de gols diferente do resto do mundo, a tabela
   fica torta e o jogador sente).
4. **Carreira**: multiplas temporadas, piramide de divisoes, acesso e rebaixamento,
   envelhecimento, evolucao por potencial, regens, save/load.
5. **Financas com realimentacao.** Sem isso o carater da liga **decai**: depois de 30
   temporadas toda liga vira o mesmo mingau achatado e a Espanha deixa de ser a Espanha. O
   laco e reputacao -> receita -> folha -> elenco -> titulo -> reputacao. Teste de longo
   prazo a escrever: rodar 30 temporadas e conferir que o gap 1o-10o da Espanha nao caiu
   abaixo de 25.
6. **Mercado de transferencias** com IA de clube.
7. Interface. Por ultimo, de proposito.
