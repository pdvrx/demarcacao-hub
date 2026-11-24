"""Histórico: a cada rodada compara terras.csv com o snapshot anterior e registra os eventos.

  data/history/snapshots/AAAA-MM-DD.csv.gz  estado completo (só gravado quando algo mudou)
  data/history/eventos.csv                   o que mudou, quando foi OBSERVADO e em qual terra
  data/history/observacoes.csv               uma linha por rodada (inclusive as sem mudança)
  data/history/marcos_gerais.csv             linha do tempo jurídico-política nacional (curada à mão)
  data/history/marcos_terra.csv              atos oficiais por terra (curado à mão ou importado)

IMPORTANTE: 'data_observacao' é quando o seu pipeline viu a mudança, NÃO a data do ato oficial.
Datas de atos (portarias, decretos) vão em marcos_terra.csv, com fonte.
"""
from __future__ import annotations

import datetime as dt
import hashlib

import pandas as pd

from . import paths
from .schema import CAMPOS_MONITORADOS

EV_COLS = ["data_observacao", "terra_id", "nome", "tipo", "campo", "valor_anterior", "valor_novo"]
OBS_COLS = ["data_observacao", "n_terras", "hash", "houve_mudanca", "n_eventos"]


def _read(path, cols):
    return pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame(columns=cols)


def _hash(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()[:16]


def _same(campo: str, a: str, b: str) -> bool:
    if campo == "area_ha":
        try:
            return abs(float(a or 0) - float(b or 0)) < 0.01
        except ValueError:
            return a == b
    return a == b


def snapshot(data: str | None = None) -> pd.DataFrame:
    data = data or dt.date.today().isoformat()
    cur = pd.read_csv(paths.data("processed", "terras.csv"), dtype=str).fillna("")
    hist = paths.ensure(paths.data("history"))
    sdir = paths.ensure(hist / "snapshots")
    dates = sorted(f.name[:-7] for f in sdir.glob("*.csv.gz"))
    prev_dates = [d for d in dates if d < data]

    events, changed, baseline = [], True, not prev_dates
    if prev_dates:
        prev = pd.read_csv(sdir / f"{prev_dates[-1]}.csv.gz", dtype=str).fillna("")
        changed = _hash(cur) != _hash(prev)
        p, c = prev.set_index("terra_id"), cur.set_index("terra_id")
        for tid in sorted(set(c.index) - set(p.index)):
            events.append([data, tid, c.at[tid, "nome"], "nova_terra", "", "", c.at[tid, "fase"]])
        fus_p = paths.data("crosswalk", "fusoes.csv")
        fus = dict(zip(*[pd.read_csv(fus_p, dtype=str)[k] for k in ("terra_removida", "terra_destino")])) if fus_p.exists() else {}
        for tid in sorted(set(p.index) - set(c.index)):
            if tid in fus:
                events.append([data, tid, p.at[tid, "nome"], "fundida_em", "", tid, fus[tid]])
            else:
                events.append([data, tid, p.at[tid, "nome"], "removida_da_base", "", p.at[tid, "fase"], ""])
        for tid in sorted(set(p.index) & set(c.index)):
            for campo in CAMPOS_MONITORADOS:
                a, b = p.at[tid, campo], c.at[tid, campo]
                if not _same(campo, a, b):
                    events.append([data, tid, c.at[tid, "nome"], "mudanca", campo, a, b])

    snap = sdir / f"{data}.csv.gz"
    if changed:
        cur.to_csv(snap, index=False, compression="gzip")
    elif snap.exists():
        snap.unlink()

    ev = _read(hist / "eventos.csv", EV_COLS)
    ev = pd.concat([ev[ev["data_observacao"] != data], pd.DataFrame(events, columns=EV_COLS)], ignore_index=True)
    ev.sort_values(["data_observacao", "terra_id", "campo"]).to_csv(hist / "eventos.csv", index=False)

    obs = _read(hist / "observacoes.csv", OBS_COLS)
    obs = obs[obs["data_observacao"] != data]
    obs = pd.concat([obs, pd.DataFrame([[data, len(cur), _hash(cur), str(changed or baseline).lower(), len(events)]],
                                       columns=OBS_COLS)], ignore_index=True)
    obs.sort_values("data_observacao").to_csv(hist / "observacoes.csv", index=False)

    label = "baseline (primeira observação)" if baseline else f"{len(events)} eventos"
    print(f"[history] {data}: {label}; snapshot {'gravado' if changed else 'inalterado'}")
    return pd.DataFrame(events, columns=EV_COLS)
