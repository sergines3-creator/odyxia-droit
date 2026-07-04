# Shim de compatibilité — cor/inference.py
# L'implémentation réelle est dans application/inference.py
# Ce fichier préserve les imports existants : from cor.inference import CorInference

from application.inference import CorInference

__all__ = ["CorInference"]
