import pandas as pd


def run_prediction_pipeline(model, input_path: str, output_path: str):
    # 1. CARGAR DATA
    df = pd.read_csv(input_path, sep=";")

    # 2. PREDECIR
    X = df.copy()

    y_pred = model.predict(X)

    df["pct_perdida_pred"] = y_pred.clip(0, 1)

    # 3. IMPACTO ECONÓMICO
    df["impacto_eur_ha_pred"] = (
        df["rendimiento_esperado_kg_ha"]
        * df["pct_perdida_pred"]
        * df["precio_mercado_eur_kg"]
    )

    # 4. CREAR SUBMISSION
    submission = df[[
        "parcel_id",
        "pct_perdida_pred",
        "impacto_eur_ha_pred"
    ]].copy()

    submission["pct_perdida_pred"] = submission["pct_perdida_pred"].round(4)
    submission["impacto_eur_ha_pred"] = submission["impacto_eur_ha_pred"].round(2)

    submission = submission.sort_values("impacto_eur_ha_pred", ascending=False)

    submission.to_csv(output_path, index=False)

    print("CSV generado")

    return df  