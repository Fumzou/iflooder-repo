"""Tests rapides de l'environnement factice et de la config."""
import numpy as np

from vrising_rl.utils import load_config
from vrising_rl.env import DummyVRisingEnv


def test_config_loads():
    cfg = load_config()
    assert cfg.bridge.port == 9000
    assert len(cfg.env.actions) >= 1


def test_dummy_env_api():
    env = DummyVRisingEnv()
    obs, info = env.reset(seed=0)
    assert env.observation_space.contains(obs)
    assert isinstance(info, dict)

    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
    assert env.observation_space.contains(obs)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool) and isinstance(truncated, bool)
    env.close()


def test_dummy_env_attack_kills_boss():
    """Attaquer en boucle doit finir par tuer le boss (récompense positive)."""
    env = DummyVRisingEnv()
    env.reset(seed=1)
    attack = env.actions.index("primary_attack")
    killed = False
    for _ in range(env.max_episode_steps):
        _, _, terminated, truncated, info = env.step(attack)
        if terminated and info["boss_hp"] <= 0:
            killed = True
            break
        if terminated or truncated:
            break
    assert killed, "Le boss devrait pouvoir être tué en attaquant."
    env.close()
