"""
Calculador de duración estimada de encharcamiento (días).
Reglas documentadas y revisables — NO es un modelo hidrológico certificado.
Todas las constantes están agrupadas para facilitar su ajuste.

Fórmula:
    duracion = base_rain × factor_drenaje × factor_pendiente
               + ajuste_humedad + ajuste_rio
    duracion = clip(round(duracion, 2), 0, MAX_DAYS)
"""
import math

import pandas as pd

MAX_DAYS = 7.0

# ------------------------------------------------------------------
# Constantes de reglas
# ------------------------------------------------------------------

# Base por lluvia 72h (mm) → días
RAIN_THRESHOLDS = [
    (0, 20, 0.0),    # < 20 mm → 0 días
    (20, 50, 0.5),   # 20-50 mm → 0.5 días
    (50, 100, 1.5),  # 50-100 mm → 1.5 días
    (100, math.inf, 3.0),  # ≥ 100 mm → 3 días
]

DRENAJE_FACTOR = {
    "Bueno": 0.5,
    "Moderado": 1.0,
    "Malo": 1.5,
    None: 1.0,
}

# Umbral pendiente (%) → factor
PENDIENTE_FACTOR = [
    (10, math.inf, 0.6),   # > 10% → escorrentía rápida
    (3, 10, 1.0),           # 3-10%
    (0, 3, 1.3),            # < 3% → zona llana → mayor acumulación
]

# Ajuste por humedad de suelo (%)
HUMEDAD_ADJUST = [
    (60, math.inf, 1.0),   # > 60% → suelo casi saturado
    (30, 60, 0.5),
    (0, 30, 0.0),           # suelo seco
]

RIVER_PROXIMITY_THRESHOLD_M = 100  # metros
RIVER_ADJUST = 0.5                 # días extra si parcela < 100m de cauce


# ------------------------------------------------------------------
# Funciones auxiliares
# ------------------------------------------------------------------
def _lookup(value, thresholds, default=None):
    """Busca en una lista [(low, high, result)] el resultado para value."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    for low, high, result in thresholds:
        if low <= value < high:
            return result
    return default


def calculate_waterlogging(
    rain_72h_mm=None,
    rain_7d_mm=None,
    humedad_suelo_pct=None,
    drenaje=None,
    pendiente_pct=None,
    distancia_rio_m=None,
) -> dict:
    """
    Calcula la duración estimada de encharcamiento para una parcela.

    Parámetros opcionales — si falta alguno se aplica valor neutro.
    Retorna dict con duracion_encharcamiento_dias y columnas de trazabilidad.
    """
    # Lluvia 72h: valor principal; fallback proporcional desde 7d
    rain = rain_72h_mm
    if rain is None and rain_7d_mm is not None:
        rain = rain_7d_mm * 3 / 7

    if rain is None:
        return {
            "duracion_encharcamiento_dias": None,
            "waterlogging_base_rain": None,
            "waterlogging_factor_drenaje": None,
            "waterlogging_factor_pendiente": None,
            "waterlogging_adjust_humedad": None,
            "waterlogging_adjust_river": None,
            "waterlogging_status": "sin_datos_lluvia",
        }

    base = _lookup(rain, RAIN_THRESHOLDS, default=0.0)
    f_drenaje = DRENAJE_FACTOR.get(drenaje, 1.0)
    f_pendiente = _lookup(pendiente_pct, PENDIENTE_FACTOR, default=1.0)
    adj_humedad = _lookup(humedad_suelo_pct, HUMEDAD_ADJUST, default=0.0)

    adj_rio = 0.0
    if distancia_rio_m is not None and not (isinstance(distancia_rio_m, float) and math.isnan(distancia_rio_m)):
        if distancia_rio_m < RIVER_PROXIMITY_THRESHOLD_M:
            adj_rio = RIVER_ADJUST

    duracion = base * f_drenaje * f_pendiente + adj_humedad + adj_rio
    duracion = round(min(max(duracion, 0.0), MAX_DAYS), 2)

    return {
        "duracion_encharcamiento_dias": duracion,
        "waterlogging_base_rain": base,
        "waterlogging_factor_drenaje": f_drenaje,
        "waterlogging_factor_pendiente": f_pendiente,
        "waterlogging_adjust_humedad": adj_humedad,
        "waterlogging_adjust_river": adj_rio,
        "waterlogging_status": "calculado",
    }


def calculate_waterlogging_for_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica el calculador fila a fila sobre un DataFrame con columnas de entrada.
    Añade la columna duracion_encharcamiento_dias (y columnas de trazabilidad opcionales).
    """
    results = []
    for _, row in df.iterrows():
        r = calculate_waterlogging(
            rain_72h_mm=_safe(row, "rain_72h_mm"),
            rain_7d_mm=_safe(row, "rain_7d_mm"),
            humedad_suelo_pct=_safe(row, "humedad_suelo_%"),
            drenaje=_safe_str(row, "drenaje"),
            pendiente_pct=_safe(row, "pendiente_%"),
            distancia_rio_m=_safe(row, "distancia_rio_m"),
        )
        results.append(r)

    out = df.copy()
    out["duracion_encharcamiento_dias"] = [r["duracion_encharcamiento_dias"] for r in results]
    return out


def get_waterlogging_risk_distribution(df: pd.DataFrame) -> dict:
    """Distribuye las parcelas por nivel de riesgo de encharcamiento."""
    col = "duracion_encharcamiento_dias"
    if col not in df.columns:
        return {}
    vals = pd.to_numeric(df[col], errors="coerce")
    return {
        "sin_riesgo": int((vals == 0).sum()),
        "bajo": int(((vals > 0) & (vals <= 1)).sum()),
        "moderado": int(((vals > 1) & (vals <= 3)).sum()),
        "alto": int((vals > 3).sum()),
        "sin_datos": int(vals.isna().sum()),
    }


def _safe(row, col):
    v = row.get(col) if hasattr(row, "get") else None
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _safe_str(row, col):
    v = row.get(col) if hasattr(row, "get") else None
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s if s and s.lower() != "nan" else None
