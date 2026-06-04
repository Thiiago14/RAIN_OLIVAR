import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from src.utils.model_loader import load_model
from src.features.prediction_perdida import run_prediction_pipeline
from src.orquestador.olivar_agent import OlivarAgent
from src.config.models_config import DEFAULT_OLIVAR_MODEL
from src.utils.report_generator import generate_pdf_report


def main():

    # 1. MODELO
    model = load_model()

    # 2. PIPELINE DE PREDICCIÓN
    df = run_prediction_pipeline(
        model,
        input_path="data/input/test_olivar.csv",
        output_path="data/output/submission_olivar.csv"
    )

    # 3. LLM
    agent = OlivarAgent(model=DEFAULT_OLIVAR_MODEL)

    llm_results = []

    for _, row in df.iterrows():
        data = row.to_dict()
        data["pct_perdida_pred"] = row["pct_perdida_pred"]
        data["impacto_eur_ha_pred"] = row["impacto_eur_ha_pred"]

        result = agent.analyze(data)

        print("\n============================")
        print(f"Parcela: {row['parcel_id']}")
        print("============================")
        print(result)

        llm_results.append({"parcel_id": row["parcel_id"], "analysis": result})

    # 4. Generar PDF
    generate_pdf_report(df, llm_results=llm_results)
    print("Informe PDF generado.")

if __name__ == "__main__":
    main()
