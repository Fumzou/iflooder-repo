# 0.4.0

- Lecture du personnage : statistiques finales (`UnitStats`), sang, équipement par emplacement, buffs actifs et emplacements de sorts.
- Sang : type, qualité, quantité restante. Aucune réserve maximale n'est supposée : le pourcentage de réserve n'est calculé que si le jeu expose ce maximum.
- Équipement : durabilité, palier légendaire, infusion, modificateurs d'arme ancestrale et apports de statistiques déclarés par chaque pièce, avec la provenance (exemplaire équipé ou modèle de l'objet).
- Sorts : joyaux équipés et leur puissance ; un jeu de modificateurs illisible est signalé comme inconnu, jamais comme « aucun joyau ».
- Buffs : potions, effets du sang et bonus permanents, avec durée totale et temps restant ; une durée nulle ou négative est traitée comme un effet sans expiration.
- 5 nouveaux outils MCP : `get_character`, `get_equipment`, `get_buffs`, `explain_stat`, `estimate_damage` ; 19 outils au total.
- `explain_stat` met une statistique finale en face de chacun de ses apports et publie le reste inexpliqué. Aucune somme n'est calculée quand les apports mélangent additif et multiplicatif.
- Les apports ne sont jamais ajoutés aux statistiques finales : le jeu les y a déjà intégrés.
- `estimate_damage` est explicitement une estimation. Le coefficient de capacité et l'intervalle ne sont pas exposés au client et doivent être fournis ; la cible n'est pas modélisée. Une entrée manquante donne `null`, jamais zéro.
- Les noms de champs sont découverts sur les composants eux-mêmes : plusieurs sont obfusqués dans les assemblies livrées et changent d'une version à l'autre. Un nom inconnu est publié tel quel avec un libellé nul, jamais renommé au jugé.
- Format des données en version 2. La passerelle lit encore les snapshots 0.3 et signale alors l'absence des données de personnage.
- 38 tests d'intégration.

# 0.3.0

- Lecture client de l'inventaire partagé lié au personnage, via les structures SharedCastleInventory du jeu.
- Nouvel outil `get_shared_inventory` : quantités, état, pagination et diagnostic ; 14 outils au total.
- Intégration aux totaux, comparaisons et plans de fabrication.
- Exclusion conservatrice des inventaires individuels hors sac lorsqu'un total partagé existe, afin de ne pas le compter deux fois.
- Lecture atomique de toutes les instances annoncées ; déduplication des références d'instance ; données incomplètes jamais présentées comme un zéro.
- Observation mémorisée lorsque le lien disparaît ; remplacement du total en changeant de gestionnaire.
- Collecte réelle en jeu toujours à valider.

# 0.2.0

- 6 nouveaux outils MCP : bilan compact, totaux de stock, recherche des contenants, audit des stations, comparaison de recette entre stations, plan de matériaux pour plusieurs fabrications.
- Coordonnées optionnelles des contenants et stations ; distance géométrique des contenants depuis la position récente du joueur.
- Recherche insensible aux accents.
- Contrôle de la date de chaque observation en plus de la date du fichier.
- Regroupement des ingrédients dupliqués avant calcul des besoins.
- Validation des arguments entiers ; 21 tests d'intégration.
- Compatible avec les snapshots 0.1 ; aucune écriture dans le jeu, aucun appel au modèle en arrière-plan.

Limitations : collecte en jeu toujours expérimentale, coffres non ouverts inconnus, mémoire limitée à la session, raffinage estimé, ingrédients directs seulement dans les projets.
