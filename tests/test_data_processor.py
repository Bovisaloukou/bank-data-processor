# tests/test_data_processor.py

import pytest
import pandas as pd
from pathlib import Path
import os
import shutil
import json
import tomlkit
import logging

# Importer la classe à tester et les utilitaires
from src.data_processor import DataProcessor
from src.utils import encrypt_data, decrypt_data # Tester les fonctions utilitaires aussi
from src.validation import validate_transaction # Tester la logique de validation

# --- Fixtures ---

@pytest.fixture(scope="session")
def project_root():
    """Retourne le chemin racine du projet."""
    return Path(__file__).parent.parent

@pytest.fixture(scope="session")
def test_config_path(project_root):
    """Retourne le chemin du fichier de configuration de test."""
    return project_root / "config/config.toml"

@pytest.fixture(scope="function")
def processor(test_config_path, project_root):
    """
    Fixture pour créer une instance de DataProcessor avec un environnement de test propre.
    Nettoie les répertoires de test avant chaque test.
    """
    test_output_dir = project_root / "data/output_test"
    test_quarantine_dir = project_root / "data/quarantine_test"
    test_input_dir = project_root / "data/input_test"
    test_log_file = project_root / "logs/processor_test.log"
    test_encryption_key_file = project_root / ".encryption_key_test"
    test_processed_files_log = project_root / "data/processed_files_test.log"


    # Nettoyer les répertoires/fichiers de test
    for d in [test_output_dir, test_quarantine_dir, test_input_dir]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    if test_log_file.exists():
        test_log_file.unlink()
    if test_encryption_key_file.exists():
        test_encryption_key_file.unlink()
    if test_processed_files_log.exists():
        test_processed_files_log.unlink()


    # Modifier la configuration pour pointer vers les répertoires/fichiers de test
    # Charger la config originale, modifier les chemins, puis recharger le processor
    original_config_path = project_root / "config/config.toml"
    with open(original_config_path, 'r') as f:
        config_data = tomlkit.load(f)

    config_data['paths']['input_dir'] = str(test_input_dir)
    config_data['paths']['output_dir'] = str(test_output_dir)
    config_data['paths']['quarantine_dir'] = str(test_quarantine_dir)
    config_data['paths']['encryption_key_file'] = str(test_encryption_key_file)
    config_data['paths']['processed_files_log'] = str(test_processed_files_log)
    config_data['logging']['log_file'] = str(test_log_file)
    config_data['processing']['parallel_workers'] = 1 # Utiliser 1 worker pour les tests simples

    # Sauvegarder la config modifiée dans un fichier temporaire de test
    temp_config_path = project_root / "config/temp_test_config.toml"
    with open(temp_config_path, 'w') as f:
        tomlkit.dump(config_data, f)

    # Créer l'instance du processeur avec la config de test
    proc = DataProcessor(config_path=str(temp_config_path))

    # Le processor étant créé, yield le pour les tests
    yield proc

    # --- Nettoyage après le test ---
    # Le nettoyage des répertoires/fichiers de sortie/quarantaine est fait au début
    # Nettoyer le fichier de config temporaire
    if temp_config_path.exists():
        temp_config_path.unlink()

# --- Tests unitaires pour DataProcessor ---

def test_processor_initialization(processor, project_root):
    """Vérifie que le processeur s'initialise correctement."""
    assert processor is not None
    assert isinstance(processor.logger, logging.Logger)
    assert isinstance(processor.config, dict)
    assert processor.encryption_key is not None
    assert Path(processor.config['paths']['output_dir']).exists()
    assert Path(processor.config['paths']['quarantine_dir']).exists()
    assert Path(processor.config['logging']['log_file']).parent.exists() # Vérifie que le répertoire de logs existe

def test_encryption_decryption(processor):
    """Vérifie les fonctions de chiffrement et déchiffrement."""
    sensitive_data = "Ceci est un numéro de compte secret : 123456789"
    encrypted = processor.encrypt_data(sensitive_data)
    decrypted = processor.decrypt_data(encrypted)
    assert decrypted == sensitive_data
    assert encrypted != sensitive_data # Assure que c'est bien chiffré

def test_process_csv(processor, project_root):
    """Teste le traitement d'un fichier CSV simple."""
    input_dir = Path(processor.config['paths']['input_dir'])
    csv_content = "Header1,Montant,Header3\nValue1,100.50,Value3\nValueA,200,ValueB"
    csv_file = input_dir / "test.csv"
    csv_file.write_text(csv_content, encoding='utf-8')

    # Appeler la méthode privée pour traiter le fichier (contourne le pipeline)
    # Dans un vrai test unitaire, on mock les dépendances (comme pd.read_csv)
    # Pour cette démo, on teste l'intégration simple.
    df = processor._process_csv(csv_file)

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) == 2
    assert 'Montant' in df.columns
    # Vérifie que le montant est converti en numérique (pyarrow)
    assert pd.api.types.is_float_dtype(df['Montant'].dtype) or pd.api.types.is_integer_dtype(df['Montant'].dtype)
    assert df['Montant'].iloc[0] == 100.50
    assert df['Montant'].iloc[1] == 200.0

def test_process_excel(processor, project_root):
    """Teste le traitement d'un fichier Excel simple."""
    input_dir = Path(processor.config['paths']['input_dir'])
    excel_file = input_dir / "test.xlsx"

    # Créer un fichier Excel bidon
    df_test = pd.DataFrame({
        'ColA': ['A1', 'A2'],
        'Montant': [50.75, 150],
        'ColC': ['C1', 'C2']
    })
    df_test.to_excel(excel_file, index=False)

    # Appeler la méthode privée
    df = processor._process_excel(excel_file)

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) == 2
    assert 'Montant' in df.columns
    assert pd.api.types.is_float_dtype(df['Montant'].dtype) or pd.api.types.is_integer_dtype(df['Montant'].dtype)
    assert df['Montant'].iloc[0] == 50.75
    assert df['Montant'].iloc[1] == 150.0

def test_process_pdf_with_table(processor, project_root):
    """Teste le traitement d'un PDF contenant une table simple."""
    # NOTE: Créer un fichier PDF *avec des tables détectables par pdfplumber* dans un test unitaire est complexe.
    # Pour ce test, on va soit :
    # 1. Mock l'appel à pdfplumber.open et page.extract_tables
    # 2. Avoir un *vrai* fichier PDF de test simple (moins "unitaire" mais plus réaliste pour la démo)
    # Option 2 est plus simple pour une démo de code.
    # Pour un vrai projet, on ferait Option 1 avec des mocks précis.

    # Créer un fichier PDF simple avec une table (nécessite reportlab ou autre lib PDF)
    # On peut réutiliser la fonction de génération de rapport PDF pour créer un fichier test.
    from src.reporting import generate_pdf_report # Importer pour le test

    input_dir = Path(processor.config['paths']['input_dir'])
    pdf_file = input_dir / "test_table.pdf"
    df_source = pd.DataFrame({
        'Date': ['2023-01-01', '2023-01-02'],
        'Description': ['Paiement 1', 'Transfert 2'],
        'Montant': [100.0, -50.0]
    })
    generate_pdf_report(df_source, pdf_file) # Utilise la fonction de rapport pour créer le PDF de test

    # Appeler la méthode privée
    df = processor._process_pdf(pdf_file)

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    # L'extraction PDF peut ajouter des lignes vides ou headers répétés, nécessite un nettoyage robuste
    # On s'attend à ce que le nettoyage remove_duplicates aide.
    # On teste si les colonnes attendues sont présentes et s'il y a des données.
    assert 'Montant' in df.columns
    # Vérifier la conversion en numérique après nettoyage
    assert pd.api.types.is_float_dtype(df['Montant'].dtype) or pd.api.types.is_integer_dtype(df['Montant'].dtype)
    # Vérifier si au moins une ligne avec des montants numériques est présente (approximation)
    assert df['Montant'].dropna().shape[0] > 0


def test_clean_data(processor):
    """Teste la fonction de nettoyage des données."""
    # Créer un DataFrame avec doublons et formats mixtes
    data = {
        'ID': [1, 2, 2, 3, 4],
        'Montant': ['1,200.50', '500', '500', '100', '2.5'],
        'Date': ['01/01/2023', '2023-01-02', '2023-01-02', 'InvalidDate', '01-03-2023'],
        'IBAN Emetteur': ['FR14xxxxxxxxxxxxxxxxxxxxxx', 'DE89yyyyyyyyyyyyyyyyyyyyyy', 'DE89yyyyyyyyyyyyyyyyyyyyyy', pd.NA, 'LU28zzzzzzzzzzzzzzzzzzzzzz'],
        'BIC_SWIFT': ['ABCDE FF', 'FGHIJKLL', 'FGHIJKLL', '12345678', 'MNOPQRSTUVW'],
        'Devise': ['EUR ', ' usd', 'USD', 'XOF', 'GBP'],
        'Extra Col': ['A', 'B', 'B', 'C', 'D']
    }
    df_raw = pd.DataFrame(data)

    df_cleaned = processor._clean_data(df_raw.copy()) # Utiliser .copy() pour ne pas modifier l'original

    assert isinstance(df_cleaned, pd.DataFrame)
    assert len(df_cleaned) == 4 # 5 lignes originales - 1 doublon = 4
    assert 'Montant' in df_cleaned.columns
    # Vérifie la conversion du montant
    assert pd.api.types.is_float_dtype(df_cleaned['Montant'].dtype) or pd.api.types.is_integer_dtype(df_cleaned['Montant'].dtype)
    # Vérifie que les formats point/virgule sont gérés
    assert 1200.50 in df_cleaned['Montant'].values
    assert 500.0 in df_cleaned['Montant'].values

    assert 'Date' in df_cleaned.columns
    # Vérifie la conversion des dates, une date invalide doit être NaT
    assert pd.api.types.is_datetime64_any_dtype(df_cleaned['Date'].dtype)
    assert pd.isna(df_cleaned['Date'].iloc[3]) # La 4ème ligne (index 3 après dropna) avait 'InvalidDate'

    # Vérifie le nettoyage des noms de colonnes
    assert 'IBAN_Emetteur' in df_cleaned.columns
    assert 'Extra_Col' in df_cleaned.columns

    # Vérifie le masquage des données sensibles
    assert df_cleaned['IBAN_Emetteur'].iloc[0].startswith('****************') # Vérifie que c'est masqué
    assert df_cleaned['IBAN_Emetteur'].iloc[0].endswith('zzzzzzzzzzzzzzzzzzzzzz'[-4:]) # Vérifie que les derniers sont visibles

    # Vérifie le nettoyage de la devise
    assert 'EUR' in df_cleaned['Devise'].values
    assert 'USD' in df_cleaned['Devise'].values
    assert 'XOF' in df_cleaned['Devise'].values
    assert 'GBP' in df_cleaned['Devise'].values

def test_validate_transaction_valid(processor):
    """Teste une transaction valide."""
    rules = processor.validation_rules
    valid_row = pd.Series({
        'Montant': 5000000.0, # Moins que max_amount (10M par défaut)
        'Devise': 'XOF',     # Devise autorisée
        'IBAN_Emetteur': 'CI00112345678901234567890123', # Format IBAN basique OK
        'IBAN_Beneficiaire': 'SN01098765432109876543210987', # Format IBAN basique OK
        'BIC_SWIFT': 'ABCDEFGH', # Format BIC 8 OK
        'Description': 'Transfert OK'
    })
    assert validate_transaction(valid_row, rules) is True

def test_validate_transaction_invalid_amount(processor):
    """Teste une transaction avec un montant invalide."""
    rules = processor.validation_rules
    invalid_row_amount = pd.Series({
        'Montant': 15000000.0, # Plus que max_amount (10M)
        'Devise': 'XOF',
        'IBAN_Emetteur': 'VALID_IBAN',
        'IBAN_Beneficiaire': 'VALID_IBAN',
        'BIC_SWIFT': 'VALID_BIC',
        'Description': 'Grosse transaction'
    })
    assert validate_transaction(invalid_row_amount, rules) is False # Devrait être invalide

def test_validate_transaction_invalid_currency(processor):
    """Teste une transaction avec une devise non autorisée."""
    rules = processor.validation_rules
    invalid_row_currency = pd.Series({
        'Montant': 1000000.0,
        'Devise': 'JPY', # Devise non autorisée par défaut (XOF, EUR, USD)
        'IBAN_Emetteur': 'VALID_IBAN',
        'IBAN_Beneficiaire': 'VALID_IBAN',
        'BIC_SWIFT': 'VALID_BIC',
        'Description': 'Paiement JPY'
    })
    assert validate_transaction(invalid_row_currency, rules) is False

def test_validate_transaction_invalid_iban(processor):
    """Teste une transaction avec un format IBAN invalide."""
    rules = processor.validation_rules
    invalid_row_iban = pd.Series({
        'Montant': 1000000.0,
        'Devise': 'XOF',
        'IBAN_Emetteur': 'INVALID-IBAN-FORMAT', # Format invalide
        'IBAN_Beneficiaire': 'VALID_IBAN',
        'BIC_SWIFT': 'VALID_BIC',
        'Description': 'IBAN KO'
    })
    assert validate_transaction(invalid_row_iban, rules) is False

def test_validate_transaction_invalid_bic(processor):
    """Teste une transaction avec un format BIC/SWIFT invalide."""
    rules = processor.validation_rules
    invalid_row_bic = pd.Series({
        'Montant': 1000000.0,
        'Devise': 'XOF',
        'IBAN_Emetteur': 'VALID_IBAN',
        'IBAN_Beneficiaire': 'VALID_IBAN',
        'BIC_SWIFT': 'INVALID_BIC_TOO_SHORT', # Format invalide
        'Description': 'BIC KO'
    })
    assert validate_transaction(invalid_row_bic, rules) is False

def test_validate_data(processor):
    """Teste la fonction de validation de DataFrame."""
    data = {
        'Montant': [5000000.0, 15000000.0, 1000000.0, 2000000.0],
        'Devise': ['XOF', 'XOF', 'JPY', 'EUR'],
        'IBAN_Emetteur': ['VALID_IBAN', 'VALID_IBAN', 'VALID_IBAN', 'INVALID-IBAN'],
        'IBAN_Beneficiaire': ['VALID_IBAN', 'VALID_IBAN', 'VALID_IBAN', 'VALID_IBAN'],
        'BIC_SWIFT': ['VALID_BIC', 'VALID_BIC', 'VALID_BIC', 'VALID_BIC'],
        'Description': ['OK', 'Trop cher', 'Mauvaise devise', 'IBAN KO']
    }
    df_cleaned = pd.DataFrame(data)

    # S'assurer que les colonnes attendues par validate_transaction sont présentes (ajoutées dans _validate_data si manquantes)
    expected_cols = ['Montant', 'Devise', 'IBAN_Emetteur', 'IBAN_Beneficiaire', 'BIC_SWIFT']
    for col in expected_cols:
        if col not in df_cleaned.columns:
             df_cleaned[col] = pd.NA # Ajouter les colonnes manquantes avec NaN/None

    valid_df, invalid_df = processor._validate_data(df_cleaned)

    assert isinstance(valid_df, pd.DataFrame)
    assert isinstance(invalid_df, pd.DataFrame)

    assert len(valid_df) == 1 # Seule la première transaction est valide
    assert len(invalid_df) == 3 # Les 3 autres sont invalides

    # Vérifier que la ligne valide est correcte
    assert valid_df.iloc[0]['Montant'] == 5000000.0
    assert valid_df.iloc[0]['Devise'] == 'XOF'

    # Vérifier que les lignes invalides contiennent les cas d'échec
    assert 15000000.0 in invalid_df['Montant'].values # Montant trop élevé
    assert 'JPY' in invalid_df['Devise'].values       # Devise non autorisée
    assert 'INVALID-IBAN' in invalid_df['IBAN_Emetteur'].values # IBAN invalide (Note: cette colonne est masquée dans le df_cleaned si le masquage est appliqué avant)

    # Vérifier que les colonnes de validation internes ne sont pas dans les DataFrames de sortie
    assert 'is_valid' not in valid_df.columns
    assert 'is_valid' not in invalid_df.columns


def test_run_pipeline_end_to_end(processor, project_root):
    """
    Teste le pipeline complet avec des fichiers d'entrée.
    C'est un test d'intégration.
    """
    input_dir = Path(processor.config['paths']['input_dir'])
    output_dir = Path(processor.config['paths']['output_dir'])
    quarantine_dir = Path(processor.config['paths']['quarantine_dir'])

    # Créer des fichiers de test dans le répertoire d'entrée
    csv_content = "Montant,Devise,IBAN_Emetteur,IBAN_Beneficiaire,BIC_SWIFT,Description\n5000000,XOF,VALID_IBAN_1,VALID_IBAN_2,VALID_BIC,Transfert OK\n15000000,XOF,VALID_IBAN_A,VALID_IBAN_B,VALID_BIC,Grosse transaction"
    (input_dir / "transactions.csv").write_text(csv_content, encoding='utf-8')

    excel_content_df = pd.DataFrame({
        'Montant': [1000000, 2000000],
        'Devise': ['EUR', 'JPY'], # JPY est invalide
        'IBAN_Emetteur': ['VALID_IBAN_X', 'VALID_IBAN_Y'],
        'IBAN_Beneficiaire': ['VALID_IBAN_P', 'VALID_IBAN_Q'],
        'BIC_SWIFT': ['VALID_BIC_1', 'VALID_BIC_2'],
        'Description': ['Paiement EUR', 'Paiement JPY']
    })
    (input_dir / "paiements.xlsx").mkdir(parents=True, exist_ok=True) # Crée le répertoire si nécessaire
    excel_content_df.to_excel(input_dir / "paiements.xlsx", index=False)

    # Créer un PDF de test simple (peut ne pas contenir de tables facilement détectables, ajuster si nécessaire)
    # Pour une démo, on s'assure que pdfplumber trouve *quelque chose* ou on mock cette partie
    # Réutiliser la fonction de rapport pour créer un PDF simple comme source
    from src.reporting import generate_pdf_report
    pdf_source_df = pd.DataFrame({
        'Montant': [7000000, 9000000],
        'Devise': ['USD', 'USD'],
        'IBAN_Emetteur': ['PDF_IBAN_1', 'PDF_IBAN_2'],
        'IBAN_Beneficiaire': ['PDF_IBAN_A', 'PDF_IBAN_B'],
        'BIC_SWIFT': ['PDF_BIC_X', 'PDF_BIC_Y'],
        'Description': ['Retrait USD', 'Dépôt USD']
    })
    generate_pdf_report(pdf_source_df, input_dir / "releve.pdf")


    # Exécuter le pipeline
    processor.run_pipeline()

    # --- Vérifier les résultats ---

    # Vérifier les fichiers de sortie
    assert (output_dir / "rapport_transactions_valides.pdf").exists()
    assert (output_dir / "transactions_valides.xlsx").exists()
    assert (output_dir / "transactions_valides_nettoyees.csv").exists()

    # Charger les données valides nettoyées pour vérification
    valid_df = pd.read_csv(output_dir / "transactions_valides_nettoyees.csv", dtype_backend='pyarrow')

    # Attendu : CSV (1 valide, 1 invalide) + Excel (1 valide, 1 invalide) + PDF (2 valides) = 4 valides au total
    # Note: La validation PDF dépend de l'extraction réussie. Assumons qu'elle est réussie pour ce test.
    assert len(valid_df) >= 4 # Devrait avoir au moins 4 transactions valides (1 CSV + 1 Excel + 2 PDF)

    # Vérifier les fichiers en quarantaine (transactions invalides)
    assert (quarantine_dir / "invalid_transactions_transactions.csv").exists() # Invalides du CSV
    assert (quarantine_dir / "invalid_transactions_paiements.csv").exists() # Invalides de l'Excel
    # Pas de fichier invalide pour le PDF si toutes les transactions extraites sont valides

    # Charger les données invalides du CSV pour vérification
    invalid_csv_df = pd.read_csv(quarantine_dir / "invalid_transactions_transactions.csv", dtype_backend='pyarrow')
    assert len(invalid_csv_df) == 1 # La transaction à 15M est invalide
    assert 15000000.0 in invalid_csv_df['Montant'].values

    # Charger les données invalides de l'Excel pour vérification
    invalid_excel_df = pd.read_csv(quarantine_dir / "invalid_transactions_paiements.csv", dtype_backend='pyarrow')
    assert len(invalid_excel_df) == 1 # La transaction JPY est invalide
    assert 'JPY' in invalid_excel_df['Devise'].values

    # Vérifier le log des fichiers traités (mécanisme de recovery)
    processed_log_path = Path(processor.config['paths']['processed_files_log'])
    assert processed_log_path.exists()
    with open(processed_log_path, 'r') as f:
        processed_files = [line.strip() for line in f if line.strip()]

    # Vérifier que les fichiers source ont été marqués comme traités
    # Les chemins sont enregistrés en relatif par rapport à la racine du projet
    assert str(input_dir.relative_to(project_root) / "transactions.csv") in processed_files
    assert str(input_dir.relative_to(project_root) / "paiements.xlsx") in processed_files
    assert str(input_dir.relative_to(project_root) / "releve.pdf") in processed_files


# Test du mécanisme de recovery
def test_recovery_mechanism(processor, project_root):
    """Teste que le script ne retraire pas les fichiers déjà marqués comme traités."""
    input_dir = Path(processor.config['paths']['input_dir'])
    processed_log_path = Path(processor.config['paths']['processed_files_log'])

    # Créer un fichier test
    csv_content = "Montant,Devise\n100,XOF\n200,EUR"
    csv_file = input_dir / "recovery_test.csv"
    csv_file.write_text(csv_content, encoding='utf-8')

    # Marquer le fichier comme déjà traité manuellement
    relative_csv_path = str(csv_file.relative_to(project_root))
    with open(processed_log_path, 'a', encoding='utf-8') as f:
        f.write(relative_csv_path + '\n')

    # Re-initialiser le processeur pour qu'il charge le log de recovery
    processor_reloaded = DataProcessor(config_path=project_root / "config/temp_test_config.toml") # Utilise le même fichier de config de test temporaire

    # Vérifier que le fichier est bien marqué comme traité au chargement
    assert processor_reloaded._is_processed(csv_file) is True

    # Exécuter le pipeline. Ce fichier ne devrait PAS être traité.
    # On peut vérifier les logs ou simplement la sortie pour s'assurer qu'il est ignoré.
    # Le plus simple pour ce test est de vérifier que run_pipeline ne l'ajoute pas aux 'future_to_file'
    # dans une version mockée, ou de vérifier les logs INFO/DEBUG.
    # Pour un test d'intégration simple, on peut vérifier qu'aucun fichier de sortie lié à 'recovery_test.csv' n'est créé,
    # ou compter les fichiers traités si on modifie run_pipeline pour exposer cette info.

    # Modification simple pour le test : Ajouter un print ou un log spécifique dans _safe_process_file
    # ou vérifier les logs après l'exécution.
    # Pour l'instant, on se fie à _is_processed correctement implémenté.
    # Une meilleure approche de test serait de mocker les méthodes _process_X et vérifier qu'elles ne sont pas appelées.

    # Lance le pipeline. Si _is_processed fonctionne, run_pipeline devrait ignorer ce fichier.
    processor_reloaded.run_pipeline()

    # Vérifier les logs pour confirmer que le fichier a été sauté (nécessite de lire le fichier de log de test)
    log_file_path = Path(processor_reloaded.config['logging']['log_file'])
    logs = log_file_path.read_text(encoding='utf-8').splitlines()
    # Chercher un message indiquant que le fichier a été ignoré ou qu'aucun nouveau fichier n'a été trouvé si c'était le seul.
    # L'actuelle implémentation loggue "Aucun nouveau fichier à traiter" si aucun fichier non traité n'est trouvé.
    found_log = any("Aucun nouveau fichier à traiter" in log_entry for log_entry in logs)
    assert found_log # Si le fichier a été ignoré et qu'il n'y en avait pas d'autres non traités, ce message apparaît.


# --- Tests unitaires pour la validation (peut être dans tests/test_validation.py) ---
# On les inclut ici pour simplifier la démo, mais les séparer est une bonne pratique.

# Voir les tests test_validate_transaction_* ci-dessus.
# Coverage >= 90% doit être vérifié par la commande `pytest --cov=src`