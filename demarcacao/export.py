"""Gera os arquivos que o site consome (site/data/) e os downloads abertos."""
from __future__ import annotations

import datetime as dt
import json
import shutil

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import MultiPoint, Point, mapping

from . import config, history, paths
from .schema import FASE_ROTULOS


def _read(path, cols=None):
    return pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame(columns=cols or [])


def _round(o, nd: int = 4):
    if isinstance(o, (list, tuple)):
        return [_round(x, nd) for x in o]
    return round(o, nd) if isinstance(o, float) else o


def _dump(path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")


def run() -> None:
    E = config.settings()["export"]
    out = paths.ensure(paths.site("data"))
    shutil.rmtree(out / "terras", ignore_errors=True)
    paths.ensure(out / "terras")
    paths.ensure(out / "downloads")

    terras = _read(paths.data("processed", "terras.csv"))
    regs = _read(paths.data("processed", "registros_por_terra.csv"))
    jur = _read(paths.data("processed", "juridico.csv"))
    ev = _read(paths.data("history", "eventos.csv"), history.EV_COLS)
    mt = _read(paths.data("history", "marcos_terra.csv"))
    mg = _read(paths.data("history", "marcos_gerais.csv"))
    obs = _read(paths.data("history", "observacoes.csv"), history.OBS_COLS)
    sens = set(terras.loc[terras["sensivel"] == "true", "terra_id"])
    meta_p = paths.data("interim", "ingest_meta.json")
    ingest_meta = json.loads(meta_p.read_text("utf-8")) if meta_p.exists() else {}

    ufp = paths.data("ref", "ufs.csv")
    uf_pts = {r.uf: (r.lon, r.lat) for r in pd.read_csv(ufp).itertuples()} if ufp.exists() else {}
    rot = terras.set_index("terra_id")

    def props(tid: str, precisao: str) -> dict:
        r = rot.loc[tid]
        return {"terra_id": tid, "nome": r["nome"], "ufs": r["ufs"], "fase": r["fase"],
                "fase_rotulo": FASE_ROTULOS.get(r["fase"], r["fase"]), "precisao_geom": precisao,
                "divergencia_fase": r["divergencia_fase"] == "true", "sensivel": tid in sens}

    feats, public_prec, bboxes, centros = [], {}, {}, []
    gpkg = paths.data("processed", "geometrias.gpkg")
    for layer in ("poligonos", "pontos"):
        try:
            gdf = gpd.read_file(gpkg, layer=layer)
        except Exception:
            continue
        for tid, prec, geom in zip(gdf["terra_id"], gdf["precisao_geom"], gdf.geometry):
            if tid in sens:
                continue  # sensíveis: só UF (abaixo)
            if layer == "poligonos":
                s = geom.simplify(E["simplificar_graus"], preserve_topology=True)
                geom = s if not s.is_empty else geom
            geom = shapely.set_precision(geom, E["precisao_coord"])
            public_prec[tid] = prec
            bboxes[tid] = [round(v, 4) for v in geom.bounds]
            feats.append({"type": "Feature", "geometry": mapping(geom), "properties": props(tid, prec)})
            if layer == "poligonos":  # ponto de referência: deixa terras pequenas visíveis no mapa nacional
                rp = geom.representative_point()
                centros.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(rp.x, 4), round(rp.y, 4)]},
                                "properties": props(tid, prec)})
    for tid in sorted(sens):  # política 'degradar_para_uf'
        pts = [uf_pts[u] for u in rot.loc[tid, "ufs"].split(";") if u in uf_pts]
        if pts:
            geom = Point(pts[0]) if len(pts) == 1 else MultiPoint(pts)
            public_prec[tid] = "uf"
            bboxes[tid] = [round(v, 4) for v in geom.bounds]
            feats.append({"type": "Feature", "geometry": mapping(geom), "properties": props(tid, "uf")})
    _dump(out / "terras.geojson", {"type": "FeatureCollection", "features": feats})
    _dump(out / "centroides.geojson", {"type": "FeatureCollection", "features": centros})

    # índice leve para busca/filtros no navegador (sem municípios de terras sensíveis)
    _dump(out / "indice.json", [{
        "id": tid, "nome": r["nome"], "ufs": r["ufs"], "fase": r["fase"], "povos": r["povos"],
        "municipios": "" if tid in sens else r["municipios"], "area_ha": r["area_ha"],
        "precisao": public_prec.get(tid, "nenhuma"), "divergente": r["divergencia_fase"] == "true",
        "bbox": bboxes.get(tid),
    } for tid, r in rot.iterrows()])

    # contorno das UFs (fundo do mapa), de data/ref/ufs.geojson (gerado por `fetch-ref`)
    uf_src, uf_dst = paths.data("ref", "ufs.geojson"), out / "ufs.geojson"
    if uf_src.exists():
        g = gpd.read_file(uf_src)
        _dump(uf_dst, {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"uf": u}, "geometry": {"type": m["type"], "coordinates": _round(m["coordinates"])}}
            for u, m in ((u, mapping(geo)) for u, geo in zip(g["uf"], g.geometry))]})
    elif uf_dst.exists():
        uf_dst.unlink()

    # ---- uma ficha por terra
    for tid, r in rot.iterrows():
        ficha = {
            **props(tid, public_prec.get(tid, "nenhuma")),
            "povos": r["povos"], "area_ha": r["area_ha"], "modalidade": r["modalidade"],
            "fases_por_fonte": r["fases_por_fonte"],
            "municipios": "" if tid in sens else r["municipios"],
            "fontes": regs[regs["terra_id"] == tid][["fonte", "nome_original", "fase_origem", "fase"]].to_dict("records"),
            "juridico": [{k: v for k, v in row.items() if v != ""}
                         for row in jur[jur["terra_id"] == tid].drop(columns=["terra_id"]).to_dict("records")]
                        if len(jur) else [],
            "historico": ev[ev["terra_id"] == tid].drop(columns=["terra_id", "nome"]).to_dict("records"),
            "marcos": mt[mt["terra_id"] == tid].drop(columns=["terra_id"]).to_dict("records") if len(mt) else [],
        }
        _dump(out / "terras" / f"{tid}.json", ficha)

    # ---- resumo, marcos gerais, meta
    por_uf: dict[str, int] = {}
    for s in terras["ufs"]:
        for u in [x for x in s.split(";") if x]:
            por_uf[u] = por_uf.get(u, 0) + 1
    _dump(out / "resumo.json", {
        "total": len(terras),
        "por_fase": terras["fase"].value_counts().to_dict(),
        "por_precisao_geom": pd.Series(public_prec).value_counts().to_dict(),
        "sem_geometria": int(len(terras) - len(public_prec)),
        "divergencias_de_fase": int((terras["divergencia_fase"] == "true").sum()),
        "por_uf": dict(sorted(por_uf.items())),
    })
    _dump(out / "marcos_gerais.json", mg.to_dict("records"))
    _dump(out / "eventos_recentes.json", ev.sort_values("data_observacao", ascending=False).head(200).to_dict("records"))
    _dump(out / "meta.json", {
        "titulo": E.get("titulo", "Demarcação em Dados"), "subtitulo": E.get("subtitulo", ""),
        "versao": E["versao"], "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "ultima_observacao": obs["data_observacao"].max() if len(obs) else None,
        "fontes": ingest_meta,
        "aviso": "Localizações por 'municipio' ou 'uf' são aproximadas e NÃO delimitam o território reivindicado.",
    })

    # ---- downloads abertos
    dl = terras.copy()
    dl.loc[dl["sensivel"] == "true", "municipios"] = ""
    dl.to_csv(out / "downloads" / "terras.csv", index=False)
    jur.to_csv(out / "downloads" / "juridico.csv", index=False)
    for name, df in (("eventos.csv", ev), ("marcos_terra.csv", mt), ("marcos_gerais.csv", mg)):
        df.to_csv(out / "downloads" / name, index=False)
    print(f"[export] site/data/: {len(feats)} feições, {len(centros)} centroides, {len(rot)} fichas, downloads/")
