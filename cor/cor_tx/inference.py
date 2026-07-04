# cor_tx/inference.py
# COR Tx — Interface d'inférence pour embeddings juridiques
#
# C'est le seul fichier que les projets externes doivent connaître
# pour utiliser COR Tx comme moteur d'embeddings.
#
# Usage depuis ODYXIA IA :
#   from cor_tx.inference import CorTxInference
#   tx = CorTxInference.charger("models/cor_tx.pt", "models/cor_tokenizer.json")
#
#   # Encoder un passage juridique
#   emb = tx.encoder_passage("L'article 34 du Code du travail camerounais...")
#   # → vecteur numpy (768,)
#
#   # Recherche sémantique
#   scores = tx.similarite(query_emb, [emb1, emb2, emb3])
#   # → [0.92, 0.45, 0.71]
#
#   # Encoder un batch de passages (pour indexation)
#   embs = tx.encoder_batch(["passage1", "passage2", ...])
#   # → numpy (N, 768)
#
# DIFFÉRENCE FONDAMENTALE avec cor/inference.py (Decoder) :
#   CorInference.repondre()    → génère du texte
#   CorTxInference.encoder()   → produit des vecteurs
#
# USAGE RAG complet :
#   1. Indexation (une fois) :
#      embs = tx.encoder_batch(tous_les_passages)
#      supabase.upsert(passages + embs)  → pgvector
#
#   2. Recherche (à chaque requête) :
#      query_emb = tx.encoder_passage(question)
#      passages  = supabase.similarity_search(query_emb, top_k=5)
#      reponse   = cor.repondre(question, passages_rag=passages)
#
# POINTS CRITIQUES :
#
#   1. Normalisation L2 obligatoire pour cosine similarity
#      Les embeddings sont normalisés à la sortie.
#      cosine_similarity(a, b) = dot(a, b) si ||a|| = ||b|| = 1
#
#   2. Pooling strategy — CLS vs Mean
#      CLS pooling  : rapide, bon pour les textes courts
#      Mean pooling : meilleur pour les textes longs (>100 tokens)
#      Par défaut : mean pooling — plus robuste sur passages juridiques
#
#   3. Batch size pour l'indexation
#      Sur CPU  : batch_size=32
#      Sur GPU  : batch_size=256
#      L'encodage d'un corpus de 400K passages prend ~30min sur GPU

import os
import math
import torch
import torch.nn.functional as F
import numpy as np
from typing import List, Optional, Union, Tuple

from cor_tx.model  import CorTx, ConfigCorTx
from cor.tokenizer import CorTokenizer


class CorTxInference:
    """
    Interface unifiée d'inférence pour COR Tx.

    Produit des embeddings juridiques africains
    pour la recherche sémantique et le RAG.
    """

    def __init__(
        self,
        modele    : CorTx,
        tokenizer : CorTokenizer,
        device    : Optional[torch.device] = None,
        pooling   : str = "mean",
    ):
        """
        modele    : CorTx chargé depuis cor_tx.pt
        tokenizer : CorTokenizer chargé depuis cor_tokenizer.json
        device    : torch.device (auto-détecté si None)
        pooling   : "mean" ou "cls"
                    "mean" → moyenne sur tokens valides (recommandé)
                    "cls"  → token [CLS] uniquement
        """
        assert pooling in ("mean", "cls"), \
            f"pooling doit être 'mean' ou 'cls', obtenu '{pooling}'"

        self.modele    = modele
        self.tokenizer = tokenizer
        self.pooling   = pooling

        # Device auto-détecté
        if device is None:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.device = device

        self.modele = self.modele.to(device)
        self.modele.eval()

        self.d_model  = modele.config.d_model
        self.max_len  = modele.config.max_len
        self.pad_id   = modele.config.pad_id

        nb_params = modele.compter_parametres()
        print(f"[COR-TX] Prêt — {nb_params:,} params | "
              f"device={device} | pooling={pooling} | "
              f"dim={self.d_model}")

    # ── Encodage ──────────────────────────────────────────────────────

    def encoder_passage(self, texte: str) -> np.ndarray:
        """
        Encode un seul texte en vecteur d'embedding normalisé.

        texte   : texte juridique à encoder
        Retourne: vecteur numpy (d_model,) normalisé L2

        Usage :
            emb = tx.encoder_passage("L'article 34 du Code du travail...")
            # → (768,) numpy float32
        """
        return self.encoder_batch([texte])[0]

    def encoder_batch(
        self,
        textes     : List[str],
        batch_size : int = 32,
        verbose    : bool = False,
    ) -> np.ndarray:
        """
        Encode un batch de textes en vecteurs d'embeddings normalisés.

        textes     : liste de textes juridiques
        batch_size : nombre de textes encodés simultanément
                     32 sur CPU, 128-256 sur GPU
        verbose    : afficher la progression

        Retourne : numpy (N, d_model) normalisé L2

        POINT CRITIQUE — batch_size et mémoire :
        Chaque texte de max_len=512 tokens consomme environ :
            d_model=768 × 512 × 4 bytes = 1.5 Mo par séquence
        Sur GPU A100 80Go : batch_size=256 est confortable.
        Sur CPU 16Go      : batch_size=32 est sûr.
        """
        tous_embeddings = []
        n = len(textes)

        for i in range(0, n, batch_size):
            batch_textes = textes[i : i + batch_size]

            if verbose and n > batch_size:
                pct = i / n * 100
                print(f"  Encodage {i}/{n} ({pct:.0f}%)...", end="\r")

            # Tokeniser et padder le batch
            input_ids = self._tokeniser_batch(batch_textes)
            input_ids = input_ids.to(self.device)

            with torch.no_grad():
                if self.pooling == "mean":
                    embeddings = self.modele.mean_pooling(input_ids)
                else:
                    embeddings = self.modele.cls_embedding(input_ids)

                # Normalisation L2 — obligatoire pour cosine similarity
                embeddings = F.normalize(embeddings, p=2, dim=-1)

            tous_embeddings.append(embeddings.cpu().numpy())

        if verbose and n > batch_size:
            print(f"  Encodage {n}/{n} (100%) — terminé")

        return np.vstack(tous_embeddings).astype(np.float32)

    # ── Similarité ────────────────────────────────────────────────────

    def similarite(
        self,
        query_emb    : np.ndarray,
        corpus_embs  : np.ndarray,
    ) -> np.ndarray:
        """
        Calcule la cosine similarity entre une requête et un corpus.

        query_emb   : (d_model,) — embedding de la question
        corpus_embs : (N, d_model) — embeddings des passages

        Retourne : (N,) scores de similarité entre -1 et 1
                   1.0 = identique, 0.0 = orthogonal, -1.0 = opposé

        POINT CRITIQUE — cosine similarity avec vecteurs normalisés :
        Si les vecteurs sont normalisés L2 (ce que fait encoder_batch),
        cosine_similarity = produit scalaire.
        C'est le calcul le plus rapide et le plus utilisé en RAG.

        Usage :
            q_emb    = tx.encoder_passage("licenciement abusif OHADA")
            p_embs   = tx.encoder_batch(passages)
            scores   = tx.similarite(q_emb, p_embs)
            top5_idx = scores.argsort()[::-1][:5]
        """
        # S'assurer que query est 2D pour le calcul matriciel
        if query_emb.ndim == 1:
            query_emb = query_emb.reshape(1, -1)

        # Cosine similarity = produit scalaire (vecteurs déjà normalisés)
        scores = (corpus_embs @ query_emb.T).squeeze()  # (N,)
        return scores.astype(np.float32)

    def top_k_passages(
        self,
        question : str,
        passages : List[str],
        k        : int = 5,
    ) -> List[Tuple[int, float, str]]:
        """
        Trouve les k passages les plus similaires à la question.

        question : question juridique en texte libre
        passages : liste de passages du corpus
        k        : nombre de passages à retourner

        Retourne : liste de (index, score, passage) triée par score décroissant

        Usage RAG :
            resultats = tx.top_k_passages(
                "Quelles sont les conditions du licenciement abusif ?",
                passages_corpus,
                k=5
            )
            for idx, score, passage in resultats:
                print(f"Score {score:.3f} : {passage[:100]}")
        """
        query_emb  = self.encoder_passage(question)
        corpus_emb = self.encoder_batch(passages)
        scores     = self.similarite(query_emb, corpus_emb)

        # Trier par score décroissant
        indices_tries = scores.argsort()[::-1][:k]

        return [
            (int(idx), float(scores[idx]), passages[idx])
            for idx in indices_tries
        ]

    # ── Utilitaires ───────────────────────────────────────────────────

    def _tokeniser_batch(self, textes: List[str]) -> torch.Tensor:
        """
        Tokenise et padde un batch de textes.

        Retourne : (B, max_len) avec padding à 0
        """
        sequences = []
        for texte in textes:
            ids = self.tokenizer.tokeniser(texte)
            ids = ids[:self.max_len]  # Tronquer
            sequences.append(ids)

        # Padding au max_len de ce batch (pas forcément max_len global)
        longueur_max = max(len(s) for s in sequences)
        longueur_max = min(longueur_max, self.max_len)

        padded = []
        for ids in sequences:
            pad = [self.pad_id] * max(0, longueur_max - len(ids))
            ids_padded = (ids + pad)[:longueur_max]
            padded.append(ids_padded)

        return torch.tensor(padded, dtype=torch.long)

    def rapport(self) -> str:
        """Retourne un rapport de l'état de l'inférence."""
        return (
            f"COR Tx Inference\n"
            f"  Modèle   : {self.modele.compter_parametres():,} params\n"
            f"  Device   : {self.device}\n"
            f"  Pooling  : {self.pooling}\n"
            f"  Dim      : {self.d_model}\n"
            f"  Max len  : {self.max_len}\n"
        )

    # ── Chargement ────────────────────────────────────────────────────

    @classmethod
    def charger(
        cls,
        chemin_modele    : str,
        chemin_tokenizer : str,
        device           : Optional[torch.device] = None,
        pooling          : str = "mean",
    ) -> "CorTxInference":
        """
        Charge COR Tx depuis les fichiers sauvegardés.

        chemin_modele    : chemin vers cor_tx.pt
        chemin_tokenizer : chemin vers cor_tokenizer.json
        device           : torch.device (auto si None)
        pooling          : "mean" ou "cls"

        Usage :
            tx = CorTxInference.charger(
                "models/cor_tx.pt",
                "models/cor_tokenizer.json",
            )
        """
        if not os.path.exists(chemin_modele):
            raise FileNotFoundError(
                f"Modèle COR Tx absent : {chemin_modele}\n"
                f"Lancer l'entraînement : python -m cor_tx.trainer --phase mlm"
            )

        modele    = CorTx.charger(chemin_modele)
        tokenizer = CorTokenizer.charger(chemin_tokenizer)

        return cls(modele, tokenizer, device=device, pooling=pooling)

    @classmethod
    def charger_depuis_env(cls) -> Optional["CorTxInference"]:
        """
        Charge COR Tx depuis les variables d'environnement.

        Variables :
            COR_TX_ACTIF      : "true" pour activer COR Tx
            COR_TX_MODEL_PATH : chemin vers cor_tx.pt
            COR_TOKENIZER_PATH: chemin vers cor_tokenizer.json
            COR_TX_POOLING    : "mean" ou "cls" (défaut: "mean")

        Retourne None si COR_TX_ACTIF != "true".

        Usage dans ODYXIA :
            tx = CorTxInference.charger_depuis_env()
            if tx:
                emb = tx.encoder_passage(question)
            else:
                emb = voyage_ai.embed(question)  # fallback
        """
        actif = os.getenv("COR_TX_ACTIF", "false").lower() == "true"
        if not actif:
            return None

        chemin_modele    = os.getenv("COR_TX_MODEL_PATH", "models/cor_tx.pt")
        chemin_tokenizer = os.getenv("COR_TOKENIZER_PATH", "models/cor_tokenizer.json")
        pooling          = os.getenv("COR_TX_POOLING", "mean")

        try:
            return cls.charger(chemin_modele, chemin_tokenizer, pooling=pooling)
        except FileNotFoundError as e:
            print(f"[COR-TX] Impossible de charger : {e}")
            return None