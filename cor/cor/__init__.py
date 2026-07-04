# cor/__init__.py — Point d'entrée du package COR
# Les shims cor/*.py redirigent vers les couches domain/ / application/ / infrastructure/
#
# Usage externe (inchangé) :
#   from cor import CorTokenizer, Cor, CorInference

__version__ = "0.1.0-dev"
__author__  = "ODYXIA"

from cor.tokenizer import CorTokenizer
from cor.model     import Cor, ConfigCor
from cor.inference import CorInference

__all__ = [
    "CorTokenizer",
    "Cor",
    "ConfigCor",
    "CorInference",
]
