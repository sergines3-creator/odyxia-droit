# dashboard/metrics_writer.py
# COR — Écrivain de métriques d'entraînement en temps réel
#
# Usage dans trainer.py :
#   from dashboard.metrics_writer import MetricsWriter
#   mw = MetricsWriter()
#   mw.start_phase("pretrain", total_epochs=3, total_steps=1500)
#   mw.log_step(step=50, loss=7.5, lr=3e-4)
#   mw.log_epoch(1, train_loss=7.2, val_loss=7.4, ppl_train=1339, ppl_val=1636, duration_s=45.2)
#   mw.log_error("val_loss remonte — risque sur-apprentissage", "WARN")
#   mw.done()

import os
import json
import time
import threading
from datetime import datetime
from typing import Optional

METRICS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "training_metrics.json"
)

MAX_STEPS_LOG  = 2000   # garder les N derniers steps pour ne pas exploser le JSON
MAX_ERRORS_LOG = 200


class MetricsWriter:
    """
    Écrit les métriques d'entraînement dans training_metrics.json.
    Thread-safe via un verrou interne.
    """

    def __init__(self, path: str = METRICS_PATH):
        self.path = path
        self._lock = threading.Lock()

        # Charger ou initialiser
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = self._empty()
        else:
            self._data = self._empty()

        self._save()

    # ──────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────

    def start_phase(
        self,
        phase: str,                    # "pretrain" | "finetune"
        total_epochs: int,
        total_steps: int,
        config_modele: Optional[dict] = None,
        config_entrainement: Optional[dict] = None,
    ):
        with self._lock:
            self._data["training_state"] = phase
            self._data["last_updated"]   = self._now()

            if config_modele:
                self._data["config_modele"] = config_modele
            if config_entrainement:
                self._data["config_entrainement"] = config_entrainement

            self._data[phase] = {
                "current_epoch" : 0,
                "total_epochs"  : total_epochs,
                "current_step"  : 0,
                "total_steps"   : total_steps,
                "epochs"        : self._data.get(phase, {}).get("epochs", []),
                "steps"         : [],
            }
            self._save()

    def log_step(self, step: int, loss: float, lr: float):
        phase = self._data.get("training_state", "pretrain")
        with self._lock:
            entry = {"step": step, "loss": round(loss, 4), "lr": lr}
            steps = self._data[phase]["steps"]
            steps.append(entry)

            # Garder les N derniers
            if len(steps) > MAX_STEPS_LOG:
                self._data[phase]["steps"] = steps[-MAX_STEPS_LOG:]

            self._data[phase]["current_step"] = step
            self._data["last_updated"] = self._now()
            self._save()

    def log_epoch(
        self,
        epoch: int,
        train_loss: float,
        val_loss: float,
        ppl_train: float,
        ppl_val: float,
        duration_s: float,
    ):
        phase = self._data.get("training_state", "pretrain")
        with self._lock:
            entry = {
                "epoch"      : epoch,
                "train_loss" : round(train_loss, 4),
                "val_loss"   : round(val_loss,   4),
                "ppl_train"  : round(ppl_train,  2),
                "ppl_val"    : round(ppl_val,    2),
                "duration_s" : round(duration_s, 1),
                "timestamp"  : self._now(),
            }
            self._data[phase]["epochs"].append(entry)
            self._data[phase]["current_epoch"] = epoch

            # Meilleure val_loss
            best_key = f"{phase}_best_val"
            best     = self._data.get(best_key, float("inf"))
            if val_loss < best:
                self._data[best_key] = round(val_loss, 4)

            self._data["last_updated"] = self._now()
            self._save()

    def log_error(self, message: str, error_type: str = "ERROR"):
        """error_type : "ERROR" | "WARN" | "INFO" """
        with self._lock:
            entry = {
                "timestamp" : self._now(),
                "type"      : error_type,
                "message"   : message,
            }
            self._data["errors"].append(entry)

            if len(self._data["errors"]) > MAX_ERRORS_LOG:
                self._data["errors"] = self._data["errors"][-MAX_ERRORS_LOG:]

            self._data["last_updated"] = self._now()
            self._save()

    def set_model_info(self, nb_params: int, vocab_size: int):
        with self._lock:
            self._data["model_info"] = {
                "nb_params"  : nb_params,
                "vocab_size" : vocab_size,
            }
            self._data["last_updated"] = self._now()
            self._save()

    def done(self, phase: Optional[str] = None):
        with self._lock:
            self._data["training_state"] = "done" if phase is None else f"{phase}_done"
            self._data["last_updated"]   = self._now()
            self._save()

    def reset(self):
        with self._lock:
            self._data = self._empty()
            self._save()

    # ──────────────────────────────────────────────
    # Interne
    # ──────────────────────────────────────────────

    @staticmethod
    def _empty() -> dict:
        return {
            "training_state"        : "idle",
            "last_updated"          : None,
            "config_modele"         : {},
            "config_entrainement"   : {},
            "model_info"            : {},
            "pretrain"              : {"current_epoch": 0, "total_epochs": 0,
                                       "current_step": 0,  "total_steps": 0,
                                       "epochs": [], "steps": []},
            "finetune"              : {"current_epoch": 0, "total_epochs": 0,
                                       "current_step": 0,  "total_steps": 0,
                                       "epochs": [], "steps": []},
            "pretrain_best_val"     : None,
            "finetune_best_val"     : None,
            "errors"                : [],
        }

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[MetricsWriter] Erreur écriture : {e}")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
