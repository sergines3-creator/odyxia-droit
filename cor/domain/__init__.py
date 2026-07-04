# COUCHE DOMAINE — Point d'entrée
# Exporte les types publics du domaine IA pur.
# Aucune dépendance vers api/, application/, infrastructure/.

from domain.model     import Cor, ConfigCor
from domain.tokenizer import CorTokenizer

__all__ = ["Cor", "ConfigCor", "CorTokenizer"]
