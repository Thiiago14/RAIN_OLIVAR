"""
Página de modelado y predicciones.
Contiene: estado, validación, botón predicción, KPIs, mapa, gráficos, tabla.
"""
import streamlit as st
import pandas as pd
from src.features.build_input_from_parcels import SCHEMA_COLUMNS, to_csv_bytes
from src.features.input_validator import load_and_validate_ml_csv
from src.features.prediction_perdida import run_prediction, load_predictions
from src.features.enrichment_assembler import get_ml_readiness, get_ml_ready_csv
from src.geo.map_builder import build_parcels_map
from src.geo.parcels_processor import process_parcels
from src.geo.geodata_loader import load_client_geodataframe
from src.geo.usage_filter import filter_ov
from app.components.kpi_cards import show_prediction_kpis
from app.components.charts import (
    show_risk_distribution,
    show_top_parcels_by_loss,
    show_top_parcels_by_impact,
    show_scatter_loss_vs_rain,
    show_scatter_waterlogging_vs_loss,
    show_loss_by_parcel_bars,
)


def render_page_modeling(selected_client: str, enriched_df: pd.DataFrame | None) -> None:
    """Página principal de modelado y predicciones."""

    st.markdown('<div class="section-title">🤖 Modelado y predicciones</div>', unsafe_allow_html=True)

    # === ESTADO DEL MODELO ===
    st.markdown("### Estado del modelo")

    if enriched_df is None or enriched_df.empty:
        st.error("No hay CSV consolidado. Completa el enriquecimiento primero.")
        return

    ml_ready = get_ml_readiness(enriched_df)
    ready_color = "#27AE60" if ml_ready["ready"] else "#E67E22"
    ready_badge = "LISTO para ML" if ml_ready["ready"] else "Incompleto"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Estado modelo", ready_badge, help="Requiere 22/22 columnas completas")
    with col2:
        st.metric("Columnas completas", f"{ml_ready['cols_complete']}/{ml_ready['cols_total']}")
    with col3:
        st.metric("Parcelas listas", ml_ready["parcelas_ok"])

    if not ml_ready["ready"]:
        st.warning(f"⚠️ No listo: {ml_ready['reason']}")
        return

    # === VALIDACIÓN Y PREDICCIÓN ===
    st.markdown("### Generar predicción")

    col_btn, col_status = st.columns([1, 2])

    with col_btn:
        if st.button("🚀 Generar predicción", use_container_width=True, type="primary", disabled=not ml_ready["ready"]):
            with st.spinner("Validando CSV y ejecutando modelo..."):
                # Validar CSV
                df_ml, val_report = load_and_validate_ml_csv(f"data/enriched/{selected_client}_input_enriched.csv")

                if df_ml is not None and val_report["is_valid"]:
                    # Predicción
                    predictions_df, pred_status = run_prediction(df_ml, selected_client)

                    if predictions_df is not None:
                        st.session_state["predictions_generated"] = True
                        st.success(f"✓ Predicción completada: {pred_status['n_predictions']} parcelas")
                        st.rerun()
                    else:
                        st.error(f"Error predicción: {pred_status['error']}")
                else:
                    st.error("CSV no válido para modelo")

    # === CARGAR PREDICCIONES ===
    predictions_df = load_predictions(selected_client)

    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones. Ejecuta 'Generar predicción' para comenzar.")
        return

    # === MERGE: PREDICCIONES + ENRIQUECIMIENTO ===
    # Crear DataFrame combinado para modelado (con todas las columnas necesarias)
    modeling_df = predictions_df.copy()

    # Preferir merge por parcel_uid si ambos tienen la columna
    merge_key = "parcel_uid" if "parcel_uid" in enriched_df.columns and "parcel_uid" in modeling_df.columns else "parcel_id"

    # Convertir a string para asegurar compatibilidad de tipos
    modeling_df[merge_key] = modeling_df[merge_key].astype(str)
    enriched_merge = enriched_df.copy()
    enriched_merge[merge_key] = enriched_merge[merge_key].astype(str)

    # Columns que queremos del enriquecimiento (evitar duplicados con predicciones)
    enrich_cols = [merge_key]
    for col in enriched_merge.columns:
        if col not in modeling_df.columns and col != merge_key:
            enrich_cols.append(col)

    modeling_df = modeling_df.merge(
        enriched_merge[enrich_cols],
        on=merge_key,
        how="left"
    )

    # === KPIs ===
    st.markdown("### KPIs principales")
    show_prediction_kpis(modeling_df)

    # === MAPA DE RIESGO ===
    st.markdown("### Mapa de resultados del modelo")

    # Cargar GDF para mapa
    gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
    ov_gdf = filter_ov(gdf)

    map_mode = st.selectbox(
        "Modo de visualización del mapa",
        options=["riesgo_ml", "impacto_economico", "encharcamiento", "pendiente", "uso_sigpac"],
        format_func=lambda x: {
            "riesgo_ml": "Riesgo ML",
            "impacto_economico": "Impacto económico",
            "encharcamiento": "Encharcamiento",
            "pendiente": "Pendiente del terreno",
            "uso_sigpac": "Uso SIGPAC (referencia)",
        }[x],
        index=0,
    )

    folium_map = build_parcels_map(
        ov_gdf,
        filter_ov=True,
        mode=map_mode,
        predictions_df=modeling_df,
    )

    from streamlit_folium import st_folium

    st_folium(folium_map, use_container_width=True, height=500)

    # === GRÁFICOS ===
    st.markdown("### Análisis visual")

    tab1, tab2, tab3 = st.tabs(["Distribución", "Top parcelas", "Correlaciones"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            show_risk_distribution(modeling_df)
        with col2:
            show_loss_by_parcel_bars(modeling_df)

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            show_top_parcels_by_loss(modeling_df, 10)
        with col2:
            show_top_parcels_by_impact(modeling_df, 10)

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            show_scatter_loss_vs_rain(modeling_df)
        with col2:
            show_scatter_waterlogging_vs_loss(modeling_df)

    # === TABLA ===
    st.markdown("### Tabla de predicciones")

    # Usar solo columnas que existen en predicciones
    display_cols = [
        "parcel_id",
        "superficie_ha",
        "pct_perdida_pred_pct",
        "nivel_riesgo",
        "impacto_eur_ha_pred",
        "impacto_total_eur",
    ]

    # Agregar columnas adicionales si están disponibles (del merge con enriched_df)
    if "rain_7d_mm" in plot_df.columns:
        display_cols.append("rain_7d_mm")
    if "humedad_suelo_%" in enriched_df.columns:
        display_cols.append("humedad_suelo_%")
    if "drenaje" in enriched_df.columns:
        display_cols.append("drenaje")
    if "duracion_encharcamiento_dias" in plot_df.columns:
        display_cols.append("duracion_encharcamiento_dias")

    display_df = modeling_df[[col for col in display_cols if col in modeling_df.columns]].copy()

    # Mapeo de nombres de columnas
    col_names_map = {
        "parcel_id": "Parcela",
        "superficie_ha": "Superficie (ha)",
        "pct_perdida_pred_pct": "Pérdida (%)",
        "nivel_riesgo": "Riesgo",
        "impacto_eur_ha_pred": "Impacto €/ha",
        "impacto_total_eur": "Impacto total €",
        "rain_7d_mm": "Lluvia 7d (mm)",
        "humedad_suelo_%": "Humedad (%)",
        "drenaje": "Drenaje",
        "duracion_encharcamiento_dias": "Encharcamiento (días)",
    }
    display_df.columns = [col_names_map.get(c, c) for c in display_df.columns]

    # Colorear por riesgo
    def color_riesgo(val):
        if val == "muy_alto":
            return ["background:#FFCDD2"] * len(display_df.columns)
        elif val == "alto":
            return ["background:#FFE0B2"] * len(display_df.columns)
        elif val == "medio":
            return ["background:#FFF9C4"] * len(display_df.columns)
        return [""] * len(display_df.columns)

    st.dataframe(
        display_df.style.apply(lambda row: color_riesgo(row["Riesgo"]), axis=1),
        use_container_width=True,
        height=min(400, 40 + len(display_df) * 35),
    )

    # === DESCARGAS ===
    st.markdown("### Descargas")

    col1, col2 = st.columns(2)

    with col1:
        pred_csv = to_csv_bytes(predictions_df)
        st.download_button(
            label="⬇️ Descargar predicciones (CSV)",
            data=pred_csv,
            file_name=f"predictions_{selected_client}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col2:
        ml_df = get_ml_ready_csv(enriched_df)
        ml_csv = to_csv_bytes(ml_df)
        st.download_button(
            label="⬇️ Descargar CSV modelo (22 cols)",
            data=ml_csv,
            file_name=f"input_ml_{selected_client}.csv",
            mime="text/csv",
            use_container_width=True,
        )
