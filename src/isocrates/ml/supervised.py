"""Modèles supervisés (attaques connues) : Random Forest multi-classe et MLP.

- Les réglages sont choisis sur val (macro-F1), jamais sur test_connu ni test_inconnu (règle 7).
- Le MLP a besoin de données mises à l'échelle : log signé puis StandardScaler, ajustés sur train.
- Déséquilibre des classes : chaque flux reçoit un poids (voir sqrt_balanced_weights).
"""
import copy
import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, precision_recall_fscore_support
from sklearn.neural_network import MLPClassifier
from sklearn.utils.class_weight import compute_sample_weight

from isocrates.ml.data import BENIGN, LABEL, ROOT

PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"


def load_sets(names=("train", "val", "test_connu", "test_inconnu")):
    """Charge les fichiers Parquet du notebook 02 et la liste des caractéristiques."""
    with open(PROCESSED / "features.json", encoding="utf-8") as f:
        features = json.load(f)["features"]

    sets = {}
    for name in names:
        df = pd.read_parquet(PROCESSED / f"{name}.parquet")
        df[LABEL] = df[LABEL].astype(str)
        sets[name] = df
    return sets, features


def signed_log(x):
    """sign(x) * log(1 + |x|).
    Écrase les très grandes valeurs (débits, durées en µs) et garde le signe des -1."""
    return np.sign(x) * np.log1p(np.abs(x))


def sqrt_balanced_weights(y):
    """Poids de chaque flux pour compenser le déséquilibre des classes.

    Le poids « balanced » de sklearn vaut n_flux / (n_classes * n_flux_de_la_classe) :
    il donnerait plus de 10 000 à heartbleed (8 flux) et ferait diverger le MLP.
    On prend donc la racine carrée de ce poids, puis on divise par la moyenne (moyenne = 1).
    """
    weights = compute_sample_weight("balanced", y)
    weights = np.sqrt(weights)
    return weights / weights.mean()


def macro_f1(y_true, y_pred):
    """Moyenne des F1 de chaque classe : une petite classe compte autant qu'une grande."""
    return f1_score(y_true, y_pred, average="macro", zero_division=0)


def macro_f1_without(y_true, y_pred, labels, excluded):
    """Macro-F1 calculé sans la classe `excluded`.
    Utile pour heartbleed : avec 2 flux seulement, son F1 saute d'un coup à la moindre erreur."""
    kept = []
    for label in labels:
        if label != excluded:
            kept.append(label)
    return f1_score(y_true, y_pred, labels=kept, average="macro", zero_division=0)


def fit_rf(X, y, max_depth=None, class_weight=None, seed=0):
    """Entraîne un Random Forest de 100 arbres et renvoie (modèle, durée en secondes)."""
    rf = RandomForestClassifier(n_estimators=100, max_depth=max_depth, class_weight=class_weight,
                                n_jobs=-1, random_state=seed)
    start = time.perf_counter()
    rf.fit(X, y)
    duration = time.perf_counter() - start
    return rf, duration


def fit_mlp(X, y, X_val, y_val, hidden=(128, 64), epochs=15, seed=0):
    """Entraîne un MLP époque par époque et garde l'époque qui a le meilleur macro-F1 sur val.

    On n'utilise pas l'option early_stopping de sklearn : elle prendrait une validation
    tirée AU HASARD dans train, ce qui est interdit (règle 1).
    Renvoie (meilleur modèle, historique, meilleure époque, durée en secondes).
    """
    weights = sqrt_balanced_weights(y)
    classes = np.unique(y)
    mlp = MLPClassifier(hidden_layer_sizes=hidden, batch_size=1024, learning_rate_init=1e-3,
                        alpha=1e-4, random_state=seed, shuffle=True)

    history = []
    best_score = -1.0
    best_model = None
    best_epoch = 0
    start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        # partial_fit = un seul passage sur toutes les données d'entraînement (une époque)
        mlp.partial_fit(X, y, classes=classes, sample_weight=weights)
        score = macro_f1(y_val, mlp.predict(X_val))
        history.append({"époque": epoch, "perte train": mlp.loss_, "macro-F1 val": score})

        if score > best_score:
            best_score = score
            best_model = copy.deepcopy(mlp)   # copie du modèle à cette époque
            best_epoch = epoch

    duration = time.perf_counter() - start
    return best_model, pd.DataFrame(history), best_epoch, duration


def per_class_report(y_true, y_pred, labels):
    """Tableau précision / rappel / F1 / nombre de flux, une ligne par classe."""
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0)
    table = pd.DataFrame({"précision": precision, "rappel": recall, "F1": f1, "flux": support},
                         index=labels)
    return table.round(3)


def detection_by_class(y_true, y_pred):
    """Pour chaque classe vraie : part de ses flux prédits comme une attaque (étiquette ≠ benign).
    Pour la classe benign, c'est donc le taux de fausses alertes."""
    y_true = np.asarray(y_true)
    flagged = np.asarray(y_pred) != BENIGN
    result = {}
    for cls in np.unique(y_true):
        is_cls = y_true == cls
        result[cls] = flagged[is_cls].mean()
    return pd.Series(result)


def save_model(obj, name):
    MODELS.mkdir(exist_ok=True)
    joblib.dump(obj, MODELS / f"{name}.joblib", compress=3)


def load_model(name):
    return joblib.load(MODELS / f"{name}.joblib")
