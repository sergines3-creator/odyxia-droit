# COUCHE DOMAINE — domain/tokenizer.py
# Responsabilité : tokeniseur BPE juridique africain (CorTokenizer).
#
# Règles de couche :
#   ✓ Logique BPE pure — aucune dépendance vers api/, application/
#   ✓ Aucun import Flask, aucun import domain.model ou infrastructure
#   ⚠ Les méthodes sauvegarder() / charger() accèdent au disque par
#     pragmatisme (la logique BPE et l'I/O sont couplées par l'historique
#     du projet) ; ils ne contiennent aucune logique IA.
#
# Exports publics : CorTokenizer, TOKENS_SPECIAUX, detecter_pays

import os
import re
import json
import time
from collections import Counter
from typing import List, Dict, Tuple, Optional

# Racine du projet (deux niveaux au-dessus de domain/)
_PROJET        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENIZER_PATH = os.path.join(_PROJET, "models", "cor_tokenizer.json")


# ══════════════════════════════════════════════════════════════════════
# VOCABULAIRE SPECIAL — ids 0-59 RESERVES ET IMMUABLES
# ══════════════════════════════════════════════════════════════════════

TOKENS_TECHNIQUES = {"[PAD]": 0, "[UNK]": 1}

TOKENS_SEQUENCE = {
    "[BOS]": 2, "[EOS]": 3, "[SEP]": 4, "[MASK]": 5,
    "[DOC]": 6, "[ART]": 7, "[REP]": 8, "[JUR]": 9,
}

TOKENS_PAYS = {
    "[CM]": 10, "[GA]": 11, "[CG]": 12, "[CD]": 13, "[TD]": 14,
    "[CF]": 15, "[GQ]": 16, "[CI]": 17, "[SN]": 18, "[BJ]": 19,
    "[BF]": 20, "[ML]": 21, "[NE]": 22, "[TG]": 23, "[GN]": 24,
    "[MG]": 25, "[KM]": 26, "[DJ]": 27, "[MR]": 28,
    "[OHADA]": 29, "[CEMAC]": 30, "[UEMOA]": 31, "[CIMA]": 32,
    "[OAPI]": 33, "[CIPRES]": 34, "[UA]": 35, "[COBAC]": 36,
}

TOKENS_DOMAINE = {
    "[AUDCG]": 37, "[AUSCGIE]": 38, "[AUPSRVE]": 39, "[AURVE]": 40,
    "[AUPAP]": 41, "[AUTF]": 42, "[AUOHSADA]": 43,
    "[TRAVAIL]": 44, "[PENAL]": 45, "[FONCIER]": 46, "[FISCAL]": 47,
    "[BANCAIRE]": 48, "[SOCIAL]": 49, "[FAMILLE]": 50,
    "[ARBITRAGE]": 51, "[DOUANE]": 52, "[ENVIRON]": 53,
    "[LOI]": 54, "[DECRET]": 55, "[ARRETE]": 56,
    "[CIRCULAIRE]": 57, "[JUGEMENT]": 58, "[ARRET]": 59,
}

TOKENS_SPECIAUX: Dict[str, int] = {}
TOKENS_SPECIAUX.update(TOKENS_TECHNIQUES)
TOKENS_SPECIAUX.update(TOKENS_SEQUENCE)
TOKENS_SPECIAUX.update(TOKENS_PAYS)
TOKENS_SPECIAUX.update(TOKENS_DOMAINE)

assert len(TOKENS_SPECIAUX) == 60
assert len(set(TOKENS_SPECIAUX.values())) == 60

PREMIER_ID_BPE = 60


# ══════════════════════════════════════════════════════════════════════
# TERMES JURIDIQUES AFRICAINS — injectes comme unites atomiques
# ══════════════════════════════════════════════════════════════════════

TERMES_JURIDIQUES = [
    "ccja", "beac", "bvmac", "cosumaf", "cndp",
    "tgi", "tcs", "tpi", "caa", "cour-supreme",
    "tribunal-administratif", "conseil-etat",
    "barreau", "parquet", "greffe", "huissier",
    "notaire", "avocat", "magistrat", "greffier",
    "acte-uniforme", "exequatur", "sentence-arbitrale",
    "clause-compromissoire", "injonction-payer",
    "saisie-attribution", "saisie-immobiliere",
    "saisie-vente", "saisie-conservatoire",
    "voie-execution", "procedure-collective",
    "liquidation-judiciaire", "redressement-judiciaire",
    "concordat-preventif",
    "licenciement", "preavis", "smig", "smag",
    "indemnite-licenciement", "rupture-abusive",
    "rupture-conventionnelle", "demission",
    "suspension-contrat", "periode-essai",
    "convention-collective", "inspection-travail",
    "tribunal-travail", "prudhommes",
    "heure-supplementaire", "conge-annuel",
    "conge-maternite", "accident-travail",
    "titre-foncier", "immatriculation", "cadastre",
    "expropriation", "bail-emphyteotique",
    "bail-commercial", "servitude", "mitoyennete",
    "usufruit", "nue-propriete", "hypotheque",
    "droit-superficie", "domaine-public",
    "domaine-prive", "lotissement",
    "sarl", "sa", "sas", "snc", "gie",
    "nantissement", "gage", "warrant",
    "lettre-change", "billet-ordre",
    "protêt", "aval", "endossement",
    "registre-commerce", "numero-contribuable",
    "assemblée-generale", "conseil-administration",
    "commissaire-comptes",
    "garde-a-vue", "detention-provisoire",
    "mise-en-examen", "non-lieu", "classement",
    "liberté-provisoire", "cautionnement",
    "perquisition", "instruction", "requisitoire",
    "mise-en-demeure", "amende", "sursis",
    "contrainte-corps",
    "fcfa", "xaf", "xof", "tva", "is", "irpp",
    "droit-douane", "valeur-en-douane",
    "dedouanement", "transit", "entrepot",
    "franchise", "exoneration", "redressement-fiscal",
    "controle-fiscal", "avis-mise-recouvrement",
    "ratio-solvabilite", "fonds-propres",
    "credit-bancaire", "escompte", "refinancement",
    "credit-documentaire", "lettre-credit",
    "garantie-bancaire", "caution-bancaire",
    "compte-dormant", "lutte-blanchiment",
    "financement-terrorisme", "kyc", "due-diligence",
    "mariage-coutumier", "dot", "polygamie",
    "divorce", "separation-corps", "pension-alimentaire",
    "garde-enfant", "adoption", "tutelle",
    "succession", "heritage", "testament",
    "partage-successoral",
    "article", "alinea", "paragraphe",
    "loi", "decret", "ordonnance", "arrete",
    "circulaire", "instruction", "note-service",
    "jugement", "arret", "ordonnance-refere",
    "contradit", "appel", "cassation",
    "pourvoi", "moyen-cassation",
]


# ══════════════════════════════════════════════════════════════════════
# DETECTION DES PAYS
# ══════════════════════════════════════════════════════════════════════

DETECTION_PAYS = {
    "[CM]"    : ["cameroun", "camerounais", "yaounde", "douala"],
    "[GA]"    : ["gabon", "gabonais", "libreville", "port-gentil"],
    "[CI]"    : ["cote d'ivoire", "ivoirien", "abidjan"],
    "[SN]"    : ["senegal", "senegalais", "dakar"],
    "[BJ]"    : ["benin", "beninois", "cotonou", "porto-novo"],
    "[BF]"    : ["burkina", "burkinabe", "ouagadougou"],
    "[ML]"    : ["mali", "malien", "bamako"],
    "[NE]"    : ["niger", "nigerien", "niamey"],
    "[TG]"    : ["togo", "togolais", "lome"],
    "[GN]"    : ["guinee", "guineen", "conakry"],
    "[CG]"    : ["congo-brazzaville", "brazzaville"],
    "[CD]"    : ["rdc", "congo-kinshasa", "kinshasa"],
    "[TD]"    : ["tchad", "tchadien", "ndjamena"],
    "[CF]"    : ["centrafrique", "centrafricain", "bangui"],
    "[GQ]"    : ["guinee equatoriale", "malabo"],
    "[OHADA]" : ["ohada", "acte uniforme", "ccja", "droit uniforme africain"],
    "[CEMAC]" : ["cemac", "beac", "cobac"],
    "[UEMOA]" : ["uemoa", "bceao"],
}


def detecter_pays(texte: str) -> str:
    """Detecte le token de pays le plus pertinent. Retourne '[OHADA]' par defaut."""
    texte_lower = texte.lower()
    scores = {}
    for token, mots_cles in DETECTION_PAYS.items():
        score = sum(1 for mot in mots_cles if mot in texte_lower)
        if score > 0:
            scores[token] = score
    if not scores:
        return "[OHADA]"
    return max(scores, key=scores.get)


# ══════════════════════════════════════════════════════════════════════
# NORMALISATION ET PRE-TOKENISATION
# ══════════════════════════════════════════════════════════════════════

def normaliser(texte: str) -> str:
    if not texte:
        return ""
    texte = texte.lower()
    texte = texte.replace("’", "'").replace("‘", "'").replace("`", "'")
    texte = texte.replace("'", " ")
    pattern_tiret = re.compile(r'([a-zàâäéèêëïîôùûüÿœæ])-([a-zàâäéèêëïîôùûüÿœæ])')
    while pattern_tiret.search(texte):
        texte = pattern_tiret.sub(r'\1_\2', texte)
    texte = re.sub(r'\bart\.?\s*(\d+)', r'article_\1', texte)
    texte = re.sub(
        r'(?:loi|decret|ordonnance|arrete)\s*n[°o]?\s*([\d/\-]+)',
        lambda m: "ref_" + re.sub(r'[/\-]', '_', m.group(1)),
        texte
    )
    return re.sub(r'\s+', ' ', texte).strip()


def pre_tokeniser(texte: str) -> List[str]:
    texte = normaliser(texte)
    if not texte:
        return []
    tokens = re.findall(r"[a-z0-9àâäéèêëïîôùûüÿœæ_]+|[.,;:!?()\[\]{}\"/°%]", texte)
    return [t for t in tokens if 1 <= len(t) <= 50]


# ══════════════════════════════════════════════════════════════════════
# ALGORITHME BPE
# ══════════════════════════════════════════════════════════════════════

def obtenir_paires(vocab_bpe: Dict[str, int]) -> Counter:
    paires = Counter()
    for mot, freq in vocab_bpe.items():
        symboles = mot.split()
        for i in range(len(symboles) - 1):
            paires[(symboles[i], symboles[i + 1])] += freq
    return paires


def fusionner_paire(vocab_bpe: Dict[str, int], paire: Tuple[str, str]) -> Dict[str, int]:
    nouveau = {}
    a, b    = paire
    pattern = re.compile(r'(?<!\S)' + re.escape(f"{a} {b}") + r'(?!\S)')
    fusion  = a + b
    for mot, freq in vocab_bpe.items():
        nouveau[pattern.sub(fusion, mot)] = freq
    return nouveau


# ══════════════════════════════════════════════════════════════════════
# COR TOKENIZER
# ══════════════════════════════════════════════════════════════════════

class CorTokenizer:
    """
    Tokeniseur BPE juridique africain pour Cor.

    Architecture du vocabulaire :
        ids 0-1   : techniques (PAD, UNK)
        ids 2-9   : sequence (BOS, EOS, SEP, MASK, DOC, ART, REP, JUR)
        ids 10-36 : pays (CEMAC + UEMOA + supranational)
        ids 37-59 : domaine juridique
        ids 60+   : BPE appris sur corpus

    POINT CRITIQUE — immutabilite des ids 0-59 :
    Hardcodes dans ConfigCor. Toute modification = re-entraîner depuis zero.
    """

    def __init__(self, vocab_size: int = 8000):
        self.vocab_size_cible = vocab_size
        self.vocab            : Dict[str, int]       = {}
        self.id_to_token      : Dict[int, str]       = {}
        self.regles_fusion    : List[Tuple[str, str]] = []
        self._initialiser_tokens_speciaux()

    def _initialiser_tokens_speciaux(self):
        for token, id_ in TOKENS_SPECIAUX.items():
            self.vocab[token]     = id_
            self.id_to_token[id_] = token
        assert len(self.vocab) == 60
        print(f"[COR-TOK] Tokens speciaux : {len(self.vocab)} (ids 0-{max(self.vocab.values())})")

    def _injecter_termes_juridiques(self):
        injected = 0
        for terme in TERMES_JURIDIQUES:
            if terme not in self.vocab:
                id_ = len(self.vocab)
                self.vocab[terme]     = id_
                self.id_to_token[id_] = terme
                injected += 1
        print(f"[COR-TOK] Termes juridiques injectes : {injected}")
        return injected

    def _construire_vocab_bpe_initial(self, corpus: List[str]) -> Dict[str, int]:
        freq_mots: Counter = Counter()
        for texte in corpus:
            freq_mots.update(pre_tokeniser(texte))
        vocab_bpe = {}
        for mot, freq in freq_mots.items():
            if mot not in self.vocab:
                vocab_bpe[' '.join(list(mot)) + ' </w>'] = freq
        return vocab_bpe

    def entrainer(self, corpus: List[str], nb_fusions: Optional[int] = None):
        """Entraine le tokeniseur BPE sur le corpus juridique africain."""
        print(f"\n{'='*65}")
        print(f"  COR TOKENIZER — Entrainement BPE")
        print(f"{'='*65}")
        t_debut = time.time()

        print(f"\n[1/4] Injection des termes juridiques africains...")
        nb_injectes = self._injecter_termes_juridiques()

        print(f"[2/4] Construction du vocabulaire initial (caracteres)...")
        vocab_bpe = self._construire_vocab_bpe_initial(corpus)

        chars = set()
        for mot in vocab_bpe:
            chars.update(mot.split())
        nb_chars = 0
        for char in sorted(chars):
            if char not in self.vocab:
                id_ = len(self.vocab)
                self.vocab[char]      = id_
                self.id_to_token[id_] = char
                nb_chars += 1

        if nb_fusions is None:
            nb_fusions = max(0, self.vocab_size_cible - len(self.vocab))

        print(f"[3/4] Apprentissage BPE ({nb_fusions} fusions max)...")
        fusions_realisees = 0
        t_log = time.time()

        for i in range(nb_fusions):
            if len(self.vocab) >= self.vocab_size_cible:
                break
            paires = obtenir_paires(vocab_bpe)
            if not paires:
                break
            meilleure = max(paires, key=paires.get)
            if paires[meilleure] < 2:
                break

            vocab_bpe = fusionner_paire(vocab_bpe, meilleure)
            self.regles_fusion.append(meilleure)
            fusions_realisees += 1

            nouveau_token = meilleure[0] + meilleure[1]
            if nouveau_token not in self.vocab:
                id_ = len(self.vocab)
                self.vocab[nouveau_token]      = id_
                self.id_to_token[id_]          = nouveau_token

            if (i + 1) % 500 == 0 or (time.time() - t_log) > 30:
                print(f"      Fusion {i+1:5d}/{nb_fusions} — vocab : {len(self.vocab):5d}")
                t_log = time.time()

        print(f"\n[4/4] Entrainement termine en {time.time()-t_debut:.0f}s")
        print(f"      VOCABULAIRE FINAL: {len(self.vocab)} tokens")
        return self

    def tokeniser(self, texte: str) -> List[int]:
        """Tokenise un texte en liste d'ids. Format : [BOS_id, ...tokens..., EOS_id]"""
        if not texte:
            return [self.vocab["[BOS]"], self.vocab["[EOS]"]]

        tokens_speciaux_pattern = re.compile(
            r'(\[(?:' +
            '|'.join(re.escape(t[1:-1]) for t in TOKENS_SPECIAUX) +
            r')\])'
        )
        parties = tokens_speciaux_pattern.split(texte)
        ids = [self.vocab["[BOS]"]]

        for partie in parties:
            if not partie:
                continue
            if partie in self.vocab:
                ids.append(self.vocab[partie])
                continue
            for mot in pre_tokeniser(partie):
                if mot in self.vocab:
                    ids.append(self.vocab[mot])
                    continue
                symboles = list(mot) + ["</w>"]
                for paire in self.regles_fusion:
                    i = 0
                    nouveau = []
                    while i < len(symboles):
                        if (i < len(symboles) - 1
                                and symboles[i] == paire[0]
                                and symboles[i + 1] == paire[1]):
                            nouveau.append(paire[0] + paire[1])
                            i += 2
                        else:
                            nouveau.append(symboles[i])
                            i += 1
                    symboles = nouveau
                for sym in symboles:
                    sym_clean = sym.replace("</w>", "")
                    if sym_clean:
                        ids.append(self.vocab.get(sym_clean, self.vocab["[UNK]"]))

        ids.append(self.vocab["[EOS]"])
        return ids

    def decoder(self, ids: List[int], ignorer_speciaux: bool = True) -> str:
        """Convertit une liste d'ids en texte lisible."""
        tokens_a_ignorer = set()
        if ignorer_speciaux:
            tokens_a_ignorer = {"[PAD]", "[BOS]", "[EOS]", "[MASK]",
                                 "[DOC]", "[ART]", "[REP]", "[JUR]"}
            tokens_a_ignorer.update(TOKENS_PAYS.keys())
            tokens_a_ignorer.update(TOKENS_DOMAINE.keys())

        fragments = []
        for id_ in ids:
            if id_ == self.vocab.get("[EOS]"):
                break
            token = self.id_to_token.get(id_, "[UNK]")
            if token not in tokens_a_ignorer:
                fragments.append(token)

        texte = " ".join(fragments)
        texte = texte.replace(" </w>", " ").replace("</w>", "")
        texte = re.sub(r'_', ' ', texte)
        return re.sub(r'\s+', ' ', texte).strip()

    def construire_prompt_cor(
        self,
        question       : str,
        passages_rag   : List[str],
        pays_token     : Optional[str] = None,
        max_len        : int = 512,
        max_rep_tokens : int = 80,
    ) -> Tuple[List[int], int]:
        """
        Construit la sequence d'entree complete pour Cor.
        Format : [BOS] [PAYS] question [SEP] passage_1 [SEP] passage_2 [REP]
        Retourne (ids, pos_rep).
        """
        bos_id = self.vocab["[BOS]"]
        sep_id = self.vocab["[SEP]"]
        rep_id = self.vocab["[REP]"]

        if pays_token is None:
            pays_token = detecter_pays(question)
        pays_id = self.vocab.get(pays_token, self.vocab["[OHADA]"])

        ids_question    = self.tokeniser(question)[1:-1]
        budget_contexte = max_len - max_rep_tokens - 1
        budget_passages = budget_contexte - len(ids_question) - 3

        ids_passages = []
        if passages_rag and budget_passages > 0:
            per_passage = max(10, budget_passages // len(passages_rag))
            for passage in passages_rag:
                ids_p = self.tokeniser(passage)[1:-1][:per_passage]
                ids_passages.extend([sep_id] + ids_p)

        ids = [bos_id, pays_id] + ids_question + ids_passages + [rep_id]

        if len(ids) > budget_contexte:
            max_passages = budget_contexte - len(ids_question) - 3
            ids_passages_tronques = ids_passages[:max(0, max_passages)]
            ids = ([bos_id, pays_id] + ids_question +
                   ids_passages_tronques + [rep_id])

        return ids, len(ids) - 1

    def sauvegarder(self, chemin: str = None):
        """Sauvegarde le tokeniseur en JSON."""
        chemin = chemin or TOKENIZER_PATH
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        data = {
            "version"           : "cor-1.0",
            "vocab_size_reel"   : len(self.vocab),
            "vocab_size_cible"  : self.vocab_size_cible,
            "nb_tokens_speciaux": 60,
            "premier_id_bpe"    : PREMIER_ID_BPE,
            "vocab"             : self.vocab,
            "id_to_token"       : {str(k): v for k, v in self.id_to_token.items()},
            "regles_fusion"     : self.regles_fusion,
            "tokens_speciaux"   : TOKENS_SPECIAUX,
        }
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] Tokeniseur sauvegarde : {chemin} ({os.path.getsize(chemin)//1024} Ko)")

    @classmethod
    def charger(cls, chemin: str = None) -> "CorTokenizer":
        """Charge un tokeniseur sauvegarde."""
        chemin = chemin or TOKENIZER_PATH
        if not os.path.exists(chemin):
            raise FileNotFoundError(
                f"Tokeniseur introuvable : {chemin}\n"
                f"Lancer d'abord : python scripts/train.py --phase tokenizer"
            )
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("version", "inconnue")
        if not version.startswith("cor-"):
            raise ValueError(
                f"Mauvais tokeniseur (version={version}). "
                f"Attends cor_tokenizer.json, pas odyxia_tokenizer.json."
            )
        tok = cls(vocab_size=data["vocab_size_cible"])
        tok.vocab         = data["vocab"]
        tok.id_to_token   = {int(k): v for k, v in data["id_to_token"].items()}
        tok.regles_fusion = [tuple(r) for r in data["regles_fusion"]]

        for token, id_attendu in TOKENS_SPECIAUX.items():
            id_reel = tok.vocab.get(token)
            if id_reel != id_attendu:
                raise ValueError(
                    f"Incoherence : '{token}' id attendu={id_attendu}, reel={id_reel}."
                )
        print(f"[OK] CorTokenizer charge : {len(tok.vocab)} tokens, {len(tok.regles_fusion)} fusions")
        return tok

    def rapport(self):
        print(f"\n{'='*65}")
        print(f"  COR TOKENIZER — Rapport de vocabulaire")
        print(f"  Vocabulaire total    : {len(self.vocab)} tokens")
        print(f"  Tokens speciaux      : 60 (ids 0-59)")
        print(f"  Tokens BPE           : {len(self.vocab) - 60}")
        print(f"  Regles de fusion     : {len(self.regles_fusion)}")
        print(f"{'='*65}")
