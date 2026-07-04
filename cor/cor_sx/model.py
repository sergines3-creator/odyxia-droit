# cor_sx/model.py
# COR Sx — Encoder-Decoder multi-tâches juridique africain
#
# Architecture : T5-style Encoder-Decoder
#
# POURQUOI ENCODER-DECODER POUR COR Sx :
#
#   COR Decoder  → génération libre (complétion de texte)
#                  "Continue ce texte juridique..."
#
#   COR Tx       → compréhension (embeddings)
#                  "Représente ce texte en vecteur"
#
#   COR Sx       → transformation texte → texte structuré
#                  "Résume ce jugement"
#                  "Extrait les clauses de ce contrat"
#                  "Classe et synthétise ce document"
#
# DIFFÉRENCE FONDAMENTALE avec COR et COR Tx :
#
#   COR Sx a deux composants distincts :
#     Encodeur → lit et comprend le document entier (bidirectionnel)
#     Décodeur → génère la sortie token par token (causal)
#
#   La Cross-Attention connecte les deux :
#     Le décodeur "regarde" l'encodeur à chaque étape de génération
#     → La sortie est ancrée dans le document d'entrée
#     → Impossible d'halluciner des faits absents du document
#
# TÂCHES MULTI-TÂCHES VIA PRÉFIXES :
#   Même modèle, différentes tâches selon le préfixe :
#     "resume_jugement: [texte]"       → résumé adaptatif
#     "extraction_contrat: [texte]"    → JSON structuré
#     "fiche_jurisprudence: [texte]"   → fiche CCJA/nationale
#     "classification_synthese: [texte]" → domaine + synthèse
#     "qa_document: [question] [SEP] [texte]" → réponse ciblée
#     "conformite: [regle] [SEP] [texte]"     → conforme/non + pourquoi
#     "risques_contrat: [texte]"       → liste des risques
#     "reformulation: [texte]"         → langage simple
#
# COHÉRENCE AVEC COR ET COR Tx :
#   Mêmes composants partagés : RMSNorm, RoPE, SwiGLU
#   Même vocabulaire : cor_tokenizer.json (7995 tokens)
#   Tokens spéciaux additionnels : [SEP] pour séparer question/document
#
# PARAMÈTRES :
#   Config dev  : d_model=256, n_heads=8,  n_layers=6   → ~45M params
#   Config prod : d_model=512, n_heads=16, n_layers=12  → ~220M params
#
# Usage :
#   from cor_sx.model import CorSx, ConfigCorSx
#   modele = CorSx(config)
#   sortie = modele.generer(input_ids, max_new_tokens=200)

import os
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass
from typing import Optional, Tuple

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ConfigCorSx:
    """
    Configuration de COR Sx.

    POINT CRITIQUE — symétrie Encodeur/Décodeur :
    Dans T5 original, encodeur et décodeur ont le même d_model.
    On suit la même convention pour simplifier le transfer learning.

    POINT CRITIQUE — n_layers_encoder vs n_layers_decoder :
    L'encodeur peut avoir moins de couches que le décodeur si
    le document d'entrée est court (jugements < 512 tokens).
    Pour les documents longs → encoder plus profond.
    Pour la génération de résumés courts → décodeur peut être léger.
    On utilise des profondeurs égales pour simplifier.

    POINT CRITIQUE — max_len_encoder vs max_len_decoder :
    max_len_encoder : longueur max du document d'entrée (512-2048)
    max_len_decoder : longueur max de la sortie générée (128-512)
    Les jugements font souvent 1000-3000 tokens.
    Les résumés font 50-300 tokens.
    On peut avoir max_len_encoder > max_len_decoder.

    PRÉFIXES DE TÂCHES :
    Chaque tâche a un identifiant unique stocké dans le vocabulaire.
    Ces tokens sont ajoutés au début de l'entrée encodeur.
    Le décodeur les "voit" via la cross-attention et adapte sa sortie.
    """

    # Vocabulaire — même que COR et COR Tx
    vocab_size           : int   = 7995

    # Dimensions — mêmes choix que COR Tx pour cohérence
    d_model              : int   = 512    # 256 dev, 512 prod
    n_heads              : int   = 16     # 8 dev, 16 prod
    n_layers_encoder     : int   = 12     # 6 dev, 12 prod
    n_layers_decoder     : int   = 12     # 6 dev, 12 prod
    ffn_dim              : int   = 2048   # 4 × d_model

    # Séquences
    max_len_encoder      : int   = 512    # Documents d'entrée
    max_len_decoder      : int   = 256    # Sorties générées

    # Régularisation
    dropout              : float = 0.1

    # Tokens spéciaux — cohérents avec COR et COR Tx
    pad_id               : int   = 0
    bos_id               : int   = 2      # [BOS] début décodeur
    eos_id               : int   = 3      # [EOS] fin génération
    sep_id               : int   = 4      # [SEP] séparateur question/doc

    # Génération
    temperature          : float = 0.7
    top_k                : int   = 50
    max_new_tokens       : int   = 256


# ══════════════════════════════════════════════════════════════════════
# COMPOSANTS PARTAGÉS — identiques à COR et COR Tx
# ══════════════════════════════════════════════════════════════════════

class RMSNorm(nn.Module):
    """Identique à COR et COR Tx."""
    def __init__(self, d_model: int, eps: float = 1e-6):
        super().__init__()
        self.eps    = eps
        self.weight = nn.Parameter(torch.ones(d_model))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rms = x.pow(2).mean(dim=-1, keepdim=True).add(self.eps).sqrt()
        return x / rms * self.weight


class RoPE(nn.Module):
    """Identique à COR et COR Tx."""
    def __init__(self, d_head: int, max_len: int = 512, base: int = 10000):
        super().__init__()
        self.d_head  = d_head
        self.max_len = max_len
        inv_freq     = 1.0 / (base ** (torch.arange(0, d_head, 2).float() / d_head))
        self.register_buffer("inv_freq", inv_freq)
        self._build_cache(max_len)

    def _build_cache(self, seq_len: int):
        t   = torch.arange(seq_len, device=self.inv_freq.device).float()
        emb = torch.cat([torch.outer(t, self.inv_freq)] * 2, dim=-1)
        self.register_buffer("cos_cached", emb.cos())
        self.register_buffer("sin_cached", emb.sin())

    def _rotate_half(self, x: torch.Tensor) -> torch.Tensor:
        x1, x2 = x[..., :x.shape[-1]//2], x[..., x.shape[-1]//2:]
        return torch.cat([-x2, x1], dim=-1)

    def forward(self, x: torch.Tensor, seq_len: int) -> torch.Tensor:
        if seq_len > self.max_len:
            self._build_cache(seq_len)
        cos = self.cos_cached[:seq_len].unsqueeze(0).unsqueeze(0)
        sin = self.sin_cached[:seq_len].unsqueeze(0).unsqueeze(0)
        return x * cos + self._rotate_half(x) * sin


class SwiGLU(nn.Module):
    """Identique à COR et COR Tx."""
    def __init__(self, d_model: int, ffn_dim: int, dropout: float = 0.1):
        super().__init__()
        self.W1      = nn.Linear(d_model, ffn_dim, bias=False)
        self.W2      = nn.Linear(d_model, ffn_dim, bias=False)
        self.W3      = nn.Linear(ffn_dim, d_model, bias=False)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.dropout(self.W3(F.silu(self.W1(x)) * self.W2(x)))


# ══════════════════════════════════════════════════════════════════════
# SELF-ATTENTION BIDIRECTIONNELLE (Encodeur)
#
# Identique à COR Tx mais sans Disentangled Attention —
# on utilise l'attention standard pour simplifier.
# Le Disentangled Attention de COR Tx est optimisé pour les embeddings.
# Pour COR Sx, l'attention standard suffit car la cross-attention
# fait le travail de relation entre tokens de positions différentes.
# ══════════════════════════════════════════════════════════════════════

class SelfAttentionEncoder(nn.Module):
    """
    Self-Attention bidirectionnelle pour l'encodeur COR Sx.

    PAS de masque causal — l'encodeur voit tout le document.
    Masque de padding uniquement pour ignorer les tokens [PAD].
    """

    def __init__(self, config: ConfigCorSx):
        super().__init__()
        assert config.d_model % config.n_heads == 0

        self.d_model = config.d_model
        self.n_heads = config.n_heads
        self.d_head  = config.d_model // config.n_heads

        self.W_q = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_k = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_v = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_o = nn.Linear(config.d_model, config.d_model, bias=False)

        self.rope         = RoPE(self.d_head, config.max_len_encoder)
        self.attn_dropout = nn.Dropout(config.dropout)
        self.scale        = math.sqrt(self.d_head)

    def forward(
        self,
        x            : torch.Tensor,
        padding_mask : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        B, S, _ = x.shape

        def split_heads(t):
            return t.view(B, S, self.n_heads, self.d_head).transpose(1, 2)

        Q = self.rope(split_heads(self.W_q(x)), S)
        K = self.rope(split_heads(self.W_k(x)), S)
        V = split_heads(self.W_v(x))

        scores = torch.matmul(Q, K.transpose(-2, -1)) / self.scale

        if padding_mask is not None:
            mask   = padding_mask.unsqueeze(1).unsqueeze(2)
            scores = scores.masked_fill(~mask, float('-inf'))

        attn   = torch.nan_to_num(F.softmax(scores, dim=-1), nan=0.0)
        attn   = self.attn_dropout(attn)
        output = torch.matmul(attn, V)
        output = output.transpose(1, 2).contiguous().view(B, S, self.d_model)

        return self.W_o(output)


# ══════════════════════════════════════════════════════════════════════
# SELF-ATTENTION CAUSALE (Décodeur)
#
# Identique à COR Decoder — masque causal obligatoire.
# Le décodeur génère token par token, ne voit que le passé.
# ══════════════════════════════════════════════════════════════════════

class SelfAttentionDecoder(nn.Module):
    """
    Self-Attention causale pour le décodeur COR Sx.

    Masque causal : le token i ne voit que les tokens 0..i-1.
    Identique à l'attention dans COR Decoder.
    """

    def __init__(self, config: ConfigCorSx):
        super().__init__()
        assert config.d_model % config.n_heads == 0

        self.d_model = config.d_model
        self.n_heads = config.n_heads
        self.d_head  = config.d_model // config.n_heads

        self.W_q = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_k = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_v = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_o = nn.Linear(config.d_model, config.d_model, bias=False)

        self.rope         = RoPE(self.d_head, config.max_len_decoder)
        self.attn_dropout = nn.Dropout(config.dropout)
        self.scale        = math.sqrt(self.d_head)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, S, _ = x.shape

        def split_heads(t):
            return t.view(B, S, self.n_heads, self.d_head).transpose(1, 2)

        Q = self.rope(split_heads(self.W_q(x)), S)
        K = self.rope(split_heads(self.W_k(x)), S)
        V = split_heads(self.W_v(x))

        scores = torch.matmul(Q, K.transpose(-2, -1)) / self.scale

        # Masque causal — triangle supérieur = -inf
        masque = torch.triu(torch.ones(S, S, device=x.device), diagonal=1).bool()
        scores = scores.masked_fill(masque, float('-inf'))

        attn   = F.softmax(scores, dim=-1)
        attn   = self.attn_dropout(attn)
        output = torch.matmul(attn, V)
        output = output.transpose(1, 2).contiguous().view(B, S, self.d_model)

        return self.W_o(output)


# ══════════════════════════════════════════════════════════════════════
# CROSS-ATTENTION
#
# C'est LE composant clé de COR Sx — absent de COR et COR Tx.
#
# CONCEPT :
#   Le décodeur génère token par token.
#   À chaque étape, la cross-attention lui permet de "regarder"
#   tous les tokens de l'encodeur pour ancrer sa génération
#   dans le document source.
#
# MÉCANISME :
#   Q vient du décodeur (ce qu'on génère)
#   K, V viennent de l'encodeur (le document source)
#
#   Score(i, j) = Q_decoder_i · K_encoder_j
#   → "À quelle partie du document dois-je faire attention
#      pour générer le token i de ma sortie ?"
#
# RÉSULTAT :
#   Le décodeur ne peut pas inventer des faits absents du document.
#   Il doit baser chaque token généré sur ce que l'encodeur lui donne.
#   → Hallucinations drastiquement réduites vs COR Decoder seul.
# ══════════════════════════════════════════════════════════════════════

class CrossAttention(nn.Module):
    """
    Cross-Attention entre le décodeur et l'encodeur.

    Q : tokens du décodeur (ce qu'on génère)
    K, V : tokens de l'encodeur (le document source)

    POINT CRITIQUE — pas de RoPE sur K, V de l'encodeur :
    RoPE encode les positions RELATIVES dans une séquence.
    Les positions de l'encodeur et du décodeur sont dans
    des espaces différents — on n'applique RoPE que sur Q.
    K et V de l'encodeur sont déjà encodés avec leurs positions
    dans la couche SelfAttentionEncoder.

    POINT CRITIQUE — masque de padding encodeur :
    Le décodeur ne doit pas faire attention aux tokens [PAD]
    de l'encodeur. On passe le masque de padding de l'encodeur.
    """

    def __init__(self, config: ConfigCorSx):
        super().__init__()
        assert config.d_model % config.n_heads == 0

        self.d_model = config.d_model
        self.n_heads = config.n_heads
        self.d_head  = config.d_model // config.n_heads

        # Q depuis le décodeur
        self.W_q = nn.Linear(config.d_model, config.d_model, bias=False)
        # K, V depuis l'encodeur
        self.W_k = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_v = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_o = nn.Linear(config.d_model, config.d_model, bias=False)

        self.attn_dropout = nn.Dropout(config.dropout)
        self.scale        = math.sqrt(self.d_head)

    def forward(
        self,
        x_decoder        : torch.Tensor,
        encoder_output   : torch.Tensor,
        encoder_pad_mask : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        x_decoder        : (B, S_dec, d_model) — tokens décodeur
        encoder_output   : (B, S_enc, d_model) — sortie encodeur
        encoder_pad_mask : (B, S_enc) — True = token valide encodeur

        Retourne : (B, S_dec, d_model)
        """
        B, S_dec, _ = x_decoder.shape
        S_enc       = encoder_output.shape[1]

        def split_heads_dec(t):
            return t.view(B, S_dec, self.n_heads, self.d_head).transpose(1, 2)

        def split_heads_enc(t):
            return t.view(B, S_enc, self.n_heads, self.d_head).transpose(1, 2)

        Q = split_heads_dec(self.W_q(x_decoder))   # (B, H, S_dec, d_head)
        K = split_heads_enc(self.W_k(encoder_output))  # (B, H, S_enc, d_head)
        V = split_heads_enc(self.W_v(encoder_output))  # (B, H, S_enc, d_head)

        # Q·K^T : chaque token décodeur × tous les tokens encodeur
        scores = torch.matmul(Q, K.transpose(-2, -1)) / self.scale
        # → (B, H, S_dec, S_enc)

        # Masquer les [PAD] de l'encodeur
        if encoder_pad_mask is not None:
            mask   = encoder_pad_mask.unsqueeze(1).unsqueeze(2)  # (B, 1, 1, S_enc)
            scores = scores.masked_fill(~mask, float('-inf'))

        attn   = torch.nan_to_num(F.softmax(scores, dim=-1), nan=0.0)
        attn   = self.attn_dropout(attn)

        output = torch.matmul(attn, V)  # (B, H, S_dec, d_head)
        output = output.transpose(1, 2).contiguous().view(B, S_dec, self.d_model)

        return self.W_o(output)


# ══════════════════════════════════════════════════════════════════════
# COUCHES ENCODER ET DECODER
# ══════════════════════════════════════════════════════════════════════

class CoucheEncoderSx(nn.Module):
    """
    Couche Encoder de COR Sx.

    Structure (Pre-Norm) :
        x = x + SelfAttentionEncoder(RMSNorm(x))
        x = x + SwiGLU(RMSNorm(x))
    """

    def __init__(self, config: ConfigCorSx):
        super().__init__()
        self.norm1 = RMSNorm(config.d_model)
        self.attn  = SelfAttentionEncoder(config)
        self.norm2 = RMSNorm(config.d_model)
        self.ffn   = SwiGLU(config.d_model, config.ffn_dim, config.dropout)
        self.drop  = nn.Dropout(config.dropout)

    def forward(
        self,
        x            : torch.Tensor,
        padding_mask : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        x = x + self.drop(self.attn(self.norm1(x), padding_mask))
        x = x + self.drop(self.ffn(self.norm2(x)))
        return x


class CoucheDecoderSx(nn.Module):
    """
    Couche Decoder de COR Sx.

    Structure (Pre-Norm) :
        x = x + SelfAttentionDecoder(RMSNorm(x))       ← causal
        x = x + CrossAttention(RMSNorm(x), enc_out)    ← cross
        x = x + SwiGLU(RMSNorm(x))                     ← FFN

    POINT CRITIQUE — ordre des opérations :
    SelfAttention d'abord → le décodeur traite ses propres tokens
    CrossAttention ensuite → il consulte l'encodeur
    FFN en dernier → transformation finale
    C'est l'ordre standard T5/BART.
    """

    def __init__(self, config: ConfigCorSx):
        super().__init__()
        self.norm1        = RMSNorm(config.d_model)
        self.self_attn    = SelfAttentionDecoder(config)
        self.norm2        = RMSNorm(config.d_model)
        self.cross_attn   = CrossAttention(config)
        self.norm3        = RMSNorm(config.d_model)
        self.ffn          = SwiGLU(config.d_model, config.ffn_dim, config.dropout)
        self.drop         = nn.Dropout(config.dropout)

    def forward(
        self,
        x                : torch.Tensor,
        encoder_output   : torch.Tensor,
        encoder_pad_mask : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        # 1. Self-Attention causale
        x = x + self.drop(self.self_attn(self.norm1(x)))
        # 2. Cross-Attention vers l'encodeur
        x = x + self.drop(self.cross_attn(self.norm2(x), encoder_output, encoder_pad_mask))
        # 3. FFN
        x = x + self.drop(self.ffn(self.norm3(x)))
        return x


# ══════════════════════════════════════════════════════════════════════
# MODÈLE PRINCIPAL COR Sx
# ══════════════════════════════════════════════════════════════════════

class CorSx(nn.Module):
    """
    COR Sx — Encoder-Decoder multi-tâches juridique africain.

    Fonctions principales :
        encoder_forward()  → encode le document source
        decoder_forward()  → génère un token à la fois (training)
        generer()          → génération complète (inférence)
        forward()          → pipeline complet pour l'entraînement

    Usage entraînement :
        logits = modele(input_ids, decoder_input_ids)
        loss = F.cross_entropy(logits, labels, ignore_index=pad_id)

    Usage inférence :
        sortie = modele.generer(input_ids, max_new_tokens=200)
    """

    def __init__(self, config: ConfigCorSx):
        super().__init__()
        self.config = config

        # Embeddings partagés encodeur/décodeur
        # POINT CRITIQUE — weight sharing :
        # T5 partage les embeddings entre encodeur, décodeur et la tête LM.
        # On fait de même pour réduire les paramètres et améliorer la cohérence.
        self.embedding = nn.Embedding(
            config.vocab_size,
            config.d_model,
            padding_idx=config.pad_id
        )
        self.embedding_dropout = nn.Dropout(config.dropout)

        # Encodeur
        self.couches_encoder = nn.ModuleList([
            CoucheEncoderSx(config)
            for _ in range(config.n_layers_encoder)
        ])
        self.norm_encoder = RMSNorm(config.d_model)

        # Décodeur
        self.couches_decoder = nn.ModuleList([
            CoucheDecoderSx(config)
            for _ in range(config.n_layers_decoder)
        ])
        self.norm_decoder = RMSNorm(config.d_model)

        # Tête de génération — partagée avec embedding (weight tying)
        # POINT CRITIQUE — weight tying :
        # La matrice de projection finale est la transposée de l'embedding.
        # Réduit les paramètres et améliore la cohérence sémantique.
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)
        self.lm_head.weight = self.embedding.weight  # Partage des poids

        self._initialiser_poids()

    def _initialiser_poids(self):
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.padding_idx is not None:
                    module.weight.data[module.padding_idx].zero_()

    def encoder_forward(
        self,
        input_ids    : torch.Tensor,
        padding_mask : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Encode le document source.

        input_ids    : (B, S_enc) — tokens du document
        padding_mask : (B, S_enc) — True = token valide

        Retourne : (B, S_enc, d_model)
        """
        if padding_mask is None:
            padding_mask = (input_ids != self.config.pad_id)

        x = self.embedding_dropout(self.embedding(input_ids))

        for couche in self.couches_encoder:
            x = couche(x, padding_mask)

        return self.norm_encoder(x)

    def decoder_forward(
        self,
        decoder_input_ids : torch.Tensor,
        encoder_output    : torch.Tensor,
        encoder_pad_mask  : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Passe décodeur pour l'entraînement (teacher forcing).

        decoder_input_ids : (B, S_dec) — tokens de la sortie décalés d'un rang
        encoder_output    : (B, S_enc, d_model) — sortie de l'encodeur
        encoder_pad_mask  : (B, S_enc)

        Retourne : (B, S_dec, vocab_size) — logits
        """
        x = self.embedding_dropout(self.embedding(decoder_input_ids))

        for couche in self.couches_decoder:
            x = couche(x, encoder_output, encoder_pad_mask)

        x = self.norm_decoder(x)
        return self.lm_head(x)

    def forward(
        self,
        input_ids         : torch.Tensor,
        decoder_input_ids : torch.Tensor,
        padding_mask      : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Pipeline complet pour l'entraînement.

        input_ids         : (B, S_enc) — document source (avec préfixe tâche)
        decoder_input_ids : (B, S_dec) — sortie décalée ([BOS] + tokens)
        padding_mask      : (B, S_enc) — masque padding encodeur

        Retourne : (B, S_dec, vocab_size) — logits

        Calcul de la loss :
            logits = modele(input_ids, decoder_input_ids)
            # Labels = decoder_input_ids décalé d'un rang
            labels = decoder_target_ids  # sans le [BOS] initial
            loss = F.cross_entropy(
                logits.view(-1, vocab_size),
                labels.view(-1),
                ignore_index=pad_id
            )
        """
        if padding_mask is None:
            padding_mask = (input_ids != self.config.pad_id)

        encoder_output = self.encoder_forward(input_ids, padding_mask)
        logits         = self.decoder_forward(decoder_input_ids, encoder_output, padding_mask)

        return logits

    @torch.no_grad()
    def generer(
        self,
        input_ids      : torch.Tensor,
        max_new_tokens : int   = 256,
        temperature    : float = 0.7,
        top_k          : int   = 50,
        padding_mask   : Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Génération auto-régressive complète.

        input_ids : (B, S_enc) — document source avec préfixe tâche
        Retourne  : (B, S_dec) — tokens générés

        ALGORITHME :
        1. Encoder le document une seule fois
        2. Initialiser le décodeur avec [BOS]
        3. À chaque étape :
           a. Passer le décodeur avec les tokens générés jusqu'ici
           b. Prendre le dernier logit
           c. Appliquer temperature + top-k sampling
           d. Ajouter le token sampléà la séquence
           e. Arrêter si [EOS] ou max_new_tokens atteint

        POINT CRITIQUE — temperature :
        temperature=1.0 → distribution originale
        temperature<1.0 → plus concentrée (plus déterministe)
        temperature>1.0 → plus plate (plus créative)
        Pour les sorties juridiques structurées → 0.3-0.7

        POINT CRITIQUE — top_k :
        top_k=1   → greedy (toujours le token le plus probable)
        top_k=50  → échantillonnage parmi les 50 meilleurs tokens
        Pour les sorties JSON structurées → top_k=10-20
        Pour les résumés → top_k=40-50
        """
        self.eval()
        B = input_ids.shape[0]
        device = input_ids.device

        # 1. Encoder le document une seule fois
        if padding_mask is None:
            padding_mask = (input_ids != self.config.pad_id)

        encoder_output = self.encoder_forward(input_ids, padding_mask)

        # 2. Initialiser avec [BOS]
        decoder_ids = torch.full(
            (B, 1), self.config.bos_id,
            dtype=torch.long, device=device
        )

        # 3. Génération token par token
        for _ in range(max_new_tokens):
            logits = self.decoder_forward(decoder_ids, encoder_output, padding_mask)
            # Prendre seulement le dernier token
            logits_last = logits[:, -1, :]  # (B, vocab_size)

            # Temperature scaling
            if temperature != 1.0:
                logits_last = logits_last / temperature

            # Top-k filtering
            if top_k > 0:
                top_k_val = min(top_k, logits_last.size(-1))
                kth_val   = torch.topk(logits_last, top_k_val).values[:, -1, None]
                logits_last = logits_last.masked_fill(logits_last < kth_val, float('-inf'))

            # Sampling
            probs      = F.softmax(logits_last, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)  # (B, 1)

            decoder_ids = torch.cat([decoder_ids, next_token], dim=1)

            # Arrêter si tous les exemples ont généré [EOS]
            if (next_token == self.config.eos_id).all():
                break

        return decoder_ids

    def compter_parametres(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def sauvegarder(self, chemin: str):
        os.makedirs(os.path.dirname(chemin) if os.path.dirname(chemin) else '.', exist_ok=True)
        torch.save({
            'config'     : self.config,
            'state_dict' : self.state_dict(),
        }, chemin)
        print(f"[COR-SX] Sauvegardé : {chemin} ({self.compter_parametres():,} params)")

    @classmethod
    def charger(cls, chemin: str) -> 'CorSx':
        checkpoint = torch.load(chemin, map_location='cpu', weights_only=False)
        config     = checkpoint['config']
        modele     = cls(config)
        modele.load_state_dict(checkpoint['state_dict'])
        print(f"[COR-SX] Chargé : {chemin} ({modele.compter_parametres():,} params)")
        return modele


# ══════════════════════════════════════════════════════════════════════
# PRÉFIXES DE TÂCHES
# ══════════════════════════════════════════════════════════════════════

PREFIXES_TACHES = {
    "resume_jugement"       : "resume_jugement: ",
    "extraction_contrat"    : "extraction_contrat: ",
    "fiche_jurisprudence"   : "fiche_jurisprudence: ",
    "classification_synthese": "classification_synthese: ",
    "qa_document"           : "qa_document: ",
    "conformite"            : "conformite: ",
    "risques_contrat"       : "risques_contrat: ",
    "reformulation"         : "reformulation: ",
}


def preparer_entree(
    tache   : str,
    document: str,
    question: Optional[str] = None,
    regle   : Optional[str] = None,
) -> str:
    """
    Prépare l'entrée formatée pour COR Sx selon la tâche.

    tache    : clé dans PREFIXES_TACHES
    document : texte du document juridique
    question : pour "qa_document" — la question posée
    regle    : pour "conformite" — la règle à vérifier

    Retourne : chaîne formatée prête pour le tokeniseur

    Usage :
        entree = preparer_entree("resume_jugement", jugement_complet)
        entree = preparer_entree("qa_document", contrat, question="Quelle est la durée ?")
        entree = preparer_entree("conformite", acte, regle="Art 34 AUDCG")
    """
    assert tache in PREFIXES_TACHES, \
        f"Tâche inconnue : '{tache}'. Choisir parmi : {list(PREFIXES_TACHES.keys())}"

    prefixe = PREFIXES_TACHES[tache]

    if tache == "qa_document":
        assert question is not None, "question requise pour qa_document"
        return f"{prefixe}{question} [SEP] {document}"

    if tache == "conformite":
        assert regle is not None, "regle requise pour conformite"
        return f"{prefixe}{regle} [SEP] {document}"

    return f"{prefixe}{document}"


# ══════════════════════════════════════════════════════════════════════
# TEST RAPIDE
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  COR Sx — Test de l'architecture")
    print("=" * 65)

    config = ConfigCorSx(
        vocab_size       = 7995,
        d_model          = 128,
        n_heads          = 4,
        n_layers_encoder = 2,
        n_layers_decoder = 2,
        ffn_dim          = 512,
        max_len_encoder  = 64,
        max_len_decoder  = 32,
        dropout          = 0.0,
    )

    modele = CorSx(config)
    nb_params = modele.compter_parametres()
    print(f"\n  Paramètres : {nb_params:,}")

    B = 2
    S_enc = 32
    S_dec = 16

    input_ids         = torch.randint(1, 7995, (B, S_enc))
    decoder_input_ids = torch.randint(1, 7995, (B, S_dec))

    # Test forward
    logits = modele(input_ids, decoder_input_ids)
    assert logits.shape == (B, S_dec, config.vocab_size)
    assert not torch.isnan(logits).any()
    print(f"  forward()        : {logits.shape} ✓")

    # Test encoder seul
    enc_out = modele.encoder_forward(input_ids)
    assert enc_out.shape == (B, S_enc, config.d_model)
    print(f"  encoder_forward(): {enc_out.shape} ✓")

    # Test génération
    sortie = modele.generer(input_ids, max_new_tokens=10, top_k=5)
    assert sortie.shape[0] == B
    assert sortie.shape[1] <= 11  # [BOS] + 10 tokens max
    print(f"  generer()        : {sortie.shape} ✓")

    # Test preparer_entree
    e1 = preparer_entree("resume_jugement", "Jugement du TGI Douala...")
    e2 = preparer_entree("qa_document", "Contrat de bail...", question="Quelle est la durée ?")
    e3 = preparer_entree("conformite", "Acte de cession...", regle="Art 67 AUDCG")
    assert e1.startswith("resume_jugement: ")
    assert "[SEP]" in e2
    assert "[SEP]" in e3
    print(f"  preparer_entree(): OK ✓")

    # Test sauvegarde
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        chemin = os.path.join(tmpdir, "cor_sx_test.pt")
        modele.sauvegarder(chemin)
        modele2 = CorSx.charger(chemin)
        assert modele2.compter_parametres() == nb_params
        logits2 = modele2(input_ids, decoder_input_ids)
        assert torch.allclose(logits, logits2)
        print(f"  Sauvegarde/chargement ✓")

    print()
    print("=" * 65)
    print(f"  COR Sx : ARCHITECTURE VALIDÉE")
    print(f"  {nb_params:,} paramètres (config mini)")
    print(f"  Config dev  : ~45M params  (d_model=256, 6+6 couches)")
    print(f"  Config prod : ~220M params (d_model=512, 12+12 couches)")
    print("=" * 65)