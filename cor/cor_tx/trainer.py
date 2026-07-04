# cor_tx/trainer.py
# COR Tx — Entraînement Masked Language Modeling (MLM)
#
# DIFFÉRENCE FONDAMENTALE avec cor/trainer.py (Decoder) :
#
#   COR Decoder s'entraîne par prédiction du token suivant :
#     Input  : [t0, t1, t2, ... tN-1]
#     Labels : [t1, t2, t3, ... tN]
#     → Objectif : "étant donné le passé, prédire le futur"
#
#   COR Tx s'entraîne par Masked Language Modeling :
#     Input  : [t0, [MASK], t2, t3, [MASK], ... tN]  ← 15% masqués
#     Labels : [-100, t1, -100, -100, t4, ... -100]   ← seulement les masqués
#     → Objectif : "étant donné le contexte COMPLET, prédire les masqués"
#
# POURQUOI MLM POUR UN ENCODEUR :
#   Le MLM force le modèle à utiliser le contexte GAUCHE ET DROIT
#   pour prédire un token. C'est impossible avec un Decoder (masque causal).
#   Résultat : l'encodeur développe une compréhension bidirectionnelle
#   profonde du texte juridique africain.
#
# PIPELINE D'ENTRAÎNEMENT :
#   1. Charger le corpus juridique africain
#   2. Tokeniser les passages
#   3. Pour chaque batch : masquer 15% des tokens
#   4. Forward pass → logits sur tout le vocabulaire
#   5. Loss = cross_entropy sur les positions masquées SEULEMENT
#   6. Backward + optimizer step
#   7. Sauvegarder le meilleur checkpoint (val_loss)
#
# TÂCHES POST-ENTRAÎNEMENT :
#   - Embeddings pour RAG (cls_embedding ou mean_pooling)
#   - Fine-tuning sur classification de domaine juridique
#   - Fine-tuning sur similarité de phrases juridiques (Sentence-BERT style)
#
# Usage :
#   python -m cor_tx.trainer --phase mlm --dev
#   python -m cor_tx.trainer --phase mlm
#   python -m cor_tx.trainer --phase mlm --gpu

import os
import sys
import json
import math
import time
import random
import argparse
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, random_split
from dataclasses import dataclass
from typing import List, Tuple, Optional

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from cor_tx.model  import CorTx, ConfigCorTx, masquer_tokens
from cor.tokenizer import CorTokenizer
from cor.corpus    import charger_corpus

CHECKPOINT_DIR  = os.path.join(BASE, "models", "checkpoints_tx")
COR_TX_PATH     = os.path.join(BASE, "models", "cor_tx.pt")
DATASET_PATH    = os.path.join(BASE, "data", "juridique_dataset.json")
TOKENIZER_PATH  = os.path.join(BASE, "models", "cor_tokenizer.json")

random.seed(42)
torch.manual_seed(42)


# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION ENTRAÎNEMENT COR Tx
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ConfigEntrainementTx:
    """
    Paramètres d'entraînement MLM pour COR Tx.

    POINT CRITIQUE — batch_size MLM vs Decoder :
    Le MLM traite des séquences complètes (pas de génération auto-régressive).
    On peut utiliser des batch_size plus grands que le Decoder.
    GPU A100 80Go : batch_size=128-256 pour COR Tx 110M params.

    POINT CRITIQUE — lr_max MLM :
    1e-4 est standard pour le MLM (légèrement plus bas que le Decoder).
    Le MLM est une tâche plus stable que la modélisation causale.

    POINT CRITIQUE — warmup_steps MLM :
    Minimum 5% des steps totaux pour le MLM.
    Plus de warmup = convergence plus stable.

    POINT CRITIQUE — mlm_prob :
    15% est la valeur originale BERT — prouvée optimale.
    Ne pas dépasser 20% (trop d'information perdue).
    Ne pas descendre sous 10% (signal trop faible).

    POINT CRITIQUE — val_ratio :
    15% de validation suffit pour détecter le sur-apprentissage.
    Sur un corpus de 162K passages : ~24K passages de validation.
    """

    # Séquences
    max_len             : int   = 512

    # Batch
    batch_size          : int   = 16       # 16 CPU, 128+ GPU
    accumulation_steps  : int   = 4        # Batch effectif = 16*4 = 64

    # Epochs
    epochs_mlm          : int   = 5        # 3 dev, 5 prod

    # Learning rates
    lr_max              : float = 1e-4     # Standard MLM
    lr_min              : float = 1e-6     # Cosine decay minimum

    # Scheduler
    warmup_steps        : int   = 500      # 5% des steps typiquement

    # Régularisation
    weight_decay        : float = 0.01
    grad_clip           : float = 1.0

    # MLM
    mlm_prob            : float = 0.15     # 15% tokens masqués

    # Validation et early stopping
    val_ratio           : float = 0.15
    patience            : int   = 3

    # Divers
    num_workers         : int   = 0        # 0 CPU, 4-8 GPU
    log_every           : int   = 100
    save_every_epochs   : int   = 1


# ══════════════════════════════════════════════════════════════════════
# DATASET MLM
# ══════════════════════════════════════════════════════════════════════

class DatasetMLM(Dataset):
    """
    Dataset pour l'entraînement MLM de COR Tx.

    DIFFÉRENCE vs DatasetPreEntrainement (Decoder) :
    Le Decoder stocke les séquences tokenisées avec leur padding.
    Le DatasetMLM stocke les séquences tokenisées SANS masquage —
    le masquage est appliqué dynamiquement à chaque batch
    (dynamic masking, comme RoBERTa).

    POINT CRITIQUE — dynamic masking :
    BERT original masquait statiquement (une fois avant l'entraînement).
    RoBERTa masque dynamiquement à chaque epoch.
    Avantage : le modèle voit des masques différents à chaque epoch
    → meilleure généralisation sur le même corpus.
    C'est ce qu'on implémente ici.

    POINT CRITIQUE — longueur des passages :
    Les passages du corpus COR font en moyenne ~200 tokens.
    On les tronque à max_len=512 si nécessaire.
    On les rejette si < 16 tokens (signal MLM trop faible).
    """

    def __init__(
        self,
        tokenizer  : CorTokenizer,
        corpus     : List[str],
        max_len    : int   = 512,
        min_len    : int   = 16,
    ):
        self.tokenizer = tokenizer
        self.max_len   = max_len
        self.pad_id    = 0

        print(f"[DATASET-MLM] Construction depuis {len(corpus)} textes...")
        t0 = time.time()

        self.sequences = []
        rejetes = 0

        for texte in corpus:
            if not texte or not texte.strip():
                continue

            ids = tokenizer.tokeniser(texte)

            if len(ids) < min_len:
                rejetes += 1
                continue

            # Tronquer à max_len
            ids = ids[:max_len]
            self.sequences.append(ids)

        duree = time.time() - t0
        print(f"[DATASET-MLM] {len(self.sequences):,} séquences "
              f"({rejetes} rejetées trop courtes) en {duree:.1f}s")

        if len(self.sequences) == 0:
            raise ValueError(
                "Dataset MLM vide — vérifier le corpus et le tokeniseur."
            )

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> torch.Tensor:
        """
        Retourne les input_ids originaux (sans masquage).
        Le masquage est appliqué dans le collate_fn.
        """
        ids = self.sequences[idx]

        # Padding au max_len
        pad = [self.pad_id] * max(0, self.max_len - len(ids))
        ids = (ids + pad)[: self.max_len]

        return torch.tensor(ids, dtype=torch.long)


def collate_mlm(
    batch     : List[torch.Tensor],
    mask_id   : int,
    vocab_size: int,
    mlm_prob  : float = 0.15,
    pad_id    : int   = 0,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Collate function pour le DataLoader MLM.

    Empile les séquences en batch et applique le masquage dynamique.

    Retourne :
        masked_ids : (B, S) — input avec tokens masqués
        labels     : (B, S) — -100 aux positions non masquées
    """
    input_ids = torch.stack(batch)  # (B, S)
    masked_ids, labels, _ = masquer_tokens(
        input_ids, mask_id, vocab_size, mlm_prob, pad_id
    )
    return masked_ids, labels


# ══════════════════════════════════════════════════════════════════════
# SCHEDULER LEARNING RATE
# ══════════════════════════════════════════════════════════════════════

def get_lr_tx(
    step         : int,
    warmup_steps : int,
    total_steps  : int,
    lr_max       : float,
    lr_min       : float,
) -> float:
    """
    Scheduler warmup linéaire + cosine decay.
    Identique au scheduler du COR Decoder — cohérence.

    Phase 1 (warmup) : lr augmente linéairement de 0 à lr_max
    Phase 2 (decay)  : lr suit un cosine de lr_max à lr_min

    POINT CRITIQUE — warmup obligatoire pour MLM :
    Sans warmup, les gradients sur la tête MLM (projection vocab)
    sont trop grands au début → explosion ou instabilité.
    """
    if step < warmup_steps:
        return lr_max * step / max(warmup_steps, 1)

    progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
    cosine   = 0.5 * (1.0 + math.cos(math.pi * progress))
    return lr_min + (lr_max - lr_min) * cosine


# ══════════════════════════════════════════════════════════════════════
# ENTRAÎNEMENT MLM
# ══════════════════════════════════════════════════════════════════════

def entrainer_mlm(
    modele    : CorTx,
    tokenizer : CorTokenizer,
    corpus    : List[str],
    config    : ConfigEntrainementTx,
    device    : torch.device,
    use_amp   : bool = False,
) -> CorTx:
    """
    Entraînement MLM complet de COR Tx.

    use_amp : Mixed Precision (bfloat16/float16) — GPU uniquement

    POINT CRITIQUE — loss MLM vs loss Decoder :
    La loss Decoder est calculée sur TOUS les tokens (prédire le suivant).
    La loss MLM est calculée sur 15% des tokens seulement.
    → La loss MLM absolue est plus haute (moins de signal par batch).
    → Une loss MLM de 2.0 est excellente (équivalent à une loss Decoder de 1.5).

    POINT CRITIQUE — perplexité MLM :
    La perplexité MLM n'est pas comparable à la perplexité Decoder.
    On suit la val_loss directement comme métrique principale.

    POINT CRITIQUE — early stopping :
    Si val_loss remonte pendant `patience` epochs → arrêt.
    Le meilleur checkpoint est toujours sauvegardé.
    """

    print(f"\n{'='*65}")
    print(f"  COR Tx — Entraînement MLM")
    print(f"  Device    : {device}")
    print(f"  Précision : {'bfloat16' if use_amp else 'float32'}")
    print(f"{'='*65}")

    # Dataset
    dataset_complet = DatasetMLM(tokenizer, corpus, config.max_len)

    n_val   = max(1, int(len(dataset_complet) * config.val_ratio))
    n_train = len(dataset_complet) - n_val
    ds_train, ds_val = random_split(
        dataset_complet, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )
    print(f"\n  Train : {n_train:,} séquences")
    print(f"  Val   : {n_val:,} séquences")

    # Collate avec masquage dynamique
    collate_fn = lambda batch: collate_mlm(
        batch,
        mask_id    = modele.config.mask_id,
        vocab_size = modele.config.vocab_size,
        mlm_prob   = config.mlm_prob,
        pad_id     = modele.config.pad_id,
    )

    loader_train = DataLoader(
        ds_train,
        batch_size  = config.batch_size,
        shuffle     = True,
        drop_last   = True,
        num_workers = config.num_workers,
        pin_memory  = (device.type == "cuda"),
        collate_fn  = collate_fn,
    )
    loader_val = DataLoader(
        ds_val,
        batch_size  = config.batch_size,
        shuffle     = False,
        num_workers = config.num_workers,
        pin_memory  = (device.type == "cuda"),
        collate_fn  = collate_fn,
    )

    # Modèle sur GPU
    modele = modele.to(device)

    # Optimizer — AdamW avec weight decay
    # POINT CRITIQUE : ne pas appliquer weight_decay sur les biais et LayerNorm
    no_decay   = {"bias", "weight"}   # RMSNorm.weight inclus
    params_wd  = [p for n, p in modele.named_parameters()
                  if not any(nd in n for nd in no_decay) and p.requires_grad]
    params_nwd = [p for n, p in modele.named_parameters()
                  if any(nd in n for nd in no_decay) and p.requires_grad]

    optimizer = torch.optim.AdamW(
        [
            {"params": params_wd,  "weight_decay": config.weight_decay},
            {"params": params_nwd, "weight_decay": 0.0},
        ],
        lr   = config.lr_max,
        betas = (0.9, 0.999),   # Standard Adam (pas 0.95 comme le Decoder)
        fused = (device.type == "cuda"),
    )

    # GradScaler pour float16 uniquement
    dtype  = torch.bfloat16 if use_amp and torch.cuda.is_bf16_supported() else torch.float32
    scaler = torch.amp.GradScaler("cuda", enabled=(use_amp and dtype == torch.float16))

    total_steps   = len(loader_train) * config.epochs_mlm
    step          = 0
    meilleure_val = float("inf")
    patience_count = 0

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    print(f"  Steps totaux    : {total_steps:,}")
    print(f"  Warmup steps    : {config.warmup_steps}")
    print(f"  Batch effectif  : {config.batch_size * config.accumulation_steps}")
    print()

    for epoch in range(config.epochs_mlm):

        # ── Entraînement ──────────────────────────────────────────────
        modele.train()
        loss_train  = 0.0
        nb_batches  = 0
        t0          = time.time()
        optimizer.zero_grad()

        for batch_idx, (masked_ids, labels) in enumerate(loader_train):

            masked_ids = masked_ids.to(device, non_blocking=True)
            labels     = labels.to(device, non_blocking=True)

            # Mise à jour lr
            lr_courant = get_lr_tx(
                step, config.warmup_steps, total_steps,
                config.lr_max, config.lr_min
            )
            for g in optimizer.param_groups:
                g["lr"] = lr_courant

            # Forward avec Mixed Precision
            use_autocast = use_amp and device.type == "cuda"
            with torch.autocast(
                device_type = device.type,
                dtype       = dtype,
                enabled     = use_autocast,
            ):
                logits = modele.mlm_logits(masked_ids)
                # Loss uniquement sur les tokens masqués (labels != -100)
                loss = F.cross_entropy(
                    logits.view(-1, modele.config.vocab_size),
                    labels.view(-1),
                    ignore_index = -100,
                )

            loss_scaled = loss / config.accumulation_steps
            scaler.scale(loss_scaled).backward()

            if (batch_idx + 1) % config.accumulation_steps == 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(modele.parameters(), config.grad_clip)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()

            loss_train += loss.item()
            nb_batches += 1
            step       += 1

            if step % config.log_every == 0:
                moy = loss_train / nb_batches
                print(f"    Step {step:5d} | loss={moy:.4f} | lr={lr_courant:.2e}")

        # Flush gradient accumulation
        if nb_batches % config.accumulation_steps != 0:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(modele.parameters(), config.grad_clip)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad()

        moy_train = loss_train / max(nb_batches, 1)

        # ── Validation ────────────────────────────────────────────────
        modele.eval()
        loss_val = 0.0
        nb_val   = 0

        with torch.no_grad():
            for masked_ids, labels in loader_val:
                masked_ids = masked_ids.to(device, non_blocking=True)
                labels     = labels.to(device, non_blocking=True)

                use_autocast = use_amp and device.type == "cuda"
                with torch.autocast(
                    device_type = device.type,
                    dtype       = dtype,
                    enabled     = use_autocast,
                ):
                    logits = modele.mlm_logits(masked_ids)
                    loss = F.cross_entropy(
                        logits.view(-1, modele.config.vocab_size),
                        labels.view(-1),
                        ignore_index = -100,
                    )

                loss_val += loss.item()
                nb_val   += 1

        moy_val  = loss_val / max(nb_val, 1)
        duree    = time.time() - t0

        print(f"\n  Epoch {epoch+1}/{config.epochs_mlm} | "
              f"train={moy_train:.4f} | "
              f"val={moy_val:.4f} | "
              f"{duree:.0f}s")

        # Alerte sur-apprentissage
        if epoch > 0 and moy_val > meilleure_val * 1.05:
            print(f"  ⚠ ALERTE : val_loss remonte — sur-apprentissage possible")

        # Checkpoint
        if moy_val < meilleure_val:
            meilleure_val  = moy_val
            patience_count = 0

            chemin_ckpt = os.path.join(CHECKPOINT_DIR, "cor_tx_best.pt")
            modele_cpu  = modele.cpu()
            modele_cpu.sauvegarder(chemin_ckpt)
            modele      = modele_cpu.to(device)
            print(f"  ✓ Checkpoint sauvegardé (val={moy_val:.4f})")
        else:
            patience_count += 1
            if patience_count >= config.patience:
                print(f"  Early stopping — val_loss ne s'améliore plus")
                break

    modele = modele.cpu()
    print(f"\n  Entraînement MLM terminé")
    print(f"  Meilleure val_loss : {meilleure_val:.4f}")
    return modele


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="COR Tx — Entraînement MLM"
    )
    parser.add_argument(
        "--phase", choices=["mlm"], default="mlm"
    )
    parser.add_argument(
        "--dev", action="store_true",
        help="Config dev (22M params, corpus réduit)"
    )
    parser.add_argument(
        "--gpu", action="store_true",
        help="Utiliser le GPU si disponible"
    )
    parser.add_argument(
        "--max-textes", type=int, default=None,
        help="Limiter le nombre de textes (pour tests)"
    )
    args = parser.parse_args()

    # Device
    if args.gpu and torch.cuda.is_available():
        device  = torch.device("cuda")
        use_amp = True
        print(f"[GPU] {torch.cuda.get_device_name(0)}")
    else:
        device  = torch.device("cpu")
        use_amp = False
        print("[CPU] Entraînement sur CPU")

    # Config modèle
    if args.dev:
        print("\n[MODE DEV] 22M params")
        config_modele = ConfigCorTx(
            vocab_size=7995, d_model=256, n_heads=8,
            n_layers=6, ffn_dim=1024, max_len=256,
            max_position_biases=256,
        )
        config = ConfigEntrainementTx(
            batch_size=8, accumulation_steps=2,
            epochs_mlm=3, lr_max=1e-4, lr_min=1e-6,
            warmup_steps=100, val_ratio=0.15, patience=3,
            num_workers=0, log_every=50,
        )
    else:
        print("\n[MODE PROD] 110M params")
        config_modele = ConfigCorTx(
            vocab_size=7995, d_model=768, n_heads=12,
            n_layers=12, ffn_dim=3072, max_len=512,
            max_position_biases=512,
        )
        config = ConfigEntrainementTx(
            batch_size=16, accumulation_steps=4,
            epochs_mlm=5, lr_max=1e-4, lr_min=1e-6,
            warmup_steps=500, val_ratio=0.15, patience=3,
            num_workers=4 if device.type == "cuda" else 0,
            log_every=100,
        )

    # Vérifications
    if not os.path.exists(TOKENIZER_PATH):
        print(f"[ERREUR] Tokeniseur absent : {TOKENIZER_PATH}")
        sys.exit(1)

    if not os.path.exists(DATASET_PATH):
        print(f"[ERREUR] Dataset absent : {DATASET_PATH}")
        sys.exit(1)

    # Charger tokeniseur et corpus
    tokenizer = CorTokenizer.charger(TOKENIZER_PATH)
    corpus    = charger_corpus(dataset_path=DATASET_PATH)

    if args.max_textes:
        import random as _random
        _random.shuffle(corpus)
        corpus = corpus[:args.max_textes]
        print(f"  Corpus limité à {len(corpus):,} textes")

    print(f"  Corpus : {len(corpus):,} textes")

    # Créer ou charger le modèle
    ckpt = os.path.join(CHECKPOINT_DIR, "cor_tx_best.pt")
    if os.path.exists(ckpt):
        print(f"  Reprise depuis : {ckpt}")
        modele = CorTx.charger(ckpt)
    else:
        modele = CorTx(config_modele)
        print(f"  Nouveau modèle : {modele.compter_parametres():,} params")

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    # Entraînement MLM
    modele = entrainer_mlm(modele, tokenizer, corpus, config, device, use_amp)

    # Sauvegarder le modèle final
    modele.sauvegarder(COR_TX_PATH)
    print(f"\n  Modèle sauvegardé : {COR_TX_PATH}")
    print(f"\n  Étapes suivantes :")
    print(f"  1. Tester les embeddings : python -m cor_tx.inference")
    print(f"  2. Intégrer dans ODYXIA RAG")


if __name__ == "__main__":
    main()