# Module simple de détection de fraudes/anomalies
import pandas as pd
import numpy as np

def detect_anomalies(df: pd.DataFrame, montant_col: str = 'Montant', seuil_zscore: float = 3.0) -> pd.DataFrame:
    """
    Détecte les transactions anormales par z-score sur le montant.
    Retourne un DataFrame des transactions suspectes.
    """
    if montant_col not in df.columns or df[montant_col].isnull().all():
        return pd.DataFrame()
    df = df.copy()
    df['zscore'] = (df[montant_col] - df[montant_col].mean()) / df[montant_col].std(ddof=0)
    suspects = df[df['zscore'].abs() > seuil_zscore]
    return suspects.drop(columns=['zscore'])
