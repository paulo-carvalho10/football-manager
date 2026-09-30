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
  // o que ja foi mostrado uma vez: penaltis (suspense), expulsoes (pausa), gols da rodada
  vistos: new Set(), suspense: null, flash: {}, escolhendoPenalti: false,
};

// ms por minuto de jogo; o "instantaneo" e o botao que vai direto ao fim
const VELOCIDADES = {"1x": 420, "2x": 200, "4x": 80};

async function abrirAoVivo() {
  Object.assign(VIVO, {s: null, anterior: null, relogio: 0, pausado: false, motivo: "", esperando: false,
                       fila: [], taticaPendente: null, visiveis: 0, gaveta: null, aba: "rodada",
                       fimVisto: false, intervaloVisto: false, segurarAte: 0,
                       vistos: new Set(), suspense: null, flash: {}, escolhendoPenalti: false,
                       emDisputa: false, disputaVista: false});
  $("#ao-vivo").innerHTML = `<div class="carregando">Entrando em campo…</div>`;
  const s = await api.post("/api/partida/iniciar", {perguntar_penalti: config().perguntarPenalti});
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
  marcarComoVisto();
  montarAoVivo();
  pintar();
  tocar();
  if (PARAMS.get("gaveta")) abrirGaveta(PARAMS.get("gaveta"));
  if (PARAMS.get("irfim")) irProFim();          // atalho de foto: o fim e a disputa
}

async function dataSemJogo(s) {
  if (s.estado) aplicarEstado(s.estado);
  const escolha = await abrirJanela({titulo: escapar(s.competicao || "Resultados da data"), corpo: `
    <p class="dica">O seu clube não entrou em campo nesta data.</p>
    <table class="grade compacta"><tbody>${(s.resultados || []).map((r) => `
      <tr><td style="text-align:right"><div class="nome-celula" style="justify-content:flex-end">${escapar(r.casa.nome)} ${escudo(r.casa, "1.3rem")}</div></td>
        <td class="c"><b class="num">${r.gols_casa} x ${r.gols_fora}</b></td>
        <td><div class="nome-celula">${escudo(r.fora, "1.3rem")} ${escapar(r.fora.nome)}</div></td></tr>`).join("")}</tbody></table>`,
    botoes: [{rotulo: "Ver tabela", valor: "tabela"}, {rotulo: "Continuar ›", primario: true, valor: "ok"}]});
  irParaModo("jogo", escolha === "tabela" ? "classificacao" : undefined);
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
            <button data-vaba="rodada">Central</button><button data-vaba="meu">Meu time</button><button data-vaba="rival">Adversário</button></div></div>
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
        <div class="segmentado velocidades" id="v-vel">${Object.keys(VELOCIDADES).map((v) =>
          `<button data-vel="${v}" title="${v}" class="${config().velocidade === v ? "ativo" : ""}">${{"1x": "▶", "2x": "▶▶", "4x": "▶▶▶"}[v]}</button>`).join("")}
          <button id="v-fim" title="Instantâneo: vai direto ao fim">⏭</button></div></div>
      <button class="btn primario" id="v-sumula" hidden>Continuar ›</button>
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
    if (VIVO.fimVisto || VIVO.emDisputa) return;
    // empate no agregado: a disputa de penaltis antes do fim de jogo
    if (s.disputa && !VIVO.disputaVista) return disputaDePenaltis(s);
    terminou();
    return;
  }
  // o motor parou NO penalti do meu time: o treinador escolhe o batedor
  if (s.penalti) {
    if (!VIVO.escolhendoPenalti) escolherPenalti();
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
  if (VIVO.s.fim) { VIVO.relogio = 90; marcarComoVisto(); pintar(); return; }
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
  VIVO.suspense = null;
  $("#v-selo").innerHTML = "";
  marcarComoVisto();      // no instantaneo nada de suspense nem pausa: vai ao resultado
  pintar();
}

/* ------------------------------------------------------------------ disputa de penaltis
 * O resultado ja saiu do servidor; a tela revela cobranca a cobranca, no ritmo da
 * velocidade escolhida. */

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

async function disputaDePenaltis(s) {
  VIVO.emDisputa = true;
  const ritmo = {"1x": 1, "2x": 0.55, "4x": 0.3}[config().velocidade] || 1;
  const d = s.disputa;
  const bolas = {casa: [], fora: []};
  const clube = (l) => (l === "casa" ? s.casa : s.fora);
  const painel = document.createElement("div");
  painel.className = "disputa";
  $("#ao-vivo").appendChild(painel);
  const linha = (l) => {
    const n = Math.max(5, bolas.casa.length, bolas.fora.length);
    const cel = Array.from({length: n}, (_, i) => {
      const b = bolas[l][i];
      return `<span class="bola ${b === undefined ? "" : b ? "gol" : "erro"}"></span>`;
    }).join("");
    const g = bolas[l].filter(Boolean).length;
    return `<div class="linha-d">${escudo(clube(l), "1.8rem")}<b class="nm">${escapar(clube(l).nome)}</b>
      <span class="bolas">${cel}</span><b class="placar-d">${g}</b></div>`;
  };
  const pintarDisputa = (msg, classe = "") => {
    painel.innerHTML = `<h2>DISPUTA DE PÊNALTIS</h2>${linha("casa")}${linha("fora")}
      <div class="msg-d ${classe}">${msg}</div>`;
  };
  pintarDisputa(`${escapar(clube(d.primeiro).nome)} começa batendo`);
  await espera(1400 * ritmo);
  for (const k of d.cobrancas) {
    pintarDisputa(`${escapar(k.nome)} <span class="dica">(${escapar(clube(k.lado).nome)})</span> vai para a cobrança…`);
    await espera(1300 * ritmo);
    bolas[k.lado].push(k.convertido);
    pintarDisputa(k.convertido ? "GOL!" : "PERDEU!", k.convertido ? "gol" : "erro");
    await espera(1000 * ritmo);
  }
  pintarDisputa(`${escapar(clube(d.vencedor).nome)} vence nos pênaltis por
    ${Math.max(d.gols_casa, d.gols_fora)} × ${Math.min(d.gols_casa, d.gols_fora)}`, "fim");
  $("#v-relogio").innerHTML += `<small class="pen">pên. ${d.gols_casa} × ${d.gols_fora}</small>`;
  await espera(2600 * ritmo);
  painel.remove();
  VIVO.disputaVista = true;
  VIVO.emDisputa = false;
  terminou();
}

function terminou() {
  VIVO.fimVisto = true;
  clearInterval(VIVO.timer);
  if (VIVO.s.estado) aplicarEstado(VIVO.s.estado);
  onzeLocal = null;
  const s = VIVO.s;
  const meus = s.meu_lado === "casa" ? s.gols_casa : s.gols_fora;
  const deles = s.meu_lado === "casa" ? s.gols_fora : s.gols_casa;
  let r = meus > deles ? "VITÓRIA" : meus === deles ? "EMPATE" : "DERROTA";
  if (s.disputa) {
    const meu = s.disputa.vencedor === s.meu_lado;
    r = `${meu ? "CLASSIFICADO" : "ELIMINADO"} nos pênaltis (${s.disputa.gols_casa} × ${s.disputa.gols_fora})`;
  }
  $("#v-selo").innerHTML = `<div class="selo">FIM DE JOGO<small>${r}${s.impacto ? `<br>${escapar(s.impacto)}` : ""}<br>ENTER para o resumo</small></div>`;
  $("#v-pausa").hidden = true;
  $("#v-fim").hidden = true;
  $("#v-subs").disabled = true;
  $("#v-tatica").disabled = true;
  $("#v-sumula").hidden = false;
}

/* ------------------------------------------------------------------ pintura */

function eventosVisiveis() {
  const vis = VIVO.s.eventos.filter((e) => e.minuto <= VIVO.relogio);
  // durante o suspense do penalti, o desfecho (gol, defesa, fora) ainda nao aparece
  const sus = VIVO.suspense;
  if (sus) {
    const i = vis.findIndex((e) => e.tipo === "penalti" && e.minuto === sus.minuto && e.jogador === sus.jogador);
    if (i >= 0) return vis.slice(0, i + 1);
  }
  return vis;
}

const chaveDoLance = (e) => `${e.tipo}:${e.minuto}:${e.jogador}:${e.lado}`;

/** Ao retomar um jogo ou ir ao fim, o que ja passou nao dispara pausa nem suspense. */
function marcarComoVisto() {
  for (const e of VIVO.s.eventos.filter((x) => x.minuto <= VIVO.relogio)) VIVO.vistos.add(chaveDoLance(e));
  for (const j of VIVO.s.rodada || []) {
    for (const l of j.lances) if (l.minuto <= VIVO.relogio) VIVO.vistos.add(chaveDaRodada(j, l));
  }
}

/** Lances que acabam de aparecer e pedem a atencao do treinador: penalti e expulsao. */
function lancesNovos() {
  const s = VIVO.s;
  for (const e of s.eventos.filter((x) => x.minuto <= VIVO.relogio)) {
    const k = chaveDoLance(e);
    if (VIVO.vistos.has(k)) continue;
    if (e.tipo === "penalti") {
      if (VIVO.suspense) return;        // um de cada vez
      VIVO.vistos.add(k);
      comecarSuspense(e);
      return;
    }
    // o desfecho do penalti espera o suspense acabar
    if (VIVO.suspense && e.minuto === VIVO.suspense.minuto) return;
    VIVO.vistos.add(k);
    if (e.tipo === "vermelho" && config().pausarNaExpulsao && !VIVO.fimVisto) avisarExpulsao(e);
    // lesao no MEU time antes do ultimo bloco: da tempo de escolher quem entra
    if (e.tipo === "lesao" && e.lado === s.meu_lado && e.minuto <= 85 && !VIVO.fimVisto) avisarLesao(e);
  }
}

async function avisarLesao(e) {
  VIVO.pausado = true;
  const nome = nomeDoJogador(e.jogador) || "?";
  const escolha = await abrirJanela({titulo: "LESÃO", estreita: true, corpo: `
    <p><span class="ic-lesao">✚</span> <b>${escapar(nome)}</b> sente aos ${e.minuto}' e pede para sair.</p>
    <p class="dica">Escolha quem entra, ou deixe a comissão técnica colocar o reserva do mesmo setor
      na parada técnica (${VIVO.s.minuto}'). Sem troca sobrando, o time fica com um a menos.</p>`,
    botoes: [{rotulo: "Deixar o automático", valor: "auto"},
             {rotulo: "Escolher substituto ›", primario: true, valor: "subs"}]});
  VIVO.pausado = false;
  if (escolha === "subs") {
    abrirGaveta("subs");
    subSai = e.jogador;
    pintarGaveta();
  }
}

function comecarSuspense(e) {
  const s = VIVO.s;
  const meu = e.lado === s.meu_lado;
  const nome = nomeDoJogador(e.jogador) || "O batedor";
  const clube = e.lado === "casa" ? s.casa : s.fora;
  const ms = meu ? 2600 : 2000;
  VIVO.suspense = {minuto: e.minuto, jogador: e.jogador};
  VIVO.segurarAte = Date.now() + ms;
  $("#v-selo").innerHTML = `<div class="selo penalti">PÊNALTI<small>${meu
    ? `${escapar(nome)} posiciona a bola…` : `${escapar(nome)} (${escapar(clube.nome)}) vai para a cobrança`}</small></div>`;
  setTimeout(() => {
    VIVO.suspense = null;
    const desfecho = VIVO.s.eventos.find((x) => x.minuto === e.minuto && x.jogador === e.jogador
      && ["gol", "penalti_defendido", "penalti_fora"].includes(x.tipo));
    const titulo = !desfecho ? "" : desfecho.tipo === "gol" ? "GOOOL!"
      : desfecho.tipo === "penalti_defendido" ? "DEFENDEU!" : "PRA FORA!";
    if (titulo && !VIVO.pausado) {
      $("#v-selo").innerHTML = `<div class="selo penalti">${titulo}<small>${escapar(desfecho.texto)}</small></div>`;
      VIVO.segurarAte = Date.now() + 1600;
      setTimeout(() => { if (!VIVO.pausado && !VIVO.fimVisto) $("#v-selo").innerHTML = ""; }, 1600);
    }
    pintar();
  }, ms);
}

async function avisarExpulsao(e) {
  const s = VIVO.s;
  const meu = e.lado === s.meu_lado;
  const clube = e.lado === "casa" ? s.casa : s.fora;
  VIVO.pausado = true;
  const escolha = await abrirJanela({titulo: "EXPULSÃO", estreita: true, corpo: `
    <p><span class="cartao vm"></span> <b>${escapar(nomeDoJogador(e.jogador) || "?")}</b> (${escapar(clube.nome)}) recebe o vermelho aos ${e.minuto}'.</p>
    <p class="dica">${meu ? "Seu time fica com um a menos. Vale mexer antes de o jogo seguir." : "O adversário fica com um a menos."}</p>`,
    botoes: [{rotulo: "Ajustar tática", valor: "tatica"}, {rotulo: "Substituições", valor: "subs"},
             {rotulo: "Continuar ›", primario: true, valor: "ok"}]});
  VIVO.pausado = false;
  if (escolha === "tatica" || escolha === "subs") abrirGaveta(escolha);
}

async function escolherPenalti() {
  const s = VIVO.s;
  const pen = s.penalti;
  VIVO.escolhendoPenalti = true;
  const cands = pen.candidatos;
  let escolhido = cands[0]?.id;
  // fechar com Esc tambem cobra: com o primeiro da lista, que e o da ordem de Taticas
  await abrirJanela({titulo: `PÊNALTI PARA O ${escapar(s[s.meu_lado].nome.toUpperCase())}!`, corpo: `
    <p class="dica">${pen.minuto}' · Quem será o cobrador?${pen.goleiro ? ` No gol, ${escapar(pen.goleiro)}.` : ""}</p>
    <table class="grade compacta escolha-penalti"><thead><tr><th></th><th>Jogador</th><th class="n">Finalização</th>
      <th class="n">Técnica</th><th class="n">Confiança</th><th class="n">Chance</th></tr></thead>
    <tbody>${cands.map((j, i) => `<tr>
      <td><input type="radio" name="batedor" value="${j.id}" id="bat-${j.id}" ${i === 0 ? "checked" : ""}></td>
      <td><label for="bat-${j.id}">${pos(j.posicao)} <b>${escapar(j.nome)}</b>${j.ordem ? ` <span class="chip">${j.ordem}º batedor</span>` : ""}</label></td>
      <td class="n">${j.finalizacao}</td><td class="n">${j.tecnica}</td><td class="n">${j.confianca}</td>
      <td class="n"><b>${j.chance}%</b></td></tr>`).join("")}</tbody></table>
    <p class="nota-honesta">A chance é a conta do motor: finalização e técnica do batedor contra os reflexos do goleiro.</p>`,
    botoes: [{rotulo: "Cobrar ›", primario: true, valor: "ok", acao: () => {
      const r = document.querySelector("input[name=batedor]:checked");
      if (r) escolhido = +r.value;
    }}]});
  VIVO.esperando = true;
  const novo = await api.post("/api/partida/seguir", {penalti: escolhido});
  VIVO.esperando = false;
  VIVO.escolhendoPenalti = false;
  if (novo.erro && !novo.minuto) { avisar(novo.erro); return; }
  VIVO.anterior = VIVO.s;
  VIVO.s = novo;
  pintar();
}

function pintar() {
  const s = VIVO.s;
  lancesNovos();
  novidadesDaRodada();
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
  const falta = s.fim || s.penalti ? "" : `próxima parada técnica: ${s.minuto}'`;
  $("#v-parada").textContent = falta;
  $("#v-conta").textContent = `${s.trocas_feitas + VIVO.fila.length}/${s.max_trocas}`;
  pintarFeed(vis);
  // estatisticas e rodada andam por bloco: mostram o bloco fechado mais recente
  const fechado = VIVO.relogio >= s.minuto ? s : VIVO.anterior;
  pintarStats(fechado);
  pintarLateral(fechado);
}

const ICONE_LANCE = {gol: "⚽", penalti: "◎", penalti_defendido: "🧤", penalti_fora: "✗",
                     lesao: '<span class="ic-lesao">✚</span>', lesao_sem_troca: '<span class="ic-lesao">✚</span>',amarelo: '<span class="cartao am" style="width:.72rem;height:1rem"></span>',
                     vermelho: '<span class="cartao vm" style="width:.72rem;height:1rem"></span>', substituicao: "⇅", defesa: "✋", chute: "↗",
                     escanteio: "⚑", impedimento: "⚐", falta: "!"};

// o lance a lance mostra so o que muda o jogo; finalizacao, escanteio, falta e impedimento
// ficam nas estatisticas
const TIPOS_DO_FEED = new Set(["gol", "amarelo", "vermelho", "substituicao", "lesao",
                               "lesao_sem_troca", "penalti_defendido", "penalti_fora"]);

function pintarFeed(todos) {
  const s = VIVO.s;
  const feed = $("#v-feed");
  const vis = todos.filter((e) => TIPOS_DO_FEED.has(e.tipo));
  const chave = `${vis.length}:${VIVO.relogio > 45}`;
  if (chave === VIVO.visiveis && feed.childElementCount) return;
  VIVO.visiveis = chave;
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
      txt = `GOL! ${escapar(nomeDoJogador(e.jogador) || e.texto.replace("GOL! ", ""))}${e.texto.includes("(pênalti)") ? " (pênalti)" : ""}`;
      if (assist) sub += ` · assistência de ${escapar(assist)}`;
    }
    linhas.push(`<div class="lance ${e.tipo}"><span class="min">${e.minuto}'</span>
      <span class="ic">${ICONE_LANCE[e.tipo] ?? ""}</span><span class="txt">${txt}<small>${sub}</small></span></div>`);
  }
  // com a lista enxuta, o 2o tempo pode comecar sem nenhum lance ainda
  if (!intervalo && VIVO.relogio > 45) {
    linhas.push(`<div class="lance marco"><span class="min">45'</span><span class="ic">${icone("apito")}</span><span class="txt">Intervalo · começa o 2º tempo</span></div>`);
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
    alvo.innerHTML = centralDaRodada();
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
      <span>${j.amarelo && vistos.has(j.id) ? '<span class="cartao am"></span>' : ""}${expulso ? '<span class="cartao vm"></span>' : ""}${j.lesionado && vistos.has(j.id) ? '<span class="ic-lesao">✚</span>' : ""}</span>
      <span class="en">${barra(j.energia, corDe(j.energia, 80, 62))}${j.energia}</span></div>`;
  }).join("")}</div>`;
}

/* ------------------------------------------------------------------ central da rodada
 * Todos os jogos da data ate o minuto do relogio: placar, quem marcou, expulsoes, trocas
 * (e amarelos, se a configuracao pedir). Os lances vem do servidor (fm.central) e sao os
 * mesmos que a artilharia e o gancho registram. */

const chaveDaRodada = (j, l) => `r:${j.casa.id}:${j.fora.id}:${l.tipo}:${l.minuto}:${l.nome}`;

function jogosDaRodada() {
  return (VIVO.s.rodada || []).map((j) => {
    const lances = j.lances.filter((l) => l.minuto <= VIVO.relogio);
    return {...j, lances,
            gols_casa: lances.filter((l) => l.tipo === "gol" && l.lado === "casa").length,
            gols_fora: lances.filter((l) => l.tipo === "gol" && l.lado === "fora").length};
  });
}

/** Gol em outro campo: a linha do placar pisca. */
function novidadesDaRodada() {
  for (const j of jogosDaRodada()) {
    for (const l of j.lances) {
      const k = chaveDaRodada(j, l);
      if (VIVO.vistos.has(k)) continue;
      VIVO.vistos.add(k);
      // so a linha do placar pisca: sem aviso no meio da tela
      if (l.tipo === "gol" && !VIVO.fimVisto) VIVO.flash[`${j.casa.id}:${j.fora.id}`] = Date.now() + 4000;
    }
  }
}

function centralDaRodada() {
  const s = VIVO.s;
  const [gc, gf] = $("#v-gols").textContent.split("×").map((x) => +x);
  const agora = Date.now();
  // so os placares: escudo, nome e gols
  const jogo = (j, meu) => {
    const piscando = (VIVO.flash[`${j.casa.id}:${j.fora.id}`] || 0) > agora;
    return `<div class="jogo-c ${meu ? "meu" : ""} ${piscando ? "pisca" : ""}">
      <div class="linha"><span class="t casa"><span class="nm">${escapar(j.casa.nome)}</span>${escudo(j.casa, "1.2rem")}</span>
        <b>${j.gols_casa} - ${j.gols_fora}</b>
        <span class="t">${escudo(j.fora, "1.2rem")}<span class="nm">${escapar(j.fora.nome)}</span></span></div></div>`;
  };
  const minha = {casa: s.casa, fora: s.fora, gols_casa: gc, gols_fora: gf, lances: []};
  const outros = jogosDaRodada();
  if (outros.some((j) => (VIVO.flash[`${j.casa.id}:${j.fora.id}`] || 0) > agora)) {
    clearTimeout(VIVO.timerFlash);
    VIVO.timerFlash = setTimeout(() => { if (VIVO.aba === "rodada") pintarLateral(); }, 4100);
  }
  return `<div class="central-rodada">${jogo(minha, true)}${outros.map((j) => jogo(j, false)).join("")
    || '<div class="vazio">Nenhum outro jogo nesta data.</div>'}</div>`;
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
  let res = meus > deles ? ["VITÓRIA", "bom"] : meus === deles ? ["EMPATE", "medio"] : ["DERROTA", "ruim"];
  if (p.disputa) res = p.disputa.vencedor === ESTADO.clube.id ? ["CLASSIFICADO NOS PÊNALTIS", "bom"] : ["ELIMINADO NOS PÊNALTIS", "ruim"];
  const time = (lista, titulo) => `<div class="painel"><div class="cab"><h2>${escapar(titulo)}</h2></div>
    <div class="corpo sem-margem"><table class="grade compacta"><tbody>${lista.map((j) => `
      <tr class="${j.entrou_aos ? "reserva" : ""}"><td>${pos(j.posicao)}</td>
        <td><b>${escapar(j.nome)}</b>${j.entrou_aos ? ` <span class="dica">${j.entrou_aos}'</span>` : ""}
          ${"⚽".repeat(j.gols)}${j.amarelo ? ' <span class="cartao am"></span>' : ""}${j.vermelho ? ' <span class="cartao vm"></span>' : ""}</td>
        <td class="n"><span class="nota ${classeNota(j.nota)}">${j.nota.toFixed(1).replace(".", ",")}</span></td></tr>`).join("")}
    </tbody></table></div></div>`;
  const cobrancas = p.disputa ? `<div class="ev disputa-pos"><span class="casa">${p.disputa.cobrancas
      .filter((k) => k.lado === "casa").map((k) => `${escapar(k.nome)} ${k.convertido ? "⚽" : "✗"}`).join("<br>")}</span>
    <span class="m">pên.</span><span>${p.disputa.cobrancas.filter((k) => k.lado === "fora")
      .map((k) => `${k.convertido ? "⚽" : "✗"} ${escapar(k.nome)}`).join("<br>")}</span></div>` : "";
  const evs = p.eventos.map((e) => {
    const conteudo = `<b>${escapar(e.texto.replace("GOL! ", ""))}</b>${e.assistencia ? `<small>assist. ${escapar(e.assistencia)}</small>` : ""}`;
    const ic = {gol: "⚽", amarelo: '<span class="cartao am"></span>', vermelho: '<span class="cartao vm"></span>', substituicao: "⇅",
                penalti_defendido: "🧤", penalti_fora: "✗", lesao: '<span class="ic-lesao">✚</span>'}[e.tipo];
    return `<div class="ev ${e.tipo}"><span class="casa">${e.lado === "casa" ? `${conteudo} ${ic}` : ""}</span>
      <span class="m">${e.minuto}'</span><span>${e.lado === "fora" ? `${ic} ${conteudo}` : ""}</span></div>`;
  }).join("") + cobrancas || '<div class="vazio">Sem lances para a súmula.</div>';
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
        <span class="res ${res[1]}">${res[0]}</span>
        ${p.disputa ? `<span class="pen-pos">pênaltis ${p.disputa.gols_casa} × ${p.disputa.gols_fora}</span>` : ""}</div>
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
      <div class="painel"><div class="cab"><div class="abas">
          <button data-paba="rodada" class="ativo">Rodada</button><button data-paba="tabela">Tabela <span class="tecla">T</span></button><button data-paba="selecao">Seleção</button></div></div>
        <div class="corpo sem-margem" id="pos-lateral"></div>
        <div class="pe"><span class="dica">Notas derivadas dos lances e do placar</span></div></div>
    </div>
    ${p.impacto ? `<div class="impacto-tabela">${escapar(p.impacto)}</div>` : ""}
    <footer class="fluxo-pe"><span class="dica">${escapar(ESTADO.aprovacao.clima ? `Ambiente no clube: ${clima(ESTADO.aprovacao.clima)}` : "")}</span>
      <span class="espaco"></span><button class="btn primario grande" id="pos-continuar">Continuar »</button></footer>`;
  $("#pos-continuar").addEventListener("click", () => irParaModo("jogo", "calendario"));
  POS.rodada = p.rodada;
  $$("[data-paba]").forEach((b) => b.addEventListener("click", () => abaDoPosJogo(b.dataset.paba)));
  abaDoPosJogo(PARAMS.get("aba") || "rodada");
}

const POS = {rodada: [], aba: "rodada"};

/** A tabela da divisao do usuario como ficou depois da rodada. */
async function tabelaCompacta() {
  const d = await api.get("/api/classificacao");
  const z = d.zonas, n = d.linhas.length;
  const zona = (i) => i <= z.continental ? "continental" : i <= z.acesso ? "acesso"
    : i > n - z.rebaixamento ? "rebaixamento" : "";
  return `<table class="grade compacta"><thead><tr><th class="c">#</th><th>${escapar(d.nome)}</th>
      <th class="n">J</th><th class="n">SG</th><th class="n">P</th></tr></thead>
    <tbody>${d.linhas.map((l, i) => `<tr class="${l.eu ? "eu" : ""}">
      <td class="c"><span class="zona ${zona(i + 1)}">${i + 1}</span></td>
      <td><div class="nome-celula">${escudo(l.clube, "1.2rem")}<b>${escapar(l.clube.nome)}</b></div></td>
      <td class="n">${l.jogos}</td><td class="n">${l.saldo > 0 ? "+" : ""}${l.saldo}</td>
      <td class="n"><b>${l.pontos}</b></td></tr>`).join("")}</tbody></table>`;
}

async function abaDoPosJogo(aba) {
  POS.aba = aba;
  $$("[data-paba]").forEach((b) => b.classList.toggle("ativo", b.dataset.paba === aba));
  const alvo = $("#pos-lateral");
  if (aba === "selecao") {
    const s = await api.get("/api/selecao");
    alvo.innerHTML = s.onze.length ? `<div class="lista-selecao">${s.onze.map((j) => `
      <div class="item-s ${j.meu ? "meu" : ""}"><span class="vaga">${j.vaga}</span>${escudo(j.clube, "1.2rem")}
        <span class="nm">${j.craque ? '<span class="ouro">★</span> ' : ""}<b>${escapar(j.nome)}</b>
          <span class="dica">${escapar(j.clube.nome)}</span></span>
        <span class="nota ${classeNota(j.nota)}">${j.nota.toFixed(1).replace(".", ",")}</span></div>`).join("")}</div>
      <p class="nota-honesta" style="margin:.7rem">${s.rodada}ª rodada da ${escapar(s.nome)}. Toda a seleção em Destaques.</p>`
      : '<div class="vazio">Sem seleção: esta data não foi rodada de liga.</div>';
    return;
  }
  if (aba === "tabela") {
    alvo.innerHTML = await tabelaCompacta();
    $("#pos-lateral tr.eu")?.scrollIntoView({block: "center"});
    return;
  }
  alvo.innerHTML = `<div class="rodada-vivo">${POS.rodada.map((r) => `
    <div class="jogo ${r.meu ? "meu" : ""}"><span>${escapar(r.casa.nome)}</span><b>${r.gols_casa} - ${r.gols_fora}</b><span>${escapar(r.fora.nome)}</span></div>`).join("")}</div>`;
}

registrarModo("posjogo", {
  elemento: "#pos-jogo", abrir: abrirPosJogo,
  tecla(ev) {
    if (ev.key === "Enter" || ev.key === " ") { irParaModo("jogo", "calendario"); ev.preventDefault(); }
    if (ev.key.toLowerCase() === "t") abaDoPosJogo(POS.aba === "tabela" ? "rodada" : "tabela");
  },
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
