"""Leitura das fontes brutas (data/raw/<fonte>/) -> tabela padronizada em data/interim/<fonte>.csv."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

from . import config, paths
from .normalize import (map_fase, map_modalidade, norm_text, normalize_name,
                        parse_float_br, parse_municipios, split_ufs)
from .schema import INTERIM_COLS

RAW_EXT = {".zip", ".shp", ".gpkg", ".geojson", ".csv", ".xlsx", ".xls", ".pdf"}


# ----------------------------------------------------------------------------- arquivos
def latest_raw(fonte: str, arquivo: str | None = None) -> Path:
    if arquivo:
        return Path(arquivo)
    d = paths.data("raw", fonte)
    files = [f for f in d.glob("*") if f.suffix.lower() in RAW_EXT and not f.name.startswith(".")]
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo em {d} (extensões aceitas: {sorted(RAW_EXT)})")
    return max(files, key=lambda f: f.stat().st_mtime)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- leitura
def read_geo(path: Path):
    import geopandas as gpd
    import shapely

    p = Path(path)
    gdf = gpd.read_file(f"zip://{p}") if p.suffix.lower() == ".zip" else gpd.read_file(p)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf["geometry"] = [shapely.make_valid(g) for g in gdf.geometry]
    return gdf


def _looks_like_header(cells: list[str]) -> bool:
    ns = [norm_text(c) for c in cells]
    hits = 0
    for kw in ("terra", "munic", "uf"):
        if any((n == kw) if kw == "uf" else (kw in n) for n in ns):
            hits += 1
    return hits >= 2


def read_pdf_table(path: Path) -> pd.DataFrame:
    """Extrai tabelas de um PDF com pdfplumber. Salva o bruto em data/interim/ para você conferir."""
    import pdfplumber

    header, rows = None, []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables:  # PDFs sem linhas de grade
                tables = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
            for t in tables:
                for row in t:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    if not any(cells):
                        continue
                    if _looks_like_header(cells):
                        if header is None:
                            header = cells
                        continue  # cabeçalho repetido em outras páginas
                    rows.append(cells)
    if not rows:
        raise ValueError(f"Nenhuma tabela extraída de {path}. Rode `inspect` e considere converter para CSV.")
    width = max(len(r) for r in rows)
    header = header or []
    cols = [header[i] if i < len(header) and header[i] else f"col{i}" for i in range(width)]
    df = pd.DataFrame([r + [""] * (width - len(r)) for r in rows], columns=cols)
    df.to_csv(paths.ensure(paths.data("interim")) / f"{Path(path).stem}_pdf_bruto.csv", index=False)
    return df


def read_table(path: Path) -> pd.DataFrame:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return read_pdf_table(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str)
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Não consegui ler {path}")


# ----------------------------------------------------------------------------- padronização
def pick_all(df: pd.DataFrame, candidates) -> list:
    """Colunas do df que casam com os candidatos, na ordem dos candidatos (exato; senão 'contém')."""
    norm = {c: norm_text(c) for c in df.columns}
    found: list = []
    for cand in candidates or []:
        nc = norm_text(cand)
        col = next((c for c, n in norm.items() if n == nc), None) or \
            next((c for c, n in norm.items() if nc and nc in n), None)
        if col is not None and col not in found:
            found.append(col)
    return found


def standardize(df: pd.DataFrame, fonte: str, cfg: dict) -> pd.DataFrame:
    cols = {k: pick_all(df, v) for k, v in cfg.get("colunas", {}).items()}
    extra_cols = {k: pick_all(df, v) for k, v in cfg.get("extras", {}).items()}
    if not cols.get("nome"):
        raise ValueError(
            f"[{fonte}] coluna de nome não encontrada. Colunas disponíveis: {list(df.columns)}. "
            "Ajuste config/sources.yml (use `python -m demarcacao inspect <arquivo>`)."
        )

    def val(r, key) -> str:
        for c in cols.get(key, []):
            v = r.get(c)
            if v is not None and str(v).strip() not in ("", "nan", "None", "NaN"):
                return str(v).strip()
        return ""

    out, idx, seen = [], [], {}
    for i, r in df.iterrows():
        nome = val(r, "nome")
        if not nome:
            continue
        ufs = split_ufs(val(r, "uf"))
        muns = parse_municipios(val(r, "municipio"), ufs)
        ufs_all = sorted(set(ufs) | {u for _, u in muns if u})
        mun_s = []
        for n, u in muns:
            u = u or (ufs_all[0] if len(ufs_all) == 1 else "")
            mun_s.append(f"{n}/{u}" if u else n)

        nome_norm = normalize_name(nome)
        base = val(r, "id") or f"{nome_norm}|{ufs_all[0] if ufs_all else ''}"
        seen[base] = seen.get(base, 0) + 1
        chave = base if seen[base] == 1 else f"{base}#{seen[base]}"

        fase, fase_origem = "", ""
        for c in cols.get("fase", []):
            raw = str(r.get(c) or "").strip()
            if raw and raw.lower() not in ("nan", "none"):
                fase_origem = fase_origem or raw
                m = map_fase(raw)
                if m:
                    fase, fase_origem = m, raw
                    break

        area = parse_float_br(val(r, "area_ha"))
        extras = {}
        for k, cs in extra_cols.items():
            for c in cs:
                v = r.get(c)
                if v is not None and str(v).strip() not in ("", "nan", "None", "NaN"):
                    extras[k] = str(v).strip()
                    break
        out.append({
            "fonte": fonte, "chave_fonte": chave, "nome_original": nome, "nome_norm": nome_norm,
            "ufs": ";".join(ufs_all), "municipios": "; ".join(mun_s), "povos": val(r, "povo"),
            "area_ha": "" if area is None else round(area, 2),
            "fase_origem": fase_origem, "fase": fase,
            "modalidade": map_modalidade(val(r, "modalidade")),
            "extras": json.dumps(extras, ensure_ascii=False) if extras else "",
        })
        idx.append(i)
    return pd.DataFrame(out, index=idx, columns=INTERIM_COLS)


# ----------------------------------------------------------------------------- orquestração
def _update_meta(fonte: str, path: Path, n: int) -> None:
    meta_path = paths.data("interim", "ingest_meta.json")
    meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}
    meta[fonte] = {
        "arquivo": Path(path).name,
        "sha256": sha256(Path(path)),
        "tamanho_bytes": Path(path).stat().st_size,
        "modificado_em": dt.datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat(timespec="seconds"),
        "n_registros": n,
        "ingerido_em": dt.datetime.now().isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")


def ingest_fonte(fonte: str, arquivo: str | None = None) -> int:
    cfg = config.sources()[fonte]
    path = latest_raw(fonte, arquivo)
    interim = paths.ensure(paths.data("interim"))

    if cfg["tipo"] == "geo":
        import geopandas as gpd

        gdf = read_geo(path)
        std = standardize(pd.DataFrame(gdf.drop(columns="geometry")), fonte, cfg)
        geo = gpd.GeoDataFrame(
            {"chave_fonte": std["chave_fonte"].values},
            geometry=gdf.loc[std.index, "geometry"].values, crs=4326,
        )
        gp = interim / f"{fonte}.gpkg"
        if gp.exists():
            gp.unlink()
        geo.to_file(gp, driver="GPKG", layer=fonte)
    else:
        std = standardize(read_table(path), fonte, cfg)

    std.to_csv(interim / f"{fonte}.csv", index=False)
    _update_meta(fonte, path, len(std))
    print(f"[ingest] {fonte}: {len(std)} registros  <- {Path(path).name}")
    return len(std)


def ingest_all(arquivos: dict[str, str] | None = None, fontes: list[str] | None = None) -> list[str]:
    done = []
    for fonte in fontes or list(config.sources()):
        try:
            ingest_fonte(fonte, (arquivos or {}).get(fonte))
            done.append(fonte)
        except FileNotFoundError as e:
            print(f"[ingest] {fonte}: pulado ({e})")
    relatorio_fases_nao_mapeadas()
    return done


def relatorio_fases_nao_mapeadas() -> None:
    frames = [pd.read_csv(p, dtype=str).fillna("") for p in paths.data("interim").glob("*.csv")
              if p.stem in config.sources()]
    if not frames:
        return
    df = pd.concat(frames)
    miss = df[(df["fase_origem"] != "") & (df["fase"] == "")]
    rep = (miss.groupby(["fonte", "fase_origem"])
           .agg(n=("nome_original", "size"), exemplos=("nome_original", lambda x: " | ".join(list(x)[:4])))
           .reset_index().sort_values(["fonte", "n"], ascending=[True, False]))
    out = paths.ensure(paths.data("processed", "relatorios")) / "fases_nao_mapeadas.csv"
    rep.to_csv(out, index=False)
    if len(rep):
        print(f"[ingest] {len(rep)} rótulos de fase não mapeados -> {out} (ajuste config/fases.yml)")
