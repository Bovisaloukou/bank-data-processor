# src/utils.py

import logging
import json
from typing import Any
from pythonjsonlogger import jsonlogger
from cryptography.fernet import Fernet
from pathlib import Path
import base64

def setup_structured_logging(name: str, level: str, log_file: str) -> logging.Logger:
    """
    Configure un logger structuré au format JSON.

    Args:
        name (str): Nom du logger.
        level (str): Niveau de logging ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        log_file (str): Chemin du fichier de log.

    Returns:
        logging.Logger: L'instance du logger configuré.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Empêcher la propagation si déjà configuré (utile dans les tests)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Créer le répertoire de logs si nécessaire
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Handler console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(jsonlogger.JsonFormatter())
    logger.addHandler(console_handler)

    # Handler fichier
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(jsonlogger.JsonFormatter())
    logger.addHandler(file_handler)

    return logger

def generate_encryption_key(key_file_path: Path) -> bytes:
    """
    Génère une nouvelle clé de chiffrement Fernet et l'enregistre dans un fichier.
    Si le fichier existe déjà, charge la clé existante.

    Args:
        key_file_path (Path): Chemin où stocker/lire la clé.

    Returns:
        bytes: La clé de chiffrement.
    """
    if key_file_path.exists():
        with open(key_file_path, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file_path, "wb") as f:
            f.write(key)
    return key

def encrypt_data(data: str, key: bytes) -> str:
    """
    Chiffre une chaîne de caractères en utilisant Fernet.

    Args:
        data (str): La chaîne à chiffrer.
        key (bytes): La clé de chiffrement Fernet.

    Returns:
        str: Les données chiffrées encodées en base64 (en tant que chaîne).
    """
    f = Fernet(key)
    encrypted_bytes = f.encrypt(data.encode('utf-8'))
    return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')

def decrypt_data(encrypted_data: str, key: bytes) -> str:
    """
    Déchiffre une chaîne de caractères chiffrée avec Fernet.

    Args:
        encrypted_data (str): Les données chiffrées (chaîne encodée en base64).
        key (bytes): La clé de chiffrement Fernet.

    Returns:
        str: Les données déchiffrées.
    """
    f = Fernet(key)
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
    decrypted_bytes = f.decrypt(encrypted_bytes)
    return decrypted_bytes.decode('utf-8')

def mask_sensitive_data(data: str, characters_to_show: int = 4) -> str:
    """
    Masque les données sensibles (ex: numéros de compte, IBAN).

    Args:
        data (str): La chaîne à masquer.
        characters_to_show (int): Nombre de caractères à montrer à la fin.

    Returns:
        str: La chaîne masquée.
    """
    if not data:
        return ""
    if len(data) <= characters_to_show:
        return "*" * len(data)
    return "*" * (len(data) - characters_to_show) + data[-characters_to_show:]