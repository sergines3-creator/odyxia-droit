"""
ODYXIA Droit — Module d'integration CamPay (v2, corrige selon doc officielle)
Doc API consultee : https://documenter.getpostman.com/view/2391374/T1LV8PVA

Gere : initiation de paiement direct (popup PIN), generation de lien de
paiement, webhook de confirmation avec verification JWT, mise a jour
automatique de l'abonnement tenant.

A placer dans /root/odyxia-droit/campay_integration.py
puis importer dans app.py :
    from campay_integration import campay_bp, init_campay
    init_campay(supabase, get_current_tenant_id, log_audit_event,
                log_security_event, log_erreur)
    app.register_blueprint(campay_bp)

PREREQUIS (.env) :
    CAMPAY_API_KEY=<jeton_acces_permanent>
    CAMPAY_WEBHOOK_SECRET=<cle_webhook_application>
    CAMPAY_BASE_URL=https://demo.campay.net/api   (sandbox)
    # ou https://www.campay.net/api               (production, a confirmer
    #   l'URL exacte une fois "Passer en LIVE" active sur le dashboard)
    MONTANT_MENSUEL_FCFA=60000
    MONTANT_ANNUEL_FCFA=600000

IMPORTANT — configuration cote dashboard CamPay :
    Dans "Gerer l'application" -> Webhook, renseigner l'URL :
        https://odyxiadroit.com/webhook/campay
    Methode : POST (recommande, plus simple a parser qu'un GET avec
    query params).
"""

import os
import uuid
import requests
import jwt as pyjwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

campay_bp = Blueprint("campay", __name__)

CAMPAY_BASE_URL = os.environ.get("CAMPAY_BASE_URL", "https://demo.campay.net/api").rstrip("/")
CAMPAY_API_KEY = os.environ.get("CAMPAY_API_KEY", "")
CAMPAY_WEBHOOK_SECRET = os.environ.get("CAMPAY_WEBHOOK_SECRET", "")
MONTANT_MENSUEL = int(os.environ.get("MONTANT_MENSUEL_FCFA", "60000"))
MONTANT_ANNUEL = int(os.environ.get("MONTANT_ANNUEL_FCFA", "600000"))

# References injectees depuis app.py au moment de l'enregistrement du blueprint
_supabase = None
_get_current_tenant_id = None
_log_audit_event = None
_log_security_event = None
_log_erreur = None


def init_campay(supabase_client, get_current_tenant_id_fn, log_audit_event_fn,
                 log_security_event_fn, log_erreur_fn):
    """
    Injecte les dependances depuis app.py pour eviter les imports circulaires.
    A appeler une seule fois au demarrage, juste apres la creation de `app`.
    """
    global _supabase, _get_current_tenant_id, _log_audit_event
    global _log_security_event, _log_erreur
    _supabase = supabase_client
    _get_current_tenant_id = get_current_tenant_id_fn
    _log_audit_event = log_audit_event_fn
    _log_security_event = log_security_event_fn
    _log_erreur = log_erreur_fn


def _campay_headers():
    return {
        "Authorization": f"Token {CAMPAY_API_KEY}",
        "Content-Type": "application/json",
    }


def _valider_numero_camerounais(telephone: str) -> str:
    """
    Normalise un numero de telephone au format attendu par CamPay : 237XXXXXXXXX
    Leve une ValueError si le format est invalide.
    """
    tel = telephone.strip().replace(" ", "").replace("-", "")
    if tel.startswith("+"):
        tel = tel[1:]
    if tel.startswith("0"):
        tel = "237" + tel[1:]
    if not tel.startswith("237"):
        tel = "237" + tel
    if len(tel) != 12 or not tel.isdigit():
        raise ValueError(f"Numero de telephone invalide : {telephone}")
    return tel


def _verifier_signature_webhook(signature_jwt: str) -> bool:
    """
    Verifie le JWT recu dans le champ 'signature' du webhook CamPay,
    signe avec la cle webhook de l'application (CAMPAY_WEBHOOK_SECRET).

    Retourne True si la signature est valide, False sinon.
    Ne leve jamais d'exception : tout echec de decodage = signature invalide.
    """
    if not CAMPAY_WEBHOOK_SECRET:
        # Aucune cle configuree : on ne peut pas verifier. On log et on
        # refuse par defaut pour eviter un faux sentiment de securite.
        return False
    try:
        pyjwt.decode(signature_jwt, CAMPAY_WEBHOOK_SECRET, algorithms=["HS256"])
        return True
    except pyjwt.InvalidTokenError:
        return False
    except Exception:
        return False


def _get_transaction_status(reference: str) -> dict:
    """
    GET /transaction/(reference)/ — recupere le statut reel d'une transaction
    directement depuis CamPay (jamais a partir du seul body du webhook).
    Retourne le JSON de reponse, ou {} en cas d'echec.
    """
    try:
        resp = requests.get(
            f"{CAMPAY_BASE_URL}/transaction/{reference}/",
            headers=_campay_headers(),
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
        return {}
    except Exception:
        return {}


@campay_bp.route("/abonnement/payer", methods=["POST"])
@jwt_required()
def initier_paiement():
    """
    Initie un paiement CamPay pour l'abonnement du tenant courant.
    POST /collect/ : declenche le popup PIN MoMo sur le telephone du cabinet.

    Body JSON attendu :
        {
            "telephone": "237670000000",
            "cadence": "mensuel" | "annuel"
        }
    """
    try:
        tenant_id = _get_current_tenant_id()
        data = request.json or {}
        telephone = data.get("telephone", "")
        cadence = data.get("cadence", "mensuel")

        if cadence not in ("mensuel", "annuel"):
            return jsonify({"erreur": "cadence doit etre 'mensuel' ou 'annuel'"}), 400

        try:
            telephone_normalise = _valider_numero_camerounais(telephone)
        except ValueError as e:
            return jsonify({"erreur": str(e)}), 400

        montant = MONTANT_MENSUEL if cadence == "mensuel" else MONTANT_ANNUEL

        # external_reference : notre reference interne, utilisee pour
        # retrouver le paiement local quand le webhook arrive.
        external_reference = str(uuid.uuid4())

        # Enregistrement local AVANT l'appel CamPay (statut pending).
        # reference_campay est temporairement = external_reference ;
        # elle sera mise a jour avec la vraie reference UUID4 de CamPay
        # une fois la reponse /collect/ recue.
        _supabase.table("paiements_campay").insert({
            "tenant_id": tenant_id,
            "reference_campay": external_reference,
            "montant_fcfa": montant,
            "cadence": cadence,
            "telephone": telephone_normalise,
            "statut": "pending",
        }).execute()

        # POST /collect/ - voir doc : amount, currency, from, description,
        # external_reference sont les champs attendus.
        payload = {
            "amount": str(montant),
            "currency": "XAF",
            "from": telephone_normalise,
            "description": f"Abonnement ODYXIA Droit - {cadence}",
            "external_reference": external_reference,
        }

        resp = requests.post(
            f"{CAMPAY_BASE_URL}/collect/",
            json=payload,
            headers=_campay_headers(),
            timeout=30,
        )

        if resp.status_code not in (200, 201):
            _log_erreur("CAMPAY_COLLECT_ECHEC", Exception(resp.text))
            _supabase.table("paiements_campay").update({
                "statut": "failed",
                "raw_webhook_payload": {"erreur_initiation": resp.text},
            }).eq("reference_campay", external_reference).execute()
            return jsonify({"erreur": "Echec de l'initiation du paiement CamPay"}), 502

        resp_data = resp.json()
        # /collect/ retourne "reference" : la vraie reference UUID4 CamPay
        # a utiliser pour interroger /transaction/(reference)/
        reference_campay_reelle = resp_data.get("reference", external_reference)

        _supabase.table("paiements_campay").update({
            "reference_campay": reference_campay_reelle,
        }).eq("reference_campay", external_reference).execute()

        _log_audit_event("PAIEMENT_INITIE", tenant_id, "system", {
            "cadence": cadence, "montant": montant,
            "reference": reference_campay_reelle,
        })

        return jsonify({
            "succes": True,
            "message": "Demande de paiement envoyee. Confirmez sur votre telephone.",
            "reference": reference_campay_reelle,
        }), 200

    except Exception as e:
        _log_erreur("INITIER_PAIEMENT_CAMPAY", e)
        return jsonify({"erreur": "Erreur interne lors de l'initiation du paiement"}), 500


@campay_bp.route("/abonnement/payer/lien", methods=["POST"])
@jwt_required()
def generer_lien_paiement():
    """
    Alternative a /abonnement/payer : POST /get_payment_link/.
    Genere un lien de paiement CamPay, utile pour l'envoi par email/SMS
    pour les relances mensuelles, sans que le cabinet soit connecte a
    l'app au moment du paiement.

    Body JSON attendu :
        { "cadence": "mensuel" | "annuel" }
    """
    try:
        tenant_id = _get_current_tenant_id()
        data = request.json or {}
        cadence = data.get("cadence", "mensuel")

        if cadence not in ("mensuel", "annuel"):
            return jsonify({"erreur": "cadence doit etre 'mensuel' ou 'annuel'"}), 400

        montant = MONTANT_MENSUEL if cadence == "mensuel" else MONTANT_ANNUEL
        external_reference = str(uuid.uuid4())

        _supabase.table("paiements_campay").insert({
            "tenant_id": tenant_id,
            "reference_campay": external_reference,
            "montant_fcfa": montant,
            "cadence": cadence,
            "statut": "pending",
        }).execute()

        payload = {
            "amount": str(montant),
            "currency": "XAF",
            "description": f"Abonnement ODYXIA Droit - {cadence}",
            "external_reference": external_reference,
            "payment_options": "MOMO",
        }

        resp = requests.post(
            f"{CAMPAY_BASE_URL}/get_payment_link/",
            json=payload,
            headers=_campay_headers(),
            timeout=30,
        )

        if resp.status_code not in (200, 201):
            _log_erreur("CAMPAY_PAYMENT_LINK_ECHEC", Exception(resp.text))
            return jsonify({"erreur": "Echec de la generation du lien"}), 502

        resp_data = resp.json()
        # CORRECTION : le champ retourne s'appelle "link", pas "payment_link"
        lien = resp_data.get("link", "")
        reference_campay_reelle = resp_data.get("reference", external_reference)

        _supabase.table("paiements_campay").update({
            "lien_paiement": lien,
            "reference_campay": reference_campay_reelle,
        }).eq("reference_campay", external_reference).execute()

        return jsonify({"succes": True, "lien_paiement": lien}), 200

    except Exception as e:
        _log_erreur("GENERER_LIEN_PAIEMENT", e)
        return jsonify({"erreur": "Erreur interne"}), 500


def _traiter_confirmation_paiement(reference: str, statut_reel: str, payload_brut: dict):
    """
    Logique commune d'activation/desactivation d'abonnement,
    appelee uniquement apres verification de la transaction.
    """
    r = _supabase.table("paiements_campay").select(
        "id,tenant_id,cadence,montant_fcfa,statut"
    ).eq("reference_campay", reference).execute()

    if not r.data:
        _log_erreur("CAMPAY_REF_INCONNUE", Exception(reference))
        return False, "Reference inconnue"

    paiement = r.data[0]
    tenant_id = paiement["tenant_id"]

    # Idempotence : si deja traite comme successful, ne rien refaire
    if paiement["statut"] == "successful":
        return True, "Deja traite"

    _supabase.table("paiements_campay").update({
        "statut": statut_reel.lower(),
        "raw_webhook_payload": payload_brut,
        "date_confirmee": datetime.utcnow().isoformat() if statut_reel == "SUCCESSFUL" else None,
    }).eq("reference_campay", reference).execute()

    if statut_reel == "SUCCESSFUL":
        t = _supabase.table("tenants").select(
            "abonnement_end,plan"
        ).eq("id", tenant_id).execute()

        now = datetime.utcnow()
        base = now
        if t.data and t.data[0].get("plan") == "actif" and t.data[0].get("abonnement_end"):
            try:
                current_end = datetime.fromisoformat(
                    t.data[0]["abonnement_end"].replace("Z", ""))
                base = current_end if current_end > now else now
            except Exception:
                base = now

        jours = 30 if paiement["cadence"] == "mensuel" else 365
        nouvelle_fin = base + timedelta(days=jours)

        _supabase.table("tenants").update({
            "plan": "actif",
            "status": "active",
            "abonnement_end": nouvelle_fin.isoformat(),
            "montant_fcfa": paiement["montant_fcfa"],
            "paiement_ref": reference,
            "paiement_date": now.isoformat(),
            "paiement_mode": "campay_momo",
        }).eq("id", tenant_id).execute()

        _log_audit_event("PAIEMENT_VALIDE", tenant_id, "system", {
            "montant": paiement["montant_fcfa"],
            "cadence": paiement["cadence"],
            "reference": reference,
            "nouvelle_fin": nouvelle_fin.isoformat(),
            "source": "campay_webhook",
        })

    elif statut_reel == "FAILED":
        _log_security_event("paiement_campay_echec", tenant_id, None, {
            "reference": reference,
        })

    return True, "Traite"


@campay_bp.route("/webhook/campay", methods=["POST", "GET"])
def webhook_campay():
    """
    Webhook appele automatiquement par CamPay quand le statut
    d'une transaction change (SUCCESSFUL ou FAILED).

    Format confirme par la doc officielle CamPay :
    - methode configurable en GET (query params) ou POST (JSON body) cote
      dashboard CamPay ; on accepte les deux ici par robustesse.
    - le champ 'signature' est un JWT signe avec la cle webhook de
      l'application (CAMPAY_WEBHOOK_SECRET). On le verifie SYSTEMATIQUEMENT
      avant de faire confiance a quoi que ce soit dans la requete.
    - en complement, on revalide aussi via GET /transaction/(reference)/
      avec notre cle API : double-controle, defense en profondeur.

    IMPORTANT SECURITE :
    - Cette route n'a PAS @jwt_required() car c'est CamPay qui l'appelle,
      pas un utilisateur ODYXIA connecte.
    - Si la signature JWT est absente ou invalide, la requete est rejetee
      avant tout traitement, meme si le statut annonce est SUCCESSFUL.
    """
    try:
        ip_source = request.headers.get("X-Forwarded-For", request.remote_addr)

        if request.method == "POST":
            payload = request.json or {}
        else:
            payload = request.args.to_dict()

        reference = payload.get("reference")
        signature_jwt = payload.get("signature", "")

        if not reference:
            _log_security_event("webhook_campay_sans_reference", details={"ip": ip_source})
            return jsonify({"erreur": "reference manquante"}), 400

        # ETAPE 1 — Verification de la signature JWT CamPay.
        # Rejet immediat si invalide, AVANT tout appel reseau ou ecriture DB.
        if not _verifier_signature_webhook(signature_jwt):
            _log_security_event("webhook_campay_signature_invalide", details={
                "ip": ip_source, "reference": reference,
            })
            return jsonify({"erreur": "Signature invalide"}), 401

        # ETAPE 2 — Double-controle : on revalide directement auprès de
        # CamPay via l'API authentifiee, on ne fait jamais confiance au
        # seul statut annonce dans le payload du webhook.
        verif_data = _get_transaction_status(reference)
        if not verif_data:
            _log_erreur("CAMPAY_WEBHOOK_VERIF_ECHEC", Exception(reference))
            _log_security_event("webhook_campay_verif_echec", details={
                "ip": ip_source, "reference": reference,
            })
            return jsonify({"erreur": "Verification echouee"}), 502

        statut_reel = verif_data.get("status", "")

        succes, message = _traiter_confirmation_paiement(reference, statut_reel, payload)

        if not succes:
            return jsonify({"erreur": message}), 404

        return jsonify({"succes": True, "message": message}), 200

    except Exception as e:
        _log_erreur("WEBHOOK_CAMPAY", e)
        return jsonify({"erreur": "Erreur interne webhook"}), 500


@campay_bp.route("/abonnement/historique-paiements", methods=["GET"])
@jwt_required()
def historique_paiements():
    """Liste l'historique des paiements CamPay du tenant courant."""
    try:
        tenant_id = _get_current_tenant_id()
        r = _supabase.table("paiements_campay").select(
            "id,montant_fcfa,cadence,statut,date_initiee,date_confirmee"
        ).eq("tenant_id", tenant_id).order("date_initiee", desc=True).limit(24).execute()
        return jsonify({"paiements": r.data}), 200
    except Exception as e:
        _log_erreur("HISTORIQUE_PAIEMENTS", e)
        return jsonify({"erreur": "Erreur interne"}), 500


@campay_bp.route("/abonnement/verifier-statut/<reference>", methods=["GET"])
@jwt_required()
def verifier_statut_paiement(reference):
    """
    Endpoint manuel de secours : permet au frontend de re-verifier
    le statut d'un paiement en cours (polling) sans attendre le webhook,
    utile si le webhook tarde ou echoue pour une raison reseau.
    """
    try:
        tenant_id = _get_current_tenant_id()

        r = _supabase.table("paiements_campay").select(
            "tenant_id,statut"
        ).eq("reference_campay", reference).execute()

        if not r.data:
            return jsonify({"erreur": "Reference inconnue"}), 404

        if r.data[0]["tenant_id"] != tenant_id:
            _log_security_event("acces_paiement_autre_tenant", tenant_id, None, {
                "reference": reference,
            })
            return jsonify({"erreur": "Non autorise"}), 403

        if r.data[0]["statut"] == "successful":
            return jsonify({"statut": "successful"}), 200

        verif_data = _get_transaction_status(reference)
        if not verif_data:
            return jsonify({"statut": "pending", "message": "Verification en cours"}), 200

        statut_reel = verif_data.get("status", "PENDING")
        if statut_reel in ("SUCCESSFUL", "FAILED"):
            _traiter_confirmation_paiement(reference, statut_reel, verif_data)

        return jsonify({"statut": statut_reel.lower()}), 200

    except Exception as e:
        _log_erreur("VERIFIER_STATUT_PAIEMENT", e)
        return jsonify({"erreur": "Erreur interne"}), 500
