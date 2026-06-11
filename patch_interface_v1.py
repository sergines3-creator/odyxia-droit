#!/usr/bin/env python3
# patch_interface_v1.py — Ajout 52 actes dans TOUS_ACTES (index.html)

NOUVEAUX_ACTES_JS = """
  // ── BAUX ─────────────────────────────────────────────────────────────────
  {key:'bail_habitation',           nom:'Bail d\\'habitation',              desc:'Bail résidentiel · droit camerounais',
   champs:['bailleur','preneur','adresse','superficie','montant','depot_garantie','date_debut','duree','faits']},
  {key:'bail_commercial',           nom:'Bail commercial',                  desc:'Art. 69-133 AUDCG OHADA · locaux commerciaux',
   champs:['bailleur','preneur','adresse','activite','montant','depot_garantie','duree','faits']},
  {key:'bail_emphyteotique',        nom:'Bail emphytéotique',               desc:'18 à 99 ans · Ord. 74/1 droit foncier CM',
   champs:['bailleur','preneur','adresse','superficie','duree','montant','faits']},
  // ── TRAVAIL ───────────────────────────────────────────────────────────────
  {key:'contrat_travail_cdi',       nom:'Contrat de travail CDI',           desc:'Durée indéterminée · Code travail CM Art. 24+',
   champs:['employeur','salarie','poste','montant','date_debut','periode_essai','adresse','avantages','faits']},
  {key:'contrat_travail_cdd',       nom:'Contrat de travail CDD',           desc:'Durée déterminée · Max 2 ans · Art. 25+ CM',
   champs:['employeur','salarie','poste','motif_cdd','montant','date_debut','date_fin','faits']},
  {key:'contrat_apprentissage',     nom:'Contrat d\\'apprentissage',         desc:'Formation professionnelle · Code travail CM',
   champs:['employeur','salarie','poste','duree','montant','date_debut','faits']},
  {key:'contrat_stage',             nom:'Convention de stage',              desc:'Tripartite · gratification obligatoire > 2 mois',
   champs:['employeur','salarie','tribunal','poste','duree','montant','date_debut']},
  {key:'lettre_licenciement_faute', nom:'Licenciement pour faute',          desc:'Faute grave/lourde · Art. 34+ Code travail CM',
   champs:['employeur','salarie','poste','date_debut','faits','motif_licenciement']},
  {key:'lettre_licenciement_economique', nom:'Licenciement économique',     desc:'Motif éco · reclassement · priorité réembauche',
   champs:['employeur','salarie','poste','faits','ancienneté','montant']},
  {key:'solde_tout_compte',         nom:'Solde de tout compte',             desc:'Art. 69+ Code travail CM · décompte final',
   champs:['employeur','salarie','poste','date_fin','motif_licenciement','montant','ancienneté','faits']},
  // ── SOCIETES ──────────────────────────────────────────────────────────────
  {key:'statuts_sarl',              nom:'Statuts SARL',                     desc:'Art. 309-384 AUSCGIE OHADA · capital min 100K FCFA',
   champs:['societe','objet','adresse','capital','creancier','requérant','faits']},
  {key:'statuts_sa',                nom:'Statuts SA',                       desc:'Art. 385-853 AUSCGIE OHADA · capital min 10M FCFA',
   champs:['societe','objet','adresse','capital','creancier','faits']},
  {key:'statuts_snc',               nom:'Statuts SNC',                      desc:'Art. 270-308 AUSCGIE OHADA · responsabilité solidaire',
   champs:['societe','objet','adresse','capital','creancier','requérant','faits']},
  {key:'statuts_gie',               nom:'Statuts GIE',                      desc:'Art. 869-885 AUSCGIE OHADA · groupement économique',
   champs:['societe','objet','creancier','adresse','requérant','faits']},
  {key:'pv_ago',                    nom:'PV Assemblée Générale Ordinaire',  desc:'Réunion annuelle · approbation comptes · quitus',
   champs:['societe','date_debut','adresse','creancier','faits','montant']},
  {key:'pv_age',                    nom:'PV Assemblée Générale Extraordinaire', desc:'Modifications statutaires · capital · objet',
   champs:['societe','date_debut','adresse','faits','creancier']},
  {key:'cession_parts_sarl',        nom:'Cession de parts sociales SARL',   desc:'Art. 317-330 AUSCGIE OHADA · agrément requis',
   champs:['requérant','adversaire','societe','objet','montant','date_debut','faits']},
  {key:'pacte_actionnaires',        nom:'Pacte d\\'actionnaires',            desc:'Préemption · tag-along · drag-along · gouvernance',
   champs:['societe','creancier','capital','faits']},
  // ── RECOUVREMENT ET SURETES ───────────────────────────────────────────────
  {key:'reconnaissance_dette',      nom:'Reconnaissance de dette',          desc:'Valeur probatoire maximale · AUPSRVE OHADA',
   champs:['creancier','debiteur','montant','nature_creance','date_exigibilite','faits','suretes']},
  {key:'cautionnement',             nom:'Acte de cautionnement',            desc:'Art. 13-55 AUS OHADA · simple ou solidaire',
   champs:['creancier','debiteur','requérant','montant','faits','duree']},
  {key:'nantissement',              nom:'Contrat de nantissement',          desc:'Art. 92-146 AUS OHADA · bien meuble incorporel',
   champs:['creancier','debiteur','nature_creance','montant','duree','faits']},
  {key:'echeancier_paiement',       nom:'Accord de paiement échelonné',     desc:'Règlement amiable · éviter voies d\\'exécution OHADA',
   champs:['creancier','debiteur','montant','duree','date_exigibilite','faits']},
  // ── PRESTATIONS ET COMMERCE ───────────────────────────────────────────────
  {key:'contrat_prestation_services', nom:'Contrat de prestation de services', desc:'Obligations de résultat · propriété intellectuelle',
   champs:['requérant','adversaire','objet','montant','duree','nature_creance','faits']},
  {key:'contrat_conseil',           nom:'Contrat de conseil',               desc:'Mission de conseil · honoraires · confidentialité',
   champs:['requérant','adversaire','objet','montant','duree','faits']},
  {key:'contrat_sous_traitance',    nom:'Contrat de sous-traitance',        desc:'Agréation maître d\\'ouvrage · paiement direct',
   champs:['requérant','adversaire','objet','montant','duree','faits']},
  {key:'contrat_partenariat',       nom:'Contrat de partenariat',           desc:'Collaboration commerciale · apports · gouvernance',
   champs:['requérant','adversaire','objet','faits','montant','duree']},
  {key:'accord_confidentialite',    nom:'Accord de confidentialité (NDA)',  desc:'Protection informations sensibles · sanctions violation',
   champs:['requérant','adversaire','objet','duree','faits']},
  {key:'protocole_accord_mou',      nom:'Protocole d\\'accord (MOU)',        desc:'Accord préliminaire · engagement de bonne foi',
   champs:['requérant','adversaire','objet','faits','duree']},
  {key:'lettre_intention',          nom:'Lettre d\\'intention',              desc:'Document précontractuel · due diligence · exclusivité',
   champs:['requérant','adversaire','objet','montant','faits']},
  {key:'contrat_agence_commerciale', nom:'Contrat d\\'agent commercial',     desc:'Art. 169-196 AUDCG OHADA · mandat d\\'intérêt commun',
   champs:['requérant','adversaire','objet','adresse','montant','duree','faits']},
  {key:'contrat_franchise',         nom:'Contrat de franchise',             desc:'Savoir-faire · marque OAPI · redevances',
   champs:['requérant','adversaire','objet','adresse','montant','nature_creance','duree']},
  {key:'contrat_distribution',      nom:'Contrat de distribution exclusive', desc:'AUDCG OHADA · territoire · minima contractuels',
   champs:['requérant','adversaire','objet','adresse','faits','duree']},
  // ── IMMOBILIER ────────────────────────────────────────────────────────────
  {key:'promesse_vente_immobiliere', nom:'Promesse de vente immobilière',   desc:'Compromis · Ord. 74/1 · conditions suspensives',
   champs:['requérant','adversaire','adresse','montant','depot_garantie','duree','faits']},
  {key:'cession_fonds_commerce',    nom:'Cession de fonds de commerce',     desc:'Art. 149-168 AUDCG OHADA · RCCM',
   champs:['requérant','adversaire','objet','adresse','montant','duree','faits']},
  // ── PRET ET FINANCEMENT ───────────────────────────────────────────────────
  {key:'contrat_pret',              nom:'Contrat de prêt',                  desc:'Entre particuliers ou entreprises · garanties OHADA',
   champs:['creancier','debiteur','montant','suretes','duree','faits','nature_creance']},
  // ── FAMILLE ───────────────────────────────────────────────────────────────
  {key:'contrat_mariage_communaute', nom:'Contrat de mariage — Communauté', desc:'Régime communauté réduite aux acquêts · Code civil CM',
   champs:['requérant','adversaire','date_debut','faits','objet']},
  {key:'contrat_mariage_separation', nom:'Contrat de mariage — Séparation', desc:'Régime séparatiste · indépendance patrimoniale',
   champs:['requérant','adversaire','date_debut','faits']},
  {key:'convention_divorce',        nom:'Convention de divorce amiable',    desc:'Consentement mutuel · garde · pension · patrimoine',
   champs:['requérant','adversaire','objet','faits','montant','adresse']},
  // ── ASSURANCES CIMA ───────────────────────────────────────────────────────
  {key:'contrat_assurance_vie',     nom:'Contrat d\\'assurance vie',         desc:'Code CIMA · capital décès · clause bénéficiaire',
   champs:['requérant','adversaire','creancier','montant','nature_creance','duree','faits']},
  {key:'contrat_assurance_rc',      nom:'Assurance responsabilité civile',  desc:'Code CIMA · RC professionnelle · franchise',
   champs:['requérant','objet','montant','suretes','nature_creance','faits']},
  // ── NUMERIQUE ─────────────────────────────────────────────────────────────
  {key:'contrat_developpement_logiciel', nom:'Contrat développement logiciel', desc:'Cahier des charges · jalons · propriété code source',
   champs:['requérant','adversaire','objet','montant','duree','faits']},
  {key:'cgu',                       nom:'Conditions Générales d\\'Utilisation', desc:'CGU plateforme numérique · droit camerounais',
   champs:['requérant','objet','adresse','adversaire','faits']},
  {key:'politique_confidentialite', nom:'Politique de confidentialité',     desc:'Données personnelles · loi camerounaise · DPO',
   champs:['requérant','objet','adversaire','faits']},
  // ── PROCURATIONS ─────────────────────────────────────────────────────────
  {key:'procuration_generale',      nom:'Procuration générale',             desc:'Mandat large · tous pouvoirs · légalisation',
   champs:['requérant','adversaire','faits','duree']},
  {key:'procuration_speciale',      nom:'Procuration spéciale',             desc:'Mandat limité · mission précise · légalisation',
   champs:['requérant','adversaire','objet','duree','faits']},
  // ── OAPI ─────────────────────────────────────────────────────────────────
  {key:'cession_marque',            nom:'Cession de marque OAPI',           desc:'Accord de Bangui 2015 · transfert propriété marque',
   champs:['requérant','adversaire','objet','reference_jugement','montant','faits']},
  {key:'licence_marque',            nom:'Licence de marque OAPI',           desc:'Accord de Bangui 2015 · exploitation sans cession',
   champs:['requérant','adversaire','objet','adresse','montant','duree']},
  // ── TRANSPORT ─────────────────────────────────────────────────────────────
  {key:'contrat_transport_marchandises', nom:'Transport de marchandises',   desc:'AUCTMR OHADA 2003 · responsabilité transporteur',
   champs:['requérant','adversaire','debiteur','objet','adresse','montant','duree']},
  // ── MEDIATION ET ARBITRAGE ────────────────────────────────────────────────
  {key:'clause_arbitrage',          nom:'Clause d\\'arbitrage OHADA',        desc:'AUDA OHADA 2017 · CCJA · clause compromissoire',
   champs:['requérant','adversaire','objet','faits','adresse','duree']},
  {key:'convention_mediation',      nom:'Convention de médiation',          desc:'AUM OHADA 2017 · accord préalable médiation',
   champs:['requérant','adversaire','objet','faits','montant']},
  // ── DROIT PUBLIC ─────────────────────────────────────────────────────────
  {key:'marche_public_travaux',     nom:'Marché public de travaux',         desc:'Code marchés publics CM · garanties · réception',
   champs:['requérant','adversaire','objet','montant','duree','faits']},
  // ── LIBERALITES ──────────────────────────────────────────────────────────
  {key:'donation',                  nom:'Acte de donation',                 desc:'Code civil CM · acceptation · rapport à succession',
   champs:['requérant','adversaire','objet','montant','faits']},"""

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Trouver la fin de TOUS_ACTES
import re
idx = content.rfind("key:'")
idx_end = content.find("];", idx)
if idx_end < 0:
    print("Fin TOUS_ACTES non trouvee")
    exit(1)

# Insérer avant ];
content = content[:idx_end] + NOUVEAUX_ACTES_JS + "\n" + content[idx_end:]

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

# Vérification
import re
keys = re.findall(r"key:'([a-z_]+)'", content)
print(f"OK — Total actes dans interface : {len(keys)}")