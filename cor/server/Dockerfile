# server/Dockerfile
# COR — Image Docker du microservice
#
# Build : docker build -f server/Dockerfile -t cor-server .
# Run   : docker run -d --name cor-server \
#           -p 5000:5000 \
#           -v /root/cor/models:/app/models \
#           --env-file .env \
#           cor-server
#
# POINTS CRITIQUES :
#
#   1. Volume obligatoire pour les modèles
#      Les fichiers cor.pt et cor_tokenizer.json NE SONT PAS
#      dans l'image Docker (trop lourds, données sensibles).
#      Ils sont montés via -v depuis le host Hetzner.
#      Sans ce volume, le serveur démarre en mode fallback.
#
#   2. --workers 2 dans gunicorn
#      Sur CPX42 (8 vCPU), 2 workers = bon équilibre.
#      Chaque worker charge le modèle → 2 × RAM modèle.
#      50M params ≈ 200Mo × 2 = 400Mo. Largement OK sur 16Go.
#      Ne pas dépasser 4 workers.
#
#   3. Timeout gunicorn
#      --timeout 60 : génération de 300 tokens sur CPU ≈ 10-30s.
#      60s est conservateur et sûr.
#      Augmenter à 120s si le modèle dépasse 125M params.
#
#   4. python:3.11-slim
#      Pas d'image torch officielle — trop lourde (plusieurs Go).
#      On installe torch CPU uniquement depuis PyPI.
#      torch CPU ≈ 200Mo. Acceptable.

FROM python:3.11-slim

# Métadonnées
LABEL maintainer="ODYXIA"
LABEL version="0.1.0-dev"
LABEL description="COR — Microservice LLM Juridique Africain"

# Dossier de travail
WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY cor/       ./cor/
COPY server/    ./server/
COPY setup.py   .

# Dossier des modèles — vide dans l'image, monté depuis le host
RUN mkdir -p /app/models /app/data /app/logs

# Variables d'environnement par défaut
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV COR_ACTIF=true
ENV COR_MAX_TOKENS=150

# Port exposé
EXPOSE 5000

# Health check Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

# Lancement
CMD ["gunicorn", \
     "server.app:create_app()", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]