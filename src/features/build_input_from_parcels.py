import pandas as pd
import geopandas as gpd

# Columnas del esquema completo — orden esperado por modelo ML (22 cols)
SCHEMA_COLUMNS = [
    "parcel_id", "zona_provincia", "tipo_olivar", "riego", "superficie_ha",
    "variedad", "estado_fenologico", "tipo_suelo", "drenaje", "pendiente_%",
    "distancia_rio_m", "altitud_m",
    "rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%",
    "profundidad_suelo_cm", "materia_organica_%",
    "rendimiento_esperado_kg_ha", "precio_mercado_eur_kg", "coste_variable_ha",
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
WEATHER_COLS = ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%"]


def build_base_input(
    gdf: gpd.GeoDataFrame,
    farmer_data: pd.DataFrame | None = None,
    weather_data: pd.DataFrame | None = None,
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

    # Fusionar datos del agricultor
    if farmer_data is not None and not farmer_data.empty:
        farmer_idx = farmer_data.set_index("parcel_id")
        for col in FARMER_COLS:
            if col in farmer_idx.columns:
                mapped = df["parcel_id"].map(farmer_idx[col])
                df[col] = mapped.where(mapped.notna() & (mapped != ""), df[col])

    # Fusionar datos meteorológicos (solo parcelas con weather_status == "ok")
    if weather_data is not None and not weather_data.empty:
        ok_weather = weather_data[weather_data.get("weather_status", "ok") == "ok"] \
            if "weather_status" in weather_data.columns else weather_data
        weather_idx = ok_weather.set_index("parcel_id")
        for col in WEATHER_COLS:
            if col in weather_idx.columns and col in df.columns:
                df[col] = df["parcel_id"].map(weather_idx[col])

    return df


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8")
