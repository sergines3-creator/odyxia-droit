#!/usr/bin/env python3
# patch_interface_v2.py — Ajout actes Vague 2 dans TOUS_ACTES (index.html)

import re

with open('/root/odyxia-droit/prompts.py', 'r', encoding='utf-8') as f:
    prompts = f.read()

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

keys_prompts = set(re.findall(r'"([a-z_]+)":\s*\{"nom":', prompts))
keys_html = set(re.findall(r"key:'([a-z_]+)'", html))
manquants = sorted(keys_prompts - keys_html)
print(f"Actes manquants : {len(manquants)}")

# Construire les entrées JS pour les actes manquants
# On récupère nom, description et champs depuis prompts.py
import ast, re as re2

CHAMPS_MAP = {
    "statuts_sasu": ["societe","objet","adresse","capital","requérant","faits"],
    "statuts_scs": ["societe","objet","adresse","capital","requérant","creancier","faits"],
    "cession_actions_sa": ["requérant","adversaire","societe","objet","montant","date_debut","faits"],
    "convention_compte_courant": ["requérant","societe","montant","suretes","duree","faits"],
    "dissolution_amiable": ["societe","creancier","requérant","faits","montant"],
    "contrat_fermage": ["bailleur","preneur","adresse","superficie","montant","duree","faits"],
    "contrat_metayage": ["bailleur","preneur","adresse","faits","duree"],
    "contrat_vente_recoltes": ["requérant","adversaire","objet","superficie","montant","date_debut","faits"],
    "contrat_sous_traitance_petroliere": ["requérant","adversaire","objet","adresse","montant","duree","faits"],
    "convention_exploitation_miniere": ["requérant","adversaire","adresse","objet","montant","duree"],
    "contrat_credit_bail": ["creancier","debiteur","objet","montant","nature_creance","duree","suretes","faits"],
    "ouverture_credit": ["creancier","debiteur","montant","objet","suretes","duree","nature_creance"],
    "garantie_bancaire": ["creancier","adversaire","debiteur","objet","montant","duree"],
    "convention_tresorerie": ["requérant","creancier","montant","suretes","duree"],
    "reglement_interieur": ["requérant","objet","faits","duree","montant"],
    "accord_teletravail": ["employeur","salarie","poste","duree","date_debut","montant","faits"],
    "plan_sauvegarde_emploi": ["employeur","objet","faits","montant","duree"],
    "accord_interessement": ["employeur","faits","objet","montant","duree"],
    "contrat_medical": ["requérant","adversaire","objet","montant","duree","faits"],
    "convention_formation": ["employeur","salarie","adversaire","objet","montant","duree","faits"],
    "contrat_scolarite": ["requérant","adversaire","objet","poste","montant","faits"],
    "contrat_gerance_hotel": ["requérant","adversaire","adresse","objet","montant","duree","faits"],
    "contrat_evenementiel": ["requérant","adversaire","objet","date_debut","adresse","montant","depot_garantie","faits"],
    "cession_brevet": ["requérant","adversaire","objet","reference_jugement","montant","faits"],
    "licence_brevet": ["requérant","adversaire","objet","adresse","montant","duree"],
    "cession_droit_auteur": ["requérant","adversaire","objet","faits","adresse","montant","duree"],
    "declaration_creance": ["creancier","debiteur","montant","nature_creance","suretes","faits"],
    "plan_redressement": ["debiteur","societe","montant","faits","duree"],
    "accord_conciliation": ["debiteur","creancier","faits","montant","duree"],
    "joint_venture": ["requérant","adversaire","objet","faits","montant","duree"],
    "contrat_commerce_international": ["requérant","adversaire","objet","montant","faits","nature_creance"],
    "testament": ["requérant","adversaire","objet","faits","creancier"],
    "partage_successoral": ["debiteur","adversaire","montant","objet","faits"],
    "donation_partage": ["requérant","adversaire","objet","faits","montant"],
    "contrat_maintenance_informatique": ["requérant","adversaire","objet","montant","faits","duree"],
    "contrat_hebergement_web": ["requérant","adversaire","objet","montant","faits","duree"],
    "cgv": ["requérant","objet","montant","duree","faits"],
    "transfert_donnees": ["requérant","adversaire","objet","adresse","faits","duree"],
    "marche_public_fournitures": ["requérant","adversaire","objet","montant","duree","faits"],
    "marche_public_services": ["requérant","adversaire","objet","montant","duree","faits"],
    "concession_service_public": ["requérant","adversaire","objet","adresse","duree","montant","faits"],
    "contrat_assurance_multirisque": ["requérant","objet","adresse","montant","nature_creance","faits"],
    "portage_salarial": ["requérant","salarie","adversaire","objet","montant","duree"],
    "assignation": ["requérant","adversaire","tribunal","objet","montant","fondements_juridiques","faits"],
    "desistement": ["requérant","adversaire","tribunal","reference_jugement","faits"],
    "transaction_judiciaire": ["requérant","adversaire","tribunal","montant","faits"],
    "pv_conciliation": ["tribunal","requérant","adversaire","objet","faits","montant"],
    "pension_alimentaire": ["requérant","adversaire","objet","montant","faits"],
    "adoption": ["requérant","adversaire","faits","tribunal"],
    "contrat_vente_commerciale": ["requérant","adversaire","objet","montant","duree","faits"],
    "contrat_commission": ["requérant","adversaire","objet","montant","duree","faits"],
    "contrat_consignation": ["requérant","adversaire","objet","montant","nature_creance","suretes","duree"],
}

NOM_MAP = {
    "statuts_sasu": ("Statuts SASU", "Societe par Actions Simplifiee Unipersonnelle"),
    "statuts_scs": ("Statuts SCS", "Art. 293-308 AUSCGIE OHADA - commandites"),
    "cession_actions_sa": ("Cession d'actions SA", "AUSCGIE OHADA - transfert valeurs mobilieres"),
    "convention_compte_courant": ("Convention compte courant d'associe", "Pret associe a sa societe - OHADA"),
    "dissolution_amiable": ("Dissolution et liquidation amiable", "AUSCGIE OHADA - radiation RCCM"),
    "contrat_fermage": ("Contrat de fermage", "Exploitation agricole - droit rural CM"),
    "contrat_metayage": ("Contrat de metayage", "Partage des recoltes - droit rural CM"),
    "contrat_vente_recoltes": ("Vente de recoltes sur pied", "Droit commercial CM - usages agricoles"),
    "contrat_sous_traitance_petroliere": ("Sous-traitance petroliere", "Code petrolier CM - knock-for-knock"),
    "convention_exploitation_miniere": ("Convention exploitation miniere", "Code minier CM - redevances"),
    "contrat_credit_bail": ("Credit-bail (leasing)", "Droit OHADA - COBAC - option d'achat"),
    "ouverture_credit": ("Contrat d'ouverture de credit", "Reglementation COBAC - ligne de credit"),
    "garantie_bancaire": ("Garantie bancaire a premiere demande", "COBAC - garantie autonome"),
    "convention_tresorerie": ("Convention de tresorerie (cash pooling)", "OHADA - COBAC - groupes de societes"),
    "reglement_interieur": ("Reglement interieur d'entreprise", "Obligatoire 11+ salaries - Code travail CM"),
    "accord_teletravail": ("Accord de teletravail", "Code travail CM - equipements - reversibilite"),
    "plan_sauvegarde_emploi": ("Plan de sauvegarde de l'emploi (PSE)", "Code travail CM - reclassement"),
    "accord_interessement": ("Accord d'interessement", "Droit CM - criteres performance - versement"),
    "contrat_medical": ("Convention de partenariat medical", "Droit sante CM - confidentialite"),
    "convention_formation": ("Convention de formation professionnelle", "Code travail CM - clause dedit"),
    "contrat_scolarite": ("Contrat de scolarite", "Droit education CM - frais scolaires"),
    "contrat_gerance_hotel": ("Contrat de gerance d'hotel", "Droit commercial CM - OHADA"),
    "contrat_evenementiel": ("Contrat de prestation evenementielle", "Droit CM - annulation - force majeure"),
    "cession_brevet": ("Cession de brevet OAPI", "Accord de Bangui 2015 - transfert brevet"),
    "licence_brevet": ("Licence de brevet OAPI", "Accord de Bangui 2015 - exploitation"),
    "cession_droit_auteur": ("Cession de droits d'auteur", "OAPI Accord Bangui - reproduction"),
    "declaration_creance": ("Declaration de creance", "Art. 78+ AUPC OHADA 2015 - proc. collective"),
    "plan_redressement": ("Plan de redressement judiciaire", "AUPC OHADA 2015 - propositions debiteur"),
    "accord_conciliation": ("Accord de conciliation OHADA", "Art. 5-1+ AUPC OHADA 2015 - preventif"),
    "joint_venture": ("Contrat de joint-venture internationale", "Droit OHADA - arbitrage CCJA"),
    "contrat_commerce_international": ("Contrat de vente internationale", "Incoterms 2020 - OHADA - credit doc"),
    "testament": ("Testament olographe", "Droit successoral CM - legataires"),
    "partage_successoral": ("Acte de partage successoral", "Droit successoral CM - lots - soultes"),
    "donation_partage": ("Donation-partage", "Anticipation succession - rapport"),
    "contrat_maintenance_informatique": ("Contrat de maintenance informatique", "SLA - niveaux de service - astreinte"),
    "contrat_hebergement_web": ("Contrat d'hebergement web", "Droit numerique CM - SLA uptime"),
    "cgv": ("Conditions Generales de Vente (CGV)", "AUDCG OHADA - prix - livraison - garanties"),
    "transfert_donnees": ("Accord transfert donnees personnelles", "Loi camerounaise - donnees - garanties"),
    "marche_public_fournitures": ("Marche public de fournitures", "Code marches publics CM - specifications"),
    "marche_public_services": ("Marche public de services", "Code marches publics CM - livrables"),
    "concession_service_public": ("Concession de service public", "Droit administratif CM - tarifs"),
    "contrat_assurance_multirisque": ("Assurance multirisque professionnelle", "Code CIMA - incendie - vol - RC"),
    "portage_salarial": ("Contrat de portage salarial", "Code travail CM - protection sociale"),
    "assignation": ("Assignation", "CPC camerounais - acte introductif instance"),
    "desistement": ("Desistement d'instance", "CPC camerounais - extinction instance"),
    "transaction_judiciaire": ("Transaction judiciaire", "Droit OHADA - chose jugee - homologation"),
    "pv_conciliation": ("PV de conciliation", "CPC CM - AUM OHADA 2017 - force executoire"),
    "pension_alimentaire": ("Convention de pension alimentaire", "Droit famille CM - enfants - indexation"),
    "adoption": ("Requete en adoption", "Code civil CM - interet de l'enfant"),
    "contrat_vente_commerciale": ("Contrat de vente commerciale", "AUDCG OHADA 2010 - reserve de propriete"),
    "contrat_commission": ("Contrat de commission", "Art. 152-168 AUDCG OHADA - nom propre"),
    "contrat_consignation": ("Contrat de consignation", "AUDCG OHADA - depot marchandises - vente"),
}

# Construire le JS
js_lignes = []
for key in manquants:
    nom, desc = NOM_MAP.get(key, (key, "Acte juridique OHADA"))
    champs = CHAMPS_MAP.get(key, ["requérant","adversaire","faits"])
    champs_js = str(champs).replace('"', "'")
    nom_js = nom.replace("'", "\\'")
    desc_js = desc.replace("'", "\\'")
    js_lignes.append(f"  {{key:'{key}', nom:'{nom_js}', desc:'{desc_js}', champs:{champs_js}}},")

nouveaux_js = "\n".join(js_lignes)

# Insérer dans TOUS_ACTES
idx = html.rfind("key:'")
idx_end = html.find("];", idx)
if idx_end < 0:
    print("Fermeture TOUS_ACTES non trouvee")
    exit(1)

html = html[:idx_end] + "\n" + nouveaux_js + "\n" + html[idx_end:]

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

keys_final = re.findall(r"key:'([a-z_]+)'", html)
print(f"OK — Total actes dans interface : {len(keys_final)}")