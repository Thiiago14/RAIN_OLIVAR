"""
Página de enriquecimiento de variables.
Incluye: meteorología, suelo, hidrología, encharcamiento, económico, CSV consolidado.
"""
import streamlit as st
import pandas as pd

from src.features.weather_enrichment import (
    load_weather_cache, enrich_weather_for_client, get_weather_stats,
)
from src.features.soil_enrichment import (
    load_soil_cache, enrich_soil_for_client, get_soil_stats,
)
from src.features.hydrology_enrichment import (
    load_hydrology_cache, enrich_hydrology_for_client, get_hydrology_stats,
)
from src.features.economic_enrichment import get_economic_stats
from src.features.waterlogging_calculator import get_waterlogging_risk_distribution
from src.features.enrichment_assembler import (
    assemble_enriched_csv, get_enrichment_coverage,
    get_ml_readiness, get_ml_ready_csv, get_slope_warnings,
    load_hms_sidecar, hms_sidecar_exists,
)
from src.features.build_input_from_parcels import build_base_input, to_csv_bytes
from src.features.persistence import (
    get_client_status, load_farmer_inputs, FARMER_COLS,
)
from src.geo.geodata_loader import load_client_geodataframe
from src.geo.parcels_processor import process_parcels
from src.geo.usage_filter import filter_ov


def render_page_enrichment(selected_client: str | None = None) -> None:
    """Página de enriquecimiento: meteo, suelo, hidrología, económico, CSV consolidado."""
    st.markdown('<div class="section-title">🌦️ Enriquecimiento</div>', unsafe_allow_html=True)

    if not selected_client:
        st.error("No hay cliente seleccionado.")
        return

    # === CARGAR DATOS BASE ===
    try:
        gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
        ov_gdf = filter_ov(gdf)
    except Exception as e:
        st.error(f"Error cargando shapefile: {str(e)}")
        return

    raw_status = get_client_status(selected_client)

    # Estado cliente
    status_map = {
        "sin_datos": ("Sin datos", "#E67E22"),
        "borrador": ("Borrador", "#E67E22"),
        "completo": ("Completo ✓", "#27AE60"),
        "listo_para_apis": ("Listo para APIs ✓", "#27AE60"),
    }
    label, color = status_map.get(raw_status, ("Desconocido", "#999"))
    st.markdown(
        f"**Estado del cliente:** <span style='color:{color};font-weight:700'>{label}</span>",
        unsafe_allow_html=True,
    )

    # =========================================================================
    # 1. ENRIQUECIMIENTO METEOROLÓGICO
    # =========================================================================
    st.markdown("---")
    st.markdown('<div class="section-title">🌧 Enriquecimiento meteorológico (Open-Meteo)</div>',
                unsafe_allow_html=True)

    if raw_status != "completo":
        st.warning("⚠️ Confirma primero los datos del agricultor (pestaña Data) para habilitar esta sección.")
    else:
        weather_df = load_weather_cache(selected_client)
        w_exists = weather_df is not None and not weather_df.empty

        if w_exists:
            wstats = get_weather_stats(weather_df)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Parcelas con datos", f"{wstats['ok']}/{wstats['total']}",
                          delta=f"{wstats['pct_ok']}% completitud")
            with col2:
                st.metric("Fuente", "Open-Meteo", delta="Sin API key · gratuito")
            with col3:
                updated = str(wstats.get("updated_at", "—"))[:16]
                st.metric("Errores", wstats["errors"], delta=f"Actualizado: {updated}")
        else:
            st.info("No hay datos meteorológicos. Haz clic en el botón para consultar Open-Meteo.")

        col_fetch, col_dl_w = st.columns([1, 2], gap="medium")
        with col_fetch:
            btn_label = "🔄 Actualizar datos meteorológicos" if w_exists else "🌧 Obtener datos meteorológicos"
            if st.button(btn_label, use_container_width=True, type="primary", key="btn_weather"):
                progress_bar = st.progress(0, text="Iniciando consultas a Open-Meteo...")
                status_text = st.empty()

                def _progress(done, total):
                    pct = int(done / total * 100)
                    progress_bar.progress(pct, text=f"Consultando parcela {done}/{total}...")
                    status_text.markdown(f"*Consultando parcela {done} de {total}...*")

                try:
                    weather_df = enrich_weather_for_client(
                        selected_client, ov_gdf, max_workers=5,
                        progress_callback=_progress,
                    )
                    progress_bar.progress(100, text="Completado.")
                    status_text.empty()
                    wstats = get_weather_stats(weather_df)
                    st.success(
                        f"Meteorología actualizada: {wstats['ok']}/{wstats['total']} parcelas OK"
                        + (f" · {wstats['errors']} con error" if wstats["errors"] else "")
                    )
                    st.rerun()
                except Exception as e:
                    progress_bar.empty()
                    status_text.empty()
                    st.error(f"Error al consultar Open-Meteo: {e}")

        if w_exists:
            err_df = weather_df[weather_df["weather_status"] != "ok"]
            if not err_df.empty:
                with st.expander(f"⚠️ {len(err_df)} parcelas con error en meteorología"):
                    st.dataframe(err_df[["parcel_id", "weather_error"]],
                                 use_container_width=True, hide_index=True)

            ok_df = weather_df[weather_df["weather_status"] == "ok"].copy()
            if not ok_df.empty:
                st.markdown("**Variables meteorológicas por parcela:**")
                display_w = ok_df[["parcel_id", "rain_72h_mm", "rain_7d_mm",
                                    "temp_media_7d", "humedad_suelo_%"]].copy()
                for col in ["rain_72h_mm", "rain_7d_mm", "temp_media_7d", "humedad_suelo_%"]:
                    if col in display_w.columns:
                        display_w[col] = pd.to_numeric(display_w[col], errors="coerce").round(2)
                st.dataframe(display_w, use_container_width=True, hide_index=True, height=280)

            with col_dl_w:
                saved_farmer = load_farmer_inputs(selected_client)
                farmer_subset = None
                if saved_farmer is not None and not saved_farmer.empty:
                    farmer_subset = saved_farmer[
                        ["parcel_id"] + [c for c in FARMER_COLS if c in saved_farmer.columns]
                    ]
                enriched_tmp = build_base_input(ov_gdf, farmer_subset, weather_df)
                st.download_button(
                    label="⬇️ CSV agricultor + meteo",
                    data=to_csv_bytes(enriched_tmp),
                    file_name=f"input_meteo_{selected_client}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # =========================================================================
    # 2. ENRIQUECIMIENTO DE SUELO
    # =========================================================================
    st.markdown("---")
    st.markdown('<div class="section-title">🌱 Enriquecimiento de suelo (SoilGrids ISRIC)</div>',
                unsafe_allow_html=True)

    if raw_status != "completo":
        st.warning("⚠️ Confirma primero los datos del agricultor.")
    else:
        soil_df = load_soil_cache(selected_client)
        soil_exists = soil_df is not None and not soil_df.empty

        if soil_exists:
            sstats = get_soil_stats(soil_df)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Parcelas con datos", f"{sstats['ok']}/{sstats['total']}",
                          delta=f"{sstats['pct_ok']}% completitud")
            with col2:
                st.metric("Fuente", "SoilGrids v2", delta="ISRIC · 250m")
            with col3:
                st.metric("Errores", sstats["errors"],
                          delta=f"Actualizado: {str(sstats.get('updated_at','—'))[:16]}")
        else:
            st.info("No hay datos de suelo. Haz clic en el botón para consultar SoilGrids.")

        col_soil_btn, _ = st.columns([1, 2], gap="medium")
        with col_soil_btn:
            soil_btn = "🔄 Actualizar datos de suelo" if soil_exists else "🌱 Obtener datos de suelo"
            if st.button(soil_btn, use_container_width=True, type="primary", key="btn_soil"):
                soil_progress = st.progress(0, text="Conectando con SoilGrids...")
                soil_status_txt = st.empty()

                def _soil_progress(done, total):
                    pct = int(done / total * 100)
                    soil_progress.progress(pct, text=f"Consultando parcela {done}/{total}...")
                    soil_status_txt.markdown(f"*Parcela {done} de {total}...*")

                try:
                    soil_df = enrich_soil_for_client(
                        selected_client, ov_gdf, max_workers=3,
                        progress_callback=_soil_progress,
                    )
                    soil_progress.progress(100, text="Completado.")
                    soil_status_txt.empty()
                    sstats = get_soil_stats(soil_df)
                    st.success(
                        f"Suelo actualizado: {sstats['ok']}/{sstats['total']} parcelas OK"
                        + (f" · {sstats['errors']} con error" if sstats["errors"] else "")
                    )
                    st.rerun()
                except Exception as e:
                    soil_progress.empty()
                    soil_status_txt.empty()
                    st.error(f"Error al consultar SoilGrids: {e}")

        if soil_exists:
            err_soil = soil_df[soil_df["soil_status"] != "ok"]
            if not err_soil.empty:
                with st.expander(f"⚠️ {len(err_soil)} parcelas con error en suelo"):
                    st.dataframe(err_soil[["parcel_id", "soil_error"]],
                                 use_container_width=True, hide_index=True)

            ok_soil = soil_df[soil_df["soil_status"] == "ok"].copy()
            if not ok_soil.empty:
                st.markdown("**Variables de suelo por parcela:**")
                display_cols = [c for c in ["parcel_id", "tipo_suelo", "drenaje",
                                             "materia_organica_%", "profundidad_suelo_cm",
                                             "clay_%", "sand_%", "silt_%"]
                                if c in ok_soil.columns]
                disp_soil = ok_soil[display_cols].copy()
                for col in ["materia_organica_%", "clay_%", "sand_%", "silt_%"]:
                    if col in disp_soil.columns:
                        disp_soil[col] = pd.to_numeric(disp_soil[col], errors="coerce").round(2)
                st.dataframe(disp_soil, use_container_width=True, hide_index=True, height=280)

    # =========================================================================
    # 3. ENRIQUECIMIENTO HIDROLÓGICO
    # =========================================================================
    st.markdown("---")
    st.markdown('<div class="section-title">🌊 Enriquecimiento hidrológico (Overpass / OSM)</div>',
                unsafe_allow_html=True)

    if raw_status != "completo":
        st.warning("⚠️ Confirma primero los datos del agricultor.")
    else:
        hydro_df = load_hydrology_cache(selected_client)
        hydro_exists = hydro_df is not None and not hydro_df.empty

        if hydro_exists:
            hstats = get_hydrology_stats(hydro_df)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Parcelas con distancia", f"{hstats['ok']}/{hstats['total']}",
                          delta=f"{hstats['pct_ok']}% completitud")
            with col2:
                st.metric("Fuente", "Overpass / OSM", delta="Radio: 5000 m")
            with col3:
                st.metric("Sin agua / errores", hstats.get("no_water", 0) + hstats.get("errors", 0),
                          delta=f"Actualizado: {str(hstats.get('updated_at','—'))[:16]}")
        else:
            st.info("No hay datos hidrológicos. Una sola consulta Overpass cubre todas las parcelas.")

        col_h_btn, col_h_tbl = st.columns([1, 3], gap="medium")
        with col_h_btn:
            h_btn = "🔄 Actualizar hidrología" if hydro_exists else "🌊 Obtener distancia a cauces"
            if st.button(h_btn, use_container_width=True, type="primary", key="btn_hydro"):
                with st.spinner("Consultando Overpass API..."):
                    try:
                        hydro_df = enrich_hydrology_for_client(selected_client, ov_gdf, radius_m=5000)
                        hstats = get_hydrology_stats(hydro_df)
                        st.success(
                            f"Hidrología actualizada: {hstats['ok']}/{hstats['total']} parcelas"
                            + (f" · {hstats.get('no_water',0)} sin agua" if hstats.get("no_water") else "")
                            + (f" · {hstats.get('errors',0)} errores" if hstats.get("errors") else "")
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error Overpass: {e}")

        if hydro_exists:
            ok_h = hydro_df[hydro_df["hydrology_status"] == "ok"].copy()
            err_h = hydro_df[hydro_df["hydrology_status"] != "ok"]
            if not err_h.empty:
                with st.expander(f"⚠️ {len(err_h)} parcelas con error / sin agua"):
                    st.dataframe(err_h[["parcel_id", "hydrology_status", "hydrology_error"]],
                                 use_container_width=True, hide_index=True)
            with col_h_tbl:
                if not ok_h.empty:
                    disp_cols = [c for c in ["parcel_id", "distancia_rio_m",
                                              "nearest_water_type", "nearest_water_name"]
                                 if c in ok_h.columns]
                    disp_h = ok_h[disp_cols].copy()
                    if "distancia_rio_m" in disp_h.columns:
                        disp_h["distancia_rio_m"] = pd.to_numeric(
                            disp_h["distancia_rio_m"], errors="coerce"
                        ).round(0)
                    st.dataframe(disp_h, use_container_width=True, hide_index=True, height=260)

    # =========================================================================
    # 3b. ESTACIÓN METEOROLÓGICA PROPIA + MODELO HMS
    # =========================================================================
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📡 Estación meteorológica propia + Modelo hidrológico HMS</div>',
        unsafe_allow_html=True,
    )

    if raw_status != "completo":
        st.warning("⚠️ Confirma primero los datos del agricultor.")
    else:
        _render_estacion_hms_section(selected_client, ov_gdf)

    # =========================================================================
    # 4. CSV CONSOLIDADO + ENCHARCAMIENTO + ECONÓMICO
    # =========================================================================
    if raw_status != "completo":
        return

    st.markdown("---")
    st.markdown('<div class="section-title">📦 CSV consolidado · 💧 Encharcamiento · 💶 Económico</div>',
                unsafe_allow_html=True)

    _w_df = load_weather_cache(selected_client)
    _s_df = load_soil_cache(selected_client)
    _h_df = load_hydrology_cache(selected_client)
    _farmer = load_farmer_inputs(selected_client)
    _farmer_sub = None
    if _farmer is not None and not _farmer.empty:
        _farmer_sub = _farmer[
            ["parcel_id"] + [c for c in FARMER_COLS if c in _farmer.columns]
        ]

    try:
        enriched_df = assemble_enriched_csv(
            selected_client, ov_gdf, _farmer_sub, _w_df, _s_df, _h_df
        )
    except Exception as e:
        st.error(f"Error al ensamblar CSV consolidado: {e}")
        return

    # Cobertura por fuente
    coverage = get_enrichment_coverage(enriched_df)
    src_labels = {
        "shapefile": ("🗺", "Shapefile"),
        "agricultor": ("👨‍🌾", "Agricultor"),
        "meteorologia": ("🌧", "Meteorología"),
        "suelo": ("🌱", "Suelo"),
        "hidrologia": ("🌊", "Hidrología"),
        "economico": ("💶", "Económico"),
    }
    cov_cols = st.columns(max(len(coverage), 1))
    for (src, cov), col in zip(coverage.items(), cov_cols):
        if not cov:
            continue
        pct_vals = [v["pct"] for v in cov.values()]
        avg_pct = round(sum(pct_vals) / len(pct_vals)) if pct_vals else 0
        icon, label = src_labels.get(src, ("•", src))
        with col:
            st.metric(f"{icon} {label}", f"{avg_pct}%", delta=f"{len(cov)} col.")

    # Advertencias de pendiente
    slope_warnings = get_slope_warnings(enriched_df)
    if slope_warnings:
        st.markdown("**⚠️ Advertencias - Pendiente extrema SIGPAC:**")
        warning_df = pd.DataFrame(slope_warnings)
        disp_warn = warning_df[["parcel_id", "pendiente_%", "nivel"]].copy()
        disp_warn.columns = ["Parcela", "Pendiente (%)", "Nivel"]
        st.dataframe(disp_warn, use_container_width=True, hide_index=True,
                     height=min(200, 40 + len(warning_df) * 35))
        st.caption("Valores >100% pueden indicar error SIGPAC. Revisar antes de usar en modelo.")

    # Distribución encharcamiento
    wlog_dist = get_waterlogging_risk_distribution(enriched_df)
    if any(v for v in wlog_dist.values() if v):
        st.markdown("**💧 Distribución de riesgo de encharcamiento:**")
        r_cols = st.columns(5)
        risk_items = [
            ("Sin riesgo", wlog_dist.get("sin_riesgo", 0), "0 días"),
            ("Bajo", wlog_dist.get("bajo", 0), "0–1 días"),
            ("Moderado", wlog_dist.get("moderado", 0), "1–3 días"),
            ("Alto", wlog_dist.get("alto", 0), "> 3 días"),
            ("Sin datos", wlog_dist.get("sin_datos", 0), "lluvia faltante"),
        ]
        for (label, val, sub), col in zip(risk_items, r_cols):
            with col:
                st.metric(f"💧 {label}", val, delta=sub)

        if "duracion_encharcamiento_dias" in enriched_df.columns:
            with st.expander("Ver tabla de encharcamiento por parcela"):
                wlog_cols = [c for c in ["parcel_id", "rain_72h_mm", "drenaje",
                                          "pendiente_%", "distancia_rio_m",
                                          "duracion_encharcamiento_dias"]
                             if c in enriched_df.columns]
                wlog_tbl = enriched_df[wlog_cols].copy()
                for col in ["rain_72h_mm", "pendiente_%", "distancia_rio_m", "duracion_encharcamiento_dias"]:
                    if col in wlog_tbl.columns:
                        wlog_tbl[col] = pd.to_numeric(wlog_tbl[col], errors="coerce").round(2)
                st.dataframe(wlog_tbl, use_container_width=True, hide_index=True)

    # Estado ready_for_ml y descargas
    st.markdown("---")
    st.markdown('<div class="section-title">📊 Estado del CSV para modelo ML</div>', unsafe_allow_html=True)

    econ_stats = get_economic_stats(enriched_df)
    ml_ready = get_ml_readiness(enriched_df)
    ready_color = "#27AE60" if ml_ready["ready"] else "#E67E22"
    ready_badge = "✅ LISTO para ML" if ml_ready["ready"] else f"⚠️ Incompleto: {ml_ready['reason']}"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Estado modelo ML", "LISTO" if ml_ready["ready"] else "Incompleto",
                  delta=f"{ml_ready['cols_complete']}/{ml_ready['cols_total']} cols")
    with col2:
        st.metric("Parcelas listas", ml_ready.get("parcelas_ok", "—"))
    with col3:
        econ_pct = econ_stats.get("pct_all", 0)
        st.metric("Cobertura económica", f"{econ_pct}%",
                  delta=f"rendimiento·precio·coste")

    # Mensaje de estado limpio (sin rutas internas)
    st.markdown(
        f"<div style='padding:10px;border-radius:8px;background:#EBF5E6;border:1px solid #A8D49A'>"
        f"<b style='color:{ready_color}'>{ready_badge}</b> · "
        f"Variables completas: {ml_ready['cols_complete']}/22 · "
        f"Económico: {econ_stats['all_filled']}/{econ_stats['total']} parcelas"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Descarga única para el cliente: CSV de 22 columnas
    import os
    ml_df = get_ml_ready_csv(enriched_df)
    st.download_button(
        label="⬇️ Descargar CSV para modelo ML",
        data=to_csv_bytes(ml_df),
        file_name=f"olivar_ml_{selected_client}.csv",
        mime="text/csv",
        use_container_width=False,
        type="primary",
    )
    st.caption(
        f"Este archivo contiene únicamente las variables requeridas por el modelo · "
        f"{len(ml_df)} parcelas · 22 variables"
    )

    # CSV interno: solo visible si variable de entorno SHOW_DEV_OPTIONS=true
    if os.getenv("SHOW_DEV_OPTIONS", "false").lower() == "true":
        with st.expander("⚙️ Opciones técnicas de desarrollo"):
            st.download_button(
                label="⬇️ CSV consolidado interno (25 cols)",
                data=to_csv_bytes(enriched_df),
                file_name=f"consolidado_interno_{selected_client}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.caption(f"{len(enriched_df)} parcelas · 25 columnas · sep ;")


# =========================================================================
# Sección Estación Propia + HMS (función auxiliar)
# =========================================================================

def _render_estacion_hms_section(client_id: str, ov_gdf) -> None:
    """Renderiza la UI de estación meteorológica propia y modelo HMS."""
    from src.services.EstacionMeteorologica import EstacionMeteorologica
    from src.services.ConstructorVariablesMeteo import ConstructorVariablesMeteo
    from src.services.MeteoFallback import MeteoConFallback

    # --- Estado de la estación ---
    try:
        estacion = EstacionMeteorologica(fuente="csv")
        disponible = estacion.disponible()
        estaciones = estacion.get_estaciones_disponibles()
    except Exception as e:
        st.error(f"Error conectando con estación meteorológica: {e}")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        status_icon = "🟢" if disponible else "🔴"
        st.metric("Estado estación", f"{status_icon} {'Online' if disponible else 'Offline'}")
    with col2:
        st.metric("Estaciones", len(estaciones), delta=estaciones[0] if estaciones else "—")
    with col3:
        st.metric("Fuente", "FIWARE IoT", delta="CSV público · ~15 min")

    if not disponible:
        st.info("La estación meteorológica no tiene datos recientes. Se usará Open-Meteo como fallback.")

    # --- Variables meteorológicas con fallback ---
    st.markdown("**Variables meteorológicas (estación propia + fallback Open-Meteo):**")

    if st.button("📡 Consultar estación propia + fallback", key="btn_estacion_propia",
                 use_container_width=True, type="primary"):
        with st.spinner("Consultando estación meteorológica..."):
            try:
                # Usar centroide de la finca para fallback Open-Meteo
                centroid_wgs84 = ov_gdf.to_crs("EPSG:4326").geometry.centroid.iloc[0]
                lat, lon = centroid_wgs84.y, centroid_wgs84.x

                wrapper = MeteoConFallback(estacion)
                meteo, hms_vars, origen = wrapper.construir_variables_completas(lat=lat, lon=lon)

                # Guardar en session_state para uso posterior
                st.session_state[f"{client_id}_meteo_propia"] = meteo
                st.session_state[f"{client_id}_hms_vars"] = hms_vars
                st.session_state[f"{client_id}_origen_variables"] = origen
                st.success("Variables meteorológicas obtenidas correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error consultando estación: {e}")

    # Mostrar resultados si existen en session_state
    meteo_key = f"{client_id}_meteo_propia"
    origen_key = f"{client_id}_origen_variables"

    if meteo_key in st.session_state:
        meteo = st.session_state[meteo_key]
        origen = st.session_state.get(origen_key, {})

        # Tabla de variables con origen
        vars_df = pd.DataFrame([
            {"Variable": k, "Valor": v, "Fuente": origen.get(k, "—")}
            for k, v in meteo.items()
            if v is not None
        ])
        if not vars_df.empty:
            st.dataframe(vars_df, use_container_width=True, hide_index=True, height=200)

    # --- Modelo HMS ---
    st.markdown("---")
    st.markdown("**🌊 Modelo hidrológico HMS (lluvia → escorrentía → hidrograma):**")

    hms_col1, hms_col2 = st.columns([1, 2])
    with hms_col1:
        uso_suelo = st.selectbox(
            "Uso de suelo",
            ["cultivos", "olivar", "bosque", "pasto", "barbecho"],
            index=1,  # olivar por defecto
            key=f"{client_id}_uso_suelo",
        )
        grupo_hidr = st.selectbox(
            "Grupo hidrológico",
            ["A", "B", "C", "D"],
            index=1,  # B por defecto
            key=f"{client_id}_grupo_hidr",
        )

    with hms_col2:
        if st.button("🌊 Ejecutar modelo HMS", key="btn_hms",
                     use_container_width=True, type="primary"):
            with st.spinner("Ejecutando modelo hidrológico HMS..."):
                try:
                    from src.hms.ModeloHMS import FincaHMS
                    import numpy as np

                    # Buscar shapefile del cliente
                    import glob
                    shp_files = glob.glob(f"data/clientes_shp/{client_id}/**/*.shp", recursive=True)
                    if not shp_files:
                        st.error(f"No se encontró shapefile para {client_id}")
                        return

                    shp_path = shp_files[0]
                    hms = FincaHMS(shp_path)

                    # Intentar descargar DEM (puede tardar)
                    try:
                        hms.descargar_dem(output=f"{client_id}_dem.tif")
                    except Exception:
                        pass  # Continuar sin DEM

                    # Parámetros morfométricos
                    params = hms.calcular_parametros_morfometricos()

                    # Obtener serie de lluvia
                    hms_vars = st.session_state.get(f"{client_id}_hms_vars")
                    if hms_vars and hms_vars.get("lluvia_serie_30min") is not None:
                        lluvia = hms_vars["lluvia_serie_30min"]
                        amc = hms_vars.get("amc_calculado", "II")
                    else:
                        # Fallback: serie sintética de prueba
                        serie = estacion.get_serie_pluviometrica(intervalo_min=30)
                        lluvia = serie.values if not serie.empty else np.zeros(48)
                        amc = "II"

                    # Calcular hidrograma
                    t, Q, metadata = hms.calcular_hidrograma(
                        lluvia, dt_h=0.5,
                        uso_suelo=uso_suelo,
                        grupo_hidrologico=grupo_hidr,
                        AMC=amc,
                    )

                    # Guardar resultados
                    metadata["params"] = params
                    metadata["AMC"] = amc
                    metadata["t_horas"] = t.tolist()
                    metadata["Q_m3s"] = Q.tolist()
                    st.session_state[f"{client_id}_hms_results"] = metadata
                    st.success("Modelo HMS ejecutado correctamente.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Error ejecutando HMS: {e}")

    # Mostrar resultados HMS si existen
    hms_key = f"{client_id}_hms_results"
    if hms_key in st.session_state:
        hms_res = st.session_state[hms_key]

        # KPIs
        st.markdown("**Resultados del modelo HMS:**")
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("CN (SCS)", hms_res.get("CN", "—"))
        with k2:
            st.metric("Caudal pico", f"{hms_res.get('caudal_pico_m3s', 0):.4f} m³/s")
        with k3:
            st.metric("Tiempo pico", f"{hms_res.get('tiempo_pico_h', 0):.2f} h")
        with k4:
            st.metric("Escorrentía", f"{hms_res.get('escorrentia_acumulada_mm', 0):.2f} mm")

        # Parámetros morfométricos
        params = hms_res.get("params", {})
        if params:
            with st.expander("📐 Parámetros morfométricos de la cuenca"):
                p_cols = st.columns(4)
                with p_cols[0]:
                    st.metric("Área", f"{params.get('area_km2', 0):.3f} km²")
                with p_cols[1]:
                    st.metric("T. concentración", f"{params.get('Tc_horas', 0):.2f} h")
                with p_cols[2]:
                    st.metric("Pendiente media", f"{params.get('pendiente_media', 0):.3f}")
                with p_cols[3]:
                    st.metric("Compacidad (Kc)", f"{params.get('Kc', 0):.3f}")

        # Gráfico del hidrograma
        if "t_horas" in hms_res and "Q_m3s" in hms_res:
            import numpy as np
            chart_df = pd.DataFrame({
                "Tiempo (h)": hms_res["t_horas"],
                "Caudal (m³/s)": hms_res["Q_m3s"],
            })
            st.line_chart(chart_df.set_index("Tiempo (h)"), use_container_width=True)
