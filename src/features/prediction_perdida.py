"""
Predicción de pérdida de producción en olivar usando modelo ML entrenado.

Genera:
- pct_perdida_pred: Porcentaje de pérdida estimado [0-1]
- impacto_eur_ha_pred: Impacto económico por hectárea
- impacto_total_eur: Impacto total (impacto_eur_ha * superficie_ha)
- nivel_riesgo: Clasificación por nivel de riesgo
"""
import os
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
import numpy as np

PREDICTIONS_DIR = "data/predictions"

# Clasificación de riesgo
RISK_LEVELS = {
    "bajo": (0.0, 0.05),
    "medio": (0.05, 0.15),
    "alto": (0.15, 0.30),
    "muy_alto": (0.30, 1.0),
}


def load_model(model_path: str):
    """Carga modelo ML usando joblib (como fue guardado)."""
    try:
        model_path = Path(model_path).resolve()
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        return joblib.load(model_path)
    except FileNotFoundError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to load model: {str(e)}")


def classify_risk(pct_perdida: float) -> str:
    """Clasifica nivel de riesgo por porcentaje de pérdida."""
    for nivel, (min_val, max_val) in RISK_LEVELS.items():
        if min_val <= pct_perdida < max_val:
            return nivel
    return "muy_alto"


def run_prediction(
    input_df: pd.DataFrame,
    client_id: str,
    model_path: str = "data/output/modelo_olivar.pkl",
    parcel_uid_col: str = None,
) -> pd.DataFrame:
    """
    Ejecuta predicción ML en un CSV ML-ready.

    Args:
        input_df: DataFrame con 22 columnas modelo (ya validado)
        client_id: Identificador del cliente
        model_path: Ruta al modelo pickle
        parcel_uid_col: Nombre de columna parcel_uid si existe (opcional)

    Retorna:
        DataFrame con predicciones
        Guarda en data/predictions/{client_id}_predictions.csv
    """
    now = datetime.now().isoformat(timespec="seconds")

    # Cargar modelo con logging detallado
    try:
        model_path_obj = Path(model_path).resolve()
        print(f"[MODEL_LOADER] MODEL_PATH: {model_path}")
        print(f"[MODEL_LOADER] MODEL_PATH_TYPE: {type(model_path)}")
        print(f"[MODEL_LOADER] MODEL_PATH_RESOLVED: {model_path_obj}")
        print(f"[MODEL_LOADER] MODEL_EXISTS: {model_path_obj.exists()}")
        if model_path_obj.exists():
            print(f"[MODEL_LOADER] MODEL_SIZE: {model_path_obj.stat().st_size} bytes")

        model = load_model(model_path)
        print(f"[MODEL_LOADER] MODEL_LOADED: {type(model)}")
    except FileNotFoundError:
        return None, {
            "status": "error",
            "error": f"Model not found at {model_path}",
            "n_predictions": 0,
        }
    except Exception as e:
        import traceback
        error_msg = f"Failed to load model: {str(e)}"
        print(f"[MODEL_LOADER] ERROR: {error_msg}")
        print(f"[MODEL_LOADER] TRACEBACK: {traceback.format_exc()}")
        return None, {
            "status": "error",
            "error": error_msg,
            "n_predictions": 0,
        }

    # Preparar datos para predicción
    X = input_df.copy()
    n_rows = len(X)

    # Ejecutar predicción
    try:
        y_pred = model.predict(X)
        y_pred = np.clip(y_pred, 0.0, 1.0)  # Clip a [0, 1]
    except Exception as e:
        return None, {
            "status": "error",
            "error": f"Prediction failed: {str(e)}",
            "n_predictions": 0,
        }

    # Crear DataFrame de resultados
    results = pd.DataFrame()

    # Columnas clave del input
    if parcel_uid_col and parcel_uid_col in input_df.columns:
        results["parcel_uid"] = input_df[parcel_uid_col]
    else:
        results["parcel_uid"] = input_df.get("parcel_uid", range(len(input_df)))

    results["parcel_id"] = input_df["parcel_id"]
    results["client_id"] = client_id
    results["superficie_ha"] = input_df["superficie_ha"]

    # Predicción
    results["pct_perdida_pred"] = y_pred
    results["pct_perdida_pred_pct"] = (y_pred * 100).round(2)  # Como porcentaje

    # Impacto económico
    results["impacto_eur_ha_pred"] = (
        input_df["rendimiento_esperado_kg_ha"]
        * y_pred
        * input_df["precio_mercado_eur_kg"]
    ).round(2)

    results["impacto_total_eur"] = (
        results["impacto_eur_ha_pred"] * input_df["superficie_ha"]
    ).round(2)

    # Nivel de riesgo
    results["nivel_riesgo"] = results["pct_perdida_pred"].apply(classify_risk)

    # Metadatos
    results["prediction_status"] = "ok"
    results["prediction_error"] = ""
    results["prediction_updated_at"] = now

    # Guardar
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    output_path = os.path.join(PREDICTIONS_DIR, f"{client_id}_predictions.csv")
    results.to_csv(output_path, index=False, sep=";")

    status = {
        "status": "ok",
        "n_predictions": n_rows,
        "output_path": output_path,
        "updated_at": now,
        "risk_distribution": {
            "bajo": int((results["nivel_riesgo"] == "bajo").sum()),
            "medio": int((results["nivel_riesgo"] == "medio").sum()),
            "alto": int((results["nivel_riesgo"] == "alto").sum()),
            "muy_alto": int((results["nivel_riesgo"] == "muy_alto").sum()),
        },
        "stats": {
            "pct_perdida_media": results["pct_perdida_pred"].mean(),
            "pct_perdida_max": results["pct_perdida_pred"].max(),
            "pct_perdida_min": results["pct_perdida_pred"].min(),
            "impacto_total": results["impacto_total_eur"].sum(),
            "impacto_medio_ha": results["impacto_eur_ha_pred"].mean(),
        }
    }

    return results, status


def load_predictions(client_id: str) -> pd.DataFrame | None:
    """Carga predicciones guardadas para un cliente."""
    path = os.path.join(PREDICTIONS_DIR, f"{client_id}_predictions.csv")
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return None
