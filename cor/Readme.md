# COR — Modèle de Langage Juridique Africain

**Decoder-Only Transformer** spécialisé sur le droit africain francophone.  
OHADA · CEMAC · UEMOA · 17 pays · 8 000 tokens juridiques

---

## Architecture

- **Type** : Decoder-Only pur (style LLaMA / Mistral)
- **Paramètres** : 12M (dev) → 50M (production)
- **Vocabulaire** : 8 000 tokens juridiques africains
- **Langues** : Français juridique africain
- **Couverture** : OHADA, CEMAC, UEMOA, CM, GA, CI, SN, BJ, BF, ML, NE, TG, GN, CD, CG, TD, CF, GQ

## Structure du projet

```
cor/
├── cor/              ← package Python
│   ├── tokenizer.py  ← BPE juridique africain (8 000 tokens)
│   ├── model.py      ← architecture Decoder-Only
│   ├── trainer.py    ← entraînement + masque de loss
│   ├── inference.py  ← interface unifiée
│   └── corpus.py     ← chargement du corpus
├── server/           ← microservice Flask
│   ├── app.py
│   ├── routes.py
│   └── Dockerfile
├── scripts/
│   ├── train.py      ← lancer l'entraînement
│   └── evaluate.py   ← évaluation
└── models/           ← poids (gitignored)
```

## Démarrage rapide

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Entraîner le tokeniseur
python scripts/train.py --phase tokenizer

# 3. Entraîner le modèle
python scripts/train.py --phase pretrain
python scripts/train.py --phase finetune

# 4. Lancer le serveur
docker-compose up -d
```

## API REST

```bash
# Générer une réponse
curl -X POST http://localhost:5000/generate \
  -H "Content-Type: application/json" \
  -H "X-Cor-Key: votre_cle_api" \
  -d '{
    "question": "licenciement sans préavis cameroun article 34",
    "passages_rag": ["article 34 code travail cameroun..."],
    "max_tokens": 150
  }'

# Santé du serveur
curl http://localhost:5000/health
```

## Statut

| Composant | Statut |
|---|---|
| Tokeniseur BPE | ✅ Prêt |
| Architecture Decoder-Only | ✅ Prête |
| Entraînement | ⏳ En cours |
| Microservice Flask | ✅ Prêt |
| Package pip | 🔜 Phase 2 |

## Intégration ODYXIA

Cor est conçu pour fonctionner avec le système RAG d'ODYXIA IA.  
Il reçoit la question + les passages RAG récupérés et génère la réponse.

```
ODYXIA IA → RAG (12 000 passages) → passages pertinents
                                          ↓
                                    COR /generate
                                          ↓
                                   réponse juridique
```

---

**ODYXIA** — Plateforme IA panafricaine · Douala, Cameroun