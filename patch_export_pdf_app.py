#!/usr/bin/env python3
# patch_export_pdf_app.py — Modifier /export_pdf pour utiliser logo/signature base64

with open('/root/odyxia-droit/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """        try:
            user_id = get_current_user_id()
            print(f"[PDF] user_id={user_id}")
            profil = supabase.table("users").select("display_name, full_name").eq("id", user_id).execute()
            if profil.data:
                nom_avocat = profil.data[0].get("display_name") or profil.data[0].get("full_name") or "Maitre"
            avocat_row = supabase.table("avocats").select("barreau, pays, logo_url, tampon_url").eq("user_id", user_id).execute()
            print(f"[PDF] avocat_row={avocat_row.data}")
            if avocat_row.data:
                cabinet = avocat_row.data[0].get("barreau", "") + " — " + avocat_row.data[0].get("pays", "")
                logo_url = avocat_row.data[0].get("logo_url")
                tampon_url = avocat_row.data[0].get("tampon_url")
                print(f"[PDF] logo_url={logo_url}")
        except Exception as e_profil:
            print(f"[PDF] Erreur profil : {e_profil}")"""

new = """        # Données envoyées depuis le modal export
        nom_avocat = data.get("nom_avocat", "Maitre").strip() or "Maitre"
        barreau    = data.get("barreau", "").strip()
        ville      = data.get("ville", "Cameroun").strip()
        logo_b64   = data.get("logo_b64")    # data:image/png;base64,...
        sig_b64    = data.get("signature_b64")

        if barreau:
            cabinet = barreau + (" — " + ville if ville else "")
        else:
            cabinet = ville or "Cameroun"

        logo_url   = None
        tampon_url = None"""

if old in content:
    content = content.replace(old, new)
    print("Fix 1 : profil depuis modal OK")
else:
    print("Fix 1 non trouvé")

# Modifier la partie qui télécharge le logo depuis URL → utiliser base64 directement
old2 = """        if logo_url:
            try:
                from reportlab.platypus import Image as RLImage
                import urllib.request
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_logo:
                    urllib.request.urlretrieve(logo_url, tmp_logo.name)
                    logo_img = RLImage(tmp_logo.name, width=80, height=80)
                    logo_img.hAlign = 'CENTER'
                    elements.append(logo_img)
                    elements.append(Spacer(1, 8))
                    os.unlink(tmp_logo.name)
            except Exception as e_logo:
                print(f"[PDF] Erreur logo : {e_logo}")"""

new2 = """        if logo_b64:
            try:
                from reportlab.platypus import Image as RLImage
                import base64 as _b64
                # Décoder le base64 (data:image/png;base64,XXX)
                if ',' in logo_b64:
                    logo_b64_data = logo_b64.split(',', 1)[1]
                else:
                    logo_b64_data = logo_b64
                logo_bytes = _b64.b64decode(logo_b64_data)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_logo:
                    tmp_logo.write(logo_bytes)
                    tmp_logo.flush()
                    logo_img = RLImage(tmp_logo.name, width=80, height=80)
                    logo_img.hAlign = 'CENTER'
                    elements.append(logo_img)
                    elements.append(Spacer(1, 8))
                os.unlink(tmp_logo.name)
            except Exception as e_logo:
                print(f"[PDF] Erreur logo b64 : {e_logo}")"""

if old2 in content:
    content = content.replace(old2, new2)
    print("Fix 2 : logo base64 OK")
else:
    print("Fix 2 non trouvé — recherche partielle")
    idx = content.find("if logo_url:")
    print(f"  logo_url trouvé à ligne ~{content[:idx].count(chr(10))}")

# Modifier la signature (tampon_url) pour utiliser sig_b64
old3 = """        if tampon_url:
            try:
                from reportlab.platypus import Image as RLImage
                import urllib.request
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_tampon:
                    urllib.request.urlretrieve(tampon_url, tmp_tampon.name)
                    tampon_img = RLImage(tmp_tampon.name, width=100, height=100)
                    tampon_img.hAlign = 'RIGHT'
                    elements.append(Spacer(1, 8))
                    elements.append(tampon_img)
                    os.unlink(tmp_tampon.name)
            except Exception:
                pass"""

new3 = """        if sig_b64:
            try:
                from reportlab.platypus import Image as RLImage
                import base64 as _b64s
                if ',' in sig_b64:
                    sig_b64_data = sig_b64.split(',', 1)[1]
                else:
                    sig_b64_data = sig_b64
                sig_bytes = _b64s.b64decode(sig_b64_data)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                    tmp_sig.write(sig_bytes)
                    tmp_sig.flush()
                    sig_img = RLImage(tmp_sig.name, width=120, height=60)
                    sig_img.hAlign = 'RIGHT'
                    elements.append(Spacer(1, 8))
                    elements.append(sig_img)
                os.unlink(tmp_sig.name)
            except Exception as e_sig:
                print(f"[PDF] Erreur signature b64 : {e_sig}")"""

if old3 in content:
    content = content.replace(old3, new3)
    print("Fix 3 : signature base64 OK")
else:
    print("Fix 3 non trouvé")
    idx = content.find("if tampon_url:")
    if idx > 0:
        print(f"  tampon_url trouvé à ligne ~{content[:idx].count(chr(10))}")
        print(repr(content[idx:idx+200]))

with open('/root/odyxia-droit/app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("patch_export_pdf_app.py appliqué")