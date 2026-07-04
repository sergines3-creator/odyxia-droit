# cor_tx.py
# COR Tx — Encodeur juridique africain
#
# Architecture hybride :
#   Base          : RoBERTa (bidirectionnel, MLM)
#   Attention     : Disentangled Attention (DeBERTa style)
#                   Sépare contenu et position → meilleur sur textes juridiques longs
#   Positional    : RoPE (cohérence avec COR Decoder)
#   Normalisation : RMSNorm (cohérence avec COR Decoder)
#   Activation    : SwiGLU (cohérence avec COR Decoder)
#
# Pourquoi cette combinaison :
#   Un texte juridique africain comme
#   "L'article 34 alinéa 2 du Code du travail camerounais
#    tel que modifié par la loi n°92/007 du 14 août 1992"
#   nécessite de comprendre les RELATIONS entre tokens
#   (article ↔ alinéa ↔ code ↔ loi) indépendamment de leur position.
#   Le Disentangled Attention de DeBERTa fait exactement ça.
#
# DIFFÉRENCE FONDAMENTALE avec COR Decoder :
#   COR Decoder   → masque causal (voit seulement le passé) → génère
#   COR Tx        → attention bidirectionnelle (voit tout) → comprend
#                   Pas de masque causal. Lit le texte dans les deux sens.
#
# Tâche d'entraînement : Masked Language Modeling (MLM)
#   15% des tokens sont masqués → le modèle prédit le token masqué
#   en utilisant le contexte GAUCHE ET DROIT.
#   C'est l'inverse du Decoder qui prédit le token suivant.
#
# Usage après entraînement :
#   1. Encoder un passage juridique → vecteur 768 dims
#   2. Comparer des vecteurs par cosine similarity
#   3. Alimenter le RAG de ODYXIA
#
# Cohérence avec COR Decoder :
#   - Même tokeniseur (cor_tokenizer.json)
#   - Même RMSNorm, RoPE, SwiGLU
#   - Même vocab_size (7995 tokens)
#   - Compatible pour transfer learning futur
#
# Paramètres :
#   Config dev  : d_model=256, n_heads=8,  n_layers=6  → ~22M params
#   Config prod : d_model=768, n_heads=12, n_layers=12 → ~110M params
#
# Usage :
#   from cor_tx import CorTx, ConfigCorTx
#   config = ConfigCorTx()
#   modele = CorTx(config)
#   embeddings = modele.encoder(input_ids)  # (B, S, d_model)
#   cls_embed  = modele.cls_embedding(input_ids)  # (B, d_model)

import os
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict


# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ConfigCorTx:
    """
    Configuration de COR Tx.

    POINT CRITIQUE — d_model vs COR Decoder :
    COR Decoder utilise d_model=512 (prod).
    COR Tx utilise d_model=768 (prod) — standard BERT/RoBERTa.
    Les deux ne partagent pas directement leurs poids
    mais utilisent les mêmes composants (RMSNorm, RoPE, SwiGLU).

    POINT CRITIQUE — n_heads et d_head :
    d_model doit être divisible par n_heads.
    d_head = d_model / n_heads
    Pour Disentangled Attention : d_head pair obligatoire.
        768 / 12 = 64  ✓
        256 / 8  = 32  ✓

    POINT CRITIQUE — max_position_biases :
    Pour le Disentangled Attention, on calcule des biais
    de position relatifs entre -max_pos et +max_pos.
    max_position_biases = 2 * max_len suffit généralement.
    """

    # Vocabulaire — même que COR Decoder
    vocab_size          : int   = 7995

    # Dimensions
    d_model             : int   = 768    # 256 pour dev, 768 pour prod
    n_heads             : int   = 12     # 8 pour dev, 12 pour prod
    n_layers            : int   = 12     # 6 pour dev, 12 pour prod
    ffn_dim             : int   = 3072   # 4 × d_model (standard)

    # Séquences
    max_len             : int   = 512

    # Disentangled Attention (DeBERTa style)
    max_position_biases : int   = 512    # Fenêtre de position relative
                                         # Doit être >= max_len

    # MLM (Masked Language Modeling)
    mlm_prob            : float = 0.15   # 15% des tokens masqués

    # Régularisation
    dropout             : float = 0.1

    # Tokens spéciaux — mêmes IDs que COR Decoder
    pad_id              : int   = 0
    bos_id              : int   = 2      # [BOS] — début de séquence
    eos_id              : int   = 3      # [EOS] — fin de séquence
    mask_id             : int   = 5      # [MASK] — token masqué pour MLM

    # Token [CLS] — représentation de la séquence entière
    # Utilisé pour produire l'embedding de la phrase
    # POINT CRITIQUE : [CLS] doit être dans le tokeniseur
    # On réutilise [BOS] (id=2) comme [CLS] pour économiser un token
    cls_id              : int   = 2


# ══════════════════════════════════════════════════════════════════════
# COMPOSANTS PARTAGÉS AVEC COR DECODER
# (RMSNorm, RoPE, SwiGLU — identiques pour cohérence)
# ══════════════════════════════════════════════════════════════════════

class RMSNorm(nn.Module):
    """
    Root Mean Square Normalization.
    Identique à COR Decoder — cohérence architecturale.
    """
    def __init__(self, d_model: int, eps: float = 1e-6):
        super().__init__()
        self.eps    = eps
        self.weight = nn.Parameter(torch.ones(d_model))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rms = x.pow(2).mean(dim=-1, keepdim=True).add(self.eps).sqrt()
        return x / rms * self.weight


class RoPE(nn.Module):
    """
    Rotary Position Embedding.
    Identique à COR Decoder.

    ADAPTATION pour COR Tx :
    Dans un Encoder bidirectionnel, RoPE s'applique sur Q et K
    sans masque causal — le modèle voit le contexte complet.
    Les distances relatives sont calculées dans les deux sens.
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
        t     = torch.arange(seq_len, device=self.inv_freq.device).float()
        freqs = torch.outer(t, self.inv_freq)
        emb   = torch.cat([freqs, freqs], dim=-1)
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


class SwiGLU(nn.Module):
    """
    SwiGLU Feed-Forward Network.
    Identique à COR Decoder — cohérence architecturale.

    Formule : SwiGLU(x) = SiLU(W1·x) ⊗ (W2·x)
    """
    def __init__(self, d_model: int, ffn_dim: int, dropout: float = 0.1):
        super().__init__()
        self.W1      = nn.Linear(d_model, ffn_dim, bias=False)
        self.W2      = nn.Linear(d_model, ffn_dim, bias=False)
        self.W3      = nn.Linear(ffn_dim, d_model, bias=False)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.dropout(self.W3(F.silu(self.W1(x)) * self.W2(x)))


# ══════════════════════════════════════════════════════════════════════
# DISENTANGLED ATTENTION (DeBERTa style)
#
# CONCEPT FONDAMENTAL :
# L'attention standard calcule le score entre deux tokens
# en fonction de leur CONTENU uniquement :
#   score(i, j) = Q_i · K_j
#
# Le Disentangled Attention sépare en 3 composantes :
#   score(i, j) = contenu-à-contenu
#               + contenu-à-position
#               + position-à-contenu
#
# Pourquoi c'est important pour le droit africain :
#   "L'article 34 du Code du travail"
#    vs
#   "Le Code du travail, article 34"
#
#   Même tokens, même contenu, ordre différent.
#   L'attention standard traite les deux pareil.
#   Le Disentangled Attention comprend que la POSITION
#   de "article 34" change son rôle sémantique.
#
# Implémentation :
#   - Q_c, K_c : projections de contenu (comme attention standard)
#   - Q_r, K_r : projections de position relative (nouveauté DeBERTa)
#   - Score = Q_c·K_c + Q_c·K_r + Q_r·K_c (3 termes)
#   - Normalisé par sqrt(3 * d_head) pour compenser
# ══════════════════════════════════════════════════════════════════════

class DisentangledAttention(nn.Module):
    """
    Disentangled Self-Attention (DeBERTa v2 style) avec RoPE.

    ADAPTATION vs DeBERTa original :
    DeBERTa utilise des embeddings de position absolus appris.
    COR Tx utilise RoPE (relatif) pour cohérence avec COR Decoder.
    Les embeddings de position relative sont calculés depuis RoPE.

    POINT CRITIQUE — masque de padding :
    Contrairement au Decoder, l'Encoder n'a pas de masque causal.
    Il a un masque de padding : les tokens [PAD] (id=0) ne participent
    pas à l'attention — leur score est mis à -inf avant softmax.

    POINT CRITIQUE — max_position_biases :
    On pré-calcule des embeddings pour les positions relatives
    de -max_pos à +max_pos. Position i-j est bornée dans cette fenêtre.
    """

    def __init__(self, config: ConfigCorTx):
        super().__init__()

        assert config.d_model % config.n_heads == 0
        assert (config.d_model // config.n_heads) % 2 == 0, \
            "d_head doit être pair pour Disentangled Attention"

        self.d_model  = config.d_model
        self.n_heads  = config.n_heads
        self.d_head   = config.d_model // config.n_heads
        self.max_pos  = config.max_position_biases
        self.dropout  = config.dropout

        # Projections de CONTENU (comme attention standard)
        self.W_qc = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_kc = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_v  = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_o  = nn.Linear(config.d_model, config.d_model, bias=False)

        # Projections de POSITION RELATIVE (nouveauté DeBERTa)
        # Embeddings pour les distances relatives -max_pos à +max_pos
        self.pos_embeddings = nn.Embedding(2 * config.max_position_biases, config.d_model)
        self.W_qr = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_kr = nn.Linear(config.d_model, config.d_model, bias=False)

        # RoPE sur Q et K de contenu
        self.rope = RoPE(self.d_head, config.max_len)

        self.attn_dropout = nn.Dropout(config.dropout)
        self.scale = math.sqrt(3 * self.d_head)  # sqrt(3) pour 3 termes

    def _get_position_embeddings(self, seq_len: int, device: torch.device) -> torch.Tensor:
        """
        Calcule les embeddings de position relative pour une séquence.

        Pour chaque paire (i, j), la distance relative est j - i.
        Bornée dans [-max_pos, max_pos] et décalée de +max_pos
        pour indexer l'embedding positif.

        Retourne : (1, seq_len, seq_len, d_model)
        """
        positions = torch.arange(seq_len, device=device)
        # Distance relative j - i pour chaque paire
        rel_pos = positions.unsqueeze(0) - positions.unsqueeze(1)  # (S, S)
        # Borner et décaler pour indexer
        rel_pos = rel_pos.clamp(-self.max_pos + 1, self.max_pos - 1)
        rel_pos = rel_pos + self.max_pos  # [0, 2*max_pos]
        # Embeddings de position
        pos_emb = self.pos_embeddings(rel_pos)  # (S, S, d_model)
        return pos_emb.unsqueeze(0)  # (1, S, S, d_model)

    def forward(
        self,
        x           : torch.Tensor,
        padding_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        x            : (B, S, d_model)
        padding_mask : (B, S) — True pour les tokens valides, False pour [PAD]

        Retourne : (B, S, d_model)
        """
        B, S, _ = x.shape

        # ── Projections de contenu ─────────────────────────────────────
        Q_c = self.W_qc(x)  # (B, S, d_model)
        K_c = self.W_kc(x)
        V   = self.W_v(x)

        # Reshape en têtes
        def split_heads(t):
            return t.view(B, S, self.n_heads, self.d_head).transpose(1, 2)
            # → (B, n_heads, S, d_head)

        Q_c = split_heads(Q_c)
        K_c = split_heads(K_c)
        V   = split_heads(V)

        # Appliquer RoPE sur Q_c et K_c
        Q_c = self.rope(Q_c, S)
        K_c = self.rope(K_c, S)

        # ── Projections de position relative ───────────────────────────
        pos_emb = self._get_position_embeddings(S, x.device)  # (1, S, S, d_model)

        # Q_r et K_r depuis les embeddings de position
        # On projette pos_emb pour obtenir les composantes de position
        Q_r = self.W_qr(pos_emb)  # (1, S, S, d_model)
        K_r = self.W_kr(pos_emb)

        # Reshape Q_r, K_r pour l'attention multi-têtes
        Q_r = Q_r.view(1, S, S, self.n_heads, self.d_head).permute(0, 3, 1, 2, 4)
        K_r = K_r.view(1, S, S, self.n_heads, self.d_head).permute(0, 3, 1, 2, 4)
        # → (1, n_heads, S, S, d_head)

        # ── Calcul des 3 scores Disentangled ───────────────────────────
        # 1. Contenu-à-Contenu : Q_c · K_c^T
        score_cc = torch.matmul(Q_c, K_c.transpose(-2, -1))
        # → (B, n_heads, S, S)

        # 2. Contenu-à-Position : Q_c · K_r^T
        # Q_c : (B, n_heads, S, d_head)
        # K_r : (1, n_heads, S, S, d_head) → on contracte sur d_head
        score_cp = torch.einsum('bnid,bnisd->bnis', Q_c, K_r)
        # → (B, n_heads, S, S)

        # 3. Position-à-Contenu : Q_r · K_c^T
        # Q_r : (1, n_heads, S, S, d_head)
        # K_c : (B, n_heads, S, d_head)
        score_pc = torch.einsum('bnojd,bnjd->bnjo', Q_r, K_c)
        # → (B, n_heads, S, S)

        # Score total normalisé
        attn_scores = (score_cc + score_cp + score_pc) / self.scale
        # → (B, n_heads, S, S)

        # ── Masque de padding ──────────────────────────────────────────
        if padding_mask is not None:
            # padding_mask : (B, S) — True = token valide, False = [PAD]
            # On met -inf sur les positions [PAD] pour qu'elles soient ignorées
            mask = padding_mask.unsqueeze(1).unsqueeze(2)  # (B, 1, 1, S)
            attn_scores = attn_scores.masked_fill(~mask, float('-inf'))

        # ── Softmax et attention ───────────────────────────────────────
        attn_weights = F.softmax(attn_scores, dim=-1)
        attn_weights = self.attn_dropout(attn_weights)

        # Sécurité : si une ligne est tout -inf (token [PAD]), nan → 0
        attn_weights = torch.nan_to_num(attn_weights, nan=0.0)

        # Contexte
        context = torch.matmul(attn_weights, V)  # (B, n_heads, S, d_head)

        # Recombiner les têtes
        context = context.transpose(1, 2).contiguous().view(B, S, self.d_model)

        return self.W_o(context)


# ══════════════════════════════════════════════════════════════════════
# COUCHE ENCODER
# ══════════════════════════════════════════════════════════════════════

class CoucheEncoder(nn.Module):
    """
    Une couche de l'Encoder COR Tx.

    Structure (Pre-Norm comme LLaMA/RoBERTa moderne) :
        x = x + DisentangledAttention(RMSNorm(x))
        x = x + SwiGLU(RMSNorm(x))

    POINT CRITIQUE — Pre-Norm vs Post-Norm :
    Post-Norm (BERT original) : normalisation après la résiduelle
    → instable à grande profondeur
    Pre-Norm (LLaMA, RoBERTa modern) : normalisation avant l'attention
    → plus stable, converge mieux
    On utilise Pre-Norm pour cohérence avec COR Decoder.
    """

    def __init__(self, config: ConfigCorTx):
        super().__init__()
        self.norm1 = RMSNorm(config.d_model)
        self.attn  = DisentangledAttention(config)
        self.norm2 = RMSNorm(config.d_model)
        self.ffn   = SwiGLU(config.d_model, config.ffn_dim, config.dropout)
        self.drop  = nn.Dropout(config.dropout)

    def forward(
        self,
        x           : torch.Tensor,
        padding_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        # Attention avec connexion résiduelle
        x = x + self.drop(self.attn(self.norm1(x), padding_mask))
        # FFN avec connexion résiduelle
        x = x + self.drop(self.ffn(self.norm2(x)))
        return x


# ══════════════════════════════════════════════════════════════════════
# TÊTE MLM
# ══════════════════════════════════════════════════════════════════════

class TeteMLM(nn.Module):
    """
    Tête de Masked Language Modeling pour l'entraînement.

    Lors de l'entraînement :
    1. 15% des tokens sont remplacés par [MASK]
    2. Le modèle prédit les tokens originaux
    3. Loss = cross_entropy sur les positions masquées uniquement

    Cette tête est utilisée UNIQUEMENT pendant l'entraînement.
    Pour l'inférence (embeddings), on l'ignore.

    Structure :
        Linear(d_model → d_model) + GELU + RMSNorm + Linear(d_model → vocab_size)
    """

    def __init__(self, config: ConfigCorTx):
        super().__init__()
        self.dense  = nn.Linear(config.d_model, config.d_model)
        self.norm   = RMSNorm(config.d_model)
        self.decoder = nn.Linear(config.d_model, config.vocab_size, bias=False)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """
        hidden_states : (B, S, d_model)
        Retourne      : (B, S, vocab_size) — logits pour chaque token
        """
        x = F.gelu(self.dense(hidden_states))
        x = self.norm(x)
        return self.decoder(x)


# ══════════════════════════════════════════════════════════════════════
# MODÈLE PRINCIPAL COR Tx
# ══════════════════════════════════════════════════════════════════════

class CorTx(nn.Module):
    """
    COR Tx — Encodeur juridique africain.

    Fonctions principales :
        encoder()       → représentations par token (B, S, d_model)
        cls_embedding() → représentation de la phrase entière (B, d_model)
        mlm_logits()    → logits pour l'entraînement MLM (B, S, vocab_size)

    Usage RAG :
        emb = modele.cls_embedding(input_ids)  # vecteur 768 dims
        # Stocker dans Supabase pgvector
        # Comparer avec cosine_similarity pour retrieval

    Usage entraînement :
        logits = modele.mlm_logits(input_ids, padding_mask)
        loss = F.cross_entropy(logits[mask_positions], labels[mask_positions])
    """

    def __init__(self, config: ConfigCorTx):
        super().__init__()
        self.config = config

        # Embedding des tokens
        # POINT CRITIQUE : pas d'embedding de position absolu
        # La position est gérée par RoPE dans DisentangledAttention
        self.embedding = nn.Embedding(
            config.vocab_size,
            config.d_model,
            padding_idx=config.pad_id
        )
        self.embedding_dropout = nn.Dropout(config.dropout)

        # Couches Encoder
        self.couches = nn.ModuleList([
            CoucheEncoder(config)
            for _ in range(config.n_layers)
        ])

        # Normalisation finale
        self.norm_finale = RMSNorm(config.d_model)

        # Tête MLM (entraînement)
        self.tete_mlm = TeteMLM(config)

        # Initialisation des poids
        self._initialiser_poids()

    def _initialiser_poids(self):
        """
        Initialisation standard BERT/RoBERTa.
        std=0.02 pour les matrices de projection.
        """
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.padding_idx is not None:
                    module.weight.data[module.padding_idx].zero_()

    def _construire_padding_mask(self, input_ids: torch.Tensor) -> torch.Tensor:
        """
        Construit le masque de padding depuis les input_ids.
        True = token valide, False = [PAD]
        """
        return input_ids != self.config.pad_id

    def encoder(
        self,
        input_ids   : torch.Tensor,
        padding_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Encode une séquence de tokens en représentations contextuelles.

        input_ids    : (B, S) — indices des tokens
        padding_mask : (B, S) — optionnel, calculé si absent

        Retourne : (B, S, d_model) — représentation de chaque token
        """
        if padding_mask is None:
            padding_mask = self._construire_padding_mask(input_ids)

        # Embeddings des tokens
        x = self.embedding(input_ids)       # (B, S, d_model)
        x = self.embedding_dropout(x)

        # Passer par toutes les couches encoder
        for couche in self.couches:
            x = couche(x, padding_mask)

        # Normalisation finale
        x = self.norm_finale(x)

        return x  # (B, S, d_model)

    def cls_embedding(
        self,
        input_ids   : torch.Tensor,
        padding_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Produit l'embedding de la séquence entière via le token [CLS].

        POINT CRITIQUE — Pooling strategy :
        On utilise le token [CLS] (position 0) comme représentation
        globale de la séquence — standard BERT/RoBERTa.
        Alternative : mean pooling sur tous les tokens valides.
        Le [CLS] pooling est plus rapide et généralement aussi bon.

        input_ids : (B, S)
        Retourne  : (B, d_model) — un vecteur par séquence
        """
        hidden = self.encoder(input_ids, padding_mask)  # (B, S, d_model)
        return hidden[:, 0, :]  # Token [CLS] = position 0

    def mean_pooling(
        self,
        input_ids   : torch.Tensor,
        padding_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Alternative au [CLS] : moyenne sur tous les tokens valides.

        Plus robuste sur les textes où [CLS] capte mal le contexte global.
        Recommandé pour les passages juridiques longs.

        input_ids : (B, S)
        Retourne  : (B, d_model)
        """
        if padding_mask is None:
            padding_mask = self._construire_padding_mask(input_ids)

        hidden = self.encoder(input_ids, padding_mask)  # (B, S, d_model)

        # Masquer les tokens [PAD]
        mask_expanded = padding_mask.unsqueeze(-1).float()  # (B, S, 1)
        sum_hidden    = (hidden * mask_expanded).sum(dim=1)  # (B, d_model)
        nb_tokens     = mask_expanded.sum(dim=1).clamp(min=1e-9)  # (B, 1)

        return sum_hidden / nb_tokens  # (B, d_model)

    def mlm_logits(
        self,
        input_ids   : torch.Tensor,
        padding_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Calcule les logits MLM pour l'entraînement.

        input_ids : (B, S) — tokens avec [MASK] aux positions masquées
        Retourne  : (B, S, vocab_size)
        """
        hidden = self.encoder(input_ids, padding_mask)
        return self.tete_mlm(hidden)

    def compter_parametres(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def sauvegarder(self, chemin: str):
        os.makedirs(os.path.dirname(chemin) if os.path.dirname(chemin) else '.', exist_ok=True)
        torch.save({
            'config'     : self.config,
            'state_dict' : self.state_dict(),
        }, chemin)
        print(f"[COR-TX] Sauvegardé : {chemin} ({self.compter_parametres():,} params)")

    @classmethod
    def charger(cls, chemin: str) -> 'CorTx':
        checkpoint = torch.load(chemin, map_location='cpu', weights_only=False)
        config     = checkpoint['config']
        modele     = cls(config)
        modele.load_state_dict(checkpoint['state_dict'])
        print(f"[COR-TX] Chargé : {chemin} ({modele.compter_parametres():,} params)")
        return modele


# ══════════════════════════════════════════════════════════════════════
# UTILITAIRE MLM — Masquage des tokens
# ══════════════════════════════════════════════════════════════════════

def masquer_tokens(
    input_ids : torch.Tensor,
    mask_id   : int,
    vocab_size: int,
    mlm_prob  : float = 0.15,
    pad_id    : int   = 0,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Applique le masquage MLM selon la stratégie BERT :
        80% → remplacer par [MASK]
        10% → remplacer par un token aléatoire
        10% → garder le token original

    POINT CRITIQUE — pourquoi pas 100% [MASK] :
    Si on remplace toujours par [MASK], le modèle apprend à ignorer
    les tokens non-masqués. La stratégie 80/10/10 force le modèle
    à traiter TOUS les tokens avec attention.

    input_ids : (B, S)
    Retourne  :
        masked_ids : (B, S) — input avec tokens masqués
        labels     : (B, S) — -100 pour tokens non-masqués (ignorés dans loss)
        mask_pos   : (B, S) — True aux positions masquées
    """
    labels     = input_ids.clone()
    masked_ids = input_ids.clone()

    # Probabilité de masquage (ignorer [PAD])
    proba_mask = torch.full(input_ids.shape, mlm_prob)
    proba_mask[input_ids == pad_id] = 0.0  # Ne pas masquer [PAD]

    mask_pos = torch.bernoulli(proba_mask).bool()

    # -100 = ignorer dans la loss (PyTorch convention)
    labels[~mask_pos] = -100

    # 80% → [MASK]
    indices_mask = torch.bernoulli(torch.full(input_ids.shape, 0.8)).bool() & mask_pos
    masked_ids[indices_mask] = mask_id

    # 10% → token aléatoire
    indices_alea = (
        torch.bernoulli(torch.full(input_ids.shape, 0.5)).bool()
        & mask_pos
        & ~indices_mask
    )
    tokens_aleatoires = torch.randint(vocab_size, input_ids.shape, dtype=torch.long)
    masked_ids[indices_alea] = tokens_aleatoires[indices_alea]

    # 10% → garder l'original (rien à faire)

    return masked_ids, labels, mask_pos


# ══════════════════════════════════════════════════════════════════════
# TEST RAPIDE
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  COR Tx — Test de l'architecture")
    print("=" * 65)

    # Config dev
    config = ConfigCorTx(
        vocab_size          = 7995,
        d_model             = 256,
        n_heads             = 8,
        n_layers            = 6,
        ffn_dim             = 1024,
        max_len             = 128,
        max_position_biases = 128,
    )

    modele = CorTx(config)
    nb_params = modele.compter_parametres()
    print(f"\n  Paramètres : {nb_params:,}")
    print(f"  Config dev : d_model={config.d_model}, "
          f"n_layers={config.n_layers}, n_heads={config.n_heads}")

    # Batch de test
    B, S = 2, 64
    input_ids = torch.randint(1, config.vocab_size, (B, S))
    input_ids[0, 50:] = 0  # Padding sur la fin du premier exemple

    print(f"\n  Input : {input_ids.shape}")

    # Test encoder
    hidden = modele.encoder(input_ids)
    assert hidden.shape == (B, S, config.d_model)
    print(f"  encoder()       : {hidden.shape} ✓")

    # Test cls_embedding
    cls_emb = modele.cls_embedding(input_ids)
    assert cls_emb.shape == (B, config.d_model)
    print(f"  cls_embedding() : {cls_emb.shape} ✓")

    # Test mean_pooling
    mean_emb = modele.mean_pooling(input_ids)
    assert mean_emb.shape == (B, config.d_model)
    print(f"  mean_pooling()  : {mean_emb.shape} ✓")

    # Test MLM logits
    logits = modele.mlm_logits(input_ids)
    assert logits.shape == (B, S, config.vocab_size)
    print(f"  mlm_logits()    : {logits.shape} ✓")

    # Test masquage MLM
    masked, labels, mask_pos = masquer_tokens(
        input_ids, config.mask_id, config.vocab_size
    )
    nb_masques = mask_pos.sum().item()
    print(f"  masquer_tokens(): {nb_masques} positions masquées "
          f"({nb_masques / (B*S) * 100:.1f}%) ✓")

    # Test loss MLM
    logits_flat  = logits.view(-1, config.vocab_size)
    labels_flat  = labels.view(-1)
    loss         = F.cross_entropy(logits_flat, labels_flat, ignore_index=-100)
    print(f"  Loss MLM initiale : {loss.item():.4f} ✓")

    # Test sauvegarde/chargement
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        chemin = os.path.join(tmpdir, "cor_tx_test.pt")
        modele.sauvegarder(chemin)
        modele2 = CorTx.charger(chemin)
        assert modele2.compter_parametres() == nb_params
        print(f"  Sauvegarde/chargement ✓")

    print()
    print("=" * 65)
    print(f"  COR Tx : ARCHITECTURE VALIDÉE")
    print(f"  {nb_params:,} paramètres (config dev)")
    print(f"  Config prod : ~110M params (d_model=768, n_layers=12)")
    print("=" * 65)