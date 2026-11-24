/* Lógica pura do site (sem DOM, sem mapa): fases, filtros, busca, linha do tempo, citação.
   Funciona no navegador (window.Hub) e no Node (module.exports), para poder ser testada. */
(function (root) {
  "use strict";

  // Ordem = avanço do procedimento administrativo (Decreto 1.775/1996).
  const FASES = [
    { id: "sem_providencia", nome: "Sem providência", cor: "#8b95a1",
      def: "Terra reivindicada; o procedimento administrativo ainda não foi iniciado." },
    { id: "em_estudo", nome: "Em estudo", cor: "#e0a62a",
      def: "Grupo técnico realiza os estudos de identificação e delimitação." },
    { id: "delimitada", nome: "Delimitada", cor: "#ee7d2c",
      def: "Relatório circunstanciado de identificação aprovado e publicado pela Funai." },
    { id: "declarada", nome: "Declarada", cor: "#d6432d",
      def: "Portaria declaratória do Ministro da Justiça reconhece os limites." },
    { id: "homologada", nome: "Homologada", cor: "#7a4cb5",
      def: "Decreto presidencial homologa a demarcação." },
    { id: "regularizada", nome: "Regularizada", cor: "#1c8a6a",
      def: "Registrada em cartório e na Secretaria do Patrimônio da União." },
  ];
  const ESPECIAIS = [
    { id: "reserva_em_constituicao", nome: "Encaminhada como Reserva", cor: "#2e7fb8",
      def: "Terra encaminhada para constituição de Reserva Indígena (rito distinto; fora da sequência acima)." },
    { id: "restricao_de_uso", nome: "Restrição de ingresso", cor: "#7b5a43",
      def: "Área com restrição de ingresso/uso (fora da sequência acima)." },
    { id: "indefinida", nome: "Fase não identificada", cor: "#4b5563",
      def: "O rótulo de fase da fonte ainda não foi mapeado." },
  ];
  const TODAS = FASES.concat(ESPECIAIS);
  const FASE = Object.fromEntries(TODAS.map((f) => [f.id, f]));

  const MODALIDADES = {
    tradicionalmente_ocupada: "Tradicionalmente ocupada", reserva_indigena: "Reserva indígena",
    dominial: "Dominial indígena", interditada: "Interditada", nao_informada: "",
  };
  const FONTES = { funai: "Funai", mpf: "MPF", cimi: "Cimi", isa: "ISA" };
  const CAMPOS = { fase: "Fase", nome: "Nome", modalidade: "Modalidade", precisao_geom: "Localização",
    area_ha: "Área (ha)", ufs: "UF", divergencia_fase: "Divergência entre fontes" };
  const PRECISAO = { poligono: "Limite oficial", municipio: "Localização aproximada (município)",
    uf: "Localização aproximada (UF)", nenhuma: "Sem localização" };

  const norm = (s) => String(s == null ? "" : s).normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[\u2019'`´]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

  const faseNome = (id) => (FASE[id] ? FASE[id].nome : id || "");
  const fonteNome = (f) => FONTES[f] || String(f || "").toUpperCase();
  const fmtHa = (v) => {
    const n = parseFloat(v);
    return isFinite(n) ? n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " ha" : "";
  };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");

  // ------------------------------------------------------------------ filtros
  function novosFiltros() {
    return { fases: new Set(), uf: "", soPoligono: false, divergentes: false, q: "" };
  }
  function passa(t, f, ignorarFase) {
    if (!ignorarFase && f.fases.size && !f.fases.has(t.fase)) return false;
    if (f.uf && !String(t.ufs).split(";").includes(f.uf)) return false;
    if (f.soPoligono && t.precisao !== "poligono") return false;
    if (f.divergentes && !t.divergente) return false;
    return true;
  }
  /** Expressão de filtro do MapLibre equivalente a `passa` (usa as propriedades das feições). */
  function exprMapa(f) {
    const c = ["all"];
    if (f.fases.size) c.push(["in", ["get", "fase"], ["literal", Array.from(f.fases)]]);
    if (f.uf) c.push(["in", f.uf, ["get", "ufs"]]);
    if (f.soPoligono) c.push(["==", ["get", "precisao_geom"], "poligono"]);
    if (f.divergentes) c.push(["==", ["get", "divergencia_fase"], true]);
    return c;
  }
  function prepararIndice(indice) {
    indice.forEach((t) => { t._s = norm([t.nome, t.povos, t.municipios, t.id].join(" ")); });
    return indice;
  }
  function buscar(indice, f) {
    const toks = norm(f.q).split(" ").filter(Boolean);
    const out = [];
    for (const t of indice) {
      if (!passa(t, f)) continue;
      if (toks.length && !toks.every((k) => t._s.includes(k))) continue;
      const nn = norm(t.nome);
      out.push({ t, r: toks.length && nn.startsWith(toks[0]) ? 0 : toks.length && nn.includes(toks[0]) ? 1 : 2 });
    }
    out.sort((a, b) => a.r - b.r || a.t.nome.localeCompare(b.t.nome, "pt-BR"));
    return out.map((x) => x.t);
  }
  function contagemPorFase(indice, f) {
    const c = {};
    for (const t of indice) if (passa(t, f, true)) c[t.fase] = (c[t.fase] || 0) + 1;
    return c;
  }

  // ------------------------------------------------------------------ linha do tempo
  function descreverEvento(h) {
    if (h.tipo === "nova_terra") return "Entrou na base";
    if (h.tipo === "removida_da_base") return "Saiu da base";
    if (h.tipo === "fundida_em") return "Unificada com " + h.valor_novo;
    const rot = CAMPOS[h.campo] || h.campo;
    const v = (x) => (h.campo === "fase" ? faseNome(x) : h.campo === "precisao_geom" ? (PRECISAO[x] || x) : x || "—");
    return rot + ": " + v(h.valor_anterior) + " → " + v(h.valor_novo);
  }
  /** Junta atos oficiais (curados e extraídos das fontes) e mudanças observadas pelo pipeline. */
  function linhaDoTempo(ficha) {
    const itens = [], vistos = new Set();
    const add = (it) => {
      const k = it.tipo + "|" + it.data + "|" + it.titulo;
      if (!it.data || vistos.has(k)) return;
      vistos.add(k);
      itens.push(it);
    };
    (ficha.marcos || []).forEach((m) => add({
      data: m.data_ato, tipo: "ato", titulo: [m.tipo_ato, m.numero_ato].filter(Boolean).join(" ") || "Ato oficial",
      desc: m.descricao, url: safeUrl(m.fonte_url), fonte: m.orgao }));
    (ficha.juridico || []).forEach((j) => { if (j.ato_data) add({
      data: j.ato_data, tipo: "ato_fonte", titulo: j.ato, fonte: fonteNome(j.fonte), inferida: true }); });
    (ficha.historico || []).forEach((h) => add({
      data: h.data_observacao, tipo: "obs", titulo: descreverEvento(h) }));
    itens.sort((a, b) => (a.data < b.data ? 1 : a.data > b.data ? -1 : 0));
    return itens;
  }
  const fmtData = (d) => {
    const p = String(d || "").split("-");
    if (p.length === 3) return p[2] + "/" + p[1] + "/" + p[0];
    if (p.length === 2) return p[1] + "/" + p[0];
    return d || "";
  };

  // ------------------------------------------------------------------ citação
  function citacao(ficha, meta, url, hoje) {
    const fontes = Array.from(new Set((ficha.fontes || []).map((x) => fonteNome(x.fonte)))).join(", ");
    return [
      (meta.titulo || "Demarcação em Dados") + ".",
      ficha.nome + " (" + ficha.terra_id + ").",
      "Versão " + meta.versao + (meta.ultima_observacao ? ", dados observados em " + fmtData(meta.ultima_observacao) : "") + ".",
      fontes ? "Fontes: " + fontes + "." : "",
      url ? "Disponível em: " + url + "." : "",
      hoje ? "Acesso em: " + hoje + "." : "",
    ].filter(Boolean).join(" ");
  }

  const api = { FASES, ESPECIAIS, TODAS, FASE, MODALIDADES, FONTES, PRECISAO, norm, faseNome, fonteNome, fmtHa, esc, safeUrl,
    novosFiltros, passa, exprMapa, prepararIndice, buscar, contagemPorFase, descreverEvento, linhaDoTempo, fmtData, citacao };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Hub = api;
})(typeof window !== "undefined" ? window : globalThis);
