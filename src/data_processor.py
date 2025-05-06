# src/data_processor.py

import pandas as pd
import pdfplumber
import json
import concurrent.futures
import tomlkit
from pathlib import Path
import logging
import base64
from typing import Dict, Any, List, Tuple
import pytesseract
from PIL import Image
import tempfile

# Importer les utilitaires et la logique de validation
from src.utils import setup_structured_logging, generate_encryption_key, encrypt_data, decrypt_data, mask_sensitive_data
from src.validation import load_validation_rules, validate_transaction
from src.reporting import generate_pdf_report, generate_excel_report
from src.categorization import categoriser_transaction, CATEGORIES_PAR_DEFAUT
from src.fraud_detection import detect_anomalies
from src.notifications import send_email_notification, send_slack_notification

class DataProcessor:
    """
    Coeur du système de traitement de données bancaires.
    Gère l'ingestion, le nettoyage, la validation et le reporting.
    """
    def __init__(self, config_path: str = 'config/config.toml'):
        """
        Initialise le processeur de données.

        Args:
            config_path (str): Chemin vers le fichier de configuration TOML.
        """
        self.config = self._load_config(config_path)
        self.logger = self._setup_structured_logging()
        self.validation_rules = load_validation_rules(self.config)
        self.encryption_key = generate_encryption_key(Path(self.config['paths']['encryption_key_file']))
        self.processed_files_log_path = Path(self.config['paths']['processed_files_log'])
        self.project_root = Path(config_path).parent.parent  # Remonter de deux niveaux depuis config/config.toml
        self._load_processed_files() # Charge l'état pour le recovery

        # Créer les répertoires de sortie/quarantaine si nécessaire
        Path(self.config['paths']['output_dir']).mkdir(parents=True, exist_ok=True)
        Path(self.config['paths']['quarantine_dir']).mkdir(parents=True, exist_ok=True)
        Path(self.config['logging']['log_file']).parent.mkdir(parents=True, exist_ok=True)


    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Charge la configuration depuis un fichier TOML."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return tomlkit.load(f)
        except FileNotFoundError:
            self.logger.error(f"Fichier de configuration non trouvé : {config_path}", extra={"event": "config_load_failed"})
            raise # Lever l'exception pour arrêter l'initialisation

    def _setup_structured_logging(self) -> logging.Logger:
        """Configure le logger structuré."""
        log_level = self.config['logging'].get('level', 'INFO').upper()
        log_file = self.config['logging'].get('log_file', 'logs/processor.log')
        return setup_structured_logging(__name__, log_level, log_file)

    def _load_processed_files(self):
        """Charge la liste des fichiers déjà traités pour le mécanisme de recovery."""
        self.processed_files: List[str] = []
        if self.processed_files_log_path.exists():
            try:
                with open(self.processed_files_log_path, 'r', encoding='utf-8') as f:
                    # Chaque ligne est le chemin d'un fichier traité
                    self.processed_files = [line.strip() for line in f if line.strip()]
            except Exception as e:
                 self.logger.error(f"Erreur lors du chargement du log des fichiers traités : {e}", extra={"event": "recovery_log_load_failed"})


    def _save_processed_file(self, file_path: Path):
        """Enregistre un fichier comme étant traité."""
        try:
            # Calculer le chemin relatif par rapport à la racine du projet
            relative_path = str(file_path.relative_to(self.project_root))
            if relative_path not in self.processed_files:
                self.processed_files.append(relative_path)
                with open(self.processed_files_log_path, 'a', encoding='utf-8') as f:
                    f.write(relative_path + '\n')
        except Exception as e:
            self.logger.error(f"Erreur lors de l'écriture dans le log des fichiers traités : {e}", 
                            extra={"event": "recovery_log_write_failed"})

    def _is_processed(self, file_path: Path) -> bool:
        """Vérifie si un fichier a déjà été traité."""
        try:
            relative_path = str(file_path.relative_to(self.project_root))
            return relative_path in self.processed_files
        except ValueError:
            self.logger.error(f"Impossible de calculer le chemin relatif pour {file_path}", 
                            extra={"event": "relative_path_calculation_failed"})
            return False

    def encrypt_data(self, data: str) -> str:
        """Chiffre une chaîne de caractères (utilise la clé interne)."""
        return encrypt_data(data, self.encryption_key)

    def decrypt_data(self, encrypted_data: str) -> str:
        """Déchiffre une chaîne de caractères (utilise la clé interne)."""
        return decrypt_data(encrypted_data, self.encryption_key)

    def _process_csv(self, file_path: Path) -> pd.DataFrame:
        """
        Charge, nettoie et valide les données d'un fichier CSV.

        Args:
            file_path (Path): Chemin vers le fichier CSV.

        Returns:
            pd.DataFrame: DataFrame nettoyé et potentiellement validé.
        """
        self.logger.info(f"Traitement du fichier CSV : {file_path}", extra={"event": "file_processing", "file": str(file_path)})
        try:
            # Lecture simple sans spécifier de backend
            df = pd.read_csv(file_path)

            # Application des étapes de nettoyage et de validation
            df = self._clean_data(df)
            # La validation est appliquée plus tard sur le DataFrame consolidé ou par transaction

            self.logger.info(f"Fichier CSV traité : {file_path}", extra={"event": "file_processed_success", "file": str(file_path), "rows": len(df)})
            return df
        except FileNotFoundError:
            self.logger.error(f"Fichier CSV non trouvé : {file_path}", extra={"event": "file_not_found", "file": str(file_path)})
            raise # Relève l'exception pour que le pipeline puisse la gérer
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du CSV {file_path}: {e}", extra={"event": "file_processing_failed", "file": str(file_path), "error": str(e)})
            raise # Relève l'exception

    def _process_excel(self, file_path: Path) -> pd.DataFrame:
        """
        Charge, nettoie et valide les données d'un fichier Excel.

        Args:
            file_path (Path): Chemin vers le fichier Excel.

        Returns:
            pd.DataFrame: DataFrame nettoyé et potentiellement validé.
        """
        self.logger.info(f"Traitement du fichier Excel : {file_path}", extra={"event": "file_processing", "file": str(file_path)})
        try:
            # Utiliser l'engine openpyxl pour lire les fichiers .xlsx sans spécifier de backend
            df = pd.read_excel(file_path, engine='openpyxl')

            # Application des étapes de nettoyage et de validation
            df = self._clean_data(df)
             # La validation est appliquée plus tard

            self.logger.info(f"Fichier Excel traité : {file_path}", extra={"event": "file_processed_success", "file": str(file_path), "rows": len(df)})
            return df
        except FileNotFoundError:
            self.logger.error(f"Fichier Excel non trouvé : {file_path}", extra={"event": "file_not_found", "file": str(file_path)})
            raise
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'Excel {file_path}: {e}", extra={"event": "file_processing_failed", "file": str(file_path), "error": str(e)})
            raise

    def _process_pdf(self, file_path: Path) -> pd.DataFrame:
        """
        Extrait les données des relevés PDF.
        NOTE : L'extraction PDF peut être complexe et nécessiter des ajustements
        selon le format exact des PDF. pdfplumber est excellent pour les tables structurées.

        Args:
            file_path (Path): Chemin vers le fichier PDF.

        Returns:
            pd.DataFrame: DataFrame contenant les données extraites.
        """
        self.logger.info(f"Traitement du fichier PDF : {file_path}", extra={"event": "file_processing", "file": str(file_path)})
        all_data: List[pd.DataFrame] = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    # Détecter les tables sur chaque page
                    # table_settings={} peut être ajusté pour une détection plus fine
                    tables = page.extract_tables()
                    for table_num, table in enumerate(tables):
                        # Convertir la table extraite en DataFrame
                        # Assurez-vous que la première ligne est l'en-tête
                        if table:
                             # Convertir la liste de listes en DataFrame
                             # La première liste est l'en-tête
                            df = pd.DataFrame(table[1:], columns=table[0])
                            all_data.append(df)
                            self.logger.debug(f"Table {table_num} extraite de la page {page_num} du PDF {file_path}", extra={"event": "pdf_table_extracted", "file": str(file_path), "page": page_num, "table": table_num, "rows": len(df)})

            if not all_data:
                self.logger.warning(f"Aucune table trouvée dans le PDF : {file_path}. Tentative d'extraction OCR...", extra={"event": "pdf_no_table_ocr", "file": str(file_path)})
                # --- Extraction OCR ---
                ocr_rows = []
                with pdfplumber.open(file_path) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        with tempfile.NamedTemporaryFile(suffix='.png') as tmp_img:
                            page_image = page.to_image(resolution=300)
                            page_image.save(tmp_img.name, format='PNG')
                            text = pytesseract.image_to_string(Image.open(tmp_img.name), lang='fra+eng')
                            # Découper le texte en lignes, filtrer les lignes qui ressemblent à des transactions
                            for line in text.splitlines():
                                # Heuristique simple : ligne contenant un montant et une devise
                                if any(dev in line for dev in ['XOF', 'EUR', 'USD']) and any(char.isdigit() for char in line):
                                    ocr_rows.append(line)
                # Tenter de parser les lignes OCR en colonnes (à adapter selon le format réel)
                if ocr_rows:
                    df_ocr = pd.DataFrame({'Ligne_OCR': ocr_rows})
                    self.logger.info(f"{len(df_ocr)} lignes extraites par OCR du PDF {file_path}", extra={"event": "pdf_ocr_extracted", "file": str(file_path), "ocr_rows": len(df_ocr)})
                    return df_ocr
                else:
                    self.logger.warning(f"OCR n'a extrait aucune ligne exploitable du PDF : {file_path}", extra={"event": "pdf_ocr_no_data", "file": str(file_path)})
                    return pd.DataFrame()
                # --- Fin extraction OCR ---

            # Concaténer toutes les tables extraites
            # Gérer les colonnes potentiellement différentes ou manquantes entre tables/pages
            combined_df = pd.concat(all_data, ignore_index=True)

            # Application des étapes de nettoyage (formatage des types, etc.)
            # Note : Le nettoyage PDF peut nécessiter plus de travail pour convertir
            # les chaînes extraites en types numériques, dates, etc.
            combined_df = self._clean_data(combined_df)

            self.logger.info(f"Fichier PDF traité : {file_path}", extra={"event": "file_processed_success", "file": str(file_path), "rows": len(combined_df)})
            return combined_df

        except FileNotFoundError:
            self.logger.error(f"Fichier PDF non trouvé : {file_path}", extra={"event": "file_not_found", "file": str(file_path)})
            raise
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du PDF {file_path}: {e}", extra={"event": "file_processing_failed", "file": str(file_path), "error": str(e)})
            raise

    # NOTE: Pour les "Images scannées", cela nécessiterait une étape d'OCR (Optical Character Recognition)
    # utilisant des bibliothèques comme Tesseract (via pytesseract) ou des services cloud.
    # C'est une complexité supplémentaire qui sort du cadre de ce script de démo initial
    # si l'objectif est de rester simple et local. On va ignorer cette partie pour l'instant.

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applique les règles de nettoyage génériques au DataFrame.

        Args:
            df (pd.DataFrame): DataFrame brut.

        Returns:
            pd.DataFrame: DataFrame nettoyé.
        """
        self.logger.debug("Application du nettoyage des données...", extra={"event": "data_cleaning_start"})
        
        # 1. Suppression des doublons (basé sur toutes les colonnes pour la simplicité)
        initial_rows = len(df)
        df.drop_duplicates(inplace=True)
        if len(df) < initial_rows:
            self.logger.debug(f"Supprimé {initial_rows - len(df)} doublons.", extra={"event": "duplicate_removal", "removed_rows": initial_rows - len(df)})

        # 2. Nettoyage basique des noms de colonnes (espaces, caractères spéciaux...)
        df.columns = df.columns.str.strip().str.replace('[^A-Za-z0-9_]+', '_', regex=True)

        # 3. Nettoyage des espaces pour toutes les colonnes de type string
        for col in df.columns:
            if df[col].dtype == 'object':  # Pour les colonnes de type string/object
                df[col] = df[col].astype(str).str.strip()

        # 4. Nettoyage et conversion des types (ex: montant, date)
        if 'Montant' in df.columns:
             df['Montant'] = df['Montant'].astype(str).str.replace(',', '.', regex=False).str.strip()
             df['Montant'] = pd.to_numeric(df['Montant'], errors='coerce')

        if 'Date' in df.columns:
             df['Date'] = pd.to_datetime(df['Date'], errors='coerce', format='mixed')

        # Ne pas masquer les données sensibles ici, cela sera fait après la validation
        # pour ne pas interférer avec les vérifications d'IBAN et BIC

        self.logger.debug("Nettoyage des données terminé.", extra={"event": "data_cleaning_end"})
        return df

    def _validate_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Valide chaque transaction (ligne) du DataFrame.

        Args:
            df (pd.DataFrame): DataFrame nettoyé.

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: Deux DataFrames, (transactions_valides, transactions_invalides).
        """
        self.logger.info(f"Début de la validation des {len(df)} transactions...", 
                        extra={"event": "validation_start", "total_transactions": len(df)})

        if df.empty:
            self.logger.warning("DataFrame vide pour la validation.", 
                              extra={"event": "validation_skipped_empty"})
            return pd.DataFrame(), pd.DataFrame()

        # On crée une nouvelle colonne 'is_valid'
        expected_cols = ['Montant', 'Devise', 'IBAN_Emetteur', 'IBAN_Beneficiaire', 'BIC_SWIFT']
        for col in expected_cols:
            if col not in df.columns:
                df[col] = pd.NA

        # Applique la validation avant le masquage
        validity_results: List[bool] = []
        for index, row in df.iterrows():
            try:
                is_valid = validate_transaction(row, self.validation_rules)
                validity_results.append(is_valid)
                if not is_valid:
                    # Masquer les données sensibles uniquement pour le logging
                    masked_row_info = {k: mask_sensitive_data(str(v)) for k, v in row.items() if k in expected_cols}
                    self.logger.warning(f"Transaction invalide détectée.", 
                                      extra={"event": "transaction_invalid", 
                                            "transaction_index": index, 
                                            "masked_data": masked_row_info})
            except Exception as e:
                self.logger.error(f"Erreur lors de la validation de la transaction à l'index {index}: {e}", 
                                extra={"event": "validation_error", 
                                      "transaction_index": index, 
                                      "error": str(e)})
                validity_results.append(False)

        df['is_valid'] = validity_results

        # Séparer les transactions valides et invalides
        valid_df = df[df['is_valid']].copy()
        invalid_df = df[~df['is_valid']].copy()

        # Supprimer la colonne de validation
        valid_df.drop(columns=['is_valid'], inplace=True)
        invalid_df.drop(columns=['is_valid'], inplace=True)

        # Masquer les données sensibles après la validation
        sensitive_cols = ['IBAN_Emetteur', 'IBAN_Beneficiaire']
        for col in sensitive_cols:
            if col in valid_df.columns:
                valid_df[col] = valid_df[col].apply(lambda x: mask_sensitive_data(str(x)))
            if col in invalid_df.columns:
                invalid_df[col] = invalid_df[col].apply(lambda x: mask_sensitive_data(str(x)))

        self.logger.info(f"Validation terminée. Valides : {len(valid_df)}, Invalides : {len(invalid_df)}", 
                        extra={"event": "validation_end", 
                              "valid_transactions": len(valid_df), 
                              "invalid_transactions": len(invalid_df)})

        return valid_df, invalid_df

    def run_pipeline(self):
        """
        Exécute le pipeline complet de traitement des données.
        Scan le répertoire d'entrée, traite les fichiers en parallèle,
        nettoie, valide, génère des rapports.
        """
        input_dir = Path(self.config['paths']['input_dir'])
        output_dir = Path(self.config['paths']['output_dir'])
        quarantine_dir = Path(self.config['paths']['quarantine_dir'])
        parallel_workers = self.config['processing'].get('parallel_workers', 4)

        self.logger.info(f"Début du pipeline de traitement des données. Répertoire d'entrée : {input_dir}", extra={"event": "pipeline_start", "input_dir": str(input_dir)})

        # Trouver les fichiers à traiter (exclure les fichiers déjà traités si recovery actif)
        files_to_process = [
            f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() in ['.csv', '.xlsx', '.xls', '.pdf'] # Types de fichiers gérés
            and not self._is_processed(f) # Vérifier si déjà traité
        ]

        if not files_to_process:
            self.logger.info("Aucun nouveau fichier à traiter.", extra={"event": "pipeline_no_new_files"})
            return

        all_valid_transactions: List[pd.DataFrame] = []
        all_invalid_transactions: List[pd.DataFrame] = []

        notification_cfg = self.config.get('notifications', {})
        notify_email = notification_cfg.get('email_enabled', False)
        notify_slack = notification_cfg.get('slack_enabled', False)
        email_params = notification_cfg.get('email', {})
        slack_webhook = notification_cfg.get('slack_webhook', None)

        # Utiliser concurrent.futures pour le parallélisme
        # ProcessPoolExecutor si le traitement est intensif en CPU (comme l'extraction PDF)
        # ThreadPoolExecutor si le traitement est intensif en I/O (lecture de fichier)
        # On utilise ThreadPoolExecutor ici car la lecture/parsing est le goulot,
        # mais ProcessPoolExecutor pourrait être mieux pour l'extraction PDF intensive.
        # Pour la démo, ThreadPoolExecutor est plus simple car pas de problèmes de pickling.
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            # Soumettre les tâches de traitement de fichier
            future_to_file = {executor.submit(self._safe_process_file, file_path): file_path for file_path in files_to_process}

            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    if result:
                        # result est un tuple (DataFrame nettoyé, chemin du fichier)
                        cleaned_df, processed_file_path = result
                        self.logger.info(f"Fichier traité avec succès : {processed_file_path}. Début validation...", extra={"event": "file_processed_successfully", "file": str(processed_file_path), "rows_before_validation": len(cleaned_df)})

                        # Appliquer la validation
                        valid_df, invalid_df = self._validate_data(cleaned_df)

                        # --- Catégorisation automatique ---
                        if not valid_df.empty:
                            # Appliquer la catégorisation sur chaque ligne
                            if 'Description' in valid_df.columns:
                                valid_df['Catégorie'] = valid_df.apply(
                                    lambda row: categoriser_transaction(row.get('Description', ''), row.get('Montant', 0.0)), axis=1
                                )
                            else:
                                valid_df['Catégorie'] = 'autre'
                            all_valid_transactions.append(valid_df)
                            self.logger.info(f"{len(valid_df)} transactions valides extraites de {processed_file_path}", extra={"event": "valid_transactions_collected", "file": str(processed_file_path), "valid_count": len(valid_df)})
                        # --- fin catégorisation ---

                        if not invalid_df.empty:
                            all_invalid_transactions.append(invalid_df)
                            self.logger.warning(f"{len(invalid_df)} transactions invalides extraites de {processed_file_path}", extra={"event": "invalid_transactions_collected", "file": str(processed_file_path), "invalid_count": len(invalid_df)})
                            # Optionnel: Sauvegarder les transactions invalides immédiatement
                            invalid_output_path = quarantine_dir / f"invalid_transactions_{processed_file_path.stem}.csv"
                            invalid_df.to_csv(invalid_output_path, index=False)
                            self.logger.info(f"Transactions invalides sauvegardées dans {invalid_output_path}", extra={"event": "invalid_transactions_saved", "file": str(invalid_output_path)})

                        # Enregistrer le fichier comme traité SEULEMENT si le traitement du fichier lui-même a réussi
                        self._save_processed_file(file_path)


                except Exception as e:
                    self.logger.error(f"Échec critique lors du traitement ou de la validation du fichier {file_path}: {e}", extra={"event": "pipeline_file_critical_failure", "file": str(file_path), "error": str(e)})
                    # Optionnel : Déplacer le fichier source en quarantaine si le traitement échoue ?
                    # quarantine_file_path = quarantine_dir / file_path.name
                    # try:
                    #     file_path.rename(quarantine_file_path)
                    #     self.logger.info(f"Fichier source déplacé en quarantaine : {file_path} -> {quarantine_file_path}", extra={"event": "source_file_quarantined", "file": str(file_path), "quarantine_file": str(quarantine_file_path)})
                    # except Exception as move_e:
                    #      self.logger.error(f"Erreur lors du déplacement du fichier {file_path} en quarantaine : {move_e}", extra={"event": "quarantine_move_failed", "file": str(file_path), "error": str(move_e)})


        # Concaténer toutes les transactions valides collectées
        final_valid_df = pd.concat(all_valid_transactions, ignore_index=True) if all_valid_transactions else pd.DataFrame()

        self.logger.info(f"Total de transactions valides collectées : {len(final_valid_df)}", extra={"event": "total_valid_collected", "count": len(final_valid_df)})


        # Génération des rapports finaux si des données valides existent
        try:
            if not final_valid_df.empty:
                # --- Détection de fraudes/anomalies ---
                suspects_df = detect_anomalies(final_valid_df)
                if not suspects_df.empty:
                    suspects_path = output_dir / "transactions_suspectes.csv"
                    suspects_df.to_csv(suspects_path, index=False)
                    self.logger.warning(f"{len(suspects_df)} transactions suspectes détectées (anomalies montants). Export : {suspects_path}", extra={"event": "fraud_anomaly_detected", "count": len(suspects_df), "file": str(suspects_path)})
                    if not suspects_df.empty and notify_email:
                        send_email_notification(
                            subject="Alerte : Transactions suspectes détectées",
                            body=f"{len(suspects_df)} transactions suspectes détectées. Voir {suspects_path}",
                            to_email=email_params.get('to'),
                            smtp_server=email_params.get('smtp_server'),
                            smtp_port=email_params.get('smtp_port'),
                            smtp_user=email_params.get('smtp_user'),
                            smtp_password=email_params.get('smtp_password')
                        )
                    if not suspects_df.empty and notify_slack and slack_webhook:
                        send_slack_notification(slack_webhook, f"Alerte : {len(suspects_df)} transactions suspectes détectées.")
                # --- fin détection fraudes ---
                self.logger.info("Génération des rapports finaux...", extra={"event": "report_generation_start"})
                try:
                    pdf_report_path = output_dir / "rapport_transactions_valides.pdf"
                    generate_pdf_report(final_valid_df, pdf_report_path)
                    self.logger.info(f"Rapport PDF généré : {pdf_report_path}", extra={"event": "report_generated", "format": "PDF", "path": str(pdf_report_path)})

                    excel_report_path = output_dir / "transactions_valides.xlsx"
                    generate_excel_report(final_valid_df, excel_report_path)
                    self.logger.info(f"Rapport Excel généré : {excel_report_path}", extra={"event": "report_generated", "format": "Excel", "path": str(excel_report_path)})

                    # Sauvegarder les données valides nettoyées dans un fichier standardisé
                    cleaned_data_path = output_dir / "transactions_valides_nettoyees.csv"
                    # Optionnel : chiffrer ce fichier s'il contient des PII non masquées
                    # Pour la démo, on va masquer les PII dans le DF nettoyé.
                    final_valid_df.to_csv(cleaned_data_path, index=False)
                    self.logger.info(f"Données valides nettoyées sauvegardées : {cleaned_data_path}", extra={"event": "cleaned_data_saved", "path": str(cleaned_data_path)})


                except Exception as e:
                    self.logger.error(f"Erreur lors de la génération des rapports : {e}", extra={"event": "report_generation_failed", "error": str(e)})
                if notify_email:
                    send_email_notification(
                        subject="Traitement terminé",
                        body=f"Le pipeline Bank Data Processor est terminé. {len(final_valid_df)} transactions valides.",
                        to_email=email_params.get('to'),
                        smtp_server=email_params.get('smtp_server'),
                        smtp_port=email_params.get('smtp_port'),
                        smtp_user=email_params.get('smtp_user'),
                        smtp_password=email_params.get('smtp_password')
                    )
                if notify_slack and slack_webhook:
                    send_slack_notification(slack_webhook, f"Pipeline terminé. {len(final_valid_df)} transactions valides.")
            else:
                self.logger.warning("Aucune transaction valide à rapporter.", extra={"event": "no_valid_transactions_for_report"})

        except Exception as e:
            self.logger.error(f"Erreur critique lors du traitement : {e}", extra={"event": "pipeline_critical_failure", "error": str(e)})
            if notify_email:
                send_email_notification(
                    subject="Erreur critique Bank Data Processor",
                    body=f"Erreur critique lors du traitement : {e}",
                    to_email=email_params.get('to'),
                    smtp_server=email_params.get('smtp_server'),
                    smtp_port=email_params.get('smtp_port'),
                    smtp_user=email_params.get('smtp_user'),
                    smtp_password=email_params.get('smtp_password')
                )
            if notify_slack and slack_webhook:
                send_slack_notification(slack_webhook, f"Erreur critique lors du traitement : {e}")
            raise

        self.logger.info("Pipeline de traitement des données terminé.", extra={"event": "pipeline_end"})

    def _safe_process_file(self, file_path: Path) -> Tuple[pd.DataFrame, Path] | None:
        """
        Traite un seul fichier source, gère les erreurs au niveau du fichier.

        Args:
            file_path (Path): Chemin vers le fichier à traiter.

        Returns:
            Tuple[pd.DataFrame, Path] | None: Le DataFrame nettoyé et le chemin du fichier si succès,
                                           None si échec.
        """
        try:
            suffix = file_path.suffix.lower()
            df: pd.DataFrame | None = None

            if suffix == '.csv':
                df = self._process_csv(file_path)
            elif suffix in ['.xlsx', '.xls']:
                df = self._process_excel(file_path)
            elif suffix == '.pdf':
                df = self._process_pdf(file_path)
            else:
                self.logger.warning(f"Type de fichier non supporté : {file_path}", extra={"event": "unsupported_file_type", "file": str(file_path)})
                return None # Ne pas traiter ce fichier

            if df is not None:
                 # Le nettoyage (_clean_data) est déjà appelé dans les méthodes _process_X
                 return df, file_path
            else:
                 self.logger.error(f"Le traitement du fichier {file_path} a retourné None.", extra={"event": "file_processing_returned_none", "file": str(file_path)})
                 return None


        except Exception as e:
            # Attrape toute erreur survenant pendant le traitement d'un fichier spécifique
            self.logger.error(f"Erreur lors du traitement du fichier {file_path}: {e}", extra={"event": "file_processing_failure", "file": str(file_path), "error": str(e)})
            return None # Indiquer l'échec pour ce fichier


# --- Bloc d'exécution principal ---

if __name__ == "__main__":
    # Charger la configuration et initialiser le processeur
    # Le chemin de config est par défaut 'config/config.toml'
    # Le logger est initialisé dans __init__
    processor = DataProcessor()
    processor.run_pipeline()