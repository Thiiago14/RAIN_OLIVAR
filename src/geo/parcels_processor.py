import hashlib

import geopandas as gpd
import pandas as pd

TARGET_CRS_METRIC = "EPSG:32630"
TARGET_CRS_WEB = "EPSG:4326"

# Campos SIGPAC que componen el identificador estable de recinto
_SIGPAC_UID_FIELDS = ["provincia", "municipio", "poligono", "parcela", "recinto"]


def make_parcel_uid(row) -> str:
    """
    Construye un identificador estable a partir de los campos SIGPAC.
    Si algún campo falta, genera un hash SHA-256 de la geometría WKB.
    Formato SIGPAC: {prov:02d}-{mun:03d}-{pol:05d}-{par:05d}-{rec:03d}
    """
    try:
        missing = [f for f in _SIGPAC_UID_FIELDS if f not in row.index or pd.isna(row[f])]
        if missing:
            raise ValueError(f"Campos SIGPAC ausentes: {missing}")
        return (
            f"{int(row['provincia']):02d}"
            f"-{int(row['municipio']):03d}"
            f"-{int(row['poligono']):05d}"
            f"-{int(row['parcela']):05d}"
            f"-{int(row['recinto']):03d}"
        )
    except (KeyError, ValueError, TypeError):
        wkb = row.geometry.wkb
        return "geo_" + hashlib.sha256(wkb).hexdigest()[:16]


def process_parcels(gdf: gpd.GeoDataFrame, client_id: str) -> gpd.GeoDataFrame:
    gdf = gdf.copy()

    # --- Corregir geometrías inválidas ---
    invalid_mask = ~gdf.geometry.is_valid
    if invalid_mask.any():
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].buffer(0)

    # --- Asegurar CRS métrico para cálculo de área ---
    if gdf.crs is None:
        raise ValueError("El GeoDataFrame no tiene CRS definido.")

    if gdf.crs.to_epsg() != 32630:
        gdf = gdf.to_crs(TARGET_CRS_METRIC)

    # --- Calcular área en hectáreas ---
    gdf["area_m2"] = gdf.geometry.area
    gdf["area_ha_calc"] = (gdf["area_m2"] / 10000).round(4)

    # --- Generar identificadores ---
    gdf = gdf.reset_index(drop=True)
    gdf["parcel_id"] = [f"{client_id}_P{str(i + 1).zfill(3)}" for i in range(len(gdf))]
    gdf["client_id"] = client_id
    # parcel_uid: identificador estable basado en campos SIGPAC
    gdf["parcel_uid"] = gdf.apply(make_parcel_uid, axis=1)

    # --- Calcular centroides (en CRS métrico) ---
    gdf["centroid_x"] = gdf.geometry.centroid.x
    gdf["centroid_y"] = gdf.geometry.centroid.y

    # --- Columnas de SIGPAC útiles disponibles ---
    # pendiente_ → pendiente_pct, altitud → altitud_m
    if "pendiente_" in gdf.columns:
        gdf["pendiente_pct"] = pd.to_numeric(gdf["pendiente_"], errors="coerce")
    if "altitud" in gdf.columns:
        gdf["altitud_m"] = pd.to_numeric(gdf["altitud"], errors="coerce")

    # --- Centroides en CRS métrico → reproyyectar a WGS84 ---
    centroids_metric = gdf.geometry.centroid
    centroids_gdf = gpd.GeoDataFrame(geometry=centroids_metric, crs=gdf.crs)
    centroids_web = centroids_gdf.to_crs(TARGET_CRS_WEB)

    # --- Convertir polígonos a EPSG:4326 para visualización web ---
    gdf_web = gdf.to_crs(TARGET_CRS_WEB)
    gdf_web["lon"] = centroids_web.geometry.x
    gdf_web["lat"] = centroids_web.geometry.y

    return gdf_web


def get_kpis(gdf: gpd.GeoDataFrame) -> dict:
    return {
        "n_parcelas": len(gdf),
        "superficie_total_ha": round(gdf["area_ha_calc"].sum(), 2),
        "superficie_media_ha": round(gdf["area_ha_calc"].mean(), 2),
        "superficie_max_ha": round(gdf["area_ha_calc"].max(), 2),
        "superficie_min_ha": round(gdf["area_ha_calc"].min(), 2),
    }
