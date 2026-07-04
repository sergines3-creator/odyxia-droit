# Shim de compatibilité — cor/trainer.py
# L'implémentation réelle est dans infrastructure/trainer.py
# Ce fichier préserve les imports existants :
#   from cor.trainer import pre_entrainer, fine_tuner, ConfigEntrainement

from infrastructure.trainer import (
    ConfigEntrainement,
    DatasetPreEntrainement,
    DatasetFineTuning,
    calculer_loss_masquee,
    get_lr,
    pre_entrainer,
    fine_tuner,
    evaluer,
)

__all__ = [
    "ConfigEntrainement",
    "DatasetPreEntrainement",
    "DatasetFineTuning",
    "calculer_loss_masquee",
    "get_lr",
    "pre_entrainer",
    "fine_tuner",
    "evaluer",
]
