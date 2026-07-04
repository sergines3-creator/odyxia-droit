# cor_sx/generateur_paires.py
# COR Sx — Générateur de paires d'entraînement (Claude API)
#
# RÔLE :
#   Ce script génère automatiquement les paires (entrée, sortie)
#   nécessaires pour le fine-tuning multi-tâches de COR Sx.
#
#   Pipeline :
#     1. Charger les passages du corpus COR (juridique_dataset.json)
#     2. Filtrer selon le domaine et la longueur (passages assez longs)
#     3. Pour chaque passage, appeler Claude API avec un prompt de tâche
#     4. Sauvegarder la paire générée dans paires_sx.json
#     5. Marquer les paires comme "en_attente_validation" (pour l'avocat)
#
#   Workflow hybride Claude + avocat :
#     ÉTAPE 1 (ce script)     : Claude génère les sorties structurées
#     ÉTAPE 2 (interface web) : L'avocat valide, corrige ou rejette
#     ÉTAPE 3 (trainer)       : COR Sx s'entraîne sur les paires validées
#
# TÂCHES SUPPORTÉES :
#   resume_jugement       → résumé adaptatif d'un jugement
#   extraction_contrat    → extraction JSON des clauses d'un contrat
#   fiche_jurisprudence   → fiche structurée d'un arrêt CCJA/national
#   classification_synthese → domaine + synthèse du document
#   qa_document           → question/réponse ciblée sur document
#   conformite            → vérification de conformité à une règle
#   risques_contrat       → identification des risques contractuels
#   reformulation         → simplification en langage accessible
#
# FORMAT DES PAIRES (paires_sx.json) :
#   {
#     "paires": [
#       {
#         "id"         : "paire_0001",
#         "tache"      : "resume_jugement",
#         "entree"     : "resume_jugement: TRIBUNAL DE...",
#         "sortie"     : "Juridiction: TGI Douala\n...",
#         "source_id"  : "passage_12345",
#         "domaine"    : "droit_travail",
#         "statut"     : "en_attente_validation",
#         "genere_par" : "claude-sonnet-4-20250514",
#         "date"       : "2026-05-29"
#       },
#       ...
#     ],
#     "metadata": {
#       "total"             : 10000,
#       "valides"           : 0,
#       "en_attente"        : 10000,
#       "rejetes"           : 0,
#       "taches_distribution": {...}
#     }
#   }
#
# COÛT ESTIMÉ :
#   ~500 tokens input + ~400 tokens output par paire
#   Claude Sonnet 4 : $3/M input + $15/M output
#   10 000 paires   : ~$75 total
#
# Usage :
#   python -m cor_sx.generateur_paires --tache resume_jugement --nb 1000
#   python -m cor_sx.generateur_paires --tache all --nb 10000
#   python -m cor_sx.generateur_paires --dry-run --nb 5

import os
import sys
import json
import time
import uuid
import random
import argparse
import anthropic
from datetime import date
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(BASE, "data", "juridique_dataset.json")
PAIRES_PATH  = os.path.join(BASE, "data", "paires_sx.json")
LOG_PATH     = os.path.join(BASE, "data", "generateur_log.json")

MODEL_CLAUDE = "claude-sonnet-4-20250514"
MAX_TOKENS   = 1000
TEMPERATURE  = 0.3  # Bas pour des sorties structurées cohérentes

# Longueur minimale d'un passage pour être utilisable
MIN_CHARS_PASSAGE = 300
# Longueur maximale d'un passage envoyé à Claude (éviter les coûts excessifs)
MAX_CHARS_PASSAGE = 8000

random.seed(42)


# ══════════════════════════════════════════════════════════════════════
# PROMPTS PAR TÂCHE
#
# POINT CRITIQUE — qualité des prompts :
# La qualité des paires générées dépend directement de la qualité
# des prompts. Des prompts vagues → paires inconsistantes.
# Des prompts précis avec exemples → paires utilisables directement.
#
# CONVENTION :
# Chaque prompt demande à Claude de produire une sortie structurée
# qui servira de label d'entraînement pour COR Sx.
# Le format doit être cohérent entre toutes les paires d'une même tâche.
# ══════════════════════════════════════════════════════════════════════

PROMPTS_TACHES = {

    "resume_jugement": """Tu es un assistant juridique spécialisé en droit africain francophone (OHADA, CEMAC, droits nationaux).

Analyse le document juridique suivant et produis un résumé structuré.

DOCUMENT :
{texte}

Produis un résumé structuré avec exactement ce format (adapte la longueur au document) :

Juridiction : [tribunal/cour]
Numéro : [numéro de l'affaire si disponible, sinon "N/A"]
Date : [date si disponible, sinon "N/A"]
Domaine : [domaine juridique principal]
Parties : [demandeur] vs [défendeur] (si applicable)
Objet : [objet du litige ou du texte en une phrase]
Décision/Contenu : [résumé des points essentiels, 2 à 5 phrases selon la longueur]
Articles cités : [liste des articles/textes applicables, séparés par des virgules, ou "N/A"]
Portée : [impact juridique, application pratique, 1 à 2 phrases]""",

    "extraction_contrat": """Tu es un assistant juridique spécialisé en droit des contrats africain (OHADA, droits nationaux).

Analyse le document contractuel suivant et extrais les informations structurées.

DOCUMENT :
{texte}

Produis une extraction structurée avec exactement ce format JSON (utilise "N/A" si une information est absente) :

{{
  "type_document": "[bail/vente/travail/prestation/autre]",
  "parties": {{
    "partie_1": "[nom et qualité]",
    "partie_2": "[nom et qualité]"
  }},
  "objet": "[description de l'objet du contrat]",
  "valeur_montant": "[montant ou valeur si applicable, sinon N/A]",
  "duree": "[durée si applicable, sinon N/A]",
  "date_debut": "[date de début si applicable, sinon N/A]",
  "obligations_partie_1": ["[obligation 1]", "[obligation 2]"],
  "obligations_partie_2": ["[obligation 1]", "[obligation 2]"],
  "clauses_importantes": ["[clause 1]", "[clause 2]"],
  "conditions_resiliation": "[conditions de résiliation ou N/A]",
  "juridiction_competente": "[juridiction applicable ou N/A]",
  "loi_applicable": "[loi/acte uniforme applicable ou N/A]"
}}""",

    "fiche_jurisprudence": """Tu es un assistant juridique spécialisé en jurisprudence africaine (CCJA, cours nationales, tribunaux OHADA).

Analyse la décision juridictionnelle suivante et produis une fiche de jurisprudence.

DÉCISION :
{texte}

Produis une fiche structurée avec exactement ce format :

Juridiction : [CCJA / Cour d'appel / Tribunal + ville]
Numéro : [numéro de la décision ou N/A]
Date : [date de la décision ou N/A]
Pays : [pays ou "Panafricain" pour CCJA]
Domaine : [domaine juridique]
Texte applicable : [acte uniforme / code / loi applicable]
Moyen soulevé : [argument juridique principal discuté]
Solution retenue : [décision de la juridiction en 1 à 2 phrases]
Portée : [apport de cette décision au droit africain, 1 à 3 phrases]
Mots-clés : [3 à 6 mots-clés séparés par des virgules]""",

    "classification_synthese": """Tu es un assistant juridique spécialisé en droit africain francophone.

Analyse le document suivant et produis une classification et synthèse.

DOCUMENT :
{texte}

Produis une classification et synthèse avec exactement ce format :

Type de document : [loi / décret / arrêté / jugement / arrêt / contrat / doctrine / autre]
Domaine juridique : [domaine principal parmi : droit_civil, droit_commercial, droit_penal, droit_travail, droit_administratif, droit_ohada, droit_cemac, droit_fiscal, droit_douanier, droit_bancaire, droit_minier, droit_foncier, droit_international, autre]
Pays / Portée : [pays concerné ou "Panafricain" pour OHADA/CEMAC]
Date / Période : [date ou période si disponible, sinon N/A]
Autorité émettrice : [qui a produit ce document, ou N/A]
Synthèse : [résumé du contenu en 2 à 4 phrases, accessible à un non-juriste]
Points clés : [2 à 4 points essentiels à retenir, sous forme de liste]
Mots-clés : [3 à 6 mots-clés séparés par des virgules]""",

    "qa_document": """Tu es un assistant juridique spécialisé en droit africain francophone.

En te basant UNIQUEMENT sur le document suivant, réponds à la question posée.
Si la réponse n'est pas dans le document, dis-le clairement.

QUESTION : {question}

DOCUMENT :
{texte}

Réponds avec exactement ce format :

Réponse : [réponse directe et précise à la question, basée sur le document]
Référence : [article / clause / passage du document qui fonde la réponse, ou "Non trouvé dans le document"]
Nuance : [précision importante ou limite de la réponse si nécessaire, ou N/A]""",

    "conformite": """Tu es un assistant juridique spécialisé en droit africain francophone (OHADA, CEMAC, droits nationaux).

Vérifie si le document suivant est conforme à la règle juridique indiquée.

RÈGLE JURIDIQUE : {regle}

DOCUMENT À VÉRIFIER :
{texte}

Produis une analyse de conformité avec exactement ce format :

Verdict : [CONFORME / NON CONFORME / PARTIELLEMENT CONFORME / IMPOSSIBLE À DÉTERMINER]
Justification : [explication du verdict en 2 à 4 phrases]
Points conformes : [éléments du document conformes à la règle, ou N/A]
Points non conformes : [éléments du document non conformes, ou N/A]
Recommandations : [corrections à apporter si non conforme, ou N/A]""",

    "risques_contrat": """Tu es un assistant juridique spécialisé en droit des contrats africain (OHADA, droits nationaux).

Analyse le document contractuel suivant et identifie les risques juridiques.

DOCUMENT :
{texte}

Produis une analyse des risques avec exactement ce format :

Niveau de risque global : [FAIBLE / MODÉRÉ / ÉLEVÉ / TRÈS ÉLEVÉ]
Risques identifiés :
[Pour chaque risque, utilise ce format]
- Risque : [description du risque]
  Gravité : [FAIBLE / MODÉRÉ / ÉLEVÉ]
  Clause concernée : [clause ou article du document, ou N/A]
  Recommandation : [comment mitiger ce risque]

Clauses manquantes : [clauses protectrices absentes qui devraient figurer, ou "Aucune"]
Recommandation générale : [conseil global en 1 à 2 phrases]""",

    "reformulation": """Tu es un assistant juridique spécialisé en droit africain francophone, expert en vulgarisation juridique.

Reformule le texte juridique suivant en langage simple et accessible à un citoyen non-juriste.
Conserve tous les éléments importants mais supprime le jargon technique.

TEXTE JURIDIQUE :
{texte}

Produis une reformulation avec exactement ce format :

En langage simple : [reformulation accessible, même longueur approximative que le texte original]
Ce que ça veut dire concrètement : [1 à 3 exemples pratiques de ce que ça implique]
À retenir : [1 à 3 points essentiels pour le citoyen]""",
}


# Règles juridiques de référence pour la tâche "conformite"
# Utilisées pour générer des paires de vérification de conformité
REGLES_REFERENCE = [
    "Article 34 de l'Acte Uniforme OHADA sur le Droit des Sociétés Commerciales (AUSCGIE) : obligations de tenue de comptabilité",
    "Article 1er de l'Acte Uniforme sur le Droit du Travail OHADA : conditions de validité du contrat de travail",
    "Article 67 de l'Acte Uniforme sur le Droit Commercial Général (AUDCG) : conditions de cession de fonds de commerce",
    "Article 3 de l'Acte Uniforme sur les Procédures Simplifiées de Recouvrement (AUPSRVE) : conditions de l'injonction de payer",
    "Article 8 du Code du travail camerounais : conditions de forme du contrat de travail",
    "Article 14 de l'Acte Uniforme sur les Sûretés (AUS) : conditions de validité du cautionnement",
    "Article 101 de l'Acte Uniforme sur les Procédures Collectives (AUPC) : obligations du débiteur en cessation des paiements",
    "Règlement COBAC R-2010/01 : ratio de solvabilité des établissements de crédit CEMAC",
]

# Questions types pour la tâche "qa_document"
QUESTIONS_TYPES = [
    "Quelles sont les obligations principales des parties ?",
    "Quelle est la durée prévue dans ce document ?",
    "Quelles sont les conditions de résiliation ou de fin ?",
    "Quel est le montant ou la valeur en jeu ?",
    "Quels articles de loi sont applicables ?",
    "Quelle juridiction est compétente en cas de litige ?",
    "Quelles sont les sanctions prévues en cas de non-respect ?",
    "Qui peut saisir la justice selon ce document ?",
    "Quelles sont les conditions de validité mentionnées ?",
    "Quels délais sont prévus dans ce document ?",
]


# ══════════════════════════════════════════════════════════════════════
# CHARGEMENT DES PASSAGES
# ══════════════════════════════════════════════════════════════════════

def charger_passages(
    dataset_path : str,
    domaines_cibles : Optional[List[str]] = None,
    min_chars    : int = MIN_CHARS_PASSAGE,
    max_chars    : int = MAX_CHARS_PASSAGE,
) -> List[Dict]:
    """
    Charge les passages du corpus COR filtrés pour la génération de paires.

    domaines_cibles : filtrer par domaine (None = tous les domaines)
    min_chars       : longueur minimale du texte
    max_chars       : longueur maximale du texte

    Retourne : liste de dicts {id, texte, domaine, source}
    """
    if not os.path.exists(dataset_path):
        print(f"[ERREUR] Dataset absent : {dataset_path}")
        return []

    # FILTRE CRITIQUE : exclure les passages sans domaine identifié
    if domaines_cibles is None:
        domaines_cibles = [d for d in ["droit_travail","droit_civil","droit_commercial","droit_penal","droit_ohada","droit_cemac","droit_constitutionnel","droit_administratif","fiscalite","douane","bancaire_finance","mines","foncier","assurance","droit_international","propriete_intellectuelle","environnement","marches_publics","transport_logistique","droit_francais","droit_uemoa"] if d]

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    passages = []
    for i, p in enumerate(data.get("passages", [])):
        texte  = p.get("texte", "").strip() if isinstance(p, dict) else str(p).strip()
        domaine = p.get("domaine") if isinstance(p, dict) else None

        if not texte:
            continue
        if len(texte) < min_chars or len(texte) > max_chars:
            continue
        if domaines_cibles and domaine not in domaines_cibles:
            continue

        passages.append({
            "id"     : f"passage_{i:06d}",
            "texte"  : texte,
            "domaine": domaine or "inconnu",
            "source" : p.get("source", "inconnu") if isinstance(p, dict) else "inconnu",
        })

    print(f"[PASSAGES] {len(passages):,} passages utilisables "
          f"({min_chars}-{max_chars} caractères)")
    return passages


# ══════════════════════════════════════════════════════════════════════
# GÉNÉRATION VIA CLAUDE API
# ══════════════════════════════════════════════════════════════════════

def generer_paire(
    client   : anthropic.Anthropic,
    passage  : Dict,
    tache    : str,
    question : Optional[str] = None,
    regle    : Optional[str] = None,
    dry_run  : bool = False,
) -> Optional[Dict]:
    """
    Génère une paire (entrée, sortie) pour une tâche donnée.

    Retourne le dict de la paire ou None si échec.

    POINT CRITIQUE — gestion des erreurs API :
    Claude API peut échouer (rate limit, timeout, contenu filtré).
    On retourne None plutôt que de lever une exception.
    Le script principal gère les retries.

    POINT CRITIQUE — format de l'entrée COR Sx :
    L'entrée est préfixée avec le nom de la tâche, exactement comme
    COR Sx s'y attend pendant l'inférence.
    """
    from cor_sx.model import PREFIXES_TACHES

    assert tache in PROMPTS_TACHES, f"Tâche inconnue : {tache}"

    texte = passage["texte"]

    # Construire le prompt
    prompt_template = PROMPTS_TACHES[tache]
    if tache == "qa_document":
        question = question or random.choice(QUESTIONS_TYPES)
        prompt   = prompt_template.format(texte=texte, question=question)
    elif tache == "conformite":
        regle  = regle or random.choice(REGLES_REFERENCE)
        prompt = prompt_template.format(texte=texte, regle=regle)
    else:
        prompt = prompt_template.format(texte=texte)

    # Construire l'entrée COR Sx
    prefixe = PREFIXES_TACHES[tache]
    if tache == "qa_document":
        entree_sx = f"{prefixe}{question} [SEP] {texte}"
    elif tache == "conformite":
        entree_sx = f"{prefixe}{regle} [SEP] {texte}"
    else:
        entree_sx = f"{prefixe}{texte}"

    # Dry run — pas d'appel API
    if dry_run:
        return {
            "id"         : f"paire_{uuid.uuid4().hex[:8]}",
            "tache"      : tache,
            "entree"     : entree_sx[:200] + "...",
            "sortie"     : f"[DRY-RUN] Sortie simulée pour {tache}",
            "source_id"  : passage["id"],
            "domaine"    : passage["domaine"],
            "statut"     : "dry_run",
            "genere_par" : "dry_run",
            "date"       : str(date.today()),
            "nb_tokens_input" : len(prompt) // 4,
        }

    # Appel Claude API
    try:
        response = client.messages.create(
            model      = MODEL_CLAUDE,
            max_tokens = MAX_TOKENS,
            temperature= TEMPERATURE,
            system     = """Tu es un assistant juridique spécialisé en droit africain francophone (OHADA, CEMAC, droits nationaux des 16 pays membres : Cameroun, Gabon, Côte d'Ivoire, Sénégal, Mali, Burkina Faso, Niger, Togo, Bénin, Guinée, Congo, RDC, Tchad, Centrafrique, Guinée Équatoriale, Comores). Tu analyses uniquement des documents juridiques africains ou du droit international applicable en Afrique. Si le document analysé ne concerne pas le droit africain, réponds uniquement : HORS_SCOPE""",
            messages   = [{"role": "user", "content": prompt}],
        )

        sortie = response.content[0].text.strip()

        return {
            "id"              : f"paire_{uuid.uuid4().hex[:8]}",
            "tache"           : tache,
            "entree"          : entree_sx,
            "sortie"          : sortie,
            "source_id"       : passage["id"],
            "domaine"         : passage["domaine"],
            "statut"          : "en_attente_validation",
            "genere_par"      : MODEL_CLAUDE,
            "date"            : str(date.today()),
            "nb_tokens_input" : response.usage.input_tokens,
            "nb_tokens_output": response.usage.output_tokens,
        }

    except anthropic.RateLimitError:
        print(f"  [RATE LIMIT] Pause 60s...")
        time.sleep(60)
        return None
    except anthropic.APIError as e:
        print(f"  [API ERREUR] {e}")
        return None
    except Exception as e:
        print(f"  [ERREUR] {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

def charger_paires_existantes(chemin: str) -> Dict:
    """Charge les paires déjà générées pour reprendre sans doublon."""
    if not os.path.exists(chemin):
        return {"paires": [], "metadata": {
            "total": 0, "valides": 0,
            "en_attente": 0, "rejetes": 0,
            "taches_distribution": {}
        }}
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_paires(chemin: str, data: Dict):
    """Sauvegarde les paires avec backup automatique."""
    # Backup si fichier existant
    if os.path.exists(chemin):
        backup = chemin.replace(".json", "_backup.json")
        import shutil
        shutil.copy2(chemin, backup)

    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generer_paires_dataset(
    taches    : List[str],
    nb_total  : int,
    dry_run   : bool = False,
    domaines  : Optional[List[str]] = None,
    delai_sec : float = 0.5,
) -> Dict:
    """
    Pipeline complet de génération de paires.

    taches    : liste de tâches (["all"] pour toutes)
    nb_total  : nombre total de paires à générer
    dry_run   : simulation sans appel API
    domaines  : filtrer les passages par domaine
    delai_sec : délai entre les appels API (éviter rate limiting)

    Retourne : rapport de génération
    """

    # Résoudre "all"
    if "all" in taches:
        taches = list(PROMPTS_TACHES.keys())

    print(f"\n{'='*65}")
    print(f"  COR Sx — Génération de paires d'entraînement")
    print(f"  Tâches   : {taches}")
    print(f"  Nombre   : {nb_total:,}")
    print(f"  Dry run  : {dry_run}")
    print(f"{'='*65}\n")

    # Charger les passages
    passages = charger_passages(DATASET_PATH, domaines)
    if not passages:
        print("[ERREUR] Aucun passage disponible")
        return {}

    # Charger les paires existantes
    data = charger_paires_existantes(PAIRES_PATH)
    paires_existantes = {p["source_id"] + p["tache"] for p in data["paires"]}
    print(f"  Paires existantes : {len(data['paires']):,}")

    # Initialiser le client Claude
    if not dry_run:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("[ERREUR] ANTHROPIC_API_KEY non définie")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = None

    # Répartir les paires entre les tâches
    nb_par_tache = nb_total // len(taches)
    reste        = nb_total % len(taches)

    # Stats
    stats = defaultdict(int)
    tokens_input  = 0
    tokens_output = 0
    t0 = time.time()

    for i_tache, tache in enumerate(taches):
        nb_cible = nb_par_tache + (1 if i_tache < reste else 0)
        nb_genere = 0

        print(f"\n  [{tache}] Génération de {nb_cible} paires...")

        # Mélanger les passages pour diversité
        passages_shuffle = passages.copy()
        random.shuffle(passages_shuffle)

        for passage in passages_shuffle:
            if nb_genere >= nb_cible:
                break

            # Éviter les doublons
            cle = passage["id"] + tache
            if cle in paires_existantes:
                continue

            # Générer la paire
            paire = generer_paire(
                client, passage, tache,
                dry_run=dry_run
            )

            if paire is None:
                stats["echecs"] += 1
                continue

            data["paires"].append(paire)
            paires_existantes.add(cle)
            nb_genere += 1
            stats[tache] += 1
            stats["total"] += 1

            if not dry_run:
                tokens_input  += paire.get("nb_tokens_input", 0)
                tokens_output += paire.get("nb_tokens_output", 0)

            # Progression
            if stats["total"] % 10 == 0:
                duree = time.time() - t0
                cout  = (tokens_input * 3 + tokens_output * 15) / 1_000_000
                print(f"    {stats['total']:>5}/{nb_total} | "
                      f"{tache} {nb_genere}/{nb_cible} | "
                      f"coût ~${cout:.2f} | "
                      f"{duree:.0f}s")

            # Sauvegarde toutes les 50 paires
            if stats["total"] % 50 == 0:
                _mettre_a_jour_metadata(data, stats)
                sauvegarder_paires(PAIRES_PATH, data)

            # Délai entre appels
            if not dry_run and delai_sec > 0:
                time.sleep(delai_sec)

    # Sauvegarde finale
    _mettre_a_jour_metadata(data, stats)
    sauvegarder_paires(PAIRES_PATH, data)

    duree_totale = time.time() - t0
    cout_total   = (tokens_input * 3 + tokens_output * 15) / 1_000_000

    rapport = {
        "total_genere"  : stats["total"],
        "echecs"        : stats["echecs"],
        "par_tache"     : {t: stats[t] for t in taches},
        "tokens_input"  : tokens_input,
        "tokens_output" : tokens_output,
        "cout_total_usd": round(cout_total, 2),
        "duree_secondes": round(duree_totale, 1),
        "fichier"       : PAIRES_PATH,
    }

    print(f"\n{'='*65}")
    print(f"  RAPPORT DE GÉNÉRATION")
    print(f"{'='*65}")
    print(f"  Total généré   : {rapport['total_genere']:,}")
    print(f"  Échecs         : {rapport['echecs']:,}")
    print(f"  Coût total     : ~${rapport['cout_total_usd']:.2f}")
    print(f"  Durée          : {rapport['duree_secondes']:.0f}s")
    print(f"  Fichier        : {PAIRES_PATH}")

    return rapport


def _mettre_a_jour_metadata(data: Dict, stats: Dict):
    """Met à jour les métadonnées du fichier paires_sx.json."""
    from collections import Counter
    taches_dist = Counter(p["tache"] for p in data["paires"])
    statuts_dist = Counter(p["statut"] for p in data["paires"])

    data["metadata"] = {
        "total"               : len(data["paires"]),
        "valides"             : statuts_dist.get("valide", 0),
        "en_attente"          : statuts_dist.get("en_attente_validation", 0),
        "rejetes"             : statuts_dist.get("rejete", 0),
        "taches_distribution" : dict(taches_dist),
        "date_derniere_maj"   : str(date.today()),
    }


# ══════════════════════════════════════════════════════════════════════
# UTILITAIRES POST-GÉNÉRATION
# ══════════════════════════════════════════════════════════════════════

def rapport_paires(chemin: str = PAIRES_PATH):
    """Affiche un rapport sur les paires générées."""
    if not os.path.exists(chemin):
        print("Aucun fichier de paires trouvé.")
        return

    with open(chemin, "r", encoding="utf-8") as f:
        data = json.load(f)

    m = data.get("metadata", {})
    print(f"\n{'='*65}")
    print(f"  RAPPORT PAIRES COR Sx")
    print(f"{'='*65}")
    print(f"  Total          : {m.get('total', 0):,}")
    print(f"  Validées       : {m.get('valides', 0):,}")
    print(f"  En attente     : {m.get('en_attente', 0):,}")
    print(f"  Rejetées       : {m.get('rejetes', 0):,}")
    print(f"  Dernière MAJ   : {m.get('date_derniere_maj', 'N/A')}")
    print(f"\n  Distribution par tâche :")
    for tache, nb in m.get("taches_distribution", {}).items():
        pct = nb / max(m.get("total", 1), 1) * 100
        print(f"    {tache:<30} : {nb:>6,} ({pct:.1f}%)")


def export_paires_validees(chemin_sortie: str = None) -> str:
    """
    Exporte uniquement les paires validées par l'avocat.
    C'est ce fichier qui sera utilisé pour l'entraînement COR Sx.
    """
    if not os.path.exists(PAIRES_PATH):
        print("Aucun fichier de paires trouvé.")
        return ""

    with open(PAIRES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    paires_validees = [p for p in data["paires"] if p["statut"] == "valide"]

    if not paires_validees:
        print("Aucune paire validée pour l'export.")
        return ""

    if chemin_sortie is None:
        chemin_sortie = PAIRES_PATH.replace(".json", "_validees.json")

    export = {
        "paires"  : paires_validees,
        "metadata": {
            "total"          : len(paires_validees),
            "date_export"    : str(date.today()),
            "usage"          : "fine-tuning COR Sx",
        }
    }

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    print(f"  {len(paires_validees):,} paires validées exportées → {chemin_sortie}")
    return chemin_sortie


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════


def generer_inputs_only(
    taches   ,
    nb_total ,
    domaines = None,
):
    import uuid, random, time
    from datetime import date
    from cor_sx.model import PREFIXES_TACHES
    from collections import defaultdict

    if "all" in taches:
        taches = list(PROMPTS_TACHES.keys())

    print(f"\n{'='*65}")
    print(f"  COR Sx — Génération des entrées uniquement")
    print(f"  Tâches  : {taches}")
    print(f"  Nombre  : {nb_total:,}")
    print(f"  Coût    : $0.00 (pas d appel Claude)")
    print(f"{'='*65}\n")

    passages = charger_passages(DATASET_PATH, domaines)
    if not passages:
        print("[ERREUR] Aucun passage disponible")
        return {}

    data = charger_paires_existantes(PAIRES_PATH)
    paires_existantes = {p["source_id"] + p["tache"] for p in data["paires"]}
    print(f"  Entrées existantes : {len(data['paires']):,}")

    nb_par_tache = nb_total // len(taches)
    reste        = nb_total % len(taches)
    stats        = defaultdict(int)
    t0           = time.time()

    for i_tache, tache in enumerate(taches):
        nb_cible  = nb_par_tache + (1 if i_tache < reste else 0)
        nb_genere = 0
        passages_shuffle = passages.copy()
        random.shuffle(passages_shuffle)
        print(f"  [{tache}] {nb_cible} entrées...")

        for passage in passages_shuffle:
            if nb_genere >= nb_cible:
                break
            cle = passage["id"] + tache
            if cle in paires_existantes:
                continue

            prefixe = PREFIXES_TACHES[tache]
            if tache == "qa_document":
                question = random.choice(QUESTIONS_TYPES)
                entree   = f"{prefixe}{question} [SEP] {passage['texte']}"
            elif tache == "conformite":
                regle  = random.choice(REGLES_REFERENCE)
                entree = f"{prefixe}{regle} [SEP] {passage['texte']}"
            else:
                entree = f"{prefixe}{passage['texte']}"

            paire = {
                "id"        : f"paire_{uuid.uuid4().hex[:8]}",
                "tache"     : tache,
                "entree"    : entree,
                "sortie"    : "",
                "source_id" : passage["id"],
                "domaine"   : passage["domaine"],
                "statut"    : "input_only",
                "genere_par": "none",
                "date"      : str(date.today()),
            }
            data["paires"].append(paire)
            paires_existantes.add(cle)
            nb_genere    += 1
            stats[tache] += 1
            stats["total"] += 1

        print(f"    -> {nb_genere} entrees generees")

    _mettre_a_jour_metadata(data, stats)
    sauvegarder_paires(PAIRES_PATH, data)
    duree = time.time() - t0
    print(f"\n  {stats['total']:,} entrees sauvegardees en {duree:.1f}s")
    print(f"  Fichier : {PAIRES_PATH}")
    return dict(stats)


def main():
    parser = argparse.ArgumentParser(
        description="COR Sx — Générateur de paires d'entraînement"
    )
    parser.add_argument(
        "--tache",
        nargs="+",
        default=["all"],
        choices=list(PROMPTS_TACHES.keys()) + ["all"],
        help="Tâche(s) à générer (all = toutes)"
    )
    parser.add_argument(
        "--nb", type=int, default=100,
        help="Nombre total de paires à générer"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulation sans appel Claude API"
    )
    parser.add_argument(
        "--rapport", action="store_true",
        help="Afficher le rapport des paires existantes"
    )
    parser.add_argument(
        "--export-valides", action="store_true",
        help="Exporter les paires validées pour l'entraînement"
    )
    parser.add_argument(
        "--inputs-only", action="store_true",
        help="Generer les entrees sans appeler Claude (gratuit)"
    )
    parser.add_argument(
        "--delai", type=float, default=0.5,
        help="Délai en secondes entre les appels API"
    )
    args = parser.parse_args()

    if args.rapport:
        rapport_paires()
        return

    if args.export_valides:
        export_paires_validees()
        return

    if args.inputs_only:
        generer_inputs_only(taches=args.tache, nb_total=args.nb)
        return

    generer_paires_dataset(
        taches    = args.tache,
        nb_total  = args.nb,
        dry_run   = args.dry_run,
        delai_sec = args.delai,
    )


if __name__ == "__main__":
    main()