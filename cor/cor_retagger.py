# cor_retagger.py
# COR — Re-classification du corpus juridique africain
#
# Version 3 — Utilise ClassifieurHybride (cor_classifier.py)
#   Etape 1 : Regles prioritaires (regex compile)
#   Etape 2 : Score regex compile (sans faux positifs)
#   Etape 3 : SBERT multilingue (cas ambigus)
#
# Ce que fait ce script :
#   1. Charge le dataset existant (juridique_dataset.json)
#   2. Re-classifie chaque passage avec ClassifieurHybride
#   3. Affiche un rapport avant/apres avec stats par etape
#   4. Sauvegarde le dataset corrige (backup automatique)
#
# Usage :
#   python cor_retagger.py --dry-run
#   python cor_retagger.py
#   python cor_retagger.py --no-sbert  ← desactiver SBERT (plus rapide)

import os
import sys
import json
import time
import shutil
import argparse
from typing import List, Dict
from collections import Counter, defaultdict

BASE         = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(BASE, "data", "juridique_dataset.json")
BACKUP_PATH  = os.path.join(BASE, "data", "juridique_dataset_backup.json")
LOG_PATH     = os.path.join(BASE, "data", "retagger_log.json")

# Importer le classifieur hybride
sys.path.insert(0, BASE)
from cor_classifier import ClassifieurHybride, DOMAINES



def retaguer_dataset(
    dataset_path   : str,
    batch_size     : int  = 10000,
    dry_run        : bool = False,
    utiliser_sbert : bool = True,
) -> Dict:
    """
    Re-classifie tous les passages du dataset avec le classifieur v2.

    seuil_min : score minimum pour conserver un passage
                Si le nouveau score est < seuil_min ET ancien domaine
                etait valide → garder l ancien tag.

    Retourne un rapport detaille des changements.
    """
    print(f"\n{'='*65}")
    print(f"  COR RETAGGER — Re-classification corpus")
    print(f"  Dataset : {dataset_path}")
    print(f"  Dry-run : {dry_run}")
    print(f"{'='*65}")

    if not os.path.exists(dataset_path):
        print(f"[ERREUR] Dataset absent : {dataset_path}")
        sys.exit(1)

    # Initialiser le classifieur hybride
    print(f"\n[0/4] Initialisation du classifieur hybride...")
    clf = ClassifieurHybride(utiliser_sbert=utiliser_sbert)
    if utiliser_sbert:
        clf._charger_sbert()  # Charger SBERT maintenant (pas lazily)

    # Charger le dataset
    print(f"\n[1/4] Chargement du dataset...")
    t0 = time.time()
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    passages = dataset.get("passages", [])
    print(f"  {len(passages):,} passages charges en {time.time()-t0:.1f}s")

    # Stats avant
    domaines_avant = Counter(
        p.get("domaine", "inconnu") for p in passages
        if isinstance(p, dict)
    )

    # Backup
    if not dry_run:
        print(f"\n[2/4] Backup du dataset original...")
        shutil.copy2(dataset_path, BACKUP_PATH)
        print(f"  Backup : {BACKUP_PATH}")
    else:
        print(f"\n[2/4] [DRY-RUN] Pas de backup")

    # Re-tagging par lots
    print(f"\n[3/4] Re-classification ({len(passages):,} passages)...")
    t1           = time.time()
    nb_changes   = 0
    nb_nouveaux  = 0   # domaines nouveaux (mines, petrole...)
    nb_priority  = 0   # corriges par regle prioritaire

    for i in range(0, len(passages), batch_size):
        batch  = passages[i : i + batch_size]
        pct    = (i / len(passages)) * 100

        for j, passage in enumerate(batch):
            if not isinstance(passage, dict) or "texte" not in passage:
                continue

            texte        = passage.get("texte", "")
            ancien_dom   = passage.get("domaine")

            # Re-classifier avec ClassifieurHybride
            profil = clf.classifier(texte)
            nouveau_dom = profil["domaine_principal"]

            # Mettre a jour si changement
            # IMPORTANT : nouveau_dom peut etre None (hors scope/bruit)
            # On met a jour meme dans ce cas pour nettoyer le corpus
            if nouveau_dom != ancien_dom:
                nb_changes += 1

                # Compter les nouveaux domaines
                if ancien_dom not in DOMAINES or nouveau_dom in (
                    "mines", "petrole_energie", "sante", "education"
                ):
                    nb_nouveaux += 1

                # Compter les corrections par regle prioritaire
                if profil.get("priority_rule"):
                    nb_priority += 1

                passage["domaine"]              = nouveau_dom
                passage["domaines_secondaires"] = profil["domaines_secondaires"]
                passage["score"]                = profil["score_max"]

            # Mettre a jour le pays si absent
            if not passage.get("pays"):
                passage["pays"] = clf.detecter_pays(texte)

        duree = time.time() - t1
        vitesse = (i + len(batch)) / max(duree, 0.1)
        print(f"  {i+len(batch):>7,}/{len(passages):,} "
              f"({pct:.0f}%) | "
              f"{vitesse:.0f} passages/s | "
              f"{nb_changes:,} corrections")

    duree_total = time.time() - t1
    print(f"\n  Re-classification terminee en {duree_total:.1f}s")
    print(f"  {nb_changes:,} passages re-classes")
    print(f"  {nb_priority:,} corriges par regle prioritaire")
    print(f"  {nb_nouveaux:,} vers nouveaux domaines")
    print(f"\n{clf.rapport_stats()}")

    # Stats apres
    domaines_apres = Counter(
        p.get("domaine", "inconnu") for p in passages
        if isinstance(p, dict)
    )

    # Mettre a jour les metadata
    dataset["passages"] = passages
    dataset["metadata"] = {
        "derniere_maj"          : time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_passages"        : len(passages),
        "tokens_estimes"        : sum(
            len(p.get("texte", "")) // 5
            for p in passages if isinstance(p, dict)
        ),
        "par_domaine"           : dict(domaines_apres),
        "retagger_version"      : "v3_hybride",
        "retagger_corrections"  : nb_changes,
    }

    # Sauvegarder
    if not dry_run:
        print(f"\n[4/4] Sauvegarde...")
        with open(dataset_path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)
        taille = os.path.getsize(dataset_path) // (1024 * 1024)
        print(f"  Dataset sauvegarde : {dataset_path} ({taille} Mo)")
    else:
        print(f"\n[4/4] [DRY-RUN] Pas de sauvegarde")

    # Rapport comparatif
    rapport = {
        "nb_passages"    : len(passages),
        "nb_changes"     : nb_changes,
        "nb_priority"    : nb_priority,
        "nb_nouveaux"    : nb_nouveaux,
        "duree_s"        : duree_total,
        "avant"          : dict(domaines_avant),
        "apres"          : dict(domaines_apres),
    }

    return rapport


def afficher_rapport(rapport: Dict):
    """Affiche le rapport comparatif avant/apres."""
    print(f"\n{'='*65}")
    print(f"  RAPPORT RE-TAGGING")
    print(f"{'='*65}")
    print(f"\n  Passages traites  : {rapport['nb_passages']:,}")
    print(f"  Corrections totales: {rapport['nb_changes']:,}")
    print(f"  Via regles prior. : {rapport['nb_priority']:,}")
    print(f"  Nouveaux domaines : {rapport['nb_nouveaux']:,}")
    print(f"  Duree             : {rapport['duree_s']:.1f}s")

    print(f"\n  {'DOMAINE':<40} {'AVANT':>8} {'APRES':>8} {'DELTA':>8}")
    print(f"  {'-'*65}")

    # Tous les domaines uniques
    tous_domaines = set(rapport["avant"]) | set(rapport["apres"])
    for dom in sorted(tous_domaines,
                      key=lambda d: -rapport["apres"].get(d, 0)):
        avant  = rapport["avant"].get(dom, 0)
        apres  = rapport["apres"].get(dom, 0)
        delta  = apres - avant
        label  = str(DOMAINES.get(dom, {}).get("label", dom) or dom or "inconnu")
        signe  = "+" if delta > 0 else ""
        print(f"  {label:<40} {avant:>8,} {apres:>8,} {signe}{delta:>7,}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="COR — Re-classification du corpus juridique"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation sans ecriture"
    )
    parser.add_argument(
        "--no-sbert",
        action="store_true",
        help="Desactiver SBERT (plus rapide, moins precis)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=10000,
        help="Taille des lots de traitement (defaut: 10000)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Tester le classifieur sur quelques exemples"
    )
    args = parser.parse_args()

    if args.test:
        print("=== TEST DU CLASSIFIEUR V2 ===\n")
        cas = [
            ("Code des douanes camerounais article 34 dedouanement",
             "douane"),
            ("Code minier decret permis exploitation minerai",
             "mines"),
            ("Licenciement preavis code du travail salarie tribunal",
             "droit_travail"),
            ("Titre foncier immatriculation cadastre expropriation",
             "foncier"),
            ("Impot sur les societes tva code general des impots dgi",
             "fiscalite"),
            ("Hydrocarbures code petrolier exploration exploitation",
             "petrole_energie"),
        ]
        for texte, attendu in cas:
            profil = classifier_v2(texte)
            dom    = profil["domaine_principal"]
            ok     = "OK" if dom == attendu else "WARN"
            priority = " [PRIORITY]" if profil.get("priority_rule") else ""
            print(f"  [{ok}] {attendu:<20} → {dom}{priority}")
            print(f"       Score={profil['score_max']:.1f} | "
                  f"Secondaires={profil['domaines_secondaires']}")
        return

    # Re-tagging complet
    rapport = retaguer_dataset(
        dataset_path   = DATASET_PATH,
        batch_size     = args.batch,
        dry_run        = args.dry_run,
        utiliser_sbert = not args.no_sbert,
    )

    # Afficher le rapport
    afficher_rapport(rapport)

    # Sauvegarder le log
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    print(f"\n  Log sauvegarde : {LOG_PATH}")

    if args.dry_run:
        print(f"\n  [DRY-RUN] Relancer sans --dry-run pour appliquer.")
    else:
        print(f"\n  Re-tagging applique.")
        print(f"  Backup disponible : {BACKUP_PATH}")
        print(f"  En cas de probleme : cp {BACKUP_PATH} {DATASET_PATH}")


if __name__ == "__main__":
    main()