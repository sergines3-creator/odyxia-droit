#!/usr/bin/env python3
# patch_interface_v3.py — Ajout actes Vague 3 dans TOUS_ACTES

import re

with open('/root/odyxia-droit/prompts.py', 'r', encoding='utf-8') as f:
    prompts = f.read()

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

keys_prompts = set(re.findall(r'"([a-z_]+)":\s*\{"nom":', prompts))
keys_html = set(re.findall(r"key:'([a-z_]+)'", html))
manquants = sorted(keys_prompts - keys_html)
print(f"Actes manquants : {len(manquants)}")
for k in manquants:
    print(f"  -> {k}")

CHAMPS_MAP = {
    "contrat_affrètement": ["requérant","adversaire","objet","adresse","montant","duree","faits"],
    "lettre_voiture": ["requérant","adversaire","debiteur","objet","adresse","faits","montant"],
    "contrat_commission_transport": ["requérant","adversaire","objet","montant","duree","faits"],
    "requete_redressement": ["debiteur","societe","montant","date_debut","faits","objet"],
    "acte_vente_immobiliere": ["requérant","adversaire","adresse","reference_jugement","montant","faits"],
    "contrat_promotion_immobiliere": ["requérant","adversaire","objet","adresse","montant","duree","faits"],
    "convention_indivision": ["requérant","adresse","faits","adversaire","duree"],
    "contrat_construction": ["requérant","adversaire","objet","adresse","montant","duree","faits"],
    "plainte_avec_constitution": ["requérant","adversaire","chefs_inculpation","faits","montant"],
    "memoire_cassation": ["requérant","adversaire","reference_jugement","moyens_cassation","faits"],
    "reclamation_fiscale": ["requérant","adversaire","reference_jugement","montant","faits"],
    "recours_douanier": ["requérant","adversaire","reference_jugement","montant","faits"],
    "ppp": ["requérant","adversaire","objet","montant","duree","faits"],
    "fiducie": ["requérant","adversaire","creancier","objet","montant","duree"],
    "portage_actions": ["requérant","adversaire","objet","societe","montant","duree","faits"],
    "compromis_arbitrage": ["requérant","adversaire","objet","faits","adresse","montant"],
    "accord_mediation_final": ["requérant","adversaire","tribunal","faits","montant","objet"],
    "reconnaissance_paternite": ["requérant","adversaire","date_debut","creancier","faits"],
    "engagement_honneur": ["requérant","objet","faits"],
    "acte_cautionnement_judiciaire": ["requérant","adversaire","reference_jugement","montant","faits"],
    "accord_non_concurrence": ["requérant","adversaire","objet","adresse","duree","montant"],
    "convention_environnementale": ["requérant","adversaire","objet","adresse","faits","montant"],
    "nantissement_fonds_commerce": ["creancier","debiteur","objet","montant","duree","faits"],
    "hypotheque": ["creancier","debiteur","adresse","reference_jugement","montant","duree","faits"],
    "billet_a_ordre": ["debiteur","creancier","montant","date_exigibilite","adresse","faits"],
    "lettre_de_change": ["requérant","debiteur","creancier","montant","date_exigibilite","adresse"],
    "separation_corps": ["requérant","adversaire","date_debut","faits","objet","tribunal"],
    "opposition_execution": ["requérant","adversaire","objet","faits","montant"],
    "mainlevee_saisie": ["requérant","adversaire","objet","faits","montant"],
}

NOM_MAP = {
    "contrat_affrètement": ("Contrat d'affretement", "AUCTMR OHADA 2003 - fret - surestaries"),
    "lettre_voiture": ("Lettre de voiture", "AUCTMR OHADA 2003 - document transport routier"),
    "contrat_commission_transport": ("Commission de transport", "AUCTMR OHADA 2003 - organisation transport"),
    "requete_redressement": ("Requete en redressement judiciaire", "Art. 25+ AUPC OHADA 2015"),
    "acte_vente_immobiliere": ("Acte de vente immobiliere definitif", "Droit foncier CM - mutation registre"),
    "contrat_promotion_immobiliere": ("Contrat de promotion immobiliere", "Droit CM - garanties achevement"),
    "convention_indivision": ("Convention d'indivision", "Droit CM - gestion bien indivis"),
    "contrat_construction": ("Contrat de construction", "Droit CM - responsabilite decennale"),
    "plainte_avec_constitution": ("Plainte avec constitution partie civile", "CPP CM - prejudice - instruction"),
    "memoire_cassation": ("Memoire ampliatif pourvoi cassation", "Cour Supreme CM - moyens cassation"),
    "reclamation_fiscale": ("Reclamation contentieuse fiscale", "CGI camerounais - decharge"),
    "recours_douanier": ("Recours douanier contentieux", "Code douanes CM - annulation"),
    "ppp": ("Partenariat Public-Prive (PPP)", "Droit CM - financement prive - risques"),
    "fiducie": ("Contrat de fiducie-surete", "AUS OHADA 2010 - transfert patrimonial"),
    "portage_actions": ("Contrat de portage d'actions", "Droit OHADA - detention temporaire"),
    "compromis_arbitrage": ("Compromis d'arbitrage", "AUDA OHADA 2017 - litige existant"),
    "accord_mediation_final": ("Accord de mediation final", "AUM OHADA 2017 - resolution litige"),
    "reconnaissance_paternite": ("Reconnaissance de paternite", "Code civil CM - filiation"),
    "engagement_honneur": ("Engagement sur l'honneur", "Usage juridique CM - declaration"),
    "acte_cautionnement_judiciaire": ("Cautionnement judiciaire", "CPC camerounais - garantie decision"),
    "accord_non_concurrence": ("Accord de non-concurrence", "Droit CM - contrepartie obligatoire"),
    "convention_environnementale": ("Convention environnementale", "Loi-cadre env CM - mitigation"),
    "nantissement_fonds_commerce": ("Nantissement fonds de commerce", "AUDCG + AUS OHADA - RCCM"),
    "hypotheque": ("Acte d'hypotheque conventionnelle", "Art. 190+ AUS OHADA 2010"),
    "billet_a_ordre": ("Billet a ordre", "AUPSRVE OHADA - droit cambiaire CM"),
    "lettre_de_change": ("Lettre de change", "AUPSRVE OHADA - droit cambiaire CM"),
    "separation_corps": ("Requete en separation de corps", "Code civil CM - mesures urgentes"),
    "opposition_execution": ("Opposition a mesure d'execution", "AUPSRVE OHADA 2023 - contestation"),
    "mainlevee_saisie": ("Demande de mainlevee de saisie", "AUPSRVE OHADA 2023 - paiement ou nullite"),
}

js_lignes = []
for key in manquants:
    nom, desc = NOM_MAP.get(key, (key, "Acte juridique OHADA"))
    champs = CHAMPS_MAP.get(key, ["requérant","adversaire","faits"])
    champs_js = str(champs).replace('"', "'")
    nom_js = nom.replace("'", "\\'")
    desc_js = desc.replace("'", "\\'")
    js_lignes.append(f"  {{key:'{key}', nom:'{nom_js}', desc:'{desc_js}', champs:{champs_js}}},")

nouveaux_js = "\n".join(js_lignes)

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