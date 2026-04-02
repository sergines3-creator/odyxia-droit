"""
embeddings_voyage.py — Themis
Pipeline de vectorisation par lots avec Voyage AI (voyage-law-2)
Chunking intelligent : découpe aux frontières juridiques (articles, alinéas, sections)
Sécurité : clés via variables d'environnement uniquement
"""

import os
import re
import time
import json
import requests
from typing import Optional
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SUPABASE_URL    = os.environ.get("SUPABASE_URL")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY")
VOYAGE_API_KEY  = os.environ.get("VOYAGE_API_KEY")
VOYAGE_MODEL    = "voyage-law-2"
VOYAGE_URL      = "https://api.voyageai.com/v1/embeddings"
VOYAGE_DIM      = 1024
BATCH_SIZE      = 50       # Voyage AI accepte jusqu'à 128 textes/requête
CHUNK_SIZE      = 800      # Taille cible par chunk (caractères)
CHUNK_OVERLAP   = 100      # Chevauchement entre chunks
DELAI_INTER_LOT = 0.3      # Secondes entre lots (rate limiting)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── CHUNKING INTELLIGENT ─────────────────────────────────────────────────────
# Séparateurs juridiques par ordre de priorité
SEPARATEURS_JURIDIQUES = [
    r'\n(?=Article\s+\d+)',           # Article 1, Article 2...
    r'\n(?=ARTICLE\s+\d+)',           # ARTICLE 1...
    r'\n(?=Art\.\s*\d+)',             # Art. 1...
    r'\n(?=Alinéa\s+\d+)',            # Alinéa 1...
    r'\n(?=Section\s+[IVX\d]+)',      # Section I, Section 1...
    r'\n(?=SECTION\s+[IVX\d]+)',      # SECTION I...
    r'\n(?=Chapitre\s+[IVX\d]+)',     # Chapitre I...
    r'\n(?=CHAPITRE\s+[IVX\d]+)',     # CHAPITRE I...
    r'\n(?=Titre\s+[IVX\d]+)',        # Titre I...
    r'\n(?=TITRE\s+[IVX\d]+)',        # TITRE I...
    r'\n(?=§\s*\d+)',                 # § 1, § 2...
    r'\n(?=\d+\.\s+[A-Z])',           # 1. Définitions...
    r'\n(?=[A-Z]{3,})',               # Titres en majuscules
    r'\n\n',                          # Double saut de ligne
    r'\n',                            # Saut de ligne simple
]


def chunking_intelligent(texte: str, taille_max: int = CHUNK_SIZE,
                          overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Découpe un texte juridique en chunks aux frontières logiques.
    Respecte la structure : articles, sections, alinéas, chapitres.
    """
    if not texte or not texte.strip():
        return []

    # Si le texte est court, retourner tel quel
    if len(texte) <= taille_max:
        return [texte.strip()]

    chunks = []

    # Tentative de découpe aux frontières juridiques
    for separateur in SEPARATEURS_JURIDIQUES:
        parties = re.split(separateur, texte)
        if len(parties) > 1:
            # Regrouper les parties courtes
            chunk_courant = ""
            for partie in parties:
                partie = partie.strip()
                if not partie:
                    continue
                if len(chunk_courant) + len(partie) <= taille_max:
                    chunk_courant += "\n" + partie if chunk_courant else partie
                else:
                    if chunk_courant:
                        chunks.append(chunk_courant.strip())
                        # Overlap : ajouter fin du chunk précédent au début du suivant
                        if overlap > 0 and len(chunk_courant) > overlap:
                            chunk_courant = chunk_courant[-overlap:] + "\n" + partie
                        else:
                            chunk_courant = partie
                    else:
                        # Partie trop longue — découpe forcée
                        for i in range(0, len(partie), taille_max - overlap):
                            sous_chunk = partie[i:i + taille_max].strip()
                            if sous_chunk:
                                chunks.append(sous_chunk)
                        chunk_courant = ""

            if chunk_courant.strip():
                chunks.append(chunk_courant.strip())

            if chunks:
                return [c for c in chunks if len(c) >= 30]

    # Fallback : découpe par taille fixe avec overlap
    for i in range(0, len(texte), taille_max - overlap):
        chunk = texte[i:i + taille_max].strip()
        if len(chunk) >= 30:
            chunks.append(chunk)

    return chunks


def extraire_index_recherche(texte: str) -> str:
    """
    Extrait les mots-clés pour l'index de recherche textuelle.
    Filtre les mots vides juridiques.
    """
    MOTS_VIDES = {
        "le", "la", "les", "un", "une", "des", "du", "de", "et", "en",
        "au", "aux", "ce", "se", "sa", "son", "ses", "mon", "ma", "mes",
        "par", "sur", "sous", "dans", "avec", "pour", "que", "qui", "quoi",
        "dont", "vers", "mais", "ou", "donc", "or", "ni", "car", "plus",
        "tout", "tous", "cette", "cet", "ces", "leur", "leurs", "meme",
        "ainsi", "alors", "aussi", "comme", "selon", "entre", "est", "sont",
        "être", "avoir", "fait", "faire", "peut", "doit", "lors", "tant"
    }

    texte_clean = re.sub(r'[^\w\s]', ' ', texte.lower())
    texte_clean = re.sub(r'\d+', ' ', texte_clean)
    mots = texte_clean.split()

    vus = set()
    mots_uniques = []
    for m in mots:
        if len(m) >= 4 and m not in MOTS_VIDES and m not in vus:
            vus.add(m)
            mots_uniques.append(m)

    return " ".join(mots_uniques[:120])


# ─── VOYAGE AI ────────────────────────────────────────────────────────────────

def get_embeddings_batch(textes: list[str],
                         input_type: str = "document") -> Optional[list]:
    """
    Vectorise un lot de textes avec Voyage AI.
    Retourne une liste d'embeddings ou None en cas d'erreur.
    """
    if not textes or not VOYAGE_API_KEY:
        return None

    try:
        textes_propres = [t[:4096] if t else "document juridique" for t in textes]

        res = requests.post(
            VOYAGE_URL,
            headers={
                "Authorization": f"Bearer {VOYAGE_API_KEY}",
                "Content-Type":  "application/json"
            },
            json={
                "input":      textes_propres,
                "model":      VOYAGE_MODEL,
                "input_type": input_type
            },
            timeout=30
        )
        res.raise_for_status()
        data = res.json()
        return [item["embedding"] for item in data["data"]]

    except requests.exceptions.Timeout:
        print("[VOYAGE] Timeout — réessai dans 5s...")
        time.sleep(5)
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            print("[VOYAGE] Rate limit — attente 30s...")
            time.sleep(30)
            return None
        print(f"[VOYAGE] HTTP {e.response.status_code} : {e}")
        return None
    except Exception as e:
        print(f"[VOYAGE] Erreur : {e}")
        return None


def vectoriser_document_complet(document_id: str, verbose: bool = True) -> dict:
    """
    Vectorise tous les chunks non-vectorisés d'un document.
    Traitement par lots de BATCH_SIZE avec gestion des erreurs et retry.

    Retourne : {"traites": N, "erreurs": M, "doc_id": document_id}
    """
    try:
        result = supabase.table("chunks").select(
            "id, contenu, contenu_index"
        ).eq("document_id", document_id).is_("embedding", "null").execute()

        chunks = result.data
        if not chunks:
            if verbose:
                print(f"[VOYAGE] Tous les chunks déjà vectorisés pour {document_id[:8]}")
            return {"traites": 0, "erreurs": 0, "doc_id": document_id}

        total    = len(chunks)
        traites  = 0
        erreurs  = 0

        if verbose:
            print(f"[VOYAGE] Vectorisation : {total} chunks pour {document_id[:8]}...")

        for i in range(0, total, BATCH_SIZE):
            lot = chunks[i:i + BATCH_SIZE]

            textes = []
            for c in lot:
                index = c.get("contenu_index") or c.get("contenu", "")
                if index and index.startswith("ENC:"):
                    index = "document juridique confidentiel"
                textes.append(index.strip() or "document juridique")

            # Retry jusqu'à 3 fois
            embeddings = None
            for tentative in range(3):
                embeddings = get_embeddings_batch(textes, "document")
                if embeddings:
                    break
                print(f"[VOYAGE] Tentative {tentative + 1}/3 échouée pour lot {i // BATCH_SIZE + 1}")
                time.sleep(2 ** tentative)

            if not embeddings:
                erreurs += len(lot)
                print(f"[VOYAGE] Lot {i // BATCH_SIZE + 1} ignoré après 3 tentatives")
                continue

            # Mise à jour Supabase
            for j, chunk in enumerate(lot):
                if j < len(embeddings) and embeddings[j]:
                    try:
                        supabase.table("chunks").update(
                            {"embedding": embeddings[j]}
                        ).eq("id", chunk["id"]).execute()
                        traites += 1
                    except Exception as e:
                        print(f"[VOYAGE] Erreur update chunk {chunk['id'][:8]} : {e}")
                        erreurs += 1

            if verbose:
                print(f"[VOYAGE] Lot {i // BATCH_SIZE + 1}/{(total + BATCH_SIZE - 1) // BATCH_SIZE} — {traites}/{total} traités")

            time.sleep(DELAI_INTER_LOT)

        if verbose:
            print(f"[VOYAGE] Terminé — {traites} vectorisés, {erreurs} erreurs")

        return {"traites": traites, "erreurs": erreurs, "doc_id": document_id}

    except Exception as e:
        print(f"[VOYAGE] Erreur critique : {e}")
        return {"traites": 0, "erreurs": -1, "doc_id": document_id}


def vectoriser_tous_documents(verbose: bool = True) -> dict:
    """
    Vectorise TOUS les chunks non-vectorisés de la base.
    Utile pour une migration ou un premier déploiement.
    """
    try:
        result = supabase.table("chunks").select(
            "document_id"
        ).is_("embedding", "null").execute()

        if not result.data:
            if verbose:
                print("[VOYAGE] Aucun chunk à vectoriser.")
            return {"total": 0, "documents": []}

        # Dédupliquer les document_ids
        doc_ids = list({c["document_id"] for c in result.data})
        total_chunks = len(result.data)

        if verbose:
            print(f"[VOYAGE] {total_chunks} chunks à vectoriser dans {len(doc_ids)} documents")

        resultats = []
        for doc_id in doc_ids:
            r = vectoriser_document_complet(doc_id, verbose=verbose)
            resultats.append(r)

        total_traites = sum(r["traites"] for r in resultats)
        total_erreurs = sum(r["erreurs"] for r in resultats)

        if verbose:
            print(f"\n[VOYAGE] Bilan final : {total_traites} vectorisés, {total_erreurs} erreurs")

        return {
            "total":     total_traites,
            "erreurs":   total_erreurs,
            "documents": resultats
        }

    except Exception as e:
        print(f"[VOYAGE] Erreur vectorisation globale : {e}")
        return {"total": 0, "erreurs": -1, "documents": []}


def chunker_et_inserer(document_id: str, pages_texte: list[dict],
                        est_sensible: bool = False,
                        cabinet: str = "") -> int:
    """
    Découpe intelligemment les pages d'un document et insère les chunks
    dans Supabase avec chiffrement optionnel.
    Retourne le nombre de chunks insérés.
    """
    from encryption import chiffrer, extraire_index

    chunks_inseres = 0

    for page_data in pages_texte:
        texte      = page_data.get("texte", "")
        page_num   = page_data.get("page", 1)

        if not texte.strip():
            continue

        # Chunking intelligent
        chunks = chunking_intelligent(texte, CHUNK_SIZE, CHUNK_OVERLAP)

        for chunk_texte in chunks:
            if len(chunk_texte) < 30:
                continue

            if est_sensible:
                contenu_final = chiffrer(chunk_texte)
                index_final   = extraire_index(chunk_texte)
            else:
                contenu_final = chunk_texte
                index_final   = extraire_index_recherche(chunk_texte)

            try:
                supabase.table("chunks").insert({
                    "document_id":   document_id,
                    "contenu":       contenu_final,
                    "contenu_index": index_final,
                    "page_numero":   page_num,
                    "metadata": {
                        "sensible": est_sensible,
                        "cabinet":  cabinet,
                        "longueur": len(chunk_texte)
                    }
                }).execute()
                chunks_inseres += 1
            except Exception as e:
                print(f"[CHUNKS] Erreur insertion page {page_num} : {e}")

    return chunks_inseres


def get_query_embedding(question: str) -> Optional[list]:
    """
    Vectorise une question utilisateur pour la recherche RAG.
    Input type = 'query' (différent de 'document').
    """
    if not question or not VOYAGE_API_KEY:
        return None

    embeddings = get_embeddings_batch([question[:4096]], input_type="query")
    return embeddings[0] if embeddings else None


def statut_vectorisation(document_id: str = None) -> dict:
    """
    Retourne le statut de vectorisation d'un ou tous les documents.
    """
    try:
        if document_id:
            total_res = supabase.table("chunks").select(
                "id", count="exact"
            ).eq("document_id", document_id).execute()
            vect_res = supabase.table("chunks").select(
                "id", count="exact"
            ).eq("document_id", document_id).not_.is_("embedding", "null").execute()

            total  = total_res.count or 0
            vect   = vect_res.count or 0
            restant = total - vect

            return {
                "document_id": document_id,
                "total":        total,
                "vectorises":   vect,
                "restants":     restant,
                "pct":          round(vect / total * 100, 1) if total > 0 else 0
            }
        else:
            total_res = supabase.table("chunks").select(
                "id", count="exact"
            ).execute()
            vect_res = supabase.table("chunks").select(
                "id", count="exact"
            ).not_.is_("embedding", "null").execute()

            total  = total_res.count or 0
            vect   = vect_res.count or 0

            return {
                "total":      total,
                "vectorises": vect,
                "restants":   total - vect,
                "pct":        round(vect / total * 100, 1) if total > 0 else 0
            }
    except Exception as e:
        print(f"[VOYAGE] Erreur statut : {e}")
        return {"erreur": str(e)}


# ─── SCRIPT STANDALONE ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("Themis — Pipeline de vectorisation Voyage AI")
    print("=" * 60)

    statut = statut_vectorisation()
    print(f"\nStatut actuel :")
    print(f"  Total chunks    : {statut.get('total', 0)}")
    print(f"  Vectorisés      : {statut.get('vectorises', 0)}")
    print(f"  À vectoriser    : {statut.get('restants', 0)}")
    print(f"  Progression     : {statut.get('pct', 0)}%")

    if statut.get('restants', 0) == 0:
        print("\nTous les chunks sont déjà vectorisés.")
        sys.exit(0)

    print(f"\nLancement de la vectorisation...")
    resultat = vectoriser_tous_documents(verbose=True)

    print(f"\nBilan :")
    print(f"  Traités  : {resultat['total']}")
    print(f"  Erreurs  : {resultat['erreurs']}")
    print("=" * 60)
