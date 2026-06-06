# V Rising RL

Un projet d'apprentissage par renforcement (Reinforcement Learning) pour piloter un
agent dans **V Rising**, via un **mod BepInEx** qui expose l'état du jeu et reçoit les
actions.

> ⚠️ À n'utiliser que sur **ton serveur privé / solo**. L'automatisation peut enfreindre
> les conditions d'utilisation sur les serveurs officiels/PvP.

## Architecture

```
  ┌────────────────────┐        TCP / JSON         ┌──────────────────────┐
  │  V Rising + Mod     │  <───── observations ──── │  Python (cet entraîn.)│
  │  (BepInEx C#)       │  ─────── actions ──────>  │  Gymnasium + SB3 (PPO)│
  │  VRisingRLBridge    │                           │                       │
  └────────────────────┘                           └──────────────────────┘
```

- **`mod/VRisingRLBridge/`** : le mod C# (BepInEx) qui tourne *dans* le jeu. Il ouvre un
  serveur TCP local, envoie l'état du joueur (PV, niveau, position, ennemis…) et applique
  les actions reçues. **À compiler sur ton PC** (il a besoin des DLL de V Rising).
- **`src/vrising_rl/`** : le code Python.
  - `env/bridge.py` — client TCP qui parle au mod.
  - `env/vrising_env.py` — l'environnement Gymnasium (observation/action/récompense).
  - `env/dummy_env.py` — un environnement **factice** pour tester la boucle d'entraînement
    **sans le jeu**.
  - `actions/` + `capture/` — alternative « vision » (capture d'écran + clavier/souris).
  - `agents/trainer.py` — entraînement PPO (Stable-Baselines3).
- **`scripts/`** — `train.py`, `evaluate.py`, `test_env.py`.
- **`config/config.yaml`** — toute la configuration (réseau, espaces, hyperparamètres).

## Installation (côté Python)

```bash
cd vrising-rl
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
# Sur le PC qui pilote réellement le jeu (Windows) :
pip install -r requirements-windows.txt
```

## Démarrage rapide (sans le jeu)

Teste tout de suite que la chaîne RL fonctionne avec l'environnement factice :

```bash
python scripts/test_env.py            # vérifie l'env factice
python scripts/train.py --env dummy --timesteps 20000
tensorboard --logdir logs/            # suivre l'apprentissage
```

## Brancher sur le vrai jeu

1. Compile et installe le mod `VRisingRLBridge` (voir `mod/README.md`).
2. Lance V Rising en solo, charge ta partie.
3. Entraîne en pointant sur le bridge :

```bash
python scripts/train.py --env vrising --timesteps 1000000
```

## Avertissement « réalisme »

Faire apprendre un agent RL sur un jeu de survie/RPG complet est un **projet de recherche
lourd** (récompense difficile à définir, horizon temporel énorme, pas de simulation
accélérée). Commence **petit** : une tâche bien délimitée (ex. « battre un boss précis »,
« farmer une ressource ») avec une récompense claire, avant d'élargir.
