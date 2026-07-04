# COUCHE DOMAINE — domain/model.py
# Responsabilité : architecture Transformer Decoder-Only pure (Cor, ConfigCor).
#
# Règles de couche :
#   ✓ Pure PyTorch — aucune dépendance vers api/, application/, infrastructure/
#   ✓ Aucun import Flask, aucun I/O fichier dans les méthodes de calcul
#   ⚠ Les méthodes sauvegarder() / charger() accèdent au disque par pragmatisme ;
#     elles ne contiennent aucune logique métier IA.
#
# Exports publics : Cor, ConfigCor

import os
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass
from typing import Optional


# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ConfigCor:
    """
    Configuration du modele Cor.

    POINT CRITIQUE — Relation params / corpus :
    Regle empirique : 10-20 tokens d'entrainement par parametre.
    A 50M params → minimum 500M tokens necessaires pour bien generaliser.
    Avec ~2M tokens actuels → sur-apprentissage inevitable.
    Solution : augmenter massivement le corpus EN PARALLELE du code.

    Progression prevue :
        Phase 1 : d_model=256, n_layers=6  → ~12M params  (dev / test)
        Phase 2 : d_model=512, n_layers=12 → ~50M params  (production)
        Phase 3 : d_model=768, n_layers=16 → ~125M params (avec corpus suffisant)
    """

    # Vocabulaire
    vocab_size  : int = 2378     # Tokeniseur BPE juridique ODYXIA
                                  # POINT CRITIQUE : 2378 tokens = vocabulaire
                                  # tres petit. Sequences plus longues,
                                  # attention diluee. A agrandir si corpus
                                  # depasse 10M tokens.

    # Dimensions
    d_model     : int = 512      # Dimension des representations
    n_heads     : int = 16       # Tetes d'attention (d_model / n_heads = 32)
    n_layers    : int = 12       # Nombre de couches Decoder
    ffn_dim     : int = 2048     # Dimension FFN interne (4 x d_model)

    # Sequences
    max_len     : int = 512      # Longueur max contexte
                                  # POINT CRITIQUE : avec passages RAG de
                                  # 60-80 tokens + question + [REP], il reste
                                  # ~350 tokens pour la reponse. Suffisant
                                  # pour du juridique court. Pas pour des
                                  # analyses longues. Augmenter a 1024 si
                                  # GPU le permet (memoire x4).

    # Regularisation
    dropout     : float = 0.1    # Dropout standard
                                  # Reduire a 0.05 si corpus > 50M tokens

    # Tokens speciaux (doivent correspondre au tokeniseur)
    pad_id      : int = 0
    bos_id      : int = 2
    eos_id      : int = 3
    sep_id      : int = 4
    rep_id      : int = 7        # [REP] = separateur contexte / reponse
                                  # OBLIGATOIRE dans le vocabulaire
                                  # C'est ICI que le masque de loss
                                  # dans infrastructure/trainer.py commence
                                  # a calculer


# ══════════════════════════════════════════════════════════════════════
# RMSNorm — Normalisation
# ══════════════════════════════════════════════════════════════════════

class RMSNorm(nn.Module):
    """
    Root Mean Square Normalization.
    Utilisee par LLaMA et Mistral a la place de LayerNorm.

    Avantage : pas de calcul de moyenne, plus rapide, aussi stable.
    Formule  : x / sqrt(mean(x^2) + eps) * weight
    """

    def __init__(self, d_model: int, eps: float = 1e-6):
        super().__init__()
        self.eps    = eps
        self.weight = nn.Parameter(torch.ones(d_model))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rms    = x.pow(2).mean(dim=-1, keepdim=True).add(self.eps).sqrt()
        return x / rms * self.weight


# ══════════════════════════════════════════════════════════════════════
# RoPE — Rotary Positional Embedding
# ══════════════════════════════════════════════════════════════════════

class RoPE(nn.Module):
    """
    Rotary Position Embedding (Su et al., 2021).
    Utilise par LLaMA, Mistral, GPT-NeoX.

    Principe : encoder la position en FAISANT TOURNER les vecteurs Q et K
    d'un angle proportionnel a la position.

    Avantage sur le positional embedding absolu :
    - Generalise mieux aux sequences longues
    - Capture les distances relatives entre tokens
    - Pas de parametres supplementaires a apprendre

    POINT CRITIQUE : base=10000 est standard jusqu'a max_len=2048.
    Si on passe a max_len=4096+, utiliser base=500000 (LLaMA 3).
    """

    def __init__(self, d_head: int, max_len: int = 512, base: int = 10000):
        super().__init__()
        self.d_head  = d_head
        self.max_len = max_len

        inv_freq = 1.0 / (
            base ** (torch.arange(0, d_head, 2).float() / d_head)
        )
        self.register_buffer("inv_freq", inv_freq)
        self._build_cache(max_len)

    def _build_cache(self, seq_len: int):
        t      = torch.arange(seq_len, device=self.inv_freq.device).float()
        freqs  = torch.outer(t, self.inv_freq)
        emb    = torch.cat([freqs, freqs], dim=-1)
        self.register_buffer("cos_cached", emb.cos())
        self.register_buffer("sin_cached", emb.sin())

    def _rotate_half(self, x: torch.Tensor) -> torch.Tensor:
        x1 = x[..., : x.shape[-1] // 2]
        x2 = x[..., x.shape[-1] // 2 :]
        return torch.cat([-x2, x1], dim=-1)

    def forward(self, x: torch.Tensor, seq_len: int) -> torch.Tensor:
        if seq_len > self.max_len:
            self._build_cache(seq_len)

        cos = self.cos_cached[:seq_len].unsqueeze(0).unsqueeze(0)
        sin = self.sin_cached[:seq_len].unsqueeze(0).unsqueeze(0)
        return x * cos + self._rotate_half(x) * sin


# ══════════════════════════════════════════════════════════════════════
# MASQUE CAUSAL
# ══════════════════════════════════════════════════════════════════════

def construire_masque_causal(seq_len: int, device: torch.device) -> torch.Tensor:
    """
    Masque triangulaire inferieur pour l'attention causale.
    Sans ce masque, le modele triche en regardant la reponse avant de la generer.
    """
    masque = torch.full((seq_len, seq_len), float("-inf"), device=device)
    return torch.triu(masque, diagonal=1)


# ══════════════════════════════════════════════════════════════════════
# MULTI-HEAD ATTENTION avec masque causal integre
# ══════════════════════════════════════════════════════════════════════

class MultiHeadAttention(nn.Module):
    """
    Multi-Head Self-Attention avec masque causal triangulaire et RoPE.
    Pas de Cross-Attention — architecture Decoder-Only pure.
    """

    def __init__(self, config: ConfigCor):
        super().__init__()

        assert config.d_model % config.n_heads == 0, (
            f"d_model ({config.d_model}) doit etre divisible "
            f"par n_heads ({config.n_heads})"
        )

        self.d_model  = config.d_model
        self.n_heads  = config.n_heads
        self.d_head   = config.d_model // config.n_heads
        self.dropout  = config.dropout

        self.W_q = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_k = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_v = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_o = nn.Linear(config.d_model, config.d_model, bias=False)

        self.rope         = RoPE(self.d_head, max_len=config.max_len)
        self.attn_dropout = nn.Dropout(config.dropout)

    def forward(
        self,
        x      : torch.Tensor,
        masque : Optional[torch.Tensor],
    ) -> torch.Tensor:

        B, S, D = x.shape

        Q = self.W_q(x)
        K = self.W_k(x)
        V = self.W_v(x)

        Q = Q.view(B, S, self.n_heads, self.d_head).transpose(1, 2)
        K = K.view(B, S, self.n_heads, self.d_head).transpose(1, 2)
        V = V.view(B, S, self.n_heads, self.d_head).transpose(1, 2)

        Q = self.rope(Q, seq_len=S)
        K = self.rope(K, seq_len=S)

        echelle = math.sqrt(self.d_head)
        scores  = torch.matmul(Q, K.transpose(-2, -1)) / echelle

        if masque is not None:
            scores = scores + masque.unsqueeze(0).unsqueeze(0)

        poids    = F.softmax(scores, dim=-1)
        poids    = self.attn_dropout(poids)
        contexte = torch.matmul(poids, V)
        contexte = contexte.transpose(1, 2).contiguous().view(B, S, D)

        return self.W_o(contexte)


# ══════════════════════════════════════════════════════════════════════
# SwiGLU — Feed-Forward Network
# ══════════════════════════════════════════════════════════════════════

class SwiGLU(nn.Module):
    """
    SwiGLU Feed-Forward Network (Shazeer, 2020).
    Formule : FFN(x) = (Swish(W1*x) * W3*x) * W2
    """

    def __init__(self, config: ConfigCor):
        super().__init__()
        self.W1 = nn.Linear(config.d_model, config.ffn_dim, bias=False)
        self.W2 = nn.Linear(config.ffn_dim, config.d_model, bias=False)
        self.W3 = nn.Linear(config.d_model, config.ffn_dim, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate = F.silu(self.W1(x))
        x_   = self.W3(x)
        return self.W2(gate * x_)


# ══════════════════════════════════════════════════════════════════════
# COUCHE DECODER
# ══════════════════════════════════════════════════════════════════════

class CoucheDecoder(nn.Module):
    """
    Une couche Decoder-Only complete :
        x → RMSNorm → MHA (causal) → résiduel
          → RMSNorm → SwiGLU       → résiduel

    Pre-norm (normalisation AVANT l'attention) comme LLaMA.
    """

    def __init__(self, config: ConfigCor):
        super().__init__()
        self.norm1    = RMSNorm(config.d_model)
        self.attn     = MultiHeadAttention(config)
        self.norm2    = RMSNorm(config.d_model)
        self.ffn      = SwiGLU(config)
        self.dropout  = nn.Dropout(config.dropout)

    def forward(
        self,
        x      : torch.Tensor,
        masque : Optional[torch.Tensor],
    ) -> torch.Tensor:

        residuel = x
        x        = self.norm1(x)
        x        = self.attn(x, masque)
        x        = self.dropout(x)
        x        = residuel + x

        residuel = x
        x        = self.norm2(x)
        x        = self.ffn(x)
        x        = self.dropout(x)
        x        = residuel + x

        return x


# ══════════════════════════════════════════════════════════════════════
# COR — MODELE COMPLET
# ══════════════════════════════════════════════════════════════════════

class Cor(nn.Module):
    """
    COR — Modele de langage juridique africain.
    Decoder-Only pur, style LLaMA / Mistral.

    Flux complet :
        input_ids (B, S)
             ↓  Embedding
             ↓  [CoucheDecoder x N]  ← masque causal
             ↓  RMSNorm finale
             ↓  LM Head (weight tying)
        logits (B, S, vocab_size)
    """

    def __init__(self, config: ConfigCor):
        super().__init__()
        self.config = config

        self.embedding = nn.Embedding(config.vocab_size, config.d_model,
                                       padding_idx=config.pad_id)

        self.couches = nn.ModuleList([
            CoucheDecoder(config) for _ in range(config.n_layers)
        ])

        self.norm_finale = RMSNorm(config.d_model)

        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)
        self.lm_head.weight = self.embedding.weight   # Weight tying

        self._init_poids()

        print(f"[COR] Modele initialise")
        print(f"      Couches   : {config.n_layers}")
        print(f"      d_model   : {config.d_model}")
        print(f"      Tetes     : {config.n_heads}")
        print(f"      FFN dim   : {config.ffn_dim}")
        print(f"      Vocab     : {config.vocab_size}")
        print(f"      Max len   : {config.max_len}")
        print(f"      Parametres: {self.compter_parametres():,}")

    def _init_poids(self):
        std_residuel = 0.02 / math.sqrt(2 * self.config.n_layers)

        for nom, param in self.named_parameters():
            if "embedding" in nom:
                nn.init.normal_(param, mean=0.0, std=0.02)
            elif "W_o" in nom or "W2" in nom:
                nn.init.normal_(param, mean=0.0, std=std_residuel)
            elif param.dim() >= 2:
                nn.init.normal_(param, mean=0.0, std=0.02)
            elif "weight" in nom and "norm" not in nom:
                nn.init.ones_(param)

    def compter_parametres(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def forward(
        self,
        input_ids : torch.Tensor,
        masque    : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:

        B, S = input_ids.shape

        if masque is None:
            masque = construire_masque_causal(S, input_ids.device)

        x = self.embedding(input_ids)

        for couche in self.couches:
            x = couche(x, masque)

        x      = self.norm_finale(x)
        logits = self.lm_head(x)

        return logits

    @torch.no_grad()
    def generer(
        self,
        tokenizer,
        prompt             : str,
        max_new_tokens     : int   = 150,
        temperature        : float = 0.7,
        top_p              : float = 0.9,
        repetition_penalty : float = 1.1,
    ) -> str:
        """Generation autoregressive token par token."""
        self.eval()
        assert tokenizer is not None, "Tokeniseur requis pour la generation"

        ids = tokenizer.tokeniser(prompt)
        if not ids:
            return ""

        max_ctx = self.config.max_len - max_new_tokens - 1
        if len(ids) > max_ctx:
            ids = ids[-max_ctx:]

        input_ids = torch.tensor([ids], dtype=torch.long)
        generes   = []

        for _ in range(max_new_tokens):
            ctx = input_ids
            if input_ids.shape[1] > self.config.max_len:
                ctx = input_ids[:, -self.config.max_len:]

            logits         = self.forward(ctx)
            logits_dernier = logits[0, -1, :]

            if repetition_penalty != 1.0 and generes:
                for token_id in set(generes):
                    if logits_dernier[token_id] > 0:
                        logits_dernier[token_id] /= repetition_penalty
                    else:
                        logits_dernier[token_id] *= repetition_penalty

            if temperature != 1.0:
                logits_dernier = logits_dernier / temperature

            probs     = F.softmax(logits_dernier, dim=-1)
            tri_probs, tri_idx = torch.sort(probs, descending=True)
            cum_probs = torch.cumsum(tri_probs, dim=0)

            masque_noyau = cum_probs - tri_probs > top_p
            tri_probs[masque_noyau] = 0.0
            tri_probs = tri_probs / tri_probs.sum()

            idx_local = torch.multinomial(tri_probs, num_samples=1)
            prochain  = tri_idx[idx_local]
            token_id  = prochain.item()

            if token_id == self.config.eos_id:
                break

            generes.append(token_id)
            input_ids = torch.cat([input_ids, prochain.view(1, 1)], dim=1)

        if not generes:
            return ""

        return tokenizer.decoder(generes)

    def sauvegarder(self, chemin: str):
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        torch.save({
            "config" : vars(self.config),
            "modele" : self.state_dict(),
        }, chemin)
        taille = os.path.getsize(chemin) // (1024 * 1024)
        print(f"[COR] Sauvegarde : {chemin} ({taille} Mo)")

    @classmethod
    def charger(cls, chemin: str) -> "Cor":
        data   = torch.load(chemin, map_location="cpu")
        config = ConfigCor(**data["config"])
        modele = cls(config)
        modele.load_state_dict(data["modele"])
        print(f"[COR] Charge depuis : {chemin}")
        return modele
