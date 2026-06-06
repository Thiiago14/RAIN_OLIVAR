"""
Modelo hidrológico HMS: lluvia → escorrentía → hidrograma de crecida.
Implementación completa en Python (sin HEC-HMS desktop).

Métodos:
  - SCS Curve Number (lluvia → escorrentía)
  - Hidrograma unitario sintético SCS
  - Convolución discreta lluvia incremental × HU
  - Descarga automática DEM Copernicus GLO-30

CRS de trabajo: EPSG:25830 (UTM zona 30N ETRS89, estándar España).
"""
import math
import os

import geopandas as gpd
import numpy as np
from loguru import logger
from shapely.geometry import box

# Tabla SCS/NRCS: CN-II por uso de suelo y grupo hidrológico
# Fuente: USDA-NRCS TR-55, Table 2-2a
SCS_CN_TABLE = {
    # uso_suelo:    A    B    C    D
    "bosque":    {"A": 45, "B": 55, "C": 70, "D": 77},
    "pasto":     {"A": 49, "B": 69, "C": 79, "D": 84},
    "cultivos":  {"A": 62, "B": 71, "C": 78, "D": 81},
    "barbecho":  {"A": 72, "B": 81, "C": 88, "D": 91},
    "urbano":    {"A": 85, "B": 90, "C": 92, "D": 93},
    "olivar":    {"A": 55, "B": 66, "C": 75, "D": 80},
}

# Tabla adimensional SCS del hidrograma unitario (28 pares t/tp vs q/qp)
# Fuente: USDA-NRCS TR-55, Figure 6-3
SCS_HU_TABLE = [
    (0.0, 0.000), (0.1, 0.030), (0.2, 0.100), (0.3, 0.190),
    (0.4, 0.310), (0.5, 0.470), (0.6, 0.660), (0.7, 0.820),
    (0.8, 0.930), (0.9, 0.990), (1.0, 1.000), (1.1, 0.990),
    (1.2, 0.930), (1.3, 0.860), (1.4, 0.780), (1.5, 0.680),
    (1.6, 0.560), (1.8, 0.390), (2.0, 0.280), (2.2, 0.207),
    (2.4, 0.147), (2.6, 0.107), (2.8, 0.077), (3.0, 0.055),
    (3.2, 0.040), (3.4, 0.029), (3.6, 0.021), (3.8, 0.015),
    (4.0, 0.011), (4.5, 0.005), (5.0, 0.000),
]

DEM_CACHE_DIR = "data/dem"
CRS_UTM30N = "EPSG:25830"
CRS_WGS84 = "EPSG:4326"
DEFAULT_PENDIENTE = 0.05  # 5% default si no hay DEM


class FincaHMS:
    """
    Modelo hidrológico lluvia-escorrentía para una finca.

    Uso:
        hms = FincaHMS("data/clientes_shp/cliente_1/parcelas.shp")
        hms.descargar_dem()
        params = hms.calcular_parametros_morfometricos()
        cn_data = hms.calcular_CN("cultivos", "B", "II")
        t, Q = hms.calcular_hidrograma(lluvia_serie_mm, dt_h=0.5)
    """

    def __init__(self, shapefile_path: str):
        """
        Carga el shapefile y calcula geometría básica.
        Reproyecta a EPSG:25830 (UTM 30N) si es necesario.
        """
        self.shapefile_path = shapefile_path
        self.gdf = gpd.read_file(shapefile_path)

        # Reproyectar a UTM 30N si el CRS es geográfico
        if self.gdf.crs and self.gdf.crs.is_geographic:
            self.gdf = self.gdf.to_crs(CRS_UTM30N)
        elif self.gdf.crs is None:
            logger.warning("Shapefile sin CRS, asumiendo EPSG:25830")
            self.gdf = self.gdf.set_crs(CRS_UTM30N)

        # Geometría unificada (disolver todas las parcelas)
        self.geometry = self.gdf.geometry.unary_union

        # Métricas básicas
        self.area_m2 = self.geometry.area
        self.area_km2 = self.area_m2 / 1e6
        self.perimetro_m = self.geometry.length
        self.centroide = self.geometry.centroid

        # DEM y parámetros derivados (se calculan bajo demanda)
        self.dem_array = None
        self.dem_path = None
        self.pendiente_media = DEFAULT_PENDIENTE

        # Parámetros morfométricos (cache)
        self._params = None

        logger.info(
            f"FincaHMS: area={self.area_km2:.3f} km², "
            f"perímetro={self.perimetro_m:.0f} m, "
            f"centroide=({self.centroide.x:.1f}, {self.centroide.y:.1f})"
        )

    # ------------------------------------------------------------------
    # 3.2 Descarga DEM Copernicus GLO-30
    # ------------------------------------------------------------------

    def descargar_dem(self, output: str = "dem_finca.tif") -> str | None:
        """
        Descarga el DEM Copernicus GLO-30 desde AWS Open Data.
        Sin API key. Tiles de 1°×1° nombrados por esquina SW.

        Returns:
            Ruta al GeoTIFF recortado, o None si falla.
        """
        os.makedirs(DEM_CACHE_DIR, exist_ok=True)
        output_path = os.path.join(DEM_CACHE_DIR, output)

        # Si ya existe en cache, usarlo
        if os.path.exists(output_path):
            logger.info(f"DEM cache encontrado: {output_path}")
            self._load_dem(output_path)
            return output_path

        # Bounding box en WGS84 con buffer 10%
        gdf_wgs84 = self.gdf.to_crs(CRS_WGS84)
        bounds = gdf_wgs84.total_bounds  # [minx, miny, maxx, maxy]
        dx = (bounds[2] - bounds[0]) * 0.1
        dy = (bounds[3] - bounds[1]) * 0.1
        bbox = box(bounds[0] - dx, bounds[1] - dy, bounds[2] + dx, bounds[3] + dy)

        # Calcular tiles necesarios (1°×1° nombrados por esquina SW)
        tiles = self._get_required_tiles(bounds[0] - dx, bounds[1] - dy,
                                          bounds[2] + dx, bounds[3] + dy)
        logger.info(f"DEM: {len(tiles)} tiles necesarios")

        # Descargar tiles
        import requests
        import tempfile

        tile_paths = []
        base_url = "https://copernicus-dem-30m.s3.amazonaws.com"

        for tile_name in tiles:
            url = f"{base_url}/{tile_name}/{tile_name}_DEM.tif"
            local_path = os.path.join(DEM_CACHE_DIR, f"{tile_name}_DEM.tif")

            if os.path.exists(local_path):
                tile_paths.append(local_path)
                continue

            try:
                logger.info(f"Descargando tile: {tile_name}")
                resp = requests.get(url, timeout=120, stream=True)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                tile_paths.append(local_path)
            except Exception as e:
                logger.warning(f"Tile {tile_name} no disponible: {e}")
                continue

        if not tile_paths:
            logger.warning("No se pudo descargar ningún tile DEM")
            return None

        # Fusionar tiles y recortar al polígono
        try:
            self._merge_and_clip_dem(tile_paths, bbox, output_path)
            self._load_dem(output_path)
            return output_path
        except Exception as e:
            logger.error(f"Error fusionando DEM: {e}")
            return None

    # ------------------------------------------------------------------
    # 3.3 Parámetros morfométricos
    # ------------------------------------------------------------------

    def calcular_parametros_morfometricos(self) -> dict:
        """
        Calcula parámetros de la cuenca:
          - Lc_km: longitud del cauce principal (diagonal bbox / 1000)
          - Ff: factor de forma de Horton = A / Lc²
          - Kc: índice de compacidad de Gravelius = 0.28 × P / √A
          - Tc: tiempo de concentración (Témez) = 0.3 × (Lc / S^0.25)^0.76
          - pendiente_media: del DEM si disponible, sino 5% default
        """
        # Pendiente desde DEM si está disponible
        if self.dem_array is not None:
            self.pendiente_media = self._calc_pendiente_dem()

        # Longitud del cauce principal (aproximación por diagonal bbox)
        bounds = self.geometry.bounds  # (minx, miny, maxx, maxy)
        dx = bounds[2] - bounds[0]
        dy = bounds[3] - bounds[1]
        Lc_m = math.sqrt(dx**2 + dy**2)
        Lc_km = Lc_m / 1000.0

        # Factor de forma de Horton
        Ff = self.area_km2 / (Lc_km**2) if Lc_km > 0 else 0

        # Índice de compacidad de Gravelius
        P_km = self.perimetro_m / 1000.0
        A_km2 = self.area_km2
        Kc = 0.28 * P_km / math.sqrt(A_km2) if A_km2 > 0 else 0

        # Tiempo de concentración (Témez) — Lc en km, S en m/m
        S = max(self.pendiente_media, 0.001)  # evitar división por cero
        Tc = 0.3 * (Lc_km / (S**0.25))**0.76

        self._params = {
            "Lc_km": round(Lc_km, 3),
            "Ff": round(Ff, 4),
            "Kc": round(Kc, 3),
            "Tc_horas": round(Tc, 3),
            "pendiente_media": round(S, 4),
            "area_km2": round(self.area_km2, 4),
            "perimetro_m": round(self.perimetro_m, 1),
        }
        return self._params

    # ------------------------------------------------------------------
    # 3.4 Número de Curva SCS
    # ------------------------------------------------------------------

    def calcular_CN(
        self,
        uso_suelo: str = "cultivos",
        grupo_hidrologico: str = "B",
        AMC: str = "II",
    ) -> dict:
        """
        Asigna CN desde tabla SCS/NRCS y aplica corrección AMC.

        Args:
            uso_suelo: bosque, pasto, cultivos, barbecho, urbano, olivar
            grupo_hidrologico: A, B, C, D
            AMC: I, II, III

        Returns:
            dict: {CN, CN2, S_mm, Ia_mm, AMC}
        """
        uso = uso_suelo.lower()
        grupo = grupo_hidrologico.upper()

        if uso not in SCS_CN_TABLE:
            logger.warning(f"Uso de suelo '{uso}' no en tabla, usando 'cultivos'")
            uso = "cultivos"
        if grupo not in ("A", "B", "C", "D"):
            logger.warning(f"Grupo '{grupo}' inválido, usando 'B'")
            grupo = "B"

        CN2 = SCS_CN_TABLE[uso][grupo]

        # Corrección AMC
        if AMC == "I":
            CN = 4.2 * CN2 / (10.0 - 0.058 * CN2)
        elif AMC == "III":
            CN = 23.0 * CN2 / (10.0 + 0.13 * CN2)
        else:  # AMC-II
            CN = float(CN2)

        # Retención máxima S [mm]
        S = 25400.0 / CN - 254.0 if CN > 0 else 0.0

        # Abstracción inicial [mm]
        Ia = 0.2 * S

        return {
            "CN": round(CN, 1),
            "CN2": CN2,
            "S_mm": round(S, 2),
            "Ia_mm": round(Ia, 2),
            "AMC": AMC,
            "uso_suelo": uso,
            "grupo_hidrologico": grupo,
        }

    # ------------------------------------------------------------------
    # 3.5 Hidrograma unitario sintético SCS
    # ------------------------------------------------------------------

    def hidrograma_unitario_SCS(
        self, duracion_lluvia_h: float, dt_h: float = 0.5
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Genera el hidrograma unitario sintético SCS adimensional.

        Args:
            duracion_lluvia_h: duración del pulso de lluvia (horas)
            dt_h: paso de tiempo del hidrograma (horas)

        Returns:
            (t_horas, q_m3s_por_mm): arrays de tiempo y caudal unitario
        """
        if self._params is None:
            self.calcular_parametros_morfometricos()

        Tc = self._params["Tc_horas"]
        A = self._params["area_km2"]

        # Tiempo de retardo y tiempo al pico
        tlag = 0.6 * Tc
        tp = duracion_lluvia_h / 2.0 + tlag

        # Caudal pico unitario [m³/s por mm de escorrentía]
        qp = 0.208 * A / tp if tp > 0 else 0

        # Interpolar tabla adimensional SCS al paso dt_h
        t_tp_ref = np.array([p[0] for p in SCS_HU_TABLE])
        q_qp_ref = np.array([p[1] for p in SCS_HU_TABLE])

        # Generar tiempos
        t_max = t_tp_ref[-1] * tp  # tiempo máximo en horas
        t_horas = np.arange(0, t_max + dt_h, dt_h)
        t_tp_interp = t_horas / tp if tp > 0 else t_horas

        # Interpolar q/qp
        q_qp_interp = np.interp(t_tp_interp, t_tp_ref, q_qp_ref)

        # Escalar a caudal real [m³/s por mm]
        q_unit = q_qp_interp * qp

        return t_horas, q_unit

    # ------------------------------------------------------------------
    # 3.6 Convolución lluvia → hidrograma
    # ------------------------------------------------------------------

    def calcular_hidrograma(
        self,
        lluvia_serie_mm: np.ndarray,
        dt_h: float = 0.5,
        uso_suelo: str = "cultivos",
        grupo_hidrologico: str = "B",
        AMC: str = "II",
    ) -> tuple[np.ndarray, np.ndarray, dict]:
        """
        Calcula el hidrograma resultante de una serie de lluvia.

        Proceso:
          1. Escorrentía acumulada SCS: Pe = (P-Ia)² / (P-Ia+S) para P > Ia
          2. Escorrentía incremental por intervalo
          3. Convolución discreta con HU sintético SCS
          4. Añadir flujo base

        Args:
            lluvia_serie_mm: array de lluvia incremental por intervalo [mm]
            dt_h: paso de tiempo (horas)
            uso_suelo, grupo_hidrologico, AMC: parámetros CN

        Returns:
            (t_horas, Q_m3s, metadata): arrays de tiempo, caudal, y metadatos
        """
        # Parámetros CN
        cn_data = self.calcular_CN(uso_suelo, grupo_hidrologico, AMC)
        S = cn_data["S_mm"]
        Ia = cn_data["Ia_mm"]

        # Escorrentía acumulada SCS
        lluvia_acum = np.cumsum(lluvia_serie_mm)
        Pe_acum = np.where(
            lluvia_acum > Ia,
            (lluvia_acum - Ia)**2 / (lluvia_acum - Ia + S),
            0.0,
        )

        # Escorrentía incremental
        Pe_incr = np.diff(np.concatenate([[0], Pe_acum]))
        Pe_incr = np.clip(Pe_incr, 0, None)

        # Hidrograma unitario
        duracion = dt_h  # cada pulso dura dt_h
        t_hu, q_hu = self.hidrograma_unitario_SCS(duracion, dt_h)

        # Convolución discreta
        if len(Pe_incr) > 0 and np.any(Pe_incr > 0):
            Q_conv = np.convolve(Pe_incr, q_hu)[:len(Pe_incr) + len(q_hu) - 1]
        else:
            Q_conv = np.zeros(len(lluvia_serie_mm) + len(q_hu) - 1)

        # Tiempo
        t_total = np.arange(0, len(Q_conv)) * dt_h

        # Flujo base estimado
        Qb = 0.001 * self.area_km2  # m³/s
        Q_total = Q_conv + Qb

        # Metadata
        escorrentia_total_mm = float(np.sum(Pe_incr))
        caudal_pico = float(np.max(Q_total)) if len(Q_total) > 0 else 0
        tiempo_pico_idx = int(np.argmax(Q_total)) if len(Q_total) > 0 else 0
        tiempo_pico_h = float(t_total[tiempo_pico_idx]) if len(t_total) > 0 else 0

        metadata = {
            "CN": cn_data["CN"],
            "S_mm": S,
            "Ia_mm": Ia,
            "AMC": AMC,
            "escorrentia_acumulada_mm": round(escorrentia_total_mm, 2),
            "caudal_pico_m3s": round(caudal_pico, 4),
            "tiempo_pico_h": round(tiempo_pico_h, 2),
            "flujo_base_m3s": round(Qb, 4),
            "params": self._params,
        }

        return t_total, Q_total, metadata

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_required_tiles(
        self, min_lon: float, min_lat: float, max_lon: float, max_lat: float
    ) -> list[str]:
        """
        Calcula los nombres de tiles Copernicus necesarios para cubrir el bbox.
        Formato: Copernicus_DSM_COG_10_N{lat}_00_{E/W}{lon}_00_DEM
        """
        tiles = []
        lat_start = int(math.floor(min_lat))
        lat_end = int(math.floor(max_lat))
        lon_start = int(math.floor(min_lon))
        lon_end = int(math.floor(max_lon))

        for lat in range(lat_start, lat_end + 1):
            for lon in range(lon_start, lon_end + 1):
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"
                tile = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
                tiles.append(tile)

        return tiles

    def _merge_and_clip_dem(
        self, tile_paths: list[str], bbox_wgs84, output_path: str
    ) -> None:
        """Fusiona tiles DEM y recorta al polígono de la finca."""
        import rasterio
        from rasterio.mask import mask
        from rasterio.merge import merge

        # Abrir todos los datasets
        datasets = [rasterio.open(p) for p in tile_paths]

        try:
            # Fusionar tiles
            if len(datasets) == 1:
                mosaic = datasets[0].read(1)
                meta = datasets[0].meta.copy()
                transform = datasets[0].transform
            else:
                mosaic, transform = merge(datasets)
                mosaic = mosaic[0]  # primera banda
                meta = datasets[0].meta.copy()
                meta.update({"transform": transform,
                             "height": mosaic.shape[0],
                             "width": mosaic.shape[1]})

            # Escribir temporal fusionado
            temp_path = output_path + ".tmp.tif"
            meta.update({"driver": "GTiff", "count": 1, "dtype": mosaic.dtype})
            with rasterio.open(temp_path, "w", **meta) as dst:
                dst.write(mosaic, 1)

            # Recortar al polígono (en WGS84)
            gdf_wgs84 = self.gdf.to_crs(CRS_WGS84)
            shapes = [geom.__geo_interface__ for geom in gdf_wgs84.geometry]

            with rasterio.open(temp_path) as src:
                out_image, out_transform = mask(src, shapes, crop=True, nodata=-9999)
                out_meta = src.meta.copy()
                out_meta.update({
                    "driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform,
                })

            with rasterio.open(output_path, "w", **out_meta) as dst:
                dst.write(out_image)

            # Limpiar temporal
            os.remove(temp_path)

        finally:
            for ds in datasets:
                ds.close()

    def _load_dem(self, path: str) -> None:
        """Carga el array DEM desde un GeoTIFF."""
        try:
            import rasterio
            with rasterio.open(path) as src:
                self.dem_array = src.read(1)
                self.dem_path = path
                logger.info(f"DEM cargado: {self.dem_array.shape} desde {path}")
        except Exception as e:
            logger.warning(f"Error cargando DEM: {e}")
            self.dem_array = None

    def _calc_pendiente_dem(self) -> float:
        """
        Calcula la pendiente media del terreno desde el DEM usando numpy.gradient.
        Retorna pendiente en m/m (adimensional).
        """
        if self.dem_array is None:
            return DEFAULT_PENDIENTE

        try:
            # Gradiente en ambas direcciones (asumiendo resolución ~30m)
            dy, dx = np.gradient(self.dem_array.astype(float))
            slope = np.sqrt(dx**2 + dy**2)

            # Resolución del DEM (aproximada a 30m para Copernicus GLO-30)
            resolution_m = 30.0
            slope_m_m = slope / resolution_m

            # Pendiente media (eliminar NaN y valores extremos)
            slope_clean = slope_m_m[~np.isnan(slope_m_m)]
            slope_clean = slope_clean[(slope_clean >= 0) & (slope_clean < 2.0)]

            if len(slope_clean) == 0:
                return DEFAULT_PENDIENTE

            return float(np.mean(slope_clean))
        except Exception as e:
            logger.warning(f"Error calculando pendiente DEM: {e}")
            return DEFAULT_PENDIENTE
