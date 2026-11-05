"""Vérification du MLP : reconnaît-il l'attaque, ou seulement la machine de l'attaquant ?

Les groupes de colonnes sont fixés à l'avance d'après leur signification,
sans regarder les résultats. Il n'y a ni TTL ni options TCP dans LYCOS :
la longueur d'en-tête n'en donne qu'un indice indirect.
"""
import numpy as np
from sklearn.neural_network import MLPClassifier

from isocrates.ml.data import BENIGN
from isocrates.ml.supervised import macro_f1, macro_f1_without, sqrt_balanced_weights

# Décrivent la connexion TCP elle-même (réglages de la machine ou déroulé de la connexion)
TCP_COLUMNS = [
    "fwd_tcp_init_win_bytes", "bwd_tcp_init_win_bytes",
    "fwd_pkt_hdr_len_min", "bwd_pkt_hdr_len_min",
    "fwd_pkt_hdr_len_tot", "bwd_pkt_hdr_len_tot",
    "flag_SYN", "flag_fin", "flag_rst", "flag_ack", "flag_psh",
    "fwd_flag_psh", "bwd_flag_psh", "flag_cwr", "flag_ece",
]

# Décrivent le rythme des paquets (peut trahir l'outil utilisé)
RHYTHM_PREFIXES = ("iat_", "fwd_iat_", "bwd_iat_", "active_", "idle_")


def rhythm_columns(features):
    """Colonnes de rythme : temps entre paquets, périodes d'activité et de pause."""
    columns = []
    for col in features:
        if col.startswith(RHYTHM_PREFIXES):
            columns.append(col)
    return columns


def column_kind(col):
    """Type d'une colonne, pour lire le classement des colonnes décisives."""
    if col in TCP_COLUMNS:
        return "connexion TCP"
    if col.startswith(RHYTHM_PREFIXES):
        return "rythme"
    if col.startswith("w_"):
        return "fenêtre 60 s"
    if col in ("dst_port", "ip_prot"):
        return "destination / protocole"
    return "taille, volume ou débit"


def kept_positions(features, removed):
    """Numéros des colonnes à garder quand on retire la liste `removed`."""
    positions = []
    for i, col in enumerate(features):
        if col not in removed:
            positions.append(i)
    return positions


def detection_after_shuffle(predict, X, is_target, positions, rng):
    """Mélange les colonnes `positions` entre tous les flux de X (toutes avec le même
    ordre, pour garder leur cohérence), puis renvoie la part des flux cibles encore
    signalés comme attaque."""
    shuffled = X.copy()
    order = rng.permutation(len(X))
    shuffled[:, positions] = X[order][:, positions]
    predictions = predict(shuffled[is_target])
    return (predictions != BENIGN).mean()


def permutation_importance(predict, X, is_target, features, n_repeats=5, seed=0):
    """Pour chaque colonne : baisse moyenne de la détection des flux cibles quand on la mélange."""
    rng = np.random.default_rng(seed)
    reference = (predict(X[is_target]) != BENIGN).mean()
    drops = {}
    for i, col in enumerate(features):
        results = []
        for _ in range(n_repeats):
            results.append(detection_after_shuffle(predict, X, is_target, [i], rng))
        drops[col] = reference - np.mean(results)
    return reference, drops


def trace_mlp_epochs(X, y, X_val, y_val, X_web, y_web, labels, hidden=(128, 64), epochs=20, seed=0):
    """Entraîne un MLP comme fit_mlp et note, à chaque époque, le macro-F1 sur val (avec et sans
    heartbleed) et la détection de chaque attaque web. Sert seulement à observer : aucun choix ici."""
    weights = sqrt_balanced_weights(y)
    classes = np.unique(y)
    mlp = MLPClassifier(hidden_layer_sizes=hidden, batch_size=1024, learning_rate_init=1e-3,
                        alpha=1e-4, random_state=seed, shuffle=True)
    rows = []
    for epoch in range(1, epochs + 1):
        mlp.partial_fit(X, y, classes=classes, sample_weight=weights)
        val_predictions = mlp.predict(X_val)
        row = {
            "graine": seed,
            "époque": epoch,
            "macro-F1 val": macro_f1(y_val, val_predictions),
            "sans heartbleed": macro_f1_without(y_val, val_predictions, labels, "heartbleed"),
        }
        detected = mlp.predict(X_web) != BENIGN
        for name in np.unique(y_web):
            row[name] = detected[y_web == name].mean()
        rows.append(row)
    return rows
