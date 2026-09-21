# Validation de la version 0.4.0

## Ce qui a été vérifié

### Compilation (ajouté après la première compilation réelle)

- **Le mod compile contre les vraies assemblies**, `VampireReferenceAssemblies 1.1.12-r99041-b2` et `BepInEx.Unity.IL2CPP 6.0.0-be.733` : **0 erreur, 0 avertissement**. Aucune signature de `src/Mod/Character.cs` n'a dû être corrigée. Les deux binaires sont produits par `scripts/Build.ps1`.
- Les types et membres lus directement par le collecteur ont été relus un par un dans les assemblies de référence avec `MetadataLoadContext`. Tous existent, aux namespaces près que le fichier importait déjà : `Durability`, `SpellModSet`, `SpellModSetComponent`, `LegendaryItemInstance` et `LegendaryItemSpellModSetComponent` sont dans `ProjectM.Shared`, `BuffBuffer` dans `ProjectM`.
- Les chemins par réflexion ont été vérifiés sur les vraies assemblies, et non supposés : `ModifiableFloat`, `ModifiableInt` et `ModifiableBool` portent bien le champ `_Value` que lit `Number()` ; `NetworkedEntity` porte bien `_Entity` que lit `Networked()` ; les 14 champs `EquipmentSlot` d'`Equipment` portent bien `SlotId` et `SlotEntity`, donc la découverte des emplacements trouvera 14 emplacements.
- `tests/modcheck/Stubs.cs` a été remis en accord avec ces lectures : namespaces réels, `SpellModSet.Count` et `LegendaryItemInstance.TierIndex` en `byte`. Les trois doublures restées synthétiques le disent à l'endroit où elles sont déclarées.

### Couverture

- **`UnitStats` ne porte que 15 champs en 1.1.12**, et pas ceux que cette version annonçait. Les chances et dégâts critiques, les vitesses bonus, les vols de vie et les résistances sacrée/argent/ail/soleil sont sur un composant distinct, `ProjectM.Shared.VampireSpecificAttributes`, que le collecteur **ne lit pas**. `get_character` publiera 15 statistiques réelles, pas la fiche complète. Corrigé dans `README.fr.md` plutôt que comblé par une estimation.
- **`Blood` expose un maximum**, `MaxBlood`. En jeu, `maxAmount` et le pourcentage de réserve seront donc publiés — contrairement au jeu de données du contrôle hors ligne, qui teste le cas inverse.

### Passerelle et contrôles hors ligne

- Passerelle MCP compilée en Release : **aucune erreur, aucun avertissement**.
- **38 tests d'intégration réussis** contre le vrai processus MCP avec des données synthétiques, dont 11 nouveaux pour le personnage : statistiques à zéro conservées mais classées en dernier, absence de réserve de sang inventée, apports jamais additionnés au bloc final, refus de sommer des modificateurs de types différents, statistique obfusquée signalée comme non reliée, bonus lus sur le modèle de l'objet distingués de ceux de l'exemplaire équipé, emplacement vide distingué d'un emplacement illisible, buffs permanents séparés des buffs qui expirent, estimation de dégâts sans entrée renvoyant `null` et non zéro, arithmétique critique vérifiée sur des valeurs connues, snapshot 0.3 traité comme une absence de données, version de format inconnue refusée.
- Les 26 tests de la version 0.3 passent sans modification : l'inventaire partagé, les plans de fabrication et la comptabilité des stocks ne sont pas affectés.
- **31 contrôles réussis sur le collecteur du personnage** (`tests/modcheck`), qui compile `src/Mod/Character.cs` contre des doublures typées des composants du jeu et lui donne un personnage synthétique : découverte des emplacements d'équipement par réflexion, champ obfusqué lu sans libellé inventé, champ non numérique signalé, statistique à zéro conservée, booléen et entier lus, repli documenté de l'exemplaire vers le modèle de l'objet, emplacement vide distingué d'un emplacement illisible, apport nul écarté, durée négative traitée comme un effet permanent, jeu de modificateurs illisible marqué inconnu, sérialisation du snapshot. Ce contrôle valide la logique du collecteur, **pas** les signatures réelles du jeu.

## Ce qui n'a pas pu être vérifié

- **Aucun test en jeu.** La réplication réelle de `UnitStats`, `Blood`, `Equipment`, `BuffBuffer`, `AbilityGroupSlotBuffer` et `SpellModSetComponent` sur le client n'est pas démontrée. Chaque collecteur est isolé : un composant non répliqué passe en `unavailable` dans `get_status` sans désactiver les autres.
- **Le mod n'a pas été chargé par BepInEx.** Il compile, mais rien ici ne prouve qu'IL2CPP accepte le plugin au démarrage du client ni que les patchs Harmony trouvent leurs cibles.

## Points ouverts, à confirmer en jeu

- **Emplacement des joyaux.** Les modificateurs de sorts sont cherchés sur l'entité d'emplacement de capacité (`AbilityGroupSlotBuffer.GroupSlotEntity`). Si le client les expose ailleurs, `jewelsReadable` restera faux. C'est le point le moins sûr de cette version.
- **Convention des dégâts critiques.** Le client ne déclare pas si la valeur est un multiplicateur (1,5 = 150 %) ou un bonus (0,5 = +50 %). `estimate_damage` annonce la lecture retenue et fournit l'autre dans `critMultiplier.alternative`. À trancher en comparant avec la fiche du personnage en jeu.
- **Champs obfusqués : hypothèse non confirmée en 1.1.12.** Aucun champ d'une seule lettre n'existe sur `UnitStats` dans `VampireReferenceAssemblies 1.1.12-r99041-b2` ; les seuls champs d'une lettre trouvés dans `ProjectM*` sont des indices de boucle dans des structures de job générées. La chance de coup critique magique porte son nom complet, `SpellCriticalStrikeChance`, sur `VampireSpecificAttributes`. La découverte par réflexion reste en place : elle coûte peu et couvre un renommage futur. Un champ inconnu resterait publié tel quel, sans libellé.
- **Provenance des bonus d'équipement.** Quand l'exemplaire équipé ne porte pas ses apports, ils sont lus sur le modèle de l'objet et marqués `item_prefab` : ils ignorent alors la qualité d'artisanat. Comparer une pièce artisanale de bonne qualité avec l'infobulle du jeu.
- **Reste inexpliqué.** L'écart entre une statistique finale et la somme de ses apports observés est normal : il contient la base du personnage, les bonus de set et toute source non exposée. Ce n'est pas un défaut de lecture.

Aucune donnée n'est inventée en cas d'indisponibilité, et aucune estimation n'est présentée comme une valeur du jeu. Les données synthétiques des tests sont temporaires et ne sont jamais installées comme données d'une partie réelle.
