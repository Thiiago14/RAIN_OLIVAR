"""
Servicio de acceso a la base meteorológica propia (sensores IoT FIWARE).
Descarga datos desde CSV público, con cache local y soporte para múltiples estaciones.

Fuente: https://portal.atdfiware.uco.es/file/datahub/ac91a79d-9498-4465-b563-ffe2a54201d8.csv
Formato: FIWARE NGSI con campos JSON embebidos (entity_location, location).
"""
import json
import os
from datetime import datetime, timedelta

import pandas as pd
import requests
from loguru import logger

DEFAULT_CSV_URL = (
    "https://portal.atdfiware.uco.es/file/datahub/"
    "ac91a79d-9498-4465-b563-ffe2a54201d8.csv"
)
CACHE_DIR = "data/api_cache/meteo_propia"
CACHE_TTL_HOURS = 1

# Columnas numéricas que nos interesan del CSV
NUMERIC_COLS = [
    "temperature", "temperatureMax", "temperatureMin", "temperatureEx",
    "humidity", "humidityIn01", "humidityIn02", "humidityMax", "humidityMin",
    "pluviometer", "pressure",
    "rSolar", "rPar", "radiometerDay", "uv",
    "windVelocity", "windDir", "windMax",
    "tempIn01", "tempIn02",
    "irrigationFrecuencyRs",
    "dhtm", "mhtm", "yhtm", "dltm", "mltm", "yltm",
    "dhhm", "mhhm", "yhhm", "dlhm", "mlhm", "ylhm",
    "dhbr", "mhbr", "yhbr", "dlbr", "mlbr", "ylbr",
    "dpcp", "mpcp", "ypcp",
]


class EstacionMeteorologica:
    """
    Acceso a datos de estaciones meteorológicas IoT (FIWARE).

    Soporta tres fuentes configurables:
      - 'csv': descarga desde URL pública (default)
      - 'postgres': consulta vía psycopg2 (preparado para futuro)
      - 'api_rest': consulta vía HTTP API (preparado para futuro)

    Filtra por gatewayOut (identificador de estación/finca) y rango temporal.
    """

    def __init__(
        self,
        fuente: str = "csv",
        csv_url: str = DEFAULT_CSV_URL,
        cache_dir: str = CACHE_DIR,
        db_config: dict | None = None,
        api_base_url: str | None = None,
    ):
        self.fuente = fuente
        self.csv_url = csv_url
        self.cache_dir = cache_dir
        self.db_config = db_config or {}
        self.api_base_url = api_base_url or ""
        os.makedirs(self.cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_historico(
        self, dias: int = 30, finca_id: str | None = None
    ) -> pd.DataFrame:
        """Ventana relativa de N días hasta el momento actual."""
        now = datetime.now()
        return self._cargar_datos(
            fecha_inicio=now - timedelta(days=dias),
            fecha_fin=now,
            finca_id=finca_id,
        )

    def get_ultimas_horas(
        self, horas: int = 72, finca_id: str | None = None
    ) -> pd.DataFrame:
        """Ventana corta de N horas hasta el momento actual."""
        now = datetime.now()
        return self._cargar_datos(
            fecha_inicio=now - timedelta(hours=horas),
            fecha_fin=now,
            finca_id=finca_id,
        )

    def get_serie_pluviometrica(
        self, intervalo_min: int = 30, finca_id: str | None = None
    ) -> pd.Series:
        """
        Serie de lluvia incremental resampleada al intervalo indicado.

        El pluviómetro es un acumulado que puede resetearse a cero.
        La lluvia incremental se calcula como diff() con clip(min=0)
        para manejar resets correctamente.

        Returns:
            pd.Series con index=datetime, values=mm por intervalo.
        """
        df = self.get_historico(dias=30, finca_id=finca_id)
        if df.empty or "pluviometer" not in df.columns:
            return pd.Series(dtype=float, name="lluvia_incremental_mm")

        df = df[["update", "pluviometer"]].dropna(subset=["pluviometer"])
        df = df.sort_values("update").set_index("update")

        # Resamplear al intervalo: tomar el último valor de cada ventana
        resampled = df["pluviometer"].resample(f"{intervalo_min}min").last().dropna()

        # Lluvia incremental = diff con clip para manejar resets a 0
        incremental = resampled.diff().clip(lower=0).fillna(0)
        incremental.name = "lluvia_incremental_mm"
        return incremental

    def disponible(self, finca_id: str | None = None, horas_recencia: int = 48) -> bool:
        """
        Verifica si hay datos recientes para la estación.
        Por defecto considera disponible si hay datos en las últimas 48h
        (las estaciones IoT pueden tener gaps de varias horas).
        """
        try:
            df = self.get_ultimas_horas(horas=horas_recencia, finca_id=finca_id)
            return not df.empty
        except Exception:
            return False

    def get_estaciones_disponibles(self) -> list[str]:
        """Lista los gatewayOut únicos en el dataset."""
        df = self._cargar_raw()
        if df.empty:
            return []
        return sorted(df["gatewayOut"].dropna().unique().tolist())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cargar_datos(
        self,
        fecha_inicio: datetime,
        fecha_fin: datetime,
        finca_id: str | None = None,
    ) -> pd.DataFrame:
        """Carga datos filtrados por rango temporal y opcionalmente por estación."""
        df = self._cargar_raw()
        if df.empty:
            return df

        # Filtrar por rango temporal
        mask = (df["update"] >= pd.Timestamp(fecha_inicio)) & (
            df["update"] <= pd.Timestamp(fecha_fin)
        )
        df = df.loc[mask].copy()

        # Filtrar por estación (gatewayOut)
        if finca_id:
            df = df[df["gatewayOut"] == finca_id]

        return df.sort_values("update").reset_index(drop=True)

    def _cargar_raw(self) -> pd.DataFrame:
        """Carga el CSV completo (desde cache o descarga)."""
        if self.fuente == "csv":
            return self._cargar_csv()
        elif self.fuente == "postgres":
            return self._cargar_postgres()
        elif self.fuente == "api_rest":
            return self._cargar_api_rest()
        else:
            raise ValueError(f"Fuente no soportada: {self.fuente}")

    def _cargar_csv(self) -> pd.DataFrame:
        """Descarga CSV con cache local (TTL de 1 hora)."""
        cache_path = os.path.join(self.cache_dir, "estacion_data.csv")

        # Verificar cache válida
        if os.path.exists(cache_path):
            age_hours = (
                datetime.now().timestamp() - os.path.getmtime(cache_path)
            ) / 3600
            if age_hours < CACHE_TTL_HOURS:
                logger.debug(f"Usando cache de estación meteo ({age_hours:.1f}h)")
                return self._parse_csv(cache_path)

        # Descargar
        logger.info(f"Descargando datos de estación meteo: {self.csv_url}")
        try:
            resp = requests.get(self.csv_url, timeout=60)
            resp.raise_for_status()
            with open(cache_path, "wb") as f:
                f.write(resp.content)
            return self._parse_csv(cache_path)
        except Exception as e:
            logger.warning(f"Error descargando CSV: {e}")
            # Intentar usar cache expirado si existe
            if os.path.exists(cache_path):
                logger.info("Usando cache expirado como fallback")
                return self._parse_csv(cache_path)
            return pd.DataFrame()

    def _parse_csv(self, path: str) -> pd.DataFrame:
        """Parsea el CSV FIWARE con manejo robusto de tipos."""
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception as e:
            logger.error(f"Error parseando CSV: {e}")
            return pd.DataFrame()

        # Parsear timestamp 'update'
        if "update" in df.columns:
            df["update"] = pd.to_datetime(df["update"], errors="coerce", utc=True)
            df = df.dropna(subset=["update"])
            # Convertir a naive datetime (sin timezone) para compatibilidad
            df["update"] = df["update"].dt.tz_localize(None)

        # Convertir columnas numéricas
        for col in NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Parsear location GeoJSON -> lat, lon
        if "location" in df.columns:
            df["lat"] = df["location"].apply(self._extract_lat)
            df["lon"] = df["location"].apply(self._extract_lon)

        return df

    def _cargar_postgres(self) -> pd.DataFrame:
        """Carga desde PostgreSQL (preparado para futuro)."""
        try:
            import psycopg2

            conn = psycopg2.connect(**self.db_config)
            query = "SELECT * FROM weather_data ORDER BY update DESC"
            df = pd.read_sql(query, conn)
            conn.close()
            if "update" in df.columns:
                df["update"] = pd.to_datetime(df["update"], errors="coerce")
            for col in NUMERIC_COLS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        except ImportError:
            logger.error("psycopg2 no instalado. pip install psycopg2-binary")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error PostgreSQL: {e}")
            return pd.DataFrame()

    def _cargar_api_rest(self) -> pd.DataFrame:
        """Carga desde API REST (preparado para futuro)."""
        try:
            url = f"{self.api_base_url}/weather/data"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            df = pd.DataFrame(data)
            if "update" in df.columns:
                df["update"] = pd.to_datetime(df["update"], errors="coerce")
            for col in NUMERIC_COLS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        except Exception as e:
            logger.error(f"Error API REST: {e}")
            return pd.DataFrame()

    @staticmethod
    def _extract_lat(location_str: str) -> float | None:
        """Extrae latitud de campo GeoJSON: {"type":"Point","coordinates":[-4.7,37.9]}"""
        try:
            if pd.isna(location_str):
                return None
            loc = json.loads(location_str)
            coords = loc.get("coordinates", [])
            return float(coords[1]) if len(coords) >= 2 else None
        except (json.JSONDecodeError, TypeError, IndexError):
            return None

    @staticmethod
    def _extract_lon(location_str: str) -> float | None:
        """Extrae longitud de campo GeoJSON."""
        try:
            if pd.isna(location_str):
                return None
            loc = json.loads(location_str)
            coords = loc.get("coordinates", [])
            return float(coords[0]) if len(coords) >= 2 else None
        except (json.JSONDecodeError, TypeError, IndexError):
            return None
