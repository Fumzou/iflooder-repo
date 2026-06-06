"""Chargement de la configuration YAML."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

# Racine du projet = deux niveaux au-dessus de src/vrising_rl/utils/
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class Config(dict):
    """Dictionnaire avec accès par attribut (config.bridge.port)."""

    def __getattr__(self, item: str) -> Any:
        try:
            value = self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc
        if isinstance(value, dict) and not isinstance(value, Config):
            value = Config(value)
            self[item] = value
        return value


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Charge la config YAML et renvoie un objet Config navigable par attribut."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config introuvable : {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data: Dict[str, Any] = yaml.safe_load(fh)
    return Config(data)
