"""Évalue un modèle entraîné. Ex : python scripts/evaluate.py models/ppo_vrising_dummy_final.zip"""
import argparse

import _bootstrap  # noqa: F401

from vrising_rl.agents import evaluate


def main() -> None:
    ap = argparse.ArgumentParser(description="Évaluation d'un agent PPO.")
    ap.add_argument("model", help="Chemin du .zip du modèle.")
    ap.add_argument("--env", default="dummy", choices=["dummy", "vrising"])
    ap.add_argument("--episodes", type=int, default=5)
    args = ap.parse_args()
    evaluate(args.model, env_name=args.env, episodes=args.episodes)


if __name__ == "__main__":
    main()
