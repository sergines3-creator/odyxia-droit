#!/usr/bin/env python3
import os, re, uuid, time, requests
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TENANT_OHADA = "00000000-0000-0000-0000-000000000001"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SOURCES = [
    "https://kalieu-elongo.com/droit-des-societes/",
    "https://kalieu-elongo.com/droit-commercial-general/",
    "https://kalieu-elongo.com/droit-des-suretes/",
    "https://kalieu-elongo.com/procedures-collectives/",
    "https://kalieu-elongo.com/voies-dexecution/",
    "https://kalieu-elongo.com/droit-de-larbitrage/",
]

def chunker(texte, taille=400, overlap=50):
    texte = re.sub(r'\n{3,}', '\n\n', texte)
    paragraphes = [p.strip() for p in texte.split('\n\n') if p.strip()]
    chunks, buffer, nb = [], [], 0
    for para in paragraphes:
        mots = para.split()
        if nb + len(mots) > taille and buffer:
            ct = ' '.join(buffer)
            if len(ct) > 80: chunks.append(ct)
            buffer = buffer[-overlap:] if overlap else []
            nb = len(buffer)
        buffer += mots
        nb += len(mots)
    if buffer:
        ct = ' '.join(buffer)
        if len(ct) > 80: chunks.append(ct)
    return chunks

def get_embedding(texte):
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        return model.encode(texte[:512], normalize_embeddings=True).tolist()
    except: return None

def scraper(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script","style","nav","header","footer","aside"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:50000]
    except Exception as e:
        print(f"  Erreur : {e}")
        return None

def scraper_liens(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(res.text, "html.parser")
        liens = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "kalieu-elongo.com" in href and href not in liens:
                liens.append(href)
        return liens[:20]
    except: return []

def indexer(nom, texte, url):
    doc_id = str(uuid.uuid4())
    supabase.table("documents").insert({
        "id": doc_id, "tenant_id": TENANT_OHADA,
        "filename": nom[:100]+".txt", "original_filename": nom[:100]+".txt",
        "nom": nom[:100], "type": "ohada", "mime_type": "text/plain",
        "file_size_bytes": len(texte), "file_hash_sha256": __import__("hashlib").sha256(texte.encode()).hexdigest(), "status": "ready",
        "storage_tier": "hot", "ocr_status": "done", "scan_status": "clean",
        "metadata": {"source": url, "type": "doctrine_ohada"}
    }).execute()
    chunks_texte = chunker(texte)
    print(f"  {len(chunks_texte)} chunks — {nom[:60]}")
    to_insert = []
    for i, chunk in enumerate(chunks_texte):
        to_insert.append({
            "tenant_id": TENANT_OHADA, "document_id": doc_id,
            "content": chunk, "contenu": chunk, "contenu_index": chunk,
            "page_number": 1, "page_numero": 1, "chunk_index": i,
            "source_type": "legal_act", "embedding": get_embedding(chunk),
            "metadata": {"source": url, "domaine": "ohada"}
        })
    for i in range(0, len(to_insert), 50):
        supabase.table("chunks").insert(to_insert[i:i+50]).execute()
    return len(chunks_texte)

print("="*60)
print("  INDEXATION kalieu-elongo.com")
print("="*60)

total = 0
urls_traitees = set()

for source in SOURCES:
    print(f"\n  Catégorie : {source}")
    liens = scraper_liens(source)
    for lien in liens:
        if lien in urls_traitees: continue
        urls_traitees.add(lien)
        texte = scraper(lien)
        if texte and len(texte) > 300:
            nom = lien.split("/")[-2] or lien.split("/")[-1]
            total += indexer(nom, texte, lien)
            time.sleep(0.5)

print(f"\n  Total : {total} chunks indexés")
print("  Terminé")
