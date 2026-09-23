"use strict";
/* A casca do jogo no navegador.
 *
 * Nenhuma regra mora aqui: este arquivo pede estado ao servidor, desenha, e manda de volta
 * o que o usuario clicou. E a mesma divisao do terminal -- por isso as duas interfaces
 * convivem sem duplicar uma linha de logica de jogo. */

/* ------------------------------------------------------------------ rede */

const api = {
  async get(rota) {
    const r = await fetch(rota);
    if (!r.ok) throw new Error(`${rota}: ${r.status}`);
    return r.json();
  },
  async post(rota, corpo = {}) {
    const r = await fetch(rota, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(corpo),
    });
    if (!r.ok) throw new Error(`${rota}: ${r.status}`);
    return r.json();
  },
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let ESTADO = null;
let telaAtual = "inicio";
let ligaVisivel = null;
let marcado = null;                       // titular clicado, esperando um reserva
let ordem = {coluna: "overall", desc: true};

/* ------------------------------------------------------------------ formato */

function dinheiro(v) {
  const n = Math.abs(v ?? 0);
  if (n >= 1e6) return `${((v ?? 0) / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${Math.round((v ?? 0) / 1e3)}k`;
  return String(v ?? 0);
}

function reais(v) {
  return `R$ ${(v ?? 0).toLocaleString("pt-BR")}`;
}

function corDe(valor, bom = 80, medio = 60) {
  if (valor >= bom) return "var(--verde)";
  if (valor >= medio) return "var(--amarelo)";
  return "var(--vermelho)";
}

function moral(n) {
  if (n >= 80) return "Ótima";
  if (n >= 65) return "Boa";
  if (n >= 50) return "Normal";
  if (n >= 35) return "Baixa";
  return "Péssima";
}

function barra(valor, cor) {
  return `<span class="barra"><i style="width:${valor}%;background:${cor}"></i></span>`;
}

function escapar(t) {
  return String(t ?? "").replace(/[&<>"]/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}

/* ------------------------------------------------------------------ camisas */

const cacheDeCamisas = new Map();
async function camisa(clubeId, numero = "1") {
  const chave = `${clubeId}-${numero}`;
  if (!cacheDeCamisas.has(chave)) {
    const r = await fetch(`/api/camisa/${clubeId}/${numero}`);
    cacheDeCamisas.set(chave, await r.text());
  }
  return cacheDeCamisas.get(chave);
}

/** Onze camisas na mesma pagina com os mesmos ids fariam todas usarem o recorte da
 *  primeira, e a cor de um jogador vazaria nos outros. */
let contador = 0;
function idsProprios(svg) {
  const s = `u${contador++}`;
  return svg.replace(/id="([\w-]+)"/g, `id="$1${s}"`)
            .replace(/url\(#([\w-]+)\)/g, `url(#$1${s})`)
            .replace(/href="#([\w-]+)"/g, `href="#$1${s}"`);
}

/* ------------------------------------------------------------------ topo */

/** A cor do clube vira ACENTO, e acento precisa se ver sobre o fundo escuro.
 *  O Santos e o Corinthians sao pretos: usados crus, o tema simplesmente sumia. */
function corDeAcento(hex) {
  const n = parseInt((hex || "#1b6b45").slice(1), 16);
  let [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const luz = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  if (luz >= 0.32) return hex;
  const f = luz < 0.05 ? 3.4 : 0.34 / Math.max(luz, 0.02);
  const clarear = (v) => Math.round(Math.min(255, Math.max(v * f, v + 60)));
  return `rgb(${clarear(r)}, ${clarear(g)}, ${clarear(b)})`;
}

function desenharTopo(e) {
  document.documentElement.style.setProperty("--clube", corDeAcento(e.clube.cor));
  $("#escudo").style.background =
    `linear-gradient(135deg, ${e.clube.cor} 55%, ${e.clube.cor2} 55%)`;
  $("#nome-do-clube").textContent = e.clube.nome;
  $("#linha-clube").textContent = `${e.liga} · rodada ${e.rodada} de ${e.total_de_rodadas}`;
  $("#treinador").textContent = e.treinador;
  $("#temporada").textContent = e.temporada;
  $("#caixa").textContent = reais(e.caixa);
  $("#data").textContent = e.data;

  const botao = $("#jogar");
  const confronto = $("#proximo-confronto");
  const onde = $("#proximo-onde");
  if (e.demitido) {
    confronto.textContent = "Você foi demitido";
    onde.textContent = e.motivo;
    botao.disabled = true;
    botao.textContent = "Fim";
  } else if (e.acabou) {
    confronto.textContent = "Temporada encerrada";
    onde.textContent = "acesso, mercado e balanço do ano";
    botao.disabled = false;
    botao.textContent = "Encerrar ano";
  } else if (e.proximo && e.proximo.tipo === "liga") {
    const p = e.proximo;
    confronto.textContent = p.casa
      ? `${e.clube.nome} x ${p.rival.nome}` : `${p.rival.nome} x ${e.clube.nome}`;
    onde.textContent = `${p.competicao} · rodada ${p.rodada}`;
    botao.disabled = false;
    botao.textContent = "Jogar";
  } else if (e.proximo) {
    confronto.textContent = e.proximo.competicao;
    onde.textContent = `${e.proximo.fase} · ${e.proximo.vivos} clubes`;
    botao.disabled = false;
    botao.textContent = "Jogar";
  } else {
    confronto.textContent = "Sem jogo nesta data";
    onde.textContent = "";
    botao.disabled = false;
    botao.textContent = "Avançar";
  }
}

/* ------------------------------------------------------------------ início */

async function telaInicio() {
  const d = await api.get("/api/inicio");
  const c = d.campanha;
  $("#campanha").innerHTML = [
    ["Posição", c.posicao ? `${c.posicao}º` : "—"], ["Pontos", c.pontos],
    ["Jogos", c.jogos], ["Vitórias", c.vitorias],
    ["Empates", c.empates], ["Derrotas", c.derrotas],
    ["Gols pró", c.gols_pro], ["Gols contra", c.gols_contra],
  ].map(([r, v]) => `<div><b>${v}</b><span>${r}</span></div>`).join("");

  const a = ESTADO.aprovacao;
  $("#clima").innerHTML = `
    <p class="meta-texto">A diretoria quer <b>${escapar(a.meta || "—")}</b>.</p>
    ${[["Torcida", a.torcida], ["Diretoria", a.diretoria]].map(([r, v]) => `
      <div class="medidor">
        <div class="topo-medidor"><span>${r}</span><b>${Math.round(v)}%</b></div>
        <div class="trilho"><i style="width:${v}%;background:${corDe(v, 60, 35)}"></i></div>
      </div>`).join("")}
    <div class="clima-etiqueta">${escapar(a.clima)}</div>`;

  $("#ultimos").innerHTML = d.ultimos.length ? d.ultimos.map((j) => `
    <tr><td class="res-${j.resultado}">${j.resultado}</td>
    <td>${escapar(j.casa)}</td>
    <td class="n"><b>${j.gols_casa} × ${j.gols_fora}</b></td>
    <td>${escapar(j.fora)}</td></tr>`).join("")
    : `<tr><td class="dica">Nenhum jogo ainda.</td></tr>`;

  $("#proximos").innerHTML = d.proximos.length ? d.proximos.map((j) => `
    <tr><td class="n">${j.rodada}</td>
    <td><span class="pastilha-clube" style="background:${j.cor}"></span>
      ${escapar(j.rival)}</td>
    <td class="dica">${j.casa ? "em casa" : "fora"}</td></tr>`).join("")
    : `<tr><td class="dica">Fim do calendário.</td></tr>`;

  await miniTabela();
}

/** A tabela em volta do clube: e o que um manager mostra na abertura, e o que faz a tela
 *  inicial responder "como estou?" sem exigir um clique. */
async function miniTabela() {
  const t = await api.get("/api/tabela");
  const eu = t.linhas.findIndex((l) => l.eu);
  const inicio = Math.max(0, Math.min(eu - 4, t.linhas.length - 9));
  const total = t.linhas.length;
  $("#mini-tabela tbody").innerHTML = t.linhas.slice(inicio, inicio + 9).map((l) => {
    const zona = l.posicao <= 4 ? "continental"
      : l.posicao > total - 4 ? "rebaixamento" : "";
    return `<tr class="${l.eu ? "eu" : ""} ${zona}">
      <td class="n">${l.posicao}</td>
      <td><span class="pastilha-clube" style="background:${l.clube.cor}"></span>
        ${escapar(l.clube.nome)}</td>
      <td class="n"><b>${l.pontos}</b></td><td class="n">${l.jogos}</td>
      <td class="n">${l.vitorias}</td><td class="n">${l.empates}</td>
      <td class="n">${l.derrotas}</td>
      <td class="n">${l.saldo > 0 ? "+" : ""}${l.saldo}</td></tr>`;
  }).join("");
}

/* ------------------------------------------------------------------ elenco */

function ordenar(lista) {
  const {coluna, desc} = ordem;
  return [...lista].sort((a, b) => {
    const x = a[coluna], y = b[coluna];
    const cmp = typeof x === "string" ? x.localeCompare(y) : (x ?? 0) - (y ?? 0);
    return desc ? -cmp : cmp;
  });
}

function telaElenco() {
  const lista = ordenar(ESTADO.elenco.map((p, i) => ({...p, numero: i + 1})));
  $("#grade-elenco tbody").innerHTML = lista.map((p) => `
    <tr class="clicavel ${p.titular ? "titular" : ""}" data-id="${p.id}">
      <td class="n">${p.numero}</td>
      <td><span class="etiqueta">${p.posicao}</span></td>
      <td>${escapar(p.nome)}</td>
      <td class="n">${p.idade}</td>
      <td class="n"><b>${p.overall}</b></td>
      <td class="n">${p.potencial}</td>
      <td class="n">${barra(p.energia, corDe(p.energia))}${p.energia}%</td>
      <td>${moral(p.moral)}</td>
      <td class="n">${p.jogos}</td>
      <td class="n">${p.gols}</td>
      <td class="n">${p.assistencias}</td>
      <td class="n">${dinheiro(p.salario)}</td>
      <td class="n">${p.contrato}</td>
    </tr>`).join("");
  $$("#grade-elenco th[data-ord]").forEach((th) =>
    th.classList.toggle("ordenado", th.dataset.ord === ordem.coluna));
}

async function abrirPerfil(id) {
  const p = await api.get(`/api/jogador?id=${id}`);
  if (p.erro) return;
  const t = p.temporada;
  abrirJanela(`
    <h2>${escapar(p.nome)}</h2>
    <div class="ficha">
      <div><span>Posição</span><b>${escapar(p.posicao_detalhe || p.posicao)}</b></div>
      <div><span>Idade</span><b>${p.idade}</b></div>
      <div><span>Overall</span><b>${p.overall}</b></div>
      <div><span>Potencial</span><b>${p.potencial}</b></div>
      <div><span>Pé</span><b style="font-size:13px">${escapar(p.pe)}</b></div>
      <div><span>Altura</span><b>${p.altura} cm</b></div>
      <div><span>País</span><b style="font-size:13px">${escapar(p.nacionalidade)}</b></div>
      <div><span>Valor</span><b>${dinheiro(p.valor)}</b></div>
      <div><span>Salário</span><b>${dinheiro(p.salario)}</b></div>
      <div><span>Contrato até</span><b>${p.contrato}</b></div>
      <div><span>Condição</span><b>${p.energia}%</b></div>
      <div><span>Moral</span><b style="font-size:13px">${moral(p.moral)}</b></div>
    </div>
    <h3>Atributos</h3>
    <div class="atributos">${Object.entries(p.atributos).map(([nome, v]) => `
      <div class="atributo"><span>${escapar(nome)}</span><b>${v}</b>
        ${barra(v, corDe(v, 78, 62))}</div>`).join("")}</div>
    <h3>Temporada</h3>
    <div class="ficha">
      <div><span>Jogos</span><b>${t.jogos}</b></div>
      <div><span>Gols</span><b>${t.gols}</b></div>
      <div><span>Assistências</span><b>${t.assistencias}</b></div>
      <div><span>Amarelos</span><b>${t.amarelos}</b></div>
      <div><span>Vermelhos</span><b>${t.vermelhos}</b></div>
    </div>`);
}

/* ------------------------------------------------------------------ escalação */

const ALTURAS = {GK: 90, DF: 71, MF: 47, FW: 21};

function colunasDe(n) {
  if (n <= 0) return [];
  if (n === 1) return [50];
  const m = 13;
  return Array.from({length: n}, (_, i) => m + (i * (100 - 2 * m)) / (n - 1));
}

const LINHAS_CAMPO = `
<svg class="linhas" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
  <g fill="none" stroke="#fff" stroke-opacity=".34" stroke-width=".5">
    <rect x="2" y="2" width="96" height="96"/><line x1="2" y1="50" x2="98" y2="50"/>
    <circle cx="50" cy="50" r="11"/>
    <rect x="26" y="83" width="48" height="15"/><rect x="38" y="93" width="24" height="5"/>
    <rect x="26" y="2" width="48" height="15"/><rect x="38" y="2" width="24" height="5"/>
    <path d="M38 83 A 13 13 0 0 1 62 83"/><path d="M38 17 A 13 13 0 0 0 62 17"/>
  </g></svg>`;

async function telaEscalacao() {
  const e = ESTADO;
  const alturas = {...ALTURAS};
  if ((e.tatica.vagas.MF || 0) >= 5) { alturas.MF = 51; alturas.FW = 19; }
  if ((e.tatica.vagas.DF || 0) >= 5) alturas.DF = 73;
  if ((e.tatica.vagas.FW || 0) >= 3) alturas.FW = 23;

  const svgLinha = await camisa(e.clube.id, "1");
  const svgGol = await camisa(e.clube.id, "2");
  const porGrupo = {};
  for (const p of e.elenco.filter((x) => x.titular)) (porGrupo[p.posicao] ||= []).push(p);

  const pecas = [];
  for (const [grupo, gente] of Object.entries(porGrupo)) {
    gente.sort((a, b) => b.overall - a.overall);
    const xs = colunasDe(gente.length);
    gente.forEach((p, i) => {
      pecas.push(`<button class="peca" data-id="${p.id}"
        style="left:${xs[i]}%;top:${alturas[grupo] ?? 50}%">
        ${idsProprios(grupo === "GK" ? svgGol : svgLinha)}
        <span class="nome">${escapar(p.nome.split(" ").slice(-1)[0])}</span>
        <span class="info">${p.posicao} ${p.overall} · ${p.energia}%</span></button>`);
    });
  }
  $("#gramado").innerHTML = LINHAS_CAMPO + pecas.join("");

  $("#grade-reservas tbody").innerHTML = e.elenco.filter((p) => !p.titular).map((p) => `
    <tr class="clicavel" data-id="${p.id}">
      <td><span class="etiqueta">${p.posicao}</span></td>
      <td>${escapar(p.nome)}</td>
      <td class="n"><b>${p.overall}</b></td>
      <td class="n">${p.energia}%</td></tr>`).join("");

  $("#formacao").innerHTML = e.opcoes.formacoes.map((f) =>
    `<option ${f === e.tatica.formacao ? "selected" : ""}>${f}</option>`).join("");

  const titulares = e.elenco.filter((p) => p.titular);
  const media = titulares.reduce((s, p) => s + p.overall, 0) / (titulares.length || 1);
  const energia = titulares.reduce((s, p) => s + p.energia, 0) / (titulares.length || 1);
  $("#resumo-onze").textContent =
    `onze: overall ${media.toFixed(1)} · energia ${energia.toFixed(0)}%`;
}

/* ------------------------------------------------------------------ tática */

const CAMPOS_DE_TATICA = [
  {chave: "formacao", rotulo: "Formação", opcoes: "formacoes"},
  {chave: "marcacao", rotulo: "Pressão", opcoes: "marcacoes"},
  {chave: "estilo", rotulo: "Mentalidade", opcoes: "estilos"},
];

function telaTatica() {
  const e = ESTADO;
  $("#campos-tatica").innerHTML = CAMPOS_DE_TATICA.map((c) => `
    <div class="campo-tatica"><span>${c.rotulo}</span>
      <div class="opcoes" data-campo="${c.chave}">
        ${e.opcoes[c.opcoes].map((o) => `<button data-valor="${escapar(o)}"
          class="${o === e.tatica[c.chave] ? "ativo" : ""}">${escapar(o)}</button>`)
          .join("")}
      </div></div>`).join("");
  $("#efeito-tatica").textContent =
    "Formação, pressão e mentalidade mudam o resultado de verdade: pressão forte cansa " +
    "mais, e o confronto de formações é calculado no motor — não é enfeite.";
}

/* ------------------------------------------------------------------ tabelas */

async function telaClassificacao() {
  const d = await api.get(`/api/tabela${ligaVisivel ? `?liga=${ligaVisivel}` : ""}`);
  ligaVisivel = d.liga;
  $("#pastilhas-ligas").innerHTML = d.ligas.map((n) =>
    `<button class="${n === d.liga ? "ativo" : ""}" data-liga="${escapar(n)}">${
      escapar(n)}</button>`).join("");
  const total = d.linhas.length;
  $("#grade-classificacao tbody").innerHTML = d.linhas.map((l) => {
    const zona = l.posicao <= 4 ? "continental"
      : l.posicao > total - 4 ? "rebaixamento" : "";
    return `<tr class="${l.eu ? "eu" : ""} ${zona}">
      <td class="n">${l.posicao}</td>
      <td><span class="pastilha-clube" style="background:${l.clube.cor}"></span>
        ${escapar(l.clube.nome)}</td>
      <td class="n"><b>${l.pontos}</b></td><td class="n">${l.jogos}</td>
      <td class="n">${l.vitorias}</td><td class="n">${l.empates}</td>
      <td class="n">${l.derrotas}</td><td class="n">${l.gols_pro}</td>
      <td class="n">${l.gols_contra}</td>
      <td class="n">${l.saldo > 0 ? "+" : ""}${l.saldo}</td></tr>`;
  }).join("");
}

function telaCopas() {
  const linhas = ESTADO.copas;
  $("#grade-copas tbody").innerHTML = linhas.length ? linhas.map((c) => `
    <tr><td>${escapar(c.nome)}</td>
    <td>${c.acabou ? "encerrada" : escapar(c.fase)}</td>
    <td class="${c.vivo && !c.acabou ? "bom" : ""}">${
      c.acabou ? "—" : c.vivo ? "vivo" : "eliminado"}</td>
    <td>${c.campeao ? escapar(c.campeao) : "—"}</td></tr>`).join("")
    : `<tr><td class="dica">Sem copas nesta carreira.</td></tr>`;
}

async function telaCalendario() {
  const d = await api.get("/api/calendario");
  $("#grade-calendario tbody").innerHTML = d.datas.map((x) => {
    const res = x.resultado
      ? `<span class="res-${x.resultado.resultado}">${x.resultado.resultado}</span>
         ${x.resultado.gols_casa} × ${x.resultado.gols_fora}`
      : (x.passou ? "—" : "");
    return `<tr class="${x.ordem === d.atual ? "eu" : ""}">
      <td class="n">${x.rodada ?? "—"}</td>
      <td>${escapar(x.competicao)}</td>
      <td>${x.rival ? `${escapar(x.rival.nome)}
        <span class="dica">${x.rival.casa ? "casa" : "fora"}</span>` : "—"}</td>
      <td class="n">${res}</td></tr>`;
  }).join("");
}

async function telaArtilheiros() {
  const d = await api.get("/api/estatisticas");
  const linhas = (lista, a, b) => lista.length ? lista.map((x, i) => `
    <tr class="${x.meu ? "eu" : ""}"><td class="n">${i + 1}</td>
    <td>${escapar(x.nome)} <span class="etiqueta">${x.posicao}</span></td>
    <td><span class="pastilha-clube" style="background:${x.cor}"></span>
      ${escapar(x.clube)}</td>
    <td class="n"><b>${x[a]}</b></td><td class="n">${x[b]}</td>
    <td class="n">${x.jogos}</td></tr>`).join("")
    : `<tr><td class="dica">Ainda não há números nesta temporada.</td></tr>`;
  $("#grade-artilheiros tbody").innerHTML = linhas(d.artilheiros, "gols", "assistencias");
  $("#grade-garcons tbody").innerHTML = linhas(d.garcons, "assistencias", "gols");
}

async function telaFinancas() {
  const d = await api.get("/api/financas");
  $("#resumo-financas tbody").innerHTML = [
    ["Caixa", reais(d.caixa), d.caixa < 0 ? "ruim" : ""],
    ["Receita prevista", reais(d.receita), ""],
    ["Folha salarial", reais(d.folha), ""],
    ["Custo de operação", reais(d.operacao), ""],
    ["Saldo previsto", reais(d.saldo_previsto), d.saldo_previsto < 0 ? "ruim" : "bom"],
    ["Valor do elenco", reais(d.valor_do_elenco), ""],
    ["Reputação", d.reputacao, ""],
  ].map(([r, v, cls]) => `<tr><td>${r}</td><td class="n ${cls}">${v}</td></tr>`).join("");

  $("#folha tbody").innerHTML = d.salarios.map((s) => `
    <tr><td>${escapar(s.nome)}</td>
    <td><span class="etiqueta">${s.posicao}</span></td>
    <td class="n">${dinheiro(s.salario)}</td>
    <td class="n">${dinheiro(s.valor)}</td>
    <td class="n">${s.contrato}</td></tr>`).join("");
}

/* ------------------------------------------------------------------ janelas */

function abrirJanela(html) {
  $("#conteudo-janela").innerHTML = html;
  $("#cortina").hidden = false;
  $("#conteudo-janela").scrollTop = 0;
  $("#fechar-janela").focus({preventScroll: true});
}

async function janelaDaPartida(r) {
  const p = r.partida;
  let html = "";
  if (p) {
    html += `<div class="placar-janela">
      <div class="lado">${idsProprios(await camisa(p.casa.id, "1"))}
        <span>${escapar(p.casa.nome)}</span></div>
      <div><div class="numeros">${p.gols_casa} × ${p.gols_fora}</div>
        <div class="relogio">90:00 · ${escapar(r.competicao)}</div></div>
      <div class="lado">${idsProprios(await camisa(p.fora.id, "2"))}
        <span>${escapar(p.fora.nome)}</span></div></div>`;
    const marca = {gol: "GOL", amarelo: "CA", vermelho: "CV", substituicao: "SUB"};
    html += `<h3>Lances</h3>`;
    html += p.eventos.length ? `<ul class="lances">${p.eventos.map((e) => `
      <li><span class="minuto">${e.minuto}'</span>
      <span class="tipo ${e.tipo}">${marca[e.tipo] ?? ""}</span>
      <span>${escapar(e.texto)} <span class="minuto">${escapar(e.clube)}</span></span>
      </li>`).join("")}</ul>` : `<p class="dica">Nada digno de nota.</p>`;
    html += `<h3>Números</h3><table class="comparativo">${p.estatisticas.map((s) => `
      <tr><td class="v">${s.casa}</td><td class="meio">${escapar(s.nome)}</td>
      <td class="v dir">${s.fora}</td></tr>`).join("")}</table>`;
  } else {
    html += `<h2>${escapar(r.competicao)}</h2>
      <p class="dica">Seu time não entrou em campo nesta data.</p>`;
  }
  if (r.outros.length) {
    html += `<h3>Outros jogos</h3><table class="grade compacta"><tbody>
      ${r.outros.slice(0, 14).map((o) => `<tr>
        <td style="text-align:right">${escapar(o.casa.nome)}</td>
        <td class="n">${o.gols_casa} × ${o.gols_fora}</td>
        <td>${escapar(o.fora.nome)}</td></tr>`).join("")}</tbody></table>`;
  }
  abrirJanela(html);
}

function janelaDeFimDeAno(r) {
  let html = `<h2>Fim da temporada ${r.temporada}</h2>`;
  if (r.demitido) {
    html += `<div class="aviso"><b>Você foi demitido</b>
      <span>${escapar(r.motivo)}</span></div>`;
  }
  const destino = r.subi ? `<span class="bom">ACESSO</span>`
    : r.cai ? `<span class="ruim">REBAIXADO</span>` : "";
  html += `<p>${r.posicao}º lugar na ${escapar(r.liga)} ${destino}</p>`;
  if (r.clima && r.clima.meta) {
    html += `<p class="dica">A meta era ${escapar(r.clima.meta)} —
      ${r.clima.bateu_a_meta ? '<span class="bom">cumprida</span>'
        : '<span class="ruim">não cumprida</span>'} ·
      torcida ${Math.round(r.clima.torcida)}% · diretoria
      ${Math.round(r.clima.diretoria)}%</p>`;
  }
  const campeoes = Object.entries({...r.campeoes, ...r.copas}).filter(([, v]) => v);
  html += `<h3>Campeões</h3><table class="grade compacta"><tbody>${campeoes.map(([k, v]) =>
    `<tr><td>${escapar(k.replace(/_/g, " "))}</td><td><b>${escapar(v)}</b></td></tr>`
  ).join("")}</tbody></table>`;
  if (r.minhas_copas.length) {
    html += `<p class="bom">Você é campeão da
      ${r.minhas_copas.map((x) => escapar(x.replace(/_/g, " "))).join(", ")}.</p>`;
  }
  if (r.balanco) {
    const b = r.balanco;
    const saldo = b.receita + b.premiacao - b.folha - b.operacao;
    html += `<h3>Balanço</h3><table class="grade compacta"><tbody>
      <tr><td>Receita</td><td class="n">${reais(b.receita)}</td></tr>
      <tr><td>Premiação</td><td class="n">${reais(b.premiacao)}</td></tr>
      <tr><td>Folha</td><td class="n">−${reais(b.folha)}</td></tr>
      <tr><td>Operação</td><td class="n">−${reais(b.operacao)}</td></tr>
      <tr><td><b>Saldo</b></td><td class="n ${saldo < 0 ? "ruim" : "bom"}">
        <b>${reais(saldo)}</b></td></tr></tbody></table>`;
  }
  if (r.compras.length || r.vendas.length) {
    html += `<h3>Mercado</h3><table class="grade compacta"><tbody>
      ${r.compras.map((t) => `<tr><td class="bom">chega</td>
        <td>${escapar(t.nome)} (${t.overall})</td><td>${escapar(t.de)}</td>
        <td class="n">${dinheiro(t.preco)}</td></tr>`).join("")}
      ${r.vendas.map((t) => `<tr><td class="ruim">sai</td>
        <td>${escapar(t.nome)} (${t.overall})</td><td>${escapar(t.para)}</td>
        <td class="n">${dinheiro(t.preco)}</td></tr>`).join("")}
      </tbody></table>`;
  }
  html += `<p class="dica">${r.aposentaram} penduraram as chuteiras no país,
    ${r.revelados} subiram da base, ${r.transferencias} transferências.</p>`;
  abrirJanela(html);
}

/* ------------------------------------------------------------------ ações */

async function mandarTatica(extra = {}) {
  const r = await api.post("/api/escalar", {
    formacao: $("#formacao")?.value ?? ESTADO.tatica.formacao,
    marcacao: ESTADO.tatica.marcacao, estilo: ESTADO.tatica.estilo, ...extra,
  });
  if (r.erro) alert(r.erro);
  await aplicar(r.estado);
}

async function jogar() {
  const botao = $("#jogar");
  botao.disabled = true;
  try {
    if (ESTADO.acabou) {
      const r = await api.post("/api/virar");
      if (r.erro) { alert(r.erro); return; }
      janelaDeFimDeAno(r);
      await aplicar(r.estado);
      return;
    }
    const r = await api.post("/api/avancar");
    if (r.erro) { alert(r.erro); return; }
    await janelaDaPartida(r);
    await aplicar(r.estado);
  } finally {
    botao.disabled = ESTADO?.demitido ?? false;
  }
}

/* ------------------------------------------------------------------ navegação */

const DESENHOS = {
  inicio: telaInicio, elenco: telaElenco, escalacao: telaEscalacao,
  tatica: telaTatica, financas: telaFinancas, classificacao: telaClassificacao,
  copas: telaCopas, calendario: telaCalendario, artilheiros: telaArtilheiros,
  salvar: () => {},
};

async function irPara(nome) {
  telaAtual = nome;
  $$(".item").forEach((b) => b.classList.toggle("ativo", b.dataset.tela === nome));
  $$(".tela").forEach((t) => t.classList.toggle("ativa", t.id === `tela-${nome}`));
  await DESENHOS[nome]?.();
}

async function aplicar(e) {
  ESTADO = e;
  desenharTopo(e);
  await DESENHOS[telaAtual]?.();
}

function ligarEventos() {
  $("#menu").addEventListener("click", (ev) => {
    const b = ev.target.closest(".item");
    if (b) irPara(b.dataset.tela);
  });
  $("#jogar").addEventListener("click", jogar);
  $("#fechar-janela").addEventListener("click", () => { $("#cortina").hidden = true; });

  $("#grade-elenco").addEventListener("click", (ev) => {
    const th = ev.target.closest("th[data-ord]");
    if (th) {
      const col = th.dataset.ord;
      ordem = {coluna: col, desc: ordem.coluna === col ? !ordem.desc : true};
      telaElenco();
      return;
    }
    const tr = ev.target.closest("tr[data-id]");
    if (tr) abrirPerfil(Number(tr.dataset.id));
  });

  $("#gramado").addEventListener("click", (ev) => {
    const peca = ev.target.closest(".peca");
    if (!peca) return;
    $$(".peca").forEach((x) => x.classList.remove("marcado"));
    if (marcado === Number(peca.dataset.id)) { marcado = null; return; }
    marcado = Number(peca.dataset.id);
    peca.classList.add("marcado");
  });

  $("#grade-reservas").addEventListener("click", async (ev) => {
    const tr = ev.target.closest("tr[data-id]");
    if (!tr) return;
    if (marcado === null) {
      $("#resumo-onze").textContent = "escolha antes um titular no campo";
      return;
    }
    const entra = Number(tr.dataset.id);
    const onze = ESTADO.onze.map((x) => (x === marcado ? entra : x));
    marcado = null;
    await mandarTatica({onze});
  });

  $("#formacao").addEventListener("change", () => mandarTatica());
  $("#auto").addEventListener("click", () => mandarTatica());

  $("#campos-tatica").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-valor]");
    if (!b) return;
    const campo = b.closest(".opcoes").dataset.campo;
    mandarTatica({[campo]: b.dataset.valor, onze: ESTADO.onze});
  });

  $("#pastilhas-ligas").addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (b) { ligaVisivel = b.dataset.liga; telaClassificacao(); }
  });

  $("#botao-salvar").addEventListener("click", async () => {
    const r = await api.post("/api/salvar", {nome: $("#nome-do-save").value || "carreira"});
    $("#aviso-save").textContent = `Salvo em ${r.arquivo}`;
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") $("#cortina").hidden = true;
    if (ev.key === " " && $("#cortina").hidden
        && !ev.target.closest("select, button, input")) {
      ev.preventDefault();
      jogar();
    }
  });
}

async function comecar() {
  ligarEventos();
  const parametros = new URLSearchParams(location.search);
  ESTADO = await api.get("/api/estado");
  desenharTopo(ESTADO);
  const inicial = parametros.get("tela");
  await irPara(DESENHOS[inicial] ? inicial : "inicio");

  // ?jogar=N avanca N datas ao abrir: serve para retomar e para conferir a tela de partida
  const pular = Number(parametros.get("jogar") || 0);
  for (let i = 0; i < pular && !ESTADO.demitido && !ESTADO.acabou; i++) {
    await jogar();
    if (i < pular - 1) $("#cortina").hidden = true;
  }
}

comecar();
