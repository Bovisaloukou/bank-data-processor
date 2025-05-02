# src/validation.py

import pandas as pd
from typing import Dict, Any, Tuple
import re

def load_validation_rules(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Charge les règles de validation depuis la configuration.

    Args:
        config (Dict[str, Any]): Dictionnaire de configuration.

    Returns:
        Dict[str, Any]: Règles de validation.
    """
    return config.get("validation", {})

def validate_bic(bic: str) -> Tuple[bool, str]:
    """
    Valide un code BIC/SWIFT selon les standards bancaires.
    Format: BANKCCLL[BBB]
    - BANK: 4 lettres pour le code de la banque
    - CC: 2 lettres pour le code pays ISO
    - LL: 2 caractères alphanumériques pour la localisation
    - BBB: 3 caractères alphanumériques optionnels pour le code branche

    Args:
        bic (str): Code BIC à valider

    Returns:
        Tuple[bool, str]: (True si valide, message d'erreur sinon)
    """
    bic = str(bic).replace(" ", "").upper()
    
    if len(bic) not in [8, 11]:
        return False, f"Longueur BIC invalide: {len(bic)} caractères (attendu 8 ou 11)"

    # Vérifie le code banque (4 premières lettres)
    if not bic[:4].isalpha():
        return False, f"Code banque invalide (4 lettres attendues): {bic[:4]}"

    # Vérifie le code pays (2 lettres)
    if not bic[4:6].isalpha():
        return False, f"Code pays invalide (2 lettres attendues): {bic[4:6]}"

    # Vérifie le code localisation (2 caractères alphanumériques)
    if not bic[6:8].isalnum():
        return False, f"Code localisation invalide (2 caractères alphanumériques attendus): {bic[6:8]}"

    # Vérifie le code branche si présent (3 caractères alphanumériques)
    if len(bic) == 11 and not bic[8:].isalnum():
        return False, f"Code branche invalide (3 caractères alphanumériques attendus): {bic[8:]}"

    return True, "BIC valide"

def validate_iban(iban: str) -> Tuple[bool, str]:
    """
    Valide un IBAN selon les standards bancaires.
    Format général: CCkkBBAN
    - CC: 2 lettres pour le code pays ISO
    - kk: 2 chiffres pour la clé de contrôle
    - BBAN: Basic Bank Account Number (longueur variable selon le pays)

    Args:
        iban (str): IBAN à valider

    Returns:
        Tuple[bool, str]: (True si valide, message d'erreur sinon)
    """
    iban = str(iban).replace(" ", "").upper()
    
    if len(iban) < 5:
        return False, "IBAN trop court"
        
    if not re.match(r"^[A-Z]{2}", iban):
        return False, f"Code pays IBAN invalide (2 lettres attendues): {iban[:2]}"
        
    if not iban[2:4].isdigit():
        return False, f"Clé de contrôle IBAN invalide (2 chiffres attendus): {iban[2:4]}"
        
    # Vérifie que le reste est alphanumérique
    if not iban[4:].isalnum():
        return False, f"Format BBAN invalide (caractères alphanumériques attendus): {iban[4:]}"

    # Longueurs standards par pays (à compléter selon les besoins)
    country_lengths = {
        'FR': 27,  # France
        'DE': 22,  # Allemagne
        'GB': 22,  # Royaume-Uni
        'CI': 28,  # Côte d'Ivoire
        'SN': 28,  # Sénégal
        'JP': 24,  # Japon (exemple)
        'US': 24   # États-Unis (exemple)
    }
    
    country = iban[:2]
    if country in country_lengths and len(iban) != country_lengths[country]:
        return False, f"Longueur IBAN invalide pour {country}: {len(iban)} caractères (attendu {country_lengths[country]})"

    return True, "IBAN valide"

def validate_transaction(row: pd.Series, rules: Dict[str, Any]) -> bool:
    """
    Valide une transaction selon les règles métier et les standards bancaires.

    Args:
        row (pd.Series): Ligne représentant une transaction.
        rules (Dict[str, Any]): Règles de validation.

    Returns:
        bool: True si la transaction est valide, False sinon.
    """
    # 1. Vérification des colonnes requises
    required_cols = ['Montant', 'Devise', 'IBAN_Emetteur', 'IBAN_Beneficiaire', 'BIC_SWIFT']
    if not all(col in row.index for col in required_cols):
        print(f"DEBUG: Colonnes manquantes. Colonnes requises: {required_cols}")
        return False

    # 2. Vérification des valeurs nulles
    if any(pd.isna(row[col]) for col in required_cols):
        print(f"DEBUG: Valeurs nulles détectées")
        return False

    # 3. Validation du montant et de la devise
    montant = row['Montant']
    devise = str(row['Devise']).strip().upper()

    # 3.1 Montant maximal
    max_amount = rules.get("max_transaction_amount", float('inf'))
    if pd.notna(montant) and montant > max_amount:
        print(f"DEBUG: Montant {montant} dépasse le maximum autorisé {max_amount}")
        return False

    # 3.2 Devise autorisée
    allowed_currencies = [c.strip().upper() for c in rules.get("allowed_currencies", [])]
    if allowed_currencies and devise not in allowed_currencies:
        print(f"DEBUG: Devise {devise} non autorisée. Devises autorisées: {allowed_currencies}")
        return False

    # 4. Validation des IBANs
    is_valid_emetteur, msg_emetteur = validate_iban(row['IBAN_Emetteur'])
    if not is_valid_emetteur:
        print(f"DEBUG: IBAN émetteur invalide: {msg_emetteur}")
        return False

    is_valid_beneficiaire, msg_beneficiaire = validate_iban(row['IBAN_Beneficiaire'])
    if not is_valid_beneficiaire:
        print(f"DEBUG: IBAN bénéficiaire invalide: {msg_beneficiaire}")
        return False

    # 5. Validation du BIC
    is_valid_bic, msg_bic = validate_bic(row['BIC_SWIFT'])
    if not is_valid_bic:
        print(f"DEBUG: BIC invalide: {msg_bic}")
        return False

    print(f"DEBUG: Transaction valide")
    return True