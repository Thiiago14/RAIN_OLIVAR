"""
Enriquecimiento meteorológico de parcelas OV via Open-Meteo.
Consulta en paralelo con manejo robusto de errores y conservación de datos previos.

Para meteorología típicamente se quiere actualizar todos los datos porque cambian con el tiempo,
pero si una consulta falla mantiene el dato anterior válido en lugar de sobrescribir con NaN.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import geopandas as gpd
import pandas as pd

from src.integrations.open_meteo_client import fetch_weather

CACHE_DIR = "data/api_cache/weather"
WEATHER_SOURCE = "open-meteo"

WEATHER_COLS = [
    "parcel_uid", "parcel_id", "client_id",
    "lat", "lon",
    "rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%",
    "weather_source", "weather_updated_at", "weather_status", "weather_error",
]


def _cache_path(client_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{client_id}_weather.csv")


def weather_cache_exists(client_id: str) -> bool:
    return os.path.exists(_cache_path(client_id))


def load_weather_cache(client_id: str) -> pd.DataFrame | None:
    """Carga cache de meteorología con tipos correctos."""
    path = _cache_path(client_id)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, sep=";", dtype=str)
        for col in ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%", "lat", "lon"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return None


def save_weather_cache(client_id: str, df: pd.DataFrame) -> str:
    """Guarda cache de meteorología."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(client_id)
    df.to_csv(path, index=False, sep=";")
    return path


def get_weather_stats(weather_df: pd.DataFrame) -> dict:
    """Resumen del estado del cache meteorológico, incluyendo stale."""
    total = len(weather_df)
    ok = int((weather_df["weather_status"] == "ok").sum())
    stale = int((weather_df["weather_status"] == "stale_weather").sum())
    errors = int((weather_df["weather_status"] == "error").sum())
    no_data = int((weather_df["weather_status"] == "no_data").sum())
    updated_at = weather_df["weather_updated_at"].max() if "weather_updated_at" in weather_df.columns else None

    return {
        "total": total,
        "ok": ok,
        "stale": stale,
        "errors": errors,
        "no_data": no_data,
        "pct_ok": round(ok / total * 100) if total > 0 else 0,
        "pct_complete": round((ok + stale) / total * 100) if total > 0 else 0,
        "updated_at": updated_at,
    }


def _fetch_one(row_dict: dict) -> dict:
    """Consulta Open-Meteo para una parcela. Retorna fila con status ok/error."""
    now = datetime.now().isoformat(timespec="seconds")
    base = {
        "parcel_uid": row_dict["parcel_uid"],
        "parcel_id": row_dict["parcel_id"],
        "client_id": row_dict["client_id"],
        "lat": row_dict["lat"],
        "lon": row_dict["lon"],
        "weather_source": WEATHER_SOURCE,
        "weather_updated_at": now,
    }
    try:
        weather = fetch_weather(row_dict["lat"], row_dict["lon"])
        return {
            **base,
            **weather,
            "weather_status": "ok",
            "weather_error": "",
        }
    except Exception as exc:
        return {
            **base,
            "rain_72h_mm": None,
            "rain_7d_mm": None,
            "temp_media_7d": None,
            "humedad_suelo_%": None,
            "weather_status": "error",
            "weather_error": str(exc)[:200],
        }


def enrich_weather_for_client(
    client_id: str,
    ov_gdf: gpd.GeoDataFrame,
    max_workers: int = 5,
    progress_callback=None,
    update_mode: str = "all",
) -> pd.DataFrame:
    """
    Consulta Open-Meteo en paralelo para parcelas OV del cliente.
    Para meteorología típicamente actualiza todas las parcelas (datos cambian).
    Pero si una consulta falla mantiene dato anterior válido.

    Args:
        client_id: Identificador del cliente
        ov_gdf: GeoDataFrame de parcelas OV
        max_workers: Número de workers paralelos
        progress_callback: Función de progreso(done, total)
        update_mode: "all" (por defecto, actualiza todas) o "errors_only"

    Estrategia:
    1. Carga cache anterior si existe
    2. Si update_mode="all": consulta todas las parcelas
    3. Si update_mode="errors_only": consulta solo las que tenían error previo
    4. Si una consulta falla: mantiene dato anterior válido, marca como stale_weather
    5. Guarda cache combinado
    """
    required = {"parcel_uid", "parcel_id", "client_id", "lat", "lon"}
    missing = required - set(ov_gdf.columns)
    if missing:
        raise ValueError(f"GeoDataFrame falta columnas: {missing}")

    # Cargar cache anterior
    prev_cache = load_weather_cache(client_id)
    prev_by_uid = {}
    if prev_cache is not None and not prev_cache.empty:
        prev_by_uid = {row["parcel_uid"]: row.to_dict() for _, row in prev_cache.iterrows()}

    all_rows = ov_gdf[list(required)].to_dict("records")

    # Determinar qué parcelas consultar
    to_fetch = all_rows
    if update_mode == "errors_only" and prev_cache is not None and not prev_cache.empty:
        # Solo reintenta parcelas con error o sin dato
        to_fetch = []
        for row in all_rows:
            uid = row["parcel_uid"]
            if uid not in prev_by_uid:
                to_fetch.append(row)
            else:
                prev = prev_by_uid[uid]
                if prev.get("weather_status") != "ok":
                    to_fetch.append(row)

    total = len(to_fetch)
    results_by_uid = {}

    if total > 0:
        results = [None] * total
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_idx = {pool.submit(_fetch_one, row): i for i, row in enumerate(to_fetch)}
            done = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                result = future.result()
                results[idx] = result
                results_by_uid[result["parcel_uid"]] = result
                done += 1
                if progress_callback:
                    progress_callback(done, total)

    # Combinar: nuevos resultados + datos previos válidos
    final_rows = {}
    for row in all_rows:
        uid = row["parcel_uid"]

        if uid in results_by_uid:
            # Usar resultado nuevo
            final_rows[uid] = results_by_uid[uid]
        elif uid in prev_by_uid:
            # Mantener dato previo
            prev = prev_by_uid[uid]
            if prev.get("weather_status") == "ok":
                # Dato previo válido → marcar como stale si se intentó consultar y falló
                if uid in results_by_uid:
                    # Se intentó pero falló → marcar como stale
                    prev["weather_status"] = "stale_weather"
                    prev["weather_error"] = "Consulta falló; manteniendo dato anterior"
                final_rows[uid] = prev
            else:
                # Dato previo con error → si hay nuevo resultado usarlo, si no dejar error
                final_rows[uid] = results_by_uid.get(uid, prev)
        else:
            # Sin dato previo ni nuevo → error
            if uid in results_by_uid:
                final_rows[uid] = results_by_uid[uid]
            else:
                # No debería pasar
                uid_row = next((r for r in all_rows if r["parcel_uid"] == uid), {})
                final_rows[uid] = {
                    "parcel_uid": uid,
                    "parcel_id": uid_row.get("parcel_id"),
                    "client_id": client_id,
                    "lat": uid_row.get("lat"),
                    "lon": uid_row.get("lon"),
                    "rain_72h_mm": None,
                    "rain_7d_mm": None,
                    "temp_media_7d": None,
                    "humedad_suelo_%": None,
                    "weather_source": WEATHER_SOURCE,
                    "weather_updated_at": datetime.now().isoformat(timespec="seconds"),
                    "weather_status": "no_data",
                    "weather_error": "Sin dato previo ni nueva consulta",
                }

    # Construir DataFrame final
    df_final = pd.DataFrame(
        [final_rows[uid] for uid in [r["parcel_uid"] for r in all_rows]],
        columns=WEATHER_COLS
    )
    save_weather_cache(client_id, df_final)
    return df_final


def merge_weather_into_base(
    base_df: pd.DataFrame,
    weather_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Fusiona variables meteorológicas en el CSV base usando parcel_id como clave.
    Usa valores si weather_status es 'ok' o 'stale_weather' (dato previo válido).
    """
    if weather_df is None or weather_df.empty:
        return base_df

    COLS = ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%"]
    # Incluir tanto 'ok' como 'stale_weather' (dato previo válido)
    valid_weather = weather_df[
        weather_df["weather_status"].isin(["ok", "stale_weather"])
    ].set_index("parcel_id")

    result = base_df.copy()
    for col in COLS:
        if col in valid_weather.columns and col in result.columns:
            result[col] = result["parcel_id"].map(valid_weather[col])

    return result
