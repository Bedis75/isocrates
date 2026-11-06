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

## Étape 3 · 2 novembre 2026 · Décision sur le découpage, puis notebook 02 (préparation)

### 3.1 Décision prise par Bedis

Le **découpage temporel par classe** proposé à l'étape 2 (voir 2.5) est retenu :
- pour chaque attaque connue (lundi → mercredi), ses 80 % de flux les plus anciens vont en **train** et ses 20 % les plus récents en **validation** ;
- le trafic normal (`benign`) est coupé 80/20 dans chaque jour ;
- le **test** reste jeudi + vendredi en entier.

On ne mélange jamais au hasard, et pour chaque classe la validation est toujours *après* l'entraînement. La règle 1 de `CLAUDE.md` a été réécrite en conséquence. Ce changement reste à justifier dans le rapport.

### 3.2 Fichier créé : `src/isocrates/ml/prepare.py`

- `add_window_features(df)` : ajoute 4 **caractéristiques de fenêtre**. Pour chaque flux, on regarde tous les flux émis par **la même IP source pendant la même minute** :
  - `w_conn` : combien de connexions ;
  - `w_dst_ports` : combien de ports de destination différents (un scan de ports en touche des centaines) ;
  - `w_dst_hosts` : combien de machines différentes contactées ;
  - `w_rst_rate` : la part de flux contenant un paquet RST (connexion refusée ou coupée, typique d'un scan).

  Les minutes sont des fenêtres **fixes** (de hh:mm:00 à hh:mm:59), calculées jour par jour. L'IP source sert ici seulement à regrouper : elle n'est jamais donnée au modèle.
- `temporal_split(df)` : renvoie « train » ou « val » pour chaque flux, selon la règle 3.1.
- `constant_columns(df, cols)` : trouve les colonnes qui ont une seule valeur. On l'applique sur train uniquement, car on ne doit rien décider en regardant la validation ou le test.
- `model_features(dropped)` : liste finale des caractéristiques données aux modèles.
- `save_split(...)` : écrit les fichiers Parquet et `features.json`.

### 3.3 Fichier créé : `notebooks/02_preparation.ipynb`

Il charge lundi, mardi et mercredi avec leurs fenêtres, découpe train/val, vérifie l'ordre temporel, retire les colonnes constantes, prépare le test (jeudi + vendredi), trace une figure, contrôle les données et exporte le tout.

**Fichiers produits** (non versionnés, car `data/` est dans `.gitignore`) :
- `data/processed/train.parquet` (129 Mo), `val.parquet` (33 Mo), `test.parquet` (73 Mo). Chacun contient les identifiants (`day`, `flow_id`, IP, ports, `timestamp`, `label`) et les 78 caractéristiques.
- `data/processed/features.json` : la liste des 78 caractéristiques et la description du découpage.

**Figure :** `reports/02_fenetres_par_classe.png`. Ce sont des boîtes à moustaches des 4 caractéristiques de fenêtre pour chaque classe, en gris pour le benign, en bleu pour les attaques connues (train/val) et en orange pour les attaques inconnues (test).

### 3.4 Résultats obtenus

| Ensemble | Flux | dont attaques | Classes d'attaque | Jours |
|---|---|---|---|---|
| train | 945 640 | 146 610 | 7 | lun, mar, mer |
| val | 236 415 | 36 656 | 7 | lun, mar, mer |
| test | 655 443 | 258 557 | 6 | jeu, ven |

- La somme fait bien 1 837 498 flux : aucun n'est perdu.
- Chaque attaque connue a exactement 20 % de ses flux en validation. Heartbleed fait exception avec 8 flux en train et 3 en val, trop peu pour une mesure fiable.
- **Contrôle automatique réussi :** pour chaque groupe, le premier flux de validation est postérieur au dernier flux d'entraînement.
- `flag_urg`, `fwd_flag_urg` et `bwd_flag_urg` sont retirées, car elles sont constantes sur train. Il reste **78 caractéristiques** (74 de flux + 4 de fenêtre).
- Après relecture des fichiers, `timestamp` est bien resté en `float64`.

**Ce que montrent les fenêtres** (médianes par classe) :

| Classe | w_conn | w_dst_ports | w_dst_hosts | w_rst_rate |
|---|---|---|---|---|
| benign | ≈ 247 | 4 | ≈ 33 | ≈ 0,001 |
| ftp_patator / ssh_patator | 66 / 50 | 1 | 1 | 0 |
| webattack_xss / bruteforce (test) | 35 | 1 | 1 | 0 |
| bot (test) | 19 | 4 | 5 | 0 |
| ddos (test) | 4 903 | 1 | 1 | 0 |
| dos_hulk | 9 688 | 1 | 1 | 0 |
| portscan (test) | 43 868 | **997** | 1 | **0,99** |

- **Portscan est très facile à repérer** grâce aux fenêtres : près de 1 000 ports différents par minute et presque toujours un RST.
- **DDoS ressemble à dos_hulk** (des milliers de connexions par minute vers un seul port). Le Random Forest devrait donc au moins le classer comme « attaque », même avec un mauvais nom.
- **Les attaques web ressemblent aux attaques patator** (quelques dizaines de connexions par minute vers un seul port) : risque de confusion.
- **Bot ressemble au trafic normal :** c'est probablement l'attaque la plus difficile à détecter.
- Un grand `w_conn` n'est pas à lui seul un signe d'attaque, car beaucoup de sources normales sont des serveurs très actifs.

**Limites à citer dans le rapport :**
1. La validation benign vient de la fin de journée, alors que la validation d'une attaque vient de la fin de cette attaque (souvent le matin). Les deux ne correspondent donc pas aux mêmes heures.
2. Les fenêtres sont fixes et non glissantes : une rafale à cheval sur deux minutes est coupée en deux.

**Aucune normalisation (scaler) ici.** Elle sera ajustée sur train dans les notebooks 03 et 04, pour ne rien apprendre du test.

**Fichiers modifiés :** `CLAUDE.md` (règle 1 réécrite, état d'avancement, planning).

---

## Étape 4 · 3 novembre 2026 · Code simplifié en « code d'étudiant »

**Demande de Bedis :** tout le code doit pouvoir être compris et expliqué à la professeure par un étudiant de M2 Data Science. Il doit donc être simple et lisible, sans astuces, avec les mêmes résultats.

**Ce qui a été fait :**
- `src/isocrates/ml/data.py`, `prepare.py` et `supervised.py` sont réécrits avec des boucles `for` simples, des variables intermédiaires nommées, une docstring par fonction et des commentaires en français qui expliquent le *pourquoi*. Les lambdas, les chaînes de méthodes pandas et le pipeline sklearn ont été retirés.
  - Exemple, le découpage train/val (`temporal_split`) se lit maintenant comme une recette : « pour chaque groupe (une attaque, ou le benign d'un jour), je trie les flux par temps ; les premiers 80 % vont en train, le reste en val ».
  - Exemple, la mise à l'échelle du MLP : avant, elle était cachée dans un pipeline ; maintenant ce sont deux lignes visibles, `signed_log(X)` puis `StandardScaler`.
- Les notebooks 01 et 02 sont réécrits dans le même style et relancés.
- **Vérification :** une empreinte (hash) des fichiers `train/val/test.parquet` a été calculée avant et après la réécriture. Elle est **identique**, donc les données produites sont exactement les mêmes. Tous les chiffres des notebooks 01 et 02 sont inchangés.
- La règle « style code d'étudiant » est ajoutée dans `CLAUDE.md` (section 6), pour toutes les prochaines étapes.

---

## Étape 5 · 3 novembre 2026 · Notebook 03 : Random Forest vs MLP, explications SHAP

> **Note du 4 novembre :** les chiffres et le choix de cette étape viennent de l'ancien découpage 80/20. Ils sont remplacés par ceux de l'étape 6. En particulier, le RF n'est plus meilleur que le MLP sur val.

### 5.1 Notions utiles

- **Random Forest (RF) :** un ensemble de 100 arbres de décision. Chaque arbre pose une suite de questions du type « `w_conn` > 500 ? », et la forêt vote. C'est le modèle de référence sur les données en tableau.
- **MLP (perceptron multicouche) :** un petit réseau de neurones. Il a besoin de données à la même échelle. On applique donc d'abord `sign(x)·log(1+|x|)`, qui écrase les valeurs énormes comme les débits ou les durées en microsecondes, puis une standardisation (moyenne 0, écart-type 1) calculée sur train seulement.
- **Époque :** un passage complet du MLP sur toutes les données d'entraînement.
- **Précision / rappel / F1, par classe :**
  - la précision répond à « quand le modèle dit X, a-t-il raison ? » ;
  - le rappel répond à « parmi les vrais X, combien en trouve-t-il ? » ;
  - le F1 est la moyenne harmonique des deux.
- **Macro-F1 :** la moyenne des F1 des 8 classes. Une petite classe compte autant qu'une grande, donc on ne peut pas tricher en ne réussissant que le benign.
- **Poids de classe :** ils donnent plus d'importance aux flux des classes rares pendant l'apprentissage.
- **SHAP :** une méthode qui calcule, pour un flux donné, combien chaque caractéristique a poussé le modèle vers une classe (valeur positive) ou l'en a éloigné (valeur négative). `TreeExplainer` est sa version exacte et rapide pour les forêts d'arbres.

### 5.2 Fichiers

- **Créé :** `src/isocrates/ml/supervised.py`. On y trouve le chargement des Parquet (`load_sets`), `signed_log`, les poids de classe (`sqrt_balanced_weights`), l'entraînement du RF (`fit_rf`) et du MLP (`fit_mlp`), les tableaux de métriques (`per_class_report`, `detection_by_class`) et la sauvegarde des modèles.
- **Créé :** `notebooks/03_supervise_rf_mlp.ipynb`, exécuté de bout en bout (environ 16 min).
- **Figures :**
  - `reports/03_mlp_epoques.png` : courbes d'apprentissage du MLP ;
  - `reports/03_confusion_val.png` : matrices de confusion sur val ;
  - `reports/03_detection_test.png` : détection par classe sur le test ;
  - `reports/03_shap_global.png` : caractéristiques les plus influentes par classe ;
  - `reports/03_shap_exemple.png` : explication d'une alerte.
- **Modèles :** `models/rf.joblib` (0,8 Mo) et `models/mlp.joblib` (0,3 Mo, avec son scaler). Ils ne sont pas versionnés dans Git.

### 5.3 Méthode

1. **RF :** 6 essais, avec une profondeur maximale de 10, 20 ou illimitée, et avec ou sans poids de classe. On garde celui qui a le meilleur macro-F1 sur **val**.
2. **MLP :** 3 tailles de réseau (64-32, 128-64, 256-128), 20 époques chacune. Après chaque époque, on mesure le macro-F1 sur val et on garde la meilleure époque. On n'utilise pas l'arrêt automatique de sklearn, car il tirerait sa validation **au hasard**, ce qui est interdit.
3. **Déséquilibre :** chaque flux du MLP reçoit un poids égal à la racine carrée du poids « balanced » de sklearn. Le poids « balanced » pur donnerait plus de 10 000 aux 8 flux heartbleed et ferait diverger l'apprentissage.
4. **Test (attaques jamais vues) :** les modèles ne peuvent pas donner le bon nom, puisqu'ils ne connaissent pas ces attaques. On mesure donc seulement la **détection**, c'est-à-dire la part des flux classés comme « une attaque quelconque ».

### 5.4 Résultats obtenus

**Réglages :** RF avec une profondeur de 10 et sans poids de classe (macro-F1 val **0,968**). MLP 128-64 à l'époque 16 (macro-F1 val **0,964**).

**Val (attaques connues), F1 par classe :**

| Classe | RF | MLP |
|---|---|---|
| benign | 1,000 | 1,000 |
| dos_goldeneye | 0,997 | 0,996 |
| dos_hulk | 1,000 | 1,000 |
| dos_slowhttptest | 0,896 | 0,870 |
| dos_slowloris | 0,884 | 0,861 |
| ftp_patator | 1,000 | 1,000 |
| heartbleed (3 flux) | 1,000 | 1,000 |
| ssh_patator | 0,967 | 0,983 |

Le point faible commun est dos_slowloris, pris pour dos_slowhttptest dans 19 % (RF) à 24 % (MLP) des cas : ce sont deux attaques « lentes » très proches.

**Test (attaques inconnues), part des flux détectés comme attaque :**

| Classe | RF | MLP |
|---|---|---|
| ddos | 98,6 % | 100 % |
| webattack_xss | 0,2 % | 99,7 % |
| webattack_bruteforce | 0 % | 94,0 % |
| webattack_sql_injection | 0 % | 16,7 % (2 sur 12) |
| portscan | 0 % | 0 % |
| bot | 0 % | 0 % |
| benign (fausses alertes) | 1 flux sur 396 886 | 46 flux (0,012 %) |

- Le RF range la DDoS sous « dos_hulk », un nom faux mais une alerte utile.
- **Le MLP généralise mieux aux attaques web.** Une hypothèse, non démontrée : un arbre ne peut répondre qu'avec des zones vues pendant l'entraînement, alors que les frontières d'un réseau de neurones se prolongent au-delà.
- **Portscan et bot échappent aux deux modèles.** C'est le rôle du détecteur d'anomalies (notebook 04).

**SHAP :**
- Les caractéristiques de fenêtre sont parmi les plus utilisées : `w_conn` pour dos_hulk et goldeneye, `w_dst_hosts` pour presque toutes les classes.
- Pour ftp et ssh_patator, c'est `dst_port` (ports 21 et 22) qui compte le plus. Cette règle est simple mais fragile si l'attaquant change de port.
- **Exemple d'alerte :** seuls 35 flux de portscan sur 160 106 sont signalés par le RF. Celui qui est expliqué est appelé « dos_goldeneye » (probabilité 0,45), surtout à cause de son grand `w_conn`, alors que `w_dst_ports` = 999 tire dans l'autre sens. **Leçon :** pour une attaque inconnue, l'étiquette du RF n'est qu'un indice, et les agents devront la présenter comme telle.

**Choix pour la suite :** on garde le **RF** dans le pipeline, pour son meilleur macro-F1 sur val, ses fausses alertes plus rares, sa vitesse et l'explication exacte qu'en donne SHAP. La meilleure généralisation du MLP est un résultat à présenter dans la comparaison.

**Corrections en cours de route :**
- Un premier tirage de l'échantillon SHAP était mal fait : pandas alignait des étiquettes par position au lieu de les aligner par index. Il est remplacé par une boucle simple qui tire 100 flux par classe.
- Les autres chiffres ne changent pas.

**Fichiers modifiés :** `CLAUDE.md` (état d'avancement).

---

## Étape 6 · 4 novembre 2026 · Ajout d'un « test connu » : découpage 70/15/15

### 6.1 Décision de Bedis et raison

**Problème :** les performances sur les attaques connues étaient mesurées sur la validation. Or la validation sert aussi à choisir les réglages (profondeur du RF, taille du MLP, meilleure époque). On choisit ce qui marche le mieux sur ces flux-là, donc le score obtenu est un peu optimiste. Il faut une mesure sur des flux qui n'ont servi à aucun choix. Mais LYCOS ne rejoue aucune attaque un autre jour : jeudi et vendredi ne contiennent que des attaques inconnues.

**Solution :** garder 15 % des flux les plus récents de lundi, mardi et mercredi comme **test connu**.

| Ensemble | Contenu | Rôle |
|---|---|---|
| train | 70 % les plus anciens de chaque attaque ; benign 70 % dans chaque jour | apprendre |
| val | 15 % suivants | choisir les réglages |
| test_connu | 15 % les plus récents | mesure finale des attaques connues, **une seule fois** |
| test_inconnu | jeudi + vendredi en entier | détection des attaques jamais vues |

On ne mélange jamais au hasard : dans chaque groupe, val vient après train et test_connu après val. Le code le vérifie avec un `assert`.

### 6.2 Fichiers

- **Modifiés :** `src/isocrates/ml/prepare.py` (`temporal_split` en 3 parties, nouvelle fonction `split_groups`) et `src/isocrates/ml/supervised.py` (`load_sets`, nouvelle fonction `macro_f1_without`).
- **Modifiés et relancés :** `notebooks/02_preparation.ipynb` et `notebooks/03_supervise_rf_mlp.ipynb`.
- **Données :** `data/processed/train.parquet`, `val.parquet`, `test_connu.parquet`, `test_inconnu.parquet` et `features.json`. L'ancien `test.parquet` est supprimé, après avoir vérifié qu'il était identique à `test_inconnu.parquet`.
- **Figure ajoutée :** `reports/03_confusion_test_connu.png`. Les autres figures des notebooks 02 et 03 sont régénérées.
- **Modèles :** `models/rf.joblib` et `models/mlp.joblib` sont remplacés.
- **Modifié :** `CLAUDE.md` (règles 1, 5 et 7, état d'avancement).

### 6.3 Résultats du découpage

| Ensemble | Flux | dont attaques |
|---|---|---|
| train | 827 434 | 128 283 |
| val | 177 308 | 27 490 |
| test_connu | 177 313 | 27 493 |
| test_inconnu | 655 443 | 258 557 |

- La somme fait bien 1 837 498 flux.
- La garantie temporelle est vérifiée pour les 10 groupes.
- `test_inconnu` a la même empreinte (hash) que l'ancien `test` : il n'a pas changé.
- Toujours 78 caractéristiques. Les colonnes constantes et le scaler sont décidés sur train seulement.

### 6.4 Heartbleed

Heartbleed n'a que 11 flux : 7 en train, 2 en val, 2 en test_connu. Avec 2 flux, son F1 ne peut valoir que 0, 0,67 ou 1. Il est donc **gardé, mais exclu du macro-F1 de test_connu**, et le notebook le dit clairement. Sa ligne reste affichée à titre indicatif.

Le critère de choix sur val reste le macro-F1 des 8 classes, heartbleed compris. Il a été fixé avant de calculer toute prédiction sur test_connu : une grille a d'abord été lancée sur val seule, sans charger test_connu.

### 6.5 Résultats des modèles

**Réglages choisis sur val :** RF de profondeur 20, sans poids de classe ; MLP (128, 64) à l'époque 9.

**Macro-F1 (sans heartbleed pour pouvoir comparer) :**

| | Val | test_connu | Écart |
|---|---|---|---|
| RF | 0,9722 | **0,9574** | −0,015 |
| MLP | 0,9743 | **0,9334** | −0,041 |

La val était bien optimiste, comme attendu. Le classement s'inverse : le MLP était très légèrement devant sur val, le RF est devant sur test_connu.

**F1 par classe :**

| Classe | RF ancien (val) | RF val | RF test_connu | MLP ancien (val) | MLP val | MLP test_connu |
|---|---|---|---|---|---|---|
| benign | 1,000 | 0,999 | 0,999 | 1,000 | 0,999 | 1,000 |
| dos_goldeneye | 0,997 | 1,000 | 0,997 | 0,996 | 0,993 | 0,996 |
| dos_hulk | 1,000 | 1,000 | 0,997 | 1,000 | 1,000 | 0,997 |
| dos_slowhttptest | 0,896 | 0,835 | 0,875 | 0,870 | 0,856 | 0,764 |
| dos_slowloris | 0,884 | 0,983 | **0,862** | 0,861 | 0,996 | **0,786** |
| ftp_patator | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| heartbleed (2-3 flux, non fiable) | 1,000 | 1,000 | 0,667 | 1,000 | 1,000 | 1,000 |
| ssh_patator | 0,967 | 0,989 | 0,972 | 0,983 | 0,977 | 0,991 |

L'ancienne val (les 20 % les plus récents) n'est pas la nouvelle val (de 70 à 85 %), donc la comparaison de ces colonnes est indicative.

**test_inconnu, part des flux signalés comme attaque :**

| Classe | RF ancien | RF nouveau | MLP ancien | MLP nouveau |
|---|---|---|---|---|
| ddos | 98,6 % | 97,7 % | 100 % | 99,9 % |
| webattack_xss | 0,2 % | 11,3 % | 99,7 % | 99,7 % |
| webattack_bruteforce | 0 % | 10,9 % | 94,0 % | 94,3 % |
| webattack_sql_injection | 0 sur 12 | 1 sur 12 | 2 sur 12 | 0 sur 12 |
| portscan | 35 flux | 55 flux | 0 % | 4 flux |
| bot | 0 % | 0 % | 0 % | 0 % |
| benign (fausses alertes) | 1 flux | 10 flux | 46 flux | 38 flux |

### 6.6 Ce qu'il faut retenir

1. **Le test connu a trouvé une faiblesse que la val cachait.** Le F1 de dos_slowloris passe de 0,983 à 0,862 pour le RF et de 0,996 à 0,786 pour le MLP. Sur test_connu, 199 flux slowloris sur 852 sont pris pour dos_slowhttptest par le RF, 289 par le MLP. Ces flux déclenchent quand même une alerte : seul le nom est faux.
2. **Le comportement change au cours d'une même attaque.** Sur val, le problème était ailleurs : 174 des 730 flux dos_slowhttptest passent pour du benign (RF).
3. **Le MLP généralise toujours mieux sur les attaques web inconnues.** Portscan et bot restent pour le notebook 04.

### 6.7 Corrections d'affirmations précédentes

- **« Le RF a le meilleur macro-F1 sur val »** (étape 5) n'est plus vrai : 0,9757 contre 0,9775 pour le MLP. Le RF reste dans le pipeline parce que l'architecture le prévoit et que SHAP TreeExplainer l'explique exactement, pas pour ses performances. On ne peut pas non plus s'appuyer sur test_connu pour choisir (règle 7).
- **« La profondeur 10 est la meilleure »** (étape 5) ne tient plus : sur la nouvelle val, la profondeur 20 fait mieux. Le grand écart observé avant (0,968 contre 0,939) venait vraisemblablement de heartbleed (3 flux en val), mais l'ancienne val n'existant plus, ce n'est pas vérifié.
- **« Le RF ne voit aucune attaque web »** dépendait du réglage : il en détecte maintenant environ 11 %.
- **La cellule Observations du notebook 03** était vide dans le commit de l'étape 03, contrairement à ce qui avait été annoncé. Elle est maintenant remplie.

### 6.8 Limites à citer dans le rapport

**Phrase de limite :** « Le test connu vient du même jour que l'entraînement et le suit immédiatement dans le temps, car LYCOS-IDS2017 ne rejoue aucune attaque un autre jour. Ses scores mesurent donc la suite d'une attaque déjà vue et sont plus faciles à obtenir que la détection d'une attaque rejouée un autre jour. »

Autres limites :
- La garantie temporelle vaut dans chaque groupe, pas entre groupes : le benign de test_connu vient de la fin de journée, alors que l'attaque vient souvent du matin.
- Les fenêtres sont calculées avant le découpage : deux flux de la même minute, de part et d'autre d'une coupure, partagent les mêmes valeurs `w_*`.

---

## Étape 7 · 4 novembre 2026 · PyTorch et notebook 04 : autoencodeur vs Isolation Forest

### 7.1 Notions utiles

- **Détecteur d'anomalies :** un modèle qui apprend seulement le trafic normal, puis signale ce qui n'y ressemble pas. Il n'a besoin d'aucun exemple d'attaque, c'est pourquoi il peut repérer des attaques jamais vues. En revanche, il ne donne pas leur nom.
- **Autoencodeur :** un réseau de neurones qui apprend à recopier son entrée en la faisant passer par un **goulot**, une couche étroite. Ici : 78 → 64 → 8 → 64 → 78. Il doit donc résumer le trafic normal. Un flux inhabituel est mal recopié, et son **erreur de reconstruction** sert de score d'anomalie.
- **Isolation Forest :** une forêt qui isole chaque flux par des coupures au hasard. Un flux anormal s'isole en peu de coupures, et reçoit donc un score élevé.
- **Seuil :** le score au-dessus duquel on lance une alerte. Ici, le 99e percentile du score sur le benign de val : par construction, 1 % de ce benign déclenche une alerte.
- **AUC :** mesure si les scores d'une attaque sont plus élevés que ceux du benign, sans dépendre du seuil. 1 = séparation parfaite, 0,5 = hasard.
- **Rappel moyen :** la moyenne des parts détectées de chaque classe d'attaque, chacune comptant autant.
- **Dans la boucle d'entraînement PyTorch (`fit_autoencoder`) :** pour chaque lot de flux, le réseau les recopie, on mesure l'erreur (`loss`), la rétropropagation calcule comment corriger chaque poids (`backward`), puis l'optimiseur Adam les met à jour (`step`).

### 7.2 Décision de Bedis et installation

Bedis a choisi PyTorch plutôt que sklearn, pour la valeur de cette compétence sur son CV. PyTorch 2.15.0 (version CPU) est installé dans l'environnement `isocrates`. Le test de bon fonctionnement passe, et le RF enregistré se recharge sans problème.

### 7.3 Fichiers

- **Créé :** `src/isocrates/ml/anomaly.py`. On y trouve la classe `Autoencoder`, `fit_autoencoder`, `reconstruction_error`, `fit_isolation_forest`, `isolation_score`, `threshold_from_benign`, `detection_table` et `mean_attack_recall`.
- **Créé :** `notebooks/04_anomalies_ae_if.ipynb`, exécuté de bout en bout.
- **Figures :** `reports/04_ae_courbes.png`, `04_detection_test_inconnu.png`, `04_scores_par_classe.png`.
- **Modèles :** `models/autoencoder.pt`, `autoencoder_meta.joblib`, `isolation_forest.joblib`, `anomaly_choice.joblib` (non versionnés dans Git).
- **Modifié :** `CLAUDE.md`. PyTorch y est marqué comme installé, et l'avancement est à jour. La phrase « le meilleur sur val/test est gardé » devient « le meilleur sur val », car elle contredisait la règle 7.

### 7.4 Protocole (fixé avant tout calcul)

1. Entraînement sur le **benign de train uniquement** : 699 151 flux.
2. Log signé et standardisation ajustés sur ces mêmes flux, pour l'autoencodeur.
3. Autoencodeur : goulot de 8, 16 ou 32, avec 20 époques, en gardant l'époque à la plus faible erreur sur le benign de val.
4. Isolation Forest : `max_samples` de 256 ou 4096.
5. Seuil de chaque modèle fixé sur le benign de val.
6. Choix des réglages et du modèle retenu **sur val**, par le rappel moyen sans heartbleed.
7. test_connu et test_inconnu servent seulement à mesurer.

Val ne contient que des attaques connues : rien ne garantissait donc que le modèle choisi soit aussi le meilleur sur les attaques inconnues.

### 7.5 Résultats obtenus

**Choix sur val :** autoencodeur, goulot 8.

| Goulot | Erreur val | Rappel moyen val |
|---|---|---|
| 8 (retenu) | 0,0206 | **0,874** |
| 16 | 0,0071 | 0,677 |
| 32 | 0,0020 | 0,836 |

Isolation Forest : 0,038 avec `max_samples` = 256, **0,255** avec 4096 (retenue).

**Rappel moyen :**

| | Val | test_connu | test_inconnu |
|---|---|---|---|
| Autoencodeur | 0,874 | 0,950 | 0,469 |
| Isolation Forest | 0,255 | 0,268 | 0,090 |

**test_inconnu, par classe :**

| Classe | Flux | Autoencodeur | AUC | Isolation Forest | AUC | RF (notebook 03) | MLP (notebook 03) |
|---|---|---|---|---|---|---|---|
| portscan | 160 106 | **100,0 %** | 0,999 | 0,5 % | 0,972 | 0,03 % | 0,002 % |
| ddos | 95 683 | **100 %** | 0,997 | 39,6 % | 0,981 | 97,7 % | 99,9 % |
| bot | 735 | **73,5 %** | 0,987 | 6,0 % | 0,649 | 0 % | 0 % |
| webattack_bruteforce | 1 360 | 5,4 % | 0,946 | 5,2 % | 0,696 | 10,9 % | **94,3 %** |
| webattack_xss | 661 | 2,7 % | 0,945 | 2,7 % | 0,686 | 11,3 % | **99,7 %** |
| webattack_sql_injection | 12 | 0 sur 12 | 0,940 | 0 sur 12 | 0,735 | 1 sur 12 | 0 sur 12 |
| benign (fausses alertes) | 396 886 | 1,53 % | | 1,19 % | | 10 flux | 38 flux |

**test_connu, autoencodeur :** dos_hulk 100 %, ftp_patator 100 %, dos_slowhttptest 99,9 %, ssh_patator 98,0 %, dos_slowloris 87,7 %, dos_goldeneye 84,3 % ; fausses alertes 0,99 %.

### 7.6 Ce qu'il faut retenir

1. **L'autoencodeur fait ce pour quoi il est là, en partie :** il attrape portscan, DDoS et la plupart du bot. La règle 6 du projet (« l'autoencodeur doit les attraper ») n'est donc **que partiellement remplie : il rate les attaques web**.
2. **Les attaques web passent entre les mailles de RF + autoencodeur.** Leur AUC est élevée (environ 0,94), mais leurs scores restent sous le seuil. Seul le MLP les détecte.
3. **Bot est fragile :** ses scores sont serrés juste autour du seuil, donc 73,5 % pourrait beaucoup changer avec un seuil un peu différent.
4. **Fausses alertes plus nombreuses que prévu :** 1,53 % au lieu de 1 % sur test_inconnu, soit 6 065 flux. Le trafic normal des autres jours s'éloigne un peu de celui appris. Le regroupement en incidents devra réduire cette charge.
5. **La précision de 97,7 % est flatteuse :** portscan et DDoS représentent 39 % des flux de test_inconnu. Avec moins d'attaques, comme dans un vrai réseau, elle serait bien plus basse.

### 7.7 Limites à citer dans le rapport

- **Une seule graine :** le rappel moyen n'évolue pas régulièrement avec le goulot (0,874, 0,677, 0,836). On ne sépare donc pas l'effet du goulot du hasard de l'entraînement.
- **Pas de plateau :** les 3 réseaux ont leur meilleure erreur à la dernière époque.
- **Critère de choix limité :** il ne repose que sur des attaques connues, celles de val.

---

## Étape 8 · 4 novembre 2026 · Vérification : le MLP triche-t-il ?

### 8.1 Question de Bedis

Sur test_inconnu, le MLP détectait 94 % des webattack_bruteforce et 99,7 % des webattack_xss. Bedis a trouvé ces chiffres suspects, puisqu'il cite une fourchette de 1 à 19 % pour un supervisé face à des attaques web jamais vues (Xu et Liu 2025, arXiv 2506.19877 ; **référence fournie par Bedis, non vérifiée ici, à contrôler avant de la citer**).

**Hypothèse testée :** un **raccourci** (*shortcut learning*), c'est-à-dire que le modèle apprend un détail facile au lieu de la vraie notion. Ici, il reconnaîtrait la machine de l'attaquant (pile TCP, rythme des outils) plutôt que le comportement d'attaque. Les attaques web et ssh/ftp_patator viennent en effet de la même machine, `172.16.0.1`.

### 8.2 Notions utiles

- **Importance par permutation :** on mélange une colonne et on regarde combien la détection baisse. Si elle baisse beaucoup, la colonne est décisive.
- **SHAP KernelExplainer :** version de SHAP qui marche pour tout modèle. Elle estime ce que chaque colonne apporte à la probabilité « attaque » d'un flux.
- **Graine :** le nombre qui fixe le hasard de l'entraînement. Changer de graine et comparer montre ce qui tient et ce qui vient du hasard.
- **Moyenne ± écart-type :** l'écart-type mesure la dispersion entre graines. Grand écart-type = résultat instable.

### 8.3 Fichiers

- **Créés :** `src/isocrates/ml/verification.py` et `notebooks/04b_verification_mlp.ipynb`.
- **Figures :** `reports/04b_colonnes_decisives.png`, `04b_mlp_sans_colonnes.png`, `04b_stabilite_autoencodeur.png`, `04b_mlp_par_epoque.png`.
- **Non versionné :** `models/04b_resultats.joblib` garde les résultats de chaque entraînement.
- **Modifiés :** `CLAUDE.md`, et une note de renvoi dans les observations des notebooks 03 et 04.

Aucun modèle du pipeline n'a changé. test_connu n'a pas été utilisé. test_inconnu a servi à mesurer, pas à choisir.

### 8.4 Méthode

**Prévu avant les calculs :**
- test direct sur le trafic normal de `172.16.0.1` (ajouté par Claude, non demandé par Bedis) ;
- colonnes décisives sur les flux web détectés ;
- MLP réentraîné (128, 64) sans colonnes TCP, sans rythme, sans les deux, et sans le top 15, avec 5 graines chacun ;
- stabilité de l'autoencodeur : goulots 8, 16 et 32, avec 5 graines chacun ;
- règle de lecture : chute si la détection moyenne passe sous 50 % **et** baisse de plus de 2 écarts-types.

**Ajouté après avoir vu les premiers résultats, donc à présenter comme tel :**
- MLP sans les 4 colonnes de fenêtre ;
- étude du trafic normal au profil « 1 machine, 1 port » ;
- suivi de la détection époque par époque.

LYCOS n'a ni colonne TTL ni options TCP. Seule la longueur d'en-tête en donne un indice indirect.

### 8.5 Résultats

**Colonnes décisives sur les flux web (part de l'importance SHAP) :** fenêtres de 60 s **63 %**, connexion TCP 14 %, taille et volume 14 %, destination 6 %, rythme 3 %. Les trois premières colonnes sont `w_dst_ports` (0,32), `w_dst_hosts` (0,30) et `fwd_pkt_hdr_len_min` (0,09, de type TCP). Le MLP range les attaques web surtout sous `dos_slowloris` (88 à 93 %).

**Retrait de colonnes, moyenne ± écart-type sur 5 graines :**

| Variante | Colonnes | bruteforce | xss | portscan |
|---|---|---|---|---|
| MLP complet | 78 | 75,3 % ± 37,8 | 79,2 % ± 42,7 | 0,0 % |
| Sans connexion TCP | 63 | 94,5 % ± 2,9 | 98,4 % ± 2,3 | 0,0 % |
| Sans rythme | 56 | 77,2 % ± 40,3 | 79,9 % ± 43,0 | 0,0 % |
| Sans TCP ni rythme | 41 | 81,0 % ± 29,6 | 82,0 % ± 39,0 | 0,0 % |
| Sans top 15 (diagnostic) | 63 | 0,0 % ± 0,0 | 1,1 % ± 1,5 | 99,8 % ± 0,1 |
| **Sans fenêtres 60 s (ajouté)** | 74 | **0,1 %** | **2,3 %** | 0,5 % |

**Le profil « 1 machine et 1 port par minute » :**

| Ensemble | Flux avec ce profil |
|---|---|
| Attaques de train | **128 283 sur 128 283 (100 %)** |
| Benign de train | 61 782 sur 699 151 (8,8 %) |
| Attaques web de test_inconnu | 2 033 sur 2 033 (100 %) |
| Benign de test_inconnu | 32 620 sur 396 886, dont **28 alertes (0,09 %)** |

**Trafic normal de la machine de l'attaquant :** le MLP signale 28 flux sur 415 (6,7 %), contre 10 sur 396 471 pour les autres machines. Le RF : 10 sur 415 (2,4 %), contre 0.

**Détection selon la règle d'arrêt du MLP complet :**

| Graine | Protocole (macro-F1 avec heartbleed) | Sans heartbleed | Époque 20 |
|---|---|---|---|
| 0 | époque 9 : 94,3 % / 99,7 % | époque 6 : 93,2 % / 98,2 % | 94,3 % / 99,7 % |
| 1 | époque 6 : 89,6 % / 99,4 % | époque 6 : 89,6 % / 99,4 % | 99,9 % / 99,8 % |
| 2 | **époque 1 : 7,9 % / 3,0 %** | époque 13 : 89,0 % / 99,4 % | 88,9 % / 99,7 % |
| 3 | époque 7 : 94,2 % / 99,4 % | époque 7 : 94,2 % / 99,4 % | 93,8 % / 99,7 % |
| 4 | époque 4 : 90,5 % / 94,7 % | époque 4 : 90,5 % / 94,7 % | 94,0 % / 99,4 % |

(chaque case : bruteforce / xss)

**Autoencodeur, 5 graines :**

| Goulot | Rappel moyen val | bot | bruteforce | xss | ddos | portscan | Fausses alertes |
|---|---|---|---|---|---|---|---|
| 8 (retenu) | 0,869 ± 0,072 | **48,0 % ± 33,6** | 5,2 % ± 0,3 | 2,7 % ± 0,0 | 100 % | 100 % | 1,4 % ± 0,1 |
| 16 | 0,720 ± 0,145 | 6,3 % ± 0,5 | 0,0 % | 2,2 % ± 1,2 | 100 % | 100 % | 1,3 % |
| 32 | 0,579 ± 0,156 | 6,0 % | 1,0 % ± 2,2 | 2,6 % ± 0,2 | 98,7 % ± 2,9 | 100 % | 1,2 % |

### 8.6 Conclusions, sans arrondir les angles

1. **La forme précise de l'hypothèse (pile TCP, rythme) n'est pas soutenue.** Retirer ces colonnes ne fait pas chuter la détection.
2. **Il y a pourtant une dépendance forte à une propriété du scénario.** La détection des attaques web repose sur les fenêtres : sans elles, elle tombe à 0,1 % et 2,3 % sur les 5 graines. Or **toutes** les attaques de train ont le profil « 1 machine, 1 port par minute », car elles ont été jouées ainsi dans le banc d'essai. Le MLP apprend donc en partie la façon dont les attaques ont été jouées. **Le 94 à 99,7 % ne doit pas être présenté comme une capacité générale à détecter les attaques web.**
3. **Ce n'est pas une règle simple pour autant.** 99,9 % du benign au même profil n'est pas signalé : le MLP combine ce profil avec d'autres colonnes.
4. **Ce n'est pas non plus une preuve que le MLP reconnaît la machine.** Viser une seule cible peut être un vrai comportement d'attaque. Le taux d'alerte plus fort sur le benign de `172.16.0.1` (6,7 %) va dans ce sens, mais ces flux partagent leurs fenêtres avec les attaques de la même minute. LYCOS ne permet pas de trancher, car toutes les attaques web viennent d'une seule source.
5. **L'instabilité venait surtout de l'arrêt à l'époque 1.** Dès que le réseau a dépassé les premières époques, la détection des attaques web est stable : bruteforce 91,3 % ± 2,3, XSS 98,2 % ± 2,0 avec un arrêt sans heartbleed. Le choix de l'époque à l'époque 1 pour la graine 2 vient de heartbleed (2 flux).
6. **Le 73,5 % de bot de l'autoencodeur n'est pas fiable :** 48,0 % ± 33,6, de 21,6 % à 94,3 %. Les autres chiffres sont stables : portscan et DDoS à environ 100 %, attaques web très basses.

### 8.7 Corrections de ce que Claude avait dit

- **« Le 94 à 99,7 % dépend du hasard de l'initialisation » :** en grande partie faux. Cet échec vient surtout de l'arrêt à l'époque 1, lié à heartbleed.
- **« La val ne permet pas de voir la différence » :** à nuancer. Le macro-F1 sans heartbleed choisit un bon modèle pour les 5 graines, mais cela n'a été constaté qu'en regardant test_inconnu.
- **La règle de chute fixée à l'avance a mal fonctionné.** L'écart-type du MLP complet (0,38) met le seuil de 2 écarts-types sous zéro : elle répond « pas de chute » même quand la détection passe de 75 % à 0 %. Elle reste telle quelle dans le notebook, et la lecture graine par graine la remplace, en le disant.
- **« Sans connexion TCP » semblait améliorer la détection (95 % ± 3) :** c'est un effet de la règle d'arrêt, aucune de ses graines ne s'arrêtant à l'époque 1. Ce n'est pas un gain réel lié au retrait des colonnes.
- **Le saut du portscan à 99,8 % sans le top 15 ne vient pas des fenêtres** (0,5 % sans elles seules). Sa cause n'est pas identifiée.

### 8.8 Phrases proposées pour le rapport

> Le MLP détecte 91 à 98 % des attaques web inconnues après l'époque 1, mais cette détection disparaît sans les caractéristiques de fenêtre (0,1 à 2,3 %). Comme toutes les attaques d'entraînement ciblent une seule machine et un seul port par minute, ce résultat dépend du scénario du banc d'essai et ne peut pas être généralisé à d'autres réseaux.

> La détection du bot par l'autoencodeur varie fortement selon la graine (48 % ± 34, de 22 % à 94 % sur 5 graines).

### 8.9 Limites

- Les tests ajoutés après coup et le top 15 dépendent de test_inconnu : ce sont des diagnostics.
- 5 graines donnent un ordre de grandeur de la dispersion, pas une mesure précise.
- Le MLP n'a été testé sur 5 graines qu'avec la taille (128, 64).
- Le RF et l'autoencodeur utilisent aussi les fenêtres, mais leur dépendance n'a pas été mesurée.

---

## Étape 9 · 5 novembre 2026 · Le RF et l'autoencodeur dépendent-ils des fenêtres ?

**Pourquoi :** l'étape 8 a montré que la détection web du MLP dépend des 4 colonnes de fenêtre. Bedis a validé la même vérification pour les deux modèles retenus.

**Méthode :** RF (profondeur 20) et autoencodeur (goulot 8), avec et sans les 4 colonnes, sur 5 graines. Le seuil vient du benign de val, et test_inconnu sert seulement à mesurer. Aucun modèle du pipeline ne change.

**Fichiers :** `notebooks/04c_fenetres_rf_ae.ipynb`, `reports/04c_fenetres_rf_ae.png`, `models/04c_resultats.joblib` (non versionné). `fit_rf` accepte maintenant une graine (`supervised.py`).

**Résultats, part détectée sur test_inconnu, moyenne [min ; max] sur 5 graines :**

| Modèle | Classe | Avec fenêtres | Sans fenêtres |
|---|---|---|---|
| RF | ddos | 97,3 % [96,0 ; 98,8] | 16,7 % [2,2 ; 43,5] |
| RF | webattack_bruteforce | 10,7 % [10,1 ; 11,0] | 1,3 % [0,5 ; 1,8] |
| RF | webattack_xss | 11,2 % [10,7 ; 11,3] | 0,3 % [0,0 ; 0,5] |
| Autoencodeur | portscan | 100 % [99,9 ; 100] | 99,0 % [96,0 ; 100] |
| Autoencodeur | ddos | 100 % | 91,2 % [61,9 ; 100] |
| Autoencodeur | bot | 49,3 % [21,6 ; 94,3] | 25,8 % [6,1 ; 99,9] |

**Ce qu'il faut retenir :**
1. **Les principales détections de l'autoencodeur tiennent sans les fenêtres :** le portscan presque entièrement, la DDoS sauf pour une graine. Elles ne reposent donc pas surtout sur le profil trouvé à l'étape 8.
2. **Le nom « dos_hulk » que le RF donne à la DDoS dépend fortement des fenêtres.**
3. **Bot est fragile dans tous les cas.** Même en relançant la même graine 0, on passe de 73,5 % à 80,0 %, pour un rappel sur val presque identique (0,8739 et 0,8737). Le modèle enregistré redonne bien 73,5 %. Sa moyenne de 49,3 % diffère légèrement du 48,0 % de l'étape 8 pour cette raison.
4. **Limite :** ces tests ne disent pas ce que feraient les modèles sur un autre réseau.

---

## Étape 10 · 5 novembre 2026 · Notebook 05 : fusion et incidents

### 10.1 Notions utiles

- **Fusion :** on combine les deux modèles pour chaque flux. Si le RF signale une attaque, on garde son nom ; sinon, si le score de l'autoencodeur dépasse le seuil, le flux est marqué « inconnu » ; sinon, pas d'alerte.
- **Incident :** un groupe d'alertes de la même IP source, séparées par moins de 5 minutes. C'est ce que lira l'analyste, et ce que recevront les agents LLM.
- **Incident sans attaque :** un incident dont tous les flux sont en réalité normaux, donc une fausse alerte pour l'analyste.
- **Incident mixte :** un incident qui contient à la fois des flux d'attaque et des flux normaux.

### 10.2 Décision et fichiers

Bedis a validé **RF + autoencodeur**. Le MLP reste un résultat de comparaison.

- **Créés :** `src/isocrates/ml/fusion.py` et `notebooks/05_fusion_incidents.ipynb`.
- **Figures :** `reports/05_fusion_par_classe.png`, `05_incidents_par_machine.png`. Exemple versionné : `reports/05_exemple_incident.json`.
- **Données (non versionnées) :** `data/processed/incidents/test_connu.json`, `test_inconnu.json`, et à part, `verite_test_connu.json`, `verite_test_inconnu.json`.

Aucun réentraînement ni réglage. **La vraie étiquette n'entre jamais dans un incident :** elle est rangée à part pour l'évaluation, et le code le contrôle.

Chaque incident contient : l'IP source, les heures, le nombre de flux, les étiquettes et les sources, les machines et ports contactés, les scores, les fenêtres maximales et deux explications (SHAP pour le RF, colonnes les plus mal reconstruites pour l'autoencodeur).

### 10.3 Résultats par flux

**test_inconnu :**

| Classe | Flux | Nom d'une attaque connue | « inconnu » | Sans alerte | Part en alerte | RF seul | Autoencodeur seul |
|---|---|---|---|---|---|---|---|
| portscan | 160 106 | 55 | 160 047 | 4 | 100,0 % | 0,03 % | 100,0 % |
| ddos | 95 683 | 93 507 | 2 176 | 0 | 100 % | 97,7 % | 100 % |
| bot | 735 | 0 | 540 | 195 | 73,5 % | 0 % | 73,5 % |
| webattack_bruteforce | 1 360 | 148 | 73 | 1 139 | 16,3 % | 10,9 % | 5,4 % |
| webattack_xss | 661 | 75 | 18 | 568 | 14,1 % | 11,3 % | 2,7 % |
| webattack_sql_injection | 12 | 1 | 0 | 11 | 8,3 % | 8,3 % | 0 % |
| benign | 396 886 | 10 | 6 065 | 390 811 | **1,53 %** | | |

Pour bot, retenir 49 % en moyenne sur 5 graines plutôt que 73,5 %.

**test_connu :** part en alerte de 97,97 à 100 % sur toutes les classes ; fausses alertes 0,99 %. Bon nom : dos_hulk 23 710 sur 23 849, dos_goldeneye 1 009 sur 1 015, dos_slowhttptest 727 sur 730, dos_slowloris **647 sur 852**, ftp_patator 601 sur 601, ssh_patator 420 sur 444, heartbleed 1 sur 2.

### 10.4 Résultats par incident

| | test_connu | test_inconnu |
|---|---|---|
| Flux en alerte | 28 960 | 262 715 |
| Incidents | 239 | **487** |
| Incidents avec attaque | 7 | 13 |
| dont avec aussi du benign | 0 | 12 |
| Incidents sans attaque | 232 | **474** |
| Part sans attaque | 97,1 % | **97,3 %** |

Sur test_inconnu, chaque attaque est présente dans au moins un incident : portscan 5, bot 5 (une par machine source), DDoS 1, bruteforce 1, XSS et sql_injection réunies dans 1.

Sensibilité de l'écart, sur val : 552 incidents à 1 minute, 197 à 5 minutes, 80 à 15 minutes.

### 10.5 Ce qu'il faut retenir

1. **Bonne nouvelle : le volume baisse fortement,** de 262 715 flux à 487 incidents.
2. **Mauvaise nouvelle : 97 % des incidents sont de fausses alertes.** La précision de 97,7 % par flux était trompeuse (voir l'étape 7) : elle vient de quelques très gros incidents d'attaque. **C'est exactement le problème de surcharge d'alertes que le projet veut réduire, et il n'est pas encore réglé par le ML seul.**
3. **Ces fausses alertes ne viennent pas d'une seule machine.** Elles sont réparties sur 32 machines, à 45 incidents au plus. Elles sont petites : environ 11 flux chacune, 179 s en médiane. Une priorisation par taille ou par score semble possible, mais elle devra être réglée sur val.
4. **Nuance sur les attaques web :** seuls 14 à 16 % de leurs flux sont signalés, mais chacune se retrouve dans un incident. Ce résultat corrige en partie la phrase « RF + autoencodeur laisse passer les attaques web » de l'étape 7 : c'est vrai flux par flux, moins au niveau des incidents. Mais ces incidents restent noyés parmi les 474 sans attaque.
5. **L'étiquette du RF peut tromper.** 97,7 % des flux de DDoS sont appelés dos_hulk. Le champ `etiquette_expliquee` peut aussi donner un nom très minoritaire : 8 flux sur 139 586 dans l'exemple enregistré.

### 10.6 Limites à citer dans le rapport

- L'écart de 5 minutes est fixé à l'avance, sans justification forte, et le nombre d'incidents en dépend beaucoup.
- Les explications portent sur un seul flux par incident.
- Les chiffres de bot sont instables.
- Les détections du notebook 05 viennent d'un seul entraînement de chaque modèle.

---

## Étape 11 · 5 novembre 2026 · Notebook 05b : priorisation des incidents

### 11.1 Notions utiles

- **Priorisation :** classer les incidents du plus urgent au moins urgent, pour que l'analyste commence par les plus probables.
- **Rang combiné :** on classe les incidents par nombre de flux, puis par score d'anomalie maximal, et on fait la moyenne des deux rangs. Un incident remonte s'il est gros, très anormal, ou un peu des deux.
- **Budget de lecture :** la part des incidents que l'on lit en premier.
- **Ordre d'arrivée :** la référence, c'est-à-dire ce que ferait un analyste sans priorisation.

### 11.2 Décision et fichiers

Bedis a choisi d'ajouter la priorisation.

- **Créés :** `src/isocrates/ml/priority.py` et `notebooks/05b_priorisation_incidents.ipynb`.
- **Figure :** `reports/05b_classes_vues.png`.
- **Non versionnés :** `data/processed/incidents/test_connu_priorise.json`, `test_inconnu_priorise.json`, `models/priority_choice.joblib`. Les fichiers du notebook 05 ne changent pas.

**Règles fixées avant de mesurer sur les tests :** quatre candidats sans vraie étiquette ni IP source, aucun score basé sur le RF (val ne contient que des attaques qu'il connaît), choix sur val, égalités comptées au rang le plus défavorable. Seuls le score retenu et l'ordre d'arrivée sont mesurés sur les tests.

### 11.3 Choix sur val (197 incidents, dont 7 avec attaque)

| Score | Incidents à lire pour voir toutes les attaques | Rang moyen de première vue | Sans heartbleed : à lire |
|---|---|---:|---:|
| ordre d'arrivée | 193 | 133,4 | non calculé |
| `nb_flux` | 142 | 23,3 | 6 |
| `score_max` | 138 | 53,7 | 138 |
| `score_moyen` | 180 | 75,1 | 180 |
| **`rang_combine` (retenu)** | **75** | 30,4 | 59 |

Budget : 75 / 197 = **38,1 % des incidents**.

### 11.4 Mesure unique sur les tests

| | test_connu : score | test_connu : arrivée | test_inconnu : score | test_inconnu : arrivée |
|---|---:|---:|---:|---:|
| Incidents en tout | 239 | 239 | 487 | 487 |
| Lus avec le budget | 90 | 91 | **185** | 186 |
| Avec attaque lus | **7 sur 7** | 2 sur 7 | **13 sur 13** | 3 sur 13 |
| Sans attaque lus | 83 | 89 | **172** | 183 |
| Classes vues dans le budget | 7 sur 7 | 2 sur 7 | 6 sur 6 | 4 sur 6 |
| À lire pour tout voir | 85 | 142 | 121 | 442 |

Rang du premier incident par attaque sur test_inconnu : portscan 2, bot 4, DDoS 17, XSS et sql_injection 50, bruteforce 121.

### 11.5 Ce qu'il faut retenir

1. **La priorisation fonctionne nettement mieux que l'ordre d'arrivée.** Avec le même budget, on lit les 13 incidents avec attaque de test_inconnu, contre 3.
2. **Elle ne règle pas la surcharge.** On lit 62 % d'incidents en moins (185 au lieu de 487), mais 172 des 185 lus sont sans attaque, soit **93 % de fausses alertes** (97,3 % avant). Les agents devront donc encore écarter beaucoup d'incidents.
3. **Le choix est fragile.** Il repose sur 7 incidents avec attaque, et heartbleed (2 flux) le décide. Sans lui, `nb_flux` suffirait avec 6 incidents, contre 59. On garde quand même le critère annoncé, car il protège les petites attaques.
4. **Les attaques web arrivent tard** (rangs 50 et 121). Un budget très court les perdrait.

### 11.6 Limites à citer dans le rapport

- L'idée de regarder la taille des incidents vient d'une observation faite sur test_inconnu (notebook 05). Le score et le budget sont choisis sur val, mais l'idée n'est pas totalement indépendante des tests.
- Le classement se calcule après coup, sur tous les incidents d'un ensemble. Il n'est pas utilisable tel quel en temps réel.
- Les détections viennent d'un seul entraînement, alors que bot est instable.
- Val ne contient que des attaques connues.
- Les autres scores n'ont volontairement pas été mesurés sur les tests : on ne sait donc pas si `nb_flux` y aurait fait mieux.

---

## Questions ouvertes (à trancher par Bedis)

1. **Combien d'incidents donner aux agents ?** Le budget en laisse 185 sur test_inconnu, soit beaucoup d'appels LLM. Proposition : pour l'évaluation (notebook 08), un échantillon fixé à l'avance avec tous les incidents avec attaque et une partie tirée au sort des incidents sans attaque, y compris hors budget.
2. **Commit Git** des étapes 9, 10 et 11 pas encore fait.
3. Le planning a environ une semaine de retard : la semaine S3 (RAG) a commencé le 4 novembre, et il reste à commencer le notebook 06.

## Prochaine étape prévue

`notebooks/06_rag_attack.ipynb` : bases ATT&CK, mitigations et D3FEND dans ChromaDB et BM25. Attention : ChromaDB, BM25, et sans doute un modèle d'embeddings restent à installer sur la connexion 4G. Prévenir Bedis de la taille avant de télécharger.
