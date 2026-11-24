// Rode com:  node --test site/tests/logic.test.js
const test = require("node:test");
const assert = require("node:assert");
const H = require("../assets/logic.js");

const indice = H.prepararIndice([
  { id: "TI0001", nome: "Xukuru de Cimbres", ufs: "PE", fase: "homologada", povos: "Xukuru", municipios: "Pesqueira/PE", precisao: "poligono", divergente: false },
  { id: "TI0002", nome: "Zo’é", ufs: "PA", fase: "regularizada", povos: "Zo’é", municipios: "Óbidos/PA", precisao: "poligono", divergente: true },
  { id: "TI0003", nome: "Gama", ufs: "MG;BA", fase: "sem_providencia", povos: "", municipios: "Viçosa/MG", precisao: "municipio", divergente: false },
]);

test("busca ignora acento, apóstrofo e caixa; nome que começa com o termo vem primeiro", () => {
  const f = H.novosFiltros();
  f.q = "zoe"; assert.deepStrictEqual(H.buscar(indice, f).map((t) => t.id), ["TI0002"]);
  f.q = "VICOSA"; assert.deepStrictEqual(H.buscar(indice, f).map((t) => t.id), ["TI0003"]);
  f.q = "xukuru"; assert.strictEqual(H.buscar(indice, f)[0].id, "TI0001");
  f.q = "nada disso"; assert.strictEqual(H.buscar(indice, f).length, 0);
});

test("filtros: fase, UF (inclusive terra em dois estados), polígono, divergência", () => {
  const f = H.novosFiltros();
  f.uf = "BA"; assert.deepStrictEqual(H.buscar(indice, f).map((t) => t.id), ["TI0003"]);
  f.uf = ""; f.soPoligono = true; assert.strictEqual(H.buscar(indice, f).length, 2);
  f.divergentes = true; assert.deepStrictEqual(H.buscar(indice, f).map((t) => t.id), ["TI0002"]);
  const g = H.novosFiltros(); g.fases.add("sem_providencia");
  assert.deepStrictEqual(H.buscar(indice, g).map((t) => t.id), ["TI0003"]);
});

test("contagem por fase ignora o próprio filtro de fase", () => {
  const f = H.novosFiltros(); f.fases.add("homologada");
  assert.deepStrictEqual(H.contagemPorFase(indice, f), { homologada: 1, regularizada: 1, sem_providencia: 1 });
});

test("expressão do mapa tem a mesma semântica do filtro", () => {
  const f = H.novosFiltros();
  assert.deepStrictEqual(H.exprMapa(f), ["all"]);
  f.fases.add("declarada"); f.uf = "MG"; f.soPoligono = true; f.divergentes = true;
  const e = H.exprMapa(f);
  assert.strictEqual(e.length, 5);
  assert.deepStrictEqual(e[1], ["in", ["get", "fase"], ["literal", ["declarada"]]]);
  assert.deepStrictEqual(e[2], ["in", "MG", ["get", "ufs"]]);
});

test("linha do tempo mistura atos e observações, mais recente primeiro, sem duplicar", () => {
  const t = H.linhaDoTempo({
    marcos: [{ data_ato: "1996-01-05", tipo_ato: "Decreto", numero_ato: "s/nº", fonte_url: "https://x.gov.br", descricao: "d" }],
    juridico: [{ fonte: "mpf", ato: "Decreto s/nº de 05/01/96", ato_data: "1996-01-05" }, { fonte: "mpf", ato: "Decreto s/nº de 05/01/96", ato_data: "1996-01-05" }],
    historico: [{ data_observacao: "2026-11-08", tipo: "mudanca", campo: "fase", valor_anterior: "declarada", valor_novo: "homologada" }],
  });
  assert.strictEqual(t.length, 3);
  assert.strictEqual(t[0].tipo, "obs");
  assert.strictEqual(t[0].titulo, "Fase: Declarada → Homologada");
  assert.ok(t.find((x) => x.tipo === "ato_fonte").inferida);
});

test("segurança: HTML escapado e só links http(s)", () => {
  assert.strictEqual(H.esc('<img src=x onerror="a">'), "&lt;img src=x onerror=&quot;a&quot;&gt;");
  assert.strictEqual(H.safeUrl("javascript:alert(1)"), "");
  assert.strictEqual(H.safeUrl("https://a.b"), "https://a.b");
});

test("formatação e citação", () => {
  assert.strictEqual(H.fmtData("2026-11-23"), "23/11/2026");
  assert.strictEqual(H.fmtData("2023-09"), "09/2023");
  assert.strictEqual(H.fmtHa("263130"), "263.130 ha");
  const c = H.citacao({ nome: "Gama", terra_id: "TI0003", fontes: [{ fonte: "funai" }, { fonte: "mpf" }] },
    { titulo: "Demarcação em Dados", versao: "0.1.0", ultima_observacao: "2026-11-23" }, "http://x/#TI0003", "24/11/2026");
  assert.match(c, /Gama \(TI0003\)\. Versão 0\.1\.0, dados observados em 23\/11\/2026\. Fontes: Funai, MPF\./);
});
