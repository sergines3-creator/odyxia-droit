# cor_classifier.py
# COR — Classifieur hybride de domaines juridiques africains
#
# Architecture en 3 étapes :
#
#   Étape 1 — Règles prioritaires (regex compilé)
#             Si le texte contient "code des douanes" → douane garanti
#             Résultat immédiat, < 1ms
#
#   Étape 2 — Score regex compilé
#             Patterns compilés une seule fois au chargement
#             Pas de faux positifs sur termes courts ("or", "sa", "port")
#             Score > SEUIL_CONFIANCE_HAUTE → résultat fiable, stop
#             Score entre SEUIL_BAS et SEUIL_CONFIANCE_HAUTE → étape 3
#             Score < SEUIL_BAS → rejeter
#
#   Étape 3 — SBERT embeddings (paraphrase-multilingual-MiniLM-L12-v2)
#             Cosine similarity avec phrases de référence par domaine
#             Résout les ambiguïtés que le scoring ne peut pas trancher
#             Supporte français ET anglais nativement
#
# POINTS CRITIQUES :
#
#   1. Les patterns regex sont compilés UNE SEULE FOIS au chargement
#      (variable module PATTERNS_DOMAINES et PATTERNS_PRIORITAIRES)
#      Ne jamais compiler dans une boucle — catastrophique pour les perfs
#
#   2. SBERT est chargé lazily (à la première utilisation)
#      Le modèle fait ~500Mo RAM — on ne le charge que si nécessaire
#      Si SBERT absent → fallback sur scoring seul avec seuil abaissé
#
#   3. Les phrases de référence SBERT sont soigneusement choisies
#      Elles représentent le "prototype" de chaque domaine
#      Mauvaises phrases de référence = mauvaise classification
#
#   4. Ce fichier est utilisé par cor_scraper.py ET cor_retagger.py
#      Toute modification impacte les deux pipelines
#
# Usage :
#   from cor_classifier import ClassifieurHybride
#   clf = ClassifieurHybride()
#   profil = clf.classifier(texte)
#   pays   = clf.detecter_pays(texte)

import os
import re
import sys
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Seuils de décision
SEUIL_BAS             = 4    # En dessous → rejeter sans SBERT
SEUIL_CONFIANCE_HAUTE = 40   # Au dessus → accepter sans SBERT
SEUIL_SBERT           = 0.35 # Cosine similarity minimum pour SBERT

# ══════════════════════════════════════════════════════════════════════
# TAXONOMIE DES DOMAINES — Version 3 (Hybride)
#
# Structure :
#   termes_fr     : termes français (regex \b...\b)
#   termes_en     : termes anglais (pour corpus futur)
#   priority_fr   : règles prioritaires françaises
#   priority_en   : règles prioritaires anglaises
#   refs_sbert_fr : phrases de référence SBERT françaises
#   refs_sbert_en : phrases de référence SBERT anglaises
#   poids         : multiplicateur de score (1-4)
# ══════════════════════════════════════════════════════════════════════

DOMAINES = {

    "droit_ohada": {
        "label" : "Droit OHADA",
        "poids" : 3,
        "termes_fr": [
            "ohada", "acte uniforme", "ccja", "aupsrve", "audcg",
            "auscgie", "aurve", "aupap", "autf", "auohsada", "auscoop",
            "droit uniforme", "organisation pour harmonisation",
            "traite ohada", "espace ohada",
            "cour commune de justice", "arbitrage ohada",
        ],
        "priority_fr": [
            "acte uniforme", "organisation pour l'harmonisation en afrique",
            "traite relatif a l'harmonisation",
        ],
        "refs_sbert_fr": [
            "L'acte uniforme OHADA régit les sociétés commerciales dans les 17 États membres.",
            "La CCJA est la juridiction supranationale de l'espace OHADA.",
            "Le droit OHADA harmonise le droit des affaires en Afrique francophone.",
            "L'AUPSRVE fixe les procédures simplifiées de recouvrement des créances.",
        ],
    },

    "droit_cemac": {
        "label" : "Droit CEMAC/COBAC",
        "poids" : 3,
        "termes_fr": [
            "cemac", "cobac", "beac", "bvmac", "cosumaf",
            "zone cemac", "communaute economique afrique centrale",
            "franc cfa", "reglementation bancaire cemac",
            "instruction cobac", "commission bancaire",
            "supervision bancaire cemac",
        ],
        "priority_fr": [
            "zone cemac", "banque des etats afrique centrale",
            "commission bancaire afrique centrale",
        ],
        "refs_sbert_fr": [
            "La COBAC supervise les établissements de crédit dans la zone CEMAC.",
            "La BEAC émet la monnaie commune des six États de la CEMAC.",
            "Le règlement CEMAC encadre les opérations bancaires transfrontalières.",
        ],
    },

    "droit_uemoa": {
        "label" : "Droit UEMOA/BCEAO",
        "poids" : 3,
        "termes_fr": [
            "uemoa", "bceao", "union economique monetaire ouest africaine",
            "zone uemoa", "commission uemoa",
            "instruction bceao", "ratio prudentiel uemoa",
        ],
        "priority_fr": [
            "banque centrale etats afrique ouest",
            "union economique monetaire ouest africaine",
        ],
        "refs_sbert_fr": [
            "La BCEAO est la banque centrale commune des États de l'UEMOA.",
            "La Commission de l'UEMOA édicte des directives harmonisées.",
        ],
    },

    "droit_travail": {
        "label" : "Droit du travail",
        "poids" : 3,
        "termes_fr": [
            "code du travail", "licenciement", "salarie", "employeur",
            "preavis", "smig", "smag", "syndicat", "greve",
            "convention collective", "inspection du travail",
            "tribunal du travail", "contrat de travail",
            "rupture abusive", "indemnite de licenciement",
            "periode essai", "heures supplementaires",
            "conge annuel", "accident du travail", "cnps",
            "securite sociale travail", "cotisations sociales",
            "mise a pied disciplinaire",
        ],
        "priority_fr": [
            "code du travail", "tribunal du travail",
            "inspection du travail",
        ],
        "refs_sbert_fr": [
            "Le licenciement sans préavis oblige l'employeur à verser une indemnité compensatrice.",
            "Le code du travail fixe la durée minimale du préavis selon l'ancienneté.",
            "Le syndicat représente les salariés dans les négociations collectives.",
            "L'inspection du travail contrôle les conditions de travail dans les entreprises.",
        ],
    },

    "droit_penal": {
        "label" : "Droit pénal",
        "poids" : 3,
        "termes_fr": [
            "code penal", "infraction penale", "delit", "crime",
            "garde vue", "detention provisoire", "mise en examen",
            "instruction penale", "parquet", "procureur republique",
            "tribunal correctionnel", "cour assises",
            "peine emprisonnement", "amende penale",
            "liberte provisoire", "perquisition",
            "trafic influence", "corruption active", "detournement",
            "blanchiment argent", "recel", "escroquerie",
            "abus confiance", "faux usage faux",
        ],
        "priority_fr": [
            "code penal", "tribunal correctionnel",
            "instruction penale", "garde a vue",
        ],
        "refs_sbert_fr": [
            "La détention provisoire est ordonnée par le juge d'instruction.",
            "Le tribunal correctionnel juge les délits passibles d'emprisonnement.",
            "La corruption d'agents publics est sanctionnée par le code pénal.",
        ],
    },

    "droit_civil": {
        "label" : "Droit civil",
        "poids" : 2,
        "termes_fr": [
            "code civil", "obligation contractuelle", "responsabilite civile",
            "dommages interets", "prejudice subi", "faute civile",
            "prescription civile", "nullite contrat", "rescision",
            "droit famille", "mariage civil", "divorce judiciaire",
            "succession legale", "heritage", "testament olographe",
            "tutelle mineurs", "adoption legale", "filiation",
            "capacite juridique", "personne morale",
        ],
        "priority_fr": [
            "code civil", "droit de la famille",
        ],
        "refs_sbert_fr": [
            "Le code civil régit les obligations contractuelles et la responsabilité.",
            "La prescription extinctive éteint le droit d'agir en justice.",
            "Le mariage civil produit des effets juridiques reconnus par la loi.",
            "La succession ab intestat s'ouvre en l'absence de testament.",
        ],
    },

    "droit_commercial": {
        "label" : "Droit commercial",
        "poids" : 2,
        "termes_fr": [
            "code commerce", "acte commerce", "commercant",
            "fonds commerce", "societe commerciale",
            "societe responsabilite limitee", "societe anonyme",
            "societe actions simplifiee", "societe nom collectif",
            "groupement interet economique",
            "registre commerce", "rccm",
            "lettre change", "billet ordre", "cheque commercial",
            "nantissement commercial", "gage commercial",
            "faillite", "liquidation judiciaire", "redressement judiciaire",
            "concordat preventif", "masse creanciers",
        ],
        "priority_fr": [
            "code de commerce", "registre du commerce",
            "liquidation judiciaire", "redressement judiciaire",
        ],
        "refs_sbert_fr": [
            "La société à responsabilité limitée est constituée par apport au capital.",
            "Le registre du commerce et du crédit mobilier (RCCM) immatricule les commerçants.",
            "La liquidation judiciaire met fin à l'activité de l'entreprise en cessation de paiements.",
            "La lettre de change est un effet de commerce négociable.",
        ],
    },

    "droit_francais": {
        "label" : "Droit français (matrice)",
        "poids" : 2,
        "termes_fr": [
            "code civil francais", "code commerce francais",
            "cour cassation", "conseil etat francais",
            "jurisprudence francaise", "doctrine francaise",
            "droit francais", "legislation francaise",
            "legifrance", "chambre civile cassation",
            "chambre commerciale cassation",
        ],
        "priority_fr": [
            "cour de cassation francaise",
            "code civil napoleon",
        ],
        "refs_sbert_fr": [
            "La Cour de cassation française est la juridiction suprême de l'ordre judiciaire.",
            "Le Code civil napoléonien a inspiré les législations africaines francophones.",
            "La jurisprudence de la Cour de cassation fait autorité en droit français.",
        ],
    },

    "droit_constitutionnel": {
        "label" : "Droit constitutionnel",
        "poids" : 2,
        "termes_fr": [
            "constitution", "constitutionnel", "souverainete nationale",
            "pouvoir executif", "pouvoir legislatif",
            "pouvoir judiciaire", "separation pouvoirs",
            "droits fondamentaux", "liberte publique",
            "etat droit", "republique democratique",
            "parlement national", "assemblee nationale",
            "senat", "president republique", "premier ministre",
            "referendum constitutionnel", "conseil constitutionnel",
            "revision constitutionnelle",
        ],
        "priority_fr": [
            "conseil constitutionnel",
            "revision de la constitution",
            "referendum constitutionnel",
        ],
        "refs_sbert_fr": [
            "La Constitution garantit la séparation des pouvoirs exécutif, législatif et judiciaire.",
            "Le Conseil constitutionnel veille à la conformité des lois à la Constitution.",
            "Les droits fondamentaux sont protégés par la Constitution de la République.",
        ],
    },

    "droit_administratif": {
        "label" : "Droit administratif",
        "poids" : 2,
        "termes_fr": [
            "droit administratif", "acte administratif",
            "service public", "domaine public administratif",
            "marche public", "appel offres administratif",
            "tribunal administratif", "recours exces pouvoir",
            "contentieux administratif", "fonction publique",
            "decret executif", "arrete ministeriel",
            "commission appel offres", "delegation service public",
        ],
        "priority_fr": [
            "tribunal administratif",
            "recours pour exces de pouvoir",
            "contentieux administratif",
        ],
        "refs_sbert_fr": [
            "Le tribunal administratif juge les litiges entre les citoyens et l'administration.",
            "Le recours pour excès de pouvoir annule les actes administratifs illégaux.",
            "Le service public est soumis aux principes d'égalité et de continuité.",
        ],
    },

    "fiscalite": {
        "label" : "Fiscalité et impôts",
        "poids" : 3,
        "termes_fr": [
            "code general impots", "taxe valeur ajoutee", "tva",
            "impot societes", "impot revenu personnes physiques", "irpp",
            "administration fiscale", "direction generale impots", "dgi",
            "redressement fiscal", "controle fiscal",
            "avis mise recouvrement", "exoneration fiscale",
            "abattement fiscal", "deduction fiscale",
            "contribuable", "assiette fiscale", "taux imposition",
            "patente commerciale", "taxe professionnelle",
            "droit enregistrement", "taxe fonciere",
            "droits succession fiscaux", "syscohada",
            "plan comptable", "bilan comptable",
        ],
        "priority_fr": [
            "code general des impots",
            "direction generale des impots",
            "administration fiscale",
        ],
        "refs_sbert_fr": [
            "Le code général des impôts fixe les taux de TVA applicables.",
            "La direction générale des impôts procède au contrôle fiscal des entreprises.",
            "Le redressement fiscal est notifié au contribuable après vérification.",
            "L'impôt sur les sociétés est calculé sur le bénéfice imposable.",
        ],
    },

    "douane": {
        "label" : "Droit douanier",
        "poids" : 4,
        "termes_fr": [
            "code douanes", "droit douane", "tarif douanier",
            "dedouanement", "declaration douane",
            "valeur douane", "nomenclature douaniere",
            "position tarifaire", "regime douanier",
            "transit douanier", "entrepot douanier",
            "franchise douaniere", "exoneration douaniere",
            "contrebande", "fraude douaniere", "contentieux douanier",
            "agent douanes", "direction generale douanes", "dgd",
            "tarif exterieur commun", "tec cemac",
            "convention kyoto", "organisation mondiale douanes",
            "importation marchandises", "exportation marchandises",
            "bureau douane", "mainlevee marchandises",
            "commissionnaire douane", "transitaire agree",
            "manifeste cargaison", "bon enlever",
        ],
        "priority_fr": [
            "code des douanes", "direction generale des douanes",
            "tarif exterieur commun", "dedouanement",
            "administration des douanes", "bureau des douanes",
        ],
        "refs_sbert_fr": [
            "Le code des douanes réglemente l'importation et l'exportation des marchandises.",
            "La déclaration en douane doit être déposée au bureau de douane compétent.",
            "La valeur en douane est calculée selon la méthode transactionnelle.",
            "La direction générale des douanes contrôle les flux de marchandises aux frontières.",
        ],
    },

    "foncier": {
        "label" : "Droit foncier et immobilier",
        "poids" : 3,
        "termes_fr": [
            "titre foncier", "immatriculation fonciere",
            "cadastre foncier", "propriete fonciere", "terrain",
            "lotissement", "expropriation utilite publique",
            "indemnisation expropriation",
            "bail emphyteotique", "bail commercial", "bail habitation",
            "servitude fonciere", "mitoyennete", "usufruit",
            "droit superficie", "domaine public foncier",
            "domaine prive etat", "reserve fonciere",
            "amenagement territoire", "urbanisme",
            "permis construire", "certificat urbanisme",
            "plan occupation sols", "geometre expert",
            "valeur venale", "mercuriale fonciere",
            "gouvernance fonciere", "reforme fonciere",
        ],
        "priority_fr": [
            "titre foncier", "immatriculation fonciere",
            "gouvernance fonciere", "reforme fonciere",
            "securisation fonciere",
        ],
        "refs_sbert_fr": [
            "Le titre foncier est la preuve irréfragable du droit de propriété foncière.",
            "L'immatriculation foncière au cadastre confère un droit opposable à tous.",
            "L'expropriation pour cause d'utilité publique donne lieu à indemnisation préalable.",
            "Le bail emphytéotique peut être conclu pour une durée de 18 à 99 ans.",
        ],
    },

    "mines": {
        "label" : "Droit minier",
        "poids" : 4,
        "termes_fr": [
            "code minier", "minier", "exploitation miniere",
            "permis recherche miniere", "permis exploitation miniere",
            "permis minier", "titre minier", "autorisation miniere",
            "carriere", "extraction miniere",
            "gisement", "ressources minieres", "cadastre minier",
            "redevance miniere", "taxe miniere",
            "substance minerale", "substance utile",
            "diamant", "gisement aurifere", "bauxite",
            "minerai fer", "cobalt", "coltan", "manganese", "uranium",
            "exploitation aurifere", "societe miniere",
            "operateur minier", "direction mines",
            "ministere mines", "rehabilitation miniere",
            "artisanat minier", "exploitation artisanale miniere",
        ],
        "priority_fr": [
            "code minier", "permis minier", "titre minier",
            "autorisation miniere", "cadastre minier",
            "direction des mines",
        ],
        "refs_sbert_fr": [
            "Le code minier régit l'octroi des permis de recherche et d'exploitation.",
            "Le titre minier confère à son titulaire le droit exclusif d'exploiter le gisement.",
            "La redevance minière est due à l'État par les sociétés d'exploitation.",
            "L'artisanat minier est encadré par des autorisations spécifiques.",
        ],
    },

    "petrole_energie": {
        "label" : "Droit pétrolier et énergétique",
        "poids" : 4,
        "termes_fr": [
            "code petrolier", "hydrocarbures", "petrole",
            "gaz naturel", "exploration petroliere",
            "exploitation petroliere", "permis petrolier",
            "contrat partage production", "cpp",
            "societe nationale hydrocarbures", "snh",
            "raffinerie", "pipeline", "terminal petrolier",
            "redevance petroliere", "taxe petroliere",
            "energies renouvelables", "energie electrique",
            "production electrique", "distribution electrique",
            "tarif electrique", "eneo", "sonara", "arsel",
        ],
        "priority_fr": [
            "code petrolier", "hydrocarbures",
            "contrat de partage de production",
            "societe nationale des hydrocarbures",
        ],
        "refs_sbert_fr": [
            "Le code pétrolier régit l'exploration et l'exploitation des hydrocarbures.",
            "Le contrat de partage de production fixe la répartition entre l'État et l'opérateur.",
            "La société nationale des hydrocarbures représente l'État dans les joint-ventures.",
        ],
    },

    "bancaire_finance": {
        "label" : "Droit bancaire et finance",
        "poids" : 2,
        "termes_fr": [
            "etablissement credit", "microfinance",
            "lutte blanchiment", "lbc-ft", "kyc",
            "due diligence bancaire", "financement terrorisme",
            "ratio solvabilite bancaire", "fonds propres reglementaires",
            "credit documentaire", "lettre credit bancaire",
            "garantie bancaire", "caution bancaire",
            "monnaie electronique", "mobile money",
            "marche financier", "titre financier",
        ],
        "priority_fr": [
            "lutte contre le blanchiment",
            "etablissement de credit",
        ],
        "refs_sbert_fr": [
            "Les établissements de crédit sont soumis à la réglementation prudentielle COBAC.",
            "La lutte contre le blanchiment impose des obligations de vigilance aux banques.",
        ],
    },

    "assurance": {
        "label" : "Droit des assurances (CIMA)",
        "poids" : 2,
        "termes_fr": [
            "code assurances cima", "contrat assurance",
            "prime assurance", "sinistre assurance",
            "indemnisation assurance", "assureur", "assure",
            "beneficiaire assurance", "assurance vie",
            "assurance dommages", "responsabilite civile automobile",
            "reassurance", "courtier assurance", "agent assurance",
        ],
        "priority_fr": [
            "code des assurances cima",
            "commission regionale controle assurances",
        ],
        "refs_sbert_fr": [
            "Le code des assurances CIMA régit les contrats d'assurance dans 14 États.",
            "La prime d'assurance est la contrepartie de la garantie accordée par l'assureur.",
        ],
    },

    "propriete_intellectuelle": {
        "label" : "Propriété intellectuelle (OAPI)",
        "poids" : 2,
        "termes_fr": [
            "oapi", "propriete intellectuelle", "brevet invention",
            "marque commerciale", "droit auteur", "copyright",
            "dessins modeles", "indication geographique",
            "contrefacon", "piraterie", "plagiat",
            "licence exploitation", "redevance propriete",
        ],
        "priority_fr": [
            "organisation africaine propriete intellectuelle",
            "brevet d'invention",
        ],
        "refs_sbert_fr": [
            "L'OAPI protège la propriété intellectuelle dans 17 États africains.",
            "Le brevet confère à son titulaire un monopole d'exploitation limité dans le temps.",
        ],
    },

    "environnement": {
        "label" : "Droit de l'environnement",
        "poids" : 2,
        "termes_fr": [
            "code environnement", "protection environnement",
            "etude impact environnemental", "ressources naturelles",
            "foret domaine", "eau ressource", "pollution industrielle",
            "developpement durable", "changement climatique",
            "biodiversite", "aire protegee", "deforestation",
            "evaluation environnementale", "convention bale",
        ],
        "priority_fr": [
            "code de l'environnement",
            "etude d'impact environnemental",
            "evaluation environnementale strategique",
        ],
        "refs_sbert_fr": [
            "L'étude d'impact environnemental est obligatoire avant tout projet industriel.",
            "Le code de l'environnement protège les ressources naturelles et la biodiversité.",
        ],
    },

    "transport_logistique": {
        "label" : "Transport et logistique",
        "poids" : 2,
        "termes_fr": [
            "contrat transport", "responsabilite transporteur",
            "transport maritime", "transport aerien",
            "transport routier", "transport ferroviaire",
            "fret maritime", "fret aerien",
            "connaissement maritime", "lettre voiture",
            "port maritime", "port fluvial", "aeroport international",
            "terminal portuaire", "chargeur maritime",
            "transitaire agree", "commissionnaire transport",
        ],
        "priority_fr": [
            "code de la marine marchande",
            "convention transport maritime",
        ],
        "refs_sbert_fr": [
            "Le connaissement maritime est le titre représentatif de la marchandise transportée.",
            "La responsabilité du transporteur est engagée en cas de perte ou avarie.",
        ],
    },

    "marches_publics": {
        "label" : "Marchés publics",
        "poids" : 2,
        "termes_fr": [
            "marche public", "appel offres", "code marches publics",
            "commande publique", "soumissionnaire", "titulaire marche",
            "maitre ouvrage", "maitre oeuvre",
            "delegation service public", "partenariat public prive",
            "commission marches", "dossier appel offres",
            "offre technique", "offre financiere",
        ],
        "priority_fr": [
            "code des marches publics",
            "commission des marches",
            "appel d'offres ouvert",
        ],
        "refs_sbert_fr": [
            "Le code des marchés publics encadre la commande publique et prévient la corruption.",
            "L'appel d'offres ouvert garantit la mise en concurrence des soumissionnaires.",
        ],
    },

    "sante": {
        "label" : "Droit de la santé",
        "poids" : 2,
        "termes_fr": [
            "code sante publique", "sante publique",
            "medecin praticien", "pharmacien", "hopital",
            "clinique medicale", "medicament", "autorisation mise marche",
            "ordre medecins", "responsabilite medicale",
            "faute medicale", "secret medical",
            "couverture sanitaire universelle",
        ],
        "priority_fr": [
            "code de la sante publique",
            "ordre national des medecins",
        ],
        "refs_sbert_fr": [
            "Le code de la santé publique régit l'exercice de la médecine et la pharmacie.",
            "La responsabilité médicale est engagée en cas de faute dans les soins.",
        ],
    },


    "droit_international": {
        "label" : "Droit international",
        "poids" : 2,
        "termes_fr": [
            "convention internationale", "traite international",
            "droit international", "cour permanente arbitrage",
            "reglement pacifique", "conflits internationaux",
            "nations unies", "convention de vienne",
            "droit des traites", "pacte international",
            "convention de geneve", "protocole additionnel",
            "droit humanitaire", "tribunal international",
            "cour internationale justice", "cij",
            "convention de la haye", "convention de new york",
            "accord multilateral", "convention de montevideo",
            "souverainete des etats", "immunite diplomatique",
            "droit des gens", "jus cogens",
        ],
        "priority_fr": [
            "cour permanente arbitrage",
            "convention de la haye",
            "cour internationale de justice",
            "nations unies",
            "droit international public",
        ],
        "refs_sbert_fr": [
            "La Convention de La Haye regit le reglement pacifique des conflits internationaux.",
            "La Cour Internationale de Justice est l organe judiciaire principal des Nations Unies.",
            "Le droit international des traites est codifie par la Convention de Vienne.",
            "Les conventions internationales priment sur les lois nationales en droit africain.",
        ],
    },
    "education": {
        "label" : "Droit de l'éducation",
        "poids" : 1,
        "termes_fr": [
            "code education", "loi orientation education",
            "etablissement scolaire", "diplome", "formation professionnelle",
            "ministere education", "programme scolaire",
            "enseignement superieur", "universite publique",
        ],
        "priority_fr": [
            "code de l'education",
            "loi d'orientation de l'education",
        ],
        "refs_sbert_fr": [
            "La loi d'orientation fixe les objectifs et les principes du système éducatif.",
            "L'enseignement supérieur est organisé selon le système LMD.",
        ],
    },
}

# Termes de bruit pur
TERMES_BRUIT = [
    "recette cuisine", "ingredients preparation", "faire cuire",
    "match football", "but marque", "equipe nationale",
    "roman policier", "personnage fiction",
]

# Termes hors scope académique pur
TERMES_HORS_SCOPE = [
    "memoire de master", "methodologie redaction",
    "unite formation recherche", "annee universitaire",
    "soutenance these", "redaction memoire",
    "cours methodologie", "jury soutenance",
]

# Détection de pays
PAYS_DETECTION = {
    "[CM]"    : ["cameroun", "camerounais", "yaounde", "douala", "dgd cameroun"],
    "[GA]"    : ["gabon", "gabonais", "libreville", "port-gentil"],
    "[CI]"    : ["cote ivoire", "ivoirien", "abidjan", "yamoussoukro"],
    "[SN]"    : ["senegal", "senegalais", "dakar"],
    "[BJ]"    : ["benin", "beninois", "cotonou", "porto-novo"],
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


# ══════════════════════════════════════════════════════════════════════
# COMPILATION DES PATTERNS REGEX — UNE SEULE FOIS AU CHARGEMENT
# ══════════════════════════════════════════════════════════════════════

def _compiler_patterns(domaines: Dict) -> Tuple[Dict, Dict, Dict]:
    """
    Compile tous les patterns regex une seule fois au chargement du module.

    POINT CRITIQUE — compilation unique :
    re.compile() est coûteux. Compilé dans une boucle sur 414K passages
    = catastrophique. Compilé une fois → réutilisé pour tous les passages.

    Retourne :
        patterns_termes    : {domaine_id: compiled_pattern}
        patterns_priority  : {domaine_id: compiled_pattern}
        patterns_pays      : {token: compiled_pattern}
    """
    patterns_termes   = {}
    patterns_priority = {}

    for did, cfg in domaines.items():
        termes = cfg.get("termes_fr", [])
        if termes:
            pattern = r'\b(?:' + '|'.join(re.escape(t) for t in termes) + r')\b'
            patterns_termes[did] = re.compile(pattern, re.IGNORECASE)

        priority = cfg.get("priority_fr", [])
        if priority:
            pattern = r'\b(?:' + '|'.join(re.escape(p) for p in priority) + r')\b'
            patterns_priority[did] = re.compile(pattern, re.IGNORECASE)

    patterns_pays = {}
    for token, mots in PAYS_DETECTION.items():
        pattern = r'\b(?:' + '|'.join(re.escape(m) for m in mots) + r')\b'
        patterns_pays[token] = re.compile(pattern, re.IGNORECASE)

    # Patterns bruit et hors scope
    pattern_bruit = re.compile(
        r'\b(?:' + '|'.join(re.escape(t) for t in TERMES_BRUIT) + r')\b',
        re.IGNORECASE
    )
    pattern_hors_scope = re.compile(
        r'\b(?:' + '|'.join(re.escape(t) for t in TERMES_HORS_SCOPE) + r')\b',
        re.IGNORECASE
    )

    return patterns_termes, patterns_priority, patterns_pays, pattern_bruit, pattern_hors_scope


# Compilation au chargement du module
(PATTERNS_TERMES,
 PATTERNS_PRIORITY,
 PATTERNS_PAYS,
 PATTERN_BRUIT,
 PATTERN_HORS_SCOPE) = _compiler_patterns(DOMAINES)


# ══════════════════════════════════════════════════════════════════════
# CLASSIFIEUR HYBRIDE
# ══════════════════════════════════════════════════════════════════════

class ClassifieurHybride:
    """
    Classifieur hybride en 3 étapes pour les domaines juridiques africains.

    Étape 1 : Règles prioritaires (regex compilé) — < 1ms
    Étape 2 : Score regex compilé — < 5ms
    Étape 3 : SBERT embeddings (si score ambigu) — < 50ms

    POINT CRITIQUE — chargement SBERT lazy :
    Le modèle SBERT (~500Mo RAM) n'est chargé qu'à la première
    utilisation réelle de l'étape 3. Si tous les passages sont
    résolus par les étapes 1 et 2, SBERT n'est jamais chargé.
    """

    def __init__(self, utiliser_sbert: bool = True):
        self.utiliser_sbert = utiliser_sbert
        self._sbert_model   = None
        self._refs_encoded  = None  # encodages des phrases de référence

        # Stats d'utilisation
        self.stats = defaultdict(int)

    def _charger_sbert(self):
        """Charge SBERT lazily à la première utilisation."""
        if self._sbert_model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            self._np = np

            print("[CLASSIFIER] Chargement SBERT...")
            self._sbert_model = SentenceTransformer(
                'paraphrase-multilingual-MiniLM-L12-v2'
            )

            # Pré-encoder toutes les phrases de référence
            self._refs_encoded = {}
            for did, cfg in DOMAINES.items():
                refs = cfg.get("refs_sbert_fr", [])
                if refs:
                    self._refs_encoded[did] = self._sbert_model.encode(
                        refs, normalize_embeddings=True
                    )

            print(f"[CLASSIFIER] SBERT prêt — {len(self._refs_encoded)} domaines encodés")

        except ImportError:
            print("[CLASSIFIER] SBERT non disponible — fallback scoring seul")
            self.utiliser_sbert = False

    def _score_regex(self, texte: str) -> Dict[str, float]:
        """
        Calcule les scores de chaque domaine via regex compilé.
        Retourne {domaine_id: score}.
        """
        scores = {}
        for did, pattern in PATTERNS_TERMES.items():
            matches = pattern.findall(texte)
            if matches:
                nb_termes  = len(DOMAINES[did].get("termes_fr", []))
                poids      = DOMAINES[did].get("poids", 1)
                nb_uniques = len(set(m.lower() for m in matches))
                score      = (nb_uniques / nb_termes) * 100 * poids
                scores[did] = round(score, 1)
        return scores

    def _classifier_sbert(self, texte: str, candidats: List[str]) -> Optional[str]:
        """
        Classe un texte parmi les domaines candidats via SBERT.

        candidats : liste de domaine_ids à considérer
        Retourne le domaine_id gagnant ou None si score insuffisant.
        """
        self._charger_sbert()
        if not self.utiliser_sbert or self._sbert_model is None:
            return None

        np = self._np

        # Encoder le texte (tronquer à 512 tokens SBERT)
        texte_court = texte[:1500]
        texte_enc   = self._sbert_model.encode(
            [texte_court], normalize_embeddings=True
        )[0]

        meilleur_dom   = None
        meilleur_score = SEUIL_SBERT

        for did in candidats:
            if did not in self._refs_encoded:
                continue
            refs_enc = self._refs_encoded[did]
            # Cosine similarity = dot product (vecteurs normalisés)
            sims = np.dot(refs_enc, texte_enc)
            score_max = float(sims.max())

            if score_max > meilleur_score:
                meilleur_score = score_max
                meilleur_dom   = did

        return meilleur_dom

    def classifier(self, texte: str) -> Dict:
        """
        Classifie un texte et retourne son profil de domaine.

        Retourne :
        {
            "domaine_principal"    : "douane",
            "label_principal"      : "Droit douanier",
            "domaines_secondaires" : ["droit_commercial"],
            "scores"               : {"douane": 120, ...},
            "score_max"            : 120,
            "est_pertinent"        : True,
            "est_bruit"            : False,
            "etape"                : 1|2|3,  ← étape qui a résolu
            "priority_rule"        : True|False,
        }
        """
        # Normaliser les accents pour la comparaison
        import unicodedata
        texte_lower = texte.lower()
        texte_norm  = ''.join(
            c for c in unicodedata.normalize('NFD', texte_lower)
            if unicodedata.category(c) != 'Mn'
        )

        # ── Filtre hors scope et bruit ────────────────────────────────
        nb_hors_scope = len(PATTERN_HORS_SCOPE.findall(texte_norm))
        if nb_hors_scope >= 2:
            self.stats["hors_scope"] += 1
            return self._resultat_vide(est_bruit=True)

        nb_bruit = len(PATTERN_BRUIT.findall(texte_norm))
        if nb_bruit >= 2:
            self.stats["bruit"] += 1
            return self._resultat_vide(est_bruit=True)

        # ── Étape 1 : Règles prioritaires ─────────────────────────────
        for did, pattern in PATTERNS_PRIORITY.items():
            if pattern.search(texte_norm):
                self.stats["etape1"] += 1
                label = DOMAINES[did]["label"]
                return {
                    "domaine_principal"    : did,
                    "label_principal"      : label,
                    "domaines_secondaires" : [],
                    "scores"               : {did: 200},
                    "score_max"            : 200,
                    "est_pertinent"        : True,
                    "est_bruit"            : False,
                    "etape"                : 1,
                    "priority_rule"        : True,
                }

        # ── Étape 2 : Score regex compilé ─────────────────────────────
        scores = self._score_regex(texte_norm)

        if not scores:
            # Aucun terme trouvé
            self.stats["rejete"] += 1
            return self._resultat_vide()

        scores_tries      = sorted(scores.items(), key=lambda x: -x[1])
        domaine_principal = scores_tries[0][0]
        score_max         = scores_tries[0][1]

        # Score élevé → résultat fiable sans SBERT
        if score_max >= SEUIL_CONFIANCE_HAUTE:
            self.stats["etape2_haute"] += 1
            return self._construire_resultat(
                domaine_principal, scores_tries, scores, etape=2
            )

        # Score trop bas → rejeter
        if score_max < SEUIL_BAS:
            self.stats["rejete"] += 1
            return self._resultat_vide()

        # Score ambigu → étape 3 SBERT
        if self.utiliser_sbert:
            # Candidats = domaines avec score > 30% du max
            seuil_candidat = score_max * 0.3
            candidats = [d for d, s in scores_tries if s >= seuil_candidat]

            self.stats["etape3"] += 1
            dom_sbert = self._classifier_sbert(texte, candidats)

            if dom_sbert:
                # SBERT a tranché
                scores[dom_sbert] = max(scores.get(dom_sbert, 0), score_max)
                scores_tries = sorted(scores.items(), key=lambda x: -x[1])
                return self._construire_resultat(
                    dom_sbert, scores_tries, scores, etape=3
                )

        # Fallback : meilleur score regex
        self.stats["etape2_bas"] += 1
        return self._construire_resultat(
            domaine_principal, scores_tries, scores, etape=2
        )

    def _construire_resultat(
        self,
        domaine_principal : str,
        scores_tries      : list,
        scores            : dict,
        etape             : int,
    ) -> Dict:
        label = DOMAINES.get(domaine_principal, {}).get("label", domaine_principal)
        score_max = scores_tries[0][1]
        seuil_sec = score_max * 0.3
        domaines_sec = [
            d for d, s in scores_tries[1:]
            if s >= seuil_sec
        ][:3]

        return {
            "domaine_principal"    : domaine_principal,
            "label_principal"      : label,
            "domaines_secondaires" : domaines_sec,
            "scores"               : dict(scores_tries[:5]),
            "score_max"            : min(score_max, 200),
            "est_pertinent"        : True,
            "est_bruit"            : False,
            "etape"                : etape,
            "priority_rule"        : False,
        }

    def _resultat_vide(self, est_bruit: bool = False) -> Dict:
        return {
            "domaine_principal"    : None,
            "label_principal"      : None,
            "domaines_secondaires" : [],
            "scores"               : {},
            "score_max"            : 0,
            "est_pertinent"        : False,
            "est_bruit"            : est_bruit,
            "etape"                : 0,
            "priority_rule"        : False,
        }

    def detecter_pays(self, texte: str) -> str:
        """Détecte le pays principal du texte."""
        texte_lower = texte.lower()
        scores = {}
        for token, pattern in PATTERNS_PAYS.items():
            matches = pattern.findall(texte_lower)
            if matches:
                scores[token] = len(matches)
        return max(scores, key=scores.get) if scores else "[OHADA]"

    def rapport_stats(self) -> str:
        """Affiche les statistiques d'utilisation des étapes."""
        total = sum(self.stats.values())
        if total == 0:
            return "Aucune classification effectuée"

        lignes = [f"Stats classifieur ({total:,} passages) :"]
        for etape, label in [
            ("etape1",       "Règles prioritaires"),
            ("etape2_haute", "Score élevé (sans SBERT)"),
            ("etape3",       "SBERT (ambigu)"),
            ("etape2_bas",   "Score bas (fallback)"),
            ("hors_scope",   "Hors scope"),
            ("bruit",        "Bruit"),
            ("rejete",       "Rejeté (score trop bas)"),
        ]:
            nb  = self.stats.get(etape, 0)
            pct = nb / total * 100
            lignes.append(f"  {label:<30} : {nb:>8,} ({pct:.1f}%)")

        return "\n".join(lignes)


# Instance globale partagée
# Usage : from cor_classifier import CLASSIFIEUR
# Évite de recharger SBERT à chaque import
CLASSIFIEUR = ClassifieurHybride(utiliser_sbert=True)


# ══════════════════════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  COR CLASSIFIER — Test du classifieur hybride")
    print("=" * 65)

    clf = ClassifieurHybride(utiliser_sbert=True)

    cas_tests = [
        ("code des douanes camerounais importation exportation marchandise",
         "douane", "Règle prioritaire douane"),
        ("code minier décret permis exploitation minerai bauxite",
         "mines", "Règle prioritaire mines"),
        ("hydrocarbures code pétrolier exploration contrat partage production",
         "petrole_energie", "Règle prioritaire pétrole"),
        ("titre foncier immatriculation cadastre expropriation utilité publique",
         "foncier", "Règle prioritaire foncier"),
        ("licenciement préavis code du travail salarié employeur smig syndicat",
         "droit_travail", "Score travail"),
        ("impôt TVA code général des impôts DGI contribuable redressement fiscal",
         "fiscalite", "Score fiscal"),
        ("présentation mémoire de master méthodologie rédaction année universitaire jury",
         None, "Hors scope académique"),
        ("recette cuisine poulet yassa ingrédients cuire four sel sucre",
         None, "Bruit"),
        ("Salvador rapport exploitation décision administrative service public",
         "droit_administratif", "SBERT — pas de faux positif transport/mines"),
    ]

    print(f"\n{'CAS':<45} {'ATTENDU':<20} {'OBTENU':<20} {'ÉTAPE':<5} OK?")
    print("-" * 100)

    for texte, attendu, label in cas_tests:
        profil = clf.classifier(texte)
        obtenu = profil["domaine_principal"]
        etape  = profil["etape"]
        ok     = "✓" if obtenu == attendu else "✗"
        print(f"{label:<45} {str(attendu):<20} {str(obtenu):<20} {etape:<5} {ok}")

    print()
    print(clf.rapport_stats())

    print()
    print("=== Test détection pays ===")
    pays_tests = [
        ("cameroun douala yaounde dgd", "[CM]"),
        ("gabon libreville port-gentil", "[GA]"),
        ("senegal dakar", "[SN]"),
        ("ohada acte uniforme ccja", "[OHADA]"),
        ("texte neutre sans pays", "[OHADA]"),
    ]
    for texte, attendu in pays_tests:
        obtenu = clf.detecter_pays(texte)
        ok = "✓" if obtenu == attendu else "✗"
        print(f"  {ok} '{texte[:40]}' → {obtenu}")


if __name__ == "__main__":
    main()