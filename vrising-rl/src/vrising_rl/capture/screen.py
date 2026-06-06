"""Capture d'écran pour l'approche "vision" (alternative au mod).

Sert si tu veux entraîner à partir des pixels plutôt que de l'état exposé par le
mod. Beaucoup plus dur à apprendre, mais ne nécessite aucun accès interne au jeu.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


class ScreenCapture:
    """Capture une région de l'écran et la renvoie en image numpy (H, W, 3)."""

    def __init__(self, region: Optional[Tuple[int, int, int, int]] = None,
                 resize: Optional[Tuple[int, int]] = (84, 84)) -> None:
        # region = (left, top, width, height) ; None = plein écran principal
        self.region = region
        self.resize = resize
        self._sct = None

    def _ensure(self):
        if self._sct is None:
            try:
                import mss  # import paresseux : nécessite un affichage
            except ImportError as exc:  # pragma: no cover
                raise ImportError("pip install mss") from exc
            self._sct = mss.mss()
        return self._sct

    def grab(self) -> np.ndarray:
        sct = self._ensure()
        if self.region is None:
            monitor = sct.monitors[1]
        else:
            left, top, width, height = self.region
            monitor = {"left": left, "top": top, "width": width, "height": height}
        raw = np.asarray(sct.grab(monitor))[:, :, :3]  # BGRA -> BGR
        if self.resize is not None:
            try:
                import cv2
                raw = cv2.resize(raw, self.resize, interpolation=cv2.INTER_AREA)
            except ImportError:  # pragma: no cover
                pass
        return raw

    def close(self) -> None:
        if self._sct is not None:
            self._sct.close()
            self._sct = None
