# ISOCRATES · Contexte du projet pour Claude Code

**Intelligent SOC · Reasoning Agents for Triage, Explanation & Security**

Projet fédéré IA de Bedis : projet de classe du module « Projet fédéré IA », M2 Data Science, ISI Mahdia (Tunisie).
Suivi par la professeure du module. Rendu final : **fin novembre 2026** (code + rapport + présentation).
Dépôt : https://github.com/Bedis75/isocrates

Langue : **français** pour les notebooks, les commentaires, les messages de commit et les explications.

---

## 1. L'idée en une phrase

Le ML détecte, les agents LLM expliquent, l'humain décide.

Un SOC reçoit trop d'alertes (Alahmadi et al., USENIX Security 2022). Le ML seul affiche des scores trop optimistes à cause du mélange aléatoire des données (Arp et al., USENIX Security 2022), et le LLM seul détecte mal (Houssel et al., 2024). ISOCRATES combine les trois.

## 2. Architecture

```
Flux réseau (LYCOS-IDS2017)
  │
  ▼
1 · MACHINE LEARNING (filtrer)
  ├─ Prétraitement : caractéristiques par flux + par IP source et par minute
  ├─ Supervisé (attaques CONNUES + label, ex. ftp_patator)
  │     Random Forest multi-classe   ⟷ comparé à un MLP
  ├─ Non supervisé (attaques INCONNUES)
  │     Autoencodeur (PyTorch, erreur de reconstruction)   ⟷ comparé à l'Isolation Forest
  │     Les deux sont entraînés et évalués ; le meilleur sur val/test est gardé dans le pipeline final
  ├─ Fusion : supervisé « attaque » → label ; détecteur d'anomalies seul → label « inconnu »
  ├─ SHAP (TreeExplainer) → pourquoi cette alerte
  └─ Regroupement : flux suspects (même IP source + fenêtre de temps) → incident JSON
  │
  ▼
2 · AGENTS LLM (LangGraph · comprendre)
  ├─ Agent Enquêteur (ReAct + outils Python sur les données réseau)
  ├─ Agent ATT&CK (RAG sur MITRE ATT&CK ; part du label pour réduire la recherche)
  ├─ Agent Rapport (sortie Pydantic, format imposé)
  └─ Agent Réponse (RAG sur les mitigations MITRE + D3FEND) → actions PROPOSÉES
  │
  ▼
3 · HUMAIN (décider)
  └─ Streamlit : l'analyste valide ou rejette chaque action ; tout est journalisé.
     AUCUNE action n'est exécutée automatiquement.
```

### Comparaisons prévues (demandées par la professeure)
- Random Forest **vs** MLP (attaques connues)
- Autoencodeur **vs** Isolation Forest (attaques inconnues)
- Agents **avec vs sans** le label transmis par le RF

## 3. Données : LYCOS-IDS2017 (état actuel)

Version corrigée de CICIDS2017 (Rosay et al., ICISSP 2022). Étiquetage déjà fait avec le script des auteurs `labelling.py`.

Fichiers étiquetés : `data/raw/lycos_labelled/` (5 CSV, 844 Mo, un par jour)

| Jour | Normal | Attaques | Rôle |
|---|---|---|---|
| Lundi (lun) | 367 181 | aucune | entraînement + validation |
| Mardi (mar) | 312 675 | ftp_patator 4 003 · ssh_patator 2 959 | entraînement + validation |
| Mercredi (mer) | 318 933 | dos_hulk 158 988 · dos_goldeneye 6 765 · dos_slowloris 5 674 · dos_slowhttptest 4 866 · heartbleed 11 | entraînement + validation |
| Jeudi (jeu) | 110 448 | webattack_bruteforce 1 360 · webattack_xss 661 · webattack_sql_injection 12 | **test** |
| Vendredi (ven) | 286 438 | portscan 160 106 · ddos 95 683 · bot 735 | **test** |

- 83 colonnes, 0 valeur manquante, 0 infinie, 0 doublon (timestamp lu en float64 ; les 11 doublons vus par `explore.py` venaient du cast float32).
- `flag_urg`, `fwd_flag_urg`, `bwd_flag_urg` sont constantes (toujours 0) : à retirer.
- 12 classes d'attaque sur 13 viennent de `172.16.0.1` (seul bot vient de 5 postes `192.168.10.x`) : la fuite par IP est confirmée.
- Pas d'infiltration (retirée par les auteurs).
- Colonne cible : `label` (valeurs en minuscules, `benign` = normal).
- Colonnes identifiants (JAMAIS utilisées comme caractéristiques du modèle) :
  `flow_id`, `src_addr`, `src_port`, `dst_addr`, `timestamp`, `label`.
- `dst_port` et `ip_prot` peuvent servir de caractéristiques.
- Les 75 autres colonnes sont des caractéristiques de flux (LycoSTand) : `flow_duration`, `pkt_len_*`, `fwd_*`, `bwd_*`, `iat_*`, `flag_SYN`, `flag_rst`, etc.

Autres fichiers dans `data/raw/lycos/lycos-ids2017/` : flux bruts LycoSTand, CSV originaux de CICIDS2017, scripts des auteurs. Ne pas les modifier.

## 4. Règles méthodologiques (NON négociables)

1. **Découpage temporel uniquement**, jamais aléatoire.
   - train = 80 % les plus anciens (par `timestamp`) de lun, mar, mer
   - val = 20 % les plus récents de lun, mar, mer (seuils, réglages)
   - test = jeu + ven (attaques jamais vues par le modèle supervisé)
   Justification : Arp et al. 2022 (piège P3 data snooping), Ndichu et al. 2026 (Table 4).
2. **Ne PAS utiliser `create_datasets.py`** des auteurs : il mélange au hasard.
3. **Ne jamais caster `timestamp` en float32** : précision perdue (environ 2 minutes). Le lire en `float64` (`dtype={"timestamp": "float64"}`) et vérifier son unité (secondes, ms ou µs) avant les fenêtres de temps.
4. **IP et ports source exclus des caractéristiques** (les attaquants ont toujours les mêmes IP : fuite d'information). Ils servent seulement au regroupement et aux caractéristiques de fenêtre.
5. **Métriques par classe**, pas seulement globales (fort déséquilibre). Priorité au **rappel** sur les attaques du test.
6. Le Random Forest ne connaît aucune attaque de jeu/ven : c'est voulu. L'autoencodeur doit les attraper.
7. Ajustements (scaler, seuils) **ajustés sur train/val uniquement**, jamais sur test.
8. Aucun résultat inventé : seuls les chiffres réellement obtenus vont dans le rapport.

## 5. Caractéristiques de fenêtre à ajouter

Par IP source et par minute (fenêtre de 60 s) :
- `w_conn` : nombre de connexions
- `w_dst_ports` : nombre de ports de destination distincts
- `w_dst_hosts` : nombre de machines distinctes contactées
- `w_rst_rate` : proportion de flux avec RST

Elles rendent un scan visible même sur un seul flux.

## 6. Traçabilité (souhait de Bedis)

- **Une étape = un notebook numéroté** dans `notebooks/`, avec :
  1. une cellule Markdown en tête (titre, date, ce qui est fait et pourquoi) ;
  2. du code court et commenté ;
  3. des sorties visibles (tableaux, graphiques) ;
  4. une cellule « Observations » à la fin.
- Le code réutilisable va dans `src/isocrates/` (les notebooks l'importent).
- Les figures sont enregistrées dans `reports/` (PNG, 150 dpi).
- Un commit Git par étape terminée, message en français.
- **`JOURNAL.md` à la racine : à compléter après CHAQUE action** (nouvelle entrée datée « Étape N » : ce qui a été fait, pourquoi, fichiers créés/modifiés, chiffres réellement obtenus, décisions ouvertes). Bedis l'envoie à une autre IA pour qu'elle lui explique le travail : écrire clairement, sans jargon non expliqué. Mettre aussi à jour « Questions ouvertes » et « Prochaine étape ».

Notebooks prévus :
- `01_donnees_lycos.ipynb` : exploration, qualité, classes par jour
- `02_preparation.ipynb` : nettoyage, fenêtres, découpage temporel → `data/processed/{train,val,test}.parquet` + `features.json`
- `03_supervise_rf_mlp.ipynb` : RF multi-classe vs MLP, SHAP
- `04_anomalies_ae_if.ipynb` : autoencodeur vs Isolation Forest, seuil au 99e percentile de val
- `05_fusion_incidents.ipynb` : fusion des scores, regroupement en incidents JSON
- `06_rag_attack.ipynb` : bases ATT&CK, mitigations, D3FEND dans ChromaDB + BM25
- `07_agents.ipynb` : graphe LangGraph des 4 agents
- `08_evaluation.ipynb` : 3 configurations (ML seul, LLM seul, ISOCRATES) + comparaisons

## 7. Environnement

- Windows + **WSL2 Ubuntu-24.04**, projet dans `~/dev/isocrates`
- Conda, environnement **`isocrates`**, Python 3.11
- Installé : pandas, pyarrow, numpy, scikit-learn, shap, matplotlib, seaborn, jupyter, tqdm, python-dotenv (torch à installer)
- RAM : 9,7 Go (+ 8 Go de swap) → charger un jour à la fois si besoin, `float32` pour les caractéristiques (jamais pour `timestamp`)
- Connexion 4G limitée : prévenir avant tout gros téléchargement (torch GPU environ 2,5 Go)
- `.gitignore` exclut `data/`, `*.csv`, `*.parquet`, modèles, `.env`

## 8. Planning

| Semaine | Dates | Objectif |
|---|---|---|
| S1 | 21 → 27 oct. | Données : exploration, préparation, découpage (EN COURS) |
| S2 | 28 oct. → 3 nov. | ML : RF/MLP, autoencodeur/IF, SHAP, incidents |
| S3 | 4 → 10 nov. | RAG : ATT&CK, mitigations, D3FEND |
| S4 | 11 → 17 nov. | Agents LangGraph de bout en bout |
| S5 | 18 → 24 nov. | Streamlit + évaluation |
| S6 | 25 → 30 nov. | Rapport + présentation |

## 9. État actuel (21 octobre 2026)

Fait :
- [x] Dépôt cloné, structure créée (`notebooks/`, `src/isocrates/{ml,rag,agents,app}`, `eval/`, `reports/`, `data/`)
- [x] Environnement conda `isocrates`
- [x] LYCOS-IDS2017 téléchargé et étiqueté (`data/raw/lycos_labelled/`)
- [x] `src/isocrates/ml/explore.py` : exploration rapide (attention, il caste `timestamp` en float32 : ses Parquet sont à supprimer)

- [x] `data/processed/` vide (plus de Parquet faussés par `explore.py`)
- [x] Unité de `timestamp` vérifiée : **microsecondes** Unix, en UTC (heure locale du banc d'essai = UTC−3). Ce sont des entiers exacts en float64, triés dans chaque CSV. `flow_duration` est aussi en µs (max 120 s, le timeout de flux). Jeudi ne couvre que 3 h (11:59 → 14:59 UTC) : l'après-midi de l'infiltration a été retiré.

- [x] `src/isocrates/ml/data.py` (`load_day` : bons types) + notebook `01_donnees_lycos.ipynb` exécuté ; figures `reports/01_*.png`

À faire maintenant :
- [ ] **Décision ouverte** : avec le 80/20 temporel (par jour ou global), la validation ne contient presque aucune attaque (par jour : 11 heartbleed seulement). Choisir comment régler le RF/MLP avant le notebook 02.
- [ ] `src/isocrates/ml/prepare.py` + notebook `02_preparation.ipynb`
- [ ] Premier commit

## 10. Références clés

- Ndichu et al. (2026), survey principal, arXiv 2605.08316
- Arp et al. (2022), *Dos and Don'ts of ML in Computer Security*, USENIX Security
- Rosay et al. (2022), LYCOS-IDS2017, ICISSP
- Engelen et al. (2021), erreurs de CICIDS2017, WTMC
- Chou, Sudheer & Park (2026), JSAN : travail le plus proche (RF + agent ReAct)
- Grinsztajn et al. (2022), NeurIPS : les arbres égalent ou battent le DL sur données tabulaires
