# COUCHE API — Point d'entrée
# Routes Flask, validation des inputs, authentification inter-services.
# Dépend uniquement de application/. Aucun import domain/ ou infrastructure/.

from api.app import create_app

__all__ = ["create_app"]
