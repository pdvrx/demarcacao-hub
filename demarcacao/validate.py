"""Checagens de integridade. Retorna código de saída != 0 se houver erro."""
from __future__ import annotations

import pandas as pd

from . import paths
from .schema import FASE_INDEFINIDA, FASES, FASES_ESPECIAIS


def run() -> int:
    errors, warns = [], []
    p = paths.data("processed", "terras.csv")
    if not p.exists():
        print("[validate] terras.csv não existe; rode o build.")
        return 1
    t = pd.read_csv(p, dtype=str).fillna("")
    if t["terra_id"].duplicated().any():
        errors.append("terra_id duplicado em terras.csv")
    bad = t[~t["fase"].isin(FASES + FASES_ESPECIAIS + [FASE_INDEFINIDA])]
    if len(bad):
        errors.append(f"{len(bad)} terras com fase fora do vocabulário")

    cw = paths.data("crosswalk")
    if (cw / "fontes_ids.csv").exists() and (cw / "terras_ids.csv").exists():
        xw = pd.read_csv(cw / "fontes_ids.csv", dtype=str).fillna("")
        ids = set(pd.read_csv(cw / "terras_ids.csv", dtype=str)["terra_id"])
        orfas = set(xw["terra_id"]) - ids
        if orfas:
            errors.append(f"vínculos apontam para terra_id inexistente: {sorted(orfas)[:5]}")
        if xw.duplicated(["fonte", "chave_fonte"]).any():
            errors.append("(fonte, chave_fonte) duplicado em fontes_ids.csv")

    n_sem = int((t["precisao_geom"] == "nenhuma").sum())
    if n_sem:
        warns.append(f"{n_sem} terras sem localização (veja relatorios/sem_localizacao.csv)")
    n_ind = int((t["fase"] == FASE_INDEFINIDA).sum())
    if n_ind:
        warns.append(f"{n_ind} terras com fase indefinida (veja relatorios/fases_nao_mapeadas.csv)")
    n_div = int((t["divergencia_fase"] == "true").sum())
    if n_div:
        warns.append(f"{n_div} terras com fases divergentes entre fontes (relatorios/divergencias_fase.csv)")

    for w in warns:
        print("[validate] aviso:", w)
    for e in errors:
        print("[validate] ERRO:", e)
    if not errors:
        print(f"[validate] ok ({len(t)} terras)")
    return 1 if errors else 0
