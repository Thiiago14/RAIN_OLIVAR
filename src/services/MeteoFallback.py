"""
Wrapper de meteorología con fallback automático variable-por-variable.
Intenta primero la estación propia IoT; si falla, usa Open-Meteo para esa variable específica.

Registra trazabilidad de origen en self.origen_variables.
Detecta sensores colgados (desviación estándar = 0 en ventana reciente).
"""
import pandas as pd
import numpy as np
from loguru import logger

from src.services.EstacionMeteorologica import EstacionMeteorologica
from src.services.ConstructorVariablesMeteo import ConstructorVariablesMeteo
from src.integrations.open_meteo_client import fetch_weather


class MeteoConFallback:
    """
    Orquesta la obtención de variables meteorológicas con fallback granular.

    Para cada variable del modelo ML:
      1. Intenta obtenerla desde la estación propia (ConstructorVariablesMeteo)
      2. Si retorna None/NaN o lanza excepción → Open-Meteo para ESA variable
      3. Registra qué fuente se usó en self.origen_variables

    Uso:
        wrapper = MeteoConFallback(estacion, client_id="cliente_1")
        meteo, hms, origen = wrapper.construir_variables_completas(lat, lon)
    """

    def __init__(
        self,
        estacion: EstacionMeteorologica,
        finca_id: str | None = None,
    ):
        self.estacion = estacion
        self.finca_id = finca_id
        self.constructor = ConstructorVariablesMeteo(estacion, finca_id)
        self.origen_variables: dict[str, str] = {}
        self._sensores_no_fiables: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def construir_variables_completas(
        self,
        lat: float | None = None,
        lon: float | None = None,
    ) -> tuple[dict, dict, dict]:
        """
        Orquesta la obtención de todas las variables con fallback.

        Args:
            lat, lon: coordenadas para Open-Meteo fallback (necesarias si la estación falla)

        Returns:
            (variables_meteo, variables_hms, origen_variables)
            - variables_meteo: dict con las 4+1 variables para el ML
            - variables_hms: dict con variables para HMS (o None si no hay datos)
            - origen_variables: dict con la fuente usada por cada variable
        """
        self.origen_variables = {}

        # SIEMPRE intentar estación primero (con fallback variable-por-variable)
        # Solo caer en Open-Meteo completo si la estación no tiene NINGÚN dato
        try:
            variables_meteo = self._obtener_meteo_con_fallback(lat, lon)
            variables_hms = self._obtener_hms_seguro()
            
            # Verificar si al menos una variable vino de la estación
            fuentes_estacion = [v for v in self.origen_variables.values() 
                              if 'sensor_propio' in v]
            if not fuentes_estacion:
                logger.warning("Estación propia no aportó ninguna variable, "
                             "todas vinieron de Open-Meteo o sin datos")
        except Exception as e:
            logger.error(f"Error crítico obteniendo variables: {e}")
            variables_meteo = self._obtener_open_meteo_completo(lat, lon)
            variables_hms = {
                "lluvia_serie_30min": None,
                "amc_calculado": "II",
                "rain_5d_mm": None,
                "eto_acumulada_7d": None,
            }

        return variables_meteo, variables_hms, dict(self.origen_variables)

    def validar_sensor(
        self, variable: str, df: pd.DataFrame, ventana_horas: int = 6
    ) -> bool:
        """
        Detecta sensores colgados: si la desviación estándar de los últimos
        registros en la ventana es 0.0, el sensor se marca como no fiable.

        Returns:
            True si el sensor es fiable, False si está colgado.
        """
        if df.empty or variable not in df.columns:
            return False

        # Filtrar por ventana temporal
        if "update" in df.columns:
            cutoff = pd.Timestamp.now() - pd.Timedelta(hours=ventana_horas)
            recent = df[df["update"] >= cutoff][variable].dropna()
        else:
            recent = df[variable].dropna()

        if recent.empty:
            return False

        std = recent.std()
        if std == 0.0 and len(recent) > 1:
            logger.warning(
                f"Sensor '{variable}' colgado: std=0 en {len(recent)} registros"
            )
            self._sensores_no_fiables.add(variable)
            return False

        return True

    # ------------------------------------------------------------------
    # Meteo con fallback variable-por-variable
    # ------------------------------------------------------------------

    def _obtener_meteo_con_fallback(
        self, lat: float | None, lon: float | None
    ) -> dict:
        """
        Obtiene cada variable ML con fallback individual a Open-Meteo.

        Prioridad: estación propia → Open-Meteo.
        Si la estación devuelve un valor (incluido 0.0), se usa directamente.
        Solo cae en Open-Meteo si la estación retorna None/NaN.
        """
        # Intentar estación propia
        try:
            vars_propias = self.constructor.construir_variables_modelo()
        except Exception as e:
            logger.warning(f"Error obteniendo variables de estación: {e}")
            vars_propias = {}

        # Open-Meteo como respaldo
        open_meteo = None
        if lat is not None and lon is not None:
            try:
                open_meteo = fetch_weather(lat, lon)
            except Exception as e:
                logger.warning(f"Open-Meteo fallback falló: {e}")

        # Combinar variable por variable: estación primero, Open-Meteo solo si falta
        result = {}
        for var in ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%"]:
            val_propio = vars_propias.get(var)
            val_om = open_meteo.get(var) if open_meteo else None

            if val_propio is not None and not _is_nan(val_propio):
                result[var] = val_propio
                self.origen_variables[var] = "sensor_propio"
            elif val_om is not None and not _is_nan(val_om):
                result[var] = val_om
                self.origen_variables[var] = "open_meteo_fallback"
            else:
                result[var] = None
                self.origen_variables[var] = "sin_datos"

        # ETo solo desde estación propia (Open-Meteo no lo provee directamente)
        # ETo es un CÁLCULO derivado de múltiples sensores (temp, humidity, rSolar, wind)
        eto = vars_propias.get("eto_penman_mm")
        if eto is not None and not _is_nan(eto):
            result["eto_penman_mm"] = eto
            self.origen_variables["eto_penman_mm"] = "calculado_estacion"
        else:
            result["eto_penman_mm"] = None
            self.origen_variables["eto_penman_mm"] = "sin_datos"

        return result

    def _obtener_open_meteo_completo(
        self, lat: float | None, lon: float | None
    ) -> dict:
        """Cuando la estación no está disponible, todo desde Open-Meteo."""
        if lat is None or lon is None:
            return {
                "rain_72h_mm": None,
                "rain_7d_mm": None,
                "temp_media_7d": None,
                "humedad_suelo_%": None,
                "eto_penman_mm": None,
            }

        try:
            om = fetch_weather(lat, lon)
            for var in ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%"]:
                self.origen_variables[var] = "open_meteo"
            self.origen_variables["eto_penman_mm"] = "sin_datos"
            return {
                "rain_72h_mm": om.get("rain_72h_mm"),
                "rain_7d_mm": om.get("rain_7d_mm"),
                "temp_media_7d": om.get("temp_media_7d"),
                "humedad_suelo_%": om.get("humedad_suelo_%"),
                "eto_penman_mm": None,  # Open-Meteo no provee ETo directamente
            }
        except Exception as e:
            logger.warning(f"Open-Meteo falló completamente: {e}")
            for var in ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%", "eto_penman_mm"]:
                self.origen_variables[var] = "error"
            return {
                "rain_72h_mm": None,
                "rain_7d_mm": None,
                "temp_media_7d": None,
                "humedad_suelo_%": None,
                "eto_penman_mm": None,
            }

    def _obtener_hms_seguro(self) -> dict:
        """Obtiene variables HMS con manejo de errores."""
        try:
            return self.constructor.construir_variables_hms()
        except Exception as e:
            logger.warning(f"Error obteniendo variables HMS: {e}")
            return {
                "lluvia_serie_30min": None,
                "amc_calculado": "II",
                "rain_5d_mm": None,
                "eto_acumulada_7d": None,
            }

    @staticmethod
    def _variable_to_sensor(var_name: str) -> str | None:
        """Mapea variable ML al nombre del sensor en el CSV."""
        mapping = {
            "rain_72h_mm": "pluviometer",
            "rain_7d_mm": "pluviometer",
            "temp_media_7d": "temperature",
            "humedad_suelo_%": "humidity",
        }
        return mapping.get(var_name)


def _is_nan(val) -> bool:
    """Verifica si un valor es NaN o None."""
    if val is None:
        return True
    try:
        return pd.isna(val) or (isinstance(val, float) and np.isnan(val))
    except (TypeError, ValueError):
        return False
