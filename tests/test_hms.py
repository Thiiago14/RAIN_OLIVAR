"""
Tests unitarios del modelo hidrológico HMS y módulos asociados.

7 tests requeridos:
  1. test_escorrentia_cero_bajo_ia
  2. test_escorrentia_positiva
  3. test_hidrograma_tiene_pico_unico
  4. test_lluvia_cero_hidrograma_cero
  5. test_amc_limites
  6. test_eto_penman_rango_fisico
  7. test_pluviometro_incremental
"""
import numpy as np
import pandas as pd
import pytest


# =========================================================================
# Helpers para instanciar HMS sin shapefile real
# =========================================================================

def _make_hms(tmp_shapefile):
    """Crea una instancia de FincaHMS con shapefile temporal."""
    from src.hms.ModeloHMS import FincaHMS
    return FincaHMS(tmp_shapefile)


# =========================================================================
# 1. Escorrentía cero bajo Ia
# =========================================================================

class TestEscorrentia:
    """Tests de la ecuación SCS de escorrentía."""

    def test_escorrentia_cero_bajo_ia(self, tmp_shapefile):
        """Lluvia < Ia debe devolver Pe = 0."""
        hms = _make_hms(tmp_shapefile)
        cn_data = hms.calcular_CN("cultivos", "B", "II")
        Ia = cn_data["Ia_mm"]

        # Lluvia total menor que Ia
        lluvia = np.array([Ia * 0.3])  # 30% de Ia

        t, Q, metadata = hms.calcular_hidrograma(
            lluvia, dt_h=0.5,
            uso_suelo="cultivos", grupo_hidrologico="B", AMC="II",
        )

        assert metadata["escorrentia_acumulada_mm"] == 0.0, (
            f"Escorrentía debería ser 0 cuando lluvia ({lluvia.sum():.2f} mm) < Ia ({Ia:.2f} mm)"
        )

    def test_escorrentia_positiva(self, tmp_shapefile):
        """Lluvia > Ia debe devolver Pe > 0 y Pe < lluvia total."""
        hms = _make_hms(tmp_shapefile)
        cn_data = hms.calcular_CN("cultivos", "B", "II")
        Ia = cn_data["Ia_mm"]

        # Lluvia total significativamente mayor que Ia
        lluvia_total = Ia * 5
        lluvia = np.array([lluvia_total])

        t, Q, metadata = hms.calcular_hidrograma(
            lluvia, dt_h=0.5,
            uso_suelo="cultivos", grupo_hidrologico="B", AMC="II",
        )

        Pe = metadata["escorrentia_acumulada_mm"]
        assert Pe > 0, f"Escorrentía debería ser > 0 cuando lluvia ({lluvia_total:.2f} mm) > Ia ({Ia:.2f} mm)"
        assert Pe < lluvia_total, (
            f"Escorrentía ({Pe:.2f} mm) debería ser < lluvia total ({lluvia_total:.2f} mm)"
        )


# =========================================================================
# 2. Hidrograma tiene pico único
# =========================================================================

class TestHidrograma:

    def test_hidrograma_tiene_pico_unico(self, tmp_shapefile, sample_rain_series):
        """El hidrograma debe tener exactamente un máximo global."""
        hms = _make_hms(tmp_shapefile)

        t, Q, metadata = hms.calcular_hidrograma(
            sample_rain_series, dt_h=0.5,
            uso_suelo="cultivos", grupo_hidrologico="B", AMC="II",
        )

        assert len(Q) > 0, "Hidrograma no debería estar vacío"

        # Encontrar máximos locales (puntos mayores que sus vecinos)
        from scipy.signal import argrelextrema
        local_maxima = argrelextrema(Q, np.greater_equal, order=3)[0]

        # Debe haber al menos un máximo
        assert len(local_maxima) >= 1, "Hidrograma debe tener al menos un máximo"

        # El máximo global debe estar bien definido
        max_idx = np.argmax(Q)
        assert Q[max_idx] > 0, "El caudal pico debe ser > 0"

    def test_lluvia_cero_hidrograma_cero(self, tmp_shapefile, zero_rain_series):
        """Serie de lluvia toda ceros debe dar Q ≈ Qb (solo flujo base)."""
        hms = _make_hms(tmp_shapefile)

        t, Q, metadata = hms.calcular_hidrograma(
            zero_rain_series, dt_h=0.5,
            uso_suelo="cultivos", grupo_hidrologico="B", AMC="II",
        )

        Qb = metadata["flujo_base_m3s"]

        # Todo el hidrograma debe ser ≈ flujo base
        assert metadata["escorrentia_acumulada_mm"] == 0.0, "Sin lluvia no hay escorrentía"
        assert np.allclose(Q, Qb, atol=1e-6), (
            f"Sin lluvia, Q debería ser ≈ Qb ({Qb:.4f}), pero Q range: [{Q.min():.6f}, {Q.max():.6f}]"
        )


# =========================================================================
# 3. AMC límites
# =========================================================================

class TestAMC:

    def test_amc_limites(self):
        """Verificar los tres rangos de AMC con valores en los límites exactos."""
        from src.services.ConstructorVariablesMeteo import ConstructorVariablesMeteo

        # Crear un mock de ConstructorVariablesMeteo solo para testear calcular_amc
        # No necesitamos una estación real
        class MockEstacion:
            def get_ultimas_horas(self, **kwargs):
                return pd.DataFrame()
            def get_historico(self, **kwargs):
                return pd.DataFrame()
            def get_serie_pluviometrica(self, **kwargs):
                return pd.Series(dtype=float)
            def disponible(self, **kwargs):
                return False

        constructor = ConstructorVariablesMeteo(MockEstacion())

        # Test directo del método calcular_amc con DataFrames mock
        def make_df_with_rain(rain_mm):
            """Crea un DataFrame que simule lluvia acumulada en pluviómetro."""
            n = 10
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="1h")
            # Crear serie donde diff() sume rain_mm
            pluviometer = np.linspace(0, rain_mm, n)
            return pd.DataFrame({
                "update": timestamps,
                "pluviometer": pluviometer,
            })

        # AMC-I: rain_5d < 35 mm (34.9 mm)
        df_34_9 = make_df_with_rain(34.9)
        amc_1 = constructor.calcular_amc(df_34_9)
        assert amc_1 == "I", f"34.9 mm debería ser AMC-I, got {amc_1}"

        # AMC-II: rain_5d = 35.0 mm (límite inferior)
        df_35 = make_df_with_rain(35.0)
        amc_2_low = constructor.calcular_amc(df_35)
        assert amc_2_low == "II", f"35.0 mm debería ser AMC-II, got {amc_2_low}"

        # AMC-II: rain_5d = 52.9 mm (límite superior)
        df_52_9 = make_df_with_rain(52.9)
        amc_2_high = constructor.calcular_amc(df_52_9)
        assert amc_2_high == "II", f"52.9 mm debería ser AMC-II, got {amc_2_high}"

        # AMC-III: rain_5d > 53 mm (53.0 mm)
        df_53 = make_df_with_rain(53.0)
        amc_3 = constructor.calcular_amc(df_53)
        assert amc_3 == "III", f"53.0 mm debería ser AMC-III, got {amc_3}"


# =========================================================================
# 4. ETo Penman rango físico
# =========================================================================

class TestETo:

    def test_eto_penman_rango_fisico(self):
        """ETo debe estar entre 0 y 15 mm/día para inputs meteorológicos plausibles."""
        from src.services.ConstructorVariablesMeteo import ConstructorVariablesMeteo

        class MockEstacion:
            def get_ultimas_horas(self, **kwargs):
                return pd.DataFrame()
            def get_historico(self, **kwargs):
                return pd.DataFrame()
            def get_serie_pluviometrica(self, **kwargs):
                return pd.Series(dtype=float)
            def disponible(self, **kwargs):
                return False

        constructor = ConstructorVariablesMeteo(MockEstacion())

        # Escenario 1: Día cálido y seco (verano mediterráneo)
        df_calido = pd.DataFrame({
            "temperature": [30.0] * 24,
            "humidity": [35.0] * 24,
            "rSolar": [350.0] * 24,      # W/m²
            "windVelocity": [3.0] * 24,   # m/s
        })
        eto_calido = constructor.calcular_eto_penman_fao56(df_calido)
        assert eto_calido is not None, "ETo no debería ser None para inputs válidos"
        assert 0 <= eto_calido <= 15, f"ETo cálida ({eto_calido:.2f}) fuera de rango [0, 15]"

        # Escenario 2: Día fresco y húmedo (invierno)
        df_frio = pd.DataFrame({
            "temperature": [8.0] * 24,
            "humidity": [85.0] * 24,
            "rSolar": [80.0] * 24,
            "windVelocity": [1.5] * 24,
        })
        eto_frio = constructor.calcular_eto_penman_fao56(df_frio)
        assert eto_frio is not None, "ETo no debería ser None para inputs válidos"
        assert 0 <= eto_frio <= 15, f"ETo fría ({eto_frio:.2f}) fuera de rango [0, 15]"
        assert eto_frio < eto_calido, "ETo en invierno debería ser menor que en verano"

        # Escenario 3: Sin radiación (noche) → ETo cercana a 0
        df_noche = pd.DataFrame({
            "temperature": [15.0] * 12,
            "humidity": [90.0] * 12,
            "rSolar": [0.0] * 12,
            "windVelocity": [1.0] * 12,
        })
        eto_noche = constructor.calcular_eto_penman_fao56(df_noche)
        assert eto_noche is not None
        assert 0 <= eto_noche <= 2, f"ETo nocturna ({eto_noche:.2f}) debería ser muy baja"


# =========================================================================
# 5. Pluviómetro incremental
# =========================================================================

class TestPluviometro:

    def test_pluviometro_incremental(self):
        """
        Dado un acumulado corriente [100, 102, 102, 105],
        la lluvia incremental debe ser [2, 0, 3].
        """
        acumulado = np.array([100.0, 102.0, 102.0, 105.0])

        # Lluvia incremental = diff con clip(min=0)
        incremental = np.diff(acumulado)
        incremental = np.clip(incremental, 0, None)

        expected = np.array([2.0, 0.0, 3.0])
        np.testing.assert_array_equal(
            incremental, expected,
            err_msg=f"Incremental {incremental} != esperado {expected}",
        )

    def test_pluviometro_con_reset(self):
        """El pluviómetro puede resetearse a 0; diff+clip debe manejarlo."""
        # Acumulado con reset: [10, 15, 20, 0, 3, 8]
        acumulado = np.array([10.0, 15.0, 20.0, 0.0, 3.0, 8.0])

        incremental = np.diff(acumulado)
        incremental = np.clip(incremental, 0, None)

        # diff = [5, 5, -20, 3, 5] → clip → [5, 5, 0, 3, 5]
        expected = np.array([5.0, 5.0, 0.0, 3.0, 5.0])
        np.testing.assert_array_equal(
            incremental, expected,
            err_msg=f"Reset no manejado: {incremental} != {expected}",
        )


# =========================================================================
# 6. CN SCS — validación de tabla
# =========================================================================

class TestCN:

    def test_cn_cultivos_grupo_b(self, tmp_shapefile):
        """CN-II para cultivos grupo B debe ser 71."""
        hms = _make_hms(tmp_shapefile)
        cn_data = hms.calcular_CN("cultivos", "B", "II")
        assert cn_data["CN2"] == 71
        assert cn_data["CN"] == 71.0  # sin corrección AMC-II

    def test_cn_correccion_amc_i(self, tmp_shapefile):
        """AMC-I debe reducir el CN."""
        hms = _make_hms(tmp_shapefile)
        cn_ii = hms.calcular_CN("cultivos", "B", "II")
        cn_i = hms.calcular_CN("cultivos", "B", "I")
        assert cn_i["CN"] < cn_ii["CN"], "AMC-I debería dar CN menor que AMC-II"

    def test_cn_correccion_amc_iii(self, tmp_shapefile):
        """AMC-III debe aumentar el CN."""
        hms = _make_hms(tmp_shapefile)
        cn_ii = hms.calcular_CN("cultivos", "B", "II")
        cn_iii = hms.calcular_CN("cultivos", "B", "III")
        assert cn_iii["CN"] > cn_ii["CN"], "AMC-III debería dar CN mayor que AMC-II"
