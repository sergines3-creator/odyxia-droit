#!/usr/bin/env python3
# indexer_corpus_ohada.py
# Indexation du corpus juridique africain multi-pays dans odyxia_base
#
# Usage :
#   python3 indexer_corpus_ohada.py                  # Indexer tous les PDFs du dossier corpus/
#   python3 indexer_corpus_ohada.py --dry-run        # Simulation sans écriture
#   python3 indexer_corpus_ohada.py --fichier AUDCG-2010_fr.pdf  # Un seul fichier

import os
import re
import uuid
import hashlib
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
TENANT_OHADA   = "00000000-0000-0000-0000-000000000001"
CORPUS_DIR     = Path("/root/odyxia-droit/corpus")
BATCH_SUPABASE = 50
TAILLE_CHUNK   = 400
OVERLAP_CHUNK  = 50
QUALITE_MIN    = 100  # chars/page minimum pour considérer le PDF lisible

# ── Classification automatique par pays et type ────────────────────────────
CATALOGUE = {
    # Actes Uniformes OHADA — tous pays
    "AUDCG-2010_fr.pdf": {
        "nom": "Acte Uniforme OHADA - Droit Commercial General (AUDCG) 2010",
        "pays": "ALL", "type": "acte_uniforme_ohada", "domaine": "droit_commercial"
    },
    "AUPSRVE-2023_fr.pdf": {
        "nom": "Acte Uniforme OHADA - Procedures Simplifiees de Recouvrement (AUPSRVE) 2023",
        "pays": "ALL", "type": "acte_uniforme_ohada", "domaine": "recouvrement"
    },
    "AUCTMR-2003_fr.pdf": {
        "nom": "Acte Uniforme OHADA - Contrat de Transport de Marchandises par Route (AUCTMR) 2003",
        "pays": "ALL", "type": "acte_uniforme_ohada", "domaine": "transport"
    },
    "AUM-2017_fr.pdf": {
        "nom": "Acte Uniforme OHADA - Mediation (AUM) 2017",
        "pays": "ALL", "type": "acte_uniforme_ohada", "domaine": "mediation"
    },
    "SYCEBNL-2022_fr.pdf": {
        "nom": "Acte Uniforme OHADA - Systeme Comptable des Entites a But Non Lucratif (SYCEBNL) 2022",
        "pays": "ALL", "type": "acte_uniforme_ohada", "domaine": "comptabilite"
    },
    "Injonction_de_payer.pdf": {
        "nom": "Procedure d Injonction de Payer - OHADA",
        "pays": "ALL", "type": "procedure_ohada", "domaine": "recouvrement"
    },
    "MEDIATION Fr.pdf": {
        "nom": "Guide Pratique de la Mediation en Afrique",
        "pays": "ALL", "type": "guide_pratique", "domaine": "mediation"
    },

    # Cameroun
    "LOI-DE-FINANCES-2025.pdf": {
        "nom": "Loi de Finances Cameroun 2025",
        "pays": "CM", "type": "loi_nationale", "domaine": "finances_publiques"
    },
    "Loi-de-Finances-Cameroun-2022.pdf": {
        "nom": "Loi de Finances Cameroun 2022",
        "pays": "CM", "type": "loi_nationale", "domaine": "finances_publiques"
    },
    "LOI-PECHE-CAMEROUN-2024-2.pdf": {
        "nom": "Loi sur la Peche au Cameroun 2024",
        "pays": "CM", "type": "loi_nationale", "domaine": "droit_rural"
    },
    "Le droit pénal camerounais et la criminalité internationale.pdf": {
        "nom": "Droit Penal Camerounais et Criminalite Internationale",
        "pays": "CM", "type": "doctrine", "domaine": "droit_penal"
    },
    "DECENTRALISATION.pdf": {
        "nom": "Loi sur la Decentralisation au Cameroun",
        "pays": "CM", "type": "loi_nationale", "domaine": "droit_administratif"
    },

    # Gabon
    "CONSTITUTION DE LA REPUBLIQUE GABONAISE.pdf": {
        "nom": "Constitution de la Republique Gabonaise",
        "pays": "GA", "type": "constitution", "domaine": "droit_constitutionnel"
    },

    # Rwanda
    "Rwanda-Loi-2008-05-arbitrage-et-mediation-commerciale.pdf": {
        "nom": "Loi Rwanda 2008 sur l Arbitrage et la Mediation Commerciale",
        "pays": "RW", "type": "loi_nationale", "domaine": "arbitrage"
    },

    # CEMAC (zone)
    "DIRECTIVE-CEMAC-LOI-DE-FINANCES.pdf": {
        "nom": "Directive CEMAC sur la Loi de Finances",
        "pays": "CEMAC", "type": "directive_cemac", "domaine": "finances_publiques"
    },
    "DIRECTIVE-CEMAC-COMPTABILITE-PUBLIQUE.pdf": {
        "nom": "Directive CEMAC sur la Comptabilite Publique",
        "pays": "CEMAC", "type": "directive_cemac", "domaine": "comptabilite"
    },
    "DIRECTIVE-CEMAC-NOMENCLATURE-BUDGETAIRE.pdf": {
        "nom": "Directive CEMAC sur la Nomenclature Budgetaire",
        "pays": "CEMAC", "type": "directive_cemac", "domaine": "finances_publiques"
    },
    "DIRECTIVE-CEMAC-PLAN-COMPTABLE.pdf": {
        "nom": "Directive CEMAC sur le Plan Comptable de l Etat",
        "pays": "CEMAC", "type": "directive_cemac", "domaine": "comptabilite"
    },
    "DIRECTIVE-CEMAC-TRANSPARENCE-DANS-LES-FINANCES-PUBLIQUES.pdf": {
        "nom": "Directive CEMAC sur la Transparence dans les Finances Publiques",
        "pays": "CEMAC", "type": "directive_cemac", "domaine": "finances_publiques"
    },
}


def verifier_qualite_pdf(chemin: Path) -> dict:
    """Vérifie la qualité du texte extrait du PDF."""
    try:
        import fitz
        doc = fitz.open(str(chemin))
        nb_pages = len(doc)
        chars_total = 0
        pages_vides = 0

        for page in doc:
            texte = page.get_text().strip()
            chars_total += len(texte)
            if len(texte) < 50:
                pages_vides += 1

        doc.close()
        chars_par_page = chars_total // nb_pages if nb_pages else 0
        pct_vides = (pages_vides / nb_pages * 100) if nb_pages else 100

        if chars_par_page >= 300:
            qualite = "EXCELLENT"
        elif chars_par_page >= 150:
            qualite = "BON"
        elif chars_par_page >= 50:
            qualite = "MOYEN"
        else:
            qualite = "MAUVAIS"

        return {
            "qualite": qualite,
            "chars_par_page": chars_par_page,
            "nb_pages": nb_pages,
            "pct_pages_vides": round(pct_vides, 1),
            "lisible": chars_par_page >= QUALITE_MIN
        }
    except Exception as e:
        return {"qualite": "ERREUR", "lisible": False, "erreur": str(e)}


def extraire_texte(chemin: Path) -> list:
    """Extrait le texte page par page — avec fallback OCR si PDF image."""
    try:
        import fitz
        doc = fitz.open(str(chemin))
        pages = []
        nb_pages = len(doc)

        # Vérifier si le PDF est une image (0 chars)
        chars_total = sum(len(p.get_text().strip()) for p in doc)
        besoin_ocr  = (chars_total / nb_pages < 30) if nb_pages else True

        if besoin_ocr:
            print(f"  [OCR] PDF image détecté — activation Tesseract...")
            try:
                import pytesseract
                from PIL import Image
                doc2 = fitz.open(str(chemin))
                for i, page in enumerate(doc2):
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    texte_ocr = pytesseract.image_to_string(img, lang="fra+eng").strip()
                    if texte_ocr and len(texte_ocr) > 50:
                        pages.append({"page": i + 1, "texte": texte_ocr})
                    if (i + 1) % 10 == 0:
                        print(f"  [OCR] {i+1}/{nb_pages} pages traitées...")
                doc2.close()
            except ImportError:
                print(f"  [WARN] pytesseract non disponible — OCR ignoré")
            except Exception as e_ocr:
                print(f"  [WARN] OCR erreur : {e_ocr}")
        else:
            for i, page in enumerate(doc):
                texte = page.get_text().strip()
                if texte and len(texte) > 50:
                    pages.append({"page": i + 1, "texte": texte})

        doc.close()
        return pages
    except Exception as e:
        print(f"  [ERREUR] Extraction : {e}")
        return []


def chunker_semantique(texte: str, taille: int = TAILLE_CHUNK,
                        overlap: int = OVERLAP_CHUNK) -> list:
    """Chunking sémantique avec chevauchement."""
    texte = re.sub(r'\n{3,}', '\n\n', texte)
    texte = re.sub(r' {2,}', ' ', texte)
    paragraphes = [p.strip() for p in texte.split('\n\n') if p.strip()]
    if not paragraphes:
        paragraphes = [texte.strip()]

    chunks, buffer, nb = [], [], 0
    for para in paragraphes:
        mots = para.split()
        if nb + len(mots) > taille and buffer:
            ct = ' '.join(buffer)
            if len(ct) > 80:
                chunks.append(ct)
            buffer = buffer[-overlap:] if overlap else []
            nb = len(buffer)
        buffer += mots
        nb += len(mots)

    if buffer:
        ct = ' '.join(buffer)
        if len(ct) > 80:
            chunks.append(ct)
    return chunks


def vectoriser_batch(model, textes: list) -> list:
    """Vectorise un batch de textes avec SBERT."""
    try:
        embeddings = model.encode(
            [t[:512] for t in textes],
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False
        )
        return [e.tolist() for e in embeddings]
    except Exception as e:
        print(f"  [ERREUR] SBERT : {e}")
        return [None] * len(textes)


def indexer_fichier(supabase, model, chemin: Path, meta: dict,
                     dry_run: bool = False) -> int:
    """Indexe un fichier PDF dans odyxia_base."""

    # Hash du fichier
    with open(chemin, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    # Vérifier doublon
    if not dry_run:
        check = supabase.table("documents").select("id").eq(
            "file_hash_sha256", file_hash
        ).eq("tenant_id", TENANT_OHADA).execute()
        if check.data:
            print(f"  [SKIP] Déjà indexé")
            return 0

    # Extraction texte
    pages = extraire_texte(chemin)
    if not pages:
        print(f"  [SKIP] Aucun texte extractible")
        return 0

    # Créer le document dans Supabase
    doc_id = str(uuid.uuid4())
    if not dry_run:
        supabase.table("documents").insert({
            "id"                : doc_id,
            "tenant_id"         : TENANT_OHADA,
            "filename"          : chemin.name,
            "original_filename" : chemin.name,
            "nom"               : meta["nom"],
            "type"              : meta["type"],
            "mime_type"         : "application/pdf",
            "file_size_bytes"   : chemin.stat().st_size,
            "file_hash_sha256"  : file_hash,
            "status"            : "ready",
            "storage_tier"      : "hot",
            "ocr_status"        : "done",
            "scan_status"       : "clean",
            "metadata"          : {
                "pays"   : meta["pays"],
                "type"   : meta["type"],
                "domaine": meta["domaine"],
                "source" : "corpus_ohada"
            }
        }).execute()

    # Chunking et vectorisation
    tous_chunks = []
    idx_global  = 0
    for page_data in pages:
        chunks_texte = chunker_semantique(page_data["texte"])
        for chunk_texte in chunks_texte:
            tous_chunks.append({
                "texte"  : chunk_texte,
                "page"   : page_data["page"],
                "idx"    : idx_global
            })
            idx_global += 1

    # Vectorisation par batch
    textes = [c["texte"] for c in tous_chunks]
    embeddings = vectoriser_batch(model, textes)

    # Insertion Supabase par batch
    if not dry_run:
        for i in range(0, len(tous_chunks), BATCH_SUPABASE):
            lot = tous_chunks[i:i + BATCH_SUPABASE]
            lot_emb = embeddings[i:i + BATCH_SUPABASE]
            to_insert = []
            for chunk, emb in zip(lot, lot_emb):
                to_insert.append({
                    "tenant_id"    : TENANT_OHADA,
                    "document_id"  : doc_id,
                    "content"      : chunk["texte"],
                    "contenu"      : chunk["texte"],
                    "contenu_index": chunk["texte"],
                    "page_number"  : chunk["page"],
                    "page_numero"  : chunk["page"],
                    "chunk_index"  : chunk["idx"],
                    "source_type"  : "legal_act",
                    "embedding"    : emb,
                    "metadata"     : {
                        "pays"   : meta["pays"],
                        "type"   : meta["type"],
                        "domaine": meta["domaine"],
                        "source" : "corpus_ohada"
                    }
                })
            supabase.table("chunks").insert(to_insert).execute()

    return len(tous_chunks)


def main():
    parser = argparse.ArgumentParser(
        description="Indexation corpus OHADA multi-pays dans odyxia_base"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation sans écriture")
    parser.add_argument("--fichier", type=str, default=None,
                        help="Indexer un seul fichier")
    args = parser.parse_args()

    if args.dry_run:
        print("\n  [DRY-RUN] Simulation — aucune écriture\n")

    # Connexions
    from supabase import create_client
    from sentence_transformers import SentenceTransformer

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("[SBERT] Chargement...")
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    print(f"[SBERT] Prêt — dim={model.get_sentence_embedding_dimension()}\n")

    # Fichiers à traiter
    if args.fichier:
        fichiers = [Path(args.fichier) if Path(args.fichier).is_absolute()
                    else CORPUS_DIR / args.fichier]
    else:
        fichiers = list(CORPUS_DIR.glob("*.pdf"))

    print("=" * 65)
    print("  INDEXATION CORPUS OHADA MULTI-PAYS")
    print("=" * 65)
    print(f"  Fichiers à traiter : {len(fichiers)}")
    print(f"  Tenant             : odyxia_base")
    print()

    total_chunks = 0
    resultats    = []

    for chemin in sorted(fichiers):
        nom_fichier = chemin.name
        meta = CATALOGUE.get(nom_fichier)

        if not meta:
            print(f"  [IGNORE] {nom_fichier} — non dans le catalogue")
            continue

        print(f"  Traitement : {nom_fichier}")
        print(f"  → {meta['nom']} | Pays: {meta['pays']} | Domaine: {meta['domaine']}")

        # Vérification qualité
        qualite = verifier_qualite_pdf(chemin)
        print(f"  → Qualité: {qualite['qualite']} ({qualite.get('chars_par_page',0)} chars/page, {qualite.get('nb_pages',0)} pages)")

        if not qualite["lisible"]:
            print(f"  [SKIP] Document non lisible — moins de {QUALITE_MIN} chars/page\n")
            resultats.append({"fichier": nom_fichier, "statut": "SKIP_QUALITE", "chunks": 0})
            continue

        # Indexation
        t0 = time.time()
        nb = indexer_fichier(supabase, model, chemin, meta, args.dry_run)
        duree = time.time() - t0

        total_chunks += nb
        resultats.append({"fichier": nom_fichier, "statut": "OK", "chunks": nb})
        print(f"  ✓ {nb} chunks indexés en {duree:.1f}s\n")

    # Rapport final
    print("=" * 65)
    print("  RAPPORT FINAL")
    print("=" * 65)
    print(f"  {'FICHIER':<55} {'STATUT':<10} {'CHUNKS':>6}")
    print(f"  {'-'*55} {'-'*10} {'-'*6}")
    for r in resultats:
        print(f"  {r['fichier'][:55]:<55} {r['statut']:<10} {r['chunks']:>6}")
    print(f"  {'-'*55} {'-'*10} {'-'*6}")
    print(f"  {'TOTAL':<55} {'':10} {total_chunks:>6}")
    print()
    if not args.dry_run:
        print(f"  {total_chunks} chunks indexés dans odyxia_base")
    else:
        print(f"  DRY-RUN — rien n'a été écrit")


if __name__ == "__main__":
    main()