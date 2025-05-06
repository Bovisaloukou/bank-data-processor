# Module de catégorisation automatique des transactions
# Basé sur des mots-clés simples pour chaque catégorie

import re
from typing import List, Dict

def charger_categories_personnalisees(categories_config: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Charge les catégories personnalisées depuis la config TOML."""
    return {cat.lower(): [kw.lower() for kw in mots] for cat, mots in categories_config.items()}

CATEGORIES_PAR_DEFAUT = {
    "salaire": ["salaire", "payroll", "remuneration"],
    "loyer": ["loyer", "rent"],
    "alimentation": ["supermarche", "carrefour", "auchan", "leclerc", "alimentation", "epicerie", "boulangerie", "restaurant", "mcdo", "kfc", "burger"],
    "transports": ["sncf", "ratp", "uber", "taxi", "essence", "station", "carburant", "total", "autoroute"],
    "sante": ["pharmacie", "medecin", "hopital", "mutuelle", "doctolib"],
    "divertissement": ["cinema", "netflix", "spotify", "loisir", "concert", "jeux"],
    "autre": []
}

def categoriser_transaction(libelle: str, montant: float, categories: Dict[str, List[str]] = None) -> str:
    """Retourne la catégorie d'une transaction selon le libellé et le montant."""
    if not libelle:
        return "autre"
    libelle = libelle.lower()
    categories = categories or CATEGORIES_PAR_DEFAUT
    for categorie, mots_cles in categories.items():
        for mot in mots_cles:
            if re.search(rf"\\b{re.escape(mot)}\\b", libelle):
                return categorie
    return "autre"
