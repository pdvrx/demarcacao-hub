"""Consolida as fontes em UMA tabela de terras (data/processed/terras.csv) + geometrias.

Regra de geometria (por terra):
  1. tem polígono da Funai vinculado        -> polígono          (precisao_geom = 'poligono')
  2. senão, município(s) conhecidos         -> ponto(s)          (precisao_geom = 'municipio')
  3. senão, só a UF                         -> ponto da UF       (precisao_geom = 'uf')
  4. senão                                  -> sem geometria     (precisao_geom = 'nenhuma')
Quando a Funai passar a publicar o polígono, a terra muda de 2/3 para 1 sozinha (e o histórico registra).
"""
from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd
import shapely
from rapidfuzz import fuzz, process
from shapely.geometry import MultiPoint, Point

from . import config, match, paths
from .normalize import norm_text, parse_data_ato, parse_municipios
from .schema import FASE_INDEFINIDA, FASES, FASES_ESPECIAIS, JURIDICO_COLS, TERRAS_COLS


def _first(values) -> str:
    for v in values:
        if v is not None and str(v).strip() not in ("", "nan"):
            return str(v).strip()
    return ""


def _ref():
    p = paths.data("ref", "municipios.csv")
    if not p.exists():
        print("[build] AVISO: data/ref/municipios.csv não existe; rode `python -m demarcacao fetch-ref`. "
              "Terras sem polígono ficarão sem localização.")
        return {}, {}
    df = pd.read_csv(p, dtype={"uf": str, "nome": str})
    df["nome_norm"] = df["nome"].map(norm_text)
    by_uf = {uf: g.reset_index(drop=True) for uf, g in df.groupby("uf")}
    up = paths.data("ref", "ufs.csv")
    ufs = {r.uf: (r.lon, r.lat) for r in pd.read_csv(up).itertuples()} if up.exists() else {}
    return by_uf, ufs


def _geocode(muns, ufs, by_uf):
    pts, miss = [], []
    for nome, uf in muns:
        n, hit = norm_text(nome), None
        for u in ([uf] if uf else ufs):
            g = by_uf.get(u)
            if g is None:
                continue
            m = g[g["nome_norm"] == n]
            if len(m):
                hit = (float(m.iloc[0].lon), float(m.iloc[0].lat))
                break
            res = process.extractOne(n, g["nome_norm"].tolist(), scorer=fuzz.ratio, score_cutoff=90)
            if res:
                hit = (float(g.iloc[res[2]].lon), float(g.iloc[res[2]].lat))
                break
        if hit:
            pts.append(hit)
        else:
            miss.append(nome)
    return pts, miss


def run() -> pd.DataFrame:
    S = config.settings()
    prio = S["prioridade_fontes"]
    rank = {f: i for i, f in enumerate(prio)}
    sens_kw = [norm_text(k) for k in S["sensivel"]["palavras_chave"]]

    xw = pd.read_csv(paths.data("crosswalk", "fontes_ids.csv"), dtype=str).fillna("")
    reg = match.load_registros(prio).merge(xw[["fonte", "chave_fonte", "terra_id"]],
                                           on=["fonte", "chave_fonte"], how="left")
    if reg["terra_id"].isna().any() or (reg["terra_id"] == "").any():
        raise RuntimeError("Há registros sem terra_id. Rode `python -m demarcacao match` antes do build.")
    reg["_rank"] = reg["fonte"].map(rank).fillna(99)
    reg = reg.sort_values(["terra_id", "_rank", "chave_fonte"])

    # ---- polígonos da Funai
    poly: dict = {}
    gp = paths.data("interim", "funai.gpkg")
    if gp.exists():
        geo = gpd.read_file(gp)
        link = xw[xw["fonte"] == "funai"][["chave_fonte", "terra_id"]]
        m = pd.DataFrame(geo.drop(columns="geometry")).assign(geometry=geo.geometry.values).merge(link, on="chave_fonte")
        for tid, g in m.groupby("terra_id"):
            poly[tid] = shapely.union_all(list(g["geometry"]))

    by_uf, uf_pts = _ref()
    terras, pts_rows, poly_rows = [], [], []

    for tid, g in reg.groupby("terra_id", sort=True):
        nome = _first(g["nome_original"])
        ufs = sorted({u for s in g["ufs"] for u in s.split(";") if u})
        seen, muns = set(), []
        for s in g["municipios"]:
            for piece in str(s).split(";"):
                piece = piece.strip()
                if piece and norm_text(piece) not in seen:
                    seen.add(norm_text(piece))
                    muns.append(piece)
        povos = _first(g["povos"])
        mods = [x for x in g["modalidade"] if x and x != "nao_informada"]
        fases_fonte = {}
        for f in prio:
            sub = g[(g["fonte"] == f) & (g["fase"] != "")]
            if len(sub):
                fases_fonte[f] = sub["fase"].iloc[0]
        fase = next(iter(fases_fonte.values()), FASE_INDEFINIDA)
        sens = any(k in norm_text(f"{nome} {povos}") for k in sens_kw)
        if sens and S["sensivel"].get("somente_sem_poligono", True) and tid in poly:
            sens = False  # polígono já é público (Funai): não há o que proteger aqui

        # ---- geometria
        if tid in poly:
            precisao = "poligono"
            poly_rows.append({"terra_id": tid, "precisao_geom": precisao, "geometry": poly[tid]})
        else:
            pts, _ = _geocode(parse_municipios("; ".join(muns), ufs), ufs, by_uf)
            if pts:
                precisao = "municipio"
            else:
                pts = [uf_pts[u] for u in ufs if u in uf_pts]
                precisao = "uf" if pts else "nenhuma"
            if pts:
                geom = Point(pts[0]) if len(pts) == 1 else MultiPoint(pts)
                pts_rows.append({"terra_id": tid, "precisao_geom": precisao, "geometry": geom})

        terras.append({
            "terra_id": tid, "nome": nome, "ufs": ";".join(ufs), "municipios": "; ".join(muns),
            "povos": povos, "area_ha": _first(g["area_ha"]),
            "modalidade": mods[0] if mods else "nao_informada",
            "fase": fase, "fase_fonte": next(iter(fases_fonte), ""),
            "fases_por_fonte": "|".join(f"{k}:{v}" for k, v in fases_fonte.items()),
            "divergencia_fase": str(len(set(fases_fonte.values())) > 1).lower(),
            "precisao_geom": precisao, "sensivel": str(sens).lower(),
            "fontes": ",".join(sorted(set(g["fonte"]))), "n_registros": len(g),
        })

    out = paths.ensure(paths.data("processed"))
    df = pd.DataFrame(terras, columns=TERRAS_COLS)
    df.to_csv(out / "terras.csv", index=False)
    reg[["terra_id", "fonte", "chave_fonte", "nome_original", "fase_origem", "fase", "ufs", "municipios",
         "area_ha"]].to_csv(out / "registros_por_terra.csv", index=False)

    gpkg = out / "geometrias.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    if poly_rows:
        gpd.GeoDataFrame(poly_rows, crs=4326).to_file(gpkg, driver="GPKG", layer="poligonos")
    if pts_rows:
        gpd.GeoDataFrame(pts_rows, crs=4326).to_file(gpkg, driver="GPKG", layer="pontos")

    _juridico(reg, out / "juridico.csv")
    _relatorios(df, reg, out / "relatorios")
    print(f"[build] {len(df)} terras: " + ", ".join(f"{k}={v}" for k, v in df["precisao_geom"].value_counts().items()))
    return df


def _relatorios(df: pd.DataFrame, reg: pd.DataFrame, d) -> None:
    paths.ensure(d)
    df[df["precisao_geom"] == "nenhuma"][["terra_id", "nome", "ufs", "municipios"]].to_csv(
        d / "sem_localizacao.csv", index=False)
    df[df["divergencia_fase"] == "true"][["terra_id", "nome", "ufs", "fases_por_fonte"]].to_csv(
        d / "divergencias_fase.csv", index=False)
    por_fonte = reg[reg["fase"] != ""].groupby(["fonte", "fase"]).size().reset_index(name="n")
    cons = df.groupby("fase").size().reset_index(name="n").assign(fonte="consolidado")
    cont = pd.concat([por_fonte, cons[["fonte", "fase", "n"]]])
    order = {f: i for i, f in enumerate(FASES + FASES_ESPECIAIS + [FASE_INDEFINIDA])}
    cont["_o"] = cont["fase"].map(order)
    cont.sort_values(["fonte", "_o"]).drop(columns="_o").to_csv(d / "contagens_por_fase.csv", index=False)


def _juridico(reg: pd.DataFrame, path) -> None:
    """Uma linha por registro de fonte com os campos jurídicos/administrativos (ato, processos, etapa...)."""
    rows = []
    for r in reg.itertuples():
        ex = json.loads(r.extras) if isinstance(r.extras, str) and r.extras else {}
        if not ex:
            continue
        ex["ato_data"] = parse_data_ato(ex.get("ato", ""))
        rows.append({"terra_id": r.terra_id, "fonte": r.fonte, **ex})
    pd.DataFrame(rows, columns=JURIDICO_COLS).sort_values(["terra_id", "fonte"]).to_csv(path, index=False)
