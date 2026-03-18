from dotenv import load_dotenv
load_dotenv()

import os
print(os.getenv("OPENAI_API_KEY"))

import pandas as pd


from src.utils.report_generator import generate_pdf_report
from src.orquestador.olivar_agent import OlivarAgent
from src.config.models_config import DEFAULT_OLIVAR_MODEL
from src.utils.data_loader import load_json


def main():
    df = pd.read_csv("data/output/submission_olivar.csv")
    df_full = pd.read_csv("data/input/test_olivar.csv", sep=";")

    # Merge para tener TODAS las variables
    df = df.merge(df_full, on="parcel_id")

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

    generate_pdf_report(df, llm_results=llm_results)
    print("Informe PDF generado.")

if __name__ == "__main__":
    main()