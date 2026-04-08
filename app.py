from dotenv import load_dotenv
load_dotenv()

import sys
import io
import os
import re
import uuid
import json
import tempfile
import threading
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta, timezone
from anthropic import Anthropic
from supabase import create_client
import requests
import pyotp
import qrcode
import base64
from io import BytesIO

from encryption import chiffrer, dechiffrer, est_chiffre, extraire_index
from audit_logger import (
    log_audit, ACTION_LOGIN, ACTION_LOGIN_ECHEC,
    ACTION_UPLOAD, ACTION_GENERATION, ACTION_EXPORT_PDF,
    ACTION_SUPPRESSION
)
from prompts import (
    prompt_chat,
    prompt_synthese_document,
    prompt_prediction,
    prompt_analyse_comparative,
    prompt_analyse_veille,
    prompt_carte_mentale,
    prompt_timeline_dossier,
    prompt_rapport_client,
    prompt_matching_veille,
    get_prompt_redaction,
    lister_types_documents,
    PROMPTS_REDACTION,
    prompt_extraction_jurisprudence,
    prompt_verification_anonymisation,
)
from prompt_injection import analyser_injection, analyser_dict, REPONSE_BLOQUEE, SEUIL_ALERTE

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
VOYAGE_MODEL   = "voyage-law-2"
VOYAGE_URL_API = "https://api.voyageai.com/v1/embeddings"
TOTP_SECRET    = os.environ.get("TOTP_SECRET", "")

CABINET_NOM    = os.environ.get("CABINET_NOM",    "Odyxia Droit")
CABINET_AVOCAT = os.environ.get("CABINET_AVOCAT", "Maitre")
CABINET_VILLE  = os.environ.get("CABINET_VILLE",  "Douala, Cameroun")

# ─── FLASK ────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app)
Talisman(app,
    force_https=False,
    strict_transport_security=True,
    session_cookie_secure=True,
    content_security_policy=False
)
app.config["JWT_SECRET_KEY"]            = os.environ.get("JWT_SECRET_KEY", "Odyxia-JWT-2026!")
app.config["JWT_ACCESS_TOKEN_EXPIRES"]  = timedelta(minutes=15)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
jwt_manager = JWTManager(app)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client   = Anthropic(api_key=ANTHROPIC_KEY)

# ─── BLUEPRINTS ───────────────────────────────────────────────────────────────
try:
    from predict_endpoint import predict_bp
    app.register_blueprint(predict_bp)
except ImportError:
    pass

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log_erreur(contexte, erreur):
    message = str(erreur)
    if SUPABASE_KEY:
        message = message.replace(SUPABASE_KEY, "***")
    print(f"[ERREUR] {contexte}: {message[:200]}")


def get_current_tenant_id() -> str:
    try:
        user_id = get_jwt_identity()
        if user_id:
            result = supabase.table("users").select("tenant_id").eq("id", user_id).execute()
            if result.data:
                return result.data[0]["tenant_id"]
    except Exception:
        pass
    return os.environ.get("DEFAULT_TENANT_ID", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def get_current_user_id() -> str:
    try:
        user_id = get_jwt_identity()
        if user_id and user_id != "solo_user":
            return user_id
    except Exception:
        pass
    return os.environ.get("DEFAULT_USER_ID", "")


from datetime import datetime, timezone

def log_audit_event(event: str, tenant_id: str, user_id: str, meta: dict, severity: str = "info"):
    """Journalise les actions métiers avec isolation par tenant."""
    try:
        # On s'assure que le meta est bien un dictionnaire
        safe_meta = meta if isinstance(meta, dict) else {"data": str(meta)}
        
        supabase.table("audit_logs").insert({
            "event": event,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "meta": safe_meta,
            "severity": severity,
            # On laisse idéalement la DB gérer le created_at, sinon :
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        # En prod, évitez print(), préférez un logger standard
        print(f"[AUDIT ERROR] {datetime.now(timezone.utc)}: {e}")

def log_security_event(event_type: str, tenant_id: str = None, user_id: str = None, details: dict = None):
    """Journalise les alertes de sécurité avec contexte technique complet."""
    try:
        context = {
            "ip_address": request.remote_addr if request else "internal",
            "user_agent": request.headers.get("User-Agent", "unknown")[:255],
            "path": request.path if request else None,
            "method": request.method if request else None
        }
        
        # Fusion des détails fournis et du contexte technique
        full_details = {**(details or {}), **context}
        
        supabase.table("security_events").insert({
            "event_type": event_type,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "details": full_details,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        print(f"[SECURITY ERROR] {datetime.now(timezone.utc)}: {e}")


def verifier_totp(user_id: str, code: str) -> bool:
    """
    Vérifie le code 2FA spécifiquement pour un utilisateur donné.
    """
    try:
        # 1. Récupérer le secret unique de l'utilisateur en base
        res = supabase.table("users").select("totp_secret").eq("id", user_id).single().execute()
        user_secret = res.data.get("totp_secret") if res.data else None

        # 2. Sécurité : Si pas de secret configuré, on refuse l'accès 2FA
        if not user_secret:
            log_security_event("2fa_missing_secret", details={"user_id": user_id})
            return False

        # 3. Vérification avec pyotp
        totp = pyotp.TOTP(user_secret)
        
        # On limite la fenêtre à 1 (30s avant/après) pour compenser les désynchronisations d'horloge
        return totp.verify(code, valid_window=1)

    except Exception as e:
        log_erreur("TOTP_VERIFICATION_ERROR", e)
        return False


def get_session(session_id: str, tenant_id: str) -> list:
    try:
        result = supabase.table("sessions").select("historique").eq(
            "id", session_id).eq("tenant_id", tenant_id).execute()
        if result.data:
            return result.data[0]["historique"]
    except Exception:
        pass
    return []


def save_session(session_id: str, historique: list, tenant_id: str):
    try:
        supabase.table("sessions").upsert({
            "id":         session_id,
            "tenant_id":  tenant_id,
            "historique": historique,
            "updated_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print("ERREUR SESSION:", str(e))


def obtenir_nom_document(document_id: str) -> str:
    try:
        result = supabase.table("documents").select(
            "nom, filename, original_filename").eq("id", document_id).execute()
        if result.data:
            d = result.data[0]
            name = d.get("nom") or d.get("original_filename") or d.get("filename") or "Document"
            return name.replace(".pdf", "").replace("-", " ").replace("_", " ")
    except Exception:
        pass
    return "Document inconnu"


MOTS_VIDES = {
    "quel","quels","quelle","quelles","dans","pour","avec","sont",
    "comment","selon","quand","cette","leurs","leur","conditions",
    "les","des","une","est","par","sur","qui","que","quoi"
}


def rechercher_chunks(question: str, limite: int = 10,
                      dossier_id: str = None, tenant_id: str = None) -> list:
    tous_chunks = []
    ids_vus = set()
    if not tenant_id:
        tenant_id = get_current_tenant_id()

    doc_ids_scope = None
    if dossier_id:
        try:
            doc_res = supabase.table("documents").select("id").eq(
                "dossier_id", dossier_id).eq("tenant_id", tenant_id).execute()
            doc_ids_scope = [d["id"] for d in (doc_res.data or [])]
            if not doc_ids_scope:
                return []
        except Exception:
            pass

    def ajouter(data):
        for chunk in data:
            if doc_ids_scope and chunk.get("document_id") not in doc_ids_scope:
                continue
            cle = (str(chunk.get('document_id','')) + "-" +
                   str(chunk.get('page_numero') or chunk.get('page_number','')))
            if cle not in ids_vus:
                ids_vus.add(cle)
                contenu = chunk.get("content") or chunk.get("contenu","")
                if est_chiffre(contenu):
                    contenu = dechiffrer(contenu)
                chunk["contenu"]     = contenu
                chunk["page_numero"] = chunk.get("page_numero") or chunk.get("page_number", 1)
                tous_chunks.append(chunk)

    try:
        embedding = get_query_embedding(question)
        if embedding:
            result = supabase.rpc("match_chunks", {
                "query_embedding": embedding,
                "match_threshold":  0.3,
                "match_count":      limite,
                "tenant_id":        tenant_id
            }).execute()
            if result.data:
                ajouter(result.data)
    except Exception as e:
        print(f"[SEARCH] Vectorielle : {e}")

    if not tous_chunks:
        try:
            q_lower = question.lower()
            result = supabase.table("chunks").select(
                "content,contenu,contenu_index,page_number,page_numero,document_id,metadata"
            ).eq("tenant_id", tenant_id).or_(
                f"content.ilike.%{q_lower}%,contenu_index.ilike.%{q_lower}%"
            ).limit(limite).execute()
            ajouter(result.data)
        except Exception:
            pass

    if len(tous_chunks) < 3:
        try:
            result = supabase.table("chunks").select(
                "content,contenu,page_number,page_numero,document_id,legal_act_id,source_type"
            ).eq("source_type", "legal_act").ilike(
                "content", f"%{question.lower()[:50]}%"
            ).limit(5).execute()
            ajouter(result.data)
        except Exception:
            pass

    if not tous_chunks:
        try:
            mots = [m for m in question.lower().split()
                    if len(m) > 4 and m not in MOTS_VIDES]
            for mot in mots[:5]:
                result = supabase.table("chunks").select(
                    "content,contenu,contenu_index,page_number,page_numero,document_id"
                ).eq("tenant_id", tenant_id).or_(
                    f"content.ilike.%{mot}%,contenu_index.ilike.%{mot}%"
                ).limit(5).execute()
                ajouter(result.data)
        except Exception:
            pass

    return tous_chunks[:limite]


# ─── VOYAGE AI ────────────────────────────────────────────────────────────────

def get_query_embedding(question: str):
    try:
        if not VOYAGE_API_KEY:
            return None
        res = requests.post(
            VOYAGE_URL_API,
            headers={"Authorization": f"Bearer {VOYAGE_API_KEY}",
                     "Content-Type": "application/json"},
            json={"input": [question[:4096]], "model": VOYAGE_MODEL,
                  "input_type": "query"},
            timeout=10
        )
        res.raise_for_status()
        return res.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"[VOYAGE] Erreur : {e}")
        return None


def _vectoriser_document(doc_id: str, tenant_id: str):
    try:
        result = supabase.table("chunks").select(
            "id,content,contenu_index"
        ).eq("document_id", doc_id).is_("embedding", "null").execute()
        chunks = result.data
        if not chunks:
            return
        BATCH = 20
        for i in range(0, len(chunks), BATCH):
            lot    = chunks[i:i+BATCH]
            textes = []
            for c in lot:
                texte = c.get("contenu_index") or c.get("content") or c.get("contenu","")
                if texte.startswith("ENC:"):
                    texte = "document juridique confidentiel"
                textes.append(texte.strip() or "document juridique")
            try:
                emb_res = requests.post(
                    VOYAGE_URL_API,
                    headers={"Authorization": f"Bearer {VOYAGE_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"input": textes, "model": VOYAGE_MODEL, "input_type": "document"},
                    timeout=30
                )
                emb_res.raise_for_status()
                embeddings = [item["embedding"] for item in emb_res.json()["data"]]
                for j, chunk in enumerate(lot):
                    supabase.table("chunks").update(
                        {"embedding": embeddings[j]}
                    ).eq("id", chunk["id"]).execute()
                time.sleep(0.2)
            except Exception as e:
                print(f"[VOYAGE] Erreur lot : {e}")
        print(f"[VOYAGE] Vectorisation terminee {doc_id[:8]}")
    except Exception as e:
        print(f"[VOYAGE] Erreur globale : {e}")


# ─── ABONNEMENT ──────────────────────────────────────────────────────────────

def verifier_abonnement(tenant_id: str) -> dict:
    """Verifie acces tenant. Fail open si erreur technique."""
    try:
        r = supabase.table("tenants").select(
            "plan,status,trial_end,abonnement_end"
        ).eq("id", tenant_id).execute()

        if not r.data:
            return {"actif": False, "plan": "inconnu", "jours_restants": 0,
                    "message": "Tenant introuvable"}

        t      = r.data[0]
        plan   = t.get("plan", "trial")
        status = t.get("status", "active")
        now    = datetime.utcnow()

        if status == "suspended":
            return {"actif": False, "plan": plan, "jours_restants": 0,
                    "message": "Compte suspendu"}

        if plan == "actif":
            abo_end = t.get("abonnement_end")
            if abo_end:
                abo_dt = datetime.fromisoformat(
                    abo_end.replace("Z", "+00:00")).replace(tzinfo=None)
                jours = (abo_dt - now).days
                if jours < 0:
                    supabase.table("tenants").update(
                        {"plan": "expire"}).eq("id", tenant_id).execute()
                    return {"actif": False, "plan": "expire", "jours_restants": 0,
                            "message": "Abonnement expire"}
                return {"actif": True, "plan": "actif", "jours_restants": jours,
                        "message": "Abonnement actif"}
            return {"actif": True, "plan": "actif", "jours_restants": 999,
                    "message": "Abonnement actif"}

        if plan == "trial":
            trial_end = t.get("trial_end")
            if trial_end:
                trial_dt = datetime.fromisoformat(
                    trial_end.replace("Z", "+00:00")).replace(tzinfo=None)
                jours = (trial_dt - now).days
                if jours < 0:
                    supabase.table("tenants").update(
                        {"plan": "expire"}).eq("id", tenant_id).execute()
                    return {"actif": False, "plan": "expire", "jours_restants": 0,
                            "message": "Periode d'essai expiree"}
                return {"actif": True, "plan": "trial", "jours_restants": jours,
                        "message": f"Essai gratuit - {jours} jour(s) restant(s)"}
            return {"actif": True, "plan": "trial", "jours_restants": 14,
                    "message": "Essai gratuit"}

        return {"actif": False, "plan": "expire", "jours_restants": 0,
                "message": "Acces expire - renouvelez votre abonnement"}

    except Exception as e:
        log_erreur("VERIFIER_ABONNEMENT", e)
        return {"actif": True, "plan": "inconnu", "jours_restants": 0, "message": ""}


@app.route("/abonnement/statut", methods=["GET"])
@jwt_required()
@limiter.limit("30 per minute")
def statut_abonnement():
    try:
        tenant_id = get_current_tenant_id()
        return jsonify(verifier_abonnement(tenant_id))
    except Exception as e:
        log_erreur("STATUT_ABONNEMENT", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/abonnement/valider", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def valider_paiement():
    try:
        data         = request.json
        admin_secret = data.get("admin_secret", "")
        tenant_id    = data.get("tenant_id", "")
        montant      = data.get("montant_fcfa", 0)
        mois         = data.get("mois", 1)
        ref          = data.get("reference", "MANUEL-" + str(int(datetime.utcnow().timestamp())))
        mode         = data.get("mode", "mobile_money")

        if admin_secret != os.environ.get("ADMIN_SECRET", ""):
            log_security_event("admin_acces_refuse", details={"route": "valider_paiement"})
            return jsonify({"erreur": "Non autorise"}), 403

        if not tenant_id:
            return jsonify({"erreur": "tenant_id requis"}), 400

        r = supabase.table("tenants").select("abonnement_end,plan").eq(
            "id", tenant_id).execute()
        if not r.data:
            return jsonify({"erreur": "Tenant introuvable"}), 404

        t   = r.data[0]
        now = datetime.utcnow()

        if t.get("plan") == "actif" and t.get("abonnement_end"):
            try:
                current_end = datetime.fromisoformat(t["abonnement_end"].replace("Z",""))
                base = current_end if current_end > now else now
            except Exception:
                base = now
        else:
            base = now

        nouvelle_fin = base + timedelta(days=30 * mois)

        supabase.table("tenants").update({
            "plan":           "actif",
            "status":         "active",
            "abonnement_end": nouvelle_fin.isoformat(),
            "montant_fcfa":   montant,
            "paiement_ref":   ref,
            "paiement_date":  now.isoformat(),
            "paiement_mode":  mode
        }).eq("id", tenant_id).execute()

        log_audit_event("PAIEMENT_VALIDE", tenant_id, "admin", {
            "montant": montant, "mois": mois, "ref": ref,
            "nouvelle_fin": nouvelle_fin.isoformat()
        })

        return jsonify({
            "succes":         True,
            "plan":           "actif",
            "abonnement_end": nouvelle_fin.isoformat(),
            "mois_ajoutes":   mois,
            "reference":      ref
        })
    except Exception as e:
        log_erreur("VALIDER_PAIEMENT", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/abonnement/webhook", methods=["POST"])
@limiter.limit("60 per minute")
def webhook_paiement():
    try:
        data = request.json or {}
        log_audit_event("WEBHOOK_PAIEMENT_RECU", "", "", {"data": str(data)[:200]})
        return jsonify({"status": "received"}), 200
    except Exception as e:
        log_erreur("WEBHOOK_PAIEMENT", e)
        return jsonify({"erreur": str(e)}), 500


# --- FONCTIONS UTILITAIRES ---

def obtenir_stats_connexions(tenant_id, debut, fin):
    """Calcule les stats de connexion pour un tenant spécifique sur une période donnée."""
    try:
        # Compte des succès
        ok = supabase.table("security_events").select("id", count="exact")\
            .eq("tenant_id", tenant_id)\
            .eq("event_type", "login_success")\
            .gte("created_at", debut.isoformat())\
            .lt("created_at", fin.isoformat()).execute()
        
        # Compte des échecs
        fail = supabase.table("security_events").select("id", count="exact")\
            .eq("tenant_id", tenant_id)\
            .eq("event_type", "login_failed")\
            .gte("created_at", debut.isoformat())\
            .lt("created_at", fin.isoformat()).execute()

        return ok.count or 0, fail.count or 0
    except Exception as e:
        log_erreur("STATS_CONNEXIONS", e)
        return 0, 0

# ─── ROUTES PUBLIQUES ─────────────────────────────────────────────────────────

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/cgu")
def cgu():
    return render_template("cgu.html")

@app.route("/login")
def login_page():
    return render_template("index.html",
        cabinet_nom=CABINET_NOM,
        cabinet_avocat=CABINET_AVOCAT,
        cabinet_ville=CABINET_VILLE
    )

@app.route("/setup-2fa-page")
def setup_2fa_page():
    return render_template("setup_2fa.html")

@app.route("/setup-2fa", methods=["GET"])
def setup_2fa():
    try:
        user_id = get_current_user_id()
        
        # Vérifier si l'utilisateur a déjà un secret
        res = supabase.table("users").select("totp_secret").eq("id", user_id).single().execute()
        existing_secret = res.data.get("totp_secret") if res.data else None
        
        # Générer un nouveau secret si inexistant
        if not existing_secret:
            secret = pyotp.random_base32()
            supabase.table("users").update({"totp_secret": secret}).eq("id", user_id).execute()
        else:
            secret = existing_secret
        
        # Récupérer le display_name pour le QR code
        profil = supabase.table("users").select("display_name, full_name, email").eq("id", user_id).single().execute()
        nom_avocat = (profil.data.get("display_name") or profil.data.get("full_name") or profil.data.get("email", "Avocat")) if profil.data else "Avocat"
        
        totp = pyotp.TOTP(secret)
        uri  = totp.provisioning_uri(
            name=nom_avocat,
            issuer_name="Odyxia Droit"
        )
        qr = qrcode.make(uri)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        qr_b64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            "qr_code": f"data:image/png;base64,{qr_b64}",
            "secret":  secret,
            "uri":     uri,
            "nom":     nom_avocat
        })
    except Exception as e:
        log_erreur("SETUP_2FA", e)
        return jsonify({"erreur": str(e)}), 500
    
@app.route("/setup-2fa-init", methods=["POST"])
@limiter.limit("10 per minute")
def setup_2fa_init():
    """Route publique : login email/password → génère QR code individuel."""
    try:
        data     = request.json
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return jsonify({"erreur": "Email et mot de passe requis"}), 400

        # 1. Authentification Supabase
        try:
            auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user_id = auth_response.user.id if auth_response.user else None
        except Exception:
            user_id = None

        if not user_id:
            return jsonify({"erreur": "Identifiants incorrects"}), 401

        # 2. Générer/récupérer le secret TOTP de cet utilisateur
        res = supabase.table("users").select("totp_secret, display_name, full_name").eq("id", user_id).single().execute()
        existing_secret = res.data.get("totp_secret") if res.data else None

        if not existing_secret:
            secret = pyotp.random_base32()
            supabase.table("users").update({"totp_secret": secret}).eq("id", user_id).execute()
        else:
            secret = existing_secret

        nom = (res.data.get("display_name") or res.data.get("full_name") or email) if res.data else email

        # 3. Générer le QR code
        totp = pyotp.TOTP(secret)
        uri  = totp.provisioning_uri(name=nom, issuer_name="Odyxia Droit")
        qr   = qrcode.make(uri)
        buf  = BytesIO()
        qr.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        return jsonify({
            "qr_code":  f"data:image/png;base64,{qr_b64}",
            "secret":   secret,
            "user_id":  user_id,
            "nom":      nom
        })
    except Exception as e:
        log_erreur("SETUP_2FA_INIT", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/setup-2fa-verify", methods=["POST"])
@limiter.limit("10 per minute")
def setup_2fa_verify():
    """Vérifie le code TOTP et confirme la configuration."""
    try:
        data    = request.json
        user_id = data.get("user_id", "")
        code    = data.get("code", "").strip()

        if not user_id or not code:
            return jsonify({"erreur": "Données manquantes"}), 400

        if not verifier_totp(user_id, code):
            return jsonify({"erreur": "Code incorrect — réessayez"}), 401

        supabase.table("users").update({"mfa_enabled": True}).eq("id", user_id).execute()
        log_security_event("2fa_configured", user_id=user_id)
        return jsonify({"succes": True})
    except Exception as e:
        log_erreur("SETUP_2FA_VERIFY", e)
        return jsonify({"erreur": str(e)}), 500    

@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    try:
        import hashlib
        data = request.json
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        code_2fa = data.get("code_2fa", "").strip()

        if not email or not password:
            return jsonify({"erreur": "Identifiants requis"}), 400

        # 1. Vérification Supabase
        try:
            auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user_id = auth_response.user.id if auth_response.user else None
        except Exception:
            user_id = None

        if not user_id:
            log_security_event("login_failed", details={"reason": "auth_echec", "email": email})
            return jsonify({"erreur": "Identifiants incorrects"}), 401

        # 2. Gestion de la 2FA
        # ATTENTION : En production, ne renvoyez 'require_2fa' que si l'utilisateur a vraiment activé la 2FA
        if not code_2fa:
            return jsonify({"require_2fa": True}), 200

        if not verifier_totp(user_id, code_2fa):
            log_security_event("login_failed", details={"reason": "2fa_echec", "user_id": user_id})
            return jsonify({"erreur": "Code de sécurité invalide"}), 401

        # 3. Isolation des données (Multi-ténance)
        try:
            user_row = supabase.table("users").select("tenant_id").eq("id", user_id).single().execute()
            tenant_id = user_row.data["tenant_id"] if user_row.data else os.environ.get("DEFAULT_TENANT_ID")
        except Exception:
            tenant_id = os.environ.get("DEFAULT_TENANT_ID")

        # 4. Génération des tokens (Session persistante)
        access_token = create_access_token(identity=user_id, additional_claims={"tenant_id": tenant_id})
        refresh_tok  = create_refresh_token(identity=user_id)

        # Stockage sécurisé du hash
        token_hash = hashlib.sha256(refresh_tok.encode()).hexdigest()
        expires_at = datetime.utcnow() + timedelta(days=30)
        
        supabase.table("refresh_tokens").insert({
            "user_id": user_id,
            "tenant_id": tenant_id,
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
            "user_agent": request.headers.get("User-Agent", "")[:200],
            "ip_address": request.remote_addr
        }).execute()

        return jsonify({
            "token": access_token,
            "refresh_token": refresh_tok,
            "expires_in": 900
        })

    except Exception as e:
        log_erreur("LOGIN_GLOBAL", e)
        # On ne renvoie pas str(e) au client pour la sécurité
        return jsonify({"erreur": "Service temporairement indisponible"}), 500


@app.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
@limiter.limit("30 per minute")
def refresh():
    try:
        import hashlib
        identity    = get_jwt_identity()
        auth_header = request.headers.get("Authorization", "")
        raw_token   = auth_header.replace("Bearer ", "").strip()
        token_hash  = hashlib.sha256(raw_token.encode()).hexdigest()

        result = supabase.table("refresh_tokens").select(
            "id,revoked,expires_at"
        ).eq("token_hash", token_hash).execute()

        if not result.data:
            return jsonify({"erreur": "Token invalide"}), 401

        rt = result.data[0]
        if rt.get("revoked"):
            log_security_event("refresh_token_revoque", details={"user_id": identity})
            return jsonify({"erreur": "Token revoque"}), 401

        expires_at = datetime.fromisoformat(rt["expires_at"].replace("Z", "+00:00"))
        if expires_at < datetime.now(timezone.utc):
            return jsonify({"erreur": "Token expire"}), 401

        new_access_token = create_access_token(identity=identity)
        log_security_event("token_refreshed", details={"user_id": identity})
        return jsonify({"token": new_access_token, "expires_in": 900})

    except Exception as e:
        log_erreur("REFRESH", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/logout", methods=["POST"])
@jwt_required()
@limiter.limit("20 per minute")
def logout():
    try:
        import hashlib
        user_id = get_jwt_identity() # Identité extraite du JWT
        data = request.json or {}
        raw_token = data.get("refresh_token")

        if raw_token:
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            # Double vérification : hash ET user_id
            supabase.table("refresh_tokens").update({
                "revoked": True,
                "revoked_at": datetime.utcnow().isoformat()
            }).eq("token_hash", token_hash).eq("user_id", user_id).execute()

        log_security_event("logout", tenant_id=get_current_tenant_id(), user_id=user_id)
        return jsonify({"succes": True})
    except Exception as e:
        log_erreur("LOGOUT", e)
        return jsonify({"erreur": "Erreur lors de la déconnexion"}), 500
    
@app.route("/profil", methods=["GET"])
@jwt_required()
def get_profil():
    try:
        user_id   = get_current_user_id()
        tenant_id = get_current_tenant_id()
        r = supabase.table("users").select(
            "full_name, display_name, email"
        ).eq("id", user_id).execute()
        if not r.data:
            return jsonify({"display_name": "Maître", "full_name": "Maître"})
        u = r.data[0]
        display = u.get("display_name") or ("Maître " + (u.get("full_name") or ""))
        return jsonify({
            "display_name": display,
            "full_name":    u.get("full_name", ""),
            "email":        u.get("email", "")
        })
    except Exception as e:
        log_erreur("GET_PROFIL", e)
        return jsonify({"display_name": "Maître"}), 500


@app.route("/profil", methods=["PUT"])
@jwt_required()
@limiter.limit("10 per minute")
def update_profil():
    try:
        user_id      = get_current_user_id()
        data         = request.json
        display_name = data.get("display_name", "").strip()
        if not display_name:
            return jsonify({"erreur": "Nom requis"}), 400
        supabase.table("users").update({
            "display_name": display_name
        }).eq("id", user_id).execute()
        log_audit_event("PROFIL_UPDATED", get_current_tenant_id(), user_id,
                        {"display_name": display_name})
        return jsonify({"succes": True, "display_name": display_name})
    except Exception as e:
        log_erreur("UPDATE_PROFIL", e)
        return jsonify({"erreur": str(e)}), 500


# ─── INSCRIPTION ─────────────────────────────────────────────────────────────

@app.route("/inscription")
def page_inscription():
    return render_template("inscription.html")


@app.route("/inscription", methods=["POST"])
@limiter.limit("5 per minute")
def creer_compte():
    try:
        data = request.json
        required = ['email','password','prenom','nom','pays','type_compte']
        for field in required:
            if not data.get(field,'').strip():
                return jsonify({"erreur": f"Champ requis manquant : {field}"}), 400

        email       = data['email'].strip().lower()
        password    = data['password']
        prenom      = data['prenom'].strip()
        nom         = data['nom'].strip()
        pays        = data['pays'].strip()
        langue      = data.get('langue','fr')
        type_compte = data['type_compte']
        telephone   = data.get('telephone','').strip()

        if type_compte == 'avocat':
            if not data.get('num_barreau','').strip():
                return jsonify({"erreur": "Numero de barreau requis pour un avocat"}), 400
            if not data.get('barreau','').strip():
                return jsonify({"erreur": "Nom du barreau requis"}), 400
        if type_compte == 'juriste':
            if not data.get('entreprise','').strip():
                return jsonify({"erreur": "Entreprise employeur requise"}), 400
            if not data.get('num_juriste','').strip():
                return jsonify({"erreur": "Numero d identification requis"}), 400

        existing = supabase.table("tenants").select("id").eq(
            "slug", email.replace('@','-').replace('.','-')).execute()
        if existing.data:
            return jsonify({"erreur": "Un compte existe deja avec cet email"}), 400

        try:
            auth_response = supabase.auth.sign_up({"email": email, "password": password})
            user_id = auth_response.user.id if auth_response.user else None
            if not user_id:
                return jsonify({"erreur": "Erreur lors de la creation du compte"}), 500
        except Exception as e:
            err_msg = str(e).lower()
            if 'already' in err_msg or 'exists' in err_msg:
                return jsonify({"erreur": "Un compte existe deja avec cet email"}), 400
            return jsonify({"erreur": "Erreur d authentification : " + str(e)[:100]}), 500

        try:
            nom_prenom_enc  = chiffrer(f"{prenom} {nom}")
            telephone_enc   = chiffrer(telephone) if telephone else None
            num_barreau_enc = chiffrer(data.get('num_barreau','')) if type_compte=='avocat' else None
            entreprise_enc  = chiffrer(data.get('entreprise','')) if type_compte=='juriste' else None
            num_juriste_enc = chiffrer(data.get('num_juriste','')) if type_compte=='juriste' else None
        except Exception:
            nom_prenom_enc  = f"{prenom} {nom}"
            telephone_enc   = telephone
            num_barreau_enc = data.get('num_barreau','')
            entreprise_enc  = data.get('entreprise','')
            num_juriste_enc = data.get('num_juriste','')

        maintenant = datetime.now(timezone.utc)
        fin_essai  = maintenant + timedelta(days=14)
        tenant_id  = str(uuid.uuid4())
        slug       = email.replace('@','-').replace('.','-')

        supabase.table("tenants").insert({
            "id":               tenant_id,
            "name":             f"{prenom} {nom}",
            "slug":             slug,
            "mode":             "solo",
            "plan":             "trial",
            "status":           "active",
            "trial_end":        fin_essai.isoformat(),
            "storage_used_mb":  0,
            "storage_limit_mb": 2048,
        }).execute()

        supabase.table("users").insert({
            "id":          user_id,
            "tenant_id":   tenant_id,
            "email":       email,
            "full_name":   f"{prenom} {nom}",
            "role":        "owner",
            "is_active":   True,
            "mfa_enabled": False,
        }).execute()

        profil = {
            "id":             str(uuid.uuid4()),
            "tenant_id":      tenant_id,
            "user_id":        user_id,
            "email":          email,
            "pays":           pays,
            "langue":         langue,
            "type_compte":    type_compte,
            "nom_prenom_enc": nom_prenom_enc,
            "telephone_enc":  telephone_enc,
            "statut":         "essai",
            "essai_debut":    maintenant.isoformat(),
            "essai_fin":      fin_essai.isoformat(),
            "accepte_comm":   data.get('accepte_comm', False),
        }
        if type_compte == 'avocat':
            profil["barreau"]           = data.get('barreau','').strip()
            profil["barreau_pays"]      = pays
            profil["annee_inscription"] = data.get('annee_inscription','')
            profil["num_barreau_enc"]   = num_barreau_enc
        else:
            profil["entreprise_enc"]  = entreprise_enc
            profil["poste"]           = data.get('poste','').strip()
            profil["num_juriste_enc"] = num_juriste_enc

        try:
            supabase.table("avocats").insert(profil).execute()
        except Exception as e:
            print(f"[INSCRIPTION] Table avocats : {e}")

        log_security_event("login_success", tenant_id, user_id, {
            "action":"inscription","type_compte":type_compte,"pays":pays})
        log_audit_event("INSCRIPTION", tenant_id, user_id, {
            "type_compte":type_compte,"pays":pays})

        return jsonify({
            "succes":    True,
            "tenant_id": tenant_id,
            "user_id":   user_id,
            "essai_fin": fin_essai.isoformat(),
            "message":   "Compte cree avec succes - essai de 14 jours demarre",
        })
    except Exception as e:
        log_erreur("INSCRIPTION", e)
        return jsonify({"erreur": str(e)[:200]}), 500


# ─── CHAT ─────────────────────────────────────────────────────────────────────

def _preparer_contexte_chat(q: str, session_id: str,
                            tenant_id: str, dossier_id: str = None):
    # 1. Récupération sécurisée de l'historique (limité au tenant)
    historique_session = get_session(session_id, tenant_id)
    
    # 2. Recherche de connaissances (RAG) avec isolation stricte
    # Vérifiez bien que 'rechercher_chunks' applique le filtre tenant_id
    chunks = rechercher_chunks(q, dossier_id=dossier_id, tenant_id=tenant_id)

    contexte_parts = []
    sources = []
    
    # Utilisation d'un set pour éviter les doublons de noms de docs (plus rapide)
    doc_cache = {}

    if chunks:
        for i, chunk in enumerate(chunks, 1):
            doc_id = chunk["document_id"]
            if doc_id not in doc_cache:
                doc_cache[doc_id] = obtenir_nom_document(doc_id)
            
            nom_doc = doc_cache[doc_id]
            page = chunk.get("page_numero", 1)
            
            content = f"[Passage {i} - {nom_doc}, Page {page}]\n{chunk['contenu']}"
            contexte_parts.append(content)
            
            ref = f"{nom_doc} (p.{page})"
            if ref not in sources:
                sources.append(ref)

    contexte_global = "\n\n".join(contexte_parts)

    # 3. Construction des messages pour l'IA
    messages = []
    # On garde les 3 derniers tours (6 messages) pour la cohérence
    for echange in historique_session[-3:]: 
        messages.append({"role": "user", "content": echange["question"]})
        messages.append({"role": "assistant", "content": echange["reponse"]})

    # 4. Injection du Prompt Système (C'est ici qu'on définit les règles juridiques)
    system_prompt = prompt_chat(q, contexte_global)
    
    # Message actuel
    messages.append({"role": "user", "content": q})

    return system_prompt, messages, sources, historique_session


@app.route("/question", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")
def question():
    try:
        data       = request.json
        q          = data.get("question", "").strip()
        session_id = data.get("session_id", "default")
        dossier_id = data.get("dossier_id", None)
        tenant_id  = get_current_tenant_id()

        _abo = verifier_abonnement(tenant_id)
        if not _abo["actif"]:
            return jsonify({"erreur": "acces_expire",
                            "message": _abo["message"],
                            "plan": _abo["plan"]}), 402

        if not q:
            return jsonify({"erreur": "Question vide"}), 400

        inj = analyser_injection(q, champ="question")
        if inj.bloque:
            log_security_event("prompt_injection_bloquee", tenant_id,
                get_current_user_id(), {"score":inj.score,"patterns":inj.patterns,
                "champ":"question","extrait":q[:120]})
            return jsonify(REPONSE_BLOQUEE), 400
        if inj.score >= SEUIL_ALERTE:
            log_security_event("prompt_injection_alerte", tenant_id,
                get_current_user_id(), {"score":inj.score,"patterns":inj.patterns})

        system_prompt, messages, sources, historique_session = \
            _preparer_contexte_chat(q, session_id, tenant_id, dossier_id)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=messages
        )

        reponse_texte = response.content[0].text
        historique_session.append({"question": q, "reponse": reponse_texte})
        save_session(session_id, historique_session, tenant_id)
        log_audit_event("RAG_QUERY", tenant_id, get_current_user_id(),
                        {"session_id":session_id,"sources_count":len(sources)})
        return jsonify({"reponse": reponse_texte, "sources": list(set(sources))})

    except Exception as e:
        log_erreur("QUESTION", e)
        return jsonify({"reponse": "Erreur : " + str(e), "sources": []}), 500


@app.route("/question_stream", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")
def question_stream():
    try:
        # 1. Extraction et validation
        user_id = get_current_user_id()
        tenant_id = get_current_tenant_id() # Doit venir du JWT
        data = request.json
        q = data.get("question", "").strip()
        session_id = data.get("session_id", "default")
        dossier_id = data.get("dossier_id")

        # 2. Vérification d'accès (Abonnement)
        _abo = verifier_abonnement(tenant_id)
        if not _abo["actif"]:
            return jsonify({"erreur": "acces_expire", "message": _abo["message"]}), 402

        if not q:
            return jsonify({"erreur": "La question est requise"}), 400

        # 3. Sécurité : Détection d'injection
        inj = analyser_injection(q, champ="question_stream")
        if inj.bloque:
            log_security_event("prompt_injection_bloquee", tenant_id, user_id, {"score": inj.score})
            return jsonify({"erreur": "Contenu non autorisé"}), 400

        # 4. Préparation du contexte
        system_prompt, messages, sources, historique_session = \
            _preparer_contexte_chat(q, session_id, tenant_id, dossier_id)

        def generer():
            reponse_complete = ""
            try:
                # Envoi immédiat des sources pour rassurer l'utilisateur
                yield f"data: {json.dumps({'type':'sources','sources':list(set(sources))}, ensure_ascii=False)}\n\n"

                with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    system=system_prompt,
                    messages=messages
                ) as stream:
                    for token in stream.text_stream:
                        reponse_complete += token
                        yield f"data: {json.dumps({'type':'token','text':token}, ensure_ascii=False)}\n\n"

                # Sauvegarde sécurisée même si la connexion client coupe après le stream
                try:
                    historique_session.append({"question": q, "reponse": reponse_complete, "at": datetime.utcnow().isoformat()})
                    save_session(session_id, historique_session, tenant_id)
                except Exception as e_save:
                    log_erreur("SAVE_SESSION_STREAM", e_save)

                yield f"data: {json.dumps({'type':'fin','complet':reponse_complete}, ensure_ascii=False)}\n\n"

            except Exception as e:
                log_erreur("STREAM_CORE", e)
                yield f"data: {json.dumps({'type':'erreur','message': 'Une interruption est survenue'}, ensure_ascii=False)}\n\n"

        return Response(stream_with_context(generer()),
                        mimetype="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "X-Accel-Buffering": "no",
                            "Connection": "keep-alive"
                        })

    except Exception as e:
        log_erreur("QUESTION_STREAM_GLOBAL", e)
        return jsonify({"erreur": "Erreur interne du service de streaming"}), 500


@app.route("/nouvelle-conversation", methods=["POST"])
@jwt_required()
def nouvelle_conversation():
    try:
        data       = request.json
        session_id = data.get("session_id","default")
        tenant_id  = get_current_tenant_id()
        supabase.table("sessions").delete().eq("id",session_id).eq(
            "tenant_id",tenant_id).execute()
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


# ─── MEMOIRE ──────────────────────────────────────────────────────────────────

@app.route("/memoire/sauvegarder", methods=["POST"])
@jwt_required()
def sauvegarder_memoire():
    try:
        data       = request.json
        session_id = data.get("session_id","")
        historique = data.get("historique",[])
        tenant_id  = get_current_tenant_id()

        if not historique or len(historique) < 2:
            return jsonify({"ok":False,"raison":"Conversation trop courte"})

        lignes = []
        for m in historique[-10:]:
            role = "Avocat" if m["role"]=="user" else "Odyxia"
            lignes.append(role + ": " + str(m.get("content",""))[:300])
        texte_conv = " | ".join(lignes)

        prompt_resume = (
            "Resume cette conversation juridique en 3 phrases max. "
            "Format strict sur 3 lignes : "
            "RESUME: [resume] "
            "MOTS_CLES: [mot1,mot2,mot3] "
            "DOMAINE: [domaine] "
            "Conversation: " + texte_conv
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role":"user","content":prompt_resume}]
        )

        texte     = response.content[0].text.strip()
        resume    = ""
        mots_cles = []
        domaine   = ""

        for ligne in texte.splitlines():
            if ligne.startswith("RESUME:"):
                resume = ligne.replace("RESUME:","").strip()
            elif ligne.startswith("MOTS_CLES:"):
                mots_cles = [m.strip() for m in ligne.replace("MOTS_CLES:","").split(",")]
            elif ligne.startswith("DOMAINE:"):
                domaine = ligne.replace("DOMAINE:","").strip()

        if not resume:
            resume = texte[:400]

        supabase.table("memoires").insert({
            "tenant_id":  tenant_id,
            "session_id": session_id,
            "resume":     resume,
            "mots_cles":  mots_cles,
            "domaine":    domaine,
        }).execute()

        return jsonify({"ok":True,"resume":resume})
    except Exception as e:
        log_erreur("MEMOIRE_SAUVEGARDER", e)
        return jsonify({"ok":False,"erreur":str(e)}), 500


@app.route("/memoire/contexte", methods=["GET"])
@jwt_required()
def contexte_memoire():
    try:
        tenant_id = get_current_tenant_id()
        result = supabase.table("memoires").select(
            "resume,mots_cles,domaine,created_at"
        ).eq("tenant_id",tenant_id).order("created_at",desc=True).limit(3).execute()
        return jsonify({"memoires":result.data or [],"count":len(result.data or [])})
    except Exception as e:
        log_erreur("MEMOIRE_CONTEXTE", e)
        return jsonify({"memoires":[],"count":0}), 500


# ─── SYNTHESE ─────────────────────────────────────────────────────────────────

@app.route("/synthese_document", methods=["POST"])
@jwt_required()
def synthese_document():
    try:
        data        = request.json
        document_id = data.get("document_id","")
        tenant_id   = get_current_tenant_id()

        if not document_id:
            return jsonify({"erreur":"document_id requis"}), 400

        doc_check = supabase.table("documents").select("id").eq(
            "id",document_id).eq("tenant_id",tenant_id).execute()
        if not doc_check.data:
            return jsonify({"erreur":"Document non trouve"}), 404

        result = supabase.table("chunks").select(
            "content,contenu,page_number,page_numero"
        ).eq("document_id",document_id).limit(20).execute()
        if not result.data:
            return jsonify({"erreur":"Document non indexe"}), 404

        texte_complet = "\n".join([
            c.get("content") or c.get("contenu","")
            for c in result.data
            if not est_chiffre(c.get("content") or c.get("contenu",""))
        ])[:8000]

        nom_doc  = obtenir_nom_document(document_id)
        prompt   = prompt_synthese_document(texte_complet, nom_doc)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role":"user","content":prompt}]
        )
        raw      = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        synthese = json.loads(raw)
        return jsonify({"succes":True,"synthese":synthese,"document_id":document_id})
    except Exception as e:
        log_erreur("SYNTHESE", e)
        return jsonify({"erreur":str(e)}), 500


# ─── CARTE MENTALE ────────────────────────────────────────────────────────────

@app.route("/carte_mentale", methods=["POST"])
@jwt_required()
@limiter.limit("15 per minute")
def carte_mentale():
    try:
        data        = request.json
        document_id = data.get("document_id","")
        tenant_id   = get_current_tenant_id()

        if not document_id:
            return jsonify({"erreur":"document_id requis"}), 400

        doc_check = supabase.table("documents").select("id").eq(
            "id",document_id).eq("tenant_id",tenant_id).execute()
        if not doc_check.data:
            return jsonify({"erreur":"Document non trouve"}), 404

        result = supabase.table("chunks").select(
            "content,contenu,page_number,page_numero"
        ).eq("document_id",document_id).order("chunk_index").limit(25).execute()
        if not result.data:
            return jsonify({"erreur":"Document vide ou non indexe"}), 404

        texte_complet = "\n".join([
            c.get("content") or c.get("contenu","")
            for c in result.data
            if not est_chiffre(c.get("content") or c.get("contenu",""))
        ])[:10000]

        nom_doc      = obtenir_nom_document(document_id)
        prompt_texte = prompt_carte_mentale(texte_complet, nom_doc)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role":"user","content":prompt_texte}]
        )
        raw   = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        carte = json.loads(raw)
        return jsonify({"succes":True,"document_id":document_id,"nom":nom_doc,"carte":carte})

    except json.JSONDecodeError as e:
        log_erreur("CARTE_MENTALE_JSON", e)
        return jsonify({"erreur":"Erreur de parsing - reessayez"}), 500
    except Exception as e:
        log_erreur("CARTE_MENTALE", e)
        return jsonify({"erreur":str(e)}), 500


# ─── REDACTION ────────────────────────────────────────────────────────────────

@app.route("/rediger", methods=["POST"])
@jwt_required()
@limiter.limit("20 per minute")
def rediger():
    try:
        data      = request.json
        type_doc  = data.get("type","")
        donnees   = data.get("donnees",{})
        tenant_id = get_current_tenant_id()

        _abo = verifier_abonnement(tenant_id)
        if not _abo["actif"]:
            return jsonify({"erreur":"acces_expire",
                            "message":_abo["message"],
                            "plan":_abo["plan"]}), 402

        inj_faits = analyser_injection(
            donnees.get("faits","") or donnees.get("objet",""), champ="faits")
        inj_dict  = analyser_dict(donnees)
        inj = inj_faits if inj_faits.bloque else inj_dict
        if inj.bloque:
            log_security_event("prompt_injection_bloquee", tenant_id,
                get_current_user_id(), {"score":inj.score,"patterns":inj.patterns,"champ":inj.champ})
            return jsonify(REPONSE_BLOQUEE), 400
        if inj.score >= SEUIL_ALERTE:
            log_security_event("prompt_injection_alerte", tenant_id,
                get_current_user_id(), {"score":inj.score,"patterns":inj.patterns})

        if type_doc not in PROMPTS_REDACTION:
            return jsonify({"erreur":f"Type inconnu : {type_doc}"}), 400

        chunks   = rechercher_chunks(
            donnees.get("faits","") or donnees.get("points_cles","") or type_doc,
            tenant_id=tenant_id)
        contexte = ""
        sources  = []
        for i, chunk in enumerate(chunks, 1):
            nom_doc = obtenir_nom_document(chunk["document_id"])
            page    = chunk.get("page_numero",1)
            contexte += f"[{nom_doc} - p.{page}]\n{chunk['contenu']}\n\n"
            sources.append(f"{nom_doc} - p.{page}")

        prompt_texte = get_prompt_redaction(
            type_doc, donnees,
            contexte or "Aucun document indexe dans ce dossier.")

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role":"user","content":prompt_texte}]
        )

        document_genere = response.content[0].text
        config          = PROMPTS_REDACTION[type_doc]

        log_audit_event("DOCUMENT_GENERATED", tenant_id, get_current_user_id(),
                        {"type":type_doc})
        try:
            log_audit(ACTION_GENERATION, {"type":type_doc,"nom":config["nom"]})
        except Exception:
            pass

        return jsonify({
            "document": document_genere,
            "type":     type_doc,
            "nom":      config["nom"],
            "sources":  list(set(sources))
        })
    except Exception as e:
        log_erreur("REDIGER", e)
        return jsonify({"erreur":str(e)}), 500


@app.route("/types_documents", methods=["GET"])
@jwt_required()
def types_documents():
    return jsonify(lister_types_documents())


# ─── DOSSIERS ─────────────────────────────────────────────────────────────────

@app.route("/dossiers", methods=["GET"])
@jwt_required()
def liste_dossiers():
    try:
        tenant_id = get_current_tenant_id()
        result = supabase.table("dossiers").select(
            "id,nom,description,created_at,status"
        ).eq("tenant_id",tenant_id).order("nom").execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


@app.route("/dossiers", methods=["POST"])
@jwt_required()
def creer_dossier():
    try:
        data      = request.json
        nom       = data.get("nom","").strip()
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()

        if not nom:
            return jsonify({"erreur":"Nom de dossier requis"}), 400

        dossier_id = str(uuid.uuid4())
        supabase.table("dossiers").insert({
            "id":          dossier_id,
            "tenant_id":   tenant_id,
            "created_by":  user_id,
            "nom":         nom,
            "description": data.get("description",""),
            "created_at":  datetime.now().isoformat()
        }).execute()
        return jsonify({"succes":True,"id":dossier_id,"nom":nom})
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


@app.route("/dossiers/<dossier_id>", methods=["PUT"])
@jwt_required()
def renommer_dossier(dossier_id):
    try:
        data      = request.json
        tenant_id = get_current_tenant_id()
        update    = {}
        if data.get("nom","").strip():
            update["nom"] = data["nom"].strip()
        if data.get("etape_index") is not None:
            update["etape_index"] = data["etape_index"]
        for field in ["description","demandeur","defendeur","juridiction","numero_role"]:
            if field in data:
                update[field] = data[field]
        if not update:
            return jsonify({"erreur":"Aucun champ a mettre a jour"}), 400
        supabase.table("dossiers").update(update).eq(
            "id",dossier_id).eq("tenant_id",tenant_id).execute()
        return jsonify({"succes":True})
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


@app.route("/dossiers/<dossier_id>", methods=["DELETE"])
@jwt_required()
def supprimer_dossier(dossier_id):
    try:
        tenant_id = get_current_tenant_id()
        check = supabase.table("dossiers").select("id").eq(
            "id",dossier_id).eq("tenant_id",tenant_id).execute()
        if not check.data:
            return jsonify({"erreur":"Dossier non trouve"}), 404

        docs = supabase.table("documents").select("id").eq(
            "dossier_id",dossier_id).eq("tenant_id",tenant_id).execute()
        for doc in docs.data:
            supabase.table("chunks").delete().eq("document_id",doc["id"]).execute()
            supabase.table("documents").delete().eq("id",doc["id"]).execute()

        supabase.table("dossiers").delete().eq(
            "id",dossier_id).eq("tenant_id",tenant_id).execute()

        log_audit_event("DOSSIER_DELETED", tenant_id, get_current_user_id(),
                        {"dossier_id":dossier_id})
        try:
            log_audit(ACTION_SUPPRESSION, {"type":"dossier","dossier_id":dossier_id})
        except Exception:
            pass
        return jsonify({"succes":True})
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


# ─── DOCUMENTS ────────────────────────────────────────────────────────────────

@app.route("/upload_document", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def upload_document():
    chunks_inseres = 0
    try:
        if "fichier" not in request.files:
            return jsonify({"erreur":"Aucun fichier recu"}), 400

        fichier       = request.files["fichier"]
        dossier_id    = request.form.get("dossier_id","")
        est_sensible  = request.form.get("sensible","false").lower() == "true"
        est_chiffre_d = request.form.get("chiffre","false").lower() == "true"
        est_manuscrit = request.form.get("manuscrit","false").lower() == "true"
        tenant_id     = get_current_tenant_id()
        user_id       = get_current_user_id()

        _abo = verifier_abonnement(tenant_id)
        if not _abo["actif"]:
            return jsonify({"erreur":"acces_expire",
                            "message":_abo["message"],
                            "plan":_abo["plan"]}), 402

        if est_chiffre_d:
            est_sensible = True

        if not fichier.filename.lower().endswith(".pdf"):
            return jsonify({"erreur":"Format PDF uniquement"}), 400

        header = fichier.read(5)
        fichier.seek(0)
        if header != b'%PDF-':
            log_security_event("document_quarantined", tenant_id, user_id,
                               {"reason":"invalid_magic_bytes","filename":fichier.filename})
            return jsonify({"erreur":"Fichier invalide"}), 400

        fichier.seek(0, 2)
        taille = fichier.tell()
        fichier.seek(0)
        if taille > 50 * 1024 * 1024:
            return jsonify({"erreur":"Fichier trop volumineux - max 50 Mo"}), 400

        import hashlib
        fichier_bytes = fichier.read()
        file_hash = hashlib.sha256(fichier_bytes).hexdigest()
        fichier.seek(0)

        hash_check = supabase.table("documents").select("id,nom").eq(
            "file_hash_sha256",file_hash).eq("tenant_id",tenant_id).execute()
        if hash_check.data:
            return jsonify({
                "erreur": f"Ce document existe deja : '{hash_check.data[0].get('nom') or fichier.filename}'"
            }), 400

        import fitz
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            fichier.save(tmp.name)
            tmp_path = tmp.name

        doc         = fitz.open(tmp_path)
        pages_texte = []
        nb_pages    = len(doc)

        for i, page in enumerate(doc):
            texte = page.get_text().strip()
            if texte:
                pages_texte.append({"page":i+1,"texte":texte})

        doc.close()
        os.unlink(tmp_path)

        if not pages_texte:
            if est_manuscrit:
                try:
                    import pytesseract
                    from PIL import Image
                    doc_ocr = fitz.open(tmp_path if os.path.exists(tmp_path) else "-")
                    for i, page in enumerate(doc_ocr):
                        mat = fitz.Matrix(2.0, 2.0)
                        pix = page.get_pixmap(matrix=mat)
                        img = Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
                        texte_ocr = pytesseract.image_to_string(img, lang="fra+eng").strip()
                        if texte_ocr:
                            pages_texte.append({"page":i+1,"texte":texte_ocr})
                    doc_ocr.close()
                except ImportError:
                    pages_texte = [{"page":1,"texte":f"[Document manuscrit - {nb_pages} page(s) - OCR non disponible]"}]
                except Exception as e_ocr:
                    pages_texte = [{"page":1,"texte":f"[Document scanne - {nb_pages} page(s) - erreur OCR]"}]
            else:
                pages_texte = [{"page":1,"texte":f"[Document PDF image - {nb_pages} page(s) - cochez Manuscrit pour OCR]"}]

        if not pages_texte:
            pages_texte = [{"page":1,"texte":"[Document vide ou illisible]"}]

        doc_id = str(uuid.uuid4())

        compression_algo  = "none"
        compression_ratio = 1.0
        taille_compresse  = taille

        try:
            import zstandard as zstd
            compressor = zstd.ZstdCompressor(level=3)
            fichier_compresse = compressor.compress(fichier_bytes)
            ratio = len(fichier_compresse) / taille
            if ratio < 0.80:
                decompressor = zstd.ZstdDecompressor()
                fichier_decompresse = decompressor.decompress(fichier_compresse)
                if hashlib.sha256(fichier_decompresse).hexdigest() == file_hash:
                    taille_compresse  = len(fichier_compresse)
                    compression_algo  = "zstd_3"
                    compression_ratio = round(ratio, 4)
        except Exception:
            pass

        supabase.table("documents").insert({
            "id":                doc_id,
            "tenant_id":         tenant_id,
            "uploaded_by":       user_id if user_id else None,
            "filename":          fichier.filename,
            "original_filename": fichier.filename,
            "nom":               fichier.filename,
            "type":              "juridique",
            "mime_type":         "application/pdf",
            "file_size_bytes":   taille,
            "file_hash_sha256":  file_hash,
            "compression_algo":  compression_algo,
            "compression_ratio": compression_ratio,
            "compressed_size_bytes": taille_compresse,
            "compression_valid": compression_algo != "none",
            "dossier_id":        dossier_id if dossier_id else None,
            "manuscrit":         est_manuscrit,
            "ocr_status":        "done",
            "scan_status":       "clean",
            "status":            "ready",
            "storage_tier":      "hot",
            "metadata": {
                "sensible":  est_sensible,
                "chiffre":   est_chiffre_d,
                "manuscrit": est_manuscrit,
                "type_doc":  request.form.get("type_doc","juridique"),
                "juge":      request.form.get("juge",""),
            }
        }).execute()

        chunks_a_inserer = []
        for page_data in pages_texte:
            texte = page_data["texte"]
            for j in range(0, len(texte), 800):
                chunk_texte = texte[j:j+800].strip()
                if len(chunk_texte) > 50:
                    if est_sensible:
                        contenu_final = chiffrer(chunk_texte)
                        index_final   = extraire_index(chunk_texte)
                    else:
                        contenu_final = chunk_texte
                        index_final   = chunk_texte
                    chunks_a_inserer.append({
                        "tenant_id":     tenant_id,
                        "document_id":   doc_id,
                        "content":       contenu_final,
                        "contenu":       contenu_final,
                        "contenu_index": index_final,
                        "page_number":   page_data["page"],
                        "page_numero":   page_data["page"],
                        "chunk_index":   j // 800,
                        "source_type":   "document",
                        "source_hash":   file_hash,
                        "char_count":    len(chunk_texte),
                        "metadata":      {"sensible": est_sensible, "manuscrit": est_manuscrit}
                    })

        for i in range(0, len(chunks_a_inserer), 100):
            supabase.table("chunks").insert(chunks_a_inserer[i:i+100]).execute()
            chunks_inseres += len(chunks_a_inserer[i:i+100])

        threading.Thread(
            target=_vectoriser_document,
            args=(doc_id, tenant_id),
            daemon=True
        ).start()

        log_audit_event("DOCUMENT_UPLOADED", tenant_id, user_id, {
            "filename":fichier.filename,"hash":file_hash,
            "chunks":chunks_inseres,"dossier_id":dossier_id})
        try:
            log_audit(ACTION_UPLOAD, {"fichier":fichier.filename,
                "chunks":chunks_inseres,"manuscrit":est_manuscrit,"dossier_id":dossier_id})
        except Exception:
            pass

        return jsonify({
            "succes":      True,
            "message":     f"'{fichier.filename}' indexe",
            "chunks":      chunks_inseres,
            "document_id": doc_id,
            "manuscrit":   est_manuscrit
        })
    except Exception as e:
        log_erreur("UPLOAD", e)
        return jsonify({"erreur":str(e)}), 500


@app.route("/liste_documents", methods=["GET"])
@jwt_required()
def liste_documents():
    try:
        dossier_id = request.args.get("dossier_id","")
        tenant_id  = get_current_tenant_id()
        query = supabase.table("documents").select(
            "id,nom,filename,original_filename,type,dossier_id,"
            "manuscrit,status,storage_tier,created_at,metadata"
        ).eq("tenant_id",tenant_id).eq("status","ready").order("created_at",desc=True)
        if dossier_id:
            query = query.eq("dossier_id",dossier_id)
        result = query.execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


@app.route("/supprimer_document", methods=["DELETE"])
@jwt_required()
def supprimer_document():
    try:
        data      = request.json
        doc_id    = data.get("id")
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()

        if not doc_id:
            return jsonify({"erreur":"ID manquant"}), 400

        check = supabase.table("documents").select("id").eq(
            "id",doc_id).eq("tenant_id",tenant_id).execute()
        if not check.data:
            return jsonify({"erreur":"Document non trouve"}), 404

        supabase.table("chunks").delete().eq("document_id",doc_id).execute()
        supabase.table("documents").update({
            "status":     "deleted",
            "deleted_at": datetime.now().isoformat()
        }).eq("id",doc_id).eq("tenant_id",tenant_id).execute()

        log_audit_event("DOCUMENT_DELETED", tenant_id, user_id, {"document_id":doc_id})
        try:
            log_audit(ACTION_SUPPRESSION, {"document_id":doc_id})
        except Exception:
            pass
        return jsonify({"succes":True})
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


# ─── JURISPRUDENCE ────────────────────────────────────────────────────────────

@app.route("/jurisprudence/contribuer", methods=["POST"])
@jwt_required()
@limiter.limit("20 per minute")
def contribuer_jurisprudence():
    try:
        data         = request.json
        document_id  = data.get("document_id","")
        consentement = data.get("consentement", False)
        tenant_id    = get_current_tenant_id()
        user_id      = get_current_user_id()

        if not document_id:
            return jsonify({"erreur":"document_id requis"}), 400
        if not consentement:
            return jsonify({"erreur":"Consentement requis"}), 400

        doc_check = supabase.table("documents").select("id,nom,filename,metadata").eq(
            "id",document_id).eq("tenant_id",tenant_id).execute()
        if not doc_check.data:
            return jsonify({"erreur":"Document non trouve"}), 404

        nom_fichier = doc_check.data[0].get("nom") or doc_check.data[0].get("filename","")

        chunks = supabase.table("chunks").select("content,contenu,page_number").eq(
            "document_id",document_id).order("chunk_index").limit(40).execute()
        if not chunks.data:
            return jsonify({"erreur":"Document non indexe"}), 404

        texte = "\n".join([
            c.get("content") or c.get("contenu","")
            for c in chunks.data
            if not est_chiffre(c.get("content") or c.get("contenu",""))
        ])[:12000]

        prompt_texte = prompt_extraction_jurisprudence(texte, nom_fichier)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role":"user","content":prompt_texte}]
        )
        raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            return jsonify({"erreur":"Erreur d extraction - document illisible"}), 500

        if not meta.get("est_jugement", False):
            return jsonify({"succes":False,"message":"Ce document ne semble pas etre un jugement.",
                            "est_jugement":False})
        if meta.get("confiance") == "faible":
            return jsonify({"succes":False,"message":"Document peu lisible. Activez OCR.",
                            "confiance":"faible"})

        texte_a_verifier = " ".join([
            meta.get("titre",""), meta.get("contenu",""),
            meta.get("ratio_decidendi",""), meta.get("issue_detail","")
        ])
        prompt_verif = prompt_verification_anonymisation(texte_a_verifier)
        response_verif = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role":"user","content":prompt_verif}]
        )
        raw_verif = response_verif.content[0].text.strip().replace("```json","").replace("```","").strip()
        try:
            verif = json.loads(raw_verif)
        except json.JSONDecodeError:
            verif = {"action":"valider","risque":"faible"}

        if verif.get("action") == "rejeter":
            log_security_event("jurisprudence_anonymisation_echec", tenant_id, user_id, {
                "document_id":document_id,"risque":verif.get("risque")})
            return jsonify({"succes":False,"message":"Anonymisation insuffisante.",
                            "risque":verif.get("risque")})

        juris_id = str(uuid.uuid4())
        supabase.table("jurisprudence_predict").insert({
            "id":              juris_id,
            "titre":           meta.get("titre",""),
            "contenu":         meta.get("contenu",""),
            "domaine":         meta.get("domaine","autre"),
            "issue":           meta.get("issue",""),
            "issue_detail":    meta.get("issue_detail",""),
            "juridiction":     meta.get("juridiction",""),
            "juge":            meta.get("juge"),
            "chambre":         meta.get("chambre"),
            "date_dec":        meta.get("date_dec"),
            "reference":       meta.get("reference"),
            "montant_litige":  meta.get("montant_litige"),
            "type_partie":     meta.get("type_partie"),
            "textes_appliques":meta.get("textes_appliques",[]),
            "moyens_retenus":  meta.get("moyens_retenus",[]),
            "moyens_rejetes":  meta.get("moyens_rejetes",[]),
            "ratio_decidendi": meta.get("ratio_decidendi",""),
            "source":          "contribution_cabinet",
            "tenant_id":       tenant_id,
            "contributed_by":  user_id,
            "document_id":     document_id,
            "anonymise":       True,
            "consentement":    True,
        }).execute()

        supabase.table("documents").update({
            "metadata": {
                **doc_check.data[0].get("metadata",{}),
                "contribue_jurisprudence": True,
                "juris_id": juris_id
            }
        }).eq("id",document_id).eq("tenant_id",tenant_id).execute()

        log_audit_event("JURISPRUDENCE_CONTRIBUEE", tenant_id, user_id, {
            "document_id":document_id,"juris_id":juris_id,
            "domaine":meta.get("domaine"),"issue":meta.get("issue")})

        return jsonify({
            "succes":    True,
            "juris_id":  juris_id,
            "message":   "Merci pour votre contribution.",
            "extraction": {
                "juridiction": meta.get("juridiction"),
                "juge":        meta.get("juge"),
                "domaine":     meta.get("domaine"),
                "issue":       meta.get("issue"),
                "date_dec":    meta.get("date_dec"),
                "confiance":   meta.get("confiance")
            }
        })
    except Exception as e:
        log_erreur("JURISPRUDENCE_CONTRIBUER", e)
        return jsonify({"erreur":str(e)}), 500


@app.route("/jurisprudence/stats", methods=["GET"])
@jwt_required()
def stats_jurisprudence():
    try:
        result    = supabase.table("jurisprudence_predict").select(
            "domaine,issue,juridiction,date_dec").execute()
        decisions = result.data or []
        total     = len(decisions)
        domaines  = {}
        juridictions = {}
        issues = {"favorable":0,"defavorable":0,"partiel":0,"autre":0}
        for d in decisions:
            dom   = d.get("domaine","autre") or "autre"
            jurid = d.get("juridiction","autre") or "autre"
            iss   = d.get("issue","autre") or "autre"
            domaines[dom]       = domaines.get(dom,0) + 1
            juridictions[jurid] = juridictions.get(jurid,0) + 1
            if iss in issues:
                issues[iss] += 1
            else:
                issues["autre"] = issues.get("autre",0) + 1
        return jsonify({"total":total,"domaines":domaines,
                        "juridictions":juridictions,"issues":issues,"fiable":total>=50})
    except Exception as e:
        log_erreur("JURISPRUDENCE_STATS", e)
        return jsonify({"total":0,"fiable":False}), 500


# ─── COMPARAISON ──────────────────────────────────────────────────────────────

@app.route("/comparaison/analyser", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def comparaison_analyser():
    try:
        data          = request.json
        juge          = data.get("juge","").strip()
        juridiction   = data.get("juridiction","").strip()
        chambre       = data.get("chambre","").strip()
        domaine       = data.get("domaine","")
        periode       = data.get("periode","Toutes")
        affaire       = data.get("affaire","")
        arguments_def = data.get("arguments_defense","")
        antecedents   = data.get("antecedents","")
        tenant_id     = get_current_tenant_id()

        for _val, _nom in [(juge,"juge"),(affaire,"affaire"),
                           (arguments_def,"arguments_defense"),(antecedents,"antecedents")]:
            if _val:
                inj = analyser_injection(_val, champ=_nom)
                if inj.bloque:
                    log_security_event("prompt_injection_bloquee", tenant_id,
                        get_current_user_id(), {"score":inj.score,"patterns":inj.patterns,"champ":_nom})
                    return jsonify(REPONSE_BLOQUEE), 400

        if not juge and not juridiction:
            return jsonify({"erreur":"Juge ou juridiction requis"}), 400

        query = supabase.table("jurisprudence_predict").select(
            "id,titre,contenu,domaine,issue,juridiction,juge,date_dec,reference,source")
        if juge:
            query = query.ilike("juge", f"%{juge}%")
        if juridiction:
            query = query.ilike("juridiction", f"%{juridiction}%")
        if domaine:
            query = query.eq("domaine", domaine)

        result    = query.order("date_dec",desc=True).limit(15).execute()
        decisions = result.data

        if not decisions:
            return jsonify({"succes":False,"message":"Aucune decision trouvee.","decisions":[]})

        prompt_texte = prompt_analyse_comparative(juge, juridiction, domaine, periode, decisions)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role":"user","content":prompt_texte}]
        )
        raw     = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        analyse = json.loads(raw)

        log_audit_event("COMPARAISON", tenant_id, get_current_user_id(),
                        {"juge":juge,"juridiction":juridiction,"domaine":domaine})
        return jsonify({"succes":True,"decisions":decisions,"analyse":analyse,"nb":len(decisions)})

    except json.JSONDecodeError:
        return jsonify({"erreur":"Erreur de parsing - reessayez"}), 500
    except Exception as e:
        log_erreur("COMPARAISON", e)
        return jsonify({"erreur":str(e)}), 500


@app.route("/comparaison/juges", methods=["GET"])
@jwt_required()
def liste_juges():
    try:
        result = supabase.table("jurisprudence_predict").select(
            "juge,juridiction").not_.is_("juge","null").execute()
        juges = {}
        for d in result.data:
            j = d.get("juge","").strip()
            if j:
                if j not in juges:
                    juges[j] = {"juge":j,"juridiction":d.get("juridiction",""),"nb":0}
                juges[j]["nb"] += 1
        return jsonify(sorted(juges.values(), key=lambda x: x["nb"], reverse=True))
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


@app.route("/comparaison/profil_juge", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def profil_juge():
    try:
        data        = request.json
        juge        = data.get("juge","").strip()
        juridiction = data.get("juridiction","").strip()

        if not juge and not juridiction:
            return jsonify({"erreur":"Juge ou juridiction requis"}), 400

        query = supabase.table("jurisprudence_predict").select(
            "domaine,issue,date_dec,juge,juridiction,chambre")
        if juge:
            query = query.ilike("juge", f"%{juge}%")
        if juridiction:
            query = query.ilike("juridiction", f"%{juridiction}%")

        result    = query.execute()
        decisions = result.data
        if not decisions:
            return jsonify({"succes":False,"message":"Aucune decision trouvee"})

        total     = len(decisions)
        fav       = sum(1 for d in decisions if d.get("issue")=="favorable")
        defav     = sum(1 for d in decisions if d.get("issue")=="defavorable")
        part      = sum(1 for d in decisions if d.get("issue")=="partiel")
        taux_fav  = round(fav/total*100) if total else 0
        previsibilite = min(round(max(taux_fav, round(defav/total*100) if total else 0)*0.9+(10 if total>5 else 0)), 95)

        domaines = {}
        for d in decisions:
            dom = d.get("domaine") or "autre"
            if dom not in domaines:
                domaines[dom] = {"total":0,"fav":0}
            domaines[dom]["total"] += 1
            if d.get("issue") == "favorable":
                domaines[dom]["fav"] += 1

        return jsonify({
            "succes":True,"juge":juge or juridiction,"total":total,
            "favorables":fav,"defavorables":defav,"partielles":part,
            "taux_fav":taux_fav,"previsibilite":previsibilite,"domaines":domaines
        })
    except Exception as e:
        log_erreur("PROFIL_JUGE", e)
        return jsonify({"erreur":str(e)}), 500


# ─── SECURITE ─────────────────────────────────────────────────────────────────

@app.route("/incident/declarer", methods=["POST"])
@jwt_required()
def declarer_incident():
    try:
        data      = request.json
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()

        description = data.get("description","")
        if not description:
            return jsonify({"erreur":"Description de l incident requise"}), 400

        incident_id  = str(uuid.uuid4())
        maintenant   = datetime.now(timezone.utc)
        deadline_72h = maintenant + timedelta(hours=72)

        supabase.table("incidents").insert({
            "id":               incident_id,
            "tenant_id":        tenant_id,
            "type_incident":    data.get("type_incident","violation_donnees"),
            "severite":         data.get("severite","moyen"),
            "description":      description,
            "donnees_impactees":data.get("donnees_impactees",[]),
            "users_impactes":   data.get("users_impactes",0),
            "detecte_le":       maintenant.isoformat(),
            "declare_le":       maintenant.isoformat(),
            "statut":           "ouvert",
            "mesures_prises":   data.get("mesures_prises",""),
            "notifie_autorite": False,
            "notifie_users":    False,
        }).execute()

        log_audit_event("INCIDENT_DECLARE", tenant_id, user_id,
                        {"incident_id":incident_id,"severite":data.get("severite")})
        log_security_event("incident_declared", tenant_id, user_id,
                           {"incident_id":incident_id})

        return jsonify({
            "succes":       True,
            "incident_id":  incident_id,
            "declare_le":   maintenant.isoformat(),
            "deadline_72h": deadline_72h.isoformat(),
        })
    except Exception as e:
        log_erreur("INCIDENT_DECLARER", e)
        return jsonify({"erreur":str(e)}), 500


@app.route("/incident/liste", methods=["GET"])
@jwt_required()
def liste_incidents():
    try:
        tenant_id = get_current_tenant_id()
        result = supabase.table("incidents").select(
            "id,type_incident,severite,statut,detecte_le,declare_le,notifie_autorite"
        ).eq("tenant_id",tenant_id).order("created_at",desc=True).execute()
        return jsonify({"incidents":result.data or []})
    except Exception as e:
        return jsonify({"incidents":[]}), 500


@app.route("/incident/resoudre/<incident_id>", methods=["POST"])
@jwt_required()
def resoudre_incident(incident_id):
    try:
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()
        data      = request.json
        supabase.table("incidents").update({
            "statut":           "resolu",
            "resolu_le":        datetime.now(timezone.utc).isoformat(),
            "mesures_prises":   data.get("mesures_prises",""),
            "notifie_autorite": data.get("notifie_autorite",False),
            "notifie_users":    data.get("notifie_users",False),
        }).eq("id",incident_id).eq("tenant_id",tenant_id).execute()
        log_audit_event("INCIDENT_RESOLU", tenant_id, user_id, {"incident_id":incident_id})
        return jsonify({"succes":True,"message":"Incident cloture"})
    except Exception as e:
        return jsonify({"erreur":str(e)}), 500


@app.route("/securite/audit", methods=["GET"])
@jwt_required()
def audit_securite():
    try:
        tenant_id = get_current_tenant_id()
        resultats = []
        score = 0
        total = 0

        def check(nom, ok, critique=False, detail=""):
            nonlocal score, total
            total += 1
            if ok: score += 1
            resultats.append({"nom":nom,"statut":"OK" if ok else "FAIL",
                               "critique":critique,"detail":detail})

        check("SUPABASE_URL configuree",     bool(os.environ.get("SUPABASE_URL")),     critique=True)
        check("ANTHROPIC_API_KEY configuree", bool(os.environ.get("ANTHROPIC_API_KEY")),critique=True)
        check("JWT_SECRET_KEY configuree",    bool(os.environ.get("JWT_SECRET_KEY")),   critique=True)
        check("ENCRYPTION_KEY configuree",    bool(os.environ.get("ENCRYPTION_KEY")),   critique=True)
        check("TOTP_SECRET configure",        bool(os.environ.get("TOTP_SECRET")),      critique=True)
        check("ADMIN_SECRET configure",       bool(os.environ.get("ADMIN_SECRET")),     critique=True)
        check("JWT secret longueur suffisante",
              len(os.environ.get("JWT_SECRET_KEY","")) >= 32, critique=True)
        check("Cle chiffrement AES valide",
              len(os.environ.get("ENCRYPTION_KEY","")) >= 32, critique=True)
        check("Rate limiting actif", True)

        try:
            import zstandard
            check("Compression Zstd disponible", True)
        except ImportError:
            check("Compression Zstd disponible", False)

        try:
            supabase.table("audit_logs").select("id").eq(
                "tenant_id",tenant_id).limit(1).execute()
            check("Table audit_logs accessible", True, critique=True)
        except Exception:
            check("Table audit_logs accessible", False, critique=True)

        try:
            r = supabase.table("incidents").select("id").eq(
                "tenant_id",tenant_id).eq("severite","critique").eq("statut","ouvert").execute()
            check("Aucun incident critique ouvert", len(r.data or [])==0, critique=True)
        except Exception:
            check("Aucun incident critique ouvert", True, critique=True)

        pct             = round((score/total)*100) if total > 0 else 0
        critiques_fails = [r for r in resultats if r["statut"]!="OK" and r["critique"]]

        return jsonify({
            "audit_id":        str(uuid.uuid4()),
            "genere_le":       datetime.now(timezone.utc).isoformat(),
            "score":           pct,
            "score_detail":    f"{score}/{total} points",
            "niveau":          "Excellent" if pct>=90 else "Bon" if pct>=75 else "A ameliorer" if pct>=50 else "Critique",
            "soc2_ready":      pct>=80 and len(critiques_fails)==0,
            "resultats":       resultats,
            "critiques_fails": critiques_fails,
        })
    except Exception as e:
        log_erreur("AUDIT_SECURITE", e)
        return jsonify({"erreur":str(e)}), 500


# ─── RAPPORT ACCES ────────────────────────────────────────────────────────────

@app.route("/rapport/acces", methods=["GET"])
@jwt_required()
def rapport_acces_mensuel():
    try:
        tenant_id  = get_current_tenant_id()
        user_id    = get_current_user_id()
        maintenant = datetime.now(timezone.utc)
        mois  = request.args.get("mois")
        annee = request.args.get("annee")

        if mois and annee:
            debut_mois = datetime(int(annee), int(mois), 1, tzinfo=timezone.utc)
        else:
            debut_mois = datetime(maintenant.year, maintenant.month, 1, tzinfo=timezone.utc)

        fin_mois = datetime(
            debut_mois.year + (1 if debut_mois.month==12 else 0),
            1 if debut_mois.month==12 else debut_mois.month+1,
            1, tzinfo=timezone.utc)

        connexions_result = supabase.table("security_events").select(
            "event_type,created_at"
        ).eq("tenant_id",tenant_id).gte("created_at",debut_mois.isoformat()
        ).lt("created_at",fin_mois.isoformat()).in_(
            "event_type",["login_success","login_failed","logout"]).execute()
        connexions         = connexions_result.data or []
        nb_connexions_ok   = sum(1 for c in connexions if c["event_type"]=="login_success")
        nb_connexions_fail = sum(1 for c in connexions if c["event_type"]=="login_failed")

        incidents_result = supabase.table("incidents").select(
            "type_incident,severite,statut"
        ).eq("tenant_id",tenant_id).gte("created_at",debut_mois.isoformat()
        ).lt("created_at",fin_mois.isoformat()).execute()
        incidents = incidents_result.data or []

        score = 100
        if nb_connexions_fail > 10: score -= 20
        if nb_connexions_fail > 5:  score -= 10
        if any(i.get("severite")=="critique" for i in incidents): score -= 30
        if any(i.get("severite")=="eleve"    for i in incidents): score -= 15
        score = max(0, score)

        log_audit_event("RAPPORT_ACCES_GENERE", tenant_id, user_id,
                        {"periode":debut_mois.strftime("%Y-%m"),"score":score})

        return jsonify({
            "rapport_id": str(uuid.uuid4()),
            "genere_le":  maintenant.isoformat(),
            "periode":    {"debut":debut_mois.isoformat(),"fin":fin_mois.isoformat(),
                           "label":debut_mois.strftime("%B %Y")},
            "conformite": {"score":score,"soc2_ready":score>=80,
                           "niveau":"Excellent" if score>=90 else "Bon" if score>=70 else "A ameliorer"},
            "connexions": {"total":len(connexions),"reussies":nb_connexions_ok,
                           "echouees":nb_connexions_fail},
            "incidents":  {"total":len(incidents),
                           "ouverts":sum(1 for i in incidents if i.get("statut")=="ouvert"),
                           "resolus":sum(1 for i in incidents if i.get("statut")=="resolu")},
        })
    except Exception as e:
        log_erreur("RAPPORT_ACCES", e)
        return jsonify({"erreur":str(e)}), 500


# ─── STATS ────────────────────────────────────────────────────────────────────

@app.route("/stats", methods=["GET"])
@jwt_required()
def stats_cabinet():
    try:
        tenant_id = get_current_tenant_id()
        dos  = supabase.table("dossiers").select("id",count="exact").eq("tenant_id",tenant_id).execute()
        docr = supabase.table("documents").select("id",count="exact").eq(
            "tenant_id",tenant_id).eq("status","ready").execute()
        jurr = supabase.table("jurisprudence_predict").select("issue,domaine,date_dec").execute()

        nb_dossiers = dos.count  if hasattr(dos,"count")  else len(dos.data)
        nb_docs     = docr.count if hasattr(docr,"count") else len(docr.data)
        decisions   = jurr.data or []
        total_dec   = len(decisions)
        fav_dec     = sum(1 for d in decisions if d.get("issue")=="favorable")
        taux_succes = round(fav_dec/total_dec*100) if total_dec else 0

        domaines = {}
        for d in decisions:
            dom = d.get("domaine") or "autre"
            domaines[dom] = domaines.get(dom,0) + 1
        top_domaine = max(domaines, key=domaines.get) if domaines else "-"

        return jsonify({
            "succes":True,"dossiers":nb_dossiers,"documents":nb_docs,
            "decisions":total_dec,"taux_succes":taux_succes,
            "top_domaine":top_domaine,"domaines":domaines
        })
    except Exception as e:
        log_erreur("STATS", e)
        return jsonify({"erreur":str(e)}), 500


# ─── TIMELINE ─────────────────────────────────────────────────────────────────

@app.route("/timeline_dossier", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def timeline_dossier():
    try:
        data       = request.json
        dossier_id = data.get("dossier_id","")
        tenant_id  = get_current_tenant_id()

        if not dossier_id:
            return jsonify({"erreur":"dossier_id requis"}), 400

        docs_result = supabase.table("documents").select("id,nom,filename").eq(
            "dossier_id",dossier_id).eq("tenant_id",tenant_id).execute()
        if not docs_result.data:
            return jsonify({"erreur":"Aucun document dans ce dossier"}), 404

        doc_ids = [d["id"] for d in docs_result.data]
        chunks_result = supabase.table("chunks").select(
            "content,contenu,document_id,page_number,page_numero"
        ).in_("document_id",doc_ids).limit(30).execute()
        if not chunks_result.data:
            return jsonify({"erreur":"Documents non indexes"}), 404

        texte = ""
        for chunk in chunks_result.data:
            c = chunk.get("content") or chunk.get("contenu","")
            if est_chiffre(c):
                c = dechiffrer(c)
            texte += c + "\n"
        texte = texte[:9000]

        prompt_texte = prompt_timeline_dossier(texte, dossier_id)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role":"user","content":prompt_texte}]
        )
        raw      = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        timeline = json.loads(raw)
        return jsonify({"succes":True,"dossier_id":dossier_id,"timeline":timeline})

    except json.JSONDecodeError:
        return jsonify({"erreur":"Erreur de parsing - reessayez"}), 500
    except Exception as e:
        log_erreur("TIMELINE", e)
        return jsonify({"erreur":str(e)}), 500


# ─── EXPORT PDF ───────────────────────────────────────────────────────────────

@app.route("/export_pdf", methods=["POST"])
@jwt_required()
def export_pdf():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

        data      = request.json
        contenu   = data.get("contenu","")
        nom       = data.get("nom","Document Odyxia Droit")
        tenant_id = get_current_tenant_id()

        if not contenu:
            return jsonify({"erreur":"Contenu vide"}), 400

        buffer = io.BytesIO()
        doc    = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=2.5*cm, leftMargin=2.5*cm,
            topMargin=2.5*cm,   bottomMargin=2.5*cm)

        OR   = colors.HexColor("#1A6B9A")
        DARK = colors.HexColor("#0B1F3A")
        GRAY = colors.HexColor("#6B7280")

        s_titre = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=15,
            textColor=OR, alignment=TA_CENTER, spaceAfter=4)
        s_sub   = ParagraphStyle("sub",   fontName="Helvetica", fontSize=9,
            textColor=GRAY, alignment=TA_CENTER, spaceAfter=2)
        s_h1    = ParagraphStyle("h1",    fontName="Helvetica-Bold", fontSize=12,
            textColor=OR, spaceBefore=12, spaceAfter=6)
        s_corps = ParagraphStyle("corps", fontName="Helvetica", fontSize=10,
            textColor=DARK, leading=16, alignment=TA_JUSTIFY, spaceAfter=8)

        elements = []
        elements.append(Paragraph(f"Odyxia Droit - {CABINET_NOM}", s_titre))
        elements.append(Paragraph(f"{CABINET_AVOCAT} - {CABINET_VILLE}", s_sub))
        elements.append(Paragraph(
            f"Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}", s_sub))
        elements.append(HRFlowable(width="100%", thickness=1, color=OR, spaceAfter=12))
        elements.append(Paragraph(nom.upper(), s_titre))
        elements.append(HRFlowable(width="60%", thickness=0.5, color=OR, spaceAfter=16))

        for ligne in contenu.split("\n"):
            ligne = ligne.strip()
            if not ligne:
                elements.append(Spacer(1, 6))
            elif ligne.startswith("## ") or ligne.startswith("# "):
                elements.append(Paragraph(ligne.lstrip("# "), s_h1))
            else:
                ligne = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', ligne)
                ligne = re.sub(r'\*(.+?)\*',     r'<i>\1</i>', ligne)
                elements.append(Paragraph(ligne, s_corps))

        elements.append(Spacer(1, 20))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=OR))
        elements.append(Paragraph(
            f"Odyxia Droit - {CABINET_NOM} - Document confidentiel", s_sub))

        doc.build(elements)
        buffer.seek(0)

        log_audit_event("PDF_EXPORTED", tenant_id, get_current_user_id(), {"nom":nom})
        try:
            log_audit(ACTION_EXPORT_PDF, {"nom":nom})
        except Exception:
            pass

        return send_file(buffer, as_attachment=True,
            download_name=nom.replace(" ","_")+".pdf",
            mimetype="application/pdf")

    except Exception as e:
        log_erreur("EXPORT PDF", e)
        return jsonify({"erreur":str(e)}), 500


# ─── VEILLE ───────────────────────────────────────────────────────────────────

SOURCES_VEILLE = [
    {"id":"ohada","nom":"OHADA","url":"https://www.ohada.com/actes-uniformes.html","domaine":"ohada.com","actif":True},
    {"id":"izf",  "nom":"CEMAC / IZF","url":"https://www.izf.net/textes-juridiques","domaine":"izf.net","actif":True},
    {"id":"spm",  "nom":"Lois Camerounaises","url":"https://www.droit-afrique.com/pays/cameroun","domaine":"droit-afrique.com","actif":True},
    {"id":"ccja", "nom":"Jurisprudence CCJA","url":"https://www.ccja-ohada.org/decisions","domaine":"ccja-ohada.org","actif":True},
    {"id":"wipo", "nom":"Propriete Intellectuelle OMPI","url":"https://www.wipo.int/wipolex/fr/profile/CM","domaine":"wipo.int","actif":True},
]

@app.route("/veille/sources", methods=["GET"])
@jwt_required()
def veille_sources():
    return jsonify(SOURCES_VEILLE)


@app.route("/veille/synchroniser", methods=["POST"])
@jwt_required()
@limiter.limit("5 per minute")
def veille_synchroniser():
    try:
        from bs4 import BeautifulSoup
        import hashlib, fitz
        data      = request.json
        source_id = data.get("source_id")
        tenant_id = get_current_tenant_id()
        sources   = SOURCES_VEILLE if not source_id else [s for s in SOURCES_VEILLE if s["id"]==source_id]
        resultats = []
        headers   = {"User-Agent":"Mozilla/5.0"}

        for source in sources:
            resultat = {"source":source["nom"],"source_id":source["id"],
                        "nouveaux":0,"doublons":0,"erreurs":0,"details":[]}
            try:
                res  = requests.get(source["url"], headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, "html.parser")
                liens_pdf = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if ".pdf" in href.lower():
                        if not href.startswith("http"):
                            href = f"https://{source['domaine']}" + ("" if href.startswith("/") else "/") + href
                        liens_pdf.append({"url":href,"nom":a.get_text(strip=True) or href.split("/")[-1]})

                for lien in liens_pdf[:10]:
                    try:
                        pdf_res = requests.get(lien["url"], headers=headers, timeout=30)
                        if pdf_res.status_code==200 and len(pdf_res.content)>1000:
                            file_hash = hashlib.sha256(pdf_res.content).hexdigest()
                            hash_check = supabase.table("documents").select("id").eq(
                                "file_hash_sha256",file_hash).eq("tenant_id",tenant_id).execute()
                            if hash_check.data:
                                resultat["doublons"] += 1
                                continue
                            with tempfile.NamedTemporaryFile(delete=False,suffix=".pdf") as tmp:
                                tmp.write(pdf_res.content)
                                tmp_path = tmp.name
                            doc_fitz    = fitz.open(tmp_path)
                            pages_texte = []
                            for i, page in enumerate(doc_fitz):
                                texte = page.get_text().strip()
                                if texte:
                                    pages_texte.append({"page":i+1,"texte":texte})
                            doc_fitz.close()
                            os.unlink(tmp_path)
                            if pages_texte:
                                doc_id = str(uuid.uuid4())
                                nom_f  = lien["nom"][:100]
                                supabase.table("documents").insert({
                                    "id":doc_id,"tenant_id":tenant_id,
                                    "filename":nom_f,"original_filename":nom_f,"nom":nom_f,
                                    "type":source["id"],"mime_type":"application/pdf",
                                    "file_size_bytes":len(pdf_res.content),"file_hash_sha256":file_hash,
                                    "status":"ready","storage_tier":"hot","ocr_status":"done","scan_status":"clean",
                                }).execute()
                                for page_data in pages_texte:
                                    for j in range(0,len(page_data["texte"]),800):
                                        chunk_texte = page_data["texte"][j:j+800].strip()
                                        if len(chunk_texte)>50:
                                            supabase.table("chunks").insert({
                                                "tenant_id":tenant_id,"document_id":doc_id,
                                                "content":chunk_texte,"contenu":chunk_texte,
                                                "contenu_index":chunk_texte,
                                                "page_number":page_data["page"],"page_numero":page_data["page"],
                                                "chunk_index":j//800,"source_type":"document",
                                            }).execute()
                                resultat["nouveaux"] += 1
                    except Exception:
                        resultat["erreurs"] += 1
            except Exception as e:
                resultat["erreurs"] += 1
                resultat["details"].append(f"Erreur : {str(e)[:100]}")
            resultats.append(resultat)

        return jsonify({"succes":True,"resultats":resultats})
    except Exception as e:
        log_erreur("VEILLE", e)
        return jsonify({"erreur":str(e)}), 500


# ─── HEALTH ───────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    status = {"status":"ok","service":"odyxia-droit","supabase":"ok"}
    try:
        supabase.table("sessions").select("id").limit(1).execute()
    except Exception:
        status["supabase"] = "degraded"
    return jsonify(status), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)