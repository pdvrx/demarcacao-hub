"""Teste de ponta a ponta com dados sintéticos: ingest -> match -> build -> histórico -> export."""
import json

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from demarcacao import build, export, history, ingest, match, paths, validate


def _funai(proj, gamas=False, beta_fase="Declarada"):
    rows = [
        (1, "Terra Indígena Alfa", "Povo A", "Viçosa", "MG", "100,5", "Homologada", "Tradicionalmente ocupada", box(-43, -21, -42.9, -20.9)),
        (2, "Terra Indígena Beta", "Povo B", "Porto Seguro", "BA", "200", beta_fase, "Tradicionalmente ocupada", box(-39.2, -16.5, -39.1, -16.4)),
    ]
    if gamas:
        rows.append((3, "Terra Indígena Gama", "Povo G", "Viçosa", "MG", "50", "Em estudo", "Tradicionalmente ocupada", box(-42.9, -20.8, -42.8, -20.7)))
    gdf = gpd.GeoDataFrame(
        [dict(terrai_cod=r[0], terrai_nom=r[1], etnia_nome=r[2], municipio_=r[3], uf_sigla=r[4], superficie=r[5],
              fase_ti=r[6], modalidade_=r[7], geometry=r[8]) for r in rows], crs=4326)
    p = proj / "data/raw/funai/ti.gpkg"
    if p.exists():
        p.unlink()
    gdf.to_file(p, driver="GPKG")


def _mpf(proj):
    pd.DataFrame([
        ("BA", "Beta", "Povo B", "Porto Seguro", "Declarada"),
        ("AC", "Isolados do Igarapé Tapada", "Isolados", "Mâncio Lima", "Reivindicada"),
        ("MG", "Gama", "Povo G", "Viçosa", "Reivindicada"),
        ("MG", "Terra Indígena Alfa", "Povo A", "Viçosa", "Regularizada"),
    ], columns=["UF", "Terra Indígena", "Povo", "Município", "Situação Jurídica"]).to_csv(
        proj / "data/raw/mpf/tabela.csv", index=False)


def _ref(proj):
    pd.DataFrame([
        (1, "Viçosa", "MG", -42.88, -20.75), (2, "Porto Seguro", "BA", -39.06, -16.44),
        (3, "Mâncio Lima", "AC", -72.9, -7.6),
    ], columns=["cod_ibge", "nome", "uf", "lon", "lat"]).to_csv(proj / "data/ref/municipios.csv", index=False)
    pd.DataFrame([("MG", -44.0, -18.5), ("BA", -41.7, -12.5), ("AC", -70.5, -9.0)],
                 columns=["uf", "lon", "lat"]).to_csv(proj / "data/ref/ufs.csv", index=False)


def _rodar(data):
    ingest.ingest_all()
    match.run(data)
    df = build.run()
    ev = history.snapshot(data)
    export.run()
    return df, ev


def test_pipeline_e_historico(proj):
    _funai(proj)
    _mpf(proj)
    _ref(proj)

    df, ev = _rodar("2026-11-01")
    t = df.set_index("nome")
    assert len(df) == 4                                   # Alfa, Beta, Isolados, Gama
    assert t.loc["Terra Indígena Alfa", "divergencia_fase"] == "true"   # funai x mpf
    assert t.loc["Terra Indígena Alfa", "fase"] == "homologada"         # funai tem prioridade
    assert t.loc["Gama", "precisao_geom"] == "municipio"                # sem polígono -> ponto
    assert t.loc["Gama", "fase"] == "sem_providencia"
    assert t.loc["Isolados do Igarapé Tapada", "sensivel"] == "true"
    assert len(ev) == 0                                                  # baseline não gera eventos
    assert validate.run() == 0

    gj = json.loads((proj / "site/data/terras.geojson").read_text("utf-8"))
    por_nome = {f["properties"]["nome"]: f for f in gj["features"]}
    assert por_nome["Gama"]["geometry"]["type"] == "Point"
    iso = por_nome["Isolados do Igarapé Tapada"]                         # sensível: só UF
    assert iso["properties"]["precisao_geom"] == "uf"
    ficha = json.loads((proj / f"site/data/terras/{iso['properties']['terra_id']}.json").read_text("utf-8"))
    assert ficha["municipios"] == ""

    # ---- segunda rodada: Funai passa a publicar o polígono de Gama e Beta avança de fase
    _funai(proj, gamas=True, beta_fase="Homologada")
    df2, ev2 = _rodar("2026-11-08")
    mud = {(r.nome, r.campo): (r.valor_anterior, r.valor_novo) for r in ev2.itertuples()}
    assert mud[("Terra Indígena Gama", "precisao_geom")] == ("municipio", "poligono")
    assert mud[("Terra Indígena Beta", "fase")] == ("declarada", "homologada")
    assert len(df2) == 4                                  # Gama NÃO duplicou: foi vinculada pelo nome

    eventos = pd.read_csv(proj / "data/history/eventos.csv")
    assert set(eventos["data_observacao"]) == {"2026-11-08"}

    # ---- rodar de novo sem mudanças: nenhum evento e nenhum snapshot novo
    _, ev3 = _rodar("2026-11-15")
    assert len(ev3) == 0
    assert not (proj / "data/history/snapshots/2026-11-15.csv.gz").exists()
    assert len(pd.read_csv(proj / "data/history/observacoes.csv")) == 3


def test_vinculo_confirmado_nao_e_alterado(proj):
    _funai(proj)
    _mpf(proj)
    _ref(proj)
    _rodar("2026-11-01")
    xw_path = proj / "data/crosswalk/fontes_ids.csv"
    xw = pd.read_csv(xw_path, dtype=str)
    xw.loc[xw["fonte"] == "mpf", "status"] = "confirmado"
    xw.to_csv(xw_path, index=False)
    antes = pd.read_csv(xw_path, dtype=str)
    match.run("2026-11-02")
    depois = pd.read_csv(xw_path, dtype=str)
    pd.testing.assert_frame_equal(antes.reset_index(drop=True), depois.reset_index(drop=True))


def test_extras_juridicos_e_data_do_ato(proj):
    from demarcacao.normalize import parse_data_ato
    assert parse_data_ato("Decreto s/nº de 05/01/96") == "1996-01-05"
    assert parse_data_ato("Decreto s/nº de 27/10/04") == "2004-10-27"
    assert parse_data_ato("Portaria Funai nº 924 de 18/03/2015") == "2015-03-18"
    assert parse_data_ato("Instrumento público") == ""

    _funai(proj)
    pd.DataFrame([
        ("BA", "Beta", "Povo B", "Porto Seguro", "Declarada", "Portaria MJ 123 de 10/02/2010", "ICP 1/2020", "ACP 55/2021"),
    ], columns=["UF", "Terra Indígena", "Povo", "Município", "Situação Jurídica", "ATO",
                "Nº Processo Funai", "Processos Judiciais"]).to_csv(proj / "data/raw/mpf/tabela.csv", index=False)
    _ref(proj)
    _rodar("2026-11-01")
    jur = pd.read_csv(proj / "data/processed/juridico.csv", dtype=str).fillna("")
    beta = jur[(jur["fonte"] == "mpf")].iloc[0]
    assert beta["ato_data"] == "2010-02-10" and beta["processos_judiciais"] == "ACP 55/2021"
    tid = beta["terra_id"]
    ficha = json.loads((proj / f"site/data/terras/{tid}.json").read_text("utf-8"))
    assert ficha["juridico"][0]["processo_funai"] == "ICP 1/2020"


def test_sensivel_com_poligono_publico_nao_degrada(proj):
    gdf = gpd.GeoDataFrame([dict(terrai_cod=9, terrai_nom="Terra Indígena Zeta", etnia_nome="Isolados",
                                 municipio_="Viçosa", uf_sigla="MG", superficie="10", fase_ti="Regularizada",
                                 modalidade="Tradicionalmente ocupada", geometry=box(-43, -21, -42.9, -20.9))], crs=4326)
    gdf.to_file(proj / "data/raw/funai/ti.gpkg", driver="GPKG")
    _ref(proj)
    df, _ = _rodar("2026-11-01")
    assert df.iloc[0]["sensivel"] == "false" and df.iloc[0]["precisao_geom"] == "poligono"


def _funai_rows(proj, rows):
    gdf = gpd.GeoDataFrame(
        [dict(terrai_cod=c, terrai_nom=n, etnia_nome="X", municipio_="Viçosa", uf_sigla=uf, superficie="1",
              fase_ti="Homologada", modalidade_="Tradicionalmente ocupada", geometry=box(-43 + i * .2, -21, -42.9 + i * .2, -20.9))
         for i, (c, n, uf) in enumerate(rows)], crs=4326)
    p = proj / "data/raw/funai/ti.gpkg"
    if p.exists():
        p.unlink()
    gdf.to_file(p, driver="GPKG")


def _mpf_rows(proj, rows):
    pd.DataFrame(rows, columns=["UF", "Terra Indígena", "Povo", "Município", "Situação Jurídica"]).to_csv(
        proj / "data/raw/mpf/tabela.csv", index=False)


def test_grafias_equivalentes_viram_uma_terra(proj):
    from demarcacao.match import key, score, _ufs
    assert score(key("Zo’é", {"PA"}), key("Zoe", {"PA"})) == 100
    assert score(key("Fulni-ô", {"PE"}), key("Fulniô", {"PE"})) == 100
    assert score(key("Valparaíso (RI)", {"AM"}), key("Valparaíso", {"AM"})) == 100
    assert score(key("Fazenda Boa Vista - MG", {"MG"}), key("Fazenda Boa Vista", {"MG"})) == 100
    assert score(key("Caramuru/Paraguassu", {"BA"}), key("Caramuru-Paraguaçu", {"BA"})) == 100
    # terras DISTINTAS não podem passar do limiar automático (93)
    assert score(key("Irapuá", {"RS"}), key("Itapuã", {"RS"})) < 93
    assert score(key("Apinayé II", {"TO"}), key("Apinayé", {"TO"})) < 93
    assert score(key("Pankararé", {"BA"}), key("Neo-Pankararé", {"BA"})) < 93
    assert score(key("Tekoa Itaoka (Icapara II)", {"SP"}), key("Tekoa Itapuã (Icapara I)", {"SP"})) < 93

    _funai_rows(proj, [(1, "Xukuru de Cimbres", "PE"), (2, "Irapuá", "RS")])
    _mpf_rows(proj, [("PE", "Xucuru de Cimbres", "P", "Pesqueira", "Homologada"),
                     ("RS", "Itapuã", "P", "Viamão", "Reivindicada")])
    _ref(proj)
    df, _ = _rodar("2026-11-01")
    assert len(df) == 3                      # Xukuru fundida; Irapuá e Itapuã seguem distintas


def test_empate_vai_para_revisao_e_decisao_humana_e_respeitada(proj):
    # duas terras da Funai com o mesmo nome (como "Xacriabá" x2) e uma linha do MPF
    _funai_rows(proj, [(1, "Xacriabá", "MG"), (2, "Xacriabá", "MG")])
    _mpf_rows(proj, [("MG", "Xakriabá", "P", "Viçosa", "Homologada")])
    _ref(proj)
    df, _ = _rodar("2026-11-01")
    assert len(df) == 3                      # empate: NÃO vincula sozinho
    rev = pd.read_csv(proj / "data/crosswalk/revisar.csv", sep=";", encoding="utf-8-sig", dtype=str).fillna("")
    assert len(rev) == 2 and set(rev["obs"]) == {"empate entre candidatas"}
    assert set(rev["fonte"]) == {"mpf"}

    # o humano escolhe a primeira candidata
    alvo = rev.iloc[0]["candidato_id"]
    rev["decisao"] = ["sim", "nao"]
    rev.to_csv(proj / "data/crosswalk/revisar.csv", sep=";", encoding="utf-8-sig", index=False)
    df2, _ = _rodar("2026-11-02")
    assert len(df2) == 2
    xw = pd.read_csv(proj / "data/crosswalk/fontes_ids.csv", dtype=str)
    mp = xw[xw["fonte"] == "mpf"].iloc[0]
    assert mp["terra_id"] == alvo and mp["status"] == "confirmado"
    assert (proj / "data/crosswalk/fusoes.csv").exists()
    ev = pd.read_csv(proj / "data/history/eventos.csv")
    assert "fundida_em" in set(ev["tipo"])   # a fusão aparece no histórico, não como "removida"
    # rodar de novo não desfaz a decisão
    _rodar("2026-11-03")
    xw = pd.read_csv(proj / "data/crosswalk/fontes_ids.csv", dtype=str)
    assert xw[xw["fonte"] == "mpf"].iloc[0]["terra_id"] == alvo


def test_fases_especiais_e_relatorio_com_exemplos(proj):
    from demarcacao.normalize import map_fase
    assert map_fase("Encaminhada RI") == "reserva_em_constituicao"
    assert map_fase("Com restrição de ingresso") == "restricao_de_uso"
    assert map_fase("Dominial Indígena") == ""


def test_atualizacao_de_crosswalk_antigo_funde_duplicatas(proj):
    """Simula o estado gerado pela versão anterior do cruzamento (mesma terra duplicada como 'novo')."""
    _funai_rows(proj, [(1, "Xukuru de Cimbres", "PE")])
    _mpf_rows(proj, [("PE", "Xucuru de Cimbres", "P", "Pesqueira", "Homologada")])
    _ref(proj)
    _rodar("2026-11-01")
    xw_p, id_p = proj / "data/crosswalk/fontes_ids.csv", proj / "data/crosswalk/terras_ids.csv"
    xw, ids = pd.read_csv(xw_p, dtype=str), pd.read_csv(id_p, dtype=str)
    xw.loc[xw["fonte"] == "mpf", ["terra_id", "status"]] = ["TI0099", "novo"]     # separa de novo
    ids = pd.concat([ids, pd.DataFrame([{"terra_id": "TI0099", "nome_canonico": "Xucuru de Cimbres", "criado_em": "x"}])])
    xw.to_csv(xw_p, index=False)
    ids.to_csv(id_p, index=False)
    assert len(ids) == 2
    df, _ = _rodar("2026-11-02")
    assert len(df) == 1
    assert list(pd.read_csv(proj / "data/crosswalk/fusoes.csv")["terra_removida"]) == ["TI0099"]


def test_export_gera_arquivos_do_site(proj):
    _funai(proj)
    _mpf(proj)
    _ref(proj)
    gpd.GeoDataFrame([{"uf": "MG", "geometry": box(-51, -23, -39.8, -14.2)}], crs=4326).to_file(
        proj / "data/ref/ufs.geojson", driver="GeoJSON")
    _rodar("2026-11-01")
    out = proj / "site/data"
    idx = json.loads((out / "indice.json").read_text("utf-8"))
    por_nome = {t["nome"]: t for t in idx}
    assert len(idx) == 4
    assert por_nome["Terra Indígena Alfa"]["bbox"] and por_nome["Terra Indígena Alfa"]["precisao"] == "poligono"
    assert por_nome["Isolados do Igarapé Tapada"]["municipios"] == ""        # sensível: sem município no índice
    assert por_nome["Isolados do Igarapé Tapada"]["precisao"] == "uf"
    cen = json.loads((out / "centroides.geojson").read_text("utf-8"))
    assert len(cen["features"]) == 2 and all(f["geometry"]["type"] == "Point" for f in cen["features"])
    uf = json.loads((out / "ufs.geojson").read_text("utf-8"))
    assert uf["features"][0]["properties"]["uf"] == "MG"
    meta = json.loads((out / "meta.json").read_text("utf-8"))
    assert meta["titulo"] and meta["versao"]
