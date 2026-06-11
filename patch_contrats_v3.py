#!/usr/bin/env python3
# patch_contrats_v3.py — Vague 3 : 28 nouveaux contrats pour atteindre 170

NOUVEAUX_PROMPTS_V3 = r'''

# =============================================================================
# VAGUE 3 — 28 NOUVEAUX CONTRATS OHADA
# =============================================================================

# ── TRANSPORT COMPLEMENTAIRE ──────────────────────────────────────────────────

def prompt_contrat_affrètement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat d'affrètement conforme à l'AUCTMR OHADA 2003
et au droit maritime camerounais.
Structure :
1. IDENTIFICATION (fréteur et affréteur)
2. DESCRIPTION DU VEHICULE OU NAVIRE
3. VOYAGE OU PERIODE D'AFFRETEMENT
4. FRET (prix et modalites de paiement)
5. CHARGEMENT ET DECHARGEMENT
6. SURESTARIES (en cas de retard)
7. RESPONSABILITE DU FRETEUR
8. RESILIATION
--- DONNEES ---
Freteur : {donnees.get('requérant','')}
Affreteur : {donnees.get('adversaire','')}
Vehicule/Navire : {donnees.get('objet','')}
Trajet : {donnees.get('adresse','')}
Fret (FCFA) : {donnees.get('montant','')}
Duree/Voyage : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_lettre_voiture(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une lettre de voiture conforme à l'AUCTMR OHADA 2003
— document de transport de marchandises par route.
Structure :
1. IDENTIFICATION (expediteur, transporteur, destinataire)
2. LIEU ET DATE DE PRISE EN CHARGE
3. LIEU DE DESTINATION
4. DESIGNATION DES MARCHANDISES
5. POIDS ET VOLUME
6. INSTRUCTIONS PARTICULIERES
7. FRAIS DE TRANSPORT
8. RESERVES EVENTUELLES
--- DONNEES ---
Expediteur : {donnees.get('requérant','')}
Transporteur : {donnees.get('adversaire','')}
Destinataire : {donnees.get('debiteur','')}
Marchandises : {donnees.get('objet','')}
Depart : {donnees.get('adresse','')}
Destination : {donnees.get('adresse','')}
Poids/Volume : {donnees.get('faits','')}
Montant (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_commission_transport(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de commission de transport conforme
à l'AUCTMR OHADA 2003 — organisation du transport par un tiers.
Structure :
1. IDENTIFICATION (commettant et commissionnaire de transport)
2. MISSION DU COMMISSIONNAIRE
3. CHOIX DES TRANSPORTEURS
4. OBLIGATIONS DU COMMISSIONNAIRE
5. RESPONSABILITE (Art. 27 AUCTMR)
6. REMUNERATION
7. COMPTE-RENDU
--- DONNEES ---
Commettant : {donnees.get('requérant','')}
Commissionnaire transport : {donnees.get('adversaire','')}
Type de transport : {donnees.get('objet','')}
Remuneration (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── PROCEDURES COLLECTIVES COMPLEMENTAIRES ────────────────────────────────────

def prompt_requete_redressement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une requête en redressement judiciaire conforme
à l'AUPC OHADA 2015 (Art. 25 et suivants).
Structure :
1. IDENTIFICATION DU DEBITEUR
2. TRIBUNAL COMPETENT
3. SITUATION FINANCIERE (actif, passif, date de cessation)
4. CAUSES DES DIFFICULTES
5. PERSPECTIVES DE REDRESSEMENT
6. DEMANDE D'OUVERTURE DE LA PROCEDURE
7. DESIGNATION D'UN SYNDIC
8. MESURES CONSERVATOIRES DEMANDEES
--- DONNEES ---
Debiteur : {donnees.get('debiteur','')}
Forme sociale : {donnees.get('societe','')}
Actif (FCFA) : {donnees.get('montant','')}
Date de cessation de paiements : {donnees.get('date_debut','')}
Causes : {donnees.get('faits','')}
Perspectives : {donnees.get('objet','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT IMMOBILIER COMPLEMENTAIRE ───────────────────────────────────────────

def prompt_acte_vente_immobiliere(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de vente immobilière définitif conforme
au droit foncier camerounais — Ord. 74/1 et loi 80/22.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESIGNATION DU BIEN (titre foncier, superficie, bornage)
3. ORIGINE DE LA PROPRIETE (historique des mutations)
4. PRIX DE VENTE ET PAIEMENT
5. TRANSFERT DE PROPRIETE
6. GARANTIE D'EVICTION
7. CHARGES ET SERVITUDES
8. FRAIS ET DROITS D'ENREGISTREMENT
9. MUTATION AU REGISTRE FONCIER
--- DONNEES ---
Vendeur : {donnees.get('requérant','')}
Acquereur : {donnees.get('adversaire','')}
Bien : {donnees.get('adresse','')}
Titre foncier : {donnees.get('reference_jugement','')}
Prix (FCFA) : {donnees.get('montant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_promotion_immobiliere(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de promotion immobilière conforme
au droit camerounais — maître d'ouvrage délégué.
Structure :
1. IDENTIFICATION (maitre d'ouvrage et promoteur)
2. PROGRAMME IMMOBILIER
3. MISSIONS DU PROMOTEUR
4. BUDGET ET FINANCEMENT
5. DELAIS DE CONSTRUCTION
6. GARANTIES D'ACHEVEMENT
7. REMUNERATION DU PROMOTEUR
8. REDDITION DE COMPTES
--- DONNEES ---
Maitre d'ouvrage : {donnees.get('requérant','')}
Promoteur : {donnees.get('adversaire','')}
Programme : {donnees.get('objet','')}
Localisation : {donnees.get('adresse','')}
Budget (FCFA) : {donnees.get('montant','')}
Delai : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_convention_indivision(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention d'indivision conforme au droit
camerounais — gestion collective d'un bien indivis.
Structure :
1. IDENTIFICATION DES INDIVISAIRES
2. DESIGNATION DU BIEN INDIVIS
3. QUOTE-PARTS DE CHAQUE INDIVISAIRE
4. GERANT DE L'INDIVISION
5. PRISES DE DECISIONS (majorite requise)
6. CHARGES ET DEPENSES
7. REVENUS ET REPARTITION
8. SORTIE DE L'INDIVISION
--- DONNEES ---
Indivisaires : {donnees.get('requérant','')}
Bien indivis : {donnees.get('adresse','')}
Quote-parts : {donnees.get('faits','')}
Gerant : {donnees.get('adversaire','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT DES LIBERTES ET DROITS FONDAMENTAUX ─────────────────────────────────

def prompt_contrat_construction(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de construction conforme au droit camerounais
— entreprise de travaux et maître d'ouvrage.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESCRIPTION DES TRAVAUX (plans, devis)
3. DELAIS D'EXECUTION
4. PRIX ET MODALITES DE PAIEMENT (avancement)
5. RESPONSABILITE DECENNALE
6. ASSURANCE DOMMAGES-OUVRAGE
7. RECEPTION DES TRAVAUX
8. GARANTIE DE PARFAIT ACHEVEMENT
9. PENALITES DE RETARD
--- DONNEES ---
Maitre d'ouvrage : {donnees.get('requérant','')}
Entrepreneur : {donnees.get('adversaire','')}
Travaux : {donnees.get('objet','')}
Localisation : {donnees.get('adresse','')}
Montant (FCFA) : {donnees.get('montant','')}
Delai : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT PENAL COMPLEMENTAIRE ────────────────────────────────────────────────

def prompt_plainte_avec_constitution(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une plainte avec constitution de partie civile conforme
au Code de procédure pénale camerounais.
Structure :
1. IDENTIFICATION DU PLAIGNANT ET DE L'AVOCAT
2. FAITS CONSTITUTIFS DE L'INFRACTION (dates, circonstances)
3. QUALIFICATION PENALE
4. PREJUDICE SUBI (materiel, moral, corporel)
5. CHIFFRAGE DES DOMMAGES-INTERETS
6. DEMANDE DE CONSTITUTION DE PARTIE CIVILE
7. DEMANDE D'INSTRUCTION
--- DONNEES ---
Plaignant : {donnees.get('requérant','')}
Mis en cause : {donnees.get('adversaire','')}
Infraction : {donnees.get('chefs_inculpation','')}
Faits : {donnees.get('faits','')}
Prejudice (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_memoire_cassation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un mémoire ampliatif de pourvoi en cassation conforme
au Code de procédure camerounais devant la Cour Suprême.
Structure :
1. IDENTIFICATION DES PARTIES
2. DECISION ATTAQUEE (reference, date)
3. MOYENS DE CASSATION :
   - Violation de la loi
   - Defaut de base legale
   - Contradiction de motifs
   - Manque de motifs
4. DEVELOPPEMENT DE CHAQUE MOYEN
5. DEMANDE (cassation avec ou sans renvoi)
--- DONNEES ---
Demandeur en cassation : {donnees.get('requérant','')}
Defendeur en cassation : {donnees.get('adversaire','')}
Decision attaquee : {donnees.get('reference_jugement','')}
Moyens de cassation : {donnees.get('moyens_cassation','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT FISCAL ET DOUANIER ──────────────────────────────────────────────────

def prompt_reclamation_fiscale(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une réclamation contentieuse fiscale conforme
au Code général des impôts camerounais.
Structure :
1. IDENTIFICATION DU CONTRIBUABLE
2. REFERENCE DE L'AVIS D'IMPOSITION CONTESTE
3. NATURE ET MONTANT DES IMPOSITIONS
4. MOTIFS DE LA RECLAMATION
5. ARGUMENTS JURIDIQUES
6. DEMANDE (decharge totale ou partielle, sursis de paiement)
7. PIECES JOINTES
--- DONNEES ---
Contribuable : {donnees.get('requérant','')}
Administration fiscale : {donnees.get('adversaire','DGI Cameroun')}
Reference avis : {donnees.get('reference_jugement','')}
Montant conteste (FCFA) : {donnees.get('montant','')}
Motifs : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_recours_douanier(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un recours douanier contentieux conforme
au Code des douanes camerounais.
Structure :
1. IDENTIFICATION DE L'OPERATEUR ECONOMIQUE
2. REFERENCE DE LA DECISION CONTESTEE
3. INFRACTION DOUANIERE REPROACHEE
4. CONTESTATION DES FAITS
5. ARGUMENTS JURIDIQUES ET TARIFAIRES
6. DEMANDE (annulation, reduction, remise)
--- DONNEES ---
Operateur : {donnees.get('requérant','')}
Bureau des douanes : {donnees.get('adversaire','DGD Cameroun')}
Reference decision : {donnees.get('reference_jugement','')}
Montant en litige (FCFA) : {donnees.get('montant','')}
Motifs : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT ADMINISTRATIF COMPLEMENTAIRE ────────────────────────────────────────

def prompt_ppp(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de Partenariat Public-Privé (PPP) conforme
au droit camerounais et aux standards OHADA.
Structure :
1. IDENTIFICATION (autorite publique et partenaire prive)
2. OBJET DU PPP (infrastructure, service)
3. MONTAGE FINANCIER (financement prive, subvention publique)
4. REPARTITION DES RISQUES
5. DUREE DU CONTRAT
6. REMUNERATION DU PARTENAIRE PRIVE
7. PERFORMANCE ET INDICATEURS
8. CONTROLE DE L'AUTORITE PUBLIQUE
9. FIN DU CONTRAT ET TRANSFERT DES BIENS
--- DONNEES ---
Autorite publique : {donnees.get('requérant','')}
Partenaire prive : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Investissement prive (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT BANCAIRE COMPLEMENTAIRE ─────────────────────────────────────────────

def prompt_fiducie(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de fiducie-sûreté conforme au droit OHADA
et aux évolutions de l'AUS 2010.
Structure :
1. IDENTIFICATION (constituant, fiduciaire, beneficiaire)
2. BIENS TRANSFERES EN FIDUCIE
3. MISSION DU FIDUCIAIRE
4. OBLIGATION GARANTIE
5. DUREE DE LA FIDUCIE
6. REALISATION EN CAS DE DEFAUT
7. RETROCESSION EN CAS D'EXECUTION
8. PUBLICITE
--- DONNEES ---
Constituant : {donnees.get('requérant','')}
Fiduciaire : {donnees.get('adversaire','')}
Beneficiaire : {donnees.get('creancier','')}
Biens : {donnees.get('objet','')}
Obligation garantie (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_portage_actions(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de portage d'actions conforme au droit
OHADA — détention temporaire d'actions pour compte d'autrui.
Structure :
1. IDENTIFICATION (donneur d'ordre et porteur)
2. ACTIONS PORTEES (societe, nombre, valeur)
3. DUREE DU PORTAGE
4. REMUNERATION DU PORTEUR
5. DROITS ET OBLIGATIONS PENDANT LE PORTAGE
6. CONDITION DE RETROCESSION
7. PRIX DE RETROCESSION
8. CONFIDENTIALITE
--- DONNEES ---
Donneur d'ordre : {donnees.get('requérant','')}
Porteur : {donnees.get('adversaire','')}
Actions : {donnees.get('objet','')}
Societe : {donnees.get('societe','')}
Remuneration (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── ARBITRAGE COMPLEMENTAIRE ──────────────────────────────────────────────────

def prompt_compromis_arbitrage(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un compromis d'arbitrage conforme à l'AUDA OHADA 2017
— soumission d'un litige existant à l'arbitrage.
Structure :
1. IDENTIFICATION DES PARTIES
2. LITIGE SOUMIS A L'ARBITRAGE (description precise)
3. COMPOSITION DU TRIBUNAL ARBITRAL
4. SIEGE DE L'ARBITRAGE
5. LANGUE DE LA PROCEDURE
6. DROIT APPLICABLE AU FOND
7. DELAI DE PROCEDURE
8. CONFIDENTIALITE
9. PARTAGE DES FRAIS
--- DONNEES ---
Partie A : {donnees.get('requérant','')}
Partie B : {donnees.get('adversaire','')}
Litige : {donnees.get('objet','')}
Nombre d'arbitres : {donnees.get('faits','3')}
Siege : {donnees.get('adresse','')}
Montant en litige (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_accord_mediation_final(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord de médiation (protocole d'accord final)
conforme à l'AUM OHADA 2017 — résolution du litige par médiation.
Structure :
1. IDENTIFICATION DES PARTIES ET DU MEDIATEUR
2. RAPPEL DU LITIGE
3. ACCORD DES PARTIES
4. CONCESSIONS RECIPROQUES
5. OBLIGATIONS MUTUELLES
6. MODALITES D'EXECUTION
7. RENONCIATION AUX VOIES DE RECOURS
8. HOMOLOGATION EVENTUELLE
--- DONNEES ---
Partie A : {donnees.get('requérant','')}
Partie B : {donnees.get('adversaire','')}
Mediateur : {donnees.get('tribunal','')}
Accord : {donnees.get('faits','')}
Montant (FCFA) : {donnees.get('montant','')}
Obligations : {donnees.get('objet','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── ACTES DE LA VIE QUOTIDIENNE ───────────────────────────────────────────────

def prompt_reconnaissance_paternite(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de reconnaissance de paternité conforme
au Code civil camerounais applicable.
Structure :
1. IDENTIFICATION DU DECLARANT (pere)
2. IDENTIFICATION DE L'ENFANT
3. DECLARATION DE PATERNITE
4. EFFETS JURIDIQUES (nom, filiation, succession)
5. ACTE D'ETAT CIVIL DE REFERENCE
6. DATE ET SIGNATURE
--- DONNEES ---
Pere declarant : {donnees.get('requérant','')}
Enfant reconnu : {donnees.get('adversaire','')}
Date de naissance de l'enfant : {donnees.get('date_debut','')}
Mere : {donnees.get('creancier','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_engagement_honneur(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un engagement sur l'honneur conforme aux usages
juridiques camerounais et OHADA.
Structure :
1. IDENTIFICATION DU DECLARANT
2. OBJET DE L'ENGAGEMENT
3. DECLARATION SOLENNELLE
4. CONSEQUENCES EN CAS DE FAUSSE DECLARATION
5. DATE ET SIGNATURE
--- DONNEES ---
Declarant : {donnees.get('requérant','')}
Objet : {donnees.get('objet','')}
Contenu de l'engagement : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_acte_cautionnement_judiciaire(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de cautionnement judiciaire conforme
au Code de procédure civile camerounais.
Structure :
1. IDENTIFICATION (caution et beneficiaire)
2. DECISION JUDICIAIRE DE REFERENCE
3. ENGAGEMENT DE LA CAUTION
4. MONTANT GARANTI
5. CONDITIONS DE MISE EN JEU
6. DUREE
--- DONNEES ---
Caution : {donnees.get('requérant','')}
Beneficiaire : {donnees.get('adversaire','')}
Decision : {donnees.get('reference_jugement','')}
Montant (FCFA) : {donnees.get('montant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT DE LA CONCURRENCE ───────────────────────────────────────────────────

def prompt_accord_non_concurrence(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord de non-concurrence conforme au droit
camerounais et aux principes OHADA de la concurrence.
Structure :
1. IDENTIFICATION DES PARTIES
2. PERIMETRE D'ACTIVITE INTERDIT
3. ZONE GEOGRAPHIQUE COUVERTE
4. DUREE (raisonnable - max 2 ans)
5. CONTREPARTIE FINANCIERE (obligation de validite)
6. SANCTIONS EN CAS DE VIOLATION
7. MODALITES DE LEVEE
--- DONNEES ---
Obligee (ex-salarie ou cede) : {donnees.get('requérant','')}
Beneficiaire : {donnees.get('adversaire','')}
Activite interdite : {donnees.get('objet','')}
Zone : {donnees.get('adresse','')}
Duree : {donnees.get('duree','2 ans')}
Contrepartie mensuelle (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT DE L'ENVIRONNEMENT ──────────────────────────────────────────────────

def prompt_convention_environnementale(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention environnementale conforme à la loi-cadre
sur l'environnement camerounais et aux standards OHADA.
Structure :
1. IDENTIFICATION DES PARTIES
2. OBJET (protection, compensation, restoration)
3. OBLIGATIONS ENVIRONNEMENTALES
4. ETUDE D'IMPACT ENVIRONNEMENTAL
5. MESURES DE MITIGATION
6. REPORTING ET AUDIT
7. SANCTIONS
8. DUREE
--- DONNEES ---
Entreprise : {donnees.get('requérant','')}
Autorite environnementale : {donnees.get('adversaire','')}
Projet concerne : {donnees.get('objet','')}
Zone : {donnees.get('adresse','')}
Mesures : {donnees.get('faits','')}
Budget environnemental (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT FONCIER COMPLEMENTAIRE ──────────────────────────────────────────────

def prompt_nantissement_fonds_commerce(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de nantissement de fonds de commerce conforme
à l'AUDCG OHADA 2010 (Art. 146-151) et à l'AUS OHADA 2010.
Structure :
1. IDENTIFICATION (creancier et debiteur constituant)
2. DESIGNATION DU FONDS DE COMMERCE NANTI
3. ELEMENTS INCORPORELS NANTIS (clientele, nom commercial, marque)
4. CREANCE GARANTIE
5. INSCRIPTION AU RCCM
6. DROITS DU CREANCIER NANTI
7. OBLIGATIONS DU CONSTITUANT
8. REALISATION EN CAS DE DEFAUT
--- DONNEES ---
Creancier : {donnees.get('creancier','')}
Constituant : {donnees.get('debiteur','')}
Fonds de commerce : {donnees.get('objet','')}
Montant garanti (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_hypotheque(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte d'hypothèque conventionnelle conforme
à l'AUS OHADA 2010 (Art. 190 et suivants).
Structure :
1. IDENTIFICATION DES PARTIES
2. BIEN HYPOTHEQUE (description, titre foncier)
3. CREANCE GARANTIE (montant, echeance)
4. RANG DE L'HYPOTHEQUE
5. INSCRIPTION AU REGISTRE FONCIER
6. OBLIGATIONS DU CONSTITUANT
7. REALISATION (saisie immobiliere)
8. MAINLEVEE
--- DONNEES ---
Creancier hypothecaire : {donnees.get('creancier','')}
Constituant : {donnees.get('debiteur','')}
Bien : {donnees.get('adresse','')}
Titre foncier : {donnees.get('reference_jugement','')}
Montant garanti (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── BILLET ET EFFETS DE COMMERCE ──────────────────────────────────────────────

def prompt_billet_a_ordre(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un billet à ordre conforme à l'AUPSRVE OHADA
et au droit cambiaire camerounais.
Structure :
1. DENOMINATION (billet a ordre)
2. PROMESSE INCONDITIONNELLE DE PAYER
3. MONTANT (en lettres et en chiffres)
4. ECHEANCE
5. LIEU DE PAIEMENT
6. BENEFICIAIRE
7. DATE ET LIEU DE CREATION
8. SIGNATURE DU SOUSCRIPTEUR
--- DONNEES ---
Souscripteur (debiteur) : {donnees.get('debiteur','')}
Beneficiaire : {donnees.get('creancier','')}
Montant (FCFA) : {donnees.get('montant','')}
Echeance : {donnees.get('date_exigibilite','')}
Lieu de paiement : {donnees.get('adresse','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_lettre_de_change(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une lettre de change conforme à l'AUPSRVE OHADA
et au droit cambiaire camerounais.
Structure :
1. DENOMINATION (lettre de change)
2. ORDRE DE PAYER (inconditionnel)
3. MONTANT (en lettres et en chiffres)
4. TIREE (personne qui doit payer)
5. ECHEANCE
6. LIEU DE PAIEMENT
7. BENEFICIAIRE
8. DATE ET LIEU DE CREATION
9. SIGNATURE DU TIREUR
--- DONNEES ---
Tireur : {donnees.get('requérant','')}
Tire : {donnees.get('debiteur','')}
Beneficiaire : {donnees.get('creancier','')}
Montant (FCFA) : {donnees.get('montant','')}
Echeance : {donnees.get('date_exigibilite','')}
Lieu de paiement : {donnees.get('adresse','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT DE LA FAMILLE COMPLEMENTAIRE ───────────────────────────────────────

def prompt_separation_corps(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une requête en séparation de corps conforme
au Code civil camerounais.
Structure :
1. IDENTIFICATION DES EPOUX
2. DATE ET LIEU DU MARIAGE
3. FAITS A L'ORIGINE DE LA DEMANDE
4. MESURES URGENTES (residence, enfants, aliments)
5. DEMANDES DEFINITIVES
6. JURIDICTION COMPETENTE
--- DONNEES ---
Requerant : {donnees.get('requérant','')}
Epoux/Epouse : {donnees.get('adversaire','')}
Date de mariage : {donnees.get('date_debut','')}
Faits : {donnees.get('faits','')}
Enfants : {donnees.get('objet','')}
Tribunal : {donnees.get('tribunal','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── ACTES COMPLEMENTAIRES OHADA ───────────────────────────────────────────────

def prompt_opposition_execution(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une opposition à mesure d'exécution conforme
à l'AUPSRVE OHADA 2023 — contestation voie d'exécution.
Structure :
1. IDENTIFICATION DES PARTIES
2. MESURE D'EXECUTION CONTESTEE (nature, date)
3. MOYENS D'OPPOSITION
4. ARGUMENTS JURIDIQUES
5. DEMANDE (mainlevee, suspension, reduction)
6. URGENCE ET MESURES CONSERVATOIRES
--- DONNEES ---
Opposant (debiteur) : {donnees.get('requérant','')}
Creancier poursuivant : {donnees.get('adversaire','')}
Mesure contestee : {donnees.get('objet','')}
Moyens : {donnees.get('faits','')}
Montant en litige (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_mainlevee_saisie(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une demande de mainlevée de saisie conforme
à l'AUPSRVE OHADA 2023.
Structure :
1. IDENTIFICATION DES PARTIES
2. SAISIE DONT LA MAINLEVEE EST DEMANDEE
3. FONDEMENT DE LA DEMANDE :
   - Paiement de la dette
   - Nullite de la saisie
   - Absence de titre executoire
4. PIECES JUSTIFICATIVES
5. DEMANDE AU JUGE DE L'EXECUTION
--- DONNEES ---
Demandeur : {donnees.get('requérant','')}
Creancier saisissant : {donnees.get('adversaire','')}
Type de saisie : {donnees.get('objet','')}
Motif de mainlevee : {donnees.get('faits','')}
Montant (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""
'''

NOUVELLES_ENTREES_V3 = """
PROMPTS_REDACTION.update({
    "contrat_affrètement": {"nom": "Contrat d'affretement", "description": "AUCTMR OHADA 2003 - fret - surestaries", "champs": ["requérant","adversaire","objet","adresse","montant","duree","faits"], "fn": prompt_contrat_affrètement},
    "lettre_voiture": {"nom": "Lettre de voiture", "description": "AUCTMR OHADA 2003 - document de transport routier", "champs": ["requérant","adversaire","debiteur","objet","adresse","faits","montant"], "fn": prompt_lettre_voiture},
    "contrat_commission_transport": {"nom": "Contrat de commission de transport", "description": "AUCTMR OHADA 2003 - organisation transport", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_contrat_commission_transport},
    "requete_redressement": {"nom": "Requete en redressement judiciaire", "description": "Art. 25+ AUPC OHADA 2015 - ouverture procedure", "champs": ["debiteur","societe","montant","date_debut","faits","objet"], "fn": prompt_requete_redressement},
    "acte_vente_immobiliere": {"nom": "Acte de vente immobiliere definitif", "description": "Droit foncier CM - Ord. 74/1 - mutation registre", "champs": ["requérant","adversaire","adresse","reference_jugement","montant","faits"], "fn": prompt_acte_vente_immobiliere},
    "contrat_promotion_immobiliere": {"nom": "Contrat de promotion immobiliere", "description": "Droit CM - maitre d'ouvrage delegue - garanties", "champs": ["requérant","adversaire","objet","adresse","montant","duree","faits"], "fn": prompt_contrat_promotion_immobiliere},
    "convention_indivision": {"nom": "Convention d'indivision", "description": "Droit CM - gestion collective bien indivis", "champs": ["requérant","adresse","faits","adversaire","duree"], "fn": prompt_convention_indivision},
    "contrat_construction": {"nom": "Contrat de construction", "description": "Droit CM - responsabilite decennale - reception", "champs": ["requérant","adversaire","objet","adresse","montant","duree","faits"], "fn": prompt_contrat_construction},
    "plainte_avec_constitution": {"nom": "Plainte avec constitution de partie civile", "description": "CPP CM - infraction - prejudice - instruction", "champs": ["requérant","adversaire","chefs_inculpation","faits","montant"], "fn": prompt_plainte_avec_constitution},
    "memoire_cassation": {"nom": "Memoire ampliatif pourvoi en cassation", "description": "Cour Supreme CM - moyens de cassation", "champs": ["requérant","adversaire","reference_jugement","moyens_cassation","faits"], "fn": prompt_memoire_cassation},
    "reclamation_fiscale": {"nom": "Reclamation contentieuse fiscale", "description": "CGI camerounais - decharge - sursis de paiement", "champs": ["requérant","adversaire","reference_jugement","montant","faits"], "fn": prompt_reclamation_fiscale},
    "recours_douanier": {"nom": "Recours douanier contentieux", "description": "Code douanes CM - annulation - reduction", "champs": ["requérant","adversaire","reference_jugement","montant","faits"], "fn": prompt_recours_douanier},
    "ppp": {"nom": "Contrat de Partenariat Public-Prive (PPP)", "description": "Droit CM - financement prive - partage risques", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_ppp},
    "fiducie": {"nom": "Contrat de fiducie-surete", "description": "AUS OHADA 2010 - transfert patrimonial garantie", "champs": ["requérant","adversaire","creancier","objet","montant","duree"], "fn": prompt_fiducie},
    "portage_actions": {"nom": "Contrat de portage d'actions", "description": "Droit OHADA - detention temporaire pour compte d'autrui", "champs": ["requérant","adversaire","objet","societe","montant","duree","faits"], "fn": prompt_portage_actions},
    "compromis_arbitrage": {"nom": "Compromis d'arbitrage", "description": "AUDA OHADA 2017 - litige existant soumis arbitrage", "champs": ["requérant","adversaire","objet","faits","adresse","montant"], "fn": prompt_compromis_arbitrage},
    "accord_mediation_final": {"nom": "Accord de mediation final", "description": "AUM OHADA 2017 - resolution litige par mediation", "champs": ["requérant","adversaire","tribunal","faits","montant","objet"], "fn": prompt_accord_mediation_final},
    "reconnaissance_paternite": {"nom": "Reconnaissance de paternite", "description": "Code civil CM - filiation - effets successoraux", "champs": ["requérant","adversaire","date_debut","creancier","faits"], "fn": prompt_reconnaissance_paternite},
    "engagement_honneur": {"nom": "Engagement sur l'honneur", "description": "Usage juridique CM - declaration solennelle", "champs": ["requérant","objet","faits"], "fn": prompt_engagement_honneur},
    "acte_cautionnement_judiciaire": {"nom": "Cautionnement judiciaire", "description": "CPC camerounais - garantie decision judiciaire", "champs": ["requérant","adversaire","reference_jugement","montant","faits"], "fn": prompt_acte_cautionnement_judiciaire},
    "accord_non_concurrence": {"nom": "Accord de non-concurrence", "description": "Droit CM - perimetre - contrepartie obligatoire", "champs": ["requérant","adversaire","objet","adresse","duree","montant"], "fn": prompt_accord_non_concurrence},
    "convention_environnementale": {"nom": "Convention environnementale", "description": "Loi-cadre environnement CM - mitigation - audit", "champs": ["requérant","adversaire","objet","adresse","faits","montant"], "fn": prompt_convention_environnementale},
    "nantissement_fonds_commerce": {"nom": "Nantissement de fonds de commerce", "description": "AUDCG OHADA 2010 - AUS 2010 - inscription RCCM", "champs": ["creancier","debiteur","objet","montant","duree","faits"], "fn": prompt_nantissement_fonds_commerce},
    "hypotheque": {"nom": "Acte d'hypotheque conventionnelle", "description": "Art. 190+ AUS OHADA 2010 - registre foncier", "champs": ["creancier","debiteur","adresse","reference_jugement","montant","duree","faits"], "fn": prompt_hypotheque},
    "billet_a_ordre": {"nom": "Billet a ordre", "description": "AUPSRVE OHADA - droit cambiaire CM", "champs": ["debiteur","creancier","montant","date_exigibilite","adresse","faits"], "fn": prompt_billet_a_ordre},
    "lettre_de_change": {"nom": "Lettre de change", "description": "AUPSRVE OHADA - droit cambiaire CM", "champs": ["requérant","debiteur","creancier","montant","date_exigibilite","adresse"], "fn": prompt_lettre_de_change},
    "separation_corps": {"nom": "Requete en separation de corps", "description": "Code civil CM - mesures urgentes - enfants", "champs": ["requérant","adversaire","date_debut","faits","objet","tribunal"], "fn": prompt_separation_corps},
    "opposition_execution": {"nom": "Opposition a mesure d'execution", "description": "AUPSRVE OHADA 2023 - contestation voie execution", "champs": ["requérant","adversaire","objet","faits","montant"], "fn": prompt_opposition_execution},
    "mainlevee_saisie": {"nom": "Demande de mainlevee de saisie", "description": "AUPSRVE OHADA 2023 - paiement ou nullite", "champs": ["requérant","adversaire","objet","faits","montant"], "fn": prompt_mainlevee_saisie},
})
"""

with open('/root/odyxia-droit/prompts.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content + "\n" + NOUVEAUX_PROMPTS_V3 + "\n" + NOUVELLES_ENTREES_V3

with open('/root/odyxia-droit/prompts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK - Vague 3 ajoutee dans prompts.py")

import py_compile
py_compile.compile('/root/odyxia-droit/prompts.py', doraise=True)
print("Syntaxe OK")