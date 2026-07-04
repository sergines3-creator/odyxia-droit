# COUCHE APPLICATION — application/inference.py
# Responsabilité : orchestration de l'inférence, cas d'usage métier.
#
# Règles de couche :
#   ✓ Peut importer domain/ (Cor, ConfigCor, CorTokenizer)
#   ✓ Peut importer infrastructure/ si besoin (chargement fichiers)
#   ✗ Aucun import Flask, aucun détail HTTP
#
# Exports publics : CorInference

import os
import torch
from typing import List, Optional, Dict, Any

from domain.model     import Cor, ConfigCor
from domain.tokenizer import CorTokenizer


class CorInference:
    """
    Interface unifiée d'inférence pour Cor.

    Encapsule le modèle et le tokeniseur.
    Expose une API simple pour les projets externes.
    """

    def __init__(self, modele: Cor, tokenizer: CorTokenizer):
        self.modele    = modele
        self.tokenizer = tokenizer
        self._actif    = os.getenv("COR_ACTIF", "true").lower() == "true"

        if not self._actif:
            print("[COR] Mode INACTIF (COR_ACTIF=false) — fallback activé")
        else:
            params = modele.compter_parametres()
            print(f"[COR] Prêt — {params:,} paramètres")

    @property
    def actif(self) -> bool:
        """
        True si Cor est actif et doit être utilisé.
        False si le projet appelant doit utiliser son fallback.

        Contrôlé par la variable d'environnement COR_ACTIF.
        Mettre COR_ACTIF=false dans .env pour désactiver Cor
        sans modifier le code (utile pendant l'entraînement).
        """
        return self._actif

    @classmethod
    def charger(
        cls,
        chemin_modele    : str,
        chemin_tokenizer : str,
    ) -> "CorInference":
        """
        Charge Cor depuis le disque.

        POINT CRITIQUE — ordre de chargement :
        Toujours charger le tokeniseur avant le modèle.
        Le modèle a besoin de vocab_size pour construire lm_head.
        """
        print(f"[COR] Chargement tokeniseur...")
        tokenizer = CorTokenizer.charger(chemin_tokenizer)

        print(f"[COR] Chargement modèle...")
        modele = Cor.charger(chemin_modele)

        # Vérifier la cohérence vocab_size
        vocab_size_tok   = len(tokenizer.vocab)
        vocab_size_model = modele.config.vocab_size

        if vocab_size_tok != vocab_size_model:
            raise ValueError(
                f"Incohérence vocab_size : "
                f"tokeniseur={vocab_size_tok}, modèle={vocab_size_model}. "
                f"Re-entraîner le modèle avec le bon tokeniseur."
            )

        modele.eval()
        return cls(modele, tokenizer)

    @classmethod
    def depuis_config(
        cls,
        config_modele    : Optional[ConfigCor] = None,
        chemin_tokenizer : Optional[str] = None,
    ) -> "CorInference":
        """
        Initialise Cor avec des poids aléatoires (pour les tests).

        POINT CRITIQUE : ne jamais utiliser en production.
        Les poids aléatoires produisent du charabia.
        Utiliser charger() avec un modèle entraîné.
        """
        config    = config_modele or ConfigCor()
        modele    = Cor(config)
        tokenizer = CorTokenizer.charger(chemin_tokenizer) if chemin_tokenizer \
                    else CorTokenizer(vocab_size=config.vocab_size)
        return cls(modele, tokenizer)

    def repondre(
        self,
        question      : str,
        passages_rag  : Optional[List[str]] = None,
        pays_token    : Optional[str] = None,
        max_tokens    : int   = 150,
        temperature   : float = 0.7,
        top_p         : float = 0.9,
        repetition_penalty : float = 1.1,
    ) -> Optional[str]:
        """
        Génère une réponse juridique à partir d'une question et de passages RAG.

        Retourne None si Cor est inactif (COR_ACTIF=false).
        Le projet appelant doit gérer ce cas et utiliser son fallback.

        question     : question de l'utilisateur
        passages_rag : passages pertinents récupérés par le RAG
        pays_token   : "[CM]", "[GA]", etc. — détecté auto si None
        max_tokens   : nombre max de tokens à générer
        temperature  : 0.1=précis, 0.7=équilibré, 1.5=créatif
        top_p        : nucleus sampling (0.9 recommandé)
        repetition_penalty : pénalité pour éviter les boucles (1.1 recommandé)

        POINT CRITIQUE — passages_rag vides :
        Si aucun passage RAG n'est fourni, Cor génère depuis sa mémoire
        paramétrique uniquement. Risque d'hallucination élevé.
        Toujours fournir des passages RAG pertinents en production.
        """
        if not self._actif:
            return None

        passages_rag = passages_rag or []

        # Construire le prompt avec le tokeniseur
        ids_prompt, pos_rep = self.tokenizer.construire_prompt_cor(
            question     = question,
            passages_rag = passages_rag,
            pays_token   = pays_token,
            max_len      = self.modele.config.max_len,
        )

        # Décoder le prompt en texte pour le passer à generer()
        # (generer() attend une string, pas des ids)
        prompt_texte = self._ids_to_prompt_texte(ids_prompt)

        # Générer
        reponse = self.modele.generer(
            tokenizer          = self.tokenizer,
            prompt             = prompt_texte,
            max_new_tokens     = max_tokens,
            temperature        = temperature,
            top_p              = top_p,
            repetition_penalty = repetition_penalty,
        )

        return reponse if reponse else None

    def _ids_to_prompt_texte(self, ids: List[int]) -> str:
        """
        Reconstitue le texte du prompt depuis les ids.
        Préserve les tokens spéciaux ([CM], [SEP], [REP], etc.)
        pour que generer() les reconnaisse correctement.
        """
        fragments = []
        for id_ in ids:
            token = self.tokenizer.id_to_token.get(id_, "[UNK]")
            fragments.append(token)
        return " ".join(fragments)

    def tokeniser(self, texte: str) -> List[int]:
        """Expose le tokeniseur pour les projets externes."""
        return self.tokenizer.tokeniser(texte)

    def decoder(self, ids: List[int]) -> str:
        """Expose le décodeur pour les projets externes."""
        return self.tokenizer.decoder(ids)

    def info(self) -> Dict[str, Any]:
        """
        Retourne les informations sur le modèle chargé.
        Utilisé par l'endpoint /health du microservice.
        """
        return {
            "actif"      : self._actif,
            "parametres" : self.modele.compter_parametres(),
            "vocab_size" : len(self.tokenizer.vocab),
            "d_model"    : self.modele.config.d_model,
            "n_layers"   : self.modele.config.n_layers,
            "max_len"    : self.modele.config.max_len,
            "version"    : "cor-0.1.0-dev",
        }
