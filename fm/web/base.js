"use strict";
/* PRANCHETA 11 -- a base comum de todas as telas.
 *
 * Nenhuma regra de jogo mora no navegador: ele pede estado ao servidor, desenha, e manda
 * de volta o que o usuario decidiu. Este arquivo tem o que todas as telas usam -- rede,
 * formato de numero, icones, escudo, camisa, janela e a troca de modo. */

/* ------------------------------------------------------------------ rede */

const api = {
  async get(rota) {
    const r = await fetch(rota);
    if (r.status === 500) { const d = await r.json(); throw new Error(d.erro || rota); }
    if (!r.ok) throw new Error(`${rota}: ${r.status}`);
    return r.json();
  },
  async post(rota, corpo = {}) {
    const r = await fetch(rota, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(corpo),
    });
    if (r.status === 500) { const d = await r.json(); throw new Error(d.erro || rota); }
    if (!r.ok) throw new Error(`${rota}: ${r.status}`);
    return r.json();
  },
};

const $ = (s, raiz = document) => raiz.querySelector(s);
const $$ = (s, raiz = document) => Array.from(raiz.querySelectorAll(s));
const PARAMS = new URLSearchParams(location.search);
if (PARAMS.get("foto")) document.documentElement.classList.add("sem-animacao");

/* ------------------------------------------------------------------ formato */

function escapar(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

/* Dinheiro. O motor conta tudo em EURO. Valor de mercado e transferencia aparecem em euro,
 * como no futebol entre paises; o dinheiro do CLUBE -- caixa, receita, folha, salario --
 * na moeda do pais dele (MOEDA, que vem com o estado). O que o usuario digita nessa moeda
 * volta para euro antes de ir ao servidor (paraEuro). */
let MOEDA = {codigo: "EUR", simbolo: "€", taxa: 1};

function _curto(v, simbolo) {
  const n = Math.abs(v ?? 0);
  const s = (v ?? 0) < 0 ? "−" : "";
  if (n >= 1e9) return `${s}${simbolo} ${(n / 1e9).toFixed(2).replace(".", ",")} bi`;
  if (n >= 1e6) return `${s}${simbolo} ${(n / 1e6).toFixed(1).replace(".", ",")} mi`;
  if (n >= 1e3) return `${s}${simbolo} ${Math.round(n / 1e3)} mil`;
  return `${s}${simbolo} ${Math.round(n)}`;
}

/* euros do motor -> moeda do clube, texto curto (R$ 12,4 mi) */
function dinheiro(v, moeda = MOEDA) { return _curto((v ?? 0) * moeda.taxa, moeda.simbolo); }
/* valor de mercado e transferencia: sempre em euro */
function euros(v) { return _curto(v, "€"); }
/* transferencia com a conversao ao lado, onde o valor encontra o caixa do clube */
function eurosConvertido(v) {
  return MOEDA.codigo === "EUR" ? euros(v)
    : `${euros(v)} <small class="dica">≈ ${dinheiro(v)}</small>`;
}
function daMoeda(v, moeda = MOEDA) { return Math.round((v ?? 0) * moeda.taxa); }
function paraEuro(v, moeda = MOEDA) { return Math.round((v ?? 0) / moeda.taxa); }
/* numero inteiro por extenso, para os campos de negociacao */
function inteiro(v, simbolo) { return `${simbolo} ${Math.round(v || 0).toLocaleString("pt-BR")}`; }

function dinheiroInteiro(v) { return inteiro(daMoeda(v), MOEDA.simbolo); }

function corDe(valor, bom = 80, medio = 60) {
  if (valor >= bom) return "var(--bom)";
  if (valor >= medio) return "var(--medio)";
  return "var(--ruim)";
}

function classeOvr(o) {
  return o >= 80 ? "a" : o >= 72 ? "b" : o >= 64 ? "c" : "d";
}

function ovr(o) { return `<span class="ovr ${classeOvr(o)}">${o}</span>`; }
function pos(p) { return `<span class="pos ${p}">${POSICOES[p] || p}</span>`; }
const POSICOES = {GK: "GOL", DF: "DEF", MF: "MEI", FW: "ATA"};
const POSICOES_LONGAS = {GK: "Goleiro", DF: "Defensor", MF: "Meio-campista", FW: "Atacante"};

function barra(valor, cor, largura) {
  const w = largura ? `style="width:${largura}"` : "";
  return `<span class="barra" ${w}><i style="width:${Math.max(0, Math.min(100, valor))}%;background:${cor}"></i></span>`;
}

function energia(v) {
  return `<span class="celula-barra">${barra(v, corDe(v, 85, 70))}<span class="num">${v}%</span></span>`;
}

function forma(lista) {
  return `<span class="forma">${(lista || []).map((r) => `<i class="${r}">${r}</i>`).join("")}</span>`;
}

// o motor escreve sem acento; a tela, com
const CLIMAS = {"sob observacao": "sob observação", "insustentavel": "insustentável"};
function clima(t) { return CLIMAS[t] || t || ""; }

function sobrenome(nome) {
  const partes = String(nome).split(" ");
  return partes.length > 1 && partes[partes.length - 1].length > 2
    ? partes[partes.length - 1] : nome;
}

/* ------------------------------------------------------------------ icones
 * Desenhados para o jogo, traco simples de 24px. Nenhum vem de biblioteca de marca. */

const ICONES = {
  elenco: '<path d="M8 3 4 5.5 2.5 10l3 1.2V21h13v-9.8l3-1.2L20 5.5 16 3c-.6 1.6-2.2 2.7-4 2.7S8.6 4.6 8 3Z"/>',
  campo: '<rect x="3" y="3" width="18" height="18" rx="1.5"/><path d="M3 12h18"/><circle cx="12" cy="12" r="3"/><path d="M8 3v3.5h8V3M8 21v-3.5h8V21"/>',
  tatica: '<rect x="4.5" y="3.5" width="15" height="18" rx="2"/><path d="M9 2.5h6v3H9z"/><path d="M8 16.5 11.5 12l3 2L17 9.5"/><path d="M14.8 9.4H17v2.2"/><circle cx="8.5" cy="9" r="1"/>',
  mercado: '<path d="M4 8h13l-3.5-3.5M20 16H7l3.5 3.5"/>',
  tabela: '<path d="M7 4h10v4a5 5 0 0 1-10 0V4Z"/><path d="M7 5.5H4.5c0 2.5 1 4 3 4.3M17 5.5h2.5c0 2.5-1 4-3 4.3M12 13v4M8.5 20.5h7M10 17h4v3.5h-4z"/>',
  calendario: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/><path d="M7.5 14h2M11 14h2M14.5 14h2M7.5 17h2M11 17h2"/>',
  financas: '<ellipse cx="9" cy="7" rx="5.5" ry="2.5"/><path d="M3.5 7v4c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V7"/><path d="M9.5 16.3c.9 1.3 3.2 2.2 5.5 2.2 3 0 5.5-1.1 5.5-2.5v-4c0-1.2-1.8-2.2-4.3-2.4"/><path d="M3.5 11v4c0 1.4 2.5 2.5 5.5 2.5"/>',
  mensagens: '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/>',
  treinador: '<circle cx="12" cy="7.5" r="3.5"/><path d="M5 20.5c.6-4 3.4-6.5 7-6.5s6.4 2.5 7 6.5"/><path d="M15.5 13.5 18 11l2 2"/>',
  salvar: '<path d="M5 3.5h11l3.5 3.5v13.5H5z"/><path d="M8 3.5v5h7v-5M8 20.5v-6h8v6"/>',
  sair: '<path d="M14 4h5.5v16H14"/><path d="M10 8l-4 4 4 4M6 12h10"/>',
  jogar: '<path d="M8 5.5v13l10.5-6.5z"/>',
  novo: '<circle cx="12" cy="12" r="8.5"/><path d="M10 8.5v7l5.5-3.5z"/>',
  pasta: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.3l2 2h8.7A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/>',
  lapis: '<path d="M4 20l1-4.5L15.5 5a2 2 0 0 1 3 3L8 18.5z"/><path d="M13.5 7l3 3"/>',
  engrenagem: '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M21.2 12h-2.4M5.2 12H2.8M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7M18.5 18.5l-1.7-1.7M7.2 7.2 5.5 5.5"/><circle cx="12" cy="12" r="6.3"/>',
  medalha: '<circle cx="12" cy="15" r="5.5"/><path d="M8.5 2.5h7L13 9.7M8.5 2.5 11 9.7"/><path d="m12 12.4.9 1.8 2 .3-1.4 1.4.3 2-1.8-.9-1.8.9.3-2-1.4-1.4 2-.3z"/>',
  estrela: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8L3.5 9.7l5.9-.9z"/>',
  desligar: '<path d="M12 3v8"/><path d="M6.6 6.5a7.5 7.5 0 1 0 10.8 0"/>',
  cadeado: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  troca: '<path d="M7 4v14M3.5 14.5 7 18l3.5-3.5M17 20V6M13.5 9.5 17 6l3.5 3.5"/>',
  pausa: '<path d="M8.5 5v14M15.5 5v14"/>',
  relogio: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
  apito: '<circle cx="9" cy="14" r="5"/><path d="M13 11l7.5-4.5v4L14 13"/>',
  olho: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/>',
  bola: '<circle cx="12" cy="12" r="8.5"/><path d="m12 7.5 3.3 2.4-1.3 3.9h-4l-1.3-3.9z"/><path d="M12 3.5v4M15.3 9.9l3.9-1.2M14 13.8l2.3 3.3M10 13.8l-2.3 3.3M8.7 9.9 4.8 8.7"/>',
  pessoa: '<circle cx="12" cy="8" r="4"/><path d="M4.5 21c.7-4.3 3.8-7 7.5-7s6.8 2.7 7.5 7"/>',
};

function icone(nome, extra = "") {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}>${ICONES[nome] || ""}</svg>`;
}

/* ------------------------------------------------------------------ logo
 * A marca e uma prancheta de treinador com o esquema desenhado a giz, e o 11 num selo
 * dourado. Tudo vetor, sem fonte embutida: o texto usa Bahnschrift, que o Windows traz. */

function logo(compacto = false) {
  const prancheta = `
    <g>
      <rect x="6" y="20" width="92" height="122" rx="11" fill="#0f2b1d" stroke="#f3c332" stroke-width="4"/>
      <rect x="16" y="32" width="72" height="100" rx="4" fill="#2f8a4b"/>
      <g fill="none" stroke="#f4f6f0" stroke-width="2.4" stroke-opacity=".9">
        <rect x="22" y="38" width="60" height="88" rx="1"/>
        <path d="M22 82h60"/><circle cx="52" cy="82" r="10"/>
        <path d="M38 38v12h28V38M38 126v-12h28v12"/>
      </g>
      <g stroke="#f3c332" stroke-width="3" stroke-linecap="round" fill="none">
        <path d="M34 106 44 96M34 96l10 10"/>
        <path d="M58 104c6-8 10-14 14-26"/><path d="M66 78h6.5v6.5"/>
      </g>
      <circle cx="46" cy="64" r="5" fill="none" stroke="#f4f6f0" stroke-width="2.6"/>
      <rect x="30" y="6" width="44" height="24" rx="6" fill="#f3c332"/>
      <rect x="44" y="12" width="16" height="7" rx="3" fill="#0f2b1d"/>
    </g>`;
  if (compacto) {
    return `<svg class="logo-p" viewBox="0 0 330 150" role="img" aria-label="PRANCHETA 11">
      ${prancheta}
      <text x="118" y="98" font-family="Bahnschrift, 'Arial Narrow', sans-serif" font-weight="700"
        font-size="58" textLength="202" lengthAdjust="spacingAndGlyphs" fill="#f4f6f0">PRANCHETA</text>
      <rect x="118" y="108" width="54" height="30" rx="5" fill="#f3c332"/>
      <text x="145" y="131" text-anchor="middle" font-family="Bahnschrift, sans-serif" font-weight="700"
        font-size="25" fill="#1b1503">11</text>
    </svg>`;
  }
  return `<svg viewBox="0 0 560 170" role="img" aria-label="PRANCHETA 11">
    <g transform="translate(0 10)">${prancheta}</g>
    <text x="122" y="104" font-family="Bahnschrift, 'Arial Narrow', sans-serif" font-weight="700"
      font-size="76" textLength="428" lengthAdjust="spacingAndGlyphs" fill="#f4f6f0">PRANCHETA</text>
    <rect x="124" y="118" width="92" height="44" rx="7" fill="#f3c332"/>
    <text x="170" y="152" text-anchor="middle" font-family="Bahnschrift, sans-serif" font-weight="700"
      font-size="38" fill="#1b1503">11</text>
    <text x="232" y="148" font-family="Bahnschrift, 'Segoe UI', sans-serif" font-weight="400"
      font-size="19" textLength="318" lengthAdjust="spacing" fill="#a4b8ab">MANAGER DE FUTEBOL</text>
  </svg>`;
}

/* ------------------------------------------------------------------ escudo
 * O escudo oficial so aparece se foi baixado (data/escudos, fora do git). Sem ele, um
 * escudo generico nas cores do clube, com as iniciais -- nunca um desenho que imite
 * o de verdade. */

function iniciais(nome) {
  const partes = String(nome).replace(/[^A-Za-zÀ-ú ]/g, "").split(" ").filter((p) => p.length > 2);
  if (partes.length >= 2) return (partes[0][0] + partes[1][0]).toUpperCase();
  return String(nome).slice(0, 3).toUpperCase();
}

function contraste(hex) {
  const n = parseInt(String(hex || "#000").replace("#", "").padEnd(6, "0").slice(0, 6), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#111" : "#fff";
}

function escudoGerado(c) {
  const a = c.cor || "#2f8a4b";
  const b = c.cor2 || "#ffffff";
  const txt = contraste(a);
  return `<svg viewBox="0 0 40 46" aria-hidden="true">
    <path d="M20 1.5 37.5 7v15c0 11-7.6 18.6-17.5 22.5C10.1 40.6 2.5 33 2.5 22V7z" fill="${a}" stroke="${b}" stroke-width="2.2"/>
    <path d="M6 28.5h28c-2.4 6.7-7.4 11.3-14 14.1C13.4 39.8 8.4 35.2 6 28.5Z" fill="${b}" opacity=".9"/>
    <text x="20" y="22.5" text-anchor="middle" font-family="Bahnschrift, sans-serif" font-weight="700"
      font-size="11" fill="${txt}">${escapar(iniciais(c.nome))}</text>
  </svg>`;
}

function escudo(c, tamanho = "", porNome = false) {
  if (!c) return "";
  const t = tamanho ? `style="--t:${tamanho}"` : "";
  if (c.escudo) {
    const src = porNome ? `/api/escudo/n-${encodeURIComponent(c.nome)}` : `/api/escudo/${c.id}`;
    return `<span class="escudo" ${t}><img src="${src}" alt="" loading="lazy"
      onerror="this.parentNode.innerHTML=this.parentNode.dataset.reserva"></span>`
      .replace('class="escudo"', `class="escudo" data-reserva="${escapar(escudoGerado(c))}"`);
  }
  return `<span class="escudo" ${t}>${escudoGerado(c)}</span>`;
}

/* ------------------------------------------------------------------ camisas */

const cacheDeCamisas = new Map();
async function camisa(clubeId, numero = "1") {
  const chave = `${clubeId}-${numero}`;
  if (!cacheDeCamisas.has(chave)) {
    cacheDeCamisas.set(chave, fetch(`/api/camisa/${clubeId}/${numero}`).then((r) => r.text()));
  }
  return cacheDeCamisas.get(chave);
}

/** Onze camisas na mesma pagina com os mesmos ids fariam todas usarem o recorte da
 *  primeira, e a cor de um jogador vazaria nos outros. */
let contadorDeIds = 0;
function idsProprios(svg) {
  const s = `u${contadorDeIds++}`;
  return svg.replace(/id="([\w-]+)"/g, `id="$1${s}"`)
            .replace(/url\(#([\w-]+)\)/g, `url(#$1${s})`)
            .replace(/href="#([\w-]+)"/g, `href="#$1${s}"`);
}

/** A cor do clube vira ACENTO, e acento precisa se ver sobre o fundo escuro. */
function corDeAcento(hex) {
  const n = parseInt((hex || "#2f8a4b").slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const luz = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  if (luz >= 0.32) return hex;
  const f = luz < 0.05 ? 3.4 : 0.34 / Math.max(luz, 0.02);
  const clarear = (v) => Math.round(Math.min(255, Math.max(v * f, v + 60)));
  return `rgb(${clarear(r)}, ${clarear(g)}, ${clarear(b)})`;
}

/* ------------------------------------------------------------------ janelas */

function abrirJanela({titulo, corpo, botoes = [{rotulo: "Fechar", primario: true}], estreita = false}) {
  const j = $("#janela");
  j.className = `janela${estreita ? " estreita" : ""}`;
  j.innerHTML = `
    <div class="cab"><h2>${titulo}</h2>
      <button class="btn fantasma pequeno" data-fechar>Esc</button></div>
    <div class="corpo">${corpo}</div>
    <div class="pe">${botoes.map((b, i) =>
      `<button class="btn ${b.primario ? "primario" : ""}" data-botao="${i}">${b.rotulo}</button>`).join("")}</div>`;
  $("#cortina").hidden = false;
  return new Promise((resolver) => {
    const fechar = (valor) => { $("#cortina").hidden = true; resolver(valor); };
    $$("[data-botao]", j).forEach((el) => el.addEventListener("click", async () => {
      const b = botoes[+el.dataset.botao];
      if (b.acao) { const r = await b.acao(); if (r === false) return; }
      fechar(b.valor ?? +el.dataset.botao);
    }));
    $("[data-fechar]", j).addEventListener("click", () => fechar(null));
    janelaAberta = () => fechar(null);
  });
}
let janelaAberta = null;
function fecharJanela() {
  if (!$("#cortina").hidden && janelaAberta) { janelaAberta(); janelaAberta = null; return true; }
  return false;
}

function avisar(texto, ms = 2600) {
  // numa pilha: dois gols no mesmo minuto em campos diferentes nao saem um sobre o outro
  let pilha = document.getElementById("toasts");
  if (!pilha) {
    pilha = document.createElement("div");
    pilha.id = "toasts";
    document.body.appendChild(pilha);
  }
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = texto;
  pilha.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

/* ------------------------------------------------------------------ modos
 * O jogo tem seis "modos" de tela cheia: menu, nova carreira, escolha do clube, o jogo,
 * a partida ao vivo e o pos-jogo. Cada um registra como se desenha e o que faz com o
 * teclado. */

const MODOS = {};
let modoAtual = null;

function registrarModo(nome, {elemento, abrir, tecla}) {
  MODOS[nome] = {elemento, abrir, tecla};
}

async function irParaModo(nome, ...args) {
  for (const [n, m] of Object.entries(MODOS)) $(m.elemento).hidden = n !== nome;
  modoAtual = nome;
  if (MODOS[nome].abrir) await MODOS[nome].abrir(...args);
}

document.addEventListener("keydown", (ev) => {
  if (ev.target.matches("input, select, textarea") && ev.key !== "Escape") return;
  if (ev.key === "Escape" && fecharJanela()) { ev.preventDefault(); return; }
  const m = MODOS[modoAtual];
  if (m && m.tecla) m.tecla(ev);
});

/* ------------------------------------------------------------------ configuracoes
 * Preferencias do jogador neste navegador. Nao entram no save: sao da maquina, nao da
 * carreira. */

const CONFIG_PADRAO = {velocidade: "1x", pausarNoGol: true, pausarNoIntervalo: true,
                       perguntarPenalti: true, pausarNaExpulsao: true};
// as velocidades antigas (lenta/normal/rapida/turbo) viram as novas
const VELOCIDADE_ANTIGA = {lenta: "1x", normal: "1x", rapida: "2x", turbo: "4x"};
function config() {
  let c;
  try { c = {...CONFIG_PADRAO, ...JSON.parse(localStorage.getItem("p11-config") || "{}")}; }
  catch { c = {...CONFIG_PADRAO}; }
  if (VELOCIDADE_ANTIGA[c.velocidade]) c.velocidade = VELOCIDADE_ANTIGA[c.velocidade];
  return c;
}
function salvarConfig(c) {
  try { localStorage.setItem("p11-config", JSON.stringify(c)); } catch { /* sem storage */ }
}

/* Erro que escapou vira aviso na tela: melhor que uma tela parada sem explicacao. */
window.addEventListener("error", (ev) => avisar(`Erro: ${ev.message}`, 8000));
window.addEventListener("unhandledrejection", (ev) => avisar(`Erro: ${ev.reason && ev.reason.message || ev.reason}`, 8000));
