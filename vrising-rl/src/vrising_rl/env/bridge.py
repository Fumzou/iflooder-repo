"""Client TCP qui dialogue avec le mod VRisingRLBridge tournant dans le jeu.

Protocole : une requête JSON par ligne, une réponse JSON par ligne.

  Python -> Mod   {"cmd": "reset"}
                  {"cmd": "step", "action": 5}
                  {"cmd": "ping"}

  Mod -> Python   {"obs": [...], "reward": 0.0, "terminated": false,
                   "truncated": false, "info": {...}}
"""
from __future__ import annotations

import json
import socket
import time
from typing import Any, Dict


class BridgeError(RuntimeError):
    """Erreur de communication avec le mod du jeu."""


class GameBridge:
    """Connexion TCP bas niveau, en lignes JSON, vers le mod du jeu."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        timeout_s: float = 10.0,
        connect_retries: int = 5,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.connect_retries = connect_retries
        self._sock: socket.socket | None = None
        self._buf = b""

    # -- cycle de vie -------------------------------------------------------
    def connect(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, self.connect_retries + 1):
            try:
                self._sock = socket.create_connection(
                    (self.host, self.port), timeout=self.timeout_s
                )
                self._sock.settimeout(self.timeout_s)
                return
            except OSError as exc:  # pragma: no cover - dépend du réseau
                last_exc = exc
                wait = min(2 ** attempt, 16)
                print(f"[bridge] connexion impossible ({exc}); retry dans {wait}s "
                      f"({attempt}/{self.connect_retries})")
                time.sleep(wait)
        raise BridgeError(
            f"Impossible de se connecter au mod sur {self.host}:{self.port}. "
            f"Le jeu et le mod VRisingRLBridge sont-ils lancés ?"
        ) from last_exc

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # -- échange ------------------------------------------------------------
    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Envoie une commande JSON et renvoie la réponse JSON décodée."""
        if self._sock is None:
            raise BridgeError("Bridge non connecté : appelle connect() d'abord.")
        line = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            self._sock.sendall(line)
            return self._read_line()
        except (OSError, ValueError) as exc:
            raise BridgeError(f"Échange avec le mod échoué : {exc}") from exc

    def _read_line(self) -> Dict[str, Any]:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)  # type: ignore[union-attr]
            if not chunk:
                raise BridgeError("Connexion fermée par le mod.")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\n", 1)
        return json.loads(raw.decode("utf-8"))

    # -- aide -------------------------------------------------------------
    def ping(self) -> bool:
        try:
            resp = self.request({"cmd": "ping"})
            return bool(resp.get("ok", False))
        except BridgeError:
            return False
