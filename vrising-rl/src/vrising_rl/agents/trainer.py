"""Entraînement / évaluation PPO (Stable-Baselines3)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..utils import load_config
from ..env import VRisingEnv, DummyVRisingEnv


def build_env(env_name: str, config: Any = None):
    """Fabrique l'environnement demandé : 'dummy' (hors-ligne) ou 'vrising'."""
    cfg = config or load_config()
    if env_name == "dummy":
        return DummyVRisingEnv(cfg)
    if env_name == "vrising":
        return VRisingEnv(cfg)
    raise ValueError(f"Environnement inconnu : {env_name!r} (attendu: dummy|vrising)")


def _make_model(env, cfg):
    from stable_baselines3 import PPO

    p = cfg.ppo
    return PPO(
        policy=p.policy,
        env=env,
        learning_rate=float(p.learning_rate),
        n_steps=int(p.n_steps),
        batch_size=int(p.batch_size),
        n_epochs=int(p.n_epochs),
        gamma=float(p.gamma),
        gae_lambda=float(p.gae_lambda),
        clip_range=float(p.clip_range),
        ent_coef=float(p.ent_coef),
        device=p.device,
        tensorboard_log=str(cfg.train.log_dir),
        verbose=1,
    )


def train(env_name: str = "dummy", timesteps: int | None = None,
          config: Any = None) -> str:
    from stable_baselines3.common.callbacks import CheckpointCallback

    cfg = config or load_config()
    total = int(timesteps or cfg.train.total_timesteps)

    models_dir = Path(cfg.train.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    Path(cfg.train.log_dir).mkdir(parents=True, exist_ok=True)

    env = build_env(env_name, cfg)
    model = _make_model(env, cfg)

    ckpt = CheckpointCallback(
        save_freq=int(cfg.train.save_freq),
        save_path=str(models_dir / "checkpoints"),
        name_prefix=cfg.train.run_name,
    )
    model.learn(total_timesteps=total, callback=ckpt,
                tb_log_name=cfg.train.run_name, progress_bar=False)

    out = models_dir / f"{cfg.train.run_name}_{env_name}_final.zip"
    model.save(str(out))
    env.close()
    print(f"[train] modèle sauvegardé : {out}")
    return str(out)


def evaluate(model_path: str, env_name: str = "dummy", episodes: int = 5,
             config: Any = None) -> float:
    from stable_baselines3 import PPO

    cfg = config or load_config()
    env = build_env(env_name, cfg)
    model = PPO.load(model_path)

    returns = []
    for ep in range(episodes):
        obs, _ = env.reset()
        done = False
        total = 0.0
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(int(action))
            total += reward
            done = terminated or truncated
        returns.append(total)
        print(f"[eval] épisode {ep + 1}/{episodes} : return = {total:.1f}")
    env.close()
    mean_ret = sum(returns) / len(returns)
    print(f"[eval] return moyen sur {episodes} épisodes : {mean_ret:.1f}")
    return mean_ret
