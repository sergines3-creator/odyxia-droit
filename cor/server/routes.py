# server/routes.py
# COR — Routes du microservice Flask (avec sécurité avancée + RAG + train + clients)
#
# Endpoints publics (sans clé) :
#   GET  /health
#
# Endpoints authentifiés (X-Cor-Key) :
#   POST /generate
#   POST /tokenize
#   GET  /info
#
# Endpoints RAG (X-Cor-Key) :
#   POST   /rag/add_document
#   POST   /rag/add_pdf
#   GET    /rag/documents
#   DELETE /rag/document/<doc_id>
#   GET    /rag/stats
#
# Endpoints entraînement (X-Cor-Key) :
#   POST /train/start
#   GET  /train/status
#   POST /train/stop
#
# Endpoints administration (X-Cor-Key) :
#   GET  /clients
#   POST /clients

import os
import time
import json
import threading
import functools
from flask import Flask, request, jsonify, current_app, g
from flask_limiter import Limiter

_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Compatibilité : décorateur simple si api/security.py n'est pas chargé ─────

def _verifier_cle_simple(f):
    """Décorateur legacy (clé unique depuis .env)."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        cle_attendue = current_app.config.get("COR_API_KEY", "")
        cle_recue    = request.headers.get("X-Cor-Key", "")

        if not cle_attendue:
            return jsonify({"erreur": "COR_API_KEY non configurée"}), 500
        if not cle_recue or cle_recue != cle_attendue:
            return jsonify({"erreur": "Clé API invalide ou absente (header X-Cor-Key)"}), 401

        g.client_info = {"client_id": "legacy", "nom": "Legacy"}
        g.t_debut     = time.time()
        return f(*args, **kwargs)
    return wrapper


def _get_auth_decorator():
    try:
        from api.security import verifier_client
        return verifier_client
    except ImportError:
        return _verifier_cle_simple


def _journal_ok(alerte=None):
    try:
        from api.security import journaliser_requete
        journaliser_requete("200", alerte)
    except ImportError:
        pass


# ── État global de l'entraînement ─────────────────────────────────────────────

_train_state = {
    "actif"      : False,
    "thread"     : None,
    "debut"      : None,
    "config"     : {},
    "dernier_log": None,
}
_train_lock = threading.Lock()


# ── Validation des inputs /generate ───────────────────────────────────────────

def valider_generate_input(data: dict) -> tuple:
    if not isinstance(data, dict):
        return "Body JSON attendu", {}

    question = data.get("question", "")
    if not question or not isinstance(question, str):
        return "Champ 'question' requis (string)", {}
    if len(question.strip()) < 3:
        return "Question trop courte (minimum 3 caractères)", {}
    if len(question) > 500:
        return "Question trop longue (maximum 500 caractères)", {}

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


# ── Enregistrement des routes ──────────────────────────────────────────────────

def enregistrer_routes(app: Flask, limiter: Limiter):
    """Enregistre toutes les routes sur l'application Flask."""

    auth = _get_auth_decorator()

    # ────────────────────────────────────────────────────────────────────────
    # GET /health
    # ────────────────────────────────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health():
        cor = current_app.cor
        return jsonify({
            "status"       : "ok",
            "modele_charge": cor is not None,
        }), 200

    # ────────────────────────────────────────────────────────────────────────
    # GET /info
    # ────────────────────────────────────────────────────────────────────────
    @app.route("/info", methods=["GET"])
    @auth
    def info():
        cor = current_app.cor
        if cor is None:
            return jsonify({"modele_charge": False, "message": "Modèle non chargé"}), 200
        return jsonify(cor.info()), 200

    # ────────────────────────────────────────────────────────────────────────
    # POST /generate
    # ────────────────────────────────────────────────────────────────────────
    @app.route("/generate", methods=["POST"])
    @limiter.limit("100 per minute")
    @auth
    def generate():
        data = request.get_json(silent=True) or {}
        erreur, inputs = valider_generate_input(data)

        if erreur:
            return jsonify({"erreur": erreur}), 400

        # Protection contre les injections de prompt
        avec_timeout = None
        try:
            from api.security import detecter_injection, avec_timeout
            alerte = detecter_injection(inputs["question"])
            if alerte:
                _journal_ok(alerte=f"injection_tentative: {alerte}")
                return jsonify({
                    "erreur"  : "Requête refusée : contenu non autorisé",
                    "fallback": True,
                }), 400
        except ImportError:
            pass

        cor = current_app.cor

        if cor is None or not cor.actif:
            _journal_ok()
            return jsonify({
                "reponse" : None,
                "fallback": True,
                "message" : "Cor inactif — utiliser le LLM de fallback",
            }), 200

        # RAG automatique si aucun passage fourni
        passages = inputs["passages_rag"]
        if not passages:
            try:
                from infrastructure.rag import rechercher
                passages_rag = rechercher(
                    question=inputs["question"],
                    pays    =inputs.get("pays_token"),
                    k       =3,
                )
                passages = [p["texte"] for p in passages_rag]
            except Exception:
                passages = []

        t_debut = time.time()
        try:
            def _gen():
                return cor.repondre(
                    question     = inputs["question"],
                    passages_rag = passages,
                    pays_token   = inputs["pays_token"],
                    max_tokens   = inputs["max_tokens"],
                    temperature  = inputs["temperature"],
                    top_p        = inputs["top_p"],
                )

            if avec_timeout:
                reponse = avec_timeout(_gen)
            else:
                reponse = _gen()

        except TimeoutError:
            _journal_ok(alerte="timeout_generation")
            return jsonify({
                "reponse" : None,
                "fallback": True,
                "message" : "Timeout — génération trop longue",
            }), 200
        except Exception as e:
            app.logger.error(f"Erreur génération : {e}")
            return jsonify({
                "reponse" : None,
                "fallback": True,
                "message" : "Erreur interne — fallback activé",
            }), 200

        duree_ms = int((time.time() - t_debut) * 1000)

        if reponse is None:
            _journal_ok()
            return jsonify({"reponse": None, "fallback": True, "message": "Génération vide"}), 200

        _journal_ok()
        return jsonify({"reponse": reponse, "fallback": False, "duree_ms": duree_ms}), 200

    # ────────────────────────────────────────────────────────────────────────
    # POST /tokenize
    # ────────────────────────────────────────────────────────────────────────
    @app.route("/tokenize", methods=["POST"])
    @limiter.limit("200 per minute")
    @auth
    def tokenize():
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
        resultat = {"ids": ids, "nb_tokens": len(ids)}

        if data.get("decoder", False):
            resultat["decode"] = cor.decoder(ids)

        return jsonify(resultat), 200

    # ════════════════════════════════════════════════════════════════════════
    # ENDPOINTS RAG
    # ════════════════════════════════════════════════════════════════════════

    @app.route("/rag/add_document", methods=["POST"])
    @auth
    def rag_add_document():
        data = request.get_json(silent=True) or {}

        texte = data.get("texte", "")
        if not texte or not isinstance(texte, str) or len(texte.strip()) < 20:
            return jsonify({"erreur": "Champ 'texte' requis (minimum 20 caractères)"}), 400

        metadata = {
            "pays"   : data.get("pays", "inconnu"),
            "domaine": data.get("domaine", "general"),
            "source" : data.get("source", ""),
            "titre"  : data.get("titre", ""),
        }

        try:
            from infrastructure.rag import indexer_document
            result = indexer_document(texte, metadata)
        except ImportError:
            return jsonify({"erreur": "Module RAG non disponible (pip install chromadb sentence-transformers)"}), 503
        except Exception as e:
            return jsonify({"erreur": str(e)}), 500

        if "erreur" in result:
            return jsonify(result), 400

        _journal_ok()
        return jsonify(result), 201

    @app.route("/rag/add_pdf", methods=["POST"])
    @auth
    def rag_add_pdf():
        if "fichier" not in request.files:
            return jsonify({"erreur": "Fichier PDF requis (champ 'fichier')"}), 400

        fichier = request.files["fichier"]
        if not fichier.filename.lower().endswith(".pdf"):
            return jsonify({"erreur": "Seuls les fichiers PDF sont acceptés"}), 400

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            fichier.save(tmp.name)
            chemin_tmp = tmp.name

        metadata = {
            "pays"   : request.form.get("pays", "inconnu"),
            "domaine": request.form.get("domaine", "general"),
            "source" : request.form.get("source", fichier.filename),
            "titre"  : request.form.get("titre", ""),
        }

        try:
            from infrastructure.rag import indexer_pdf
            result = indexer_pdf(chemin_tmp, metadata)
        except ImportError:
            return jsonify({"erreur": "Module RAG non disponible"}), 503
        except Exception as e:
            return jsonify({"erreur": str(e)}), 500
        finally:
            try:
                os.unlink(chemin_tmp)
            except Exception:
                pass

        if "erreur" in result:
            return jsonify(result), 400

        _journal_ok()
        return jsonify(result), 201

    @app.route("/rag/documents", methods=["GET"])
    @auth
    def rag_documents():
        try:
            from infrastructure.rag import lister_documents
            docs = lister_documents()
        except ImportError:
            return jsonify({"erreur": "Module RAG non disponible"}), 503
        except Exception as e:
            return jsonify({"erreur": str(e)}), 500

        return jsonify({"documents": docs, "total": len(docs)}), 200

    @app.route("/rag/document/<doc_id>", methods=["DELETE"])
    @auth
    def rag_delete_document(doc_id):
        if not doc_id or len(doc_id) > 64:
            return jsonify({"erreur": "doc_id invalide"}), 400

        try:
            from infrastructure.rag import supprimer_document
            result = supprimer_document(doc_id)
        except ImportError:
            return jsonify({"erreur": "Module RAG non disponible"}), 503
        except Exception as e:
            return jsonify({"erreur": str(e)}), 500

        if "erreur" in result:
            return jsonify(result), 404

        _journal_ok()
        return jsonify(result), 200

    @app.route("/rag/stats", methods=["GET"])
    @auth
    def rag_stats():
        try:
            from infrastructure.rag import stats
            result = stats()
        except ImportError:
            return jsonify({"erreur": "Module RAG non disponible"}), 503
        except Exception as e:
            return jsonify({"erreur": str(e)}), 500

        return jsonify(result), 200

    # ════════════════════════════════════════════════════════════════════════
    # ENDPOINTS ENTRAÎNEMENT
    # ════════════════════════════════════════════════════════════════════════

    @app.route("/train/start", methods=["POST"])
    @auth
    def train_start():
        with _train_lock:
            if _train_state["actif"]:
                return jsonify({"erreur": "Entraînement déjà en cours"}), 409

        data = request.get_json(silent=True) or {}

        epochs = max(1, min(int(data.get("epochs", 3)), 100))
        lr     = max(1e-6, min(float(data.get("lr", 1e-4)), 1e-2))
        batch  = max(1, min(int(data.get("batch_size", 8)), 128))
        phase  = data.get("phase", "finetune")

        if phase not in ("pretrain", "finetune"):
            return jsonify({"erreur": "phase doit être 'pretrain' ou 'finetune'"}), 400

        def _lancer():
            with _train_lock:
                _train_state["actif"]       = True
                _train_state["debut"]       = time.time()
                _train_state["config"]      = {"epochs": epochs, "lr": lr, "batch_size": batch, "phase": phase}
                _train_state["dernier_log"] = "Démarrage..."

            try:
                import sys
                sys.path.insert(0, _PROJET)

                if phase == "pretrain":
                    from infrastructure.trainer import pre_entrainer, ConfigEntrainement
                    from domain.tokenizer import CorTokenizer
                    from infrastructure.corpus import charger_corpus
                    config = ConfigEntrainement(nb_epochs=epochs, lr=lr, batch_size=batch)
                    tok = CorTokenizer()
                    tok.charger()
                    corpus = charger_corpus(tok)
                    pre_entrainer(config, corpus)
                else:
                    from infrastructure.trainer import fine_tuner, ConfigEntrainement
                    from domain.tokenizer import CorTokenizer
                    from infrastructure.corpus import charger_corpus
                    config = ConfigEntrainement(nb_epochs=epochs, lr=lr, batch_size=batch)
                    tok = CorTokenizer()
                    tok.charger()
                    corpus = charger_corpus(tok)
                    fine_tuner(config, corpus)

                with _train_lock:
                    _train_state["dernier_log"] = "Terminé avec succès"
            except Exception as e:
                with _train_lock:
                    _train_state["dernier_log"] = f"Erreur : {e}"
            finally:
                with _train_lock:
                    _train_state["actif"]  = False
                    _train_state["thread"] = None

        t = threading.Thread(target=_lancer, daemon=True, name="cor-trainer")
        with _train_lock:
            _train_state["thread"] = t
        t.start()

        _journal_ok()
        return jsonify({"statut": "démarré", "phase": phase, "epochs": epochs, "lr": lr, "batch_size": batch}), 200

    @app.route("/train/status", methods=["GET"])
    @auth
    def train_status():
        metrics_path = os.path.join(_PROJET, "training_metrics.json")
        metrics = {}
        if os.path.exists(metrics_path):
            try:
                with open(metrics_path, "r", encoding="utf-8") as f:
                    metrics = json.load(f)
            except Exception:
                pass

        with _train_lock:
            actif       = _train_state["actif"]
            debut       = _train_state["debut"]
            config      = dict(_train_state["config"])
            dernier_log = _train_state["dernier_log"]

        duree_s = int(time.time() - debut) if debut else 0

        return jsonify({
            "actif"      : actif,
            "config"     : config,
            "duree_s"    : duree_s,
            "dernier_log": dernier_log,
            "metrics"    : metrics,
        }), 200

    @app.route("/train/stop", methods=["POST"])
    @auth
    def train_stop():
        with _train_lock:
            if not _train_state["actif"]:
                return jsonify({"message": "Aucun entraînement en cours"}), 200

            stop_path = os.path.join(_PROJET, "training_metrics.json")
            try:
                if os.path.exists(stop_path):
                    with open(stop_path, "r", encoding="utf-8") as f:
                        m = json.load(f)
                    m["stop_requested"] = True
                    with open(stop_path, "w", encoding="utf-8") as f:
                        json.dump(m, f)
            except Exception:
                pass
            _train_state["dernier_log"] = "Arrêt demandé..."

        _journal_ok()
        return jsonify({"message": "Arrêt demandé — en attente de la fin de l'étape courante"}), 200

    # ════════════════════════════════════════════════════════════════════════
    # ENDPOINTS ADMINISTRATION
    # ════════════════════════════════════════════════════════════════════════

    @app.route("/clients", methods=["GET"])
    @auth
    def get_clients():
        try:
            from api.security import lister_clients
            clients = lister_clients()
        except ImportError:
            return jsonify({"erreur": "Module sécurité non disponible"}), 503
        except Exception as e:
            return jsonify({"erreur": str(e)}), 500

        return jsonify({"clients": clients, "total": len(clients)}), 200

    @app.route("/clients", methods=["POST"])
    @auth
    def post_clients():
        data = request.get_json(silent=True) or {}

        nom = data.get("nom", "").strip()
        if not nom:
            return jsonify({"erreur": "Champ 'nom' requis"}), 400
        if len(nom) > 100:
            return jsonify({"erreur": "Nom trop long (max 100 caractères)"}), 400

        quota = data.get("quota_mensuel", 1000)
        if not isinstance(quota, int) or quota < 0:
            return jsonify({"erreur": "'quota_mensuel' doit être un entier positif"}), 400

        try:
            from api.security import creer_client
            result = creer_client(nom=nom, quota_mensuel=quota)
        except ImportError:
            return jsonify({"erreur": "Module sécurité non disponible"}), 503
        except Exception as e:
            return jsonify({"erreur": str(e)}), 500

        _journal_ok()
        return jsonify(result), 201
