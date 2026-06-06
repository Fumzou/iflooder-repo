# VRisingRLBridge — le mod (côté jeu)

Mod **BepInEx (IL2CPP)** qui ouvre un serveur TCP local pour exposer l'état du
joueur à l'agent RL Python et appliquer ses actions.

## Pré-requis

1. **Installer BepInEx pour V Rising** (version IL2CPP). Voir Thunderstore
   (`BepInExPack V Rising`) — c'est l'installeur standard de la communauté.
2. Lancer V Rising **une fois** avec BepInEx : ça génère les *interop assemblies*
   dans `VRising\BepInEx\interop\` (nécessaires pour compiler).
3. Avoir le **.NET 6 SDK** pour compiler.
4. (Recommandé) Les frameworks de mod communautaires **Bloodstone / Wetstone /
   VampireCommandFramework** facilitent l'accès à l'ECS et aux hooks d'Update.

## Compiler

```powershell
# Indique où est installé V Rising (sinon, édite le .csproj)
$env:VRISING_DIR = "C:\Program Files (x86)\Steam\steamapps\common\VRising"
dotnet build -c Release
```

Copie ensuite `bin\Release\net6.0\VRisingRLBridge.dll` dans
`VRising\BepInEx\plugins\`.

## Ce qui est déjà fait ✅

- Serveur TCP + protocole "ligne JSON" (`BridgeServer.cs`).
- Boucle thread-safe : le réseau dépose les requêtes, le jeu les traite sur son
  thread principal (`Plugin.Pump()`).
- Sérialisation de l'observation + info en JSON.

## Ce qu'il reste à câbler ⚠️ (marqué `TODO` dans `Plugin.cs`)

| Méthode | Rôle |
|---|---|
| `GetObservation()` | Lire l'entité joueur (PV, niveau d'équip., position, ennemis…) |
| `BuildInfoJson()`  | Remplir les stats utilisées pour la récompense |
| `ApplyAction(int)` | Traduire l'index d'action en input/commande de jeu |
| `ResetEpisode()`   | Remettre le joueur dans un état de départ reproductible |
| `Pump()` hook      | Appeler `Pump()` chaque frame (hook Update de Bloodstone/Wetstone) |

> Ces points dépendent de l'API ECS de V Rising, qui change parfois entre
> patches. Inspire-toi des mods existants (dépôts GitHub de la communauté
> V Rising modding) pour récupérer l'entité joueur et ses composants.

## Vérifier la liaison

Une fois le mod chargé et le jeu lancé :

```bash
# côté Python
python -c "from vrising_rl.env import GameBridge; b=GameBridge(); b.connect(); print('ping ok:', b.ping())"
```
