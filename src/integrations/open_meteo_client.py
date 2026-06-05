"""
Cliente HTTP para Open-Meteo (https://open-meteo.com).
No requiere API key. Datos históricos disponibles hasta 92 días atrás.

Variables consultadas:
  hourly: precipitation, soil_moisture_0_to_7cm
  daily:  precipitation_sum, temperature_2m_mean
"""
import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 30


def fetch_weather(lat: float, lon: float) -> dict:
    """
    Consulta Open-Meteo para un punto geográfico.

    Retorna dict con:
        rain_72h_mm    – Precipitación acumulada últimas 72 h (mm)
        rain_7d_mm     – Precipitación acumulada últimos 7 días (mm)
        temp_media_7d  – Temperatura media últimos 7 días (°C)
        humedad_suelo_pct – Humedad volumétrica suelo 0-7 cm × 100 (%)

    Lanza requests.HTTPError o requests.Timeout en caso de fallo.
    """
    params = {
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "hourly": "precipitation,soil_moisture_0_to_7cm",
        "daily": "precipitation_sum,temperature_2m_mean",
        "past_days": 8,
        "forecast_days": 1,
        "timezone": "auto",
    }

    resp = requests.get(FORECAST_URL, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return _parse_response(resp.json())


def _parse_response(data: dict) -> dict:
    hourly = data.get("hourly", {})
    daily = data.get("daily", {})

    h_precip = hourly.get("precipitation", [])
    h_soil = hourly.get("soil_moisture_0_to_7cm", [])
    d_precip = daily.get("precipitation_sum", [])
    d_temp = daily.get("temperature_2m_mean", [])

    # rain_72h_mm — suma últimas 72 entradas horarias
    p72 = [v for v in h_precip[-72:] if v is not None]
    rain_72h = round(sum(p72), 2) if p72 else None

    # rain_7d_mm — suma últimos 7 días daily (excluye día de forecast)
    p7 = [v for v in d_precip[-8:-1] if v is not None]
    if not p7:
        p7 = [v for v in d_precip[-7:] if v is not None]
    rain_7d = round(sum(p7), 2) if p7 else None

    # temp_media_7d — media últimos 7 días daily
    t7 = [v for v in d_temp[-8:-1] if v is not None]
    if not t7:
        t7 = [v for v in d_temp[-7:] if v is not None]
    temp_media = round(sum(t7) / len(t7), 1) if t7 else None

    # humedad_suelo_% — media de las últimas 24 horas válidas × 100
    s24 = [v for v in h_soil[-24:] if v is not None]
    humedad = round((sum(s24) / len(s24)) * 100, 1) if s24 else None

    return {
        "rain_72h_mm": rain_72h,
        "rain_7d_mm": rain_7d,
        "temp_media_7d": temp_media,
        "humedad_suelo_%": humedad,
    }
