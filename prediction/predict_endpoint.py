"""
predict_endpoint.py — Odyxia Droit
Blueprint Flask pour l'analyse prédictive juridique
Sécurité : JWT requis sur toutes les routes + rate limiting + audit logs
"""

import os
import uuid
import time
import json
import tempfile
import threading
import requests

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
from anthropic import Anthropic
from supabase import create_client

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
VOYAGE_MODEL   = "voyage-law-2"
VOYAGE_URL     = "https://api.voyageai.com/v1/embeddings"

predict_bp = Blueprint("predict", __name__, url_prefix="/predict")
supabase   = create_client(SUPABASE_URL, SUPABASE_KEY)
client     = Anthropic(api_key=ANTHROPIC_KEY)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def log_erreur(contexte, erreur):
    message = str(erreur)
    if SUPABASE_KEY:
        message = message.replace(SUPABASE_KEY, "***")
    print(f"[PREDICT][ERREUR] {contexte}: {message[:200]}")


def get_embedding_voyage(texte: str, input_type: str = "document"):
    """Vectorise un texte avec Voyage AI voyage-law-2."""
    try:
        if not VOYAGE_API_KEY:
            return None
        res = requests.post(
            VOYAGE_URL,
            headers={
                "Authorization": f"Bearer {VOYAGE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "input": [texte[:4096]],
                "model": VOYAGE_MODEL,
                "input_type": input_type
            },
            timeout=15
        )
        res.raise_for_status()
        return res.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"[VOYAGE] Erreur embedding : {e}")
        return None


def vectoriser_jurisprudence(doc_id: str):
    """Vectorise les chunks de jurisprudence en arrière-plan."""
    try:
        result = supabase.table("jurisprudence_predict").select(
            "id, contenu"
        ).eq("id", doc_id).is_("embedding", "null").execute()

        if not result.data:
            return

        for item in result.data:
            texte = item.get("contenu", "")[:4096]
            if not texte:
                continue
            embedding = get_embedding_voyage(texte, "document")
            if embedding:
                supabase.table("jurisprudence_predict").update(
                    {"embedding": embedding}
                ).eq("id", item["id"]).execute()
                time.sleep(0.1)

        print(f"[PREDICT] Vectorisation terminée pour {doc_id[:8]}")
    except Exception as e:
        print(f"[PREDICT] Erreur vectorisation : {e}")


def rechercher_precedents(query: str, domaine: str = "", limite: int = 8):
    """
    Recherche les précédents jurisprudentiels similaires.
    Niveau 1 : vectoriel (RPC match_jurisprudence)
    Niveau 2 : ilike sur contenu
    """
    resultats = []
    ids_vus = set()

    def ajouter(data):
        for item in data:
            if item["id"] not in ids_vus:
                ids_vus.add(item["id"])
                resultats.append(item)

    # Niveau 1 — vectoriel
    try:
        embedding = get_embedding_voyage(query[:4096], "query")
        if embedding:
            params = {
                "query_embedding": embedding,
                "match_threshold": 0.3,
                "match_count": limite
            }
            if domaine:
                params["filter_domaine"] = domaine
            res = supabase.rpc("match_jurisprudence", params).execute()
            if res.data:
                ajouter(res.data)
    except Exception as e:
        print(f"[PREDICT] Vectorielle : {e}")

    # Niveau 2 — ilike
    if not resultats:
        try:
            mots = [m for m in query.lower().split() if len(m) > 4][:5]
            for mot in mots:
                q = supabase.table("jurisprudence_predict").select(
                    "id, titre, contenu, domaine, issue, juridiction, date_dec, reference, source"
                ).ilike("contenu", f"%{mot}%")
                if domaine:
                    q = q.eq("domaine", domaine)
                res = q.limit(4).execute()
                ajouter(res.data)
        except Exception as e:
            print(f"[PREDICT] ilike : {e}")

    return resultats[:limite]


def analyser_risque(query: str, precedents: list, domaine: str) -> dict:
    """
    Calcule un score de risque basé sur les précédents.
    Retourne : score (0-100), level, facteurs
    """
    if not precedents:
        return {
            "score": 50,
            "level": "indéterminé",
            "facteurs": ["Aucun précédent indexé — score estimé par défaut"]
        }

    total = len(precedents)
    defavorables = sum(1 for p in precedents if p.get("issue") == "defavorable")
    favorables   = sum(1 for p in precedents if p.get("issue") == "favorable")
    partiels     = sum(1 for p in precedents if p.get("issue") == "partiel")

    score = int((defavorables / total) * 100) if total > 0 else 50
    score = max(10, min(95, score))

    if score >= 70:
        level = "élevé"
    elif score >= 45:
        level = "modéré"
    elif score >= 20:
        level = "faible"
    else:
        level = "très faible"

    facteurs = [
        f"{total} précédent(s) analysé(s) — domaine : {domaine}",
        f"{defavorables} issue(s) défavorable(s) · {favorables} favorable(s) · {partiels} partielle(s)"
    ]

    if defavorables > favorables:
        facteurs.append("Tendance jurisprudentielle défavorable sur ce type de litige")
    elif favorables > defavorables:
        facteurs.append("Tendance jurisprudentielle favorable — précédents positifs disponibles")
    else:
        facteurs.append("Jurisprudence partagée — issue incertaine")

    return {"score": score, "level": level, "facteurs": facteurs}


def calculer_probabilite_succes(precedents: list) -> dict:
    """
    Calcule la probabilité de succès en pourcentage.
    """
    if not precedents:
        return {
            "probability": 0.5,
            "confidence": "faible",
            "base": "estimation par défaut"
        }

    total      = len(precedents)
    favorables = sum(1 for p in precedents if p.get("issue") == "favorable")
    partiels   = sum(1 for p in precedents if p.get("issue") == "partiel")

    proba = (favorables + partiels * 0.5) / total if total > 0 else 0.5
    proba = max(0.05, min(0.95, proba))

    if total >= 6:
        confidence = "élevée"
    elif total >= 3:
        confidence = "modérée"
    else:
        confidence = "faible"

    return {
        "probability": round(proba, 2),
        "confidence": confidence,
        "base": f"{total} précédent(s) · {favorables} favorable(s)"
    }


def generer_synthese_claude(query: str, domaine: str, precedents: list,
                             risk: dict, success: dict) -> dict:
    """
    Génère une synthèse et des recommandations via Claude.
    Retourne un dict JSON structuré.
    """
    contexte_precedents = ""
    for i, p in enumerate(precedents[:5], 1):
        contexte_precedents += (
            f"\n[Précédent {i}] {p.get('titre', 'Sans titre')} "
            f"| {p.get('juridiction', '')} | {p.get('date_dec', '')} "
            f"| Issue : {p.get('issue', 'inconnue')} "
            f"| {p.get('reference', '')}\n"
            f"Résumé : {p.get('contenu', '')[:300]}\n"
        )

    prompt = f"""Tu es Odyxia Droit, assistant juridique IA expert en droit OHADA, CEMAC et africain.

DOSSIER À ANALYSER :
Domaine : {domaine}
Description : {query}

PRÉCÉDENTS JURISPRUDENTIELS SIMILAIRES :
{contexte_precedents if contexte_precedents else "Aucun précédent indexé."}

SCORES CALCULÉS :
- Score de risque : {risk['score']}/100 ({risk['level']})
- Probabilité de succès : {int(success['probability'] * 100)}% (confiance : {success['confidence']})

Génère une analyse prédictive complète en JSON strict (sans markdown, sans backticks) :
{{
  "synthese": "Synthèse juridique de 3-4 phrases — analyse du dossier basée sur les précédents",
  "actions_prioritaires": [
    "Action 1 concrète à mener immédiatement",
    "Action 2",
    "Action 3"
  ],
  "points_vigilance": [
    "Point de vigilance 1 — risque identifié",
    "Point de vigilance 2",
    "Point de vigilance 3"
  ],
  "prochaines_etapes": [
    "Étape 1 procédurale",
    "Étape 2",
    "Étape 3"
  ],
  "alternatives": [
    "Alternative 1 (ex: négociation amiable, médiation OHADA)",
    "Alternative 2"
  ],
  "jurisprudence_cle": [
    "Référence jurisprudentielle clé 1 et son enseignement",
    "Référence 2"
  ]
}}

Réponds UNIQUEMENT avec le JSON. Pas de texte avant ou après."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[PREDICT] JSON parse error : {e}")
        return {
            "synthese": "Analyse générée — veuillez consulter les précédents disponibles.",
            "actions_prioritaires": ["Consulter un spécialiste du domaine"],
            "points_vigilance": ["Données insuffisantes pour une analyse précise"],
            "prochaines_etapes": ["Alimenter la bibliothèque avec plus de jurisprudence"],
            "alternatives": ["Négociation amiable"],
            "jurisprudence_cle": []
        }
    except Exception as e:
        log_erreur("SYNTHESE_CLAUDE", e)
        raise


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@predict_bp.route("/upload_jurisprudence", methods=["POST"])
@jwt_required()
def upload_jurisprudence():
    """
    Upload et indexation d'un document de jurisprudence.
    Sécurité : JWT requis.
    """
    try:
        if "fichier" not in request.files:
            return jsonify({"erreur": "Aucun fichier reçu"}), 400

        fichier  = request.files["fichier"]
        domaine  = request.form.get("domaine", "commercial")
        issue    = request.form.get("issue", "")
        juridiction = request.form.get("juridiction", "")
        reference   = request.form.get("reference", "")
        date_dec    = request.form.get("date_dec", "")
        titre       = request.form.get("titre", fichier.filename.replace(".pdf", ""))

        if not fichier.filename.lower().endswith(".pdf"):
            return jsonify({"erreur": "Format PDF uniquement"}), 400

        # Validation fichier
        header = fichier.read(5)
        fichier.seek(0)
        if header != b'%PDF-':
            return jsonify({"erreur": "Fichier invalide — pas un vrai PDF"}), 400

        fichier.seek(0, 2)
        taille = fichier.tell()
        fichier.seek(0)
        if taille > 30 * 1024 * 1024:
            return jsonify({"erreur": "Fichier trop volumineux — max 30 Mo"}), 400

        import fitz
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            fichier.save(tmp.name)
            tmp_path = tmp.name

        doc = fitz.open(tmp_path)
        texte_complet = ""
        for page in doc:
            texte_complet += page.get_text().strip() + "\n"
        doc.close()
        os.unlink(tmp_path)

        if not texte_complet.strip():
            return jsonify({"erreur": "Impossible d'extraire le texte"}), 400

        texte_limite = texte_complet[:8000]

        doc_id = str(uuid.uuid4())
        supabase.table("jurisprudence_predict").insert({
            "id":          doc_id,
            "titre":       titre[:200],
            "contenu":     texte_limite,
            "domaine":     domaine,
            "issue":       issue,
            "juridiction": juridiction,
            "date_dec":    date_dec if date_dec else None,
            "source":      fichier.filename,
            "reference":   reference,
            "created_at":  datetime.now().isoformat()
        }).execute()

        # Vectorisation en arrière-plan
        threading.Thread(
            target=vectoriser_jurisprudence,
            args=(doc_id,),
            daemon=True
        ).start()

        try:
            from audit_logger import log_audit, ACTION_UPLOAD
            log_audit(ACTION_UPLOAD, {
                "type":      "jurisprudence",
                "fichier":   fichier.filename,
                "domaine":   domaine,
                "issue":     issue,
                "doc_id":    doc_id
            })
        except Exception:
            pass

        return jsonify({
            "succes":   True,
            "message":  f"'{titre}' indexé avec succès",
            "doc_id":   doc_id,
            "domaine":  domaine,
            "issue":    issue
        })

    except Exception as e:
        log_erreur("UPLOAD_JURISPRUDENCE", e)
        return jsonify({"erreur": str(e)}), 500


@predict_bp.route("/liste_jurisprudence", methods=["GET"])
@jwt_required()
def liste_jurisprudence():
    """Liste tous les documents de jurisprudence indexés."""
    try:
        result = supabase.table("jurisprudence_predict").select(
            "id, titre, domaine, issue, juridiction, date_dec, reference, source, created_at"
        ).order("created_at", desc=True).execute()
        return jsonify(result.data)
    except Exception as e:
        log_erreur("LISTE_JURISPRUDENCE", e)
        return jsonify({"erreur": str(e)}), 500


@predict_bp.route("/supprimer_jurisprudence", methods=["DELETE"])
@jwt_required()
def supprimer_jurisprudence():
    """Supprime un document de jurisprudence."""
    try:
        data   = request.json
        doc_id = data.get("id")
        if not doc_id:
            return jsonify({"erreur": "ID manquant"}), 400

        supabase.table("jurisprudence_predict").delete().eq("id", doc_id).execute()

        try:
            from audit_logger import log_audit, ACTION_SUPPRESSION
            log_audit(ACTION_SUPPRESSION, {"type": "jurisprudence", "doc_id": doc_id})
        except Exception:
            pass

        return jsonify({"succes": True, "message": "Document supprimé"})
    except Exception as e:
        log_erreur("SUPPRIMER_JURISPRUDENCE", e)
        return jsonify({"erreur": str(e)}), 500


@predict_bp.route("/analyser", methods=["POST"])
@jwt_required()
def analyser():
    """
    Analyse prédictive complète d'un dossier.
    Pipeline :
      1. Recherche précédents similaires (vectoriel + ilike)
      2. Calcul score de risque
      3. Calcul probabilité de succès
      4. Synthèse Claude avec recommandations
    Sécurité : JWT requis.
    """
    try:
        data    = request.json
        query   = data.get("query", "").strip()
        domaine = data.get("domaine", "")

        if not query:
            return jsonify({"erreur": "Description du dossier requise"}), 400

        if len(query) < 30:
            return jsonify({
                "erreur": "Description trop courte — décrivez les faits et enjeux du dossier"
            }), 400

        # 1. Recherche précédents
        precedents = rechercher_precedents(query, domaine, limite=8)

        # 2. Score de risque
        risk = analyser_risque(query, precedents, domaine)

        # 3. Probabilité de succès
        success = calculer_probabilite_succes(precedents)

        # 4. Synthèse Claude
        recommendations = generer_synthese_claude(
            query, domaine, precedents, risk, success
        )

        try:
            from audit_logger import log_audit, ACTION_PREDICT
            log_audit(ACTION_PREDICT, {
                "domaine":           domaine,
                "precedents_trouves": len(precedents),
                "risk_score":        risk["score"],
                "success_proba":     success["probability"]
            })
        except Exception:
            pass

        return jsonify({
            "succes":             True,
            "domaine":            domaine,
            "precedents_trouves": len(precedents),
            "risk":               risk,
            "success":            success,
            "recommendations":    recommendations,
            "precedents":         [
                {
                    "titre":       p.get("titre", ""),
                    "juridiction": p.get("juridiction", ""),
                    "date_dec":    p.get("date_dec", ""),
                    "issue":       p.get("issue", ""),
                    "reference":   p.get("reference", "")
                }
                for p in precedents
            ]
        })

    except Exception as e:
        log_erreur("ANALYSER", e)
        return jsonify({"erreur": str(e)}), 500


@predict_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    """Statistiques de la bibliothèque jurisprudentielle."""
    try:
        result = supabase.table("jurisprudence_predict").select(
            "domaine, issue"
        ).execute()

        docs = result.data
        total = len(docs)

        par_domaine = {}
        par_issue   = {"favorable": 0, "defavorable": 0, "partiel": 0, "": 0}

        for d in docs:
            dom = d.get("domaine", "autre")
            par_domaine[dom] = par_domaine.get(dom, 0) + 1
            iss = d.get("issue", "")
            par_issue[iss] = par_issue.get(iss, 0) + 1

        return jsonify({
            "total":       total,
            "par_domaine": par_domaine,
            "par_issue":   par_issue
        })
    except Exception as e:
        log_erreur("STATS", e)
        return jsonify({"erreur": str(e)}), 500


