"""
Cliente para Overpass API (OpenStreetMap).
Estrategia: UNA sola consulta por bbox del cliente (no por parcela),
devuelve todos los elementos de agua encontrados en el área.

URL: https://overpass-api.de/api/interpreter  (GET)
Sin API key. Gratuito. Respetar rate limits con User-Agent.
"""
import math

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
TIMEOUT_S = 45
USER_AGENT = "RAIN-OLIVAR/1.0 (agricultural risk analysis)"

WATER_TAGS = '["waterway"~"river|stream|ditch"]'
NATURE_TAGS = '["natural"="water"]'


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos WGS84."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------
def _expand_bbox(south: float, west: float, north: float, east: float, radius_m: int) -> tuple:
    """Expande la bbox en ~radius_m metros en cada dirección."""
    d_lat = radius_m / 111_000
    mean_lat = (south + north) / 2
    d_lon = radius_m / (111_000 * max(math.cos(math.radians(mean_lat)), 0.01))
    return south - d_lat, west - d_lon, north + d_lat, east + d_lon


def _build_query(south: float, west: float, north: float, east: float) -> str:
    bb = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    return (
        f"[out:json][timeout:{TIMEOUT_S}];"
        f"(way{WATER_TAGS}({bb});"
        f"node{WATER_TAGS}({bb});"
        f"way{NATURE_TAGS}({bb});"
        f"node{NATURE_TAGS}({bb}););"
        f"out center tags;"
    )


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def fetch_water_features(
    south: float,
    west: float,
    north: float,
    east: float,
    radius_m: int = 5000,
) -> list[dict]:
    """
    Consulta Overpass API para obtener elementos de agua en el área.
    Devuelve lista de dicts con: lat, lon, wtype, wname.
    Prueba múltiples servidores si el primero falla.
    """
    s, w, n, e = _expand_bbox(south, west, north, east, radius_m)
    query = _build_query(s, w, n, e)

    last_exc = None
    for url in OVERPASS_URLS:
        try:
            resp = requests.get(
                url,
                params={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_S,
            )
            resp.raise_for_status()
            return _parse_elements(resp.json().get("elements", []))
        except Exception as exc:
            last_exc = exc
            continue

    raise RuntimeError(f"Overpass no disponible: {last_exc}")


def _parse_elements(elements: list) -> list[dict]:
    """Extrae coordenadas y metadatos de cada elemento OSM."""
    features = []
    for elem in elements:
        # Coordenadas: nodo tiene lat/lon; way tiene center
        if elem.get("type") == "node":
            lat = elem.get("lat")
            lon = elem.get("lon")
        else:
            center = elem.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        tags = elem.get("tags", {})
        wtype = (
            tags.get("waterway")
            or tags.get("water")
            or tags.get("natural")
            or "water"
        )
        wname = tags.get("name") or tags.get("name:es") or ""
        features.append({"lat": lat, "lon": lon, "wtype": wtype, "wname": wname})

    return features


def nearest_feature(
    lat: float,
    lon: float,
    features: list[dict],
) -> tuple[float | None, str | None, str | None]:
    """
    Encuentra el elemento de agua más cercano al punto dado.
    Retorna (distancia_m, wtype, wname) o (None, None, None) si no hay elementos.
    """
    if not features:
        return None, None, None

    best_dist = float("inf")
    best_type = None
    best_name = None

    for f in features:
        d = haversine(lat, lon, f["lat"], f["lon"])
        if d < best_dist:
            best_dist = d
            best_type = f["wtype"]
            best_name = f["wname"]

    return round(best_dist), best_type, best_name
