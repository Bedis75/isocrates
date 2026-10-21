"""Exploration de LYCOS-IDS2017 étiqueté : colonnes, classes, valeurs manquantes.
Convertit aussi chaque CSV en Parquet pour accélérer les chargements suivants."""
from pathlib import Path
import numpy as np
import pandas as pd

RAW = Path("data/raw/lycos_labelled")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)


def find_label_column(df: pd.DataFrame) -> str:
    for c in df.columns:
        if c.strip().lower() in {"label", "class", "attack", "attack_cat"}:
            return c
    raise ValueError(f"Colonne de label introuvable. Colonnes : {list(df.columns)}")


def main() -> None:
    files = sorted(RAW.glob("*.csv"))
    if not files:
        raise SystemExit(f"Aucun CSV dans {RAW.resolve()}")

    for f in files:
        df = pd.read_csv(f, low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        label = find_label_column(df)

        num = df.select_dtypes(include="number").columns
        df[num] = df[num].astype("float32")
        n_inf = int(np.isinf(df[num]).sum().sum())

        print(f"\n=== {f.name} : {len(df):,} flux, {df.shape[1]} colonnes")
        print(df[label].value_counts().to_string())
        print(f"manquantes : {int(df.isna().sum().sum()):,} · infinies : {n_inf:,} · doublons : {int(df.duplicated().sum()):,}")

        df.to_parquet(OUT / f"{f.stem.split('.')[0]}.parquet", index=False)

    print("\n=== Colonnes")
    print(list(df.columns))
    print("\n=== Colonnes non numériques")
    print(df.select_dtypes(exclude="number").columns.tolist())


if __name__ == "__main__":
    main()
