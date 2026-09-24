"use strict";
/* A partida ao vivo e o pos-jogo.
 *
 * O servidor joga em blocos de 5 minutos e PARA no fim de cada um, esperando a ordem
 * seguinte. O navegador anda o relogio minuto a minuto dentro do bloco que ja recebeu,
 * revelando os lances na hora deles. Pausar e so parar este relogio; trocas e tatica
 * pedidas na pausa seguem junto com o pedido do proximo bloco -- ou seja, valem a partir
 * do fim do bloco em curso, e a tela diz o minuto. */

const VIVO = {
  s: null, anterior: null,      // retrato atual (ate o fim do bloco) e o do bloco anterior
  relogio: 0, pausado: false, motivo: "", esperando: false,
  fila: [], taticaPendente: null, visiveis: 0, timer: null,
  gaveta: null, aba: "rodada", fimVisto: false, intervaloVisto: false, segurarAte: 0,
};

const VELOCIDADES = {lenta: 900, normal: 420, rapida: 160, turbo: 45};

async function abrirAoVivo() {
  Object.assign(VIVO, {s: null, anterior: null, relogio: 0, pausado: false, motivo: "", esperando: false,
                       fila: [], taticaPendente: null, visiveis: 0, gaveta: null, aba: "rodada",
                       fimVisto: false, intervaloVisto: false, segurarAte: 0});
  $("#ao-vivo").innerHTML = `<div class="carregando">Entrando em campo…</div>`;
  const s = await api.post("/api/partida/iniciar");
  if (s.erro) {
    avisar(s.erro);
    if (s.fim_de_temporada) return irParaModo("jogo");
    return irParaModo("jogo");
  }
  if (s.sem_jogo) return dataSemJogo(s);
  VIVO.s = s;
  VIVO.anterior = s;
  // retomando um jogo em andamento (a pagina foi recarregada): o relogio volta so ao
  // comeco do bloco atual, nao ao apito inicial
  if (s.minuto > 5) VIVO.relogio = s.fim ? 90 : s.minuto - 5;
  VIVO.intervaloVisto = VIVO.relogio >= 45;
  montarAoVivo();
  pintar();
  tocar();
  if (PARAMS.get("gaveta")) abrirGaveta(PARAMS.get("gaveta"));
}

async function dataSemJogo(s) {
  if (s.estado) aplicarEstado(s.estado);
  await abrirJanela({titulo: escapar(s.competicao || "Resultados da data"), corpo: `
    <p class="dica">O seu clube não entrou em campo nesta data.</p>
    <table class="grade compacta"><tbody>${(s.resultados || []).map((r) => `
      <tr><td style="text-align:right"><div class="nome-celula" style="justify-content:flex-end">${escapar(r.casa.nome)} ${escudo(r.casa, "1.3rem")}</div></td>
        <td class="c"><b class="num">${r.gols_casa} x ${r.gols_fora}</b></td>
        <td><div class="nome-celula">${escudo(r.fora, "1.3rem")} ${escapar(r.fora.nome)}</div></td></tr>`).join("")}</tbody></table>`,
    botoes: [{rotulo: "Continuar ›", primario: true}]});
  irParaModo("jogo");
}

/* ------------------------------------------------------------------ montagem */

function montarAoVivo() {
  const s = VIVO.s;
  const eu = s.meu_lado;
  $("#ao-vivo").innerHTML = `
    <header class="placar-vivo">
      <div class="time casa">${escudo(s.casa, "3.6rem")}<div><h2 class="${eu === "casa" ? "meu" : ""}">${escapar(s.casa.nome)}</h2><small>mandante</small></div></div>
      <div class="centro">
        <div class="comp">${escapar(s.competicao)}</div>
        <div class="gols" id="v-gols">0 × 0</div>
        <div class="relogio" id="v-relogio">0'</div>
      </div>
      <div class="time fora">${escudo(s.fora, "3.6rem")}<div><h2 class="${eu === "fora" ? "meu" : ""}">${escapar(s.fora.nome)}</h2><small>visitante</small></div></div>
    </header>
    <div class="progresso" id="v-progresso"><i style="width:0"></i><span class="meio"></span></div>
    <div class="vivo-corpo">
      <div class="coluna">
        <div class="painel"><div class="cab"><h2>Estatísticas</h2></div><div class="corpo" id="v-stats"></div></div>
      </div>
      <div class="painel"><div class="cab"><h2>Lance a lance</h2><span class="dica" id="v-parada"></span></div>
        <div class="corpo sem-margem feed" id="v-feed"></div></div>
      <div class="coluna">
        <div class="painel">
          <div class="cab"><div class="abas" id="v-abas">
            <button data-vaba="rodada">Rodada</button><button data-vaba="meu">Meu time</button><button data-vaba="rival">Adversário</button></div></div>
          <div class="corpo sem-margem" id="v-lateral"></div>
        </div>
      </div>
      <div id="v-selo"></div>
    </div>
    <footer class="controles">
      <div class="grupo"><button class="btn primario" id="v-pausa">${icone("pausa")} Pausar</button><span class="tecla">ESPAÇO</span></div>
      <div class="grupo"><button class="btn azul" id="v-subs">${icone("troca")} Substituições <b id="v-conta"></b></button><span class="tecla">S</span></div>
      <div class="grupo"><button class="btn" id="v-tatica">${icone("tatica")} Tática</button><span class="tecla">T</span></div>
      <span class="espaco"></span>
      <div class="grupo">${icone("relogio", 'style="width:1rem;height:1rem"')} Velocidade
        <div class="segmentado" id="v-vel" style="width:17rem">${Object.keys(VELOCIDADES).map((v) =>
          `<button data-vel="${v}" class="${config().velocidade === v ? "ativo" : ""}">${{lenta: "Lenta", normal: "Normal", rapida: "Rápida", turbo: "Turbo"}[v]}</button>`).join("")}</div></div>
      <button class="btn" id="v-fim">Ir para o fim ›</button>
      <button class="btn primario" id="v-sumula" hidden>Ver súmula ›</button>
    </footer>`;
  $("#v-pausa").addEventListener("click", alternarPausa);
  $("#v-subs").addEventListener("click", () => abrirGaveta("subs"));
  $("#v-tatica").addEventListener("click", () => abrirGaveta("tatica"));
  $("#v-fim").addEventListener("click", irProFim);
  $("#v-sumula").addEventListener("click", () => irParaModo("posjogo"));
  $$("[data-vel]").forEach((b) => b.addEventListener("click", () => {
    salvarConfig({...config(), velocidade: b.dataset.vel});
    $$("[data-vel]").forEach((x) => x.classList.toggle("ativo", x === b));
    tocar();
  }));
  $$("[data-vaba]").forEach((b) => b.addEventListener("click", () => { VIVO.aba = b.dataset.vaba; pintarLateral(); }));
}

/* ------------------------------------------------------------------ relogio */

function tocar() {
  clearInterval(VIVO.timer);
  VIVO.timer = setInterval(passo, VELOCIDADES[config().velocidade] || 420);
}

async function passo() {
  const s = VIVO.s;
  if (!s || VIVO.pausado || VIVO.esperando || VIVO.gaveta) return;
  if (Date.now() < VIVO.segurarAte) return;
  if (VIVO.relogio < s.minuto) {
    VIVO.relogio++;
    pintar();
    if (VIVO.relogio === 45 && !VIVO.intervaloVisto && s.minuto >= 45 && config().pausarNoIntervalo && !s.fim) {
      VIVO.intervaloVisto = true;
      pausar("INTERVALO", "Fim do 1º tempo · ESPAÇO para o 2º tempo");
    }
    return;
  }
  if (s.fim) {
    if (!VIVO.fimVisto) terminou();
    return;
  }
  // o relogio alcancou o fim do bloco: pede o proximo, levando as decisoes da pausa
  VIVO.esperando = true;
  const corpo = {trocas: VIVO.fila.map((t) => [t.sai.id, t.entra.id])};
  if (VIVO.taticaPendente) corpo.tatica = VIVO.taticaPendente;
  const novo = await api.post("/api/partida/seguir", corpo);
  VIVO.esperando = false;
  if (novo.erro && !novo.minuto) { avisar(novo.erro); return; }
  if (VIVO.fila.length) avisar(`${VIVO.fila.length} substituição(ões) feita(s) aos ${s.minuto}'`);
  if (VIVO.taticaPendente) avisar(`Tática alterada aos ${s.minuto}'`);
  VIVO.fila = [];
  VIVO.taticaPendente = null;
  VIVO.anterior = VIVO.s;
  VIVO.s = novo;
  pintar();
}

function pausar(titulo, sub) {
  VIVO.pausado = true;
  VIVO.motivo = titulo;
  $("#v-selo").innerHTML = `<div class="selo">${titulo}<small>${sub || "ESPAÇO para continuar"}</small></div>`;
  $("#v-pausa").innerHTML = `${icone("jogar")} Continuar`;
}

function alternarPausa() {
  if (VIVO.fimVisto) return irParaModo("posjogo");
  if (VIVO.pausado) {
    VIVO.pausado = false;
    $("#v-selo").innerHTML = "";
    $("#v-pausa").innerHTML = `${icone("pausa")} Pausar`;
  } else {
    pausar("PAUSADO");
  }
}

async function irProFim() {
  if (VIVO.s.fim) { VIVO.relogio = 90; pintar(); return; }
  VIVO.esperando = true;
  const corpo = {ate_o_fim: true, trocas: VIVO.fila.map((t) => [t.sai.id, t.entra.id])};
  if (VIVO.taticaPendente) corpo.tatica = VIVO.taticaPendente;
  const novo = await api.post("/api/partida/seguir", corpo);
  VIVO.esperando = false;
  VIVO.fila = [];
  VIVO.taticaPendente = null;
  VIVO.anterior = VIVO.s;
  VIVO.s = novo;
  VIVO.relogio = 90;
  VIVO.pausado = false;
  $("#v-selo").innerHTML = "";
  pintar();
}

function terminou() {
  VIVO.fimVisto = true;
  clearInterval(VIVO.timer);
  if (VIVO.s.estado) aplicarEstado(VIVO.s.estado);
  onzeLocal = null;
  const s = VIVO.s;
  const meus = s.meu_lado === "casa" ? s.gols_casa : s.gols_fora;
  const deles = s.meu_lado === "casa" ? s.gols_fora : s.gols_casa;
  const r = meus > deles ? "VITÓRIA" : meus === deles ? "EMPATE" : "DERROTA";
  $("#v-selo").innerHTML = `<div class="selo">FIM DE JOGO<small>${r} · ENTER para a súmula</small></div>`;
  $("#v-pausa").hidden = true;
  $("#v-fim").hidden = true;
  $("#v-subs").disabled = true;
  $("#v-tatica").disabled = true;
  $("#v-sumula").hidden = false;
}

/* ------------------------------------------------------------------ pintura */

function eventosVisiveis() {
  return VIVO.s.eventos.filter((e) => e.minuto <= VIVO.relogio);
}

function pintar() {
  const s = VIVO.s;
  const vis = eventosVisiveis();
  const gc = vis.filter((e) => e.tipo === "gol" && e.lado === "casa").length;
  const gf = vis.filter((e) => e.tipo === "gol" && e.lado === "fora").length;
  const placar = $("#v-gols");
  const novoPlacar = `${gc} × ${gf}`;
  if (placar.textContent !== novoPlacar) {
    placar.textContent = novoPlacar;
    if (VIVO.relogio > 0) {
      placar.classList.remove("flash"); void placar.offsetWidth; placar.classList.add("flash");
      if (config().pausarNoGol && !VIVO.fimVisto) VIVO.segurarAte = Date.now() + 1800;
    }
  }
  const tempo = VIVO.relogio > 45 ? "2º tempo" : "1º tempo";
  $("#v-relogio").innerHTML = `${VIVO.relogio}'<small>${VIVO.relogio >= 90 && s.fim ? "encerrado" : tempo}</small>`;
  const prog = $("#v-progresso");
  prog.querySelector("i").style.width = `${(VIVO.relogio / 90) * 100}%`;
  prog.querySelectorAll(".marca-gol").forEach((m) => m.remove());
  for (const e of vis.filter((x) => x.tipo === "gol")) {
    const lado = e.lado === "casa" ? s.casa : s.fora;
    prog.insertAdjacentHTML("beforeend",
      `<span class="marca-gol" style="left:${(e.minuto / 90) * 100}%;background:${lado.cor};color:${contraste(lado.cor)}">${e.minuto}</span>`);
  }
  const falta = s.fim ? "" : `próxima parada técnica: ${s.minuto}'`;
  $("#v-parada").textContent = falta;
  $("#v-conta").textContent = `${s.trocas_feitas + VIVO.fila.length}/${s.max_trocas}`;
  pintarFeed(vis);
  // estatisticas e rodada andam por bloco: mostram o bloco fechado mais recente
  const fechado = VIVO.relogio >= s.minuto ? s : VIVO.anterior;
  pintarStats(fechado);
  pintarLateral(fechado);
}

const ICONE_LANCE = {gol: "⚽", amarelo: '<span class="cartao am" style="width:.72rem;height:1rem"></span>',
                     vermelho: '<span class="cartao vm" style="width:.72rem;height:1rem"></span>', substituicao: "⇅", defesa: "✋", chute: "↗",
                     escanteio: "⚑", impedimento: "⚐", falta: "!"};

function pintarFeed(vis) {
  const s = VIVO.s;
  const feed = $("#v-feed");
  if (vis.length === VIVO.visiveis && feed.childElementCount) return;
  VIVO.visiveis = vis.length;
  const nomeDoLado = (l) => (l === "casa" ? s.casa : s.fora);
  const linhas = [];
  linhas.push(`<div class="lance marco"><span class="min">0'</span><span class="ic">${icone("apito")}</span>
    <span class="txt">Começa a partida</span></div>`);
  let intervalo = false;
  for (const e of vis) {
    if (!intervalo && e.minuto > 45) {
      linhas.push(`<div class="lance marco"><span class="min">45'</span><span class="ic">${icone("apito")}</span><span class="txt">Intervalo · começa o 2º tempo</span></div>`);
      intervalo = true;
    }
    const clube = nomeDoLado(e.lado);
    let txt = escapar(e.texto);
    let sub = `<span class="lado" style="background:${clube.cor}"></span>${escapar(clube.nome)}`;
    if (e.tipo === "gol") {
      const assist = e.segundo ? nomeDoJogador(e.segundo) : null;
      txt = `GOL! ${escapar(nomeDoJogador(e.jogador) || e.texto.replace("GOL! ", ""))}`;
      if (assist) sub += ` · assistência de ${escapar(assist)}`;
    }
    linhas.push(`<div class="lance ${e.tipo}"><span class="min">${e.minuto}'</span>
      <span class="ic">${ICONE_LANCE[e.tipo] ?? ""}</span><span class="txt">${txt}<small>${sub}</small></span></div>`);
  }
  if (VIVO.relogio >= 90 && s.fim) {
    linhas.push(`<div class="lance marco"><span class="min">90'</span><span class="ic">${icone("apito")}</span><span class="txt">Fim de jogo</span></div>`);
  }
  feed.innerHTML = linhas.reverse().join("");
}

function nomeDoJogador(id) {
  const s = VIVO.s;
  const todos = [...s.escalacao_casa, ...s.escalacao_fora, ...s.banco];
  return todos.find((j) => j.id === id)?.nome;
}

/** Seu time e sempre ouro e o rival sempre cinza: com as cores dos clubes, Vitoria x
 *  Flamengo virava vermelho contra vermelho. */
function coresDosLados(meuLado) {
  return meuLado === "casa" ? ["var(--ouro)", "var(--cinza-claro)"] : ["var(--cinza-claro)", "var(--ouro)"];
}

function pintarStats(s) {
  const [cc, cf] = coresDosLados(VIVO.s.meu_lado);
  $("#v-stats").innerHTML = s.estatisticas.map(([nome, a, b]) => {
    const na = parseFloat(a) || 0, nb = parseFloat(b) || 0;
    const tot = na + nb || 1;
    return `<div class="stat-linha"><span class="nome-stat">${nome}</span><b>${a}</b>
      <span class="duas"><i style="width:${100 * na / tot}%;background:${cc}"></i>
        <i style="width:${100 * nb / tot}%;background:${cf}"></i></span><b>${b}</b></div>`;
  }).join("");
}

function pintarLateral(fechado) {
  fechado = fechado || (VIVO.relogio >= VIVO.s.minuto ? VIVO.s : VIVO.anterior);
  const s = VIVO.s;
  $$("[data-vaba]").forEach((b) => b.classList.toggle("ativo", b.dataset.vaba === VIVO.aba));
  const alvo = $("#v-lateral");
  if (VIVO.aba === "rodada") {
    const minha = {casa: s.casa.nome, fora: s.fora.nome,
                   gols_casa: +$("#v-gols").textContent.split("×")[0], gols_fora: +$("#v-gols").textContent.split("×")[1], meu: true};
    const jogos = [minha, ...fechado.rodada];
    alvo.innerHTML = `<div class="rodada-vivo">${jogos.map((j) => `
      <div class="jogo ${j.meu ? "meu" : ""} ${j.mudou ? "mudou" : ""}"><span>${escapar(j.casa)}</span>
        <b>${j.gols_casa} - ${j.gols_fora}</b><span>${escapar(j.fora)}</span></div>`).join("")}</div>
      <p class="nota-honesta" style="margin:.7rem">Os outros placares são decididos pelo motor rápido; o minuto de cada gol é ilustrativo.</p>`;
    return;
  }
  const meu = s.meu_lado;
  const lado = VIVO.aba === "meu" ? meu : (meu === "casa" ? "fora" : "casa");
  const lista = s[`escalacao_${lado}`];
  const vistos = new Set(eventosVisiveis().map((e) => e.jogador));
  alvo.innerHTML = `<div class="escalacao-vivo">${lista.map((j) => {
    const expulso = j.expulso && vistos.has(j.id);
    return `<div class="j ${j.em_campo && !expulso ? "" : "fora-de-campo"}">${pos(j.posicao)}
      <span class="nm">${escapar(j.nome)}${j.entrou_aos ? ` <span class="dica">(${j.entrou_aos}')</span>` : ""}</span>
      <span>${j.amarelo && vistos.has(j.id) ? '<span class="cartao am"></span>' : ""}${expulso ? '<span class="cartao vm"></span>' : ""}</span>
      <span class="en">${barra(j.energia, corDe(j.energia, 80, 62))}${j.energia}</span></div>`;
  }).join("")}</div>`;
}

/* ------------------------------------------------------------------ gavetas */

let subSai = null, subEntra = null;

function abrirGaveta(qual) {
  if (VIVO.fimVisto) return;
  VIVO.gaveta = qual;
  subSai = subEntra = null;
  pintarGaveta();
}

function fecharGaveta() {
  VIVO.gaveta = null;
  $("#gaveta-slot").innerHTML = "";
  pintar();
}

function pintarGaveta() {
  const s = VIVO.s;
  if (VIVO.gaveta === "subs") {
    const meus = s[`escalacao_${s.meu_lado}`];
    const vaiSair = new Set(VIVO.fila.map((t) => t.sai.id));
    const vaiEntrar = new Set(VIVO.fila.map((t) => t.entra.id));
    const emCampo = meus.filter((j) => j.em_campo);
    const usadas = s.trocas_feitas + VIVO.fila.length;
    const esgotou = usadas >= s.max_trocas;
    $("#gaveta-slot").innerHTML = `<aside class="gaveta">
      <div class="cab"><h2>Substituições</h2><span class="contador-trocas">${usadas}/${s.max_trocas}</span>
        <button class="btn fantasma pequeno" id="g-fechar">Esc</button></div>
      <div class="corpo">
        ${VIVO.fila.length ? `<div class="fila-trocas">${VIVO.fila.map((t, i) => `<div class="troca">
          <span class="ruim">▼ ${escapar(t.sai.nome)}</span><span class="bom">▲ ${escapar(t.entra.nome)}</span>
          <span class="espaco"></span><button class="btn pequeno fantasma" data-desfaz="${i}">desfazer</button></div>`).join("")}</div>` : ""}
        <div class="subs">
          <div><h3>Em campo · sai</h3>${emCampo.map((j) => `<div class="j ${subSai === j.id ? "sel" : ""} ${vaiSair.has(j.id) || esgotou ? "bloq" : ""}" data-sai="${j.id}">
            ${pos(j.posicao)}<span class="nm">${escapar(j.nome)}</span>${ovr(j.overall)}
            <span class="en" style="color:${corDe(j.energia, 80, 62)}">${j.energia}%</span></div>`).join("")}</div>
          <div><h3>Banco · entra</h3>${s.banco.map((j) => `<div class="j ${subEntra === j.id ? "sel" : ""} ${vaiEntrar.has(j.id) || esgotou ? "bloq" : ""}" data-entra="${j.id}">
            ${pos(j.posicao)}<span class="nm">${escapar(j.nome)}</span>${ovr(j.overall)}
            <span class="en" style="color:${corDe(j.energia, 85, 70)}">${j.energia}%</span></div>`).join("") || '<div class="vazio">Banco vazio.</div>'}</div>
        </div>
        <p class="nota-honesta">A energia em campo cai com o minuto, o fôlego e a energia com que o jogador entrou.
          As trocas entram na próxima parada técnica (${s.minuto}'). Quem sai não volta.</p>
      </div>
      <div class="pe"><span class="dica">Escolha quem sai e quem entra</span><span class="espaco"></span>
        <button class="btn azul" id="g-add" ${subSai && subEntra && !esgotou ? "" : "disabled"}>Adicionar troca</button>
        <button class="btn primario" id="g-ok">Confirmar <span class="tecla">ENTER</span></button></div>
    </aside>`;
    $$("[data-sai]").forEach((el) => el.addEventListener("click", () => {
      if (el.classList.contains("bloq")) return;
      subSai = +el.dataset.sai; pintarGaveta();
    }));
    $$("[data-entra]").forEach((el) => el.addEventListener("click", () => {
      if (el.classList.contains("bloq")) return;
      subEntra = +el.dataset.entra; pintarGaveta();
    }));
    $$("[data-desfaz]").forEach((el) => el.addEventListener("click", () => {
      VIVO.fila.splice(+el.dataset.desfaz, 1); pintarGaveta();
    }));
    $("#g-add").addEventListener("click", adicionarTroca);
  } else {
    const t = VIVO.taticaPendente || s.tatica;
    const seg = (campo, opcoes, rotulos) => `<div class="segmentado" data-gt="${campo}">${opcoes.map((o) =>
      `<button data-v="${o}" class="${t[campo] === o ? "ativo" : ""}">${rotulos[o] || o}</button>`).join("")}</div>`;
    $("#gaveta-slot").innerHTML = `<aside class="gaveta">
      <div class="cab"><h2>Tática durante o jogo</h2><button class="btn fantasma pequeno" id="g-fechar">Esc</button></div>
      <div class="corpo tatica-grade">
        <div class="linha-t"><span>Mentalidade</span>${seg("estilo", ["retrancado", "defensivo", "equilibrado", "ofensivo", "all-out"],
          {retrancado: "Retranca", defensivo: "Defensiva", equilibrado: "Equilíbrio", ofensivo: "Ofensiva", "all-out": "Tudo"})}</div>
        <div class="linha-t"><span>Marcação</span>${seg("marcacao", ["leve", "normal", "forte"], {leve: "Leve", normal: "Normal", forte: "Pressão alta"})}</div>
        <div class="linha-t"><span>Formação</span>${seg("formacao", ["4-3-3", "4-4-2", "4-2-3-1", "4-5-1", "3-5-2", "3-4-3", "5-3-2"], {})}</div>
        <div class="efeito">${efeitoDaTatica(t)}</div>
        <p class="nota-honesta">A mudança vale a partir da próxima parada técnica (${s.minuto}') e só para esta partida.</p>
      </div>
      <div class="pe"><span class="espaco"></span><button class="btn primario" id="g-ok">Confirmar <span class="tecla">ENTER</span></button></div>
    </aside>`;
    $$("[data-gt] button").forEach((b) => b.addEventListener("click", () => {
      VIVO.taticaPendente = {...(VIVO.taticaPendente || s.tatica), [b.parentNode.dataset.gt]: b.dataset.v};
      pintarGaveta();
    }));
  }
  $("#g-fechar").addEventListener("click", fecharGaveta);
  $("#g-ok").addEventListener("click", confirmarGaveta);
}

function adicionarTroca() {
  const s = VIVO.s;
  const meus = s[`escalacao_${s.meu_lado}`];
  const sai = meus.find((j) => j.id === subSai);
  const entra = s.banco.find((j) => j.id === subEntra);
  if (!sai || !entra) return;
  VIVO.fila.push({sai, entra});
  subSai = subEntra = null;
  pintarGaveta();
}

function confirmarGaveta() {
  if (VIVO.gaveta === "subs" && subSai && subEntra) adicionarTroca();
  if (VIVO.gaveta === "subs" && VIVO.fila.length) avisar(`${VIVO.fila.length} troca(s) entram aos ${VIVO.s.minuto}'`);
  fecharGaveta();
}

registrarModo("aovivo", {
  elemento: "#ao-vivo", abrir: abrirAoVivo,
  tecla(ev) {
    if (!VIVO.s) return;
    const k = ev.key.toLowerCase();
    if (VIVO.gaveta) {
      if (ev.key === "Escape") fecharGaveta();
      if (ev.key === "Enter") confirmarGaveta();
      return;
    }
    if (ev.key === " ") { alternarPausa(); ev.preventDefault(); }
    else if (k === "s") abrirGaveta("subs");
    else if (k === "t") abrirGaveta("tatica");
    else if (ev.key === "Enter" && VIVO.fimVisto) irParaModo("posjogo");
    else if (ev.key === "Escape" && VIVO.pausado && !VIVO.fimVisto) alternarPausa();
  },
});

/* ================================================================== POS-JOGO */

function classeNota(n) { return n >= 8 ? "n8" : n >= 7 ? "n7" : n >= 6 ? "n6" : n >= 5 ? "n5" : "n4"; }

async function abrirPosJogo() {
  clearInterval(VIVO.timer);
  const p = await api.get("/api/posjogo");
  if (p.erro) { avisar(p.erro); return irParaModo("jogo"); }
  if (!ESTADO) aplicarEstado(await api.get("/api/estado"));
  const meuLado = p.casa.id === ESTADO.clube.id ? "casa" : "fora";
  const meus = meuLado === "casa" ? p.gols_casa : p.gols_fora;
  const deles = meuLado === "casa" ? p.gols_fora : p.gols_casa;
  const res = meus > deles ? ["VITÓRIA", "bom"] : meus === deles ? ["EMPATE", "medio"] : ["DERROTA", "ruim"];
  const time = (lista, titulo) => `<div class="painel"><div class="cab"><h2>${escapar(titulo)}</h2></div>
    <div class="corpo sem-margem"><table class="grade compacta"><tbody>${lista.map((j) => `
      <tr class="${j.entrou_aos ? "reserva" : ""}"><td>${pos(j.posicao)}</td>
        <td><b>${escapar(j.nome)}</b>${j.entrou_aos ? ` <span class="dica">${j.entrou_aos}'</span>` : ""}
          ${"⚽".repeat(j.gols)}${j.amarelo ? ' <span class="cartao am"></span>' : ""}${j.vermelho ? ' <span class="cartao vm"></span>' : ""}</td>
        <td class="n"><span class="nota ${classeNota(j.nota)}">${j.nota.toFixed(1).replace(".", ",")}</span></td></tr>`).join("")}
    </tbody></table></div></div>`;
  const evs = p.eventos.map((e) => {
    const conteudo = `<b>${escapar(e.texto.replace("GOL! ", ""))}</b>${e.assistencia ? `<small>assist. ${escapar(e.assistencia)}</small>` : ""}`;
    const ic = {gol: "⚽", amarelo: '<span class="cartao am"></span>', vermelho: '<span class="cartao vm"></span>', substituicao: "⇅"}[e.tipo];
    return `<div class="ev ${e.tipo}"><span class="casa">${e.lado === "casa" ? `${conteudo} ${ic}` : ""}</span>
      <span class="m">${e.minuto}'</span><span>${e.lado === "fora" ? `${ic} ${conteudo}` : ""}</span></div>`;
  }).join("") || '<div class="vazio">Sem lances para a súmula.</div>';
  const [cc, cf] = coresDosLados(meuLado);
  const cmp = p.estatisticas.map(([nome, a, b, suf]) => {
    const tot = (a + b) || 1;
    return `<div class="cmp"><span class="rot">${nome}</span><b>${a}${suf}</b>
      <span class="stat-linha" style="margin:0;display:block"><span class="duas"><i style="width:${100 * a / tot}%;background:${cc}"></i>
      <i style="width:${100 * b / tot}%;background:${cf}"></i></span></span><b>${b}${suf}</b></div>`;
  }).join("");
  $("#pos-jogo").innerHTML = `
    <header class="pos-cab">
      <div class="time casa">${escudo(p.casa, "3.6rem")}<h2>${escapar(p.casa.nome)}</h2></div>
      <div class="placar"><small>${escapar(p.competicao)}</small>${p.gols_casa} × ${p.gols_fora}
        <span class="res ${res[1]}">${res[0]}</span></div>
      <div class="time fora">${escudo(p.fora, "3.6rem")}<h2>${escapar(p.fora.nome)}</h2></div>
    </header>
    <div class="pos-corpo">
      ${time(p.time_casa, p.casa.nome)}
      <div class="coluna">
        <div class="painel"><div class="cab"><h2>Súmula</h2>
          ${p.melhor_em_campo ? `<span class="chip ouro">Craque do jogo: ${escapar(p.melhor_em_campo.nome)} · ${p.melhor_em_campo.nota.toFixed(1).replace(".", ",")}</span>` : ""}</div>
          <div class="corpo linha-tempo">${evs}</div></div>
        <div class="painel fixo"><div class="cab"><h2>Estatísticas</h2></div><div class="corpo comparativo">${cmp}</div></div>
      </div>
      ${time(p.time_fora, p.fora.nome)}
      <div class="painel"><div class="cab"><h2>Rodada</h2></div>
        <div class="corpo sem-margem rodada-vivo">${p.rodada.map((r) => `
          <div class="jogo ${r.meu ? "meu" : ""}"><span>${escapar(r.casa.nome)}</span><b>${r.gols_casa} - ${r.gols_fora}</b><span>${escapar(r.fora.nome)}</span></div>`).join("")}</div>
        <div class="pe"><span class="dica">Notas derivadas dos lances e do placar</span></div></div>
    </div>
    <footer class="fluxo-pe"><span class="dica">${escapar(ESTADO.aprovacao.clima ? `Ambiente no clube: ${clima(ESTADO.aprovacao.clima)}` : "")}</span>
      <span class="espaco"></span><button class="btn primario grande" id="pos-continuar">Continuar »</button></footer>`;
  $("#pos-continuar").addEventListener("click", () => irParaModo("jogo"));
}

registrarModo("posjogo", {
  elemento: "#pos-jogo", abrir: abrirPosJogo,
  tecla(ev) { if (ev.key === "Enter" || ev.key === " ") { irParaModo("jogo"); ev.preventDefault(); } },
});

/* ================================================================== COMECO */

(async function comecar() {
  const m = await api.get("/api/menu");
  const pedido = PARAMS.get("modo");
  if (pedido && MODOS[pedido] && (m.carreira || ["menu", "nova", "clube"].includes(pedido))) {
    return irParaModo(pedido);
  }
  if (PARAMS.get("tela") && m.carreira) return irParaModo("jogo", PARAMS.get("tela"));
  irParaModo("menu");
})();
