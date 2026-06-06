"""
Constructor de variables meteorológicas derivadas desde la estación IoT.
Produce las variables que alimentan el modelo ML (22 cols) y el modelo HMS.

Variables ML sustituidas:
  - rain_72h_mm, rain_7d_mm, temp_media_7d, humedad_suelo_%

Variables HMS adicionales:
  - lluvia_serie_30min, amc_calculado, rain_5d_mm, eto_acumulada_7d
"""
import numpy as np
import pandas as pd
from loguru import logger

from src.services.EstacionMeteorologica import EstacionMeteorologica


class ConstructorVariablesMeteo:
    """
    Deriva variables meteorológicas agregadas desde series crudas de la estación.

    Uso:
        estacion = EstacionMeteorologica()
        constructor = ConstructorVariablesMeteo(estacion)
        vars_ml  = constructor.construir_variables_modelo()
        vars_hms = constructor.construir_variables_hms()
    """

    def __init__(self, estacion: EstacionMeteorologica, finca_id: str | None = None):
        self.estacion = estacion
        self.finca_id = finca_id

    # ------------------------------------------------------------------
    # Variables para modelo ML (sustituyen Open-Meteo)
    # ------------------------------------------------------------------

    def construir_variables_modelo(self) -> dict:
        """
        Retorna dict con las 4 columnas meteorológicas del CSV de 22 columnas
        que actualmente se obtienen de Open-Meteo.

        Returns:
            dict: {rain_72h_mm, rain_7d_mm, temp_media_7d, humedad_suelo_%, eto_penman_mm}
        """
        df_7d = self.estacion.get_ultimas_horas(horas=168, finca_id=self.finca_id)  # 7 días
        df_72h = self.estacion.get_ultimas_horas(horas=72, finca_id=self.finca_id)

        rain_72h = self._sumar_lluvia(df_72h, horas=72)
        rain_7d = self._sumar_lluvia(df_7d, horas=168)
        temp_media_7d = self._media_columna(df_7d, "temperature", horas=168)
        humedad_suelo = self._media_columna(df_7d, "humidity", horas=24)  # proxy superficial
        eto_penman = self._eto_media_7d(df_7d)

        return {
            "rain_72h_mm": _round(rain_72h),
            "rain_7d_mm": _round(rain_7d),
            "temp_media_7d": _round(temp_media_7d),
            "humedad_suelo_%": _round(humedad_suelo),
            "eto_penman_mm": _round(eto_penman),
        }

    # ------------------------------------------------------------------
    # Variables para modelo HMS
    # ------------------------------------------------------------------

    def construir_variables_hms(self) -> dict:
        """
        Retorna dict con variables de entrada al modelo hidrológico HMS.

        Returns:
            dict: {lluvia_serie_30min, amc_calculado, rain_5d_mm, eto_acumulada_7d}
        """
        serie_pluvio = self.estacion.get_serie_pluviometrica(
            intervalo_min=30, finca_id=self.finca_id
        )
        df_5d = self.estacion.get_ultimas_horas(horas=120, finca_id=self.finca_id)
        df_7d = self.estacion.get_ultimas_horas(horas=168, finca_id=self.finca_id)

        # Lluvia incremental cada 30 min (últimos 7 días para HMS)
        lluvia_30min = serie_pluvio.values if not serie_pluvio.empty else np.array([])

        # Rain 5d para AMC
        rain_5d = self._sumar_lluvia(df_5d, horas=120)

        # AMC
        amc = self.calcular_amc(df_5d)

        # ETo acumulada 7 días
        eto_acum = self._eto_acumulada_7d(df_7d)

        return {
            "lluvia_serie_30min": lluvia_30min,
            "amc_calculado": amc,
            "rain_5d_mm": _round(rain_5d),
            "eto_acumulada_7d": _round(eto_acum),
        }

    # ------------------------------------------------------------------
    # ETo Penman-Monteith FAO-56 simplificada
    # ------------------------------------------------------------------

    def calcular_eto_penman_fao56(self, df: pd.DataFrame) -> float:
        """
        Calcula ETo diaria media usando Penman-Monteith FAO-56 simplificada.

        Usa los campos de la estación:
          - temperature (°C)
          - humidity (%)
          - rSolar (W/m²) → convertir a MJ/m²/día × 0.0864
          - windVelocity (m/s)

        Returns:
            ETo en mm/día. Retorna None si no hay datos suficientes.
        """
        if df.empty:
            return None

        T = df["temperature"].dropna()
        HR = df["humidity"].dropna()
        Rs_W = df["rSolar"].dropna() if "rSolar" in df.columns else pd.Series(dtype=float)
        wind = df["windVelocity"].dropna() if "windVelocity" in df.columns else pd.Series(dtype=float)

        if T.empty or HR.empty:
            return None

        T_mean = T.mean()
        HR_mean = HR.mean()
        Rs_W_mean = Rs_W.mean() if not Rs_W.empty else 0.0
        wind_mean = wind.mean() if not wind.empty else 2.0  # default 2 m/s

        # Convertir radiación W/m² → MJ/m²/día
        Rs_MJ = Rs_W_mean * 0.0864

        # Presión de vapor de saturación [kPa]
        es = 0.6108 * np.exp(17.27 * T_mean / (T_mean + 237.3))

        # Presión de vapor real [kPa]
        ea = (HR_mean / 100.0) * es

        # Pendiente de la curva de presión de vapor [kPa/°C]
        delta = 4098.0 * es / (T_mean + 237.3) ** 2

        # Constante psicrométrica [kPa/°C]
        gamma = 0.0665

        # Radiación neta [MJ/m²/día]
        Rn = 0.77 * Rs_MJ - 2.5
        Rn = max(Rn, 0.0)  # no puede ser negativa

        # Penman-Monteith combinada [mm/día]
        numerator = (
            0.408 * delta * Rn
            + gamma * (900.0 / (T_mean + 273.0)) * wind_mean * (es - ea)
        )
        denominator = delta + gamma * (1.0 + 0.34 * wind_mean)

        if denominator == 0:
            return None

        eto = numerator / denominator
        return max(eto, 0.0)  # ETo no puede ser negativa

    # ------------------------------------------------------------------
    # AMC — Condición de Humedad Antecedente (SCS)
    # ------------------------------------------------------------------

    def calcular_amc(self, df_5d: pd.DataFrame) -> str:
        """
        Determina la Condición de Humedad Antecedente (AMC) según SCS.

        Tabla estándar:
          - rain_5d < 35 mm  → AMC-I  (seco)
          - 35–53 mm         → AMC-II (normal)
          - > 53 mm          → AMC-III (húmedo)

        Returns:
            'I', 'II' o 'III'
        """
        rain_5d = self._sumar_lluvia(df_5d, horas=120)
        if rain_5d is None:
            return "II"  # default normal si no hay datos

        if rain_5d < 35.0:
            return "I"
        elif rain_5d <= 53.0:
            return "II"
        else:
            return "III"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sumar_lluvia(self, df: pd.DataFrame, horas: int) -> float | None:
        """Suma lluvia incremental en la ventana de horas indicada."""
        if df.empty or "pluviometer" not in df.columns:
            return None

        pluvio = df[["update", "pluviometer"]].dropna(subset=["pluviometer"])
        if pluvio.empty:
            return None

        pluvio = pluvio.sort_values("update")
        vals = pluvio["pluviometer"].values

        # Lluvia = diff con clip para resets
        diffs = np.diff(vals)
        diffs = np.clip(diffs, 0, None)

        return float(np.sum(diffs)) if len(diffs) > 0 else None

    def _media_columna(self, df: pd.DataFrame, columna: str, horas: int) -> float | None:
        """Media de una columna en la ventana temporal."""
        if df.empty or columna not in df.columns:
            return None
        vals = df[columna].dropna()
        if vals.empty:
            return None
        return float(vals.mean())

    def _eto_media_7d(self, df: pd.DataFrame) -> float | None:
        """ETo media diaria de los últimos 7 días."""
        return self.calcular_eto_penman_fao56(df)

    def _eto_acumulada_7d(self, df: pd.DataFrame) -> float | None:
        """ETo acumulada en 7 días (ETo diaria × 7)."""
        eto_diaria = self.calcular_eto_penman_fao56(df)
        if eto_diaria is None:
            return None
        return eto_diaria * 7.0


def _round(val: float | None, digits: int = 2) -> float | None:
    """Redondeo seguro que acepta None."""
    if val is None:
        return None
    return round(val, digits)
