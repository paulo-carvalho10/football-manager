"use strict";
/* O jogo: a casca de gerenciamento e as telas do clube. */

let ESTADO = null;
let telaAtual = "elenco";
let selecionado = null;               // jogador em destaque na lateral
const ORDEM_ELENCO = {coluna: "titular", desc: true};

const ABAS = [
  {id: "elenco", rotulo: "Elenco", icone: "elenco"},
  {id: "escalacao", rotulo: "Escalação", icone: "tatica"},
  {id: "transferencias", rotulo: "Transferências", icone: "mercado"},
  {id: "classificacao", rotulo: "Tabela", icone: "tabela"},
  {id: "calendario", rotulo: "Calendário", icone: "calendario"},
  {id: "financas", rotulo: "Finanças", icone: "financas"},
  {id: "mensagens", rotulo: "Mensagens", icone: "mensagens"},
  {id: "treinador", rotulo: "Treinador", icone: "treinador"},
  {id: "destaques", rotulo: "Destaques", icone: "estrela"},
  {id: "salvar", rotulo: "Salvar", icone: "salvar", acao: janelaSalvar},
  {id: "menu", rotulo: "Menu", icone: "sair", acao: () => irParaModo("menu")},
];

const TELAS = {};

async function abrirJogo(tela) {
  $("#marca-topo").innerHTML = logo(true);
  $("#icones").innerHTML = ABAS.map((a) => `
    <button data-aba="${a.id}" title="${a.rotulo}">${icone(a.icone)}<span>${a.rotulo}</span>
      ${a.id === "mensagens" ? '<span class="badge" id="badge-msg" hidden></span>' : ""}</button>`).join("");
  $$("[data-aba]").forEach((b) => b.addEventListener("click", () => {
    const a = ABAS.find((x) => x.id === b.dataset.aba);
    if (a.acao) a.acao(); else irPara(a.id);
  }));
  await recarregarEstado();
  await irPara(tela || PARAMS.get("tela") || telaAtual);
  if (PARAMS.get("convites") && ESTADO.convites.length) janelaDeConvites(ESTADO.convites, ESTADO.demitido);
}

async function recarregarEstado() {
  const e = await api.get("/api/estado");
  if (e.sem_carreira) { irParaModo("menu"); return null; }
  aplicarEstado(e);
  return e;
}

function aplicarEstado(e) {
  ESTADO = e;
  document.documentElement.style.setProperty("--clube", corDeAcento(e.clube.cor));
  desenharTopo(e);
  desenharLateral(e);
  desenharRodape(e);
  // proposta nova por um jogador do clube abre a janela sozinha (transferencias.js)
  if (typeof verificarPropostas === "function") setTimeout(() => verificarPropostas(e), 0);
}

async function irPara(nome) {
  if (!TELAS[nome]) nome = "elenco";
  telaAtual = nome;
  $$(".tela").forEach((t) => t.classList.toggle("ativa", t.id === `tela-${nome}`));
  $$("[data-aba]").forEach((b) => b.classList.toggle("ativo", b.dataset.aba === nome));
  await TELAS[nome]();
}

/* ------------------------------------------------------------------ topo */

function textoDoProximo(e) {
  if (e.demitido) return {rotulo: "Você foi demitido", texto: `${e.convites.length} clube(s) chamando`, botao: "Ver convites ›"};
  if (e.acabou) return {rotulo: "Temporada encerrada", texto: "Balanço, acesso e mercado", botao: "Encerrar ano ›"};
  const p = e.proximo;
  if (p && p.tipo === "liga") {
    const casa = p.casa ? e.clube.nome : p.rival.nome;
    const fora = p.casa ? p.rival.nome : e.clube.nome;
    return {rotulo: `${p.competicao} · rodada ${p.rodada}`, texto: `${casa} x ${fora}`, botao: "Jogar ›"};
  }
  if (p) return {rotulo: `${p.competicao}`, texto: p.fase, botao: "Jogar ›"};
  return {rotulo: "Sem jogo do clube", texto: "Rodada dos outros", botao: "Avançar ›"};
}

function desenharTopo(e) {
  const t = textoDoProximo(e);
  $("#prox-rotulo").textContent = t.rotulo;
  $("#prox-texto").textContent = t.texto;
  $("#jogar").innerHTML = t.botao;
  const badge = $("#badge-msg");
  if (badge) { badge.hidden = !e.nao_lidas; badge.textContent = e.nao_lidas; }
}

/* ------------------------------------------------------------------ lateral */

function trilho(rotulo, v) {
  return `<div class="linha"><span>${rotulo}</span>
    <span class="trilho"><i style="width:${v}%;background:${corDe(v, 65, 40)}"></i></span><b>${Math.round(v)}%</b></div>`;
}

function desenharLateral(e) {
  const p = e.proximo;
  let prox = `<div class="vazio">Sem jogo marcado.</div>`;
  if (p && p.tipo === "liga") {
    const [casa, fora] = p.casa ? [e.clube, p.rival] : [p.rival, e.clube];
    prox = `<div class="confronto">
        <div>${escudo(casa)}<span>${escapar(casa.nome)}</span></div>
        <span class="x">×</span>
        <div>${escudo(fora)}<span>${escapar(fora.nome)}</span></div></div>
      <div class="onde">${escapar(p.competicao)} · rodada ${p.rodada} · ${p.casa ? "em casa" : "fora"}</div>`;
  } else if (p) {
    prox = `<div class="confronto"><div>${escudo(e.clube)}<span>${escapar(e.clube.nome)}</span></div>
      <span class="x">×</span><div>${escudo({nome: "?", cor: "#25302a", cor2: "#71897a"})}<span>sorteio da fase</span></div></div>
      <div class="onde">${escapar(p.competicao)} · ${escapar(p.fase)}</div>`;
  } else if (e.acabou) {
    prox = `<div class="vazio">Temporada encerrada.</div>`;
  }
  $("#lateral").innerHTML = `
    <div class="cartao-clube">
      <div class="topo-clube">${escudo(e.clube)}
        <div><h1>${escapar(e.clube.nome)}</h1>
          <div class="sub">${escapar(e.liga_nome)} · ${e.rodada ? `${e.posicao}º lugar` : "pré-temporada"}</div>
          <div class="sub">${icone("treinador", 'style="width:.9rem;height:.9rem;vertical-align:-2px"')} ${escapar(e.treinador)}</div></div>
      </div>
      <div class="confianca">${trilho("Diretoria", e.aprovacao.diretoria)}${trilho("Torcida", e.aprovacao.torcida)}</div>
      <div class="clima">Ambiente: <b>${escapar(clima(e.aprovacao.clima))}</b><br>Meta: ${escapar(e.aprovacao.meta)}</div>
    </div>
    <div class="painel fixo"><div class="cab"><h2>Próxima partida</h2></div>
      <div class="prox-jogo">${prox}
        <button class="btn azul bloco" id="btn-escalar">${icone("tatica")} Escalar time</button></div></div>
    <div class="painel fixo" id="resumo-jogador"></div>`;
  $("#btn-escalar").addEventListener("click", () => irPara("escalacao"));
  desenharResumoJogador();
}

const ROTULOS_ATRIBUTOS = {
  finalizacao: "Finalização", passe: "Passe", drible: "Drible", marcacao: "Marcação",
  velocidade: "Velocidade", forca: "Força", resistencia: "Resistência", tecnica: "Técnica",
  posicionamento: "Posicionamento", visao: "Visão", reflexos: "Reflexos", "jogo aereo": "Jogo aéreo",
};

async function desenharResumoJogador() {
  const alvo = $("#resumo-jogador");
  if (!alvo) return;
  const lista = ESTADO.elenco;
  const j = lista.find((p) => p.id === selecionado) || lista.find((p) => p.titular) || lista[0];
  if (!j) { alvo.innerHTML = ""; return; }
  const [perfil, svg] = await Promise.all([
    api.get(`/api/jogador?id=${j.id}`),
    camisa(ESTADO.clube.id, j.posicao === "GK" ? "2" : "1"),
  ]);
  const chaves = j.posicao === "GK"
    ? ["reflexos", "posicionamento", "jogo aereo", "passe"]
    : ["finalizacao", "passe", "drible", "marcacao", "velocidade", "forca"];
  alvo.innerHTML = `<div class="cab"><h2>Jogador</h2>
      <button class="btn fantasma pequeno" id="ver-perfil">Perfil ›</button></div>
    <div class="resumo-jogador">
      <div class="topo-j"><span class="camisa-mini">${idsProprios(svg)}</span>
        <div><h3>${escapar(j.nome)}</h3>
          <div class="linha-flex" style="margin-top:.3rem">${pos(j.posicao)} ${ovr(j.overall)}
            <span class="dica">${j.idade} anos · ${escapar(j.perfil)}</span></div></div></div>
      <div class="atributos-mini">${chaves.map((k) => {
        const v = perfil.atributos[k];
        return `<div><span>${ROTULOS_ATRIBUTOS[k]}</span><b>${v}</b>
          <span class="t"><i style="width:${v}%;background:${corDe(v, 75, 60)}"></i></span></div>`;
      }).join("")}</div>
      <div class="kpis">
        <div class="kpi-c"><span>Energia</span><b style="color:${corDe(j.energia, 85, 70)}">${j.energia}%</b></div>
        <div class="kpi-c"><span>Valor</span><b>${dinheiro(j.valor)}</b></div>
      </div>
      ${j.lesao ? `<p class="dica"><span class="ic-lesao">✚</span> ${escapar(j.lesao.tipo)} · ${j.lesao.dias} dias · volta ${j.lesao.volta}</p>` : ""}
      ${j.emprestado_de ? `<p class="dica">Emprestado pelo ${escapar(j.emprestado_de)} até o fim da temporada.</p>` : `
      <div class="linha-flex dica">Contrato: ${avisoDeContrato(j)}<span class="espaco"></span>
        <button class="btn pequeno" id="btn-emprestar">Emprestar</button>
        <button class="btn pequeno ${j.vence_em <= 1 ? "primario" : ""}" id="btn-renovar">Renovar</button></div>`}
    </div>`;
  $("#ver-perfil").addEventListener("click", () => abrirPerfil(j.id));
  $("#btn-renovar")?.addEventListener("click", () => renovarContrato(j.id));
  $("#btn-emprestar")?.addEventListener("click", () => emprestarJogador(j.id));
}

/* ------------------------------------------------------------------ rodape */

function desenharRodape(e) {
  $("#rodape").innerHTML = `
    <div>${icone("calendario")} <b>${e.data}</b></div>
    <div>Temporada <b>${e.temporada}</b></div>
    <div>${escapar(e.liga_nome)} · rodada <b>${e.rodada}</b>/${e.total_de_rodadas}</div>
    <div>${icone("financas")} Caixa <b class="${e.caixa < 0 ? "ruim" : ""}">${reais(e.caixa)}</b></div>
    <div>Reputação <b>${e.reputacao}</b></div>
    <span class="espaco"></span>
    <button id="rodape-msg">${icone("mensagens")} ${e.nao_lidas ? `<b>${e.nao_lidas}</b> não lidas` : "Mensagens"}</button>
    <div>${icone("treinador")} ${escapar(e.treinador)}</div>`;
  $("#rodape-msg").addEventListener("click", () => irPara("mensagens"));
}

/* ================================================================== ELENCO */

const COLUNAS_ELENCO = [
  {id: "posicao", rotulo: "Pos", valor: (p) => ORDEM_POS[p.posicao]},
  {id: "nome", rotulo: "Nome"},
  {id: "pe", rotulo: "Pé", classe: "c"},
  {id: "overall", rotulo: "OVR", classe: "n"},
  {id: "energia", rotulo: "Energia"},
  {id: "salario", rotulo: "Salário", classe: "n"},
  {id: "valor", rotulo: "Valor", classe: "n"},
  {id: "gols", rotulo: "Gols", classe: "n"},
  {id: "assistencias", rotulo: "Assist.", classe: "n"},
  {id: "perfil", rotulo: "Perfil"},
  {id: "idade", rotulo: "Idade", classe: "n"},
  {id: "cartoes", rotulo: "Cartões", classe: "c", valor: (p) => p.amarelos + 3 * p.vermelhos},
  {id: "contrato", rotulo: "Contrato", classe: "c"},
];

/** O aviso de contrato: vermelho acaba nesta temporada, amarelo na proxima. */
function avisoDeContrato(p) {
  if (p.vence_em <= 0) return `<span title="Contrato termina ao fim desta temporada: renove ou ele sai de graça">🔴 ${p.contrato}</span>`;
  if (p.vence_em === 1) return `<span title="Contrato termina ao fim da próxima temporada">🟡 ${p.contrato}</span>`;
  return `<span class="dica">${p.contrato}</span>`;
}
const ORDEM_POS = {GK: 0, DF: 1, MF: 2, FW: 3};

/** SUSPENSO / PENDURADO, sempre na competicao do proximo jogo. */
function seloGancho(p) {
  const emp = p.emprestado_de ? `<span class="selo-gancho emp" title="Emprestado pelo ${escapar(p.emprestado_de)} até o fim da temporada">EMP</span>` : "";
  if (p.lesao) return `<span class="selo-gancho les" title="${escapar(p.lesao.tipo)}: volta a partir de ${p.lesao.volta}">✚ ${p.lesao.dias}d</span>${emp}`;
  if (p.suspenso) return `<span class="selo-gancho susp" title="Suspenso para o próximo jogo desta competição">SUSPENSO</span>${emp}`;
  if (p.pendurado) return `<span class="selo-gancho pend" title="Mais um amarelo e fica fora do jogo seguinte">PENDURADO</span>${emp}`;
  return emp;
}

function ordenarElenco(lista) {
  const {coluna, desc} = ORDEM_ELENCO;
  const col = COLUNAS_ELENCO.find((c) => c.id === coluna);
  const v = (p) => coluna === "titular" ? (p.titular ? 1 : 0) * 1000 - ORDEM_POS[p.posicao] * 100 + p.overall / 10
    : col && col.valor ? col.valor(p) : p[coluna];
  return [...lista].sort((a, b) => {
    const va = v(a), vb = v(b);
    const r = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return desc ? -r : r;
  });
}

TELAS.elenco = function () {
  const e = ESTADO;
  const lista = ordenarElenco(e.elenco);
  const titulares = e.elenco.filter((p) => p.titular);
  const media = titulares.reduce((s, p) => s + p.overall, 0) / (titulares.length || 1);
  const folha = e.elenco.reduce((s, p) => s + p.salario, 0);
  const pe = (x) => x === "E" ? "Esq" : x === "A" ? "Amb" : "Dir";
  $("#tela-elenco").innerHTML = `
    <div class="painel">
      <div class="cab"><h2>Elenco · ${e.elenco.length} jogadores</h2>
        <span class="dica">Titulares: OVR médio ${media.toFixed(1)} · folha ${dinheiro(folha)}/mês</span>
        <button class="btn pequeno" id="ordem-padrao">Titulares primeiro</button></div>
      <div class="corpo sem-margem">
        <table class="grade" id="grade-elenco">
          <thead><tr>${COLUNAS_ELENCO.map((c) => `<th data-ord="${c.id}" class="${c.classe || ""}
            ${ORDEM_ELENCO.coluna === c.id ? "ativo" : ""} ${ORDEM_ELENCO.coluna === c.id && !ORDEM_ELENCO.desc ? "asc" : ""}">${c.rotulo}</th>`).join("")}</tr></thead>
          <tbody>${lista.map((p, i) => {
            const divisor = ORDEM_ELENCO.coluna === "titular" && i > 0 && lista[i - 1].titular && !p.titular;
            return `<tr class="clicavel ${p.titular ? "" : "reserva"} ${p.id === selecionado ? "sel" : ""} ${divisor ? "divisor" : ""}" data-id="${p.id}">
              <td>${pos(p.posicao)}</td>
              <td><div class="nome-celula"><b>${escapar(p.nome)}</b>
                ${e.funcoes.capitao === p.id ? '<span class="chip ouro">C</span>' : ""}${seloGancho(p)}</div></td>
              <td class="c">${pe(p.pe)}</td>
              <td class="n">${ovr(p.overall)}</td>
              <td>${energia(p.energia)}</td>
              <td class="n">${dinheiro(p.salario)}</td>
              <td class="n">${dinheiro(p.valor)}</td>
              <td class="n">${p.gols}</td>
              <td class="n">${p.assistencias}</td>
              <td>${escapar(p.perfil)}</td>
              <td class="n">${p.idade}</td>
              <td class="c">${p.amarelos ? `<span class="cartao am"></span> ${p.amarelos}` : ""}
                ${p.vermelhos ? ` <span class="cartao vm"></span> ${p.vermelhos}` : ""}</td>
              <td class="c">${avisoDeContrato(p)}</td>
            </tr>`;
          }).join("")}</tbody>
        </table>
      </div>
    </div>`;
  $$("#grade-elenco th[data-ord]").forEach((th) => th.addEventListener("click", () => {
    const c = th.dataset.ord;
    Object.assign(ORDEM_ELENCO, ORDEM_ELENCO.coluna === c ? {desc: !ORDEM_ELENCO.desc}
      : {coluna: c, desc: !["nome", "posicao", "perfil", "pe"].includes(c)});
    TELAS.elenco();
  }));
  $("#ordem-padrao").addEventListener("click", () => {
    Object.assign(ORDEM_ELENCO, {coluna: "titular", desc: true});
    TELAS.elenco();
  });
  $$("#grade-elenco tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      selecionado = +tr.dataset.id;
      $$("#grade-elenco tbody tr").forEach((x) => x.classList.toggle("sel", x === tr));
      desenharResumoJogador();
    });
    tr.addEventListener("dblclick", () => abrirPerfil(+tr.dataset.id));
  });
};

/* ================================================================== PERFIL DO JOGADOR */

async function abrirPerfil(id) {
  const j = await api.get(`/api/jogador?id=${id}`);
  if (j.erro) return avisar(j.erro);
  const svg = j.clube ? await camisa(j.clube.id, j.posicao === "GK" ? "2" : "1") : "";
  const t = j.temporada;
  const meu = j.clube && ESTADO && j.clube.id === ESTADO.clube.id;
  const attrs = Object.entries(j.atributos).map(([k, v]) => `
    <div class="attr"><span>${ROTULOS_ATRIBUTOS[k] || k}</span>
      <span class="t"><i style="width:${v}%;background:${corDe(v, 75, 60)}"></i></span><b>${v}</b></div>`).join("");
  return abrirJanela({titulo: escapar(j.nome), corpo: `
    <div class="perfil-j">
      <div>
        <span class="camisa-grande">${svg ? idsProprios(svg) : ""}</span>
        <div class="linha-flex" style="justify-content:center">${pos(j.posicao)} ${ovr(j.overall)}</div>
        <p class="dica" style="text-align:center">${escapar(j.posicao_detalhe)} · ${POSICOES_LONGAS[j.posicao]}</p>
        ${j.clube ? `<div class="linha-flex" style="justify-content:center">${escudo(j.clube)} <b>${escapar(j.clube.nome)}</b></div>` : ""}
      </div>
      <div>
        <div class="kpis">
          <div class="kpi-c"><span>Idade</span><b>${j.idade}</b></div>
          <div class="kpi-c"><span>Potencial</span><b>${j.potencial}</b></div>
          <div class="kpi-c"><span>Pé</span><b>${j.pe}</b></div>
          <div class="kpi-c"><span>Altura</span><b>${j.altura ? `${j.altura} cm` : "—"}</b></div>
          <div class="kpi-c"><span>Nacionalidade</span><b>${escapar(j.nacionalidade || "—")}</b></div>
          <div class="kpi-c"><span>Energia</span><b style="color:${corDe(j.energia, 85, 70)}">${j.energia}%</b></div>
          <div class="kpi-c"><span>Moral</span><b>${j.moral}</b></div>
          <div class="kpi-c"><span>Valor</span><b>${dinheiro(j.valor)}</b></div>
          <div class="kpi-c"><span>Salário/mês</span><b>${dinheiro(j.salario)}</b></div>
          <div class="kpi-c"><span>Contrato até</span><b>${j.contrato}</b></div>
        </div>
        <div class="secao"><h3>Atributos</h3><div class="atributos">${attrs}</div></div>
        <div class="secao"><h3>Temporada</h3>
          <div class="kpis">
            <div class="kpi-c"><span>Jogos</span><b>${t.jogos}</b></div>
            <div class="kpi-c destaque"><span>Gols</span><b>${t.gols}</b></div>
            <div class="kpi-c"><span>Assistências</span><b>${t.assistencias}</b></div>
            <div class="kpi-c"><span>Amarelos</span><b>${t.amarelos}</b></div>
            <div class="kpi-c"><span>Vermelhos</span><b>${t.vermelhos}</b></div>
          </div></div>
      </div>
    </div>`,
    botoes: meu && !j.emprestado_de
      ? [{rotulo: "Emprestar", valor: "emprestar"}, {rotulo: "Renovar contrato", valor: "renovar"}, {rotulo: "Fechar", primario: true}]
      : [{rotulo: "Fechar", primario: true}]}).then((r) => {
    if (r === "renovar") renovarContrato(j.id);
    if (r === "emprestar") emprestarJogador(j.id);
  });
}

/* ================================================================== ESCALACAO E TATICA */

let marcado = null;           // {id, onde: "campo" | "banco"}
let onzeLocal = null;         // o onze enquanto o usuario mexe, antes de mandar

const LINHAS_CAMPO = `
<svg class="linhas" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
  <g fill="none" stroke="#fff" stroke-opacity=".38" stroke-width=".45">
    <rect x="3" y="2.5" width="94" height="95"/><line x1="3" y1="50" x2="97" y2="50"/>
    <ellipse cx="50" cy="50" rx="10" ry="8"/>
    <rect x="25" y="83" width="50" height="14.5"/><rect x="38" y="92.5" width="24" height="5"/>
    <rect x="25" y="2.5" width="50" height="14.5"/><rect x="38" y="2.5" width="24" height="5"/>
    <path d="M40 83 A 11 8 0 0 1 60 83"/><path d="M40 17 A 11 8 0 0 0 60 17"/>
  </g></svg>`;

/** A lista do onze esta na ORDEM das vagas da formacao, que vem do servidor com rotulo,
 *  setor e posicao no desenho. Trocar dois titulares e trocar os dois de vaga -- e a vaga
 *  vale no jogo: quem ocupa a de centroavante finaliza como centroavante. */
function pecasNoCampo(titulares) {
  return ESTADO.tatica.posicoes.map((vaga, i) => ({p: titulares[i], vaga})).filter((x) => x.p);
}

TELAS.escalacao = async function () {
  const e = ESTADO;
  if (!onzeLocal) onzeLocal = [...e.onze];
  const porId = Object.fromEntries(e.elenco.map((p) => [p.id, p]));
  const titulares = onzeLocal.map((id) => porId[id]).filter(Boolean);
  const reservas = e.elenco.filter((p) => !onzeLocal.includes(p.id))
    .sort((a, b) => ORDEM_POS[a.posicao] - ORDEM_POS[b.posicao] || b.overall - a.overall);
  const [svgLinha, svgGol] = await Promise.all([camisa(e.clube.id, "1"), camisa(e.clube.id, "2")]);
  const media = titulares.reduce((s, p) => s + p.overall, 0) / (titulares.length || 1);
  const energiaMedia = titulares.reduce((s, p) => s + p.energia, 0) / (titulares.length || 1);
  const f = e.funcoes || {};

  const colocados = pecasNoCampo(titulares);
  const pecas = colocados.map(({p, vaga}) => `
    <button class="peca ${p.posicao !== vaga.setor ? "fora-de-posicao" : ""} ${p.suspenso ? "suspenso" : ""}
      ${marcado && marcado.id === p.id ? "marcado" : ""}" data-campo="${p.id}" draggable="true"
      title="${escapar(p.nome)} · ${ROTULOS_VAGA[vaga.rotulo] || vaga.rotulo}${p.posicao !== vaga.setor ? " (improvisado)" : ""}"
      style="left:${vaga.x}%;top:${vaga.y}%">
      ${seloGancho(p)}<span class="camisa-peca">${idsProprios(p.posicao === "GK" ? svgGol : svgLinha)}
        ${f.capitao === p.id ? '<span class="faixa">C</span>' : ""}</span>
      <span class="nome">${escapar(sobrenome(p.nome))}</span>
      <span class="info"><span class="vaga ${p.posicao !== vaga.setor ? "improvisado" : ""}">${vaga.rotulo}</span>${ovr(p.overall)}</span>
      <span class="energia"><i style="width:${p.energia}%;background:${corDe(p.energia, 85, 70)}"></i></span>
    </button>`).join("");

  const seg = (campo, opcoes, atual, rotulos = {}) => `<div class="segmentado" data-tatica="${campo}">${opcoes.map((o) =>
    `<button data-v="${o}" class="${o === atual ? "ativo" : ""}">${rotulos[o] || o}</button>`).join("")}</div>`;
  const opcoesFuncao = (chave) => `<select data-funcao="${chave}"><option value="">—</option>${titulares.map((p) =>
    `<option value="${p.id}" ${f[chave] === p.id ? "selected" : ""}>${escapar(p.nome)}</option>`).join("")}</select>`;
  const formacoes = [...e.opcoes.formacoes].sort();
  const improvisados = colocados.filter(({p, vaga}) => p.posicao !== vaga.setor)
    .map(({p, vaga}) => `${sobrenome(p.nome)} de ${vaga.rotulo}`);

  $("#tela-escalacao").innerHTML = `
    <div class="painel">
      <div class="cab"><h2>Escalação</h2>
        <select id="sel-formacao" style="width:auto">${formacoes.map((x) =>
          `<option ${x === e.tatica.formacao ? "selected" : ""}>${x}</option>`).join("")}</select>
        <button class="btn pequeno" id="auto">Automática</button>
        <button class="btn primario pequeno" id="confirmar-onze" ${onzeIgual() ? "disabled" : ""}>Confirmar</button></div>
      <div class="gramado" id="gramado">${LINHAS_CAMPO}${pecas}</div>
      <div class="pe"><span class="dica">OVR médio <b class="num">${media.toFixed(1)}</b> ·
        energia <b class="num">${energiaMedia.toFixed(0)}%</b></span>
        <span class="espaco" style="flex:1"></span>
        ${titulares.some((p) => p.suspenso) ? `<span class="chip" style="border-color:var(--ruim);color:var(--ruim)">suspenso na escalação: ${escapar(titulares.filter((p) => p.suspenso).map((p) => sobrenome(p.nome)).join(", "))} — entra o melhor reserva do setor</span>` : ""}
        ${improvisados.length ? `<span class="chip" style="border-color:var(--ruim);color:var(--ruim)">improvisado: ${escapar(improvisados.join(" · "))}</span>`
          : '<span class="chip ativo">todos na posição</span>'}
        <span class="dica">Clique em dois titulares para trocar de vaga · titular e reserva para substituir</span></div>
    </div>
    <div class="coluna">
      <div class="painel">
        <div class="cab"><h2>Reservas</h2><span class="dica">${reservas.length}</span></div>
        <div class="corpo sem-margem"><table class="grade compacta lista-banco"><tbody>${reservas.map((p) => `
          <tr class="clicavel ${marcado && marcado.id === p.id ? "marcado" : ""} ${p.suspenso ? "suspenso" : ""}" data-banco="${p.id}" draggable="true">
            <td>${pos(p.posicao)}</td><td><b>${escapar(p.nome)}</b> ${seloGancho(p)}</td>
            <td class="n">${ovr(p.overall)}</td><td>${energia(p.energia)}</td><td class="n dica">${p.idade}a</td></tr>`).join("")}
        </tbody></table></div>
      </div>
      <div class="painel fixo">
        <div class="cab"><h2>Tática</h2></div>
        <div class="corpo tatica-grade">
          <div class="linha-t"><span>Mentalidade</span>${seg("estilo", ["retrancado", "defensivo", "equilibrado", "ofensivo", "all-out"],
            e.tatica.estilo, {"retrancado": "Retranca", "defensivo": "Defensiva", "equilibrado": "Equilíbrio", "ofensivo": "Ofensiva", "all-out": "Tudo"})}</div>
          <div class="linha-t"><span>Marcação</span>${seg("marcacao", ["leve", "normal", "forte"], e.tatica.marcacao,
            {leve: "Leve", normal: "Normal", forte: "Pressão alta"})}</div>
          <div class="efeito" id="efeito-tatica">${efeitoDaTatica(e.tatica)}</div>
        </div>
      </div>
      <div class="painel fixo">
        <div class="cab"><h2>Funções</h2></div>
        <div class="corpo">
          <div class="funcoes">
            <label class="campo"><span>Capitão</span>${opcoesFuncao("capitao")}</label>
            <label class="campo"><span>Pênalti · 1º</span>${opcoesFuncao("penaltis")}</label>
            <label class="campo"><span>Pênalti · 2º</span>${opcoesFuncao("penaltis2")}</label>
            <label class="campo"><span>Pênalti · 3º</span>${opcoesFuncao("penaltis3")}</label>
            <label class="campo"><span>Faltas</span>${opcoesFuncao("faltas")}</label>
            <label class="campo"><span>Escanteios</span>${opcoesFuncao("escanteios")}</label>
          </div>
          <p class="nota-honesta">Os batedores de pênalti valem na partida: bate o primeiro que estiver em
            campo. Capitão, faltas e escanteios ficam salvos, mas ainda não mudam o resultado.</p>
        </div>
      </div>
    </div>`;
  ligarEscalacao();
};

function efeitoDaTatica(t) {
  const txt = {
    retrancado: "cria bem menos e concede bem menos", defensivo: "cria um pouco menos e se expõe menos",
    equilibrado: "sem viés: o elenco decide", ofensivo: "cria mais e se expõe mais",
    "all-out": "tudo ao ataque: muito mais gols pros dois lados",
  }[t.estilo];
  const mrc = {leve: "marcação leve poupa energia e cede espaço",
               normal: "marcação normal", forte: "pressão alta sufoca o rival e cansa o time na rodada seguinte"}[t.marcacao];
  return `<b>${t.formacao}</b> · ${txt}; ${mrc}. Os efeitos são modestos de propósito — tática é escolha, não atalho.`;
}

const ROTULOS_VAGA = {GOL: "goleiro", LE: "lateral-esquerdo", LD: "lateral-direito", ZAG: "zagueiro",
  VOL: "volante", MC: "meio-campo", MEI: "meia", ME: "meia-esquerda", MD: "meia-direita",
  PE: "ponta-esquerda", PD: "ponta-direita", CA: "centroavante"};

/** A ORDEM conta: e ela que diz quem ocupa cada vaga. */
function onzeIgual() {
  return onzeLocal && ESTADO && onzeLocal.length === ESTADO.onze.length
    && onzeLocal.every((id, i) => ESTADO.onze[i] === id);
}

function trocar(a, b) {
  // a e b: {id, onde}. Dois do campo trocam de vaga; campo e banco, substituicao.
  if (a.onde === "banco" && b.onde === "banco") { marcado = b; return; }
  if (a.onde === "campo" && b.onde === "campo") {
    const i = onzeLocal.indexOf(a.id), k = onzeLocal.indexOf(b.id);
    [onzeLocal[i], onzeLocal[k]] = [onzeLocal[k], onzeLocal[i]];
    marcado = null;
    return;
  }
  const doCampo = a.onde === "campo" ? a.id : b.id;
  const doBanco = a.onde === "banco" ? a.id : b.id;
  onzeLocal = onzeLocal.map((id) => id === doCampo ? doBanco : id);
  marcado = null;
}

function ligarEscalacao() {
  const clicar = (id, onde) => {
    if (!marcado) marcado = {id, onde};
    else if (marcado.id === id) marcado = null;
    else trocar(marcado, {id, onde});
    TELAS.escalacao();
  };
  $$("[data-campo]").forEach((el) => {
    el.addEventListener("click", () => clicar(+el.dataset.campo, "campo"));
    el.addEventListener("dblclick", () => abrirPerfil(+el.dataset.campo));
  });
  $$("[data-banco]").forEach((el) => {
    el.addEventListener("click", () => clicar(+el.dataset.banco, "banco"));
    el.addEventListener("dblclick", () => abrirPerfil(+el.dataset.banco));
  });
  // arrastar: do banco para o campo e do campo para o banco
  const alvos = [...$$("[data-campo]"), ...$$("[data-banco]")];
  alvos.forEach((el) => {
    const eu = () => el.dataset.campo ? {id: +el.dataset.campo, onde: "campo"} : {id: +el.dataset.banco, onde: "banco"};
    el.addEventListener("dragstart", (ev) => { ev.dataTransfer.setData("text/plain", JSON.stringify(eu())); });
    el.addEventListener("dragover", (ev) => { ev.preventDefault(); el.classList.add("alvo"); });
    el.addEventListener("dragleave", () => el.classList.remove("alvo"));
    el.addEventListener("drop", (ev) => {
      ev.preventDefault();
      const origem = JSON.parse(ev.dataTransfer.getData("text/plain"));
      if (origem.id !== eu().id && !(origem.onde === "banco" && eu().onde === "banco")) {
        trocar(origem, eu());
        TELAS.escalacao();
      }
    });
  });
  $("#auto").addEventListener("click", async () => {
    const r = await api.post("/api/escalar", {formacao: ESTADO.tatica.formacao});
    aplicarEstado(r.estado);
    onzeLocal = [...r.estado.onze];
    avisar("Escalação automática aplicada");
    TELAS.escalacao();
  });
  $("#confirmar-onze").addEventListener("click", mandarOnze);
  $("#sel-formacao").addEventListener("change", (ev) => mandarTatica({formacao: ev.target.value}));
  $$("[data-tatica] button").forEach((b) => b.addEventListener("click", () =>
    mandarTatica({[b.parentNode.dataset.tatica]: b.dataset.v})));
  $$("[data-funcao]").forEach((s) => s.addEventListener("change", async () => {
    const funcoes = {...ESTADO.funcoes};
    $$("[data-funcao]").forEach((x) => { if (x.value) funcoes[x.dataset.funcao] = +x.value; else delete funcoes[x.dataset.funcao]; });
    const r = await api.post("/api/escalar", {onze: ESTADO.onze, funcoes});
    aplicarEstado(r.estado);
    TELAS.escalacao();
  }));
}

async function mandarOnze() {
  const r = await api.post("/api/escalar", {onze: onzeLocal, funcoes: ESTADO.funcoes});
  if (r.erro) { avisar(r.erro); return; }
  aplicarEstado(r.estado);
  onzeLocal = [...r.estado.onze];
  avisar("Escalação confirmada");
  TELAS.escalacao();
}

async function mandarTatica(mudanca) {
  const t = {...ESTADO.tatica, ...mudanca};
  // mudar a formacao sem escolher o onze refaz a escalacao automatica para o esquema novo
  const corpo = {formacao: t.formacao, marcacao: t.marcacao, estilo: t.estilo};
  if (!mudanca.formacao) corpo.onze = onzeIgual() ? ESTADO.onze : onzeLocal;
  const r = await api.post("/api/escalar", corpo);
  if (r.erro) { avisar(r.erro); return; }
  aplicarEstado(r.estado);
  onzeLocal = [...r.estado.onze];
  TELAS.escalacao();
}

/* ================================================================== CLASSIFICACAO */

// comp "auto" = a competicao do proximo jogo. A escolha do usuario vale ate a data andar.
let CLASS = {comp: "auto", visao: "geral", bloco: null, data: null};

function seletorDeCompeticao(lista, atual) {
  const grupo = (tipo, rotulo) => {
    const itens = lista.filter((x) => x.tipo === tipo);
    return itens.length ? `<optgroup label="${rotulo}">${itens.map((x) =>
      `<option value="${x.id}" ${x.id === atual ? "selected" : ""}>${escapar(x.nome)}${x.minha ? " ★" : ""}</option>`).join("")}</optgroup>` : "";
  };
  return `<select id="sel-comp" class="sel-comp" title="Escolher competição">${grupo("liga", "Ligas")}${grupo("copa", "Copas")}</select>`;
}

TELAS.classificacao = async function () {
  if (CLASS.data !== ESTADO.indice_da_data) {
    Object.assign(CLASS, {comp: PARAMS.get("comp") || "auto",
                          bloco: PARAMS.get("bloco") ? +PARAMS.get("bloco") : null, data: ESTADO.indice_da_data});
  }
  const d = await api.get(`/api/classificacao?comp=${encodeURIComponent(CLASS.comp)}`);
  if (d.tipo === "copa") return telaDaCopa(d);
  CLASS.comp = d.liga;
  const z = d.zonas;
  const n = d.linhas.length;
  const zona = (i) => i <= z.continental ? "continental" : i <= z.acesso ? "acesso"
    : i > n - z.rebaixamento ? "rebaixamento" : "";
  const v = CLASS.visao;
  const linha = (l) => v === "geral" ? l : {...l, ...l[v]};
  const ordenadas = v === "geral" ? d.linhas : [...d.linhas].sort((a, b) =>
    b[v].pontos - a[v].pontos || (b[v].gols_pro - b[v].gols_contra) - (a[v].gols_pro - a[v].gols_contra) || b[v].gols_pro - a[v].gols_pro);
  const lista = (titulo, itens, fmt) => `<div class="painel fixo"><div class="cab"><h2>${titulo}</h2></div>
    <div class="corpo sem-margem"><table class="grade compacta"><tbody>${itens.length ? itens.map(fmt).join("")
      : '<tr><td class="vazio">Sem jogos ainda.</td></tr>'}</tbody></table></div></div>`;
  const corSituacao = {"vivo": "bom", "campeão": "ouro", "eliminado": "ruim"};
  const copas = ESTADO.copas.map((c) => `<tr><td><b>${escapar(c.nome)}</b><div class="dica">${escapar(c.fase)}</div></td>
    <td class="${corSituacao[c.situacao] || "fraco"}" style="white-space:normal">${escapar(c.situacao)}</td></tr>`);

  $("#tela-classificacao").innerHTML = `
    <div class="painel">
      <div class="cab">${seletorDeCompeticao(d.competicoes, d.liga)}<h2>rodada ${d.rodada}/${d.total_de_rodadas}</h2>
        <span class="espaco"></span>
        <div class="segmentado" style="width:15rem">${[["geral", "Geral"], ["casa", "Casa"], ["fora", "Fora"]].map(([k, r]) =>
          `<button data-visao="${k}" class="${k === v ? "ativo" : ""}">${r}</button>`).join("")}</div></div>
      <div class="corpo sem-margem"><table class="grade">
        <thead><tr><th class="c">#</th><th>Clube</th><th class="n">P</th><th class="n">J</th><th class="n">V</th>
          <th class="n">E</th><th class="n">D</th><th class="n">GP</th><th class="n">GC</th><th class="n">SG</th>
          <th class="n">%</th><th class="c">Últimos 5</th></tr></thead>
        <tbody>${ordenadas.map((l0, i) => {
          const l = linha(l0);
          const sg = l.gols_pro - l.gols_contra;
          return `<tr class="${l0.eu ? "eu" : ""}">
            <td class="c"><span class="zona ${v === "geral" ? zona(i + 1) : ""}">${i + 1}</span></td>
            <td><div class="nome-celula">${escudo(l0.clube)}<b>${escapar(l0.clube.nome)}</b></div></td>
            <td class="n"><b>${l.pontos}</b></td><td class="n">${l.jogos}</td><td class="n">${l.vitorias}</td>
            <td class="n">${l.empates}</td><td class="n">${l.derrotas}</td><td class="n">${l.gols_pro}</td>
            <td class="n">${l.gols_contra}</td><td class="n ${sg > 0 ? "bom" : sg < 0 ? "ruim" : ""}">${sg > 0 ? "+" : ""}${sg}</td>
            <td class="n">${l.jogos ? Math.round(100 * l.pontos / (3 * l.jogos)) : 0}</td>
            <td class="c">${forma(l0.ultimos)}</td></tr>`;
        }).join("")}</tbody></table></div>
      <div class="pe">
        ${z.continental ? '<span class="linha-flex"><span class="zona continental">&nbsp;</span> <span class="dica">vaga continental (indicativa)</span></span>' : ""}
        ${z.acesso ? '<span class="linha-flex"><span class="zona acesso">&nbsp;</span> <span class="dica">acesso</span></span>' : ""}
        ${z.rebaixamento ? '<span class="linha-flex"><span class="zona rebaixamento">&nbsp;</span> <span class="dica">rebaixamento</span></span>' : ""}
      </div>
    </div>
    <div class="coluna" style="overflow:auto">
      ${lista("Artilharia", d.artilheiros.slice(0, 6), (x, i) => `<tr class="${x.meu ? "eu" : ""}"><td class="n">${i + 1}</td>
        <td><b>${escapar(x.nome)}</b><div class="dica">${escapar(x.clube)}</div></td><td class="n"><b>${x.gols}</b></td></tr>`)}
      ${lista("Assistências", d.garcons.slice(0, 5), (x, i) => `<tr class="${x.meu ? "eu" : ""}"><td class="n">${i + 1}</td>
        <td><b>${escapar(x.nome)}</b><div class="dica">${escapar(x.clube)}</div></td><td class="n"><b>${x.assistencias}</b></td></tr>`)}
      ${lista("Melhores defesas", d.melhores_defesas.slice(0, 3), (x) => `<tr><td>${escapar(x.clube)}</td><td class="n">${x.gols} gc</td></tr>`)}
      ${lista("Piores defesas", d.piores_defesas.slice(0, 3), (x) => `<tr><td>${escapar(x.clube)}</td><td class="n ruim">${x.gols} gc</td></tr>`)}
      ${lista("Copas", copas, (x) => x)}
    </div>`;
  ligarSeletorDeCompeticao();
  $$("[data-visao]").forEach((b) => b.addEventListener("click", () => { CLASS.visao = b.dataset.visao; TELAS.classificacao(); }));
};

function ligarSeletorDeCompeticao() {
  $("#sel-comp").addEventListener("change", (ev) => {
    CLASS.comp = ev.target.value;
    CLASS.bloco = null;
    TELAS.classificacao();
  });
}

/* ------------------------------------------------------------------ copas
 * Uma copa em abas por fase. Fases de mata-mata seguidas viram UM chaveamento, em
 * colunas (oitavas -> quartas -> semi -> final), com as rodadas ainda por sortear vazias.
 * Os pares sao sorteados a cada rodada (fm.copa), entao a coluna seguinte so se preenche
 * depois do sorteio: nao ha arvore fixa para desenhar antes. */

function blocosDaCopa(d) {
  const blocos = [];
  for (const f of d.fases) {
    const ultimo = blocos[blocos.length - 1];
    // rodadas de mata-mata seguidas ficam juntas, ate uma fase que recebe clubes novos
    // (a Serie A entrando na Copa do Brasil): ali comeca outro chaveamento
    if (f.tipo === "mata" && ultimo && ultimo.tipo === "mata" && !f.abre) ultimo.fases.push(f);
    else blocos.push({tipo: f.tipo, nome: f.nome, fases: [f]});
  }
  if (d.a_sortear.length) {
    const ultimo = blocos[blocos.length - 1];
    if (ultimo && ultimo.tipo === "mata") ultimo.vazias = d.a_sortear;
    else blocos.push({tipo: "mata", nome: "Mata-mata", fases: [], vazias: d.a_sortear});
  }
  const ultimoMata = blocos.filter((b) => b.tipo === "mata").pop();
  if (ultimoMata && (ultimoMata.fases.length + (ultimoMata.vazias || []).length) > 1) ultimoMata.nome = "Chaveamento";
  return blocos;
}

function miniTabela(linhas, avancam, titulo) {
  return `<div class="mini-tabela">${titulo ? `<h3>${escapar(titulo)}</h3>` : ""}
    <table class="grade compacta"><thead><tr><th class="c">#</th><th>Clube</th><th class="n">P</th><th class="n">J</th>
      <th class="n">V</th><th class="n">SG</th></tr></thead>
    <tbody>${linhas.map((l) => `<tr class="${l.eu ? "eu" : ""}">
      <td class="c"><span class="zona ${l.posicao <= avancam ? "acesso" : ""}">${l.posicao}</span></td>
      <td><div class="nome-celula">${escudo(l.clube, "1.2rem")}<b>${escapar(l.clube.nome)}</b></div></td>
      <td class="n"><b>${l.pontos}</b></td><td class="n">${l.jogos}</td><td class="n">${l.vitorias}</td>
      <td class="n">${l.saldo > 0 ? "+" : ""}${l.saldo}</td></tr>`).join("")}</tbody></table></div>`;
}

function cartaoDeConfronto(x) {
  const lado = (clube, gols) => {
    const perdeu = x.vencedor && x.vencedor !== clube.id;
    return `<div class="lado-c ${x.vencedor === clube.id ? "venceu" : ""} ${perdeu ? "caiu" : ""}">
      ${escudo(clube, "1.2rem")}<span class="nm">${escapar(clube.nome)}</span><b>${x.agregado ? gols : ""}</b></div>`;
  };
  const jogos = x.jogos.length > 1 ? `<div class="jogos-c">${x.jogos.map((j) =>
    `<span>${j.gols_casa}–${j.gols_fora}</span>`).join(" · ")}</div>` : "";
  return `<div class="confronto ${x.meu ? "meu" : ""}">${lado(x.casa, x.agregado?.[0])}${lado(x.fora, x.agregado?.[1])}${jogos}</div>`;
}

function chaveamento(bloco) {
  const colunas = bloco.fases.map((f) => `<div class="coluna-chave">
      <h3>${escapar(f.nome)}${f.em_curso ? ' <span class="chip ouro">agora</span>' : ""}</h3>
      <div class="cartas">${f.confrontos.map(cartaoDeConfronto).join("")}
        ${f.poupados.length ? `<div class="dica poupados">Direto para a rodada seguinte: ${f.poupados.map((k) => escapar(k.nome)).join(", ")}</div>` : ""}</div>
    </div>`);
  const vazias = (bloco.vazias || []).map((nome) => `<div class="coluna-chave vazia">
      <h3>${escapar(nome)}</h3><div class="cartas"><div class="confronto a-sortear">a sortear</div></div></div>`);
  return `<div class="chave">${[...colunas, ...vazias].join("")}</div>`;
}

function telaDaCopa(d) {
  const blocos = blocosDaCopa(d);
  if (CLASS.bloco === null || CLASS.bloco >= blocos.length) {
    // abre na ultima fase que ja teve jogo, nao num chaveamento so com "a sortear"
    const comJogo = blocos.map((b, i) => (b.fases.length ? i : -1)).filter((i) => i >= 0);
    CLASS.bloco = comJogo.length ? comJogo[comJogo.length - 1] : Math.max(0, blocos.length - 1);
  }
  const b = blocos[CLASS.bloco];
  let corpo = '<div class="vazio">A competição ainda não começou: os confrontos aparecem depois do sorteio.</div>';
  if (b && b.tipo === "grupos") {
    const f = b.fases[0];
    corpo = `<div class="grade-grupos">${f.grupos.map((g) => miniTabela(g.linhas, f.avancam, g.nome)).join("")}</div>`;
  } else if (b && b.tipo === "liga") {
    const f = b.fases[0];
    corpo = `<div style="padding:.6rem 1rem">${miniTabela(f.linhas, f.avancam)}</div>`;
  } else if (b) {
    corpo = chaveamento(b);
  }
  $("#tela-classificacao").innerHTML = `
    <div class="painel">
      <div class="cab">${seletorDeCompeticao(d.competicoes, d.id)}
        <h2>${d.campeao ? `Campeão: ${escapar(d.campeao.nome)}` : escapar(d.fase_atual)}</h2>
        <span class="espaco"></span>
        ${blocos.length > 1 ? `<div class="abas">${blocos.map((x, i) =>
          `<button data-bloco="${i}" class="${i === CLASS.bloco ? "ativo" : ""}">${escapar(x.nome)}</button>`).join("")}</div>` : ""}</div>
      <div class="corpo sem-margem copa-corpo">${corpo}</div>
      ${b && b.tipo !== "mata" ? `<div class="pe"><span class="linha-flex"><span class="zona acesso">&nbsp;</span>
        <span class="dica">avança de fase</span></span></div>` : ""}
    </div>
    <div class="coluna" style="overflow:auto">
      <div class="painel fixo"><div class="cab"><h2>Artilharia</h2></div>
        <div class="corpo sem-margem"><table class="grade compacta"><tbody>${d.artilheiros.slice(0, 8).map((x, i) => `
          <tr class="${x.meu ? "eu" : ""}"><td class="n">${i + 1}</td><td><b>${escapar(x.nome)}</b><div class="dica">${escapar(x.clube)}</div></td>
          <td class="n"><b>${x.gols}</b></td></tr>`).join("") || '<tr><td class="vazio">Sem gols ainda.</td></tr>'}</tbody></table></div></div>
    </div>`;
  ligarSeletorDeCompeticao();
  $$("[data-bloco]").forEach((x) => x.addEventListener("click", () => { CLASS.bloco = +x.dataset.bloco; telaDaCopa(d); }));
}

/* O MERCADO virou a tela de Transferencias: fm/web/transferencias.js */

/* ================================================================== CALENDARIO */

TELAS.calendario = async function () {
  const [cal, ini] = await Promise.all([api.get("/api/calendario"), api.get("/api/inicio")]);
  const c = ini.campanha;
  $("#tela-calendario").innerHTML = `
    <div class="painel">
      <div class="cab"><h2>Calendário ${ESTADO.temporada}</h2><span class="dica">${cal.datas.length} datas · liga e copas</span></div>
      <div class="corpo sem-margem"><table class="grade" id="grade-cal">
        <thead><tr><th class="n">#</th><th>Data</th><th>Competição</th><th>Adversário</th><th class="c">Local</th><th class="c">Resultado</th></tr></thead>
        <tbody>${cal.datas.map((d) => {
          const r = d.resultado;
          const res = r ? `<span class="forma"><i class="${r.resultado}">${r.resultado}</i></span> <b class="num">${r.gols_casa} x ${r.gols_fora}</b>` : "";
          return `<tr class="${d.ordem === cal.atual ? "eu" : ""} ${d.passou ? "reserva" : ""}">
            <td class="n">${d.ordem + 1}</td><td class="num">${d.dia.slice(0, 5)}</td>
            <td>${d.tipo === "copa" ? `<span class="chip ouro">${escapar(d.competicao)}</span>` : `${escapar(ESTADO.liga_nome)} · ${d.rodada}ª rodada`}</td>
            <td>${d.rival ? `<b>${escapar(d.rival.nome)}</b>` : '<span class="dica">conforme o chaveamento</span>'}</td>
            <td class="c">${d.rival ? (d.rival.casa ? "Casa" : "Fora") : ""}</td>
            <td class="c">${res}</td></tr>`;
        }).join("")}</tbody></table></div>
    </div>
    <div class="coluna">
      <div class="painel fixo"><div class="cab"><h2>Campanha na liga</h2></div>
        <div class="corpo"><div class="kpis">
          <div class="kpi-c destaque"><span>Posição</span><b>${c.posicao ? `${c.posicao}º` : "—"}</b></div>
          <div class="kpi-c"><span>Pontos</span><b>${c.pontos}</b></div>
          <div class="kpi-c"><span>Jogos</span><b>${c.jogos}</b></div>
          <div class="kpi-c"><span>V-E-D</span><b>${c.vitorias}-${c.empates}-${c.derrotas}</b></div>
          <div class="kpi-c"><span>Gols</span><b>${c.gols_pro}:${c.gols_contra}</b></div>
        </div></div></div>
      <div class="painel"><div class="cab"><h2>Últimos jogos</h2></div>
        <div class="corpo sem-margem"><table class="grade compacta"><tbody>${ini.ultimos.map((r) => `
          <tr><td>${forma([r.resultado])}</td><td>${escapar(r.casa)}</td><td class="n"><b>${r.gols_casa} x ${r.gols_fora}</b></td>
          <td>${escapar(r.fora)}</td></tr>`).join("") || '<tr><td class="vazio">Nenhum jogo ainda.</td></tr>'}</tbody></table></div></div>
    </div>`;
  $("#grade-cal tr.eu")?.scrollIntoView({block: "center"});
};

/* ================================================================== FINANCAS */

TELAS.financas = async function () {
  const f = await api.get("/api/financas");
  const despesas = f.folha + f.operacao;
  const maior = Math.max(f.receita, despesas, 1);
  const barraH = (rotulo, v, cor) => `<div style="margin-bottom:.8rem"><div class="linha-flex"><span>${rotulo}</span>
    <span class="espaco"></span><b class="num">${reais(v)}</b></div>
    <div class="forca-barra" style="width:100%;height:.7rem;margin-top:.3rem"><i style="width:${100 * v / maior}%;background:${cor}"></i></div></div>`;
  $("#tela-financas").innerHTML = `
    <div class="coluna">
      <div class="painel fixo"><div class="cab"><h2>Situação</h2></div>
        <div class="corpo"><div class="kpis">
          <div class="kpi-c destaque"><span>Caixa</span><b>${dinheiro(f.caixa)}</b></div>
          <div class="kpi-c"><span>Valor do elenco</span><b>${dinheiro(f.valor_do_elenco)}</b></div>
          <div class="kpi-c"><span>Reputação</span><b>${f.reputacao}</b></div>
          <div class="kpi-c"><span>Saldo previsto</span><b class="${f.saldo_previsto < 0 ? "ruim" : "bom"}">${dinheiro(f.saldo_previsto)}</b></div>
        </div></div></div>
      <div class="painel"><div class="cab"><h2>Orçamento do ano</h2></div>
        <div class="corpo">
          ${barraH("Receita prevista", f.receita, "var(--bom)")}
          ${barraH("Folha salarial", f.folha, "var(--ruim)")}
          ${barraH("Custo de operação", f.operacao, "#c77a2a")}
          <p class="nota-honesta">A receita sai do valor do elenco no início do ano e da reputação; premiação
            de liga e de copas entra no fechamento. O balanço é feito na virada da temporada.</p>
        </div></div>
      <div class="painel fixo"><div class="cab"><h2>Folha por setor</h2><span class="dica">por mês</span></div>
        <div class="corpo">${folhaPorSetor()}</div></div>
      <div class="painel"><div class="cab"><h2>Contratos terminando</h2><span class="dica">até ${ESTADO.temporada + 1}</span></div>
        <div class="corpo sem-margem"><table class="grade compacta"><tbody>${ESTADO.elenco
          .filter((p) => p.contrato <= ESTADO.temporada + 1).sort((a, b) => a.contrato - b.contrato || b.overall - a.overall)
          .map((p) => `<tr><td>${pos(p.posicao)}</td><td><b>${escapar(p.nome)}</b></td><td class="n">${ovr(p.overall)}</td>
            <td class="n">${p.idade}a</td><td class="n ${p.contrato <= ESTADO.temporada ? "ruim" : "medio"}">${p.contrato}</td></tr>`).join("")
          || '<tr><td class="vazio">Nenhum contrato perto do fim.</td></tr>'}</tbody></table></div></div>
    </div>
    <div class="painel"><div class="cab"><h2>Maiores salários</h2></div>
      <div class="corpo sem-margem"><table class="grade">
        <thead><tr><th>Jogador</th><th>Pos</th><th class="n">Salário/mês</th><th class="n">Valor</th><th class="n">Contrato</th></tr></thead>
        <tbody>${f.salarios.map((s) => `<tr><td><b>${escapar(s.nome)}</b></td><td>${pos(s.posicao)}</td>
          <td class="n">${dinheiro(s.salario)}</td><td class="n">${dinheiro(s.valor)}</td>
          <td class="n ${s.contrato <= ESTADO.temporada ? "ruim" : ""}">${s.contrato}</td></tr>`).join("")}</tbody></table></div></div>`;
};

function folhaPorSetor() {
  const soma = {GK: 0, DF: 0, MF: 0, FW: 0};
  ESTADO.elenco.forEach((p) => { soma[p.posicao] += p.salario; });
  const total = Object.values(soma).reduce((a, b) => a + b, 0) || 1;
  return Object.entries(soma).map(([g, v]) => `<div class="linha-flex" style="margin-bottom:.45rem">
    <span style="width:6.5rem">${pos(g)} <span class="dica">${POSICOES_LONGAS[g]}</span></span>
    <span class="forca-barra" style="flex:1;width:auto;height:.55rem"><i style="width:${100 * v / total}%"></i></span>
    <b class="num" style="width:6rem;text-align:right">${dinheiro(v)}</b>
    <span class="dica num" style="width:3rem;text-align:right">${Math.round(100 * v / total)}%</span></div>`).join("");
}

/* ================================================================== MENSAGENS */

let msgSelecionada = null;

TELAS.mensagens = async function () {
  const {mensagens} = await api.get("/api/mensagens");
  if (!mensagens.some((m) => m.id === msgSelecionada)) msgSelecionada = mensagens[0]?.id ?? null;
  const m = mensagens.find((x) => x.id === msgSelecionada);
  $("#tela-mensagens").innerHTML = `
    <div class="painel"><div class="cab"><h2>Caixa de entrada</h2>
        <button class="btn pequeno" id="ler-todas">Marcar todas como lidas</button></div>
      <div class="corpo sem-margem caixa-msg">${mensagens.map((x) => `
        <div class="msg ${x.lida ? "lida" : ""} ${x.tipo} ${x.id === msgSelecionada ? "sel" : ""}" data-msg="${escapar(x.id)}">
          <span class="ponto"></span>
          <div><b>${escapar(x.assunto)}</b><small>${escapar(x.remetente)} · ${x.data}</small></div>
        </div>`).join("") || '<div class="vazio">Nada por aqui.</div>'}</div></div>
    <div class="painel"><div class="corpo leitura">${m ? `
      <h2>${escapar(m.assunto)}</h2><div class="de">De: ${escapar(m.remetente)} · ${m.data}</div>
      <p>${escapar(m.texto)}</p>` : '<div class="vazio">Selecione uma mensagem.</div>'}
      <p class="nota-honesta" style="margin-top:2rem">A caixa é montada da situação do clube a cada dia: o que a diretoria,
        a torcida, a preparação física e o olheiro diriam hoje.</p></div></div>`;
  if (m && !m.lida) {
    await api.post("/api/lida", {ids: [m.id]});
    recarregarEstado();
  }
  $$("[data-msg]").forEach((el) => el.addEventListener("click", () => { msgSelecionada = el.dataset.msg; TELAS.mensagens(); }));
  $("#ler-todas").addEventListener("click", async () => {
    await api.post("/api/lida", {ids: mensagens.map((x) => x.id)});
    await recarregarEstado();
    TELAS.mensagens();
  });
};

/* ================================================================== TREINADOR */

TELAS.treinador = async function () {
  const [t, rk] = await Promise.all([api.get("/api/treinador"), api.get("/api/tecnicos")]);
  const n = t.total;
  const rep = rk.reputacao;
  $("#tela-treinador").innerHTML = `
    <div class="coluna">
      <div class="painel fixo"><div class="corpo" style="text-align:center">
        <div class="avatar-treinador" style="justify-content:center;flex-direction:column;border:0;background:none">
          <div class="rosto" style="width:5.5rem;height:5.5rem">${icone("pessoa", 'style="width:3rem;height:3rem"')}</div>
          <b style="font-size:1.3rem">${escapar(t.nome)}</b>
          <span class="dica">Treinador do ${escapar(t.clube)} · ${t.temporadas}ª temporada</span></div>
        <div class="kpis" style="margin-top:.8rem">
          <div class="kpi-c destaque"><span>Reputação</span><b>${String(rep.valor).replace(".", ",")}</b></div>
          <div class="kpi-c"><span>Ranking</span><b>${rep.posicao}º</b></div></div>
        <div class="confianca" style="margin-top:1rem;text-align:left">${trilho("Diretoria", t.diretoria)}${trilho("Torcida", t.torcida)}</div>
        <p class="clima" style="text-align:left">Ambiente: <b>${escapar(clima(t.clima))}</b></p>
      </div></div>
      <div class="painel fixo"><div class="cab"><h2>Carreira</h2></div><div class="corpo"><div class="kpis">
        <div class="kpi-c"><span>Jogos</span><b>${n.jogos}</b></div>
        <div class="kpi-c"><span>Vitórias</span><b class="bom">${n.vitorias}</b></div>
        <div class="kpi-c"><span>Empates</span><b>${n.empates}</b></div>
        <div class="kpi-c"><span>Derrotas</span><b class="ruim">${n.derrotas}</b></div>
        <div class="kpi-c destaque"><span>Aproveitamento</span><b>${String(t.aproveitamento).replace(".", ",")}%</b></div>
        <div class="kpi-c"><span>Gols</span><b>${n.gols_pro}:${n.gols_contra}</b></div>
      </div></div></div>
    </div>
    <div class="coluna">
      <div class="painel fixo"><div class="cab"><h2>Títulos</h2></div><div class="corpo">${t.titulos.length
        ? `<div class="lista-simples">${t.titulos.map((x) => `<div class="item ok">${icone("tabela")}<b>${escapar(x.nome)}</b>
            <span class="espaco"></span><span class="dica">${x.temporada}</span></div>`).join("")}</div>`
        : '<div class="vazio">Nenhum título ainda. A primeira taça é a mais difícil.</div>'}</div></div>
      <div class="painel fixo"><div class="cab"><h2>Confiança na temporada</h2>
          <span class="linha-flex dica"><span class="cartao" style="background:var(--ouro);width:.8rem;height:.3rem"></span>Diretoria
          <span class="cartao" style="background:var(--bom);width:.8rem;height:.3rem"></span>Torcida</span></div>
        <div class="corpo">${curvaDeConfianca(t.curva)}</div></div>
      <div class="painel"><div class="cab"><h2>Temporada a temporada</h2></div>
        <div class="corpo sem-margem"><table class="grade">
          <thead><tr><th>Ano</th><th>Clube</th><th>Divisão</th><th class="n">Pos</th><th class="n">J</th><th class="n">V</th>
            <th class="n">E</th><th class="n">D</th><th>Destino</th></tr></thead>
          <tbody>
            <tr class="eu"><td>${t.atual.temporada}</td><td>${escapar(t.clube)}</td><td>${escapar(t.atual.liga)}</td>
              <td class="n">${t.atual.posicao || "—"}</td><td class="n">${t.atual.numeros.jogos}</td><td class="n">${t.atual.numeros.vitorias}</td>
              <td class="n">${t.atual.numeros.empates}</td><td class="n">${t.atual.numeros.derrotas}</td><td class="dica">em andamento</td></tr>
            ${t.anos.map((a) => `<tr><td>${a.temporada}</td><td>${escapar(a.clube)}</td><td>${escapar(a.liga)}</td>
              <td class="n">${a.posicao}º</td><td class="n">${a.numeros.jogos ?? "—"}</td><td class="n">${a.numeros.vitorias ?? "—"}</td>
              <td class="n">${a.numeros.empates ?? "—"}</td><td class="n">${a.numeros.derrotas ?? "—"}</td>
              <td>${a.subiu ? '<span class="bom">acesso</span>' : a.caiu ? '<span class="ruim">rebaixado</span>' : ""}</td></tr>`).join("")}
          </tbody></table></div></div>
    </div>
    <div class="coluna">
      <div class="painel"><div class="cab"><h2>Ranking de técnicos</h2><span class="dica">reputação</span></div>
        <div class="corpo sem-margem" style="overflow:auto"><table class="grade compacta">
          <thead><tr><th class="n">#</th><th>Técnico</th><th>Clube</th><th class="n">Rep.</th><th class="n">Ano</th><th class="n">Tít.</th></tr></thead>
          <tbody>${rk.ranking.map((x) => `<tr class="${x.usuario ? "eu" : ""}"><td class="n">${x.posicao}</td>
            <td><b>${escapar(x.nome)}</b> <span class="dica">${x.idade}</span></td>
            <td>${x.clube ? `<div class="nome-celula">${escudo(x.clube, "1.1rem")}<span>${escapar(x.clube.nome)}</span></div>` : '<span class="dica">sem clube</span>'}</td>
            <td class="n"><b>${String(x.reputacao).replace(".", ",")}</b></td>
            <td class="n ${x.variacao > 0 ? "bom" : x.variacao < 0 ? "ruim" : "dica"}">${x.variacao > 0 ? "+" : ""}${String(x.variacao).replace(".", ",")}</td>
            <td class="n">${x.titulos || ""}</td></tr>`).join("")}</tbody></table></div>
        <div class="pe"><span class="dica">A reputação anda na virada: o que você fez com o elenco que tinha, títulos, acesso e queda.
          É ela que faz clubes maiores te chamarem.</span></div></div>
    </div>`;
};

function curvaDeConfianca(curva) {
  if (curva.length < 2) return '<div class="vazio">A curva aparece depois das primeiras rodadas.</div>';
  const L = 600, A = 150, n = curva.length;
  const x = (i) => 30 + (i * (L - 40)) / (n - 1);
  const y = (v) => 10 + (A - 30) * (1 - v / 100);
  const linha = (k) => curva.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p[k]).toFixed(1)}`).join(" ");
  const guias = [25, 50, 75].map((v) => `<line x1="30" x2="${L - 10}" y1="${y(v)}" y2="${y(v)}" stroke="#21503a" stroke-dasharray="3 4"/>
    <text x="4" y="${y(v) + 4}" fill="#71897a" font-size="11">${v}</text>`).join("");
  return `<svg viewBox="0 0 ${L} ${A}" style="width:100%;height:9rem" preserveAspectRatio="none">${guias}
    <path d="${linha("diretoria")}" fill="none" stroke="#f3c332" stroke-width="2.4" vector-effect="non-scaling-stroke"/>
    <path d="${linha("torcida")}" fill="none" stroke="#3fcf72" stroke-width="2.4" vector-effect="non-scaling-stroke"/></svg>`;
}

/* ================================================================== SALVAR E VIRADA */

function janelaSalvar() {
  return abrirJanela({titulo: "Salvar carreira", estreita: true, corpo: `
    <label class="campo"><span>Nome do save</span>
      <input type="text" id="nome-save" value="${escapar(ESTADO.clube.nome.toLowerCase().replace(/[^a-z0-9]+/g, "-"))}-${ESTADO.temporada}"></label>
    <p class="nota-honesta">O save guarda a semente e as suas decisões — escalações, táticas e trocas durante
      os jogos —, não o mundo inteiro. Por isso tem poucos KB.</p>`,
    botoes: [{rotulo: "Cancelar"}, {rotulo: "Salvar", primario: true, acao: async () => {
      const nome = $("#nome-save").value.trim().replace(/[^\w-]+/g, "-") || "carreira";
      const r = await api.post("/api/salvar", {nome});
      avisar(r.erro ? r.erro : `Salvo em ${r.arquivo.split(/[\\/]/).pop()}`);
    }}]});
}

async function encerrarAno() {
  const r = await api.post("/api/virar");
  if (r.erro) return avisar(r.erro);
  aplicarEstado(r.estado);
  onzeLocal = null;
  const destino = r.subi ? '<span class="chip ativo">ACESSO</span>' : r.cai ? '<span class="chip" style="color:var(--ruim);border-color:var(--ruim)">REBAIXADO</span>' : "";
  const campeoes = Object.entries({...r.campeoes, ...r.copas}).filter(([, v]) => v);
  let corpo = r.demitido ? `<div class="aviso"><b>Você foi demitido</b>${escapar(r.motivo)}</div>` : "";
  corpo += `<div class="kpis">
      <div class="kpi-c destaque"><span>Sua posição</span><b>${r.posicao}º</b></div>
      <div class="kpi-c"><span>Divisão</span><b>${escapar(r.liga_nome)}</b></div>
      <div class="kpi-c"><span>Torcida</span><b>${Math.round(r.clima.torcida || 0)}%</b></div>
      <div class="kpi-c"><span>Diretoria</span><b>${Math.round(r.clima.diretoria || 0)}%</b></div>
    </div>
    <p>${destino} ${r.clima.meta ? `Meta: ${escapar(r.clima.meta)} — ${r.clima.bateu_a_meta ? '<span class="bom">cumprida</span>' : '<span class="ruim">não cumprida</span>'}` : ""}</p>
    <div class="secao"><h3>Campeões</h3><table class="grade compacta"><tbody>${campeoes.map(([k, v]) =>
      `<tr><td>${escapar(r.nomes[k] || k)}</td><td><b>${escapar(v)}</b></td></tr>`).join("")}</tbody></table></div>`;
  if (r.balanco) {
    const b = r.balanco;
    const saldo = b.receita + b.premiacao - b.folha - b.operacao;
    corpo += `<div class="secao"><h3>Balanço</h3><div class="kpis">
      <div class="kpi-c"><span>Receita</span><b>${dinheiro(b.receita)}</b></div>
      <div class="kpi-c"><span>Premiação</span><b>${dinheiro(b.premiacao)}</b></div>
      <div class="kpi-c"><span>Folha</span><b>${dinheiro(b.folha)}</b></div>
      <div class="kpi-c"><span>Operação</span><b>${dinheiro(b.operacao)}</b></div>
      <div class="kpi-c destaque"><span>Saldo</span><b class="${saldo < 0 ? "ruim" : "bom"}">${dinheiro(saldo)}</b></div></div></div>`;
  }
  if (r.compras.length || r.vendas.length) {
    corpo += `<div class="secao"><h3>Mercado do clube</h3><table class="grade compacta"><tbody>
      ${r.compras.map((t) => `<tr><td class="bom">chega</td><td>${escapar(t.nome)} (${t.overall})</td><td>${escapar(t.de)}</td><td class="n">${dinheiro(t.preco)}</td></tr>`).join("")}
      ${r.vendas.map((t) => `<tr><td class="ruim">sai</td><td>${escapar(t.nome)} (${t.overall})</td><td>${escapar(t.para)}</td><td class="n">${dinheiro(t.preco)}</td></tr>`).join("")}
      </tbody></table></div>`;
  }
  corpo += blocoDeReputacao(r.reputacao_tecnico);
  corpo += `<p class="dica">${r.aposentaram} aposentadorias no mundo, ${r.revelados} garotos subiram da base, ${r.transferencias} transferências.</p>`;
  await abrirJanela({titulo: `Fim da temporada ${r.temporada}`, corpo,
                     botoes: [{rotulo: "Premiações ›", primario: true}]});
  if (r.premios) await janelaDePremios(r.premios);
  if (r.convites.length || r.demitido) {
    const assumiu = await janelaDeConvites(r.convites, r.demitido);
    if (!assumiu && r.demitido) return irParaModo("menu");
  }
  irPara(telaAtual);
}

function blocoDeReputacao(rep) {
  if (!rep || rep.valor === undefined) return "";
  const v = rep.variacao || 0;
  return `<div class="secao"><h3>Sua reputação</h3><div class="kpis">
    <div class="kpi-c destaque"><span>Reputação</span><b>${String(rep.valor).replace(".", ",")}</b></div>
    <div class="kpi-c"><span>No ano</span><b class="${v > 0 ? "bom" : v < 0 ? "ruim" : ""}">${v > 0 ? "+" : ""}${String(v).replace(".", ",")}</b></div>
    <div class="kpi-c"><span>Ranking</span><b>${rep.posicao}º de ${rep.de}</b></div></div></div>`;
}

/* ------------------------------------------------------------------ premiacoes */

function linhaDePremio(rotulo, x, extra) {
  if (!x) return "";
  const meu = x.clube === ESTADO.clube.id;
  return `<tr class="${meu ? "eu" : ""}"><td class="dica">${rotulo}</td><td>${pos(x.posicao)} <b>${escapar(x.nome)}</b></td>
    <td class="dica">${escapar(x.clube_nome)}</td><td class="n">${extra(x)}</td></tr>`;
}

function htmlDePremios(p) {
  const media = (x) => `nota ${x.media.toFixed(2).replace(".", ",")}`;
  const podio = p.bola_de_ouro.map((x, i) => `<div class="degrau d${i + 1} ${x.clube === ESTADO.clube.id ? "meu" : ""}">
      <span class="medalha">${["🥇", "🥈", "🥉"][i]}</span><b>${escapar(x.nome)}</b>
      <span class="dica">${escapar(x.clube_nome)} · ${media(x)} · ${x.gols} gols</span></div>`).join("");
  const ligas = Object.values(p.ligas).map((d) => `<div class="secao"><h3>${escapar(d.nome)}</h3>
      <table class="grade compacta"><tbody>
        ${linhaDePremio("Craque da liga", d.craque, media)}
        ${linhaDePremio("Artilheiro", d.artilheiro, (x) => `${x.gols} gols`)}
        ${linhaDePremio("Garçom", d.garcom, (x) => `${x.assistencias} assist.`)}
        ${linhaDePremio("Melhor goleiro", d.goleiro, media)}
        ${linhaDePremio("Revelação", d.revelacao, (x) => `${x.idade} anos · ${media(x)}`)}
        ${d.tecnico ? `<tr class="${d.tecnico.usuario ? "eu" : ""}"><td class="dica">Técnico do ano</td>
          <td colspan="3"><b>${escapar(d.tecnico.nome)}</b>${d.tecnico.usuario ? ' <span class="chip ouro">você</span>' : ""}</td></tr>` : ""}
      </tbody></table>
      ${d.selecao.length ? `<div class="selecao-do-ano"><span class="dica">Seleção do ano:</span>
        ${d.selecao.map((x) => `<span class="${x.clube === ESTADO.clube.id ? "meu" : ""}">${escapar(x.nome)}</span>`).join(" · ")}</div>` : ""}
    </div>`).join("");
  return `<div class="bola-de-ouro"><h3>Bola de Ouro ${p.temporada}</h3><div class="podio">${podio}</div></div>${ligas}
    <p class="nota-honesta">Pela média das notas do ano (mínimo de jogos), com um pouco a mais para quem ganhou título.
      Premiado ganha moral.</p>`;
}

function janelaDePremios(p) {
  return abrirJanela({titulo: `Premiações ${p.temporada}`, corpo: htmlDePremios(p),
                     botoes: [{rotulo: "Continuar ›", primario: true}]});
}

/* ------------------------------------------------------------------ convites
 * Demitido, escolher um convite e obrigatorio (ou volta ao menu). Empregado, da para
 * ficar. Aceitar e uma acao do save: o replay refaz a troca no mesmo ponto. */

async function janelaDeConvites(convites, obrigatorio) {
  const corpo = `${obrigatorio ? `<div class="aviso"><b>Você foi demitido</b>${escapar(ESTADO.motivo || "")}</div>` : ""}
    <p class="dica">${convites.length ? "Clubes que querem você no comando:" : "Nenhum clube chamou."}</p>
    <div class="convites">${convites.map((k) => `<div class="convite">
      ${escudo(k.clube, "2.6rem")}<div class="info"><b>${escapar(k.clube.nome)}</b>
        <span class="dica">${escapar(k.liga)}${k.posicao ? ` · ${k.posicao}º na tabela` : ""} · tradição ${k.reputacao}</span>
        ${k.tecnico_atual ? `<span class="dica">demite ${escapar(k.tecnico_atual)} para você assumir</span>` : ""}</div>
      <button class="btn primario" data-assumir="${k.clube.id}">Assumir</button></div>`).join("")}</div>`;
  let escolhido = null;
  const promessa = abrirJanela({titulo: obrigatorio ? "Convites" : "Propostas de outros clubes", corpo,
    botoes: [{rotulo: obrigatorio ? "Voltar ao menu" : `Ficar no ${escapar(ESTADO.clube.nome)}`, valor: null}]});
  $$("[data-assumir]").forEach((b) => b.addEventListener("click", async () => {
    const r = await api.post("/api/assumir", {clube: +b.dataset.assumir});
    if (r.erro) return avisar(r.erro);
    escolhido = r;
    fecharJanela();
  }));
  await promessa;
  if (!escolhido) return false;
  aplicarEstado(escolhido.estado);
  onzeLocal = null;
  avisar(escolhido.mensagem);
  irPara("elenco");
  return true;
}

/* ================================================================== JOGAR */

async function jogar() {
  const e = ESTADO;
  if (e.demitido) {
    const assumiu = await janelaDeConvites(e.convites, true);
    if (!assumiu) irParaModo("menu");
    return;
  }
  if (e.acabou) return encerrarAno();
  if (!onzeIgual() && onzeLocal) await mandarOnze();
  irParaModo("aovivo");
}

$("#jogar").addEventListener("click", jogar);

registrarModo("jogo", {
  elemento: "#jogo",
  abrir: (tela) => abrirJogo(tela),
  tecla(ev) {
    if (ev.key === "Enter" && !ev.repeat) { jogar(); ev.preventDefault(); }
    const atalhos = {"1": "elenco", "2": "escalacao", "3": "transferencias", "4": "classificacao",
                     "5": "calendario", "6": "financas", "7": "mensagens", "8": "treinador",
                     "9": "destaques"};
    if (atalhos[ev.key]) irPara(atalhos[ev.key]);
    if (ev.key === "Escape" && marcado) { marcado = null; TELAS.escalacao(); }
  },
});


/* ================================================================== DESTAQUES
 * A selecao de cada rodada de liga e a artilharia de cada competicao, deste ano e dos
 * anos que ja acabaram. */

const DEST = {liga: null, rodada: null, comp: null, temporada: null};

function classeDaNota(n) { return n >= 8 ? "n8" : n >= 7 ? "n7" : n >= 6 ? "n6" : n >= 5 ? "n5" : "n4"; }

function campinhoDaSelecao(s) {
  if (!s.onze.length) return '<div class="vazio">A seleção aparece depois da primeira rodada.</div>';
  return `<div class="campinho">${LINHAS_CAMPO}${s.onze.map((j) => `
    <div class="destaque ${j.meu ? "meu" : ""} ${j.craque ? "craque" : ""}" style="left:${j.x}%;top:${j.y}%"
      title="${escapar(j.nome)} · ${escapar(j.clube.nome)}">
      ${escudo(j.clube)}
      <span class="nome">${escapar(sobrenome(j.nome))}</span>
      <span class="linha-d"><span class="vaga">${j.vaga}</span>
        <span class="nota ${classeDaNota(j.nota)}">${j.nota.toFixed(1).replace(".", ",")}</span>
        ${j.gols ? `<span>${"⚽".repeat(Math.min(j.gols, 3))}</span>` : ""}</span>
    </div>`).join("")}</div>`;
}

TELAS.destaques = async function () {
  const qs = new URLSearchParams();
  if (DEST.liga) qs.set("liga", DEST.liga);
  if (DEST.rodada) qs.set("rodada", DEST.rodada);
  const qa = new URLSearchParams();
  if (DEST.comp) qa.set("comp", DEST.comp);
  if (DEST.temporada) qa.set("temporada", DEST.temporada);
  const [s, a, pr] = await Promise.all([api.get(`/api/selecao?${qs}`), api.get(`/api/artilharia?${qa}`),
                                        api.get(`/api/premios${DEST.anoPremio ? `?temporada=${DEST.anoPremio}` : ""}`)]);
  DEST.liga = s.liga;
  DEST.comp = a.competicao;
  DEST.temporada = a.temporada;
  const i = s.rodadas.indexOf(s.rodada);
  const craque = s.onze.find((j) => j.craque);
  const passado = a.temporada !== ESTADO.temporada;

  $("#tela-destaques").innerHTML = `
    <div class="painel">
      <div class="cab"><h2>Seleção da rodada</h2>
        <div class="abas">${s.ligas.map((l) => `<button data-sliga="${l.id}" class="${l.id === s.liga ? "ativo" : ""}">${escapar(l.nome)}</button>`).join("")}</div>
        <div class="navegador">
          <button class="btn pequeno" id="rod-ant" ${i > 0 ? "" : "disabled"}>‹</button>
          <b>${s.rodada ? `${s.rodada}ª rodada` : "—"}</b>
          <button class="btn pequeno" id="rod-prox" ${i >= 0 && i < s.rodadas.length - 1 ? "" : "disabled"}>›</button>
        </div></div>
      ${campinhoDaSelecao(s)}
      <div class="pe">${craque ? `<span class="chip ouro">★ Craque da rodada: ${escapar(craque.nome)} (${escapar(craque.clube.nome)}) · ${craque.nota.toFixed(1).replace(".", ",")}</span>` : ""}
        ${s.meus ? `<span class="chip ativo">${s.meus} do ${escapar(ESTADO.clube.nome)}</span>` : ""}
        <span class="espaco" style="flex:1"></span>
        <span class="dica">4-3-3 pelas notas · no seu jogo a nota vem dos lances; nos outros, do placar, gols e assistências</span></div>
    </div>
    <div class="coluna">
      <div class="painel">
        <div class="cab"><h2>Artilharia</h2>
          <select id="art-temporada" style="width:auto">${a.temporadas.map((t) =>
            `<option value="${t}" ${t === a.temporada ? "selected" : ""}>${t}${t === ESTADO.temporada ? " (atual)" : ""}</option>`).join("")}</select></div>
        <div class="corpo sem-margem">
          <div class="abas" style="padding:.5rem .8rem">${a.competicoes.map((c) =>
            `<button data-comp="${c.id}" class="${c.id === a.competicao ? "ativo" : ""}">${escapar(c.nome)}</button>`).join("")
            || '<span class="dica">Nenhum gol ainda.</span>'}</div>
          <table class="grade compacta"><thead><tr><th class="n">#</th><th>Jogador</th><th>Clube</th>
            <th class="n">J</th><th class="n">G</th>${passado ? "" : '<th class="n">A</th><th class="n">Média</th>'}</tr></thead>
          <tbody>${a.artilheiros.map((x, k) => `<tr class="${x.meu ? "eu" : ""}">
            <td class="n">${k + 1}</td><td><b>${escapar(x.nome)}</b></td>
            <td><div class="nome-celula">${x.clube && x.clube.id ? escudo(x.clube, "1.2rem") : ""}<span>${escapar(x.clube ? x.clube.nome : "")}</span></div></td>
            <td class="n">${x.jogos}</td><td class="n"><b>${x.gols}</b></td>
            ${passado ? "" : `<td class="n">${x.assistencias}</td><td class="n dica">${x.jogos ? (x.gols / x.jogos).toFixed(2).replace(".", ",") : "—"}</td>`}</tr>`).join("")
            || '<tr><td colspan="7" class="vazio">Sem gols nesta competição.</td></tr>'}</tbody></table>
        </div></div>
      <div class="painel fixo">
        <div class="cab"><h2>${passado ? "Artilheiros de cada competição" : "Assistências"}</h2></div>
        <div class="corpo sem-margem" style="max-height:15rem;overflow:auto"><table class="grade compacta"><tbody>${passado
          ? a.campeoes.filter((x) => x.temporada === a.temporada).map((x) => `<tr><td>${escapar(x.competicao)}</td>
              <td><b>${escapar(x.nome)}</b> <span class="dica">${escapar(x.clube)}</span></td><td class="n"><b>${x.gols}</b></td></tr>`).join("")
          : a.garcons.slice(0, 8).map((x, k) => `<tr class="${x.meu ? "eu" : ""}"><td class="n">${k + 1}</td><td><b>${escapar(x.nome)}</b>
              <span class="dica">${escapar(x.clube ? x.clube.nome : "")}</span></td><td class="n"><b>${x.assistencias}</b></td></tr>`).join("")
            || '<tr><td class="vazio">Nenhuma assistência ainda.</td></tr>'}</tbody></table></div></div>
      <div class="painel fixo">
        <div class="cab"><h2>Galeria de artilheiros</h2><span class="dica">o maior de cada competição, ano a ano</span></div>
        <div class="corpo sem-margem" style="max-height:12rem;overflow:auto"><table class="grade compacta"><tbody>${a.campeoes.map((x) =>
          `<tr><td class="n">${x.temporada}</td><td>${escapar(x.competicao)}</td><td><b>${escapar(x.nome)}</b>
            <span class="dica">${escapar(x.clube)}</span></td><td class="n"><b>${x.gols}</b></td></tr>`).join("")
          || '<tr><td class="vazio">A galeria começa quando a primeira temporada terminar.</td></tr>'}</tbody></table></div></div>
      <div class="painel fixo">
        <div class="cab"><h2>Premiações</h2>${pr.temporadas.length ? `<select id="premio-ano" style="width:auto">${pr.temporadas.map((t) =>
          `<option value="${t}" ${t === pr.temporada ? "selected" : ""}>${t}</option>`).join("")}</select>` : ""}</div>
        <div class="corpo" style="max-height:22rem;overflow:auto">${pr.premios ? htmlDePremios(pr.premios)
          : '<div class="vazio">A Bola de Ouro e os prêmios de cada liga saem no fim da primeira temporada.</div>'}</div></div>
    </div>`;

  $$("[data-sliga]").forEach((b) => b.addEventListener("click", () => { DEST.liga = b.dataset.sliga; DEST.rodada = null; TELAS.destaques(); }));
  $("#rod-ant").addEventListener("click", () => { DEST.rodada = s.rodadas[i - 1]; TELAS.destaques(); });
  $("#rod-prox").addEventListener("click", () => { DEST.rodada = s.rodadas[i + 1]; TELAS.destaques(); });
  $$("[data-comp]").forEach((b) => b.addEventListener("click", () => { DEST.comp = b.dataset.comp; TELAS.destaques(); }));
  $("#art-temporada").addEventListener("change", (ev) => { DEST.temporada = +ev.target.value; DEST.comp = null; TELAS.destaques(); });
  $("#premio-ano")?.addEventListener("change", (ev) => { DEST.anoPremio = +ev.target.value; TELAS.destaques(); });
};
