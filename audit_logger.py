"""
audit_logger.py — Themis
Journal d'audit de toutes les actions sensibles
"""

import os
from datetime import datetime
from flask import request

# Actions auditées
ACTION_LOGIN         = "LOGIN"
ACTION_LOGIN_ECHEC   = "LOGIN_ECHEC"
ACTION_UPLOAD        = "UPLOAD_DOCUMENT"
ACTION_GENERATION    = "GENERATION_DOCUMENT"
ACTION_EXPORT_PDF    = "EXPORT_PDF"
ACTION_SUPPRESSION   = "SUPPRESSION_DOCUMENT"
ACTION_PREDICT       = "ANALYSE_PREDICTIVE"
ACTION_REDACTION     = "REDACTION_DOCUMENT"


def log_audit(action: str, details: dict = None, succes: bool = True):
    """
    Enregistre une action dans la table audit_logs de Supabase.
    Ne bloque jamais l'application en cas d'erreur.
    """
    try:
        from supabase import create_client
        supabase = create_client(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_KEY")
        )

        ip = "unknown"
        user_agent = "unknown"
        try:
            ip = request.remote_addr or "unknown"
            user_agent = request.headers.get("User-Agent", "unknown")[:200]
        except Exception:
            pass

        supabase.table("audit_logs").insert({
            "action": action,
            "succes": succes,
            "ip": ip,
            "user_agent": user_agent,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }).execute()

    except Exception as e:
        print(f"[AUDIT] Erreur log ({action}) : {str(e)[:100]}")