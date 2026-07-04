# cor_scraper.py
# COR — Collecte et ingestion du corpus juridique africain
#
# Philosophie : Droit comme centre, domaines satellites autour
#
#   CENTRE      : Droit (OHADA, CEMAC, codes nationaux, jurisprudence)
#   SATELLITES  : Fiscalite, Douane, Foncier, Bancaire, Social, Commercial
#                 + tout document gravitant autour du droit africain
#
# Le classifieur de domaine detecte automatiquement le domaine
# de chaque document et cree de nouveaux tags si necessaire.
# Seul le bruit pur (cuisine, sport, fiction...) est rejete.
#
# Modules :
#   1. Ingestion PDFs locaux (data/raw/)
#   2. Scraper CCJA (ccja-ohada.org — robots.txt absent)
#   3. API Legifrance (droit francais — matrice OHADA) [necessite cle PISTE]
#
# Usage :
#   python cor_scraper.py --module pdfs
#   python cor_scraper.py --module pdfs --dry-run
#   python cor_scraper.py --module ccja --max-pages 50
#   python cor_scraper.py --module all
#   python cor_scraper.py --module pdfs --seuil 10

import os
import sys
import json
import time
import hashlib
import logging
import argparse
import re
import random
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
from collections import defaultdict

try:
    import fitz
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False
    print("[WARN] pymupdf absent — pip install pymupdf")

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# Importer le classifieur hybride
try:
    from cor_classifier import ClassifieurHybride, DOMAINES
    # Instance globale — chargee une seule fois
    _CLASSIFIEUR = ClassifieurHybride(utiliser_sbert=True)
    CLASSIFIER_OK = True
except ImportError:
    CLASSIFIER_OK = False
    print("[WARN] cor_classifier.py absent — classification basique")

try:
    import pytesseract
    from PIL import Image
    import io
    TESSERACT_OK = True
except ImportError:
    TESSERACT_OK = False

try:
    import cv2
    import numpy as np
    OPENCV_OK = True
except ImportError:
    OPENCV_OK = False
    print("[WARN] opencv absent — pip install opencv-python-headless")

BASE         = os.path.dirname(os.path.abspath(__file__))
RAW_DIR      = os.path.join(BASE, "data", "raw")
OUTPUT_DIR   = os.path.join(BASE, "data")
DATASET_PATH = os.path.join(OUTPUT_DIR, "juridique_dataset.json")
LOG_PATH     = os.path.join(OUTPUT_DIR, "scraper_log.json")

# Seuil de confiance minimum pour accepter un document (0-100)
# Un document doit scorer >= ce seuil dans AU MOINS UN domaine
SEUIL_DEFAUT = 15

# Longueur minimale du texte extrait
MIN_CHARS = 200

# Taille et chevauchement des passages
MAX_CHARS_PASSAGE = 1000
OVERLAP_CHARS     = 100

# Rate limiting scraper web
RATE_LIMIT = 3.0

USER_AGENT = (
    "CorAI/1.0 (Modele de langage juridique africain; "
    "contact: odyxia-cor@proton.me; "
    "https://codeberg.org/odyxia-cor/cor)"
)

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger("cor_scraper")


# ══════════════════════════════════════════════════════════════════════
# TAXONOMIE DES DOMAINES
#
# Structure : {
#   "domaine_id" : {
#       "label"    : nom lisible,
#       "termes"   : mots-cles pour la detection,
#       "pays"     : pays pertinents (optionnel),
#       "poids"    : importance relative dans le corpus (1-3)
#   }
# }
#
# POINT CRITIQUE — extensibilite automatique :
# Si le classifieur detecte un document qui ne correspond
# a aucun domaine existant mais contient des termes juridiques
# generaux, il cree automatiquement un domaine "autre_juridique".
# Les nouveaux domaines sont loggues dans scraper_log.json
# pour revue manuelle.
# ══════════════════════════════════════════════════════════════════════

DOMAINES = {

    # ── CENTRE : Droit ──────────────────────────────────────────────
    "droit_ohada": {
        "label"  : "Droit OHADA",
        "poids"  : 3,
        "termes" : [
            "ohada", "acte uniforme", "ccja", "aupsrve", "audcg",
            "auscgie", "aurve", "aupap", "autf", "auohsada",
            "droit uniforme", "organisation pour l'harmonisation",
            "traite ohada", "espace ohada", "17 etats",
        ],
    },
    "droit_cemac": {
        "label"  : "Droit CEMAC/COBAC",
        "poids"  : 3,
        "termes" : [
            "cemac", "cobac", "beac", "bvmac", "cosumaf",
            "zone cemac", "communaute economique", "franc cfa",
            "reglementation bancaire cemac", "instruction cobac",
        ],
    },
    "droit_uemoa": {
        "label"  : "Droit UEMOA/BCEAO",
        "poids"  : 3,
        "termes" : [
            "uemoa", "bceao", "union economique monetaire",
            "zone uemoa", "commission uemoa", "reglementation uemoa",
        ],
    },
    "droit_travail": {
        "label"  : "Droit du travail",
        "poids"  : 3,
        "termes" : [
            "code du travail", "licenciement", "salarie", "employeur",
            "preavis", "smig", "smag", "syndicat", "greve",
            "convention collective", "inspection du travail",
            "tribunal du travail", "contrat de travail",
            "rupture abusive", "indemnite de licenciement",
            "periode d'essai", "heures supplementaires",
            "conge annuel", "accident du travail", "cnps",
            "securite sociale", "cotisations sociales",
        ],
    },
    "droit_penal": {
        "label"  : "Droit penal",
        "poids"  : 3,
        "termes" : [
            "code penal", "infraction", "delit", "crime",
            "garde a vue", "detention provisoire", "mise en examen",
            "instruction penale", "parquet", "procureur",
            "tribunal correctionnel", "cour d'assises",
            "peine d'emprisonnement", "amende penale",
            "liberté provisoire", "perquisition",
            "trafic d'influence", "corruption", "detournement",
        ],
    },
    "droit_civil": {
        "label"  : "Droit civil",
        "poids"  : 3,
        "termes" : [
            "code civil", "contrat", "obligation", "responsabilite",
            "dommages et interets", "prejudice", "faute",
            "prescription", "nullite", "rescision",
            "droit de la famille", "mariage", "divorce",
            "succession", "heritage", "testament", "tutelle",
            "adoption", "filiation", "capacite juridique",
        ],
    },
    "droit_commercial": {
        "label"  : "Droit commercial",
        "poids"  : 3,
        "termes" : [
            "code de commerce", "acte de commerce", "commercant",
            "fonds de commerce", "societe commerciale",
            "sarl", "sa", "sas", "snc", "gie",
            "registre du commerce", "rccm",
            "lettre de change", "billet a ordre", "cheque",
            "nantissement", "gage", "hypotheque",
            "faillite", "liquidation", "redressement judiciaire",
        ],
    },
    "droit_francais": {
        "label"  : "Droit francais (matrice)",
        "poids"  : 2,
        "termes" : [
            "code civil francais", "code de commerce francais",
            "cour de cassation", "conseil d'etat francais",
            "jurisprudence francaise", "doctrine francaise",
            "droit francais", "legislation francaise",
            "legifrance", "dalloz", "jurisclasseur",
        ],
    },
    "droit_constitutionnel": {
        "label"  : "Droit constitutionnel",
        "poids"  : 2,
        "termes" : [
            "constitution", "constitutionnel", "souverainete",
            "pouvoir executif", "pouvoir legislatif",
            "pouvoir judiciaire", "separation des pouvoirs",
            "droits fondamentaux", "liberte publique",
            "etat de droit", "republique", "democratie",
            "parlement", "assemblee nationale", "senat",
            "president de la republique", "premier ministre",
        ],
    },
    "droit_administratif": {
        "label"  : "Droit administratif",
        "poids"  : 2,
        "termes" : [
            "droit administratif", "acte administratif",
            "service public", "domaine public", "concession",
            "marche public", "appel d'offres",
            "tribunal administratif", "recours pour exces de pouvoir",
            "contentieux administratif", "fonction publique",
        ],
    },

    # ── SATELLITES ───────────────────────────────────────────────────
    "fiscalite": {
        "label"  : "Fiscalite et impots",
        "poids"  : 3,
        "termes" : [
            "impot", "taxe", "tva", "is", "irpp", "fiscalite",
            "code general des impots", "administration fiscale",
            "direction generale des impots", "dgi",
            "redressement fiscal", "controle fiscal",
            "avis de mise en recouvrement", "exoneration",
            "abattement fiscal", "deduction fiscale",
            "contribuable", "assiette fiscale", "taux d'imposition",
            "impot sur les societes", "impot sur le revenu",
            "patente", "taxe professionnelle", "droit d'enregistrement",
            "taxe fonciere", "droits de succession",
            "comptabilite", "bilan", "compte de resultat",
            "plan comptable", "syscohada", "ohada comptable",
        ],
    },
    "douane": {
        "label"  : "Droit douanier",
        "poids"  : 3,
        "termes" : [
            "douane", "droit de douane", "tarif douanier",
            "dedouanement", "declaration en douane",
            "code des douanes", "valeur en douane",
            "nomenclature douaniere", "hs code", "position tarifaire",
            "regime douanier", "transit douanier", "entrepot douanier",
            "franchise douaniere", "exoneration douaniere",
            "contrebande", "fraude douaniere", "contentieux douanier",
            "agent des douanes", "direction generale des douanes", "dgd",
            "tarif exterieur commun", "tec cemac",
            "convention de kyoto", "organisation mondiale des douanes",
            "omd", "incoterms", "connaissement", "manifeste",
            "inspection avant embarquement", "certificate of origin",
        ],
    },
    "foncier": {
        "label"  : "Droit foncier et immobilier",
        "poids"  : 3,
        "termes" : [
            "foncier", "titre foncier", "immatriculation",
            "cadastre", "propriete fonciere", "terrain",
            "lotissement", "expropriation", "indemnisation",
            "bail emphyteotique", "bail commercial", "bail d'habitation",
            "servitude", "mitoyennete", "usufruit",
            "droit de superficie", "domaine public foncier",
            "domaine prive de l'etat", "reserve fonciere",
            "amenagement du territoire", "urbanisme",
            "permis de construire", "certificat d'urbanisme",
            "plan d'occupation des sols", "geometre",
        ],
    },
    "bancaire_finance": {
        "label"  : "Droit bancaire et finance",
        "poids"  : 2,
        "termes" : [
            "banque", "credit", "pret", "taux d'interet",
            "etablissement de credit", "microfinance",
            "lutte contre le blanchiment", "lbc-ft", "kyc",
            "due diligence", "financement du terrorisme",
            "ratio de solvabilite", "fonds propres",
            "credit documentaire", "lettre de credit",
            "garantie bancaire", "caution bancaire",
            "compte bancaire", "virement", "prelevement",
            "monnaie electronique", "mobile money",
            "bourse", "marche financier", "titre financier",
            "action", "obligation financiere", "dividende",
        ],
    },
    "social_rh": {
        "label"  : "Droit social et ressources humaines",
        "poids"  : 2,
        "termes" : [
            "ressources humaines", "gestion du personnel",
            "bulletin de paie", "salaire", "remuneration",
            "cotisation sociale", "retraite", "pension",
            "maladie professionnelle", "invalidite",
            "assurance maladie", "mutuelle",
            "formation professionnelle", "apprentissage",
            "discrimination", "harcelement", "egalite professionnelle",
        ],
    },
    "assurance": {
        "label"  : "Droit des assurances (CIMA)",
        "poids"  : 2,
        "termes" : [
            "assurance", "cima", "contrat d'assurance",
            "prime d'assurance", "sinistre", "indemnisation",
            "assureur", "assure", "beneficiaire",
            "assurance vie", "assurance dommages",
            "responsabilite civile", "assurance automobile",
            "assurance maladie", "reassurance",
            "courtier d'assurance", "agent d'assurance",
        ],
    },
    "propriete_intellectuelle": {
        "label"  : "Propriete intellectuelle (OAPI)",
        "poids"  : 2,
        "termes" : [
            "oapi", "propriete intellectuelle", "brevet",
            "marque", "droit d'auteur", "copyright",
            "dessins et modeles", "indication geographique",
            "contrefacon", "piraterie", "plagiat",
            "licence", "redevance", "droits voisins",
        ],
    },
    "environnement": {
        "label"  : "Droit de l'environnement",
        "poids"  : 1,
        "termes" : [
            "environnement", "ecologie", "pollution",
            "droit de l'environnement", "etude d'impact",
            "ressources naturelles", "foret", "eau",
            "mine", "exploitation miniere", "hydrocarbures",
            "petrole", "code minier", "code petrolier",
            "developpement durable", "changement climatique",
        ],
    },
    "transport_logistique": {
        "label"  : "Transport et logistique",
        "poids"  : 1,
        "termes" : [
            "transport", "logistique", "fret", "expediteur",
            "transitaire", "connaissement", "lettre de voiture",
            "contrat de transport", "responsabilite du transporteur",
            "transport maritime", "transport aerien",
            "transport routier", "transport ferroviaire",
            "port", "aeroport", "entrepot", "stockage",
        ],
    },
    "marches_publics": {
        "label"  : "Marches publics et commande publique",
        "poids"  : 2,
        "termes" : [
            "marche public", "appel d'offres", "code des marches",
            "commande publique", "soumissionnaire", "titulaire",
            "maitre d'ouvrage", "maitre d'oeuvre",
            "contrat public", "delegation de service public",
            "partenariat public prive", "ppp",
            "corruption marche public", "favoritisme",
            "commission des marches",
        ],
    },
}

# Termes de bruit pur — documents a rejeter systematiquement
# Si un document contient UNIQUEMENT ces termes et aucun terme
# des domaines ci-dessus, il est rejete.
TERMES_BRUIT = [
    # Cuisine
    "recette", "cuisine", "ingredients", "cuire", "four",
    "poulet", "riz", "sel", "sucre", "farine", "sauce",
    "mijoter", "bouillon", "epices", "assaisonnement",
    # Sport
    "sport", "football", "match", "joueur", "equipe",
    "score", "arbitre", "stade", "competition", "tournoi",
    # Fiction / loisirs
    "roman", "fiction", "personnage", "chapitre",
    "musique", "chanson", "artiste", "album",
    "mode", "vetement", "tendance", "beaute",
]

# Nombre minimum de termes bruit pour qualifier un document de bruit pur
# Un document juridique peut contenir quelques mots de bruit
# mais pas une concentration suffisante
SEUIL_BRUIT = 4


# ══════════════════════════════════════════════════════════════════════
# CLASSIFIEUR DE DOMAINE
# ══════════════════════════════════════════════════════════════════════

class ClassifieurDomaine:
    """
    Detecte automatiquement le(s) domaine(s) d'un document.

    Principe :
    - Score chaque domaine selon le nombre de termes trouves
    - Normalise par le nombre de termes du domaine (equite)
    - Pondere par le poids du domaine
    - Retourne le domaine principal + domaines secondaires

    EXTENSIBILITE AUTOMATIQUE :
    Si un document a un score > 0 dans aucun domaine mais contient
    des termes juridiques generaux, il est tague "autre_juridique"
    et logue pour revue manuelle. Cela permet de detecter des
    nouveaux domaines emergents sans modifier le code.
    """

    # Termes juridiques generaux (filet de securite)
    TERMES_JURIDIQUES_GENERAUX = [
        "loi", "droit", "juridique", "judiciaire", "tribunal",
        "cour", "jugement", "arret", "procedure", "article",
        "code", "decret", "ordonnance", "arrete", "reglement",
        "contrat", "obligation", "responsabilite", "sanction",
        "avocat", "notaire", "huissier", "magistrat", "juge",
        "africain", "cameroun", "gabon", "ohada", "cemac",
        "senegal", "cote d'ivoire", "benin", "afrique",
    ]

    def __init__(self):
        self.nouveaux_domaines_detectes: Set[str] = set()

    def classifier(self, texte: str) -> Dict:
        """
        Classifie un texte et retourne son profil de domaine.

        Retourne :
        {
            "domaine_principal" : "fiscalite",
            "label_principal"   : "Fiscalite et impots",
            "domaines_secondaires": ["droit_commercial", "bancaire"],
            "scores"            : {"fiscalite": 45, "droit_commercial": 12},
            "score_max"         : 45,
            "est_pertinent"     : True,
            "est_bruit"         : False,
        }
        """
        texte_lower = texte.lower()
        scores      = {}

        # Scorer chaque domaine
        for domaine_id, config in DOMAINES.items():
            termes  = config["termes"]
            poids   = config.get("poids", 1)
            trouves = sum(1 for t in termes if t in texte_lower)

            if trouves > 0:
                # Score = (termes trouves / termes total) * 100 * poids
                score_brut = (trouves / len(termes)) * 100
                scores[domaine_id] = round(score_brut * poids, 1)

        # Detecter le bruit pur
        nb_bruit  = sum(1 for t in TERMES_BRUIT if t in texte_lower)
        est_bruit = nb_bruit >= SEUIL_BRUIT and (not scores or max(scores.values(), default=0) < 10)

        # Si aucun domaine detecte — verifier termes generaux
        if not scores and not est_bruit:
            nb_generaux = sum(
                1 for t in self.TERMES_JURIDIQUES_GENERAUX
                if t in texte_lower
            )
            if nb_generaux >= 3:
                # Nouveau domaine potentiel
                scores["autre_juridique"] = nb_generaux * 2
                self.nouveaux_domaines_detectes.add("autre_juridique")

        # Trier par score
        scores_tries = sorted(scores.items(), key=lambda x: -x[1])

        if not scores_tries:
            return {
                "domaine_principal"    : None,
                "label_principal"      : None,
                "domaines_secondaires" : [],
                "scores"               : {},
                "score_max"            : 0,
                "est_pertinent"        : False,
                "est_bruit"            : est_bruit,
            }

        domaine_principal = scores_tries[0][0]
        score_max         = scores_tries[0][1]

        # Domaines secondaires (score > 30% du score principal)
        seuil_secondaire = score_max * 0.3
        domaines_sec = [
            d for d, s in scores_tries[1:]
            if s >= seuil_secondaire
        ][:3]  # max 3 domaines secondaires

        label_principal = DOMAINES.get(
            domaine_principal, {}
        ).get("label", domaine_principal)

        return {
            "domaine_principal"    : domaine_principal,
            "label_principal"      : label_principal,
            "domaines_secondaires" : domaines_sec,
            "scores"               : dict(scores_tries),
            "score_max"            : score_max,
            "est_pertinent"        : score_max > 0,
            "est_bruit"            : est_bruit,
        }

    def detecter_pays(self, texte: str) -> str:
        """Detecte le pays principal mentionne dans le texte."""
        texte_lower = texte.lower()
        pays_scores = {
            "[CM]"    : ["cameroun", "camerounais", "yaounde", "douala", "dgd"],
            "[GA]"    : ["gabon", "gabonais", "libreville", "port-gentil"],
            "[CI]"    : ["cote d'ivoire", "ivoirien", "abidjan"],
            "[SN]"    : ["senegal", "senegalais", "dakar"],
            "[BJ]"    : ["benin", "beninois", "cotonou"],
            "[BF]"    : ["burkina", "ouagadougou"],
            "[ML]"    : ["mali", "malien", "bamako"],
            "[NE]"    : ["niger", "nigerien", "niamey"],
            "[TG]"    : ["togo", "togolais", "lome"],
            "[GN]"    : ["guinee", "conakry"],
            "[CG]"    : ["congo-brazzaville", "brazzaville"],
            "[CD]"    : ["rdc", "congo-kinshasa", "kinshasa"],
            "[TD]"    : ["tchad", "tchadien", "ndjamena"],
            "[CF]"    : ["centrafrique", "bangui"],
            "[GQ]"    : ["guinee equatoriale", "malabo"],
            "[OHADA]" : ["ohada", "acte uniforme", "ccja"],
            "[CEMAC]" : ["cemac", "beac", "cobac"],
            "[UEMOA]" : ["uemoa", "bceao"],
        }
        scores = {}
        for token, mots in pays_scores.items():
            s = sum(1 for m in mots if m in texte_lower)
            if s > 0:
                scores[token] = s

        if not scores:
            return "[OHADA]"
        return max(scores, key=scores.get)

    def rapport_nouveaux_domaines(self) -> List[str]:
        return list(self.nouveaux_domaines_detectes)


# Instance globale du classifieur
# Utilise ClassifieurHybride si disponible, sinon fallback ClassifieurDomaine
if CLASSIFIER_OK:
    classifieur = _CLASSIFIEUR
else:
    classifieur = ClassifieurDomaine()


# ══════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════

def hash_texte(texte: str) -> str:
    texte_norm = re.sub(r'\s+', ' ', texte.lower().strip())
    return hashlib.sha256(texte_norm.encode('utf-8')).hexdigest()


def decouper_en_passages(
    texte    : str,
    max_chars: int = MAX_CHARS_PASSAGE,
    overlap  : int = OVERLAP_CHARS,
) -> List[str]:
    if len(texte) <= max_chars:
        return [texte] if len(texte) >= MIN_CHARS else []

    passages = []
    debut    = 0

    while debut < len(texte):
        fin = debut + max_chars
        if fin < len(texte):
            for sep in ['. ', '.\n', '\n\n', '\n', ' ']:
                pos = texte.rfind(sep, debut, fin)
                if pos > debut + max_chars // 2:
                    fin = pos + len(sep)
                    break

        passage = texte[debut:fin].strip()
        if len(passage) >= MIN_CHARS:
            passages.append(passage)
        debut = max(debut + 1, fin - overlap)

    return passages


def nettoyer_texte(texte: str) -> str:
    """
    Nettoyage du texte extrait d un PDF.

    Deux niveaux :
    1. Nettoyage standard (retours chariot, espaces, pages)
    2. Filtre artefacts OCR (symboles parasites, series de points)

    POINT CRITIQUE — filtre artefacts OCR :
    Tesseract produit des artefacts sur les documents mal scannes :
      Series de points : .........  ou  ---------
      Symboles parasites : paragraphe, copyright, fleches
      Sequences non-alphabetiques longues
    Ces artefacts consomment du vocabulaire BPE inutilement.

    CE QU ON NE SUPPRIME PAS :
    - Numeros d articles (art. 34)
    - Tirets dans termes composes (garde-a-vue)
    - Ponctuation juridique standard (. , ; : ! ?)
    - Guillemets et apostrophes (citations juridiques)
    """
    # Nettoyage standard
    texte = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', texte)
    texte = re.sub(r'\r\n', '\n', texte)
    texte = re.sub(r'\r', '\n', texte)
    texte = re.sub(r'^\s*\d+\s*$', '', texte, flags=re.MULTILINE)
    texte = re.sub(r' +$', '', texte, flags=re.MULTILINE)
    texte = re.sub(r'\n{3,}', '\n\n', texte)
    texte = re.sub(r'[ \t]+', ' ', texte)

    # Filtre artefacts OCR
    # Series de points/tirets/barres/underscores (4+ consecutifs)
    texte = re.sub(r'[.\-_|]{4,}', ' ', texte)

    # Symboles parasites Tesseract
    texte = re.sub(r'[§¤©®°±←→↑↓•·■□▪▫★☆✓✗†‡‰′″‹›«»]', ' ', texte)

    # Sequences non-alphanumeriques > 3 consecutifs
    # (tampons, filigranes, codes-barres mal lus)
    texte = re.sub(r'[^\w\s\-\'\".,;:!?()/\n%&#@]{3,}', ' ', texte)

    # Sequences de chiffres tres longues (codes-barres, numeros serie)
    texte = re.sub(r'\d{15,}', ' ', texte)

    # Nettoyage final
    texte = re.sub(r' {2,}', ' ', texte)
    texte = re.sub(r'\n ', '\n', texte)

    return texte.strip()



# ══════════════════════════════════════════════════════════════════════
# PRETRAITEMENT IMAGE — Binarisation Otsu + Deskewing
#
# Ces deux etapes sont obligatoires avant Tesseract sur des documents
# scannés ou photocopiés (très fréquents dans les fora juridiques africains).
#
# POINT CRITIQUE — Otsu vs seuillage fixe :
# Le seuillage fixe (ex: tout pixel > 128 = blanc) echoue sur les
# documents avec eclairage inégal (scan de livre = plus sombre au centre).
# Otsu calcule automatiquement le seuil optimal par analyse de l'histogramme.
# Résultat : 20-30% d'amélioration sur les documents photocopiés.
#
# POINT CRITIQUE — Deskewing :
# Tesseract tombe à 40-60% de précision sur un document incliné de 3°.
# On détecte l'angle via minAreaRect (rectangle minimal englobant
# les pixels de texte) et on corrige par rotation affine.
# Correction limitée à ±45° pour éviter les faux positifs sur
# des documents avec peu de texte.
# ══════════════════════════════════════════════════════════════════════

def deskew(image_np):
    """
    Redresse un document incliné.

    Algorithme :
    1. Trouver les coordonnées de tous les pixels non-blancs
    2. Calculer le rectangle minimal les englobant (minAreaRect)
    3. Extraire l'angle d'inclinaison
    4. Appliquer une rotation affine inverse

    POINT CRITIQUE — angle < 0.5° :
    En dessous de 0.5°, la correction est inutile et peut
    introduire des artefacts d interpolation. On ignore.

    POINT CRITIQUE — angle > 45° :
    minAreaRect retourne des angles entre -90° et 0°.
    Un angle < -45° signifie que le document est en portrait
    mais détecté en paysage → ajouter 90°.
    """
    if not OPENCV_OK:
        return image_np

    coords = np.column_stack(np.where(image_np < 128))  # pixels sombres = texte
    if len(coords) < 50:
        # Pas assez de pixels texte pour estimer l angle — retourner tel quel
        return image_np

    angle = cv2.minAreaRect(coords.astype(np.float32))[-1]

    # Correction de l angle selon la convention minAreaRect
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90

    # Ignorer les inclinaisons negligeables
    if abs(angle) < 0.5:
        return image_np

    # Rotation affine
    (h, w)  = image_np.shape[:2]
    centre  = (w // 2, h // 2)
    M       = cv2.getRotationMatrix2D(centre, angle, 1.0)
    redresse = cv2.warpAffine(
        image_np, M, (w, h),
        flags      = cv2.INTER_CUBIC,
        borderMode = cv2.BORDER_REPLICATE,
    )
    return redresse


def binariser_otsu(image_np):
    """
    Binarisation par seuillage d Otsu.

    Otsu minimise la variance intra-classe entre pixels sombres
    (texte) et pixels clairs (fond). Le seuil optimal est calculé
    automatiquement depuis l histogramme de l image.

    Avantage sur seuillage adaptatif :
    Plus rapide, suffisant pour la majorité des documents.
    Pour des documents très dégradés (seuillage adaptatif serait
    meilleur), Tesseract échouerait de toute façon.

    Retourne une image binaire : 0=noir (texte), 255=blanc (fond).
    """
    if not OPENCV_OK:
        return image_np

    # S assurer qu on est en niveaux de gris
    if len(image_np.shape) == 3:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
    else:
        gray = image_np.copy()

    # Débruitage léger avant seuillage
    # h=10 : agressivité du débruitage (0=aucun, 20=fort)
    # Trop fort = perte de detail sur les petits caractères
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Seuillage Otsu
    _, binary = cv2.threshold(
        denoised, 0, 255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return binary


def pretraiter_image_ocr(pil_image):
    """
    Pipeline complet de prétraitement OCR :
        1. Conversion en niveaux de gris
        2. Débruitage
        3. Binarisation Otsu
        4. Deskewing (redressement)

    Retourne une image PIL prête pour Tesseract.

    POINT CRITIQUE — ordre des opérations :
    L ordre est important. Le deskewing APRÈS binarisation est plus
    précis car les pixels sont déjà binarisés (0 ou 255) — pas de
    valeurs intermédiaires qui brouillent la détection de l angle.

    POINT CRITIQUE — si OpenCV absent :
    Retourne l image PIL originale sans prétraitement.
    Tesseract tournera quand même, avec une qualité moindre.
    """
    if not OPENCV_OK:
        return pil_image

    # PIL → numpy
    img_np = np.array(pil_image)

    # 1. Binarisation Otsu (inclut niveaux de gris + débruitage)
    binary = binariser_otsu(img_np)

    # 2. Deskewing sur image binaire
    redresse = deskew(binary)

    # 3. Re-binarisation apres deskew
    # POINT CRITIQUE : warpAffine avec INTER_CUBIC cree des valeurs
    # intermediaires par interpolation. On re-binarise avec seuil
    # fixe 128 pour retrouver une image strictement binaire.
    if OPENCV_OK and len(redresse.shape) == 2:
        _, redresse = cv2.threshold(redresse, 128, 255, cv2.THRESH_BINARY)

    # numpy → PIL
    return Image.fromarray(redresse)

# ══════════════════════════════════════════════════════════════════════
# EXTRACTION PDF
# ══════════════════════════════════════════════════════════════════════

def extraire_texte_pdf(chemin_pdf: str) -> Optional[str]:
    if not PYMUPDF_OK:
        return None
    try:
        doc       = fitz.open(chemin_pdf)
        textes    = []
        pages_ocr = 0

        for num_page, page in enumerate(doc):
            texte_page = page.get_text("text")
            if len(texte_page.strip()) < 50:
                if TESSERACT_OK:
                    try:
                        # DPI 300 pour meilleure qualite OCR
                        # 200 DPI = limite basse, 300 = recommande pour juridique
                        pix        = page.get_pixmap(dpi=300)
                        img        = Image.open(io.BytesIO(pix.tobytes("png")))

                        # Pretraitement : Otsu + Deskewing
                        # POINT CRITIQUE : sans ce pretraitement, Tesseract
                        # produit 40-60% d erreurs sur docs scannés inclinés
                        img        = pretraiter_image_ocr(img)

                        # OCR avec configuration optimisee pour le francais juridique
                        # --oem 3 : moteur LSTM (meilleur pour le francais)
                        # --psm 6 : assume un bloc de texte uniforme
                        config_tess = "--oem 3 --psm 6"
                        texte_page  = pytesseract.image_to_string(
                            img,
                            lang   = "fra+eng",
                            config = config_tess,
                        )
                        pages_ocr += 1
                    except Exception as e:
                        logger.debug(f"OCR page {num_page+1} : {e}")
                        continue
                else:
                    continue
            textes.append(texte_page)

        doc.close()
        if pages_ocr > 0:
            logger.info(f"  OCR applique : {pages_ocr} pages")

        texte_complet = "\n\n".join(textes)
        return nettoyer_texte(texte_complet) if texte_complet else None

    except Exception as e:
        logger.error(f"Erreur PDF {chemin_pdf}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# MODULE 1 — INGESTION PDFs LOCAUX
# ══════════════════════════════════════════════════════════════════════

def ingerer_pdfs_locaux(
    raw_dir : str,
    dry_run : bool = False,
    seuil   : int  = SEUIL_DEFAUT,
) -> Tuple[List[Dict], Dict]:

    logger.info(f"\n{'='*60}")
    logger.info(f"  MODULE 1 — Ingestion PDFs locaux")
    logger.info(f"  Dossier : {raw_dir}")
    logger.info(f"  Seuil   : {seuil}/100")
    logger.info(f"{'='*60}")

    if not os.path.exists(raw_dir):
        logger.warning(f"Dossier absent : {raw_dir}")
        logger.info(f"Creez data/raw/ et deposez vos PDFs dedans.")
        return [], {"erreur": "dossier_absent"}

    tous     = list(Path(raw_dir).rglob("*"))
    pdfs     = [f for f in tous if f.suffix.lower() == ".pdf"]
    non_pdfs = [f for f in tous if f.suffix.lower() != ".pdf" and f.is_file()]

    logger.info(f"  PDFs trouves     : {len(pdfs)}")
    logger.info(f"  Non-PDFs ignores : {len(non_pdfs)}")

    if non_pdfs:
        for f in non_pdfs[:5]:
            logger.info(f"    Ignore : {f.name}")
        if len(non_pdfs) > 5:
            logger.info(f"    ... et {len(non_pdfs)-5} autres")

    if not pdfs:
        logger.warning(f"Aucun PDF trouve dans {raw_dir}")
        return [], {"pdfs_trouves": 0}

    passages   = []
    hashes_vus = set()
    rapport    = {
        "pdfs_trouves"   : len(pdfs),
        "pdfs_acceptes"  : 0,
        "pdfs_rejetes"   : 0,
        "doublons"       : 0,
        "bruit"          : 0,
        "hors_seuil"     : 0,
        "trop_courts"    : 0,
        "erreurs"        : 0,
        "passages_total" : 0,
        "par_domaine"    : defaultdict(int),
        "fichiers"       : [],
    }

    for i, pdf_path in enumerate(sorted(pdfs)):
        nom = pdf_path.name
        logger.info(f"\n  [{i+1}/{len(pdfs)}] {nom}")

        fiche = {
            "fichier"        : nom,
            "statut"         : None,
            "raison"         : None,
            "domaine"        : None,
            "score"          : 0,
            "passages"       : 0,
        }

        # Extraire
        texte = extraire_texte_pdf(str(pdf_path))
        if not texte:
            logger.warning(f"    ✗ Extraction echouee")
            fiche["statut"] = "erreur"
            fiche["raison"] = "extraction_echouee"
            rapport["erreurs"]       += 1
            rapport["pdfs_rejetes"]  += 1
            rapport["fichiers"].append(fiche)
            continue

        logger.info(f"    Texte : {len(texte):,} chars")

        # Longueur minimale
        if len(texte) < MIN_CHARS:
            logger.warning(f"    ✗ Trop court ({len(texte)} chars)")
            fiche["statut"] = "rejete"
            fiche["raison"] = "trop_court"
            rapport["trop_courts"]   += 1
            rapport["pdfs_rejetes"]  += 1
            rapport["fichiers"].append(fiche)
            continue

        # Deduplication
        h = hash_texte(texte)
        if h in hashes_vus:
            logger.warning(f"    ✗ Doublon detecte")
            fiche["statut"] = "rejete"
            fiche["raison"] = "doublon"
            rapport["doublons"]      += 1
            rapport["pdfs_rejetes"]  += 1
            rapport["fichiers"].append(fiche)
            continue
        hashes_vus.add(h)

        # Classification de domaine
        profil = classifieur.classifier(texte)
        pays   = classifieur.detecter_pays(texte)

        fiche["domaine"] = profil["domaine_principal"]
        fiche["score"]   = profil["score_max"]

        logger.info(
            f"    Domaine : {profil['label_principal']} "
            f"(score={profil['score_max']:.1f})"
        )
        if profil["domaines_secondaires"]:
            labels_sec = [
                DOMAINES.get(d, {}).get("label", d)
                for d in profil["domaines_secondaires"]
            ]
            logger.info(f"    Secondaires : {', '.join(labels_sec)}")
        logger.info(f"    Pays : {pays}")

        # Bruit pur
        if profil["est_bruit"]:
            logger.warning(f"    ✗ Document hors scope (bruit detecte)")
            fiche["statut"] = "rejete"
            fiche["raison"] = "bruit"
            rapport["bruit"]         += 1
            rapport["pdfs_rejetes"]  += 1
            rapport["fichiers"].append(fiche)
            continue

        # Seuil de pertinence
        if not profil["est_pertinent"] or profil["score_max"] < seuil:
            logger.warning(
                f"    ✗ Score insuffisant "
                f"({profil['score_max']:.1f} < {seuil})"
            )
            fiche["statut"] = "rejete"
            fiche["raison"] = f"score_insuffisant ({profil['score_max']:.1f})"
            rapport["hors_seuil"]    += 1
            rapport["pdfs_rejetes"]  += 1
            rapport["fichiers"].append(fiche)
            continue

        # Decouper en passages
        liste_passages = decouper_en_passages(texte)
        fiche["passages"] = len(liste_passages)
        fiche["statut"]   = "accepte"

        logger.info(f"    ✓ Accepte — {len(liste_passages)} passages")

        if not dry_run:
            for passage in liste_passages:
                passages.append({
                    "texte"               : passage,
                    "source"              : f"pdf_local:{nom}",
                    "domaine"             : profil["domaine_principal"],
                    "domaines_secondaires": profil["domaines_secondaires"],
                    "pays"                : pays,
                    "score"               : profil["score_max"],
                    "date"                : datetime.now().strftime("%Y-%m-%d"),
                })

        rapport["pdfs_acceptes"]                         += 1
        rapport["passages_total"]                        += len(liste_passages)
        rapport["par_domaine"][profil["domaine_principal"]] += 1
        rapport["fichiers"].append(fiche)

    # Rapport module 1
    logger.info(f"\n{'='*60}")
    logger.info(f"  RAPPORT MODULE 1")
    logger.info(f"  PDFs acceptes  : {rapport['pdfs_acceptes']}")
    logger.info(f"  PDFs rejetes   : {rapport['pdfs_rejetes']}")
    logger.info(f"    Doublons     : {rapport['doublons']}")
    logger.info(f"    Bruit        : {rapport['bruit']}")
    logger.info(f"    Score faible : {rapport['hors_seuil']}")
    logger.info(f"    Trop courts  : {rapport['trop_courts']}")
    logger.info(f"    Erreurs      : {rapport['erreurs']}")
    logger.info(f"  Passages       : {rapport['passages_total']}")

    if rapport["par_domaine"]:
        logger.info(f"  Repartition par domaine :")
        for dom, nb in sorted(
            rapport["par_domaine"].items(), key=lambda x: -x[1]
        ):
            label = DOMAINES.get(dom, {}).get("label", dom)
            logger.info(f"    {label:<35} : {nb} PDFs")

    # Nouveaux domaines detectes
    nouveaux = []  # ClassifieurHybride - voir rapport_stats()
    if nouveaux:
        logger.info(f"\n  ⚠ Nouveaux domaines detectes : {nouveaux}")
        logger.info(f"    Verifier scraper_log.json pour revue manuelle")

    return passages, dict(rapport)


# ══════════════════════════════════════════════════════════════════════
# MODULE 2 — SCRAPER CCJA
# ══════════════════════════════════════════════════════════════════════

def verifier_robots_txt(base_url: str) -> bool:
    import urllib.robotparser
    try:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        rp.read()
        return rp.can_fetch(USER_AGENT, base_url + "/")
    except Exception:
        return True  # robots.txt absent = pas de restriction


def requete_securisee(url, session, timeout=15):
    time.sleep(RATE_LIMIT + random.uniform(0, 1))
    try:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("Rate limit — pause 30s")
            time.sleep(30)
        return None
    except Exception:
        return None


def scraper_ccja(
    max_pages : int = 50,
    dry_run   : bool = False,
    seuil     : int  = SEUIL_DEFAUT,
) -> Tuple[List[Dict], Dict]:

    logger.info(f"\n{'='*60}")
    logger.info(f"  MODULE 2 — Scraper CCJA")
    logger.info(f"{'='*60}")

    if not REQUESTS_OK:
        return [], {"erreur": "requests_absent"}

    BASE_URL = "https://www.ccja-ohada.org"
    if not verifier_robots_txt(BASE_URL):
        logger.error("robots.txt interdit le scraping — annule")
        return [], {"erreur": "robots_txt_interdit"}

    session = requests.Session()
    session.headers.update({
        "User-Agent"     : USER_AGENT,
        "Accept-Language": "fr-FR,fr;q=0.9",
    })

    passages   = []
    hashes_vus = set()
    rapport    = {
        "pages_visitees"     : 0,
        "decisions_acceptees": 0,
        "doublons"           : 0,
        "passages_total"     : 0,
    }

    urls_depart = [
        f"{BASE_URL}/jurisprudence",
        f"{BASE_URL}/arrets",
        f"{BASE_URL}/fr/jurisprudence",
    ]
    urls_visitees  = set()
    pages_traitees = 0

    for url_dep in urls_depart:
        if pages_traitees >= max_pages:
            break
        r = requete_securisee(url_dep, session)
        if not r:
            continue

        rapport["pages_visitees"] += 1
        pages_traitees            += 1
        soup = BeautifulSoup(r.text, "html.parser")

        for lien in soup.find_all("a", href=True):
            href = lien["href"]
            if href.startswith("/"):
                href = BASE_URL + href
            elif not href.startswith("http"):
                continue

            mots_cles = ["decision", "arret", "jurisprudence", "ccja"]
            if not any(m in href.lower() for m in mots_cles):
                continue
            if href in urls_visitees:
                continue
            urls_visitees.add(href)
            if pages_traitees >= max_pages:
                break

            r2 = requete_securisee(href, session)
            if not r2:
                continue

            rapport["pages_visitees"] += 1
            pages_traitees            += 1
            soup2 = BeautifulSoup(r2.text, "html.parser")

            contenu = None
            for sel in ["article", "main", ".content", "#content"]:
                el = soup2.select_one(sel)
                if el:
                    contenu = el.get_text(separator="\n")
                    break
            if not contenu:
                body    = soup2.find("body")
                contenu = body.get_text(separator="\n") if body else ""

            contenu = nettoyer_texte(contenu)
            if len(contenu) < MIN_CHARS:
                continue

            h = hash_texte(contenu)
            if h in hashes_vus:
                rapport["doublons"] += 1
                continue
            hashes_vus.add(h)

            profil = classifieur.classifier(contenu)
            pays   = classifieur.detecter_pays(contenu)

            if not profil["est_pertinent"] or profil["score_max"] < seuil:
                continue

            liste_passages = decouper_en_passages(contenu)
            rapport["decisions_acceptees"] += 1
            rapport["passages_total"]      += len(liste_passages)

            logger.info(
                f"  ✓ {href[-50:]} "
                f"({len(liste_passages)} passages, "
                f"domaine={profil['domaine_principal']})"
            )

            if not dry_run:
                for p in liste_passages:
                    passages.append({
                        "texte"   : p,
                        "source"  : f"ccja:{href}",
                        "domaine" : profil["domaine_principal"],
                        "pays"    : pays,
                        "score"   : profil["score_max"],
                        "date"    : datetime.now().strftime("%Y-%m-%d"),
                    })

    logger.info(f"  Pages visitees      : {rapport['pages_visitees']}")
    logger.info(f"  Decisions acceptees : {rapport['decisions_acceptees']}")
    logger.info(f"  Passages            : {rapport['passages_total']}")
    return passages, rapport


# ══════════════════════════════════════════════════════════════════════
# SAUVEGARDE
# ══════════════════════════════════════════════════════════════════════

def sauvegarder_dataset(
    nouveaux_passages : List[Dict],
    rapport_global    : Dict,
    dry_run           : bool = False,
):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    dataset = {"passages": [], "paires_qr": [], "metadata": {}}
    if os.path.exists(DATASET_PATH):
        try:
            with open(DATASET_PATH, "r", encoding="utf-8") as f:
                dataset = json.load(f)
            logger.info(f"  Passages existants : {len(dataset.get('passages', []))}")
        except Exception as e:
            logger.warning(f"  Lecture dataset : {e}")

    # Deduplication finale
    hashes_ex = {
        hash_texte(p["texte"])
        for p in dataset.get("passages", [])
        if isinstance(p, dict) and "texte" in p
    }
    uniques       = []
    doublons_fin  = 0
    for p in nouveaux_passages:
        h = hash_texte(p["texte"])
        if h not in hashes_ex:
            uniques.append(p)
            hashes_ex.add(h)
        else:
            doublons_fin += 1

    logger.info(f"  Nouveaux uniques   : {len(uniques)}")
    if doublons_fin:
        logger.info(f"  Doublons finaux    : {doublons_fin}")

    if dry_run:
        logger.info("  [DRY-RUN] Pas de sauvegarde")
        return

    dataset["passages"].extend(uniques)

    # Stats par domaine
    stats_domaines = defaultdict(int)
    for p in dataset["passages"]:
        if isinstance(p, dict):
            dom = p.get("domaine", "inconnu")
            stats_domaines[dom] += 1

    dataset["metadata"] = {
        "derniere_maj"  : datetime.now().isoformat(),
        "total_passages": len(dataset["passages"]),
        "tokens_estimes": sum(
            len(p.get("texte","")) // 5
            for p in dataset["passages"]
            if isinstance(p, dict)
        ),
        "par_domaine"   : dict(stats_domaines),
        "nouveaux_domaines_detectes": []  # ClassifieurHybride - voir rapport_stats(),
    }

    with open(DATASET_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "date"    : datetime.now().isoformat(),
            "rapport" : rapport_global,
        }, f, ensure_ascii=False, indent=2)

    taille = os.path.getsize(DATASET_PATH) // (1024 * 1024)
    logger.info(f"\n  Dataset : {DATASET_PATH} ({taille} Mo)")
    logger.info(f"  Total   : {dataset['metadata']['total_passages']:,} passages")
    logger.info(f"  Tokens  : ~{dataset['metadata']['tokens_estimes']:,}")

    # Repartition domaines
    logger.info(f"\n  Repartition par domaine :")
    for dom, nb in sorted(stats_domaines.items(), key=lambda x: -x[1]):
        label = DOMAINES.get(dom, {}).get("label", dom)
        pct   = nb / max(len(dataset["passages"]), 1) * 100
        logger.info(f"    {label:<35} : {nb:>6} passages ({pct:.1f}%)")


def afficher_progression(dataset_path: str):
    if not os.path.exists(dataset_path):
        return
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    passages     = data.get("passages", [])
    tokens_est   = sum(len(p.get("texte","")) // 5 for p in passages)
    tokens_cible = 500_000_000
    pct          = tokens_est / tokens_cible * 100

    logger.info(f"\n{'='*60}")
    logger.info(f"  PROGRESSION CORPUS COR")
    logger.info(f"{'='*60}")
    logger.info(f"  Passages : {len(passages):,}")
    logger.info(f"  Tokens   : {tokens_est:,} / {tokens_cible:,}")
    logger.info(f"  Progress : {'█' * int(pct/5)}{'-' * (20-int(pct/5))} {pct:.2f}%")
    if tokens_est < tokens_cible:
        logger.info(f"  Manque   : ~{tokens_cible - tokens_est:,} tokens")
        logger.info(f"  Action   : ajouter des PDFs dans data/raw/")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="COR — Collecte corpus juridique africain"
    )
    parser.add_argument("--module",    choices=["pdfs","ccja","all"], default="pdfs")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--seuil",     type=int, default=SEUIL_DEFAUT)
    args = parser.parse_args()

    logger.info(f"{'='*60}")
    logger.info(f"  COR SCRAPER")
    logger.info(f"  Module : {args.module} | Seuil : {args.seuil} | Dry-run : {args.dry_run}")
    logger.info(f"  Domaines couverts : {len(DOMAINES)}")
    logger.info(f"{'='*60}")

    tous_passages  = []
    rapport_global = {}

    if args.module in ("pdfs", "all"):
        p, r = ingerer_pdfs_locaux(RAW_DIR, args.dry_run, args.seuil)
        tous_passages.extend(p)
        rapport_global["pdfs"] = r

    if args.module in ("ccja", "all"):
        p, r = scraper_ccja(args.max_pages, args.dry_run, args.seuil)
        tous_passages.extend(p)
        rapport_global["ccja"] = r

    logger.info(f"\n  Passages collectes : {len(tous_passages):,}")
    sauvegarder_dataset(tous_passages, rapport_global, args.dry_run)

    if not args.dry_run:
        afficher_progression(DATASET_PATH)

    logger.info(f"\n  Termine. Etape suivante : scripts/train.py --phase tokenizer")


if __name__ == "__main__":
    main()