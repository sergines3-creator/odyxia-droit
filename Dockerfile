# Dockerfile
# ODYXIA Droit — Image Docker pour Hetzner cor-prod
#
# Build  : docker build -t odyxia-droit .
# Run    : docker run -d --name odyxia-droit \
#            -p 5001:5000 \
#            --env-file .env \
#            --restart unless-stopped \
#            odyxia-droit
#
# POINTS CRITIQUES :
#
#   1. Port 5001 sur l hôte (5000 est déjà pris par COR)
#      ODYXIA Droit tourne en parallèle de COR sur cor-prod.
#      Port interne Docker reste 5000.
#
#   2. sentence-transformers (~420Mo)
#      Le modèle SBERT est téléchargé au premier démarrage
#      et mis en cache dans /root/.cache/huggingface.
#      On monte ce cache via volume pour éviter le
#      re-téléchargement à chaque redémarrage.
#
#   3. --workers 2 Gunicorn
#      Sur CPX42 (16Go RAM), 2 workers est optimal.
#      Chaque worker charge SBERT (~420Mo) → 2 × 420Mo = 840Mo.
#      Largement dans les limites du serveur.
#
#   4. PyMuPDF et Tesseract
#      PyMuPDF nécessite libmupdf — inclus dans pymupdf wheel.
#      Tesseract nécessite tesseract-ocr + tessdata français.
#
#   5. Timeout 120s
#      Plus long que COR car ODYXIA Droit appelle Claude API
#      (2-5s) + vectorisation SBERT (10ms) + Supabase (50ms).
#      60s serait trop court pour les documents longs.

FROM python:3.11-slim

LABEL maintainer="ODYXIA"
LABEL version="1.0.0"
LABEL description="ODYXIA Droit — Assistant Juridique OHADA"

WORKDIR /app

# Dépendances système
# tesseract-ocr + tesseract-ocr-fra : OCR pour documents manuscrits
# libgl1 : requis par PyMuPDF pour le rendu PDF
# poppler-utils : extraction PDF avancée
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Requirements Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY app.py           .
COPY prompts.py       .
COPY encryption.py    .
COPY audit_logger.py  .
COPY prompt_injection.py .

# Blueprints optionnels


# Templates et fichiers statiques
COPY templates/    ./templates/

# Dossiers de travail
RUN mkdir -p /app/logs /tmp/odyxia

# Cache HuggingFace — sera monté depuis le host pour persistance
ENV HF_HOME=/app/.cache/huggingface
RUN mkdir -p /app/.cache/huggingface

# Variables d'environnement par défaut
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_DEBUG=false

# Port interne
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" \
    || exit 1

# Lancement Gunicorn
# --workers 2      : 2 processus parallèles
# --threads 2      : 2 threads par worker (pour les SSE)
# --timeout 120    : Claude API peut prendre jusqu à 30s
# --worker-class sync : sync pour SSE (pas gevent/eventlet)
CMD ["gunicorn", \
     "app:app", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "3", \
     "--threads", "4", \
     "--timeout", "120", \
     "--worker-class", "gthread", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
