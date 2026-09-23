"use strict";
/* A casca do jogo no navegador.
 *
 * Nenhuma regra mora aqui: tudo que este arquivo faz e pedir estado ao servidor, desenhar,
 * e mandar de volta o que o usuario clicou. A mesma divisao do terminal -- por isso as duas
 * interfaces podem existir ao mesmo tempo sem duplicar uma linha de logica. */

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

let ESTADO = null;
let escolhido = null;          // titular clicado, esperando um reserva
let ligaVisivel = null;

/* ------------------------------------------------------------------ utilidades */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function dinheiro(v) {
  const n = Math.abs(v);
  if (n >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${Math.round(v / 1e3)}k`;
  return String(v);
}

function corDaEnergia(e) {
  if (e >= 80) return "var(--bom)";
  if (e >= 60) return "var(--medio)";
  return "var(--ruim)";
}

function corDaAprovacao(v) {
  if (v >= 60) return "var(--bom)";
  if (v >= 35) return "var(--medio)";
  return "var(--ruim)";
}

/** As camisas vem do servidor como SVG. Cada uma ganha ids proprios: onze recortes com o
 *  mesmo id fariam as onze usarem o da primeira, e a cor de um jogador vazaria nos outros. */
const camisasEmCache = new Map();
async function camisa(clubeId, numero = "1") {
  const chave = `${clubeId}-${numero}`;
  if (!camisasEmCache.has(chave)) {
    const r = await fetch(`/api/camisa/${clubeId}/${numero}`);
    camisasEmCache.set(chave, await r.text());
  }
  return camisasEmCache.get(chave);
}

let contadorDeIds = 0;
function comIdsProprios(svg) {
  const sufixo = `u${contadorDeIds++}`;
  return svg.replace(/id="([\w-]+)"/g, `id="$1${sufixo}"`)
            .replace(/url\(#([\w-]+)\)/g, `url(#$1${sufixo})`)
            .replace(/href="#([\w-]+)"/g, `href="#$1${sufixo}"`);
}

/* ------------------------------------------------------------------ topo */

function desenharTopo(e) {
  document.documentElement.style.setProperty("--tema", e.clube.cor);
  document.documentElement.style.setProperty("--tema-suave", `${e.clube.cor}22`);
  $("#faixa-cor").style.background = e.clube.cor;
  $("#nome-do-clube").textContent = e.clube.nome;
  $("#contexto").textContent =
    `${e.liga} · ${e.temporada} · rodada ${e.rodada} de ${e.total_de_rodadas}`;
  $("#posicao").textContent = e.posicao ? `${e.posicao}º` : "—";
  $("#pontos").textContent = e.pontos;
  $("#caixa").textContent = dinheiro(e.caixa);
}

/* ------------------------------------------------------------------ lobby */

async function desenharProximo(e) {
  const alvo = $("#proximo");
  const botao = $("#jogar");
  const dica = $("#dica-jogar");

  if (e.demitido) {
    alvo.innerHTML = `<p class="rival">Você foi demitido.</p>
      <p class="onde">${e.motivo}</p>`;
    botao.disabled = true;
    botao.textContent = "Fim de linha";
    dica.textContent = "";
    return;
  }
  if (e.acabou) {
    alvo.innerHTML = `<p class="rival">Temporada encerrada</p>
      <p class="onde">${e.liga} · ${e.temporada}</p>`;
    botao.disabled = false;
    botao.textContent = "Encerrar temporada";
    dica.textContent = "Acesso, rebaixamento, mercado e o balanço do ano.";
    return;
  }

  botao.disabled = false;
  botao.textContent = "Jogar";
  const p = e.proximo;
  if (!p) {
    alvo.innerHTML = `<p class="onde">Sem jogo nesta data.</p>`;
    dica.textContent = "";
    return;
  }
  if (p.tipo === "copa") {
    alvo.innerHTML = `<p class="rival">${p.competicao}</p>
      <p class="onde">${p.fase} · ${p.vivos} clubes vivos</p>`;
    dica.textContent = "O sorteio dos confrontos sai na hora da partida.";
  } else {
    const svg = comIdsProprios(await camisa(p.rival.id, "1"));
    alvo.innerHTML = `<div class="confronto">${svg}
      <div><div class="rival">${p.rival.nome}</div>
      <div class="onde">${p.casa ? "em casa" : "fora de casa"} · rodada ${p.rodada}</div>
      </div></div>`;
    dica.textContent = "";
  }
}

function desenharClima(e) {
  const a = e.aprovacao;
  $("#meta").textContent = a.meta ? `A diretoria quer ${a.meta}.` : "";
  for (const [chave, valor] of [["torcida", a.torcida], ["diretoria", a.diretoria]]) {
    $(`#${chave}-n`).textContent = `${Math.round(valor)}%`;
    const barra = $(`#${chave}-b`);
    barra.style.width = `${valor}%`;
    barra.style.background = corDaAprovacao(valor);
  }
  $("#clima").textContent = a.clima;
}

function desenharElenco(e) {
  const corpo = $("#tabela-elenco tbody");
  corpo.innerHTML = e.elenco.map((p) => `
    <tr class="${p.titular ? "titular" : ""}">
      <td class="marca">${p.titular ? "›" : ""}</td>
      <td><span class="posicao-etiqueta">${p.posicao}</span></td>
      <td>${p.nome}</td>
      <td class="n">${p.overall}</td>
      <td class="n">${p.potencial}</td>
      <td class="n">${p.idade}</td>
      <td><span class="barra-energia"><i style="width:${p.energia}%;
        background:${corDaEnergia(p.energia)}"></i></span>${p.energia}%</td>
      <td class="n">${dinheiro(p.salario)}</td>
    </tr>`).join("");
}

/* ------------------------------------------------------------------ campo */

const ALTURAS = {GK: 91, DF: 72, MF: 48, FW: 22};

function posicoesDaLinha(n) {
  if (n <= 0) return [];
  if (n === 1) return [50];
  const margem = 13, largura = 100 - 2 * margem;
  return Array.from({length: n}, (_, i) => margem + (i * largura) / (n - 1));
}

function alturasDe(vagas) {
  const a = {...ALTURAS};
  if ((vagas.MF || 0) >= 5) { a.MF = 52; a.FW = 20; }
  if ((vagas.DF || 0) >= 5) a.DF = 74;
  if ((vagas.FW || 0) >= 3) a.FW = 24;
  return a;
}

const LINHAS_DO_CAMPO = `
<svg class="linhas" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
  <g fill="none" stroke="#fff" stroke-opacity=".38" stroke-width=".5">
    <rect x="2" y="2" width="96" height="96"/>
    <line x1="2" y1="50" x2="98" y2="50"/>
    <circle cx="50" cy="50" r="11"/>
    <rect x="26" y="83" width="48" height="15"/>
    <rect x="38" y="93" width="24" height="5"/>
    <rect x="26" y="2" width="48" height="15"/>
    <rect x="38" y="2" width="24" height="5"/>
    <path d="M38 83 A 13 13 0 0 1 62 83"/>
    <path d="M38 17 A 13 13 0 0 0 62 17"/>
  </g>
  <circle cx="50" cy="50" r=".9" fill="#fff" fill-opacity=".38"/>
</svg>`;

async function desenharCampo(e) {
  const gramado = $("#gramado");
  const titulares = e.elenco.filter((p) => p.titular);
  const porGrupo = {};
  for (const p of titulares) (porGrupo[p.posicao] ||= []).push(p);

  const alturas = alturasDe(e.tatica.vagas);
  const svgLinha = comIdsProprios(await camisa(e.clube.id, "1"));
  const svgGol = comIdsProprios(await camisa(e.clube.id, "2"));

  const pecas = [];
  for (const [grupo, gente] of Object.entries(porGrupo)) {
    gente.sort((a, b) => b.overall - a.overall);
    const xs = posicoesDaLinha(gente.length);
    gente.forEach((p, i) => {
      const svg = grupo === "GK" ? comIdsProprios(svgGol) : comIdsProprios(svgLinha);
      pecas.push(`<button class="pecaJ" data-id="${p.id}"
        style="left:${xs[i]}%;top:${alturas[grupo] ?? 50}%">
        ${svg}
        <span class="nome">${p.nome.split(" ").slice(-1)[0]}</span>
        <span class="dados">${p.posicao} ${p.overall} - E:${p.energia}</span>
      </button>`);
    });
  }
  gramado.innerHTML = LINHAS_DO_CAMPO + pecas.join("");

  $("#reservas").innerHTML = e.elenco.filter((p) => !p.titular).map((p) => `
    <button class="reserva" data-id="${p.id}">
      <span class="pos">${p.posicao}</span>${p.nome}
      <span class="ovr">${p.overall}</span>
      <span class="pos">${p.energia}%</span>
    </button>`).join("");

  for (const sel of ["formacao", "marcacao", "estilo"]) {
    const campo = $(`#${sel}`);
    const opcoes = e.opcoes[sel === "formacao" ? "formacoes" :
      sel === "marcacao" ? "marcacoes" : "estilos"];
    campo.innerHTML = opcoes.map((o) =>
      `<option ${o === e.tatica[sel] ? "selected" : ""}>${o}</option>`).join("");
  }
}

function ligarCampo() {
  $("#gramado").addEventListener("click", (ev) => {
    const peca = ev.target.closest(".pecaJ");
    if (!peca) return;
    $$(".pecaJ").forEach((x) => x.classList.remove("escolhido"));
    if (escolhido === Number(peca.dataset.id)) { escolhido = null; return; }
    escolhido = Number(peca.dataset.id);
    peca.classList.add("escolhido");
  });

  $("#reservas").addEventListener("click", async (ev) => {
    const banco = ev.target.closest(".reserva");
    if (!banco) return;
    if (escolhido === null) {
      $("#gramado").animate([{opacity: 1}, {opacity: .5}, {opacity: 1}], 260);
      return;
    }
    const entra = Number(banco.dataset.id);
    const onze = ESTADO.onze.map((x) => (x === escolhido ? entra : x));
    escolhido = null;
    await mandarEscalacao({onze});
  });

  for (const sel of ["formacao", "marcacao", "estilo"]) {
    $(`#${sel}`).addEventListener("change", async () => {
      // trocar de formacao muda as vagas, entao o onze e' remontado pelo servidor
      const corpo = {formacao: $("#formacao").value, marcacao: $("#marcacao").value,
                     estilo: $("#estilo").value};
      if (sel !== "formacao") corpo.onze = ESTADO.onze;
      await mandarEscalacao(corpo);
    });
  }
  $("#auto").addEventListener("click", () => mandarEscalacao({
    formacao: $("#formacao").value, marcacao: $("#marcacao").value,
    estilo: $("#estilo").value,
  }));
}

async function mandarEscalacao(corpo) {
  const r = await api.post("/api/escalar", {
    formacao: $("#formacao").value, marcacao: $("#marcacao").value,
    estilo: $("#estilo").value, ...corpo,
  });
  if (r.erro) alert(r.erro);
  await aplicar(r.estado);
}

/* ------------------------------------------------------------------ tabela */

async function desenharTabela(liga) {
  const dados = await api.get(`/api/tabela${liga ? `?liga=${liga}` : ""}`);
  ligaVisivel = dados.liga;
  $("#abas-ligas").innerHTML = dados.ligas.map((n) =>
    `<button class="${n === dados.liga ? "ativa" : ""}" data-liga="${n}">${n}</button>`
  ).join("");
  const total = dados.linhas.length;
  $("#tabela-liga tbody").innerHTML = dados.linhas.map((l) => {
    let zona = "";
    if (l.posicao <= 4) zona = "zona-libertadores";
    else if (l.posicao > total - 4) zona = "zona-rebaixamento";
    return `<tr class="${l.eu ? "eu" : ""} ${zona}">
      <td class="n">${l.posicao}</td>
      <td><span class="clube"><span class="pastilha"
        style="background:${l.clube.cor}"></span>${l.clube.nome}</span></td>
      <td class="n">${l.pontos}</td><td class="n">${l.jogos}</td>
      <td class="n">${l.vitorias}</td><td class="n">${l.empates}</td>
      <td class="n">${l.derrotas}</td><td class="n">${l.gols_pro}</td>
      <td class="n">${l.gols_contra}</td>
      <td class="n">${l.saldo > 0 ? "+" : ""}${l.saldo}</td>
    </tr>`;
  }).join("");
}

/* ------------------------------------------------------------------ copas */

function desenharCopas(e) {
  if (!e.copas.length) {
    $("#lista-copas").innerHTML = `<p class="dica">Sem copas nesta carreira.</p>`;
    return;
  }
  $("#lista-copas").innerHTML = e.copas.map((c) => {
    const situacao = c.acabou
      ? (c.campeao ? `Campeão: ${c.campeao}` : "encerrada")
      : (c.vivo ? "Você segue vivo" : "Você está fora");
    return `<div class="copa ${c.vivo && !c.acabou ? "vivo" : "fora"}">
      <h3>${c.nome}</h3>
      <p>${c.acabou ? "Encerrada" : c.fase}</p>
      <p class="situacao">${situacao}</p>
    </div>`;
  }).join("");
}

/* ------------------------------------------------------------------ partida */

async function mostrarPartida(r) {
  const p = r.partida;
  let html = "";
  if (p) {
    const svgCasa = comIdsProprios(await camisa(p.casa.id, "1"));
    const svgFora = comIdsProprios(await camisa(p.fora.id, "2"));
    html += `<div class="placar">
      <div class="lado">${svgCasa}<span>${p.casa.nome}</span></div>
      <div class="numeros">${p.gols_casa} × ${p.gols_fora}</div>
      <div class="lado">${svgFora}<span>${p.fora.nome}</span></div>
    </div>`;
    const simbolo = {gol: "GOL", amarelo: "!", vermelho: "!!!", substituicao: "↔"};
    html += p.eventos.length
      ? `<ul class="sumula">${p.eventos.map((e) => `
          <li><span class="minuto">${e.minuto}'</span>
          <span class="${e.meu ? "meu" : ""}">${simbolo[e.tipo] ?? ""}</span>
          <span>${e.texto} <span class="minuto">${e.clube}</span></span></li>`).join("")}
        </ul>`
      : `<p class="dica">Nada digno de nota.</p>`;
    html += `<table class="tabela-stats">${p.estatisticas.map((s) => `
      <tr><td class="v">${s.casa}</td><td class="rotulo">${s.nome}</td>
      <td class="v dir">${s.fora}</td></tr>`).join("")}</table>`;
  } else {
    html += `<p class="dica">Seu time não jogou nesta data (${r.competicao}).</p>`;
  }
  if (r.outros.length) {
    html += `<div class="outros-jogos"><h3>Outros jogos — ${r.competicao}</h3>
      ${r.outros.slice(0, 12).map((o) => `<div><span class="dir">${o.casa.nome}</span>
        <span class="placarzinho">${o.gols_casa} × ${o.gols_fora}</span>
        <span>${o.fora.nome}</span></div>`).join("")}</div>`;
  }
  abrirModal(html);
}

function mostrarFimDeTemporada(r) {
  let html = `<h2 style="margin-top:0">Fim da temporada ${r.temporada}</h2>`;
  if (r.demitido) {
    html += `<div class="aviso-grande"><b>Você foi demitido</b>
      <span>${r.motivo}</span></div>`;
  }
  const destino = r.subi ? `<span class="destaque">ACESSO!</span>`
    : r.cai ? `<span style="color:var(--ruim)">REBAIXADO</span>` : "";
  html += `<p>${r.posicao}º lugar na ${r.liga} ${destino}</p>`;
  if (r.clima && r.clima.meta) {
    html += `<p class="dica">A meta era ${r.clima.meta} —
      ${r.clima.bateu_a_meta ? '<span class="destaque">cumprida</span>'
        : '<span style="color:var(--ruim)">não cumprida</span>'}.
      Torcida ${Math.round(r.clima.torcida)}%, diretoria
      ${Math.round(r.clima.diretoria)}%.</p>`;
  }
  const campeoes = {...r.campeoes, ...r.copas};
  html += `<h3>Campeões</h3><ul class="sumula">${
    Object.entries(campeoes).filter(([, v]) => v).map(([k, v]) =>
      `<li><span></span><span></span><span>${k.replace(/_/g, " ")}: <b>${v}</b></span></li>`
    ).join("")}</ul>`;
  if (r.minhas_copas.length) {
    html += `<p class="destaque">Você é campeão da
      ${r.minhas_copas.map((x) => x.replace(/_/g, " ")).join(", ")}!</p>`;
  }
  if (r.balanco) {
    const b = r.balanco;
    const saldo = b.receita + b.premiacao - b.folha - b.operacao;
    html += `<h3>Caixa</h3><p class="dica">
      receita ${dinheiro(b.receita)} + premiação ${dinheiro(b.premiacao)}
      − folha ${dinheiro(b.folha)} − operação ${dinheiro(b.operacao)}
      = <b>${saldo >= 0 ? "+" : ""}${dinheiro(saldo)}</b></p>`;
  }
  if (r.compras.length || r.vendas.length) {
    html += `<h3>Mercado</h3><ul class="sumula">`;
    html += r.compras.map((t) => `<li><span class="minuto">chega</span><span></span>
      <span>${t.nome} (${t.overall}) do ${t.de} por ${dinheiro(t.preco)}</span></li>`).join("");
    html += r.vendas.map((t) => `<li><span class="minuto">sai</span><span></span>
      <span>${t.nome} (${t.overall}) para o ${t.para} por ${dinheiro(t.preco)}</span></li>`).join("");
    html += `</ul>`;
  }
  html += `<p class="dica">${r.aposentaram} penduraram as chuteiras no país,
    ${r.revelados} subiram da base, ${r.transferencias} transferências.</p>`;
  abrirModal(html);
}

function abrirModal(html) {
  $("#conteudo-modal").innerHTML = html;
  $("#cortina").hidden = false;
  $(".janela").scrollTop = 0;     // sumula longa abria rolada, escondendo o placar
  $("#fechar-modal").focus({preventScroll: true});
}

/* ------------------------------------------------------------------ ciclo */

async function aplicar(e) {
  ESTADO = e;
  desenharTopo(e);
  await desenharProximo(e);
  desenharClima(e);
  desenharElenco(e);
  desenharCopas(e);
  if ($("#campo").classList.contains("ativo")) await desenharCampo(e);
  if ($("#tabela").classList.contains("ativo")) await desenharTabela(ligaVisivel);
}

async function jogar() {
  const botao = $("#jogar");
  botao.disabled = true;
  try {
    if (ESTADO.acabou) {
      const r = await api.post("/api/virar");
      if (r.erro) { alert(r.erro); return; }
      mostrarFimDeTemporada(r);
      await aplicar(r.estado);
      return;
    }
    const r = await api.post("/api/avancar");
    if (r.erro) { alert(r.erro); return; }
    await mostrarPartida(r);
    await aplicar(r.estado);
  } finally {
    botao.disabled = ESTADO?.demitido ?? false;
  }
}

function ligarAbas() {
  $$(".aba").forEach((aba) => {
    aba.addEventListener("click", async () => {
      $$(".aba").forEach((x) => x.classList.remove("ativa"));
      $$(".painel").forEach((x) => x.classList.remove("ativo"));
      aba.classList.add("ativa");
      $(`#${aba.dataset.painel}`).classList.add("ativo");
      if (aba.dataset.painel === "campo") await desenharCampo(ESTADO);
      if (aba.dataset.painel === "tabela") await desenharTabela(ligaVisivel);
    });
  });
  $("#abas-ligas").addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (b) desenharTabela(b.dataset.liga);
  });
}

/** Abre direto numa aba: ?aba=campo. Serve para voltar onde parou e para conferir uma
 *  tela sem ter de clicar ate ela. */
function abaInicial() {
  const pedida = new URLSearchParams(location.search).get("aba");
  if (!pedida) return;
  const aba = $$(".aba").find((x) => x.dataset.painel === pedida);
  if (!aba) return;
  $$(".aba").forEach((x) => x.classList.remove("ativa"));
  $$(".painel").forEach((x) => x.classList.remove("ativo"));
  aba.classList.add("ativa");
  $(`#${pedida}`).classList.add("ativo");
}

async function comecar() {
  ligarAbas();
  abaInicial();
  ligarCampo();
  $("#jogar").addEventListener("click", jogar);
  $("#fechar-modal").addEventListener("click", () => { $("#cortina").hidden = true; });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") $("#cortina").hidden = true;
    if (ev.key === " " && $("#cortina").hidden && !ev.target.closest("select, button")) {
      ev.preventDefault();
      jogar();
    }
  });
  await aplicar(await api.get("/api/estado"));

  // ?jogar=N avanca N datas ao abrir. Serve para retomar de onde parou sem clicar N vezes,
  // e para conferir a tela de partida sem interacao manual.
  const pular = Number(new URLSearchParams(location.search).get("jogar") || 0);
  for (let i = 0; i < pular && !ESTADO.demitido && !ESTADO.acabou; i++) {
    await jogar();
    if (i < pular - 1) $("#cortina").hidden = true;
  }
}

comecar();
