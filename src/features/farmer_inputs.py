import pandas as pd
import geopandas as gpd

TIPO_OLIVAR_OPTIONS = ["", "Tradicional", "Intensivo", "Superintensivo"]
RIEGO_OPTIONS = ["", "Secano", "Riego"]
VARIEDAD_OPTIONS = [
    "", "Picual", "Hojiblanca", "Arbequina", "Manzanilla",
    "Cornicabra", "Otra", "Desconocida",
]
ESTADO_FENOLOGICO_OPTIONS = [
    "", "Brotacion", "Floracion", "Cuajado", "Engorde",
    "Envero", "Maduracion", "Reposo", "Desconocido",
]

FARMER_COLS = ["tipo_olivar", "riego", "variedad", "estado_fenologico"]

READONLY_COLS = [
    "parcel_uid", "parcel_id", "client_id", "uso_sigpac",
    "superficie_ha", "area_ha_calc", "pendiente_%", "altitud_m", "zona_provincia",
]


def init_farmer_data(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "parcel_uid": gdf["parcel_uid"].values if "parcel_uid" in gdf.columns else [""] * len(gdf),
        "parcel_id": gdf["parcel_id"].values,
        "tipo_olivar": "",
        "riego": "",
        "variedad": "",
        "estado_fenologico": "",
    })


def build_editor_df(gdf: gpd.GeoDataFrame, farmer_data: pd.DataFrame) -> pd.DataFrame:
    """Combina columnas de visualización + columnas editables para st.data_editor."""
    display_cols = ["parcel_uid", "parcel_id", "client_id", "uso_sigpac",
                    "area_ha_calc", "pendiente_pct", "altitud_m"]
    cols = [c for c in display_cols if c in gdf.columns]
    base = gdf[cols].copy()
    base = base.rename(columns={
        "area_ha_calc": "superficie_ha",
        "pendiente_pct": "pendiente_%",
    })

    # Merge por parcel_uid si disponible, sino por parcel_id
    if "parcel_uid" in farmer_data.columns and "parcel_uid" in base.columns:
        farmer_map = farmer_data.set_index("parcel_uid")
        join_col = "parcel_uid"
    else:
        farmer_map = farmer_data.set_index("parcel_id")
        join_col = "parcel_id"

    for col in FARMER_COLS:
        if col in farmer_map.columns:
            base[col] = base[join_col].map(farmer_map[col]).fillna("")
        else:
            base[col] = ""

    return base.reset_index(drop=True)


def calc_completeness(edited_df: pd.DataFrame) -> dict:
    """
    Calcula la completitud de los campos obligatorios del agricultor.

    Retorna:
        total_fields: int - total de celdas obligatorias
        filled_fields: int - celdas completas (no vacías)
        pending_fields: int - celdas vacías
        pct: int - porcentaje (0-100)
        is_complete: bool
        missing_parcels: lista de dicts {parcel_id, missing_cols}
    """
    available_cols = [c for c in FARMER_COLS if c in edited_df.columns]
    n_parcels = len(edited_df)
    total_fields = n_parcels * len(available_cols)

    filled_fields = int(
        sum((edited_df[c] != "").sum() for c in available_cols)
    )
    pending_fields = total_fields - filled_fields
    pct = round(filled_fields / total_fields * 100) if total_fields > 0 else 0

    missing_parcels = []
    pid_col = "parcel_id" if "parcel_id" in edited_df.columns else edited_df.columns[0]
    for _, row in edited_df.iterrows():
        missing = [c for c in available_cols if row.get(c, "") == ""]
        if missing:
            missing_parcels.append({
                "parcel_id": row.get(pid_col, "?"),
                "missing_cols": missing,
            })

    return {
        "total_fields": total_fields,
        "filled_fields": filled_fields,
        "pending_fields": pending_fields,
        "pct": pct,
        "is_complete": pct == 100,
        "missing_parcels": missing_parcels,
    }
