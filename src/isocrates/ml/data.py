"""Chargement des données LYCOS-IDS2017 étiquetées.

Points importants :
- `timestamp` est lu en float64 (jamais float32, sinon on perd environ 2 minutes de précision).
- les caractéristiques de flux sont lues en float32 pour économiser la RAM.
- les colonnes identifiants (IP, ports source, etc.) ne servent jamais de caractéristiques.
"""
from pathlib import Path

import pandas as pd

# Dossier racine du projet (3 niveaux au-dessus de ce fichier : ml -> isocrates -> src -> racine)
ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "lycos_labelled"

# Pour chaque jour : (nom du fichier CSV, rôle dans le découpage)
DAYS = {
    "lun": ("Monday-WorkingHours.pcap_lycos.csv", "train/val"),
    "mar": ("Tuesday-WorkingHours.pcap_lycos.csv", "train/val"),
    "mer": ("Wednesday-WorkingHours.pcap_lycos.csv", "train/val"),
    "jeu": ("Thursday-WorkingHours.pcap_lycos.csv", "test"),
    "ven": ("Friday-WorkingHours.pcap_lycos.csv", "test"),
}

LABEL = "label"          # colonne cible
BENIGN = "benign"        # valeur de la cible pour le trafic normal
TS = "timestamp"         # temps du flux, en microsecondes
TS_PER_SECOND = 1_000_000

# Colonnes jamais utilisées comme caractéristiques (identifiants ou fuite d'information)
ID_COLS = ["flow_id", "src_addr", "src_port", "dst_addr", TS, LABEL]


def day_path(day):
    """Chemin du fichier CSV d'un jour ("lun", "mar", ...)."""
    file_name = DAYS[day][0]
    return RAW_DIR / file_name


def read_header(day="lun"):
    """Liste des noms de colonnes (on lit seulement la première ligne du CSV)."""
    header = pd.read_csv(day_path(day), nrows=0)
    return list(header.columns)


def feature_columns(columns):
    """Garde les colonnes utilisables comme caractéristiques (toutes sauf ID_COLS)."""
    features = []
    for col in columns:
        if col not in ID_COLS:
            features.append(col)
    return features


def column_types(columns):
    """Type à utiliser pour chaque colonne lors de la lecture du CSV."""
    special_types = {
        "flow_id": "string",
        "src_addr": "string",
        "dst_addr": "string",
        "src_port": "int32",
        "dst_port": "int32",
        "ip_prot": "int16",
        TS: "float64",       # précision complète pour le temps
        LABEL: "category",
    }
    types = {}
    for col in columns:
        if col in special_types:
            types[col] = special_types[col]
        else:
            types[col] = "float32"   # caractéristique de flux
    return types


def load_day(day, usecols=None):
    """Charge un jour ("lun", "mar", "mer", "jeu", "ven") avec les bons types.
    On ajoute une colonne "day" pour savoir d'où vient chaque flux."""
    if usecols is None:
        usecols = read_header(day)
    df = pd.read_csv(day_path(day), usecols=usecols, dtype=column_types(usecols))
    df.insert(0, "day", day)
    return df
