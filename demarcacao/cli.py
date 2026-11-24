"""python -m demarcacao <comando>"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

from . import build, config, export, history, ingest, match, paths, refs, validate


def cmd_inspect(a) -> None:
    p = Path(a.arquivo)
    ext = p.suffix.lower()
    pd.set_option("display.width", 200, "display.max_columns", 30, "display.max_colwidth", 40)
    if ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(p) as pdf:
            print(f"{len(pdf.pages)} páginas")
            for i, page in enumerate(pdf.pages[:3], 1):
                tabs = page.extract_tables()
                print(f"--- página {i}: {len(tabs)} tabela(s)")
                for t in tabs[:1]:
                    for row in t[:4]:
                        print([(c or "").replace("\n", " ")[:25] for c in row])
        print("\nDica: se as colunas saírem bagunçadas, converta o PDF para CSV/XLSX e ponha em data/raw/<fonte>/.")
    elif ext in (".zip", ".shp", ".gpkg", ".geojson"):
        gdf = ingest.read_geo(p)
        print(f"{len(gdf)} feições; CRS={gdf.crs}\nColunas: {list(gdf.columns)}")
        print(pd.DataFrame(gdf.drop(columns='geometry')).head(8))
    else:
        df = ingest.read_table(p)
        print(f"{len(df)} linhas\nColunas: {list(df.columns)}")
        print(df.head(8))


def cmd_fetch(a) -> None:
    import requests
    for fonte, cfg in config.sources().items():
        if a.fonte and fonte != a.fonte:
            continue
        url = cfg.get("url")
        if not url:
            print(f"[fetch] {fonte}: sem 'url' em config/sources.yml. Baixe manualmente em {cfg.get('pagina')} "
                  f"e salve em data/raw/{fonte}/")
            continue
        ext = Path(url.split("?")[0]).suffix or ".bin"
        dest = paths.ensure(paths.data("raw", fonte)) / f"{fonte}_{dt.date.today().isoformat()}{ext}"
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        print(f"[fetch] {fonte}: {dest}")


def cmd_status(_a) -> None:
    for fonte in config.sources():
        d = paths.data("raw", fonte)
        files = sorted(f for f in d.glob("*") if f.suffix.lower() in ingest.RAW_EXT)
        itm = paths.data("interim", f"{fonte}.csv")
        n = len(pd.read_csv(itm)) if itm.exists() else "-"
        print(f"{fonte:6s} raw={[f.name for f in files] or 'NENHUM'}  interim={n}")
    t = paths.data("processed", "terras.csv")
    print("terras.csv:", len(pd.read_csv(t)) if t.exists() else "não gerado")
    snaps = sorted(f.name[:-7] for f in paths.data("history", "snapshots").glob("*.csv.gz"))
    print("snapshots:", snaps[-3:] or "nenhum")
    print("ref IBGE:", "ok" if paths.data("ref", "municipios.csv").exists() else "falta -> fetch-ref")


def cmd_update(a) -> None:
    done = ingest.ingest_all()
    if not done:
        sys.exit("Nenhuma fonte ingerida. Coloque arquivos em data/raw/<fonte>/ (veja README).")
    match.run(a.data)
    build.run()
    history.snapshot(a.data)
    export.run()
    sys.exit(validate.run())


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="demarcacao")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("inspect", help="mostra colunas/amostra de um arquivo bruto")
    s.add_argument("arquivo")
    s.set_defaults(fn=cmd_inspect)

    sub.add_parser("fetch-ref", help="baixa municípios/UFs do IBGE").set_defaults(fn=lambda a: refs.fetch_ref())

    s = sub.add_parser("fetch", help="baixa fontes que tenham 'url' em config/sources.yml")
    s.add_argument("--fonte")
    s.set_defaults(fn=cmd_fetch)

    s = sub.add_parser("ingest", help="raw -> interim")
    s.add_argument("--fonte")
    s.add_argument("--arquivo")
    s.set_defaults(fn=lambda a: ingest.ingest_fonte(a.fonte, a.arquivo) if a.fonte else ingest.ingest_all())

    s = sub.add_parser("match", help="cruza fontes e atribui terra_id")
    s.add_argument("--data")
    s.set_defaults(fn=lambda a: match.run(a.data))

    sub.add_parser("build", help="gera terras.csv e geometrias").set_defaults(fn=lambda a: build.run())

    s = sub.add_parser("snapshot", help="compara com o snapshot anterior e grava histórico")
    s.add_argument("--data", help="AAAA-MM-DD (padrão: hoje)")
    s.set_defaults(fn=lambda a: history.snapshot(a.data))

    sub.add_parser("export", help="gera site/data/").set_defaults(fn=lambda a: export.run())
    sub.add_parser("validate", help="checagens de integridade").set_defaults(fn=lambda a: sys.exit(validate.run()))
    sub.add_parser("status", help="o que há em cada etapa").set_defaults(fn=cmd_status)

    s = sub.add_parser("update", help="pipeline completo")
    s.add_argument("--data", help="AAAA-MM-DD (padrão: hoje)")
    s.set_defaults(fn=cmd_update)

    a = ap.parse_args(argv)
    a.fn(a)
