# COUCHE INFRASTRUCTURE — infrastructure/corpus.py
# Responsabilité : chargement et consolidation du corpus juridique africain.
#
# Règles de couche :
#   ✓ I/O fichier autorisé (c'est le rôle de l'infrastructure)
#   ✓ Aucun import Flask, aucun import application/ ou api/
#   ✓ Peut importer domain/ si besoin (pas nécessaire ici)
#
# Exports publics : charger_corpus, charger_dataset_json, rapport_corpus

import os
import json
from typing import List, Optional

_PROJET      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_DIR   = os.path.join(_PROJET, "data")
DATASET_PATH = os.path.join(_PROJET, "data", "juridique_dataset.json")


def charger_dataset_json(chemin: str, min_len: int = 20) -> List[str]:
    """
    Charge un dataset au format juridique_dataset.json.

    Format :
    {
        "passages"         : [{"texte": "..."}, ...],
        "paires_qr"        : [{"question": "...", "reponse": "..."}, ...],
        "paires_similaires": [{"ancre": "...", "positif": "..."}, ...]
    }

    POINT CRITIQUE : on extrait TOUT le texte disponible pour maximiser le BPE.
    """
    if not os.path.exists(chemin):
        return []
    textes = []
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[CORPUS] Erreur lecture {chemin} : {e}")
        return []

    for p in data.get("passages", []):
        t = p.get("texte", "") if isinstance(p, dict) else str(p)
        if t and len(t.strip()) >= min_len:
            textes.append(t.strip())

    for paire in data.get("paires_qr", []):
        for champ in ["question", "reponse"]:
            t = paire.get(champ, "")
            if t and len(t.strip()) >= min_len:
                textes.append(t.strip())

    for paire in data.get("paires_similaires", []):
        for champ in ["ancre", "positif"]:
            t = paire.get(champ, "")
            if t and len(t.strip()) >= min_len:
                textes.append(t.strip())

    return textes


def charger_fichiers_txt(dossier: str, min_len: int = 20) -> List[str]:
    """
    Charge tous les fichiers .txt d'un dossier.
    Tente UTF-8 puis latin-1 en fallback.
    """
    textes = []
    if not os.path.exists(dossier):
        return []

    for nom in os.listdir(dossier):
        if not nom.endswith(".txt"):
            continue
        chemin = os.path.join(dossier, nom)
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                lignes = f.readlines()
        except UnicodeDecodeError:
            try:
                with open(chemin, "r", encoding="latin-1") as f:
                    lignes = f.readlines()
            except Exception:
                print(f"[CORPUS] Impossible de lire : {nom}")
                continue

        for ligne in lignes:
            ligne = ligne.strip()
            if len(ligne) >= min_len:
                textes.append(ligne)

    return textes


def charger_corpus(
    dataset_path : Optional[str] = None,
    corpus_dir   : Optional[str] = None,
    min_len      : int  = 20,
    verbose      : bool = True,
) -> List[str]:
    """
    Charge et consolide toutes les sources de corpus disponibles.

    Sources chargées dans l'ordre :
    1. data/juridique_dataset.json (source principale)
    2. data/*.txt                  (textes bruts supplémentaires)

    POINT CRITIQUE — volume minimum :
    BPE 8000 tokens : minimum 500K tokens (~2Mo de texte).
    Modèle 50M params : minimum 500M tokens pour bien généraliser.
    """
    dataset_path = dataset_path or DATASET_PATH
    corpus_dir   = corpus_dir   or CORPUS_DIR

    textes  = []
    sources = {}

    t = charger_dataset_json(dataset_path, min_len)
    if t:
        textes.extend(t)
        sources["dataset_json"] = len(t)
    elif verbose:
        print(f"[CORPUS] Dataset principal absent : {dataset_path}")

    t = charger_fichiers_txt(corpus_dir, min_len)
    if t:
        textes.extend(t)
        sources["fichiers_txt"] = len(t)

    avant       = len(textes)
    textes      = list(dict.fromkeys(t for t in textes if t))
    nb_doublons = avant - len(textes)

    if verbose:
        print(f"\n[CORPUS] Rapport de chargement :")
        for source, nb in sources.items():
            print(f"  {source:<20} : {nb:>6} textes")
        if nb_doublons:
            print(f"  doublons retires     : {nb_doublons:>6}")
        print(f"  TOTAL                : {len(textes):>6} textes uniques")

        nb_tokens = sum(len(t) for t in textes) // 5
        print(f"  Volume estime        : ~{nb_tokens:,} tokens")

        if nb_tokens < 500_000:
            print(f"\n  ⚠ CORPUS INSUFFISANT ({nb_tokens:,} < 500 000 minimum)")
            print(f"    Sources recommandees : JORcam, OHADA.com, jurAfrica")

    return textes


def rapport_corpus(textes: List[str]):
    """Affiche des statistiques détaillées sur le corpus."""
    if not textes:
        print("[CORPUS] Corpus vide.")
        return
    longueurs = [len(t) for t in textes]
    print(f"\n{'='*55}")
    print(f"  RAPPORT CORPUS")
    print(f"  Textes total      : {len(textes):,}")
    print(f"  Longueur min      : {min(longueurs)} chars")
    print(f"  Longueur max      : {max(longueurs)} chars")
    print(f"  Longueur moyenne  : {sum(longueurs)//len(longueurs)} chars")
    print(f"  Volume total      : {sum(longueurs):,} chars")
    print(f"  Tokens estimes    : ~{sum(longueurs)//5:,}")
    print(f"{'='*55}")
