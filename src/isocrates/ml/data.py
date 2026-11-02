"""Chargement de LYCOS-IDS2017 étiqueté, avec les bons types.

- `timestamp` : float64 (microsecondes Unix, UTC). JAMAIS float32 (perte d'environ 2 min).
- caractéristiques de flux : float32 (RAM limitée).
- identifiants : jamais utilisés comme caractéristiques du modèle.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "lycos_labelled"

# code du jour -> (fichier CSV, rôle dans le découpage temporel)
DAYS = {
    "lun": ("Monday-WorkingHours.pcap_lycos.csv", "train/val"),
    "mar": ("Tuesday-WorkingHours.pcap_lycos.csv", "train/val"),
    "mer": ("Wednesday-WorkingHours.pcap_lycos.csv", "train/val"),
    "jeu": ("Thursday-WorkingHours.pcap_lycos.csv", "test"),
    "ven": ("Friday-WorkingHours.pcap_lycos.csv", "test"),
}

LABEL = "label"
BENIGN = "benign"
TS = "timestamp"
TS_PER_SECOND = 1_000_000  # timestamp en microsecondes

# Jamais utilisées comme caractéristiques (fuite d'information ou identifiant)
ID_COLS = ["flow_id", "src_addr", "src_port", "dst_addr", TS, LABEL]


def day_path(day: str) -> Path:
    return RAW_DIR / DAYS[day][0]


def read_header(day: str = "lun") -> list[str]:
    return pd.read_csv(day_path(day), nrows=0).columns.tolist()


def feature_columns(columns: list[str]) -> list[str]:
    """Colonnes utilisables comme caractéristiques (dont dst_port et ip_prot)."""
    return [c for c in columns if c not in ID_COLS]


def _dtypes(columns: list[str]) -> dict:
    types = {c: "float32" for c in feature_columns(columns)}
    types.update({
        "flow_id": "string", "src_addr": "string", "dst_addr": "string",
        "src_port": "int32", "dst_port": "int32", "ip_prot": "int16",
        TS: "float64", LABEL: "category",
    })
    return {c: t for c, t in types.items() if c in columns}


def load_day(day: str, usecols: list[str] | None = None) -> pd.DataFrame:
    """Charge un jour (`lun`, `mar`, `mer`, `jeu`, `ven`) avec les bons types."""
    columns = usecols or read_header(day)
    df = pd.read_csv(day_path(day), usecols=columns, dtype=_dtypes(columns))
    df.insert(0, "day", day)
    return df
