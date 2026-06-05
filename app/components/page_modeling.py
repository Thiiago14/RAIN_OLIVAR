"""
Página de modelado y predicciones.
Dashboard completo: estado, KPIs, mapa, gráficos, tabla, descargas.
"""
import streamlit as st
import pandas as pd

from src.features.input_validator import load_and_validate_ml_csv
from src.features.prediction_perdida import run_prediction, load_predictions
from src.features.enrichment_assembler import get_ml_readiness
from src.features.build_input_from_parcels import to_csv_bytes
from src.geo.map_builder import build_parcels_map
from src.geo.parcels_processor import process_parcels
from src.geo.geodata_loader import load_client_geodataframe
from src.geo.usage_filter import filter_ov
from app.components.charts import (
    show_risk_distribution,
    show_top_parcels_by_loss,
    show_top_parcels_by_impact,
    show_scatter_loss_vs_rain,
    show_scatter_waterlogging_vs_loss,
    show_loss_by_parcel_bars,
    show_single_parcel_summary,
)


def _build_modeling_df(predictions_df: pd.DataFrame, enriched_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fusiona predicciones con datos enriquecidos por parcel_id.

    Siempre usa parcel_id porque parcel_uid en predictions es un índice autoincremental
    (0, 1, 2...) que no coincide con los UIDs de SIGPAC en el shapefile.
    """
    if enriched_df is None or enriched_df.empty:
        return predictions_df.copy()

    modeling_df = predictions_df.copy()
    enriched_copy = enriched_df.copy()

    # Normalizar clave de merge a string limpio
    modeling_df["parcel_id"] = modeling_df["parcel_id"].astype(str).str.strip()
    enriched_copy["parcel_id"] = enriched_copy["parcel_id"].astype(str).str.strip()

    # Traer columnas enriquecidas que no están ya en predictions
    extra_cols = ["parcel_id"] + [c for c in enriched_copy.columns if c not in modeling_df.columns]
    modeling_df = modeling_df.merge(enriched_copy[extra_cols], on="parcel_id", how="left")

    return modeling_df


def _build_map_gdf(ov_gdf, enriched_df: pd.DataFrame | None, predictions_df: pd.DataFrame | None):
    """
    Construye GeoDataFrame completo para el mapa, combinando geometrías + enriquecimiento + predicciones.

    Siempre usa parcel_id como clave de merge porque parcel_uid en predictions
    es un índice autoincremental (0,1,2...) que NO coincide con los UIDs de SIGPAC.
    """
    import geopandas as gpd

    map_gdf = ov_gdf.copy()
    map_gdf["parcel_id"] = map_gdf["parcel_id"].astype(str).str.strip()

    # 1. Merge con enriquecimiento (pendiente_%, rain_7d_mm, humedad, etc.)
    if enriched_df is not None and not enriched_df.empty:
        enrich = enriched_df.drop(columns=["geometry"], errors="ignore").copy()
        enrich["parcel_id"] = enrich["parcel_id"].astype(str).str.strip()
        extra = ["parcel_id"] + [c for c in enrich.columns if c not in map_gdf.columns]
        map_gdf = map_gdf.merge(enrich[extra], on="parcel_id", how="left")

    # 2. Merge con predicciones (nivel_riesgo, impacto_total_eur, etc.)
    if predictions_df is not None and not predictions_df.empty:
        preds = predictions_df.copy()
        preds["parcel_id"] = preds["parcel_id"].astype(str).str.strip()
        extra = ["parcel_id"] + [c for c in preds.columns if c not in map_gdf.columns]
        map_gdf = map_gdf.merge(preds[extra], on="parcel_id", how="left")

    # 3. Convertir columnas numéricas
    numeric_candidates = [
        "pendiente_%", "pendiente_pct", "rain_72h_mm", "rain_7d_mm",
        "humedad_suelo_%", "duracion_encharcamiento_dias", "distancia_rio_m",
        "pct_perdida_pred_pct", "pct_perdida_pred",
        "impacto_total_eur", "impacto_eur_ha_pred",
        "rendimiento_esperado_kg_ha", "precio_mercado_eur_kg",
        "altitud_m", "profundidad_suelo_cm", "materia_organica_%",
    ]
    for col in numeric_candidates:
        if col in map_gdf.columns:
            map_gdf[col] = pd.to_numeric(map_gdf[col], errors="coerce")

    return map_gdf


def _last_prediction_date(predictions_df: pd.DataFrame) -> str:
    """Retorna la fecha de la última predicción o '—'."""
    if "prediction_updated_at" in predictions_df.columns:
        val = predictions_df["prediction_updated_at"].iloc[0]
        return str(val)[:16] if pd.notna(val) else "—"
    return "—"


def render_page_modeling(selected_client: str, enriched_df: pd.DataFrame | None) -> None:
    """Página principal de modelado y predicciones."""

    # Encabezado
    st.markdown(
        "<h2 style='color:#2D5016;margin-bottom:2px'>🤖 Modelado y predicciones</h2>"
        "<p style='color:#7A9A6E;font-size:13px;margin-top:0'>Resultados estimados de pérdida de producción por parcela</p>",
        unsafe_allow_html=True,
    )

    # === REQUISITOS PREVIOS ===
    if enriched_df is None or enriched_df.empty:
        st.error("No hay datos enriquecidos. Completa la pestaña Enriquecimiento primero.")
        return

    ml_ready = get_ml_readiness(enriched_df)
    predictions_df = load_predictions(selected_client)

    # === ESTADO + BOTÓN ===
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        color = "#27AE60" if ml_ready["ready"] else "#E67E22"
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:12px 16px;"
            f"border-left:4px solid {color};box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:10px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Estado</div>"
            f"<div style='font-size:18px;font-weight:700;color:{color}'>"
            f"{'LISTO' if ml_ready['ready'] else 'Incompleto'}</div>"
            f"<div style='font-size:11px;color:#999'>para modelo ML</div></div>",
            unsafe_allow_html=True,
        )
    with col_s2:
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:12px 16px;"
            f"border-left:4px solid #4A7C59;box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:10px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Columnas</div>"
            f"<div style='font-size:18px;font-weight:700;color:#1E3A2F'>"
            f"{ml_ready['cols_complete']}/22</div>"
            f"<div style='font-size:11px;color:#999'>variables completas</div></div>",
            unsafe_allow_html=True,
        )
    with col_s3:
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:12px 16px;"
            f"border-left:4px solid #4A7C59;box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:10px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Parcelas listas</div>"
            f"<div style='font-size:18px;font-weight:700;color:#1E3A2F'>"
            f"{ml_ready.get('parcelas_ok', '—')}</div>"
            f"<div style='font-size:11px;color:#999'>de {len(enriched_df)} OV</div></div>",
            unsafe_allow_html=True,
        )
    with col_s4:
        last_pred = _last_prediction_date(predictions_df) if predictions_df is not None else "—"
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:12px 16px;"
            f"border-left:4px solid {'#4A7C59' if predictions_df is not None else '#CCC'};"
            f"box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:10px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Última predicción</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1E3A2F'>{last_pred}</div>"
            f"<div style='font-size:11px;color:#999'>fecha/hora</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    if not ml_ready["ready"]:
        st.warning(f"⚠️ {ml_ready['reason']} — Completa el enriquecimiento antes de generar predicción.")
        return

    # === BOTÓN PREDICCIÓN ===
    if st.button("🚀 Generar predicción", type="primary", use_container_width=False):
        with st.spinner("Validando CSV y ejecutando modelo..."):
            df_ml, val_report = load_and_validate_ml_csv(
                f"data/enriched/{selected_client}_input_enriched.csv"
            )
            if df_ml is not None and val_report["is_valid"]:
                result_df, pred_status = run_prediction(df_ml, selected_client)
                if result_df is not None:
                    st.session_state["predictions_generated"] = True
                    st.success(f"Predicción completada: {pred_status['n_predictions']} parcelas")
                    st.rerun()
                else:
                    st.error(f"Error: {pred_status['error']}")
            else:
                st.error("CSV no válido para el modelo")
                for e in val_report.get("errors", []):
                    st.write(f"- {e}")

    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones. Ejecuta 'Generar predicción' para comenzar.")
        return

    # === CONSTRUIR MODELING_DF ===
    modeling_df = _build_modeling_df(predictions_df, enriched_df)

    # Nota sobre condiciones climáticas si pérdida es muy baja
    mean_loss = modeling_df["pct_perdida_pred_pct"].mean()
    if "rain_7d_mm" in modeling_df.columns:
        mean_rain = pd.to_numeric(modeling_df["rain_7d_mm"], errors="coerce").mean()
        if mean_rain < 5 and mean_loss < 1:
            st.info(
                "Las pérdidas estimadas son bajas porque no se registró lluvia acumulada "
                "reciente ni encharcamiento en las parcelas evaluadas."
            )

    # === KPIs ===
    st.markdown("---")
    st.markdown("<div class='section-title'>📊 KPIs principales</div>", unsafe_allow_html=True)

    n = len(modeling_df)
    perdida_media = modeling_df["pct_perdida_pred_pct"].mean()
    perdida_max = modeling_df["pct_perdida_pred_pct"].max()
    impacto_total = modeling_df["impacto_total_eur"].sum()
    impacto_medio = modeling_df["impacto_eur_ha_pred"].mean()
    n_alto = int(modeling_df["nivel_riesgo"].isin(["alto", "muy_alto"]).sum())
    parcela_critica = modeling_df.loc[modeling_df["impacto_total_eur"].idxmax(), "parcel_id"] if n > 0 else "—"

    kpi_data = [
        ("Parcelas analizadas", str(n), ""),
        ("Pérdida media", f"{perdida_media:.2f}%", "estimada"),
        ("Pérdida máxima", f"{perdida_max:.2f}%", "caso más crítico"),
        ("Impacto total", f"€ {impacto_total:,.0f}", "estimado"),
        ("Impacto medio/ha", f"€ {impacto_medio:,.2f}", "por hectárea"),
        ("Riesgo alto/muy alto", str(n_alto), f"de {n} (por impacto)"),
        ("Parcela crítica (impacto)", parcela_critica, "mayor impacto económico"),
    ]

    kpi_cols = st.columns(len(kpi_data))
    for col, (label, value, sub) in zip(kpi_cols, kpi_data):
        with col:
            st.markdown(
                f"<div style='background:#fff;border-radius:10px;padding:10px 12px;"
                f"border-top:3px solid #4A7C59;box-shadow:0 2px 6px rgba(0,0,0,.06);text-align:center'>"
                f"<div style='font-size:9px;color:#7A9A6E;text-transform:uppercase;font-weight:600;letter-spacing:.5px'>{label}</div>"
                f"<div style='font-size:17px;font-weight:700;color:#1E3A2F;margin:4px 0'>{value}</div>"
                f"<div style='font-size:10px;color:#aaa'>{sub}</div></div>",
                unsafe_allow_html=True,
            )

    # === MAPA DE RESULTADOS ===
    st.markdown("---")
    st.markdown("<div class='section-title'>🗺 Mapa de resultados del modelo</div>", unsafe_allow_html=True)

    try:
        gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
        ov_gdf = filter_ov(gdf)

        # Construir GeoDataFrame completo para el mapa (geometría + enriquecimiento + predicciones)
        # Usa parcel_id como clave (parcel_uid en predictions es índice autoincremental, no SIGPAC)
        map_gdf = _build_map_gdf(ov_gdf, enriched_df, predictions_df)

        col_mode, col_base = st.columns([2, 1], gap="medium")
        with col_mode:
            map_mode = st.selectbox(
                "Modo de visualización",
                options=["riesgo", "impacto_economico", "encharcamiento", "pendiente", "uso_sigpac"],
                format_func=lambda x: {
                    "riesgo": "🎯 Predicción de riesgo",
                    "impacto_economico": "💶 Impacto económico",
                    "encharcamiento": "💧 Encharcamiento estimado",
                    "pendiente": "⛰️ Pendiente del terreno",
                    "uso_sigpac": "🗺 Uso SIGPAC (referencia)",
                }[x],
                index=0,
                label_visibility="collapsed",
            )
        with col_base:
            from src.geo.map_builder import BASEMAPS
            basemap = st.selectbox(
                "Mapa base",
                options=list(BASEMAPS.keys()),
                index=0,
                label_visibility="collapsed",
            )

        # Verificar que los datos de predicción están en el GeoDataFrame
        if map_mode in ("riesgo", "impacto_economico") and "nivel_riesgo" not in map_gdf.columns:
            st.warning("No hay predicciones disponibles para este modo. Genera predicciones primero.")
        else:
            # Pasar el GeoDataFrame ya fusionado (predictions_df=None para evitar merge interno)
            folium_map = build_parcels_map(
                map_gdf,
                filter_ov=False,   # ya filtrado OV en map_gdf
                mode=map_mode,
                predictions_df=None,   # ya fusionado en map_gdf
                basemap=basemap,
            )
            from streamlit_folium import st_folium
            st_folium(folium_map, use_container_width=True, height=500)

    except Exception as e:
        import traceback
        st.warning(f"No se pudo renderizar el mapa: {str(e)}")
        st.code(traceback.format_exc())

    # === GRÁFICOS ===
    st.markdown("---")
    st.markdown("<div class='section-title'>📈 Análisis visual</div>", unsafe_allow_html=True)

    n_parcelas = len(modeling_df)

    if n_parcelas <= 1:
        # Caso de una sola parcela: ficha resumen
        st.info("Este cliente tiene una sola parcela de olivar. Los gráficos comparativos se activan cuando existan dos o más parcelas.")
        show_single_parcel_summary(modeling_df)
    else:
        tab1, tab2, tab3 = st.tabs(["📊 Distribución", "🏆 Top parcelas", "🔬 Correlaciones"])

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
    st.markdown("---")
    st.markdown("<div class='section-title'>📋 Tabla de predicciones</div>", unsafe_allow_html=True)

    # Columnas para el cliente (sin columnas técnicas)
    table_col_map = {
        "parcel_id": "Parcela",
        "superficie_ha": "Superficie (ha)",
        "pct_perdida_pred_pct": "Pérdida estimada (%)",
        "nivel_riesgo": "Predicción de riesgo",
        "impacto_eur_ha_pred": "Impacto €/ha",
        "impacto_total_eur": "Impacto total €",
        "rain_7d_mm": "Lluvia 7d (mm)",
        "humedad_suelo_%": "Humedad suelo (%)",
        "pendiente_%": "Pendiente (%)",
        "duracion_encharcamiento_dias": "Encharcamiento (días)",
    }
    available_cols = [c for c in table_col_map if c in modeling_df.columns]
    table_df = modeling_df[available_cols].copy()

    # Ordenar: riesgo → impacto desc → pérdida desc
    risk_order = {"muy_alto": 0, "alto": 1, "medio": 2, "bajo": 3}
    if "nivel_riesgo" in table_df.columns:
        table_df["_risk_order"] = table_df["nivel_riesgo"].map(risk_order).fillna(9)
        table_df = table_df.sort_values(
            ["_risk_order", "impacto_total_eur", "pct_perdida_pred_pct"],
            ascending=[True, False, False],
        ).drop(columns=["_risk_order"])

    table_df.columns = [table_col_map.get(c, c) for c in table_df.columns]

    # Color por riesgo
    def _color_row(row):
        r = row.get("Predicción de riesgo", "")
        if r == "muy_alto":
            return ["background:#FFCDD2;color:#B71C1C"] * len(row)
        if r == "alto":
            return ["background:#FFE0B2;color:#E65100"] * len(row)
        if r == "medio":
            return ["background:#FFF9C4;color:#F57F17"] * len(row)
        return [""] * len(row)

    st.dataframe(
        table_df.style.apply(_color_row, axis=1),
        use_container_width=True,
        height=min(420, 42 + len(table_df) * 36),
        hide_index=True,
    )

    # === DESCARGA ===
    st.markdown("---")
    col_dl, col_info = st.columns([1, 2])
    with col_dl:
        # Exportar predicciones + variables clave (sin columnas técnicas internas)
        export_cols = [c for c in table_col_map if c in modeling_df.columns]
        export_df = modeling_df[export_cols].copy()
        st.download_button(
            label="⬇️ Descargar resultados de predicción",
            data=to_csv_bytes(export_df),
            file_name=f"prediccion_{selected_client}.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )
    with col_info:
        st.caption(
            f"El archivo incluye: parcela, pérdida estimada, nivel de riesgo, "
            f"impacto económico y variables ambientales clave. "
            f"{len(export_df)} parcelas · sep ;"
        )
