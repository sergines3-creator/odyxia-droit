#!/usr/bin/env python3
# patch_version_wizard.py — Wizard de validation des modifications Quill

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. CSS ────────────────────────────────────────────────────────────────────
CSS = """
/* ── MODAL SAUVEGARDE VERSION ─────────────────────────────────────── */
.save-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,0.55);
  z-index:1200;display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transition:opacity .2s;
}
.save-overlay.open{opacity:1;pointer-events:all;}
.save-modal{
  background:var(--bg);border:0.5px solid #E5E5E5;border-radius:12px;
  width:400px;max-width:95vw;
  box-shadow:0 16px 48px rgba(0,0,0,0.18);
  transform:translateY(12px);transition:transform .2s;
}
.save-overlay.open .save-modal{transform:translateY(0);}
.save-modal-hdr{
  padding:18px 20px 14px;border-bottom:0.5px solid #E5E5E5;
  display:flex;justify-content:space-between;align-items:center;
}
.save-modal-title{font-size:13px;font-weight:600;color:#0A0A0A;}
.save-modal-close{
  background:none;border:none;cursor:pointer;
  font-size:16px;color:#A3A3A3;padding:0;
}
.save-modal-close:hover{color:#0A0A0A;}
.save-modal-body{padding:18px 20px;}
.save-modal-info{
  font-size:12px;color:#6B7280;margin-bottom:16px;
  line-height:1.6;
}
.save-modal-ftr{
  padding:12px 20px;border-top:0.5px solid #E5E5E5;
  display:flex;justify-content:flex-end;gap:8px;
}
.save-btn-cancel{
  padding:8px 16px;border:0.5px solid #E5E5E5;border-radius:6px;
  background:#fff;font-size:12px;color:#0A0A0A;cursor:pointer;
}
.save-btn-confirm{
  padding:8px 18px;border:none;border-radius:6px;
  background:#0A0A0A;color:#fff;font-size:12px;
  font-weight:500;cursor:pointer;
}
.save-btn-confirm:hover{background:#333;}
.save-versions-list{
  margin-top:12px;border-top:0.5px solid #F0F0F0;padding-top:12px;
}
.save-version-item{
  display:flex;justify-content:space-between;align-items:center;
  padding:6px 0;border-bottom:0.5px solid #F5F5F5;
  font-size:11px;color:#6B7280;
}
.save-version-item:last-child{border-bottom:none;}
.save-version-note{font-weight:500;color:#0A0A0A;max-width:200px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.save-version-restore{
  font-size:10px;padding:2px 8px;border-radius:4px;
  border:0.5px solid #E5E5E5;background:#fff;cursor:pointer;
  color:#0A0A0A;
}
.save-version-restore:hover{background:#F5F5F5;}
"""

if CSS not in content:
    content = content.replace('</style>', CSS + '\n</style>', 1)
    print("CSS sauvegarde OK")

# ── 2. HTML ───────────────────────────────────────────────────────────────────
HTML = """
<!-- MODAL SAUVEGARDE VERSION -->
<div class="save-overlay" id="save-overlay" onclick="saveClickOverlay(event)">
  <div class="save-modal">
    <div class="save-modal-hdr">
      <div class="save-modal-title">Enregistrer les modifications</div>
      <button class="save-modal-close" onclick="fermerSaveModal()">✕</button>
    </div>
    <div class="save-modal-body">
      <div class="save-modal-info">
        Vous avez modifié ce document. Ajoutez une note pour identifier cette version.
      </div>
      <div class="export-field">
        <label class="export-label">Note de version <span style="font-weight:400;color:#A3A3A3">(optionnel)</span></label>
        <input class="export-input" id="save-note" type="text" 
          placeholder="Ex: Correction clause résiliation, ajout article 5...">
      </div>
      <div id="save-versions-container" style="display:none;">
        <div style="font-size:11px;font-weight:600;color:#0A0A0A;margin-bottom:8px;">Versions précédentes</div>
        <div class="save-versions-list" id="save-versions-list"></div>
      </div>
    </div>
    <div class="save-modal-ftr">
      <button class="save-btn-cancel" onclick="fermerSaveModal()">Annuler</button>
      <button class="save-btn-confirm" onclick="saveConfirmer()">Enregistrer la version</button>
    </div>
  </div>
</div>
"""

if HTML not in content:
    content = content.replace('</body>', HTML + '\n</body>', 1)
    print("HTML sauvegarde OK")

# ── 3. JavaScript ─────────────────────────────────────────────────────────────
JS = """
// ══════════════════════════════════════════════════════════════════════════════
// MODAL SAUVEGARDE VERSION
// ══════════════════════════════════════════════════════════════════════════════

let SAVE_VERSIONS = []; // Historique local des versions

function ouvrirSaveModal() {
  document.getElementById('save-note').value = '';
  chargerVersions();
  document.getElementById('save-overlay').classList.add('open');
  setTimeout(() => document.getElementById('save-note').focus(), 100);
}

function fermerSaveModal() {
  document.getElementById('save-overlay').classList.remove('open');
}

function saveClickOverlay(e) {
  if (e.target === document.getElementById('save-overlay')) fermerSaveModal();
}

function chargerVersions() {
  const container = document.getElementById('save-versions-container');
  const list      = document.getElementById('save-versions-list');
  if (!SAVE_VERSIONS.length) { container.style.display = 'none'; return; }

  container.style.display = 'block';
  list.innerHTML = SAVE_VERSIONS.slice(-5).reverse().map((v, i) => `
    <div class="save-version-item">
      <div>
        <div class="save-version-note">${v.note || 'Version sans note'}</div>
        <div style="font-size:10px;color:#A3A3A3;margin-top:1px;">${v.date}</div>
      </div>
      <button class="save-version-restore" onclick="restaurerVersion(${SAVE_VERSIONS.length - 1 - i})">
        Restaurer
      </button>
    </div>
  `).join('');
}

function restaurerVersion(idx) {
  const v = SAVE_VERSIONS[idx];
  if (!v) return;
  if (!confirm('Restaurer cette version ? Les modifications actuelles seront perdues.')) return;
  if (quill) quill.root.innerHTML = v.contenu;
  REDAC_CONTENU = v.contenu_texte;
  fermerSaveModal();
  showToast('Version restaurée');
}

async function saveConfirmer() {
  const btn  = document.querySelector('.save-btn-confirm');
  const note = document.getElementById('save-note').value.trim();

  // Récupérer le contenu actuel de Quill
  const contenuHtml  = quill ? quill.root.innerHTML : '';
  const contenuTexte = quill ? quill.getText() : REDAC_CONTENU || '';

  // Sauvegarder dans l'historique local
  const version = {
    note        : note || 'Version sans note',
    date        : new Date().toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}),
    contenu     : contenuHtml,
    contenu_texte: contenuTexte,
    nom_doc     : ACTE_ACTIF?.nom || 'Document',
  };
  SAVE_VERSIONS.push(version);

  // Mettre à jour REDAC_CONTENU avec le contenu Quill actuel
  REDAC_CONTENU = contenuTexte;

  btn.disabled    = true;
  btn.textContent = 'Enregistrement...';

  // Sauvegarde dans Supabase (optionnel — bonne pratique)
  try {
    await apiFetch('/document/sauvegarder_version', 'POST', {
      nom     : version.nom_doc,
      note    : version.note,
      contenu : contenuTexte,
    });
  } catch(e) {
    // Silencieux — la version est quand même sauvée localement
  }

  fermerSaveModal();
  showToast('Version enregistrée — ' + (note || 'sans note'));

  btn.disabled    = false;
  btn.textContent = 'Enregistrer la version';
}
"""

idx_script = content.rfind('</script>')
if idx_script > 0:
    content = content[:idx_script] + "\n" + JS + "\n" + content[idx_script:]
    print("JS sauvegarde OK")

# ── 4. Modifier le bouton Enregistrer ─────────────────────────────────────────
# Chercher le bouton save existant
import re
# Remplacer onclick du bouton save
old_btn = 'id="btn-redac-save"'
if old_btn in content:
    # Trouver le bouton complet et ajouter onclick
    content = re.sub(
        r'(<button[^>]*id="btn-redac-save"[^>]*)(onclick="[^"]*")?([^>]*>)',
        lambda m: m.group(1) + ' onclick="ouvrirSaveModal()"' + m.group(3),
        content
    )
    print("Bouton save modifié")
else:
    print("WARN: btn-redac-save non trouvé")

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("patch_version_wizard.py appliqué")