"""
Endpoints de hidrología y meteorología para fincas.

GET /api/finca/{finca_id}/hidrograma  — modelo HMS completo
GET /api/finca/{finca_id}/meteo/resumen — resumen meteorológico 7 días
"""
import glob
import os

import numpy as np
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _find_shapefile(finca_id: str) -> str | None:
    """Busca el shapefile de una finca/cliente."""
    patterns = [
        f"data/clientes_shp/{finca_id}/**/*.shp",
        f"data/clientes_shp/{finca_id}/*.shp",
    ]
    for pattern in patterns:
        files = glob.glob(pattern, recursive=True)
        if files:
            return files[0]
    return None


@router.get("/finca/{finca_id}/hidrograma")
def get_hidrograma(
    finca_id: str,
    dias_historico: int = Query(default=3, ge=1, le=30),
    uso_suelo: str = Query(default="cultivos"),
    grupo_hidrologico: str = Query(default="B"),
):
    """
    Ejecuta el modelo hidrológico HMS para una finca.

    Retorna: CN, Tc, AMC, caudal pico, tiempo pico, escorrentía, ETo,
    origen de variables meteorológicas, y series del hidrograma.
    """
    from src.services.EstacionMeteorologica import EstacionMeteorologica
    from src.services.ConstructorVariablesMeteo import ConstructorVariablesMeteo
    from src.services.MeteoFallback import MeteoConFallback
    from src.hms.ModeloHMS import FincaHMS

    # 1. Buscar shapefile
    shp_path = _find_shapefile(finca_id)
    if not shp_path:
        raise HTTPException(
            status_code=404,
            detail=f"Shapefile no encontrado para finca '{finca_id}'",
        )

    # 2. Estación meteorológica + fallback
    estacion = EstacionMeteorologica(fuente="csv")
    wrapper = MeteoConFallback(estacion, finca_id=None)

    # Obtener centroide de la finca para fallback
    try:
        import geopandas as gpd
        gdf = gpd.read_file(shp_path)
        gdf_wgs = gdf.to_crs("EPSG:4326")
        centroid = gdf_wgs.geometry.centroid.iloc[0]
        lat, lon = centroid.y, centroid.x
    except Exception:
        lat, lon = None, None

    meteo, hms_vars, origen = wrapper.construir_variables_completas(lat=lat, lon=lon)

    # 3. Modelo HMS
    try:
        hms = FincaHMS(shp_path)

        # Intentar DEM (no bloqueante)
        try:
            hms.descargar_dem(output=f"{finca_id}_dem.tif")
        except Exception:
            pass

        params = hms.calcular_parametros_morfometricos()

        # Serie de lluvia
        if hms_vars and hms_vars.get("lluvia_serie_30min") is not None:
            lluvia = hms_vars["lluvia_serie_30min"]
        else:
            serie = estacion.get_serie_pluviometrica(intervalo_min=30)
            lluvia = serie.values if not serie.empty else np.zeros(48)

        amc = hms_vars.get("amc_calculado", "II") if hms_vars else "II"

        t, Q, metadata = hms.calcular_hidrograma(
            lluvia, dt_h=0.5,
            uso_suelo=uso_suelo,
            grupo_hidrologico=grupo_hidrologico,
            AMC=amc,
        )

        return {
            "finca_id": finca_id,
            "CN": metadata.get("CN"),
            "Tc_horas": params.get("Tc_horas"),
            "AMC": amc,
            "caudal_pico_m3s": metadata.get("caudal_pico_m3s"),
            "tiempo_pico_h": metadata.get("tiempo_pico_h"),
            "escorrentia_mm": metadata.get("escorrentia_acumulada_mm"),
            "eto_penman_mm": meteo.get("eto_penman_mm"),
            "origen_variables": origen,
            "hidrograma": {
                "tiempo_h": t.tolist(),
                "caudal_m3s": Q.tolist(),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error modelo HMS: {str(e)}")


@router.get("/finca/{finca_id}/meteo/resumen")
def get_meteo_resumen(finca_id: str):
    """
    Resumen meteorológico de los últimos 7 días con estadísticos básicos
    (media, min, max, último valor) para cada sensor disponible.
    """
    from src.services.EstacionMeteorologica import EstacionMeteorologica

    estacion = EstacionMeteorologica(fuente="csv")

    try:
        df = estacion.get_historico(dias=7, finca_id=None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando datos: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=404, detail="No hay datos meteorológicos disponibles")

    # Columnas de sensores a resumir
    sensor_cols = [
        "temperature", "humidity", "pluviometer", "pressure",
        "rSolar", "rPar", "uv", "windVelocity", "windMax",
        "temperatureMax", "temperatureMin", "humidityMax", "humidityMin",
    ]

    resumen = {}
    for col in sensor_cols:
        if col not in df.columns:
            continue
        vals = df[col].dropna()
        if vals.empty:
            continue

        resumen[col] = {
            "media": round(float(vals.mean()), 2),
            "min": round(float(vals.min()), 2),
            "max": round(float(vals.max()), 2),
            "ultimo": round(float(vals.iloc[-1]), 2),
            "n_registros": int(len(vals)),
        }

    # Metadata
    estaciones = df["gatewayOut"].unique().tolist() if "gatewayOut" in df.columns else []
    update_range = {
        "desde": str(df["update"].min()) if "update" in df.columns else None,
        "hasta": str(df["update"].max()) if "update" in df.columns else None,
    }

    return {
        "finca_id": finca_id,
        "estaciones": estaciones,
        "periodo": update_range,
        "total_registros": len(df),
        "resumen_sensores": resumen,
    }
