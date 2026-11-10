"use strict";
/* Interface do Extrator DATASUS. Regras de negócio ficam no Python (window.pywebview.api):
   opções dos formulários, plano/estimativa, fila. Aqui ficam só o estado da tela e a montagem do pedido. */

// ---------------------------------------------------------------- ícones (traço fino)
const ICONES = {
  painel: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  novo: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M12 8v8M8 12h8"/>',
  coletas: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
  config: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  play: '<path d="M7 4v16l13-8z"/>', parar: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  subir: '<path d="M12 19V5M5 12l7-7 7 7"/>', descer: '<path d="M12 5v14M19 12l-7 7-7-7"/>',
  lixo: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>', pasta: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  planilha: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 3v18"/>',
  relatorio: '<path d="M6 3h9l5 5v13H6z"/><path d="M14 3v6h6M9 13h7M9 17h7"/>',
  alerta: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18h.01"/>', busca: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  check: '<path d="m5 12 5 5L20 7"/>', setaD: '<path d="M5 12h14M13 6l6 6-6 6"/>', setaE: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  atualizar: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>', vazio: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 15h6"/>',
};
const icone = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONES[n] || ""}</svg>`;
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => (n ?? 0).toLocaleString("pt-BR");
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const REGIOES = { Norte: "ac am ap pa ro rr to", Nordeste: "al ba ce ma pb pe pi rn se", "Centro-Oeste": "df go ms mt", Sudeste: "es mg rj sp", Sul: "pr rs sc" };
const PASSOS = [["Base de dados", "base"], ["O que contar", "tabela"], ["Período", "periodo"], ["Filtros", "filtros"], ["Saída", "saida"], ["Revisar", "revisar"]];
const SITUACAO = { "em andamento": "andamento", "na fila": "fila", "concluído": "ok", erro: "erro", interrompido: "erro" };

function chavePeriodo(r) {
  const m = /^([A-Za-zç]{3})\/(\d{4})/.exec(r);
  if (m) return +m[2] * 12 + MESES.indexOf(m[1][0].toUpperCase() + m[1].slice(1).toLowerCase()) + 1;
  const a = /^(\d{4})/.exec(r);
  return a ? +a[1] * 12 : 0;
}
function nomeGrupo(rot) {
  if (rot.length === 1) return rot[0];
  if (rot.length === 2) return `${rot[0]} + ${rot[1]}`;
  return `${rot[0]} até ${rot[rot.length - 1]} (${rot.length} opções)`;
}
function tempo(seg) {
  if (seg < 3600) return `${Math.max(1, Math.round(seg / 60))} min`;
  if (seg < 48 * 3600) return `${(seg / 3600).toFixed(1).replace(".", ",")} h`;
  return `${(seg / 86400).toFixed(1).replace(".", ",")} dias`;
}
const dataCurta = (iso) => (iso ? iso.replace("T", " ").slice(0, 16).split(" ").map((p, i) => (i ? p : p.split("-").reverse().join("/"))).join(" ") : "");

// ---------------------------------------------------------------- estado
const S = {
  view: "painel", passo: 0, prefs: {}, bases: [], ufs: {}, form: null, carregando: true,
  p: {
    nome: "Meu pedido", base: "sih", abrangencia: "nacional", estados: [], linha: "", conteudos: [], colunas: [], ordenar: false,
    periodos: [], filtros: {}, ordemCampos: [], titulos: {}, combinar: "independentes",
    formato: "por_periodo", evidencias: "pdf_png", regioes: true, contBlocos: [], confTotal: true, confPdf: true, pasta: "",
  },
  campo: null, marc: { fil: new Set(), per: new Set() }, busca: { fil: "", per: "" }, de: "", ate: "",
  est: null, coletas: [], filaRodando: false, sel: null, abaColetas: "todas", log: [], erroPasso: "", opcoesInfo: null,
};
let api = null;

// ---------------------------------------------------------------- tema
function temaResolvido() { return S.prefs.tema === "auto" ? S.prefs.tema_sistema : S.prefs.tema; }
function aplicarTema() {
  const t = temaResolvido();
  document.documentElement.dataset.theme = t === "escuro" ? "dark" : "light";
  document.querySelectorAll("#temas button").forEach((b) => b.classList.toggle("ativo", b.dataset.tema === S.prefs.tema));
  api && api.barra_escura(t === "escuro");
}
async function trocarTema(t) {
  S.prefs.tema = t;
  await api.salvar_preferencia("tema", t);
  aplicarTema();
}

// ---------------------------------------------------------------- avisos e diálogo
function toast(texto, tipo = "") {
  const el = document.createElement("div");
  el.className = `toast ${tipo}`;
  el.textContent = texto;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4200);
}
function confirmar(titulo, texto, ok = "Confirmar", perigo = false) {
  return new Promise((res) => {
    const f = document.createElement("div");
    f.className = "fundo-dialogo";
    f.innerHTML = `<div class="dialogo" role="dialog" aria-modal="true"><h3>${esc(titulo)}</h3><p>${esc(texto)}</p>
      <div class="acoes"><button class="btn fantasma" data-r="0">Cancelar</button><button class="btn ${perigo ? "perigo" : "primario"}" data-r="1">${esc(ok)}</button></div></div>`;
    f.addEventListener("click", (e) => { const r = e.target.closest("[data-r]"); if (r || e.target === f) { f.remove(); res(r?.dataset.r === "1"); } });
    document.body.append(f);
    f.querySelector('[data-r="1"]').focus();
  });
}

// ---------------------------------------------------------------- formulário (opções do site)
async function carregarFormulario() {
  const p = S.p;
  const ufs = p.abrangencia === "estadual" ? p.estados : [];
  if (p.abrangencia === "estadual" && !ufs.length && S.form) return;
  const f = await api.formulario(p.base, p.abrangencia, ufs.length ? ufs : ["sp"]);
  S.form = f;
  if (!f.linhas.includes(p.linha)) {
    const pref = p.abrangencia === "nacional" ? "Unidade da Federação" : "Município";
    p.linha = f.linhas.includes(pref) ? pref : f.linhas[0];
  }
  p.conteudos = p.conteudos.filter((c) => f.conteudos.includes(c));
  if (!p.conteudos.length) p.conteudos = [f.conteudos[0]];
  p.colunas = p.colunas.filter((c) => f.colunas.includes(c));
  p.contBlocos = p.contBlocos.filter((c) => p.conteudos.includes(c));
  const validos = new Set(f.periodos);
  p.periodos = p.periodos.filter((it) => it.valores.every((v) => validos.has(v)));
  if (!p.periodos.length) p.periodos = f.periodos.slice(-(f.mensal ? 12 : 5)).map((v) => ({ tipo: "separada", nome: v, valores: [v] }));
  S.de = p.periodos[0]?.valores[0] || f.periodos[0];
  S.ate = f.periodos[f.periodos.length - 1];
  const novos = {};
  for (const fil of f.filtros) {
    const ok = new Set(fil.opcoes.map((o) => o[0]));
    novos[fil.nome] = (p.filtros[fil.nome] || []).filter((it) => it.valores.every((v) => ok.has(v)));
  }
  p.filtros = novos;
  p.ordemCampos = p.ordemCampos.filter((c) => novos[c]?.length);
  if (!S.campo || !novos[S.campo]) S.campo = f.filtros[0]?.nome;
  S.marc.fil.clear(); S.marc.per.clear();
}
const ehLinha = (campo) => campo.toLowerCase() === S.p.linha.toLowerCase();
function camposEmBloco() {
  const ordem = [...S.p.ordemCampos, ...Object.keys(S.p.filtros).filter((c) => !S.p.ordemCampos.includes(c))];
  return ordem.filter((c) => (S.p.filtros[c] || []).length > 1 && !ehLinha(c));
}
function montarPedido() {
  const p = S.p;
  const blocos = camposEmBloco();
  const filtros = Object.fromEntries(Object.entries(p.filtros).filter(([, v]) => v.length));
  return {
    nome: p.nome.trim(), base: p.base, abrangencia: p.abrangencia, estados: p.abrangencia === "estadual" ? p.estados : [],
    linha: p.linha, colunas: p.colunas, conteudos: p.conteudos, exibir_linhas_zeradas: true,
    sem_resultado: { valor: "SR", linha_zerada: true, nenhum_registro: true, celula_traco: true, celula_nao_disponivel: true },
    ordenar_pelos_valores: p.ordenar, periodos: p.periodos, filtros, ordem_dos_blocos: blocos,
    titulos_dos_blocos: Object.fromEntries(blocos.map((c) => [c, p.titulos[c] || c.toUpperCase()])), combinar_filtros: p.combinar,
    layout: { conteudos_nos_blocos: p.contBlocos.length ? p.contBlocos : p.conteudos.slice(0, 1), brasil_e_regioes: p.regioes },
    saida: { formato: p.formato, evidencias: p.evidencias, conferir_total: p.confTotal, conferir_pdf: p.confPdf, pasta: p.pasta },
  };
}
let tEst = null;
function agendarEstimativa() {
  clearTimeout(tEst);
  tEst = setTimeout(async () => {
    S.est = await api.estimar(montarPedido());
    renderTrilho();
    if (S.view === "novo" && (S.passo === 1 || S.passo === 5)) renderPrevia();
  }, 140);
}

// ---------------------------------------------------------------- navegação
function ir(view) {
  S.view = view;
  document.querySelectorAll(".nav").forEach((b) => b.classList.toggle("ativo", b.dataset.ir === view));
  render();
  $("#rolagem").scrollTop = 0;
}
function validar(passo) {
  const p = S.p;
  if (passo === 0 && p.abrangencia === "estadual" && !p.estados.length) return "Escolha pelo menos um estado.";
  if (passo === 1 && !p.conteudos.length) return "Marque pelo menos um conteúdo para contar.";
  if (passo === 1 && p.colunas.includes(p.linha)) return `"${p.linha}" já está nas linhas: tire das colunas.`;
  if (passo === 2 && !p.periodos.length) return "Adicione pelo menos um período.";
  if (passo === 4 && !p.nome.trim()) return "Dê um nome ao pedido.";
  return "";
}
function irPasso(i) {
  if (i < 0 || i >= PASSOS.length) return;
  for (let k = S.passo; k < i; k++) {
    const e = validar(k);
    if (e) { S.passo = k; S.erroPasso = e; render(); return; }
  }
  S.passo = i; S.erroPasso = "";
  render();
  $("#rolagem").scrollTop = 0;
}

// ---------------------------------------------------------------- render geral
function render() {
  const titulos = { painel: "Painel", novo: "Novo pedido", coletas: "Minhas coletas", config: "Configurações" };
  $("#titulo").textContent = titulos[S.view];
  const R = { painel: renderPainel, novo: renderNovo, coletas: renderColetas, config: renderConfig }[S.view];
  $("#rolagem").innerHTML = `<div class="pagina">${R()}</div>`;
  renderTopo();
  renderRodape();
  if (S.view === "novo") { renderTrilho(); renderPrevia(); if (S.passo === 3) renderListaOpcoes("fil"); if (S.passo === 2) renderListaOpcoes("per"); }
  if (S.view === "coletas") carregarLog();
  document.querySelectorAll("svg[data-icone]").forEach((s) => { s.outerHTML = icone(s.dataset.icone); });
}
function renderTopo() {
  const emAnd = S.coletas.find((c) => c.situacao === "em andamento");
  const nFila = S.coletas.filter((c) => c.situacao === "na fila").length;
  const ctx = {
    painel: `${S.coletas.length} coletas · ${nFila} na fila`,
    novo: `passo ${S.passo + 1} de 6 · ${esc(S.bases.find((b) => b.chave === S.p.base)?.nome || "")}`,
    coletas: emAnd ? `coletando “${esc(emAnd.nome)}” · ${emAnd.feitas || 0}/${emAnd.total || "?"}` : "nenhuma coleta em andamento",
    config: `versão ${esc(S.prefs.versao || "")}`,
  }[S.view];
  $("#contexto").innerHTML = ctx;
  const paradaComFila = nFila && !S.filaRodando;
  $("#acoes-topo").innerHTML = (paradaComFila ? `<button class="btn" data-acao="iniciar-fila">${icone("play")}Iniciar fila</button>` : "")
    + (S.view !== "novo" ? `<button class="btn primario" data-ir="novo">${icone("novo")}Novo pedido</button>` : "");
}
function renderRodape() {
  const r = $("#rodape-passo");
  r.hidden = S.view !== "novo";
  if (r.hidden) return;
  r.innerHTML = `<button class="btn fantasma" data-acao="voltar" ${S.passo ? "" : "disabled"}>${icone("setaE")}Voltar</button>
    <span class="erro">${esc(S.erroPasso)}</span>
    <span class="dicas">Ctrl+Enter avança · Alt+← volta · Ctrl+1…6 vai ao passo</span>
    ${S.passo < 5 ? `<button class="btn primario" data-acao="avancar">Avançar${icone("setaD")}</button>`
      : `<button class="btn primario" data-acao="gerar">${icone("check")}Gerar pedido</button>`}`;
}
function renderLado() {
  $("#lista-bases").innerHTML = S.bases.map((b) => `<button class="nav" data-base-rapida="${b.chave}"><span class="mono faint" style="width:44px;font-size:11px">${b.chave.toUpperCase()}</span>${esc(b.nome)}</button>`).join("");
  const emAnd = S.coletas.find((c) => c.situacao === "em andamento");
  const nFila = S.coletas.filter((c) => c.situacao === "na fila").length;
  $("#ponto-vivo").className = `ponto ${emAnd ? "vivo" : S.filaRodando ? "ok" : ""}`;
  $("#texto-vivo").textContent = emAnd ? `coletando · ${emAnd.feitas || 0}/${emAnd.total || "?"}` : nFila ? `${nFila} na fila` : "nenhuma coleta ativa";
  const c = $("#contador-fila");
  c.hidden = !nFila; c.textContent = nFila;
}

// ---------------------------------------------------------------- painel
function linhaColeta(c, compacta = false) {
  const prog = c.total ? Math.round((100 * (c.feitas || 0)) / c.total) : c.situacao === "concluído" ? 100 : 0;
  const base = S.bases.find((b) => b.chave === c.base)?.nome || c.base;
  const progTxt = c.situacao === "na fila" ? `${S.coletas.filter((x) => x.situacao === "na fila").indexOf(c) + 1}º da fila` : c.total ? `${fmt(c.feitas || 0)} / ${fmt(c.total)}` : "—";
  return `<tr data-coleta="${c.id}" class="${S.sel === c.id && S.view === "coletas" ? "sel" : ""}" style="cursor:pointer">
    <td class="nome"><b>${esc(c.nome)}</b><span>${esc(base)} · ${dataCurta(c.criado_em)}</span></td>
    <td><span class="pilula ${SITUACAO[c.situacao] || ""}">${esc(c.situacao)}</span></td>
    <td class="progresso"><span class="mono">${progTxt}</span><div class="barra ${c.situacao === "concluído" ? "ok" : c.situacao === "erro" ? "ruim" : ""}"><i style="width:${prog}%"></i></div></td>
    ${compacta ? "" : `<td class="mono muted">${dataCurta(c.inicio) || "—"}</td><td class="mono muted">${dataCurta(c.fim) || "—"}</td>`}
    <td><div class="acoes-linha">
      <button class="icone-btn" title="Abrir planilha" data-abrir="planilha" ${c.tem_planilha ? "" : "disabled"}>${icone("planilha")}</button>
      <button class="icone-btn" title="Relatório" data-abrir="relatorio" ${c.tem_relatorio ? "" : "disabled"}>${icone("relatorio")}</button>
      <button class="icone-btn" title="Abrir pasta" data-abrir="pasta" ${c.tem_pasta ? "" : "disabled"}>${icone("pasta")}</button>
    </div></td></tr>`;
}
function filtrarColetas() {
  const m = { todas: () => true, andamento: (c) => c.situacao === "em andamento", fila: (c) => c.situacao === "na fila", ok: (c) => c.situacao === "concluído", erro: (c) => c.situacao === "erro" || c.situacao === "interrompido" };
  return ordenadas().filter(m[S.abaColetas]);
}
function ordenadas() {
  const o = { "em andamento": 0, "na fila": 1 };
  const ativos = S.coletas.filter((c) => c.situacao in o).sort((a, b) => o[a.situacao] - o[b.situacao]);
  const fim = S.coletas.filter((c) => !(c.situacao in o)).sort((a, b) => (b.fim || b.criado_em || "").localeCompare(a.fim || a.criado_em || ""));
  return [...ativos, ...fim];
}
function abasColetas() {
  const n = (f) => S.coletas.filter(f).length;
  const abas = [["todas", "Todas", S.coletas.length], ["andamento", "Em andamento", n((c) => c.situacao === "em andamento")], ["fila", "Na fila", n((c) => c.situacao === "na fila")], ["ok", "Concluídas", n((c) => c.situacao === "concluído")], ["erro", "Com erro", n((c) => c.situacao === "erro" || c.situacao === "interrompido")]];
  return `<div class="abas">${abas.map(([k, t, q]) => `<button class="aba ${S.abaColetas === k ? "ativo" : ""}" data-aba="${k}">${t}<span class="n">${q}</span></button>`).join("")}</div>`;
}
function renderPainel() {
  const emAnd = S.coletas.find((c) => c.situacao === "em andamento");
  const nFila = S.coletas.filter((c) => c.situacao === "na fila").length;
  const concl = S.coletas.filter((c) => c.situacao === "concluído");
  const erros = S.coletas.filter((c) => c.situacao === "erro" || c.situacao === "interrompido");
  const celulas = concl.reduce((a, c) => a + (c.celulas || 0), 0);
  const errosConf = concl.reduce((a, c) => a + (c.erros_conferencia || 0), 0);
  let alertas = "";
  if (erros.length) alertas += `<div class="alerta">${icone("alerta")}<div><b>${erros.length === 1 ? "Uma coleta parou" : `${erros.length} coletas pararam`}</b>
    ${erros.slice(0, 3).map((c) => `<div><b style="display:inline">${esc(c.nome)}</b> — ${esc(c.mensagem || c.motivo || c.situacao)}</div>`).join("")}</div>
    <div class="acoes"><button class="btn pequeno" data-ir="coletas">Ver coletas</button></div></div>`;
  if (nFila && !S.filaRodando) alertas += `<div class="alerta aviso">${icone("alerta")}<div><b>${nFila} coleta(s) esperando com a fila parada</b>A fila para quando a janela do executor é fechada. Ela continua de onde parou.</div>
    <div class="acoes"><button class="btn pequeno" data-acao="iniciar-fila">${icone("play")}Iniciar fila</button></div></div>`;
  const pct = emAnd?.total ? Math.round((100 * (emAnd.feitas || 0)) / emAnd.total) : 0;
  const lista = filtrarColetas();
  return `${alertas}
  <section class="kpis">
    <div class="cartao kpi ${emAnd ? "ativo" : ""}"><span class="eyebrow">Em andamento</span>
      <div class="valor">${emAnd ? `${fmt(emAnd.feitas || 0)}<small> / ${fmt(emAnd.total || 0)}</small>` : "—"}</div>
      <div class="barra"><i style="width:${pct}%"></i></div>
      <span class="detalhe">${emAnd ? `${esc(emAnd.nome)} · faltam ${tempo(Math.max(0, (emAnd.total || 0) - (emAnd.feitas || 0)) * 20)}` : "nenhuma coleta agora"}</span></div>
    <div class="cartao kpi"><span class="eyebrow">Na fila</span><div class="valor">${nFila}</div><span class="detalhe">${S.filaRodando ? "rodam uma de cada vez" : nFila ? "fila parada" : "fila vazia"}</span></div>
    <div class="cartao kpi"><span class="eyebrow">Concluídas</span><div class="valor">${concl.length}</div><span class="detalhe">${fmt(celulas)} células entregues</span></div>
    <div class="cartao kpi ${errosConf ? "atencao" : ""}"><span class="eyebrow">Conferência</span>
      <div class="valor">${errosConf}<small> erros</small></div><span class="detalhe">${errosConf ? "células diferentes dos PDFs: veja o relatório" : concl.length ? "todas as células batem com os PDFs" : "nenhuma coleta concluída ainda"}</span></div>
  </section>
  <section class="cartao"><header><h2>Coletas</h2><div class="lado-dir">${abasColetas()}</div></header>
    ${lista.length ? `<div style="overflow-x:auto"><table class="tab"><thead><tr><th>Pedido</th><th>Situação</th><th>Progresso</th><th>Início</th><th>Fim</th><th></th></tr></thead>
    <tbody>${lista.map((c) => linhaColeta(c)).join("")}</tbody></table></div>`
      : `<div class="vazio">${icone("vazio")}<b>${S.coletas.length ? "Nada nesta aba" : "Monte seu primeiro pedido"}</b><span>As coletas aparecem aqui com o progresso de cada uma.</span>${S.coletas.length ? "" : `<button class="btn primario" data-ir="novo">${icone("novo")}Novo pedido</button>`}</div>`}
  </section>`;
}

// ---------------------------------------------------------------- minhas coletas
function renderColetas() {
  const lista = ordenadas();
  if (!S.sel && lista.length) S.sel = lista[0].id;
  const c = S.coletas.find((x) => x.id === S.sel);
  let det = `<div class="vazio">${icone("coletas")}<b>Nenhuma coleta selecionada</b></div>`;
  if (c) {
    const prog = c.total ? Math.round((100 * (c.feitas || 0)) / c.total) : c.situacao === "concluído" ? 100 : 0;
    const fase = { coleta: "consultando o site", aguardando: "site instável, tentando de novo", planilha: "montando a planilha", conferencia: "conferindo com os PDFs", concluido: "concluída", erro: "parou com erro", interrompido: "parada a pedido" }[c.fase] || (c.situacao === "na fila" ? "esperando a vez" : "");
    det = `<div class="detalhe-coleta">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><h2 style="margin:0;font:600 17px var(--display)">${esc(c.nome)}</h2><span class="pilula ${SITUACAO[c.situacao] || ""}">${esc(c.situacao)}</span><span class="muted">${esc(fase)}</span></div>
      <div class="barra ${c.situacao === "concluído" ? "ok" : c.situacao === "erro" ? "ruim" : ""}" style="height:7px"><i style="width:${prog}%"></i></div>
      <div class="metricas">
        <div><b>${c.total ? `${fmt(c.feitas || 0)} / ${fmt(c.total)}` : "—"}</b><span>consultas</span></div>
        <div><b>${c.celulas != null ? fmt(c.celulas) : "—"}</b><span>células${c.sr != null ? ` · ${fmt(c.sr)} SR` : ""}</span></div>
        <div><b style="color:${c.erros_conferencia ? "var(--bad)" : "inherit"}">${c.erros_conferencia ?? "—"}</b><span>erros na conferência</span></div>
      </div>
      ${c.mensagem || c.motivo ? `<div class="alerta ${c.situacao === "erro" ? "" : "aviso"}">${icone("alerta")}<div>${esc(c.mensagem || c.motivo)}</div></div>` : ""}
      <div class="barra-acoes">
        ${c.situacao === "na fila" ? `<button class="btn" data-acao-coleta="subir">${icone("subir")}Subir</button><button class="btn" data-acao-coleta="descer">${icone("descer")}Descer</button>` : ""}
        ${c.situacao === "em andamento" ? `<button class="btn perigo" data-acao-coleta="parar">${icone("parar")}Parar</button>` : ""}
        ${c.situacao === "erro" || c.situacao === "interrompido" ? `<button class="btn primario" data-acao-coleta="continuar">${icone("play")}Continuar de onde parou</button>` : ""}
        ${c.situacao !== "em andamento" ? `<button class="btn fantasma" data-acao-coleta="remover">${icone("lixo")}${c.situacao === "na fila" ? "Tirar da fila" : "Tirar do histórico"}</button>` : ""}
        <span style="margin-left:auto;display:flex;gap:6px">
          <button class="btn" data-abrir="planilha" data-id="${c.id}" ${c.tem_planilha ? "" : "disabled"}>${icone("planilha")}Planilha</button>
          <button class="btn" data-abrir="relatorio" data-id="${c.id}" ${c.tem_relatorio ? "" : "disabled"}>${icone("relatorio")}Relatório</button>
          <button class="btn" data-abrir="pasta" data-id="${c.id}" ${c.tem_pasta ? "" : "disabled"}>${icone("pasta")}Pasta</button></span>
      </div>
      <div><div class="eyebrow" style="margin-bottom:6px">Registro da coleta</div><div class="log" id="log">${S.log.length ? "" : "Sem registro ainda."}</div></div>
      <div class="mono faint" style="font-size:11px">${esc(c.pasta)}</div></div>`;
  }
  return `<div class="grade-2" style="grid-template-columns:minmax(0,1.05fr) minmax(0,1fr)">
    <section class="cartao"><header><h2>Fila e histórico</h2><div class="lado-dir"><span class="muted" style="font-size:12px">uma coleta por vez</span></div></header>
      ${lista.length ? `<table class="tab"><thead><tr><th>Pedido</th><th>Situação</th><th>Progresso</th><th></th></tr></thead><tbody>${lista.map((x) => linhaColeta(x, true)).join("")}</tbody></table>`
        : `<div class="vazio">${icone("vazio")}<b>Nenhuma coleta ainda</b><button class="btn primario" data-ir="novo">${icone("novo")}Novo pedido</button></div>`}
    </section>
    <section class="cartao"><div class="corpo">${det}</div></section></div>`;
}
async function carregarLog() {
  if (S.view !== "coletas" || !S.sel) return;
  S.log = await api.log(S.sel, 60);
  const el = $("#log");
  if (!el) return;
  const fundo = el.scrollTop + el.clientHeight >= el.scrollHeight - 10;
  el.innerHTML = S.log.length ? S.log.map((l) => {
    const cls = /ERROS: [1-9]|ERRO:|desisti|Fim: erro/.test(l) ? "l-erro" : /tentativa|AVISO/.test(l) ? "l-tent" : /concluido|Coleta completa|ERROS: 0/.test(l) ? "l-ok" : "";
    return `<div class="${cls}">${esc(l)}</div>`;
  }).join("") : "Sem registro ainda.";
  if (fundo) el.scrollTop = el.scrollHeight;
}

// ---------------------------------------------------------------- configurações
function renderConfig() {
  const o = S.opcoesInfo || {};
  return `<section class="cartao"><header><h2>Aparência</h2></header><div class="corpo bloco">
      <div class="segmentado">${[["claro", "Claro"], ["escuro", "Escuro"], ["auto", "Seguir o Windows"]].map(([k, t]) => `<button class="${S.prefs.tema === k ? "ativo" : ""}" data-tema="${k}">${t}</button>`).join("")}</div>
      <p class="ajuda muted" style="margin:0">Ctrl+D alterna entre claro e escuro.</p></div></section>
    <section class="cartao"><header><h2>Pasta padrão dos pedidos</h2></header><div class="corpo linha-form">
      <input class="entrada mono" id="cfg-pasta" style="flex:1" value="${esc(S.prefs.pasta)}">
      <button class="btn" data-acao="escolher-pasta-padrao">${icone("pasta")}Escolher…</button></div></section>
    <section class="cartao"><header><h2>Opções dos formulários do TabNet</h2></header><div class="corpo bloco">
      <p class="ajuda muted" style="margin:0">As listas de cada campo (municípios, CID, procedimentos…) foram lidas do site em <b class="mono">${esc(o.atualizado_em || "—")}</b>. Atualize quando o DATASUS publicar períodos novos.</p>
      <div class="linha-form"><button class="btn" data-acao="atualizar-opcoes" ${o.ativo ? "disabled" : ""}>${icone("atualizar")}${o.ativo ? "Atualizando…" : "Atualizar agora"}</button><span class="muted">${esc(o.mensagem || "")}</span></div></div></section>
    <section class="cartao"><header><h2>Atalhos</h2></header><div class="corpo"><table class="tab"><tbody>
      ${[["Ctrl+N", "Novo pedido"], ["Ctrl+Enter", "Avançar no pedido"], ["Alt+←", "Voltar um passo"], ["Ctrl+1 … 6", "Ir ao passo"], ["Ctrl+H", "Minhas coletas"], ["Ctrl+D", "Alternar tema"]].map(([k, t]) => `<tr><td class="mono" style="width:160px">${k}</td><td>${t}</td></tr>`).join("")}
    </tbody></table></div></section>`;
}

// ---------------------------------------------------------------- novo pedido
function renderNovo() {
  const p = S.p;
  const sub = [
    S.bases.find((b) => b.chave === p.base)?.nome + (p.abrangencia === "estadual" ? ` · ${p.estados.length} UF` : " · Brasil"),
    `${p.conteudos.length} conteúdo(s) · ${p.linha}`, `${p.periodos.length} período(s)`,
    Object.values(p.filtros).filter((v) => v.length).length ? `${Object.values(p.filtros).filter((v) => v.length).length} campo(s)` : "opcional",
    { por_periodo: "aba por período", longo: "aba única", serie: "série no tempo" }[p.formato], "conferir e gerar",
  ];
  const passos = `<nav class="passos">${PASSOS.map(([t], i) => `<button class="passo ${i === S.passo ? "atual" : i < S.passo ? "feito" : ""}" data-passo="${i}">
    <span class="n">${i < S.passo ? "✓" : i + 1}</span><b>${t}</b><span>${esc(sub[i])}</span></button>`).join("")}</nav>`;
  const corpo = [passoBase, passoTabela, passoPeriodo, passoFiltros, passoSaida, passoRevisar][S.passo]();
  return `${passos}<div class="grade-2"><div style="display:grid;gap:16px;min-width:0">${corpo}</div><aside class="trilho" id="trilho"></aside></div>`;
}
function passoBase() {
  const p = S.p;
  const base = S.bases.find((b) => b.chave === p.base);
  return `<section class="cartao"><div class="corpo bloco"><h3>Qual base de dados?</h3>
    <div class="cartoes-base">${S.bases.map((b) => `<button class="base ${b.chave === p.base ? "sel" : ""}" data-base="${b.chave}">
      <b>${b.chave === p.base ? icone("check").replace("<svg", '<svg style="width:16px;height:16px;color:var(--accent)"') : ""}${esc(b.nome)} <span class="sigla">${b.chave.toUpperCase()}</span></b>
      <span class="muted" style="font-size:12px">${esc(b.descricao)}</span>
      <span class="meta"><span>${esc(b.periodo)}</span><span>${b.n_periodos} ${b.mensal ? "meses" : "anos"}</span><span>${b.n_conteudos} conteúdos</span><span>${b.n_filtros} filtros</span></span></button>`).join("")}</div></div></section>
  <section class="cartao"><div class="corpo bloco"><h3>Onde?</h3>
    <div class="segmentado"><button class="${p.abrangencia === "nacional" ? "ativo" : ""}" data-abr="nacional">Brasil inteiro</button><button class="${p.abrangencia === "estadual" ? "ativo" : ""}" data-abr="estadual">Dentro de estados</button></div>
    <p class="ajuda">${p.abrangencia === "nacional" ? "Linhas por região, estado, ano…" : `Linhas por município e mais detalhes: ${esc(base?.so_estadual.join(", "))}.`}</p>
    ${p.abrangencia === "estadual" ? `<div class="chips">${Object.keys(S.ufs).map((u) => `<button class="chip uf ${p.estados.includes(u) ? "sel" : ""}" data-uf="${u}" title="${esc(S.ufs[u])}">${u.toUpperCase()}</button>`).join("")}</div>
      <div class="chips"><button class="chip" data-regiao="todos">Todos</button>${Object.keys(REGIOES).map((r) => `<button class="chip" data-regiao="${r}">${r}</button>`).join("")}<button class="chip" data-regiao="limpar">Limpar</button></div>` : ""}
  </div></section>`;
}
function chipsOrdenados(lista, sel, attr) {
  return `<div class="chips">${lista.map((c) => { const i = sel.indexOf(c); return `<button class="chip ${i >= 0 ? "sel" : ""}" data-${attr}="${esc(c)}">${i >= 0 ? `<span class="ordem">${i + 1}</span>` : ""}${esc(c)}</button>`; }).join("")}</div>`;
}
function passoTabela() {
  const p = S.p, f = S.form;
  return `<section class="cartao"><div class="corpo bloco"><h3><span class="n">1</span>O que contar em cada célula</h3>
      <p class="ajuda">Marque quantos quiser. Vêm na mesma consulta, na ordem em que você marcar.</p>${chipsOrdenados(f.conteudos, p.conteudos, "conteudo")}</div></section>
    <section class="cartao"><div class="corpo bloco"><h3><span class="n">2</span>Uma linha da planilha para cada</h3>
      <div class="linha-form"><select class="entrada" id="sel-linha" style="min-width:300px">${f.linhas.map((l) => `<option ${l === p.linha ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <label class="interruptor"><input type="checkbox" id="chk-ordenar" ${p.ordenar ? "checked" : ""}><i></i>Ordenar as linhas pelo valor</label></div></div></section>
    <section class="cartao"><div class="corpo bloco"><h3><span class="n">3</span>Quebrar em colunas <span class="muted" style="font-weight:400">(opcional)</span></h3>
      <p class="ajuda">Cada tipo marcado vira um bloco com <b>todas</b> as suas categorias. Para só algumas, ou para somar categorias, use o passo Filtros.</p>${chipsOrdenados(f.colunas, p.colunas, "coluna")}</div></section>
    <section class="cartao"><header><h2>Prévia das colunas</h2></header><div class="corpo" id="previa"></div></section>`;
}
function construtor(id, opcoes, itens, ajuda, permiteGrupo = true) {
  const n = S.marc[id].size;
  const dica = n === 0 ? "Clique nas opções para marcar. A caixa do cabeçalho marca todas as mostradas." : n === 1 ? "1 marcada → “Adicionar separadas”." : `${n} marcadas → “Adicionar separadas” (um resultado cada) ou “Somar num grupo” (um só).`;
  return `<div class="bloco">
    <div class="busca">${icone("busca")}<input class="entrada" id="busca-${id}" placeholder="${id === "per" ? "Buscar período (ex.: 2025)" : "Buscar pelo nome ou código"}" value="${esc(S.busca[id])}"></div>
    <div class="lista-opcoes" id="lista-${id}"></div>
    <div class="barra-acoes"><button class="btn" data-b="${id}" data-op="separadas">+ Adicionar separadas</button>
      ${permiteGrupo ? `<button class="btn" data-b="${id}" data-op="grupo">Σ Somar num grupo</button>` : ""}
      <button class="btn fantasma" data-b="${id}" data-op="desmarcar">Desmarcar</button><span class="info" id="info-${id}">${esc(dica)}</span></div>
    <div><div class="eyebrow" style="margin-bottom:6px">Será coletado · ${itens.length} resultado(s)</div>
      <div class="coletado">${itens.length ? itens.map((it, i) => `<div class="item-coletado">
        <input value="${esc(it.nome)}" data-b="${id}" data-renomear="${i}" title="Nome na planilha">
        <span class="tag ${it.tipo === "grupo" ? "grupo" : ""}">${it.tipo === "grupo" ? "somadas" : "separada"}</span>
        <span class="mono faint" style="font-size:11px">${it.valores.length} op.</span>
        <button class="icone-btn" data-b="${id}" data-remover="${i}" title="Remover">${icone("lixo")}</button></div>`).join("")
        : `<div class="vazio" style="padding:18px">${esc(ajuda)}</div>`}</div></div></div>`;
}
function opcoesDe(id) {
  if (id === "per") return [...S.form.periodos].reverse().map((v) => [v, v]);
  return S.form.filtros.find((f) => f.nome === S.campo)?.opcoes || [];
}
function itensDe(id) {
  if (id === "per") return S.p.periodos;
  return (S.p.filtros[S.campo] = S.p.filtros[S.campo] || []);
}
function renderListaOpcoes(id) {
  const el = $(`#lista-${id}`);
  if (!el) return;
  const termo = S.busca[id].trim().toLowerCase();
  const todas = opcoesDe(id);
  const vis = termo ? todas.filter(([, l]) => l.toLowerCase().includes(termo)) : todas;
  const est = {};
  for (const it of itensDe(id)) for (const v of it.valores) est[v] ??= it.tipo === "separada" ? "separada" : "em grupo";
  const limite = 400;
  const todasMarcadas = vis.length && vis.every(([v]) => S.marc[id].has(v));
  el.innerHTML = `<div class="opcao" data-b="${id}" data-marcar-todas="1" style="position:sticky;top:0;background:var(--raise);z-index:1">
      <span class="caixa" ${todasMarcadas ? 'style="background:var(--accent);border-color:var(--accent)"' : ""}></span><b style="font-size:12px">${vis.length === todas.length ? `Todas as ${fmt(todas.length)} opções` : `${fmt(vis.length)} de ${fmt(todas.length)}`}</b></div>`
    + vis.slice(0, limite).map(([v, l]) => `<div class="opcao ${S.marc[id].has(v) ? "marcada" : ""}" data-b="${id}" data-v="${esc(v)}"><span class="caixa"></span><span>${esc(l)}</span>${est[v] ? `<span class="estado">${est[v]}</span>` : ""}</div>`).join("")
    + (vis.length > limite ? `<div class="opcao faint">Mostrando ${limite} de ${fmt(vis.length)}. Refine a busca.</div>` : "");
}
function passoPeriodo() {
  const f = S.form;
  const ops = (sel) => f.periodos.map((x) => `<option ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
  return `<section class="cartao"><div class="corpo bloco"><h3>Atalhos para um intervalo</h3>
      <div class="linha-form"><div class="campo"><label>De</label><select class="entrada mono" id="per-de">${ops(S.de)}</select></div>
        <div class="campo"><label>Até</label><select class="entrada mono" id="per-ate">${ops(S.ate)}</select></div>
        <button class="btn" data-atalho="separados">Cada um separado</button><button class="btn" data-atalho="somado">Tudo somado</button>
        ${f.mensal ? `<button class="btn" data-atalho="ano">Um grupo por ano</button><button class="btn" data-atalho="tri">Um grupo por trimestre</button>` : ""}</div>
      <p class="ajuda">Cada período sozinho vira uma aba da planilha; períodos somados viram uma aba com o total. O TabNet avisa que os últimos seis meses ainda podem mudar.</p></div></section>
    <section class="cartao"><div class="corpo">${construtor("per", null, S.p.periodos, "Nenhum período: use um atalho ou marque na lista.")}</div></section>`;
}
function passoFiltros() {
  const f = S.form;
  const campo = f.filtros.find((x) => x.nome === S.campo);
  const status = (n) => { const its = S.p.filtros[n] || []; if (!its.length) return ""; const s = its.filter((i) => i.tipo === "separada").length, g = its.length - s; return [s ? `${s} sep.` : "", g ? `${g} grupo${g > 1 ? "s" : ""}` : ""].filter(Boolean).join(" · "); };
  const dica = ehLinha(S.campo) ? "Este campo está nas linhas da planilha: as opções escolhem quais linhas aparecem (sem nada, aparecem todas)."
    : campo?.coluna ? "Também existe como coluna: as opções separadas daqui saem numa consulta só." : "";
  return `<section class="cartao"><div class="corpo bloco">
    <p class="ajuda" style="margin:0">Escolha um campo e marque as opções. <b>1 item</b> limita o pedido inteiro; <b>2 ou mais</b> viram um bloco de colunas na planilha.</p>
    <div class="seletor"><div class="campos">${f.filtros.map((x) => `<button class="campo-item ${x.nome === S.campo ? "sel" : ""}" data-campo="${esc(x.nome)}">
        <span>${esc(x.nome)} <small>${fmt(x.opcoes.length)}</small></span><em>${status(x.nome)}</em></button>`).join("")}</div>
      <div class="bloco" style="min-width:0">
        <div class="linha-form" style="justify-content:space-between"><h3 style="margin:0;font:600 15px var(--display)">${esc(S.campo)}</h3>
          ${ehLinha(S.campo) ? "" : `<div class="campo" style="grid-auto-flow:column;align-items:center;gap:8px"><label>Nome do bloco</label><input class="entrada" id="titulo-bloco" value="${esc(S.p.titulos[S.campo] || S.campo.toUpperCase())}" style="width:200px"></div>`}</div>
        ${dica ? `<p class="ajuda" style="margin:0">${esc(dica)}</p>` : ""}
        ${construtor("fil", null, itensDe("fil"), "Nada escolhido: este campo fica em “Todas as categorias”.", !ehLinha(S.campo))}
      </div></div></div></section>
    <section class="cartao"><div class="corpo bloco"><h3>Escolhendo em mais de um campo</h3>
      <div class="grade-2" style="grid-template-columns:1fr 1fr;gap:10px">
        ${[["independentes", "Um bloco por campo", "Masc, Fem, 20 a 29, 30 a 39 → 4 resultados"], ["cruzar", "Combinar os campos", "Masc 20 a 29, Masc 30 a 39, Fem 20 a 29… → cada combinação"]].map(([k, t, d]) => `<label class="opcao-radio ${S.p.combinar === k ? "sel" : ""}"><input type="radio" name="combinar" value="${k}" ${S.p.combinar === k ? "checked" : ""}><div><b>${t}</b><span>${d}</span></div></label>`).join("")}
      </div></div></section>`;
}
function passoSaida() {
  const p = S.p;
  const radio = (nome, val, titulo, desc) => `<label class="opcao-radio ${p[nome] === val ? "sel" : ""}"><input type="radio" name="${nome}" value="${val}" ${p[nome] === val ? "checked" : ""}><div><b>${titulo}</b><span>${desc}</span></div></label>`;
  const regioesOk = p.abrangencia === "nacional" && p.linha === "Unidade da Federação";
  return `<section class="cartao"><div class="corpo bloco"><h3>Pedido</h3>
      <div class="linha-form"><div class="campo" style="flex:1"><label for="nome">Nome do pedido</label><input class="entrada" id="nome" value="${esc(p.nome)}"></div></div>
      <div class="linha-form"><div class="campo" style="flex:1"><label>Salvar em</label><input class="entrada mono" id="pasta" value="${esc(p.pasta)}"></div><button class="btn" data-acao="escolher-pasta">${icone("pasta")}Escolher…</button></div></div></section>
    <section class="cartao"><div class="corpo bloco"><h3>Formato da planilha</h3>
      ${radio("formato", "por_periodo", "Uma aba por período, com blocos de colunas", "Como a planilha FA - INTERNAÇÕES")}
      ${radio("formato", "longo", "Tudo numa aba, uma linha por valor", "Para filtros, tabela dinâmica e Power BI")}
      ${radio("formato", "serie", "Uma aba por conteúdo, períodos lado a lado", "Para ver a evolução no tempo")}
      <label class="interruptor" style="${regioesOk ? "" : "opacity:.45;pointer-events:none"}"><input type="checkbox" id="chk-regioes" ${p.regioes ? "checked" : ""}><i></i>Acrescentar BRASIL - TOTAL e as regiões no fim${regioesOk ? "" : " (só com linhas por Unidade da Federação, no Brasil inteiro)"}</label>
      <div class="campo"><label>Conteúdos dentro dos blocos (SEXO, IDADE…)</label>${chipsOrdenados(p.conteudos, p.contBlocos.length ? p.contBlocos : p.conteudos.slice(0, 1), "contbloco")}</div></div></section>
    <section class="cartao"><div class="corpo bloco"><h3>Evidências e conferências</h3>
      ${radio("evidencias", "pdf_png", "PDF e print de cada consulta", "Recomendado")}${radio("evidencias", "pdf", "Só PDF", "Menos arquivos")}${radio("evidencias", "nenhuma", "Sem evidências", "Mais rápido, sem prova da origem")}
      <label class="interruptor"><input type="checkbox" id="chk-conf-total" ${p.confTotal ? "checked" : ""}><i></i>Conferir que a soma das linhas bate com o TOTAL do site</label>
      <label class="interruptor"><input type="checkbox" id="chk-conf-pdf" ${p.confPdf ? "checked" : ""}><i></i>Conferir cada valor da planilha com o texto do PDF</label>
      <p class="ajuda" style="margin:0">Sem resultado vira <b class="mono">SR</b>: linhas zeradas (sempre exibidas), “Nenhum registro selecionado”, “-” e “...”.</p></div></section>`;
}
function passoRevisar() {
  const e = S.est || {};
  return `<section class="cartao"><header><h2>Prévia da planilha</h2><div class="lado-dir"><span class="mono muted" style="font-size:12px">${esc((e.abas || [])[0] || "")} · ${(e.abas || []).length} aba(s) · “·” = valor</span></div></header><div class="corpo" id="previa"></div></section>
    ${(e.avisos || []).length ? `<div class="alerta aviso">${icone("alerta")}<div><b>Atenção</b>${e.avisos.map((a) => `<div>${esc(a)}</div>`).join("")}</div></div>` : ""}`;
}
function renderPrevia() {
  const el = $("#previa");
  if (!el) return;
  const e = S.est;
  if (!e) { el.innerHTML = '<div class="esqueleto" style="width:60%"></div>'; return; }
  if (e.erro) { el.innerHTML = `<div class="alerta">${icone("alerta")}<div>${esc(e.erro)}</div></div>`; return; }
  const cols = e.colunas;
  const grupos = [];
  for (const c of cols) {
    const g = c.grupo === null ? `#${c.sub}` : c.grupo === "=TOTAL" ? `=${c.sub}` : c.grupo;
    if (grupos.length && grupos[grupos.length - 1].g === g && c.grupo && c.grupo !== "=TOTAL") grupos[grupos.length - 1].cols.push(c);
    else grupos.push({ g, cols: [c], titulo: c.grupo && c.grupo !== "=TOTAL" ? c.grupo : c.sub });
  }
  const variosCont = new Set(cols.filter((c) => c.grupo && c.grupo !== "=TOTAL").map((c) => c.conteudo)).size > 1;
  const cab1 = grupos.map((g) => (g.g[0] === "#" || g.g[0] === "=") ? `<th rowspan="2">${esc(g.titulo)}</th>` : `<th colspan="${g.cols.length}">${esc(g.titulo)}</th>`).join("");
  const cab2 = grupos.filter((g) => !(g.g[0] === "#" || g.g[0] === "=")).flatMap((g) => g.cols.map((c) => `<th>${esc(c.sub)}${variosCont ? ` · ${esc(c.conteudo)}` : ""}</th>`)).join("");
  const ls = e.linhas;
  const iSep = ls.indexOf("");
  const corpo = iSep > 0 ? ls.slice(0, Math.min(5, iSep)) : ls.slice(0, 6);
  const fim = iSep > 0 ? ls.slice(iSep) : [];
  const mostrar = [...corpo, ...(ls.length > corpo.length + fim.length ? ["…"] : []), ...fim];
  const linha = (r) => r === "" ? `<tr class="sep"><td colspan="${cols.length + 1}"></td></tr>` : `<tr><td>${esc(r)}</td>${cols.map(() => `<td>${r === "…" ? "…" : "·"}</td>`).join("")}</tr>`;
  el.innerHTML = `<div class="planilha"><table><thead><tr><th rowspan="2">${esc(S.p.linha === "Unidade da Federação" ? "ESTADOS" : S.p.linha.toUpperCase())}</th>${cab1}</tr><tr>${cab2}</tr></thead><tbody>${mostrar.map(linha).join("")}</tbody></table></div>
    <p class="ajuda muted" style="margin:10px 0 0">${fmt(ls.filter(Boolean).length)} linhas × ${fmt(cols.length)} colunas por aba.</p>`;
}
function renderTrilho() {
  const el = $("#trilho");
  if (!el) return;
  const p = S.p, e = S.est || {};
  const filtros = Object.entries(p.filtros).filter(([, v]) => v.length);
  el.innerHTML = `<section class="cartao estimativa corpo" style="padding:16px">
      <span class="eyebrow">Estimativa</span>
      ${e.erro ? `<span class="muted">${esc(e.erro)}</span>` : `
      <div class="linha"><span class="muted">Consultas ao site</span><span class="grande">${e.consultas != null ? fmt(e.consultas) : "…"}</span></div>
      <div class="linha"><span class="muted">Tempo estimado</span><b class="num">${e.segundos != null ? tempo(e.segundos) : "…"}</b></div>
      <div class="linha"><span class="muted">Arquivos de evidência</span><b class="num">${e.arquivos != null ? fmt(e.arquivos) : "…"}</b></div>
      <span class="conta">uma consulta por vez · cerca de 20 s cada</span>`}</section>
    <section class="cartao resumo corpo" style="padding:16px"><span class="eyebrow" style="display:block;margin-bottom:10px">Resumo do pedido</span><dl>
      <div><dt>Base</dt><dd>${esc(S.bases.find((b) => b.chave === p.base)?.nome)} · ${p.abrangencia === "nacional" ? "Brasil" : `${p.estados.length} estado(s): ${esc(p.estados.map((u) => u.toUpperCase()).join(", ") || "nenhum")}`}</dd></div>
      <div><dt>Linhas</dt><dd>${esc(p.linha)}</dd></div>
      <div><dt>Colunas</dt><dd>Total${p.colunas.map((c) => ` + ${esc(c)}`).join("")}</dd></div>
      <div><dt>Conteúdo</dt><dd>${esc(p.conteudos.join(", "))}</dd></div>
      <div><dt>Período</dt><dd>${p.periodos.length} item(ns): ${esc(p.periodos.slice(0, 3).map((x) => x.nome).join(", "))}${p.periodos.length > 3 ? "…" : ""}</dd></div>
      <div><dt>Filtros</dt><dd>${filtros.length ? filtros.map(([c, its]) => `${esc(c)}: ${its.length} item(ns)`).join("<br>") : "nenhum (todas as categorias)"}</dd></div>
    </dl></section>`;
}

// ---------------------------------------------------------------- ações dos construtores de itens
function adicionar(id, op, valores, nome) {
  const itens = itensDe(id);
  const rot = Object.fromEntries(opcoesDe(id));
  const ordem = new Map(opcoesDe(id).map(([v], i) => [v, i]));
  let sel = valores ?? [...S.marc[id]];
  sel = sel.filter((v) => rot[v] !== undefined).sort((a, b) => (id === "per" ? chavePeriodo(a) - chavePeriodo(b) : ordem.get(a) - ordem.get(b)));
  if (!sel.length) { toast("Marque pelo menos uma opção na lista."); return; }
  if (op === "separadas") {
    const ja = new Set(itens.filter((i) => i.tipo === "separada").map((i) => i.valores[0]));
    for (const v of sel) if (!ja.has(v)) itens.push({ tipo: "separada", nome: rot[v], valores: [v] });
  } else {
    if (sel.length < 2) { toast("Para somar num grupo, marque pelo menos 2 opções."); return; }
    if (itens.some((i) => i.tipo === "grupo" && i.valores.join() === sel.join())) { toast("Esse grupo já está na lista."); return; }
    itens.push({ tipo: "grupo", nome: nome || nomeGrupo(sel.map((v) => rot[v])), valores: sel });
  }
  depoisItens(id);
}
function depoisItens(id) {
  S.marc[id].clear();
  if (id === "fil") {
    if (ehLinha(S.campo)) S.p.filtros[S.campo] = itensDe("fil").filter((i) => i.tipo === "separada");
    for (const [c, its] of Object.entries(S.p.filtros)) if (its.length && !S.p.ordemCampos.includes(c)) S.p.ordemCampos.push(c);
    S.p.ordemCampos = S.p.ordemCampos.filter((c) => S.p.filtros[c]?.length);
  }
  const y = $("#rolagem").scrollTop;
  render();
  $("#rolagem").scrollTop = y;
  agendarEstimativa();
}
function atalhoPeriodo(tipo) {
  const a = chavePeriodo($("#per-de").value), z = chavePeriodo($("#per-ate").value);
  if (a > z) { toast("O início do intervalo precisa vir antes do fim.", "erro"); return; }
  const intervalo = S.form.periodos.filter((x) => chavePeriodo(x) >= a && chavePeriodo(x) <= z);
  if (tipo === "separados") return adicionar("per", "separadas", intervalo);
  if (tipo === "somado") return intervalo.length === 1 ? adicionar("per", "separadas", intervalo) : adicionar("per", "grupo", intervalo, `${intervalo[0]} a ${intervalo[intervalo.length - 1]} (somado)`);
  const grupos = {};
  for (const x of intervalo) {
    const k = chavePeriodo(x), ano = Math.floor((k - 1) / 12), mes = ((k - 1) % 12) + 1;
    (grupos[tipo === "ano" ? `${ano}` : `${Math.floor((mes - 1) / 3) + 1}º tri/${ano}`] ??= []).push(x);
  }
  for (const [g, ps] of Object.entries(grupos)) ps.length === 1 ? adicionar("per", "separadas", ps) : adicionar("per", "grupo", ps, `${g} (somado)`);
}

// ---------------------------------------------------------------- eventos
window.addEventListener("error", (e) => api && api.registrar_erro(`${e.message} @ ${e.filename}:${e.lineno}`));
window.addEventListener("unhandledrejection", (e) => api && api.registrar_erro(`promessa: ${e.reason}`));
document.addEventListener("click", async (ev) => {
  if (ev.target.matches('input[type="radio"]')) return; // o clique no rótulo já tratou
  const t = ev.target.closest("button, [data-v], [data-marcar-todas], [data-coleta], label.opcao-radio");
  if (!t) return;
  const d = t.dataset, p = S.p;
  if (d.ir) return ir(d.ir);
  if (d.tema) return trocarTema(d.tema);
  if (d.baseRapida) { p.base = d.baseRapida; S.passo = 0; await carregarFormulario(); ir("novo"); return agendarEstimativa(); }
  if (d.passo) return irPasso(+d.passo);
  if (d.base) { p.base = d.base; await carregarFormulario(); render(); return agendarEstimativa(); }
  if (d.abr) { p.abrangencia = d.abr; await carregarFormulario(); render(); return agendarEstimativa(); }
  if (d.uf) { p.estados = p.estados.includes(d.uf) ? p.estados.filter((u) => u !== d.uf) : [...p.estados, d.uf]; await carregarFormulario(); render(); return agendarEstimativa(); }
  if (d.regiao) { p.estados = d.regiao === "todos" ? Object.keys(S.ufs) : d.regiao === "limpar" ? [] : REGIOES[d.regiao].split(" "); await carregarFormulario(); render(); return agendarEstimativa(); }
  const alternar = (lista, v) => (lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v]);
  if (d.conteudo) { p.conteudos = alternar(p.conteudos, d.conteudo); p.contBlocos = p.contBlocos.filter((c) => p.conteudos.includes(c)); render(); return agendarEstimativa(); }
  if (d.coluna) { p.colunas = alternar(p.colunas, d.coluna); render(); return agendarEstimativa(); }
  if (d.contbloco) { const atual = p.contBlocos.length ? p.contBlocos : p.conteudos.slice(0, 1); p.contBlocos = alternar(atual, d.contbloco); render(); return agendarEstimativa(); }
  if (d.campo) { S.campo = d.campo; S.marc.fil.clear(); S.busca.fil = ""; return render(); }
  if (d.atalho) return atalhoPeriodo(d.atalho);
  if (d.v !== undefined && d.b) { const m = S.marc[d.b]; m.has(d.v) ? m.delete(d.v) : m.add(d.v); t.classList.toggle("marcada"); return atualizarInfo(d.b); }
  if (d.marcarTodas) {
    const termo = S.busca[d.b].trim().toLowerCase();
    const vis = opcoesDe(d.b).filter(([, l]) => !termo || l.toLowerCase().includes(termo)).map(([v]) => v);
    const todas = vis.every((v) => S.marc[d.b].has(v));
    vis.forEach((v) => (todas ? S.marc[d.b].delete(v) : S.marc[d.b].add(v)));
    renderListaOpcoes(d.b); return atualizarInfo(d.b);
  }
  if (d.op) { if (d.op === "desmarcar") { S.marc[d.b].clear(); renderListaOpcoes(d.b); return atualizarInfo(d.b); } return adicionar(d.b, d.op); }
  if (d.remover !== undefined) { itensDe(d.b).splice(+d.remover, 1); return depoisItens(d.b); }
  if (t.matches("label.opcao-radio")) { const inp = t.querySelector("input"); p[inp.name] = inp.value; render(); return agendarEstimativa(); }
  if (d.acao === "avancar") return irPasso(S.passo + 1);
  if (d.acao === "voltar") return irPasso(S.passo - 1);
  if (d.acao === "gerar") return gerar();
  if (d.acao === "escolher-pasta") { const r = await api.escolher_pasta(p.pasta); if (r) { p.pasta = r; render(); agendarEstimativa(); } return; }
  if (d.acao === "escolher-pasta-padrao") { const r = await api.escolher_pasta(S.prefs.pasta); if (r) { S.prefs.pasta = r; p.pasta = r; await api.salvar_preferencia("pasta", r); render(); } return; }
  if (d.acao === "atualizar-opcoes") { await api.atualizar_opcoes(); S.opcoesInfo = await api.info_opcoes(); render(); return; }
  if (d.acao === "iniciar-fila") { await api.acao_coleta("", "iniciar_fila"); toast("Fila iniciada numa janela própria."); setTimeout(atualizarColetas, 1500); return; }
  if (d.abrir) { ev.stopPropagation(); const id = d.id || t.closest("[data-coleta]")?.dataset.coleta; const r = await api.abrir(id, d.abrir); if (!r.ok) toast("Arquivo ainda não existe.", "erro"); return; }
  if (d.acaoColeta) {
    const c = S.coletas.find((x) => x.id === S.sel);
    if (d.acaoColeta === "parar" && !(await confirmar("Parar a coleta?", "Ela termina a consulta atual, salva tudo e para. Dá para continuar depois de onde parou.", "Parar", true))) return;
    if (d.acaoColeta === "remover" && !(await confirmar(c.situacao === "na fila" ? "Tirar da fila?" : "Tirar do histórico?", "A pasta, a planilha e as evidências continuam onde estão.", "Tirar", true))) return;
    const r = await api.acao_coleta(S.sel, d.acaoColeta);
    if (!r.ok) toast("Não foi possível fazer isso agora.", "erro");
    else if (d.acaoColeta === "parar") toast("Parada pedida: a coleta para ao terminar a consulta atual.");
    else if (d.acaoColeta === "continuar") toast("A coleta voltou para a fila e continua de onde parou.", "ok");
    return atualizarColetas();
  }
  if (d.coleta) { S.sel = d.coleta; S.log = []; return S.view === "coletas" ? render() : ir("coletas"); }
  if (d.aba) { S.abaColetas = d.aba; return render(); }
});
function atualizarInfo(id) {
  const n = S.marc[id].size;
  const el = $(`#info-${id}`);
  if (el) el.textContent = n === 0 ? "Clique nas opções para marcar. A caixa do cabeçalho marca todas as mostradas." : n === 1 ? "1 marcada → “Adicionar separadas”." : `${n} marcadas → “Adicionar separadas” (um resultado cada) ou “Somar num grupo” (um só).`;
}
document.addEventListener("input", (ev) => {
  const t = ev.target;
  if (t.id === "busca-fil" || t.id === "busca-per") { const id = t.id.slice(6); S.busca[id] = t.value; return renderListaOpcoes(id); }
  if (t.id === "nome") { S.p.nome = t.value; return; }
  if (t.id === "titulo-bloco") { S.p.titulos[S.campo] = t.value.trim() || S.campo.toUpperCase(); return agendarEstimativa(); }
});
document.addEventListener("change", (ev) => {
  const t = ev.target, p = S.p;
  if (t.id === "per-de") { S.de = t.value; return; }
  if (t.id === "per-ate") { S.ate = t.value; return; }
  if (t.id === "sel-linha") { p.linha = t.value; render(); return agendarEstimativa(); }
  if (t.id === "chk-ordenar") { p.ordenar = t.checked; return agendarEstimativa(); }
  if (t.id === "chk-regioes") { p.regioes = t.checked; return agendarEstimativa(); }
  if (t.id === "chk-conf-total") p.confTotal = t.checked;
  if (t.id === "chk-conf-pdf") p.confPdf = t.checked;
  if (t.id === "pasta") { p.pasta = t.value; return; }
  if (t.id === "cfg-pasta") { S.prefs.pasta = t.value; api.salvar_preferencia("pasta", t.value); return; }
  if (t.id === "nome") { p.nome = t.value; renderTrilho(); return; }
  if (t.dataset.renomear !== undefined) { const it = itensDe(t.dataset.b)[+t.dataset.renomear]; if (it && t.value.trim()) it.nome = t.value.trim(); agendarEstimativa(); }
});
document.addEventListener("keydown", (ev) => {
  if (ev.ctrlKey && ev.key === "Enter" && S.view === "novo") { ev.preventDefault(); return S.passo < 5 ? irPasso(S.passo + 1) : gerar(); }
  if (ev.altKey && ev.key === "ArrowLeft" && S.view === "novo") { ev.preventDefault(); return irPasso(S.passo - 1); }
  if (ev.ctrlKey && /^[1-6]$/.test(ev.key)) { ev.preventDefault(); if (S.view !== "novo") ir("novo"); return irPasso(+ev.key - 1); }
  if (ev.ctrlKey && ev.key.toLowerCase() === "d") { ev.preventDefault(); return trocarTema(temaResolvido() === "escuro" ? "claro" : "escuro"); }
  if (ev.ctrlKey && ev.key.toLowerCase() === "n") { ev.preventDefault(); return ir("novo"); }
  if (ev.ctrlKey && ev.key.toLowerCase() === "h") { ev.preventDefault(); return ir("coletas"); }
});

async function gerar() {
  for (let k = 0; k < 5; k++) { const e = validar(k); if (e) { S.passo = k; S.erroPasso = e; return render(); } }
  const pedido = montarPedido();
  let r = await api.gerar(pedido, false);
  if (r.existe) {
    if (!(await confirmar("Pedido já existe", `Já existe um pedido com esse nome em ${r.pasta}. Substituir? Se a coleta já tinha começado, ela continua de onde parou nas consultas que não mudaram.`, "Substituir"))) return;
    r = await api.gerar(pedido, true);
  }
  if (r.erro) return toast(r.erro, "erro");
  toast(`“${pedido.nome}” entrou na fila (${r.posicao === 1 ? "começa agora" : `${r.posicao}º da fila`}): ${fmt(S.est?.consultas)} consultas, cerca de ${tempo(S.est?.segundos || 0)}.`, "ok");
  S.sel = r.id;
  await atualizarColetas();
  ir("coletas");
}

// ---------------------------------------------------------------- atualização periódica
async function atualizarColetas() {
  const r = await api.coletas();
  const antes = JSON.stringify(S.coletas) + S.filaRodando;
  S.coletas = r.coletas; S.filaRodando = r.fila_rodando;
  renderLado();
  if (JSON.stringify(S.coletas) + S.filaRodando !== antes && (S.view === "painel" || S.view === "coletas")) {
    const y = $("#rolagem").scrollTop;
    render();
    $("#rolagem").scrollTop = y;
  } else if (S.view !== "novo") renderTopo();
  carregarLog();
}
async function vigiarTema() {
  if (S.prefs.tema !== "auto") return;
  const t = await api.tema_sistema();
  if (t !== S.prefs.tema_sistema) { S.prefs.tema_sistema = t; aplicarTema(); }
}

async function iniciar() {
  api = window.pywebview.api;
  S.prefs = await api.preferencias();
  S.p.pasta = S.prefs.pasta;
  aplicarTema();
  $("#versao").textContent = S.prefs.versao;
  [S.bases, S.ufs] = await Promise.all([api.bases(), api.ufs()]);
  await carregarFormulario();
  S.opcoesInfo = await api.info_opcoes();
  await atualizarColetas();
  S.carregando = false;
  ir("painel");
  agendarEstimativa();
  setInterval(atualizarColetas, 2000);
  setInterval(vigiarTema, 5000);
  setInterval(async () => { if (S.view === "config" && S.opcoesInfo?.ativo) { S.opcoesInfo = await api.info_opcoes(); render(); } }, 2000);
}
document.querySelectorAll("svg[data-icone]").forEach((s) => { s.outerHTML = icone(s.dataset.icone); });
if (window.pywebview?.api) iniciar(); else window.addEventListener("pywebviewready", iniciar);
