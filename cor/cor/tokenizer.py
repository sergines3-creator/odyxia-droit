# Shim de compatibilité — cor/tokenizer.py
# L'implémentation réelle est dans domain/tokenizer.py
# Ce fichier préserve les imports existants : from cor.tokenizer import CorTokenizer

from domain.tokenizer import (
    CorTokenizer,
    TOKENS_TECHNIQUES,
    TOKENS_SEQUENCE,
    TOKENS_PAYS,
    TOKENS_DOMAINE,
    TOKENS_SPECIAUX,
    TERMES_JURIDIQUES,
    DETECTION_PAYS,
    detecter_pays,
    normaliser,
    pre_tokeniser,
    obtenir_paires,
    fusionner_paire,
)

__all__ = [
    "CorTokenizer",
    "TOKENS_TECHNIQUES",
    "TOKENS_SEQUENCE",
    "TOKENS_PAYS",
    "TOKENS_DOMAINE",
    "TOKENS_SPECIAUX",
    "TERMES_JURIDIQUES",
    "DETECTION_PAYS",
    "detecter_pays",
    "normaliser",
    "pre_tokeniser",
    "obtenir_paires",
    "fusionner_paire",
]
