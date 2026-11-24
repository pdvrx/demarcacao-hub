import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """Projeto temporário com a mesma config do repositório e pastas de dados vazias."""
    shutil.copytree(REPO / "config", tmp_path / "config")
    for d in ("raw/funai", "raw/mpf", "raw/cimi", "raw/isa", "interim", "ref", "crosswalk",
              "processed/relatorios", "history/snapshots"):
        (tmp_path / "data" / d).mkdir(parents=True)
    shutil.copy(REPO / "data/history/marcos_gerais.csv", tmp_path / "data/history/marcos_gerais.csv")
    shutil.copy(REPO / "data/history/marcos_terra.csv", tmp_path / "data/history/marcos_terra.csv")
    (tmp_path / "site").mkdir()
    monkeypatch.setenv("DEMARCACAO_ROOT", str(tmp_path))
    return tmp_path
