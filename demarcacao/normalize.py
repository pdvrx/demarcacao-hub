"""Normalização de nomes, UFs, números e rótulos de fase."""
from __future__ import annotations

import re
import unicodedata

from . import config, paths
from .schema import UFS

PREFIX_TOKENS = {
    "terra", "terras", "indigena", "indigenas", "ti", "t", "i",
    "reserva", "ri", "parque", "pi", "colonia", "agricola",
}
STOP = {"de", "do", "da", "dos", "das", "e"}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))


def norm_text(s) -> str:
    """minúsculo, sem acento, só letras/números separados por espaço."""
    s = strip_accents("" if s is None else s).lower()
    s = re.sub(r"[\u2019'`\u00b4]", "", s)  # apóstrofos colam as letras: Zo’é -> zoe
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_name(s) -> str:
    """Nome de terra sem prefixos ('Terra Indígena', 'TI'...) e sem preposições."""
    toks = norm_text(s).split()
    while toks and toks[0] in PREFIX_TOKENS:
        toks.pop(0)
    return " ".join(t for t in toks if t not in STOP)


def split_ufs(s) -> list[str]:
    found = re.findall(r"\b[A-Za-z]{2}\b", str(s or "").upper())
    return sorted({u for u in found if u in UFS})


def parse_float_br(s):
    """'1.234,56' -> 1234.56 ; '12.345' (milhar BR) -> 12345.0 ; retorna None se não der."""
    s = str(s or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_municipios(text, ufs: list[str] | None = None) -> list[tuple[str, str | None]]:
    """'Altamira, Anapu/PA; Porto Velho/RO' -> [('Altamira', None), ('Anapu', 'PA'), ...]"""
    out = []
    for piece in re.split(r"[;\n,]", str(text or "")):
        piece = piece.strip()
        if not piece or piece.lower() in ("nan", "none"):
            continue
        m = re.match(r"^(.*?)\s*[/\-]\s*([A-Za-z]{2})$", piece)
        if m and m.group(2).upper() in UFS:
            out.append((m.group(1).strip(), m.group(2).upper()))
        else:
            out.append((piece, None))
    return out


_rules_cache: dict[str, list] = {}


def _rules() -> list:
    key = str(paths.root())
    if key not in _rules_cache:
        _rules_cache[key] = config.fases()["regras_fase"]
    return _rules_cache[key]


def map_fase(label) -> str:
    """Rótulo de uma fonte -> fase canônica ('' se não reconhecido)."""
    n = norm_text(label)
    if not n:
        return ""
    for sub, fase in _rules():
        if sub in n:
            return fase or ""
    return ""


def map_modalidade(label) -> str:
    n = norm_text(label)
    for sub, mod in (
        ("reserva", "reserva_indigena"), ("dominial", "dominial"),
        ("interdit", "interditada"), ("tradicional", "tradicionalmente_ocupada"),
    ):
        if sub in n:
            return mod
    return "nao_informada"


def parse_data_ato(text) -> str:
    """'Decreto s/nº de 05/01/96' -> '1996-01-05' (ano de 2 dígitos: >=80 -> 19xx, senão 20xx).
    Retorna '' se não achar data. É uma INFERÊNCIA do texto: confira antes de citar."""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", str(text or ""))
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 1900 if y >= 80 else 2000
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"
