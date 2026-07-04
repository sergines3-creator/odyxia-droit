# dashboard/app.py
# COR — Serveur du tableau de bord d'entraînement
#
# Lancement (depuis le dossier cor/) :
#   python dashboard/app.py
#   ou : python -m dashboard.app
#
# Écoute sur http://localhost:5001
# Le serveur COR (API) écoute sur http://localhost:5000

import os
import sys
import json
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE, ".env"))

from dashboard.metrics_writer import METRICS_PATH

app = Flask(__name__, template_folder="templates")

COR_SERVER_URL = os.getenv("COR_SERVER_URL", "http://localhost:5000")
COR_API_KEY    = os.getenv("COR_API_KEY", "")


# ── Données métriques ──────────────────────────────────────────────────

def _load_metrics() -> dict:
    if not os.path.exists(METRICS_PATH):
        return {
            "training_state"     : "idle",
            "last_updated"       : None,
            "config_modele"      : {},
            "config_entrainement": {},
            "model_info"         : {},
            "pretrain"           : {"current_epoch": 0, "total_epochs": 0,
                                    "current_step": 0,  "total_steps": 0,
                                    "epochs": [], "steps": []},
            "finetune"           : {"current_epoch": 0, "total_epochs": 0,
                                    "current_step": 0,  "total_steps": 0,
                                    "epochs": [], "steps": []},
            "pretrain_best_val"  : None,
            "finetune_best_val"  : None,
            "errors"             : [],
        }
    try:
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


# ── Routes dashboard ───────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/metrics")
def api_metrics():
    return jsonify(_load_metrics())


@app.route("/api/status")
def api_status():
    data     = _load_metrics()
    pretrain = data.get("pretrain", {})
    finetune = data.get("finetune", {})
    return jsonify({
        "state"            : data.get("training_state", "idle"),
        "last_updated"     : data.get("last_updated"),
        "pretrain_epoch"   : pretrain.get("current_epoch", 0),
        "pretrain_total"   : pretrain.get("total_epochs", 0),
        "pretrain_step"    : pretrain.get("current_step", 0),
        "pretrain_steps"   : pretrain.get("total_steps", 0),
        "finetune_epoch"   : finetune.get("current_epoch", 0),
        "finetune_total"   : finetune.get("total_epochs", 0),
        "pretrain_best_val": data.get("pretrain_best_val"),
        "finetune_best_val": data.get("finetune_best_val"),
        "error_count"      : len(data.get("errors", [])),
    })


@app.route("/api/logs")
def api_logs():
    data   = _load_metrics()
    errors = list(reversed(data.get("errors", [])))
    return jsonify({"logs": errors, "total": len(errors)})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    from dashboard.metrics_writer import MetricsWriter
    MetricsWriter().reset()
    return jsonify({"ok": True})


# ── Proxy vers le serveur COR (pour le chat, évite CORS + masque la clé) ──

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Proxy transparent vers POST /generate du serveur COR.
    Le navigateur n'a jamais besoin de connaître la COR_API_KEY.
    """
    try:
        import urllib.request
        import urllib.error

        body = request.get_data()

        req = urllib.request.Request(
            url     = f"{COR_SERVER_URL}/generate",
            data    = body,
            method  = "POST",
            headers = {
                "Content-Type": "application/json",
                "X-Cor-Key"   : COR_API_KEY,
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return jsonify(data)

    except urllib.error.URLError:
        return jsonify({
            "fallback": True,
            "reponse" : None,
            "message" : f"Serveur COR inaccessible ({COR_SERVER_URL}) — lancer : python -m api.app",
        }), 200

    except Exception as e:
        return jsonify({
            "fallback": True,
            "reponse" : None,
            "message" : f"Erreur proxy : {e}",
        }), 200


if __name__ == "__main__":
    print()
    print("  =" * 23)
    print("  COR -- Tableau de bord")
    print("  http://localhost:5001")
    print("  =" * 23)
    print()
    if not COR_API_KEY:
        print("  [WARN] COR_API_KEY absente dans .env")
        print("         Le chat ne fonctionnera pas sans le serveur COR")
    print()
    app.run(host="0.0.0.0", port=5001, debug=False)
