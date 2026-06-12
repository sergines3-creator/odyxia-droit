#!/usr/bin/env python3
# patch_safe.py — Modifications sures uniquement (sans toucher au HTML dashboard)

import re

with open('/root/odyxia-droit/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

pages_avant = re.findall(r'id="page-([^"]+)"', content)
print(f"Pages avant : {pages_avant}")

# 1. Supprimer nav-profil (lignes contenant nav-profil et son contenu)
lines = content.split('\n')
new_lines = []
skip_count = 0
for i, line in enumerate(lines):
    if 'id="nav-profil"' in line:
        skip_count = 6  # sauter 6 lignes (le bloc nav-item complet)
    if skip_count > 0:
        skip_count -= 1
        continue
    new_lines.append(line)
content = '\n'.join(new_lines)
print("1. nav-profil supprimé")

# 2. Supprimer page-profil
idx_profil_start = content.find('<div class="page" id="page-profil">')
idx_profil_end   = content.find('</div><!-- fin page-profil -->')
if idx_profil_start > 0 and idx_profil_end > 0:
    idx_profil_end += len('</div><!-- fin page-profil -->')
    content = content[:idx_profil_start] + content[idx_profil_end:]
    print("2. page-profil supprimée")

# 3. Corriger showPage
content = content.replace(
    "document.getElementById('nav-' + p).classList.add('active');",
    "const _navEl = document.getElementById('nav-' + p); if (_navEl) _navEl.classList.add('active');"
)
content = content.replace("  if (p === 'profil') chargerProfil();", "")
print("3. showPage corrigé")

# 4. Supprimer OHADA CMR
content = content.replace(
    '<span class="hdr-pays" id="hdr-pays">OHADA · CMR</span>',
    '<span class="hdr-pays" id="hdr-pays"></span>'
)
print("4. OHADA CMR supprimé")

# 5. Simplifier sidebar avocat
old_sb = 'Chargement...</div>\n  <div id="sb-avocat-barreau" style="font-size:10px;color:#6B6B6B;margin-top:2px;">Barreau</div>'
if old_sb in content:
    content = content.replace(old_sb, 'Chargement...</div>')
    print("5. Sidebar simplifié")

# 6. Afficher nom avocat dans entete
old_prof = """    const sbNomEl = document.getElementById('sb-avocat-nom');
    const sbBarEl = document.getElementById('sb-avocat-barreau');
    if (sbNomEl) sbNomEl.textContent = u.display_name || u.full_name || 'Maître';
    if (sbBarEl) sbBarEl.textContent = a.barreau || 'Barreau';"""
new_prof = """    const sbNomEl = document.getElementById('sb-avocat-nom');
    const hdrPaysEl = document.getElementById('hdr-pays');
    const _nomAv = u.display_name || u.full_name || 'Maître';
    if (sbNomEl) sbNomEl.textContent = _nomAv;
    if (hdrPaysEl) hdrPaysEl.textContent = 'Maître ' + _nomAv;"""
if old_prof in content:
    content = content.replace(old_prof, new_prof)
    print("6. Nom avocat dans entete OK")

# 7. Corriger scroll Quill
content = content.replace(
    'id="redac-result-body" style="padding:0;overflow:hidden;"',
    'id="redac-result-body" style="padding:0;overflow:auto;"'
)
print("7. Scroll Quill OK")

# 8. Corriger init() — supprimer references aux anciens elements
old_init = """  document.getElementById('dash-greeting').textContent = greeting + ', Maître';
  document.getElementById('dash-date').textContent = now.toLocaleDateString('fr-FR', {weekday:'long',day:'numeric',month:'long',year:'numeric'});"""
new_init = """  const _grEl = document.getElementById('dash-greeting');
  const _dtEl = document.getElementById('dash-date');
  if (_grEl) _grEl.textContent = greeting + ', Maître';
  if (_dtEl) _dtEl.textContent = now.toLocaleDateString('fr-FR', {weekday:'long',day:'numeric',month:'long',year:'numeric'});"""
if old_init in content:
    content = content.replace(old_init, new_init)
    print("8. init() corrigé")

# 9. Supprimer chargerProfil de init()
content = content.replace("  await chargerProfil();\n", "")
print("9. chargerProfil() retiré de init()")

# 10. Guard initQuill
if "function initQuill() {\n  if (!document.getElementById('quill-editor')) return;" not in content:
    content = content.replace(
        'function initQuill() {',
        "function initQuill() {\n  if (!document.getElementById('quill-editor')) return;",
        1
    )
    print("10. initQuill guard OK")

# Verification finale
pages_apres = re.findall(r'id="page-([^"]+)"', content)
print(f"\nPages apres : {pages_apres}")

with open('/root/odyxia-droit/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("patch_safe.py applique avec succes")