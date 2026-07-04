# COUCHE INFRASTRUCTURE — infrastructure/trainer.py
# Responsabilité : boucles d'entraînement, datasets, scheduler, checkpoints.
#
# Règles de couche :
#   ✓ Peut importer domain/ (Cor, ConfigCor)
#   ✓ I/O fichier autorisé (checkpoints, datasets)
#   ✗ Aucun import Flask, aucun import application/ ou api/
#
# Exports publics : pre_entrainer, fine_tuner, ConfigEntrainement,
#                   DatasetPreEntrainement, DatasetFineTuning, get_lr,
#                   calculer_loss_masquee

import os
import sys
import json
import math
import time
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, random_split
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJET not in sys.path:
    sys.path.insert(0, _PROJET)

# Métriques dashboard — import optionnel (n'arrête pas l'entraînement si absent)
try:
    from dashboard.metrics_writer import MetricsWriter as _MW
    _mw = _MW()
except Exception:
    _mw = None


def _mw_call(method: str, *args, **kwargs):
    """Appelle une méthode de MetricsWriter en silence si indisponible."""
    if _mw is not None:
        try:
            getattr(_mw, method)(*args, **kwargs)
        except Exception:
            pass


from domain.model import Cor, ConfigCor

CHECKPOINT_DIR = os.path.join(_PROJET, "models", "checkpoints")
COR_PATH       = os.path.join(_PROJET, "models", "cor.pt")
DATASET_PATH   = os.path.join(_PROJET, "data", "juridique_dataset.json")

random.seed(42)
torch.manual_seed(42)


# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION ENTRAINEMENT
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ConfigEntrainement:
    """
    Parametres d'entrainement.

    POINTS CRITIQUES :

    batch_size :
        8 sur CPU, 32-64 sur GPU A100.
        Trop petit = gradients bruites. Trop grand = generalisation reduite.
        Regle : augmenter avec accumulation_steps pour simuler un grand batch.

    lr_max :
        3e-4 est la valeur standard pour les Transformers (Karpathy rule).
        Ne jamais depasser 1e-3 — explosion garantie sans warmup suffisant.
        Pour le fine-tuning, diviser par 3 : 1e-4.

    warmup_steps :
        Minimum 1% des steps totaux.
        A 50M params, min 200 steps de warmup recommandes.
        Sans warmup : gradients explosent dans les premieres iterations.

    val_ratio :
        15% de validation est le minimum pour detecter le sur-apprentissage.
        POINT CRITIQUE : si val_loss remonte alors que train_loss descend
        → sur-apprentissage → arreter immediatement (early stopping).

    patience :
        Nombre d'epochs sans amelioration de val_loss avant arret.
        3-5 epochs est raisonnable. Ne pas mettre 1 (trop sensible au bruit).

    accumulation_steps :
        Simule un batch plus grand sans memoire supplementaire.
        batch_size=8, accumulation=4 → batch effectif = 32.
        Obligatoire sur GPU avec peu de VRAM.
    """
    # Dimensions des sequences
    max_len_pretrain : int   = 256    # Pre-entrainement : contexte seul
    max_len_finetune : int   = 512    # Fine-tuning : question+RAG+reponse

    # Batch
    batch_size       : int   = 8
    accumulation_steps : int = 4     # Batch effectif = 8 * 4 = 32

    # Epochs
    epochs_pretrain  : int   = 3
    epochs_ft        : int   = 5

    # Learning rates
    lr_max           : float = 3e-4  # Pre-entrainement
    lr_ft            : float = 1e-4  # Fine-tuning
    lr_min           : float = 1e-5  # Minimum cosine decay

    # Scheduler
    warmup_steps     : int   = 200

    # Regularisation
    weight_decay     : float = 0.01
    grad_clip        : float = 1.0

    # Validation et early stopping
    val_ratio        : float = 0.15
    patience         : int   = 3

    # Divers
    num_workers      : int   = 0     # 0 sur Windows, 2-4 sur Linux/GPU
    log_every        : int   = 50    # Afficher la loss tous les N steps


# ══════════════════════════════════════════════════════════════════════
# DATASET PRE-ENTRAINEMENT
# ══════════════════════════════════════════════════════════════════════

class DatasetPreEntrainement(Dataset):
    """
    Dataset pour le pre-entrainement — modelisation du langage.

    Objectif : le modele apprend le style juridique africain.
    Format   : sequence de tokens, predire le suivant.

    Input  : tokens[0 : S-1]
    Labels : tokens[1 : S]    (decalage d'un token)

    POINT CRITIQUE — fenetres glissantes :
    Un texte long est decoupe en fenetres qui se chevauchent a 50%.
    Avantage : plus d'exemples, meilleure couverture du corpus.
    Risque    : les exemples ne sont pas independants. Acceptable
    pour le pre-entrainement, pas pour le fine-tuning.

    POINT CRITIQUE — longueur minimale :
    On rejette les sequences < 8 tokens. En dessous, le signal
    d'apprentissage est trop faible (trop peu de contexte).
    """

    def __init__(self, tokenizer, corpus: List[str], max_len: int = 256):
        self.tokenizer = tokenizer
        self.max_len   = max_len
        self.exemples  = []

        print(f"[DATASET-PRE] Construction depuis {len(corpus)} textes...")
        rejetes = 0

        for texte in corpus:
            if not texte or not texte.strip():
                continue

            ids = tokenizer.tokeniser(texte)

            if len(ids) < 8:
                rejetes += 1
                continue

            # Fenetres glissantes avec chevauchement 50%
            pas = max_len // 2
            for i in range(0, max(1, len(ids) - 7), pas):
                fenetre = ids[i : i + max_len]
                if len(fenetre) >= 8:
                    self.exemples.append(fenetre)

        print(f"[DATASET-PRE] {len(self.exemples)} exemples "
              f"({rejetes} textes rejetes trop courts)")

        if len(self.exemples) == 0:
            raise ValueError(
                "Dataset de pre-entrainement vide. "
                "Verifier que le corpus contient des textes tokenisables."
            )

    def __len__(self) -> int:
        return len(self.exemples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        ids = self.exemples[idx]

        # Padding au max_len
        pad_id = 0
        pad    = [pad_id] * max(0, self.max_len - len(ids))
        ids    = (ids + pad)[: self.max_len]

        t = torch.tensor(ids, dtype=torch.long)

        # Input = tout sauf le dernier token
        # Labels = tout sauf le premier token (decalage)
        return t[:-1], t[1:]


# ══════════════════════════════════════════════════════════════════════
# DATASET FINE-TUNING — FORMAT STRICT AVEC [REP]
# ══════════════════════════════════════════════════════════════════════

class DatasetFineTuning(Dataset):
    """
    Dataset pour le fine-tuning question-reponse.

    FORMAT STRICT ET INVARIABLE (toujours identique) :
    ┌─────────────────────────────────────────────────────────────┐
    │ [BOS] [CM] question [SEP] passage_rag [REP] reponse [EOS]  │
    │  ↑                                     ↑                    │
    │  debut                         separateur OBLIGATOIRE       │
    │                                                             │
    │  Loss = 0 ici ──────────────┘  Loss calculee ici ──────→   │
    └─────────────────────────────────────────────────────────────┘

    POINT CRITIQUE — Pourquoi [REP] est non-negociable :
    Le modele apprend : "quand je vois [REP], je dois generer
    une reponse juridique coherente".
    Sans ce token, le modele ne sait pas ou commence la reponse.
    Il va "continuer le texte RAG" au lieu de "repondre".

    POINT CRITIQUE — Masque de loss (loss_mask) :
    On retourne un masque binaire avec chaque exemple :
        0 = position de question/RAG (loss ignoree)
        1 = position de reponse (loss calculee)

    Ce masque est utilise dans la fonction calculer_loss_masquee()
    du trainer — PAS dans le modele lui-meme.

    POINT CRITIQUE — Passage RAG aleatoire pendant le fine-tuning :
    On prend un passage aleatoire du corpus comme contexte.
    Risque : le modele peut apprendre a ignorer le passage RAG
    si les passages sont trop bruites ou non pertinents.
    Solution : utiliser de vrais passages pertinents pour chaque
    question lors du fine-tuning final (retrieval-augmented FT).
    """

    def __init__(
        self,
        tokenizer,
        paires_qr     : List[Dict],
        passages_index : List[Dict],
        config         : ConfigEntrainement,
        config_modele  : ConfigCor,
    ):
        self.tokenizer   = tokenizer
        self.max_len     = config.max_len_finetune
        self.exemples    = []

        # IDs des tokens speciaux
        bos_id = config_modele.bos_id   # 2
        eos_id = config_modele.eos_id   # 3
        sep_id = config_modele.sep_id   # 4
        rep_id = config_modele.rep_id   # 7  ← separateur contexte/reponse
        pad_id = config_modele.pad_id   # 0

        # Tokens de pays disponibles
        pays_tokens = {
            "cameroun" : tokenizer.vocab.get("[CM]", 1),
            "gabon"    : tokenizer.vocab.get("[GA]", 1),
            "benin"    : tokenizer.vocab.get("[BJ]", 1),
            "cote"     : tokenizer.vocab.get("[CI]", 1),
            "ohada"    : tokenizer.vocab.get("[CM]", 1),  # defaut
        }

        print(f"[DATASET-FT] Construction depuis {len(paires_qr)} paires Q/R...")
        rejetes = 0

        for paire in paires_qr:
            question = (paire.get("question") or "").strip()
            reponse  = (paire.get("reponse")  or "").strip()

            if not question or not reponse:
                rejetes += 1
                continue

            # Detecter le pays pour le token de pays
            q_lower  = question.lower()
            pays_id  = pays_tokens["ohada"]  # defaut
            for mot, pid in pays_tokens.items():
                if mot in q_lower:
                    pays_id = pid
                    break

            # Tokeniser la question (sans BOS/EOS)
            ids_q = tokenizer.tokeniser(question)
            # Retirer BOS et EOS si presents
            if ids_q and ids_q[0] == bos_id:
                ids_q = ids_q[1:]
            if ids_q and ids_q[-1] == eos_id:
                ids_q = ids_q[:-1]
            ids_q = ids_q[:60]  # max 60 tokens pour la question

            # Choisir un passage RAG pertinent
            # POINT CRITIQUE : ici on prend un passage aleatoire.
            # En production, utiliser le retrieval reel (TF-IDF / SBERT).
            if passages_index:
                passage = random.choice(passages_index)
                texte_p = passage.get("texte", "") if isinstance(passage, dict) else str(passage)
                ids_p   = tokenizer.tokeniser(texte_p)
                if ids_p and ids_p[0] == bos_id:
                    ids_p = ids_p[1:]
                if ids_p and ids_p[-1] == eos_id:
                    ids_p = ids_p[:-1]

                # Budget pour le passage = max_len - question - reponse - tokens speciaux
                budget_passage = self.max_len - len(ids_q) - 80 - 6
                ids_p = ids_p[: max(10, budget_passage)]
            else:
                ids_p = []

            # Tokeniser la reponse
            ids_r = tokenizer.tokeniser(reponse)
            if ids_r and ids_r[0] == bos_id:
                ids_r = ids_r[1:]
            if ids_r and ids_r[-1] == eos_id:
                ids_r = ids_r[:-1]
            ids_r = ids_r[:80]  # max 80 tokens pour la reponse

            # ─────────────────────────────────────────────────────────
            # ASSEMBLER LA SEQUENCE COMPLETE
            # Format : [BOS] pays question [SEP] passage [REP] reponse [EOS]
            # ─────────────────────────────────────────────────────────
            contexte = (
                [bos_id, pays_id] +
                ids_q +
                [sep_id] +
                ids_p +
                [rep_id]           # ← SEPARATEUR INVARIABLE
            )
            reponse_ids = ids_r + [eos_id]

            sequence_complete = (contexte + reponse_ids)[: self.max_len]

            if len(sequence_complete) < 6:
                rejetes += 1
                continue

            # ─────────────────────────────────────────────────────────
            # CONSTRUIRE LE MASQUE DE LOSS
            # 0 = ignorer (contexte : question + RAG)
            # 1 = calculer (reponse uniquement)
            # ─────────────────────────────────────────────────────────
            # Trouver la position de [REP] dans la sequence
            pos_rep = None
            for i, tok in enumerate(sequence_complete):
                if tok == rep_id:
                    pos_rep = i
                    break

            if pos_rep is None:
                # [REP] a ete tronque → exemple invalide
                rejetes += 1
                continue

            loss_mask = [0] * len(sequence_complete)
            # La loss commence AU TOKEN APRES [REP]
            for i in range(pos_rep + 1, len(sequence_complete)):
                loss_mask[i] = 1

            # Verifier qu'il y a au moins 2 tokens de reponse
            if sum(loss_mask) < 2:
                rejetes += 1
                continue

            # Padding
            longueur = len(sequence_complete)
            pad_len  = self.max_len - longueur
            sequence_complete = sequence_complete + [pad_id] * pad_len
            loss_mask         = loss_mask         + [0]      * pad_len

            self.exemples.append((
                torch.tensor(sequence_complete, dtype=torch.long),
                torch.tensor(loss_mask,         dtype=torch.long),
            ))

        print(f"[DATASET-FT] {len(self.exemples)} exemples valides "
              f"({rejetes} rejetes)")

        if len(self.exemples) == 0:
            raise ValueError(
                "Dataset de fine-tuning vide apres filtrage. "
                "Verifier les paires Q/R et que [REP] est dans le vocabulaire "
                f"(rep_id={config_modele.rep_id})."
            )

    def __len__(self) -> int:
        return len(self.exemples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.exemples[idx]


# ══════════════════════════════════════════════════════════════════════
# MASQUE DE LOSS — Coeur du fine-tuning
# ══════════════════════════════════════════════════════════════════════

def calculer_loss_masquee(
    logits    : torch.Tensor,   # (B, S, vocab_size)
    input_ids : torch.Tensor,   # (B, S) — sequence complete
    loss_mask : torch.Tensor,   # (B, S) — 0=ignorer, 1=calculer
) -> torch.Tensor:
    """
    Cross-entropy loss calculee UNIQUEMENT sur les tokens de reponse.

    PRINCIPE :
    Dans un Decoder-Only, le modele predit le token suivant a chaque
    position. Pour la position t, il predit input_ids[t+1].

    Donc :
        logits[:, :-1, :]  → predictions aux positions 0 a S-2
        input_ids[:, 1:]   → labels aux positions 1 a S-1
        loss_mask[:, 1:]   → masque decale d'un token

    POINT CRITIQUE — decalage du masque :
    Le masque est defini sur les positions de la SEQUENCE.
    Mais les logits et labels sont decales d'un token.
    On doit donc decaler le masque de la meme facon.

    Exemple :
        Sequence  : [BOS] Q [SEP] RAG [REP] R1  R2  [EOS]
        Masque    :  0    0  0    0    0    1   1    1
        Labels    :      Q [SEP] RAG [REP] R1  R2  [EOS]  (decale)
        Masque dec:  0    0  0    0    0    1   1    1
        Loss calc :                              R1  R2  [EOS]  ✓

    POINT CRITIQUE — ignore_index :
    On utilise ignore_index=-1 et on met -1 aux positions masquees.
    C'est plus propre que de multiplier la loss par le masque.
    """
    B, S, V = logits.shape

    # Decaler : predictions vs labels
    logits_dec = logits[:, :-1, :].contiguous()    # (B, S-1, V)
    labels_dec = input_ids[:, 1:].contiguous()      # (B, S-1)
    mask_dec   = loss_mask[:, 1:].contiguous()      # (B, S-1)

    # Appliquer le masque : positions a ignorer → -1
    labels_masques = labels_dec.clone()
    labels_masques[mask_dec == 0] = -1

    # Cross-entropy avec ignore_index=-1
    loss = F.cross_entropy(
        logits_dec.reshape(B * (S - 1), V),
        labels_masques.reshape(B * (S - 1)),
        ignore_index=-1,
        reduction="mean",
    )

    return loss


# ══════════════════════════════════════════════════════════════════════
# SCHEDULER — Warmup lineaire + Cosine Decay
# ══════════════════════════════════════════════════════════════════════

def get_lr(
    step          : int,
    warmup_steps  : int,
    total_steps   : int,
    lr_max        : float,
    lr_min        : float,
) -> float:
    """
    Learning rate schedule :
        - Phase 1 (0 → warmup_steps)   : montee lineaire 0 → lr_max
        - Phase 2 (warmup → total)     : descente cosine lr_max → lr_min

    POINT CRITIQUE — Pourquoi ce schedule est obligatoire :
    Au debut de l'entrainement, les poids sont aleatoires et les
    gradients sont tres grands. Un lr eleve d'emblee → explosion.
    Le warmup lineaire permet de "chauffer" le modele progressivement.

    POINT CRITIQUE — Cosine vs lineaire pour la decroissance :
    La decroissance cosine est douce au debut et rapide a la fin.
    Elle permet au modele d'explorer l'espace des solutions avant
    de converger. La decroissance lineaire est trop brusque.
    """
    if step < warmup_steps:
        # Warmup lineaire
        return lr_max * (step + 1) / warmup_steps

    # Cosine decay
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    cosine   = 0.5 * (1.0 + math.cos(math.pi * progress))
    return lr_min + (lr_max - lr_min) * cosine


# ══════════════════════════════════════════════════════════════════════
# PRE-ENTRAINEMENT
# ══════════════════════════════════════════════════════════════════════

def pre_entrainer(
    modele    : Cor,
    tokenizer,
    corpus    : List[str],
    config    : ConfigEntrainement,
) -> Cor:
    """
    Phase 1 — Pre-entrainement sur le corpus juridique.

    Objectif : le modele apprend le style et le vocabulaire juridique
    africain (OHADA, CEMAC, CM, GA, BJ...).

    Ce n'est PAS encore un modele de dialogue — c'est un modele
    qui sait "parler juridique africain".

    POINT CRITIQUE — Sur-apprentissage en pre-entrainement :
    Avec ~2M tokens, 3 epochs = le modele a vu chaque token ~3 fois.
    C'est peu. Mais au-dela de 5-10 epochs avec ce corpus,
    la val_loss va remonter → sur-apprentissage.
    Surveiller imperativement la val_loss.

    POINT CRITIQUE — Loss initiale attendue :
    Avec vocab_size=2378, la loss initiale theorique est :
        log(2378) = 7.77
    Si la loss initiale est tres differente, verifier l'initialisation.
    Si la loss ne descend pas apres 100 steps → probleme de lr ou de data.
    """
    print("\n" + "=" * 65)
    print("  PHASE 1 — Pre-entrainement")
    print("  Objectif : apprendre le style juridique africain")
    print("=" * 65)

    # Construire le dataset complet
    dataset_complet = DatasetPreEntrainement(
        tokenizer, corpus, max_len=config.max_len_pretrain
    )

    # Split train / validation
    n_val   = max(1, int(len(dataset_complet) * config.val_ratio))
    n_train = len(dataset_complet) - n_val
    ds_train, ds_val = random_split(
        dataset_complet, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    print(f"  Train : {n_train} exemples")
    print(f"  Val   : {n_val} exemples")

    loader_train = DataLoader(
        ds_train,
        batch_size  = config.batch_size,
        shuffle     = True,
        drop_last   = True,
        num_workers = config.num_workers,
        pin_memory  = False,
    )
    loader_val = DataLoader(
        ds_val,
        batch_size  = config.batch_size,
        shuffle     = False,
        drop_last   = False,
        num_workers = config.num_workers,
    )

    total_steps    = len(loader_train) * config.epochs_pretrain
    optimizer      = torch.optim.AdamW(
        modele.parameters(),
        lr           = config.lr_max,
        weight_decay = config.weight_decay,
        betas        = (0.9, 0.95),   # betas LLaMA (0.95 au lieu de 0.999)
    )

    step           = 0
    meilleure_val  = float("inf")
    patience_count = 0

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    _mw_call("start_phase", "pretrain",
             total_epochs=config.epochs_pretrain,
             total_steps=total_steps,
             config_entrainement=vars(config))
    _mw_call("set_model_info",
             nb_params=modele.compter_parametres(),
             vocab_size=modele.config.vocab_size)

    for epoch in range(config.epochs_pretrain):
        # ── Entrainement ──────────────────────────────────────────────
        modele.train()
        loss_train = 0.0
        nb_batches = 0
        t_debut    = time.time()

        optimizer.zero_grad()

        for batch_idx, (input_ids, labels) in enumerate(loader_train):

            # Mettre a jour le lr
            lr_courant = get_lr(
                step, config.warmup_steps, total_steps,
                config.lr_max, config.lr_min
            )
            for g in optimizer.param_groups:
                g["lr"] = lr_courant

            # Forward
            # DatasetPreEntrainement retourne deja input=t[:-1] et labels=t[1:].
            # Le decalage est fait dans le dataset — PAS de re-decalage ici.
            logits = modele(input_ids)   # (B, S-1, V)

            B, S, V = logits.shape
            loss = F.cross_entropy(
                logits.reshape(B * S, V),
                labels.reshape(B * S),
                ignore_index=0,
            )

            # Gradient accumulation
            loss = loss / config.accumulation_steps
            loss.backward()

            if (batch_idx + 1) % config.accumulation_steps == 0:
                torch.nn.utils.clip_grad_norm_(
                    modele.parameters(), config.grad_clip
                )
                optimizer.step()
                optimizer.zero_grad()

            loss_train += loss.item() * config.accumulation_steps
            nb_batches += 1
            step       += 1

            if step % config.log_every == 0:
                moy_courant = loss_train / nb_batches
                print(f"    Step {step:4d} | loss={moy_courant:.4f} "
                      f"| lr={lr_courant:.2e}")
                _mw_call("log_step", step=step, loss=moy_courant, lr=lr_courant)

        # Flush gradient accumulation en fin d'epoch
        if nb_batches % config.accumulation_steps != 0:
            torch.nn.utils.clip_grad_norm_(modele.parameters(), config.grad_clip)
            optimizer.step()
            optimizer.zero_grad()

        moy_train = loss_train / max(nb_batches, 1)
        ppl_train = math.exp(min(moy_train, 10))

        # ── Validation ────────────────────────────────────────────────
        modele.eval()
        loss_val   = 0.0
        nb_val     = 0

        with torch.no_grad():
            for input_ids, labels in loader_val:
                logits = modele(input_ids)   # (B, S-1, V) — decalage fait dans dataset
                B, S, V = logits.shape
                loss = F.cross_entropy(
                    logits.reshape(B * S, V),
                    labels.reshape(B * S),
                    ignore_index=0,
                )
                loss_val += loss.item()
                nb_val   += 1

        moy_val = loss_val / max(nb_val, 1)
        ppl_val = math.exp(min(moy_val, 10))
        duree   = time.time() - t_debut

        print(f"\n  Epoch {epoch+1}/{config.epochs_pretrain} "
              f"| train_loss={moy_train:.4f} (ppl={ppl_train:.1f}) "
              f"| val_loss={moy_val:.4f} (ppl={ppl_val:.1f}) "
              f"| {duree:.0f}s")

        _mw_call("log_epoch", epoch=epoch+1,
                 train_loss=moy_train, val_loss=moy_val,
                 ppl_train=ppl_train, ppl_val=ppl_val,
                 duration_s=duree)

        # POINT CRITIQUE — Alerte sur-apprentissage
        if epoch > 0 and moy_val > meilleure_val * 1.05:
            print(f"  ⚠ ALERTE : val_loss remonte ({moy_val:.4f} > "
                  f"{meilleure_val:.4f}). Risque de sur-apprentissage.")
            _mw_call("log_error",
                     f"Pré-entraîn. epoch {epoch+1} : val_loss remonte "
                     f"({moy_val:.4f} > {meilleure_val:.4f}) — risque sur-apprentissage",
                     "WARN")

        # Checkpoint si amelioration
        if moy_val < meilleure_val:
            meilleure_val  = moy_val
            patience_count = 0
            chemin_ckpt = os.path.join(CHECKPOINT_DIR, "pretrain_best.pt")
            modele.sauvegarder(chemin_ckpt)
            print(f"  ✓ Meilleur checkpoint sauvegarde (val_loss={moy_val:.4f})")
        else:
            patience_count += 1
            print(f"  Patience : {patience_count}/{config.patience}")
            if patience_count >= config.patience:
                print(f"  Early stopping — val_loss ne s'ameliore plus.")
                _mw_call("log_error",
                         f"Early stopping pré-entraîn. après {epoch+1} epochs "
                         f"(patience={config.patience})", "INFO")
                break

    print(f"\n  Pre-entrainement termine. Meilleure val_loss : {meilleure_val:.4f}")
    _mw_call("done", "pretrain")
    return modele


# ══════════════════════════════════════════════════════════════════════
# FINE-TUNING QUESTION-REPONSE
# ══════════════════════════════════════════════════════════════════════

def fine_tuner(
    modele         : Cor,
    tokenizer,
    dataset_path   : str,
    config         : ConfigEntrainement,
    config_modele  : ConfigCor,
) -> Cor:
    """
    Phase 2 — Fine-tuning sur les paires question-reponse.

    Objectif : le modele apprend a REPONDRE aux questions juridiques,
    pas seulement a continuer du texte.

    La difference avec le pre-entrainement :
    - Format de sequence strict avec [REP]
    - Loss calculee UNIQUEMENT sur les tokens de reponse
    - Learning rate plus faible (1e-4 au lieu de 3e-4)

    POINT CRITIQUE — Ordre obligatoire :
    TOUJOURS pre-entrainer avant de fine-tuner.
    Un fine-tuning depuis des poids aleatoires ne converge pas
    avec si peu de paires Q/R.

    POINT CRITIQUE — Sur-apprentissage en fine-tuning :
    Avec quelques centaines de paires Q/R, le modele peut sur-apprendre
    en 2-3 epochs. Surveiller la val_loss de tres pres.
    Si val_loss remonte des l'epoch 2 → arreter.
    """
    print("\n" + "=" * 65)
    print("  PHASE 2 — Fine-tuning Question-Reponse")
    print("  Objectif : apprendre a repondre aux questions juridiques")
    print("=" * 65)

    if not os.path.exists(dataset_path):
        print(f"[WARN] Dataset introuvable : {dataset_path}")
        print(f"       Creez juridique_dataset.json avec les cles :")
        print(f"       'paires_qr' (list) et 'passages' (list)")
        return modele

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    paires_qr = data.get("paires_qr", [])
    passages  = data.get("passages",  [])

    if not paires_qr:
        print("[WARN] Aucune paire Q/R dans le dataset — skip fine-tuning")
        return modele

    print(f"  {len(paires_qr)} paires Q/R chargees")
    print(f"  {len(passages)} passages RAG disponibles")

    # Dataset complet
    try:
        dataset_complet = DatasetFineTuning(
            tokenizer, paires_qr, passages, config, config_modele
        )
    except ValueError as e:
        print(f"[ERREUR] {e}")
        _mw_call("log_error", f"DatasetFineTuning : {e}", "ERROR")
        return modele

    # Split train / val
    n_val   = max(1, int(len(dataset_complet) * config.val_ratio))
    n_train = len(dataset_complet) - n_val
    ds_train, ds_val = random_split(
        dataset_complet, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    print(f"  Train : {n_train} exemples")
    print(f"  Val   : {n_val} exemples")

    loader_train = DataLoader(
        ds_train,
        batch_size  = config.batch_size,
        shuffle     = True,
        drop_last   = False,
        num_workers = config.num_workers,
    )
    loader_val = DataLoader(
        ds_val,
        batch_size  = config.batch_size,
        shuffle     = False,
        num_workers = config.num_workers,
    )

    total_steps   = len(loader_train) * config.epochs_ft
    optimizer     = torch.optim.AdamW(
        modele.parameters(),
        lr           = config.lr_ft,
        weight_decay = config.weight_decay,
        betas        = (0.9, 0.95),
    )

    step           = 0
    meilleure_val  = float("inf")
    patience_count = 0

    _mw_call("start_phase", "finetune",
             total_epochs=config.epochs_ft,
             total_steps=total_steps)

    for epoch in range(config.epochs_ft):
        # ── Entrainement ──────────────────────────────────────────────
        modele.train()
        loss_train = 0.0
        nb_batches = 0
        t_debut    = time.time()

        optimizer.zero_grad()

        for batch_idx, (input_ids, loss_mask) in enumerate(loader_train):

            lr_courant = get_lr(
                step,
                config.warmup_steps // 2,   # warmup plus court en FT
                total_steps,
                config.lr_ft,
                config.lr_min,
            )
            for g in optimizer.param_groups:
                g["lr"] = lr_courant

            # Forward
            logits = modele(input_ids)   # (B, S, vocab_size)

            # MASQUE DE LOSS — uniquement sur les tokens de reponse
            loss = calculer_loss_masquee(logits, input_ids, loss_mask)

            loss = loss / config.accumulation_steps
            loss.backward()

            if (batch_idx + 1) % config.accumulation_steps == 0:
                torch.nn.utils.clip_grad_norm_(
                    modele.parameters(), config.grad_clip
                )
                optimizer.step()
                optimizer.zero_grad()

            loss_train += loss.item() * config.accumulation_steps
            nb_batches += 1
            step       += 1

            if step % config.log_every == 0:
                moy_courant = loss_train / nb_batches
                print(f"    Step {step:4d} | loss={moy_courant:.4f} "
                      f"| lr={lr_courant:.2e}")
                _mw_call("log_step", step=step, loss=moy_courant, lr=lr_courant)

        # Flush
        if nb_batches % config.accumulation_steps != 0:
            torch.nn.utils.clip_grad_norm_(modele.parameters(), config.grad_clip)
            optimizer.step()
            optimizer.zero_grad()

        moy_train = loss_train / max(nb_batches, 1)
        ppl_train = math.exp(min(moy_train, 10))

        # ── Validation ────────────────────────────────────────────────
        modele.eval()
        loss_val = 0.0
        nb_val   = 0

        with torch.no_grad():
            for input_ids, loss_mask in loader_val:
                logits = modele(input_ids)
                loss   = calculer_loss_masquee(logits, input_ids, loss_mask)
                loss_val += loss.item()
                nb_val   += 1

        moy_val = loss_val / max(nb_val, 1)
        ppl_val = math.exp(min(moy_val, 10))
        duree   = time.time() - t_debut

        print(f"\n  Epoch {epoch+1}/{config.epochs_ft} "
              f"| train_loss={moy_train:.4f} (ppl={ppl_train:.1f}) "
              f"| val_loss={moy_val:.4f} (ppl={ppl_val:.1f}) "
              f"| {duree:.0f}s")

        _mw_call("log_epoch", epoch=epoch+1,
                 train_loss=moy_train, val_loss=moy_val,
                 ppl_train=ppl_train, ppl_val=ppl_val,
                 duration_s=duree)

        if epoch > 0 and moy_val > meilleure_val * 1.05:
            print(f"  ⚠ ALERTE SUR-APPRENTISSAGE : "
                  f"val_loss={moy_val:.4f} > {meilleure_val:.4f}")
            print(f"  Reduire epochs_ft ou augmenter le corpus Q/R.")
            _mw_call("log_error",
                     f"Fine-tuning epoch {epoch+1} : sur-apprentissage détecté "
                     f"val_loss={moy_val:.4f} > {meilleure_val:.4f}. "
                     "Réduire epochs_ft ou augmenter le corpus Q/R.", "WARN")

        if moy_val < meilleure_val:
            meilleure_val  = moy_val
            patience_count = 0
            chemin_ckpt = os.path.join(CHECKPOINT_DIR, "ft_best.pt")
            modele.sauvegarder(chemin_ckpt)
            print(f"  ✓ Meilleur checkpoint FT (val_loss={moy_val:.4f})")
        else:
            patience_count += 1
            print(f"  Patience : {patience_count}/{config.patience}")
            if patience_count >= config.patience:
                print(f"  Early stopping FT.")
                _mw_call("log_error",
                         f"Early stopping fine-tuning après {epoch+1} epochs "
                         f"(patience={config.patience})", "INFO")
                break

    print(f"\n  Fine-tuning termine. Meilleure val_loss : {meilleure_val:.4f}")
    _mw_call("done", "finetune")
    return modele


# ══════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════

def evaluer(modele: Cor, tokenizer, config_modele: ConfigCor):
    """
    Evaluation qualitative sur quelques exemples.

    POINT CRITIQUE — Interpretation des resultats :
    Avec des poids aleatoires ou peu entraines, les reponses seront
    incoherentes. C'est normal. Chercher :
    - Est-ce que la reponse commence apres [REP] ? ✓
    - Est-ce que le modele s'arrete a [EOS] ? ✓
    - Est-ce que le style ressemble a du juridique ? (apres entrainement)
    """
    print("\n" + "=" * 65)
    print("  EVALUATION")
    print("=" * 65)

    modele.eval()

    exemples = [
        (
            "[CM] licenciement sans preavis cameroun article 34 [SEP] "
            "article 34 code travail preavis duree categorie anciennete [REP]",
            "licenciement cameroun article 34"
        ),
        (
            "[CM] injonction payer ohada creance commerciale [SEP] "
            "procedure simplifiee recouvrement creance certaine liquide [REP]",
            "injonction payer OHADA"
        ),
        (
            "[GA] titre foncier immatriculation gabon [SEP] "
            "procedure immatriculation cadastre propriete gabon [REP]",
            "titre foncier Gabon"
        ),
    ]

    for prompt_complet, label in exemples:
        print(f"\n  [{label}]")
        print(f"  Prompt : '{prompt_complet[:80]}...'")

        reponse = modele.generer(
            tokenizer        = tokenizer,
            prompt           = prompt_complet,
            max_new_tokens   = 60,
            temperature      = 0.7,
            top_p            = 0.9,
            repetition_penalty = 1.1,
        )
        print(f"  Reponse : '{reponse[:120]}'")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  COR — Entrainement Decoder-Only Juridique Africain")
    print("=" * 65)

    # Configuration modele (Phase 1 dev, passer a prod pour 50M)
    config_modele = ConfigCor(
        d_model  = 256,    # Passer a 512 pour 50M params
        n_heads  = 8,      # Passer a 16 pour 50M params
        n_layers = 6,      # Passer a 12 pour 50M params
        ffn_dim  = 1024,   # Passer a 2048 pour 50M params
        max_len  = 512,
    )

    # Configuration entrainement
    config = ConfigEntrainement(
        batch_size         = 8,
        accumulation_steps = 4,
        epochs_pretrain    = 3,
        epochs_ft          = 5,
        lr_max             = 3e-4,
        lr_ft              = 1e-4,
        lr_min             = 1e-5,
        warmup_steps       = 200,
        val_ratio          = 0.15,
        patience           = 3,
    )

    print(f"\nConfiguration modele :")
    print(f"  d_model  : {config_modele.d_model}")
    print(f"  n_heads  : {config_modele.n_heads}")
    print(f"  n_layers : {config_modele.n_layers}")
    print(f"  ffn_dim  : {config_modele.ffn_dim}")
    print(f"  max_len  : {config_modele.max_len}")

    # Initialiser le modele
    print(f"\n1. Initialisation COR...")
    modele = Cor(config_modele)
    print(f"   Parametres : {modele.compter_parametres():,}")

    # Charger le tokeniseur
    print(f"\n2. Chargement du tokeniseur...")
    from domain.tokenizer import CorTokenizer
    chemin_tok = os.path.join(_PROJET, "models", "cor_tokenizer.json")
    tokenizer  = CorTokenizer.charger(chemin_tok)
    print(f"   Vocabulaire : {len(tokenizer.vocab)} tokens")

    # Verifier que [REP] est dans le vocabulaire
    if config_modele.rep_id not in tokenizer.vocab.values():
        print(f"\n⚠ ATTENTION : [REP] (id={config_modele.rep_id}) absent du vocabulaire !")
        print(f"  Ajouter [REP] au tokeniseur avant d'entrainer.")
        print(f"  Sans [REP], le masque de loss ne peut pas fonctionner.")
        _mw_call("log_error",
                 f"[REP] (id={config_modele.rep_id}) absent du vocabulaire — "
                 "le masque de loss ne fonctionnera pas. Ajouter [REP] au tokeniseur.", "ERROR")

    # Charger le corpus
    print(f"\n3. Chargement du corpus...")
    from infrastructure.corpus import charger_corpus
    corpus = charger_corpus()
    print(f"   {len(corpus)} textes juridiques")

    # Reprendre depuis un checkpoint si disponible
    ckpt_ft      = os.path.join(CHECKPOINT_DIR, "ft_best.pt")
    ckpt_pretrain = os.path.join(CHECKPOINT_DIR, "pretrain_best.pt")

    if os.path.exists(ckpt_ft):
        print(f"\n  Reprise depuis checkpoint FT : {ckpt_ft}")
        modele = Cor.charger(ckpt_ft)
    elif os.path.exists(ckpt_pretrain):
        print(f"\n  Reprise depuis checkpoint pre-entrainement : {ckpt_pretrain}")
        modele = Cor.charger(ckpt_pretrain)

    # Phase 1 — Pre-entrainement
    modele = pre_entrainer(modele, tokenizer, corpus, config)

    # Phase 2 — Fine-tuning
    modele = fine_tuner(modele, tokenizer, DATASET_PATH, config, config_modele)

    # Evaluation
    evaluer(modele, tokenizer, config_modele)

    # Sauvegarde finale
    print(f"\n4. Sauvegarde finale...")
    modele.sauvegarder(COR_PATH)

    print(f"\n{'='*65}")
    print(f"  COR entraine et sauvegarde.")
    print(f"  Fichier : {COR_PATH}")
    print(f"  Etape suivante : integrer dans api.py via cor_inference.py")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
