#!/usr/bin/env python3
# patch_contrats_v1.py — Ajout Vague 1 : 50 nouveaux contrats OHADA

NOUVEAUX_PROMPTS = r'''

# =============================================================================
# VAGUE 1 — 50 NOUVEAUX CONTRATS OHADA
# =============================================================================

# ── BAUX ─────────────────────────────────────────────────────────────────────

def prompt_bail_habitation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de bail d'habitation conforme au droit camerounais
et aux principes OHADA de protection des parties.
Structure :
1. IDENTIFICATION DES PARTIES (bailleur et preneur)
2. DESIGNATION DES LIEUX (adresse, superficie, etat des lieux)
3. DUREE (date debut, duree, renouvellement tacite)
4. LOYER ET CHARGES (montant, modalites, revision annuelle)
5. DEPOT DE GARANTIE (montant, restitution)
6. OBLIGATIONS DU BAILLEUR (delivrance, entretien, jouissance paisible)
7. OBLIGATIONS DU PRENEUR (paiement, entretien, sous-location interdite)
8. RESILIATION (preavis, causes, procedure)
9. CLAUSE RESOLUTOIRE
10. ELECTION DE DOMICILE ET JURIDICTION COMPETENTE
--- DONNEES ---
Bailleur : {donnees.get('bailleur','')}
Preneur : {donnees.get('preneur','')}
Adresse du bien : {donnees.get('adresse','')}
Superficie : {donnees.get('superficie','')}
Loyer mensuel (FCFA) : {donnees.get('montant','')}
Depot de garantie : {donnees.get('depot_garantie','')}
Date de debut : {donnees.get('date_debut','')}
Duree : {donnees.get('duree','1 an renouvelable')}
Clauses particulieres : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_bail_commercial(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un bail commercial conforme à l'AUDCG OHADA (Art. 69-133)
et au droit camerounais applicable.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESIGNATION DES LOCAUX COMMERCIAUX
3. DESTINATION DES LIEUX (activite commerciale autorisee)
4. DUREE (minimum 2 ans selon AUDCG, renouvellement)
5. LOYER ET REVISION (indices, periode de revision)
6. CHARGES ET TRAVAUX
7. DEPOT DE GARANTIE
8. DROIT AU BAIL ET FONDS DE COMMERCE
9. OBLIGATIONS DES PARTIES
10. RESILIATION ET INDEMNITE D'EVICTION
11. CLAUSE D'ARBITRAGE OHADA
--- DONNEES ---
Bailleur : {donnees.get('bailleur','')}
Preneur : {donnees.get('preneur','')}
Adresse : {donnees.get('adresse','')}
Activite : {donnees.get('activite','')}
Loyer mensuel (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','2 ans')}
Depot de garantie : {donnees.get('depot_garantie','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_bail_emphyteotique(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un bail emphytéotique conforme au droit foncier camerounais
(Ord. 74/1 du 6 juillet 1974) et aux principes OHADA.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESIGNATION DU BIEN IMMEUBLE (titre foncier, superficie)
3. DUREE (18 a 99 ans selon droit camerounais)
4. CANON EMPHYTEOTIQUE (loyer symbolique ou reel)
5. DROITS DE L'EMPHYTEOTE (construire, ameliorer, hypothequer)
6. OBLIGATIONS DE L'EMPHYTEOTE
7. FIN DU BAIL (restitution, accession des constructions)
8. RESILIATION ANTICIPEE
--- DONNEES ---
Bailleur : {donnees.get('bailleur','')}
Emphyteote : {donnees.get('preneur','')}
Bien : {donnees.get('adresse','')}
Superficie : {donnees.get('superficie','')}
Duree : {donnees.get('duree','30 ans')}
Canon annuel (FCFA) : {donnees.get('montant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── TRAVAIL ───────────────────────────────────────────────────────────────────

def prompt_contrat_travail_cdi(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de travail à durée indéterminée (CDI) conforme
au Code du travail camerounais (Loi n°92/007 du 14 août 1992).
Structure :
1. IDENTIFICATION DES PARTIES (employeur et salarie)
2. POSTE ET FONCTIONS (description precise)
3. LIEU DE TRAVAIL
4. DATE DE PRISE D'EFFET
5. PERIODE D'ESSAI (duree selon categorie professionnelle)
6. REMUNERATION (salaire de base, primes, avantages en nature)
7. DUREE DU TRAVAIL (40h/semaine selon Code travail CM)
8. CONGES PAYES (24 jours ouvrables minimum)
9. OBLIGATIONS DU SALARIE (loyaute, confidentialite, non-concurrence)
10. OBLIGATIONS DE L'EMPLOYEUR (paiement, securite, formation)
11. RUPTURE DU CONTRAT (preavis selon anciennete et categorie)
12. CONVENTION COLLECTIVE APPLICABLE
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Salarie : {donnees.get('salarie','')}
Poste : {donnees.get('poste','')}
Salaire brut mensuel (FCFA) : {donnees.get('montant','')}
Date de debut : {donnees.get('date_debut','')}
Periode d'essai : {donnees.get('periode_essai','3 mois')}
Lieu de travail : {donnees.get('adresse','')}
Avantages : {donnees.get('avantages','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_travail_cdd(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de travail à durée déterminée (CDD) conforme
au Code du travail camerounais - Art. 25 et suivants.
Structure :
1. IDENTIFICATION DES PARTIES
2. MOTIF DU RECOURS AU CDD (travaux saisonniers, remplacement, surcroi)
3. POSTE ET FONCTIONS
4. DUREE PRECISE (dates debut et fin - maximum 2 ans renouvelable une fois)
5. REMUNERATION
6. CONDITIONS DE TRAVAIL
7. INDEMNITE DE FIN DE CONTRAT (10% de la remuneration totale brute)
8. RENOUVELLEMENT ET TRANSFORMATION EN CDI
9. RUPTURE ANTICIPEE (conditions et indemnites)
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Salarie : {donnees.get('salarie','')}
Poste : {donnees.get('poste','')}
Motif CDD : {donnees.get('motif_cdd','')}
Salaire brut mensuel (FCFA) : {donnees.get('montant','')}
Date de debut : {donnees.get('date_debut','')}
Date de fin : {donnees.get('date_fin','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_apprentissage(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat d'apprentissage conforme au Code du travail camerounais
et aux normes OHADA de formation professionnelle.
Structure :
1. IDENTIFICATION (maitre d'apprentissage et apprenti)
2. QUALIFICATION VISEE
3. DUREE (avec phases theorique et pratique)
4. REMUNERATION PROGRESSIVE
5. OBLIGATIONS DU MAITRE D'APPRENTISSAGE
6. OBLIGATIONS DE L'APPRENTI
7. CONDITIONS DE RUPTURE
8. CERTIFICAT DE FIN D'APPRENTISSAGE
--- DONNEES ---
Maitre d'apprentissage : {donnees.get('employeur','')}
Apprenti : {donnees.get('salarie','')}
Qualification visee : {donnees.get('poste','')}
Duree : {donnees.get('duree','2 ans')}
Remuneration mensuelle (FCFA) : {donnees.get('montant','')}
Date de debut : {donnees.get('date_debut','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_stage(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de stage conforme au droit camerounais,
definissant les droits et obligations des trois parties.
Structure :
1. IDENTIFICATION (stagiaire, entreprise, etablissement d'enseignement)
2. OBJET ET MISSIONS DU STAGE
3. DUREE ET HORAIRES
4. GRATIFICATION (obligatoire si stage > 2 mois)
5. ENCADREMENT (maitre de stage)
6. CONFIDENTIALITE
7. PROPRIETE INTELLECTUELLE
8. ASSURANCES
--- DONNEES ---
Entreprise : {donnees.get('employeur','')}
Stagiaire : {donnees.get('salarie','')}
Etablissement : {donnees.get('tribunal','')}
Mission : {donnees.get('poste','')}
Duree : {donnees.get('duree','')}
Gratification mensuelle (FCFA) : {donnees.get('montant','')}
Date de debut : {donnees.get('date_debut','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_lettre_licenciement_faute(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une lettre de licenciement pour faute grave conforme
au Code du travail camerounais - Art. 34 et suivants.
Structure :
1. EN-TETE (employeur, salarie, date, LRAR)
2. OBJET : Licenciement pour faute grave
3. RAPPEL DE L'ENTRETIEN PREALABLE (date)
4. EXPOSE PRECIS DES FAITS FAUTIFS (dates, circonstancies)
5. QUALIFICATION DE LA FAUTE (faute simple / grave / lourde)
6. DECISION DE LICENCIEMENT
7. DATE DE FIN DE CONTRAT (avec ou sans preavis selon faute)
8. SOLDE DE TOUT COMPTE
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Salarie : {donnees.get('salarie','')}
Poste : {donnees.get('poste','')}
Date entretien prealable : {donnees.get('date_debut','')}
Faits fautifs : {donnees.get('faits','')}
Type de faute : {donnees.get('motif_licenciement','faute grave')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_lettre_licenciement_economique(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une lettre de licenciement économique conforme
au Code du travail camerounais et aux normes OHADA.
Structure :
1. EN-TETE
2. OBJET : Licenciement pour motif economique
3. CONTEXTE ECONOMIQUE (difficultes, restructuration, suppression de poste)
4. CRITERES D'ORDRE (anciennete, charges familiales, qualifications)
5. EFFORTS DE RECLASSEMENT EFFECTUES
6. DECISION ET DATE D'EFFET
7. PREAVIS ET INDEMNITES (indemnite de licenciement selon anciennete)
8. PRIORITE DE REEMBAUCHE (1 an)
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Salarie : {donnees.get('salarie','')}
Poste : {donnees.get('poste','')}
Motif economique : {donnees.get('faits','')}
Anciennete : {donnees.get('ancienneté','')}
Salaire (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_solde_tout_compte(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un recu pour solde de tout compte conforme
au Code du travail camerounais - Art. 69 et suivants.
Structure :
1. IDENTIFICATION DES PARTIES
2. DATE ET MODE DE RUPTURE
3. DECOMPTE DETAILLE :
   - Salaires et primes dus
   - Indemnite de preavis
   - Indemnite de licenciement (si applicable)
   - Conges payes non pris
   - Autres indemnites contractuelles
4. TOTAL NET A PAYER
5. RESERVES EVENTUELLES DU SALARIE
6. DELAI DE CONTESTATION (6 mois)
--- DONNEES ---
Employeur : {donnees.get('employeur','')}
Salarie : {donnees.get('salarie','')}
Poste : {donnees.get('poste','')}
Date fin de contrat : {donnees.get('date_fin','')}
Mode de rupture : {donnees.get('motif_licenciement','')}
Salaire mensuel (FCFA) : {donnees.get('montant','')}
Anciennete : {donnees.get('ancienneté','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── SOCIETES ──────────────────────────────────────────────────────────────────

def prompt_statuts_sarl(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les statuts d'une SARL conforme à l'AUSCGIE OHADA 2014
(Art. 309 à 384) - Societe a Responsabilite Limitee.
Structure :
1. DENOMINATION SOCIALE
2. FORME JURIDIQUE (SARL)
3. OBJET SOCIAL (precis et complet)
4. SIEGE SOCIAL
5. DUREE (99 ans maximum)
6. CAPITAL SOCIAL (minimum 100 000 FCFA selon OHADA) et repartition des parts
7. GERANCE (nomination, pouvoirs, remuneration, revocation)
8. ASSEMBLEES DES ASSOCIES (AGO, AGE, convocation, quorum, vote)
9. EXERCICE SOCIAL ET COMPTES
10. REPARTITION DES BENEFICES
11. DISSOLUTION ET LIQUIDATION
12. CONTESTATIONS (arbitrage CCJA ou juridiction competente)
--- DONNEES ---
Denomination : {donnees.get('societe','')}
Objet social : {donnees.get('objet','')}
Siege social : {donnees.get('adresse','')}
Capital social (FCFA) : {donnees.get('capital','')}
Associes et parts : {donnees.get('creancier','')}
Gerant(s) : {donnees.get('requérant','')}
Clauses : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_statuts_sa(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les statuts d'une SA conforme à l'AUSCGIE OHADA 2014
(Art. 385 à 853) - Societe Anonyme avec ou sans conseil d'administration.
Structure :
1. DENOMINATION, FORME, OBJET, SIEGE, DUREE
2. CAPITAL SOCIAL (minimum 10 000 000 FCFA) et actions
3. LIBERATION DES ACTIONS
4. ADMINISTRATION (CA ou Administrateur General selon forme)
5. DIRECTION GENERALE
6. ASSEMBLEES GENERALES (AGO, AGE)
7. COMMISSAIRES AUX COMPTES
8. EXERCICE SOCIAL ET AFFECTATION DES RESULTATS
9. DISSOLUTION ET LIQUIDATION
--- DONNEES ---
Denomination : {donnees.get('societe','')}
Objet social : {donnees.get('objet','')}
Siege : {donnees.get('adresse','')}
Capital (FCFA) : {donnees.get('capital','')}
Actionnaires : {donnees.get('creancier','')}
Forme : {donnees.get('faits','avec Conseil d Administration')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_statuts_snc(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les statuts d'une SNC conforme à l'AUSCGIE OHADA 2014
(Art. 270 à 308) - Societe en Nom Collectif.
Structure :
1. DENOMINATION, OBJET, SIEGE, DUREE
2. CAPITAL ET PARTS SOCIALES (responsabilite solidaire et indefinie)
3. GERANCE
4. DECISIONS COLLECTIVES
5. CESSION DE PARTS (agrement obligatoire)
6. DISSOLUTION
--- DONNEES ---
Denomination : {donnees.get('societe','')}
Objet : {donnees.get('objet','')}
Siege : {donnees.get('adresse','')}
Capital (FCFA) : {donnees.get('capital','')}
Associes : {donnees.get('creancier','')}
Gerant : {donnees.get('requérant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_statuts_gie(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les statuts d'un GIE conforme à l'AUSCGIE OHADA 2014
(Art. 869 à 885) - Groupement d'Interet Economique.
Structure :
1. DENOMINATION, OBJET ECONOMIQUE, SIEGE, DUREE
2. MEMBRES (personnes physiques ou morales)
3. ADMINISTRATION (gerant, pouvoirs)
4. DECISIONS
5. CONTRIBUTIONS DES MEMBRES
6. RESPONSABILITE (solidaire et indefinie)
7. DISSOLUTION
--- DONNEES ---
Denomination GIE : {donnees.get('societe','')}
Objet : {donnees.get('objet','')}
Membres : {donnees.get('creancier','')}
Siege : {donnees.get('adresse','')}
Gerant : {donnees.get('requérant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_pv_ago(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un procès-verbal d'Assemblée Générale Ordinaire conforme
à l'AUSCGIE OHADA 2014 - reunion annuelle obligatoire.
Structure :
1. EN-TETE (societe, date, lieu, heure)
2. LISTE DES PRESENTS ET REPRESENTES (feuille de presence)
3. BUREAU DE SEANCE (president, secretaire, scrutateurs)
4. QUORUM ET OUVERTURE
5. ORDRE DU JOUR
6. RESOLUTIONS SOUMISES ET VOTES
7. CLOTURE DE SEANCE
--- DONNEES ---
Societe : {donnees.get('societe','')}
Date AG : {donnees.get('date_debut','')}
Lieu : {donnees.get('adresse','')}
Associes presents : {donnees.get('creancier','')}
Resolutions : {donnees.get('faits','')}
Resultat exercice (FCFA) : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_pv_age(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un procès-verbal d'Assemblée Générale Extraordinaire conforme
à l'AUSCGIE OHADA 2014 - modifications statutaires.
Structure :
1. EN-TETE ET CONVOCATION REGULIERE
2. FEUILLE DE PRESENCE ET QUORUM (2/3 des droits de vote selon OHADA)
3. BUREAU DE SEANCE
4. OBJET DE L'AGE
5. RESOLUTIONS EXTRAORDINAIRES
6. VOTE ET RESULTATS
7. CLOTURE
--- DONNEES ---
Societe : {donnees.get('societe','')}
Date AGE : {donnees.get('date_debut','')}
Lieu : {donnees.get('adresse','')}
Objet des modifications : {donnees.get('faits','')}
Associes presents : {donnees.get('creancier','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_cession_parts_sarl(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de cession de parts sociales de SARL conforme
à l'AUSCGIE OHADA 2014 - Art. 317 à 330.
Structure :
1. IDENTIFICATION DES PARTIES (cedant et cessionnaire)
2. DESIGNATION DE LA SOCIETE
3. PARTS CEDEES (nombre, numeros, valeur nominale)
4. PRIX DE CESSION ET MODALITES DE PAIEMENT
5. AGREMENT DES ASSOCIES (PV d'agrement joint)
6. GARANTIES DU CEDANT
7. DATE DE PRISE D'EFFET
8. ENREGISTREMENT ET PUBLICITE (RCCM)
--- DONNEES ---
Cedant : {donnees.get('requérant','')}
Cessionnaire : {donnees.get('adversaire','')}
Societe : {donnees.get('societe','')}
Parts cedees : {donnees.get('objet','')}
Prix de cession (FCFA) : {donnees.get('montant','')}
Date : {donnees.get('date_debut','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_pacte_actionnaires(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un pacte d'actionnaires/associes conforme au droit OHADA,
organisant les relations entre actionnaires en dehors des statuts.
Structure :
1. IDENTIFICATION DES PARTIES ET DE LA SOCIETE
2. OBJET DU PACTE
3. DROITS DE PREEMPTION (priorite d'achat)
4. DROIT DE SORTIE CONJOINTE (tag-along)
5. DROIT D'ENTRAINEMENT (drag-along)
6. INALIENERABILITE TEMPORAIRE
7. GOUVERNANCE ET NOMINATIONS
8. DIVIDENDES ET POLITIQUE FINANCIERE
9. CONFIDENTIALITE
10. DUREE ET RESILIATION
11. CLAUSE D'ARBITRAGE
--- DONNEES ---
Societe : {donnees.get('societe','')}
Actionnaires signataires : {donnees.get('creancier','')}
Capital concerne : {donnees.get('capital','')}
Clauses specifiques : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── RECOUVREMENT ET SURETES ───────────────────────────────────────────────────

def prompt_reconnaissance_dette(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une reconnaissance de dette conforme au droit camerounais
et à l'AUPSRVE OHADA, à valeur probatoire maximale.
Structure :
1. IDENTIFICATION COMPLETE DES PARTIES
2. RECONNAISSANCE DE LA DETTE (montant en lettres et en chiffres)
3. ORIGINE DE LA DETTE (contrat, pret, prestation)
4. MODALITES DE REMBOURSEMENT (date unique ou echeancier)
5. TAUX D'INTERET (legal ou conventionnel)
6. CLAUSE PENALE (en cas de defaut)
7. SOLIDARITE (si plusieurs debiteurs)
8. DATE ET SIGNATURES LEGALISEES
--- DONNEES ---
Creancier : {donnees.get('creancier','')}
Debiteur : {donnees.get('debiteur','')}
Montant (FCFA) : {donnees.get('montant','')}
Origine : {donnees.get('nature_creance','')}
Date d'exigibilite : {donnees.get('date_exigibilite','')}
Modalites : {donnees.get('faits','paiement en une fois')}
Interets : {donnees.get('suretes','taux legal')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_cautionnement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de cautionnement conforme à l'AUS OHADA 2010
(Art. 13 à 55) - surete personnelle.
Structure :
1. IDENTIFICATION (creancier, debiteur principal, caution)
2. OBLIGATION GARANTIE (montant, nature, duree)
3. ETENDUE DU CAUTIONNEMENT (simple ou solidaire)
4. MENTIONS MANUSCRITES OBLIGATOIRES AUS
5. BENEFICE DE DISCUSSION ET DE DIVISION
6. DUREE DU CAUTIONNEMENT
7. RECOURS DE LA CAUTION CONTRE LE DEBITEUR
8. EXTINCTION
--- DONNEES ---
Creancier : {donnees.get('creancier','')}
Debiteur principal : {donnees.get('debiteur','')}
Caution : {donnees.get('requérant','')}
Montant garanti (FCFA) : {donnees.get('montant','')}
Type (simple/solidaire) : {donnees.get('faits','solidaire')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_nantissement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de nantissement conforme à l'AUS OHADA 2010
(Art. 92 à 146) - surete sur bien meuble incorporel.
Structure :
1. IDENTIFICATION DES PARTIES
2. BIEN NANTI (fonds de commerce, parts sociales, creance, marque)
3. CREANCE GARANTIE (montant, echeance)
4. FORMALITES DE PUBLICITE (RCCM pour fonds de commerce)
5. DROITS DU CREANCIER NANTI
6. OBLIGATIONS DU CONSTITUANT
7. REALISATION EN CAS DE DEFAUT
--- DONNEES ---
Creancier : {donnees.get('creancier','')}
Constituant : {donnees.get('debiteur','')}
Bien nanti : {donnees.get('nature_creance','')}
Montant garanti (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_echeancier_paiement(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord de paiement echelonne conforme au droit OHADA,
evitant le recours aux voies d'execution.
Structure :
1. IDENTIFICATION DES PARTIES
2. MONTANT TOTAL DE LA DETTE
3. ECHEANCIER DETAILLE (dates et montants)
4. INTERETS EVENTUELS
5. CLAUSE RESOLUTOIRE (defaut de paiement d'une echeance)
6. RENONCIATION TEMPORAIRE AUX POURSUITES
7. TITRE EXECUTOIRE EN CAS DE DEFAUT
--- DONNEES ---
Creancier : {donnees.get('creancier','')}
Debiteur : {donnees.get('debiteur','')}
Montant total (FCFA) : {donnees.get('montant','')}
Nombre d'echeances : {donnees.get('duree','')}
Premiere echeance : {donnees.get('date_exigibilite','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── PRESTATIONS ET COMMERCE ───────────────────────────────────────────────────

def prompt_contrat_prestation_services(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de prestation de services conforme au droit OHADA
et au droit camerounais applicable.
Structure :
1. IDENTIFICATION DES PARTIES (prestataire et client)
2. OBJET DES PRESTATIONS (description precise)
3. DUREE ET CALENDRIER D'EXECUTION
4. PRIX ET MODALITES DE PAIEMENT
5. OBLIGATIONS DU PRESTATAIRE
6. OBLIGATIONS DU CLIENT
7. PROPRIETE INTELLECTUELLE (des livrables)
8. CONFIDENTIALITE
9. RESPONSABILITE ET ASSURANCE
10. RESILIATION
11. FORCE MAJEURE
12. JURIDICTION COMPETENTE
--- DONNEES ---
Prestataire : {donnees.get('requérant','')}
Client : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Prix (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Modalites de paiement : {donnees.get('nature_creance','')}
Faits/clauses : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_conseil(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de conseil juridique/strategique conforme
au droit OHADA et aux regles deontologiques du barreau camerounais.
Structure :
1. IDENTIFICATION DES PARTIES
2. MISSION DE CONSEIL (perimetre precis)
3. HONORAIRES (forfait, vacation horaire, success fee)
4. MODALITES D'INTERVENTION
5. OBLIGATIONS DU CONSEILLER (diligence, confidentialite, independance)
6. OBLIGATIONS DU CLIENT (cooperation, paiement)
7. CONFLITS D'INTERETS
8. RESILIATION
9. JURIDICTION
--- DONNEES ---
Conseil : {donnees.get('requérant','')}
Client : {donnees.get('adversaire','')}
Mission : {donnees.get('objet','')}
Honoraires (FCFA) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_sous_traitance(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de sous-traitance conforme au droit OHADA
et au droit camerounais des marches.
Structure :
1. IDENTIFICATION (entrepreneur principal et sous-traitant)
2. MARCHE PRINCIPAL (reference)
3. TRAVAUX SOUS-TRAITES (description precise)
4. PRIX ET PAIEMENTS (alignes sur marche principal)
5. DELAIS ET PENALITES
6. AGREATION PAR LE MAITRE D'OUVRAGE
7. RESPONSABILITES ET ASSURANCES
8. RESILIATION
--- DONNEES ---
Entrepreneur principal : {donnees.get('requérant','')}
Sous-traitant : {donnees.get('adversaire','')}
Travaux : {donnees.get('objet','')}
Montant (FCFA) : {donnees.get('montant','')}
Delai : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_partenariat(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de partenariat commercial conforme au droit OHADA,
organisant la collaboration entre deux entites.
Structure :
1. IDENTIFICATION DES PARTENAIRES
2. OBJET DU PARTENARIAT
3. APPORTS DE CHAQUE PARTIE
4. GOUVERNANCE ET COMITE DE PILOTAGE
5. PARTAGE DES REVENUS
6. PROPRIETE INTELLECTUELLE COMMUNE
7. EXCLUSIVITE (si applicable)
8. CONFIDENTIALITE
9. DUREE ET RENOUVELLEMENT
10. RESILIATION ET EFFETS
--- DONNEES ---
Partenaire A : {donnees.get('requérant','')}
Partenaire B : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Apports : {donnees.get('faits','')}
Partage revenus : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_accord_confidentialite(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un accord de confidentialite (NDA) conforme au droit OHADA
et au droit camerounais - protégeant les informations sensibles.
Structure :
1. IDENTIFICATION DES PARTIES
2. DEFINITION DES INFORMATIONS CONFIDENTIELLES
3. OBLIGATIONS DE CONFIDENTIALITE
4. EXCLUSIONS (informations deja publiques)
5. DUREE DE LA CONFIDENTIALITE
6. SANCTIONS EN CAS DE VIOLATION
7. RETOUR DES INFORMATIONS
8. JURIDICTION
--- DONNEES ---
Partie divulgatrice : {donnees.get('requérant','')}
Partie receptrice : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','informations commerciales et techniques')}
Duree de confidentialite : {donnees.get('duree','5 ans')}
Sanctions : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_protocole_accord_mou(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un protocole d'accord (MOU) conforme au droit OHADA
- accord preliminaire entre parties.
Structure :
1. IDENTIFICATION DES PARTIES
2. CONTEXTE ET OBJECTIFS
3. ENGAGEMENTS DE CHAQUE PARTIE
4. CALENDRIER DE MISE EN OEUVRE
5. NATURE JURIDIQUE (contraignant ou declaration d'intention)
6. CONFIDENTIALITE
7. DUREE
8. NEGOTIATION DE BONNE FOI
--- DONNEES ---
Partie A : {donnees.get('requérant','')}
Partie B : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Engagements : {donnees.get('faits','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_lettre_intention(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une lettre d'intention conforme au droit OHADA
- document precontractuel engageant les negotiations.
Structure :
1. EN-TETE
2. OBJET DE L'INTENTION (acquisition, partenariat, investissement)
3. TERMES ENVISAGES (prix indicatif, conditions)
4. DUE DILIGENCE PREVUE
5. EXCLUSIVITE DE NEGOCIATION (si applicable)
6. CONFIDENTIALITE
7. CALENDRIER
8. CARACTERE NON CONTRAIGNANT (sauf clauses specifiques)
--- DONNEES ---
Emetteur : {donnees.get('requérant','')}
Destinataire : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Prix indicatif (FCFA) : {donnees.get('montant','')}
Conditions : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_agence_commerciale(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat d'agent commercial conforme à l'AUDCG OHADA 2010
(Art. 169 à 196) - mandat d'interet commun.
Structure :
1. IDENTIFICATION (mandant et agent)
2. TERRITOIRE ET CLIENTELE CONFIES
3. PRODUITS OU SERVICES REPRESENTES
4. EXCLUSIVITE (si accordee)
5. COMMISSIONS (taux, base de calcul, paiement)
6. OBLIGATIONS DE L'AGENT
7. OBLIGATIONS DU MANDANT
8. DUREE ET RESILIATION
9. INDEMNITE DE FIN DE CONTRAT (Art. 194 AUDCG)
--- DONNEES ---
Mandant : {donnees.get('requérant','')}
Agent commercial : {donnees.get('adversaire','')}
Produits/services : {donnees.get('objet','')}
Territoire : {donnees.get('adresse','')}
Commission (%) : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_franchise(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de franchise conforme au droit OHADA et OAPI
- transmission d'un savoir-faire et d'une marque.
Structure :
1. IDENTIFICATION (franchiseur et franchise)
2. OBJET (concept, marque, savoir-faire)
3. TERRITOIRE EXCLUSIF
4. DROIT D'ENTREE
5. REDEVANCES (royalties sur CA)
6. FORMATION ET ASSISTANCE
7. NORMES ET STANDARDS A RESPECTER
8. APPROVISIONNEMENT
9. DUREE ET RENOUVELLEMENT
10. RESILIATION ET EFFETS
11. NON-CONCURRENCE POST-CONTRACTUELLE
--- DONNEES ---
Franchiseur : {donnees.get('requérant','')}
Franchise : {donnees.get('adversaire','')}
Concept : {donnees.get('objet','')}
Territoire : {donnees.get('adresse','')}
Droit d'entree (FCFA) : {donnees.get('montant','')}
Redevance (%) : {donnees.get('nature_creance','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_distribution(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de distribution exclusive conforme à l'AUDCG OHADA
- organisation du reseau de vente.
Structure :
1. IDENTIFICATION (fournisseur et distributeur)
2. PRODUITS DISTRIBUES
3. TERRITOIRE EXCLUSIF
4. OBJECTIFS DE VENTE (minima contractuels)
5. CONDITIONS D'ACHAT ET PRIX
6. PUBLICITE ET PROMOTION
7. OBLIGATIONS DU DISTRIBUTEUR
8. OBLIGATIONS DU FOURNISSEUR
9. DUREE ET RESILIATION
--- DONNEES ---
Fournisseur : {donnees.get('requérant','')}
Distributeur : {donnees.get('adversaire','')}
Produits : {donnees.get('objet','')}
Territoire : {donnees.get('adresse','')}
Conditions : {donnees.get('faits','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── IMMOBILIER ────────────────────────────────────────────────────────────────

def prompt_promesse_vente_immobiliere(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une promesse de vente immobilière (compromis de vente)
conforme au droit foncier camerounais - Ord. 74/1 et loi 80/22.
Structure :
1. IDENTIFICATION DES PARTIES (promettant vendeur et beneficiaire)
2. DESIGNATION DU BIEN (titre foncier, superficie, description)
3. PRIX DE VENTE ET MODALITES
4. INDEMNITE D'IMMOBILISATION
5. CONDITIONS SUSPENSIVES (financement, purge hypotheques)
6. DELAI DE REALISATION
7. ETAT DES LIEUX ET SERVITUDES
8. FRAIS ET TAXES
9. CLAUSES PENALES
--- DONNEES ---
Vendeur : {donnees.get('requérant','')}
Acquereur : {donnees.get('adversaire','')}
Bien : {donnees.get('adresse','')}
Prix (FCFA) : {donnees.get('montant','')}
Indemnite d'immobilisation : {donnees.get('depot_garantie','')}
Delai de realisation : {donnees.get('duree','')}
Conditions : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_cession_fonds_commerce(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de cession de fonds de commerce conforme
à l'AUDCG OHADA 2010 - Art. 149 à 168.
Structure :
1. IDENTIFICATION DES PARTIES
2. DESIGNATION DU FONDS (elements incorporels et corporels)
3. PRIX GLOBAL ET VENTILATION (clientele, materiel, stock, bail)
4. MODALITES DE PAIEMENT
5. GARANTIES (privilege du vendeur, nantissement)
6. CLAUSE DE NON-CONCURRENCE
7. PURGE DES INSCRIPTIONS
8. TRANSFERT DU BAIL COMMERCIAL
9. ENREGISTREMENT ET PUBLICITE RCCM
--- DONNEES ---
Vendeur : {donnees.get('requérant','')}
Acquereur : {donnees.get('adversaire','')}
Fonds : {donnees.get('objet','')}
Adresse : {donnees.get('adresse','')}
Prix global (FCFA) : {donnees.get('montant','')}
Non-concurrence : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── PRET ET FINANCEMENT ───────────────────────────────────────────────────────

def prompt_contrat_pret(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de prêt conforme au droit camerounais et OHADA
- pret entre particuliers ou entre entreprises.
Structure :
1. IDENTIFICATION DES PARTIES (preteur et emprunteur)
2. MONTANT DU PRET
3. TAUX D'INTERET (legal ou conventionnel - respecter usure)
4. MODALITES DE REMBOURSEMENT (tableau d'amortissement)
5. GARANTIES (caution, hypotheque, nantissement)
6. DEFAUT DE PAIEMENT ET CLAUSE PENALE
7. ANTICIPATION DE REMBOURSEMENT
8. ATTRIBUTION DE JURIDICTION
--- DONNEES ---
Preteur : {donnees.get('creancier','')}
Emprunteur : {donnees.get('debiteur','')}
Montant (FCFA) : {donnees.get('montant','')}
Taux d'interet : {donnees.get('suretes','taux legal')}
Duree : {donnees.get('duree','')}
Remboursement : {donnees.get('faits','mensuel')}
Garanties : {donnees.get('nature_creance','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── FAMILLE ───────────────────────────────────────────────────────────────────

def prompt_contrat_mariage_communaute(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de mariage sous le régime de la communauté
conforme au Code civil camerounais applicable.
Structure :
1. IDENTIFICATION DES FUTURS EPOUX
2. REGIME MATRIMONIAL CHOISI (communaute reduite aux acquets)
3. BIENS PROPRES DE CHAQUE EPOUX
4. BIENS COMMUNS (acquets)
5. GESTION DES BIENS COMMUNS
6. DETTES (propres et communes)
7. DISSOLUTION (divorce, deces)
8. LIQUIDATION ET PARTAGE
--- DONNEES ---
Epoux A : {donnees.get('requérant','')}
Epoux B : {donnees.get('adversaire','')}
Date mariage prevue : {donnees.get('date_debut','')}
Biens propres epoux A : {donnees.get('faits','')}
Biens propres epoux B : {donnees.get('objet','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_mariage_separation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de mariage sous le régime de la séparation de biens
conforme au Code civil camerounais.
Structure :
1. IDENTIFICATION DES FUTURS EPOUX
2. REGIME DE SEPARATION DE BIENS
3. BIENS DE CHAQUE EPOUX (restent personnels)
4. CONTRIBUTION AUX CHARGES DU MARIAGE
5. GESTION INDEPENDANTE DES BIENS
6. DETTES (chaque epoux repond de ses propres dettes)
7. PREUVE DE LA PROPRIETE
--- DONNEES ---
Epoux A : {donnees.get('requérant','')}
Epoux B : {donnees.get('adversaire','')}
Date mariage : {donnees.get('date_debut','')}
Contribution charges : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_convention_divorce(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de divorce par consentement mutuel
conforme au Code civil et a la procedure camerounaise.
Structure :
1. IDENTIFICATION DES EPOUX
2. ACCORD SUR LE PRINCIPE DU DIVORCE
3. LIQUIDATION DU REGIME MATRIMONIAL
4. RESIDENCE ET GARDE DES ENFANTS
5. DROIT DE VISITE ET D'HEBERGEMENT
6. PENSION ALIMENTAIRE POUR LES ENFANTS
7. PRESTATION COMPENSATOIRE (si applicable)
8. SORT DU DOMICILE CONJUGAL
9. ENGAGEMENT DE NON-RECOURS ULTERIEUR
--- DONNEES ---
Epoux : {donnees.get('requérant','')}
Epouse : {donnees.get('adversaire','')}
Enfants : {donnees.get('objet','')}
Garde : {donnees.get('faits','')}
Pension alimentaire (FCFA/mois) : {donnees.get('montant','')}
Domicile conjugal : {donnees.get('adresse','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── ASSURANCES CIMA ───────────────────────────────────────────────────────────

def prompt_contrat_assurance_vie(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les conditions particulieres d'un contrat d'assurance vie
conforme au Code CIMA.
Structure :
1. IDENTIFICATION (assureur, souscripteur, assure, beneficiaire)
2. GARANTIES SOUSCRITES (deces, invalidite, rente)
3. CAPITAL ASSURE
4. PRIME (montant, periodicite)
5. DUREE DU CONTRAT
6. CLAUSE BENEFICIAIRE
7. VALEUR DE RACHAT
8. EXCLUSIONS
9. PRESCRIPTION BIENNALE CIMA
--- DONNEES ---
Souscripteur : {donnees.get('requérant','')}
Assure : {donnees.get('adversaire','')}
Beneficiaire : {donnees.get('creancier','')}
Capital assure (FCFA) : {donnees.get('montant','')}
Prime mensuelle (FCFA) : {donnees.get('nature_creance','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_contrat_assurance_rc(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras les conditions particulieres d'un contrat d'assurance
responsabilite civile professionnelle conforme au Code CIMA.
Structure :
1. IDENTIFICATION (assureur et assure)
2. ACTIVITE PROFESSIONNELLE COUVERTE
3. GARANTIES RC (dommages corporels, materiels, immaterialels)
4. PLAFONDS DE GARANTIE
5. FRANCHISE
6. PRIME ET PAIEMENT
7. EXCLUSIONS
8. DECLARATION DE SINISTRE (delai 5 jours Code CIMA)
--- DONNEES ---
Assure : {donnees.get('requérant','')}
Activite : {donnees.get('objet','')}
Plafond de garantie (FCFA) : {donnees.get('montant','')}
Franchise (FCFA) : {donnees.get('suretes','')}
Prime annuelle (FCFA) : {donnees.get('nature_creance','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── NUMERIQUE ─────────────────────────────────────────────────────────────────

def prompt_contrat_developpement_logiciel(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de développement logiciel conforme au droit OHADA
et aux regles de propriete intellectuelle OAPI.
Structure :
1. IDENTIFICATION DES PARTIES
2. OBJET (cahier des charges resume)
3. SPECIFICATIONS TECHNIQUES
4. PLANNING ET JALONS
5. RECETTE ET TESTS D'ACCEPTATION
6. PRIX ET MODALITES DE PAIEMENT (par jalons)
7. PROPRIETE DU CODE SOURCE
8. MAINTENANCE GARANTIE (duree)
9. CONFIDENTIALITE
10. PENALITES DE RETARD
11. RESILIATION
--- DONNEES ---
Prestataire : {donnees.get('requérant','')}
Client : {donnees.get('adversaire','')}
Objet : {donnees.get('objet','')}
Budget total (FCFA) : {donnees.get('montant','')}
Delai de livraison : {donnees.get('duree','')}
Jalons : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_cgu(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras des Conditions Générales d'Utilisation (CGU) conformes
au droit camerounais du numerique et aux standards OHADA.
Structure :
1. IDENTIFICATION DE L'EDITEUR
2. OBJET DES CGU
3. ACCES AU SERVICE
4. COMPTE UTILISATEUR ET RESPONSABILITES
5. PROPRIETE INTELLECTUELLE
6. DONNEES PERSONNELLES (conformite loi camerounaise)
7. CONTENU INTERDIT
8. RESPONSABILITE LIMITEE DE L'EDITEUR
9. MODIFICATION DES CGU
10. DUREE ET RESILIATION
11. DROIT APPLICABLE ET JURIDICTION
--- DONNEES ---
Editeur : {donnees.get('requérant','')}
Service : {donnees.get('objet','')}
Site web : {donnees.get('adresse','')}
Email contact : {donnees.get('adversaire','')}
Faits/clauses : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_politique_confidentialite(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une politique de confidentialite conforme à la loi camerounaise
sur les donnees personnelles et aux standards internationaux.
Structure :
1. RESPONSABLE DU TRAITEMENT
2. DONNEES COLLECTEES (types, finalites)
3. BASE LEGALE DU TRAITEMENT
4. DUREE DE CONSERVATION
5. DESTINATAIRES DES DONNEES
6. TRANSFERTS INTERNATIONAUX
7. DROITS DES PERSONNES (acces, rectification, effacement)
8. SECURITE DES DONNEES
9. COOKIES
10. CONTACT DPO
--- DONNEES ---
Societe : {donnees.get('requérant','')}
Service : {donnees.get('objet','')}
Email DPO : {donnees.get('adversaire','')}
Donnees collectees : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── PROCURATIONS ──────────────────────────────────────────────────────────────

def prompt_procuration_generale(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une procuration générale conforme au droit camerounais
- mandat large conferant des pouvoirs etendus.
Structure :
1. IDENTIFICATION DU MANDANT
2. IDENTIFICATION DU MANDATAIRE
3. ETENDUE DES POUVOIRS (actes d'administration et de disposition)
4. DUREE (illimitee ou limitee)
5. REVOCATION
6. DATE ET SIGNATURE LEGALISEE
--- DONNEES ---
Mandant : {donnees.get('requérant','')}
Mandataire : {donnees.get('adversaire','')}
Pouvoirs : {donnees.get('faits','tous pouvoirs generaux')}
Duree : {donnees.get('duree','indeterminee')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_procuration_speciale(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une procuration spéciale conforme au droit camerounais
- mandat limite a un acte ou une mission precise.
Structure :
1. IDENTIFICATION DU MANDANT
2. IDENTIFICATION DU MANDATAIRE
3. MISSION PRECISE ET LIMITATIVE
4. POUVOIRS CONFERES (liste exhaustive)
5. DUREE LIMITEE
6. DATE ET SIGNATURE LEGALISEE
--- DONNEES ---
Mandant : {donnees.get('requérant','')}
Mandataire : {donnees.get('adversaire','')}
Mission : {donnees.get('objet','')}
Duree : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── OAPI ──────────────────────────────────────────────────────────────────────

def prompt_cession_marque(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de cession de marque conforme à l'Accord de Bangui
(OAPI revise 2015) - transfert de propriete d'une marque enregistree.
Structure :
1. IDENTIFICATION DES PARTIES (cedant et cessionnaire)
2. DESIGNATION DE LA MARQUE (numero OAPI, classes, pays)
3. PRIX DE CESSION
4. GARANTIE D'EVICTION
5. CLAUSE DE NON-CONCURRENCE
6. INSCRIPTION AU REGISTRE OAPI
7. FRAIS D'ENREGISTREMENT
--- DONNEES ---
Cedant : {donnees.get('requérant','')}
Cessionnaire : {donnees.get('adversaire','')}
Marque : {donnees.get('objet','')}
Numero OAPI : {donnees.get('reference_jugement','')}
Prix (FCFA) : {donnees.get('montant','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_licence_marque(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de licence de marque conforme à l'Accord de Bangui
OAPI - autorisation d'exploitation sans transfert de propriete.
Structure :
1. IDENTIFICATION (concedant et licence)
2. MARQUE LICENCIEE (numero OAPI, classes)
3. TERRITOIRE ET EXCLUSIVITE
4. REDEVANCES (montant ou %)
5. OBLIGATIONS DE QUALITE
6. DUREE ET RENOUVELLEMENT
7. CONTROLE D'USAGE
8. RESILIATION
--- DONNEES ---
Concedant : {donnees.get('requérant','')}
Licence : {donnees.get('adversaire','')}
Marque : {donnees.get('objet','')}
Territoire : {donnees.get('adresse','')}
Redevance : {donnees.get('montant','')}
Duree : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── TRANSPORT OHADA ───────────────────────────────────────────────────────────

def prompt_contrat_transport_marchandises(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de transport de marchandises par route conforme
à l'AUCTMR OHADA 2003.
Structure :
1. IDENTIFICATION (expediteur, transporteur, destinataire)
2. DESIGNATION DES MARCHANDISES (nature, quantite, poids)
3. LIEU DE PRISE EN CHARGE ET DE LIVRAISON
4. DELAI DE LIVRAISON
5. PRIX ET MODALITES DE PAIEMENT
6. RESPONSABILITE DU TRANSPORTEUR (Art. 17 AUCTMR)
7. DECLARATION DE VALEUR
8. ASSURANCE DES MARCHANDISES
9. RECLAMATIONS ET DELAIS
--- DONNEES ---
Expediteur : {donnees.get('requérant','')}
Transporteur : {donnees.get('adversaire','')}
Destinataire : {donnees.get('debiteur','')}
Marchandises : {donnees.get('objet','')}
Trajet : {donnees.get('adresse','')}
Prix (FCFA) : {donnees.get('montant','')}
Delai : {donnees.get('duree','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── MEDIATION ET ARBITRAGE ────────────────────────────────────────────────────

def prompt_clause_arbitrage(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une clause compromissoire d'arbitrage OHADA conforme
à l'AUDA 2017 et au Reglement CCJA 2017.
Structure :
1. IDENTIFICATION DES PARTIES
2. CONTRAT DE REFERENCE
3. CLAUSE D'ARBITRAGE (formule complete)
4. CENTRE D'ARBITRAGE (CCJA ou centre national)
5. NOMBRE D'ARBITRES (1 ou 3)
6. LANGUE DE LA PROCEDURE
7. SIEGE DE L'ARBITRAGE
8. DROIT APPLICABLE AU FOND
--- DONNEES ---
Partie A : {donnees.get('requérant','')}
Partie B : {donnees.get('adversaire','')}
Contrat : {donnees.get('objet','')}
Centre d'arbitrage : {donnees.get('faits','CCJA OHADA')}
Siege : {donnees.get('adresse','Abidjan')}
Langue : {donnees.get('duree','francais')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_convention_mediation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras une convention de médiation conforme à l'AUM OHADA 2017
- accord de recourir a la mediation avant tout litige.
Structure :
1. IDENTIFICATION DES PARTIES
2. LITIGE VISE (ou clause generale)
3. CHOIX DU MEDIATEUR OU DU CENTRE
4. PROCEDURE DE MEDIATION
5. CONFIDENTIALITE
6. FRAIS DE MEDIATION
7. DUREE DE LA MEDIATION
8. EFFETS DE L'ACCORD DE MEDIATION
--- DONNEES ---
Partie A : {donnees.get('requérant','')}
Partie B : {donnees.get('adversaire','')}
Objet du litige : {donnees.get('objet','')}
Mediateur/Centre : {donnees.get('faits','')}
Montant en litige : {donnees.get('montant','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

# ── DROIT PUBLIC ──────────────────────────────────────────────────────────────

def prompt_marche_public_travaux(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un contrat de marché public de travaux conforme
au Code des Marches Publics camerounais et aux normes OHADA.
Structure :
1. IDENTIFICATION (maitre d'ouvrage et entreprise)
2. OBJET DES TRAVAUX
3. DOCUMENTS CONTRACTUELS (CCAP, CCTP, DPGF)
4. PRIX ET MODALITES DE REGLEMENT
5. DELAI D'EXECUTION ET PENALITES
6. GARANTIES (retenue de garantie, caution de bonne fin)
7. ASSURANCES
8. RECEPTION DES TRAVAUX
9. RESILIATION
--- DONNEES ---
Maitre d'ouvrage : {donnees.get('requérant','')}
Entreprise : {donnees.get('adversaire','')}
Objet travaux : {donnees.get('objet','')}
Montant (FCFA) : {donnees.get('montant','')}
Delai : {donnees.get('duree','')}
Faits : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""

def prompt_donation(donnees: dict, contexte: str) -> str:
    return f"""{IDENTITE_ODYXIA}
Tu rédigeras un acte de donation conforme au Code civil camerounais
applicable et au droit OHADA des liberalites.
Structure :
1. IDENTIFICATION DU DONATEUR ET DU DONATAIRE
2. DESIGNATION DU BIEN DONNE
3. VALEUR DU BIEN
4. ACCEPTATION EXPRESSE DU DONATAIRE
5. CHARGES EVENTUELLES
6. RESERVE D'USUFRUIT (si applicable)
7. RAPPORT A SUCCESSION
8. ENREGISTREMENT ET PUBLICITE
--- DONNEES ---
Donateur : {donnees.get('requérant','')}
Donataire : {donnees.get('adversaire','')}
Bien donne : {donnees.get('objet','')}
Valeur (FCFA) : {donnees.get('montant','')}
Charges : {donnees.get('faits','')}
--- CONTEXTE DOCUMENTAIRE ---
{contexte}
"""
'''

NOUVELLES_ENTREES = """
PROMPTS_REDACTION.update({
    "bail_habitation": {"nom": "Contrat de bail d'habitation", "description": "Bail residentiel conforme droit camerounais", "champs": ["bailleur","preneur","adresse","superficie","montant","depot_garantie","date_debut","duree","faits"], "fn": prompt_bail_habitation},
    "bail_commercial": {"nom": "Contrat de bail commercial", "description": "Art. 69-133 AUDCG OHADA - locaux commerciaux", "champs": ["bailleur","preneur","adresse","activite","montant","depot_garantie","duree","faits"], "fn": prompt_bail_commercial},
    "bail_emphyteotique": {"nom": "Bail emphyteotique", "description": "18 a 99 ans - Ord. 74/1 droit foncier camerounais", "champs": ["bailleur","preneur","adresse","superficie","duree","montant","faits"], "fn": prompt_bail_emphyteotique},
    "contrat_travail_cdi": {"nom": "Contrat de travail CDI", "description": "Duree indeterminee - Code travail Cameroun Art. 24+", "champs": ["employeur","salarie","poste","montant","date_debut","periode_essai","adresse","avantages","faits"], "fn": prompt_contrat_travail_cdi},
    "contrat_travail_cdd": {"nom": "Contrat de travail CDD", "description": "Duree determinee - Max 2 ans - Code travail CM Art. 25+", "champs": ["employeur","salarie","poste","motif_cdd","montant","date_debut","date_fin","faits"], "fn": prompt_contrat_travail_cdd},
    "contrat_apprentissage": {"nom": "Contrat d'apprentissage", "description": "Formation professionnelle - Code travail camerounais", "champs": ["employeur","salarie","poste","duree","montant","date_debut","faits"], "fn": prompt_contrat_apprentissage},
    "contrat_stage": {"nom": "Convention de stage", "description": "Tripartite - gratification obligatoire > 2 mois", "champs": ["employeur","salarie","tribunal","poste","duree","montant","date_debut"], "fn": prompt_contrat_stage},
    "lettre_licenciement_faute": {"nom": "Lettre de licenciement pour faute", "description": "Faute grave/lourde - Art. 34+ Code travail CM", "champs": ["employeur","salarie","poste","date_debut","faits","motif_licenciement"], "fn": prompt_lettre_licenciement_faute},
    "lettre_licenciement_economique": {"nom": "Lettre de licenciement economique", "description": "Motif economique - reclassement - priorite reembauche", "champs": ["employeur","salarie","poste","faits","ancienneté","montant"], "fn": prompt_lettre_licenciement_economique},
    "solde_tout_compte": {"nom": "Recu pour solde de tout compte", "description": "Art. 69+ Code travail CM - decompte final", "champs": ["employeur","salarie","poste","date_fin","motif_licenciement","montant","ancienneté","faits"], "fn": prompt_solde_tout_compte},
    "statuts_sarl": {"nom": "Statuts SARL", "description": "Art. 309-384 AUSCGIE OHADA - capital min 100 000 FCFA", "champs": ["societe","objet","adresse","capital","creancier","requérant","faits"], "fn": prompt_statuts_sarl},
    "statuts_sa": {"nom": "Statuts SA", "description": "Art. 385-853 AUSCGIE OHADA - capital min 10M FCFA", "champs": ["societe","objet","adresse","capital","creancier","faits"], "fn": prompt_statuts_sa},
    "statuts_snc": {"nom": "Statuts SNC", "description": "Art. 270-308 AUSCGIE OHADA - responsabilite solidaire", "champs": ["societe","objet","adresse","capital","creancier","requérant","faits"], "fn": prompt_statuts_snc},
    "statuts_gie": {"nom": "Statuts GIE", "description": "Art. 869-885 AUSCGIE OHADA - groupement economique", "champs": ["societe","objet","creancier","adresse","requérant","faits"], "fn": prompt_statuts_gie},
    "pv_ago": {"nom": "PV Assemblee Generale Ordinaire", "description": "Reunion annuelle - approbation comptes - quitus", "champs": ["societe","date_debut","adresse","creancier","faits","montant"], "fn": prompt_pv_ago},
    "pv_age": {"nom": "PV Assemblee Generale Extraordinaire", "description": "Modifications statutaires - capital - objet - siege", "champs": ["societe","date_debut","adresse","faits","creancier"], "fn": prompt_pv_age},
    "cession_parts_sarl": {"nom": "Cession de parts sociales SARL", "description": "Art. 317-330 AUSCGIE OHADA - agrement requis", "champs": ["requérant","adversaire","societe","objet","montant","date_debut","faits"], "fn": prompt_cession_parts_sarl},
    "pacte_actionnaires": {"nom": "Pacte d'actionnaires", "description": "Preemption - tag-along - drag-along - gouvernance", "champs": ["societe","creancier","capital","faits"], "fn": prompt_pacte_actionnaires},
    "reconnaissance_dette": {"nom": "Reconnaissance de dette", "description": "Valeur probatoire maximale - AUPSRVE OHADA", "champs": ["creancier","debiteur","montant","nature_creance","date_exigibilite","faits","suretes"], "fn": prompt_reconnaissance_dette},
    "cautionnement": {"nom": "Acte de cautionnement", "description": "Art. 13-55 AUS OHADA - simple ou solidaire", "champs": ["creancier","debiteur","requérant","montant","faits","duree"], "fn": prompt_cautionnement},
    "nantissement": {"nom": "Contrat de nantissement", "description": "Art. 92-146 AUS OHADA - bien meuble incorporel", "champs": ["creancier","debiteur","nature_creance","montant","duree","faits"], "fn": prompt_nantissement},
    "echeancier_paiement": {"nom": "Accord de paiement echelonne", "description": "Reglement amiable - eviter voies d'execution OHADA", "champs": ["creancier","debiteur","montant","duree","date_exigibilite","faits"], "fn": prompt_echeancier_paiement},
    "contrat_prestation_services": {"nom": "Contrat de prestation de services", "description": "Obligations de resultat - propriete intellectuelle", "champs": ["requérant","adversaire","objet","montant","duree","nature_creance","faits"], "fn": prompt_contrat_prestation_services},
    "contrat_conseil": {"nom": "Contrat de conseil", "description": "Mission de conseil - honoraires - confidentialite", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_contrat_conseil},
    "contrat_sous_traitance": {"nom": "Contrat de sous-traitance", "description": "Agreation maitre d'ouvrage - paiement direct", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_contrat_sous_traitance},
    "contrat_partenariat": {"nom": "Contrat de partenariat", "description": "Collaboration commerciale - apports - gouvernance", "champs": ["requérant","adversaire","objet","faits","montant","duree"], "fn": prompt_contrat_partenariat},
    "accord_confidentialite": {"nom": "Accord de confidentialite (NDA)", "description": "Protection informations sensibles - sanctions violation", "champs": ["requérant","adversaire","objet","duree","faits"], "fn": prompt_accord_confidentialite},
    "protocole_accord_mou": {"nom": "Protocole d'accord (MOU)", "description": "Accord preliminaire - engagement de bonne foi", "champs": ["requérant","adversaire","objet","faits","duree"], "fn": prompt_protocole_accord_mou},
    "lettre_intention": {"nom": "Lettre d'intention", "description": "Document precontractuel - due diligence - exclusivite", "champs": ["requérant","adversaire","objet","montant","faits"], "fn": prompt_lettre_intention},
    "contrat_agence_commerciale": {"nom": "Contrat d'agent commercial", "description": "Art. 169-196 AUDCG OHADA - mandat d'interet commun", "champs": ["requérant","adversaire","objet","adresse","montant","duree","faits"], "fn": prompt_contrat_agence_commerciale},
    "contrat_franchise": {"nom": "Contrat de franchise", "description": "Savoir-faire - marque OAPI - redevances", "champs": ["requérant","adversaire","objet","adresse","montant","nature_creance","duree"], "fn": prompt_contrat_franchise},
    "contrat_distribution": {"nom": "Contrat de distribution exclusive", "description": "AUDCG OHADA - territoire - minima contractuels", "champs": ["requérant","adversaire","objet","adresse","faits","duree"], "fn": prompt_contrat_distribution},
    "promesse_vente_immobiliere": {"nom": "Promesse de vente immobiliere", "description": "Compromis - Ord. 74/1 - conditions suspensives", "champs": ["requérant","adversaire","adresse","montant","depot_garantie","duree","faits"], "fn": prompt_promesse_vente_immobiliere},
    "cession_fonds_commerce": {"nom": "Cession de fonds de commerce", "description": "Art. 149-168 AUDCG OHADA - RCCM", "champs": ["requérant","adversaire","objet","adresse","montant","duree","faits"], "fn": prompt_cession_fonds_commerce},
    "contrat_pret": {"nom": "Contrat de pret", "description": "Entre particuliers ou entreprises - garanties OHADA", "champs": ["creancier","debiteur","montant","suretes","duree","faits","nature_creance"], "fn": prompt_contrat_pret},
    "contrat_mariage_communaute": {"nom": "Contrat de mariage - Communaute", "description": "Regime communaute reduite aux acquets - Code civil CM", "champs": ["requérant","adversaire","date_debut","faits","objet"], "fn": prompt_contrat_mariage_communaute},
    "contrat_mariage_separation": {"nom": "Contrat de mariage - Separation de biens", "description": "Regime separatiste - independance patrimoniale", "champs": ["requérant","adversaire","date_debut","faits"], "fn": prompt_contrat_mariage_separation},
    "convention_divorce": {"nom": "Convention de divorce amiable", "description": "Consentement mutuel - garde - pension - patrimoine", "champs": ["requérant","adversaire","objet","faits","montant","adresse"], "fn": prompt_convention_divorce},
    "contrat_assurance_vie": {"nom": "Contrat d'assurance vie", "description": "Code CIMA - capital deces - clause beneficiaire", "champs": ["requérant","adversaire","creancier","montant","nature_creance","duree","faits"], "fn": prompt_contrat_assurance_vie},
    "contrat_assurance_rc": {"nom": "Assurance responsabilite civile pro", "description": "Code CIMA - RC professionnelle - franchise", "champs": ["requérant","objet","montant","suretes","nature_creance","faits"], "fn": prompt_contrat_assurance_rc},
    "contrat_developpement_logiciel": {"nom": "Contrat de developpement logiciel", "description": "Cahier des charges - jalons - propriete code source", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_contrat_developpement_logiciel},
    "cgu": {"nom": "Conditions Generales d'Utilisation", "description": "CGU plateforme numerique - droit camerounais", "champs": ["requérant","objet","adresse","adversaire","faits"], "fn": prompt_cgu},
    "politique_confidentialite": {"nom": "Politique de confidentialite", "description": "Donnees personnelles - loi camerounaise - DPO", "champs": ["requérant","objet","adversaire","faits"], "fn": prompt_politique_confidentialite},
    "procuration_generale": {"nom": "Procuration generale", "description": "Mandat large - tous pouvoirs - legalisation", "champs": ["requérant","adversaire","faits","duree"], "fn": prompt_procuration_generale},
    "procuration_speciale": {"nom": "Procuration speciale", "description": "Mandat limite - mission precise - legalisation", "champs": ["requérant","adversaire","objet","duree","faits"], "fn": prompt_procuration_speciale},
    "cession_marque": {"nom": "Cession de marque OAPI", "description": "Accord de Bangui 2015 - transfert propriete marque", "champs": ["requérant","adversaire","objet","reference_jugement","montant","faits"], "fn": prompt_cession_marque},
    "licence_marque": {"nom": "Licence de marque OAPI", "description": "Accord de Bangui 2015 - exploitation sans cession", "champs": ["requérant","adversaire","objet","adresse","montant","duree"], "fn": prompt_licence_marque},
    "contrat_transport_marchandises": {"nom": "Contrat de transport de marchandises", "description": "AUCTMR OHADA 2003 - responsabilite transporteur", "champs": ["requérant","adversaire","debiteur","objet","adresse","montant","duree"], "fn": prompt_contrat_transport_marchandises},
    "clause_arbitrage": {"nom": "Clause compromissoire d'arbitrage", "description": "AUDA OHADA 2017 - CCJA - clause a inserer dans contrat", "champs": ["requérant","adversaire","objet","faits","adresse","duree"], "fn": prompt_clause_arbitrage},
    "convention_mediation": {"nom": "Convention de mediation", "description": "AUM OHADA 2017 - accord prealable a la mediation", "champs": ["requérant","adversaire","objet","faits","montant"], "fn": prompt_convention_mediation},
    "marche_public_travaux": {"nom": "Marche public de travaux", "description": "Code marches publics CM - garanties - reception", "champs": ["requérant","adversaire","objet","montant","duree","faits"], "fn": prompt_marche_public_travaux},
    "donation": {"nom": "Acte de donation", "description": "Code civil CM - acceptation - rapport a succession", "champs": ["requérant","adversaire","objet","montant","faits"], "fn": prompt_donation},
})
"""

# Lecture et modification
with open('/root/odyxia-droit/prompts.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content + "\n" + NOUVEAUX_PROMPTS + "\n" + NOUVELLES_ENTREES

with open('/root/odyxia-droit/prompts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK - 50 contrats Vague 1 ajoutes dans prompts.py")

# Verification syntaxe
import py_compile
py_compile.compile('/root/odyxia-droit/prompts.py', doraise=True)
print("Syntaxe OK")