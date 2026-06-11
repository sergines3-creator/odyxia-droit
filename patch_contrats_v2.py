#!/usr/bin/env python3
# patch_contrats_v2.py — Vague 2 : 60 nouveaux contrats OHADA

NOUVEAUX_PROMPTS_V2 = r'''

# =============================================================================
# VAGUE 2 — 60 NOUVEAUX CONTRATS OHADA
# =============================================================================

# ── SOCIETES COMPLEMENTAIRES ──────────────────────────────────────────────────

def prompt_statuts_sasu(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les statuts d'une SASU (Société par Actions Simplifiée Unipersonnelle)
conforme à l'AUSCGIE OHADA 2014 — associé unique.
Structure :
1. DENOMINATION, FORME, OBJET, SIEGE, DUREE
2. ASSOCIE UNIQUE (identité complète)
3. CAPITAL SOCIAL ET ACTIONS
4. PRESIDENT (pouvoirs étendus)
5. DECISIONS DE L'ASSOCIE UNIQUE
6. EXERCICE SOCIAL ET COMPTES
7. DISSOLUTION ET LIQUIDATION
--- DONNEES ---
Denomination : {donnees.get('societe','')}
Objet social : {donnees.get('objet','')}
Siege : {donnees.get('adresse','')}
Capital (FCFA) : {donnees.get('capital','')}
Associe unique : {donnees.get('requérant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_statuts_scs(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les statuts d'une SCS (Société en Commandite Simple)
conforme à l'AUSCGIE OHADA 2014 (Art. 293-308).
Structure :
1. DENOMINATION, OBJET, SIEGE, DUREE
2. ASSOCIES COMMANDITES (responsabilité indéfinie et solidaire)
3. ASSOCIES COMMANDITAIRES (responsabilité limitée aux apports)
4. CAPITAL ET PARTS SOCIALES
5. GERANCE (commandités uniquement)
6. DECISIONS COLLECTIVES
7. CESSION DE PARTS
8. DISSOLUTION
--- DONNEES ---
Denomination : {donnees.get('societe','')}
Objet : {donnees.get('objet','')}
Siege : {donnees.get('adresse','')}
Capital (FCFA) : {donnees.get('capital','')}
Commandites : {donnees.get('requérant','')}
Commanditaires : {donnees.get('creancier','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_cession_actions_sa(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de cession d'actions de SA conforme
à l'AUSCGIE OHADA 2014 — transfert de valeurs mobilières.
Structure :
1. IDENTIFICATION DES PARTIES (cedant et cessionnaire)
2. DESIGNATION DE LA SOCIETE ET DES ACTIONS
3. NOMBRE D'ACTIONS CEDEES ET VALEUR NOMINALE
4. PRIX DE CESSION ET MODALITES
5. CLAUSE D'AGREMENT (si applicable selon statuts)
6. GARANTIES DU CEDANT
7. DATE DE TRANSFERT DE PROPRIETE
8. INSCRIPTION AU REGISTRE DES ACTIONNAIRES
--- DONNEES ---
Cedant : {donnees.get('requérant','')}
Cessionnaire : {donnees.get('adversaire','')}
Societe : {donnees.get('societe','')}
Actions cedees : {donnees.get('objet','')}
Prix (FCFA) : {donnees.get('montant','')}
Date : {donnees.get('date_debut','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_convention_compte_courant(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de compte courant d'associé conforme
au droit OHADA — prêt d'un associé à sa société.
Structure :
1. IDENTIFICATION (associe et societe)
2. MONTANT MIS A DISPOSITION
3. TAUX D'INTERET (dans la limite legale)
4. MODALITES DE REMBOURSEMENT
5. BLOCAGE EVENTUEL (en cas de difficultes)
6. SUBORDINATION AUX CREANCIERS EXTERIEURS
7. DUREE ET RESILIATION
--- DONNEES ---
Associe : {donnees.get('requérant','')}
Societe : {donnees.get('societe','')}
Montant (FCFA) : {donnees.get('montant','')}
Taux d'interet : {donnees.get('suretes','taux legal')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_dissolution_amiable(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de dissolution amiable et de liquidation de société
conforme à l'AUSCGIE OHADA 2014.
Structure :
1. IDENTIFICATION DE LA SOCIETE
2. DECISION DE DISSOLUTION (PV AGE)
3. NOMINATION DU LIQUIDATEUR
4. POUVOIRS DU LIQUIDATEUR
5. OPERATIONS DE LIQUIDATION
6. REPARTITION DU BONI DE LIQUIDATION
7. CLOTURE DE LIQUIDATION
8. RADIATION DU RCCM
--- DONNEES ---
Societe : {donnees.get('societe','')}
Associes : {donnees.get('creancier','')}
Liquidateur : {donnees.get('requérant','')}
Cause de dissolution : {donnees.get('faits','')}
Actif net (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT AGRICOLE ET RURAL ───────────────────────────────────────────────────

def prompt_contrat_fermage(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de fermage conforme au droit foncier
et rural camerounais — exploitation agricole contre redevance.
Structure :
1. IDENTIFICATION DES PARTIES (bailleur et fermier)
2. DESIGNATION DU BIEN AGRICOLE (superficie, cultures)
3. DUREE DU BAIL (minimum 3 ans recommande)
4. REDEVANCE ANNUELLE (en especes ou en nature)
5. OBLIGATIONS DU FERMIER (exploitation en bon pere de famille)
6. OBLIGATIONS DU BAILLEUR
7. AMELIORATIONS ET INDEMNITES
8. RESILIATION ET EFFETS
--- DONNEES ---
Bailleur : {donnees.get('bailleur','')}
Fermier : {donnees.get('preneur','')}
Bien agricole : {donnees.get('adresse','')}
Superficie : {donnees.get('superficie','')}
Redevance annuelle (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','3 ans')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_metayage(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de métayage conforme au droit rural camerounais
— partage des récoltes entre propriétaire et métayer.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESIGNATION DU BIEN (terres, cultures)
3. DUREE
4. PARTAGE DES RECOLTES (pourcentages)
5. APPORTS DU PROPRIETAIRE (semences, engrais, outils)
6. APPORTS DU METAYER (travail, soin des cultures)
7. COMPTABILITE DES RECOLTES
8. RESILIATION
--- DONNEES ---
Proprietaire : {donnees.get('bailleur','')}
Metayer : {donnees.get('preneur','')}
Terres : {donnees.get('adresse','')}
Partage recoltes : {donnees.get('faits','50/50')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_vente_recoltes(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de vente de récoltes sur pied conforme
au droit commercial camerounais et aux usages agricoles OHADA.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESIGNATION DES RECOLTES (culture, superficie, estimation)
3. PRIX CONVENU
4. MODALITES DE PAIEMENT
5. DATE ET CONDITIONS DE RECOLTE
6. RISQUES ET PERTES (force majeure climatique)
7. GARANTIES
--- DONNEES ---
Vendeur : {donnees.get('requérant','')}
Acheteur : {donnees.get('adversaire','')}
Recoltes : {donnees.get('objet','')}
Superficie : {donnees.get('superficie','')}
Prix (FCFA) : {donnees.get('montant','')}
Date de recolte : {donnees.get('date_debut','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT MINIER ET PETROLIER ─────────────────────────────────────────────────

def prompt_contrat_sous_traitance_petroliere(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de sous-traitance pétrolière conforme
au Code pétrolier camerounais et aux standards internationaux.
Structure :
1. IDENTIFICATION (compagnie petroliere et sous-traitant)
2. SERVICES OU TRAVAUX SOUS-TRAITES
3. ZONE D'OPERATION
4. DUREE DU CONTRAT
5. REMUNERATION (day-rate, lump sum ou reegie)
6. RESPONSABILITES ET INDEMNISATION (knock-for-knock)
7. ASSURANCES OBLIGATOIRES
8. PROPRIETE DES EQUIPEMENTS
9. CONFIDENTIALITE (donnees geologiques)
10. RESILIATION
--- DONNEES ---
Compagnie petroliere : {donnees.get('requérant','')}
Sous-traitant : {donnees.get('adversaire','')}
Services : {donnees.get('objet','')}
Zone : {donnees.get('adresse','')}
Remuneration (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_convention_exploitation_miniere(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention d'exploitation minière artisanale
conforme au Code minier camerounais.
Structure :
1. IDENTIFICATION DES PARTIES
2. PERIMETRE D'EXPLOITATION
3. SUBSTANCES MINERALES VISEES
4. DUREE ET RENOUVELLEMENT
5. REDEVANCES ET TAXES MINIERES
6. OBLIGATIONS ENVIRONNEMENTALES
7. SECURITE ET SANTE DES TRAVAILLEURS
8. RAPPORT D'ACTIVITE PERIODIQUE
--- DONNEES ---
Autorite miniere : {donnees.get('requérant','')}
Exploitant : {donnees.get('adversaire','')}
Perimetre : {donnees.get('adresse','')}
Substances : {donnees.get('objet','')}
Redevance annuelle (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── CREDIT-BAIL ───────────────────────────────────────────────────────────────

def prompt_contrat_credit_bail(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de crédit-bail (leasing) conforme au droit
OHADA et à la réglementation COBAC applicable en zone CEMAC.
Structure :
1. IDENTIFICATION (credit-bailleur et credit-preneur)
2. BIEN OBJET DU CREDIT-BAIL (description precise)
3. DUREE DU CONTRAT (irrévocable pendant la période principale)
4. LOYERS (montant, periodicite, indexation)
5. OPTION D'ACHAT (prix de levee d'option)
6. ASSURANCE DU BIEN
7. ENTRETIEN ET REPARATIONS (a la charge du preneur)
8. RISQUES ET PERTES
9. RESILIATION ET INDEMNITES
10. FIN DE CONTRAT (levee option, restitution, renouvellement)
--- DONNEES ---
Credit-bailleur : {donnees.get('creancier','')}
Credit-preneur : {donnees.get('debiteur','')}
Bien : {donnees.get('objet','')}
Valeur du bien (FCFA) : {donnees.get('montant','')}
Loyer mensuel (FCFA) : {donnees.get('nature_creance','')}
Duree : {donnees.get('duree','')}
Option d'achat (FCFA) : {donnees.get('suretes','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── BANQUE ET FINANCEMENT ─────────────────────────────────────────────────────

def prompt_ouverture_credit(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat d'ouverture de crédit conforme à la
réglementation bancaire COBAC et au droit OHADA.
Structure :
1. IDENTIFICATION (banque et beneficiaire)
2. MONTANT DU CREDIT AUTORISE
3. NATURE DU CREDIT (decouvert, ligne de credit revolving)
4. TAUX D'INTERET ET COMMISSIONS
5. DUREE ET RENOUVELLEMENT
6. GARANTIES EXIGEES
7. CONDITIONS D'UTILISATION
8. REMBOURSEMENT
9. RESILIATION
--- DONNEES ---
Banque : {donnees.get('creancier','')}
Beneficiaire : {donnees.get('debiteur','')}
Montant autorise (FCFA) : {donnees.get('montant','')}
Nature du credit : {donnees.get('objet','ligne de credit')}
Taux : {donnees.get('suretes','')}
Duree : {donnees.get('duree','')}
Garanties : {donnees.get('nature_creance','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_garantie_bancaire(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une garantie bancaire autonome à première demande
conforme aux règles COBAC et aux pratiques OHADA.
Structure :
1. IDENTIFICATION (banque garante, beneficiaire, donneur d'ordre)
2. OBJET DE LA GARANTIE
3. MONTANT MAXIMUM GARANTI
4. CONDITIONS D'APPEL EN GARANTIE (premiere demande)
5. DOCUMENTS REQUIS
6. DUREE DE VALIDITE
7. REDUCTION ET EXTINCTION
8. DROIT APPLICABLE
--- DONNEES ---
Banque garante : {donnees.get('creancier','')}
Beneficiaire : {donnees.get('adversaire','')}
Donneur d'ordre : {donnees.get('debiteur','')}
Objet : {donnees.get('objet','')}
Montant garanti (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_convention_tresorerie(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de trésorerie (cash pooling) conforme
au droit OHADA et aux règles COBAC pour groupes de sociétés.
Structure :
1. IDENTIFICATION DES SOCIETES DU GROUPE
2. SOCIETE CENTRALISATRICE (tete de groupe)
3. MECANISME DE CENTRALISATION
4. TAUX D'INTERET INTRAGROUPE
5. PLAFONDS PAR SOCIETE
6. REPORTING ET CONTROLE
7. DUREE ET RESILIATION
--- DONNEES ---
Societe centralisatrice : {donnees.get('requérant','')}
Societes participantes : {donnees.get('creancier','')}
Plafond global (FCFA) : {donnees.get('montant','')}
Taux interet intragroupe : {donnees.get('suretes','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT SOCIAL APPROFONDI ───────────────────────────────────────────────────

def prompt_reglement_interieur(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un règlement intérieur d'entreprise conforme
au Code du travail camerounais — obligatoire pour les entreprises de 11+ salariés.
Structure :
1. DISPOSITIONS GENERALES
2. HORAIRES DE TRAVAIL ET POINTAGE
3. CONGES ET ABSENCES
4. HYGIENE ET SECURITE AU TRAVAIL
5. DISCIPLINE ET SANCTIONS (echelle des sanctions)
6. PROCEDURE DISCIPLINAIRE
7. HARCELEMENT ET DISCRIMINATIONS
8. UTILISATION DES EQUIPEMENTS
9. CONFIDENTIALITE
10. ENTREE EN VIGUEUR
--- DONNEES ---
Entreprise : {donnees.get('requérant','')}
Secteur d'activite : {donnees.get('objet','')}
Nombre de salaries : {donnees.get('faits','')}
Horaires : {donnees.get('duree','')}
Specificites : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_accord_teletravail(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord de télétravail conforme au Code du travail
camerounais et aux pratiques modernes en zone OHADA.
Structure :
1. IDENTIFICATION DES PARTIES
2. DEFINITION ET MODALITES DU TELETRAVAIL
3. LIEU(X) DE TELETRAVAIL
4. JOURS ET HORAIRES DE TELETRAVAIL
5. EQUIPEMENTS FOURNIS PAR L'EMPLOYEUR
6. PRISE EN CHARGE DES FRAIS
7. DISPONIBILITE ET JOIGNABILITE
8. SANTE ET SECURITE A DOMICILE
9. REVERSIBILITE
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Salarie : {donnees.get('salarie','')}
Poste : {donnees.get('poste','')}
Jours de teletravail/semaine : {donnees.get('duree','')}
Date d'effet : {donnees.get('date_debut','')}
Indemnite mensuelle (FCFA) : {donnees.get('montant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_plan_sauvegarde_emploi(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un Plan de Sauvegarde de l'Emploi (PSE) conforme
au Code du travail camerounais et aux normes OHADA.
Structure :
1. CONTEXTE ECONOMIQUE ET JUSTIFICATION
2. NOMBRE ET CATEGORIES DE POSTES SUPPRIMES
3. CRITERES D'ORDRE DES LICENCIEMENTS
4. MESURES DE RECLASSEMENT INTERNE
5. MESURES D'ACCOMPAGNEMENT EXTERNE
6. INDEMNITES SUPRA-LEGALES
7. CALENDRIER DE MISE EN OEUVRE
8. CONSULTATION DES REPRESENTANTS DU PERSONNEL
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Nombre de postes supprimes : {donnees.get('objet','')}
Motif economique : {donnees.get('faits','')}
Indemnites proposees (FCFA) : {donnees.get('montant','')}
Calendrier : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_accord_interessement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord d'intéressement des salariés conforme
au droit camerounais et aux pratiques OHADA.
Structure :
1. IDENTIFICATION DES PARTIES
2. BENEFICIAIRES
3. CRITERES DE CALCUL (resultat, chiffre d'affaires, objectifs)
4. FORMULE D'INTERESSEMENT
5. MODALITES DE VERSEMENT
6. INFORMATION DES SALARIES
7. DUREE ET RENOUVELLEMENT
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Beneficiaires : {donnees.get('faits','tous les salaries')}
Critere principal : {donnees.get('objet','')}
Enveloppe max (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','1 an')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── SANTE ET EDUCATION ────────────────────────────────────────────────────────

def prompt_contrat_medical(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de partenariat médical conforme
au droit de la santé camerounais et aux normes OHADA.
Structure :
1. IDENTIFICATION DES ETABLISSEMENTS
2. OBJET DU PARTENARIAT (referenement, partage equipements)
3. MODALITES DE COLLABORATION
4. RESPONSABILITE MEDICALE
5. FACTURATION ET PAIEMENT
6. CONFIDENTIALITE DES DOSSIERS PATIENTS
7. DUREE ET RESILIATION
--- DONNEES ---
Etablissement A : {donnees.get('requérant','')}
Etablissement B : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Modalites financieres : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_convention_formation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de formation professionnelle conforme
au Code du travail camerounais et aux normes OHADA.
Structure :
1. IDENTIFICATION (employeur, salarie, organisme de formation)
2. OBJET ET PROGRAMME DE FORMATION
3. DUREE ET CALENDRIER
4. COUT DE LA FORMATION
5. PRISE EN CHARGE FINANCIERE
6. CLAUSE DE DEDIT-FORMATION (remboursement si depart premature)
7. ATTESTATION DE FORMATION
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Salarie : {donnees.get('salarie','')}
Organisme : {donnees.get('adversaire','')}
Formation : {donnees.get('objet','')}
Cout (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Clause dedit : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_scolarite(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de scolarité conforme au droit de l'éducation
camerounais — etablissement prive et famille.
Structure :
1. IDENTIFICATION (etablissement et parents/tuteur)
2. ELEVE CONCERNE
3. CLASSE ET ANNEE SCOLAIRE
4. FRAIS DE SCOLARITE (montant, echeancier)
5. REGLEMENT INTERIEUR (reference)
6. OBLIGATIONS DE L'ETABLISSEMENT
7. OBLIGATIONS DES PARENTS
8. CONDITIONS DE RESILIATION
--- DONNEES ---
Etablissement : {donnees.get('requérant','')}
Parents/Tuteur : {donnees.get('adversaire','')}
Eleve : {donnees.get('objet','')}
Classe : {donnees.get('poste','')}
Frais annuels (FCFA) : {donnees.get('montant','')}
Echeancier : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── HOTELLERIE ET RESTAURATION ────────────────────────────────────────────────

def prompt_contrat_gerance_hotel(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de gérance d'hôtel conforme au droit OHADA
et au droit commercial camerounais.
Structure :
1. IDENTIFICATION (proprietaire et gerant)
2. DESCRIPTION DE L'ETABLISSEMENT
3. DUREE DU CONTRAT DE GERANCE
4. REMUNERATION DU GERANT (fixe + variable)
5. POUVOIRS DU GERANT
6. OBLIGATIONS DU GERANT (normes, classement, entretien)
7. OBLIGATIONS DU PROPRIETAIRE
8. INVENTAIRE DES BIENS
9. RESILIATION ET INDEMNITES
--- DONNEES ---
Proprietaire : {donnees.get('requérant','')}
Gerant : {donnees.get('adversaire','')}
Hotel : {donnees.get('adresse','')}
Nombre de chambres : {donnees.get('objet','')}
Remuneration mensuelle (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_evenementiel(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de prestation événementielle conforme
au droit OHADA et au droit commercial camerounais.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESCRIPTION DE L'EVENEMENT (nature, date, lieu)
3. PRESTATIONS INCLUSES
4. PRIX ET ACOMPTE
5. CONDITIONS D'ANNULATION ET REMBOURSEMENT
6. FORCE MAJEURE
7. RESPONSABILITE
8. ASSURANCES
--- DONNEES ---
Prestataire : {donnees.get('requérant','')}
Client : {donnees.get('adversaire','')}
Evenement : {donnees.get('objet','')}
Date : {donnees.get('date_debut','')}
Lieu : {donnees.get('adresse','')}
Prix total (FCFA) : {donnees.get('montant','')}
Acompte (FCFA) : {donnees.get('depot_garantie','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── OAPI COMPLEMENTAIRE ───────────────────────────────────────────────────────

def prompt_cession_brevet(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de cession de brevet conforme à l'Accord de Bangui
(OAPI révisé 2015) — transfert de propriété d'un brevet d'invention.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESIGNATION DU BREVET (numero OAPI, titre, pays)
3. ETENDUE DE LA CESSION (droits cedes)
4. PRIX DE CESSION
5. GARANTIE D'EVICTION
6. GARANTIE DE NON-CONTREFACON
7. INSCRIPTION AU REGISTRE OAPI
8. FRAIS D'ENREGISTREMENT
--- DONNEES ---
Cedant : {donnees.get('requérant','')}
Cessionnaire : {donnees.get('adversaire','')}
Brevet : {donnees.get('objet','')}
Numero OAPI : {donnees.get('reference_jugement','')}
Prix (FCFA) : {donnees.get('montant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_licence_brevet(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de licence de brevet conforme à l'Accord de Bangui
OAPI — autorisation d'exploitation sans transfert de propriété.
Structure :
1. IDENTIFICATION (concedant et licencie)
2. BREVET LICENCE (numero OAPI, portee)
3. TERRITOIRE ET EXCLUSIVITE
4. REDEVANCES (montant ou % sur CA)
5. OBLIGATIONS D'EXPLOITATION
6. AMELIORATIONS ET INVENTIONS DERIVEES
7. DUREE ET RENOUVELLEMENT
8. RESILIATION
--- DONNEES ---
Concedant : {donnees.get('requérant','')}
Licencie : {donnees.get('adversaire','')}
Brevet : {donnees.get('objet','')}
Territoire : {donnees.get('adresse','')}
Redevance : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_cession_droit_auteur(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de cession de droits d'auteur conforme
à l'Accord de Bangui OAPI et au droit camerounais.
Structure :
1. IDENTIFICATION DES PARTIES
2. OEUVRE CONCERNEE (description precise)
3. DROITS CEDES (reproduction, representation, adaptation)
4. TERRITOIRE
5. DUREE (limitee ou toute la duree de protection)
6. PRIX DE CESSION
7. DROIT MORAL (incessible)
8. GARANTIES DE L'AUTEUR
--- DONNEES ---
Auteur cedant : {donnees.get('requérant','')}
Cessionnaire : {donnees.get('adversaire','')}
Oeuvre : {donnees.get('objet','')}
Droits cedes : {donnees.get('faits','')}
Territoire : {donnees.get('adresse','')}
Prix (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── PROCEDURES COLLECTIVES ────────────────────────────────────────────────────

def prompt_declaration_creance(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une déclaration de créance conforme à l'AUPC OHADA 2015
(Art. 78 et suivants) — dans le cadre d'une procédure collective.
Structure :
1. IDENTIFICATION DU CREANCIER
2. IDENTIFICATION DU DEBITEUR EN PROCEDURE COLLECTIVE
3. MONTANT DE LA CREANCE (principal, interets, accessoires)
4. NATURE ET ORIGINE DE LA CREANCE
5. SURETES DONT BENEFICIE LE CREANCIER
6. PIECES JUSTIFICATIVES JOINTES
7. CLASSEMENT SOLLICITE (privilegiee, chirographaire)
8. SIGNATURE ET DATE
--- DONNEES ---
Creancier : {donnees.get('creancier','')}
Debiteur en procedure : {donnees.get('debiteur','')}
Montant principal (FCFA) : {donnees.get('montant','')}
Nature de la creance : {donnees.get('nature_creance','')}
Suretes : {donnees.get('suretes','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_plan_redressement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un plan de redressement judiciaire conforme
à l'AUPC OHADA 2015 — propositions du débiteur aux créanciers.
Structure :
1. DIAGNOSTIC DE L'ENTREPRISE
2. CAUSES DES DIFFICULTES
3. MESURES DE REDRESSEMENT ENVISAGEES
4. PLAN DE CONTINUATION (echeancier de paiement)
5. MESURES SOCIALES (emploi, formation)
6. PERSPECTIVES DE RETOUR A MEILLEURE FORTUNE
7. GARANTIES OFFERTES AUX CREANCIERS
8. CALENDRIER DE MISE EN OEUVRE
--- DONNEES ---
Debiteur : {donnees.get('debiteur','')}
Forme sociale : {donnees.get('societe','')}
Passif total (FCFA) : {donnees.get('montant','')}
Mesures proposees : {donnees.get('faits','')}
Duree du plan : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_accord_conciliation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord de conciliation conforme à l'AUPC OHADA 2015
(Art. 5-1 et suivants) — procédure préventive amiable.
Structure :
1. IDENTIFICATION DES PARTIES
2. CONTEXTE (difficultes de l'entreprise)
3. CONCESSIONS DES CREANCIERS (delais, remises)
4. ENGAGEMENTS DU DEBITEUR
5. CALENDRIER D'EXECUTION
6. HOMOLOGATION PAR LE TRIBUNAL
7. EFFETS DE L'ACCORD (suspension des poursuites)
8. CADUCITE EN CAS D'INEXECUTION
--- DONNEES ---
Debiteur : {donnees.get('debiteur','')}
Creanciers conciliants : {donnees.get('creancier','')}
Concessions accordees : {donnees.get('faits','')}
Montant total (FCFA) : {donnees.get('montant','')}
Duree du plan : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT INTERNATIONAL PRIVE ─────────────────────────────────────────────────

def prompt_joint_venture(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de joint-venture internationale conforme
au droit OHADA et aux usages du commerce international.
Structure :
1. IDENTIFICATION DES PARTENAIRES (nationalites differentes)
2. OBJET DU JOINT-VENTURE
3. STRUCTURE JURIDIQUE CHOISIE (societe commune ou contractuelle)
4. APPORTS DE CHAQUE PARTENAIRE
5. GOUVERNANCE ET PRISE DE DECISIONS
6. PARTAGE DES PROFITS ET PERTES
7. PROPRIETE INTELLECTUELLE
8. DUREE ET SORTIE
9. DROIT APPLICABLE ET ARBITRAGE CCJA
--- DONNEES ---
Partenaire A : {donnees.get('requérant','')}
Partenaire B : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Apports : {donnees.get('faits','')}
Partage profits : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_commerce_international(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de vente internationale de marchandises conforme
aux Incoterms 2020 et aux principes OHADA du commerce international.
Structure :
1. IDENTIFICATION DES PARTIES (vendeur et acheteur)
2. DESIGNATION DES MARCHANDISES
3. PRIX ET DEVISE
4. INCOTERM APPLICABLE (FOB, CIF, DAP...)
5. MODALITES DE PAIEMENT (credit documentaire, virement SWIFT)
6. TRANSFERT DE PROPRIETE ET DES RISQUES
7. DOCUMENTS REQUIS (facture, BL, certificat origine)
8. ASSURANCE
9. GARANTIES ET RECLAMATIONS
10. DROIT APPLICABLE ET ARBITRAGE CCI/CCJA
--- DONNEES ---
Vendeur : {donnees.get('requérant','')}
Acheteur : {donnees.get('adversaire','')}
Marchandises : {donnees.get('objet','')}
Prix total : {donnees.get('montant','')}
Incoterm : {donnees.get('faits','CIF')}
Paiement : {donnees.get('nature_creance','credit documentaire')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── ACTES NOTARIES ────────────────────────────────────────────────────────────

def prompt_testament(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un testament olographe conforme au droit successoral
camerounais — acte de dernière volonté.
Structure :
1. EN-TETE (identification du testateur)
2. DECLARATION DE BONNE SANTE MENTALE
3. DESIGNATION DES LEGATAIRES
4. BIENS LEGUES A CHAQUE LEGATAIRE
5. RESERVE HEREDITAIRE (respect des droits des heritiers reserves)
6. EXECUTEUR TESTAMENTAIRE (si applicable)
7. REVOCATION DES TESTAMENTS ANTERIEURS
8. DATE ET SIGNATURE MANUSCRITE (obligatoire)
--- DONNEES ---
Testateur : {donnees.get('requérant','')}
Legataires : {donnees.get('adversaire','')}
Biens legues : {donnees.get('objet','')}
Legs specifiques : {donnees.get('faits','')}
Executeur testamentaire : {donnees.get('creancier','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_partage_successoral(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de partage successoral conforme au droit
successoral camerounais et aux principes OHADA.
Structure :
1. IDENTIFICATION DES HERITIERS
2. DESIGATION DU DEFUNT ET DATE DE DECES
3. MASSE SUCCESSORALE (actif et passif)
4. QUOTITE DISPONIBLE ET RESERVE
5. LOTS ATTRIBUES A CHAQUE HERITIER
6. SOULTES EVENTUELLES
7. DECLARATION DE PARTAGE DEFINITIF
8. ENREGISTREMENT ET PUBLICITE FONCIERE
--- DONNEES ---
Defunt : {donnees.get('debiteur','')}
Heritiers : {donnees.get('adversaire','')}
Actif successoral (FCFA) : {donnees.get('montant','')}
Biens a partager : {donnees.get('objet','')}
Lots : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_donation_partage(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de donation-partage conforme au droit
camerounais — anticipation de succession entre vifs.
Structure :
1. IDENTIFICATION DU DONATEUR ET DES DONATAIRES
2. BIENS DONNEES ET PARTAGES
3. LOTS ATTRIBUES A CHAQUE DONATAIRE
4. VALEUR DE CHAQUE LOT
5. SOULTES EVENTUELLES
6. RAPPORT A SUCCESSION
7. ACCEPTATION DES DONATAIRES
8. ENREGISTREMENT
--- DONNEES ---
Donateur : {donnees.get('requérant','')}
Donataires : {donnees.get('adversaire','')}
Biens : {donnees.get('objet','')}
Lots : {donnees.get('faits','')}
Valeur totale (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT NUMERIQUE COMPLEMENTAIRE ────────────────────────────────────────────

def prompt_contrat_maintenance_informatique(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de maintenance informatique conforme
au droit OHADA et aux usages du secteur informatique.
Structure :
1. IDENTIFICATION DES PARTIES
2. MATERIELS ET LOGICIELS COUVERTS
3. TYPES DE MAINTENANCE (preventive, corrective, evolutive)
4. NIVEAUX DE SERVICE (SLA - delais d'intervention)
5. ASTREINTE ET URGENCES
6. PRIX ET FACTURATION
7. EXCLUSIONS
8. PROPRIETE DES DONNEES
9. DUREE ET RESILIATION
--- DONNEES ---
Prestataire : {donnees.get('requérant','')}
Client : {donnees.get('adversaire','')}
Systemes couverts : {donnees.get('objet','')}
Prix mensuel (FCFA) : {donnees.get('montant','')}
SLA : {donnees.get('faits','4h ouvrables')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_hebergement_web(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat d'hébergement web conforme au droit
camerounais du numérique et aux standards OHADA.
Structure :
1. IDENTIFICATION DES PARTIES
2. SERVICES D'HEBERGEMENT (specifications techniques)
3. DISPONIBILITE GARANTIE (SLA uptime)
4. SECURITE ET SAUVEGARDE
5. BANDE PASSANTE ET STOCKAGE
6. DONNEES PERSONNELLES (conformite)
7. PRIX ET PAIEMENT
8. SUSPENSION ET RESILIATION
9. RESPONSABILITES
--- DONNEES ---
Hebergeur : {donnees.get('requérant','')}
Client : {donnees.get('adversaire','')}
Specifications : {donnees.get('objet','')}
Prix mensuel (FCFA) : {donnees.get('montant','')}
SLA uptime : {donnees.get('faits','99.9%')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_cgv(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras des Conditions Générales de Vente (CGV) conformes
au droit commercial camerounais et à l'AUDCG OHADA.
Structure :
1. IDENTIFICATION DU VENDEUR
2. CHAMP D'APPLICATION
3. PRIX ET MODALITES DE PAIEMENT
4. LIVRAISON ET TRANSFERT DE RISQUES
5. GARANTIES LEGALES
6. DROIT DE RETRACTATION (vente a distance)
7. RESPONSABILITE DU VENDEUR
8. RECLAMATIONS ET SAV
9. DROIT APPLICABLE
--- DONNEES ---
Vendeur : {donnees.get('requérant','')}
Produits/Services : {donnees.get('objet','')}
Conditions de paiement : {donnees.get('montant','')}
Delai de livraison : {donnees.get('duree','')}
Faits/clauses : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_transfert_donnees(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord de transfert de données personnelles conforme
à la loi camerounaise sur la protection des données personnelles.
Structure :
1. IDENTIFICATION DES RESPONSABLES DE TRAITEMENT
2. DONNEES TRANSFEREES (categories, finalites)
3. BASE LEGALE DU TRANSFERT
4. PAYS DESTINATAIRE ET NIVEAU DE PROTECTION
5. GARANTIES APPROPRIEES
6. OBLIGATIONS DU DESTINATAIRE
7. DROITS DES PERSONNES CONCERNEES
8. DUREE ET DESTRUCTION DES DONNEES
--- DONNEES ---
Exportateur : {donnees.get('requérant','')}
Importateur : {donnees.get('adversaire','')}
Donnees transferees : {donnees.get('objet','')}
Pays destinataire : {donnees.get('adresse','')}
Garanties : {donnees.get('faits','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── MARCHES PUBLICS COMPLEMENTAIRES ──────────────────────────────────────────

def prompt_marche_public_fournitures(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de marché public de fournitures conforme
au Code des Marchés Publics camerounais.
Structure :
1. IDENTIFICATION (acheteur public et fournisseur)
2. DESIGNATION DES FOURNITURES
3. QUANTITES ET SPECIFICATIONS TECHNIQUES
4. PRIX UNITAIRES ET MONTANT TOTAL
5. DELAIS DE LIVRAISON
6. MODALITES DE RECEPTION
7. GARANTIE DES FOURNITURES
8. PENALITES DE RETARD
9. RESILIATION
--- DONNEES ---
Acheteur public : {donnees.get('requérant','')}
Fournisseur : {donnees.get('adversaire','')}
Fournitures : {donnees.get('objet','')}
Montant total (FCFA) : {donnees.get('montant','')}
Delai de livraison : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_marche_public_services(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de marché public de services conforme
au Code des Marchés Publics camerounais.
Structure :
1. IDENTIFICATION (maitre d'ouvrage et prestataire)
2. OBJET DES SERVICES
3. DUREE D'EXECUTION
4. PRIX ET MODALITES DE REGLEMENT
5. RAPPORTS ET LIVRABLES
6. PENALITES
7. RESILIATION
--- DONNEES ---
Maitre d'ouvrage : {donnees.get('requérant','')}
Prestataire : {donnees.get('adversaire','')}
Services : {donnees.get('objet','')}
Montant (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_concession_service_public(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de délégation de service public conforme
au droit administratif camerounais et aux normes OHADA.
Structure :
1. IDENTIFICATION (autorite concedante et concessionnaire)
2. OBJET DE LA CONCESSION (service public delegue)
3. ZONE GEOGRAPHIQUE
4. DUREE DE LA CONCESSION
5. INVESTISSEMENTS DU CONCESSIONNAIRE
6. TARIFS ET MODALITES DE REVISION
7. DROITS ET OBLIGATIONS DES PARTIES
8. CONTROLE DE L'AUTORITE CONCEDANTE
9. FIN DE CONCESSION (reprise des biens)
--- DONNEES ---
Autorite concedante : {donnees.get('requérant','')}
Concessionnaire : {donnees.get('adversaire','')}
Service public : {donnees.get('objet','')}
Zone : {donnees.get('adresse','')}
Duree : {donnees.get('duree','')}
Investissements (FCFA) : {donnees.get('montant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── ASSURANCES CIMA COMPLEMENTAIRES ──────────────────────────────────────────

def prompt_contrat_assurance_multirisque(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les conditions particulières d'un contrat d'assurance
multirisque professionnelle conforme au Code CIMA.
Structure :
1. IDENTIFICATION (assureur et assure)
2. BIENS ET ACTIVITES ASSURES
3. GARANTIES SOUSCRITES :
   - Incendie et risques annexes
   - Degats des eaux
   - Vol et vandalisme
   - Responsabilite civile
   - Pertes d'exploitation
4. CAPITAUX ASSURES PAR GARANTIE
5. FRANCHISES
6. PRIME ET PAIEMENT
7. EXCLUSIONS
8. DECLARATION ET GESTION DES SINISTRES
--- DONNEES ---
Assure : {donnees.get('requérant','')}
Activite : {donnees.get('objet','')}
Locaux : {donnees.get('adresse','')}
Capital total assure (FCFA) : {donnees.get('montant','')}
Prime annuelle (FCFA) : {donnees.get('nature_creance','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── PORTAGE SALARIAL ──────────────────────────────────────────────────────────

def prompt_portage_salarial(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de portage salarial conforme au droit
du travail camerounais et aux pratiques OHADA.
Structure :
1. IDENTIFICATION (societe de portage, salarie porte, client)
2. MISSION DU SALARIE PORTE
3. REMUNERATION (calcul sur honoraires)
4. FRAIS DE GESTION DE LA SOCIETE DE PORTAGE
5. PROTECTION SOCIALE DU SALARIE PORTE
6. DUREE DE LA MISSION
7. COMPTE RENDU D'ACTIVITE
--- DONNEES ---
Societe de portage : {donnees.get('requérant','')}
Salarie porte : {donnees.get('salarie','')}
Client : {donnees.get('adversaire','')}
Mission : {donnees.get('objet','')}
Honoraires (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── ACTES DE PROCEDURE COMPLEMENTAIRES ────────────────────────────────────────

def prompt_assignation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une assignation conforme au Code de procédure civile
et commerciale camerounais — acte introductif d'instance.
Structure :
1. EN-TETE (huissier, parties, tribunal saisi)
2. IDENTIFICATION DU DEFENDEUR
3. OBJET DE LA DEMANDE
4. EXPOSE DES FAITS ET MOYENS
5. PRETENTIONS (demandes chiffrees)
6. FONDEMENTS JURIDIQUES
7. DATE D'AUDIENCE
8. INJONCTION DE COMPARAITRE
--- DONNEES ---
Demandeur : {donnees.get('requérant','')}
Defendeur : {donnees.get('adversaire','')}
Tribunal : {donnees.get('tribunal','')}
Objet : {donnees.get('objet','')}
Montant reclame (FCFA) : {donnees.get('montant','')}
Fondements : {donnees.get('fondements_juridiques','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_desistement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de désistement d'instance conforme au Code de
procédure civile camerounais.
Structure :
1. IDENTIFICATION DES PARTIES
2. REFERENCE A L'INSTANCE EN COURS
3. DECLARATION DE DESISTEMENT
4. MOTIFS (accord transactionnel, etc.)
5. EFFETS (extinction de l'instance)
6. FRAIS ET DEPENS
7. SIGNATURES
--- DONNEES ---
Demandeur se desistant : {donnees.get('requérant','')}
Defendeur : {donnees.get('adversaire','')}
Tribunal : {donnees.get('tribunal','')}
Reference dossier : {donnees.get('reference_jugement','')}
Motifs : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_transaction_judiciaire(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord transactionnel judiciaire conforme au droit OHADA
— règlement du litige en cours d'instance.
Structure :
1. IDENTIFICATION DES PARTIES ET DE L'INSTANCE
2. RAPPEL DU LITIGE
3. CONCESSIONS RECIPROQUES
4. MONTANT DE L'INDEMNITE TRANSACTIONNELLE
5. MODALITES DE PAIEMENT
6. RENONCIATION A TOUT RECOURS
7. HOMOLOGATION PAR LE TRIBUNAL
8. EFFETS (autorite de la chose jugee)
--- DONNEES ---
Partie A : {donnees.get('requérant','')}
Partie B : {donnees.get('adversaire','')}
Tribunal : {donnees.get('tribunal','')}
Indemnite transactionnelle (FCFA) : {donnees.get('montant','')}
Concessions : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_pv_conciliation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un procès-verbal de conciliation conforme au Code de
procédure civile camerounais et à l'AUM OHADA 2017.
Structure :
1. EN-TETE (date, lieu, conciliateur)
2. IDENTIFICATION DES PARTIES
3. EXPOSE DU DIFFEREND
4. TENTATIVE DE CONCILIATION
5. ACCORD DES PARTIES (ou echec)
6. TERMES DE L'ACCORD (si succes)
7. FORCE EXECUTOIRE
8. SIGNATURES
--- DONNEES ---
Conciliateur : {donnees.get('tribunal','')}
Partie A : {donnees.get('requérant','')}
Partie B : {donnees.get('adversaire','')}
Differend : {donnees.get('objet','')}
Accord : {donnees.get('faits','')}
Montant (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT DE LA FAMILLE COMPLEMENTAIRE ───────────────────────────────────────

def prompt_pension_alimentaire(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de pension alimentaire conforme
au droit de la famille camerounais.
Structure :
1. IDENTIFICATION DES PARTIES (creancier et debiteur d'aliments)
2. BENEFICIAIRES (enfants, conjoint)
3. MONTANT DE LA PENSION
4. MODALITES DE VERSEMENT
5. INDEXATION ANNUELLE
6. CONDITIONS DE REVISION
7. CESSATION DE LA PENSION
--- DONNEES ---
Debiteur d'aliments : {donnees.get('requérant','')}
Creancier d'aliments : {donnees.get('adversaire','')}
Beneficiaires : {donnees.get('objet','')}
Montant mensuel (FCFA) : {donnees.get('montant','')}
Conditions de revision : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_adoption(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une requête en adoption conforme au Code civil
et à la procédure camerounaise.
Structure :
1. IDENTIFICATION DES REQUERANTS (futurs parents adoptifs)
2. IDENTIFICATION DE L'ENFANT A ADOPTER
3. SITUATION JURIDIQUE DE L'ENFANT
4. CONDITIONS REQUISES (age, duree d'accueil, enquete sociale)
5. MOTIVATIONS DES REQUERANTS
6. INTERETS DE L'ENFANT
7. DEMANDE AU TRIBUNAL
--- DONNEES ---
Requerants : {donnees.get('requérant','')}
Enfant : {donnees.get('adversaire','')}
Situation actuelle : {donnees.get('faits','')}
Tribunal : {donnees.get('tribunal','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── CONTRAT DE VENTE ──────────────────────────────────────────────────────────

def prompt_contrat_vente_commerciale(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de vente commerciale conforme à l'AUDCG OHADA 2010
et au droit commercial camerounais.
Structure :
1. IDENTIFICATION DES PARTIES (vendeur et acheteur)
2. DESIGNATION DE LA CHOSE VENDUE
3. PRIX ET MODALITES DE PAIEMENT
4. LIVRAISON (lieu, delai, conditions)
5. TRANSFERT DE PROPRIETE ET DES RISQUES
6. GARANTIES (vices caches, eviction)
7. CLAUSE DE RESERVE DE PROPRIETE
8. PENALITES DE RETARD
9. DROIT APPLICABLE
--- DONNEES ---
Vendeur : {donnees.get('requérant','')}
Acheteur : {donnees.get('adversaire','')}
Bien vendu : {donnees.get('objet','')}
Prix (FCFA) : {donnees.get('montant','')}
Delai de livraison : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_commission(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de commission conforme à l'AUDCG OHADA 2010
(Art. 152-168) — le commissionnaire agit en son nom propre.
Structure :
1. IDENTIFICATION (commettant et commissionnaire)
2. OBJET DE LA COMMISSION (achat ou vente)
3. MARCHANDISES CONCERNEES
4. COMMISSION (taux ou montant fixe)
5. OBLIGATIONS DU COMMISSIONNAIRE
6. COMPTE-RENDU ET JUSTIFICATIFS
7. DEBOURS ET AVANCES
8. DUREE ET RESILIATION
--- DONNEES ---
Commettant : {donnees.get('requérant','')}
Commissionnaire : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Commission (%) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_consignation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de consignation conforme à l'AUDCG OHADA 2010
— dépôt de marchandises en vue de leur vente.
Structure :
1. IDENTIFICATION DES PARTIES (deposant et consignataire)
2. MARCHANDISES CONSIGNEES (description, quantite, valeur)
3. DUREE DE LA CONSIGNATION
4. PRIX DE VENTE MINIMUM
5. COMMISSION DU CONSIGNATAIRE
6. REDDITION DE COMPTE
7. INVENDUS (retour ou destruction)
8. ASSURANCE DES MARCHANDISES
--- DONNEES ---
Deposant : {donnees.get('requérant','')}
Consignataire : {donnees.get('adversaire','')}
Marchandises : {donnees.get('objet','')}
Valeur (FCFA) : {donnees.get('montant','')}
Prix minimum de vente : {donnees.get('nature_creance','')}
Commission (%) : {donnees.get('suretes','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""
'''

NOUVELLES_ENTREES_V2 = """
PROMPTS_REDACTION.update({
    "statuts_sasu": {"nom": "Statuts SASU", "description": "Societe par Actions Simplifiee Unipersonnelle OHADA", "champs": ["societe","objet","adresse","capital","requérant","faits"], "fn": prompt_statuts_sasu},
    "statuts_scs": {"nom": "Statuts SCS", "description": "Art. 293-308 AUSCGIE OHADA - commandites et commanditaires", "champs": ["societe","objet","adresse","capital","requérant","creancier","faits"], "fn": prompt_statuts_scs},
    "cession_actions_sa": {"nom": "Cession d'actions SA", "description": "AUSCGIE OHADA - transfert valeurs mobilieres", "champs": ["requérant","adversaire","societe","objet","montant","date_debut","faits"], "fn": prompt_cession_actions_sa},
    "convention_compte_courant": {"nom": "Convention de compte courant d'associe", "description": "Pret associe a sa societe - taux legal OHADA", "champs": ["requérant","societe","montant","suretes","duree","faits"], "fn": prompt_convention_compte_courant},
    "dissolution_amiable": {"nom": "Dissolution et liquidation amiable", "description": "AUSCGIE OHADA - radiation RCCM", "champs": ["societe","creancier","requérant","faits","montant"], "fn": prompt_dissolution_amiable},
    "contrat_fermage": {"nom": "Contrat de fermage", "description": "Exploitation agricole contre redevance - droit rural CM", "champs": ["bailleur","preneur","adresse","superficie","montant","duree","faits"], "fn": prompt_contrat_fermage},
    "contrat_metayage": {"nom": "Contrat de metayage", "description": "Partage des recoltes - droit rural camerounais", "champs": ["bailleur","preneur","adresse","faits","duree"], "fn": prompt_contrat_metayage},
    "contrat_vente_recoltes": {"nom": "Vente de recoltes sur pied", "description": "Droit commercial CM - usages agricoles OHADA", "champs": ["requérant","adversaire","objet","superficie","montant","date_debut","faits"], "fn": prompt_contrat_vente_recoltes},
    "contrat_sous_traitance_petroliere": {"nom": "Sous-traitance petroliere", "description": "Code petrolier CM - knock-for-knock - standards internationaux", "champs": ["requérant","adversaire","objet","adresse","montant","duree","faits"], "fn": prompt_contrat_sous_traitance_petroliere},
    "convention_exploitation_miniere": {"nom": "Convention d'exploitation miniere", "description": "Code minier camerounais - redevances - environnement", "champs": ["requérant","adversaire","adresse","objet","montant","duree"], "fn": prompt_convention_exploitation_miniere},
    "contrat_credit_bail": {"nom": "Contrat de credit-bail (leasing)", "description": "Droit OHADA - COBAC - option d'achat", "champs": ["creancier","debiteur","objet","montant","nature_creance","duree","suretes","faits"], "fn": prompt_contrat_credit_bail},
    "ouverture_credit": {"nom": "Contrat d'ouverture de credit", "description": "Reglementation COBAC - ligne de credit - garanties", "champs": ["creancier","debiteur","montant","objet","suretes","duree","nature_creance"], "fn": prompt_ouverture_credit},
    "garantie_bancaire": {"nom": "Garantie bancaire a premiere demande", "description": "COBAC - garantie autonome - appel sans reserves", "champs": ["creancier","adversaire","debiteur","objet","montant","duree"], "fn": prompt_garantie_bancaire},
    "convention_tresorerie": {"nom": "Convention de tresorerie (cash pooling)", "description": "Droit OHADA - COBAC - groupes de societes", "champs": ["requérant","creancier","montant","suretes","duree"], "fn": prompt_convention_tresorerie},
    "reglement_interieur": {"nom": "Reglement interieur d'entreprise", "description": "Obligatoire 11+ salaries - Code travail CM", "champs": ["requérant","objet","faits","duree","montant"], "fn": prompt_reglement_interieur},
    "accord_teletravail": {"nom": "Accord de teletravail", "description": "Code travail CM - equipements - disponibilite - reversibilite", "champs": ["employeur","salarie","poste","duree","date_debut","montant","faits"], "fn": prompt_accord_teletravail},
    "plan_sauvegarde_emploi": {"nom": "Plan de sauvegarde de l'emploi (PSE)", "description": "Code travail CM - reclassement - indemnites", "champs": ["employeur","objet","faits","montant","duree"], "fn": prompt_plan_sauvegarde_emploi},
    "accord_interessement": {"nom": "Accord d'interessement des salaries", "description": "Droit camerounais - criteres performance - versement", "champs": ["employeur","faits","objet","montant","duree"], "fn": prompt_accord_interessement},
    "contrat_medical": {"nom": "Convention de partenariat medical", "description": "Droit sante CM - referenement - confidentialite dossiers", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_contrat_medical},
    "convention_formation": {"nom": "Convention de formation professionnelle", "description": "Code travail CM - clause dedit-formation", "champs": ["employeur","salarie","adversaire","objet","montant","duree","faits"], "fn": prompt_convention_formation},
    "contrat_scolarite": {"nom": "Contrat de scolarite", "description": "Droit education CM - frais scolaires - obligations", "champs": ["requérant","adversaire","objet","poste","montant","faits"], "fn": prompt_contrat_scolarite},
    "contrat_gerance_hotel": {"nom": "Contrat de gerance d'hotel", "description": "Droit commercial CM - OHADA - remuneration gerant", "champs": ["requérant","adversaire","adresse","objet","montant","duree","faits"], "fn": prompt_contrat_gerance_hotel},
    "contrat_evenementiel": {"nom": "Contrat de prestation evenementielle", "description": "Droit commercial CM - annulation - force majeure", "champs": ["requérant","adversaire","objet","date_debut","adresse","montant","depot_garantie","faits"], "fn": prompt_contrat_evenementiel},
    "cession_brevet": {"nom": "Cession de brevet OAPI", "description": "Accord de Bangui 2015 - transfert propriete brevet", "champs": ["requérant","adversaire","objet","reference_jugement","montant","faits"], "fn": prompt_cession_brevet},
    "licence_brevet": {"nom": "Licence de brevet OAPI", "description": "Accord de Bangui 2015 - exploitation sans cession", "champs": ["requérant","adversaire","objet","adresse","montant","duree"], "fn": prompt_licence_brevet},
    "cession_droit_auteur": {"nom": "Cession de droits d'auteur", "description": "OAPI Accord Bangui - reproduction representation adaptation", "champs": ["requérant","adversaire","objet","faits","adresse","montant","duree"], "fn": prompt_cession_droit_auteur},
    "declaration_creance": {"nom": "Declaration de creance", "description": "Art. 78+ AUPC OHADA 2015 - procedure collective", "champs": ["creancier","debiteur","montant","nature_creance","suretes","faits"], "fn": prompt_declaration_creance},
    "plan_redressement": {"nom": "Plan de redressement judiciaire", "description": "AUPC OHADA 2015 - propositions debiteur aux creanciers", "champs": ["debiteur","societe","montant","faits","duree"], "fn": prompt_plan_redressement},
    "accord_conciliation": {"nom": "Accord de conciliation OHADA", "description": "Art. 5-1+ AUPC OHADA 2015 - procedure preventive amiable", "champs": ["debiteur","creancier","faits","montant","duree"], "fn": prompt_accord_conciliation},
    "joint_venture": {"nom": "Contrat de joint-venture internationale", "description": "Droit OHADA - arbitrage CCJA - gouvernance commune", "champs": ["requérant","adversaire","objet","faits","montant","duree"], "fn": prompt_joint_venture},
    "contrat_commerce_international": {"nom": "Contrat de vente internationale", "description": "Incoterms 2020 - OHADA - credit documentaire", "champs": ["requérant","adversaire","objet","montant","faits","nature_creance"], "fn": prompt_contrat_commerce_international},
    "testament": {"nom": "Testament olographe", "description": "Droit successoral CM - legataires - reserve hereditaire", "champs": ["requérant","adversaire","objet","faits","creancier"], "fn": prompt_testament},
    "partage_successoral": {"nom": "Acte de partage successoral", "description": "Droit successoral CM - lots - soultes - publicite fonciere", "champs": ["debiteur","adversaire","montant","objet","faits"], "fn": prompt_partage_successoral},
    "donation_partage": {"nom": "Donation-partage", "description": "Anticipation succession - lots - rapport a succession", "champs": ["requérant","adversaire","objet","faits","montant"], "fn": prompt_donation_partage},
    "contrat_maintenance_informatique": {"nom": "Contrat de maintenance informatique", "description": "SLA - niveaux de service - astreinte urgences", "champs": ["requérant","adversaire","objet","montant","faits","duree"], "fn": prompt_contrat_maintenance_informatique},
    "contrat_hebergement_web": {"nom": "Contrat d'hebergement web", "description": "Droit numerique CM - SLA uptime - securite donnees", "champs": ["requérant","adversaire","objet","montant","faits","duree"], "fn": prompt_contrat_hebergement_web},
    "cgv": {"nom": "Conditions Generales de Vente (CGV)", "description": "AUDCG OHADA - prix - livraison - garanties legales", "champs": ["requérant","objet","montant","duree","faits"], "fn": prompt_cgv},
    "transfert_donnees": {"nom": "Accord de transfert de donnees personnelles", "description": "Loi camerounaise donnees personnelles - garanties", "champs": ["requérant","adversaire","objet","adresse","faits","duree"], "fn": prompt_transfert_donnees},
    "marche_public_fournitures": {"nom": "Marche public de fournitures", "description": "Code marches publics CM - specifications - reception", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_marche_public_fournitures},
    "marche_public_services": {"nom": "Marche public de services", "description": "Code marches publics CM - livrables - penalites", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_marche_public_services},
    "concession_service_public": {"nom": "Concession de service public", "description": "Droit administratif CM - tarifs - controle - fin concession", "champs": ["requérant","adversaire","objet","adresse","duree","montant","faits"], "fn": prompt_concession_service_public},
    "contrat_assurance_multirisque": {"nom": "Assurance multirisque professionnelle", "description": "Code CIMA - incendie - vol - RC - pertes exploitation", "champs": ["requérant","objet","adresse","montant","nature_creance","faits"], "fn": prompt_contrat_assurance_multirisque},
    "portage_salarial": {"nom": "Contrat de portage salarial", "description": "Code travail CM - protection sociale - gestion honoraires", "champs": ["requérant","salarie","adversaire","objet","montant","duree"], "fn": prompt_portage_salarial},
    "assignation": {"nom": "Assignation", "description": "CPC camerounais - acte introductif d'instance", "champs": ["requérant","adversaire","tribunal","objet","montant","fondements_juridiques","faits"], "fn": prompt_assignation},
    "desistement": {"nom": "Desistement d'instance", "description": "CPC camerounais - extinction instance - accord transactionnel", "champs": ["requérant","adversaire","tribunal","reference_jugement","faits"], "fn": prompt_desistement},
    "transaction_judiciaire": {"nom": "Transaction judiciaire", "description": "Droit OHADA - autorite chose jugee - homologation", "champs": ["requérant","adversaire","tribunal","montant","faits"], "fn": prompt_transaction_judiciaire},
    "pv_conciliation": {"nom": "PV de conciliation", "description": "CPC CM - AUM OHADA 2017 - force executoire", "champs": ["tribunal","requérant","adversaire","objet","faits","montant"], "fn": prompt_pv_conciliation},
    "pension_alimentaire": {"nom": "Convention de pension alimentaire", "description": "Droit famille CM - enfants - conjoint - indexation", "champs": ["requérant","adversaire","objet","montant","faits"], "fn": prompt_pension_alimentaire},
    "adoption": {"nom": "Requete en adoption", "description": "Code civil CM - procedure - interet de l'enfant", "champs": ["requérant","adversaire","faits","tribunal"], "fn": prompt_adoption},
    "contrat_vente_commerciale": {"nom": "Contrat de vente commerciale", "description": "AUDCG OHADA 2010 - reserve de propriete - garanties", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_contrat_vente_commerciale},
    "contrat_commission": {"nom": "Contrat de commission", "description": "Art. 152-168 AUDCG OHADA - agit en nom propre", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_contrat_commission},
    "contrat_consignation": {"nom": "Contrat de consignation", "description": "AUDCG OHADA - depot marchandises - vente pour compte", "champs": ["requérant","adversaire","objet","montant","nature_creance","suretes","duree"], "fn": prompt_contrat_consignation},
})
"""

with open('/root/odyxia-droit/prompts.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content + "\n" + NOUVEAUX_PROMPTS_V2 + "\n" + NOUVELLES_ENTREES_V2

with open('/root/odyxia-droit/prompts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK - Vague 2 ajoutee dans prompts.py")

import py_compile
py_compile.compile('/root/odyxia-droit/prompts.py', doraise=True)
print("Syntaxe OK")