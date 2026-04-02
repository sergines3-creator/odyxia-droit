"""
encryption.py — Odyxia Droit
Chiffrement/déchiffrement Fernet (AES-128)
+ extraction mots-clés pour index de recherche séparé
"""

import os
import re
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")

MOTS_VIDES = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "en",
    "au", "aux", "ce", "se", "sa", "son", "ses", "mon", "ma", "mes",
    "ton", "ta", "tes", "nous", "vous", "ils", "elles", "est", "sont",
    "par", "sur", "sous", "dans", "avec", "pour", "que", "qui", "quoi",
    "dont", "vers", "mais", "ou", "donc", "or", "ni", "car", "plus",
    "tout", "tous", "cette", "cet", "ces", "leur", "leurs", "meme",
    "ainsi", "alors", "aussi", "comme", "selon", "entre"
}


def get_fernet():
    if not ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY manquante dans les variables d'environnement")
    return Fernet(ENCRYPTION_KEY.encode())


def chiffrer(texte: str) -> str:
    """Chiffre un texte — retourne ENC:..."""
    try:
        f = get_fernet()
        chiffre = f.encrypt(texte.encode("utf-8"))
        return "ENC:" + chiffre.decode("utf-8")
    except Exception as e:
        print(f"[ENCRYPTION] Erreur chiffrement : {e}")
        return texte


def dechiffrer(texte: str) -> str:
    """Déchiffre un texte ENC:... — retourne le texte clair."""
    try:
        if not texte.startswith("ENC:"):
            return texte
        f = get_fernet()
        donnees = texte[4:].encode("utf-8")
        return f.decrypt(donnees).decode("utf-8")
    except Exception as e:
        print(f"[ENCRYPTION] Erreur déchiffrement : {e}")
        return "[Document chiffré — clé invalide]"


def est_chiffre(texte: str) -> bool:
    """Vérifie si un chunk est chiffré."""
    return isinstance(texte, str) and texte.startswith("ENC:")


def extraire_index(texte: str, longueur_min: int = 4) -> str:
    """
    Extrait les mots-clés anonymisés pour l'index de recherche.
    Les documents chiffrés restent consultables via ces mots-clés génériques.
    """
    if not texte:
        return ""
    texte_clean = texte.lower()
    texte_clean = re.sub(r'[^\w\s]', ' ', texte_clean)
    texte_clean = re.sub(r'\d+', ' ', texte_clean)
    mots = texte_clean.split()
    mots_index = [
        m for m in mots
        if len(m) >= longueur_min
        and m not in MOTS_VIDES
        and not m.isdigit()
    ]
    vus = set()
    mots_uniques = []
    for m in mots_index:
        if m not in vus:
            vus.add(m)
            mots_uniques.append(m)
    return " ".join(mots_uniques[:100])


def generer_cle() -> str:
    """Génère une nouvelle clé Fernet — à utiliser une seule fois à l'installation."""
    return Fernet.generate_key().decode()


if __name__ == "__main__":
    print("Nouvelle clé ENCRYPTION_KEY :")
    print(generer_cle())

