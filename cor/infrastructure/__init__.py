# COUCHE INFRASTRUCTURE — Point d'entrée
# Gestion des fichiers, corpus, entraînement, futur RAG.
# Dépend de domain/. Aucun import Flask.

from infrastructure.corpus  import charger_corpus, charger_dataset_json
from infrastructure.trainer import pre_entrainer, fine_tuner, ConfigEntrainement

__all__ = [
    "charger_corpus",
    "charger_dataset_json",
    "pre_entrainer",
    "fine_tuner",
    "ConfigEntrainement",
]
