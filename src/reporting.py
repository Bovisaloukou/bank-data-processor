# src/reporting.py

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
import pandas as pd
from pathlib import Path

def generate_pdf_report(df: pd.DataFrame, output_path: Path):
    """
    Génère un rapport PDF simple à partir d'un DataFrame.
    
    Args:
        df (pd.DataFrame): Le DataFrame contenant les données à convertir en PDF
        output_path (Path): Chemin où sauvegarder le fichier PDF
    """
    # Conversion du DataFrame en liste de listes pour reportlab
    # Assurer que toutes les données sont des chaînes pour l'affichage dans PDF
    data = [df.columns.tolist()] + df.astype(str).values.tolist()

    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    # Style de tableau basique
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),  # Taille de police légèrement réduite pour plus de colonnes
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
    ])

    # Calculer la largeur des colonnes (simplement répartir l'espace)
    col_widths = [500 / len(df.columns)] * len(df.columns) if len(df.columns) > 0 else []

    table = Table(data, colWidths=col_widths)
    table.setStyle(style)

    elements = [table]
    doc.build(elements)

def generate_excel_report(df: pd.DataFrame, output_path: Path):
    """
    Génère un rapport Excel à partir d'un DataFrame.
    
    Args:
        df (pd.DataFrame): Le DataFrame à exporter en Excel
        output_path (Path): Chemin où sauvegarder le fichier Excel
    """
    df.to_excel(output_path, index=False)