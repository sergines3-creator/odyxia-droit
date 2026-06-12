#!/usr/bin/env python3
# patch_final.py — Toutes les modifications en une seule passe sécurisée

import re

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

pages_avant = re.findall(r'id="page-([^"]+)"', content)
print(f"Pages avant : {pages_avant}")

# ════════════════════════════════════════════════════════════════════
# 1. SUPPRIMER LIEN NAV-PROFIL (chirurgical par numéro de ligne)
# ════════════════════════════════════════════════════════════════════
lines = content.split('\n')

# Trouver et supprimer les lignes du nav-profil
new_lines = []
skip = False
i = 0
while i < len(lines):
    line = lines[i]
    if 'id="nav-profil"' in line or (skip and ('</div>' in line and 'nav-item' not in line and i > 0)):
        if 'id="nav-profil"' in line:
            skip = True
        if skip and '</div>' in line:
            skip = False
            i += 1
            continue
        i += 1
        continue
    new_lines.append(line)
    i += 1
content = '\n'.join(new_lines)
print("1. nav-profil supprimé")

# ════════════════════════════════════════════════════════════════════
# 2. SUPPRIMER PAGE-PROFIL
# ════════════════════════════════════════════════════════════════════
idx_profil_start = content.find('<div class="page" id="page-profil">')
idx_profil_end   = content.find('</div><!-- fin page-profil -->')
if idx_profil_start > 0 and idx_profil_end > 0:
    idx_profil_end += len('</div><!-- fin page-profil -->')
    content = content[:idx_profil_start] + content[idx_profil_end:]
    print("2. page-profil supprimée")
else:
    print("2. page-profil non trouvée (déjà supprimée?)")

# ════════════════════════════════════════════════════════════════════
# 3. CORRIGER showPage — nav null safe + supprimer chargerProfil
# ════════════════════════════════════════════════════════════════════
old_nav = "document.getElementById('nav-' + p).classList.add('active');"
new_nav = "const _navEl = document.getElementById('nav-' + p); if (_navEl) _navEl.classList.add('active');"
content = content.replace(old_nav, new_nav)
content = content.replace("  if (p === 'profil') chargerProfil();", "")
print("3. showPage corrigé")

# ════════════════════════════════════════════════════════════════════
# 4. SUPPRIMER "OHADA · CMR" de l'entête
# ════════════════════════════════════════════════════════════════════
content = content.replace(
    '<span class="hdr-pays" id="hdr-pays">OHADA · CMR</span>',
    '<span class="hdr-pays" id="hdr-pays"></span>'
)
print("4. OHADA CMR supprimé")

# ════════════════════════════════════════════════════════════════════
# 5. SIMPLIFIER SIDEBAR AVOCAT — supprimer "Barreau"
# ════════════════════════════════════════════════════════════════════
content = content.replace(
    'Chargement...</div>\n  <div id="sb-avocat-barreau" style="font-size:10px;color:#6B6B6B;margin-top:2px;">Barreau</div>',
    'Chargement...</div>'
)
print("5. Sidebar avocat simplifié")

# ════════════════════════════════════════════════════════════════════
# 6. AFFICHER NOM AVOCAT DANS ENTÊTE via chargerProfil
# ════════════════════════════════════════════════════════════════════
old_sb = """    const sbNomEl = document.getElementById('sb-avocat-nom');
    const sbBarEl = document.getElementById('sb-avocat-barreau');
    if (sbNomEl) sbNomEl.textContent = u.display_name || u.full_name || 'Maître';
    if (sbBarEl) sbBarEl.textContent = a.barreau || 'Barreau';"""
new_sb = """    const sbNomEl = document.getElementById('sb-avocat-nom');
    const hdrPaysEl = document.getElementById('hdr-pays');
    const _nomAvocat = u.display_name || u.full_name || 'Maître';
    if (sbNomEl) sbNomEl.textContent = _nomAvocat;
    if (hdrPaysEl) hdrPaysEl.textContent = 'Maître ' + _nomAvocat;"""
if old_sb in content:
    content = content.replace(old_sb, new_sb)
    print("6. Nom avocat dans entête OK")
else:
    print("6. WARN: pattern sb-avocat non trouvé")

# ════════════════════════════════════════════════════════════════════
# 7. CORRIGER SCROLL QUILL
# ════════════════════════════════════════════════════════════════════
content = content.replace(
    'id="redac-result-body" style="padding:0;overflow:hidden;"',
    'id="redac-result-body" style="padding:0;overflow:auto;"'
)
print("7. Scroll Quill corrigé")

# ════════════════════════════════════════════════════════════════════
# 8. NOUVEAU DASHBOARD — remplacer uniquement le contenu interne
# ════════════════════════════════════════════════════════════════════
NOUVEAU_DASHBOARD_CONTENU = '''      <div style="padding:20px 24px 0;">
        <h2 id="dash-greeting" style="font-size:18px;font-weight:600;color:#0A0A0A;font-family:var(--serif,Georgia,serif);">Bonjour, Maître</h2>
        <p id="dash-date" style="font-size:11px;color:#A3A3A3;margin-top:2px;"></p>
      </div>

      <div id="dash-alert" style="display:none;margin:12px 24px 0;padding:10px 14px;border-radius:6px;border:0.5px solid #FCD34D;background:#FFFBEB;font-size:11px;color:#92400E;"></div>

      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:16px 24px;">
        <div style="background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;padding:14px 16px;">
          <div id="kpi-docs" style="font-size:22px;font-weight:700;color:#0A0A0A;">—</div>
          <div style="font-size:10px;color:#A3A3A3;margin-top:3px;">Documents indexés</div>
        </div>
        <div style="background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;padding:14px 16px;">
          <div id="kpi-dossiers" style="font-size:22px;font-weight:700;color:#0A0A0A;">—</div>
          <div style="font-size:10px;color:#A3A3A3;margin-top:3px;">Dossiers actifs</div>
        </div>
        <div style="background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;padding:14px 16px;">
          <div id="kpi-actes" style="font-size:22px;font-weight:700;color:#0A0A0A;">—</div>
          <div style="font-size:10px;color:#A3A3A3;margin-top:3px;">Actes générés</div>
          <div style="font-size:10px;color:#6B7280;margin-top:2px;">ce mois</div>
        </div>
        <div style="background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;padding:14px 16px;">
          <div id="kpi-jours" style="font-size:22px;font-weight:700;color:#0A0A0A;">—</div>
          <div style="font-size:10px;color:#A3A3A3;margin-top:3px;">Jours abonnement</div>
          <div style="font-size:10px;color:#6B7280;margin-top:2px;">restants</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;padding:0 24px 16px;flex-wrap:wrap;">
        <div onclick="showPage('bibliotheque')" style="padding:8px 14px;border-radius:6px;border:0.5px solid #E5E5E5;background:#fff;cursor:pointer;font-size:12px;font-weight:500;color:#0A0A0A;">Uploader un document</div>
        <div onclick="showPage('redaction')" style="padding:8px 14px;border-radius:6px;border:0.5px solid #E5E5E5;background:#fff;cursor:pointer;font-size:12px;font-weight:500;color:#0A0A0A;">Rédiger un acte</div>
        <div onclick="showPage('analyse')" style="padding:8px 14px;border-radius:6px;border:0.5px solid #E5E5E5;background:#fff;cursor:pointer;font-size:12px;font-weight:500;color:#0A0A0A;">Analyser un document</div>
        <div onclick="showPage('chat')" style="padding:8px 14px;border-radius:6px;border:0.5px solid #E5E5E5;background:#fff;cursor:pointer;font-size:12px;font-weight:500;color:#0A0A0A;">Poser une question</div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:0 24px 24px;">
        <div style="background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;overflow:hidden;">
          <div style="padding:12px 16px;border-bottom:0.5px solid #E5E5E5;display:flex;justify-content:space-between;">
            <span style="font-size:11px;font-weight:600;color:#0A0A0A;">Documents récents</span>
            <span onclick="showPage('bibliotheque')" style="font-size:10px;color:#6B7280;cursor:pointer;">Voir tout</span>
          </div>
          <div id="dash-docs-recent" style="padding:8px 0;">
            <div style="padding:20px 16px;text-align:center;font-size:11px;color:#A3A3A3;">Aucun document</div>
          </div>
        </div>
        <div style="background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;overflow:hidden;">
          <div style="padding:12px 16px;border-bottom:0.5px solid #E5E5E5;display:flex;justify-content:space-between;">
            <span style="font-size:11px;font-weight:600;color:#0A0A0A;">Activité récente</span>
            <span onclick="showPage('redaction')" style="font-size:10px;color:#6B7280;cursor:pointer;">Rédiger</span>
          </div>
          <div id="dash-activite-recent" style="padding:8px 0;">
            <div style="padding:20px 16px;text-align:center;font-size:11px;color:#A3A3A3;">Générez votre premier acte</div>
          </div>
        </div>
      </div>'''

# Trouver le contenu interne du dashboard (entre la div et fin)
dash_open  = '<div class="page active" id="page-dashboard">'
dash_close = '</div><!-- fin page-dashboard -->'
idx_open  = content.find(dash_open)
idx_close = content.find(dash_close)

if idx_open > 0 and idx_close > 0:
    # Remplacer le contenu entre les deux marqueurs
    content = content[:idx_open + len(dash_open)] + '\n' + NOUVEAU_DASHBOARD_CONTENU + '\n    ' + content[idx_close:]
    print("8. Nouveau dashboard inséré")
else:
    print("8. WARN: dashboard markers non trouvés")

# ════════════════════════════════════════════════════════════════════
# 9. AJOUTER JS DASHBOARD
# ════════════════════════════════════════════════════════════════════
JS_DASHBOARD = """
// ── NOUVEAU DASHBOARD ─────────────────────────────────────────────
let ACTES_GENERES_HIST = [];

async function chargerDashboard() {
  const now   = new Date();
  const heure = now.getHours();
  const salut = heure < 12 ? 'Bonjour' : heure < 18 ? 'Bon après-midi' : 'Bonsoir';
  const jours = ['dimanche','lundi','mardi','mercredi','jeudi','vendredi','samedi'];
  const mois  = ['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];
  const dateStr = `${jours[now.getDay()]} ${now.getDate()} ${mois[now.getMonth()]} ${now.getFullYear()}`;

  const grEl = document.getElementById('dash-greeting');
  const dtEl = document.getElementById('dash-date');
  if (dtEl) dtEl.textContent = dateStr;

  // Nom avocat
  try {
    const profil = await apiFetch('/profil', 'GET');
    const nom = profil?.display_name || profil?.full_name || 'Maître';
    if (grEl) grEl.textContent = salut + ', ' + nom;
  } catch(e) {
    if (grEl) grEl.textContent = salut + ', Maître';
  }

  // Stats
  try {
    const stats = await apiFetch('/stats', 'GET');
    if (stats) {
      const kD = document.getElementById('kpi-docs');
      const kDo = document.getElementById('kpi-dossiers');
      const kA = document.getElementById('kpi-actes');
      if (kD)  kD.textContent  = stats.documents || 0;
      if (kDo) kDo.textContent = stats.dossiers  || 0;
      if (kA)  kA.textContent  = ACTES_GENERES_HIST.length;
    }
  } catch(e) {}

  // Abonnement
  try {
    const abo = await apiFetch('/abonnement/statut', 'GET');
    const alert = document.getElementById('dash-alert');
    const kJ = document.getElementById('kpi-jours');
    if (abo) {
      const j = abo.jours_restants || 0;
      if (kJ) kJ.textContent = abo.actif ? j : '0';
      if (alert && j <= 7 && abo.actif) {
        alert.textContent = `Attention : votre abonnement expire dans ${j} jour${j > 1 ? 's' : ''}.`;
        alert.style.display = 'block';
      }
    }
  } catch(e) {}

  // Documents récents
  try {
    const docs = await apiFetch('/liste_documents', 'GET');
    const container = document.getElementById('dash-docs-recent');
    if (container && docs && docs.length) {
      container.innerHTML = docs.slice(0, 5).map(d => {
        const nom  = (d.nom || d.filename || 'Document').replace('.pdf','');
        const date = d.created_at ? new Date(d.created_at).toLocaleDateString('fr-FR') : '';
        return `<div onclick="showPage('bibliotheque')" style="display:flex;align-items:center;gap:10px;padding:8px 16px;border-bottom:0.5px solid #F5F5F5;cursor:pointer;">
          <div style="width:6px;height:6px;border-radius:50%;background:#22C55E;flex-shrink:0;"></div>
          <div style="flex:1;min-width:0;">
            <div style="font-size:12px;font-weight:500;color:#0A0A0A;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${nom}</div>
            <div style="font-size:10px;color:#A3A3A3;margin-top:1px;">PDF</div>
          </div>
          <div style="font-size:10px;color:#A3A3A3;">${date}</div>
        </div>`;
      }).join('');
    }
  } catch(e) {}

  // Activité actes générés
  const actContainer = document.getElementById('dash-activite-recent');
  if (actContainer && ACTES_GENERES_HIST.length) {
    actContainer.innerHTML = ACTES_GENERES_HIST.slice(-5).reverse().map(a =>
      `<div onclick="showPage('redaction')" style="display:flex;align-items:center;gap:10px;padding:8px 16px;border-bottom:0.5px solid #F5F5F5;cursor:pointer;">
        <div style="width:6px;height:6px;border-radius:50%;background:#1A6B9A;flex-shrink:0;"></div>
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:500;color:#0A0A0A;">${a.nom}</div>
          <div style="font-size:10px;color:#A3A3A3;">Acte généré</div>
        </div>
        <div style="font-size:10px;color:#A3A3A3;">${a.heure}</div>
      </div>`
    ).join('');
  }
}

function enregistrerActeGenere(nomActe) {
  const heure = new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'});
  ACTES_GENERES_HIST.push({nom: nomActe, heure});
  const kA = document.getElementById('kpi-actes');
  if (kA) kA.textContent = ACTES_GENERES_HIST.length;
}
"""

# Insérer avant le dernier </script>
idx_script = content.rfind('</script>')
if idx_script > 0 and 'chargerDashboard' not in content:
    content = content[:idx_script] + JS_DASHBOARD + content[idx_script:]
    print("9. JS dashboard ajouté")

# ════════════════════════════════════════════════════════════════════
# 10. APPELER chargerDashboard au chargement et dans showPage
# ════════════════════════════════════════════════════════════════════
# Dans init()
if 'await chargerStats();' in content and 'await chargerDashboard();' not in content:
    content = content.replace(
        'await chargerStats();',
        'await chargerStats();\n  await chargerDashboard();',
        1
    )
    print("10. chargerDashboard dans init() OK")

# Dans showPage
old_show = "  if (p === 'bibliotheque') chargerDocsBib();"
new_show = "  if (p === 'bibliotheque') chargerDocsBib();\n  if (p === 'dashboard') chargerDashboard();"
if old_show in content and "if (p === 'dashboard') chargerDashboard();" not in content:
    content = content.replace(old_show, new_show)
    print("10. chargerDashboard dans showPage OK")

# ════════════════════════════════════════════════════════════════════
# VERIFICATION FINALE
# ════════════════════════════════════════════════════════════════════
pages_apres = re.findall(r'id="page-([^"]+)"', content)
print(f"\nPages après : {pages_apres}")

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("\npatch_final.py appliqué avec succès")