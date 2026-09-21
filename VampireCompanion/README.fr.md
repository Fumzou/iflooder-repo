# Vampire Companion 0.4.0

Assistant V Rising **côté client**, pour Codex / ChatGPT avec connexion MCP locale.

**Statut : archive de sources, à compiler puis à valider en jeu.** Cette version ajoute la lecture du personnage. Contrairement aux précédentes, **elle ne contient pas de binaires** : tu la compiles toi-même. Le mod compile désormais sans erreur ni avertissement contre les vraies assemblies de référence du jeu, ce qui n'avait pas pu être fait au moment de l'écriture ; **il n'a toujours pas été chargé dans une partie**. Les tests de la passerelle se font avec des données de test explicitement séparées ; aucune connexion à ta partie n'a été effectuée pendant le développement. Cible de compilation : références V Rising **1.1.12-r99041-b2**, BepInEx IL2CPP **6.0.0-be.733**, .NET 6.

Lire `VALIDATION.md` avant d'installer : il liste précisément ce qui a été vérifié et ce qui ne l'a pas été.

## Installation Windows

1. Extraire cette archive dans un dossier permanent, par exemple `C:\VampireCompanion`.
2. Installer le **SDK .NET 6** (ou un SDK compatible avec la cible net6.0), puis compiler les deux parties :

   ```powershell
   cd C:\VampireCompanion
   powershell -ExecutionPolicy Bypass -File scripts\Build.ps1
   ```

   Le script produit `release\BepInEx\plugins\VampireCompanion\VampireCompanion.dll` et `release\mcp\VampireCompanion.Mcp.exe`. **Si la compilation du mod échoue, conserver le message d'erreur complet** : il désigne le champ ou le composant dont la signature a changé, et le collecteur concerné peut être corrigé sans toucher au reste.
3. Installer le **BepInExPack pour V Rising** en suivant le [guide communautaire](https://wiki.vrisingmods.com/user/), puis lancer le jeu une fois et le fermer. Le mod se charge dans le client PC. Il ne s'installe pas sur le serveur auquel tu te connectes. Vérifier que le serveur autorise les mods client.
4. Copier `release\BepInEx\plugins\VampireCompanion\VampireCompanion.dll` dans le dossier `BepInEx\plugins\VampireCompanion\` du jeu (créer le dernier dossier).
5. Dans l'application de bureau ChatGPT/Codex sur **le même PC**, ouvrir les paramètres des serveurs MCP et ajouter un serveur **STDIO** nommé `vampire-companion`. Commande : chemin complet de `release\mcp\VampireCompanion.Mcp.exe`. Aucun argument ni clé API n'est nécessaire.
6. Relancer le jeu, rejoindre ta partie, ouvrir ton inventaire puis entrer dans le territoire ; ouvrir les coffres hors inventaire partagé et les stations que tu souhaites observer. Attendre quelques secondes.
7. Demander : **« Utilise vampire-companion : vérifie la connexion, puis donne-moi mes statistiques. »**

La passerelle Windows est autonome : elle inclut son runtime et ne demande ni Python ni Node.js. BepInEx fournit le runtime du mod. L'application ChatGPT mobile seule ne lance pas cet exécutable Windows. Le modèle reste un service en ligne ; les données retournées par les outils lui sont transmises.

Alternative avec Codex CLI :

```powershell
codex mcp add vampire-companion -- "C:\VampireCompanion\release\mcp\VampireCompanion.Mcp.exe"
```

Un installateur PowerShell facultatif est fourni dans `scripts\Install.ps1`. Il copie seulement le mod, sauvegarde la DLL précédente et affiche la commande MCP. L'installation manuelle ci-dessus suffit.

## Mise à jour depuis 0.1, 0.2 ou 0.3

Fermer V Rising et arrêter le serveur MCP dans l'application. Compiler cette version, puis remplacer la DLL du jeu **et** l'exécutable MCP. Les deux doivent venir de la même version : le format des données passe en **version 2**, et une passerelle 0.3 face à un mod 0.4 refuse de lire le snapshot avec un message explicite. Dans l'autre sens, une passerelle 0.4 lit encore un snapshot 0.3 et signale simplement l'absence des données de personnage. Si le chemin de l'exécutable a changé, modifier la commande du serveur MCP. `get_status` affiche la version du mod et celle du format, et l'initialisation MCP annonce celle de la passerelle.

## Nouveauté 0.4 : le personnage

Le mod lit maintenant ce qui manquait pour analyser un build.

| Donnée | Ce qui est publié |
|---|---|
| Statistiques finales | Le bloc `UnitStats` calculé par le jeu, champ par champ. En 1.1.12 ce composant porte 15 champs : puissances physique, magique, de récolte et de siège, résistances physique, magique et au feu, régénération passive, récupération de vie, réduction des dégâts et de ceux de corruption, soins reçus, réduction des contrôles, consommation de sang. **Les chances et dégâts critiques, les vitesses, les vols de vie et les bonus contre les types d'ennemis n'y sont pas** : voir la limite de couverture ci-dessous. |
| Sang | Type, qualité en pourcentage et quantité restante. Les bonus du sang sont des buffs : ils apparaissent dans `get_buffs`. |
| Équipement | Chaque emplacement : objet, durabilité, palier légendaire, infusion, modificateurs d'arme ancestrale, et les apports de statistiques que la pièce déclare. |
| Buffs | Potions, effets du sang, bonus permanents, avec durée totale, temps restant et apports de statistiques. |
| Sorts | Les emplacements de capacité et les joyaux qui y sont sertis, avec leur puissance. |

**La règle qui gouverne tout le reste :** le jeu a **déjà** intégré l'équipement, le sang et les buffs dans les statistiques finales. Les apports publiés à côté sont les *entrées* de ce calcul, pas un supplément. Les additionner au bloc final compterait chaque anneau deux fois. La passerelle le répète dans chaque réponse concernée, et les instructions MCP l'imposent au modèle.

`explain_stat` est le seul endroit où les deux se rencontrent : il met la valeur finale en face de chaque apport observé, additionne **uniquement** si tous les apports sont additifs, et publie le **reste inexpliqué**. Ce reste est normal — il contient la base du personnage, les bonus de set et toute source que le client n'expose pas. Il n'est pas présenté comme une erreur, et la somme des apports n'est jamais présentée comme la valeur réelle.

### Noms de champs et valeurs manquantes

**Limite de couverture constatée à la compilation (1.1.12-r99041-b2).** `UnitStats` ne porte que les 15 champs listés plus haut. Les autres statistiques de la fiche — chances et dégâts critiques physiques et magiques, vitesses de déplacement bonus, puissance de compétence d'arme, efficacité de l'ultime, emplacements d'inventaire supplémentaires, résistances sacrée, à l'argent, à l'ail et au soleil, résilience JcJ — sont portées par un **autre** composant, `ProjectM.Shared.VampireSpecificAttributes` (32 champs, répliqué séparément), que ce collecteur **ne lit pas**. `get_character` publiera donc les 15 statistiques d'`UnitStats` et rien de plus. Ce n'est pas une lecture vide ni une valeur inventée : c'est une couverture partielle, signalée ici plutôt que laissée à découvrir.

Les noms de champs sont malgré tout découverts sur les composants eux-mêmes au lieu d'être codés en dur, parce qu'ils changent d'une version à l'autre. Aucun champ d'une seule lettre n'a été trouvé sur `UnitStats` en 1.1.12 ; la chance de coup critique magique y porte son nom complet, `SpellCriticalStrikeChance`, mais sur `VampireSpecificAttributes`. Conséquences :

- un champ inconnu est publié **tel quel**, avec un libellé nul, jamais renommé au jugé ;
- `explain_stat` indique quand la valeur finale et les apports ne peuvent pas être reliés avec certitude ;
- une mise à jour du jeu qui renomme un champ fait perdre son libellé, pas sa valeur.

Une statistique à zéro est conservée : c'est une observation, pas une absence. Une valeur absente vaut **inconnu**, jamais zéro.

### Dégâts et DPS

`estimate_damage` est **une estimation, jamais une valeur du jeu**, et ne prétend pas le contraire.

Le client expose la puissance et les critiques. Il n'expose **pas** le coefficient de dégâts d'une capacité ni l'intervalle entre deux coups : ces deux entrées doivent être fournies, et sans elles l'outil renvoie `null` au lieu d'un chiffre inventé. La cible n'est pas modélisée du tout — ni armure, ni résistances, ni réductions, ni immunités, ni dégâts sur la durée, ni effets conditionnels : la formule d'atténuation n'est pas publique, et la deviner transformerait une estimation en fiction.

La convention des dégâts critiques n'est pas déclarée par le jeu. L'outil annonce la lecture retenue (multiplicateur direct ou bonus au-dessus d'un coup normal) et fournit l'autre dans `critMultiplier.alternative`, au lieu de cacher le choix dans le résultat.

### Vérification dans ta partie

1. `get_status` : les entrées `stats`, `blood`, `equipment`, `buffs` et `spells` doivent afficher `observed`. Toute autre valeur indique un composant non répliqué, et le message se trouve dans `warnings`.
2. Comparer `get_character` avec la fiche du personnage en jeu, statistique par statistique. Les 15 champs d'`UnitStats` doivent correspondre exactement, puisqu'ils sont lus et non calculés ; signaler tout écart. Les statistiques absentes de la liste ne sont pas un écart de lecture mais la limite de couverture décrite plus haut.
3. Boire une potion, puis rappeler `get_buffs` : le buff doit apparaître avec un temps restant qui décroît, et la statistique concernée doit avoir bougé dans `get_character`.
4. `explain_stat` sur la puissance physique, puis retirer une pièce d'équipement et recommencer : l'apport de cette pièce doit disparaître, et la valeur finale baisser d'autant si l'apport était additif.
5. Changer de sang et vérifier le type, la qualité et les buffs associés.
6. Sertir ou retirer un joyau, puis `get_equipment` : si `jewelsReadable` reste faux, c'est le point le plus incertain de cette version — le signaler.
7. Comparer une pièce artisanale de bonne qualité avec son infobulle : si les apports sont marqués `item_prefab`, ils ignorent la qualité d'artisanat.

## Nouveauté 0.3 : salle des coffres

`get_shared_inventory` lit les quantités de l'inventaire partagé **lorsque les buffers correspondants sont répliqués au personnage local**. Il n'est alors plus nécessaire d'ouvrir chaque coffre inclus dans ce système. La collecte est tentée à chaque cycle (2 secondes par défaut), sans appel à ChatGPT.

Le collecteur suit `SharedCastleInventoryConnection` sur le personnage, puis les instances du gestionnaire et leurs `SharedCastleInventoryItems`. Il ne scanne pas tous les châteaux. Chaque instance est lue une seule fois ; aucune observation nouvelle n'est publiée si une instance annoncée manque ou si une quantité est invalide. Une liste d'instances vide est considérée comme non confirmée, pas comme un stock nul.

**Comptage prudent :** dès qu'une observation partagée existe, les totaux et plans de fabrication utilisent uniquement le sac et cet inventaire partagé. Tous les autres inventaires observés (coffres et machines compris) sont exclus des sommes, car leur appartenance au total partagé n'est pas garantie côté client. Ils restent consultables via `find_stock` et `list_containers`. Cette règle peut sous-estimer des ressources situées hors du réseau partagé ; elle évite de les additionner deux fois. `accounting` explique les exclusions et `includedInTotals` identifie les lignes utilisées.

La perte de connexion au gestionnaire, la déconnexion ou une lecture incomplète rend la dernière observation mémorisée. Le remplacement par un autre gestionnaire remplace le total précédent, sans le fusionner. La mémoire est remise à zéro à la reconnexion. La passerelle traite aussi comme mémorisée toute observation ou tout fichier de plus de 10 secondes.

### Vérification dans ta partie

1. Mettre à jour **la DLL et l'exécutable MCP**, puis redémarrer jeu et MCP.
2. Entrer dans le territoire contenant la salle des coffres, attendre quelques secondes, puis demander : « Utilise get_shared_inventory et donne-moi mes ressources partagées. »
3. Si `availableNow` reste faux, ouvrir le menu construction et réessayer. Le moment précis de réplication reste à confirmer en jeu.
4. Comparer une ressource avec les quantités affichées par le jeu. Ouvrir ensuite un coffre déjà inclus : `summarize_stock` ne doit pas augmenter simplement parce que ce coffre a été ouvert.
5. Déplacer une ressource, attendre le cycle suivant et comparer à nouveau. Sortir du territoire puis vérifier que la connexion disparaît et que l'observation devient mémorisée. Si le jeu conserve ce lien en dehors du territoire, partager le diagnostic : ce comportement n'a pas été validé ici.

Statuts : `observed` = lecture complète des instances annoncées ; `no_character_connection` = pas de lien sur le personnage ; `manager_not_replicated` / `instances_not_replicated` / `partial_replication` = données non disponibles ou incomplètes ; `empty_instance_list_unconfirmed` = liste vide non confirmée ; `instance_manager_mismatch` / `invalid_quantity` = lecture rejetée ; `disconnected` = jeu déconnecté ; `not_collected` = ancien snapshot ou collecte pas encore effectuée.

**Cette extension est compilée et testée avec des données synthétiques, mais n'a pas été chargée dans une vraie partie.** L'existence des signatures ne prouve pas que tous ces composants soient répliqués sur chaque version/serveur. En cas d'indisponibilité, aucune quantité n'est inventée.

## Nouveautés 0.2 : ce que tu peux demander

| Demande | Réponse disponible |
|---|---|
| « Fais le bilan de ma partie » | Résumé compact du personnage, nombre d'inventaires observés, ressources distinctes, état des bonus, production et déblocages. |
| « Combien de bois ai-je dans les contenants connus ? » | Sommes par ressource, avec quantités récemment observées séparées des quantités mémorisées. Pas de total garanti du château. |
| « Où ai-je rangé mes planches ? » | Recherche des contenants par leur nom ou leur contenu, identifiants, âge des observations, coordonnées si accessibles et distance en ligne droite depuis la dernière position récente du personnage. |
| « Quelles stations ont un bonus manquant ? » | Sol adapté et pièce close : actif, absent ou inconnu. Le diagnostic indique quand rouvrir une station pour confirmer. Aucun pourcentage de bonus n'est inventé. |
| « Quelles machines produisent, et lesquelles ont des sorties à récupérer ? » | Production observée et présence d'objets dans les inventaires de sortie de raffinage accessibles. Une file vide n'est pas une preuve de panne ou de fin de production. |
| « Compare cette recette entre mes stations » | Coûts, différence avec la recette de base, durée si connue et nombre maximal théorique de fabrications d'après les ingrédients. Pas de classement artificiel entre des ressources différentes. |
| « Prépare la liste pour fabriquer ces trois objets » | Besoins directs cumulés pour 1 à 20 fabrications sélectionnées, stock déduit une seule fois par ressource et quantités manquantes. |

Les coordonnées sont des coordonnées internes du jeu, pas un marqueur sur la carte ni un itinéraire. Elles restent inconnues si le transform est rattaché à un parent. Une position de coffre mémorisée peut être ancienne ; la distance est géométrique et ne tient pas compte des murs ou étages.

Le plan de projet ne décompose **pas** récursivement les recettes, ne réemploie pas automatiquement les produits d'une étape dans une autre et ne conserve pas d'objectif entre les sessions. ChatGPT choisit les recettes à partir des outils de recherche. Le nombre de fabrications correspond à des lots, pas nécessairement au nombre d'objets obtenus.

## Fonctionnement livré

| Donnée | Collecte implémentée |
|---|---|
| Personnage | Nom, santé, position lorsqu'elle est exposée, arme et niveaux d'équipement. |
| Statistiques | Bloc final `UnitStats` lu sur le personnage, champ par champ, sans recalcul. |
| Sang | Type, qualité, quantité restante. Maximum publié seulement si le jeu l'expose. |
| Équipement | Emplacements découverts sur le composant, objet, durabilité, palier légendaire, infusion, modificateurs, apports déclarés avec leur provenance. |
| Buffs | Buffs actifs, durée totale, temps restant, apports déclarés. |
| Sorts | Emplacements de capacité et joyaux sertis avec leur puissance, quand le client les expose. |
| Inventaire | Sac du personnage, inventaires externes rattachés ; nom et quantité par objet. |
| Coffres | Lecture des cibles des menus d'inventaire ouverts, puis mémoire pendant la session. |
| Stations | Menus d'artisanat et de raffinage ouverts ; inventaires d'entrée/sortie accessibles. |
| Bonus | Drapeaux réels `MatchingFloor` et `EnclosedRoom` du composant `CastleWorkstation`. Aucun bonus n'est déduit du simple déblocage d'un sol. |
| Progression | Buffers accessibles de recettes, plans/sols, V Blood et progression, via l'entité de progression du joueur. |
| Recettes | Ingrédients, produits, déblocage observé. Coûts exacts de l'interface d'artisanat si les noms des ingrédients correspondent. |
| Raffinage | Coûts estimés à partir des exigences et du multiplicateur que reçoit l'interface. Arrondi à vérifier en jeu ; la passerelle ne confirme pas cette estimation comme une fabrication certaine. |
| Fabrications | Files d'artisanat et recette de raffinage active lorsque disponibles. |

La collecte est écrite contre de vraies signatures des bibliothèques du jeu. **Ces fonctions n'ont pas encore été vérifiées dans une partie réelle.** Les erreurs d'un collecteur sont isolées, consignées dans le journal BepInEx et exposées dans `get_status` quand les données sont publiées.

### Ce qui reste inconnu

- Un coffre jamais ouvert n'a pas de détail individuel ; son contenu peut néanmoins être inclus dans l'inventaire partagé répliqué. Les ressources hors de ces deux sources restent inconnues.
- Les observations des coffres fermés sont mémorisées, pas certifiées actuelles. Un objet déplacé peut apparaître dans plusieurs anciennes observations. Le calcul exclut ces stocks par défaut.
- La mémoire est séparée par session et remise à zéro à la reconnexion. Elle n'est pas fusionnée entre serveurs, personnages ou redémarrages.
- Il n'y a pas de carte complète des sols posés. Le mod lit le **bonus actif de chaque station visitée** et les déblocages accessibles.
- Les durées effectives de raffinage, les serviteurs, les mods de quêtes propres aux serveurs et la totalité des paramètres serveur ne sont pas couverts.
- Les dégâts réels ne sont pas lisibles côté client : le coefficient de chaque capacité et l'atténuation de la cible ne sont pas exposés. `estimate_damage` calcule à partir de ce que tu fournis et le déclare comme une estimation.
- L'écart entre une statistique finale et la somme de ses apports observés n'est pas comblé par une hypothèse. Il est publié tel quel.
- Les noms d'objets utilisent la langue du jeu quand la localisation est accessible, sinon un nom interne ou un identifiant. Les plans/sols peuvent conserver des noms internes anglais.
- Ce compagnon consulte le jeu et répond aux demandes de lecture. Il ne déplace pas le personnage, ne transfère pas d'objets et ne lance pas de fabrication.

## Outils MCP et économie de tokens

| Outil | Utilisation |
|---|---|
| `get_shared_inventory` | Quantités partagées, état et diagnostics ; filtres `query`, `limit`, `offset`. |
| `get_character` | Statistiques finales, sang, résumé de l'équipement, des buffs et des sorts. `query` filtre une statistique. |
| `get_equipment` | Détail par emplacement et joyaux des sorts, avec la provenance de chaque apport. |
| `get_buffs` | Buffs actifs, temps restant et apports. |
| `explain_stat` | Une statistique finale en face de ses apports, avec le reste inexpliqué. `query` obligatoire. |
| `estimate_damage` | Estimation de dégâts et de DPS. `kind` obligatoire ; `coefficient` et `intervalSeconds` viennent de toi. |
| `get_overview` | Bilan compact, utile pour commencer une conversation. |
| `summarize_stock` | Totaux par ressource, récent et mémorisé séparés. |
| `list_containers` | Contenants visités, recherche par contenu, fraîcheur, position et distance si disponibles. |
| `audit_stations` | Bonus manquants/inconnus, production observée et inventaires de sortie. |
| `compare_recipe_stations` | Pour `recipeGuid`, compare les coûts et la capacité théorique des stations visitées ; `includeCached=false` par défaut. |
| `plan_project` | `targets` : 1 à 20 objets `{recipeGuid, stationId, batches}` ; regroupe les besoins avant de déduire les stocks. |
| `get_status` | Connexion, personnage, erreurs et couverture des données. |
| `find_stock` | Recherche par nom ou GUID, avec coffre d'origine et fraîcheur. |
| `get_stations` | Recherche des stations, bonus et files de production. |
| `get_progression` | Recherche des recettes/plans/V Blood connus. |
| `find_recipes` | Recherche des ingrédients et produits d'une recette. |
| `plan_craft` | Calcul pour `recipeGuid`, `stationId` et `batches` ; stocks mémorisés exclus par défaut. |
| `refresh` | Demande une nouvelle collecte, délai maximal 3 secondes. |

La passerelle expose **19 outils**. Les recherches sont insensibles à la casse et aux accents. Elles renvoient 15 résultats par défaut, 50 maximum, avec `query`, `limit`, `offset` et `nextOffset`. Le mod ne fait **aucun appel à un modèle** et ne transmet aucun flux permanent à ChatGPT. Les outils ne sont appelés qu'à la demande. Les calculs sont effectués dans la passerelle.

`observed_now` signifie observé récemment dans la session, avec un fichier de données **et une observation** âgés d'au plus 10 secondes. `last_observed` signifie mémorisé. Un `null` signifie inconnu, jamais « non » ou « zéro ». Une station fermée ou un déblocage inconnu empêche de confirmer qu'une fabrication est actuellement possible.

Exemples : « Vérifie les bonus de mes stations », « Cherche les planches avec 5 résultats », « Quels plans de sols connais-tu ? », « Calcule les matériaux pour 3 fabrications de cette recette dans cette station », « Donne-moi mes statistiques », « D'où vient ma puissance physique ? », « Quels buffs vont expirer bientôt ? », « Qu'est-ce que mes anneaux m'apportent ? ».

## Dépannage et test dans le jeu

Le fichier `%LOCALAPPDATA%\VampireCompanion\snapshot.json` doit apparaître après le chargement du mod. La configuration se trouve dans `BepInEx\config\fr.tristan.vampirecompanion.cfg`. Si tu changes `DataDirectory`, passe le même chemin à la passerelle avec `--data-dir`.

1. Vérifier la ligne « Vampire Companion chargé » dans `BepInEx\LogOutput.log`.
2. Appeler `get_status` : `connected` est résumé par `fresh`, qui doit être vrai une fois en jeu et les données reçues. Appeler `refresh` si nécessaire.
3. Comparer les quantités du sac puis d'un coffre ouvert avec `find_stock`.
4. Fermer le coffre et attendre 5 secondes : ses données doivent passer à `last_observed`.
5. Ouvrir une station avec le sol adapté, puis une sans ce sol : comparer `matchingFloor` et `confinedRoom` avec les icônes du jeu.
6. Comparer les coûts affichés dans le jeu à `plan_craft`, surtout les coûts impairs et le raffinage. Les coûts non vérifiés restent explicitement des estimations.
7. Demander le même ingrédient dans deux fabrications avec `plan_project` : le stock doit être déduit une seule fois, après cumul des besoins. Comparer la liste aux recettes affichées.
8. Tester `summarize_stock` après un transfert entre coffre et sac : la mémoire reste séparée et ne doit pas être présentée comme un stock actuel.
9. Se déconnecter puis se reconnecter : `sessionId` doit changer et les anciens coffres ne doivent pas être fusionnés.

Si un collecteur ne marche pas, conserver le journal BepInEx et la version du jeu ; le script `scripts\Diagnose.ps1` copie les données utiles dans un dossier local pour diagnostic. Le snapshot contient le nom du personnage et ses observations : le consulter avant de le partager.

## Recompiler

Le SDK .NET 6 (ou un SDK compatible avec la cible net6.0) est nécessaire pour recompiler. Les dépendances sont téléchargées depuis NuGet et le dépôt BepInEx.

```powershell
dotnet build src\Mod\VampireCompanion.csproj -c Release
dotnet publish src\Bridge\VampireCompanion.Mcp.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o release\mcp
```

Les assemblies du jeu et de BepInEx ne sont pas incluses dans le dossier du plugin. Ne copier que `VampireCompanion.dll` dans le jeu. Le script `scripts\Build.ps1` effectue les étapes de compilation et de copie.

Tests de protocole et calcul, sans lancer le jeu : `python tests/test_bridge.py --dotnet dotnet`. Ces tests construisent la passerelle puis l'interrogent via de vrais messages JSON-RPC avec un jeu de données synthétique temporaire.

Contrôle du collecteur de personnage sans le jeu ni BepInEx : `dotnet run --project tests\modcheck\modcheck.csproj -c Release`. Il compile le collecteur contre des doublures typées des composants et vérifie ce qu'il publie. Il valide la logique, pas les signatures réelles du jeu ; voir `tests/modcheck/README.md`.

## Sources techniques

- [V Rising Mod Wiki : fonctionnement des mods](https://wiki.vrisingmods.com/dev/how-mods-work.html)
- [V Rising Mod Wiki : environnement de développement](https://wiki.vrisingmods.com/dev/development_setup.html)
- [V Rising Mod Wiki : entités et composants](https://wiki.vrisingmods.com/dev/ecs-entities.html)
- [VampireReferenceAssemblers](https://github.com/mfoltz/VampireReferenceAssemblers) : référence de compilation 1.1.12-r99041-b2.
- [Eclipse](https://github.com/mfoltz/Eclipse) : vérification des points d'entrée client (`GameDataManager`, `ConsoleShared`, déconnexion) et de la lecture client des statistiques (`ModifyUnitStatBuff_DOTS`, `UnitStatType`).
- [Bloodcraft](https://github.com/mfoltz/Bloodcraft) : vérification des composants `UnitStats`, `Blood`, `Equipment`, `BuffBuffer`, `AbilityGroupSlotBuffer`, `SpellModSet`, `LegendaryItemInstance`.
- [OpenAI : MCP dans Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

Projet original, sans code ni assets du jeu redistribués. Non affilié à Stunlock Studios ou OpenAI.
