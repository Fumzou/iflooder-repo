"""Envoi clavier/souris vers le jeu (approche "vision").

⚠️ Sur Windows, la plupart des jeux ignorent pyautogui : il faut un envoi de
type DirectInput (pydirectinput) ou SendInput via pywin32. On charge ces libs
de façon paresseuse pour que le module s'importe quand même sous Linux (CI).

Mappe les noms d'actions de config.yaml vers de vraies touches/clics.
"""
from __future__ import annotations

from typing import Dict


# Correspondance action -> touche clavier (par défaut, ZQSD adaptable).
DEFAULT_KEY_MAP: Dict[str, str] = {
    "move_up": "w",
    "move_down": "s",
    "move_left": "a",
    "move_right": "d",
    "ability_q": "q",
    "ability_e": "e",
    "ability_r": "r",
    "dodge": "space",
    "interact": "f",
}

# Actions souris.
MOUSE_ACTIONS = {
    "primary_attack": "left",
    "weapon_skill_1": "right",
}


class GameController:
    """Traduit un nom d'action en entrée clavier/souris réelle."""

    def __init__(self, key_map: Dict[str, str] | None = None,
                 hold_s: float = 0.08, dry_run: bool = False) -> None:
        self.key_map = key_map or DEFAULT_KEY_MAP
        self.hold_s = hold_s
        self.dry_run = dry_run
        self._backend = None

    def _ensure_backend(self):
        if self._backend is None and not self.dry_run:
            try:
                import pydirectinput as backend  # Windows
                backend.PAUSE = 0.0
            except ImportError:
                try:
                    import pyautogui as backend  # cross-platform (souvent ignoré par les jeux)
                except ImportError as exc:  # pragma: no cover
                    raise ImportError(
                        "Aucun backend d'entrée. Sur le PC du jeu : "
                        "pip install -r requirements-windows.txt"
                    ) from exc
            self._backend = backend
        return self._backend

    def perform(self, action_name: str) -> None:
        if action_name == "idle":
            return
        if self.dry_run:
            print(f"[controller:dry-run] {action_name}")
            return
        backend = self._ensure_backend()
        if action_name in MOUSE_ACTIONS:
            backend.click(button=MOUSE_ACTIONS[action_name])
        elif action_name in self.key_map:
            key = self.key_map[action_name]
            backend.keyDown(key)
            backend.keyUp(key)
