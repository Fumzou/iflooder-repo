# Contrôle du collecteur sans le jeu

Ce projet compile `src/Mod/Character.cs` contre des **doublures typées** des composants du
jeu (`Stubs.cs`), lui fournit un personnage synthétique et vérifie ce qu'il publie.

```powershell
dotnet run --project tests\modcheck\modcheck.csproj -c Release
```

Il ne nécessite ni V Rising, ni BepInEx, ni les assemblies de référence.

**Ce qu'il prouve :** la logique du collecteur — découverte des champs par réflexion,
lecture des champs obfusqués sans libellé inventé, conservation des statistiques à zéro,
repli du bonus de l'exemplaire vers le modèle de l'objet, emplacement vide distingué d'un
emplacement illisible, durée négative traitée comme un effet permanent, jeu de
modificateurs illisible marqué inconnu plutôt que « aucun joyau ».

**Ce qu'il ne prouve pas :** que les vraies assemblies du jeu ont ces signatures. Les
doublures sont reconstituées à partir du code source de mods 1.1.x. Seule la compilation
du mod avec `scripts\Build.ps1` le confirme.
