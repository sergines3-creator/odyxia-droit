# scripts/train_tx.py
# COR Tx — Entraînement MLM optimisé GPU (RunPod H100/A100)
#
# Ce script est l'équivalent de scripts/train_runpod.py pour COR Decoder
# mais adapté à l'entraînement MLM de COR Tx (Encodeur).
#
# DIFFÉRENCES vs train_runpod.py :
#   train_runpod.py → prédiction du token suivant (Decoder)
#   train_tx.py     → Masked Language Modeling (Encoder)
#
# WORKFLOW RUNPOD :
#   1. Déployer pod RunPod (H100 SXM recommandé)
#   2. git clone + git checkout develop
#   3. Transférer dataset depuis Hetzner
#   4. Lancer ce script
#   5. Récupérer cor_tx.pt sur Hetzner
#   6. Éteindre le pod
#
# Usage :
#   python scripts/train_tx.py --phase mlm --dev
#   python scripts/train_tx.py --phase mlm
#   python scripts/train_tx.py --phase mlm --max-textes 50000
#
# Estimation coût RunPod H100 ($3.29/hr) :
#   Config dev  (22M params,  70M tokens, 3 epochs) : ~1h   → ~$3
#   Config prod (110M params, 70M tokens, 5 epochs) : ~4h   → ~$13
#   Config prod (110M params, 500M tokens, 5 epochs): ~30h  → ~$99

import os
import sys
import argparse
import time
import subprocess
import torch

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from cor_tx.model   import CorTx, ConfigCorTx
from cor_tx.trainer import ConfigEntrainementTx, entrainer_mlm
from cor.tokenizer  import CorTokenizer
from cor.corpus     import charger_corpus

TOKENIZER_PATH  = os.path.join(BASE, "models", "cor_tokenizer.json")
DATASET_PATH    = os.path.join(BASE, "data",   "juridique_dataset.json")
COR_TX_PATH     = os.path.join(BASE, "models", "cor_tx.pt")
CHECKPOINT_DIR  = os.path.join(BASE, "models", "checkpoints_tx")

# Serveur Hetzner pour rapatriement
HETZNER_HOST    = "root@178.105.151.139"
HETZNER_PATH    = "/root/cor/models/"
SSH_KEY         = os.path.expanduser("~/.ssh/id_ed25519")

PRIX_H100_H     = 3.29  # $/hr estimation RunPod H100


# ══════════════════════════════════════════════════════════════════════
# DÉTECTION GPU
# ══════════════════════════════════════════════════════════════════════

def detecter_gpu():
    """
    Détecte le GPU et retourne la configuration optimale pour MLM.

    POINT CRITIQUE — batch_size MLM vs Decoder :
    Le MLM est moins gourmand en mémoire que la génération auto-régressive.
    On peut utiliser des batch_size plus grands.
        A100 80Go : batch_size=128-256
        H100 80Go : batch_size=256
    """
    if not torch.cuda.is_available():
        print("[GPU] Absent — entraînement CPU")
        print("      Sur CPU, l'entraînement est très lent.")
        print("      Utiliser RunPod pour l'entraînement sérieux.")
        return {
            "device"        : torch.device("cpu"),
            "gpu_name"      : "CPU",
            "vram_total_gb" : 0,
            "use_amp"       : False,
            "batch_size"    : 8,
            "num_workers"   : 0,
        }

    device   = torch.device("cuda")
    gpu_name = torch.cuda.get_device_name(0)
    vram     = torch.cuda.get_device_properties(0).total_memory / (1024**3)

    print(f"\n[GPU] Détecté : {gpu_name}")
    print(f"      VRAM    : {vram:.1f} Go")

    use_amp = True  # bfloat16 sur H100/A100, float16 sinon

    if vram >= 70:
        batch_size  = 128
        num_workers = 8
    elif vram >= 35:
        batch_size  = 64
        num_workers = 4
    else:
        batch_size  = 32
        num_workers = 2

    print(f"      batch_size  : {batch_size}")
    print(f"      num_workers : {num_workers}")

    return {
        "device"        : device,
        "gpu_name"      : gpu_name,
        "vram_total_gb" : vram,
        "use_amp"       : use_amp,
        "batch_size"    : batch_size,
        "num_workers"   : num_workers,
    }


def monitorer_gpu() -> str:
    """Affiche l'utilisation GPU via nvidia-smi."""
    try:
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            u, mu, mt, t = r.stdout.strip().split(", ")
            return f"GPU {u}% | VRAM {int(mu)//1024:.1f}/{int(mt)//1024:.1f}Go | {t}°C"
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# RAPATRIEMENT VERS HETZNER
# ══════════════════════════════════════════════════════════════════════

def rapatrier_vers_hetzner(dry_run: bool = False) -> bool:
    """
    Transfère cor_tx.pt et les checkpoints vers Hetzner via rsync.

    POINT CRITIQUE — faire AVANT d'éteindre RunPod :
    Instance RunPod éteinte = données perdues définitivement.
    """
    print(f"\n{'='*65}")
    print(f"  RAPATRIEMENT COR Tx → HETZNER")
    print(f"  Source : {os.path.join(BASE, 'models')}/")
    print(f"  Dest   : {HETZNER_HOST}:{HETZNER_PATH}")
    print(f"{'='*65}")

    if dry_run:
        print(f"  [DRY-RUN] Pas de transfert")
        return True

    if not os.path.exists(SSH_KEY):
        print(f"  [WARN] Clé SSH absente : {SSH_KEY}")
        print(f"  Transfert manuel :")
        print(f"  scp -i ~/.ssh/id_ed25519 models/cor_tx.pt {HETZNER_HOST}:{HETZNER_PATH}")
        return False

    fichiers = [
        COR_TX_PATH,
        os.path.join(CHECKPOINT_DIR, "cor_tx_best.pt"),
    ]

    for fichier in fichiers:
        if not os.path.exists(fichier):
            continue
        cmd = [
            "rsync", "-avz", "--progress",
            "-e", f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no",
            fichier,
            f"{HETZNER_HOST}:{HETZNER_PATH}",
        ]
        print(f"  Transfert : {os.path.basename(fichier)}...")
        r = subprocess.run(cmd, capture_output=False)
        if r.returncode != 0:
            print(f"  ✗ Erreur — relancer manuellement")
            return False
        print(f"  ✓ OK")

    print(f"  Rapatriement terminé")
    return True


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="COR Tx — Entraînement MLM GPU RunPod"
    )
    parser.add_argument("--phase", choices=["mlm"], default="mlm")
    parser.add_argument("--dev",   action="store_true",
                        help="Config dev (22M params, validation rapide)")
    parser.add_argument("--max-textes", type=int, default=None,
                        help="Limiter corpus (tests)")
    parser.add_argument("--no-rapatrier", action="store_true",
                        help="Ne pas transférer vers Hetzner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation sans entraînement")
    args = parser.parse_args()

    print("=" * 65)
    print("  COR Tx — Entraînement MLM RunPod")
    print(f"  Mode    : {'dev (22M)' if args.dev else 'prod (110M)'}")
    print("=" * 65)

    # Détection GPU
    gpu = detecter_gpu()
    device  = gpu["device"]
    use_amp = gpu["use_amp"]

    # Config modèle
    if args.dev:
        print("\n[MODE DEV] 22M params")
        config_modele = ConfigCorTx(
            vocab_size=7995, d_model=256, n_heads=8,
            n_layers=6, ffn_dim=1024, max_len=256,
            max_position_biases=256,
        )
        config = ConfigEntrainementTx(
            batch_size          = min(64, gpu["batch_size"]),
            accumulation_steps  = 2,
            epochs_mlm          = 3,
            lr_max              = 1e-4,
            lr_min              = 1e-6,
            warmup_steps        = 200,
            val_ratio           = 0.15,
            patience            = 3,
            num_workers         = gpu["num_workers"],
            log_every           = 50,
        )
    else:
        print("\n[MODE PROD] 110M params")
        config_modele = ConfigCorTx(
            vocab_size=7995, d_model=768, n_heads=12,
            n_layers=12, ffn_dim=3072, max_len=512,
            max_position_biases=512,
        )
        config = ConfigEntrainementTx(
            batch_size          = gpu["batch_size"],
            accumulation_steps  = 2,
            epochs_mlm          = 5,
            lr_max              = 1e-4,
            lr_min              = 1e-6,
            warmup_steps        = 500,
            val_ratio           = 0.15,
            patience            = 3,
            num_workers         = gpu["num_workers"],
            log_every           = 100,
        )

    # Vérifications
    for chemin, nom in [(TOKENIZER_PATH, "Tokeniseur"), (DATASET_PATH, "Dataset")]:
        if not os.path.exists(chemin):
            print(f"\n[ERREUR] {nom} absent : {chemin}")
            sys.exit(1)

    if args.dry_run:
        print("\n[DRY-RUN] OK — GPU et config validés")
        print(f"  GPU       : {gpu['gpu_name']}")
        print(f"  batch_size: {config.batch_size}")
        print(f"  amp       : {use_amp}")
        return

    # Charger tokeniseur et corpus
    tokenizer = CorTokenizer.charger(TOKENIZER_PATH)
    corpus    = charger_corpus(dataset_path=DATASET_PATH)

    if args.max_textes:
        import random
        random.shuffle(corpus)
        corpus = corpus[:args.max_textes]

    print(f"\n  Corpus : {len(corpus):,} textes")

    # Créer ou charger le modèle
    ckpt = os.path.join(CHECKPOINT_DIR, "cor_tx_best.pt")
    if os.path.exists(ckpt):
        print(f"  Reprise depuis : {ckpt}")
        modele = CorTx.charger(ckpt)
    else:
        modele = CorTx(config_modele)
        print(f"  Nouveau modèle : {modele.compter_parametres():,} params")

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    # Entraînement
    t0     = time.time()
    modele = entrainer_mlm(modele, tokenizer, corpus, config, device, use_amp)

    # Sauvegarder
    modele.sauvegarder(COR_TX_PATH)
    duree_h  = (time.time() - t0) / 3600
    cout_est = duree_h * PRIX_H100_H

    print(f"\n{'='*65}")
    print(f"  Entraînement MLM terminé")
    print(f"  Durée  : {duree_h*60:.0f} minutes")
    print(f"  Coût   : ~${cout_est:.2f} (H100 ${PRIX_H100_H}/hr)")
    print(f"  Modèle : {COR_TX_PATH}")
    print(f"{'='*65}")

    # Rapatriement
    if not args.no_rapatrier:
        rapatrier_vers_hetzner()
    else:
        print(f"\n  [ATTENTION] Transférer manuellement avant d'éteindre RunPod :")
        print(f"  scp models/cor_tx.pt {HETZNER_HOST}:{HETZNER_PATH}")

    print(f"\n  Étapes suivantes sur Hetzner :")
    print(f"  1. nano /root/cor/.env  → COR_TX_ACTIF=true")
    print(f"  2. docker restart cor-server")
    print(f"  3. Tester : python -m cor_tx.inference")


if __name__ == "__main__":
    main()