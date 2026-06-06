"""Entraîne un agent PPO. Ex : python scripts/train.py --env dummy --timesteps 20000"""
import argparse

import _bootstrap  # noqa: F401

from vrising_rl.agents import train


def main() -> None:
    ap = argparse.ArgumentParser(description="Entraînement PPO V Rising RL.")
    ap.add_argument("--env", default="dummy", choices=["dummy", "vrising"])
    ap.add_argument("--timesteps", type=int, default=None,
                    help="Surcharge train.total_timesteps de la config.")
    args = ap.parse_args()
    train(env_name=args.env, timesteps=args.timesteps)


if __name__ == "__main__":
    main()
