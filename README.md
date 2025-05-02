# Bank Data Processor

Ce projet implémente un script Python pour automatiser le traitement de données bancaires (ingestion, nettoyage, validation, reporting). Il est conçu comme une démonstration des compétences en automatisation, traitement de données et développement logiciel Python de niveau "production".

## Auteur

Bovis ALOUKOU

## Architecture Technique

Le système suit une architecture modulaire basée sur une classe principale `DataProcessor`.

*   **Couche d'Ingestion** : Utilise des bibliothèques spécifiques pour lire différents formats :
    *   `pandas` avec `dtype_backend='pyarrow'` pour les performances et la gestion des types stricts.
    *   `pandas` avec `openpyxl` pour les fichiers Excel (.xlsx/.xls).
    *   `pdfplumber` pour l'extraction de données (tables) à partir de fichiers PDF structurés. *Note : Le traitement des PDF numérisés ou non structurés nécessiterait une couche d'OCR supplémentaire.*
*   **Couche de Nettoyage** : Le module `src.data_processor` inclut une méthode générique `_clean_data` pour :
    *   Supprimer les doublons.
    *   Nettoyer/normaliser les noms de colonnes.
    *   Convertir les types de données (ex: montant, date) en gérant différents formats.
    *   Masquer ou anonymiser les informations personnellement identifiables (PII) dans le DataFrame nettoyé avant d'être potentiellement stockées ou logguées.
*   **Moteur de Validation** : Le module `src.validation` contient la logique de validation métier (`validate_transaction`) appliquée à chaque transaction (ligne du DataFrame). Les règles de validation sont chargées depuis le fichier `config/config.toml`, permettant une configuration flexible (ex: montant maximal, devises autorisées, patterns basiques pour IBAN/BIC).
*   **Parallélisme** : L'exécution du pipeline (`run_pipeline`) utilise `concurrent.futures.ThreadPoolExecutor` pour traiter plusieurs fichiers d'entrée simultanément, améliorant les performances sur les machines multi-cœurs.
*   **Sécurité** :
    *   **Chiffrement** : Utilisation de `cryptography.fernet` (basé sur AES-256) pour chiffrer/déchiffrer des données sensibles si nécessaire (ex: avant de les stocker dans un fichier ou une base de données). La clé de chiffrement est générée et stockée localement dans un fichier (sécurisé localement pour la démo).
    *   **Masquage des PII** : Les données sensibles (IBAN, numéros de compte) sont masquées dans les DataFrames nettoyés et les logs pour réduire le risque de fuite d'informations.
*   **Journalisation (Logging)** : Le module `src.utils` configure un logger structuré utilisant `python-json-logger`. Les logs sont écrits à la console et dans un fichier au format JSON, facilitant l'analyse et l'intégration avec des outils de supervision (bien que la supervision temps réel ne soit pas implémentée dans cette version locale). Chaque événement important (début/fin de traitement, erreur, transaction invalide) est loggué avec des détails contextuels.
*   **Gestion des Erreurs et Recovery** : Les exceptions sont gérées au niveau du traitement de chaque fichier dans `_safe_process_file` pour éviter qu'une erreur dans un fichier n'arrête tout le pipeline. Un mécanisme simple de recovery est implémenté en enregistrant les chemins des fichiers traités dans un log (`data/processed_files.log`). Au redémarrage, le processeur lit ce log et ignore les fichiers déjà traités.
*   **Reporting** : Des fonctions (`generate_pdf_report`, `generate_excel_report`) sont fournies pour générer des rapports résumant les transactions valides dans des formats courants.

## Workflow de Développement

Ce projet utilise `poetry` pour la gestion des dépendances et plusieurs outils pour assurer la qualité du code.

1.  **Cloner le dépôt** :
    ```bash
    git clone <URL_DU_DEPOT>
    cd bank-data-processor
    ```
2.  **Installer Poetry** : Si vous n'avez pas Poetry, suivez les instructions officielles : [https://python-poetry.org/docs/](https://python-poetry.org/docs/)
3.  **Installer les dépendances** :
    ```bash
    make install # Installe les dépendances principales et de développement
    ```
4.  **Configurer les pre-commit hooks** (Optionnel mais recommandé) : Installe les hooks qui s'exécuteront avant chaque commit (formatage, linting, sécurité).
    ```bash
    poetry run pre-commit install
    ```
5.  **Exécuter les Tests Unitaires** :
    ```bash
    make test # Lance pytest et génère un rapport de couverture HTML dans htmlcov/
    ```
    Vise une couverture de code supérieure à 90% comme spécifié.
6.  **Exécuter le Linter et l'analyse de Sécurité** :
    ```bash
    make lint # Lance ruff (vérifie le style et les erreurs) et bandit (analyse de sécurité)
    ```
7.  **Formater le code** :
    ```bash
    make format # Lance ruff pour formater automatiquement le code
    ```

## Guide de Débogage

*   **Logging détaillé** : Modifiez le niveau de logging dans `config/config.toml` à `DEBUG`. Consultez les logs dans le fichier spécifié (`logs/processor.log` par défaut).
*   **Erreurs Pandas** : Si vous rencontrez des `SettingWithCopyWarning` ou des problèmes de manipulation de DataFrame, activez le mode strict pour les chaînes d'assignation en ajoutant ceci au début de votre script ou session de débogage :
    ```python
    import pandas as pd
    pd.options.mode.chained_assignment = 'raise' # Lève une exception au lieu d'un warning
    ```
*   **Fichiers source** : Vérifiez la structure et le contenu des fichiers d'entrée dans `data/input`. Assurez-vous qu'ils correspondent au format attendu par le script (colonnes présentes, formats de données, etc.).
*   **Fichiers traités** : Si le script semble ignorer des fichiers, vérifiez le contenu de `data/processed_files.log`. Supprimez la ligne correspondant au fichier si vous souhaitez le retraiter.

## Comment utiliser le script en local

1.  **Installer le projet** : Suivez les étapes du workflow de développement (`make install`).
2.  **Placer les fichiers d'entrée** : Copiez vos fichiers de données bancaires (CSV, Excel, PDF) dans le répertoire `data/input/`.
3.  **Vérifier/Ajuster la configuration** : Ouvrez `config/config.toml` et ajustez les règles de validation (`max_transaction_amount`, `allowed_currencies`) et les chemins si nécessaire (bien que les chemins par défaut devraient fonctionner si vous suivez l'arborescence).
4.  **Lancer le traitement** :
    ```bash
    make run
    ```
    Cela exécutera le script principal (`src/data_processor.py`). Vous verrez les logs dans la console et dans le fichier `logs/processor.log`.
5.  **Consulter les résultats** :
    *   Les transactions valides nettoyées et les rapports (PDF, Excel) se trouvent dans `data/output/`.
    *   Les transactions invalides (celles qui ont échoué à la validation) sont enregistrées dans `data/quarantine/`.
    *   Le log de traitement (`logs/processor.log`) contient l'historique détaillé de l'exécution.

## Types de Documents attendus

Le script est conçu pour traiter des fichiers contenant des données **structurées** de transactions bancaires. Il ne s'attend pas à des "types" de documents bancaires spécifiques comme des chèques ou des bordereaux de versement individuels (qui sont souvent des images ou des formats très variables), mais plutôt des **relevés de transactions** ou des **exports de systèmes bancaires**.

Pour que le script fonctionne correctement, les fichiers d'entrée (CSV, Excel, PDF avec tables) doivent contenir des données tabulaires avec des colonnes claires, incluant idéalement :

*   Une colonne pour le **Montant** (numérique).
*   Une colonne pour la **Devise** (code ISO 4217 comme XOF, EUR, USD).
*   Des colonnes pour l'**IBAN** de l'émetteur et/ou du bénéficiaire.
*   Une colonne pour le **BIC/SWIFT**.
*   Une colonne pour une **Date** de transaction.
*   Optionnellement, des colonnes pour la **Description**, le **Type de Transaction**, etc.

Le script s'attend à retrouver ces informations (ou une partie) pour pouvoir appliquer les règles de validation (`Montant`, `Devise`, `IBAN`, `BIC`). Si certaines colonnes sont manquantes, le script essaiera de s'adapter (via `pd.NA`), mais la validation sera moins complète.

**Exemple de structure de données attendue (pour CSV/Excel) :**

| Date       | Description           | Référence  | Montant    | Devise | IBAN_Emetteur              | IBAN_Beneficiaire              | BIC_SWIFT    |
| :--------- | :-------------------- | :--------- | :--------- | :----- | :------------------------- | :------------------------- | :----------- |
| 2023-01-15 | Virement Salaire      | SAL001     | 1250000.00 | XOF    | CI001XXXXXXXXXXXXXXXXXXXX  | FR76YYYYYYYYYYYYYYYYYYYYY  | ABCDEFGH     |
| 2023-01-16 | Paiement Fournisseur  | INV987     | -550000.00 | XOF    | CI001XXXXXXXXXXXXXXXXXXXX  | DE89ZZZZZZZZZZZZZZZZZZZZZ  | IJKLMNOP     |
| 2023-01-17 | Achat en ligne        | WEB-XYZ    | -150.50    | EUR    | CI001XXXXXXXXXXXXXXXXXXXX  | N/A                        | N/A          |
| 2023-01-18 | Remboursement Client  | REF456     | 75.20      | USD    | US98AAAAAAAAAAAAAAAAAAAAAA | CI001XXXXXXXXXXXXXXXXXXXX  | QRSTUVWX     |
| 2023-01-19 | Transaction suspecte  | SUSPICIOUS | 12000000.0 | XOF    | CI001XXXXXXXXXXXXXXXXXXXX  | BE68BBBBBBBBBBBBBBBBBBBBB  | YZABCDYZ     |

Le script tentera d'adapter les noms de colonnes s'ils contiennent des espaces ou des caractères spéciaux (ex: "IBAN Emetteur" deviendra "IBAN_Emetteur"). Cependant, plus la structure des fichiers d'entrée est cohérente, meilleur sera le résultat.

Pour les PDF, le script essaie de trouver et d'extraire les données tabulaires. Sa réussite dépend fortement de la façon dont le PDF est structuré (s'il contient de vraies tables lisibles par des logiciels).

Ce projet te fournira une excellente base pour démontrer tes compétences sur ton CV. Bonne chance pour ton stage chez Orabank !