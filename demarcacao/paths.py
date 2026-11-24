"""Caminhos do projeto. DEMARCACAO_ROOT permite apontar para outra raiz (usado nos testes)."""
import os
from pathlib import Path


def root() -> Path:
    env = os.environ.get("DEMARCACAO_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[1]


def data(*parts) -> Path:
    return root().joinpath("data", *parts)


def config(*parts) -> Path:
    return root().joinpath("config", *parts)


def site(*parts) -> Path:
    return root().joinpath("site", *parts)


def ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
