# scripts/train_runpod.py
# COR — Entraînement optimisé GPU (RunPod A100 / H100)
#
# Ce script remplace scripts/train.py pour l'entraînement sur GPU.
# Il ajoute :
#   - Détection et utilisation automatique du GPU
#   - Mixed Precision (float16/bfloat16) → 2x moins de VRAM, 2x plus rapide
#   - Gradient Scaler (stabilité avec float16)
#   - batch_size optimisé GPU (32-64 au lieu de 8)
#   - num_workers optimisé (4-8 au lieu de 0)
#   - Sauvegarde automatique vers Hetzner via rsync
#   - Monitoring GPU (VRAM, température, utilisation)
#   - Estimation de durée et coût RunPod en temps réel
#
# WORKFLOW RUNPOD :
#   1. Créer une instance RunPod A100 (80Go VRAM)
#   2. Uploader le projet Cor via rsync ou git clone
#   3. Lancer ce script
#   4. Récupérer cor.pt sur Hetzner automatiquement
#   5. Éteindre l'instance RunPod
#
# Usage :
#   python scripts/train_runpod.py --phase pretrain
#   python scripts/train_runpod.py --phase pretrain --dev
#   python scripts/train_runpod.py --phase all
#   python scripts/train_runpod.py --phase pretrain --precision bf16
#
# POINT CRITIQUE — coût RunPod :
#   A100 80Go  : ~$1.50-2.50/h selon disponibilité
#   H100 80Go  : ~$2.50-4.00/h
#   Estimation : 50M params, 57M tokens, 3 epochs ≈ 2-4h sur A100
#   Coût total : ~$5-10 pour un entraînement complet
#
# python scripts/train_runpod.py

import os
import sys
import argparse
import time
import json
import subprocess
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

TOKENIZER_PATH = os.path.join(BASE, "models", "cor_tokenizer.json")
MODELE_PATH    = os.path.join(BASE, "models", "cor.pt")
DATASET_PATH   = os.path.join(BASE, "data", "juridique_dataset.json")
CHECKPOINT_DIR = os.path.join(BASE, "models", "checkpoints")
LOG_PATH       = os.path.join(BASE, "models", "training_log.json")

# Serveur Hetzner pour rapatriement automatique
HETZNER_HOST   = "root@178.105.151.139"
HETZNER_PATH   = "/root/cor/models/"
SSH_KEY        = os.path.expanduser("~/.ssh/cor_hetzner")  # clé sur RunPod


# ══════════════════════════════════════════════════════════════════════
# DETECTION GPU ET CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

def detecter_gpu():
    """
    Détecte le GPU disponible et retourne la configuration optimale.

    POINT CRITIQUE — bfloat16 vs float16 :
    - bfloat16 : même plage dynamique que float32, moins précis
                 Recommandé sur A100/H100 (support natif)
                 Pas de gradient scaler nécessaire
    - float16  : plus précis mais risque d'underflow
                 Nécessite GradScaler obligatoirement
                 Compatible avec plus de GPU (V100, RTX...)

    Sur A100/H100 → bfloat16 est le meilleur choix.
    Sur V100/RTX  → float16 avec GradScaler.
    """
    import torch

    if not torch.cuda.is_available():
        print("[GPU] Aucun GPU détecté — entraînement CPU")
        print("      Ce script est optimisé pour GPU.")
        print("      Sur CPU, utiliser scripts/train.py à la place.")
        return {
            "device"        : torch.device("cpu"),
            "gpu_name"      : "CPU",
            "vram_total_gb" : 0,
            "precision"     : "float32",
            "dtype"         : torch.float32,
            "use_scaler"    : False,
            "batch_size"    : 8,
            "num_workers"   : 0,
        }

    device   = torch.device("cuda")
    gpu_name = torch.cuda.get_device_name(0)
    vram     = torch.cuda.get_device_properties(0).total_memory / (1024**3)

    print(f"\n[GPU] Détecté : {gpu_name}")
    print(f"      VRAM    : {vram:.1f} Go")

    # Choisir la précision selon le GPU
    # bfloat16 supporté nativement sur Ampere (A100) et Hopper (H100)
    supports_bf16 = torch.cuda.is_bf16_supported()

    if supports_bf16:
        precision  = "bfloat16"
        dtype      = torch.bfloat16
        use_scaler = False  # bfloat16 n'a pas besoin de GradScaler
        print(f"      Précision : bfloat16 (natif A100/H100, pas de GradScaler)")
    else:
        precision  = "float16"
        dtype      = torch.float16
        use_scaler = True   # float16 nécessite GradScaler obligatoirement
        print(f"      Précision : float16 + GradScaler")

    # Batch size selon VRAM disponible
    # Règle empirique pour 50M params, max_len=512 :
    #   40Go VRAM → batch_size=32
    #   80Go VRAM → batch_size=64
    if vram >= 70:
        batch_size  = 64
        num_workers = 8
    elif vram >= 35:
        batch_size  = 32
        num_workers = 4
    elif vram >= 15:
        batch_size  = 16
        num_workers = 4
    else:
        batch_size  = 8
        num_workers = 2

    print(f"      batch_size  : {batch_size}")
    print(f"      num_workers : {num_workers}")

    return {
        "device"        : device,
        "gpu_name"      : gpu_name,
        "vram_total_gb" : vram,
        "precision"     : precision,
        "dtype"         : dtype,
        "use_scaler"    : use_scaler,
        "batch_size"    : batch_size,
        "num_workers"   : num_workers,
    }


def monitorer_gpu():
    """
    Affiche l'utilisation GPU en temps réel.
    Nécessite nvidia-smi (disponible sur toutes les instances RunPod).
    """
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            ligne = result.stdout.strip().split("\n")[0]
            util, mem_used, mem_total, temp = ligne.split(", ")
            return (f"GPU {util}% | "
                    f"VRAM {int(mem_used)//1024:.1f}/{int(mem_total)//1024:.1f}Go | "
                    f"{temp}°C")
    except Exception:
        pass
    return "GPU stats indisponibles"


# ══════════════════════════════════════════════════════════════════════
# PRE-ENTRAINEMENT GPU
# ══════════════════════════════════════════════════════════════════════

def pre_entrainer_gpu(
    modele,
    tokenizer,
    corpus,
    config,
    gpu_config,
):
    """
    Pré-entraînement optimisé GPU avec Mixed Precision.

    Différences vs CPU :
    - autocast(dtype) : calculs en float16/bfloat16 automatiquement
    - GradScaler      : évite l'underflow des gradients en float16
    - batch_size      : 32-64 au lieu de 8
    - pin_memory=True : transfert CPU→GPU plus rapide
    - non_blocking    : transfert asynchrone des données

    POINT CRITIQUE — autocast et GradScaler :
    autocast réduit la précision pour les calculs mais garde
    les poids en float32. GradScaler amplifie les gradients
    avant le backward pour éviter qu'ils deviennent 0 en float16.
    Sans GradScaler avec float16, les gradients peuvent underflow
    → le modèle n'apprend plus après quelques étapes.
    """
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, random_split
    from cor.trainer import DatasetPreEntrainement, get_lr

    device    = gpu_config["device"]
    dtype     = gpu_config["dtype"]
    precision = gpu_config["precision"]

    print(f"\n{'='*65}")
    print(f"  PRE-ENTRAINEMENT GPU")
    print(f"  Précision : {precision}")
    print(f"  Device    : {gpu_config['gpu_name']}")
    print(f"{'='*65}")

    # Dataset
    dataset_complet = DatasetPreEntrainement(
        tokenizer, corpus, max_len=config.max_len_pretrain
    )
    n_val   = max(1, int(len(dataset_complet) * config.val_ratio))
    n_train = len(dataset_complet) - n_val
    ds_train, ds_val = random_split(
        dataset_complet, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )
    print(f"  Train : {n_train:,} exemples")
    print(f"  Val   : {n_val:,} exemples")

    loader_train = DataLoader(
        ds_train,
        batch_size  = gpu_config["batch_size"],
        shuffle     = True,
        drop_last   = True,
        num_workers = gpu_config["num_workers"],
        pin_memory  = (device.type == "cuda"),  # Optimisation GPU uniquement
        persistent_workers = gpu_config["num_workers"] > 0,
    )
    loader_val = DataLoader(
        ds_val,
        batch_size  = gpu_config["batch_size"],
        shuffle     = False,
        num_workers = gpu_config["num_workers"],
        pin_memory  = (device.type == "cuda"),
    )

    # Déplacer le modèle sur GPU
    modele = modele.to(device)
    print(f"  Modèle déplacé sur {device}")

    # Optimizer
    optimizer = torch.optim.AdamW(
        modele.parameters(),
        lr           = config.lr_max,
        weight_decay = config.weight_decay,
        betas        = (0.9, 0.95),
        fused        = True if device.type == "cuda" else False,
        # fused=True : version CUDA optimisée de AdamW (30% plus rapide)
    )

    # GradScaler — uniquement pour float16
    scaler = torch.amp.GradScaler("cuda", enabled=gpu_config["use_scaler"])

    total_steps    = len(loader_train) * config.epochs_pretrain
    step           = 0
    meilleure_val  = float("inf")
    patience_count = 0
    log_entrainement = []

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    # Estimation du coût RunPod
    t_debut_global = time.time()
    PRIX_A100_H    = 2.0  # $/h estimation

    for epoch in range(config.epochs_pretrain):

        # ── Entraînement ──────────────────────────────────────────
        modele.train()
        loss_train = 0.0
        nb_batches = 0
        t_debut    = time.time()
        optimizer.zero_grad()

        for batch_idx, (input_ids, labels) in enumerate(loader_train):

            # Transfert CPU → GPU (non_blocking = asynchrone)
            input_ids = input_ids.to(device, non_blocking=True)
            labels    = labels.to(device, non_blocking=True)

            # Mise à jour du learning rate
            lr_courant = get_lr(
                step, config.warmup_steps, total_steps,
                config.lr_max, config.lr_min
            )
            for g in optimizer.param_groups:
                g["lr"] = lr_courant

            # Forward avec Mixed Precision
            # autocast réduit automatiquement la précision des calculs
            # compatibles (matmul, conv) et garde float32 pour les autres
            with torch.autocast(device_type=device.type if device.type == "cuda" else "cpu", dtype=dtype if device.type == "cuda" else torch.float32, enabled=(device.type == "cuda")):
                logits = modele(input_ids)
                B, S, V = logits.shape
                loss = F.cross_entropy(
                    logits.reshape(B * S, V),
                    labels.reshape(B * S),
                    ignore_index=0,
                )

            # Backward avec GradScaler (float16 uniquement)
            loss_scaled = loss / config.accumulation_steps
            scaler.scale(loss_scaled).backward()

            if (batch_idx + 1) % config.accumulation_steps == 0:
                # Unscale avant clip_grad_norm
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(
                    modele.parameters(), config.grad_clip
                )
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()

            loss_train += loss.item()
            nb_batches += 1
            step       += 1

            # Log intermédiaire
            if step % config.log_every == 0:
                gpu_stats  = monitorer_gpu()
                moy_courant = loss_train / nb_batches
                duree_h    = (time.time() - t_debut_global) / 3600
                cout_est   = duree_h * PRIX_A100_H
                print(f"    Step {step:5d} | "
                      f"loss={moy_courant:.4f} | "
                      f"lr={lr_courant:.2e} | "
                      f"{gpu_stats} | "
                      f"~${cout_est:.2f}")

        # Flush gradient accumulation
        if nb_batches % config.accumulation_steps != 0:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(modele.parameters(), config.grad_clip)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad()

        moy_train = loss_train / max(nb_batches, 1)
        import math
        ppl_train = math.exp(min(moy_train, 10))

        # ── Validation ────────────────────────────────────────────
        modele.eval()
        loss_val = 0.0
        nb_val   = 0

        with torch.no_grad():
            for input_ids, labels in loader_val:
                input_ids = input_ids.to(device, non_blocking=True)
                labels    = labels.to(device, non_blocking=True)

                with torch.autocast(device_type=device.type if device.type == "cuda" else "cpu", dtype=dtype if device.type == "cuda" else torch.float32, enabled=(device.type == "cuda")):
                    logits = modele(input_ids)
                    B, S, V = logits.shape
                    loss = F.cross_entropy(
                        logits.reshape(B * S, V),
                        labels.reshape(B * S),
                        ignore_index=0,
                    )
                loss_val += loss.item()
                nb_val   += 1

        moy_val   = loss_val / max(nb_val, 1)
        ppl_val   = math.exp(min(moy_val, 10))
        duree     = time.time() - t_debut
        duree_tot = (time.time() - t_debut_global) / 3600
        cout_tot  = duree_tot * PRIX_A100_H

        print(f"\n  Epoch {epoch+1}/{config.epochs_pretrain} | "
              f"train={moy_train:.4f} (ppl={ppl_train:.1f}) | "
              f"val={moy_val:.4f} (ppl={ppl_val:.1f}) | "
              f"{duree:.0f}s | ~${cout_tot:.2f} RunPod")

        # Alerte sur-apprentissage
        if epoch > 0 and moy_val > meilleure_val * 1.05:
            print(f"  ⚠ ALERTE SUR-APPRENTISSAGE : val_loss remonte")

        # Checkpoint
        if moy_val < meilleure_val:
            meilleure_val  = moy_val
            patience_count = 0
            # Sauvegarder sur disque local RunPod
            chemin_ckpt = os.path.join(CHECKPOINT_DIR, "pretrain_best.pt")
            # Déplacer le modèle en CPU pour la sauvegarde
            modele_cpu = modele.cpu()
            modele_cpu.sauvegarder(chemin_ckpt)
            modele = modele_cpu.to(device)
            print(f"  ✓ Checkpoint sauvegardé (val={moy_val:.4f})")

            # Logger
            log_entrainement.append({
                "epoch"      : epoch + 1,
                "train_loss" : moy_train,
                "val_loss"   : moy_val,
                "ppl_val"    : ppl_val,
                "duree_s"    : duree,
                "cout_usd"   : cout_tot,
                "gpu"        : monitorer_gpu(),
            })
        else:
            patience_count += 1
            if patience_count >= config.patience:
                print(f"  Early stopping — val_loss ne s'améliore plus")
                break

    # Ramener le modèle en CPU pour sauvegarde finale
    modele = modele.cpu()

    # Sauvegarder le log
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "date"           : datetime.now().isoformat(),
            "gpu"            : gpu_config["gpu_name"],
            "precision"      : precision,
            "meilleure_val"  : meilleure_val,
            "epochs"         : log_entrainement,
            "cout_total_usd" : (time.time() - t_debut_global) / 3600 * PRIX_A100_H,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n  Pré-entraînement terminé")
    print(f"  Meilleure val_loss : {meilleure_val:.4f}")
    print(f"  Coût estimé : ~${(time.time() - t_debut_global)/3600*PRIX_A100_H:.2f}")
    return modele


# ══════════════════════════════════════════════════════════════════════
# RAPATRIEMENT AUTOMATIQUE VERS HETZNER
# ══════════════════════════════════════════════════════════════════════

def rapatrier_vers_hetzner(chemin_local: str, dry_run: bool = False):
    """
    Transfère cor.pt et les checkpoints vers le serveur Hetzner
    via rsync (reprend automatiquement si coupure).

    POINT CRITIQUE — faire ça AVANT d'éteindre RunPod :
    Une instance RunPod éteinte = données perdues.
    Ce transfert est la dernière étape obligatoire.

    POINT CRITIQUE — clé SSH :
    La clé SSH doit être présente sur RunPod dans ~/.ssh/cor_hetzner
    Uploader la clé au démarrage de l'instance RunPod :
        scp -i D:/cor_ssh/cor_hetzner D:/cor_ssh/cor_hetzner runpod@<ip>:~/.ssh/
        chmod 600 ~/.ssh/cor_hetzner
    """
    print(f"\n{'='*65}")
    print(f"  RAPATRIEMENT VERS HETZNER")
    print(f"  Source : {chemin_local}")
    print(f"  Dest   : {HETZNER_HOST}:{HETZNER_PATH}")
    print(f"{'='*65}")

    if dry_run:
        print(f"  [DRY-RUN] Simulation — pas de transfert")
        return True

    if not os.path.exists(SSH_KEY):
        print(f"  [WARN] Clé SSH absente : {SSH_KEY}")
        print(f"  Transfert manuel requis :")
        print(f"  rsync -avz models/ {HETZNER_HOST}:{HETZNER_PATH}")
        return False

    fichiers = [
        os.path.join(BASE, "models", "cor.pt"),
        os.path.join(BASE, "models", "cor_tokenizer.json"),
        os.path.join(BASE, "models", "training_log.json"),
        CHECKPOINT_DIR,
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

        print(f"\n  Transfert : {os.path.basename(fichier)}...")
        result = subprocess.run(cmd, capture_output=False)

        if result.returncode == 0:
            print(f"  ✓ Transféré")
        else:
            print(f"  ✗ Erreur transfert — relancer manuellement")
            return False

    print(f"\n  ✓ Rapatriement terminé")
    print(f"  Vérifier sur Hetzner : ls -lh {HETZNER_PATH}")
    return True


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="COR — Entraînement GPU optimisé RunPod"
    )
    parser.add_argument(
        "--phase",
        choices=["all", "pretrain", "finetune"],
        default="pretrain",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Config dev (12M params, valider architecture)"
    )
    parser.add_argument(
        "--precision",
        choices=["auto", "bf16", "fp16", "fp32"],
        default="auto",
        help="Précision (auto = détection automatique)"
    )
    parser.add_argument(
        "--no-rapatrier",
        action="store_true",
        help="Ne pas transférer vers Hetzner après entraînement"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation sans entraînement"
    )
    args = parser.parse_args()

    print("=" * 65)
    print("  COR — Entraînement GPU RunPod")
    print(f"  Phase     : {args.phase}")
    print(f"  Mode      : {'dev (12M)' if args.dev else 'prod (50M)'}")
    print(f"  Précision : {args.precision}")
    print("=" * 65)

    # Détection GPU
    gpu_config = detecter_gpu()

    # Override précision si demandé
    import torch
    if args.precision == "bf16":
        gpu_config["dtype"]      = torch.bfloat16
        gpu_config["precision"]  = "bfloat16"
        gpu_config["use_scaler"] = False
    elif args.precision == "fp16":
        gpu_config["dtype"]      = torch.float16
        gpu_config["precision"]  = "float16"
        gpu_config["use_scaler"] = True
    elif args.precision == "fp32":
        gpu_config["dtype"]      = torch.float32
        gpu_config["precision"]  = "float32"
        gpu_config["use_scaler"] = False

    # Configurations
    from cor.model   import ConfigCor
    from cor.trainer import ConfigEntrainement

    if args.dev:
        print("\n[MODE DEV] 12M params")
        config_modele = ConfigCor(
            d_model  = 256,
            n_heads  = 8,
            n_layers = 6,
            ffn_dim  = 1024,
            max_len  = 512,
        )
        config = ConfigEntrainement(
            batch_size         = min(32, gpu_config["batch_size"]),
            accumulation_steps = 2,
            epochs_pretrain    = 3,
            epochs_ft          = 5,
            lr_max             = 3e-4,
            lr_min             = 1e-5,
            warmup_steps       = 100,
            val_ratio          = 0.15,
            patience           = 3,
            num_workers        = gpu_config["num_workers"],
            log_every          = 100,
            max_len_pretrain   = 512,
            max_len_finetune   = 512,
        )
    else:
        print("\n[MODE PROD] 50M params")
        config_modele = ConfigCor(
            d_model  = 512,
            n_heads  = 16,
            n_layers = 12,
            ffn_dim  = 2048,
            max_len  = 512,
        )
        config = ConfigEntrainement(
            batch_size         = gpu_config["batch_size"],
            accumulation_steps = 2,
            epochs_pretrain    = 5,
            epochs_ft          = 5,
            lr_max             = 3e-4,
            lr_min             = 1e-5,
            warmup_steps       = 500,
            val_ratio          = 0.15,
            patience           = 3,
            num_workers        = gpu_config["num_workers"],
            log_every          = 50,
            max_len_pretrain   = 512,
            max_len_finetune   = 512,
        )

    # Vérifications
    if not os.path.exists(TOKENIZER_PATH):
        print(f"\n[ERREUR] Tokeniseur absent : {TOKENIZER_PATH}")
        print(f"  Lancer d'abord sur Hetzner :")
        print(f"  python scripts/train.py --phase tokenizer")
        sys.exit(1)

    if not os.path.exists(DATASET_PATH):
        print(f"\n[ERREUR] Dataset absent : {DATASET_PATH}")
        sys.exit(1)

    if args.dry_run:
        print("\n[DRY-RUN] Vérifications OK — pas d'entraînement lancé")
        print(f"  GPU       : {gpu_config['gpu_name']}")
        print(f"  Précision : {gpu_config['precision']}")
        print(f"  Batch     : {config.batch_size}")
        print(f"  Workers   : {config.num_workers}")
        return

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    # Charger tokeniseur et corpus
    from cor.tokenizer import CorTokenizer
    from cor.corpus    import charger_corpus
    from cor.model     import Cor

    tokenizer = CorTokenizer.charger(TOKENIZER_PATH)
    config_modele.vocab_size = len(tokenizer.vocab)
    print(f"\n  vocab_size : {config_modele.vocab_size}")

    t_total = time.time()

    # Phase pré-entraînement
    if args.phase in ("all", "pretrain"):
        corpus = charger_corpus(dataset_path=DATASET_PATH)
        print(f"  Corpus : {len(corpus):,} textes")

        # Charger ou créer le modèle
        ckpt = os.path.join(CHECKPOINT_DIR, "pretrain_best.pt")
        if os.path.exists(ckpt):
            print(f"  Reprise depuis : {ckpt}")
            modele = Cor.charger(ckpt)
        else:
            modele = Cor(config_modele)
            print(f"  Nouveau modèle : {modele.compter_parametres():,} params")

        modele = pre_entrainer_gpu(modele, tokenizer, corpus, config, gpu_config)
        modele.sauvegarder(MODELE_PATH)
        print(f"\n  Modèle sauvegardé : {MODELE_PATH}")

    # Phase fine-tuning
    if args.phase in ("all", "finetune"):
        if not os.path.exists(MODELE_PATH):
            print("[ERREUR] Pré-entraînement requis avant fine-tuning")
            sys.exit(1)

        from cor.trainer import fine_tuner
        modele = Cor.charger(MODELE_PATH)

        modele = fine_tuner(
            modele, tokenizer, DATASET_PATH, config, config_modele
        )
        modele.sauvegarder(MODELE_PATH)

    # Durée et coût total
    duree_h   = (time.time() - t_total) / 3600
    cout_est  = duree_h * 2.0  # $2/h estimation A100

    print(f"\n{'='*65}")
    print(f"  Entraînement terminé")
    print(f"  Durée   : {duree_h*60:.0f} minutes")
    print(f"  Coût    : ~${cout_est:.2f} (estimation A100 $2/h)")
    print(f"  Modèle  : {MODELE_PATH}")
    print(f"{'='*65}")

    # Rapatriement vers Hetzner
    if not args.no_rapatrier:
        print(f"\n  IMPORTANT : Transférer cor.pt vers Hetzner AVANT d'éteindre RunPod")
        rapatrier_vers_hetzner(MODELE_PATH)
    else:
        print(f"\n  ATTENTION : Transfert désactivé (--no-rapatrier)")
        print(f"  Transférer manuellement AVANT d'éteindre RunPod :")
        print(f"  rsync -avz -e 'ssh -i ~/.ssh/cor_hetzner' \\")
        print(f"    {BASE}/models/ {HETZNER_HOST}:{HETZNER_PATH}")

    print(f"\n  Étape suivante sur Hetzner :")
    print(f"  1. nano /root/cor/.env  → COR_ACTIF=true")
    print(f"  2. docker restart cor-server")
    print(f"  3. curl http://178.105.151.139:5000/health")


if __name__ == "__main__":
    main()