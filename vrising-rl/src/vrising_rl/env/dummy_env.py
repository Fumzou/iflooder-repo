"""Environnement FACTICE pour tester toute la chaîne RL sans le jeu.

Il imite l'interface de VRisingEnv (même observation_space / action_space que la
config) avec une mini-tâche apprenable : un "boss" a des PV ; l'action
`primary_attack` lui inflige des dégâts, les autres actions sont neutres ou
risquées. L'agent doit apprendre à attaquer pour tuer le boss vite tout en
gardant ses PV. Pratique pour valider train.py / evaluate.py.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as exc:  # pragma: no cover
    raise ImportError("Installe gymnasium : pip install -r requirements.txt") from exc

from ..utils import load_config


class DummyVRisingEnv(gym.Env):
    """Simulateur léger : un combat de boss simplifié."""

    metadata = {"render_modes": ["human"]}

    def __init__(self, config: Optional[Any] = None) -> None:
        super().__init__()
        self.cfg = config or load_config()
        self.actions = list(self.cfg.env.actions)
        self.obs_size = int(self.cfg.env.observation_size)
        self.max_episode_steps = int(self.cfg.env.max_episode_steps)

        self.action_space = spaces.Discrete(len(self.actions))
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self.obs_size,), dtype=np.float32
        )

        # indices d'action "utiles" si présents dans la config
        self._attack_idx = self._index_of("primary_attack")
        self._dodge_idx = self._index_of("dodge")

        self._reset_state()

    def _index_of(self, name: str) -> int:
        return self.actions.index(name) if name in self.actions else -1

    def _reset_state(self) -> None:
        self.player_hp = 100.0
        self.boss_hp = 300.0
        self.steps = 0
        self.rng = getattr(self, "rng", np.random.default_rng())

    def _make_obs(self) -> np.ndarray:
        obs = np.zeros(self.obs_size, dtype=np.float32)
        obs[0] = self.player_hp / 100.0
        obs[1] = self.boss_hp / 300.0
        obs[2] = self.steps / self.max_episode_steps
        return obs

    def reset(self, *, seed: Optional[int] = None, options=None
              ) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self._reset_state()
        return self._make_obs(), {"player_hp": self.player_hp, "boss_hp": self.boss_hp}

    def step(self, action: int
             ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        action = int(action)
        reward = -0.01  # pénalité de temps

        # Le boss tape, sauf si on esquive (réduit les dégâts).
        incoming = float(self.rng.uniform(1.0, 4.0))
        if action == self._dodge_idx:
            incoming *= 0.2
        self.player_hp -= incoming
        reward -= 0.1 * incoming

        # Attaquer fait des dégâts au boss.
        if action == self._attack_idx:
            dmg = float(self.rng.uniform(8.0, 14.0))
            self.boss_hp -= dmg
            reward += 0.2 * dmg

        self.steps += 1
        terminated = False
        if self.boss_hp <= 0:
            reward += 200.0          # boss vaincu
            terminated = True
        if self.player_hp <= 0:
            reward -= 200.0          # mort
            terminated = True
        truncated = self.steps >= self.max_episode_steps

        info = {"player_hp": max(0.0, self.player_hp), "boss_hp": max(0.0, self.boss_hp)}
        return self._make_obs(), reward, terminated, truncated, info

    def render(self):  # pragma: no cover - debug humain
        print(f"step={self.steps:4d}  player={self.player_hp:6.1f}  boss={self.boss_hp:6.1f}")
