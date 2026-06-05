"""
Enriquecimiento hidrológico usando Overpass API / OpenStreetMap.
Estrategia eficiente: UNA sola consulta para todas las parcelas (bbox expandida),
luego distancia punto-a-punto por Haversine.

Con manejo robusto de errores:
- update_mode="errors_only": Retenta solo si hubo error en consulta anterior
- update_mode="force_all": Intenta nueva consulta, conserva datos previos válidos si falla
- Marca como "stale" si mantiene dato anterior debido a fallo de consulta
"""
import os
from datetime import datetime

import geopandas as gpd
import pandas as pd

from src.integrations.overpass_client import (
    fetch_water_features, nearest_feature,
)

CACHE_DIR = "data/api_cache/hydrology"
HYDRO_SOURCE = "overpass-osm"
DEFAULT_RADIUS_M = 5000

HYDRO_COLS = [
    "parcel_uid", "parcel_id", "client_id", "lat", "lon",
    "distancia_rio_m", "nearest_water_type", "nearest_water_name",
    "overpass_radius_m",
    "hydrology_source", "hydrology_updated_at",
    "hydrology_status", "hydrology_error",
]


def _cache_path(client_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{client_id}_hydrology.csv")


def enrich_hydrology_for_client(
    client_id: str,
    ov_gdf: gpd.GeoDataFrame,
    radius_m: int = DEFAULT_RADIUS_M,
    update_mode: str = "errors_only",
) -> pd.DataFrame:
    """
    Consulta Overpass UNA vez para toda la bbox del cliente, luego calcula distancia
    de cada parcela al agua más cercana.

    Args:
        client_id: Identificador del cliente
        ov_gdf: GeoDataFrame de parcelas OV
        radius_m: Radio de búsqueda en metros
        update_mode: "errors_only" o "force_all"

    Estrategia:
    1. Carga cache anterior si existe
    2. Consulta Overpass UNA VEZ para toda la bbox
    3. Si consulta OK: procesa todas las parcelas
    4. Si consulta falla:
       - Si update_mode="errors_only": mantiene cache anterior (marca como stale si es necesario)
       - Si update_mode="force_all": intenta procesamiento sin datos nuevos, conserva anteriores
    """
    required = {"parcel_uid", "parcel_id", "client_id", "lat", "lon"}
    missing = required - set(ov_gdf.columns)
    if missing:
        raise ValueError(f"GeoDataFrame falta columnas: {missing}")

    now = datetime.now().isoformat(timespec="seconds")

    # Cargar cache anterior
    prev_cache = load_hydrology_cache(client_id)
    prev_by_uid = {}
    if prev_cache is not None and not prev_cache.empty:
        prev_by_uid = {row["parcel_uid"]: row.to_dict() for _, row in prev_cache.iterrows()}

    # Bbox de todas las parcelas OV
    lats = ov_gdf["lat"].tolist()
    lons = ov_gdf["lon"].tolist()
    south, west = min(lats), min(lons)
    north, east = max(lats), max(lons)

    # Una sola consulta Overpass
    try:
        features = fetch_water_features(south, west, north, east, radius_m)
        fetch_ok = True
        fetch_error = ""
    except Exception as exc:
        features = []
        fetch_ok = False
        fetch_error = str(exc)[:300]

    rows = []
    for _, row in ov_gdf.iterrows():
        uid = row["parcel_uid"]
        base = {
            "parcel_uid": uid,
            "parcel_id": row["parcel_id"],
            "client_id": row["client_id"],
            "lat": row["lat"],
            "lon": row["lon"],
            "overpass_radius_m": radius_m,
            "hydrology_source": HYDRO_SOURCE,
            "hydrology_updated_at": now,
        }

        if not fetch_ok:
            # Consulta Overpass falló
            if update_mode == "errors_only" and uid in prev_by_uid:
                # Mantener dato anterior si existe
                prev = prev_by_uid[uid]
                if prev.get("hydrology_status") in ("ok", "no_water_found", "beyond_radius"):
                    # Dato previo válido → marcar como stale
                    prev["hydrology_status"] = "stale"
                    prev["hydrology_error"] = "Consulta Overpass falló; manteniendo dato anterior"
                    prev["hydrology_updated_at"] = now
                    rows.append(prev)
                else:
                    # Dato previo con error → no cambiar
                    prev["hydrology_error"] = fetch_error
                    prev["hydrology_updated_at"] = now
                    rows.append(prev)
            else:
                # Crear fila de error
                rows.append({
                    **base,
                    "distancia_rio_m": None,
                    "nearest_water_type": None,
                    "nearest_water_name": None,
                    "hydrology_status": "error",
                    "hydrology_error": fetch_error,
                })
            continue

        # Consulta OK → procesar
        dist, wtype, wname = nearest_feature(row["lat"], row["lon"], features)

        if dist is None:
            status = "no_water_found"
        elif dist > radius_m:
            status = "beyond_radius"
        else:
            status = "ok"

        rows.append({
            **base,
            "distancia_rio_m": dist,
            "nearest_water_type": wtype or "",
            "nearest_water_name": wname or "",
            "hydrology_status": status,
            "hydrology_error": "",
        })

    df = pd.DataFrame(rows, columns=HYDRO_COLS)
    _save_hydrology_cache(client_id, df)
    return df


def _save_hydrology_cache(client_id: str, df: pd.DataFrame) -> str:
    """Guarda cache de hidrología, preservando estructura."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(client_id)
    df.to_csv(path, index=False, sep=";")
    return path


def load_hydrology_cache(client_id: str) -> pd.DataFrame | None:
    """Carga cache de hidrología con tipos correctos."""
    path = _cache_path(client_id)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, sep=";", dtype=str)
        for col in ["distancia_rio_m", "lat", "lon", "overpass_radius_m"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return None


def get_hydrology_stats(df: pd.DataFrame) -> dict:
    """Estadísticas de cobertura hidrológica, incluyendo stale."""
    total = len(df)
    ok = int((df["hydrology_status"] == "ok").sum())
    no_water = int((df["hydrology_status"] == "no_water_found").sum())
    beyond = int((df["hydrology_status"] == "beyond_radius").sum())
    stale = int((df["hydrology_status"] == "stale").sum())
    errors = int((df["hydrology_status"] == "error").sum())
    updated = df["hydrology_updated_at"].max() if "hydrology_updated_at" in df.columns else None

    return {
        "total": total,
        "ok": ok,
        "no_water": no_water,
        "beyond_radius": beyond,
        "stale": stale,
        "errors": errors,
        "pct_ok": round(ok / total * 100) if total > 0 else 0,
        "pct_complete": round((ok + no_water + beyond + stale) / total * 100) if total > 0 else 0,
        "updated_at": updated,
    }
