"""
Fixtures compartidos para tests de AgriAI.
"""
import os
import tempfile

import numpy as np
import geopandas as gpd
import pytest
from shapely.geometry import Polygon


@pytest.fixture
def tmp_shapefile(tmp_path):
    """Crea un shapefile temporal con un polígono rectangular en UTM 30N."""
    # Rectángulo ~1 km² en UTM 30N (zona Córdoba)
    coords = [
        (350000, 4200000),
        (351000, 4200000),
        (351000, 4201000),
        (350000, 4201000),
        (350000, 4200000),
    ]
    poly = Polygon(coords)
    gdf = gpd.GeoDataFrame(
        {"parcel_id": ["test_01"], "geometry": [poly]},
        crs="EPSG:25830",
    )
    shp_path = str(tmp_path / "test_finca.shp")
    gdf.to_file(shp_path)
    return shp_path


@pytest.fixture
def sample_rain_series():
    """Serie de lluvia incremental de 24 intervalos (12 horas a dt=0.5h)."""
    # Evento de lluvia: pico en el intervalo 8-10
    rain = np.zeros(24)
    rain[6] = 2.0
    rain[7] = 5.0
    rain[8] = 8.0
    rain[9] = 6.0
    rain[10] = 3.0
    rain[11] = 1.0
    return rain


@pytest.fixture
def zero_rain_series():
    """Serie de lluvia toda ceros."""
    return np.zeros(24)
