# Shim de compatibilité — cor/corpus.py
# L'implémentation réelle est dans infrastructure/corpus.py
# Ce fichier préserve les imports existants : from cor.corpus import charger_corpus

from infrastructure.corpus import (
    charger_corpus,
    charger_dataset_json,
    charger_fichiers_txt,
    rapport_corpus,
)

__all__ = [
    "charger_corpus",
    "charger_dataset_json",
    "charger_fichiers_txt",
    "rapport_corpus",
]
