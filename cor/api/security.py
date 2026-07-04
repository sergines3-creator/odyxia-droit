# COUCHE API — api/security.py
#
# Sécurité avancée pour le microservice COR :
#   - Authentification multi-clients via clients.json
#   - Vérification d'intégrité SHA-256 du modèle
#   - Protection contre les injections de prompt
#   - Journalisation des événements de sécurité (logs/security.jsonl)
#   - Timeout de génération (30 secondes)

import os
import re
import json
import time
import hashlib
import logging
import functools
import threading
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, request, jsonify, current_app, g

logger = logging.getLogger(__name__)

_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLIENTS_PATH  = os.path.join(_PROJET, "clients.json")
LOG_DIR       = os.path.join(_PROJET, "logs")
SECURITY_LOG  = os.path.join(LOG_DIR, "security.jsonl")
MODELE_PATH   = os.path.join(_PROJET, "models", "cor.pt")
HASH_PATH     = os.path.join(_PROJET, "models", "cor.pt.sha256")

TIMEOUT_GENERATION = 30  # secondes


# ── Patterns d'injection de prompt ────────────────────────────────────────────

_PATTERNS_INJECTION = [
    r"\bignore\s+(all\s+)?(previous|les?|mes?|ces?)\b",
    r"\boubli(e|es|ons|ez)\b",
    r"\bnouvelle\s+instruction",
    r"\bsystem\s*:",
    r"\[INST\]",
    r"<\|",
    r"\|>",
    # Tokens spéciaux COR (IDs réservés sous forme textuelle)
    r"\[PAD\]",
    r"\[UNK\]",
    r"\[BOS\]",
    r"\[EOS\]",
    r"\[SEP\]",
    r"\[REP\]",
    # Tentatives de jailbreak classiques
    r"you are now",
    r"tu es maintenant",
    r"pretend\s+you",
    r"fais\s+semblant",
    r"ignore.*instructions",
    r"oublie.*règles",
    r"act\s+as\s+if",
    r"agis\s+comme\s+si",
    r"DAN\b",
    r"jailbreak",
]

_RE_INJECTION = [re.compile(p, re.IGNORECASE) for p in _PATTERNS_INJECTION]


# ── Journalisation sécurité thread-safe ───────────────────────────────────────

_log_lock = threading.Lock()


def _journal(
    ip        : str,
    client_id : str,
    endpoint  : str,
    statut    : str,
    duree_ms  : int,
    alerte    : Optional[str] = None,
):
    """Enregistre un événement dans logs/security.jsonl (une ligne JSON par événement)."""
    os.makedirs(LOG_DIR, exist_ok=True)

    entree = {
        "timestamp" : datetime.now(timezone.utc).isoformat(),
        "ip"        : ip,
        "client_id" : client_id,
        "endpoint"  : endpoint,
        "statut"    : statut,
        "duree_ms"  : duree_ms,
        "alerte"    : alerte,
    }

    ligne = json.dumps(entree, ensure_ascii=False)

    with _log_lock:
        try:
            with open(SECURITY_LOG, "a", encoding="utf-8") as f:
                f.write(ligne + "\n")
        except Exception as e:
            logger.error(f"[SECURITY] Impossible d'écrire le log : {e}")


# ── Gestion des clients ────────────────────────────────────────────────────────

_clients_cache     = None
_clients_cache_mtime = 0.0
_clients_lock      = threading.Lock()


def _charger_clients() -> dict:
    """
    Charge clients.json avec mise en cache (rechargé si le fichier est modifié).
    Retourne un dict { cle_api: client_dict }.
    """
    global _clients_cache, _clients_cache_mtime

    if not os.path.exists(CLIENTS_PATH):
        return {}

    try:
        mtime = os.path.getmtime(CLIENTS_PATH)
    except OSError:
        return {}

    with _clients_lock:
        if _clients_cache is not None and mtime == _clients_cache_mtime:
            return _clients_cache

        try:
            with open(CLIENTS_PATH, "r", encoding="utf-8") as f:
                donnees = json.load(f)
        except Exception as e:
            logger.error(f"[SECURITY] Erreur lecture clients.json : {e}")
            return _clients_cache or {}

        index = {}
        for c in donnees.get("clients", []):
            cle = c.get("cle_api", "")
            if cle:
                index[cle] = c

        _clients_cache      = index
        _clients_cache_mtime = mtime
        return index


def _sauvegarder_clients(clients_list: list):
    """Écrit la liste mise à jour dans clients.json."""
    with _clients_lock:
        try:
            with open(CLIENTS_PATH, "w", encoding="utf-8") as f:
                json.dump({"clients": clients_list}, f, ensure_ascii=False, indent=2)
            # Invalider le cache
            global _clients_cache, _clients_cache_mtime
            _clients_cache      = None
            _clients_cache_mtime = 0.0
        except Exception as e:
            logger.error(f"[SECURITY] Erreur écriture clients.json : {e}")
            raise


def _incrementer_quota(cle: str):
    """Incrémente requetes_utilisees pour un client (mise à jour atomique du fichier)."""
    if not os.path.exists(CLIENTS_PATH):
        return

    with _clients_lock:
        try:
            with open(CLIENTS_PATH, "r", encoding="utf-8") as f:
                donnees = json.load(f)

            for c in donnees.get("clients", []):
                if c.get("cle_api") == cle:
                    c["requetes_utilisees"] = c.get("requetes_utilisees", 0) + 1
                    break

            with open(CLIENTS_PATH, "w", encoding="utf-8") as f:
                json.dump(donnees, f, ensure_ascii=False, indent=2)

            # Invalider le cache
            global _clients_cache, _clients_cache_mtime
            _clients_cache      = None
            _clients_cache_mtime = 0.0

        except Exception as e:
            logger.error(f"[SECURITY] Erreur incrémentation quota : {e}")


# ── Décorateur d'authentification multi-clients ───────────────────────────────

def verifier_client(f):
    """
    Décorateur d'authentification multi-clients.

    Vérifie X-Cor-Key dans les clients.json.
    Si clients.json n'existe pas, replie sur COR_API_KEY (compatibilité legacy).
    Vérifie le quota mensuel.
    Stocke le client identifié dans g.client_info.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        t_debut   = time.time()
        cle_recue = request.headers.get("X-Cor-Key", "")
        ip        = request.remote_addr or "inconnu"

        # ── Cas 1 : clients.json présent → authentification multi-clients
        if os.path.exists(CLIENTS_PATH):
            clients = _charger_clients()

            if not cle_recue or cle_recue not in clients:
                duree = int((time.time() - t_debut) * 1000)
                _journal(ip, "inconnu", request.path, "401", duree, "cle_invalide")
                return jsonify({"erreur": "Clé API invalide ou absente (header X-Cor-Key)"}), 401

            client = clients[cle_recue]

            if not client.get("actif", True):
                duree = int((time.time() - t_debut) * 1000)
                _journal(ip, client.get("client_id", "?"), request.path, "403", duree, "client_inactif")
                return jsonify({"erreur": "Client désactivé"}), 403

            quota = client.get("quota_mensuel", 0)
            utilise = client.get("requetes_utilisees", 0)
            if quota > 0 and utilise >= quota:
                duree = int((time.time() - t_debut) * 1000)
                _journal(ip, client.get("client_id", "?"), request.path, "429", duree, "quota_depasse")
                return jsonify({
                    "erreur"           : "Quota mensuel atteint",
                    "quota_mensuel"    : quota,
                    "requetes_utilisees": utilise,
                }), 429

            g.client_info = client
            g.t_debut     = t_debut

        # ── Cas 2 : pas de clients.json → authentification simple (legacy)
        else:
            cle_attendue = current_app.config.get("COR_API_KEY", "")
            if not cle_attendue:
                return jsonify({"erreur": "COR_API_KEY non configurée sur le serveur"}), 500

            if not cle_recue or cle_recue != cle_attendue:
                duree = int((time.time() - t_debut) * 1000)
                _journal(ip, "legacy", request.path, "401", duree, "cle_invalide")
                return jsonify({"erreur": "Clé API invalide ou absente (header X-Cor-Key)"}), 401

            g.client_info = {"client_id": "legacy", "nom": "Legacy"}
            g.t_debut     = t_debut

        return f(*args, **kwargs)

    return wrapper


def journaliser_requete(statut: str, alerte: Optional[str] = None):
    """À appeler en fin de route pour journaliser la requête complète."""
    ip        = request.remote_addr or "inconnu"
    client    = getattr(g, "client_info", {})
    client_id = client.get("client_id", "inconnu")
    t_debut   = getattr(g, "t_debut", time.time())
    duree     = int((time.time() - t_debut) * 1000)

    _journal(ip, client_id, request.path, statut, duree, alerte)

    # Incrémenter le quota si la requête a abouti
    if statut == "200" and os.path.exists(CLIENTS_PATH):
        cle = request.headers.get("X-Cor-Key", "")
        if cle:
            _incrementer_quota(cle)


# ── Vérification d'intégrité du modèle ────────────────────────────────────────

def verifier_integrite_modele() -> tuple[bool, str]:
    """
    Compare le SHA-256 de cor.pt avec cor.pt.sha256.

    Returns:
        (True, "") si intègre ou si le fichier hash est absent (pas bloquant)
        (False, message_erreur) si le hash ne correspond pas
    """
    if not os.path.exists(MODELE_PATH):
        return True, ""  # modèle absent — démarrage en mode fallback, pas une erreur d'intégrité

    if not os.path.exists(HASH_PATH):
        logger.info("[SECURITY] cor.pt.sha256 absent — vérification d'intégrité ignorée")
        return True, ""

    try:
        with open(HASH_PATH, "r", encoding="utf-8") as f:
            hash_attendu = f.read().strip().split()[0].lower()
    except Exception as e:
        return False, f"Impossible de lire cor.pt.sha256 : {e}"

    sha256 = hashlib.sha256()
    try:
        with open(MODELE_PATH, "rb") as f:
            for bloc in iter(lambda: f.read(65536), b""):
                sha256.update(bloc)
    except Exception as e:
        return False, f"Impossible de lire cor.pt : {e}"

    hash_reel = sha256.hexdigest().lower()

    if hash_reel != hash_attendu:
        msg = f"Intégrité du modèle compromise ! Attendu={hash_attendu[:12]}… Reçu={hash_reel[:12]}…"
        logger.critical(f"[SECURITY] {msg}")
        _journal("serveur", "system", "/startup", "INTEGRITY_FAIL", 0, msg)
        return False, msg

    logger.info(f"[SECURITY] Intégrité du modèle vérifiée (SHA-256 OK)")
    return True, ""


def generer_hash_modele():
    """
    Génère (ou régénère) cor.pt.sha256 à partir du modèle actuel.
    À appeler après chaque entraînement.
    """
    if not os.path.exists(MODELE_PATH):
        raise FileNotFoundError(f"Modèle introuvable : {MODELE_PATH}")

    sha256 = hashlib.sha256()
    with open(MODELE_PATH, "rb") as f:
        for bloc in iter(lambda: f.read(65536), b""):
            sha256.update(bloc)

    hash_val = sha256.hexdigest()

    with open(HASH_PATH, "w", encoding="utf-8") as f:
        f.write(f"{hash_val}  cor.pt\n")

    logger.info(f"[SECURITY] Hash généré : {hash_val[:12]}…")
    return hash_val


# ── Détection d'injection de prompt ───────────────────────────────────────────

def detecter_injection(texte: str) -> Optional[str]:
    """
    Analyse un texte pour détecter des tentatives d'injection de prompt.

    Returns:
        None si le texte est propre
        str (description du pattern détecté) si une injection est détectée
    """
    for pattern in _RE_INJECTION:
        m = pattern.search(texte)
        if m:
            return f"Pattern détecté : '{m.group(0)}'"
    return None


# ── Gestionnaire de clients (CRUD) ────────────────────────────────────────────

def lister_clients() -> list[dict]:
    """Retourne la liste des clients (sans les clés API en clair)."""
    if not os.path.exists(CLIENTS_PATH):
        return []

    try:
        with open(CLIENTS_PATH, "r", encoding="utf-8") as f:
            donnees = json.load(f)
    except Exception:
        return []

    result = []
    for c in donnees.get("clients", []):
        result.append({
            "client_id"          : c.get("client_id", ""),
            "nom"                : c.get("nom", ""),
            "quota_mensuel"      : c.get("quota_mensuel", 0),
            "requetes_utilisees" : c.get("requetes_utilisees", 0),
            "actif"              : c.get("actif", True),
            # La clé API est masquée : on montre seulement les 4 derniers chars
            "cle_api_masquee"    : "****" + c.get("cle_api", "")[-4:],
        })

    return result


def creer_client(nom: str, quota_mensuel: int = 1000) -> dict:
    """
    Crée un nouveau client avec une clé API générée aléatoirement.

    Returns:
        dict avec client_id, nom, cle_api (en clair, une seule fois), quota_mensuel
    """
    import secrets

    cle_api   = secrets.token_hex(32)  # 64 chars hex
    client_id = f"client_{secrets.token_hex(4)}"

    nouveau = {
        "client_id"          : client_id,
        "nom"                : nom,
        "cle_api"            : cle_api,
        "quota_mensuel"      : quota_mensuel,
        "requetes_utilisees" : 0,
        "actif"              : True,
        "date_creation"      : datetime.now(timezone.utc).isoformat(),
    }

    # Charger la liste existante
    clients_list = []
    if os.path.exists(CLIENTS_PATH):
        try:
            with open(CLIENTS_PATH, "r", encoding="utf-8") as f:
                clients_list = json.load(f).get("clients", [])
        except Exception:
            clients_list = []

    clients_list.append(nouveau)
    _sauvegarder_clients(clients_list)

    logger.info(f"[SECURITY] Nouveau client créé : {client_id} ({nom})")

    return {
        "client_id"     : client_id,
        "nom"           : nom,
        "cle_api"       : cle_api,  # retourné en clair UNE seule fois
        "quota_mensuel" : quota_mensuel,
        "actif"         : True,
    }


# ── Timeout de génération ──────────────────────────────────────────────────────

def avec_timeout(fn, timeout: int = TIMEOUT_GENERATION, *args, **kwargs):
    """
    Exécute fn(*args, **kwargs) avec un timeout.
    Lève TimeoutError si la génération dépasse `timeout` secondes.

    Utilise un thread dédié — compatible Windows (pas de signal.alarm).
    """
    resultat  = [None]
    exception = [None]

    def cible():
        try:
            resultat[0] = fn(*args, **kwargs)
        except Exception as e:
            exception[0] = e

    t = threading.Thread(target=cible, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        raise TimeoutError(f"Génération interrompue après {timeout}s")

    if exception[0]:
        raise exception[0]

    return resultat[0]
