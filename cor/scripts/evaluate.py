# scripts/evaluate.py
# COR — Évaluation du modèle entraîné
#
# Usage :
#   python scripts/evaluate.py                    ← évaluation complète
#   python scripts/evaluate.py --qualitatif       ← exemples de génération
#   python scripts/evaluate.py --perplexite       ← perplexité sur corpus test
#
# POINT CRITIQUE — Interpréter les résultats :
#   Perplexité < 50  : très bon (modèle a bien appris le style juridique)
#   Perplexité 50-200: acceptable
#   Perplexité > 200 : sur-apprentissage ou corpus insuffisant
#
#   La perplexité seule ne suffit pas — évaluer aussi qualitativement.
#   Un modèle peut avoir faible perplexité et produire du charabia
#   si le corpus était bruité.

import os
import sys
import math
import argparse
import torch
import torch.nn.functional as F

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

TOKENIZER_PATH = os.path.join(BASE, "models", "cor_tokenizer.json")
MODELE_PATH    = os.path.join(BASE, "models", "cor.pt")


QUESTIONS_TEST = [
    {
        "label"   : "Licenciement Cameroun",
        "question": "licenciement sans préavis cameroun article 34",
        "passages": ["article 34 code travail cameroun preavis duree categorie anciennete"],
        "pays"    : "[CM]",
    },
    {
        "label"   : "Injonction payer OHADA",
        "question": "injonction payer ohada créance commerciale procedure",
        "passages": ["procedure simplifiee recouvrement creance certaine liquide exigible aupsrve"],
        "pays"    : "[OHADA]",
    },
    {
        "label"   : "Titre foncier Gabon",
        "question": "titre foncier immatriculation gabon expropriation",
        "passages": ["procedure immatriculation cadastre propriete gabon domaine public"],
        "pays"    : "[GA]",
    },
    {
        "label"   : "SARL OHADA capital social",
        "question": "creation sarl ohada capital social minimum associes",
        "passages": ["auscgie article 311 sarl capital social associes responsabilite"],
        "pays"    : "[OHADA]",
    },
    {
        "label"   : "Garde à vue Cameroun",
        "question": "garde a vue duree maximale cameroun droits avocat",
        "passages": ["code procedure penale cameroun garde vue duree 24h renouvelable avocat"],
        "pays"    : "[CM]",
    },
]


def evaluer_qualitatif(cor):
    """Génération sur les questions de test."""
    print("\n" + "="*65)
    print("  ÉVALUATION QUALITATIVE")
    print("="*65)

    for i, cas in enumerate(QUESTIONS_TEST):
        print(f"\n  [{i+1}/{len(QUESTIONS_TEST)}] {cas['label']}")
        print(f"  Question : {cas['question']}")

        reponse = cor.repondre(
            question     = cas["question"],
            passages_rag = cas["passages"],
            pays_token   = cas["pays"],
            max_tokens   = 80,
            temperature  = 0.7,
            top_p        = 0.9,
        )

        if reponse:
            print(f"  Réponse  : {reponse[:200]}")
        else:
            print(f"  Réponse  : [vide — modèle non entraîné ou COR_ACTIF=false]")


def evaluer_perplexite(cor, tokenizer):
    """Calcule la perplexité sur un corpus de test."""
    print("\n" + "="*65)
    print("  ÉVALUATION PERPLEXITÉ")
    print("="*65)

    textes_test = [
        "licenciement abusif indemnite compensatrice prejudice subi salarie tribunal travail",
        "injonction payer procedure simplifiee recouvrement creance certaine liquide exigible",
        "titre foncier immatriculation cadastre propriete gabon expropriation utilite publique",
        "acte uniforme ohada societes commerciales sarl capital social minimum responsabilite",
        "detention provisoire mise en examen instruction penale juge libertés",
    ]

    perplexites = []
    modele = cor.modele
    modele.eval()

    with torch.no_grad():
        for texte in textes_test:
            ids = tokenizer.tokeniser(texte)
            if len(ids) < 4:
                continue

            ids_t = torch.tensor([ids])
            logits = modele(ids_t)

            B, S, V = logits.shape
            loss = F.cross_entropy(
                logits[:, :-1, :].reshape(B * (S-1), V),
                ids_t[:, 1:].reshape(B * (S-1)),
                ignore_index=0,
            )
            ppl = math.exp(min(loss.item(), 10))
            perplexites.append(ppl)
            print(f"  {texte[:50]:<50} ppl={ppl:.1f}")

    if perplexites:
        moy = sum(perplexites) / len(perplexites)
        print(f"\n  Perplexité moyenne : {moy:.1f}")
        if moy < 50:
            print(f"  ✓ Très bon — style juridique bien appris")
        elif moy < 200:
            print(f"  ~ Acceptable — continuer l'entraînement")
        else:
            print(f"  ✗ Insuffisant — vérifier corpus et hyperparamètres")


def main():
    parser = argparse.ArgumentParser(description="COR — Évaluation")
    parser.add_argument("--qualitatif",  action="store_true")
    parser.add_argument("--perplexite",  action="store_true")
    args = parser.parse_args()

    # Tout par défaut
    if not args.qualitatif and not args.perplexite:
        args.qualitatif = True
        args.perplexite = True

    # Vérifications
    for chemin, nom in [
        (MODELE_PATH,    "Modèle"),
        (TOKENIZER_PATH, "Tokeniseur"),
    ]:
        if not os.path.exists(chemin):
            print(f"[ERREUR] {nom} absent : {chemin}")
            print(f"         Lancer d'abord : python scripts/train.py")
            sys.exit(1)

    # Charger Cor
    from cor.inference import CorInference
    from cor.tokenizer import CorTokenizer

    cor       = CorInference.charger(MODELE_PATH, TOKENIZER_PATH)
    tokenizer = CorTokenizer.charger(TOKENIZER_PATH)

    if args.qualitatif:
        evaluer_qualitatif(cor)

    if args.perplexite:
        evaluer_perplexite(cor, tokenizer)

    print(f"\n{'='*65}")
    print(f"  Évaluation terminée")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()