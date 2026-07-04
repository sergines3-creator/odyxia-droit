# scripts/train.py
# COR — Script de lancement de l'entraînement
#
# Usage :
#   python scripts/train.py --phase all        ← tout (tokenizer + pretrain + finetune)
#   python scripts/train.py --phase tokenizer  ← tokeniseur uniquement
#   python scripts/train.py --phase pretrain   ← pré-entraînement uniquement
#   python scripts/train.py --phase finetune   ← fine-tuning uniquement
#
# POINTS CRITIQUES :
#
#   1. Ordre obligatoire
#      tokenizer → pretrain → finetune
#      Ne jamais lancer finetune sans pretrain terminé.
#      Ne jamais lancer pretrain sans tokenizer.
#
#   2. Checkpoints
#      Les checkpoints sont sauvegardés dans models/checkpoints/.
#      En cas d'interruption, relancer le même script —
#      il reprend depuis le meilleur checkpoint disponible.
#
#   3. GPU vs CPU
#      Sur CPX42 (CPU only) : pretrain ≈ 2-4h/epoch pour 12M params.
#      Sur A100 GPU (RunPod) : pretrain ≈ 5-15min/epoch.
#      Recommandé : entraîner sur RunPod, déployer sur CPX42.
#
#   4. Corpus insuffisant
#      Si le corpus est < 500K tokens, le BPE s'arrête avant 8000 tokens
#      et la val_loss remonte dès l'epoch 2-3 (sur-apprentissage).
#      Augmenter le corpus avant de lancer l'entraînement complet.

import os
import sys
import argparse
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

TOKENIZER_PATH = os.path.join(BASE, "models", "cor_tokenizer.json")
MODELE_PATH    = os.path.join(BASE, "models", "cor.pt")
DATASET_PATH   = os.path.join(BASE, "data", "juridique_dataset.json")
CHECKPOINT_DIR = os.path.join(BASE, "models", "checkpoints")


def phase_tokenizer():
    """Entraîne et sauvegarde le tokeniseur BPE."""
    print("\n" + "="*65)
    print("  PHASE TOKENIZER")
    print("="*65)

    from cor.tokenizer import CorTokenizer
    from cor.corpus    import charger_corpus

    corpus = charger_corpus(dataset_path=DATASET_PATH)

    if not corpus:
        print("[ERREUR] Corpus vide — ajouter des données dans data/")
        print("         Format : data/juridique_dataset.json")
        sys.exit(1)

    tok = CorTokenizer(vocab_size=8000)
    tok.entrainer(corpus)
    tok.sauvegarder(TOKENIZER_PATH)
    tok.rapport()


def phase_pretrain(config_modele, config_entrainement):
    """Pré-entraîne Cor sur le corpus juridique."""
    print("\n" + "="*65)
    print("  PHASE PRE-ENTRAINEMENT")
    print("="*65)

    from cor.model     import Cor
    from cor.tokenizer import CorTokenizer
    from cor.trainer   import pre_entrainer
    from cor.corpus    import charger_corpus

    # Charger le tokeniseur
    if not os.path.exists(TOKENIZER_PATH):
        print(f"[ERREUR] Tokeniseur absent : {TOKENIZER_PATH}")
        print(f"         Lancer d'abord : python scripts/train.py --phase tokenizer")
        sys.exit(1)

    tokenizer = CorTokenizer.charger(TOKENIZER_PATH)

    # Mettre à jour vocab_size depuis le tokeniseur réel
    config_modele.vocab_size = len(tokenizer.vocab)
    print(f"  vocab_size ajusté : {config_modele.vocab_size}")

    # Charger ou initialiser le modèle
    ckpt = os.path.join(CHECKPOINT_DIR, "pretrain_best.pt")
    if os.path.exists(ckpt):
        print(f"  Reprise depuis checkpoint : {ckpt}")
        modele = Cor.charger(ckpt)
    else:
        modele = Cor(config_modele)

    # Charger le corpus
    corpus = charger_corpus(dataset_path=DATASET_PATH)
    if not corpus:
        print("[ERREUR] Corpus vide")
        sys.exit(1)

    # Pré-entraîner
    modele = pre_entrainer(modele, tokenizer, corpus, config_entrainement)
    modele.sauvegarder(MODELE_PATH)
    print(f"\n[OK] Modèle sauvegardé : {MODELE_PATH}")


def phase_finetune(config_modele, config_entrainement):
    """Fine-tune Cor sur les paires question-réponse."""
    print("\n" + "="*65)
    print("  PHASE FINE-TUNING")
    print("="*65)

    from cor.model     import Cor
    from cor.tokenizer import CorTokenizer
    from cor.trainer   import fine_tuner

    # Vérifications
    for chemin, nom in [
        (TOKENIZER_PATH, "Tokeniseur"),
        (MODELE_PATH,    "Modèle pré-entraîné"),
    ]:
        if not os.path.exists(chemin):
            print(f"[ERREUR] {nom} absent : {chemin}")
            sys.exit(1)

    tokenizer = CorTokenizer.charger(TOKENIZER_PATH)

    # Charger depuis le meilleur checkpoint FT si disponible
    ckpt_ft = os.path.join(CHECKPOINT_DIR, "ft_best.pt")
    if os.path.exists(ckpt_ft):
        print(f"  Reprise depuis checkpoint FT : {ckpt_ft}")
        modele = Cor.charger(ckpt_ft)
    else:
        modele = Cor.charger(MODELE_PATH)

    # Fine-tuner
    modele = fine_tuner(
        modele, tokenizer, DATASET_PATH,
        config_entrainement, config_modele
    )
    modele.sauvegarder(MODELE_PATH)
    print(f"\n[OK] Modèle fine-tuné sauvegardé : {MODELE_PATH}")


def main():
    parser = argparse.ArgumentParser(description="COR — Entraînement")
    parser.add_argument(
        "--phase",
        choices=["all", "tokenizer", "pretrain", "finetune"],
        default="all",
        help="Phase d'entraînement à exécuter"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Config développement (12M params, rapide)"
    )
    args = parser.parse_args()

    # ── Configuration du modèle ────────────────────────────────────────
    from cor.model   import ConfigCor
    from cor.trainer import ConfigEntrainement

    if args.dev:
        # Config légère pour développement et tests
        print("[MODE DEV] 12M params — rapide, pour valider l'architecture")
        config_modele = ConfigCor(
            d_model  = 256,
            n_heads  = 8,
            n_layers = 6,
            ffn_dim  = 1024,
            max_len  = 512,
        )
        config_entrainement = ConfigEntrainement(
            batch_size         = 4,
            accumulation_steps = 2,
            epochs_pretrain    = 2,
            epochs_ft          = 3,
            lr_max             = 3e-4,
            warmup_steps       = 50,
        )
    else:
        # Config production — 50M params
        print("[MODE PROD] 50M params — entraînement complet")
        config_modele = ConfigCor(
            d_model  = 512,
            n_heads  = 16,
            n_layers = 12,
            ffn_dim  = 2048,
            max_len  = 512,
        )
        config_entrainement = ConfigEntrainement(
            batch_size         = 8,
            accumulation_steps = 4,
            epochs_pretrain    = 3,
            epochs_ft          = 5,
            lr_max             = 3e-4,
            warmup_steps       = 200,
        )

    os.makedirs(os.path.join(BASE, "models", "checkpoints"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)

    t_total = time.time()

    # ── Exécution ──────────────────────────────────────────────────────
    if args.phase in ("all", "tokenizer"):
        phase_tokenizer()

    if args.phase in ("all", "pretrain"):
        phase_pretrain(config_modele, config_entrainement)

    if args.phase in ("all", "finetune"):
        phase_finetune(config_modele, config_entrainement)

    duree = time.time() - t_total
    print(f"\n{'='*65}")
    print(f"  Entraînement terminé en {duree/60:.1f} minutes")
    print(f"  Modèle : {MODELE_PATH}")
    print(f"  Étape suivante : lancer le serveur")
    print(f"    docker build -f server/Dockerfile -t cor-server .")
    print(f"    docker run -d -p 5000:5000 -v $(pwd)/models:/app/models cor-server")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()