"""
Enriquecimiento edáfico usando SoilGrids v2 (ISRIC).
Consulta en paralelo con manejo robusto de errores y conservación de datos válidos previos.

Estrategia:
- update_mode="errors_only" (por defecto): Retenta solo parcelas con error o sin dato.
- update_mode="force_all": Consulta todas las parcelas, pero conserva datos válidos previos
  si una nueva consulta falla.
- Marca como "stale" si una parcela mantiene dato anterior porque la nueva consulta falló.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import geopandas as gpd
import pandas as pd

from src.integrations.soilgrids_client import fetch_soil

CACHE_DIR = "data/api_cache/soil"
SOIL_SOURCE = "soilgrids-v2"

SOIL_COLS = [
    "parcel_uid", "parcel_id", "client_id", "lat", "lon",
    "clay_%", "sand_%", "silt_%", "soc_g_kg",
    "materia_organica_%", "cfvo_%",
    "tipo_suelo", "drenaje", "profundidad_suelo_cm",
    "soil_source", "soil_updated_at", "soil_status", "soil_error",
]

# Términos de textura compatibles con el CSV del modelo
_TEXTURE_MAP_ESP = {
    "Arcilloso": "Arcilloso",
    "Franco-arcilloso": "Franco-arcilloso",
    "Limoso": "Limoso",
    "Franco-limoso": "Limoso",
    "Franco": "Franco",
    "Franco-arenoso": "Franco-arenoso",
    "Arenoso": "Arenoso",
}

_DRAINAGE_BASE = {
    "Arcilloso": "Malo",
    "Franco-arcilloso": "Moderado",
    "Limoso": "Moderado",
    "Franco-limoso": "Moderado",
    "Franco": "Bueno",
    "Franco-arenoso": "Bueno",
    "Arenoso": "Bueno",
}


def classify_texture(clay: float, sand: float, silt: float) -> str | None:
    """Triángulo textural USDA simplificado → términos del modelo."""
    if any(v is None for v in [clay, sand, silt]):
        return None
    if clay >= 40:
        return "Arcilloso"
    if clay >= 27:
        return "Franco-arcilloso"
    if silt >= 50:
        return "Franco-limoso" if clay >= 12 else "Limoso"
    if sand >= 70:
        return "Arenoso"
    if sand >= 45:
        return "Franco-arenoso"
    return "Franco"


def classify_drainage(tipo_suelo: str | None, pendiente_pct: float | None = None) -> str | None:
    """Drenaje base por textura, ajustado por pendiente del shapefile."""
    if tipo_suelo is None:
        return None
    drenaje = _DRAINAGE_BASE.get(tipo_suelo, "Moderado")
    if pendiente_pct is not None and not pd.isna(pendiente_pct):
        # Pendiente alta mejora el drenaje (favorece escorrentía)
        if pendiente_pct > 15 and drenaje == "Malo":
            drenaje = "Moderado"
        elif pendiente_pct > 15 and drenaje == "Moderado":
            drenaje = "Bueno"
    return drenaje


def soc_to_mo_pct(soc_g_kg: float | None) -> float | None:
    """Convierte SOC (g/kg) a materia orgánica (%) usando factor Van Bemmelen."""
    if soc_g_kg is None:
        return None
    return round(soc_g_kg * 1.724 / 10, 2)


def estimate_depth(cfvo_30_60_pct: float | None) -> int:
    """
    Proxy de profundidad efectiva del suelo basado en CFVO a 30-60 cm.
    Alta pedregosidad → menor profundidad efectiva.
    """
    if cfvo_30_60_pct is None or pd.isna(cfvo_30_60_pct):
        return 80  # valor por defecto moderado
    if cfvo_30_60_pct >= 50:
        return 35
    if cfvo_30_60_pct >= 30:
        return 60
    if cfvo_30_60_pct >= 15:
        return 85
    return 110


def _fetch_one(row_dict: dict) -> dict:
    """Consulta SoilGrids para una parcela. Retorna fila con status ok/error."""
    now = datetime.now().isoformat(timespec="seconds")
    base = {
        "parcel_uid": row_dict.get("parcel_uid"),
        "parcel_id": row_dict.get("parcel_id"),
        "client_id": row_dict.get("client_id"),
        "lat": row_dict.get("lat"),
        "lon": row_dict.get("lon"),
        "soil_source": SOIL_SOURCE,
        "soil_updated_at": now,
    }
    try:
        raw = fetch_soil(row_dict["lat"], row_dict["lon"])

        clay = raw.get("clay_pct")
        sand = raw.get("sand_pct")
        silt = raw.get("silt_pct")
        soc = raw.get("soc_g_kg")
        cfvo = raw.get("cfvo_30_60_pct")
        tipo = classify_texture(clay, sand, silt)
        pendiente = row_dict.get("pendiente_pct")

        return {
            **base,
            "clay_%": clay,
            "sand_%": sand,
            "silt_%": silt,
            "soc_g_kg": soc,
            "materia_organica_%": soc_to_mo_pct(soc),
            "cfvo_%": cfvo,
            "tipo_suelo": tipo,
            "drenaje": classify_drainage(tipo, pendiente),
            "profundidad_suelo_cm": estimate_depth(cfvo),
            "soil_status": "ok",
            "soil_error": "",
        }
    except Exception as exc:
        return {
            **base,
            "clay_%": None, "sand_%": None, "silt_%": None,
            "soc_g_kg": None, "materia_organica_%": None, "cfvo_%": None,
            "tipo_suelo": None, "drenaje": None, "profundidad_suelo_cm": None,
            "soil_status": "error",
            "soil_error": str(exc)[:250],
        }


def enrich_soil_for_client(
    client_id: str,
    ov_gdf: gpd.GeoDataFrame,
    max_workers: int = 3,
    progress_callback=None,
    update_mode: str = "errors_only",
) -> pd.DataFrame:
    """
    Consulta SoilGrids en paralelo, conservando datos válidos previos.

    Args:
        client_id: Identificador del cliente
        ov_gdf: GeoDataFrame de parcelas OV
        max_workers: Número de workers paralelos
        progress_callback: Función de progreso
        update_mode: "errors_only" (solo parcelas con error) o "force_all" (todas)

    Estrategia:
    1. Carga cache anterior si existe.
    2. Si update_mode="errors_only": identifica parcelas con error o sin dato.
    3. Si update_mode="force_all": consulta todas las parcelas.
    4. Consulta SoilGrids en paralelo.
    5. Combina: datos nuevos exitosos + datos previos válidos para fallidas + nuevos errores.
    6. Guarda cache combinado sin perder datos buenos.
    """
    required = {"parcel_uid", "parcel_id", "client_id", "lat", "lon"}
    missing = required - set(ov_gdf.columns)
    if missing:
        raise ValueError(f"GeoDataFrame falta columnas: {missing}")

    # Cargar cache anterior si existe
    prev_cache = load_soil_cache(client_id)
    prev_by_uid = {}
    if prev_cache is not None and not prev_cache.empty:
        prev_by_uid = {row["parcel_uid"]: row.to_dict() for _, row in prev_cache.iterrows()}

    # Determinar qué parcelas consultar según el modo
    extra_cols = list(required)
    if "pendiente_pct" in ov_gdf.columns:
        extra_cols.append("pendiente_pct")

    all_rows = ov_gdf[extra_cols].to_dict("records")
    to_fetch = all_rows

    if update_mode == "errors_only" and prev_cache is not None and not prev_cache.empty:
        # Solo reintenta parcelas con error o sin dato
        to_fetch = []
        for row in all_rows:
            uid = row["parcel_uid"]
            if uid not in prev_by_uid:
                # Sin dato previo → consultar
                to_fetch.append(row)
            else:
                prev = prev_by_uid[uid]
                if prev.get("soil_status") != "ok":
                    # Tiene error previo → reintenta
                    to_fetch.append(row)

    # Consultar en paralelo
    total = len(to_fetch)
    results_by_uid = {}

    if total > 0:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_row = {pool.submit(_fetch_one, row): row for row in to_fetch}
            done = 0
            for future in as_completed(future_to_row):
                result = future.result()
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
            if prev.get("soil_status") == "ok":
                # Dato previo válido → mantener, marcar como stale si se intentó consultar
                if uid in results_by_uid or update_mode == "force_all":
                    # Se intentó pero falló → marcar como stale
                    prev["soil_status"] = "stale"
                    prev["soil_error"] = "Consulta falló; manteniendo dato anterior"
                final_rows[uid] = prev
            else:
                # Dato previo con error → si hay nuevo resultado usarlo, si no dejar error
                final_rows[uid] = results_by_uid.get(uid, prev)
        else:
            # Sin dato previo ni nuevo → error
            if uid in results_by_uid:
                final_rows[uid] = results_by_uid[uid]
            else:
                # No debería pasar, pero por seguridad crear fila de error
                uid_row = next((r for r in all_rows if r["parcel_uid"] == uid), {})
                final_rows[uid] = {
                    "parcel_uid": uid,
                    "parcel_id": uid_row.get("parcel_id"),
                    "client_id": client_id,
                    "lat": uid_row.get("lat"),
                    "lon": uid_row.get("lon"),
                    "clay_%": None, "sand_%": None, "silt_%": None,
                    "soc_g_kg": None, "materia_organica_%": None, "cfvo_%": None,
                    "tipo_suelo": None, "drenaje": None, "profundidad_suelo_cm": None,
                    "soil_source": SOIL_SOURCE,
                    "soil_updated_at": datetime.now().isoformat(timespec="seconds"),
                    "soil_status": "no_data",
                    "soil_error": "Sin dato previo ni nueva consulta",
                }

    # Construir DataFrame final con columnas en orden
    df_final = pd.DataFrame(
        [final_rows[uid] for uid in [r["parcel_uid"] for r in all_rows]],
        columns=SOIL_COLS
    )
    _save_soil_cache(client_id, df_final)
    return df_final


def _save_soil_cache(client_id: str, df: pd.DataFrame) -> str:
    """Guarda cache de suelo, preservando estructura."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{client_id}_soil.csv")
    df.to_csv(path, index=False, sep=";")
    return path


def load_soil_cache(client_id: str) -> pd.DataFrame | None:
    """Carga cache de suelo con tipos correctos."""
    path = os.path.join(CACHE_DIR, f"{client_id}_soil.csv")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, sep=";", dtype=str)
        for col in ["clay_%", "sand_%", "silt_%", "soc_g_kg",
                    "materia_organica_%", "cfvo_%", "profundidad_suelo_cm", "lat", "lon"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return None


def get_soil_stats(soil_df: pd.DataFrame) -> dict:
    """Estadísticas de cobertura de suelo, incluyendo stale y no_data."""
    total = len(soil_df)
    ok = int((soil_df["soil_status"] == "ok").sum())
    stale = int((soil_df["soil_status"] == "stale").sum())
    errors = int((soil_df["soil_status"] == "error").sum())
    no_data = int((soil_df["soil_status"] == "no_data").sum())
    updated = soil_df["soil_updated_at"].max() if "soil_updated_at" in soil_df.columns else None

    return {
        "total": total,
        "ok": ok,
        "stale": stale,
        "errors": errors,
        "no_data": no_data,
        "pct_ok": round(ok / total * 100) if total > 0 else 0,
        "pct_complete": round((ok + stale) / total * 100) if total > 0 else 0,
        "updated_at": updated,
    }
