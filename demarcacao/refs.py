"""Referências geográficas (IBGE): ponto representativo de cada município e de cada UF.
Usadas para posicionar, de forma APROXIMADA, terras que ainda não têm polígono.

Saída: data/ref/municipios.csv (cod_ibge,nome,uf,lon,lat), data/ref/ufs.csv (uf,lon,lat) e
data/ref/ufs.geojson (contorno das UFs, usado como fundo do mapa).
Você também pode colocar esses arquivos à mão (mesmas colunas) se a API do IBGE mudar.
"""
from __future__ import annotations

import json

import pandas as pd

from . import paths

MUN_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
MALHA_URL = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
             "?intrarregiao=municipio&formato=application/vnd.geo+json&qualidade=minima")


def _uf_of(m: dict) -> dict:
    for path in (("microrregiao", "mesorregiao", "UF"),
                 ("regiao-imediata", "regiao-intermediaria", "UF")):
        cur = m
        for k in path:
            cur = (cur or {}).get(k)
        if cur:
            return cur
    return {}


def fetch_ref() -> None:
    import geopandas as gpd
    import requests
    import shapely

    muns = requests.get(MUN_URL, timeout=120).json()
    info = {str(m["id"]): (m["nome"], _uf_of(m).get("sigla", "")) for m in muns}
    uf_ids = sorted({_uf_of(m).get("id") for m in muns if _uf_of(m).get("id")})

    rows, uf_rows, uf_geoms = [], [], []
    for uf_id in uf_ids:
        txt = requests.get(MALHA_URL.format(uf=uf_id), timeout=180).text
        gdf = gpd.GeoDataFrame.from_features(json.loads(txt)["features"], crs=4326)
        pts = gdf.geometry.representative_point()
        for code, p in zip(gdf["codarea"], pts):
            nome, uf = info.get(str(code), ("", ""))
            rows.append({"cod_ibge": code, "nome": nome, "uf": uf, "lon": round(p.x, 5), "lat": round(p.y, 5)})
        up = shapely.union_all(list(gdf.geometry)).representative_point()
        uf_sigla = next((info[str(c)][1] for c in gdf["codarea"] if str(c) in info), "")
        uf_rows.append({"uf": uf_sigla, "lon": round(up.x, 5), "lat": round(up.y, 5)})
        uf_geoms.append({"uf": uf_sigla, "geometry": shapely.union_all(list(gdf.geometry))})
        print(f"[ref] UF {uf_sigla}: {len(gdf)} municípios")

    out = paths.ensure(paths.data("ref"))
    pd.DataFrame(rows).sort_values(["uf", "nome"]).to_csv(out / "municipios.csv", index=False)
    pd.DataFrame(uf_rows).sort_values("uf").to_csv(out / "ufs.csv", index=False)
    gj = out / "ufs.geojson"
    if gj.exists():
        gj.unlink()
    gpd.GeoDataFrame(uf_geoms, crs=4326).to_file(gj, driver="GeoJSON")
    print(f"[ref] contornos das UFs -> {gj}")
    print(f"[ref] {len(rows)} municípios -> {out / 'municipios.csv'}")
