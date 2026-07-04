# Shim de compatibilité — cor/model.py
# L'implémentation réelle est dans domain/model.py
# Ce fichier préserve les imports existants : from cor.model import Cor, ConfigCor

from domain.model import (
    Cor,
    ConfigCor,
    RMSNorm,
    RoPE,
    construire_masque_causal,
    MultiHeadAttention,
    SwiGLU,
    CoucheDecoder,
)

__all__ = [
    "Cor",
    "ConfigCor",
    "RMSNorm",
    "RoPE",
    "construire_masque_causal",
    "MultiHeadAttention",
    "SwiGLU",
    "CoucheDecoder",
]
