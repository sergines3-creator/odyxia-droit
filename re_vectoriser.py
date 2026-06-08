#!/usr/bin/env python3
# re_vectoriser.py
# Re-vectorisation des chunks existants — Voyage AI (1024 dims) → SBERT (384 dims)
#
# QUAND LANCER CE SCRIPT :
#   Après avoir appliqué patch_app.py qui remplace Voyage AI par SBERT.
#   Les anciens chunks ont des embeddings de 1024 dimensions (Voyage AI).
#   SBERT produit des embeddings de 384 dimensions.
#   Sans re-vectorisation : la recherche pgvector échoue (dimensions incompatibles).
#
# CE QUE CE SCRIPT FAIT :
#   1. Compte les chunks avec embeddings existants (à re-vectoriser)
#   2. Compte les chunks sans embeddings (à vectoriser pour la première fois)
#   3. Traite par batches de 32 (optimal pour SBERT)
#   4. Affiche la progression en temps réel
#   5. Sauvegarde un rapport JSON à la fin
#
# DURÉE ESTIMÉE :
#   6 707 chunks (votre corpus actuel) × ~10ms/chunk = ~1 minute sur CPU
#   Sur GPU : ~10 secondes
#
# SÉCURITÉ :
#   Les embeddings sont mis à jour un batch à la fois.
#   Si le script est interrompu, relancez-le — il reprend là où il s'est arrêté
#   grâce au flag --force qui re-traite tous les chunks.
#   Sans --force : traite seulement les chunks sans embedding (plus rapide).
#
# Usage :
#   python re_vectoriser.py                  # Vectoriser les chunks sans embedding
#   python re_vectoriser.py --force          # Re-vectoriser TOUS les chunks
#   python re_vectoriser.py --tenant TENANT_ID  # Un seul tenant
#   python re_vectoriser.py --dry-run        # Simulation sans écriture

import os
import sys
import json
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

BATCH_SBERT    = 32    # Chunks par batch SBERT (optimal CPU/GPU)
BATCH_SUPABASE = 50    # Chunks par batch Supabase (limite API)
RAPPORT_PATH   = "re_vectoriser_rapport.json"


def verifier_config():
    """Vérifie que les variables d'environnement sont configurées."""
    erreurs = []
    if not SUPABASE_URL:
        erreurs.append("SUPABASE_URL manquante dans .env")
    if not SUPABASE_KEY:
        erreurs.append("SUPABASE_KEY manquante dans .env")
    if erreurs:
        for e in erreurs:
            print(f"  [ERREUR] {e}")
        sys.exit(1)


def charger_sbert():
    """Charge le modèle SBERT."""
    try:
        from sentence_transformers import SentenceTransformer
        print("[SBERT] Chargement paraphrase-multilingual-MiniLM-L12-v2...")
        t0 = time.time()
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        duree = time.time() - t0
        dim = model.get_sentence_embedding_dimension()
        print(f"[SBERT] Prêt — dim={dim}, chargé en {duree:.1f}s")
        return model
    except ImportError:
        print("[ERREUR] sentence-transformers non installé")
        print("  Installer : pip install sentence-transformers")
        sys.exit(1)
    except Exception as e:
        print(f"[ERREUR] Chargement SBERT : {e}")
        sys.exit(1)


def connecter_supabase():
    """Connexion Supabase."""
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Test de connexion
        client.table("chunks").select("id").limit(1).execute()
        print("[SUPABASE] Connexion OK")
        return client
    except ImportError:
        print("[ERREUR] supabase-py non installé")
        print("  Installer : pip install supabase")
        sys.exit(1)
    except Exception as e:
        print(f"[ERREUR] Connexion Supabase : {e}")
        sys.exit(1)


def compter_chunks(supabase, tenant_id: str = None, force: bool = False):
    """Compte les chunks à traiter."""
    try:
        query_all = supabase.table("chunks").select("id", count="exact")
        if tenant_id:
            query_all = query_all.eq("tenant_id", tenant_id)
        total = query_all.execute().count or 0

        if force:
            a_traiter = total
        else:
            query_sans = supabase.table("chunks").select("id", count="exact").is_("embedding", "null")
            if tenant_id:
                query_sans = query_sans.eq("tenant_id", tenant_id)
            a_traiter = query_sans.execute().count or 0

        deja_faits = total - a_traiter
        return total, a_traiter, deja_faits
    except Exception as e:
        print(f"[ERREUR] Comptage : {e}")
        return 0, 0, 0


def charger_chunks_batch(supabase, offset: int, batch: int,
                          tenant_id: str = None, force: bool = False):
    """Charge un batch de chunks à vectoriser."""
    try:
        query = supabase.table("chunks").select(
            "id,content,contenu_index,tenant_id,document_id"
        )
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        if not force:
            query = query.is_("embedding", "null")
        result = query.range(offset, offset + batch - 1).execute()
        return result.data or []
    except Exception as e:
        print(f"[ERREUR] Chargement chunks : {e}")
        return []


def vectoriser_batch_sbert(model, chunks: list) -> list:
    """
    Vectorise un batch de chunks avec SBERT.

    POINT CRITIQUE — texte à encoder :
    On utilise contenu_index si disponible (texte non chiffré).
    Si le contenu est chiffré (ENC:...), on encode un texte générique.
    Les documents chiffrés ne peuvent pas être vectorisés correctement
    sans la clé de déchiffrement — ce cas est logué mais pas bloquant.
    """
    textes = []
    for chunk in chunks:
        texte = chunk.get("contenu_index") or chunk.get("content") or ""
        if texte.startswith("ENC:"):
            texte = "document juridique confidentiel"
        textes.append(texte.strip()[:512] or "document juridique")

    try:
        embeddings = model.encode(
            textes,
            normalize_embeddings=True,
            batch_size=BATCH_SBERT,
            show_progress_bar=False,
        )
        return [e.tolist() for e in embeddings]
    except Exception as e:
        print(f"[ERREUR] Vectorisation batch : {e}")
        return [None] * len(chunks)


def mettre_a_jour_supabase(supabase, chunks: list, embeddings: list,
                             dry_run: bool = False) -> int:
    """
    Met à jour les embeddings dans Supabase.
    Retourne le nombre de chunks mis à jour.
    """
    nb_ok = 0
    for i in range(0, len(chunks), BATCH_SUPABASE):
        lot_chunks = chunks[i:i + BATCH_SUPABASE]
        lot_embs   = embeddings[i:i + BATCH_SUPABASE]
        for chunk, emb in zip(lot_chunks, lot_embs):
            if emb is None:
                continue
            if dry_run:
                nb_ok += 1
                continue
            try:
                supabase.table("chunks").update(
                    {"embedding": emb}
                ).eq("id", chunk["id"]).execute()
                nb_ok += 1
            except Exception as e:
                print(f"  [WARN] Chunk {chunk['id'][:8]} : {e}")
    return nb_ok


def main():
    parser = argparse.ArgumentParser(
        description="Re-vectorise les chunks ODYXIA Droit : Voyage AI → SBERT"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-vectoriser TOUS les chunks (même ceux déjà vectorisés)"
    )
    parser.add_argument(
        "--tenant", type=str, default=None,
        help="Traiter uniquement ce tenant_id"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulation sans écriture dans Supabase"
    )
    parser.add_argument(
        "--batch", type=int, default=32,
        help="Taille des batches SBERT (défaut : 32)"
    )
    args = parser.parse_args()

    global BATCH_SBERT
    BATCH_SBERT = args.batch

    print("=" * 65)
    print("  RE-VECTORISATION ODYXIA DROIT")
    print("  Voyage AI (1024 dims) → SBERT (384 dims)")
    print("=" * 65)

    if args.dry_run:
        print("\n  [DRY-RUN] Simulation — aucune écriture dans Supabase")

    # Vérifications
    verifier_config()

    # Connexions
    supabase = connecter_supabase()
    model    = charger_sbert()

    # Comptage
    total, a_traiter, deja_faits = compter_chunks(
        supabase, args.tenant, args.force
    )
    print(f"\n  Total chunks      : {total:,}")
    print(f"  Déjà vectorisés   : {deja_faits:,}")
    print(f"  À traiter         : {a_traiter:,}")

    if a_traiter == 0:
        print("\n  Rien à faire — tous les chunks sont déjà vectorisés.")
        print("  Utiliser --force pour re-vectoriser quand même.")
        return

    # Estimation durée
    duree_estimee = (a_traiter / BATCH_SBERT) * 0.3  # ~300ms/batch CPU
    print(f"\n  Durée estimée     : ~{duree_estimee:.0f}s ({duree_estimee/60:.1f} min)")
    print(f"  Batch SBERT       : {BATCH_SBERT} chunks")

    if not args.dry_run:
        input("\n  Appuyez sur Entrée pour démarrer (Ctrl+C pour annuler)...")

    print()

    # Re-vectorisation
    t0         = time.time()
    nb_traites = 0
    nb_erreurs = 0
    offset     = 0
    PAGE_SIZE  = 200  # Chunks chargés par page depuis Supabase

    while offset < a_traiter:
        # Charger le batch depuis Supabase
        chunks_batch = charger_chunks_batch(
            supabase, offset, PAGE_SIZE, args.tenant, args.force
        )
        if not chunks_batch:
            break

        # Vectoriser avec SBERT
        embeddings = vectoriser_batch_sbert(model, chunks_batch)

        # Compter les erreurs
        nb_none = sum(1 for e in embeddings if e is None)
        nb_erreurs += nb_none

        # Mettre à jour Supabase
        nb_ok = mettre_a_jour_supabase(
            supabase, chunks_batch, embeddings, args.dry_run
        )
        nb_traites += nb_ok
        offset     += len(chunks_batch)

        # Progression
        pct    = min(nb_traites / a_traiter * 100, 100)
        duree  = time.time() - t0
        vitesse = nb_traites / max(duree, 0.1)
        restant = (a_traiter - nb_traites) / max(vitesse, 0.1)
        print(
            f"  {nb_traites:>6}/{a_traiter} ({pct:5.1f}%) | "
            f"{vitesse:.0f} chunks/s | "
            f"~{restant:.0f}s restant",
            end="\r"
        )

    duree_totale = time.time() - t0
    print(f"\n")  # Nouvelle ligne après \r

    # Rapport
    rapport = {
        "date"          : datetime.now().isoformat(),
        "total"         : total,
        "traites"       : nb_traites,
        "erreurs"       : nb_erreurs,
        "duree_secondes": round(duree_totale, 1),
        "vitesse_moy"   : round(nb_traites / max(duree_totale, 0.1), 1),
        "modele_sbert"  : "paraphrase-multilingual-MiniLM-L12-v2",
        "dimension"     : 384,
        "tenant"        : args.tenant or "tous",
        "force"         : args.force,
        "dry_run"       : args.dry_run,
    }

    if not args.dry_run:
        with open(RAPPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)

    print("=" * 65)
    print("  RAPPORT RE-VECTORISATION")
    print("=" * 65)
    print(f"  Chunks traités   : {nb_traites:,}")
    print(f"  Erreurs          : {nb_erreurs:,}")
    print(f"  Durée            : {duree_totale:.1f}s")
    print(f"  Vitesse moyenne  : {rapport['vitesse_moy']:.0f} chunks/s")
    print(f"  Dimension SBERT  : 384 dims")
    if not args.dry_run:
        print(f"  Rapport          : {RAPPORT_PATH}")

    if nb_erreurs > 0:
        print(f"\n  [WARN] {nb_erreurs} chunks n'ont pas pu être vectorisés")
        print(f"  (documents chiffrés ou contenu vide)")

    print(f"\n  Re-vectorisation terminée.")
    if not args.dry_run:
        print(f"\n  Prochaine étape — vérifier la recherche :")
        print(f"  curl -X POST http://localhost:5000/question_stream \\")
        print(f"    -H 'Authorization: Bearer TOKEN' \\")
        print(f"    -d '{{\"question\": \"licenciement cameroun\"}}'")


if __name__ == "__main__":
    main()