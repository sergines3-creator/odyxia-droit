# COUCHE API — api/app.py
# Responsabilité : factory Flask, configuration, rate limiting, chargement du modèle.
#
# Règles de couche :
#   ✓ Peut importer application/ (CorInference)
#   ✗ Aucun import domain/ ou infrastructure/ direct
#   ✗ Aucune logique métier ici — déléguer à application/
#
# Exports publics : create_app

import os
import sys
import time

# Ajouter la racine du projet au path
_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJET not in sys.path:
    sys.path.insert(0, _PROJET)

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

# Chemins des modèles
MODELE_PATH    = os.path.join(_PROJET, "models", "cor.pt")
TOKENIZER_PATH = os.path.join(_PROJET, "models", "cor_tokenizer.json")


def create_app() -> Flask:
    """
    Factory Flask — crée et configure l'application.

    Pattern factory utilisé pour :
    - Tests unitaires (app isolée par test)
    - Gunicorn multi-workers (chaque worker crée sa propre instance)
    - Flexibilité de configuration

    POINT CRITIQUE — modèle partagé entre workers :
    Avec gunicorn --workers 2, chaque worker charge le modèle
    indépendamment → 2× la RAM utilisée.
    Sur CPX42 (16Go), 2 workers × 200Mo = 400Mo. Acceptable.
    Ne pas dépasser 4 workers sans vérifier la RAM disponible.
    """
    app = Flask(__name__)

    # ── Configuration ─────────────────────────────────────────────────
    app.config["COR_API_KEY"]     = os.getenv("COR_API_KEY", "")
    app.config["COR_ACTIF"]       = os.getenv("COR_ACTIF", "true").lower() == "true"
    app.config["MAX_TOKENS"]      = int(os.getenv("COR_MAX_TOKENS", "150"))
    app.config["DEBUG"]           = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    if not app.config["COR_API_KEY"]:
        print("[WARN] COR_API_KEY non définie — toutes les requêtes seront rejetées")
        print("       Définir COR_API_KEY dans .env")

    # ── Rate Limiting ──────────────────────────────────────────────────
    limiter = Limiter(
        app             = app,
        key_func        = get_remote_address,
        default_limits  = ["100 per minute"],
        storage_uri     = "memory://",
    )

    # ── Chargement du modèle ───────────────────────────────────────────
    cor_instance = None
    t_debut = time.time()

    if app.config["COR_ACTIF"]:
        try:
            from application.inference import CorInference
            if os.path.exists(MODELE_PATH) and os.path.exists(TOKENIZER_PATH):
                print(f"[COR-SERVER] Chargement du modèle...")
                cor_instance = CorInference.charger(MODELE_PATH, TOKENIZER_PATH)
                duree = time.time() - t_debut
                print(f"[COR-SERVER] Modèle chargé en {duree:.1f}s")
            else:
                print(f"[COR-SERVER] Modèle absent — mode fallback activé")
                print(f"  Attendu : {MODELE_PATH}")
                print(f"  Lancer  : python scripts/train.py")
        except Exception as e:
            print(f"[COR-SERVER] Erreur chargement modèle : {e}")
            print(f"[COR-SERVER] Démarrage en mode fallback")
    else:
        print(f"[COR-SERVER] COR_ACTIF=false — mode fallback")

    # Stocker l'instance dans le contexte app
    app.cor = cor_instance

    # ── Routes ────────────────────────────────────────────────────────
    from api.routes import enregistrer_routes
    enregistrer_routes(app, limiter)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)
