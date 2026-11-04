"""Détecteurs d'anomalies (attaques inconnues) : autoencodeur PyTorch et Isolation Forest.

Idée commune : on apprend à quoi ressemble le trafic NORMAL (benign de train uniquement),
puis chaque flux reçoit un score d'anomalie. Plus le score est grand, plus le flux est suspect.
Le seuil d'alerte est fixé sur le benign de val, jamais sur test_connu ni test_inconnu (règle 7).
"""
import copy
import time

import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from isocrates.ml.data import BENIGN


class Autoencoder(nn.Module):
    """Réseau qui apprend à recopier son entrée en passant par un « goulot » étroit.
    Il doit donc résumer le trafic normal : un flux anormal est mal reconstruit."""

    def __init__(self, n_features, latent_size):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(n_features, 64),
            nn.ReLU(),
            nn.Linear(64, latent_size),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_size, 64),
            nn.ReLU(),
            nn.Linear(64, n_features),
        )

    def forward(self, x):
        code = self.encoder(x)
        reconstruction = self.decoder(code)
        return reconstruction


def fit_autoencoder(Z_train, Z_val, latent_size, epochs=20, batch_size=1024, seed=0):
    """Entraîne l'autoencodeur sur du trafic normal et garde l'époque où l'erreur
    sur le benign de val est la plus basse.
    Renvoie (meilleur modèle, historique, meilleure époque, durée en secondes)."""
    torch.manual_seed(seed)   # pour obtenir les mêmes résultats à chaque exécution

    model = Autoencoder(Z_train.shape[1], latent_size)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_function = nn.MSELoss()

    dataset = TensorDataset(torch.from_numpy(Z_train))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    val_tensor = torch.from_numpy(Z_val)

    history = []
    best_loss = float("inf")
    best_state = None
    best_epoch = 0
    start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        # Apprentissage : on parcourt toutes les données, lot par lot
        model.train()
        total_loss = 0.0
        for (batch,) in loader:
            optimizer.zero_grad()                       # remet les gradients à zéro
            reconstruction = model(batch)               # le réseau recopie le lot
            loss = loss_function(reconstruction, batch) # erreur entre la copie et l'original
            loss.backward()                             # rétropropagation : calcule les gradients
            optimizer.step()                            # met à jour les poids
            total_loss += loss.item() * len(batch)
        train_loss = total_loss / len(dataset)

        # Évaluation sur le benign de val, sans apprentissage
        model.eval()
        with torch.no_grad():
            val_loss = loss_function(model(val_tensor), val_tensor).item()
        history.append({"époque": epoch, "perte train": train_loss, "perte val": val_loss})

        if val_loss < best_loss:
            best_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())
            best_epoch = epoch

    duration = time.perf_counter() - start
    model.load_state_dict(best_state)   # on revient à la meilleure époque
    return model, pd.DataFrame(history), best_epoch, duration


def reconstruction_error(model, Z, batch_size=65536):
    """Score de l'autoencodeur : erreur quadratique moyenne de chaque flux.
    On travaille par lots pour ne pas remplir la mémoire."""
    model.eval()
    errors = []
    with torch.no_grad():
        for start in range(0, len(Z), batch_size):
            batch = torch.from_numpy(Z[start:start + batch_size])
            reconstruction = model(batch)
            error = ((reconstruction - batch) ** 2).mean(dim=1)
            errors.append(error.numpy())
    return np.concatenate(errors)


def fit_isolation_forest(X, max_samples):
    """Entraîne une Isolation Forest de 100 arbres et renvoie (modèle, durée en secondes)."""
    forest = IsolationForest(n_estimators=100, max_samples=max_samples, n_jobs=-1, random_state=0)
    start = time.perf_counter()
    forest.fit(X)
    duration = time.perf_counter() - start
    return forest, duration


def isolation_score(forest, X):
    """Score de l'Isolation Forest. score_samples est plus bas pour un flux anormal :
    on change le signe pour que, comme pour l'autoencodeur, grand = suspect."""
    return -forest.score_samples(X)


def threshold_from_benign(scores, y, percentile=99):
    """Seuil d'alerte : 99e percentile des scores du benign.
    Par construction, environ 1 % du benign de cet ensemble déclenche une alerte."""
    return np.percentile(scores[y == BENIGN], percentile)


def detection_table(y, scores, threshold):
    """Pour chaque classe : nombre de flux, nombre d'alertes (score > seuil), part détectée et AUC.
    Pour benign, la part détectée est le taux de fausses alertes.
    L'AUC mesure la séparation attaque / benign sans dépendre du seuil (1 = parfait, 0,5 = hasard)."""
    benign_scores = scores[y == BENIGN]
    rows = []
    for name in np.unique(y):
        class_scores = scores[y == name]
        row = {
            "classe": name,
            "flux": len(class_scores),
            "alertes": int((class_scores > threshold).sum()),
            "part détectée": (class_scores > threshold).mean(),
        }
        if name != BENIGN:
            all_scores = np.concatenate([benign_scores, class_scores])
            labels = np.concatenate([np.zeros(len(benign_scores)), np.ones(len(class_scores))])
            row["AUC"] = roc_auc_score(labels, all_scores)
        rows.append(row)
    return pd.DataFrame(rows).set_index("classe")


def mean_attack_recall(table, excluded="heartbleed"):
    """Moyenne des parts détectées sur les classes d'attaque, chaque classe comptant autant.
    `excluded` est retirée : heartbleed n'a que 2 flux en val et en test_connu."""
    recalls = []
    for name in table.index:
        if name != BENIGN and name != excluded:
            recalls.append(table.loc[name, "part détectée"])
    return float(np.mean(recalls))
