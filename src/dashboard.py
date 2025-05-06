# Dashboard interactif avec Streamlit
import streamlit as st
import pandas as pd
from pathlib import Path

def charger_csv(path):
    if Path(path).exists():
        return pd.read_csv(path)
    return pd.DataFrame()

def main():
    st.title("Bank Data Processor – Dashboard")
    output_dir = Path("data/output")
    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Section", ["Transactions valides", "Transactions suspectes", "Catégories", "Rapports"])

    valid_path = output_dir / "transactions_valides_nettoyees.csv"
    suspects_path = output_dir / "transactions_suspectes.csv"
    valid_df = charger_csv(valid_path)
    suspects_df = charger_csv(suspects_path)

    if page == "Transactions valides":
        st.header("Transactions valides")
        st.dataframe(valid_df)
        st.write(f"Total : {len(valid_df)} transactions")
    elif page == "Transactions suspectes":
        st.header("Transactions suspectes (anomalies)")
        st.dataframe(suspects_df)
        st.write(f"Total : {len(suspects_df)} transactions suspectes")
    elif page == "Catégories":
        st.header("Répartition par catégorie")
        if not valid_df.empty and 'Catégorie' in valid_df.columns:
            st.bar_chart(valid_df['Catégorie'].value_counts())
            st.dataframe(valid_df.groupby('Catégorie').agg({'Montant': ['sum', 'mean', 'count']}))
        else:
            st.info("Aucune donnée de catégorie disponible.")
    elif page == "Rapports":
        st.header("Rapports générés")
        pdf_path = output_dir / "rapport_transactions_valides.pdf"
        excel_path = output_dir / "transactions_valides.xlsx"
        if pdf_path.exists():
            st.write(f"[Télécharger le rapport PDF]({pdf_path})")
        if excel_path.exists():
            st.write(f"[Télécharger le rapport Excel]({excel_path})")

if __name__ == "__main__":
    main()
