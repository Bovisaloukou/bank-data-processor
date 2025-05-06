# API RESTful avec FastAPI
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import pandas as pd
from src.data_processor import DataProcessor

app = FastAPI(title="Bank Data Processor API")

OUTPUT_DIR = Path("data/output")

@app.post("/run-pipeline")
def run_pipeline(background_tasks: BackgroundTasks):
    def process():
        processor = DataProcessor()
        processor.run_pipeline()
    background_tasks.add_task(process)
    return {"status": "Traitement lancé en arrière-plan"}

@app.get("/transactions-valides")
def get_transactions_valides():
    path = OUTPUT_DIR / "transactions_valides_nettoyees.csv"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Aucune donnée disponible"})
    df = pd.read_csv(path)
    return df.to_dict(orient="records")

@app.get("/transactions-suspectes")
def get_transactions_suspectes():
    path = OUTPUT_DIR / "transactions_suspectes.csv"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Aucune donnée disponible"})
    df = pd.read_csv(path)
    return df.to_dict(orient="records")

@app.get("/categories")
def get_categories():
    path = OUTPUT_DIR / "transactions_valides_nettoyees.csv"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Aucune donnée disponible"})
    df = pd.read_csv(path)
    if 'Catégorie' not in df.columns:
        return []
    return df['Catégorie'].value_counts().to_dict()

@app.get("/rapport-pdf")
def download_pdf():
    path = OUTPUT_DIR / "rapport_transactions_valides.pdf"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Fichier PDF non trouvé"})
    return FileResponse(path, media_type="application/pdf", filename=path.name)

@app.get("/rapport-excel")
def download_excel():
    path = OUTPUT_DIR / "transactions_valides.xlsx"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Fichier Excel non trouvé"})
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=path.name)
