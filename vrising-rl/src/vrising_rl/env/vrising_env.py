"""Environnement Gymnasium connecté au vrai jeu via le mod (bridge TCP).

Observation : vecteur de floats (taille = env.observation_size).
Action      : Discrete(len(env.actions)).

La récompense est calculée côté Python à partir de l'état renvoyé par le mod,
afin de pouvoir l'ajuster sans recompiler le mod. Le mod PEUT aussi renvoyer
directement un champ "reward" ; dans ce cas il est ajouté tel quel.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

try:  # gymnasium est la dépendance standard ; on reste tolérant.
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as exc:  # pragma: no cover
    raise ImportError("Installe gymnasium : pip install -r requirements.txt") from exc

from ..utils import load_config
from .bridge import GameBridge, BridgeError


class VRisingEnv(gym.Env):
    """Environnement RL relié à V Rising via le mod VRisingRLBridge."""

    metadata = {"render_modes": []}

    def __init__(self, config: Optional[Any] = None) -> None:
        super().__init__()
        self.cfg = config or load_config()

        self.actions = list(self.cfg.env.actions)
        obs_size = int(self.cfg.env.observation_size)

        self.action_space = spaces.Discrete(len(self.actions))
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

        self.max_episode_steps = int(self.cfg.env.max_episode_steps)
        self.step_interval_s = float(self.cfg.env.step_interval_s)
        self._rw = self.cfg.env.reward

        self.bridge = GameBridge(
            host=self.cfg.bridge.host,
            port=int(self.cfg.bridge.port),
            timeout_s=float(self.cfg.bridge.timeout_s),
            connect_retries=int(self.cfg.bridge.connect_retries),
        )
        self._connected = False
        self._steps = 0
        self._prev: Dict[str, Any] = {}

    # -- helpers ------------------------------------------------------------
    def _ensure_connected(self) -> None:
        if not self._connected:
            self.bridge.connect()
            self._connected = True

    def _to_obs(self, raw_obs) -> np.ndarray:
        arr = np.asarray(raw_obs, dtype=np.float32)
        if arr.shape != self.observation_space.shape:
            raise BridgeError(
                f"Taille d'observation reçue {arr.shape} != attendue "
                f"{self.observation_space.shape}. Vérifie env.observation_size "
                f"dans config.yaml et ce que renvoie le mod."
            )
        return arr

    def _compute_reward(self, info: Dict[str, Any]) -> float:
        """Récompense façonnée à partir des deltas d'état (info)."""
        r = float(info.get("reward", 0.0))  # bonus éventuel envoyé par le mod
        prev, cur = self._prev, info

        def delta(key: str) -> float:
            return float(cur.get(key, 0.0)) - float(prev.get(key, 0.0))

        if prev:
            r += self._rw.damage_dealt * max(0.0, delta("total_damage_dealt"))
            r += self._rw.damage_taken * max(0.0, -delta("player_hp"))
            r += self._rw.enemy_killed * max(0.0, delta("enemies_killed"))
            r += self._rw.gear_level_gain * max(0.0, delta("gear_level"))
            r += self._rw.boss_killed * max(0.0, delta("bosses_killed"))
        if info.get("player_dead"):
            r += self._rw.player_died
        r += self._rw.time_penalty
        return r

    # -- API Gymnasium ------------------------------------------------------
    def reset(self, *, seed: Optional[int] = None, options=None
              ) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)
        self._ensure_connected()
        resp = self.bridge.request({"cmd": "reset"})
        self._steps = 0
        info = dict(resp.get("info", {}))
        self._prev = info
        return self._to_obs(resp["obs"]), info

    def step(self, action: int
             ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        self._ensure_connected()
        action = int(action)
        resp = self.bridge.request({"cmd": "step", "action": action})

        if self.step_interval_s > 0:
            time.sleep(self.step_interval_s)

        obs = self._to_obs(resp["obs"])
        info = dict(resp.get("info", {}))
        reward = self._compute_reward(info)
        self._prev = info

        self._steps += 1
        terminated = bool(resp.get("terminated", False)) or bool(info.get("player_dead"))
        truncated = bool(resp.get("truncated", False)) or self._steps >= self.max_episode_steps
        return obs, reward, terminated, truncated, info

    def close(self) -> None:
        if self._connected:
            try:
                self.bridge.request({"cmd": "close"})
            except BridgeError:
                pass
            self.bridge.close()
            self._connected = False
