"""Vérifie qu'un environnement respecte l'API Gymnasium et tourne quelques pas."""
import argparse

import _bootstrap  # noqa: F401  (ajoute src/ au path)

from vrising_rl.agents import build_env


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke test d'un environnement.")
    ap.add_argument("--env", default="dummy", choices=["dummy", "vrising"])
    ap.add_argument("--steps", type=int, default=200)
    args = ap.parse_args()

    env = build_env(args.env)
    print(f"observation_space = {env.observation_space}")
    print(f"action_space      = {env.action_space}")

    obs, info = env.reset(seed=0)
    assert env.observation_space.contains(obs), "obs hors de l'espace d'observation !"

    total = 0.0
    for i in range(args.steps):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        total += reward
        if terminated or truncated:
            print(f"  épisode terminé au pas {i + 1} (return={total:.1f}) -> reset")
            total = 0.0
            env.reset()
    env.close()
    print("OK : l'environnement fonctionne.")


if __name__ == "__main__":
    main()
