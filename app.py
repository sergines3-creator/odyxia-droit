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

CABINET_NOM    = os.environ.get("CABINET_NOM",    "ODYXIA Droit")
CABINET_AVOCAT = os.environ.get("CABINET_AVOCAT", "Maître")
CABINET_VILLE  = os.environ.get("CABINET_VILLE",  "Douala, Cameroun")

# ─── FLASK ────────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
Talisman(app,
    force_https=False,
    strict_transport_security=True,
    session_cookie_secure=True,
    content_security_policy=False
)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "ODYXIA-JWT-2026!")
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
        issuer_name=f"ODYXIA Droit — {CABINET_NOM}"
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
        nom       = data.get("nom", "Document ODYXIA Droit")
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
        elements.append(Paragraph(f"ODYXIA Droit · {CABINET_NOM}", s_titre))
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
            f"ODYXIA Droit · {CABINET_NOM} · Document confidentiel", s_sub))

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
        story.append(Paragraph("ODYXIA Droit.", s_title))
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
            f"ODYXIA Droit · {CABINET_NOM} · {CABINET_VILLE}", s_center))

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