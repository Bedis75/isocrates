"""Préparation : caractéristiques de fenêtre, découpage temporel, export Parquet.

Découpage (décision du 2 novembre 2026, voir JOURNAL.md) :
- train/val sur lun, mar, mer, temporel PAR CLASSE : pour chaque attaque, ses 80 % de flux
  les plus anciens en train et ses 20 % les plus récents en val ; le benign est coupé
  80/20 dans chaque jour. Jamais de mélange aléatoire.
- test = jeu + ven en entier.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from isocrates.ml.data import BENIGN, LABEL, TS, TS_PER_SECOND, feature_columns, load_day, read_header

WINDOW_S = 60
WINDOW_COLS = ["w_conn", "w_dst_ports", "w_dst_hosts", "w_rst_rate"]
TRAIN_FRAC = 0.8


def add_window_features(df: pd.DataFrame) -> pd.DataFrame:
    """Par IP source et par fenêtre fixe de 60 s (calculé dans un seul jour) :
    nombre de connexions, ports et machines de destination distincts, part de flux avec RST."""
    window = (df[TS] // (WINDOW_S * TS_PER_SECOND)).astype("int64")
    g = df.assign(_w=window, _rst=(df["flag_rst"] > 0)).groupby(["src_addr", "_w"], sort=False)
    df["w_conn"] = g[TS].transform("size").astype("float32")
    df["w_dst_ports"] = g["dst_port"].transform("nunique").astype("float32")
    df["w_dst_hosts"] = g["dst_addr"].transform("nunique").astype("float32")
    df["w_rst_rate"] = g["_rst"].transform("mean").astype("float32")
    return df


def load_with_windows(days: list[str]) -> pd.DataFrame:
    """Charge plusieurs jours, un à la fois, en ajoutant les caractéristiques de fenêtre."""
    return pd.concat([add_window_features(load_day(d)) for d in days], ignore_index=True)


def temporal_split(df: pd.DataFrame, frac: float = TRAIN_FRAC) -> pd.Series:
    """Renvoie « train » ou « val » pour chaque flux.
    Groupe = le jour pour le benign, la classe pour une attaque ; dans chaque groupe,
    les `frac` flux les plus anciens vont en train."""
    group = np.where(df[LABEL] == BENIGN, "benign_" + df["day"], df[LABEL].astype(str))
    rank = df.groupby(group)[TS].rank(method="first", pct=True)
    return pd.Series(np.where(rank <= frac, "train", "val"), index=df.index, name="split")


def constant_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    """Colonnes à valeur unique (à déterminer sur train uniquement)."""
    return [c for c in columns if df[c].nunique(dropna=False) <= 1]


def model_features(dropped: list[str]) -> list[str]:
    """Caractéristiques finales : colonnes de flux du CSV (hors identifiants et constantes) + fenêtres."""
    return [c for c in feature_columns(read_header()) + WINDOW_COLS if c not in dropped]


def save_split(sets: dict[str, pd.DataFrame], features: list[str], meta: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in sets.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    (out_dir / "features.json").write_text(
        json.dumps({"features": features, **meta}, indent=2, ensure_ascii=False))
