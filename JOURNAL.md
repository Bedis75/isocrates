# Journal de travail · ISOCRATES

> **À l'IA qui lit ce fichier.** Ce journal décrit, étape par étape, ce que Claude Code a fait dans le dépôt ISOCRATES pour Bedis (étudiant en M2 Data Science). Ton rôle est de **lui expliquer** ce travail clairement, en français, sans supposer qu'il connaît déjà tous les termes : le pourquoi de chaque choix, ce que montrent les chiffres et ce qui reste à décider. Les chiffres cités ici ont tous été réellement obtenus en exécutant le code : n'en invente pas d'autres.

## Contexte en bref

- **Projet :** ISOCRATES, un SOC (centre de surveillance de sécurité) « intelligent ». Le machine learning détecte les attaques dans le trafic réseau, des agents LLM les expliquent, un analyste humain décide. Projet de classe, rendu fin novembre 2026.
- **Données :** LYCOS-IDS2017, une version corrigée du jeu CICIDS2017. Cinq fichiers CSV, un par jour (lundi → vendredi, 3 → 7 juillet 2017). Chaque ligne est un **flux réseau** (une connexion entre deux machines) décrit par 77 caractéristiques numériques et une étiquette (`benign` = normal, ou le nom d'une attaque).
- **Règle centrale :** le découpage des données est **temporel**. On entraîne sur le passé (lundi, mardi, mercredi) et on teste sur le futur (jeudi, vendredi), jamais en mélangeant au hasard, sinon les scores sont artificiellement bons (Arp et al., 2022).
- **Environnement :** Python 3.11, conda `isocrates`, WSL2, 9,7 Go de RAM.
- Le détail complet du projet est dans `CLAUDE.md`.

---

## Étape 1 · 21 octobre 2026 · Lecture du cadre et vérifications préalables

**Ce qui a été fait :**
1. Lecture de `CLAUDE.md` (architecture, règles méthodologiques, planning).
2. Vérification de `data/processed/` : le dossier était déjà vide. Il devait l'être, car un ancien script (`explore.py`) y avait écrit des fichiers Parquet faussés (voir ci-dessous).
3. Vérification de **l'unité de la colonne `timestamp`** sur les 5 fichiers.

**Pourquoi vérifier `timestamp` :** on doit construire plus tard des caractéristiques sur des fenêtres de 60 secondes. Si on se trompe d'unité (secondes, millisecondes ou microsecondes), toutes les fenêtres sont fausses. De plus, l'ancien script convertissait `timestamp` en `float32` : ce type n'a qu'environ 7 chiffres significatifs, alors que les timestamps en ont 16, ce qui arrondit les temps d'environ 2 minutes.

**Résultat :**
- `timestamp` est en **microsecondes** depuis le 1er janvier 1970 (temps Unix), en UTC. Exemple : `1499082997567312` correspond au lundi 3 juillet 2017, 11:56:37 UTC.
- Lues en `float64`, les valeurs restent exactes (elles sont sous 2⁵³, limite des entiers exacts en float64).
- Les lignes de chaque fichier sont déjà **triées** dans l'ordre chronologique.
- L'heure locale du banc d'essai (au Canada) est UTC−3 : chaque journée va d'environ 9 h à 17 h, heure locale.
- **Jeudi ne dure que 3 heures** (9 h → 12 h locale) : les auteurs ont retiré l'après-midi, qui contenait l'attaque « infiltration ».
- `flow_duration` est aussi en microsecondes (maximum 120 s, la durée au-delà de laquelle un flux est coupé).

| Jour | Début (UTC) | Fin (UTC) | Durée |
|---|---|---|---|
| Lundi | 11:56 | 20:01 | 8 h 05 |
| Mardi | 11:53 | 20:00 | 8 h 07 |
| Mercredi | 11:42 | 20:08 | 8 h 25 |
| Jeudi | 11:59 | 14:59 | 3 h 01 |
| Vendredi | 11:59 | 20:02 | 8 h 03 |

**Fichier modifié :** `CLAUDE.md` (section « État actuel »).

---

## Étape 2 · 21 octobre 2026 · Module de chargement et notebook 01 (exploration)

### 2.1 Fichier créé : `src/isocrates/ml/data.py`

Code réutilisable que tous les notebooks importent, pour toujours charger les données de la même façon.

- `DAYS` : dictionnaire jour → (fichier CSV, rôle). `lun`, `mar`, `mer` : `train/val` ; `jeu`, `ven` : `test`.
- `ID_COLS` : colonnes **jamais** utilisées comme entrées du modèle : `flow_id`, `src_addr`, `src_port`, `dst_addr`, `timestamp`, `label`.
- `feature_columns(cols)` : renvoie les 77 colonnes utilisables comme caractéristiques (dont `dst_port` et `ip_prot`).
- `load_day("lun")` : charge un jour avec les bons types :
  - `timestamp` en `float64` (jamais `float32`) ;
  - les caractéristiques en `float32`, pour économiser la RAM (environ 150 à 225 Mo par jour) ;
  - les adresses IP en texte et `label` en catégorie.

### 2.2 Fichier créé : `notebooks/01_donnees_lycos.ipynb`

Il est exécuté de bout en bout, avec ses sorties visibles. Il contient :

1. **Liste des colonnes :** 83 au total, dont 6 identifiants ou cible et 77 caractéristiques.
2. **Qualité, jour par jour :** valeurs manquantes, infinies, doublons. Le notebook charge un jour à la fois pour ménager la RAM.
3. **Répartition des classes** par jour.
4. **Vérification clé :** aucune attaque du test n'apparaît dans train/val.
5. **Chronologie :** nombre de flux d'attaque par minute, pour chaque jour.
6. **Aperçu du découpage 80/20 :** dans quel ensemble tombe chaque attaque.
7. **Caractéristiques constantes** (inutiles pour un modèle).
8. **IP sources des attaques,** pour justifier leur exclusion des caractéristiques.
9. **Cellule « Observations »,** qui résume les points ci-dessous.

### 2.3 Figures créées (`reports/`, PNG à 150 dpi)

- `01_attaques_par_jour.png` : carte de chaleur classe × jour avec le nombre de flux dans chaque case (couleur en échelle log).
- `01_chronologie_attaques.png` : 5 graphiques, un par jour. En gris, le trafic total par minute ; en points colorés, chaque attaque.

### 2.4 Résultats obtenus

**Qualité :** 1 837 498 flux, **0** valeur manquante, **0** infinie, **0** doublon. Les « 11 doublons » signalés auparavant venaient vraisemblablement de l'arrondi `float32` du timestamp, qui rendait identiques des lignes en réalité distinctes.

**Classes :**

| Classe | lun | mar | mer | jeu | ven |
|---|---|---|---|---|---|
| benign | 367 181 | 312 675 | 318 933 | 110 448 | 286 438 |
| ftp_patator | | 4 003 | | | |
| ssh_patator | | 2 959 | | | |
| dos_hulk | | | 158 988 | | |
| dos_goldeneye | | | 6 765 | | |
| dos_slowloris | | | 5 674 | | |
| dos_slowhttptest | | | 4 866 | | |
| heartbleed | | | 11 | | |
| webattack_bruteforce | | | | 1 360 | |
| webattack_xss | | | | 661 | |
| webattack_sql_injection | | | | 12 | |
| portscan | | | | | 160 106 |
| ddos | | | | | 95 683 |
| bot | | | | | 735 |

- Il y a 441 823 attaques au total (24 % des flux), très déséquilibrées : de 160 106 flux (portscan) à 11 flux (heartbleed). Il faut donc des métriques **par classe**.
- **Aucune attaque du test n'existe en train/val.** Le modèle supervisé (Random Forest) ne peut donc pas les reconnaître par leur nom : c'est voulu, et c'est le rôle du détecteur d'anomalies (autoencodeur) de les attraper.

**Fuite par adresse IP :** 12 classes d'attaque sur 13 viennent d'une seule IP, `172.16.0.1`, la passerelle de l'attaquant. Cette IP n'émet que 1 383 flux normaux contre 441 088 flux d'attaque. Un modèle qui verrait l'IP apprendrait « 172.16.0.1 = attaque » au lieu d'apprendre le comportement réseau, et ses scores seraient trompeurs. Les IP sont donc exclues des caractéristiques. Seule l'attaque `bot` vient de 5 postes internes (`192.168.10.x`), dont le trafic est surtout normal.

**Colonnes inutiles :** `flag_urg`, `fwd_flag_urg` et `bwd_flag_urg` valent toujours 0. Elles seront à retirer dans le notebook 02.

**Fenêtres horaires des attaques** (heure locale, entre les quantiles 1 % et 99 % pour écarter les flux isolés) :

| Jour | Attaque | De | À |
|---|---|---|---|
| mar | ftp_patator | 09:19 | 10:19 |
| mar | ssh_patator | 14:09 | 15:10 |
| mer | dos_slowloris | 09:48 | 10:09 |
| mer | dos_slowhttptest | 10:15 | 10:33 |
| mer | dos_hulk | 10:43 | 11:00 |
| mer | dos_goldeneye | 11:10 | 11:18 |
| mer | heartbleed | 15:12 | 15:31 |
| jeu | webattack_bruteforce | 09:21 | 09:59 |
| jeu | webattack_xss | 10:15 | 10:34 |
| jeu | webattack_sql_injection | 10:40 | 10:42 |
| ven | bot | 10:05 | 11:00 |
| ven | portscan | 14:51 | 15:23 (premiers flux épars dès 13:05) |
| ven | ddos | 15:56 | 16:16 |

Quelques flux sont étiquetés hors de la fenêtre principale, par exemple 4 flux `dos_slowloris` à 9 h 01 et 14 h 24.

### 2.5 Problème découvert : la validation n'a presque pas d'attaques

La règle prévoit : train = les 80 % les plus anciens de lundi, mardi et mercredi ; val = les 20 % les plus récents. Or les attaques ont lieu surtout le matin, donc presque toutes tombent dans train. Le notebook a testé deux lectures de la règle :

| Lecture | Coupure (heure locale) | Attaques en validation |
|---|---|---|
| 80/20 **par jour** | lun 15:15, mar 15:22, mer 14:34 | seulement 11 heartbleed |
| 80/20 **global** (3 jours bout à bout) | mercredi 10:59 | 6 765 goldeneye, 8 581 hulk, 11 heartbleed, 3 slowloris ; aucun ftp, ssh ni slowhttptest |

**Conséquence :**
- Pour l'autoencodeur et l'Isolation Forest, il n'y a pas de problème : leur seuil se calcule sur le trafic normal de la validation.
- Pour le Random Forest et le MLP, on ne peut pas régler les modèles sur la validation telle quelle, puisque la plupart des attaques connues n'y figurent pas.

**Proposition de Claude (non encore validée) :** un découpage temporel **par classe**. Pour chaque classe, les 80 % de flux les plus anciens vont en train et les 20 % les plus récents en val. Le découpage reste temporel, sans mélange aléatoire, et chaque attaque connue apparaît en validation. Cela modifie la règle 1 de `CLAUDE.md` : à valider avec la professeure, ou au moins à justifier dans le rapport.

**Fichier modifié :** `CLAUDE.md`. Les points de données (0 doublon, colonnes URG, fuite IP) et l'avancement y sont mis à jour, et la décision ouverte y est notée.

---

## Questions ouvertes (à trancher par Bedis)

1. **Découpage train/val** pour le Random Forest et le MLP : garder le 80/20 strict, ou passer au 80/20 temporel par classe ? (voir 2.5)
2. **Premier commit Git** pas encore fait. Il comprendra `data.py`, le notebook 01, les figures, `CLAUDE.md`, `.gitignore` et ce journal.

## Prochaine étape prévue

`src/isocrates/ml/prepare.py` et `notebooks/02_preparation.ipynb` : nettoyage, retrait des colonnes constantes, caractéristiques de fenêtre par IP source et par minute (`w_conn`, `w_dst_ports`, `w_dst_hosts`, `w_rst_rate`), découpage temporel, puis export de `data/processed/{train,val,test}.parquet` et `features.json`.
