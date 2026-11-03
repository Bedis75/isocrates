"""Préparation des données : caractéristiques de fenêtre, découpage train/val, export.

Découpage choisi le 2 novembre 2026 (voir JOURNAL.md) :
- lun, mar, mer -> train/val, découpage temporel PAR CLASSE :
  pour chaque attaque, ses 80 % de flux les plus anciens vont en train, les 20 % les plus récents en val ;
  pour le trafic normal (benign), même règle mais jour par jour.
- jeu, ven -> test, en entier.
On ne mélange jamais les flux au hasard.
"""
import json

import pandas as pd

from isocrates.ml.data import BENIGN, LABEL, TS, TS_PER_SECOND, feature_columns, load_day, read_header

WINDOW_SECONDS = 60
WINDOW_COLS = ["w_conn", "w_dst_ports", "w_dst_hosts", "w_rst_rate"]
TRAIN_FRAC = 0.8


def add_window_features(df):
    """Ajoute 4 caractéristiques calculées sur tous les flux de la même IP source
    pendant la même minute :
      w_conn      : nombre de connexions
      w_dst_ports : nombre de ports de destination différents
      w_dst_hosts : nombre de machines de destination différentes
      w_rst_rate  : part des flux qui contiennent un paquet RST
    """
    # Numéro de la minute : timestamp (en µs) divisé par la durée d'une minute (en µs)
    df["minute"] = df[TS] // (WINDOW_SECONDS * TS_PER_SECOND)
    # flag_rst vaut 0 ou 1 : on le transforme en vrai/faux
    df["has_rst"] = df["flag_rst"] > 0

    # Un groupe = une IP source pendant une minute
    groups = df.groupby(["src_addr", "minute"])

    # transform() renvoie, pour chaque flux, le résultat calculé sur son groupe
    df["w_conn"] = groups[TS].transform("count")
    df["w_dst_ports"] = groups["dst_port"].transform("nunique")
    df["w_dst_hosts"] = groups["dst_addr"].transform("nunique")
    df["w_rst_rate"] = groups["has_rst"].transform("mean")

    df[WINDOW_COLS] = df[WINDOW_COLS].astype("float32")
    df = df.drop(columns=["minute", "has_rst"])
    return df


def load_with_windows(days):
    """Charge plusieurs jours, un par un, et ajoute les fenêtres.
    Les fenêtres sont calculées dans chaque jour séparément."""
    tables = []
    for day in days:
        df = load_day(day)
        df = add_window_features(df)
        tables.append(df)
    return pd.concat(tables, ignore_index=True)


def temporal_split(df, frac=TRAIN_FRAC):
    """Ajoute une colonne "split" qui vaut "train" ou "val".

    Groupes : chaque classe d'attaque forme un groupe ; le benign forme un groupe par jour.
    Dans chaque groupe, on trie les flux par temps : les premiers 80 % vont en train,
    le reste en val. Ainsi la val est toujours APRÈS le train.
    """
    # 1) Nom du groupe de chaque flux
    group = df[LABEL].astype(str)
    is_benign = df[LABEL] == BENIGN
    group[is_benign] = "benign_" + df.loc[is_benign, "day"]

    # 2) Par défaut tout est en val, puis on met les plus anciens de chaque groupe en train
    df["split"] = "val"
    for name in group.unique():
        rows = df[group == name]
        rows = rows.sort_values(TS, kind="stable")
        n_train = int(len(rows) * frac)
        first_rows = rows.index[:n_train]
        df.loc[first_rows, "split"] = "train"
    return df


def constant_columns(df, columns):
    """Colonnes qui ont une seule valeur dans df (inutiles pour un modèle)."""
    constants = []
    for col in columns:
        if df[col].nunique() <= 1:
            constants.append(col)
    return constants


def model_features(dropped):
    """Liste finale des caractéristiques : colonnes de flux du CSV + fenêtres,
    sans les colonnes retirées."""
    candidates = feature_columns(read_header()) + WINDOW_COLS
    features = []
    for col in candidates:
        if col not in dropped:
            features.append(col)
    return features


def save_split(sets, features, meta, out_dir):
    """Écrit train/val/test en Parquet et la liste des caractéristiques dans features.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sets:
        sets[name].to_parquet(out_dir / f"{name}.parquet", index=False)

    info = {"features": features}
    info.update(meta)
    with open(out_dir / "features.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
