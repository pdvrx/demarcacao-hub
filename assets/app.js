/* Interface do site: mapa, filtros, lista, painel de detalhe e páginas. Lógica pura em logic.js. */
(function () {
  "use strict";
  const H = window.Hub;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = H.esc;
  const mobileMQ = window.matchMedia("(max-width:900px)");
  const isMobile = () => mobileMQ.matches;

  const S = { meta: null, resumo: null, indice: [], byId: new Map(), f: H.novosFiltros(), sel: null, shown: 80,
    fichas: new Map(), hasUF: false, map: null, mapReady: false, view: "mapa", results: [] };

  const J = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u + " → HTTP " + r.status); return r.json(); });
  const opt = (u) => J(u).catch(() => null);

  // =====================================================================  inicialização
  async function boot() {
    try {
      const [meta, resumo, indice, terras, centros, ufs] = await Promise.all([
        J("data/meta.json"), J("data/resumo.json"), J("data/indice.json"),
        J("data/terras.geojson"), J("data/centroides.geojson"), opt("data/ufs.geojson")]);
      S.meta = meta; S.resumo = resumo; S.hasUF = !!ufs;
      S.indice = H.prepararIndice(indice);
      indice.forEach((t) => S.byId.set(t.id, t));
      initChrome();
      initUI();
      initPages();
      initMap(terras, centros, ufs);
    } catch (e) {
      showError(e);
    }
  }

  function showError(e) {
    console.error(e);
    $("#loading").innerHTML = '<div class="errbox"><b>Não foi possível carregar os dados.</b><p>Abra o site por um servidor local ' +
      '(<code>python -m http.server 8000 -d site</code> e depois <code>http://localhost:8000</code>) e confirme que ' +
      '<code>python -m demarcacao update</code> foi executado.</p><p class="small muted">' + esc(e && e.message) + "</p></div>";
  }

  function initChrome() {
    const m = S.meta;
    $("#brand-t").textContent = m.titulo || "Demarcação em Dados";
    $("#brand-s").textContent = m.subtitulo || "";
    document.title = m.titulo || document.title;
    const v = $("#ver");
    v.textContent = "v" + m.versao + (m.ultima_observacao ? " · dados de " + H.fmtData(m.ultima_observacao) : "");
    v.hidden = false;
    $$("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if ($("#side").classList.contains("open")) $("#side").classList.remove("open");
      else if (S.sel) closePanel();
    });
  }

  // =====================================================================  filtros e lista
  function initUI() {
    const r = S.resumo, pg = r.por_precisao_geom || {};
    const aprox = (pg.municipio || 0) + (pg.uf || 0);
    $("#stats").innerHTML = [
      [r.total, "terras na base"], [pg.poligono || 0, "com limite oficial"],
      [aprox, "localização aproximada"], [r.divergencias_de_fase || 0, "fontes divergem"],
    ].map(([n, l]) => '<div class="stat"><b>' + n.toLocaleString("pt-BR") + "</b><span>" + l + "</span></div>").join("");

    const ufSel = $("#uf");
    Object.keys(r.por_uf || {}).sort().forEach((u) => {
      const o = document.createElement("option");
      o.value = u; o.textContent = u + " (" + r.por_uf[u] + ")";
      ufSel.appendChild(o);
    });

    $("#q").addEventListener("input", (e) => { S.f.q = e.target.value; $("#q-x").hidden = !S.f.q; onFilters(); });
    $("#q-x").addEventListener("click", () => { S.f.q = ""; $("#q").value = ""; $("#q-x").hidden = true; onFilters(); $("#q").focus(); });
    ufSel.addEventListener("change", (e) => { S.f.uf = e.target.value; onFilters(); });
    $("#f-poly").addEventListener("change", (e) => { S.f.soPoligono = e.target.checked; onFilters(); });
    $("#f-div").addEventListener("change", (e) => { S.f.divergentes = e.target.checked; onFilters(); });
    $("#clear-fases").addEventListener("click", () => { S.f.fases.clear(); onFilters(); });
    $("#clear-all").addEventListener("click", () => {
      S.f = H.novosFiltros();
      $("#q").value = ""; $("#q-x").hidden = true; ufSel.value = "";
      $("#f-poly").checked = false; $("#f-div").checked = false;
      onFilters();
    });
    $("#fase-chips").addEventListener("click", (e) => {
      const b = e.target.closest("[data-fase]"); if (!b) return;
      const id = b.dataset.fase;
      S.f.fases.has(id) ? S.f.fases.delete(id) : S.f.fases.add(id);
      onFilters();
    });
    $("#list").addEventListener("click", (e) => {
      if (e.target.closest(".more")) { S.shown += 120; renderList(); return; }
      const b = e.target.closest("[data-id]"); if (b) select(b.dataset.id);
    });
    $("#fab").addEventListener("click", () => $("#side").classList.toggle("open"));
    renderChips(); renderList();
  }

  function filtrosAtivos() {
    const f = S.f; return f.fases.size || f.uf || f.soPoligono || f.divergentes || f.q;
  }

  function onFilters() {
    S.shown = 80;
    renderChips(); renderList(); applyMapFilters();
    $("#clear-fases").hidden = !S.f.fases.size;
    $("#clear-all").hidden = !filtrosAtivos();
  }

  function renderChips() {
    const c = H.contagemPorFase(S.indice, S.f);
    $("#fase-chips").innerHTML = H.TODAS.filter((f) => c[f.id] || S.f.fases.has(f.id)).map((f) =>
      '<button class="chip' + (c[f.id] ? "" : " zero") + '" style="--c:' + f.cor + '" data-fase="' + f.id +
      '" aria-pressed="' + S.f.fases.has(f.id) + '" title="' + esc(f.def) + '"><i></i>' + esc(f.nome) +
      " <em>" + (c[f.id] || 0) + "</em></button>").join("");
  }

  function renderList() {
    const res = (S.results = H.buscar(S.indice, S.f));
    $("#count").textContent = res.length === S.indice.length ? res.length.toLocaleString("pt-BR") + " terras"
      : res.length.toLocaleString("pt-BR") + " de " + S.indice.length.toLocaleString("pt-BR") + " terras";
    const ul = $("#list");
    if (!res.length) { ul.innerHTML = '<li class="empty">Nenhuma terra com esses filtros.</li>'; return; }
    const part = res.slice(0, S.shown);
    ul.innerHTML = part.map((t) => {
      const fase = H.FASE[t.fase] || { cor: "#555", nome: t.fase };
      const sub = [fase.nome, t.ufs.split(";").filter(Boolean).join(", "), t.povos ? t.povos.slice(0, 38) : ""].filter(Boolean).join(" · ");
      return '<li><button data-id="' + t.id + '"' + (t.id === S.sel ? ' aria-current="true"' : "") + '><i class="' +
        (t.precisao === "poligono" ? "" : "ring") + '" style="background:' + fase.cor + ";--c:" + fase.cor + '"></i><div><b>' +
        esc(t.nome) + "</b><span>" + esc(sub) + "</span></div></button></li>";
    }).join("") + (res.length > part.length ? '<li class="more"><button class="btn more">Mostrar mais (' + (res.length - part.length) + ")</button></li>" : "");
  }

  function markList() {
    $$("#list [data-id]").forEach((b) => {
      if (b.dataset.id === S.sel) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });
  }

  // =====================================================================  mapa
  const HIT = ["poly-fill", "centros", "approx-mun", "approx-uf"];
  let hoverId = null, popup = null;

  function initMap(terras, centros, ufs) {
    const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    let map;
    try {
      map = new maplibregl.Map({
        container: "map", attributionControl: false, minZoom: 2.5, maxZoom: 15,
        bounds: [[-74.5, -34.5], [-33.5, 5.8]], fitBoundsOptions: { padding: 24 },
        style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": css("--mapbg") } }] },
      });
    } catch (e) { showError(new Error("Seu navegador não conseguiu iniciar o mapa (WebGL).")); return; }
    S.map = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: "metric" }), "bottom-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Limites: Funai · UF: IBGE" }), "bottom-right");

    map.on("load", () => {
      const cor = ["match", ["get", "fase"]].concat(H.TODAS.flatMap((f) => [f.id, f.cor]), ["#4b5563"]);
      const poly = ["==", ["get", "precisao_geom"], "poligono"];
      const hov = ["boolean", ["feature-state", "hover"], false];

      map.addSource("osm", { type: "raster", tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"] });
      map.addLayer({ id: "osm", type: "raster", source: "osm", layout: { visibility: "none" } });
      if (ufs) {
        map.addSource("ufs", { type: "geojson", data: ufs });
        map.addLayer({ id: "ufs-fill", type: "fill", source: "ufs", paint: { "fill-color": css("--land") } });
        map.addLayer({ id: "ufs-line", type: "line", source: "ufs", paint: { "line-color": css("--uf-line"), "line-width": 0.7 } });
      }
      map.addSource("terras", { type: "geojson", data: terras, promoteId: "terra_id" });
      map.addSource("centros", { type: "geojson", data: centros, promoteId: "terra_id" });

      map.addLayer({ id: "poly-fill", type: "fill", source: "terras", filter: poly,
        paint: { "fill-color": cor, "fill-opacity": ["case", hov, 0.88, 0.62] } });
      map.addLayer({ id: "poly-line", type: "line", source: "terras", filter: poly,
        paint: { "line-color": cor, "line-width": ["case", hov, 2.4, 1] } });
      map.addLayer({ id: "centros", type: "circle", source: "centros", maxzoom: 8.5, paint: {
        "circle-color": cor, "circle-stroke-color": "#ffffff", "circle-stroke-width": 0.7,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 2.6, 6, 4.8],
        "circle-opacity": ["interpolate", ["linear"], ["zoom"], 6.5, 0.95, 8.5, 0],
        "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 6.5, 0.95, 8.5, 0] } });
      map.addLayer({ id: "approx-uf", type: "circle", source: "terras", filter: ["==", ["get", "precisao_geom"], "uf"], paint: {
        "circle-color": cor, "circle-opacity": 0.1, "circle-stroke-color": cor, "circle-stroke-width": 1.3, "circle-stroke-opacity": 0.7,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 8, 8, 18] } });
      map.addLayer({ id: "approx-mun", type: "circle", source: "terras", filter: ["==", ["get", "precisao_geom"], "municipio"], paint: {
        "circle-color": cor, "circle-opacity": 0.28, "circle-stroke-color": cor, "circle-stroke-width": 1.8,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 4, 8, 9] } });
      const none = ["==", ["get", "terra_id"], ""];
      map.addLayer({ id: "sel-poly", type: "line", source: "terras", filter: ["all", poly, none],
        paint: { "line-color": "#111827", "line-width": 3 } });
      map.addLayer({ id: "sel-pt", type: "circle", source: "terras", filter: ["all", ["!=", ["get", "precisao_geom"], "poligono"], none],
        paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#111827", "circle-stroke-width": 3 } });
      map.addLayer({ id: "sel-centro", type: "circle", source: "centros", maxzoom: 8.5, filter: none,
        paint: { "circle-radius": 10, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#111827", "circle-stroke-width": 3 } });

      popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: "tip", offset: 10 });
      map.on("mousemove", onMove);
      map.on("mouseout", () => { setHover(null); popup.remove(); });
      map.on("click", (e) => {
        const fs = map.queryRenderedFeatures(e.point, { layers: HIT });
        if (fs.length) select(fs[0].properties.terra_id, { fit: false });
      });

      const osm = $("#osm");
      osm.addEventListener("change", () => setOSM(osm.checked));
      if (!ufs) { osm.checked = true; osm.disabled = true; setOSM(true); }

      applyMapFilters(); updateSelectedLayers();
      $("#loading").classList.add("off");
      S.mapReady = true;
      route();
    });
  }

  function setOSM(on) {
    const map = S.map;
    map.setLayoutProperty("osm", "visibility", on ? "visible" : "none");
    if (S.hasUF) map.setPaintProperty("ufs-fill", "fill-opacity", on ? 0 : 1);
  }

  function applyMapFilters() {
    if (!S.mapReady) return;
    const e = H.exprMapa(S.f), map = S.map;
    const base = { "poly-fill": ["==", ["get", "precisao_geom"], "poligono"], "poly-line": ["==", ["get", "precisao_geom"], "poligono"],
      "approx-uf": ["==", ["get", "precisao_geom"], "uf"], "approx-mun": ["==", ["get", "precisao_geom"], "municipio"], centros: null };
    Object.keys(base).forEach((id) => map.setFilter(id, base[id] ? ["all", base[id], e] : e));
  }

  function updateSelectedLayers() {
    if (!S.mapReady) return;
    const map = S.map, id = S.sel || "";
    const eq = ["==", ["get", "terra_id"], id];
    map.setFilter("sel-poly", ["all", ["==", ["get", "precisao_geom"], "poligono"], eq]);
    map.setFilter("sel-pt", ["all", ["!=", ["get", "precisao_geom"], "poligono"], eq]);
    map.setFilter("sel-centro", eq);
  }

  function onMove(e) {
    const map = S.map, fs = map.queryRenderedFeatures(e.point, { layers: HIT });
    map.getCanvas().style.cursor = fs.length ? "pointer" : "";
    if (!fs.length) { setHover(null); popup.remove(); return; }
    const p = fs[0].properties, fase = H.FASE[p.fase];
    setHover(fs[0].layer.id === "poly-fill" ? p.terra_id : null);
    popup.setLngLat(e.lngLat).setHTML("<b>" + esc(p.nome) + "</b><br><span style='color:#5d6762'>" + esc(fase ? fase.nome : p.fase) + "</span>").addTo(map);
  }

  function setHover(id) {
    if (id === hoverId) return;
    const map = S.map;
    if (hoverId) map.setFeatureState({ source: "terras", id: hoverId }, { hover: false });
    hoverId = id;
    if (id) map.setFeatureState({ source: "terras", id }, { hover: true });
  }

  function pad() {
    return isMobile() ? { top: 70, left: 40, right: 40, bottom: Math.round(window.innerHeight * 0.55) }
      : { top: 70, left: 70, bottom: 70, right: 470 };
  }

  function fitTo(t) {
    if (!S.mapReady || !t || !t.bbox) return;
    const [x0, y0, x1, y1] = t.bbox;
    if (Math.abs(x1 - x0) < 1e-6 && Math.abs(y1 - y0) < 1e-6) {
      S.map.flyTo({ center: [x0, y0], zoom: t.precisao === "uf" ? 5.2 : 8.2, padding: pad(), duration: 900 });
    } else {
      S.map.fitBounds([[x0, y0], [x1, y1]], { padding: pad(), maxZoom: t.precisao === "poligono" ? 11 : 8, duration: 900 });
    }
  }

  // =====================================================================  seleção e rotas
  async function select(id, opts) {
    const o = Object.assign({ fit: true, push: true }, opts), t = S.byId.get(id);
    if (!t) return;
    S.sel = id;
    updateSelectedLayers(); markList();
    $("#detail").classList.add("open");
    if (isMobile()) $("#side").classList.remove("open");
    if (o.push && location.hash.slice(1) !== id) history.pushState(null, "", "#" + id);
    if (o.fit) fitTo(t);
    renderSkeleton(t);
    document.title = t.nome + " — " + (S.meta.titulo || "");
    try {
      let f = S.fichas.get(id);
      if (!f) { f = await J("data/terras/" + id + ".json"); S.fichas.set(id, f); }
      if (S.sel === id) renderDetail(f);
    } catch (e) {
      if (S.sel === id) $("#detail").innerHTML = '<div class="d-head"><button class="d-close" id="d-close" aria-label="Fechar">×</button>' +
        "<h2>" + esc(t.nome) + '</h2></div><div class="d-scroll"><p class="note warn">Não foi possível carregar a ficha desta terra.</p></div>';
      bindClose();
    }
  }

  function closePanel(skipHistory) {
    S.sel = null;
    $("#detail").classList.remove("open");
    updateSelectedLayers(); markList();
    document.title = S.meta.titulo || document.title;
    if (!skipHistory && location.hash) history.pushState(null, "", location.pathname + location.search);
  }

  function go(v) {
    if (v === "mapa") { if (location.hash) history.pushState(null, "", location.pathname + location.search); }
    else location.hash = v;
    route();
  }

  function setView(v) {
    S.view = v;
    ["mapa", "dados", "metodologia", "sobre"].forEach((n) => { $("#v-" + n).hidden = n !== v; });
    $$("[data-go]").forEach((b) => { if (b.dataset.go === v) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
    if (v === "mapa" && S.map) S.map.resize();
    window.scrollTo(0, 0);
  }

  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    if (/^TI\d+$/.test(h)) { setView("mapa"); if (S.byId.has(h) && S.sel !== h) select(h, { push: false }); }
    else if (["dados", "metodologia", "sobre"].includes(h)) setView(h);
    else { setView("mapa"); if (S.sel) closePanel(true); }
  }
  window.addEventListener("hashchange", () => { if (S.meta) route(); });

  // =====================================================================  painel de detalhe
  function bindClose() { const b = $("#d-close"); if (b) b.addEventListener("click", () => closePanel()); }

  function renderSkeleton(t) {
    const fase = H.FASE[t.fase] || { nome: t.fase, cor: "#555" };
    $("#detail").innerHTML = '<div class="d-head"><button class="d-close" id="d-close" aria-label="Fechar">×</button><div class="d-kicker">' +
      esc(t.id) + "</div><h2>" + esc(t.nome) + '</h2><div class="badges"><span class="badge phase" style="--c:' + fase.cor + '">' +
      esc(fase.nome) + '</span></div></div><div class="d-scroll"><p class="muted">Carregando…</p></div>';
    bindClose();
  }

  const ROT = { ato: "Ato", etapa: "Etapa do processo", processo_funai: "Processo na Funai", processos_judiciais: "Processos judiciais",
    atuacao_administrativa: "Atuação administrativa", situacao_revisao: "Situação da revisão", sobreposicoes: "Sobreposições",
    observacoes: "Observações", reestudo: "Reestudo" };

  function longText(v) {
    const s = String(v);
    return s.length > 220 ? '<details class="long"><summary>' + esc(s.slice(0, 160)) + '… ver tudo</summary><div class="pre">' + esc(s) + "</div></details>"
      : '<span class="pre">' + esc(s) + "</span>";
  }

  function secFase(f) {
    const fase = H.FASE[f.fase] || { nome: f.fase, cor: "#555", def: "" };
    const i = H.FASES.findIndex((x) => x.id === f.fase);
    if (i < 0) return '<div class="d-sec"><h3>Fase do processo</h3><p class="note">' + esc(fase.def || "") + "</p></div>";
    return '<div class="d-sec"><h3>Fase do processo</h3><ol class="steps" aria-label="Etapas do procedimento">' + H.FASES.map((x, k) =>
      '<li class="' + (k < i ? "done" : k === i ? "cur" : "") + '" style="--c:' + x.cor + '"' + (k === i ? ' aria-current="step"' : "") + ">" + esc(x.nome) + "</li>").join("") +
      '</ol><p class="stepdef"><b>' + esc(fase.nome) + ".</b> " + esc(fase.def) + "</p></div>";
  }

  function secFatos(f) {
    const jur = f.juridico || [], pick = (k) => { const j = jur.find((x) => x[k]); return j ? j[k] : ""; };
    const um = f.ufs.split(";").filter(Boolean).length === 1;
    const muns = (f.municipios || "").split(";").map((s) => s.trim()).filter(Boolean).map((s) => (um ? s.replace(/\/[A-Z]{2}$/, "") : s)).join(", ");
    const rows = [["Estado(s)", f.ufs.split(";").filter(Boolean).join(", ")], ["Municípios", muns], ["Povo(s)", f.povos], ["Área", H.fmtHa(f.area_ha)],
      ["Modalidade", H.MODALIDADES[f.modalidade] || ""], ["População", pick("populacao")], ["Coord. Regional", pick("cr")]].filter((r) => r[1]);
    const dtf = jur.find((x) => x.data_fonte);
    let h = '<div class="d-sec"><h3>Identificação</h3><dl class="facts">' + rows.map((r) => "<dt>" + r[0] + "</dt><dd>" + esc(r[1]) + "</dd>").join("") +
      (dtf ? "<dt>Atualizado na fonte</dt><dd>" + esc(dtf.data_fonte) + " <small>(" + esc(H.fonteNome(dtf.fonte)) + ")</small></dd>" : "") + "</dl>";
    if (f.precisao_geom !== "poligono") h += '<p class="note" style="margin-top:12px">' + (f.sensivel
      ? "Por proteção, a localização desta terra é exibida apenas no nível do estado."
      : "A posição no mapa é <b>aproximada</b> (" + (f.precisao_geom === "uf" ? "estado" : "município") + "): esta terra ainda não tem polígono publicado e o ponto não indica seu limite.") + "</p>";
    return h + "</div>";
  }

  function secDiverg(f) {
    if (!f.divergencia_fase) return "";
    return '<div class="d-sec"><p class="note warn"><b>As fontes registram fases diferentes.</b> Isso pode refletir defasagem de atualização ou critérios distintos, e não indica, por si só, erro de nenhuma delas. Veja a comparação em “Fontes”. A fase exibida segue a fonte de maior prioridade.</p></div>';
  }

  function secJuridico(f) {
    const rows = [];
    (f.juridico || []).forEach((j) => {
      const tag = ' <small>(' + esc(H.fonteNome(j.fonte)) + ")</small>";
      Object.keys(ROT).forEach((k) => {
        if (!j[k]) return;
        let v = longText(j[k]);
        if (k === "ato" && j.ato_data) v += ' <small class="muted">· data inferida do texto: ' + esc(H.fmtData(j.ato_data)) + "</small>";
        rows.push("<dt>" + ROT[k] + "</dt><dd>" + v + tag + "</dd>");
      });
    });
    return '<div class="d-sec"><h3>Situação jurídica e administrativa</h3>' +
      (rows.length ? '<dl class="facts">' + rows.join("") + "</dl>" : '<p class="muted small">Nenhum dado jurídico nas fontes carregadas.</p>') + "</div>";
  }

  function secTempo(f) {
    const it = H.linhaDoTempo(f);
    let h = '<div class="d-sec"><h3>Linha do tempo <small>atos oficiais e mudanças observadas</small></h3>';
    if (!it.length) {
      h += '<p class="muted small">Ainda sem registros. O histórico passa a acumular a cada atualização dos dados' +
        (S.meta.ultima_observacao ? " (primeira observação em " + esc(H.fmtData(S.meta.ultima_observacao)) + ")" : "") + ".</p>";
    } else {
      h += '<ol class="tl">' + it.map((x) => {
        const quem = x.tipo === "obs" ? "Observado pelo hub" : "Ato oficial";
        const meta = [x.desc, x.fonte, x.inferida ? "data inferida do texto da fonte" : ""].filter(Boolean).map(esc).join(" · ");
        return '<li class="' + (x.tipo === "obs" ? "obs" : "") + '"><div class="when">' + esc(H.fmtData(x.data)) + " · " + quem + '</div><div class="what">' +
          esc(x.titulo) + "</div>" + (meta ? '<div class="meta">' + meta + "</div>" : "") +
          (x.url ? '<div class="meta"><a href="' + esc(x.url) + '" target="_blank" rel="noopener">fonte</a></div>' : "") + "</li>";
      }).join("") + "</ol>";
    }
    return h + "</div>";
  }

  function secContexto(f) {
    const q = encodeURIComponent('"' + f.nome + '" terra indígena');
    let h = '<div class="d-sec"><h3>Contexto e notícias</h3>';
    if (f.noticias && f.noticias.length) {
      h += '<ul class="tl" style="list-style:none">' + f.noticias.map((n) => '<li><div class="when">' + esc(H.fmtData(n.data)) + " · " + esc(n.fonte || "") +
        '</div><a href="' + esc(H.safeUrl(n.url)) + '" target="_blank" rel="noopener">' + esc(n.titulo) + "</a></li>").join("") + "</ul>";
    } else {
      h += '<div class="soon">Contexto histórico e notícias desta terra entram aqui nas próximas etapas.<br>' +
        '<a href="https://news.google.com/search?q=' + q + '&hl=pt-BR&gl=BR&ceid=BR:pt-419" target="_blank" rel="noopener">Buscar notícias (site externo)</a></div>';
    }
    return h + "</div>";
  }

  function secFontes(f) {
    const fs = f.fontes || [];
    if (!fs.length) return "";
    return '<div class="d-sec"><h3>Fontes</h3><table class="src"><thead><tr><th>Fonte</th><th>Nome na fonte</th><th>Fase na fonte</th></tr></thead><tbody>' + fs.map((r) => {
      const diff = f.divergencia_fase && r.fase && r.fase !== f.fase;
      return '<tr class="' + (diff ? "diff" : "") + '"><td>' + esc(H.fonteNome(r.fonte)) + "</td><td>" + esc(r.nome_original) + "</td><td>" +
        esc(r.fase ? H.faseNome(r.fase) : "—") + (r.fase_origem ? '<br><small class="muted">“' + esc(r.fase_origem) + "”</small>" : "") + "</td></tr>";
    }).join("") + "</tbody></table></div>";
  }

  function renderDetail(f) {
    const fase = H.FASE[f.fase] || { nome: f.fase, cor: "#555" }, mod = H.MODALIDADES[f.modalidade] || "";
    const url = location.origin + location.pathname + "#" + f.terra_id;
    const cite = H.citacao(f, S.meta, url, new Date().toLocaleDateString("pt-BR"));
    $("#detail").innerHTML =
      '<div class="d-head"><button class="d-close" id="d-close" aria-label="Fechar painel">×</button><div class="d-kicker">' + esc(f.terra_id) + (mod ? " · " + esc(mod) : "") +
      "</div><h2>" + esc(f.nome) + '</h2><div class="badges"><span class="badge phase" style="--c:' + fase.cor + '">' + esc(fase.nome) + '</span><span class="badge">' +
      esc(H.PRECISAO[f.precisao_geom] || "") + "</span>" + (f.divergencia_fase ? '<span class="badge warn">Fontes divergem</span>' : "") + "</div></div>" +
      '<div class="d-scroll">' + secFase(f) + secDiverg(f) + secFatos(f) + secJuridico(f) + secTempo(f) + secContexto(f) + secFontes(f) +
      '<div class="d-actions"><button class="btn primary" id="b-link">Copiar link</button><button class="btn" id="b-cite">Como citar</button>' +
      '<a class="btn" href="data/terras/' + esc(f.terra_id) + '.json" target="_blank" rel="noopener">Ficha em JSON</a></div>' +
      '<div class="cite" id="cite">' + esc(cite) + "</div></div>";
    bindClose();
    $("#b-link").addEventListener("click", (e) => copy(url, e.target, "Link copiado ✓"));
    $("#b-cite").addEventListener("click", (e) => {
      const box = $("#cite"); box.classList.toggle("show");
      if (box.classList.contains("show")) copy(cite, e.target, "Citação copiada ✓");
    });
    $(".d-scroll").scrollTop = 0;
  }

  function copy(text, btn, okLabel) {
    const old = btn.textContent;
    const done = () => { btn.textContent = okLabel; setTimeout(() => { btn.textContent = old; }, 1600); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => window.prompt("Copie:", text));
    else window.prompt("Copie:", text);
  }

  // =====================================================================  páginas de conteúdo
  function initPages() {
    const m = S.meta, base = location.origin + location.pathname;
    $("#d-obs").textContent = m.ultima_observacao ? H.fmtData(m.ultima_observacao) : "—";
    $("#d-ver").textContent = m.versao;
    $("#d-cite").textContent = (m.titulo || "Demarcação em Dados") + ". Terras indígenas: fases, atos e histórico. Versão " + m.versao +
      (m.ultima_observacao ? ", dados observados em " + H.fmtData(m.ultima_observacao) : "") + ". Disponível em: " + base + ".";
    $("#s-ver").textContent = m.versao;
    $("#s-obs").textContent = m.ultima_observacao ? H.fmtData(m.ultima_observacao) : "—";
    $("#s-gen").textContent = m.gerado_em ? H.fmtData(String(m.gerado_em).slice(0, 10)) : "—";

    $("#met-fases").innerHTML = "<thead><tr><th>Fase</th><th>O que significa</th></tr></thead><tbody>" + H.TODAS.map((f, k) =>
      '<tr><td style="white-space:nowrap"><span class="dot" style="background:' + f.cor + '"></span>' + esc(f.nome) + "</td><td>" + esc(f.def) +
      (k === H.FASES.length ? "" : "") + "</td></tr>").join("") + "</tbody>";

    const fo = m.fontes || {}, ks = Object.keys(fo);
    $("#met-fontes").innerHTML = ks.length
      ? "<thead><tr><th>Fonte</th><th>Arquivo</th><th>Arquivo modificado em</th><th>Registros</th><th>SHA-256</th></tr></thead><tbody>" +
        ks.map((k) => "<tr><td>" + esc(H.fonteNome(k)) + "</td><td>" + esc(fo[k].arquivo) + "</td><td>" + esc(H.fmtData(String(fo[k].modificado_em || "").slice(0, 10))) +
          "</td><td>" + esc(fo[k].n_registros) + '</td><td class="mono" title="' + esc(fo[k].sha256) + '">' + esc(String(fo[k].sha256 || "").slice(0, 12)) + "…</td></tr>").join("") + "</tbody>"
      : "<tbody><tr><td>Sem informação de fontes nesta versão.</td></tr></tbody>";
  }

  boot();
})();
