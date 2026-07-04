# server/app.py
# COR — Microservice Flask
#
# Expose Cor comme une API REST indépendante.
# Consommé par ODYXIA IA, ODYXIA Droit, ODYXIA Douane, etc.
#
# POINTS CRITIQUES :
#
#   1. Sécurité inter-services
#      Toutes les routes (sauf /health) exigent X-Cor-Key.
#      Cette clé est partagée via .env entre Cor et les projets clients.
#      Sans cette clé, requête rejetée avec 401.
#
#   2. COR_ACTIF=false
#      Si le modèle n'est pas entraîné, mettre COR_ACTIF=false.
#      /generate retourne {"fallback": true} — le client utilise
#      son propre LLM (Anthropic, Mistral, etc.).
#
#   3. Chargement au démarrage
#      Le modèle est chargé UNE SEULE FOIS au démarrage de Flask.
#      Chaque requête utilise la même instance en mémoire.
#      Ne pas recharger le modèle à chaque requête.
#
#   4. Rate limiting
#      100 requêtes/minute par IP par défaut.
#      Ajuster selon la capacité du serveur.
#      Sur CPX42 (16Go RAM), 50M params → ~200ms/requête CPU.
#      Donc ~300 req/min théorique — 100 est conservateur et sûr.
#
# Lancement :
#   gunicorn "server.app:create_app()" --bind 0.0.0.0:5000 --workers 2

import os
import sys
import time

# Ajouter la racine du projet au path
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

# Chemins des modèles
MODELE_PATH    = os.path.join(BASE, "models", "cor.pt")
TOKENIZER_PATH = os.path.join(BASE, "models", "cor_tokenizer.json")


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
            from cor.inference import CorInference
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
    from server.routes import enregistrer_routes
    enregistrer_routes(app, limiter)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)