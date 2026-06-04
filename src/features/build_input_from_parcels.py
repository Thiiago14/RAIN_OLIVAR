import pandas as pd
import geopandas as gpd

# Columnas del esquema completo de test_olivar.csv
# Clasificadas por origen de dato
SCHEMA_COLUMNS = [
    # -- Del shapefile/polígono --
    "parcel_id",
    "superficie_ha",
    "pendiente_%",
    "altitud_m",
    # -- Localización (del shapefile SIGPAC) --
    "zona_provincia",
    # -- A completar por el agricultor --
    "tipo_olivar",
    "riego",
    "variedad",
    "estado_fenologico",
    "tipo_suelo",
    "drenaje",
    "rendimiento_esperado_kg_ha",
    "precio_mercado_eur_kg",
    "coste_variable_ha",
    # -- Fuentes externas (API climática / sensores) --
    "rain_72h_mm",
    "rain_7d_mm",
    "temp_media_7d",
    "humedad_suelo_%",
    "profundidad_suelo_cm",
    "materia_organica_%",
    "distancia_rio_m",
    "duracion_encharcamiento_dias",
]

PROVINCIA_MAP = {
    18: "Granada",
    14: "Córdoba",
    41: "Sevilla",
    23: "Jaén",
    11: "Cádiz",
    29: "Málaga",
    21: "Huelva",
    4: "Almería",
}


FARMER_COLS = ["tipo_olivar", "riego", "variedad", "estado_fenologico"]


def build_base_input(
    gdf: gpd.GeoDataFrame,
    farmer_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows = []

    for _, row in gdf.iterrows():
        provincia_code = row.get("provincia", None)
        zona = PROVINCIA_MAP.get(int(provincia_code), str(provincia_code)) if provincia_code else None

        entry = {
            "parcel_id": row.get("parcel_id"),
            "superficie_ha": row.get("area_ha_calc"),
            "pendiente_%": row.get("pendiente_pct"),
            "altitud_m": row.get("altitud_m"),
            "zona_provincia": zona,
            "tipo_olivar": None,
            "riego": None,
            "variedad": None,
            "estado_fenologico": None,
            "tipo_suelo": None,
            "drenaje": None,
            "rendimiento_esperado_kg_ha": None,
            "precio_mercado_eur_kg": None,
            "coste_variable_ha": None,
            "rain_72h_mm": None,
            "rain_7d_mm": None,
            "temp_media_7d": None,
            "humedad_suelo_%": None,
            "profundidad_suelo_cm": None,
            "materia_organica_%": None,
            "distancia_rio_m": None,
            "duracion_encharcamiento_dias": None,
        }
        rows.append(entry)

    df = pd.DataFrame(rows, columns=SCHEMA_COLUMNS)

    # Fusionar datos editados por el agricultor si se proporcionan
    if farmer_data is not None and not farmer_data.empty:
        farmer_idx = farmer_data.set_index("parcel_id")
        for col in FARMER_COLS:
            if col in farmer_idx.columns:
                mapped = df["parcel_id"].map(farmer_idx[col])
                df[col] = mapped.where(mapped.notna() & (mapped != ""), df[col])

    return df


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8")
