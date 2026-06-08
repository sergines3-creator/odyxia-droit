#!/usr/bin/env python3
# patch_app.py
# Script de patch automatique — applique les 6 réformes sur app.py ODYXIA Droit
#
# Usage :
#   cd C:\odyxia\odyxia-droit
#   python patch_app.py
#
# Ce script :
#   1. Lit app.py
#   2. Applique les 6 réformes
#   3. Sauvegarde app.py.backup (sécurité)
#   4. Écrit le nouveau app.py
#   5. Vérifie la syntaxe Python avant de remplacer

import os
import re
import shutil
import py_compile
import tempfile
import sys

APP_PATH    = "app.py"
BACKUP_PATH = "app.py.backup"

def lire():
    with open(APP_PATH, "r", encoding="utf-8") as f:
        return f.read()

def ecrire(content):
    with open(APP_PATH, "w", encoding="utf-8") as f:
        f.write(content)

def backup():
    shutil.copy2(APP_PATH, BACKUP_PATH)
    print(f"  Backup : {BACKUP_PATH}")

def verifier_syntaxe(content):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        py_compile.compile(tmp_path, doraise=True)
        return True
    except py_compile.PyCompileError as e:
        print(f"  [ERREUR SYNTAXE] {e}")
        return False
    finally:
        os.unlink(tmp_path)


# ══════════════════════════════════════════════════════════════════════
# RÉFORME 1 — SBERT remplace Voyage AI
# ══════════════════════════════════════════════════════════════════════

REFORM_1_CODE = '''
# ─── SBERT LOCAL (remplace Voyage AI) ────────────────────────────────────────
# RÉFORME 1 : SBERT local — gratuit, tourne sur Hetzner
# Remplace Voyage AI ($0.10/M tokens) par SBERT (~420Mo RAM, $0)
#
# POINT CRITIQUE — dimension embeddings :
# Voyage-law-2 → 1024 dims | SBERT → 384 dims
# Les anciens chunks ont des embeddings 1024 dims.
# Re-vectoriser tous les chunks :
#   python3 re_vectoriser.py
#
# Ajouter dans requirements.txt : sentence-transformers>=2.2.0

_sbert_model = None

def get_sbert_model():
    """Charge SBERT une seule fois en mémoire (lazy loading)."""
    global _sbert_model
    if _sbert_model is None:
        from sentence_transformers import SentenceTransformer
        print("[SBERT] Chargement paraphrase-multilingual-MiniLM-L12-v2...")
        _sbert_model = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2"
        )
        print(f"[SBERT] Prêt — dim={_sbert_model.get_sentence_embedding_dimension()}")
    return _sbert_model

def get_query_embedding(question: str):
    """Génère l embedding d une question via SBERT local."""
    try:
        model = get_sbert_model()
        embedding = model.encode(
            question[:512], normalize_embeddings=True, show_progress_bar=False
        )
        return embedding.tolist()
    except Exception as e:
        print(f"[SBERT] Erreur query : {e}")
        return None

def _vectoriser_document_sbert_batch(textes: list):
    """Vectorise un batch de textes en une seule passe."""
    try:
        model = get_sbert_model()
        embeddings = model.encode(
            [t[:512] for t in textes],
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return [e.tolist() for e in embeddings]
    except Exception as e:
        print(f"[SBERT] Erreur batch : {e}")
        return [None] * len(textes)

def _vectoriser_document(doc_id: str, tenant_id: str):
    """Vectorise tous les chunks d un document avec SBERT batch."""
    try:
        result = supabase.table("chunks").select(
            "id,content,contenu_index"
        ).eq("document_id", doc_id).is_("embedding", "null").execute()
        chunks = result.data
        if not chunks:
            return
        textes = []
        for c in chunks:
            texte = c.get("contenu_index") or c.get("content") or ""
            if texte.startswith("ENC:"):
                texte = "document juridique confidentiel"
            textes.append(texte.strip() or "document juridique")
        embeddings = _vectoriser_document_sbert_batch(textes)
        BATCH = 50
        for i in range(0, len(chunks), BATCH):
            lot = chunks[i:i + BATCH]
            for chunk, emb in zip(lot, embeddings[i:i + BATCH]):
                if emb:
                    supabase.table("chunks").update(
                        {"embedding": emb}
                    ).eq("id", chunk["id"]).execute()
        print(f"[SBERT] Vectorisation terminée {doc_id[:8]} — {len(chunks)} chunks")
    except Exception as e:
        print(f"[SBERT] Erreur vectorisation : {e}")
'''

# ══════════════════════════════════════════════════════════════════════
# RÉFORME 2 — Chunking sémantique
# ══════════════════════════════════════════════════════════════════════

REFORM_2_CODE = '''
def _chunker_semantique(texte: str, taille: int = 400, overlap: int = 50) -> list:
    """
    Réforme 2 — Chunking sémantique avec chevauchement.
    Remplace le découpage fixe par 800 chars.
    taille : mots cibles par chunk | overlap : mots de chevauchement
    """
    if not texte or not texte.strip():
        return []
    texte = re.sub(r\'\\n{3,}\', \'\\n\\n\', texte)
    texte = re.sub(r\' {2,}\', \' \', texte)
    paragraphes = [p.strip() for p in texte.split(\'\\n\\n\') if p.strip()]
    if not paragraphes:
        paragraphes = [texte.strip()]

    chunks  = []
    buffer  = []
    nb_mots = 0

    for para in paragraphes:
        mots_para = para.split()
        if len(mots_para) > taille * 1.5:
            phrases = re.split(r\'(?<=[.!?;])\\s+\', para)
            for phrase in phrases:
                mots_phrase = phrase.split()
                if not mots_phrase:
                    continue
                if nb_mots + len(mots_phrase) > taille and buffer:
                    ct = \' \'.join(buffer)
                    if len(ct) > 80:
                        chunks.append(ct)
                    buffer  = buffer[-overlap:] if overlap else []
                    nb_mots = len(buffer)
                buffer  += mots_phrase
                nb_mots += len(mots_phrase)
        else:
            if nb_mots + len(mots_para) > taille and buffer:
                ct = \' \'.join(buffer)
                if len(ct) > 80:
                    chunks.append(ct)
                buffer  = buffer[-overlap:] if overlap else []
                nb_mots = len(buffer)
            buffer  += mots_para
            nb_mots += len(mots_para)

    if buffer:
        ct = \' \'.join(buffer)
        if len(ct) > 80:
            chunks.append(ct)
    return chunks
'''

# ══════════════════════════════════════════════════════════════════════
# RÉFORME 3 — Cache
# ══════════════════════════════════════════════════════════════════════

REFORM_3_CODE = '''
# ─── CACHE (Réforme 3) ────────────────────────────────────────────────────────
_cache_mem    = {}
_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client if _redis_client is not False else None
    try:
        import redis as _redis
        r = _redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            db=0, socket_timeout=1, socket_connect_timeout=1
        )
        r.ping()
        _redis_client = r
        print("[CACHE] Redis connecté")
        return r
    except Exception:
        _redis_client = False
        return None

def cache_get(cle: str):
    try:
        r = _get_redis()
        if r:
            val = r.get(f"odyxia:{cle}")
            return val.decode("utf-8") if val else None
        return _cache_mem.get(cle)
    except Exception:
        return None

def cache_set(cle: str, valeur: str, ttl: int = 3600):
    try:
        r = _get_redis()
        if r:
            r.setex(f"odyxia:{cle}", ttl, valeur)
        else:
            if len(_cache_mem) >= 500:
                _cache_mem.pop(next(iter(_cache_mem)))
            _cache_mem[cle] = valeur
    except Exception:
        pass

def cache_key(question: str, tenant_id: str, dossier_id: str = None) -> str:
    import hashlib as _hc
    contenu = f"{tenant_id}:{dossier_id or \'\'}:{question.strip().lower()}"
    return _hc.sha256(contenu.encode()).hexdigest()[:32]
'''

# ══════════════════════════════════════════════════════════════════════
# RÉFORME 5 — Reranking
# ══════════════════════════════════════════════════════════════════════

REFORM_5_CODE = '''
# ─── RERANKING (Réforme 5) ───────────────────────────────────────────────────
_reranker_model = None

def _get_reranker():
    global _reranker_model
    if _reranker_model is not None:
        return _reranker_model if _reranker_model is not False else None
    try:
        from sentence_transformers import CrossEncoder
        _reranker_model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512
        )
        print("[RERANKER] Cross-encoder prêt")
        return _reranker_model
    except Exception as e:
        print(f"[RERANKER] Non disponible : {e}")
        _reranker_model = False
        return None

def reranker_chunks(question: str, chunks: list, top_k: int = 5) -> list:
    """Rerank les chunks par cross-encoder. Fallback cosine si absent."""
    if not chunks:
        return []
    if len(chunks) <= top_k:
        return chunks
    model = _get_reranker()
    if model is None:
        return chunks[:top_k]
    try:
        paires = [(question, c.get("contenu", "")[:500]) for c in chunks]
        scores = model.predict(paires)
        return [c for c, _ in sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[:top_k]]
    except Exception as e:
        print(f"[RERANKER] Erreur : {e}")
        return chunks[:top_k]
'''

# ══════════════════════════════════════════════════════════════════════
# RÉFORME 6 — Prompt juridique africain
# ══════════════════════════════════════════════════════════════════════

REFORM_6_CODE = '''
# ─── PROMPT JURIDIQUE AFRICAIN (Réforme 6) ───────────────────────────────────
_CONTEXTE_PAYS = {
    "CM": "Cameroun — Code du travail (Loi n92/007), Code pénal CM, droit CEMAC",
    "GA": "Gabon — Code du travail gabonais, Code civil gabonais, droit CEMAC",
    "CI": "Côte d Ivoire — Code du travail ivoirien, droit UEMOA",
    "SN": "Sénégal — Code du travail sénégalais, droit UEMOA",
    "BJ": "Bénin — Code du travail béninois, droit UEMOA",
    "ML": "Mali — Code du travail malien, droit UEMOA",
    "BF": "Burkina Faso — Code du travail burkinabè, droit UEMOA",
    "TG": "Togo — Code du travail togolais, droit UEMOA",
    "NE": "Niger — Code du travail nigérien, droit UEMOA",
    "TD": "Tchad — Code du travail tchadien, droit CEMAC",
    "CG": "Congo-Brazzaville — Code du travail congolais, droit CEMAC",
    "GN": "Guinée — Code du travail guinéen, droit OHADA",
    "GQ": "Guinée Équatoriale — droit CEMAC, droit OHADA",
    "CF": "Centrafrique — droit CEMAC, droit OHADA",
}

_SYSTEM_PROMPT_BASE = """Tu es Odyxia, assistant juridique expert en droit africain francophone.
CADRE : droit OHADA (17 États), droit CEMAC/COBAC, droits nationaux africains.
Hiérarchie : OHADA -> droit communautaire -> droit national.
RÈGLES ABSOLUES :
1. Citer toujours l article et la loi applicables
2. Distinguer droit OHADA (supranational) et droit national
3. Si absent des documents : dire "Je ne trouve pas cette information dans vos documents"
4. Ne jamais inventer de jurisprudence ou d articles
5. Signaler si un délai est légal vs conventionnel
6. Recommander de consulter un avocat pour les décisions importantes
STYLE : réponses structurées, langue juridique précise, sources entre crochets."""

def _construire_system_prompt_odyxia(chunks: list, pays: str = "CM") -> str:
    """Construit le prompt système avec contexte RAG et pays."""
    pays_info = _CONTEXTE_PAYS.get(pays, "Zone OHADA — droit africain francophone")
    system = f"{_SYSTEM_PROMPT_BASE}\\nCONTEXTE NATIONAL : {pays_info}\\n"
    if chunks:
        contexte_parts = []
        doc_cache = {}
        for i, chunk in enumerate(chunks, 1):
            doc_id = chunk.get("document_id", "")
            if doc_id not in doc_cache:
                doc_cache[doc_id] = obtenir_nom_document(doc_id)
            nom = doc_cache[doc_id]
            page = chunk.get("page_numero", 1)
            contexte_parts.append(f"[Source {i} — {nom}, p.{page}]\\n{chunk.get(\'contenu\', \'\')}")
        system += "\\n\\nDOCUMENTS DISPONIBLES :\\n" + "\\n\\n".join(contexte_parts)
    return system
'''

# ══════════════════════════════════════════════════════════════════════
# RÉFORME 4 — Streaming natif Claude
# ══════════════════════════════════════════════════════════════════════

REFORM_4_QUESTION_STREAM = '''
@app.route("/question_stream", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")
def question_stream():
    try:
        user_id    = get_jwt_identity()
        tenant_id  = get_current_tenant_id()
        data       = request.json
        q          = data.get("question", "").strip()
        session_id = data.get("session_id", "default")
        dossier_id = data.get("dossier_id")

        _abo = verifier_abonnement(tenant_id)
        if not _abo["actif"]:
            return jsonify({"erreur": "acces_expire", "message": _abo["message"]}), 402

        if not q:
            return jsonify({"erreur": "La question est requise"}), 400

        inj = analyser_injection(q, champ="question_stream")
        if inj.bloque:
            log_security_event("prompt_injection_bloquee", tenant_id, user_id, {"score": inj.score})
            return jsonify({"erreur": "Contenu non autorisé"}), 400

        # Réforme 3 — vérifier le cache
        cle_cache = cache_key(q, tenant_id, dossier_id)
        cached    = cache_get(cle_cache)
        if cached:
            def generer_cache():
                yield f"data: {json.dumps({\'type\': \'sources\', \'sources\': []}, ensure_ascii=False)}\\n\\n"
                yield f"data: {json.dumps({\'type\': \'token\', \'text\': cached}, ensure_ascii=False)}\\n\\n"
                yield f"data: {json.dumps({\'type\': \'fin\', \'complet\': cached}, ensure_ascii=False)}\\n\\n"
            return Response(
                stream_with_context(generer_cache()),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
            )

        # Réforme 2+5 — RAG avec chunking sémantique + reranking
        chunks_bruts      = rechercher_chunks(q, dossier_id=dossier_id, tenant_id=tenant_id)
        chunks_rerankes   = reranker_chunks(q, chunks_bruts, top_k=5)
        historique_session = get_session(session_id, tenant_id)
        pays_code          = get_current_pays_code()

        # Réforme 6 — Prompt juridique africain
        system_prompt = _construire_system_prompt_odyxia(chunks_rerankes, pays_code)
        sources       = []
        doc_cache     = {}
        for chunk in chunks_rerankes:
            doc_id = chunk.get("document_id", "")
            if doc_id not in doc_cache:
                doc_cache[doc_id] = obtenir_nom_document(doc_id)
            ref = f"{doc_cache[doc_id]} (p.{chunk.get(\'page_numero\', 1)})"
            if ref not in sources:
                sources.append(ref)

        messages = []
        for e in historique_session[-3:]:
            messages.append({"role": "user",      "content": e.get("question", "")})
            messages.append({"role": "assistant", "content": e.get("reponse", "")})
        messages.append({"role": "user", "content": q})

        # Réforme 4 — Streaming natif Claude
        def generer():
            try:
                yield f"data: {json.dumps({\'type\': \'sources\', \'sources\': list(set(sources))}, ensure_ascii=False)}\\n\\n"
                reponse_complete = ""
                with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1500,
                    system=system_prompt,
                    messages=messages,
                ) as stream:
                    for token in stream.text_stream:
                        reponse_complete += token
                        yield f"data: {json.dumps({\'type\': \'token\', \'text\': token}, ensure_ascii=False)}\\n\\n"
                try:
                    historique_session.append({
                        "question": q, "reponse": reponse_complete,
                        "at": datetime.utcnow().isoformat()
                    })
                    save_session(session_id, historique_session, tenant_id)
                    # Réforme 3 — mise en cache
                    cache_set(cle_cache, reponse_complete, ttl=3600)
                except Exception as e_save:
                    log_erreur("SAVE_SESSION_STREAM", e_save)
                yield f"data: {json.dumps({\'type\': \'fin\', \'complet\': reponse_complete}, ensure_ascii=False)}\\n\\n"
            except Exception as e:
                log_erreur("STREAM_CLAUDE", e)
                yield f"data: {json.dumps({\'type\': \'erreur\', \'message\': \'Interruption du service\'}, ensure_ascii=False)}\\n\\n"

        return Response(
            stream_with_context(generer()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
        )

    except Exception as e:
        log_erreur("QUESTION_STREAM_GLOBAL", e)
        return jsonify({"erreur": "Erreur interne du service de streaming"}), 500
'''


# ══════════════════════════════════════════════════════════════════════
# TRAITER_PDF_ASYNC amélioré (Réformes 1+2)
# ══════════════════════════════════════════════════════════════════════

REFORM_UPLOAD_ASYNC = '''
        def traiter_pdf_async(pages_texte, doc_id, tenant_id, file_hash, est_sensible, est_manuscrit):
            try:
                chunks_a_inserer = []
                chunk_global_idx = 0
                for page_data in pages_texte:
                    # Réforme 2 — chunking sémantique
                    chunks_texte = _chunker_semantique(page_data["texte"], taille=400, overlap=50)
                    for chunk_texte in chunks_texte:
                        if len(chunk_texte.strip()) < 80:
                            continue
                        if est_sensible:
                            contenu_final = chiffrer(chunk_texte)
                            index_final   = extraire_index(chunk_texte)
                        else:
                            contenu_final = chunk_texte
                            index_final   = chunk_texte
                        chunks_a_inserer.append({
                            "tenant_id"    : tenant_id,
                            "document_id"  : doc_id,
                            "content"      : contenu_final,
                            "contenu"      : contenu_final,
                            "contenu_index": index_final,
                            "page_number"  : page_data["page"],
                            "page_numero"  : page_data["page"],
                            "chunk_index"  : chunk_global_idx,
                            "source_type"  : "document",
                            "source_hash"  : file_hash,
                            "char_count"   : len(chunk_texte),
                            "metadata"     : {"sensible": est_sensible, "manuscrit": est_manuscrit, "chunker": "semantique_v2"}
                        })
                        chunk_global_idx += 1
                for i in range(0, len(chunks_a_inserer), 100):
                    supabase.table("chunks").insert(chunks_a_inserer[i:i+100]).execute()
                # Réforme 1 — vectorisation SBERT batch
                _vectoriser_document(doc_id, tenant_id)
                supabase.table("documents").update({"status": "ready"}).eq("id", doc_id).execute()
                print(f"[UPLOAD-V2] {doc_id[:8]} — {len(chunks_a_inserer)} chunks sémantiques")
            except Exception as e:
                print(f"[UPLOAD-V2 ERROR] {e}")
                supabase.table("documents").update({"status": "error"}).eq("id", doc_id).execute()
'''


def appliquer_patches(content: str) -> tuple:
    """Applique tous les patches. Retourne (nouveau_content, nb_patches_ok)."""
    nb_ok = 0
    nb_ko = 0

    # ── Patch 1 : Supprimer VOYAGE_API_KEY et ses constantes ──────────
    old_voyage_const = '''VOYAGE_MODEL   = "voyage-law-2"
VOYAGE_URL_API = "https://api.voyageai.com/v1/embeddings"'''
    new_voyage_const = "# VOYAGE_API_KEY supprimé — remplacé par SBERT local (Réforme 1)"
    if old_voyage_const in content:
        content = content.replace(old_voyage_const, new_voyage_const)
        print("  [OK] Patch 1a : constantes Voyage supprimées")
        nb_ok += 1
    else:
        print("  [--] Patch 1a : constantes Voyage absentes ou déjà supprimées")

    # ── Patch 1b : Remplacer les fonctions Voyage par SBERT ───────────
    old_voyage_marker = "# ─── VOYAGE AI ──────────"
    if old_voyage_marker in content:
        # Trouver la fin du bloc Voyage AI (jusqu à la prochaine section)
        debut = content.find(old_voyage_marker)
        fin   = content.find("\n# ─── ABONNEMENT", debut)
        if fin == -1:
            fin = content.find("\n@app.route", debut)
        if fin > debut:
            content = content[:debut] + REFORM_1_CODE + "\n" + content[fin:]
            print("  [OK] Patch 1b : Voyage AI → SBERT local")
            nb_ok += 1
        else:
            print("  [KO] Patch 1b : fin du bloc Voyage non trouvée")
            nb_ko += 1
    else:
        print("  [--] Patch 1b : bloc Voyage absent")

    # ── Patch 2 : Ajouter chunker sémantique après les helpers ────────
    old_marker_helpers = "def obtenir_nom_document"
    if old_marker_helpers in content:
        idx = content.find(old_marker_helpers)
        # Insérer après la fonction obtenir_nom_document
        fin_fn = content.find("\n\ndef ", idx + 1)
        if fin_fn > 0:
            content = content[:fin_fn] + "\n" + REFORM_2_CODE + "\n" + content[fin_fn:]
            print("  [OK] Patch 2 : chunker sémantique ajouté")
            nb_ok += 1
        else:
            print("  [KO] Patch 2 : fin de fonction non trouvée")
            nb_ko += 1
    else:
        print("  [KO] Patch 2 : marqueur obtenir_nom_document absent")
        nb_ko += 1

    # ── Patch 3 : Cache — ajouter après MOTS_VIDES ────────────────────
    old_mots_vides = 'MOTS_VIDES = {'
    if old_mots_vides in content:
        idx = content.find(old_mots_vides)
        fin = content.find("\n\ndef ", idx)
        if fin > 0:
            content = content[:fin] + "\n" + REFORM_3_CODE + "\n" + content[fin:]
            print("  [OK] Patch 3 : cache ajouté")
            nb_ok += 1
        else:
            print("  [KO] Patch 3 : fin MOTS_VIDES non trouvée")
            nb_ko += 1
    else:
        print("  [KO] Patch 3 : MOTS_VIDES absent")
        nb_ko += 1

    # ── Patch 5 : Reranking — ajouter avant rechercher_chunks ─────────
    old_rechercher = "def rechercher_chunks("
    if old_rechercher in content:
        idx = content.find(old_rechercher)
        content = content[:idx] + REFORM_5_CODE + "\n\n" + content[idx:]
        print("  [OK] Patch 5 : reranking ajouté")
        nb_ok += 1
    else:
        print("  [KO] Patch 5 : rechercher_chunks absent")
        nb_ko += 1

    # ── Patch 6 : Prompt africain — ajouter avant # ─── ROUTES ───────
    old_routes_marker = "# ─── ROUTES PUBLIQUES"
    if old_routes_marker in content:
        idx = content.find(old_routes_marker)
        content = content[:idx] + REFORM_6_CODE + "\n\n" + content[idx:]
        print("  [OK] Patch 6 : prompt juridique africain ajouté")
        nb_ok += 1
    else:
        print("  [KO] Patch 6 : marqueur ROUTES PUBLIQUES absent")
        nb_ko += 1

    # ── Patch 4a : Remplacer question_stream ──────────────────────────
    old_stream_marker = "@app.route(\"/question_stream\", methods=[\"POST\"])"
    if old_stream_marker in content:
        debut = content.find(old_stream_marker)
        # Trouver la fin de la fonction (prochaine route)
        fin = content.find('\n\n@app.route("/nouvelle-conversation"', debut)
        if fin == -1:
            fin = content.find('\n\n\n# ─── MEMOIRE', debut)
        if fin > debut:
            content = content[:debut] + REFORM_4_QUESTION_STREAM + "\n\n" + content[fin:]
            print("  [OK] Patch 4 : question_stream → streaming natif Claude")
            nb_ok += 1
        else:
            print("  [KO] Patch 4 : fin question_stream non trouvée")
            nb_ko += 1
    else:
        print("  [KO] Patch 4 : route question_stream absente")
        nb_ko += 1

    # ── Patch 1+2 upload async ────────────────────────────────────────
    old_async = "        def traiter_pdf_async(pages_texte, doc_id, tenant_id, file_hash, est_sensible, est_manuscrit):"
    if old_async in content:
        debut_async = content.find(old_async)
        fin_async   = content.find("\n        threading.Thread(", debut_async)
        if fin_async > debut_async:
            content = content[:debut_async] + REFORM_UPLOAD_ASYNC + content[fin_async:]
            print("  [OK] Patch 1+2b : traiter_pdf_async → version sémantique")
            nb_ok += 1
        else:
            print("  [KO] Patch 1+2b : fin traiter_pdf_async non trouvée")
            nb_ko += 1
    else:
        print("  [--] Patch 1+2b : traiter_pdf_async absent ou déjà patché")

    return content, nb_ok, nb_ko


def main():
    print("=" * 65)
    print("  PATCH ODYXIA DROIT — 6 Réformes")
    print("=" * 65)

    if not os.path.exists(APP_PATH):
        print(f"[ERREUR] {APP_PATH} introuvable")
        print(f"  Lancer ce script depuis le dossier odyxia-droit/")
        sys.exit(1)

    content_original = lire()
    print(f"\n  app.py lu : {len(content_original):,} chars")

    backup()

    print(f"\n  Application des patches...")
    content_patche, nb_ok, nb_ko = appliquer_patches(content_original)

    print(f"\n  {nb_ok} patches OK | {nb_ko} patches KO")

    if nb_ko > 0:
        print(f"\n  [AVERTISSEMENT] {nb_ko} patch(es) ont échoué.")
        print(f"  Vérifier les patterns dans app.py.")

    # Vérification syntaxe avant d'écrire
    print(f"\n  Vérification syntaxe Python...")
    if not verifier_syntaxe(content_patche):
        print(f"  [ERREUR] Syntaxe invalide — app.py NON modifié")
        print(f"  Le backup est disponible : {BACKUP_PATH}")
        sys.exit(1)

    print(f"  Syntaxe OK")
    ecrire(content_patche)
    print(f"\n  app.py mis à jour : {len(content_patche):,} chars")
    print(f"  Backup sauvegardé : {BACKUP_PATH}")

    print(f"\n  Ajouter dans requirements.txt :")
    print(f"    sentence-transformers>=2.2.0")
    print(f"    redis>=4.0.0")
    print(f"\n  Puis installer :")
    print(f"    pip install sentence-transformers redis")
    print(f"\n  IMPORTANT — Re-vectoriser les chunks existants :")
    print(f"    python3 re_vectoriser.py")
    print(f"\n  PATCH TERMINÉ")
    print("=" * 65)


if __name__ == "__main__":
    main()