import yaml

from . import paths


def load(name: str) -> dict:
    with open(paths.config(name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def sources() -> dict:
    return load("sources.yml")["fontes"]


def settings() -> dict:
    return load("settings.yml")


def fases() -> dict:
    return load("fases.yml")
