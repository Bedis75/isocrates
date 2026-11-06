"""Priorisation des incidents : dans quel ordre l'analyste doit-il les lire ?

Le score n'utilise que des informations connues sans la vraie étiquette.
Il ne doit pas utiliser l'IP source (règle 4). Le choix se fait sur val uniquement (règle 7).

En cas d'égalité, on compte le rang le plus défavorable : si 50 incidents ont le même score,
ils ont tous le rang du dernier d'entre eux. Les résultats ne dépendent donc pas de la chance.
"""
import pandas as pd

from isocrates.ml.data import BENIGN

CANDIDATES = ["nb_flux", "score_max", "score_moyen", "rang_combine"]


def incident_table(incidents, truth):
    """Une ligne par incident : les colonnes utiles au score, puis la vérité (évaluation seulement)."""
    rows = []
    for incident in incidents:
        incident_truth = truth[incident["id"]]
        benign_flows = incident_truth.get(BENIGN, 0)
        rows.append({
            "id": incident["id"],
            "debut_utc": incident["debut_utc"],
            "nb_flux": incident["nb_flux"],
            "score_max": incident["score_anomalie"]["max"],
            "score_moyen": incident["score_anomalie"]["moyen"],
            "avec_attaque": benign_flows < incident["nb_flux"],
        })
    return pd.DataFrame(rows).set_index("id")


def worst_rank(values):
    """Rang de chaque incident (1 = à lire en premier), plus grande valeur d'abord.
    En cas d'égalité, tous reçoivent le rang le plus défavorable."""
    return values.rank(ascending=False, method="max").astype(int)


def add_scores(table):
    """Ajoute le rang combiné : la moyenne du rang par nb_flux et du rang par score_max.
    Un petit rang combiné = à lire tôt, donc on prend l'opposé pour que « plus grand = plus urgent »."""
    table = table.copy()
    rank_flows = worst_rank(table["nb_flux"])
    rank_score = worst_rank(table["score_max"])
    table["rang_combine"] = -(rank_flows + rank_score) / 2
    return table


def chronological_rank(table):
    """Ordre de référence, sans priorisation : l'analyste lit les incidents dans l'ordre d'arrivée."""
    return table["debut_utc"].rank(method="max").astype(int)


def first_rank_by_class(ranks, truth):
    """Pour chaque attaque : rang du premier incident qui la contient.
    C'est le nombre d'incidents à lire avant de la voir au moins une fois."""
    first = {}
    for incident_id, rank in ranks.items():
        for label in truth[incident_id]:
            if label == BENIGN:
                continue
            if label not in first or rank < first[label]:
                first[label] = int(rank)
    return pd.Series(first).sort_index()


def reading_summary(ranks, truth):
    """Résumé d'un ordre de lecture, utilisé pour comparer les candidats."""
    first = first_rank_by_class(ranks, truth)
    return {
        "incidents à lire pour voir toutes les attaques": int(first.max()),
        "rang moyen de la première vue": round(float(first.mean()), 1),
    }


def attacks_seen_within(ranks, truth, budget):
    """Parmi les attaques, lesquelles sont vues si on ne lit que `budget` incidents ?"""
    first = first_rank_by_class(ranks, truth)
    seen = []
    for label, rank in first.items():
        if rank <= budget:
            seen.append(label)
    return seen
