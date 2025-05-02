# Makefile pour le projet de traitement de données bancaires

.PHONY: install test lint format run clean help

# Variables
PYTHON = poetry run python
PYTEST = poetry run pytest
RUFF_CHECK = poetry run ruff check . --diff
RUFF_FORMAT = poetry run ruff format . --diff
BANDIT = poetry run bandit -r src

help:
	@echo "Commandes disponibles :"
	@echo "  install    Installe les dépendances avec poetry."
	@echo "  test       Exécute les tests unitaires et la couverture de code."
	@echo "  lint       Vérifie le code avec ruff et bandit."
	@echo "  format     Formate le code avec ruff."
	@echo "  run        Lance le script principal de traitement."
	@echo "  clean      Nettoie les fichiers temporaires et caches."

install:
	@echo "Installation des dépendances..."
	@poetry install --with dev
	@poetry sync

test: install
	@echo "Exécution des tests unitaires et calcul de la couverture..."
	@$(PYTEST) tests/ -v --cov=src --cov-report=html --cov-report=term

lint: install
	@echo "Exécution du linter (ruff) et de l'analyse de sécurité (bandit)..."
	@$(RUFF_CHECK)
	@$(BANDIT)

format: install
	@echo "Formatage du code avec ruff..."
	@$(RUFF_FORMAT)

run: install
	@echo "Lancement du script de traitement..."
	@$(PYTHON) src/data_processor.py

clean:
	@echo "Nettoyage des fichiers temporaires et caches..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name ".pytest_cache" -delete
	@rm -rf .coverage htmlcov/
	@rm -f .encryption_key
	@rm -rf data/output/* data/quarantine/* # Nettoie aussi les sorties précédentes