#!/usr/bin/env python3
# patch_dashboard.py — Nouveau tableau de bord avocat

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. CSS du nouveau dashboard ───────────────────────────────────────────────
CSS_DASH = """
/* ── NOUVEAU DASHBOARD ─────────────────────────────────────────────── */
.dash-welcome-new{
  padding:20px 24px 0;
}
.dash-greeting{
  font-size:18px;font-weight:600;color:#0A0A0A;
  font-family:var(--serif,Georgia,serif);
}
.dash-date-str{font-size:11px;color:#A3A3A3;margin-top:2px;}
.dash-abonnement{
  display:inline-flex;align-items:center;gap:6px;
  margin-top:8px;padding:4px 10px;border-radius:20px;
  background:#F0FDF4;border:0.5px solid #86EFAC;
  font-size:10px;font-weight:500;color:#16A34A;
}
.dash-abonnement.warn{
  background:#FFF7ED;border-color:#FCD34D;color:#D97706;
}
.dash-abonnement.expired{
  background:#FEF2F2;border-color:#FCA5A5;color:#DC2626;
}
.dash-kpis{
  display:grid;grid-template-columns:repeat(4,1fr);gap:12px;
  padding:16px 24px;
}
.dash-kpi{
  background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;
  padding:14px 16px;cursor:default;
}
.dash-kpi-val{
  font-size:24px;font-weight:700;color:#0A0A0A;
  font-family:var(--serif,Georgia,serif);
}
.dash-kpi-label{font-size:10px;color:#A3A3A3;margin-top:3px;font-weight:500;}
.dash-kpi-sub{font-size:10px;color:#6B7280;margin-top:2px;}
.dash-shortcuts{
  display:flex;gap:8px;padding:0 24px 16px;flex-wrap:wrap;
}
.dash-shortcut{
  display:flex;align-items:center;gap:6px;
  padding:8px 14px;border-radius:6px;border:0.5px solid #E5E5E5;
  background:#fff;cursor:pointer;font-size:12px;font-weight:500;
  color:#0A0A0A;transition:all .15s;white-space:nowrap;
}
.dash-shortcut:hover{background:#0A0A0A;color:#fff;border-color:#0A0A0A;}
.dash-two-col{
  display:grid;grid-template-columns:1fr 1fr;gap:12px;
  padding:0 24px 24px;
}
.dash-panel{
  background:#fff;border:0.5px solid #E5E5E5;border-radius:8px;
  overflow:hidden;
}
.dash-panel-hdr{
  padding:12px 16px;border-bottom:0.5px solid #E5E5E5;
  display:flex;justify-content:space-between;align-items:center;
}
.dash-panel-title{font-size:11px;font-weight:600;color:#0A0A0A;}
.dash-panel-link{font-size:10px;color:#6B7280;cursor:pointer;}
.dash-panel-link:hover{color:#0A0A0A;}
.dash-panel-body{padding:8px 0;}
.dash-item{
  display:flex;align-items:center;gap:10px;
  padding:8px 16px;border-bottom:0.5px solid #F5F5F5;
  cursor:pointer;transition:background .1s;
}
.dash-item:last-child{border-bottom:none;}
.dash-item:hover{background:#F9F9F9;}
.dash-item-dot{
  width:6px;height:6px;border-radius:50%;
  background:#E5E5E5;flex-shrink:0;
}
.dash-item-dot.active{background:#22C55E;}
.dash-item-dot.warn{background:#F59E0B;}
.dash-item-info{flex:1;min-width:0;}
.dash-item-name{
  font-size:12px;font-weight:500;color:#0A0A0A;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.dash-item-sub{font-size:10px;color:#A3A3A3;margin-top:1px;}
.dash-item-date{font-size:10px;color:#A3A3A3;flex-shrink:0;}
.dash-empty{
  padding:20px 16px;text-align:center;
  font-size:11px;color:#A3A3A3;
}
.dash-alert{
  margin:0 24px 12px;padding:10px 14px;
  border-radius:6px;border:0.5px solid #FCD34D;
  background:#FFFBEB;font-size:11px;color:#92400E;
  display:none;
}
.dash-alert.visible{display:block;}
"""

if CSS_DASH not in content:
    content = content.replace('</style>', CSS_DASH + '\n</style>', 1)
    print("CSS dashboard OK")

# ── 2. Remplacer le contenu de page-dashboard ────────────────────────────────
old_dash = content[content.find('<div class="page active" id="page-dashboard">'):
                   content.find('</div><!-- fin page-dashboard -->') + len('</div><!-- fin page-dashboard -->')]

new_dash = '''<div class="page active" id="page-dashboard">
  <!-- Alerte abonnement -->
  <div class="dash-alert" id="dash-alert"></div>

  <!-- Bienvenue -->
  <div class="dash-welcome-new">
    <div class="dash-greeting" id="dash-greeting-new">Bonjour, Maître</div>
    <div class="dash-date-str" id="dash-date-new"></div>
    <div class="dash-abonnement" id="dash-abo-badge" style="display:none;"></div>
  </div>

  <!-- KPIs -->
  <div class="dash-kpis">
    <div class="dash-kpi">
      <div class="dash-kpi-val" id="kpi-docs">—</div>
      <div class="dash-kpi-label">Documents indexés</div>
    </div>
    <div class="dash-kpi">
      <div class="dash-kpi-val" id="kpi-dossiers">—</div>
      <div class="dash-kpi-label">Dossiers actifs</div>
    </div>
    <div class="dash-kpi">
      <div class="dash-kpi-val" id="kpi-actes">—</div>
      <div class="dash-kpi-label">Actes générés</div>
      <div class="dash-kpi-sub">ce mois</div>
    </div>
    <div class="dash-kpi">
      <div class="dash-kpi-val" id="kpi-jours">—</div>
      <div class="dash-kpi-label">Jours d'abonnement</div>
      <div class="dash-kpi-sub">restants</div>
    </div>
  </div>

  <!-- Raccourcis -->
  <div class="dash-shortcuts">
    <div class="dash-shortcut" onclick="showPage('bibliotheque')">Uploader un document</div>
    <div class="dash-shortcut" onclick="showPage('redaction')">Rédiger un acte</div>
    <div class="dash-shortcut" onclick="showPage('analyse')">Analyser un document</div>
    <div class="dash-shortcut" onclick="showPage('dossiers')">Nouveau dossier</div>
    <div class="dash-shortcut" onclick="showPage('chat')">Poser une question</div>
  </div>

  <!-- Deux colonnes -->
  <div class="dash-two-col">
    <!-- Documents récents -->
    <div class="dash-panel">
      <div class="dash-panel-hdr">
        <span class="dash-panel-title">Documents récents</span>
        <span class="dash-panel-link" onclick="showPage('bibliotheque')">Voir tout</span>
      </div>
      <div class="dash-panel-body" id="dash-docs-recent">
        <div class="dash-empty">Aucun document</div>
      </div>
    </div>

    <!-- Actes récents -->
    <div class="dash-panel">
      <div class="dash-panel-hdr">
        <span class="dash-panel-title">Activité récente</span>
        <span class="dash-panel-link" onclick="showPage('redaction')">Rédiger</span>
      </div>
      <div class="dash-panel-body" id="dash-activite-recent">
        <div class="dash-empty">Aucune activité</div>
      </div>
    </div>
  </div>
</div><!-- fin page-dashboard -->'''

if old_dash and old_dash in content:
    content = content.replace(old_dash, new_dash)
    print("HTML dashboard remplacé")
else:
    print("WARN: bloc dashboard non trouvé — insertion manuelle")

# ── 3. JavaScript du nouveau dashboard ───────────────────────────────────────
JS_DASH = """
// ══════════════════════════════════════════════════════════════════════════════
// NOUVEAU DASHBOARD
// ══════════════════════════════════════════════════════════════════════════════

// Historique local des actes générés (en session)
let ACTES_GENERES_HIST = [];

async function chargerDashboard() {
  // Date et heure
  const now  = new Date();
  const heure = now.getHours();
  const salut = heure < 12 ? 'Bonjour' : heure < 18 ? 'Bon après-midi' : 'Bonsoir';
  const jours = ['dimanche','lundi','mardi','mercredi','jeudi','vendredi','samedi'];
  const mois  = ['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];
  const dateStr = `${jours[now.getDay()]} ${now.getDate()} ${mois[now.getMonth()]} ${now.getFullYear()}`;

  const greetEl = document.getElementById('dash-greeting-new');
  const dateEl  = document.getElementById('dash-date-new');
  if (greetEl) {
    // Récupérer le nom de l'avocat
    try {
      const profil = await apiFetch('/profil', 'GET');
      const nom = profil?.display_name || profil?.full_name || 'Maître';
      greetEl.textContent = `${salut}, ${nom}`;
    } catch(e) {
      greetEl.textContent = `${salut}, Maître`;
    }
  }
  if (dateEl) dateEl.textContent = dateStr;

  // Abonnement
  try {
    const abo = await apiFetch('/abonnement/statut', 'GET');
    const badge = document.getElementById('dash-abo-badge');
    const alert = document.getElementById('dash-alert');
    if (abo && badge) {
      badge.style.display = 'inline-flex';
      const j = abo.jours_restants || 0;
      if (!abo.actif) {
        badge.className = 'dash-abonnement expired';
        badge.textContent = 'Abonnement expiré';
        if (alert) { alert.textContent = 'Votre abonnement a expiré. Contactez-nous pour renouveler.'; alert.classList.add('visible'); }
      } else if (j <= 7) {
        badge.className = 'dash-abonnement warn';
        badge.textContent = `${j} jour${j > 1 ? 's' : ''} restant${j > 1 ? 's' : ''}`;
        if (alert) { alert.textContent = `Attention : votre abonnement expire dans ${j} jour${j > 1 ? 's' : ''}. Pensez à renouveler.`; alert.classList.add('visible'); }
      } else {
        badge.className = 'dash-abonnement';
        badge.textContent = `${j} jours restants`;
      }
      const kpiJ = document.getElementById('kpi-jours');
      if (kpiJ) kpiJ.textContent = abo.actif ? j : '0';
    }
  } catch(e) {}

  // Stats
  try {
    const stats = await apiFetch('/stats', 'GET');
    if (stats) {
      const kpiD = document.getElementById('kpi-docs');
      const kpiDos = document.getElementById('kpi-dossiers');
      const kpiA = document.getElementById('kpi-actes');
      if (kpiD)   kpiD.textContent   = stats.documents || 0;
      if (kpiDos) kpiDos.textContent = stats.dossiers  || 0;
      if (kpiA)   kpiA.textContent   = ACTES_GENERES_HIST.length || 0;
    }
  } catch(e) {}

  // Documents récents
  try {
    const docs = await apiFetch('/liste_documents', 'GET');
    const container = document.getElementById('dash-docs-recent');
    if (container && docs && docs.length) {
      container.innerHTML = docs.slice(0, 5).map(d => {
        const nom  = d.nom || d.filename || 'Document';
        const date = d.created_at ? new Date(d.created_at).toLocaleDateString('fr-FR') : '';
        return `<div class="dash-item" onclick="showPage('bibliotheque')">
          <div class="dash-item-dot active"></div>
          <div class="dash-item-info">
            <div class="dash-item-name">${nom.replace('.pdf','')}</div>
            <div class="dash-item-sub">PDF · ${d.storage_tier || 'hot'}</div>
          </div>
          <div class="dash-item-date">${date}</div>
        </div>`;
      }).join('');
    }
  } catch(e) {}

  // Activité récente (actes générés en session)
  const actContainer = document.getElementById('dash-activite-recent');
  if (actContainer) {
    if (ACTES_GENERES_HIST.length) {
      actContainer.innerHTML = ACTES_GENERES_HIST.slice(-5).reverse().map(a => `
        <div class="dash-item" onclick="showPage('redaction')">
          <div class="dash-item-dot" style="background:#1A6B9A;"></div>
          <div class="dash-item-info">
            <div class="dash-item-name">${a.nom}</div>
            <div class="dash-item-sub">Acte généré</div>
          </div>
          <div class="dash-item-date">${a.heure}</div>
        </div>`).join('');
    } else {
      actContainer.innerHTML = '<div class="dash-empty">Générez votre premier acte</div>';
    }
  }
}

// Enregistrer chaque acte généré dans l'historique
function enregistrerActeGenere(nomActe) {
  const heure = new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'});
  ACTES_GENERES_HIST.push({nom: nomActe, heure});
  // Mettre à jour le KPI
  const kpiA = document.getElementById('kpi-actes');
  if (kpiA) kpiA.textContent = ACTES_GENERES_HIST.length;
}
"""

idx_script = content.rfind('</script>')
if idx_script > 0:
    content = content[:idx_script] + "\n" + JS_DASH + "\n" + content[idx_script:]
    print("JS dashboard OK")

# ── 4. Appeler chargerDashboard au chargement ────────────────────────────────
# Trouver l'init existante
if 'chargerDocsBib()' in content and 'chargerDashboard()' not in content:
    content = content.replace(
        'chargerDocsBib()',
        'chargerDocsBib();\n  chargerDashboard()',
        1
    )
    print("chargerDashboard() ajouté à l'init")

# ── 5. Appeler enregistrerActeGenere après génération ────────────────────────
old_toast = "showToast('Document généré avec succès');"
new_toast = """showToast('Document généré avec succès');
    enregistrerActeGenere(ACTE_ACTIF?.nom || 'Document');"""

if old_toast in content:
    content = content.replace(old_toast, new_toast)
    print("enregistrerActeGenere() ajouté")

# ── 6. Appeler chargerDashboard quand on revient sur le dashboard ─────────────
old_show = "function showPage(page) {"
new_show = """function showPage(page) {
  if (page === 'dashboard') { setTimeout(chargerDashboard, 100); }"""

if old_show in content and 'if (page === ' not in content[content.find(old_show):content.find(old_show)+200]:
    content = content.replace(old_show, new_show)
    print("Refresh dashboard au changement de page OK")

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("patch_dashboard.py appliqué")