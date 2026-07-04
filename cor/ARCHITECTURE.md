# COR — Architecture & Description des dossiers

COR est un LLM (modèle de langage) spécialisé en **droit africain francophone** (OHADA, CEMAC, UEMOA, Cameroun, Gabon, Bénin, Côte d'Ivoire).
Le code est organisé en **4 couches strictes** — chaque couche ne peut appeler que la couche immédiatement en dessous.

---

## Vue d'ensemble de la structure

```
cor/                       ← racine du projet
│
├── domain/                ← COUCHE 1 : le cerveau du modèle (PyTorch pur)
├── infrastructure/        ← COUCHE 2 : données, fichiers, entraînement, RAG
├── application/           ← COUCHE 3 : orchestration de l'inférence
├── api/                   ← COUCHE 4 : exposition HTTP (Flask) + sécurité
│
├── cor/                   ← compatibilité : anciens imports toujours fonctionnels
├── dashboard/             ← interface visuelle de suivi d'entraînement (Flask 5001)
├── admin/                 ← interface d'administration React + Tailwind (port 5173)
├── scripts/               ← outils en ligne de commande
├── server/                ← serveur Flask principal (port 5000)
├── cor_sx/                ← variante expérimentale COR Sx (Encoder-Decoder)
├── cor_tx/                ← variante expérimentale COR Tx
│
├── models/                ← fichiers du modèle sauvegardé
├── data/                  ← corpus juridique + base vectorielle ChromaDB
├── logs/                  ← journaux de sécurité (security.jsonl)
│
├── clients.json           ← clients API autorisés (créé automatiquement)
├── requirements.txt       ← liste des dépendances Python
├── .env.example           ← template de configuration
└── ARCHITECTURE.md        ← ce fichier
```

---

## Description détaillée de chaque dossier

---

### `domain/` — Le cerveau du modèle

> **Rôle** : contient l'architecture Transformer pure. Aucune dépendance vers Flask, les fichiers ou la base de données. Uniquement PyTorch.

C'est le cœur intellectuel du projet — la définition mathématique du modèle.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `model.py` | Définit l'architecture complète du réseau de neurones : `ConfigCor` (paramètres du modèle), `RMSNorm` (normalisation), `RoPE` (encodage de position), `MultiHeadAttention` (attention causale), `SwiGLU` (activation FFN), `CoucheDecoder` (bloc Transformer), `Cor` (le modèle complet) |
| `tokenizer.py` | Définit `CorTokenizer` : le tokeniseur BPE juridique avec 8000 tokens dont 60 réservés pour les tokens spéciaux (`[CM]`, `[GA]`, `[REP]`, `[OHADA]`, etc.) |

**Règle** : aucun import Flask ici. Aucune lecture de fichier externe (sauf `sauvegarder()`/`charger()` pour pragmatisme).

---

### `infrastructure/` — Données et entraînement

> **Rôle** : tout ce qui touche aux fichiers, au disque et aux boucles d'entraînement. Peut utiliser `domain/`.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `corpus.py` | Charge et consolide le corpus juridique depuis `data/juridique_dataset.json` et les fichiers `.txt`. Fonctions : `charger_corpus()`, `charger_dataset_json()`, `charger_fichiers_txt()`, `rapport_corpus()` |
| `trainer.py` | Contient toute la logique d'entraînement : `ConfigEntrainement` (hyperparamètres), `DatasetPreEntrainement`, `DatasetFineTuning`, `pre_entrainer()`, `fine_tuner()`, `get_lr()` (scheduler LR), `calculer_loss_masquee()` (masque [REP]) |
| `rag.py` | Moteur RAG : base vectorielle ChromaDB + embeddings `paraphrase-multilingual-MiniLM-L12-v2`. Fonctions : `indexer_document()`, `indexer_pdf()` (chunks 500 tokens, overlap 50), `rechercher()` (filtre par pays/domaine, seuil cosinus), `supprimer_document()`, `lister_documents()`, `stats()`. Base persistée dans `data/chroma_db/`. |

**Futur** : améliorer l'indexation RAG avec re-ranking et filtres sémantiques avancés.

---

### `application/` — Orchestration

> **Rôle** : fait le lien entre le modèle et le monde extérieur. Reçoit une question, construit le prompt, appelle le modèle, retourne la réponse.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `inference.py` | Classe `CorInference` : la seule interface que les projets externes (ODYXIA IA, ODYXIA Droit) doivent connaître. Méthodes : `charger()`, `repondre()`, `tokeniser()`, `decoder()`, `info()`. Gère le flag `COR_ACTIF` pour le fallback. |

---

### `api/` — Exposition HTTP

> **Rôle** : transforme `CorInference` en service web REST. Gère l'authentification, la validation des entrées et le rate limiting. Ne contient aucune logique métier.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `app.py` | Factory Flask `create_app()` : crée le serveur sur le port **5000**, charge le modèle au démarrage, configure le rate limiter. Vérifie l'intégrité SHA-256 du modèle au démarrage. |
| `routes.py` | Définit tous les endpoints HTTP. Délègue l'auth à `security.py`. |
| `security.py` | Authentification multi-clients (`clients.json`), vérification SHA-256 du modèle (`cor.pt.sha256`), détection d'injection de prompt (16 patterns), journalisation `logs/security.jsonl`, timeout génération 30s. |

**Lancement** : `python -m api.app` → serveur disponible sur `http://localhost:5000`

---

### `cor/` — Couche de compatibilité (shims)

> **Rôle** : permet aux anciens imports (`from cor import CorInference`) de continuer à fonctionner sans modification, même après la réorganisation en couches.

Chaque fichier dans `cor/` est un simple **redirecteur** vers la vraie implémentation :

| Fichier shim | Redirige vers |
|-------------|--------------|
| `cor/model.py` | `domain/model.py` |
| `cor/tokenizer.py` | `domain/tokenizer.py` |
| `cor/inference.py` | `application/inference.py` |
| `cor/corpus.py` | `infrastructure/corpus.py` |
| `cor/trainer.py` | `infrastructure/trainer.py` |

```python
# Ces imports fonctionnent tous (via shims) :
from cor import CorInference, Cor, CorTokenizer
from cor.model     import Cor, ConfigCor
from cor.tokenizer import CorTokenizer
from cor.trainer   import pre_entrainer, ConfigEntrainement
```

---

### `dashboard/` — Interface visuelle

> **Rôle** : tableau de bord web pour suivre l'entraînement en temps réel et tester le modèle.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `app.py` | Serveur Flask sur le port **5001**. Sert l'interface HTML et expose des APIs de métriques. Contient aussi un proxy vers `/generate` pour le chat (la clé API reste côté serveur). |
| `metrics_writer.py` | Classe `MetricsWriter` : écrit les métriques d'entraînement (loss, perplexité, LR) dans `training_metrics.json` de façon thread-safe. Appelée automatiquement par le trainer. |
| `templates/index.html` | Interface complète : progression epoch/step, courbes de loss, logs filtrables, diagramme de l'architecture, et un onglet chat pour tester COR. |

**Lancement** : `python dashboard/app.py` → interface disponible sur `http://localhost:5001`

---

### `scripts/` — Outils en ligne de commande

> **Rôle** : scripts d'entraînement et d'évaluation à lancer directement depuis le terminal.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `train.py` | Script principal d'entraînement. Phases : `tokenizer` → `pretrain` → `finetune`. Options : `--dev` (rapide, 12M params) ou production (50M params). |
| `evaluate.py` | Évalue le modèle entraîné : génération qualitative sur des questions-test + calcul de perplexité. |
| `train_runpod.py` | Version adaptée pour l'entraînement sur GPU cloud (RunPod). |
| `train_tx.py` | Script d'entraînement pour la variante COR Tx. |

**Usage** :
```bash
python scripts/train.py --dev        # test rapide
python scripts/train.py              # entraînement complet
python scripts/evaluate.py           # évaluation
```

---

### `admin/` — Interface d'administration React

> **Rôle** : interface d'administration complète pour gérer COR sans toucher au terminal.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `src/App.jsx` | Composant racine avec les 4 onglets de navigation |
| `src/api.js` | Client HTTP centralisé vers le serveur COR (lit `VITE_COR_URL` et `VITE_COR_KEY`) |
| `src/tabs/TabDashboard.jsx` | Vue d'ensemble : statut serveur, compteurs RAG, graphiques répartition pays/domaine, infos modèle |
| `src/tabs/TabTest.jsx` | Formulaire de test : question, sélecteur pays, température, génération temps réel, historique 10 requêtes |
| `src/tabs/TabDocuments.jsx` | Gestion RAG : upload PDF (drag & drop), indexation texte brut, liste avec suppression |
| `src/tabs/TabTraining.jsx` | Entraînement : configuration epochs/lr/batch, courbe loss en temps réel, logs, bouton stop |
| `package.json` | Dépendances npm : React 18, Vite 5, Tailwind CSS 3, Recharts |
| `.env.example` | Variables Vite : `VITE_COR_URL`, `VITE_COR_KEY` |

**Lancement** :
```bash
cd admin
npm install
cp .env.example .env   # renseigner VITE_COR_KEY
npm run dev            # http://localhost:5173
npm run build          # build statique dans admin/dist/
```

---

### `server/` — Serveur Flask principal

> **Rôle** : serveur Flask sur le port 5000, exposant tous les endpoints COR.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `app.py` | Factory Flask, charge le modèle au démarrage, configure le rate limiter. |
| `routes.py` | Tous les endpoints : `/health`, `/generate`, `/tokenize`, `/info`, RAG (`/rag/*`), entraînement (`/train/*`), administration (`/clients`). |
| `Dockerfile` | Image Docker pour déployer en production (Hetzner, Railway, etc.). |

---

### `cor_sx/` — Variante COR Sx (expérimental)

> **Rôle** : variante Encoder-Decoder (style T5) du modèle COR. Architecture différente du modèle principal (qui est Decoder-Only).

| Fichier | Ce qu'il fait |
|---------|--------------|
| `model.py` | Architecture Encoder-Decoder T5-style pour COR Sx |
| `generateur_paires.py` | Génère des paires question-réponse pour le fine-tuning de COR Sx |

---

### `cor_tx/` — Variante COR Tx (expérimental)

> **Rôle** : autre variante expérimentale du modèle COR avec sa propre architecture, trainer et inference.

| Fichier | Ce qu'il fait |
|---------|--------------|
| `model.py` | Architecture du modèle COR Tx |
| `trainer.py` | Boucle d'entraînement spécifique à COR Tx |
| `inference.py` | Interface d'inférence pour COR Tx |

---

### `models/` — Fichiers du modèle sauvegardé

> **Rôle** : stocke les poids du modèle et le tokeniseur après entraînement.

| Fichier | Ce qu'il contient |
|---------|-----------------|
| `cor.pt` | Poids du modèle COR entraîné (PyTorch checkpoint) |
| `cor_tokenizer.json` | Vocabulaire BPE (8000 tokens) et règles de fusion |
| `checkpoints/pretrain_best.pt` | Meilleur checkpoint du pré-entraînement |
| `checkpoints/ft_best.pt` | Meilleur checkpoint du fine-tuning |

---

### `data/` — Corpus d'entraînement

> **Rôle** : contient les textes juridiques africains utilisés pour entraîner le modèle.

| Fichier | Ce qu'il contient |
|---------|-----------------|
| `juridique_dataset.json` | Dataset principal : passages de loi, paires question-réponse, paires similaires. Format : `{ "passages": [...], "paires_qr": [...], "paires_similaires": [...] }` |
| `*.txt` (optionnel) | Textes juridiques bruts supplémentaires (OHADA, JO Cameroun, etc.) |

**Volume minimum recommandé** : 500 000 tokens (~2 Mo de texte) pour le BPE, 500 millions pour un bon modèle.

---

### `logs/` — Journaux de sécurité

> **Rôle** : journaux générés automatiquement par `api/security.py`.

| Fichier | Ce qu'il contient |
|---------|-----------------|
| `security.jsonl` | Une ligne JSON par requête : timestamp, ip, client_id, endpoint, statut HTTP, durée_ms, alerte (injection, quota dépassé, etc.) |

---

### Fichiers racine

| Fichier | Ce qu'il fait |
|---------|--------------|
| `requirements.txt` | Liste toutes les dépendances Python à installer (`pip install -r requirements.txt`) |
| `.env.example` | Template du fichier de configuration. À copier en `.env` et remplir avec la vraie `COR_API_KEY`. |
| `clients.json` | Base des clients API autorisés. Créé automatiquement à l'ajout du premier client via `POST /clients`. Structure : `{ "clients": [{ "client_id", "nom", "cle_api", "quota_mensuel", "requetes_utilisees", "actif" }] }` |
| `cor_classifier.py` | Classifieur hybride (regex + SBERT) pour identifier le domaine juridique d'un texte (20+ domaines : droit du travail, droit commercial, procédure pénale...) |
| `cor_scraper.py` | Collecteur de corpus : télécharge des PDFs et pages web juridiques (OHADA.com, JORcam, jurAfrica) pour alimenter `data/` |
| `cor_retagger.py` | Outil de retaggage du corpus (correction et normalisation des annotations) |
| `setup.py` | Configuration du package Python pour installer COR comme bibliothèque |
| `Readme.md` | Documentation générale du projet |

---

## Règles d'architecture

| Règle | Description |
|-------|-------------|
| **R1** | Une couche ne peut importer que la couche immédiatement en dessous |
| **R2** | Aucune logique métier dans `api/` — tout déléguer à `application/` |
| **R3** | Aucun import Flask dans `domain/` ou `infrastructure/` |
| **R4** | Chaque fichier commence par un commentaire indiquant sa couche et sa responsabilité |
| **R5** | Les noms publics (classes, méthodes, fonctions) restent identiques pour ne pas casser les imports existants |

---

## Flux complet — d'une question à une réponse

```
Utilisateur / Admin React (port 5173)
    │
    ▼
POST /generate  (server/routes.py)
    │  1. Vérification X-Cor-Key (api/security.py)
    │  2. Détection injection de prompt
    ▼
RAG automatique  (infrastructure/rag.py)
    │  rechercher() → passages pertinents (ChromaDB)
    ▼
CorInference.repondre()  (application/inference.py)
    │  construction du prompt avec passages RAG
    ▼
CorTokenizer.construire_prompt_cor()  (domain/tokenizer.py)
    │  [BOS][CM] question [SEP] passage_rag [REP]
    ▼
Cor.generer()  (domain/model.py)
    │  décodage autorégressif token par token
    ▼
Réponse juridique jusqu'à [EOS]
    │  Journalisation → logs/security.jsonl
    ▼
Utilisateur
```

---

## Comment lancer le projet

```bash
# 1. Installer les dépendances Python
pip install -r requirements.txt

# 2. Configurer les clés
cp .env.example .env
# Éditer .env — définir COR_API_KEY

# 3. Lancer le serveur COR (port 5000)
python server/app.py

# 4. Lancer le dashboard d'entraînement (port 5001) — optionnel
python dashboard/app.py

# 5. Lancer l'interface admin React (port 5173) — optionnel
cd admin
npm install
cp .env.example .env    # définir VITE_COR_KEY
npm run dev
```

---

## Comment ajouter un composant

**Nouvelle source de données** → créer dans `infrastructure/`, appeler depuis `infrastructure/corpus.py`

**Nouveau cas d'usage** → créer dans `application/`, exposer via `server/routes.py`

**Nouveau client API** → `POST /clients` avec `{"nom": "...", "quota_mensuel": 1000}` — récupérer la `cle_api` retournée (affichée une seule fois)

**Nouveau document RAG** → via l'interface admin onglet "Documents", ou `POST /rag/add_document` / `POST /rag/add_pdf`
