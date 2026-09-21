# Validation de la version 0.4.0

## Ce qui a été vérifié

- Passerelle MCP compilée en Release : **aucune erreur, aucun avertissement**.
- **38 tests d'intégration réussis** contre le vrai processus MCP avec des données synthétiques, dont 11 nouveaux pour le personnage : statistiques à zéro conservées mais classées en dernier, absence de réserve de sang inventée, apports jamais additionnés au bloc final, refus de sommer des modificateurs de types différents, statistique obfusquée signalée comme non reliée, bonus lus sur le modèle de l'objet distingués de ceux de l'exemplaire équipé, emplacement vide distingué d'un emplacement illisible, buffs permanents séparés des buffs qui expirent, estimation de dégâts sans entrée renvoyant `null` et non zéro, arithmétique critique vérifiée sur des valeurs connues, snapshot 0.3 traité comme une absence de données, version de format inconnue refusée.
- Les 26 tests de la version 0.3 passent sans modification : l'inventaire partagé, les plans de fabrication et la comptabilité des stocks ne sont pas affectés.
- **31 contrôles réussis sur le collecteur du personnage** (`tests/modcheck`), qui compile `src/Mod/Character.cs` contre des doublures typées des composants du jeu et lui donne un personnage synthétique : découverte des emplacements d'équipement par réflexion, champ obfusqué lu sans libellé inventé, champ non numérique signalé, statistique à zéro conservée, booléen et entier lus, repli documenté de l'exemplaire vers le modèle de l'objet, emplacement vide distingué d'un emplacement illisible, apport nul écarté, durée négative traitée comme un effet permanent, jeu de modificateurs illisible marqué inconnu, sérialisation du snapshot. Ce contrôle valide la logique du collecteur, **pas** les signatures réelles du jeu.

## Ce qui n'a pas pu être vérifié

- **Le mod C# n'a pas été compilé.** L'environnement de développement de cette version n'avait pas accès à NuGet, donc ni à `VampireReferenceAssemblies 1.1.12-r99041-b2` ni à `BepInEx.Unity.IL2CPP`. Le collecteur de personnage est écrit contre des signatures relevées dans le code source de mods 1.1.x qui les utilisent réellement (`Eclipse` pour la lecture côté client, `Bloodcraft` pour les composants de sang, d'équipement et de joyaux), mais **la première compilation aura lieu sur le PC du joueur**. Lancer `scripts\Build.ps1` et remonter les erreurs éventuelles.
- **Aucun test en jeu.** La réplication réelle de `UnitStats`, `Blood`, `Equipment`, `BuffBuffer`, `AbilityGroupSlotBuffer` et `SpellModSetComponent` sur le client n'est pas démontrée. Chaque collecteur est isolé : un composant non répliqué passe en `unavailable` dans `get_status` sans désactiver les autres.
- L'exécutable Windows autonome n'a pas été produit ici : la compilation `win-x64` autonome demande le runtime .NET depuis NuGet.

## Points ouverts, à confirmer en jeu

- **Emplacement des joyaux.** Les modificateurs de sorts sont cherchés sur l'entité d'emplacement de capacité (`AbilityGroupSlotBuffer.GroupSlotEntity`). Si le client les expose ailleurs, `jewelsReadable` restera faux. C'est le point le moins sûr de cette version.
- **Convention des dégâts critiques.** Le client ne déclare pas si la valeur est un multiplicateur (1,5 = 150 %) ou un bonus (0,5 = +50 %). `estimate_damage` annonce la lecture retenue et fournit l'autre dans `critMultiplier.alternative`. À trancher en comparant avec la fiche du personnage en jeu.
- **Champs obfusqués.** Au moins la chance de coup critique magique apparaît sous un nom d'une lettre dans les assemblies livrées. Ces champs sont publiés tels quels, sans libellé ; `explain_stat` le signale au lieu de les relier au hasard.
- **Provenance des bonus d'équipement.** Quand l'exemplaire équipé ne porte pas ses apports, ils sont lus sur le modèle de l'objet et marqués `item_prefab` : ils ignorent alors la qualité d'artisanat. Comparer une pièce artisanale de bonne qualité avec l'infobulle du jeu.
- **Reste inexpliqué.** L'écart entre une statistique finale et la somme de ses apports observés est normal : il contient la base du personnage, les bonus de set et toute source non exposée. Ce n'est pas un défaut de lecture.

Aucune donnée n'est inventée en cas d'indisponibilité, et aucune estimation n'est présentée comme une valeur du jeu. Les données synthétiques des tests sont temporaires et ne sont jamais installées comme données d'une partie réelle.
