"""Cruzamento entre fontes: dá a cada terra um ID interno estável (TI0001...).

Arquivos (versionados, editáveis):
  data/crosswalk/terras_ids.csv      terra_id, nome_canonico, criado_em
  data/crosswalk/fontes_ids.csv      fonte, chave_fonte, nome_original, ufs, terra_id, status, score, atualizado_em
  data/crosswalk/revisar.csv         pares prováveis para conferência humana (gerado a cada rodada; coluna 'decisao' é sua)
  data/crosswalk/pares_distintos.csv pares que você decidiu que NÃO são a mesma terra (nunca mais são sugeridos/fundidos)
  data/crosswalk/fusoes.csv          log de terras fundidas (terra_removida -> terra_destino)

Revisão: abra revisar.csv no Excel, preencha 'decisao' com sim ou nao, salve como CSV e rode `update` de novo.
  sim -> a linha de fonte passa para a terra candidata (status 'confirmado'; nunca mais é alterada)
  nao -> o par vira 'distinto' e não volta a aparecer
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from rapidfuzz import fuzz

from . import config, paths
from .normalize import normalize_name

XW_COLS = ["fonte", "chave_fonte", "nome_original", "ufs", "terra_id", "status", "score", "atualizado_em"]
ID_COLS = ["terra_id", "nome_canonico", "criado_em"]
REV_COLS = ["decisao", "fonte", "chave_fonte", "nome_original", "ufs", "municipios", "area_ha", "terra_id_atual",
            "candidato_id", "candidato_nome", "candidato_fontes", "candidato_municipios", "candidato_area_ha",
            "score", "obs"]
_SUBS = (("ss", "c"), ("k", "c"), ("y", "i"))


# ----------------------------------------------------------------------------- similaridade
def key(nome: str, ufs) -> str:
    """Chave de comparação: sem prefixos/UF final/'(RI)' e com grafias equivalentes (k=c, y=i, ss=c)."""
    toks = normalize_name(nome).split()
    ufl = {u.lower() for u in ufs}
    while len(toks) > 1 and (toks[-1] in ("ri", "ti") or toks[-1] in ufl):
        toks.pop()
    s = " ".join(toks)
    for a, b in _SUBS:
        s = s.replace(a, b)
    return s


def score(a: str, b: str) -> float:
    return max(fuzz.token_sort_ratio(a, b), fuzz.ratio(a.replace(" ", ""), b.replace(" ", "")))


def _ufs(s) -> set:
    return {u for u in str(s).split(";") if u}


# ----------------------------------------------------------------------------- IO
def read_flex(path) -> pd.DataFrame:
    """Lê CSV salvo pelo Excel (';' ou ',', UTF-8 ou cp1252)."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc, dtype=str).fillna("")
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Não consegui ler {path}")


def _read(path, cols):
    return read_flex(path) if path.exists() else pd.DataFrame(columns=cols)


def load_registros(prio: list[str]) -> pd.DataFrame:
    frames = [pd.read_csv(paths.data("interim", f"{f}.csv"), dtype=str).fillna("")
              for f in prio if paths.data("interim", f"{f}.csv").exists()]
    if not frames:
        raise FileNotFoundError("Nada em data/interim/. Rode `python -m demarcacao ingest` primeiro.")
    return pd.concat(frames, ignore_index=True)


# ----------------------------------------------------------------------------- núcleo
class Matcher:
    def __init__(self, xw, ids, distintos, S, cfgs):
        self.xw, self.ids, self.distintos = xw, ids, distintos
        self.prio = S["prioridade_fontes"]
        self.rank = {f: i for i, f in enumerate(self.prio)}
        self.auto, self.rev = S["match"]["limiar_auto"], S["match"]["limiar_revisar"]
        self.cfgs = cfgs
        self.fusoes: list[dict] = []
        self.rebuild()

    def rebuild(self):
        self.pool: dict[str, dict] = {}
        for r in self.xw.itertuples():
            self.add(r.terra_id, r.nome_original, r.ufs, r.fonte)

    def add(self, tid, nome, ufs, fonte):
        p = self.pool.setdefault(tid, {"keys": set(), "ufs": set(), "fontes": set()})
        p["keys"].add(key(nome, _ufs(ufs)))
        p["ufs"] |= _ufs(ufs)
        p["fontes"].add(fonte)

    def min_rank(self, tid) -> int:
        return min(self.rank.get(f, 99) for f in self.pool[tid]["fontes"])

    def candidates(self, nome, ufs, fonte, own=None):
        """Até 3 terras parecidas (score >= limiar_revisar), da mais à menos parecida."""
        k, ufs = key(nome, _ufs(ufs)), _ufs(ufs)
        multi = self.cfgs.get(fonte, {}).get("permite_varias_linhas", False)
        out = []
        for tid, p in self.pool.items():
            if tid == own or (own and frozenset((own, tid)) in self.distintos):
                continue
            if not multi and fonte in p["fontes"]:
                continue  # essa fonte já tem uma linha para essa terra: são terras distintas
            if ufs and p["ufs"] and not (ufs & p["ufs"]):
                continue
            sc = max(score(k, kk) for kk in p["keys"])
            if sc >= self.rev:
                out.append((sc, tid))
        return sorted(out, reverse=True)[:3]

    def unique_auto(self, cands) -> str | None:
        """Candidata única acima do limiar automático (empate entre duas => None, vai para revisão)."""
        if not cands or cands[0][0] < self.auto:
            return None
        top = [c for c in cands if c[0] >= cands[0][0] - 0.5]
        return top[0][1] if len(top) == 1 else None


def _next_id(ids, fusoes) -> int:
    nums = [int(t[2:]) for t in list(ids["terra_id"]) + list(fusoes["terra_removida"]) if str(t).startswith("TI")]
    return 1 + max(nums or [0])


def _drop_orphans(m: Matcher, today: str, destino: str | None = None):
    vivos = set(m.xw["terra_id"])
    for tid in list(m.ids["terra_id"]):
        if tid not in vivos:
            m.ids = m.ids[m.ids["terra_id"] != tid]
            if destino:
                m.fusoes.append({"data": today, "terra_removida": tid, "terra_destino": destino})


def aplicar_revisao(m: Matcher, today: str) -> int:
    p = paths.data("crosswalk", "revisar.csv")
    if not p.exists():
        return 0
    rev = read_flex(p)
    if "decisao" not in rev.columns:
        return 0
    n = 0
    for r in rev.itertuples():
        d = str(r.decisao).strip().lower()
        if d in ("sim", "s", "1", "x", "yes"):
            mask = (m.xw["fonte"] == r.fonte) & (m.xw["chave_fonte"] == r.chave_fonte)
            if not mask.any() or m.xw.loc[mask, "terra_id"].iloc[0] != r.terra_id_atual:
                print(f"[match] revisão ignorada (linha já mudou): {r.fonte} {r.chave_fonte}")
                continue
            if r.candidato_id not in set(m.ids["terra_id"]):
                print(f"[match] revisão ignorada (candidato inexistente): {r.candidato_id}")
                continue
            m.xw.loc[mask, ["terra_id", "status", "score", "atualizado_em"]] = [r.candidato_id, "confirmado", "100", today]
            _drop_orphans(m, today, destino=r.candidato_id)
            n += 1
        elif d in ("nao", "não", "n", "0", "no"):
            m.distintos.add(frozenset((r.terra_id_atual, r.candidato_id)))
            n += 1
    if n:
        print(f"[match] {n} decisões de revisão aplicadas")
    return n


def consolidar(m: Matcher, today: str) -> int:
    """Funde terras 'novo' (de uma linha só) em terras parecidas de fonte de maior prioridade."""
    total = 0
    for _ in range(5):
        merged = False
        counts = m.xw.groupby("terra_id").size()
        rows = m.xw[(m.xw["status"] == "novo") & (m.xw["terra_id"].map(counts) == 1)].copy()
        rows["_r"] = rows["fonte"].map(m.rank).fillna(99)
        for r in rows.sort_values("_r", ascending=False).itertuples():
            cur = m.xw[(m.xw["fonte"] == r.fonte) & (m.xw["chave_fonte"] == r.chave_fonte)].iloc[0]
            if (m.xw["terra_id"] == cur["terra_id"]).sum() != 1:
                continue
            cands = m.candidates(r.nome_original, r.ufs, r.fonte, own=cur["terra_id"])
            tgt = m.unique_auto(cands)
            if tgt and m.rank.get(r.fonte, 99) >= m.min_rank(tgt):
                mask = (m.xw["fonte"] == r.fonte) & (m.xw["chave_fonte"] == r.chave_fonte)
                m.xw.loc[mask, ["terra_id", "status", "score", "atualizado_em"]] = [tgt, "auto", str(round(cands[0][0], 1)), today]
                _drop_orphans(m, today, destino=tgt)
                m.rebuild()
                merged = True
                total += 1
        if not merged:
            break
    return total


def gerar_revisar(m: Matcher, reg: pd.DataFrame) -> int:
    info = {(r.fonte, r.chave_fonte): (r.municipios, r.area_ha) for r in reg.itertuples()}
    canon = dict(zip(m.ids["terra_id"], m.ids["nome_canonico"]))
    best_row = {}
    for r in m.xw.assign(_r=m.xw["fonte"].map(m.rank).fillna(99)).sort_values("_r").itertuples():
        best_row.setdefault(r.terra_id, r)
    rows, seen = [], set()
    for r in m.xw[m.xw["status"] == "novo"].itertuples():
        cands = m.candidates(r.nome_original, r.ufs, r.fonte, own=r.terra_id)
        tied = bool(cands) and cands[0][0] >= m.auto and len([c for c in cands if c[0] >= cands[0][0] - 0.5]) > 1
        for sc, tid in cands:
            if m.rank.get(r.fonte, 99) < m.min_rank(tid):
                continue  # a linha é de fonte mais prioritária: a outra terra é que deve ser movida
            pair = frozenset((r.terra_id, tid))
            if pair in seen:
                continue
            seen.add(pair)
            cb = best_row.get(tid)
            cm = info.get((cb.fonte, cb.chave_fonte), ("", "")) if cb else ("", "")
            mu, ar = info.get((r.fonte, r.chave_fonte), ("", ""))
            rows.append({"decisao": "", "fonte": r.fonte, "chave_fonte": r.chave_fonte, "nome_original": r.nome_original,
                         "ufs": r.ufs, "municipios": mu, "area_ha": ar, "terra_id_atual": r.terra_id,
                         "candidato_id": tid, "candidato_nome": canon.get(tid, ""),
                         "candidato_fontes": ",".join(sorted(m.pool[tid]["fontes"])), "candidato_municipios": cm[0],
                         "candidato_area_ha": cm[1], "score": round(sc, 1),
                         "obs": "empate entre candidatas" if tied else ""})
    df = pd.DataFrame(rows, columns=REV_COLS)
    if len(df):
        df = df.sort_values("score", ascending=False)
    # ';' + UTF-8 com BOM: abre direto no Excel em português
    df.to_csv(paths.data("crosswalk", "revisar.csv"), index=False, sep=";", encoding="utf-8-sig")
    return len(df)


def run(today: str | None = None) -> pd.DataFrame:
    today = today or dt.date.today().isoformat()
    S, cfgs = config.settings(), config.sources()
    reg = load_registros(S["prioridade_fontes"])
    cw = paths.ensure(paths.data("crosswalk"))
    xw = _read(cw / "fontes_ids.csv", XW_COLS)
    ids = _read(cw / "terras_ids.csv", ID_COLS)
    fus = _read(cw / "fusoes.csv", ["data", "terra_removida", "terra_destino"])
    dist_df = _read(cw / "pares_distintos.csv", ["terra_a", "terra_b"])
    distintos = {frozenset((a, b)) for a, b in zip(dist_df["terra_a"], dist_df["terra_b"])}

    m = Matcher(xw, ids, distintos, S, cfgs)
    aplicar_revisao(m, today)
    m.rebuild()

    known = set(zip(m.xw["fonte"], m.xw["chave_fonte"]))
    n_next = _next_id(m.ids, fus)
    reg = reg.assign(_r=reg["fonte"].map(m.rank).fillna(99)).sort_values(["_r", "nome_norm", "chave_fonte"])
    novos_xw, novos_ids = [], []
    for r in reg.itertuples():
        if (r.fonte, r.chave_fonte) in known:
            continue
        cands = m.candidates(r.nome_original, r.ufs, r.fonte)
        tid = m.unique_auto(cands)
        if tid:
            status, sc = "auto", cands[0][0]
        else:
            tid, status, sc = f"TI{n_next:04d}", "novo", (cands[0][0] if cands else 0)
            n_next += 1
            novos_ids.append({"terra_id": tid, "nome_canonico": r.nome_original, "criado_em": today})
            m.ids = pd.concat([m.ids, pd.DataFrame([novos_ids[-1]])], ignore_index=True)
        row = {"fonte": r.fonte, "chave_fonte": r.chave_fonte, "nome_original": r.nome_original, "ufs": r.ufs,
               "terra_id": tid, "status": status, "score": str(round(sc, 1)), "atualizado_em": today}
        novos_xw.append(row)
        m.xw = pd.concat([m.xw, pd.DataFrame([row])], ignore_index=True)
        m.add(tid, r.nome_original, r.ufs, r.fonte)
        known.add((r.fonte, r.chave_fonte))

    n_fund = consolidar(m, today)
    n_rev = gerar_revisar(m, reg)

    xw = m.xw.sort_values(["terra_id", "fonte", "chave_fonte"])
    ids = m.ids.sort_values("terra_id")
    xw.to_csv(cw / "fontes_ids.csv", index=False)
    ids.to_csv(cw / "terras_ids.csv", index=False)
    if m.fusoes:
        pd.concat([fus, pd.DataFrame(m.fusoes)]).to_csv(cw / "fusoes.csv", index=False)
    pd.DataFrame([sorted(p) for p in m.distintos], columns=["terra_a", "terra_b"]).sort_values(
        ["terra_a", "terra_b"]).to_csv(cw / "pares_distintos.csv", index=False)
    print(f"[match] {len(ids)} terras; {len(novos_xw)} registros novos; {n_fund} fusões automáticas; "
          f"{n_rev} pares para revisar -> data/crosswalk/revisar.csv")
    return xw
