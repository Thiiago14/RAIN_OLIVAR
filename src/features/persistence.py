"""
Persistencia de datos del agricultor por cliente.
Guarda y carga archivos CSV en data/client_inputs/.
"""
import os
from datetime import datetime

import geopandas as gpd
import pandas as pd

INPUTS_DIR = "data/client_inputs"

PERSIST_COLS = [
    "parcel_uid",
    "parcel_id",
    "client_id",
    "uso_sigpac",
    "tipo_olivar",
    "riego",
    "variedad",
    "estado_fenologico",
    "updated_at",
    "completion_status",
]

FARMER_COLS = ["tipo_olivar", "riego", "variedad", "estado_fenologico"]


def _input_path(client_id: str) -> str:
    return os.path.join(INPUTS_DIR, f"{client_id}_farmer_inputs.csv")


def client_file_exists(client_id: str) -> bool:
    return os.path.exists(_input_path(client_id))


def get_client_status(client_id: str) -> str:
    """
    Devuelve el estado del cliente:
    'sin_datos' | 'borrador' | 'completo'
    """
    if not client_file_exists(client_id):
        return "sin_datos"
    try:
        df = load_farmer_inputs(client_id)
        if df is None or df.empty:
            return "sin_datos"
        statuses = df["completion_status"].unique()
        if "completo" in statuses and len(statuses) == 1:
            return "completo"
        return "borrador"
    except Exception:
        return "sin_datos"


def save_farmer_inputs(
    client_id: str,
    edited_df: pd.DataFrame,
    ov_gdf: gpd.GeoDataFrame,
    status: str = "borrador",
) -> str:
    """
    Guarda los datos del agricultor para el cliente dado.

    edited_df debe contener: parcel_id + FARMER_COLS.
    ov_gdf es el GeoDataFrame de parcelas OV procesado (contiene parcel_uid, uso_sigpac, client_id).

    Retorna la ruta del archivo guardado.
    """
    os.makedirs(INPUTS_DIR, exist_ok=True)

    now = datetime.now().isoformat(timespec="seconds")

    # Merge parcel_uid desde ov_gdf
    uid_map = ov_gdf.set_index("parcel_id")["parcel_uid"].to_dict()
    uso_map = ov_gdf.set_index("parcel_id")["uso_sigpac"].to_dict() if "uso_sigpac" in ov_gdf.columns else {}
    cid_map = ov_gdf.set_index("parcel_id")["client_id"].to_dict()

    out = edited_df[["parcel_id"] + [c for c in FARMER_COLS if c in edited_df.columns]].copy()
    out["parcel_uid"] = out["parcel_id"].map(uid_map)
    out["client_id"] = out["parcel_id"].map(cid_map)
    out["uso_sigpac"] = out["parcel_id"].map(uso_map)
    out["updated_at"] = now
    out["completion_status"] = status

    out = out[PERSIST_COLS]
    path = _input_path(client_id)
    out.to_csv(path, index=False, sep=";")
    return path


def load_farmer_inputs(client_id: str) -> pd.DataFrame | None:
    """
    Carga el archivo de datos del agricultor del cliente.
    Retorna None si no existe.
    """
    path = _input_path(client_id)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, sep=";", dtype=str).fillna("")
        return df
    except Exception:
        return None


def merge_saved_with_gdf(
    saved_df: pd.DataFrame,
    ov_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    Hace merge entre los datos guardados y el GDF actual por parcel_uid.
    Las parcelas nuevas (no en saved_df) se inicializan vacías.
    Las parcelas eliminadas del shapefile se descartan del saved_df.
    Retorna un DataFrame con parcel_id + FARMER_COLS.
    """
    base = pd.DataFrame({
        "parcel_uid": ov_gdf["parcel_uid"].values,
        "parcel_id": ov_gdf["parcel_id"].values,
        "tipo_olivar": "",
        "riego": "",
        "variedad": "",
        "estado_fenologico": "",
    })

    if saved_df is None or saved_df.empty or "parcel_uid" not in saved_df.columns:
        return base

    saved_indexed = saved_df.set_index("parcel_uid")
    for col in FARMER_COLS:
        if col in saved_indexed.columns:
            base[col] = base["parcel_uid"].map(saved_indexed[col]).fillna("")

    return base
