"""Fusion du RF et de l'autoencodeur, puis regroupement des flux suspects en incidents.

Règle de fusion (fixée par l'architecture du projet) :
- le RF prédit une attaque -> on garde son étiquette (source « supervisé ») ;
- sinon, le score de l'autoencodeur dépasse le seuil -> étiquette « inconnu » (source « anomalie ») ;
- sinon -> benign, pas d'alerte.

Un incident contient les alertes d'une même IP source, séparées par moins de GAP_SECONDS.
La vraie étiquette n'entre jamais dans un incident : les agents ne doivent pas la voir.
"""
import numpy as np
import pandas as pd
import torch

from isocrates.ml.data import BENIGN, TS, TS_PER_SECOND

UNKNOWN = "inconnu"
SOURCE_SUPERVISED = "supervisé"
SOURCE_ANOMALY = "anomalie"
SOURCE_NONE = "aucune"
GAP_SECONDS = 300   # 5 minutes sans alerte de cette IP : on ouvre un nouvel incident
TOP_N = 5


def fuse(rf_labels, ae_scores, threshold):
    """Applique la règle de fusion. Renvoie (étiquettes finales, source de chaque alerte)."""
    rf_alert = rf_labels != BENIGN
    ae_alert = ae_scores > threshold

    final_labels = rf_labels.astype(object).copy()
    final_labels[ae_alert & ~rf_alert] = UNKNOWN

    sources = np.full(len(rf_labels), SOURCE_NONE, dtype=object)
    sources[ae_alert] = SOURCE_ANOMALY
    sources[rf_alert] = SOURCE_SUPERVISED     # le RF est prioritaire : il donne un nom
    return final_labels, sources


def number_incidents(alerts, gap_seconds=GAP_SECONDS):
    """Ajoute à `alerts` une colonne "incident" : pour chaque IP source, on trie par temps,
    et un écart de plus de gap_seconds entre deux alertes ouvre un nouvel incident."""
    alerts = alerts.sort_values(["src_addr", TS], kind="stable").copy()
    max_gap = gap_seconds * TS_PER_SECOND
    numbers = pd.Series(0, index=alerts.index)
    next_number = 0

    for ip, times in alerts.groupby("src_addr")[TS]:
        gaps = times.diff()
        is_new = gaps > max_gap
        ip_numbers = is_new.cumsum() + next_number
        numbers[times.index] = ip_numbers
        next_number = int(ip_numbers.max()) + 1

    alerts["incident"] = numbers
    return alerts


def count_values(values, n=TOP_N):
    """Les n valeurs les plus fréquentes, sous forme de dictionnaire simple pour le JSON."""
    counts = pd.Series(values).value_counts().head(n)
    result = {}
    for value, count in counts.items():
        result[str(value)] = int(count)
    return result


def top_contributions(values, raw_values, features, name, n=TOP_N):
    """Les n colonnes où `values` est le plus grand en valeur absolue, de la plus forte à la plus faible."""
    order = np.argsort(np.abs(values))[::-1][:n]
    rows = []
    for i in order:
        rows.append({"colonne": features[i], "valeur": round(float(raw_values[i]), 3), name: round(float(values[i]), 4)})
    return rows


def explain_with_autoencoder(model, z_row, x_row, features):
    """Colonnes les plus mal reconstruites par l'autoencodeur pour un flux :
    c'est ce qui rend ce flux différent du trafic normal appris."""
    model.eval()
    with torch.no_grad():
        batch = torch.from_numpy(z_row.reshape(1, -1))
        reconstruction = model(batch)
    errors = ((reconstruction - batch) ** 2).numpy()[0]
    return top_contributions(errors, x_row, features, "erreur")


def explain_with_shap(explainer, x_row, class_index, features):
    """Colonnes qui ont le plus pesé pour la classe prédite par le RF, sur un flux."""
    explanation = explainer(x_row.reshape(1, -1))
    return top_contributions(explanation.values[0, :, class_index], x_row, features, "shap")


def to_time_text(timestamp, zone):
    """Convertit un timestamp (µs) en date et heure lisibles dans le fuseau demandé."""
    moment = pd.to_datetime(timestamp, unit="us", utc=True).tz_convert(zone)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def summarize_incident(incident_id, flows, threshold):
    """Résumé d'un incident à partir de ses flux. N'utilise jamais la vraie étiquette."""
    return {
        "id": incident_id,
        "src_addr": str(flows["src_addr"].iloc[0]),
        "debut_utc": to_time_text(flows[TS].min(), "UTC"),
        "fin_utc": to_time_text(flows[TS].max(), "UTC"),
        "debut_local": to_time_text(flows[TS].min(), "America/Halifax"),
        "duree_s": round((flows[TS].max() - flows[TS].min()) / TS_PER_SECOND, 1),
        "nb_flux": len(flows),
        "etiquettes": count_values(flows["final"]),
        "sources": count_values(flows["source"]),
        "nb_machines_dst": int(flows["dst_addr"].nunique()),
        "nb_ports_dst": int(flows["dst_port"].nunique()),
        "machines_dst": count_values(flows["dst_addr"]),
        "ports_dst": count_values(flows["dst_port"]),
        "protocoles": count_values(flows["ip_prot"]),
        "score_anomalie": {
            "max": round(float(flows["ae_score"].max()), 4),
            "moyen": round(float(flows["ae_score"].mean()), 4),
            "seuil": round(float(threshold), 4),
        },
        "proba_rf_max": round(float(flows["rf_proba"].max()), 3),
        "fenetre_max": {
            "w_conn": float(flows["w_conn"].max()),
            "w_dst_ports": float(flows["w_dst_ports"].max()),
            "w_dst_hosts": float(flows["w_dst_hosts"].max()),
            "w_rst_rate": round(float(flows["w_rst_rate"].max()), 3),
        },
    }
