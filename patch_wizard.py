#!/usr/bin/env python3
# patch_wizard.py — Wizard modal pour la rédaction d'actes

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. CSS du wizard ──────────────────────────────────────────────────────────
CSS_WIZARD = """
/* ── WIZARD MODAL ─────────────────────────────────────────────────── */
.wizard-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,0.55);
  z-index:1000;display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transition:opacity .2s;
}
.wizard-overlay.open{opacity:1;pointer-events:all;}
.wizard-modal{
  background:var(--bg);border:0.5px solid #E5E5E5;border-radius:12px;
  width:520px;max-width:95vw;max-height:88vh;
  display:flex;flex-direction:column;
  box-shadow:0 16px 48px rgba(0,0,0,0.18);
  transform:translateY(12px);transition:transform .2s;
}
.wizard-overlay.open .wizard-modal{transform:translateY(0);}
.wizard-header{
  padding:20px 24px 16px;border-bottom:0.5px solid #E5E5E5;
  display:flex;justify-content:space-between;align-items:flex-start;
  flex-shrink:0;
}
.wizard-title{font-size:14px;font-weight:600;color:#0A0A0A;line-height:1.3;}
.wizard-subtitle{font-size:11px;color:#A3A3A3;margin-top:2px;}
.wizard-close{
  background:none;border:none;cursor:pointer;
  font-size:18px;color:#A3A3A3;padding:0;line-height:1;
  flex-shrink:0;margin-left:12px;
}
.wizard-close:hover{color:#0A0A0A;}
.wizard-steps{
  display:flex;align-items:center;gap:0;
  padding:14px 24px;border-bottom:0.5px solid #E5E5E5;
  flex-shrink:0;
}
.wizard-step{
  display:flex;align-items:center;gap:6px;font-size:11px;
  color:#A3A3A3;font-weight:500;
}
.wizard-step.active{color:#0A0A0A;}
.wizard-step.done{color:#22c55e;}
.wizard-step-num{
  width:20px;height:20px;border-radius:50%;
  border:1.5px solid currentColor;
  display:flex;align-items:center;justify-content:center;
  font-size:10px;font-weight:600;flex-shrink:0;
}
.wizard-step.active .wizard-step-num{background:#0A0A0A;color:#fff;border-color:#0A0A0A;}
.wizard-step.done .wizard-step-num{background:#22c55e;color:#fff;border-color:#22c55e;}
.wizard-sep{flex:1;height:1px;background:#E5E5E5;margin:0 8px;}
.wizard-body{flex:1;overflow-y:auto;padding:20px 24px;}
.wizard-field{margin-bottom:16px;}
.wizard-label{
  display:block;font-size:11px;font-weight:600;
  color:#0A0A0A;margin-bottom:5px;letter-spacing:0.02em;
}
.wizard-label span{color:#A3A3A3;font-weight:400;}
.wizard-input,.wizard-textarea{
  width:100%;border:0.5px solid #E5E5E5;border-radius:6px;
  padding:9px 12px;font-size:12px;color:#0A0A0A;
  background:#fff;outline:none;font-family:inherit;
  box-sizing:border-box;transition:border-color .15s;
}
.wizard-input:focus,.wizard-textarea:focus{border-color:#0A0A0A;}
.wizard-textarea{resize:vertical;min-height:80px;line-height:1.6;}
.wizard-footer{
  padding:14px 24px;border-top:0.5px solid #E5E5E5;
  display:flex;justify-content:space-between;align-items:center;
  flex-shrink:0;
}
.wizard-progress{font-size:10px;color:#A3A3A3;}
.wizard-btns{display:flex;gap:8px;}
.wizard-btn-back{
  padding:8px 16px;border:0.5px solid #E5E5E5;border-radius:6px;
  background:#fff;font-size:12px;color:#0A0A0A;cursor:pointer;
}
.wizard-btn-back:hover{background:#F5F5F5;}
.wizard-btn-next{
  padding:8px 20px;border:none;border-radius:6px;
  background:#0A0A0A;color:#fff;font-size:12px;
  font-weight:500;cursor:pointer;
}
.wizard-btn-next:hover{background:#333;}
.wizard-btn-next:disabled{background:#D4D4D4;cursor:not-allowed;}
.wizard-btn-generate{
  padding:8px 20px;border:none;border-radius:6px;
  background:#0A0A0A;color:#fff;font-size:12px;
  font-weight:500;cursor:pointer;display:flex;align-items:center;gap:6px;
}
.wizard-btn-generate:hover{background:#333;}
.wizard-spinner{
  width:12px;height:12px;border:2px solid rgba(255,255,255,0.3);
  border-top-color:#fff;border-radius:50%;
  animation:spin .6s linear infinite;display:none;
}
@keyframes spin{to{transform:rotate(360deg);}}
"""

# Insérer le CSS avant </style>
if CSS_WIZARD not in content:
    content = content.replace('</style>', CSS_WIZARD + '\n</style>', 1)
    print("CSS wizard ajouté")

# ── 2. HTML du wizard ─────────────────────────────────────────────────────────
HTML_WIZARD = """
<!-- WIZARD MODAL -->
<div class="wizard-overlay" id="wizard-overlay" onclick="wizardClickOverlay(event)">
  <div class="wizard-modal">
    <div class="wizard-header">
      <div>
        <div class="wizard-title" id="wizard-title">Rédaction d'acte</div>
        <div class="wizard-subtitle" id="wizard-subtitle"></div>
      </div>
      <button class="wizard-close" onclick="fermerWizard()">✕</button>
    </div>
    <div class="wizard-steps" id="wizard-steps"></div>
    <div class="wizard-body" id="wizard-body"></div>
    <div class="wizard-footer">
      <div class="wizard-progress" id="wizard-progress"></div>
      <div class="wizard-btns">
        <button class="wizard-btn-back" id="wizard-btn-back" onclick="wizardPrecedent()" style="display:none">Précédent</button>
        <button class="wizard-btn-next" id="wizard-btn-next" onclick="wizardSuivant()">Suivant</button>
        <button class="wizard-btn-generate" id="wizard-btn-generate" onclick="wizardGenerer()" style="display:none">
          <span class="wizard-spinner" id="wizard-spinner"></span>
          Générer le document
        </button>
      </div>
    </div>
  </div>
</div>
"""

# Insérer avant </body>
if HTML_WIZARD not in content:
    content = content.replace('</body>', HTML_WIZARD + '\n</body>', 1)
    print("HTML wizard ajouté")

# ── 3. JavaScript du wizard ───────────────────────────────────────────────────
JS_WIZARD = """
// ══════════════════════════════════════════════════════════════════════════════
// WIZARD MODAL — Rédaction d'actes OHADA
// ══════════════════════════════════════════════════════════════════════════════

const CHAMPS_TEXTAREA = ['faits','arguments','demandes','moyens','these_defensive',
  'nullites','garanties','moyens_cassation','arguments_adverses','reponses',
  'prejudice','cause_dissolution','perspectives','objet_consultation',
  'faits_resumes','analyse_juridique','recommandations','moyens_appel',
  'concession_a','concession_b','fumus_boni_juris','fondements_juridiques',
  'demandes_reconventionnelles','chefs_inculpation','objet','activite'];

const CHAMPS_LABELS = {
  'requérant':'Demandeur / Requérant','adversaire':'Partie adverse / Défendeur',
  'tribunal':'Tribunal compétent','demandeur':'Demandeur','defendeur':'Défendeur',
  'faits':'Exposé des faits','montant':'Montant (FCFA)','objet':'Objet / Description',
  'nature_creance':'Nature de la créance','date_exigibilite':'Date d\'exigibilité',
  'creancier':'Créancier','debiteur':'Débiteur','suretes':'Sûretés / Garanties',
  'date_debut':'Date de début','date_fin':'Date de fin','duree':'Durée',
  'bailleur':'Bailleur','preneur':'Preneur / Locataire','adresse':'Adresse / Localisation',
  'superficie':'Superficie','activite':'Activité commerciale',
  'depot_garantie':'Dépôt de garantie','employeur':'Employeur',
  'salarie':'Salarié','poste':'Poste / Fonction','motif_cdd':'Motif du CDD',
  'periode_essai':'Période d\'essai','avantages':'Avantages en nature',
  'ancienneté':'Ancienneté','motif_licenciement':'Motif du licenciement',
  'societe':'Dénomination sociale','capital':'Capital social (FCFA)',
  'arguments':'Arguments juridiques','demandes':'Prétentions / Demandes',
  'moyens':'Moyens de droit','reference_jugement':'Référence de la décision',
  'date_signification':'Date de signification','urgence':'Urgence / Péril',
  'biens_vises':'Biens visés par la saisie','tiers_saisi':'Tiers saisi',
  'titre_executoire':'Titre exécutoire','garanties':'Garanties offertes',
  'caution':'Montant de la caution','lieu_detention':'Lieu de détention',
  'chefs_inculpation':'Chefs d\'inculpation','these_defensive':'Thèse défensive',
  'nullites':'Nullités soulevées','cause_dissolution':'Cause de dissolution',
  'perspectives':'Perspectives de redressement','fautes':'Fautes de gestion',
  'actif':'Actif (FCFA)','passif':'Passif (FCFA)',
  'date_cessation':'Date de cessation de paiements','pieces':'Pièces jointes',
  'contrat':'Contrat de référence','clause_arbitrage':'Clause d\'arbitrage',
  'droit_applicable':'Droit applicable','juge':'Nom du juge',
  'juridiction':'Juridiction','chambre':'Chambre','domaine':'Domaine juridique',
  'periode':'Période','affaire':'Description de l\'affaire',
  'arguments_defense':'Arguments de la défense','antecedents':'Antécédents judiciaires',
  'appellant':'Appelant','intime':'Intimé','decision_attaquee':'Décision attaquée',
  'moyens_appel':'Moyens d\'appel','pays_origine':'Pays d\'origine',
  'decision':'Décision étrangère','acte_attaque':'Acte administratif attaqué',
  'date_acte':'Date de l\'acte','titre_foncier':'Titre foncier',
  'localisation':'Localisation du bien','droit_requérant':'Droit du requérant',
  'delai':'Délai accordé','consequences':'Conséquences annoncées',
  'reference_sentence':'Référence de la sentence','date_sentence':'Date de la sentence',
  'objet_consultation':'Objet de la consultation',
  'faits_resumes':'Résumé des faits','analyse_juridique':'Analyse juridique',
  'recommandations':'Recommandations','concession_a':'Concessions de la partie A',
  'concession_b':'Concessions de la partie B',
  'fumus_boni_juris':'Fumus boni juris (apparence du droit)',
  'fondements_juridiques':'Fondements juridiques',
  'demandes_reconventionnelles':'Demandes reconventionnelles',
  'type_conclusions':'Type de conclusions','salarie_porte':'Salarié porté',
  'date_dec':'Date de la décision','source':'Source','actif_net':'Actif net',
  'commandites':'Associés commandités','commanditaires':'Associés commanditaires',
  'quota':'Quote-parts','partage':'Partage des récoltes',
  'day_rate':'Rémunération (day-rate)','zone':'Zone d\'opération',
  'substances':'Substances minérales','budget_env':'Budget environnemental',
  'legataires':'Légataires','lots':'Lots attribués','soultes':'Soultes',
  'beneficiaire':'Bénéficiaire','souscripteur':'Souscripteur',
  'clause_beneficiaire':'Clause bénéficiaire','valeur_rachat':'Valeur de rachat',
  'plafond':'Plafond de garantie','franchise':'Franchise',
  'systemes':'Systèmes couverts','sla':'SLA / Niveau de service',
  'cookies':'Politique cookies','dpo':'Email DPO',
  'mandat':'Mission du mandataire','jalons':'Jalons de livraison',
  'spec':'Spécifications techniques','incoterm':'Incoterm applicable',
  'devise':'Devise','fret':'Fret / Prix transport','surestaries':'Surestaries',
  'debiteur_proc':'Débiteur en procédure','partenaire_prive':'Partenaire privé',
  'indicateurs':'Indicateurs de performance','rang':'Rang de l\'hypothèque',
  'porteur':'Porteur d\'actions','donneur_ordre':'Donneur d\'ordre',
  'zone_geo':'Zone géographique','contrepartie':'Contrepartie financière',
  'objet_env':'Objet de la convention','mesures':'Mesures de mitigation',
  'budget_ppp':'Budget PPP','risques':'Répartition des risques',
  'hotel':'Description de l\'hôtel','nb_chambres':'Nombre de chambres',
  'evenement':'Description de l\'événement','acompte':'Acompte',
  'programme':'Programme immobilier','classe':'Classe / Niveau',
  'formation':'Formation visée','organe':'Organisme de formation',
  'critere':'Critère de performance','enveloppe':'Enveloppe maximale',
  'soins':'Soins / Prestations médicales','partenariat_med':'Objet du partenariat',
  'nb_postes':'Nombre de postes supprimés','motif_eco':'Motif économique',
  'jours_tt':'Jours de télétravail par semaine','indemnite_tt':'Indemnité mensuelle',
  'redev':'Redevance / Royalties','exclusivite':'Exclusivité',
  'success_fee':'Success fee','vacation':'Vacation horaire',
  'min_vente':'Objectifs de vente minimaux','produits':'Produits distribués',
  'concept':'Concept / Savoir-faire','droit_entree':'Droit d\'entrée',
  'canon':'Canon emphytéotique','mairie':'Autorité concédante',
  'service':'Service public délégué','tarifs':'Tarifs',
  'investissement':'Investissement (FCFA)','type_credit':'Type de crédit',
  'commissions':'Commissions bancaires','fiduciaire':'Fiduciaire',
  'mode':'Mode de rupture','solde':'Solde dû',
  'reference_jugement': 'Référence du jugement / Numéro OAPI',
  'moyens_cassation': 'Moyens de cassation',
  'fondements_juridiques': 'Fondements juridiques',
};

const PLACEHOLDERS = {
  'requérant':'Ex: Maître Dupont, avocat au Barreau de Douala',
  'adversaire':'Ex: Société ABC SARL, Akwa Douala',
  'tribunal':'Ex: Tribunal de Grande Instance du Wouri',
  'montant':'Ex: 5 000 000',
  'objet':'Ex: Description précise de l\'objet',
  'adresse':'Ex: Rue Joss, Akwa, Douala, Cameroun',
  'faits':'Décrivez les faits de manière chronologique et précise...',
  'bailleur':'Ex: M. Jean MBARGA, propriétaire',
  'preneur':'Ex: SARL TechCam, représentée par son gérant',
  'superficie':'Ex: 150 m²',
  'duree':'Ex: 2 ans renouvelable',
  'employeur':'Ex: SARL Industries du Cameroun',
  'salarie':'Ex: M. Paul NKENG, ingénieur',
  'poste':'Ex: Directeur Commercial',
  'montant':'Ex: 450 000 FCFA brut mensuel',
  'societe':'Ex: SARL KENGNE & Associés',
  'capital':'Ex: 1 000 000',
  'creancier':'Ex: Banque Commerciale du Cameroun',
  'debiteur':'Ex: M. Thomas BIYA',
};

// Groupement des champs par étapes (max 4 champs par étape)
function grouperChamps(champs) {
  const groupes = [];
  const taille = 4;
  for (let i = 0; i < champs.length; i += taille) {
    groupes.push(champs.slice(i, i + taille));
  }
  // Si une seule étape, pas de regroupement
  if (groupes.length === 1) return [champs];
  return groupes;
}

let WIZARD_ACTE    = null;
let WIZARD_ETAPES  = [];
let WIZARD_STEP    = 0;
let WIZARD_DONNEES = {};

function ouvrirWizard(acte) {
  WIZARD_ACTE    = acte;
  WIZARD_DONNEES = {};
  WIZARD_ETAPES  = grouperChamps(acte.champs || []);
  WIZARD_STEP    = 0;

  document.getElementById('wizard-title').textContent   = acte.nom;
  document.getElementById('wizard-subtitle').textContent = acte.desc || '';

  wizardRendreEtape();
  wizardRendreSteps();

  const overlay = document.getElementById('wizard-overlay');
  overlay.classList.add('open');
}

function fermerWizard() {
  document.getElementById('wizard-overlay').classList.remove('open');
  WIZARD_ACTE = null;
}

function wizardClickOverlay(e) {
  if (e.target === document.getElementById('wizard-overlay')) fermerWizard();
}

function wizardRendreSteps() {
  const container = document.getElementById('wizard-steps');
  const n = WIZARD_ETAPES.length;
  if (n <= 1) { container.innerHTML = ''; return; }

  let html = '';
  for (let i = 0; i < n; i++) {
    const classe = i < WIZARD_STEP ? 'done' : i === WIZARD_STEP ? 'active' : '';
    const label  = i === 0 ? 'Informations' : i === n-1 ? 'Finalisation' : `Étape ${i+1}`;
    html += `<div class="wizard-step ${classe}">
      <div class="wizard-step-num">${i < WIZARD_STEP ? '✓' : i+1}</div>
      <span>${label}</span>
    </div>`;
    if (i < n-1) html += '<div class="wizard-sep"></div>';
  }
  container.innerHTML = html;
}

function wizardRendreEtape() {
  const champs = WIZARD_ETAPES[WIZARD_STEP] || [];
  const n      = WIZARD_ETAPES.length;
  let html = '';

  for (const champ of champs) {
    const label = CHAMPS_LABELS[champ] || champ.replace(/_/g,' ').replace(/\b\w/g, l => l.toUpperCase());
    const isTA  = CHAMPS_TEXTAREA.includes(champ);
    const ph    = PLACEHOLDERS[champ] || '';
    const val   = WIZARD_DONNEES[champ] || '';

    html += `<div class="wizard-field">
      <label class="wizard-label" for="wz_${champ}">${label}</label>`;

    if (isTA) {
      html += `<textarea class="wizard-textarea" id="wz_${champ}" 
        placeholder="${ph}" rows="4">${val}</textarea>`;
    } else {
      html += `<input class="wizard-input" type="text" id="wz_${champ}" 
        placeholder="${ph}" value="${val}">`;
    }
    html += '</div>';
  }

  document.getElementById('wizard-body').innerHTML = html;
  document.getElementById('wizard-progress').textContent = 
    n > 1 ? `Étape ${WIZARD_STEP + 1} sur ${n}` : '';

  // Boutons
  const btnBack     = document.getElementById('wizard-btn-back');
  const btnNext     = document.getElementById('wizard-btn-next');
  const btnGenerate = document.getElementById('wizard-btn-generate');

  btnBack.style.display     = WIZARD_STEP > 0 ? '' : 'none';
  btnNext.style.display     = WIZARD_STEP < n - 1 ? '' : 'none';
  btnGenerate.style.display = WIZARD_STEP === n - 1 ? '' : 'none';

  // Focus premier champ
  setTimeout(() => {
    const first = document.getElementById(`wz_${champs[0]}`);
    if (first) first.focus();
  }, 50);
}

function wizardSauvegarderEtape() {
  const champs = WIZARD_ETAPES[WIZARD_STEP] || [];
  for (const champ of champs) {
    const el = document.getElementById(`wz_${champ}`);
    if (el) WIZARD_DONNEES[champ] = el.value.trim();
  }
}

function wizardSuivant() {
  wizardSauvegarderEtape();
  if (WIZARD_STEP < WIZARD_ETAPES.length - 1) {
    WIZARD_STEP++;
    wizardRendreEtape();
    wizardRendreSteps();
    document.getElementById('wizard-body').scrollTop = 0;
  }
}

function wizardPrecedent() {
  wizardSauvegarderEtape();
  if (WIZARD_STEP > 0) {
    WIZARD_STEP--;
    wizardRendreEtape();
    wizardRendreSteps();
    document.getElementById('wizard-body').scrollTop = 0;
  }
}

async function wizardGenerer() {
  wizardSauvegarderEtape();

  const btn     = document.getElementById('wizard-btn-generate');
  const spinner = document.getElementById('wizard-spinner');
  btn.disabled  = true;
  spinner.style.display = 'inline-block';
  btn.querySelector('span:last-child') && (btn.lastChild.textContent = ' Génération...');

  try {
    const r = await apiFetch('/rediger', 'POST', {
      type    : WIZARD_ACTE.key,
      donnees : WIZARD_DONNEES,
      session_id: SESSION_ID
    });

    fermerWizard();

    if (!r || !r.document) {
      showToast('Erreur lors de la génération', true);
      return;
    }

    REDAC_CONTENU = r.document;
    document.getElementById('redac-result-title').textContent = r.nom || WIZARD_ACTE.nom;
    document.getElementById('btn-redac-export').style.display  = 'inline-flex';
    document.getElementById('btn-redac-email').style.display   = 'inline-flex';
    document.getElementById('btn-redac-save').style.display    = 'inline-flex';

    const html2 = r.document
      .replace(/^### (.+)$/gm,'<h3>$1</h3>')
      .replace(/^## (.+)$/gm,'<h2>$1</h2>')
      .replace(/^# (.+)$/gm,'<h1>$1</h1>')
      .replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>')
      .replace(/\\*(.+?)\\*/g,'<em>$1</em>')
      .replace(/^---+$/gm,'<hr/>')
      .replace(/\\n\\n/g,'</p><p>').replace(/\\n/g,'<br/>');

    if (typeof quill !== 'undefined' && quill) {
      quill.root.innerHTML = '<p>' + html2 + '</p>';
    }

    showToast('Document généré avec succès');

  } catch(e) {
    showToast('Erreur : ' + e.message, true);
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
  }
}

// Touche Escape pour fermer
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') fermerWizard();
});
"""

# ── 4. Modifier selectionnerActe pour ouvrir le wizard ───────────────────────
# Remplacer la fonction selectionnerActe existante
old_select = """function selectionnerActe(acte, el) {
  document.querySelectorAll('.redac-acte-item').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  ACTE_ACTIF = acte;
  const zone = document.getElementById('redac-champs-zone');"""

new_select = """function selectionnerActe(acte, el) {
  document.querySelectorAll('.redac-acte-item').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  ACTE_ACTIF = acte;
  // Ouvrir le wizard modal
  ouvrirWizard(acte);
  return;
  const zone = document.getElementById('redac-champs-zone');"""

if old_select in content:
    content = content.replace(old_select, new_select)
    print("selectionnerActe modifié pour ouvrir le wizard")
else:
    print("WARN: selectionnerActe non trouvé — vérifier manuellement")

# Insérer le JS du wizard avant </script> final
idx_script = content.rfind('</script>')
if idx_script > 0:
    content = content[:idx_script] + "\n" + JS_WIZARD + "\n" + content[idx_script:]
    print("JS wizard inséré")

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("patch_wizard.py appliqué avec succès")