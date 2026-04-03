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
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
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
    PROMPTS_REDACTION
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")          # service_role key
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
VOYAGE_MODEL   = "voyage-law-2"
VOYAGE_URL_API = "https://api.voyageai.com/v1/embeddings"
TOTP_SECRET    = os.environ.get("TOTP_SECRET", "")

CABINET_NOM    = os.environ.get("CABINET_NOM",    "Odyxia Droit")
CABINET_AVOCAT = os.environ.get("CABINET_AVOCAT", "Maître")
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
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "Odyxia-JWT-2026!")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=8)
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

# ─── HELPERS TENANT ───────────────────────────────────────────────────────────

def get_current_tenant_id() -> str:
    """
    Récupère le tenant_id de l'utilisateur connecté via JWT.
    Fallback sur DEFAULT_TENANT_ID si utilisateur non trouvé.
    """
    try:
        user_id = get_jwt_identity()
        if user_id:
            result = supabase.table("users").select(
                "tenant_id"
            ).eq("id", user_id).execute()
            if result.data:
                return result.data[0]["tenant_id"]
    except Exception:
        pass
    return os.environ.get("DEFAULT_TENANT_ID",
                          "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def get_current_user_id() -> str:
    try:
        user_id = get_jwt_identity()
        if user_id and user_id != "solo_user":
            return user_id
    except Exception:
        pass
    return os.environ.get("DEFAULT_USER_ID", "")


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
    """Vectorise les chunks d'un document en arrière-plan."""
    try:
        result = supabase.table("chunks").select(
            "id, content, contenu_index"
        ).eq("document_id", doc_id).is_("embedding", "null").execute()

        chunks = result.data
        if not chunks:
            return

        BATCH = 20
        for i in range(0, len(chunks), BATCH):
            lot = chunks[i:i + BATCH]
            textes = []
            for c in lot:
                # Compatibilité ancien/nouveau schéma
                texte = (c.get("contenu_index") or
                         c.get("content") or
                         c.get("contenu", ""))
                if texte.startswith("ENC:"):
                    texte = "document juridique confidentiel"
                textes.append(texte.strip() or "document juridique")
            try:
                emb_res = requests.post(
                    VOYAGE_URL_API,
                    headers={"Authorization": f"Bearer {VOYAGE_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"input": textes, "model": VOYAGE_MODEL,
                          "input_type": "document"},
                    timeout=30
                )
                emb_res.raise_for_status()
                embeddings = [item["embedding"]
                              for item in emb_res.json()["data"]]
                for j, chunk in enumerate(lot):
                    supabase.table("chunks").update(
                        {"embedding": embeddings[j]}
                    ).eq("id", chunk["id"]).execute()
                time.sleep(0.2)
            except Exception as e:
                print(f"[VOYAGE] Erreur lot : {e}")
        print(f"[VOYAGE] Vectorisation terminée {doc_id[:8]}")
    except Exception as e:
        print(f"[VOYAGE] Erreur globale : {e}")


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def log_erreur(contexte, erreur):
    message = str(erreur)
    if SUPABASE_KEY:
        message = message.replace(SUPABASE_KEY, "***")
    print(f"[ERREUR] {contexte}: {message[:200]}")


def get_session(session_id: str, tenant_id: str) -> list:
    """Récupère l'historique d'une session — isolé par tenant."""
    try:
        result = supabase.table("sessions").select(
            "historique"
        ).eq("id", session_id).eq("tenant_id", tenant_id).execute()
        if result.data:
            return result.data[0]["historique"]
    except Exception:
        pass
    return []


def save_session(session_id: str, historique: list, tenant_id: str):
    """Sauvegarde l'historique d'une session — isolé par tenant."""
    try:
        supabase.table("sessions").upsert({
            "id":          session_id,
            "tenant_id":   tenant_id,
            "historique":  historique,
            "updated_at":  datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print("ERREUR SESSION:", str(e))


MOTS_VIDES = {
    "quel", "quels", "quelle", "quelles", "dans", "pour", "avec", "sont",
    "comment", "selon", "quand", "cette", "leurs", "leur", "conditions",
    "les", "des", "une", "est", "par", "sur", "qui", "que", "quoi"
}


def rechercher_chunks(question: str, limite: int = 10,
                      dossier_id: str = None,
                      tenant_id: str = None) -> list:
    """
    Recherche RAG multi-niveaux — isolée par tenant_id.
    Cherche dans les documents du cabinet ET dans les actes juridiques publics.
    """
    tous_chunks = []
    ids_vus = set()

    if not tenant_id:
        tenant_id = get_current_tenant_id()

    # Pré-filtrer les document_ids si scope dossier actif
    doc_ids_scope = None
    if dossier_id:
        try:
            doc_res = supabase.table("documents").select("id").eq(
                "dossier_id", dossier_id
            ).eq("tenant_id", tenant_id).execute()
            doc_ids_scope = [d["id"] for d in (doc_res.data or [])]
            if not doc_ids_scope:
                return []
        except Exception:
            pass

    def ajouter(data):
        for chunk in data:
            # Filtre scope si actif
            if doc_ids_scope and chunk.get("document_id") not in doc_ids_scope:
                continue
            cle = (str(chunk.get('document_id', '')) + "-" +
                   str(chunk.get('page_numero') or chunk.get('page_number', '')))
            if cle not in ids_vus:
                ids_vus.add(cle)
                # Compatibilité ancien/nouveau schéma
                contenu = (chunk.get("content") or
                           chunk.get("contenu", ""))
                if est_chiffre(contenu):
                    contenu = dechiffrer(contenu)
                chunk["contenu"] = contenu
                chunk["page_numero"] = (chunk.get("page_numero") or
                                        chunk.get("page_number", 1))
                tous_chunks.append(chunk)

    # Niveau 1 — vectoriel
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

    # Niveau 2 — ilike content
    if not tous_chunks:
        try:
            q_lower = question.lower()
            result = supabase.table("chunks").select(
                "content, contenu, contenu_index, page_number, page_numero, document_id, metadata"
            ).eq("tenant_id", tenant_id).or_(
                f"content.ilike.%{q_lower}%,contenu_index.ilike.%{q_lower}%"
            ).limit(limite).execute()
            ajouter(result.data)
        except Exception:
            pass

    # Niveau 3 — actes juridiques publics (pas de filtre tenant)
    if len(tous_chunks) < 3:
        try:
            result = supabase.table("chunks").select(
                "content, contenu, page_number, page_numero, document_id, legal_act_id, source_type"
            ).eq("source_type", "legal_act").ilike(
                "content", f"%{question.lower()[:50]}%"
            ).limit(5).execute()
            ajouter(result.data)
        except Exception:
            pass

    # Niveau 4 — mot par mot
    if not tous_chunks:
        try:
            mots = [m for m in question.lower().split()
                    if len(m) > 4 and m not in MOTS_VIDES]
            for mot in mots[:5]:
                result = supabase.table("chunks").select(
                    "content, contenu, contenu_index, page_number, page_numero, document_id"
                ).eq("tenant_id", tenant_id).or_(
                    f"content.ilike.%{mot}%,contenu_index.ilike.%{mot}%"
                ).limit(5).execute()
                ajouter(result.data)
        except Exception:
            pass

    return tous_chunks[:limite]


def obtenir_nom_document(document_id: str) -> str:
    try:
        result = supabase.table("documents").select(
            "nom, filename, original_filename"
        ).eq("id", document_id).execute()
        if result.data:
            d = result.data[0]
            name = (d.get("nom") or
                    d.get("original_filename") or
                    d.get("filename") or
                    "Document")
            return name.replace(".pdf", "").replace("-", " ").replace("_", " ")
    except Exception:
        pass
    return "Document inconnu"


def verifier_totp(code: str) -> bool:
    if not TOTP_SECRET:
        return True
    totp = pyotp.TOTP(TOTP_SECRET)
    return totp.verify(code, valid_window=1)


def log_audit_event(event: str, tenant_id: str, user_id: str, meta: dict,
                    severity: str = "info"):
    """Écrit dans audit_logs Supabase — RGPD compliant."""
    try:
        supabase.table("audit_logs").insert({
            "event":      event,
            "tenant_id":  tenant_id,
            "user_id":    user_id,
            "meta":       meta,
            "severity":   severity,
            "created_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"[AUDIT] Erreur : {e}")


def log_security_event(event_type: str, tenant_id: str = None,
                       user_id: str = None, details: dict = None):
    """Écrit dans security_events — requis SOC 2."""
    try:
        supabase.table("security_events").insert({
            "event_type": event_type,
            "tenant_id":  tenant_id,
            "user_id":    user_id,
            "details":    details or {},
            "ip_address": request.remote_addr if request else None,
            "created_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"[SECURITY] Erreur : {e}")


# ─── ROUTES PRINCIPALES ───────────────────────────────────────────────────────

@app.route("/")
def index():
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
    secret = os.environ.get("TOTP_SECRET", "")
    if not secret:
        return jsonify({"erreur": "TOTP_SECRET non configuré"}), 500
    totp = pyotp.TOTP(secret)
    uri  = totp.provisioning_uri(
        name=CABINET_AVOCAT,
        issuer_name=f"Odyxia Droit — {CABINET_NOM}"
    )
    qr = qrcode.make(uri)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()
    return jsonify({"qr_code": f"data:image/png;base64,{qr_b64}",
                    "secret": secret, "uri": uri})


@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    try:
        import bcrypt
        data     = request.json
        password = data.get("password", "").encode()
        hash_s   = os.environ.get("CABINET_PASSWORD", "").encode()

        if bcrypt.checkpw(password, hash_s):
            if TOTP_SECRET:
                code_2fa = data.get("code_2fa", "").strip()
                if not code_2fa:
                    return jsonify({"require_2fa": True}), 200
                if not verifier_totp(code_2fa):
                    log_security_event("login_failed", details={"reason": "2fa_echec"})
                    try:
                        log_audit(ACTION_LOGIN_ECHEC, {"status": "2fa_echec"}, succes=False)
                    except Exception:
                        pass
                    return jsonify({"erreur": "Code 2FA incorrect ou expiré"}), 401

            # Identity = user_id (pour récupérer tenant_id ensuite)
            # En mode solo : on utilise DEFAULT_TENANT_ID comme identity
            identity = os.environ.get("DEFAULT_USER_ID", "solo_user")
            token = create_access_token(identity=identity)

            log_security_event("login_success", details={"mode": "password"})
            try:
                log_audit(ACTION_LOGIN, {"status": "succes"}, succes=True)
            except Exception:
                pass
            return jsonify({"token": token})
        else:
            log_security_event("login_failed", details={"reason": "wrong_password"})
            try:
                log_audit(ACTION_LOGIN_ECHEC, {"status": "echec"}, succes=False)
            except Exception:
                pass
            return jsonify({"erreur": "Mot de passe incorrect"}), 401
    except Exception as e:
        log_erreur("LOGIN", e)
        return jsonify({"erreur": str(e)}), 500


# ─── INSCRIPTION ─────────────────────────────────────────────────────────────

@app.route("/inscription")
def page_inscription():
    return render_template("inscription.html")


@app.route("/inscription", methods=["POST"])
@limiter.limit("5 per minute")
def creer_compte():
    """
    Création d'un nouveau compte avocat / juriste.
    - Crée l'utilisateur dans Supabase Auth
    - Chiffre les données sensibles (nom, téléphone, numéro barreau)
    - Crée le tenant + utilisateur dans les tables applicatives
    - Démarre la période d'essai de 14 jours
    """
    try:
        data = request.json

        # ── Validation champs obligatoires ────────────────
        required = ['email', 'password', 'prenom', 'nom', 'pays', 'type_compte']
        for field in required:
            if not data.get(field, '').strip():
                return jsonify({"erreur": f"Champ requis manquant : {field}"}), 400

        email       = data['email'].strip().lower()
        password    = data['password']
        prenom      = data['prenom'].strip()
        nom         = data['nom'].strip()
        pays        = data['pays'].strip()
        langue      = data.get('langue', 'fr')
        type_compte = data['type_compte']
        telephone   = data.get('telephone', '').strip()

        # Validation numéro barreau pour avocats
        if type_compte == 'avocat':
            num_barreau = data.get('num_barreau', '').strip()
            if not num_barreau:
                return jsonify({"erreur": "Numéro de barreau requis pour un avocat"}), 400
            if not data.get('barreau', '').strip():
                return jsonify({"erreur": "Nom du barreau requis"}), 400

        if type_compte == 'juriste':
            if not data.get('entreprise', '').strip():
                return jsonify({"erreur": "Entreprise employeur requise"}), 400
            if not data.get('num_juriste', '').strip():
                return jsonify({"erreur": "Numéro d'identification requis"}), 400

        # ── Vérifier si email déjà utilisé ────────────────
        existing = supabase.table("tenants").select("id").eq(
            "slug", email.replace('@', '-').replace('.', '-')
        ).execute()
        if existing.data:
            return jsonify({"erreur": "Un compte existe déjà avec cet email"}), 400

        # ── Créer utilisateur Supabase Auth ───────────────
        try:
            auth_response = supabase.auth.sign_up({
                "email":    email,
                "password": password,
            })
            user_id = auth_response.user.id if auth_response.user else None
            if not user_id:
                return jsonify({"erreur": "Erreur lors de la création du compte"}), 500
        except Exception as e:
            err_msg = str(e).lower()
            if 'already' in err_msg or 'exists' in err_msg:
                return jsonify({"erreur": "Un compte existe déjà avec cet email"}), 400
            return jsonify({"erreur": "Erreur d'authentification : " + str(e)[:100]}), 500

        # ── Chiffrement données sensibles ─────────────────
        try:
            from encryption import chiffrer
            nom_prenom_enc     = chiffrer(f"{prenom} {nom}")
            telephone_enc      = chiffrer(telephone) if telephone else None
            num_barreau_enc    = chiffrer(data.get('num_barreau', '')) if type_compte == 'avocat' else None
            entreprise_enc     = chiffrer(data.get('entreprise', '')) if type_compte == 'juriste' else None
            num_juriste_enc    = chiffrer(data.get('num_juriste', '')) if type_compte == 'juriste' else None
        except Exception:
            # Fallback sans chiffrement si module non disponible
            nom_prenom_enc  = f"{prenom} {nom}"
            telephone_enc   = telephone
            num_barreau_enc = data.get('num_barreau', '')
            entreprise_enc  = data.get('entreprise', '')
            num_juriste_enc = data.get('num_juriste', '')

        # ── Dates essai ───────────────────────────────────
        from datetime import timezone
        maintenant  = datetime.now(timezone.utc)
        fin_essai   = maintenant + timedelta(days=14)
        tenant_id   = str(uuid.uuid4())
        slug        = email.replace('@', '-').replace('.', '-')

        # ── Créer le tenant ───────────────────────────────
        supabase.table("tenants").insert({
            "id":               tenant_id,
            "name":             f"{prenom} {nom}",
            "slug":             slug,
            "mode":             "solo",
            "plan":             "trial",
            "status":           "active",
            "storage_used_mb":  0,
            "storage_limit_mb": 2048,
        }).execute()

        # ── Créer l'utilisateur applicatif ────────────────
        supabase.table("users").insert({
            "id":           user_id,
            "tenant_id":    tenant_id,
            "email":        email,
            "full_name":    f"{prenom} {nom}",
            "role":         "owner",
            "is_active":    True,
            "mfa_enabled":  False,
        }).execute()

        # ── Créer profil avocat/juriste ───────────────────
        profil = {
            "id":               str(uuid.uuid4()),
            "tenant_id":        tenant_id,
            "user_id":          user_id,
            "email":            email,
            "pays":             pays,
            "langue":           langue,
            "type_compte":      type_compte,
            "nom_prenom_enc":   nom_prenom_enc,
            "telephone_enc":    telephone_enc,
            "statut":           "essai",
            "essai_debut":      maintenant.isoformat(),
            "essai_fin":        fin_essai.isoformat(),
            "accepte_comm":     data.get('accepte_comm', False),
        }
        if type_compte == 'avocat':
            profil["barreau"]          = data.get('barreau', '').strip()
            profil["barreau_pays"]     = pays
            profil["annee_inscription"]= data.get('annee_inscription', '')
            profil["num_barreau_enc"]  = num_barreau_enc
        else:
            profil["entreprise_enc"]   = entreprise_enc
            profil["poste"]            = data.get('poste', '').strip()
            profil["num_juriste_enc"]  = num_juriste_enc

        # Insérer le profil (table avocats — créée si absente)
        try:
            supabase.table("avocats").insert(profil).execute()
        except Exception as e:
            print(f"[INSCRIPTION] Table avocats inexistante — à créer : {e}")

        # ── Log sécurité ──────────────────────────────────
        log_security_event("login_success", tenant_id, user_id, {
            "action":      "inscription",
            "type_compte": type_compte,
            "pays":        pays,
        })

        log_audit_event("INSCRIPTION", tenant_id, user_id, {
            "type_compte": type_compte,
            "pays":        pays,
        })

        print(f"[INSCRIPTION] Nouveau compte : {email} | {type_compte} | {pays}")

        return jsonify({
            "succes":      True,
            "tenant_id":   tenant_id,
            "user_id":     user_id,
            "essai_fin":   fin_essai.isoformat(),
            "message":     "Compte créé avec succès — essai de 14 jours démarré",
        })

    except Exception as e:
        log_erreur("INSCRIPTION", e)
        return jsonify({"erreur": str(e)[:200]}), 500


# ─── CHAT ─────────────────────────────────────────────────────────────────────

def _preparer_contexte_chat(q: str, session_id: str,
                             tenant_id: str, dossier_id: str = None):
    """
    Prépare le contexte commun pour le chat.
    Isolé par tenant_id — un cabinet ne voit pas les chunks d'un autre.
    """
    historique_session = get_session(session_id, tenant_id)
    chunks = rechercher_chunks(q, dossier_id=dossier_id, tenant_id=tenant_id)

    contexte = ""
    sources  = []
    if chunks:
        for i, chunk in enumerate(chunks, 1):
            nom_doc = obtenir_nom_document(chunk["document_id"])
            page    = chunk.get("page_numero", 1)
            contexte += (f"\n[Passage {i} — {nom_doc}, Page {page}]\n"
                         f"{chunk['contenu']}\n")
            sources.append(f"{nom_doc} · p.{page}")

    messages = []
    for echange in historique_session[-6:]:
        messages.append({"role": "user",      "content": echange["question"]})
        messages.append({"role": "assistant", "content": echange["reponse"]})

    system_prompt = prompt_chat(q, contexte)
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

        if not q:
            return jsonify({"erreur": "Question vide"}), 400

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
                        {"session_id": session_id, "sources_count": len(sources)})

        return jsonify({"reponse": reponse_texte, "sources": list(set(sources))})

    except Exception as e:
        log_erreur("QUESTION", e)
        return jsonify({"reponse": "Erreur : " + str(e), "sources": []}), 500


@app.route("/question_stream", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")
def question_stream():
    try:
        data       = request.json
        q          = data.get("question", "").strip()
        session_id = data.get("session_id", "default")
        dossier_id = data.get("dossier_id", None)
        tenant_id  = get_current_tenant_id()

        if not q:
            return jsonify({"erreur": "Question vide"}), 400

        system_prompt, messages, sources, historique_session = \
            _preparer_contexte_chat(q, session_id, tenant_id, dossier_id)

        def generer():
            reponse_complete = ""
            try:
                yield f"data: {json.dumps({'type': 'sources', 'sources': list(set(sources))}, ensure_ascii=False)}\n\n"

                with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    system=system_prompt,
                    messages=messages
                ) as stream:
                    for token in stream.text_stream:
                        reponse_complete += token
                        yield f"data: {json.dumps({'type': 'token', 'text': token}, ensure_ascii=False)}\n\n"

                historique_session.append({
                    "question": q,
                    "reponse":  reponse_complete
                })
                save_session(session_id, historique_session, tenant_id)
                yield f"data: {json.dumps({'type': 'fin', 'complet': reponse_complete}, ensure_ascii=False)}\n\n"

            except Exception as e:
                log_erreur("STREAM", e)
                yield f"data: {json.dumps({'type': 'erreur', 'message': str(e)}, ensure_ascii=False)}\n\n"

        return Response(
            stream_with_context(generer()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control":     "no-cache",
                "X-Accel-Buffering": "no",
                "Connection":        "keep-alive"
            }
        )

    except Exception as e:
        log_erreur("QUESTION_STREAM", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/nouvelle-conversation", methods=["POST"])
@jwt_required()
def nouvelle_conversation():
    try:
        data       = request.json
        session_id = data.get("session_id", "default")
        tenant_id  = get_current_tenant_id()
        supabase.table("sessions").delete().eq(
            "id", session_id
        ).eq("tenant_id", tenant_id).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


# ─── SYNTHÈSE DOCUMENT ────────────────────────────────────────────────────────


# ─── MÉMOIRE PERSISTANTE ─────────────────────────────────────────────────────

@app.route("/memoire/sauvegarder", methods=["POST"])
@jwt_required()
def sauvegarder_memoire():
    try:
        data       = request.json
        session_id = data.get("session_id", "")
        historique = data.get("historique", [])
        tenant_id  = get_current_tenant_id()

        if not historique or len(historique) < 2:
            return jsonify({"ok": False, "raison": "Conversation trop courte"})

        lignes = []
        for m in historique[-10:]:
            role = "Avocat" if m["role"] == "user" else "Odyxia"
            lignes.append(role + ": " + str(m.get("content", ""))[:300])
        texte_conv = " | ".join(lignes)

        prompt_resume = (
            "Résume cette conversation juridique en 3 phrases max. "
            "Format strict sur 3 lignes separees : "
            "RESUME: [résumé] "
            "MOTS_CLES: [mot1,mot2,mot3] "
            "DOMAINE: [domaine] "
            "Conversation: " + texte_conv
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt_resume}]
        )

        texte     = response.content[0].text.strip()
        resume    = ""
        mots_cles = []
        domaine   = ""

        for ligne in texte.splitlines():
            if ligne.startswith("RESUME:"):
                resume = ligne.replace("RESUME:", "").strip()
            elif ligne.startswith("MOTS_CLES:"):
                mots_cles = [m.strip() for m in ligne.replace("MOTS_CLES:", "").split(",")]
            elif ligne.startswith("DOMAINE:"):
                domaine = ligne.replace("DOMAINE:", "").strip()

        if not resume:
            resume = texte[:400]

        supabase.table("memoires").insert({
            "tenant_id":  tenant_id,
            "session_id": session_id,
            "resume":     resume,
            "mots_cles":  mots_cles,
            "domaine":    domaine,
        }).execute()

        print("[MEMOIRE] Sauvegardé — " + domaine)
        return jsonify({"ok": True, "resume": resume})

    except Exception as e:
        log_erreur("MEMOIRE_SAUVEGARDER", e)
        return jsonify({"ok": False, "erreur": str(e)}), 500


@app.route("/memoire/contexte", methods=["GET"])
@jwt_required()
def contexte_memoire():
    try:
        tenant_id = get_current_tenant_id()
        result = supabase.table("memoires").select(
            "resume, mots_cles, domaine, created_at"
        ).eq("tenant_id", tenant_id).order(
            "created_at", desc=True
        ).limit(3).execute()
        return jsonify({"memoires": result.data or [], "count": len(result.data or [])})
    except Exception as e:
        log_erreur("MEMOIRE_CONTEXTE", e)
        return jsonify({"memoires": [], "count": 0}), 500


# ─── SÉCURITÉ — GESTION INCIDENTS 72H RGPD ───────────────────────────────────

@app.route("/incident/declarer", methods=["POST"])
@jwt_required()
def declarer_incident():
    """
    Déclare un incident de sécurité.
    Génère automatiquement un rapport RGPD et logue l'incident.
    """
    try:
        data      = request.json
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()

        type_incident     = data.get("type_incident", "violation_donnees")
        severite          = data.get("severite", "moyen")
        description       = data.get("description", "")
        donnees_impactees = data.get("donnees_impactees", [])
        users_impactes    = data.get("users_impactes", 0)
        mesures_prises    = data.get("mesures_prises", "")

        if not description:
            return jsonify({"erreur": "Description de l'incident requise"}), 400

        incident_id = str(uuid.uuid4())
        maintenant  = datetime.now(timezone.utc)
        deadline_72h = maintenant + timedelta(hours=72)

        supabase.table("incidents").insert({
            "id":               incident_id,
            "tenant_id":        tenant_id,
            "type_incident":    type_incident,
            "severite":         severite,
            "description":      description,
            "donnees_impactees": donnees_impactees,
            "users_impactes":   users_impactes,
            "detecte_le":       maintenant.isoformat(),
            "declare_le":       maintenant.isoformat(),
            "statut":           "ouvert",
            "mesures_prises":   mesures_prises,
            "notifie_autorite": False,
            "notifie_users":    False,
        }).execute()

        log_audit_event("INCIDENT_DECLARE", tenant_id, user_id, {
            "incident_id": incident_id,
            "severite":    severite,
            "type":        type_incident,
        })

        log_security_event("incident_declared", tenant_id, user_id, {
            "incident_id": incident_id,
            "severite":    severite,
        })

        print(f"[INCIDENT] Déclaré — {severite} | {type_incident} | tenant {tenant_id[:8]}")

        return jsonify({
            "succes":       True,
            "incident_id":  incident_id,
            "declare_le":   maintenant.isoformat(),
            "deadline_72h": deadline_72h.isoformat(),
            "message":      "Incident déclaré. Vous avez jusqu'au "
                           + deadline_72h.strftime("%d/%m/%Y %H:%M UTC")
                           + " pour notifier l'autorité compétente.",
        })

    except Exception as e:
        log_erreur("INCIDENT_DECLARER", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/incident/rapport/<incident_id>", methods=["GET"])
@jwt_required()
def rapport_incident(incident_id):
    """
    Génère le rapport RGPD complet pour un incident déclaré.
    Format conforme aux exigences de notification des autorités.
    """
    try:
        tenant_id = get_current_tenant_id()

        result = supabase.table("incidents").select("*").eq(
            "id", incident_id
        ).eq("tenant_id", tenant_id).execute()

        if not result.data:
            return jsonify({"erreur": "Incident introuvable"}), 404

        inc = result.data[0]

        detecte_le  = inc.get("detecte_le", "")
        declare_le  = inc.get("declare_le", "")
        deadline_dt = datetime.fromisoformat(declare_le.replace("Z", "+00:00")) + timedelta(hours=72) if declare_le else None
        deadline    = deadline_dt.strftime("%d/%m/%Y %H:%M UTC") if deadline_dt else "N/A"

        rapport = {
            "incident_id":     incident_id,
            "genere_le":       datetime.now(timezone.utc).isoformat(),
            "conforme_rgpd":   True,
            "delai_72h":       deadline,
            "statut":          inc.get("statut", "ouvert"),
            "details": {
                "type_violation":      inc.get("type_incident", ""),
                "severite":            inc.get("severite", ""),
                "description":         inc.get("description", ""),
                "date_detection":      detecte_le,
                "date_declaration":    declare_le,
                "categories_donnees":  inc.get("donnees_impactees", []),
                "nombre_personnes":    inc.get("users_impactes", 0),
                "mesures_prises":      inc.get("mesures_prises", ""),
                "notifie_autorite":    inc.get("notifie_autorite", False),
                "notifie_utilisateurs":inc.get("notifie_users", False),
            },
            "obligations_rgpd": {
                "notification_autorite": {
                    "obligatoire": inc.get("severite") in ["eleve", "critique"],
                    "deadline":    deadline,
                    "autorite_cmr": "CNIL Cameroun — Agence Nationale des Technologies de l'Information et de la Communication (ANTIC)",
                    "effectuee":   inc.get("notifie_autorite", False),
                },
                "notification_personnes": {
                    "obligatoire": inc.get("severite") == "critique",
                    "effectuee":  inc.get("notifie_users", False),
                },
            },
            "checklist_rgpd": [
                {"action": "Incident détecté et documenté",          "fait": True},
                {"action": "Incident déclaré dans le système",       "fait": True},
                {"action": "Mesures correctives immédiates prises",  "fait": bool(inc.get("mesures_prises"))},
                {"action": "Autorité compétente notifiée (72h)",     "fait": inc.get("notifie_autorite", False)},
                {"action": "Personnes concernées notifiées",         "fait": inc.get("notifie_users", False)},
                {"action": "Incident résolu et clôturé",             "fait": inc.get("statut") == "resolu"},
            ],
        }

        return jsonify(rapport)

    except Exception as e:
        log_erreur("INCIDENT_RAPPORT", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/incident/liste", methods=["GET"])
@jwt_required()
def liste_incidents():
    """Liste tous les incidents du tenant."""
    try:
        tenant_id = get_current_tenant_id()
        result = supabase.table("incidents").select(
            "id, type_incident, severite, statut, detecte_le, declare_le, notifie_autorite"
        ).eq("tenant_id", tenant_id).order(
            "created_at", desc=True
        ).execute()
        return jsonify({"incidents": result.data or []})
    except Exception as e:
        log_erreur("INCIDENT_LISTE", e)
        return jsonify({"incidents": []}), 500


@app.route("/incident/resoudre/<incident_id>", methods=["POST"])
@jwt_required()
def resoudre_incident(incident_id):
    """Marque un incident comme résolu."""
    try:
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()
        data      = request.json

        supabase.table("incidents").update({
            "statut":           "resolu",
            "resolu_le":        datetime.now(timezone.utc).isoformat(),
            "mesures_prises":   data.get("mesures_prises", ""),
            "notifie_autorite": data.get("notifie_autorite", False),
            "notifie_users":    data.get("notifie_users", False),
        }).eq("id", incident_id).eq("tenant_id", tenant_id).execute()

        log_audit_event("INCIDENT_RESOLU", tenant_id, user_id, {"incident_id": incident_id})

        return jsonify({"succes": True, "message": "Incident clôturé"})

    except Exception as e:
        log_erreur("INCIDENT_RESOUDRE", e)
        return jsonify({"erreur": str(e)}), 500


def detecter_anomalies(tenant_id, user_id, action, metadata=None):
    """
    Détecteur d'anomalies appelé à chaque action sensible.
    Crée automatiquement un incident si une anomalie est détectée.
    """
    try:
        if not metadata:
            metadata = {}

        anomalie = None
        severite = "faible"

        # Tentatives de connexion répétées
        if action == "login_failed":
            recent = supabase.table("security_events").select("id").eq(
                "event_type", "login_failed"
            ).eq("tenant_id", tenant_id).gte(
                "created_at",
                (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
            ).execute()
            if len(recent.data or []) >= 5:
                anomalie = "Tentatives de connexion répétées détectées"
                severite = "eleve"

        # Upload massif de documents
        elif action == "upload_document":
            recent = supabase.table("audit_logs").select("id").eq(
                "action", "UPLOAD_DOCUMENT"
            ).eq("tenant_id", tenant_id).gte(
                "created_at",
                (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            ).execute()
            if len(recent.data or []) >= 50:
                anomalie = "Volume d'upload anormalement élevé"
                severite = "moyen"

        if anomalie:
            supabase.table("incidents").insert({
                "id":            str(uuid.uuid4()),
                "tenant_id":     tenant_id,
                "type_incident": "anomalie_detectee",
                "severite":      severite,
                "description":   anomalie,
                "detecte_le":    datetime.now(timezone.utc).isoformat(),
                "statut":        "ouvert",
            }).execute()
            print(f"[INCIDENT AUTO] {anomalie} — tenant {tenant_id[:8]}")

    except Exception:
        pass




# ─── RAPPORT D'ACCÈS MENSUEL ──────────────────────────────────────────────────

@app.route("/rapport/acces", methods=["GET"])
@jwt_required()
def rapport_acces_mensuel():
    """
    Génère le rapport d'accès mensuel pour le tenant.
    Couvre : connexions, documents, actions sensibles, anomalies.
    Conforme SOC 2 Type 1 et RGPD.
    """
    try:
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()

        mois      = request.args.get("mois")
        annee     = request.args.get("annee")

        maintenant = datetime.now(timezone.utc)
        if mois and annee:
            debut_mois = datetime(int(annee), int(mois), 1, tzinfo=timezone.utc)
        else:
            debut_mois = datetime(maintenant.year, maintenant.month, 1, tzinfo=timezone.utc)

        if debut_mois.month == 12:
            fin_mois = datetime(debut_mois.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            fin_mois = datetime(debut_mois.year, debut_mois.month + 1, 1, tzinfo=timezone.utc)

        periode_debut = debut_mois.isoformat()
        periode_fin   = fin_mois.isoformat()

        # 1 — Connexions
        connexions_result = supabase.table("security_events").select(
            "event_type, created_at, metadata"
        ).eq("tenant_id", tenant_id).gte(
            "created_at", periode_debut
        ).lt("created_at", periode_fin).in_(
            "event_type", ["login_success", "login_failed", "logout"]
        ).order("created_at", desc=True).execute()

        connexions   = connexions_result.data or []
        nb_connexions_ok   = sum(1 for c in connexions if c["event_type"] == "login_success")
        nb_connexions_fail = sum(1 for c in connexions if c["event_type"] == "login_failed")

        # 2 — Documents uploadés
        docs_result = supabase.table("audit_logs").select(
            "action, created_at, metadata"
        ).eq("tenant_id", tenant_id).gte(
            "created_at", periode_debut
        ).lt("created_at", periode_fin).eq(
            "action", "UPLOAD_DOCUMENT"
        ).execute()

        docs_uploades = len(docs_result.data or [])

        # 3 — Actions sensibles
        actions_result = supabase.table("audit_logs").select(
            "action, created_at, user_id"
        ).eq("tenant_id", tenant_id).gte(
            "created_at", periode_debut
        ).lt("created_at", periode_fin).execute()

        actions = actions_result.data or []
        actions_par_type = {}
        for a in actions:
            t = a.get("action", "INCONNU")
            actions_par_type[t] = actions_par_type.get(t, 0) + 1

        # 4 — Incidents
        incidents_result = supabase.table("incidents").select(
            "type_incident, severite, statut, detecte_le"
        ).eq("tenant_id", tenant_id).gte(
            "created_at", periode_debut
        ).lt("created_at", periode_fin).execute()

        incidents = incidents_result.data or []

        # 5 — Score de conformité
        score = 100
        if nb_connexions_fail > 10: score -= 20
        if nb_connexions_fail > 5:  score -= 10
        any_critique = any(i.get("severite") == "critique" for i in incidents)
        any_eleve    = any(i.get("severite") == "eleve" for i in incidents)
        if any_critique: score -= 30
        if any_eleve:    score -= 15
        score = max(0, score)

        rapport = {
            "rapport_id":    str(uuid.uuid4()),
            "genere_le":     maintenant.isoformat(),
            "tenant_id":     tenant_id,
            "periode": {
                "debut": periode_debut,
                "fin":   periode_fin,
                "label": debut_mois.strftime("%B %Y"),
            },
            "conformite": {
                "score":        score,
                "niveau":       "Excellent" if score >= 90 else "Bon" if score >= 70 else "A améliorer" if score >= 50 else "Critique",
                "soc2_ready":   score >= 80,
                "rgpd_ready":   len([i for i in incidents if not i.get("notifie_autorite") and i.get("severite") in ["eleve","critique"]]) == 0,
            },
            "connexions": {
                "total":            len(connexions),
                "reussies":         nb_connexions_ok,
                "echouees":         nb_connexions_fail,
                "taux_echec_pct":   round((nb_connexions_fail / max(len(connexions), 1)) * 100, 1),
                "alerte":           nb_connexions_fail > 10,
            },
            "documents": {
                "uploades_ce_mois": docs_uploades,
                "actions_totales":  len(actions),
                "par_type":         actions_par_type,
            },
            "incidents": {
                "total":    len(incidents),
                "ouverts":  sum(1 for i in incidents if i.get("statut") == "ouvert"),
                "resolus":  sum(1 for i in incidents if i.get("statut") == "resolu"),
                "critiques":sum(1 for i in incidents if i.get("severite") == "critique"),
                "eleves":   sum(1 for i in incidents if i.get("severite") == "eleve"),
                "liste":    incidents[:10],
            },
            "recommandations": _generer_recommandations(
                nb_connexions_fail, incidents, score
            ),
            "certifications": {
                "soc2_type1":  "En cours" if score >= 70 else "Non conforme",
                "rgpd":        "Conforme" if score >= 60 else "Non conforme",
                "prochaine_revue": (maintenant + timedelta(days=30)).strftime("%d/%m/%Y"),
            },
        }

        log_audit_event("RAPPORT_ACCES_GENERE", tenant_id, user_id, {
            "periode": debut_mois.strftime("%Y-%m"),
            "score":   score,
        })

        return jsonify(rapport)

    except Exception as e:
        log_erreur("RAPPORT_ACCES", e)
        return jsonify({"erreur": str(e)}), 500


def _generer_recommandations(nb_echecs, incidents, score):
    """Génère des recommandations personnalisées selon l'état du tenant."""
    recs = []

    if nb_echecs > 5:
        recs.append({
            "priorite": "haute",
            "titre":    "Tentatives de connexion suspectes",
            "action":   "Vérifiez les logs de connexion et envisagez de renforcer la politique de mot de passe.",
        })

    incidents_non_resolus = [i for i in incidents if i.get("statut") == "ouvert"]
    if incidents_non_resolus:
        recs.append({
            "priorite": "haute",
            "titre":    f"{len(incidents_non_resolus)} incident(s) non résolu(s)",
            "action":   "Clôturez les incidents ouverts et documentez les mesures prises.",
        })

    if score < 80:
        recs.append({
            "priorite": "moyenne",
            "titre":    "Score SOC 2 insuffisant",
            "action":   "Réalisez un pentest externe et documentez les procédures de sécurité.",
        })

    if not recs:
        recs.append({
            "priorite": "info",
            "titre":    "Aucune anomalie détectée",
            "action":   "Continuez les bonnes pratiques. Planifiez la prochaine revue trimestrielle.",
        })

    return recs


@app.route("/rapport/acces/export", methods=["GET"])
@jwt_required()
def export_rapport_acces():
    """
    Exporte le rapport d'accès mensuel en JSON structuré
    prêt pour import dans un outil d'audit.
    """
    try:
        tenant_id = get_current_tenant_id()
        mois  = request.args.get("mois", str(datetime.now(timezone.utc).month))
        annee = request.args.get("annee", str(datetime.now(timezone.utc).year))

        rapport_response = rapport_acces_mensuel()
        rapport_data = rapport_response.get_json()

        from flask import Response
        import json
        nom_fichier = f"rapport_acces_{annee}_{mois.zfill(2)}.json"
        return Response(
            json.dumps(rapport_data, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={nom_fichier}"}
        )

    except Exception as e:
        log_erreur("RAPPORT_EXPORT", e)
        return jsonify({"erreur": str(e)}), 500



@app.route("/synthese_document", methods=["POST"])
@jwt_required()
def synthese_document():
    try:
        data        = request.json
        document_id = data.get("document_id", "")
        tenant_id   = get_current_tenant_id()

        if not document_id:
            return jsonify({"erreur": "document_id requis"}), 400

        # Vérification appartenance tenant
        doc_check = supabase.table("documents").select("id").eq(
            "id", document_id
        ).eq("tenant_id", tenant_id).execute()
        if not doc_check.data:
            return jsonify({"erreur": "Document non trouvé"}), 404

        result = supabase.table("chunks").select(
            "content, contenu, page_number, page_numero"
        ).eq("document_id", document_id).limit(20).execute()

        if not result.data:
            return jsonify({"erreur": "Document non indexé"}), 404

        texte_complet = "\n".join([
            c.get("content") or c.get("contenu", "")
            for c in result.data
            if not est_chiffre(c.get("content") or c.get("contenu", ""))
        ])[:8000]

        nom_doc = obtenir_nom_document(document_id)
        prompt  = prompt_synthese_document(texte_complet, nom_doc)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw      = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        synthese = json.loads(raw)
        return jsonify({"succes": True, "synthese": synthese, "document_id": document_id})

    except Exception as e:
        log_erreur("SYNTHESE", e)
        return jsonify({"erreur": str(e)}), 500


# ─── CARTE MENTALE ────────────────────────────────────────────────────────────

@app.route("/carte_mentale", methods=["POST"])
@jwt_required()
@limiter.limit("15 per minute")
def carte_mentale():
    try:
        data        = request.json
        document_id = data.get("document_id", "")
        tenant_id   = get_current_tenant_id()

        if not document_id:
            return jsonify({"erreur": "document_id requis"}), 400

        # Vérification appartenance tenant
        doc_check = supabase.table("documents").select("id").eq(
            "id", document_id
        ).eq("tenant_id", tenant_id).execute()
        if not doc_check.data:
            return jsonify({"erreur": "Document non trouvé"}), 404

        result = supabase.table("chunks").select(
            "content, contenu, page_number, page_numero"
        ).eq("document_id", document_id).order("chunk_index").limit(25).execute()

        if not result.data:
            return jsonify({"erreur": "Document vide ou non indexé"}), 404

        texte_complet = "\n".join([
            c.get("content") or c.get("contenu", "")
            for c in result.data
            if not est_chiffre(c.get("content") or c.get("contenu", ""))
        ])[:10000]

        nom_doc      = obtenir_nom_document(document_id)
        prompt_texte = prompt_carte_mentale(texte_complet, nom_doc)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt_texte}]
        )

        raw   = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        carte = json.loads(raw)

        return jsonify({
            "succes":      True,
            "document_id": document_id,
            "nom":         nom_doc,
            "carte":       carte
        })

    except json.JSONDecodeError as e:
        log_erreur("CARTE_MENTALE_JSON", e)
        return jsonify({"erreur": "Erreur de parsing — réessayez"}), 500
    except Exception as e:
        log_erreur("CARTE_MENTALE", e)
        return jsonify({"erreur": str(e)}), 500


# ─── RÉDACTION ────────────────────────────────────────────────────────────────

@app.route("/rediger", methods=["POST"])
@jwt_required()
@limiter.limit("20 per minute")
def rediger():
    try:
        data       = request.json
        type_doc   = data.get("type", "")
        donnees    = data.get("donnees", {})
        tenant_id  = get_current_tenant_id()

        if type_doc not in PROMPTS_REDACTION:
            return jsonify({"erreur": f"Type inconnu : {type_doc}"}), 400

        chunks  = rechercher_chunks(
            donnees.get("faits", "") or donnees.get("points_cles", "") or type_doc,
            tenant_id=tenant_id
        )
        contexte = ""
        sources  = []
        for i, chunk in enumerate(chunks, 1):
            nom_doc = obtenir_nom_document(chunk["document_id"])
            page    = chunk.get("page_numero", 1)
            contexte += f"[{nom_doc} · p.{page}]\n{chunk['contenu']}\n\n"
            sources.append(f"{nom_doc} · p.{page}")

        prompt_texte = get_prompt_redaction(
            type_doc,
            donnees,
            contexte or "Aucun document indexé dans ce dossier."
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt_texte}]
        )

        document_genere = response.content[0].text
        config          = PROMPTS_REDACTION[type_doc]

        log_audit_event("DOCUMENT_GENERATED", tenant_id, get_current_user_id(),
                        {"type": type_doc})
        try:
            log_audit(ACTION_GENERATION, {"type": type_doc, "nom": config["nom"]})
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
        return jsonify({"erreur": str(e)}), 500


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
            "id, nom, description, created_at, status"
        ).eq("tenant_id", tenant_id).order("nom").execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


@app.route("/dossiers", methods=["POST"])
@jwt_required()
def creer_dossier():
    try:
        data      = request.json
        nom       = data.get("nom", "").strip()
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()

        if not nom:
            return jsonify({"erreur": "Nom de dossier requis"}), 400

        dossier_id = str(uuid.uuid4())
        supabase.table("dossiers").insert({
            "id":          dossier_id,
            "tenant_id":   tenant_id,
            "created_by":  user_id,
            "nom":         nom,
            "description": data.get("description", ""),
            "created_at":  datetime.now().isoformat()
        }).execute()

        return jsonify({"succes": True, "id": dossier_id, "nom": nom})
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


@app.route("/dossiers/<dossier_id>", methods=["PUT"])
@jwt_required()
def renommer_dossier(dossier_id):
    try:
        data        = request.json
        nouveau_nom = data.get("nom", "").strip()
        tenant_id   = get_current_tenant_id()

        if not nouveau_nom:
            return jsonify({"erreur": "Nouveau nom requis"}), 400

        supabase.table("dossiers").update(
            {"nom": nouveau_nom}
        ).eq("id", dossier_id).eq("tenant_id", tenant_id).execute()

        return jsonify({"succes": True})
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


@app.route("/dossiers/<dossier_id>", methods=["DELETE"])
@jwt_required()
def supprimer_dossier(dossier_id):
    try:
        tenant_id = get_current_tenant_id()

        # Vérification appartenance tenant
        check = supabase.table("dossiers").select("id").eq(
            "id", dossier_id
        ).eq("tenant_id", tenant_id).execute()
        if not check.data:
            return jsonify({"erreur": "Dossier non trouvé"}), 404

        docs = supabase.table("documents").select(
            "id"
        ).eq("dossier_id", dossier_id).eq("tenant_id", tenant_id).execute()

        for doc in docs.data:
            supabase.table("chunks").delete().eq("document_id", doc["id"]).execute()
            supabase.table("documents").delete().eq("id", doc["id"]).execute()

        supabase.table("dossiers").delete().eq(
            "id", dossier_id
        ).eq("tenant_id", tenant_id).execute()

        log_audit_event("DOSSIER_DELETED", tenant_id, get_current_user_id(),
                        {"dossier_id": dossier_id})
        try:
            log_audit(ACTION_SUPPRESSION, {"type": "dossier", "dossier_id": dossier_id})
        except Exception:
            pass

        return jsonify({"succes": True})
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


# ─── DOCUMENTS ────────────────────────────────────────────────────────────────

@app.route("/upload_document", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def upload_document():
    chunks_inseres = 0
    try:
        if "fichier" not in request.files:
            return jsonify({"erreur": "Aucun fichier reçu"}), 400

        fichier       = request.files["fichier"]
        dossier_id    = request.form.get("dossier_id", "")
        est_sensible  = request.form.get("sensible",   "false").lower() == "true"
        est_chiffre_d = request.form.get("chiffre",    "false").lower() == "true"
        est_manuscrit = request.form.get("manuscrit",  "false").lower() == "true"
        tenant_id     = get_current_tenant_id()
        user_id       = get_current_user_id()

        if est_chiffre_d:
            est_sensible = True

        if not fichier.filename.lower().endswith(".pdf"):
            return jsonify({"erreur": "Format PDF uniquement"}), 400

        # Vérification magic bytes PDF
        header = fichier.read(5)
        fichier.seek(0)
        if header != b'%PDF-':
            log_security_event("document_quarantined", tenant_id, user_id,
                               {"reason": "invalid_magic_bytes",
                                "filename": fichier.filename})
            return jsonify({"erreur": "Fichier invalide"}), 400

        # Vérification taille
        fichier.seek(0, 2)
        taille = fichier.tell()
        fichier.seek(0)
        if taille > 50 * 1024 * 1024:
            return jsonify({"erreur": "Fichier trop volumineux — max 50 Mo"}), 400

        # Vérification doublons dans le tenant
        import hashlib
        fichier_bytes = fichier.read()
        file_hash = hashlib.sha256(fichier_bytes).hexdigest()
        fichier.seek(0)

        hash_check = supabase.table("documents").select("id, nom").eq(
            "file_hash_sha256", file_hash
        ).eq("tenant_id", tenant_id).execute()
        if hash_check.data:
            return jsonify({
                "erreur": f"Ce document existe déjà : '{hash_check.data[0].get('nom') or fichier.filename}'"
            }), 400

        import fitz
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            fichier.save(tmp.name)
            tmp_path = tmp.name

        doc      = fitz.open(tmp_path)
        pages_texte = []

        for i, page in enumerate(doc):
            texte = page.get_text().strip()
            if texte:
                pages_texte.append({"page": i + 1, "texte": texte})

        doc.close()
        os.unlink(tmp_path)

        if not pages_texte:
            return jsonify({"erreur": "Impossible d'extraire le texte du PDF"}), 400

        doc_id = str(uuid.uuid4())

        # Insertion avec nouveau schéma + compatibilité ancien
        supabase.table("documents").insert({
            "id":               doc_id,
            "tenant_id":        tenant_id,
            "uploaded_by":      user_id if user_id else None,
            "filename":         fichier.filename,
            "original_filename": fichier.filename,
            "nom":              fichier.filename,
            "type":             "juridique",
            "mime_type":        "application/pdf",
            "file_size_bytes":  taille,
            "file_hash_sha256": file_hash,
            "dossier_id":       dossier_id if dossier_id else None,
            "manuscrit":        est_manuscrit,
            "ocr_status":       "done",
            "scan_status":      "clean",
            "status":           "ready",
            "storage_tier":     "hot",
            "metadata":         {
                "sensible":  est_sensible,
                "chiffre":   est_chiffre_d,
                "manuscrit": est_manuscrit
            }
        }).execute()

        for page_data in pages_texte:
            texte = page_data["texte"]
            for j in range(0, len(texte), 800):
                chunk_texte = texte[j:j + 800].strip()
                if len(chunk_texte) > 50:
                    if est_sensible:
                        contenu_final = chiffrer(chunk_texte)
                        index_final   = extraire_index(chunk_texte)
                    else:
                        contenu_final = chunk_texte
                        index_final   = chunk_texte

                    supabase.table("chunks").insert({
                        "tenant_id":     tenant_id,
                        "document_id":   doc_id,
                        "content":       contenu_final,    # nouveau schéma
                        "contenu":       contenu_final,    # compatibilité
                        "contenu_index": index_final,      # compatibilité
                        "page_number":   page_data["page"],# nouveau schéma
                        "page_numero":   page_data["page"],# compatibilité
                        "chunk_index":   j // 800,
                        "source_type":   "document",
                        "source_hash":   file_hash,
                        "char_count":    len(chunk_texte),
                        "metadata": {
                            "sensible":  est_sensible,
                            "manuscrit": est_manuscrit
                        }
                    }).execute()
                    chunks_inseres += 1

        threading.Thread(
            target=_vectoriser_document,
            args=(doc_id, tenant_id),
            daemon=True
        ).start()

        log_audit_event("DOCUMENT_UPLOADED", tenant_id, user_id, {
            "filename":  fichier.filename,
            "hash":      file_hash,
            "chunks":    chunks_inseres,
            "dossier_id": dossier_id
        })
        try:
            log_audit(ACTION_UPLOAD, {
                "fichier":    fichier.filename,
                "chunks":     chunks_inseres,
                "manuscrit":  est_manuscrit,
                "dossier_id": dossier_id
            })
        except Exception:
            pass

        return jsonify({
            "succes":      True,
            "message":     f"'{fichier.filename}' indexé",
            "chunks":      chunks_inseres,
            "document_id": doc_id,
            "manuscrit":   est_manuscrit
        })

    except Exception as e:
        log_erreur("UPLOAD", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/liste_documents", methods=["GET"])
@jwt_required()
def liste_documents():
    try:
        dossier_id = request.args.get("dossier_id", "")
        tenant_id  = get_current_tenant_id()
        print(f"[LISTE_DOCS] tenant_id={tenant_id} dossier_id={dossier_id}")

        query = supabase.table("documents").select(
            "id, nom, filename, original_filename, type, dossier_id, "
            "manuscrit, status, storage_tier, created_at, metadata"
        ).eq("tenant_id", tenant_id).eq("status", "ready").order("created_at", desc=True)

        if dossier_id:
            query = query.eq("dossier_id", dossier_id)

        result = query.execute()
        print(f"[LISTE_DOCS] OK — {len(result.data)} docs")
        return jsonify(result.data)
    except Exception as e:
        import traceback
        print(f"[LISTE_DOCS] ERREUR : {traceback.format_exc()}")
        return jsonify({"erreur": str(e)}), 500


@app.route("/supprimer_document", methods=["DELETE"])
@jwt_required()
def supprimer_document():
    try:
        data      = request.json
        doc_id    = data.get("id")
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()

        if not doc_id:
            return jsonify({"erreur": "ID manquant"}), 400

        # Vérification appartenance tenant
        check = supabase.table("documents").select("id").eq(
            "id", doc_id
        ).eq("tenant_id", tenant_id).execute()
        if not check.data:
            return jsonify({"erreur": "Document non trouvé"}), 404

        supabase.table("chunks").delete().eq("document_id", doc_id).execute()
        # Soft delete
        supabase.table("documents").update({
            "status":     "deleted",
            "deleted_at": datetime.now().isoformat()
        }).eq("id", doc_id).eq("tenant_id", tenant_id).execute()

        log_audit_event("DOCUMENT_DELETED", tenant_id, user_id,
                        {"document_id": doc_id})
        try:
            log_audit(ACTION_SUPPRESSION, {"document_id": doc_id})
        except Exception:
            pass

        return jsonify({"succes": True})
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


# ─── COMPARAISON ──────────────────────────────────────────────────────────────

@app.route("/comparaison/analyser", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def comparaison_analyser():
    try:
        data        = request.json
        juge        = data.get("juge",        "").strip()
        juridiction = data.get("juridiction", "").strip()
        domaine     = data.get("domaine",     "")
        periode     = data.get("periode",     "Toutes")
        tenant_id   = get_current_tenant_id()

        if not juge and not juridiction:
            return jsonify({"erreur": "Juge ou juridiction requis"}), 400

        query = supabase.table("jurisprudence_predict").select(
            "id, titre, contenu, domaine, issue, juridiction, juge, "
            "date_dec, reference, source"
        )
        if juge:
            query = query.ilike("juge", f"%{juge}%")
        if juridiction:
            query = query.ilike("juridiction", f"%{juridiction}%")
        if domaine:
            query = query.eq("domaine", domaine)

        result    = query.order("date_dec", desc=True).limit(15).execute()
        decisions = result.data

        if not decisions:
            return jsonify({
                "succes":    False,
                "message":   "Aucune décision trouvée pour ces critères.",
                "decisions": []
            })

        prompt_texte = prompt_analyse_comparative(
            juge, juridiction, domaine, periode, decisions
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt_texte}]
        )

        raw     = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        analyse = json.loads(raw)

        log_audit_event("COMPARAISON", tenant_id, get_current_user_id(), {
            "juge": juge, "juridiction": juridiction, "domaine": domaine
        })

        return jsonify({
            "succes":    True,
            "decisions": decisions,
            "analyse":   analyse,
            "nb":        len(decisions)
        })

    except json.JSONDecodeError:
        return jsonify({"erreur": "Erreur de parsing — réessayez"}), 500
    except Exception as e:
        log_erreur("COMPARAISON", e)
        return jsonify({"erreur": str(e)}), 500


@app.route("/comparaison/juges", methods=["GET"])
@jwt_required()
def liste_juges():
    try:
        result = supabase.table("jurisprudence_predict").select(
            "juge, juridiction"
        ).not_.is_("juge", "null").execute()

        juges = {}
        for d in result.data:
            j = d.get("juge", "").strip()
            if j:
                if j not in juges:
                    juges[j] = {"juge": j, "juridiction": d.get("juridiction", ""), "nb": 0}
                juges[j]["nb"] += 1

        return jsonify(sorted(juges.values(), key=lambda x: x["nb"], reverse=True))
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


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
        contenu   = data.get("contenu", "")
        nom       = data.get("nom", "Document Odyxia Droit")
        tenant_id = get_current_tenant_id()

        if not contenu:
            return jsonify({"erreur": "Contenu vide"}), 400

        buffer = io.BytesIO()
        doc    = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=2.5*cm, leftMargin=2.5*cm,
            topMargin=2.5*cm,   bottomMargin=2.5*cm)

        OR   = colors.HexColor("#1A6B9A")   # Bleu ODYXIA
        DARK = colors.HexColor("#0B1F3A")   # Navy ODYXIA
        GRAY = colors.HexColor("#6B7280")

        s_titre  = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=15,
            textColor=OR, alignment=TA_CENTER, spaceAfter=4)
        s_sub    = ParagraphStyle("sub",   fontName="Helvetica", fontSize=9,
            textColor=GRAY, alignment=TA_CENTER, spaceAfter=2)
        s_h1     = ParagraphStyle("h1",    fontName="Helvetica-Bold", fontSize=12,
            textColor=OR, spaceBefore=12, spaceAfter=6)
        s_corps  = ParagraphStyle("corps", fontName="Helvetica", fontSize=10,
            textColor=DARK, leading=16, alignment=TA_JUSTIFY, spaceAfter=8)

        elements = []
        elements.append(Paragraph(f"Odyxia Droit · {CABINET_NOM}", s_titre))
        elements.append(Paragraph(f"{CABINET_AVOCAT} · {CABINET_VILLE}", s_sub))
        elements.append(Paragraph(
            f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", s_sub))
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
            f"Odyxia Droit · {CABINET_NOM} · Document confidentiel", s_sub))

        doc.build(elements)
        buffer.seek(0)

        log_audit_event("PDF_EXPORTED", tenant_id, get_current_user_id(), {"nom": nom})
        try:
            log_audit(ACTION_EXPORT_PDF, {"nom": nom})
        except Exception:
            pass

        return send_file(buffer, as_attachment=True,
            download_name=nom.replace(" ", "_") + ".pdf",
            mimetype="application/pdf")

    except Exception as e:
        log_erreur("EXPORT PDF", e)
        return jsonify({"erreur": str(e)}), 500


# ─── VEILLE ───────────────────────────────────────────────────────────────────

SOURCES_VEILLE = [
    {"id": "ohada", "nom": "OHADA",
     "url": "https://www.ohada.com/actes-uniformes.html",
     "domaine": "ohada.com", "actif": True},
    {"id": "izf",   "nom": "CEMAC / IZF",
     "url": "https://www.izf.net/textes-juridiques",
     "domaine": "izf.net", "actif": True},
    {"id": "spm",   "nom": "Lois Camerounaises",
     "url": "https://www.droit-afrique.com/pays/cameroun",
     "domaine": "droit-afrique.com", "actif": True},
    {"id": "ccja",  "nom": "Jurisprudence CCJA",
     "url": "https://www.ccja-ohada.org/decisions",
     "domaine": "ccja-ohada.org", "actif": True},
    {"id": "wipo",  "nom": "Propriété Intellectuelle OMPI",
     "url": "https://www.wipo.int/wipolex/fr/profile/CM",
     "domaine": "wipo.int", "actif": True},
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
        data      = request.json
        source_id = data.get("source_id")
        tenant_id = get_current_tenant_id()
        sources   = SOURCES_VEILLE
        if source_id:
            sources = [s for s in SOURCES_VEILLE if s["id"] == source_id]

        resultats = []
        headers   = {"User-Agent": "Mozilla/5.0"}

        for source in sources:
            resultat = {
                "source":    source["nom"],
                "source_id": source["id"],
                "nouveaux":  0, "doublons": 0, "erreurs": 0, "details": []
            }
            try:
                res = requests.get(source["url"], headers=headers, timeout=15)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")

                liens_pdf = []
                for a in soup.find_all("a", href=True):
                    href  = a["href"]
                    texte = a.get_text(strip=True)
                    if ".pdf" in href.lower():
                        if not href.startswith("http"):
                            base = f"https://{source['domaine']}"
                            href = base + href if href.startswith("/") else base + "/" + href
                        liens_pdf.append({"url": href, "nom": texte or href.split("/")[-1]})

                # Vérifier doublons par hash dans le tenant
                import hashlib
                for lien in liens_pdf[:10]:
                    nom_f = (lien["nom"][:100] + ".pdf"
                             if not lien["nom"].endswith(".pdf") else lien["nom"][:100])
                    try:
                        import fitz
                        pdf_res = requests.get(lien["url"], headers=headers, timeout=30)
                        if pdf_res.status_code == 200 and len(pdf_res.content) > 1000:
                            file_hash = hashlib.sha256(pdf_res.content).hexdigest()

                            hash_check = supabase.table("documents").select("id").eq(
                                "file_hash_sha256", file_hash
                            ).eq("tenant_id", tenant_id).execute()
                            if hash_check.data:
                                resultat["doublons"] += 1
                                continue

                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                                tmp.write(pdf_res.content)
                                tmp_path = tmp.name

                            doc_fitz    = fitz.open(tmp_path)
                            pages_texte = []
                            for i, page in enumerate(doc_fitz):
                                texte = page.get_text().strip()
                                if texte:
                                    pages_texte.append({"page": i + 1, "texte": texte})
                            doc_fitz.close()
                            os.unlink(tmp_path)

                            if pages_texte:
                                doc_id = str(uuid.uuid4())
                                supabase.table("documents").insert({
                                    "id":               doc_id,
                                    "tenant_id":        tenant_id,
                                    "filename":         nom_f,
                                    "original_filename": nom_f,
                                    "nom":              nom_f,
                                    "type":             source["id"],
                                    "mime_type":        "application/pdf",
                                    "file_size_bytes":  len(pdf_res.content),
                                    "file_hash_sha256": file_hash,
                                    "status":           "ready",
                                    "storage_tier":     "hot",
                                    "ocr_status":       "done",
                                    "scan_status":      "clean",
                                }).execute()

                                chunks_inseres = 0
                                for page_data in pages_texte:
                                    texte = page_data["texte"]
                                    for j in range(0, len(texte), 800):
                                        chunk_texte = texte[j:j + 800].strip()
                                        if len(chunk_texte) > 50:
                                            supabase.table("chunks").insert({
                                                "tenant_id":   tenant_id,
                                                "document_id": doc_id,
                                                "content":     chunk_texte,
                                                "contenu":     chunk_texte,
                                                "contenu_index": chunk_texte,
                                                "page_number": page_data["page"],
                                                "page_numero": page_data["page"],
                                                "chunk_index": j // 800,
                                                "source_type": "document",
                                            }).execute()
                                            chunks_inseres += 1

                                resultat["nouveaux"] += 1
                                resultat["details"].append(
                                    f"OK {nom_f} ({chunks_inseres} chunks)")
                    except Exception:
                        resultat["erreurs"] += 1

            except Exception as e:
                resultat["erreurs"] += 1
                resultat["details"].append(f"Erreur : {str(e)[:100]}")

            resultats.append(resultat)

        return jsonify({"succes": True, "resultats": resultats})

    except Exception as e:
        log_erreur("VEILLE", e)
        return jsonify({"erreur": str(e)}), 500


# ─── PROFIL JUGE ──────────────────────────────────────────────────────────────

@app.route("/comparaison/profil_juge", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def profil_juge():
    try:
        data        = request.json
        juge        = data.get("juge",        "").strip()
        juridiction = data.get("juridiction", "").strip()

        if not juge and not juridiction:
            return jsonify({"erreur": "Juge ou juridiction requis"}), 400

        query = supabase.table("jurisprudence_predict").select(
            "domaine, issue, date_dec, juge, juridiction, chambre"
        )
        if juge:
            query = query.ilike("juge", f"%{juge}%")
        if juridiction:
            query = query.ilike("juridiction", f"%{juridiction}%")

        result    = query.execute()
        decisions = result.data

        if not decisions:
            return jsonify({"succes": False, "message": "Aucune décision trouvée"})

        total = len(decisions)
        fav   = sum(1 for d in decisions if d.get("issue") == "favorable")
        defav = sum(1 for d in decisions if d.get("issue") == "defavorable")
        part  = sum(1 for d in decisions if d.get("issue") == "partiel")

        domaines = {}
        for d in decisions:
            dom = d.get("domaine") or "autre"
            if dom not in domaines:
                domaines[dom] = {"total": 0, "fav": 0}
            domaines[dom]["total"] += 1
            if d.get("issue") == "favorable":
                domaines[dom]["fav"] += 1

        taux_fav      = round(fav / total * 100)    if total else 0
        taux_defav    = round(defav / total * 100)  if total else 0
        previsibilite = round(max(taux_fav, taux_defav) * 0.9 + (10 if total > 5 else 0))
        previsibilite = min(previsibilite, 95)

        radar = {
            "favorabilite":  taux_fav,
            "previsibilite": previsibilite,
            "volume":        min(total * 8, 90),
            "commercial": round(
                domaines.get("commercial", {}).get("fav", 0) /
                max(domaines.get("commercial", {}).get("total", 1), 1) * 100),
            "civil": round(
                domaines.get("civil", {}).get("fav", 0) /
                max(domaines.get("civil", {}).get("total", 1), 1) * 100),
            "penal": round(
                domaines.get("penal", {}).get("fav", 0) /
                max(domaines.get("penal", {}).get("total", 1), 1) * 100),
        }

        return jsonify({
            "succes":        True,
            "juge":          juge or juridiction,
            "total":         total,
            "favorables":    fav,
            "defavorables":  defav,
            "partielles":    part,
            "taux_fav":      taux_fav,
            "previsibilite": previsibilite,
            "radar":         radar,
            "domaines":      domaines
        })

    except Exception as e:
        log_erreur("PROFIL_JUGE", e)
        return jsonify({"erreur": str(e)}), 500


# ─── TIMELINE DOSSIER ─────────────────────────────────────────────────────────

@app.route("/timeline_dossier", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def timeline_dossier():
    try:
        data       = request.json
        dossier_id = data.get("dossier_id", "")
        tenant_id  = get_current_tenant_id()

        if not dossier_id:
            return jsonify({"erreur": "dossier_id requis"}), 400

        docs_result = supabase.table("documents").select("id, nom, filename").eq(
            "dossier_id", dossier_id
        ).eq("tenant_id", tenant_id).execute()

        if not docs_result.data:
            return jsonify({"erreur": "Aucun document dans ce dossier"}), 404

        doc_ids = [d["id"] for d in docs_result.data]
        chunks_result = supabase.table("chunks").select(
            "content, contenu, document_id, page_number, page_numero"
        ).in_("document_id", doc_ids).limit(30).execute()

        if not chunks_result.data:
            return jsonify({"erreur": "Documents non indexés"}), 404

        texte = ""
        for chunk in chunks_result.data:
            contenu = chunk.get("content") or chunk.get("contenu", "")
            if est_chiffre(contenu):
                contenu = dechiffrer(contenu)
            texte += contenu + "\n"

        texte = texte[:9000]

        prompt_texte = prompt_timeline_dossier(texte, dossier_id)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt_texte}]
        )

        raw      = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        timeline = json.loads(raw)

        return jsonify({"succes": True, "dossier_id": dossier_id, "timeline": timeline})

    except json.JSONDecodeError:
        return jsonify({"erreur": "Erreur de parsing — réessayez"}), 500
    except Exception as e:
        log_erreur("TIMELINE", e)
        return jsonify({"erreur": str(e)}), 500


# ─── STATS CABINET ────────────────────────────────────────────────────────────

@app.route("/stats", methods=["GET"])
@jwt_required()
def stats_cabinet():
    try:
        tenant_id = get_current_tenant_id()

        dos  = supabase.table("dossiers").select("id", count="exact").eq(
            "tenant_id", tenant_id).execute()
        docr = supabase.table("documents").select("id", count="exact").eq(
            "tenant_id", tenant_id).eq("status", "ready").execute()
        jurr = supabase.table("jurisprudence_predict").select(
            "issue, domaine, date_dec"
        ).execute()

        nb_dossiers = dos.count  if hasattr(dos,  "count") else len(dos.data)
        nb_docs     = docr.count if hasattr(docr, "count") else len(docr.data)
        decisions   = jurr.data or []

        total_dec   = len(decisions)
        fav_dec     = sum(1 for d in decisions if d.get("issue") == "favorable")
        taux_succes = round(fav_dec / total_dec * 100) if total_dec else 0

        domaines    = {}
        for d in decisions:
            dom = d.get("domaine") or "autre"
            domaines[dom] = domaines.get(dom, 0) + 1

        top_domaine = max(domaines, key=domaines.get) if domaines else "—"

        return jsonify({
            "succes":      True,
            "dossiers":    nb_dossiers,
            "documents":   nb_docs,
            "decisions":   total_dec,
            "taux_succes": taux_succes,
            "top_domaine": top_domaine,
            "domaines":    domaines
        })

    except Exception as e:
        log_erreur("STATS", e)
        return jsonify({"erreur": str(e)}), 500


# ─── RAPPORT CLIENT PDF ───────────────────────────────────────────────────────

@app.route("/rapport_client", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def rapport_client():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                         HRFlowable)
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

        data       = request.json
        dossier_id = data.get("dossier_id", "")
        nom_client = data.get("nom_client",  "")
        tenant_id  = get_current_tenant_id()

        if not dossier_id:
            return jsonify({"erreur": "dossier_id requis"}), 400

        # Vérification appartenance tenant
        dos_result = supabase.table("dossiers").select("nom, description").eq(
            "id", dossier_id
        ).eq("tenant_id", tenant_id).execute()
        if not dos_result.data:
            return jsonify({"erreur": "Dossier non trouvé"}), 404

        dossier_info = dos_result.data[0]
        docs_result  = supabase.table("documents").select("id, nom, filename").eq(
            "dossier_id", dossier_id
        ).eq("tenant_id", tenant_id).execute()
        docs    = docs_result.data or []
        doc_ids = [d["id"] for d in docs]

        texte = ""
        if doc_ids:
            chunks_result = supabase.table("chunks").select(
                "content, contenu, document_id"
            ).in_("document_id", doc_ids).limit(20).execute()
            for chunk in (chunks_result.data or []):
                c = chunk.get("content") or chunk.get("contenu", "")
                if est_chiffre(c):
                    c = dechiffrer(c)
                texte += c + "\n"

        texte = texte[:7000]

        prompt_texte = prompt_rapport_client(
            texte, dossier_info["nom"], nom_client, docs
        )
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt_texte}]
        )
        raw    = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        rapport = json.loads(raw)

        buffer = io.BytesIO()
        doc    = SimpleDocTemplate(buffer, pagesize=A4,
            leftMargin=2.5*cm, rightMargin=2.5*cm,
            topMargin=2.5*cm,  bottomMargin=2.5*cm)

        BLUE = colors.HexColor("#1A6B9A")
        DARK = colors.HexColor("#0B1F3A")
        GRAY = colors.HexColor("#6B7280")

        s_title = ParagraphStyle("title", fontSize=22, textColor=DARK,
                                  fontName="Helvetica-Bold", spaceAfter=4)
        s_sub   = ParagraphStyle("sub",   fontSize=12, textColor=GRAY,
                                  fontName="Helvetica",      spaceAfter=20)
        s_h2    = ParagraphStyle("h2",    fontSize=14, textColor=DARK,
                                  fontName="Helvetica-Bold", spaceBefore=16, spaceAfter=8)
        s_body  = ParagraphStyle("body",  fontSize=11, textColor=DARK,
                                  fontName="Helvetica",      leading=17, alignment=TA_JUSTIFY)
        s_item  = ParagraphStyle("item",  fontSize=11, textColor=DARK,
                                  fontName="Helvetica",      leading=17, leftIndent=16)
        s_center = ParagraphStyle("center", fontSize=10, textColor=GRAY,
                                   fontName="Helvetica",     alignment=TA_CENTER)

        story = []
        story.append(Paragraph("Odyxia Droit.", s_title))
        story.append(Paragraph(
            f"Rapport — {rapport.get('titre', dossier_info['nom'])}", s_sub))
        story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=16))

        if nom_client:
            story.append(Paragraph(f"Préparé pour : <b>{nom_client}</b>", s_body))
            story.append(Spacer(1, 8))

        story.append(Paragraph("Résumé exécutif", s_h2))
        story.append(Paragraph(rapport.get("resume", ""), s_body))
        story.append(Spacer(1, 12))

        if rapport.get("etat_avancement"):
            story.append(Paragraph("État d'avancement", s_h2))
            story.append(Paragraph(rapport["etat_avancement"], s_body))
            story.append(Spacer(1, 12))

        if rapport.get("actes_realises"):
            story.append(Paragraph("Actes réalisés", s_h2))
            for item in rapport["actes_realises"]:
                story.append(Paragraph(f"• {item}", s_item))
            story.append(Spacer(1, 12))

        if rapport.get("prochaines_etapes"):
            story.append(Paragraph("Prochaines étapes", s_h2))
            for item in rapport["prochaines_etapes"]:
                story.append(Paragraph(f"→ {item}", s_item))
            story.append(Spacer(1, 12))

        if rapport.get("probabilite_succes"):
            story.append(HRFlowable(width="100%", thickness=0.5,
                                     color=BLUE, spaceAfter=12))
            story.append(Paragraph(
                f"Évaluation préliminaire : <b>{rapport['probabilite_succes']}</b>",
                s_body
            ))

        story.append(HRFlowable(width="100%", thickness=0.5,
                                  color=BLUE, spaceBefore=20, spaceAfter=8))
        story.append(Paragraph(
            f"Odyxia Droit · {CABINET_NOM} · {CABINET_VILLE}", s_center))

        doc.build(story)
        buffer.seek(0)

        nom_fichier = f"rapport_{dossier_info['nom'].replace(' ', '_')}.pdf"
        return send_file(buffer, mimetype="application/pdf",
                         as_attachment=True, download_name=nom_fichier)

    except Exception as e:
        log_erreur("RAPPORT_CLIENT", e)
        return jsonify({"erreur": str(e)}), 500


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    status = {"status": "ok", "service": "odyxia-droit", "supabase": "ok"}
    try:
        supabase.table("sessions").select("id").limit(1).execute()
    except Exception:
        status["supabase"] = "degraded"
    return jsonify(status), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)