"""
Ensamblador de CSV consolidado por cliente.
Integra: shapefile + agricultor + meteorología + suelo + hidrología + económico + encharcamiento.
Salida: data/enriched/{client_id}_input_enriched.csv (22 columnas modelo en orden correcto).

Con soporte para datos válidos (ok o stale) y flag ready_for_ml.
"""
import os

import geopandas as gpd
import pandas as pd

from src.features.build_input_from_parcels import SCHEMA_COLUMNS, build_base_input
from src.features.waterlogging_calculator import calculate_waterlogging_for_df
from src.features.economic_enrichment import enrich_economic_for_client

ENRICHED_DIR = "data/enriched"

SOURCE_COLUMNS = {
    "shapefile": ["parcel_id", "superficie_ha", "pendiente_%", "altitud_m", "zona_provincia"],
    "agricultor": ["tipo_olivar", "riego", "variedad", "estado_fenologico"],
    "meteorologia": ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%"],
    "suelo": ["tipo_suelo", "drenaje", "profundidad_suelo_cm", "materia_organica_%"],
    "hidrologia": ["distancia_rio_m", "duracion_encharcamiento_dias"],
    "economico": ["rendimiento_esperado_kg_ha", "precio_mercado_eur_kg", "coste_variable_ha"],
}


def assemble_enriched_csv(
    client_id: str,
    ov_gdf: gpd.GeoDataFrame,
    farmer_data: pd.DataFrame | None = None,
    weather_df: pd.DataFrame | None = None,
    soil_df: pd.DataFrame | None = None,
    hydrology_df: pd.DataFrame | None = None,
    hms_results: dict | None = None,
) -> pd.DataFrame:
    """
    Genera y guarda el CSV consolidado del cliente.
    Integra: shapefile + agricultor + meteo + suelo + hidrología + económico + encharcamiento.
    Retorna DataFrame con SCHEMA_COLUMNS (22 cols, orden correcto).

    Estrategia robusta:
    - Usa datos "ok" y "stale" (dato previo válido) de APIs
    - Ignora datos con status "error" o "no_data" sin valor previo válido
    - Calcula ready_for_ml: True solo si todas las 22 cols están completas para todas las parcelas OV
    """
    # 1. Base: shapefile + agricultor + meteorología
    df = build_base_input(ov_gdf, farmer_data, weather_df)

    # 2. Suelo: tipo_suelo, drenaje, profundidad_suelo_cm, materia_organica_%
    # Usa datos ok o stale (dato previo válido mantenido después de fallo de API)
    if soil_df is not None and not soil_df.empty and "soil_status" in soil_df.columns:
        valid_soil = soil_df[soil_df["soil_status"].isin(["ok", "stale"])].set_index("parcel_id")
        for col in ["tipo_suelo", "drenaje", "profundidad_suelo_cm", "materia_organica_%"]:
            if col in valid_soil.columns and col in df.columns:
                df[col] = df["parcel_id"].map(valid_soil[col])

    # 3. Hidrología: distancia_rio_m
    # Usa datos ok o stale
    if hydrology_df is not None and not hydrology_df.empty and "hydrology_status" in hydrology_df.columns:
        valid_hydro = hydrology_df[hydrology_df["hydrology_status"].isin(["ok", "stale"])].set_index("parcel_id")
        if "distancia_rio_m" in valid_hydro.columns and "distancia_rio_m" in df.columns:
            df["distancia_rio_m"] = df["parcel_id"].map(valid_hydro["distancia_rio_m"])

    # 4. Encharcamiento: duracion_encharcamiento_dias (cálculo interno)
    has_meteo = df["rain_72h_mm"].notna().any() or df["rain_7d_mm"].notna().any()
    if has_meteo:
        df = calculate_waterlogging_for_df(df)

    # 5. Económico: rendimiento, precios, costes (tablas locales)
    df = enrich_economic_for_client(df)

    # 6. Reordenar a SCHEMA_COLUMNS (22 cols modelo)
    df = df[SCHEMA_COLUMNS]

    # 7. Calcular ready_for_ml y completeness
    n_parcelas = len(df)
    cols_complete = 0
    for col in SCHEMA_COLUMNS:
        if col in df.columns and df[col].notna().sum() == n_parcelas:
            cols_complete += 1

    ready_for_ml = (cols_complete == len(SCHEMA_COLUMNS)) and n_parcelas > 0

    # Añadir columnas de estado (no afectan los datos del modelo)
    df["_ready_for_ml"] = ready_for_ml
    df["_cols_complete"] = cols_complete
    df["_n_parcelas_ov"] = n_parcelas

    # 8. Guardar
    os.makedirs(ENRICHED_DIR, exist_ok=True)
    path = os.path.join(ENRICHED_DIR, f"{client_id}_input_enriched.csv")
    df.to_csv(path, index=False, sep=";")

    # 9. Sidecar HMS: guardar features hidrológicas en CSV separado (NO entran al ML)
    if hms_results:
        _save_hms_sidecar(client_id, df, hms_results)

    return df


def get_enrichment_coverage(df: pd.DataFrame) -> dict:
    """Cobertura (% de parcelas con valor) agrupada por fuente."""
    n = len(df)
    if n == 0:
        return {}
    coverage = {}
    for source, cols in SOURCE_COLUMNS.items():
        source_cov = {}
        for col in cols:
            if col in df.columns:
                filled = int(df[col].notna().sum())
                source_cov[col] = {"filled": filled, "total": n, "pct": round(filled / n * 100)}
        coverage[source] = source_cov
    return coverage


def get_ml_readiness(enriched_df: pd.DataFrame) -> dict:
    """
    Evalúa si el CSV consolidado está listo para modelo ML.
    Retorna dict con estado general y detalles.
    """
    n = len(enriched_df)
    if n == 0:
        return {
            "ready": False,
            "reason": "No hay parcelas OV",
            "parcelas_ok": 0,
            "parcelas_bloqueantes": [],
            "cols_complete": 0,
            "cols_total": len(SCHEMA_COLUMNS),
            "cols_missing": SCHEMA_COLUMNS,
        }

    # Contar columnas completas
    cols_complete = 0
    cols_missing = []
    for col in SCHEMA_COLUMNS:
        if col in enriched_df.columns:
            if enriched_df[col].notna().sum() == n:
                cols_complete += 1
            else:
                cols_missing.append(col)
        else:
            cols_missing.append(col)

    # Identificar parcelas bloqueantes (con variables faltantes)
    parcelas_bloqueantes = []
    for _, row in enriched_df.iterrows():
        missing_in_row = [col for col in SCHEMA_COLUMNS if col not in enriched_df.columns or pd.isna(row[col])]
        if missing_in_row:
            parcelas_bloqueantes.append({
                "parcel_id": row.get("parcel_id", "?"),
                "missing_cols": missing_in_row,
                "n_missing": len(missing_in_row),
            })

    ready = (cols_complete == len(SCHEMA_COLUMNS)) and len(parcelas_bloqueantes) == 0

    return {
        "ready": ready,
        "reason": (
            "OK: Listo para ML" if ready
            else (
                f"{len(parcelas_bloqueantes)} parcelas con datos faltantes"
                if parcelas_bloqueantes
                else f"{len(cols_missing)} columnas incompletas"
            )
        ),
        "parcelas_ok": n - len(parcelas_bloqueantes),
        "parcelas_bloqueantes": parcelas_bloqueantes,
        "cols_complete": cols_complete,
        "cols_total": len(SCHEMA_COLUMNS),
        "cols_missing": cols_missing,
    }


def get_ml_ready_csv(enriched_df: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna SOLO las 22 columnas del modelo ML en orden correcto.
    Sin columnas técnicas (_ready_for_ml, etc.).
    Apto para exportación al modelo.
    """
    # Filtrar solo las columnas del schema
    ml_cols = [col for col in SCHEMA_COLUMNS if col in enriched_df.columns]
    return enriched_df[ml_cols].copy()


def get_slope_warnings(enriched_df: pd.DataFrame) -> list:
    """
    Identifica parcelas con pendiente extrema (advertencia sin bloqueo).
    Retorna lista de dicts con {parcel_id, pendiente_%, nivel}.
    """
    warnings = []
    if "pendiente_%" not in enriched_df.columns:
        return warnings

    for _, row in enriched_df.iterrows():
        slope = row.get("pendiente_%")
        if slope is not None:
            try:
                slope_val = float(slope)
                if slope_val > 100:
                    nivel = "ALERTA FUERTE"
                    warnings.append({
                        "parcel_id": row.get("parcel_id", "?"),
                        "pendiente_%": slope_val,
                        "nivel": nivel,
                        "msg": f"Pendiente {slope_val}% (>100%) - revisar dato SIGPAC"
                    })
                elif slope_val > 60:
                    nivel = "ADVERTENCIA"
                    warnings.append({
                        "parcel_id": row.get("parcel_id", "?"),
                        "pendiente_%": slope_val,
                        "nivel": nivel,
                        "msg": f"Pendiente {slope_val}% (>60%) - revisar dato SIGPAC"
                    })
            except (ValueError, TypeError):
                pass

    return warnings


def enriched_csv_exists(client_id: str) -> bool:
    return os.path.exists(os.path.join(ENRICHED_DIR, f"{client_id}_input_enriched.csv"))


def load_enriched_csv(client_id: str) -> pd.DataFrame | None:
    path = os.path.join(ENRICHED_DIR, f"{client_id}_input_enriched.csv")
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return None


# =========================================================================
# HMS Sidecar: features hidrológicas (NO entran al modelo ML)
# =========================================================================

HMS_COLS = ["parcel_id", "caudal_pico_m3s", "tiempo_pico_h", "escorrentia_acumulada_mm"]


def _save_hms_sidecar(
    client_id: str,
    enriched_df: pd.DataFrame,
    hms_results: dict,
) -> str | None:
    """
    Guarda features HMS en CSV sidecar separado.
    Estos datos se inyectan al prompt del LLM pero NO al modelo ML.

    Args:
        client_id: identificador del cliente
        enriched_df: DataFrame con parcel_id
        hms_results: dict con {caudal_pico_m3s, tiempo_pico_h, escorrentia_acumulada_mm}
                     o dict con resultados por parcela
    """
    os.makedirs(ENRICHED_DIR, exist_ok=True)
    path = os.path.join(ENRICHED_DIR, f"{client_id}_hms_features.csv")

    rows = []
    for _, row in enriched_df.iterrows():
        parcel_id = row.get("parcel_id")
        if parcel_id is None:
            continue

        # hms_results puede ser un dict global o por parcela
        if "parcelas" in hms_results and parcel_id in hms_results["parcelas"]:
            hms = hms_results["parcelas"][parcel_id]
        else:
            hms = hms_results

        rows.append({
            "parcel_id": parcel_id,
            "caudal_pico_m3s": hms.get("caudal_pico_m3s"),
            "tiempo_pico_h": hms.get("tiempo_pico_h"),
            "escorrentia_acumulada_mm": hms.get("escorrentia_acumulada_mm"),
        })

    if not rows:
        return None

    df_hms = pd.DataFrame(rows, columns=HMS_COLS)
    df_hms.to_csv(path, index=False, sep=";")
    return path


def load_hms_sidecar(client_id: str) -> pd.DataFrame | None:
    """Carga el CSV sidecar de features HMS si existe."""
    path = os.path.join(ENRICHED_DIR, f"{client_id}_hms_features.csv")
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return None


def hms_sidecar_exists(client_id: str) -> bool:
    """Verifica si existe el sidecar HMS para un cliente."""
    path = os.path.join(ENRICHED_DIR, f"{client_id}_hms_features.csv")
    return os.path.exists(path)
