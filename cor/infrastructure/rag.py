# COUCHE INFRASTRUCTURE — infrastructure/rag.py
#
# Moteur RAG (Retrieval-Augmented Generation) pour COR.
# Base vectorielle ChromaDB + embeddings multilingues sentence-transformers.
#
# Responsabilité :
#   Indexer des textes juridiques (texte brut ou PDF),
#   les retrouver par similarité sémantique,
#   et filtrer par pays / domaine.
#
# Aucun import Flask. Aucune logique d'inférence Cor ici.

import os
import re
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dossier de persistance ChromaDB (dans le projet, pas dans /tmp)
CHROMA_DIR   = os.path.join(_PROJET, "data", "chroma_db")
COLLECTION   = "cor_juridique"

# Seuil de similarité cosinus — sous ce seuil, le passage est ignoré
# ChromaDB retourne des distances (0 = identique, 2 = opposé pour cosinus)
# distance = 1 - cosine_similarity  →  distance < 0.55 ≈ similarity > 0.45
SEUIL_DISTANCE = 0.55

# Taille des chunks pour l'indexation de PDF (en caractères ≈ tokens)
CHUNK_TAILLE   = 1800   # ≈ 500 tokens à ~3.6 chars/token pour le français
CHUNK_OVERLAP  = 180    # ≈ 50 tokens de chevauchement

# Modèle d'embedding — multilingue, supporte le français africain
MODELE_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"


# ── Initialisation lazy ────────────────────────────────────────────────────────

_client     = None
_collection = None
_ef         = None   # embedding function


def _init():
    """Initialise ChromaDB et la fonction d'embedding (appelé une seule fois)."""
    global _client, _collection, _ef

    if _client is not None:
        return

    try:
        import chromadb
        from chromadb.utils import embedding_functions as ef_utils
    except ImportError as e:
        raise ImportError(
            "chromadb et sentence-transformers sont requis pour le RAG.\n"
            "  pip install chromadb sentence-transformers"
        ) from e

    os.makedirs(CHROMA_DIR, exist_ok=True)

    _client = chromadb.PersistentClient(path=CHROMA_DIR)

    _ef = ef_utils.SentenceTransformerEmbeddingFunction(
        model_name=MODELE_EMBEDDING
    )

    _collection = _client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=_ef,
        metadata={"hnsw:space": "cosine"},
    )

    logger.info(f"[RAG] ChromaDB initialisé ({CHROMA_DIR}), {_collection.count()} documents")


def _get_collection():
    _init()
    return _collection


# ── Helpers internes ───────────────────────────────────────────────────────────

def _chunks(texte: str, taille: int = CHUNK_TAILLE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Découpe un texte en chunks avec chevauchement.
    Essaie de couper aux limites de phrase (. ! ?) plutôt qu'en milieu de mot.
    """
    if len(texte) <= taille:
        return [texte.strip()] if texte.strip() else []

    morceaux = []
    debut    = 0

    while debut < len(texte):
        fin = debut + taille

        if fin < len(texte):
            # Chercher la dernière limite de phrase avant `fin`
            limite = max(
                texte.rfind(".", debut, fin),
                texte.rfind("!", debut, fin),
                texte.rfind("?", debut, fin),
                texte.rfind("\n", debut, fin),
            )
            if limite > debut + taille // 2:
                fin = limite + 1

        morceau = texte[debut:fin].strip()
        if morceau:
            morceaux.append(morceau)

        debut = fin - overlap if fin < len(texte) else len(texte)

    return morceaux


def _id_document(texte: str) -> str:
    """Génère un ID déterministe basé sur le contenu (SHA-256 tronqué)."""
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


def _nettoyer_texte(texte: str) -> str:
    """Supprime les espaces multiples et les caractères de contrôle."""
    texte = re.sub(r"\r\n|\r", "\n", texte)
    texte = re.sub(r"[ \t]{2,}", " ", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return texte.strip()


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── API publique ───────────────────────────────────────────────────────────────

def indexer_document(
    texte     : str,
    metadata  : dict,
    doc_id    : Optional[str] = None,
) -> dict:
    """
    Indexe un texte juridique dans la base vectorielle.

    Args:
        texte    : texte complet du document
        metadata : dict avec les clés suivantes (toutes optionnelles sauf pays) :
                   - pays     : "[CM]", "[GA]", "[BJ]", "[CI]", "OHADA", etc.
                   - domaine  : "droit_travail", "droit_commercial", etc.
                   - source   : "OHADA.com", "JO Cameroun 2023", etc.
                   - titre    : titre court du document (optionnel)
        doc_id   : identifiant unique (généré si absent)

    Returns:
        dict avec nb_chunks, doc_id, statut
    """
    col = _get_collection()

    texte = _nettoyer_texte(texte)
    if not texte:
        return {"erreur": "Texte vide après nettoyage", "nb_chunks": 0}

    if doc_id is None:
        doc_id = _id_document(texte)

    morceaux = _chunks(texte)
    if not morceaux:
        return {"erreur": "Texte trop court pour être indexé", "nb_chunks": 0}

    # Métadonnées par défaut
    meta_base = {
        "pays"       : str(metadata.get("pays", "inconnu")),
        "domaine"    : str(metadata.get("domaine", "general")),
        "source"     : str(metadata.get("source", "")),
        "titre"      : str(metadata.get("titre", "")),
        "date_ajout" : _maintenant(),
        "doc_id"     : doc_id,
        "nb_chunks"  : len(morceaux),
    }

    ids      = [f"{doc_id}_c{i}" for i in range(len(morceaux))]
    metadatas = [{**meta_base, "chunk_index": i} for i in range(len(morceaux))]

    # Supprimer les anciens chunks du même doc_id si présents
    try:
        existants = col.get(where={"doc_id": doc_id}, include=[])
        if existants["ids"]:
            col.delete(ids=existants["ids"])
    except Exception:
        pass

    col.add(
        documents = morceaux,
        metadatas = metadatas,
        ids       = ids,
    )

    logger.info(f"[RAG] Indexé : {doc_id} ({len(morceaux)} chunks, pays={meta_base['pays']})")

    return {
        "doc_id"    : doc_id,
        "nb_chunks" : len(morceaux),
        "statut"    : "indexé",
        "pays"      : meta_base["pays"],
        "domaine"   : meta_base["domaine"],
    }


def indexer_pdf(chemin_pdf: str, metadata: Optional[dict] = None) -> dict:
    """
    Extrait le texte d'un PDF et l'indexe par chunks.

    Args:
        chemin_pdf : chemin absolu ou relatif vers le fichier PDF
        metadata   : même structure que indexer_document()

    Returns:
        dict avec nb_chunks, doc_id, statut, nb_pages
    """
    if not os.path.exists(chemin_pdf):
        return {"erreur": f"Fichier introuvable : {chemin_pdf}"}

    try:
        import pypdf
    except ImportError:
        try:
            import PyPDF2 as pypdf
        except ImportError:
            return {
                "erreur": (
                    "pypdf (ou PyPDF2) est requis pour lire les PDFs.\n"
                    "  pip install pypdf"
                )
            }

    texte_complet = []
    nb_pages      = 0

    try:
        with open(chemin_pdf, "rb") as f:
            lecteur = pypdf.PdfReader(f)
            nb_pages = len(lecteur.pages)

            for page in lecteur.pages:
                texte_page = page.extract_text() or ""
                if texte_page.strip():
                    texte_complet.append(texte_page)
    except Exception as e:
        return {"erreur": f"Erreur lecture PDF : {e}"}

    if not texte_complet:
        return {"erreur": "PDF sans texte extractible (image scannée ?)"}

    texte = "\n\n".join(texte_complet)

    # Titre par défaut = nom du fichier sans extension
    nom_fichier = os.path.splitext(os.path.basename(chemin_pdf))[0]

    meta = metadata or {}
    if not meta.get("titre"):
        meta["titre"] = nom_fichier
    if not meta.get("source"):
        meta["source"] = nom_fichier

    doc_id = _id_document(texte)
    result = indexer_document(texte, meta, doc_id=doc_id)
    result["nb_pages"] = nb_pages

    return result


def rechercher(
    question  : str,
    pays      : Optional[str] = None,
    domaine   : Optional[str] = None,
    k         : int           = 5,
) -> list[dict]:
    """
    Recherche les passages les plus pertinents pour une question.

    Args:
        question : question en langue naturelle
        pays     : filtre optionnel sur le pays ("[CM]", "[GA]", etc.)
        domaine  : filtre optionnel sur le domaine juridique
        k        : nombre maximum de résultats (avant filtrage par seuil)

    Returns:
        Liste de dicts { texte, score, pays, domaine, source, doc_id }
        Liste vide si aucun passage ne dépasse le seuil de pertinence.
    """
    col = _get_collection()

    if col.count() == 0:
        return []

    # Construire le filtre ChromaDB (clause $and si plusieurs critères)
    where = None
    filtres = []

    if pays:
        filtres.append({"pays": {"$eq": pays}})
    if domaine:
        filtres.append({"domaine": {"$eq": domaine}})

    if len(filtres) == 1:
        where = filtres[0]
    elif len(filtres) > 1:
        where = {"$and": filtres}

    try:
        kwargs = {
            "query_texts": [question],
            "n_results"  : min(k, col.count()),
            "include"    : ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        resultats = col.query(**kwargs)
    except Exception as e:
        logger.error(f"[RAG] Erreur recherche : {e}")
        return []

    passages = []

    docs      = resultats.get("documents", [[]])[0]
    metas     = resultats.get("metadatas", [[]])[0]
    distances = resultats.get("distances", [[]])[0]

    for texte, meta, dist in zip(docs, metas, distances):
        if dist > SEUIL_DISTANCE:
            continue  # passage non pertinent

        score = round(1.0 - dist, 4)  # convertir distance → similarité

        passages.append({
            "texte"   : texte,
            "score"   : score,
            "pays"    : meta.get("pays", ""),
            "domaine" : meta.get("domaine", ""),
            "source"  : meta.get("source", ""),
            "titre"   : meta.get("titre", ""),
            "doc_id"  : meta.get("doc_id", ""),
        })

    # Trier par score décroissant (meilleur en premier)
    passages.sort(key=lambda x: x["score"], reverse=True)

    return passages


def supprimer_document(doc_id: str) -> dict:
    """
    Supprime tous les chunks associés à un doc_id.

    Returns:
        dict avec nb_supprimés et statut
    """
    col = _get_collection()

    try:
        existants = col.get(where={"doc_id": doc_id}, include=[])
        ids = existants.get("ids", [])

        if not ids:
            return {"erreur": f"Document introuvable : {doc_id}", "nb_supprimes": 0}

        col.delete(ids=ids)

        logger.info(f"[RAG] Supprimé : {doc_id} ({len(ids)} chunks)")

        return {
            "doc_id"       : doc_id,
            "nb_supprimes" : len(ids),
            "statut"       : "supprimé",
        }

    except Exception as e:
        return {"erreur": f"Erreur suppression : {e}"}


def lister_documents() -> list[dict]:
    """
    Retourne la liste des documents indexés (un dict par document, pas par chunk).

    Returns:
        Liste triée par date d'ajout décroissante.
        Chaque entrée : { doc_id, titre, pays, domaine, source, date_ajout, nb_chunks }
    """
    col = _get_collection()

    try:
        tous = col.get(include=["metadatas"])
    except Exception as e:
        logger.error(f"[RAG] Erreur listing : {e}")
        return []

    # Dédupliquer par doc_id — garder uniquement le chunk 0 de chaque document
    vus    = {}
    for meta in tous.get("metadatas", []):
        did = meta.get("doc_id", "")
        # Chunk index 0 porte les infos canoniques du document
        if did and (did not in vus or meta.get("chunk_index", 1) == 0):
            vus[did] = {
                "doc_id"     : did,
                "titre"      : meta.get("titre", ""),
                "pays"       : meta.get("pays", ""),
                "domaine"    : meta.get("domaine", ""),
                "source"     : meta.get("source", ""),
                "date_ajout" : meta.get("date_ajout", ""),
                "nb_chunks"  : meta.get("nb_chunks", 1),
            }

    docs = sorted(vus.values(), key=lambda d: d["date_ajout"], reverse=True)

    return docs


def stats() -> dict:
    """
    Retourne les statistiques de la base vectorielle.

    Returns:
        dict avec nb_chunks_total, nb_documents, répartition par pays et domaine
    """
    col = _get_collection()

    try:
        tous = col.get(include=["metadatas"])
    except Exception as e:
        return {"erreur": str(e)}

    metadatas = tous.get("metadatas", [])

    # Compter les documents uniques
    doc_ids = {m.get("doc_id", "") for m in metadatas if m.get("doc_id")}

    # Répartition par pays
    par_pays = {}
    for m in metadatas:
        if m.get("chunk_index", 1) == 0:  # un seul chunk par document pour le comptage
            p = m.get("pays", "inconnu")
            par_pays[p] = par_pays.get(p, 0) + 1

    # Répartition par domaine
    par_domaine = {}
    for m in metadatas:
        if m.get("chunk_index", 1) == 0:
            d = m.get("domaine", "general")
            par_domaine[d] = par_domaine.get(d, 0) + 1

    return {
        "nb_chunks_total"  : len(metadatas),
        "nb_documents"     : len(doc_ids),
        "par_pays"         : par_pays,
        "par_domaine"      : par_domaine,
        "modele_embedding" : MODELE_EMBEDDING,
        "seuil_distance"   : SEUIL_DISTANCE,
        "chroma_dir"       : CHROMA_DIR,
    }
