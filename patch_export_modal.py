#!/usr/bin/env python3
# patch_export_modal.py — Modal export PDF avec signature/logo inline

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. CSS du modal export ────────────────────────────────────────────────────
CSS_EXPORT = """
/* ── MODAL EXPORT PDF ─────────────────────────────────────────────── */
.export-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,0.55);
  z-index:1100;display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transition:opacity .2s;
}
.export-overlay.open{opacity:1;pointer-events:all;}
.export-modal{
  background:var(--bg);border:0.5px solid #E5E5E5;border-radius:12px;
  width:420px;max-width:95vw;
  box-shadow:0 16px 48px rgba(0,0,0,0.18);
  transform:translateY(12px);transition:transform .2s;
}
.export-overlay.open .export-modal{transform:translateY(0);}
.export-modal-hdr{
  padding:18px 20px 14px;border-bottom:0.5px solid #E5E5E5;
  display:flex;justify-content:space-between;align-items:center;
}
.export-modal-title{font-size:13px;font-weight:600;color:#0A0A0A;}
.export-modal-close{
  background:none;border:none;cursor:pointer;
  font-size:16px;color:#A3A3A3;padding:0;
}
.export-modal-close:hover{color:#0A0A0A;}
.export-modal-body{padding:18px 20px;}
.export-field{margin-bottom:14px;}
.export-label{
  display:block;font-size:11px;font-weight:600;
  color:#0A0A0A;margin-bottom:4px;
}
.export-input{
  width:100%;border:0.5px solid #E5E5E5;border-radius:6px;
  padding:8px 10px;font-size:12px;color:#0A0A0A;
  background:#fff;outline:none;font-family:inherit;
  box-sizing:border-box;
}
.export-input:focus{border-color:#0A0A0A;}
.export-asset-row{
  display:flex;align-items:center;gap:10px;
  border:0.5px solid #E5E5E5;border-radius:6px;
  padding:10px 12px;cursor:pointer;
  transition:border-color .15s;
}
.export-asset-row:hover{border-color:#0A0A0A;}
.export-asset-preview{
  width:40px;height:40px;border-radius:4px;
  object-fit:contain;border:0.5px solid #E5E5E5;
  background:#F5F5F5;display:none;
}
.export-asset-label{font-size:11px;color:#6B7280;flex:1;}
.export-asset-btn{
  font-size:10px;padding:4px 10px;border-radius:4px;
  border:0.5px solid #E5E5E5;background:#fff;
  cursor:pointer;color:#0A0A0A;white-space:nowrap;
}
.export-asset-btn:hover{background:#F5F5F5;}
.export-modal-ftr{
  padding:12px 20px;border-top:0.5px solid #E5E5E5;
  display:flex;justify-content:flex-end;gap:8px;
}
.export-btn-cancel{
  padding:8px 16px;border:0.5px solid #E5E5E5;border-radius:6px;
  background:#fff;font-size:12px;color:#0A0A0A;cursor:pointer;
}
.export-btn-confirm{
  padding:8px 18px;border:none;border-radius:6px;
  background:#0A0A0A;color:#fff;font-size:12px;
  font-weight:500;cursor:pointer;
}
.export-btn-confirm:hover{background:#333;}
"""

if CSS_EXPORT not in content:
    content = content.replace('</style>', CSS_EXPORT + '\n</style>', 1)
    print("CSS export modal ajouté")

# ── 2. HTML du modal export ───────────────────────────────────────────────────
HTML_EXPORT = """
<!-- MODAL EXPORT PDF -->
<div class="export-overlay" id="export-overlay" onclick="exportClickOverlay(event)">
  <div class="export-modal">
    <div class="export-modal-hdr">
      <div class="export-modal-title">Exporter en PDF</div>
      <button class="export-modal-close" onclick="fermerExportModal()">✕</button>
    </div>
    <div class="export-modal-body">
      <div class="export-field">
        <label class="export-label">Nom de l'avocat</label>
        <input class="export-input" id="exp-nom" type="text" placeholder="Ex: Maître Kengne Audrey">
      </div>
      <div class="export-field">
        <label class="export-label">Barreau</label>
        <input class="export-input" id="exp-barreau" type="text" placeholder="Ex: Barreau du Cameroun">
      </div>
      <div class="export-field">
        <label class="export-label">Ville</label>
        <input class="export-input" id="exp-ville" type="text" placeholder="Ex: Douala, Cameroun">
      </div>
      <div class="export-field">
        <label class="export-label">Logo du cabinet <span style="font-weight:400;color:#A3A3A3">(optionnel)</span></label>
        <div class="export-asset-row" onclick="document.getElementById('exp-logo-input').click()">
          <img class="export-asset-preview" id="exp-logo-preview">
          <span class="export-asset-label" id="exp-logo-label">Aucun logo sélectionné</span>
          <button class="export-asset-btn" type="button">Choisir</button>
        </div>
        <input type="file" id="exp-logo-input" accept="image/*" style="display:none" onchange="expChargerImage('logo',this)">
      </div>
      <div class="export-field">
        <label class="export-label">Signature <span style="font-weight:400;color:#A3A3A3">(optionnel)</span></label>
        <div class="export-asset-row" onclick="document.getElementById('exp-sig-input').click()">
          <img class="export-asset-preview" id="exp-sig-preview">
          <span class="export-asset-label" id="exp-sig-label">Aucune signature sélectionnée</span>
          <button class="export-asset-btn" type="button">Choisir</button>
        </div>
        <input type="file" id="exp-sig-input" accept="image/*" style="display:none" onchange="expChargerImage('sig',this)">
      </div>
    </div>
    <div class="export-modal-ftr">
      <button class="export-btn-cancel" onclick="fermerExportModal()">Annuler</button>
      <button class="export-btn-confirm" onclick="expConfirmer()">Exporter PDF</button>
    </div>
  </div>
</div>
"""

if HTML_EXPORT not in content:
    content = content.replace('</body>', HTML_EXPORT + '\n</body>', 1)
    print("HTML export modal ajouté")

# ── 3. JavaScript du modal export ────────────────────────────────────────────
JS_EXPORT = """
// ══════════════════════════════════════════════════════════════════════════════
// MODAL EXPORT PDF
// ══════════════════════════════════════════════════════════════════════════════

let EXP_LOGO_B64 = null;
let EXP_SIG_B64  = null;
let EXP_CONTENU  = null;
let EXP_NOM_DOC  = null;

function ouvrirExportModal(contenu, nomDoc) {
  EXP_CONTENU = contenu;
  EXP_NOM_DOC = nomDoc;

  // Préremplir avec les données du profil si disponibles
  const nom = document.getElementById('exp-nom');
  const bar = document.getElementById('exp-barreau');
  if (!nom.value) nom.value = '';
  if (!bar.value) bar.value = '';

  document.getElementById('export-overlay').classList.add('open');
}

function fermerExportModal() {
  document.getElementById('export-overlay').classList.remove('open');
}

function exportClickOverlay(e) {
  if (e.target === document.getElementById('export-overlay')) fermerExportModal();
}

function expChargerImage(type, input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const b64 = e.target.result; // data:image/png;base64,...
    if (type === 'logo') {
      EXP_LOGO_B64 = b64;
      document.getElementById('exp-logo-preview').src = b64;
      document.getElementById('exp-logo-preview').style.display = 'block';
      document.getElementById('exp-logo-label').textContent = file.name;
    } else {
      EXP_SIG_B64 = b64;
      document.getElementById('exp-sig-preview').src = b64;
      document.getElementById('exp-sig-preview').style.display = 'block';
      document.getElementById('exp-sig-label').textContent = file.name;
    }
  };
  reader.readAsDataURL(file);
}

async function expConfirmer() {
  const btn = document.querySelector('.export-btn-confirm');
  btn.disabled = true;
  btn.textContent = 'Génération...';

  try {
    const payload = {
      contenu    : EXP_CONTENU,
      nom        : EXP_NOM_DOC,
      nom_avocat : document.getElementById('exp-nom').value.trim() || 'Maître',
      barreau    : document.getElementById('exp-barreau').value.trim(),
      ville      : document.getElementById('exp-ville').value.trim() || 'Cameroun',
      logo_b64   : EXP_LOGO_B64,
      signature_b64 : EXP_SIG_B64,
    };

    const r = await fetch('/export_pdf', {
      method : 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},
      body   : JSON.stringify(payload)
    });

    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = (EXP_NOM_DOC || 'document').replace(/ /g,'_') + '.pdf';
    a.click();

    fermerExportModal();
    showToast('PDF exporté');
  } catch(e) {
    showToast('Erreur export : ' + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Exporter PDF';
  }
}
"""

# Insérer le JS avant </script> final
idx_script = content.rfind('</script>')
if idx_script > 0:
    content = content[:idx_script] + "\n" + JS_EXPORT + "\n" + content[idx_script:]
    print("JS export modal inséré")

# ── 4. Modifier exporterRedaction pour ouvrir le modal ───────────────────────
old_fn = """async function exporterRedaction() {
  if (!REDAC_CONTENU) return;
  try {
    const r = await fetch('/export_pdf', {
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},
      body: JSON.stringify({contenu: REDAC_CONTENU, nom: ACTE_ACTIF?.nom || 'Document'})
    });
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = (ACTE_ACTIF?.nom || 'document').replace(/ /g,'_') + '.pdf';
    a.click();
    showToast('PDF exporté');
  } catch(e) { showToast('Erreur export', true); }"""

new_fn = """async function exporterRedaction() {
  if (!REDAC_CONTENU) return;
  ouvrirExportModal(REDAC_CONTENU, ACTE_ACTIF?.nom || 'Document');"""

if old_fn in content:
    content = content.replace(old_fn, new_fn)
    print("exporterRedaction modifié")
else:
    print("WARN: exporterRedaction non trouvé")

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("patch_export_modal.py appliqué")