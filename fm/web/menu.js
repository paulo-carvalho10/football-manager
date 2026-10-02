"use strict";
/* Tela inicial, nova carreira e escolha do clube. */

/* ================================================================== TELA INICIAL */

let MENU = null;

async function abrirMenu() {
  MENU = await api.get("/api/menu");
  $("#logo-grande").innerHTML = logo();
  $("#versao").textContent = `PRANCHETA 11 · versão ${MENU.versao}`;
  const c = MENU.carreira;
  const itens = [];
  if (c) {
    itens.push({id: "continuar", rotulo: "Continuar", icone: "jogar", destaque: true,
                extra: `${escapar(c.clube.nome)} · ${c.temporada}`});
  }
  itens.push(
    {id: "novo", rotulo: "Novo jogo", icone: "novo", destaque: !c},
    {id: "salvos", rotulo: "Jogos salvos", icone: "pasta",
     extra: MENU.saves.length ? `${MENU.saves.length}` : "nenhum"},
    {id: "editor", rotulo: "Editor", icone: "lapis", extra: "em breve", desativado: true},
    {id: "config", rotulo: "Configurações", icone: "engrenagem"},
    {id: "creditos", rotulo: "Créditos", icone: "estrela"},
    {id: "sair", rotulo: "Sair", icone: "desligar"},
  );
  $("#menu-principal").innerHTML = itens.map((i) => `
    <button data-menu="${i.id}" class="${i.destaque ? "destaque" : ""}" ${i.desativado ? "disabled" : ""}>
      ${icone(i.icone)}<span>${i.rotulo.toUpperCase()}</span>${i.extra ? `<small>${i.extra}</small>` : ""}
    </button>`).join("");
  $$("[data-menu]").forEach((b) => b.addEventListener("click", () => acaoDoMenu(b.dataset.menu)));
  const primeiro = $("#menu-principal button:not(:disabled)");
  if (primeiro) primeiro.focus();
}

async function acaoDoMenu(id) {
  if (id === "continuar") return irParaModo("jogo");
  if (id === "novo") return irParaModo("nova");
  if (id === "salvos") return janelaDeSaves();
  if (id === "config") return janelaDeConfiguracoes();
  if (id === "creditos") return janelaDeCreditos();
  if (id === "sair") return sair();
}

async function janelaDeSaves() {
  const saves = MENU.saves;
  const corpo = saves.length
    ? `<div class="lista-simples">${saves.map((s) => `
        <div class="item"><span>${icone("pasta")}</span><b>${escapar(s)}</b>
          <span class="espaco"></span>
          <button class="btn primario pequeno" data-carregar="${escapar(s)}">Carregar</button></div>`).join("")}
       </div>`
    : `<div class="vazio">Nenhum jogo salvo ainda.</div>`;
  const promessa = abrirJanela({titulo: "Jogos salvos", corpo, estreita: true,
                                botoes: [{rotulo: "Voltar"}]});
  $$("[data-carregar]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    b.textContent = "Carregando…";
    const r = await api.post("/api/carregar", {nome: b.dataset.carregar});
    if (r.erro) { avisar(r.erro); b.disabled = false; b.textContent = "Carregar"; return; }
    fecharJanela();
    irParaModo("jogo");
  }));
  return promessa;
}

function janelaDeConfiguracoes() {
  const c = config();
  const seg = (chave, opcoes) => `<div class="segmentado" data-cfg="${chave}">${opcoes.map(([v, r]) =>
    `<button data-v="${v}" class="${String(c[chave]) === String(v) ? "ativo" : ""}">${r}</button>`).join("")}</div>`;
  const corpo = `<div class="form-col">
    <label class="campo"><span>Velocidade da partida ao vivo</span>
      ${seg("velocidade", [["1x", "▶ 1x"], ["2x", "▶▶ 2x"], ["4x", "▶▶▶ 4x"]])}</label>
    <label class="campo"><span>Pausar automaticamente no gol</span>
      ${seg("pausarNoGol", [[true, "Sim"], [false, "Não"]])}</label>
    <label class="campo"><span>Pausar no intervalo</span>
      ${seg("pausarNoIntervalo", [[true, "Sim"], [false, "Não"]])}</label>
    <label class="campo"><span>Perguntar quem cobra pênaltis</span>
      ${seg("perguntarPenalti", [[true, "Sim"], [false, "Não, usar a ordem"]])}</label>
    <label class="campo"><span>Pausar em expulsão</span>
      ${seg("pausarNaExpulsao", [[true, "Sim"], [false, "Não"]])}</label>
  </div>`;
  const p = abrirJanela({titulo: "Configurações", corpo, estreita: true,
    botoes: [{rotulo: "Salvar", primario: true, acao: () => {
      const novo = {...c};
      $$("[data-cfg]").forEach((s) => {
        const v = $(".ativo", s).dataset.v;
        novo[s.dataset.cfg] = v === "true" ? true : v === "false" ? false : v;
      });
      salvarConfig(novo);
      avisar("Configurações salvas");
    }}]});
  $$("[data-cfg] button").forEach((b) => b.addEventListener("click", () => {
    $$("button", b.parentNode).forEach((x) => x.classList.toggle("ativo", x === b));
  }));
  return p;
}

function janelaDeCreditos() {
  return abrirJanela({titulo: "Créditos", estreita: true, corpo: `
    <div class="form-col">
      <div>${logo(true)}</div>
      <p>Motor de partida, carreira, economia e interface escritos para este jogo.</p>
      <div class="lista-simples">
        <div class="item">${icone("pessoa")}<span>Clubes e jogadores</span><span class="espaco"></span><span class="dica">fontes públicas de elencos</span></div>
        <div class="item">${icone("elenco")}<span>Camisas</span><span class="espaco"></span><span class="dica">Wikimedia Commons</span></div>
        <div class="item">${icone("estrela")}<span>Escudos</span><span class="espaco"></span><span class="dica">CBF, baixados localmente</span></div>
      </div>
      <p class="nota-honesta">Inspirado na tradição dos managers brasileiros de PC. Identidade visual,
        logo e telas próprios do PRANCHETA 11.</p>
    </div>`});
}

async function sair() {
  const ok = await abrirJanela({titulo: "Sair do jogo", estreita: true,
    corpo: `<p>O servidor do jogo será encerrado. Partidas não salvas serão perdidas.</p>`,
    botoes: [{rotulo: "Cancelar", valor: false}, {rotulo: "Sair", primario: true, valor: true}]});
  if (!ok) return;
  await api.post("/api/sair").catch(() => {});
  document.body.innerHTML = `<div class="carregando" style="height:100vh">
    <div style="text-align:center">${logo(true)}<p>Até a próxima rodada. Pode fechar esta aba.</p></div></div>`;
}

registrarModo("menu", {
  elemento: "#menu-inicial", abrir: abrirMenu,
  tecla(ev) {
    const botoes = $$("#menu-principal button:not(:disabled)");
    const i = botoes.indexOf(document.activeElement);
    if (ev.key === "ArrowDown") { botoes[(i + 1) % botoes.length].focus(); ev.preventDefault(); }
    if (ev.key === "ArrowUp") { botoes[(i - 1 + botoes.length) % botoes.length].focus(); ev.preventDefault(); }
  },
});

/* ================================================================== NOVA CARREIRA */

const NOVA = {catalogo: null, paises: new Set(["BRA"]), treinador: "", seed: 2027,
              formacao: "4-3-3", clubes: null, ms: 0};

async function abrirNova() {
  $$(".logo-p-slot").forEach((el) => { el.innerHTML = logo(true); });
  if (!NOVA.catalogo) {
    NOVA.catalogo = await api.get("/api/catalogo");
    // todos os paises liberados vem marcados: pais desmarcado nao existe no mundo, e os
    // jogadores dele nao aparecem no mercado (nem os clubes nas copas continentais)
    NOVA.paises = new Set(NOVA.catalogo.nacionais.filter((n) => n.livre).map((n) => n.pais));
  }
  desenharPaises();
  desenharEstaduais();
  desenharConfig();
  await atualizarDesempenho();
}

function ligasSelecionadas() {
  return NOVA.catalogo.nacionais
    .filter((n) => n.livre && NOVA.paises.has(n.pais))
    .flatMap((n) => n.ligas.map((l) => l.id));
}

function bandeira(n) {
  return `<span class="bandeira" style="background:linear-gradient(180deg, ${n.cores[0]} 0 50%, ${n.cores[1]} 50%)"></span>`;
}

function desenharPaises() {
  const cat = NOVA.catalogo;
  $("#lista-paises").innerHTML = cat.nacionais.map((n) => {
    const marcado = n.livre && NOVA.paises.has(n.pais);
    return `<div class="pais ${n.livre ? "" : "bloqueado"} ${marcado ? "marcado" : ""}">
      <label class="linha-pais">
        <input type="checkbox" data-pais="${n.pais}" ${marcado ? "checked" : ""} ${n.livre ? "" : "disabled"}>
        ${bandeira(n)}<span class="nome-pais">${escapar(n.nome)}</span>
        ${n.livre ? "" : `<span class="cadeado">${icone("cadeado")} Disponível na versão completa</span>`}
      </label>
      <div class="divisoes">${n.ligas.map((l) =>
        `<span class="chip ${marcado ? "ativo" : ""}">${l.divisao}ª · ${escapar(l.nome)}</span>`).join("")}</div>
    </div>`;
  }).join("");
  $$("[data-pais]").forEach((cb) => cb.addEventListener("change", async () => {
    if (cb.checked) NOVA.paises.add(cb.dataset.pais); else NOVA.paises.delete(cb.dataset.pais);
    desenharPaises();
    desenharCopas();
    await atualizarDesempenho();
  }));
  const n = ligasSelecionadas().length;
  $("#conta-ligas").textContent = `${n} divisões`;
  desenharCopas();
}

function desenharEstaduais() {
  $("#lista-estaduais").innerHTML = `<div class="lista-simples">${NOVA.catalogo.estaduais.map((e) =>
    `<div class="item inativo"><span>${escapar(e)}</span><span class="espaco"></span>
      <span class="chip">em desenvolvimento</span></div>`).join("")}</div>`;
}

function desenharCopas() {
  const cat = NOVA.catalogo;
  const blocos = cat.nacionais.filter((n) => n.livre).map((n) => {
    const ativo = NOVA.paises.has(n.pais);
    return `<h3 style="margin:.2rem 0 .5rem">${bandeira(n)} ${escapar(n.nome)}</h3>
      <div class="lista-simples" style="margin-bottom:1rem">${(cat.copas[n.pais] || []).map((c) =>
        `<div class="item ${ativo ? "ok" : "inativo"}">${ativo ? icone("check") : '<span class="dica" style="width:1.1rem;text-align:center">—</span>'}
          <span>${escapar(c)}</span></div>`).join("")}</div>`;
  }).join("");
  $("#lista-copas").innerHTML = blocos;
}

function desenharConfig() {
  $("#config-carreira").innerHTML = `
    <div class="avatar-treinador">
      <div class="rosto">${icone("pessoa")}</div>
      <div><b id="nome-previa">${escapar(NOVA.treinador || "Seu nome")}</b>
        <span class="dica">Treinador · sem clube</span></div>
    </div>
    <label class="campo"><span>Nome do treinador</span>
      <input type="text" id="in-treinador" maxlength="40" placeholder="Como a imprensa vai te chamar"
        value="${escapar(NOVA.treinador)}"></label>
    <label class="campo"><span>Formação preferida</span>
      <select id="in-formacao">${["4-3-3", "4-4-2", "4-2-3-1", "4-5-1", "3-5-2", "3-4-3", "5-3-2"].map((f) =>
        `<option ${f === NOVA.formacao ? "selected" : ""}>${f}</option>`).join("")}</select></label>
    <label class="campo"><span>Número do mundo</span>
      <input type="number" id="in-seed" min="1" max="999999" value="${NOVA.seed}"></label>
    <div class="kpis">
      <div class="kpi-c"><span>Temporada inicial</span><b id="temporada-inicial">2027</b></div>
      <div class="kpi-c"><span>Modo</span><b>Carreira</b></div>
    </div>`;
  $("#in-treinador").addEventListener("input", (e) => {
    NOVA.treinador = e.target.value;
    $("#nome-previa").textContent = NOVA.treinador || "Seu nome";
  });
  $("#in-formacao").addEventListener("change", (e) => { NOVA.formacao = e.target.value; });
  $("#in-seed").addEventListener("change", async (e) => {
    NOVA.seed = Math.max(1, parseInt(e.target.value, 10) || 2027);
    await atualizarDesempenho();
  });
}

async function atualizarDesempenho() {
  const ligas = ligasSelecionadas();
  $("#ir-para-clubes").disabled = !ligas.length;
  $("#aviso-nova").textContent = ligas.length ? "" : "Escolha pelo menos um país.";
  if (!ligas.length) { $("#perf").innerHTML = ""; NOVA.clubes = null; return; }
  const t0 = performance.now();
  NOVA.clubes = await api.get(`/api/clubes?ligas=${ligas.join(",")}&seed=${NOVA.seed}`);
  NOVA.ms = performance.now() - t0;
  const nClubes = NOVA.clubes.clubes.length;
  const porDivisao = {};
  for (const c of NOVA.clubes.clubes) porDivisao[c.liga] = (porDivisao[c.liga] || 0) + 1;
  const jogos = Object.values(porDivisao).reduce((s, n) => s + n * (n - 1), 0);
  const ti = $("#temporada-inicial");
  if (ti && NOVA.clubes.temporada) ti.textContent = NOVA.clubes.temporada;
  $("#perf").innerHTML = `
    <div class="kpi"><b>${ligas.length}</b><span>divisões</span></div>
    <div class="kpi"><b>${nClubes}</b><span>clubes</span></div>
    <div class="kpi"><b>${NOVA.clubes.jogadores.toLocaleString("pt-BR")}</b><span>jogadores</span></div>
    <div class="kpi"><b>${jogos.toLocaleString("pt-BR")}</b><span>jogos de liga por temporada</span></div>
    <div class="kpi"><b>${(NOVA.ms / 1000).toFixed(1).replace(".", ",")} s</b><span>para gerar o mundo</span></div>`;
}

registrarModo("nova", {
  elemento: "#nova-carreira", abrir: abrirNova,
  tecla(ev) {
    if (ev.key === "Escape") irParaModo("menu");
    if (ev.key === "Enter" && !$("#ir-para-clubes").disabled) $("#ir-para-clubes").click();
  },
});

/* ================================================================== ESCOLHA DO CLUBE */

const ESCOLHA = {filtro: {liga: "", busca: "", perfil: ""}, ordem: {coluna: "forca", desc: true},
                 selecionado: null};

function perfilDoClube(c) {
  const f = c.ranking / c.de;
  if (f <= 0.2) return "favorito";
  if (f <= 0.6) return "meio";
  return "zona";
}
const PERFIS_CLUBE = {favorito: "Candidato ao título", meio: "Meio de tabela", zona: "Luta contra a queda"};

async function abrirEscolha() {
  $$(".logo-p-slot").forEach((el) => { el.innerHTML = logo(true); });
  if (!NOVA.catalogo) NOVA.catalogo = await api.get("/api/catalogo");
  if (!NOVA.clubes) await atualizarDesempenho();
  const ligas = NOVA.clubes.ligas;
  $("#filtros-clube").innerHTML = `
    <label class="campo"><span>Buscar</span>
      <input type="search" id="f-busca" placeholder="Nome do clube" value="${escapar(ESCOLHA.filtro.busca)}"></label>
    <label class="campo"><span>Divisão</span>
      <select id="f-liga"><option value="">Todas</option>${ligas.map((l) =>
        `<option value="${l.id}" ${ESCOLHA.filtro.liga === l.id ? "selected" : ""}>${escapar(l.nome)}</option>`).join("")}
      </select></label>
    <label class="campo"><span>Desafio</span>
      <select id="f-perfil"><option value="">Qualquer</option>${Object.entries(PERFIS_CLUBE).map(([k, v]) =>
        `<option value="${k}" ${ESCOLHA.filtro.perfil === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
    <label class="campo"><span>Ordenar por</span>
      <select id="f-ordem">${[["forca", "Força do elenco"], ["reputacao", "Reputação"], ["caixa", "Caixa"],
        ["valor_do_elenco", "Valor do elenco"], ["nome", "Nome"]].map(([k, v]) =>
        `<option value="${k}" ${ESCOLHA.ordem.coluna === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>`;
  $("#f-busca").addEventListener("input", (e) => { ESCOLHA.filtro.busca = e.target.value; desenharClubes(); });
  $("#f-liga").addEventListener("change", (e) => { ESCOLHA.filtro.liga = e.target.value; desenharClubes(); });
  $("#f-perfil").addEventListener("change", (e) => { ESCOLHA.filtro.perfil = e.target.value; desenharClubes(); });
  $("#f-ordem").addEventListener("change", (e) => {
    ESCOLHA.ordem = {coluna: e.target.value, desc: e.target.value !== "nome"};
    desenharClubes();
  });
  $$("#tabela-clubes th[data-ord]").forEach((th) => th.onclick = () => {
    const col = th.dataset.ord;
    ESCOLHA.ordem = ESCOLHA.ordem.coluna === col
      ? {coluna: col, desc: !ESCOLHA.ordem.desc} : {coluna: col, desc: col !== "nome" && col !== "liga_nome"};
    desenharClubes();
  });
  desenharClubes();
}

function clubesFiltrados() {
  const f = ESCOLHA.filtro;
  const busca = f.busca.trim().toLowerCase();
  const lista = NOVA.clubes.clubes.filter((c) =>
    (!f.liga || c.liga === f.liga) && (!busca || c.nome.toLowerCase().includes(busca))
    && (!f.perfil || perfilDoClube(c) === f.perfil));
  const {coluna, desc} = ESCOLHA.ordem;
  lista.sort((a, b) => {
    const va = a[coluna], vb = b[coluna];
    const r = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return desc ? -r : r;
  });
  return lista;
}

function desenharClubes() {
  const lista = clubesFiltrados();
  if (!ESCOLHA.selecionado || !lista.some((c) => c.nome === ESCOLHA.selecionado)) {
    ESCOLHA.selecionado = lista[0]?.nome ?? null;
  }
  $("#conta-clubes").textContent = `${lista.length} clubes`;
  const maxForca = Math.max(...NOVA.clubes.clubes.map((c) => c.forca));
  const minForca = Math.min(...NOVA.clubes.clubes.map((c) => c.forca));
  $$("#tabela-clubes th").forEach((th) => {
    th.classList.toggle("ativo", th.dataset.ord === ESCOLHA.ordem.coluna);
    th.classList.toggle("asc", th.dataset.ord === ESCOLHA.ordem.coluna && !ESCOLHA.ordem.desc);
  });
  $("#tabela-clubes tbody").innerHTML = lista.map((c) => `
    <tr class="clicavel ${c.nome === ESCOLHA.selecionado ? "sel" : ""}" data-nome="${escapar(c.nome)}">
      <td>${escudo(c, "1.7rem", true)}</td>
      <td><b>${escapar(c.nome)}</b></td>
      <td>${escapar(c.liga_nome)}</td>
      <td class="n"><span class="celula-barra"><span class="forca-barra" style="width:3.5rem"><i style="width:${
        Math.round(100 * (c.forca - minForca + 2) / (maxForca - minForca + 2))}%"></i></span>${c.forca.toFixed(1)}</span></td>
      <td class="n">${c.reputacao}</td>
      <td class="n ${c.caixa < 0 ? "ruim" : ""}">${dinheiro(c.caixa, c.moeda || MOEDA)}</td>
      <td class="n">${euros(c.valor_do_elenco)}</td>
      <td><span class="chip ${perfilDoClube(c) === "favorito" ? "ouro" : ""}">${PERFIS_CLUBE[perfilDoClube(c)]}</span></td>
    </tr>`).join("") || `<tr><td colspan="8" class="vazio">Nenhum clube com esses filtros.</td></tr>`;
  $$("#tabela-clubes tbody tr[data-nome]").forEach((tr) => {
    tr.addEventListener("click", () => { ESCOLHA.selecionado = tr.dataset.nome; desenharClubes(); });
    tr.addEventListener("dblclick", () => { ESCOLHA.selecionado = tr.dataset.nome; assumir(); });
  });
  desenharDetalheDoClube();
}

function desenharDetalheDoClube() {
  const c = NOVA.clubes.clubes.find((x) => x.nome === ESCOLHA.selecionado);
  const alvo = $("#detalhe-clube");
  $("#assumir").disabled = !c;
  if (!c) { alvo.innerHTML = `<div class="vazio">Escolha um clube.</div>`; return; }
  alvo.style.setProperty("--cor-detalhe", corDeAcento(c.cor));
  alvo.innerHTML = `
    <div class="cabeca">${escudo(c, "", true)}
      <div><h2>${escapar(c.nome)}</h2><small>${escapar(c.liga_nome)} · ${c.ranking}º elenco de ${c.de}</small></div>
    </div>
    <div class="corpo">
      <div class="meta-caixa"><span>Expectativa da diretoria</span>${escapar(c.meta)}</div>
      <div class="ficha" style="margin-top:1rem">
        <div><span>Força do elenco</span><b>${c.forca.toFixed(1)}</b></div>
        <div><span>Reputação</span><b>${c.reputacao}</b></div>
        <div><span>Caixa</span><b class="${c.caixa < 0 ? "ruim" : ""}">${dinheiro(c.caixa, c.moeda || MOEDA)}</b></div>
        <div><span>Valor do elenco</span><b>${euros(c.valor_do_elenco)}</b></div>
        <div><span>Folha anual</span><b>${dinheiro(c.folha, c.moeda || MOEDA)}</b></div>
        <div><span>Jogadores</span><b>${c.jogadores}</b></div>
        <div><span>Idade média</span><b>${String(c.idade_media).replace(".", ",")}</b></div>
        <div><span>Desafio</span><b>${PERFIS_CLUBE[perfilDoClube(c)]}</b></div>
      </div>
      <div class="secao"><h3>Destaques do elenco</h3>
        <table class="grade compacta"><tbody>${c.estrelas.map((p) => `
          <tr><td>${pos(p.posicao)}</td><td><b>${escapar(p.nome)}</b></td><td class="n">${ovr(p.overall)}</td></tr>`).join("")}
        </tbody></table></div>
    </div>`;
}

async function assumir() {
  const c = NOVA.clubes.clubes.find((x) => x.nome === ESCOLHA.selecionado);
  if (!c) return;
  const botao = $("#assumir");
  botao.disabled = true;
  botao.textContent = "Preparando a temporada…";
  const r = await api.post("/api/nova", {ligas: ligasSelecionadas(), clube: c.nome,
                                         treinador: NOVA.treinador, seed: NOVA.seed});
  botao.textContent = "Assumir o comando ›";
  botao.disabled = false;
  if (r.erro) { avisar(r.erro); return; }
  if (NOVA.formacao !== "4-3-3") {
    await api.post("/api/escalar", {formacao: NOVA.formacao});
  }
  await irParaModo("jogo");
  boasVindas(r.estado);
}

function boasVindas(e) {
  abrirJanela({titulo: `Bem-vindo ao ${escapar(e.clube.nome)}`, estreita: true, corpo: `
    <div class="form-col">
      <div class="linha-flex">${escudo(e.clube, "3.6rem")}
        <div><b style="font-size:1.1rem">${escapar(e.treinador)}</b><div class="dica">novo treinador · temporada ${e.temporada}</div></div></div>
      <div class="meta-caixa"><span>A diretoria espera</span>${escapar(e.aprovacao.meta)}</div>
    </div>`, botoes: [{rotulo: "Ao trabalho", primario: true}]});
}

$("#ir-para-clubes").addEventListener("click", () => irParaModo("clube"));
$("#assumir").addEventListener("click", assumir);
document.addEventListener("click", (ev) => {
  const a = ev.target.closest("[data-acao]");
  if (!a) return;
  if (a.dataset.acao === "voltar-menu") irParaModo("menu");
  if (a.dataset.acao === "voltar-nova") irParaModo("nova");
});

registrarModo("clube", {
  elemento: "#escolha-clube", abrir: abrirEscolha,
  tecla(ev) {
    if (ev.key === "Escape") irParaModo("nova");
    if (ev.key === "Enter") assumir();
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      const lista = clubesFiltrados();
      const i = lista.findIndex((c) => c.nome === ESCOLHA.selecionado);
      const j = Math.max(0, Math.min(lista.length - 1, i + (ev.key === "ArrowDown" ? 1 : -1)));
      ESCOLHA.selecionado = lista[j]?.nome;
      desenharClubes();
      $("#tabela-clubes tr.sel")?.scrollIntoView({block: "nearest"});
      ev.preventDefault();
    }
  },
});
