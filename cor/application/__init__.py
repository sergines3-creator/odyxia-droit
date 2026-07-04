# COUCHE APPLICATION — Point d'entrée
# Exporte les cas d'usage exposés aux couches supérieures (api/).
# Dépend uniquement de domain/. Aucun import Flask ou I/O fichier.

from application.inference import CorInference

__all__ = ["CorInference"]
