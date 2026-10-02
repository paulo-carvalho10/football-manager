"use strict";
/* Transferencias: mercado, negociacoes, propostas recebidas e historico.
 *
 * Fluxo curto de proposito (o brief: "receber informacao -> decidir -> continuar"):
 * oferta ao clube -> contrato com o jogador -> pronto. Quem responde e o servidor; a tela
 * so pergunta e mostra. */

const TRF = {
  aba: PARAMS.get("trf") || "mercado",       // ?trf=olheiro abre direto numa aba
  filtros: {nome: "", pos: "", idade_min: "", idade_max: "", nacionalidade: "", clube: "",
            valor_max: "", salario_max: "", ovr_min: "", situacao: "", liga: ""},
  lista: null, selecionado: null,
  propostasVistas: new Set(),
};

const SITUACOES = [["", "Todos"], ["a_venda", "À venda"], ["sem_contrato", "Sem contrato"],
                   ["terminando", "Contrato terminando"], ["moral_baixa", "Moral baixa (negociação facilitada)"],
                   ["lista", "Minha lista"]];

/* Negociacao: taxa de transferencia digitada em euro; salario na moeda do clube, que volta
 * para euro antes de ir ao servidor. */
function lerNumero(txt) { return Math.round(+String(txt).replace(/[^\d]/g, "") || 0); }
function lerSalario(txt) { return paraEuro(lerNumero(txt)); }
function salarioNoCampo(v) { return daMoeda(v).toLocaleString("pt-BR"); }

TELAS.transferencias = async function () {
  const alvo = $("#tela-transferencias");
  alvo.innerHTML = `
    <div class="painel" style="grid-column:1 / -1">
      <div class="cab"><h2>Transferências</h2>
        <div class="abas" id="trf-abas">${[["mercado", "Mercado"], ["olheiro", "Olheiro"], ["negociacoes", "Negociações"],
          ["propostas", "Propostas recebidas"], ["historico", "Histórico"]].map(([k, r]) =>
          `<button data-trf="${k}" class="${TRF.aba === k ? "ativo" : ""}">${r}</button>`).join("")}</div>
        <span class="espaco" style="flex:1"></span><span id="trf-caixa" class="linha-flex"></span></div>
      <div class="corpo sem-margem" id="trf-corpo" style="display:grid;min-height:0"></div>
    </div>`;
  $$("[data-trf]").forEach((b) => b.addEventListener("click", () => { TRF.aba = b.dataset.trf; TELAS.transferencias(); }));
  await ({mercado: abaMercado, olheiro: abaOlheiro, negociacoes: abaNegociacoes, propostas: abaPropostas,
          historico: abaHistorico}[TRF.aba])();
};

function pintarCaixa(cx) {
  if (!cx) return;
  const perto = cx.folha > cx.limite_da_folha * 0.9;
  $("#trf-caixa").innerHTML = `
    <span class="kpi-c destaque" style="padding:.25rem .6rem"><span>Caixa</span><b>${dinheiro(cx.caixa)}</b></span>
    <span class="kpi-c" style="padding:.25rem .6rem"><span>Folha / limite (mês)</span>
      <b class="${perto ? "ruim" : ""}">${dinheiro(cx.folha)} / ${dinheiro(cx.limite_da_folha)}</b></span>
    <span class="kpi-c" style="padding:.25rem .6rem"><span>Elenco</span><b>${cx.elenco}</b></span>`;
}

/* ------------------------------------------------------------------ mercado */

async function abaMercado() {
  const f = TRF.filtros;
  const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== "")).toString();
  TRF.lista = await api.get(`/api/mercado?${q}`);
  pintarCaixa(TRF.lista.caixa);
  if (!TRF.lista.jogadores.some((j) => j.id === TRF.selecionado)) TRF.selecionado = TRF.lista.jogadores[0]?.id ?? null;
  const campo = (rot, html) => `<label class="campo"><span>${rot}</span>${html}</label>`;
  $("#trf-corpo").style.gridTemplateColumns = "15rem minmax(0,1fr) 22rem";
  $("#trf-corpo").innerHTML = `
    <div class="filtros" style="padding:.9rem;border-right:1px solid var(--linha);overflow:auto">
      ${campo("Buscar", `<input type="search" data-f="nome" value="${escapar(f.nome)}" placeholder="Buscar jogador...">`)}
      ${campo("Posição", `<select data-f="pos"><option value="">Todas</option>${Object.entries(POSICOES_LONGAS).map(([k, v]) =>
        `<option value="${k}" ${f.pos === k ? "selected" : ""}>${v}</option>`).join("")}</select>`)}
      <div class="campo"><span>Idade</span><div class="campo-duplo">
        <input type="number" data-f="idade_min" placeholder="mín" value="${f.idade_min}">
        <input type="number" data-f="idade_max" placeholder="máx" value="${f.idade_max}"></div></div>
      ${campo("Nacionalidade", `<input type="search" data-f="nacionalidade" value="${escapar(f.nacionalidade)}" placeholder="ex.: Brasil">`)}
      ${campo("Clube", `<input type="search" data-f="clube" value="${escapar(f.clube)}" placeholder="ex.: Santos">`)}
      <div class="campo"><span>Valor (€ mi) e salário (${MOEDA.simbolo} mi) máximos</span><div class="campo-duplo">
        <input type="number" data-f="valor_max" data-mi="1" placeholder="valor" value="${f.valor_max ? f.valor_max / 1e6 : ""}">
        <input type="number" data-f="salario_max" data-mi="1" step="0.01" placeholder="salário" value="${f.salario_max ? daMoeda(f.salario_max) / 1e6 : ""}"></div></div>
      ${campo("Força mínima", `<input type="number" data-f="ovr_min" value="${f.ovr_min}" placeholder="ex.: 70">`)}
      ${campo("Situação", `<select data-f="situacao">${SITUACOES.map(([k, r]) =>
        `<option value="${k}" ${f.situacao === k ? "selected" : ""}>${r}</option>`).join("")}</select>`)}
      ${campo("Liga", `<select data-f="liga"><option value="">Todas</option>${TRF.lista.ligas.map((l) =>
        `<option value="${l.id}" ${f.liga === l.id ? "selected" : ""}>${escapar(l.nome)}</option>`).join("")}</select>`)}
      <button class="btn primario" id="buscar">Buscar</button>
      <button class="btn" id="limpar">Limpar filtros</button>
    </div>
    <div style="overflow:auto;min-height:0">
      <div class="dica" style="padding:.5rem .8rem">${TRF.lista.total.toLocaleString("pt-BR")} jogadores${TRF.lista.total > 250 ? " · mostrando os 250 mais fortes" : ""}</div>
      <table class="grade" id="grade-trf"><thead><tr><th>Jogador</th><th>Pos</th><th class="n">Idade</th><th>Clube</th>
        <th class="n">Força</th><th class="n">Valor</th><th class="n">Salário</th></tr></thead>
      <tbody>${TRF.lista.jogadores.map((j) => `<tr class="clicavel ${j.id === TRF.selecionado ? "sel" : ""}" data-id="${j.id}">
        <td><b>${escapar(j.nome)}</b>${j.observado ? ' <span class="ouro">★</span>' : ""}${seloQuerSair(j)}</td><td>${pos(j.posicao)}</td>
        <td class="n">${j.idade}</td>
        <td>${j.livre ? '<span class="chip ativo">sem contrato</span>'
          : `<div class="nome-celula">${escudo(j.clube, "1.3rem")}<span>${escapar(j.clube.nome)}</span></div>`}</td>
        <td class="n">${ovr(j.overall)}</td><td class="n">${euros(j.valor)}</td><td class="n">${dinheiro(j.salario)}</td></tr>`).join("")
        || '<tr><td colspan="7" class="vazio">Ninguém com esse perfil.</td></tr>'}</tbody></table>
    </div>
    <div id="trf-detalhe" style="border-left:1px solid var(--linha);overflow:auto"></div>`;

  const aplicar = () => {
    $$("[data-f]").forEach((x) => {
      // o salario maximo e digitado na moeda do clube; o filtro do servidor e em euro
      const mi = (v) => x.dataset.f === "salario_max" ? paraEuro(v * 1e6) : Math.round(v * 1e6);
      TRF.filtros[x.dataset.f] = x.dataset.mi ? (x.value ? String(mi(+x.value)) : "") : x.value;
    });
    abaMercado();
  };
  $("#buscar").addEventListener("click", aplicar);
  $$("[data-f]").forEach((x) => x.addEventListener("keydown", (ev) => { if (ev.key === "Enter") aplicar(); }));
  $$("select[data-f]").forEach((x) => x.addEventListener("change", aplicar));
  $("#limpar").addEventListener("click", () => { Object.keys(TRF.filtros).forEach((k) => { TRF.filtros[k] = ""; }); abaMercado(); });
  $$("#grade-trf tbody tr[data-id]").forEach((tr) => tr.addEventListener("click", () => {
    TRF.selecionado = +tr.dataset.id;
    $$("#grade-trf tbody tr").forEach((x) => x.classList.toggle("sel", x === tr));
    detalheTrf();
  }));
  detalheTrf();
}

/* O jogador insatisfeito no clube dele (fm.moral): o dono vende por menos, ate titular,
 * e ele aceita vir para um clube menor. */
function seloQuerSair(j) {
  if (j.insatisfeito) return ' <span class="moral insatisfeito" title="Insatisfeito no clube: sai por menos, até sendo titular">quer sair</span>';
  if (j.abatido) return ' <span class="moral abatido" title="Abatido no clube: o dono aceita negociar por menos">abatido</span>';
  return "";
}

/* ------------------------------------------------------------------ olheiro */

/* O relatorio do olheiro (fm.telas.olheiro): os pontos fracos do time titular e quem
 * resolve, dentro do caixa e da folha, mais as promessas. So recomenda: a compra e o
 * fluxo de proposta de sempre -- nada entra no elenco sem o usuario. */
async function abaOlheiro() {
  TRF.lista = await api.get("/api/olheiro");
  pintarCaixa(TRF.lista.caixa);
  if (!TRF.lista.jogadores.some((j) => j.id === TRF.selecionado)) TRF.selecionado = TRF.lista.jogadores[0]?.id ?? null;
  const o = TRF.lista.orcamento;
  $("#trf-corpo").style.gridTemplateColumns = "17rem minmax(0,1fr) 22rem";
  $("#trf-corpo").innerHTML = `
    <div style="padding:.9rem;border-right:1px solid var(--linha);overflow:auto">
      <h3 class="titulo-secao">Relatório do olheiro</h3>
      ${TRF.lista.secoes.filter((x) => !["Promessas", "Oportunidades"].includes(x.titulo)).map((x) =>
        `<div class="necessidade">${escapar(x.titulo)}<span class="dica">${x.jogadores.length} indicados</span></div>`).join("")}
      <div class="kpis" style="margin-top:1rem;grid-template-columns:1fr">
        <div class="kpi-c"><span>Para transferência</span><b>${eurosConvertido(o.transferencia)}</b></div>
        <div class="kpi-c"><span>Folga na folha (mês)</span><b>${dinheiro(o.salario)}</b></div>
      </div>
    </div>
    <div style="overflow:auto;min-height:0">
      ${TRF.lista.secoes.map((x) => `
        <div class="secao-olheiro"><h3>${x.titulo === "Promessas" ? "Promessas (até 21 anos)"
          : x.titulo === "Oportunidades" ? "Oportunidades: moral baixa em outros clubes" : `Reforço para ${escapar(x.titulo)}`}</h3>
        <table class="grade compacta grade-olheiro"><tbody>${x.jogadores.map((j) => `
          <tr class="clicavel ${j.id === TRF.selecionado ? "sel" : ""}" data-id="${j.id}">
            <td><b>${escapar(j.nome)}</b>${j.observado ? ' <span class="ouro">★</span>' : ""}${seloQuerSair(j)}
              <div class="dica">${escapar(j.motivo)}</div></td>
            <td>${pos(j.posicao)}</td><td class="n">${j.idade}a</td>
            <td>${j.livre ? '<span class="chip ativo">sem contrato</span>'
              : `<div class="nome-celula">${escudo(j.clube, "1.3rem")}<span>${escapar(j.clube.nome)}</span></div>`}</td>
            <td class="n">${ovr(j.overall)}</td>
            <td class="n">${j.preco ? euros(j.preco) : "livre"}<div class="dica">${dinheiro(j.salario_pedido)}/mês</div></td>
          </tr>`).join("") || `<tr><td class="vazio">${x.titulo === "Oportunidades"
            ? "Ninguém com a moral baixa no nível do seu time agora: elas aparecem quando um clube entra em crise."
            : "Ninguém que caiba no orçamento e topa vir."}</td></tr>`}</tbody></table></div>`).join("")}
    </div>
    <div id="trf-detalhe" style="border-left:1px solid var(--linha);overflow:auto"></div>`;
  $$(".grade-olheiro tr[data-id]").forEach((tr) => tr.addEventListener("click", () => {
    TRF.selecionado = +tr.dataset.id;
    $$(".grade-olheiro tr").forEach((x) => x.classList.toggle("sel", x === tr));
    detalheTrf();
  }));
  detalheTrf();
}

const ATRIBUTOS_RESUMO = [["finalizacao", "Finalização"], ["passe", "Passe"], ["drible", "Drible"],
                          ["marcacao", "Marcação"], ["velocidade", "Velocidade"], ["resistencia", "Resistência"]];
const ATRIBUTOS_GOLEIRO = [["reflexos", "Reflexos"], ["posicionamento", "Posicionamento"],
                           ["jogo aereo", "Jogo aéreo"], ["passe", "Passe"], ["resistencia", "Resistência"]];

async function detalheTrf() {
  const alvo = $("#trf-detalhe");
  const j = TRF.lista.jogadores.find((x) => x.id === TRF.selecionado);
  if (!j) { alvo.innerHTML = '<div class="vazio">Selecione um jogador.</div>'; return; }
  const p = await api.get(`/api/jogador?id=${j.id}`);
  const attrs = (j.posicao === "GK" ? ATRIBUTOS_GOLEIRO : ATRIBUTOS_RESUMO).map(([k, r]) => {
    const v = p.atributos[k];
    return `<div class="attr"><span>${r}</span><span class="t"><i style="width:${v}%;background:${corDe(v, 75, 60)}"></i></span><b>${v}</b></div>`;
  }).join("");
  alvo.innerHTML = `<div style="padding:1rem">
    <h2 style="font-size:1.25rem">${escapar(j.nome)}</h2>
    <div class="dica" style="margin:.2rem 0 .8rem">${POSICOES_LONGAS[j.posicao]} — ${j.idade} anos · ${escapar(j.nacionalidade || "")}</div>
    <div class="linha-flex">${j.livre ? '<span class="chip ativo">sem contrato</span>'
      : `${escudo(j.clube, "2.4rem")}<div><b>${escapar(j.clube.nome)}</b><div class="dica">${escapar(j.liga)}</div></div>`}
      <span class="espaco"></span>${ovr(j.overall)}</div>
    <div class="kpis" style="margin-top:.9rem">
      <div class="kpi-c destaque"><span>Valor estimado</span><b>${euros(j.valor)}</b></div>
      <div class="kpi-c"><span>Salário/mês</span><b>${dinheiro(j.salario)}</b></div>
      <div class="kpi-c"><span>Contrato</span><b>${j.livre ? "—" : `até ${j.contrato}`}</b></div>
      <div class="kpi-c"><span>Potencial</span><b>${j.potencial}</b></div>
    </div>
    <div class="secao"><h3>Atributos</h3><div class="atributos" style="grid-template-columns:1fr">${attrs}</div></div>
    <div class="form-col" style="gap:.5rem;margin-top:1rem">
      ${j.livre ? '<button class="btn primario bloco" id="acao-principal">Negociar contrato</button>'
        : `<button class="btn primario bloco" id="acao-principal">Fazer proposta</button>
           <button class="btn bloco" id="pedir-emprestimo">Pedir emprestado</button>`}
      <button class="btn ${j.observado ? "" : "azul"} bloco" id="lista">${j.observado ? "Tirar da lista" : "Adicionar à lista"}</button>
      <button class="btn fantasma bloco" onclick="abrirPerfil(${j.id})">Ver perfil completo</button>
    </div></div>`;
  $("#acao-principal").addEventListener("click", () => j.livre ? negociarContrato(j, 0) : fazerProposta(j));
  $("#pedir-emprestimo")?.addEventListener("click", () => pedirEmprestimo(j));
  $("#lista").addEventListener("click", async () => {
    await api.post("/api/observar", {id: j.id});
    await recarregarEstado();
    TELAS.transferencias();      // a aba em que ele esta: mercado ou olheiro
  });
}

/* ------------------------------------------------------------------ o fluxo de compra */

async function fazerProposta(j, sugestao) {
  const valorInicial = sugestao || j.valor;
  const r = await abrirJanela({titulo: "Negociação", estreita: true, corpo: `
    <div class="form-col">
      <div class="linha-flex">${escudo(j.clube, "2.4rem")}<div><b>${escapar(j.nome)}</b>
        <div class="dica">${escapar(j.clube.nome)}</div></div></div>
      <div class="kpi-c"><span>Valor estimado</span><b>${eurosConvertido(j.valor)}</b></div>
      <label class="campo"><span>Sua proposta (€)</span>
        <input type="text" id="valor-oferta" inputmode="numeric" value="${Math.round(valorInicial).toLocaleString("pt-BR")}"></label>
    </div>`,
    botoes: [{rotulo: "Cancelar", valor: null},
             {rotulo: "Enviar proposta", primario: true, valor: "enviar"}]});
  if (r !== "enviar") return;
  const valor = lerNumero($("#valor-oferta").value);
  const resp = await api.post("/api/oferta", {jogador: j.id, valor});
  if (resp.resultado === "aceita") {
    await abrirJanela({titulo: "Proposta aceita", estreita: true,
      corpo: `<p>${escapar(resp.mensagem)}</p><p class="dica">Agora é negociar o contrato com o jogador.</p>`,
      botoes: [{rotulo: "Negociar contrato", primario: true}]});
    return negociarContrato(j, resp.valor);
  }
  if (resp.resultado === "contraproposta") {
    const c = await abrirJanela({titulo: "Contraproposta", estreita: true,
      corpo: `<p>${escapar(resp.mensagem)}</p>`,
      botoes: [{rotulo: "Desistir", valor: null}, {rotulo: "Fazer nova proposta", valor: "nova"},
               {rotulo: "Aceitar", primario: true, valor: "aceitar"}]});
    if (c === "aceitar") return negociarContrato(j, resp.valor);
    if (c === "nova") return fazerProposta(j, resp.valor);
    return;
  }
  if (resp.resultado === "recusada") {
    const c = await abrirJanela({titulo: "Proposta recusada", estreita: true,
      corpo: `<p>${escapar(resp.mensagem)}</p>${resp.dica ? `<p class="dica">Valor esperado aproximado: <b>${eurosConvertido(resp.dica)}</b></p>` : ""}`,
      botoes: [{rotulo: "Cancelar negociação", valor: null},
               ...(resp.dica ? [{rotulo: "Fazer nova proposta", primario: true, valor: "nova"}] : [])]});
    if (c === "nova") return fazerProposta(j, resp.dica);
    return;
  }
  avisar(resp.mensagem || "não foi possível negociar");
}

async function negociarContrato(j, preco, sugestao) {
  const info = await api.get(`/api/contrato?jogador=${j.id}`);
  if (info.ambicao) {
    return abrirJanela({titulo: "Negociação encerrada", estreita: true, corpo: `<p>${escapar(info.ambicao)}</p>`});
  }
  let anos = 3;
  const salarioInicial = sugestao || info.pretendido;
  const promessa = abrirJanela({titulo: `Contrato — ${escapar(j.nome)}`, estreita: true, corpo: `
    <div class="form-col">
      <div class="kpis">
        <div class="kpi-c"><span>Salário atual</span><b>${dinheiro(info.salario_atual)}/mês</b></div>
        <div class="kpi-c destaque"><span>Pretende</span><b>~ ${dinheiro(info.pretendido)}/mês</b></div>
        ${preco ? `<div class="kpi-c"><span>Transferência</span><b>${eurosConvertido(preco)}</b></div>` : ""}
      </div>
      <label class="campo"><span>Salário mensal (${MOEDA.simbolo})</span>
        <input type="text" id="salario-oferta" inputmode="numeric" value="${salarioNoCampo(salarioInicial)}"></label>
      <div class="campo"><span>Duração</span><div class="segmentado" id="anos">${[1, 2, 3, 4, 5].map((a) =>
        `<button data-anos="${a}" class="${a === anos ? "ativo" : ""}">${a} ${a === 1 ? "ano" : "anos"}</button>`).join("")}</div></div>
      <p class="nota-honesta">Folha do clube: ${dinheiro(info.caixa.folha)} de ${dinheiro(info.caixa.limite_da_folha)} por mês.
        Caixa: ${dinheiro(info.caixa.caixa)}.</p>
    </div>`,
    botoes: [{rotulo: "Desistir", valor: null}, {rotulo: "Propor contrato", primario: true, valor: "ok"}]});
  $$("[data-anos]").forEach((b) => b.addEventListener("click", () => {
    anos = +b.dataset.anos;
    $$("[data-anos]").forEach((x) => x.classList.toggle("ativo", x === b));
  }));
  if (await promessa !== "ok") return;
  const salario = lerSalario($("#salario-oferta").value);
  const r = await api.post("/api/contrato", {jogador: j.id, preco, salario, anos});
  if (r.resultado === "concluida") {
    aplicarEstado(r.estado);
    await abrirJanela({titulo: "Contratação concluída", estreita: true, corpo: `<p>${escapar(r.mensagem)}</p>`,
      botoes: [{rotulo: "Continuar", primario: true}]});
    return TELAS.transferencias();
  }
  const c = await abrirJanela({titulo: "Proposta recusada", estreita: true,
    corpo: `<p>${escapar(r.mensagem)}</p>${r.dica ? `<p class="dica">O jogador deseja aproximadamente <b>${dinheiro(r.dica)}/mês</b>.</p>` : ""}`,
    botoes: [{rotulo: "Encerrar", valor: null},
             ...(r.definitiva || r.resultado === "erro" ? [] : [{rotulo: "Nova proposta", primario: true, valor: "nova"}])]});
  if (c === "nova") return negociarContrato(j, preco, r.dica);
}

/* ------------------------------------------------------------------ renovacao */

const NIVEL_INTERESSE = {alto: ["🟢", "Alto"], medio: ["🟡", "Médio"], baixo: ["🔴", "Baixo"]};

async function renovarContrato(pid, sugestao) {
  const info = await api.get(`/api/renovacao?jogador=${pid}`);
  if (info.erro) return avisar(info.erro);
  const [bola, rotulo] = NIVEL_INTERESSE[info.nivel];
  if (info.nivel === "baixo") {
    return abrirJanela({titulo: "Renovação de contrato", estreita: true, corpo: `
      <p><b>${escapar(info.nome)}</b> — contrato até ${info.contrato}</p>
      <p>Interesse em renovar: ${bola} <b>${rotulo}</b></p><p>${escapar(info.motivo)}</p>
      <p class="dica">O jogador não deseja renovar neste momento. Aumentar o salário não muda isso.</p>`});
  }
  let anos = 2;
  const promessa = abrirJanela({titulo: "Renovação de contrato", estreita: true, corpo: `
    <div class="form-col">
      <b style="font-size:1.1rem">${escapar(info.nome)}</b>
      <div class="kpis">
        <div class="kpi-c"><span>Contrato atual</span><b>até ${info.contrato}</b></div>
        <div class="kpi-c"><span>Salário atual</span><b>${dinheiro(info.salario_atual)}/mês</b></div>
        <div class="kpi-c destaque"><span>Deseja</span><b>${dinheiro(info.pretendido)}/mês</b></div>
      </div>
      <p>Interesse em renovar: ${bola} <b>${rotulo}</b> — ${escapar(info.motivo)}</p>
      <label class="campo"><span>Novo salário mensal (${MOEDA.simbolo})</span>
        <input type="text" id="salario-renova" inputmode="numeric" value="${salarioNoCampo(sugestao || info.pretendido)}"></label>
      <div class="campo"><span>Novo período</span><div class="segmentado">${[1, 2, 3, 4].map((a) =>
        `<button data-anos="${a}" class="${a === anos ? "ativo" : ""}">+${a} ${a === 1 ? "ano" : "anos"}</button>`).join("")}</div></div>
    </div>`,
    botoes: [{rotulo: "Cancelar", valor: null}, {rotulo: "Propor renovação", primario: true, valor: "ok"}]});
  $$("[data-anos]").forEach((b) => b.addEventListener("click", () => {
    anos = +b.dataset.anos;
    $$("[data-anos]").forEach((x) => x.classList.toggle("ativo", x === b));
  }));
  if (await promessa !== "ok") return;
  const r = await api.post("/api/renovacao", {jogador: pid, salario: lerSalario($("#salario-renova").value), anos});
  if (r.resultado === "concluida") {
    aplicarEstado(r.estado);
    avisar(r.mensagem);
    return irPara(telaAtual);
  }
  const c = await abrirJanela({titulo: "Renovação recusada", estreita: true, corpo: `
    <p>O jogador não aceitou os termos oferecidos.</p><p>Razão: ${escapar(r.mensagem)}</p>`,
    botoes: [{rotulo: "Encerrar negociação", valor: null},
             ...(r.definitiva ? [] : [{rotulo: "Nova proposta", primario: true, valor: "nova"}])]});
  if (c === "nova") return renovarContrato(pid, r.dica);
}

/* ------------------------------------------------------------------ emprestimo
 * Um formato so: ate o fim da temporada, quem recebe paga o salario inteiro. */

async function pedirEmprestimo(j) {
  const info = await api.get(`/api/emprestimo?jogador=${j.id}`);
  if (info.erro) return avisar(info.erro);
  if (info.resultado !== "aceita") {
    return abrirJanela({titulo: "Empréstimo recusado", estreita: true, corpo: `<p>${escapar(info.mensagem)}</p>`});
  }
  const r = await abrirJanela({titulo: `Empréstimo — ${escapar(j.nome)}`, estreita: true, corpo: `
    <div class="form-col">
      <p>${escapar(info.mensagem)}</p>
      <div class="kpis">
        <div class="kpi-c destaque"><span>Taxa</span><b>${info.taxa ? eurosConvertido(info.taxa) : "sem taxa"}</b></div>
        <div class="kpi-c"><span>Salário (você paga)</span><b>${dinheiro(info.salario)}/mês</b></div>
        <div class="kpi-c"><span>Até</span><b>fim de ${info.ate}</b></div>
      </div>
      <p class="nota-honesta">Folha do clube: ${dinheiro(info.caixa.folha)} de ${dinheiro(info.caixa.limite_da_folha)} por mês.
        Caixa: ${dinheiro(info.caixa.caixa)}. Ele volta ao clube dono na virada do ano.</p>
    </div>`,
    botoes: [{rotulo: "Desistir", valor: null}, {rotulo: "Fechar empréstimo", primario: true, valor: "ok"}]});
  if (r !== "ok") return;
  const feito = await api.post("/api/emprestimo", {jogador: j.id});
  if (feito.resultado !== "concluida") return avisar(feito.mensagem);
  aplicarEstado(feito.estado);
  avisar(feito.mensagem);
  return TELAS.transferencias();
}

async function emprestarJogador(pid) {
  const info = await api.get(`/api/emprestimo?jogador=${pid}`);
  if (info.erro) return avisar(info.erro);
  if (!info.interessados.length) {
    return abrirJanela({titulo: "Emprestar", estreita: true, corpo: `
      <p>Nenhum clube tem interesse em <b>${escapar(info.nome)}</b> agora.</p>
      <p class="dica">Interessam os clubes onde ele seria titular e que têm vaga no elenco.</p>`});
  }
  let escolhido = info.interessados[0].id;
  const r = await abrirJanela({titulo: `Emprestar ${escapar(info.nome)}`, estreita: true, corpo: `
    <p class="dica">Clubes onde ele seria titular. O clube que recebe paga o salário até o fim da temporada.</p>
    <div class="form-col">${info.interessados.map((k, i) => `
      <label class="linha-flex opcao-emp"><input type="radio" name="emp-clube" value="${k.id}" ${i === 0 ? "checked" : ""}>
        ${escudo(k, "1.6rem")} <b>${escapar(k.nome)}</b></label>`).join("")}</div>`,
    botoes: [{rotulo: "Cancelar", valor: null}, {rotulo: "Emprestar", primario: true, valor: "ok", acao: () => {
      const x = document.querySelector("input[name=emp-clube]:checked");
      if (x) escolhido = +x.value;
    }}]});
  if (r !== "ok") return;
  const feito = await api.post("/api/emprestimo", {jogador: pid, clube: escolhido});
  if (feito.resultado !== "concluida") return avisar(feito.mensagem);
  aplicarEstado(feito.estado);
  avisar(feito.mensagem);
  return irPara(telaAtual);
}

/* ------------------------------------------------------------------ propostas recebidas */

/** Chamada depois de cada atualizacao do estado: proposta nova abre a janela sozinha, sem
 *  o usuario precisar entrar na aba de transferencias. */
async function verificarPropostas(e) {
  if (modoAtual !== "jogo" || !e || !e.propostas_pendentes) return;
  for (const prop of e.propostas_pendentes) {
    if (TRF.propostasVistas.has(prop.id)) continue;
    TRF.propostasVistas.add(prop.id);
    await janelaDeProposta(prop);
  }
}

async function janelaDeProposta(prop) {
  const j = prop.jogador;
  const c = await abrirJanela({titulo: "Proposta recebida", estreita: true, corpo: `
    <div class="form-col">
      <div class="linha-flex">${escudo(prop.clube, "3rem")}<div><b style="font-size:1.1rem">${escapar(prop.clube.nome)}</b>
        <div class="dica">tem interesse em:</div></div></div>
      <div><b>${escapar(j.nome)}</b> <span class="dica">${POSICOES_LONGAS[j.posicao]} | ${j.idade} anos | Força ${j.overall}</span></div>
      <div class="kpis">
        <div class="kpi-c"><span>Valor do jogador</span><b>${euros(j.valor)}</b></div>
        <div class="kpi-c destaque"><span>Proposta</span><b>${eurosConvertido(prop.valor)}</b></div>
      </div>
    </div>`,
    botoes: [{rotulo: "Recusar", valor: "recusar"}, {rotulo: "Negociar", valor: "negociar"},
             {rotulo: "Aceitar", primario: true, valor: "aceitar"}]});
  if (c === "aceitar" || c === "recusar") return enviarRespostaProposta(prop, c);
  if (c === "negociar") return contraproposta(prop);
}

async function contraproposta(prop) {
  const c = await abrirJanela({titulo: "Contraproposta", estreita: true, corpo: `
    <div class="form-col">
      <div class="kpi-c"><span>Proposta atual</span><b>${eurosConvertido(prop.valor)}</b></div>
      <label class="campo"><span>Sua exigência (€)</span>
        <input type="text" id="exigencia" inputmode="numeric" value="${Math.round(prop.valor * 1.25).toLocaleString("pt-BR")}"></label>
    </div>`,
    botoes: [{rotulo: "Voltar", valor: null}, {rotulo: "Enviar contraproposta", primario: true, valor: "ok"}]});
  if (c !== "ok") return janelaDeProposta(prop);
  return enviarRespostaProposta(prop, "contraproposta", lerNumero($("#exigencia").value));
}

async function enviarRespostaProposta(prop, acao, valor) {
  const r = await api.post("/api/propostas", {proposta: prop.id, acao, valor});
  if (r.estado) aplicarEstado(r.estado);
  if (r.erro) return avisar(r.erro);
  if (r.resultado === "nova_proposta" && r.proposta) {
    await abrirJanela({titulo: "Nova proposta", estreita: true, corpo: `<p>${escapar(r.mensagem)}</p>`,
                       botoes: [{rotulo: "Ver proposta", primario: true}]});
    return janelaDeProposta(r.proposta);
  }
  await abrirJanela({titulo: acao === "recusar" ? "Proposta recusada" : "Negociação",
                     estreita: true, corpo: `<p>${escapar(r.mensagem)}</p>`});
  if (telaAtual === "transferencias" || telaAtual === "elenco") irPara(telaAtual);
}

const STATUS_PROPOSTA = {pendente: ["Pendente", "ouro"], aceita: ["Aceita", "bom"], recusada: ["Recusada", "ruim"],
                         expirada: ["Expirada", "fraco"]};

async function abaPropostas() {
  const {propostas} = await api.get("/api/propostas");
  $("#trf-corpo").style.gridTemplateColumns = "1fr";
  $("#trf-corpo").innerHTML = `<div style="overflow:auto"><table class="grade">
    <thead><tr><th>Jogador</th><th>Clube interessado</th><th class="n">Valor</th><th>Status</th><th class="n">Ano</th><th></th></tr></thead>
    <tbody>${propostas.map((p) => {
      const [rot, cls] = STATUS_PROPOSTA[p.status] || [p.status, ""];
      return `<tr><td><b>${escapar(p.jogador ? p.jogador.nome : "?")}</b></td>
        <td><div class="nome-celula">${escudo(p.clube, "1.3rem")}<span>${escapar(p.clube.nome)}</span></div></td>
        <td class="n">${euros(p.valor)}</td><td class="${cls}">${rot}</td><td class="n">${p.temporada}</td>
        <td>${p.status === "pendente" ? `<button class="btn pequeno primario" data-prop="${escapar(p.id)}">Responder</button>` : ""}</td></tr>`;
    }).join("") || '<tr><td colspan="6" class="vazio">Nenhuma proposta recebida ainda.</td></tr>'}</tbody></table></div>`;
  $$("[data-prop]").forEach((b) => b.addEventListener("click", () =>
    janelaDeProposta(propostas.find((p) => p.id === b.dataset.prop))));
}

/* ------------------------------------------------------------------ negociacoes e historico */

const RES_NEG = {aceita: ["Aceita", "bom"], contraproposta: ["Contraproposta", "ouro"], recusada: ["Recusada", "ruim"]};

async function abaNegociacoes() {
  const {negociacoes} = await api.get("/api/negocios");
  $("#trf-corpo").style.gridTemplateColumns = "1fr";
  $("#trf-corpo").innerHTML = `<div style="overflow:auto"><table class="grade">
    <thead><tr><th>Data</th><th>Jogador</th><th>Clube</th><th class="n">Sua oferta</th><th>Resposta</th><th class="n">Pedem</th></tr></thead>
    <tbody>${negociacoes.map((n) => {
      const [rot, cls] = RES_NEG[n.resultado] || [n.resultado, ""];
      return `<tr><td class="num">${n.data}</td><td>${pos(n.posicao)} <b>${escapar(n.nome)}</b></td>
        <td>${n.clube ? escapar(n.clube.nome) : "sem clube"}</td><td class="n">${euros(n.oferta)}</td>
        <td class="${cls}">${rot}</td><td class="n">${n.valor ? euros(n.valor) : "—"}</td></tr>`;
    }).join("") || '<tr><td colspan="6" class="vazio">Nenhuma oferta feita nesta sessão.</td></tr>'}</tbody></table></div>`;
}

async function abaHistorico() {
  const {movimentos} = await api.get("/api/negocios");
  $("#trf-corpo").style.gridTemplateColumns = "1fr";
  const SENTIDO = {entrada: ["bom", "▲ chegou", "de "], saida: ["ruim", "▼ saiu", "para "],
                   emprestimo_entrada: ["bom", "▲ emprestado", "do "], emprestimo_saida: ["ruim", "▼ emprestou", "ao "]};
  const fora = ESTADO.emprestados || [];
  $("#trf-corpo").innerHTML = `<div style="overflow:auto">
    ${fora.length ? `<h3 class="sub-trf">Emprestados até o fim da temporada</h3><table class="grade compacta"><tbody>${fora.map((e) => `
      <tr><td>${pos(e.posicao)} <b>${escapar(e.nome)}</b></td><td class="n">${e.overall}</td>
        <td><div class="nome-celula">${escudo(e.clube, "1.2rem")} ${escapar(e.clube.nome)}</div></td>
        <td class="dica">volta na virada do ano</td></tr>`).join("")}</tbody></table>` : ""}
    <table class="grade">
    <thead><tr><th class="n">Ano</th><th></th><th>Jogador</th><th class="n">Força</th><th>Clube</th><th class="n">Valor</th></tr></thead>
    <tbody>${movimentos.map((m) => {
      const [cls, rot, prep] = SENTIDO[m.sentido] || SENTIDO.entrada;
      return `<tr><td class="n">${m.temporada}</td><td class="${cls}">${rot}</td>
      <td>${pos(m.posicao)} <b>${escapar(m.nome)}</b></td><td class="n">${m.overall}</td>
      <td>${prep}${escapar(m.clube)}</td><td class="n">${m.valor ? euros(m.valor) : "—"}</td></tr>`;
    }).join("") || '<tr><td colspan="6" class="vazio">Nenhuma transferência ainda.</td></tr>'}</tbody></table></div>`;
}
