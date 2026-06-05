"""
Cliente HTTP para SoilGrids v2.0 (ISRIC).
https://rest.isric.org/soilgrids/v2.0/

Variables consultadas:
  clay, sand, silt  → textura del suelo (%)
  soc               → carbono orgánico → materia orgánica (g/kg → MO%)
  cfvo              → fragmentos gruesos → proxy de profundidad (%)

Unidades después de dividir por d_factor:
  clay / sand / silt : %
  soc                : g/kg
  cfvo               : cm³/100cm³ = %
"""
import requests

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ["clay", "sand", "silt", "soc", "cfvo"]
DEPTHS = ["0-5cm", "5-15cm", "30-60cm"]
TIMEOUT_S = 45


def fetch_soil(lat: float, lon: float) -> dict:
    """
    Consulta SoilGrids para un punto geográfico en WGS84.

    Retorna dict con:
        clay_pct, sand_pct, silt_pct   – textura topsoil promedio 0-15cm (%)
        soc_g_kg                        – SOC 0-5cm (g/kg)
        cfvo_30_60_pct                  – fragmentos gruesos 30-60cm (%)

    Lanza requests.HTTPError o requests.Timeout en caso de fallo.
    """
    params = [("lon", round(lon, 6)), ("lat", round(lat, 6)), ("value", "mean")]
    for prop in PROPERTIES:
        params.append(("property", prop))
    for depth in DEPTHS:
        params.append(("depth", depth))

    resp = requests.get(
        SOILGRIDS_URL,
        params=params,
        headers={"Accept": "application/json"},
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    return _parse_response(resp.json())


def _get_layer_value(layers: list, prop_name: str, depth_label: str) -> float | None:
    """Extrae el valor mean de una propiedad/profundidad y aplica d_factor."""
    for layer in layers:
        if layer.get("name") != prop_name:
            continue
        d_factor = layer.get("unit_measure", {}).get("d_factor") or 1
        for depth in layer.get("depths", []):
            if depth.get("label") == depth_label:
                raw = depth.get("values", {}).get("mean")
                if raw is not None:
                    return round(raw / d_factor, 2)
    return None


def _parse_response(data: dict) -> dict:
    layers = data.get("properties", {}).get("layers", [])

    def avg(*values):
        valid = [v for v in values if v is not None]
        return round(sum(valid) / len(valid), 2) if valid else None

    # Textura: promedio 0-5cm y 5-15cm
    clay = avg(
        _get_layer_value(layers, "clay", "0-5cm"),
        _get_layer_value(layers, "clay", "5-15cm"),
    )
    sand = avg(
        _get_layer_value(layers, "sand", "0-5cm"),
        _get_layer_value(layers, "sand", "5-15cm"),
    )
    silt = avg(
        _get_layer_value(layers, "silt", "0-5cm"),
        _get_layer_value(layers, "silt", "5-15cm"),
    )

    soc_g_kg = _get_layer_value(layers, "soc", "0-5cm")
    cfvo_30_60 = _get_layer_value(layers, "cfvo", "30-60cm")

    return {
        "clay_pct": clay,
        "sand_pct": sand,
        "silt_pct": silt,
        "soc_g_kg": soc_g_kg,
        "cfvo_30_60_pct": cfvo_30_60,
    }
