# COUCHE API — api/routes.py
# Responsabilité : routes HTTP, validation des inputs, authentification.
#
# Règles de couche :
#   ✓ Validation des inputs à la frontière système (requêtes HTTP)
#   ✓ Délègue toute logique métier à application/ via app.cor
#   ✗ Aucun import domain/ ou infrastructure/
#   ✗ Aucune logique de génération ou de tokenisation ici
#
# Endpoints :
#   GET  /health   → état du serveur (sans authentification)
#   GET  /info     → informations sur le modèle chargé
#   POST /generate → générer une réponse juridique
#   POST /tokenize → tokeniser un texte (debug/inspection)

import time
import functools
from flask import Flask, request, jsonify, current_app
from flask_limiter import Limiter


def verifier_cle_api(f):
    """
    Décorateur de vérification de la clé API inter-services.

    La clé est transmise dans le header X-Cor-Key.
    Si absente ou incorrecte → 401.

    POINT CRITIQUE — clé vide en développement :
    Si COR_API_KEY n'est pas définie dans .env, toutes les requêtes
    sont rejetées avec 401. C'est intentionnel — forcer la configuration
    explicite de la clé même en dev.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        cle_attendue = current_app.config.get("COR_API_KEY", "")
        cle_recue    = request.headers.get("X-Cor-Key", "")

        if not cle_attendue:
            return jsonify({
                "erreur": "COR_API_KEY non configurée sur le serveur"
            }), 500

        if not cle_recue or cle_recue != cle_attendue:
            return jsonify({
                "erreur": "Clé API invalide ou absente (header X-Cor-Key)"
            }), 401

        return f(*args, **kwargs)
    return wrapper


def valider_generate_input(data: dict) -> tuple:
    """
    Valide les inputs de /generate.
    Retourne (erreur: str | None, inputs_valides: dict).

    POINT CRITIQUE — limites de longueur :
    question max 500 chars — au-delà c'est probablement du prompt injection.
    passages max 5 — au-delà le contexte dépasse max_len.
    passage max 1000 chars par passage.
    max_tokens max 300 — au-delà risque de timeout sur CPU.
    """
    if not isinstance(data, dict):
        return "Body JSON attendu", {}

    question = data.get("question", "")
    if not question or not isinstance(question, str):
        return "Champ 'question' requis (string)", {}
    if len(question.strip()) < 3:
        return "Question trop courte (minimum 3 caractères)", {}
    if len(question) > 500:
        return "Question trop longue (maximum 500 caractères)", {}

    passages = data.get("passages_rag", [])
    if not isinstance(passages, list):
        return "'passages_rag' doit être une liste", {}
    if len(passages) > 5:
        passages = passages[:5]  # tronquer silencieusement
    passages = [
        str(p)[:1000] for p in passages
        if p and isinstance(p, (str, dict))
    ]
    # Si passage est un dict {"texte": "..."}, extraire le texte
    passages_propres = []
    for p in data.get("passages_rag", [])[:5]:
        if isinstance(p, dict):
            texte = p.get("texte", "")
        else:
            texte = str(p)
        if texte and len(texte.strip()) > 5:
            passages_propres.append(texte.strip()[:1000])

    max_tokens = data.get("max_tokens", 150)
    if not isinstance(max_tokens, int) or max_tokens < 1:
        max_tokens = 150
    max_tokens = min(max_tokens, 300)

    temperature = data.get("temperature", 0.7)
    if not isinstance(temperature, (int, float)):
        temperature = 0.7
    temperature = max(0.1, min(float(temperature), 2.0))

    top_p = data.get("top_p", 0.9)
    if not isinstance(top_p, (int, float)):
        top_p = 0.9
    top_p = max(0.1, min(float(top_p), 1.0))

    pays_token = data.get("pays_token", None)
    if pays_token and not isinstance(pays_token, str):
        pays_token = None

    return None, {
        "question"    : question.strip(),
        "passages_rag": passages_propres,
        "max_tokens"  : max_tokens,
        "temperature" : temperature,
        "top_p"       : top_p,
        "pays_token"  : pays_token,
    }


def enregistrer_routes(app: Flask, limiter: Limiter):
    """Enregistre toutes les routes sur l'application Flask."""

    # ── GET /health ────────────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health():
        """
        Health check public — sans authentification.
        Utilisé par Docker, Railway, Hetzner pour vérifier que
        le serveur répond.

        Retourne toujours 200 même si le modèle n'est pas chargé.
        Le champ 'modele_charge' indique l'état réel.
        """
        cor = current_app.cor
        return jsonify({
            "status"        : "ok",
            "modele_charge" : cor is not None,
            "cor_actif"     : current_app.config.get("COR_ACTIF", False),
            "version"       : "cor-0.1.0-dev",
        }), 200

    # ── GET /info ──────────────────────────────────────────────────────
    @app.route("/info", methods=["GET"])
    @verifier_cle_api
    def info():
        """
        Informations détaillées sur le modèle chargé.
        Requiert X-Cor-Key.
        """
        cor = current_app.cor
        if cor is None:
            return jsonify({
                "modele_charge" : False,
                "message"       : "Modèle non chargé — lancer scripts/train.py",
            }), 200

        return jsonify(cor.info()), 200

    # ── POST /generate ─────────────────────────────────────────────────
    @app.route("/generate", methods=["POST"])
    @limiter.limit("100 per minute")
    @verifier_cle_api
    def generate():
        """
        Génère une réponse juridique.
        Requiert X-Cor-Key.

        Body JSON :
        {
            "question"    : "licenciement sans préavis cameroun",
            "passages_rag": ["article 34 code travail..."],
            "max_tokens"  : 150,
            "temperature" : 0.7,
            "top_p"       : 0.9,
            "pays_token"  : "[CM]"   ← optionnel, détecté auto si absent
        }

        Réponse succès :
        {
            "reponse"  : "En vertu de l'article 34...",
            "fallback" : false,
            "duree_ms" : 1250
        }

        Réponse fallback (modèle inactif) :
        {
            "reponse"  : null,
            "fallback" : true,
            "message"  : "Cor inactif — utiliser le LLM de fallback"
        }
        """
        # Valider les inputs
        data = request.get_json(silent=True) or {}
        erreur, inputs = valider_generate_input(data)

        if erreur:
            return jsonify({"erreur": erreur}), 400

        cor = current_app.cor

        # Fallback si modèle absent ou inactif
        if cor is None or not cor.actif:
            return jsonify({
                "reponse"  : None,
                "fallback" : True,
                "message"  : "Cor inactif — utiliser le LLM de fallback",
            }), 200

        # Générer
        t_debut = time.time()
        try:
            reponse = cor.repondre(
                question     = inputs["question"],
                passages_rag = inputs["passages_rag"],
                pays_token   = inputs["pays_token"],
                max_tokens   = inputs["max_tokens"],
                temperature  = inputs["temperature"],
                top_p        = inputs["top_p"],
            )
        except Exception as e:
            # Ne jamais exposer les détails de l'erreur interne
            app.logger.error(f"Erreur génération Cor : {e}")
            return jsonify({
                "reponse"  : None,
                "fallback" : True,
                "message"  : "Erreur interne — fallback activé",
            }), 200

        duree_ms = int((time.time() - t_debut) * 1000)

        if reponse is None:
            return jsonify({
                "reponse"  : None,
                "fallback" : True,
                "message"  : "Génération vide — fallback activé",
            }), 200

        return jsonify({
            "reponse"  : reponse,
            "fallback" : False,
            "duree_ms" : duree_ms,
        }), 200

    # ── POST /tokenize ─────────────────────────────────────────────────
    @app.route("/tokenize", methods=["POST"])
    @limiter.limit("200 per minute")
    @verifier_cle_api
    def tokenize():
        """
        Tokenise un texte. Utile pour le debug et l'inspection.
        Requiert X-Cor-Key.

        Body JSON :
        {
            "texte"   : "licenciement cameroun article 34",
            "decoder" : true   ← optionnel, retourne aussi le texte décodé
        }
        """
        data  = request.get_json(silent=True) or {}
        texte = data.get("texte", "")

        if not texte or not isinstance(texte, str):
            return jsonify({"erreur": "Champ 'texte' requis"}), 400
        if len(texte) > 2000:
            return jsonify({"erreur": "Texte trop long (max 2000 chars)"}), 400

        cor = current_app.cor
        if cor is None:
            return jsonify({"erreur": "Modèle non chargé"}), 503

        ids     = cor.tokeniser(texte)
        resultat = {
            "ids"        : ids,
            "nb_tokens"  : len(ids),
        }

        if data.get("decoder", False):
            resultat["decode"] = cor.decoder(ids)

        return jsonify(resultat), 200
