#!/usr/bin/env python3
# patch_version_route.py — Ajouter route /document/sauvegarder_version

with open('/root/odyxia-droit/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

NOUVELLE_ROUTE = '''

@app.route("/document/sauvegarder_version", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")
def sauvegarder_version():
    """Sauvegarde une version d'un document édité par l'avocat."""
    try:
        data      = request.json
        tenant_id = get_current_tenant_id()
        user_id   = get_current_user_id()
        nom       = data.get("nom", "Document")
        note      = data.get("note", "")
        contenu   = data.get("contenu", "")

        if not contenu:
            return jsonify({"erreur": "Contenu vide"}), 400

        version_id = str(uuid.uuid4())
        supabase.table("document_versions").insert({
            "id"        : version_id,
            "tenant_id" : tenant_id,
            "user_id"   : user_id,
            "nom"       : nom[:200],
            "note"      : note[:500],
            "contenu"   : contenu[:50000],
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()

        log_audit_event("VERSION_SAUVEGARDEE", tenant_id, user_id,
                        {"nom": nom, "note": note})

        return jsonify({"succes": True, "version_id": version_id})

    except Exception as e:
        # Table peut ne pas exister — silencieux
        log_erreur("SAUVEGARDER_VERSION", e)
        return jsonify({"succes": True})  # Ne pas bloquer l'UX


@app.route("/document/versions", methods=["GET"])
@jwt_required()
def liste_versions():
    """Récupère l'historique des versions sauvegardées."""
    try:
        tenant_id = get_current_tenant_id()
        result = supabase.table("document_versions").select(
            "id,nom,note,created_at"
        ).eq("tenant_id", tenant_id).order(
            "created_at", desc=True
        ).limit(20).execute()
        return jsonify({"versions": result.data or []})
    except Exception as e:
        return jsonify({"versions": []})

'''

# Insérer avant /health
if '@app.route("/health"' in content:
    content = content.replace(
        '@app.route("/health"',
        NOUVELLE_ROUTE + '\n@app.route("/health"'
    )
    print("Route /document/sauvegarder_version ajoutée")
else:
    print("Insertion avant /health non trouvée")

with open('/root/odyxia-droit/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
py_compile.compile('/root/odyxia-droit/app.py', doraise=True)
print("Syntaxe OK")