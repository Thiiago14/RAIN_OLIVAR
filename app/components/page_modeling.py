"""
Pestaña Modelado / Resultados.

Estado A (sin parcela): resumen general, mapa, ranking, KPIs.
Estado B (con parcela): detalle individual, mapa centrado, factores de riesgo.
"""
import streamlit as st
import pandas as pd

from src.features.input_validator import load_and_validate_ml_csv
from src.features.prediction_perdida import run_prediction
from src.features.enrichment_assembler import get_ml_readiness
from src.features.build_input_from_parcels import to_csv_bytes
from src.geo.map_builder import build_parcels_map, BASEMAPS
from src.geo.parcels_processor import process_parcels
from src.geo.geodata_loader import load_client_geodataframe
from src.geo.usage_filter import filter_ov


# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------

def _fv(v, fmt=".2f", default="—"):
    """Formatea un valor numérico de forma segura."""
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return str(default)


def _build_modeling_df(predictions_df: pd.DataFrame, enriched_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fusiona predicciones + enriquecimiento por parcel_id.
    Usa parcel_id siempre porque parcel_uid en predictions es índice autoincremental.
    """
    if enriched_df is None or enriched_df.empty:
        return predictions_df.copy()

    modeling_df = predictions_df.copy()
    enriched_copy = enriched_df.copy()

    modeling_df["parcel_id"] = modeling_df["parcel_id"].astype(str).str.strip()
    enriched_copy["parcel_id"] = enriched_copy["parcel_id"].astype(str).str.strip()

    extra_cols = ["parcel_id"] + [c for c in enriched_copy.columns if c not in modeling_df.columns]
    modeling_df = modeling_df.merge(enriched_copy[extra_cols], on="parcel_id", how="left")
    return modeling_df


def _build_map_gdf(ov_gdf, enriched_df: pd.DataFrame | None, predictions_df: pd.DataFrame | None):
    """GeoDataFrame completo para mapa: geometría + enriquecimiento + predicciones por parcel_id."""
    map_gdf = ov_gdf.copy()
    map_gdf["parcel_id"] = map_gdf["parcel_id"].astype(str).str.strip()

    if enriched_df is not None and not enriched_df.empty:
        enrich = enriched_df.drop(columns=["geometry"], errors="ignore").copy()
        enrich["parcel_id"] = enrich["parcel_id"].astype(str).str.strip()
        extra = ["parcel_id"] + [c for c in enrich.columns if c not in map_gdf.columns]
        map_gdf = map_gdf.merge(enrich[extra], on="parcel_id", how="left")

    if predictions_df is not None and not predictions_df.empty:
        preds = predictions_df.copy()
        preds["parcel_id"] = preds["parcel_id"].astype(str).str.strip()
        extra = ["parcel_id"] + [c for c in preds.columns if c not in map_gdf.columns]
        map_gdf = map_gdf.merge(preds[extra], on="parcel_id", how="left")

    numeric_cols = [
        "pendiente_%", "pendiente_pct", "rain_72h_mm", "rain_7d_mm", "humedad_suelo_%",
        "duracion_encharcamiento_dias", "distancia_rio_m", "pct_perdida_pred_pct",
        "impacto_total_eur", "impacto_eur_ha_pred", "rendimiento_esperado_kg_ha",
        "precio_mercado_eur_kg", "altitud_m", "materia_organica_%",
    ]
    for col in numeric_cols:
        if col in map_gdf.columns:
            map_gdf[col] = pd.to_numeric(map_gdf[col], errors="coerce")

    return map_gdf


def _interpretive_note(modeling_df: pd.DataFrame) -> str | None:
    """Genera nota interpretativa por reglas simples."""
    if modeling_df is None or modeling_df.empty:
        return None

    rain = pd.to_numeric(modeling_df.get("rain_7d_mm", pd.Series([0])), errors="coerce").mean()
    ench = pd.to_numeric(modeling_df.get("duracion_encharcamiento_dias", pd.Series([0])), errors="coerce").mean()
    perdida = modeling_df["pct_perdida_pred_pct"].mean() if "pct_perdida_pred_pct" in modeling_df.columns else 0

    slope_col = next((c for c in ["pendiente_%", "pendiente_pct"] if c in modeling_df.columns), None)
    n_extrema = 0
    if slope_col:
        n_extrema = int((pd.to_numeric(modeling_df[slope_col], errors="coerce") > 60).sum())

    if rain < 5 and ench == 0 and perdida < 5:
        note = ("Las pérdidas estimadas son bajas porque no se registró lluvia acumulada "
                "reciente ni encharcamiento en las parcelas evaluadas.")
    elif rain > 50 or ench > 1:
        note = (f"Se detectaron condiciones de alta humedad ({rain:.1f} mm acumulados en 7 días, "
                f"encharcamiento de {ench:.1f} días), que son los principales factores de riesgo.")
    else:
        note = "Las condiciones climáticas actuales son moderadas."

    if n_extrema > 0:
        note += f" Hay {n_extrema} parcela(s) con pendiente >60% que podrían tener anomalías SIGPAC."

    return note


def _parcel_risk_factors(row: dict) -> list[str]:
    """Genera factores de riesgo para una parcela por reglas."""
    def _f(k, default=0):
        try:
            return float(row.get(k) or default)
        except (TypeError, ValueError):
            return float(default)

    factors = []
    if _f("rain_7d_mm") > 50:
        factors.append(f"Lluvia acumulada elevada ({_f('rain_7d_mm'):.1f} mm en 7 días)")
    if _f("duracion_encharcamiento_dias") > 1:
        factors.append(f"Encharcamiento relevante ({_f('duracion_encharcamiento_dias'):.1f} días)")
    if str(row.get("drenaje", "")).lower() in ("malo", "bad", "pobre"):
        factors.append(f"Drenaje limitado ({row.get('drenaje', '—')})")
    if _f("humedad_suelo_%") > 50:
        factors.append(f"Humedad del suelo alta ({_f('humedad_suelo_%'):.1f}%)")
    slope = _f("pendiente_%") or _f("pendiente_pct")
    if slope > 60:
        factors.append(f"Pendiente elevada ({slope:.0f}%) — posible anomalía SIGPAC")
    if _f("materia_organica_%") > 0 and _f("materia_organica_%") < 1.5:
        factors.append(f"Materia orgánica baja ({_f('materia_organica_%'):.2f}%)")
    return factors


def _quick_interpretation(row: dict) -> str:
    """Genera texto de interpretación rápida para la parcela."""
    def _f(k, default=0):
        try:
            return float(row.get(k) or default)
        except (TypeError, ValueError):
            return float(default)

    riesgo = str(row.get("nivel_riesgo", "bajo")).replace("_", " ").lower()
    perdida = _f("pct_perdida_pred_pct")
    rain = _f("rain_7d_mm")
    ench = _f("duracion_encharcamiento_dias")
    drenaje = str(row.get("drenaje", "—"))

    if rain < 5 and ench == 0:
        return (f"La parcela presenta riesgo {riesgo} de pérdida productiva ({perdida:.2f}%). "
                f"La predicción se explica principalmente por la ausencia de lluvia acumulada reciente "
                f"y encharcamiento estimado nulo.")
    elif rain > 30 or ench > 1:
        return (f"La parcela presenta riesgo {riesgo} de pérdida productiva ({perdida:.2f}%). "
                f"Los factores principales son la lluvia acumulada ({rain:.1f} mm) "
                f"y el encharcamiento de {ench:.1f} días.")
    else:
        return (f"La parcela presenta riesgo {riesgo} de pérdida productiva ({perdida:.2f}%). "
                f"El drenaje {drenaje.lower()} y la humedad del suelo son los factores a monitorizar.")


# ---------------------------------------------------------------------------
# Estado A: análisis general (sin parcela)
# ---------------------------------------------------------------------------

def _render_general(selected_client: str, enriched_df: pd.DataFrame | None,
                    predictions_df: pd.DataFrame | None) -> None:
    """Vista general del cliente cuando no hay parcela seleccionada."""

    st.markdown(
        "<h2 style='color:#2D5016;margin-bottom:2px'>🤖 Modelado y resultados</h2>"
        "<p style='color:#7A9A6E;font-size:13px;margin-top:0'>"
        "Resultados estimados de pérdida de producción para las parcelas de olivar analizadas.</p>",
        unsafe_allow_html=True,
    )

    if enriched_df is None or enriched_df.empty:
        st.error("No hay datos enriquecidos. Completa la pestaña Enriquecimiento primero.")
        return

    ml_ready = get_ml_readiness(enriched_df)
    last_pred = "—"
    if predictions_df is not None and "prediction_updated_at" in predictions_df.columns:
        last_pred = str(predictions_df["prediction_updated_at"].iloc[0])[:16]

    # Estado del modelo
    col1, col2, col3, col4 = st.columns(4)
    color_estado = "#27AE60" if ml_ready["ready"] else "#E67E22"
    with col1:
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:10px 14px;"
            f"border-left:4px solid {color_estado};box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:9px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Estado</div>"
            f"<div style='font-size:17px;font-weight:700;color:{color_estado}'>{'LISTO' if ml_ready['ready'] else 'Incompleto'}</div>"
            f"<div style='font-size:10px;color:#aaa'>para modelo ML</div></div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:10px 14px;"
            f"border-left:4px solid #4A7C59;box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:9px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Columnas</div>"
            f"<div style='font-size:17px;font-weight:700;color:#1E3A2F'>{ml_ready['cols_complete']}/22</div>"
            f"<div style='font-size:10px;color:#aaa'>variables completas</div></div>",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:10px 14px;"
            f"border-left:4px solid #4A7C59;box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:9px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Parcelas listas</div>"
            f"<div style='font-size:17px;font-weight:700;color:#1E3A2F'>{ml_ready.get('parcelas_ok', '—')}</div>"
            f"<div style='font-size:10px;color:#aaa'>de {len(enriched_df)} OV</div></div>",
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"<div style='background:#fff;border-radius:10px;padding:10px 14px;"
            f"border-left:4px solid {'#4A7C59' if predictions_df is not None else '#CCC'};"
            f"box-shadow:0 2px 6px rgba(0,0,0,.06)'>"
            f"<div style='font-size:9px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Última predicción</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1E3A2F'>{last_pred}</div>"
            f"<div style='font-size:10px;color:#aaa'>fecha / hora</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin:10px 0'></div>", unsafe_allow_html=True)

    if not ml_ready["ready"]:
        st.warning(f"⚠️ {ml_ready['reason']} — Completa el enriquecimiento antes de generar predicción.")
        return

    if st.button("🚀 Generar predicción", type="primary"):
        with st.spinner("Ejecutando modelo..."):
            df_ml, val = load_and_validate_ml_csv(f"data/enriched/{selected_client}_input_enriched.csv")
            if df_ml is not None and val["is_valid"]:
                result_df, status = run_prediction(df_ml, selected_client)
                if result_df is not None:
                    st.success(f"Predicción completada: {status['n_predictions']} parcelas")
                    st.rerun()
                else:
                    st.error(f"Error: {status['error']}")
            else:
                st.error("CSV no válido")

    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones. Ejecuta 'Generar predicción'.")
        return

    # Construir modeling_df y nota interpretativa
    modeling_df = _build_modeling_df(predictions_df, enriched_df)

    note = _interpretive_note(modeling_df)
    if note:
        st.info(note)

    # KPIs
    st.markdown("---")
    st.markdown("<div class='section-title'>📊 Indicadores principales</div>", unsafe_allow_html=True)

    n = len(modeling_df)
    perdida_media = modeling_df["pct_perdida_pred_pct"].mean()
    perdida_max = modeling_df["pct_perdida_pred_pct"].max()
    impacto_total = modeling_df["impacto_total_eur"].sum()
    impacto_medio = modeling_df["impacto_eur_ha_pred"].mean()
    n_alto = int(modeling_df["nivel_riesgo"].isin(["alto", "muy_alto"]).sum())
    parcela_critica = modeling_df.loc[modeling_df["impacto_total_eur"].idxmax(), "parcel_id"]

    kpi_data = [
        ("Parcelas analizadas", str(n), ""),
        ("Pérdida media", f"{perdida_media:.2f}%", "estimada"),
        ("Pérdida máxima", f"{perdida_max:.2f}%", "caso más crítico"),
        ("Impacto total", f"€{impacto_total:,.0f}", "estimado"),
        ("Impacto medio/ha", f"€{impacto_medio:,.2f}", "por hectárea"),
        ("Riesgo alto/muy alto", str(n_alto), "parcelas"),
        ("Parcela crítica", parcela_critica, "mayor impacto"),
    ]
    kpi_cols = st.columns(len(kpi_data))
    for col, (label, value, sub) in zip(kpi_cols, kpi_data):
        with col:
            st.markdown(
                f"<div style='background:#fff;border-radius:10px;padding:9px 11px;"
                f"border-top:3px solid #4A7C59;box-shadow:0 2px 5px rgba(0,0,0,.05);text-align:center'>"
                f"<div style='font-size:8px;color:#7A9A6E;text-transform:uppercase;font-weight:600;letter-spacing:.4px'>{label}</div>"
                f"<div style='font-size:16px;font-weight:700;color:#1E3A2F;margin:3px 0'>{value}</div>"
                f"<div style='font-size:9px;color:#aaa'>{sub}</div></div>",
                unsafe_allow_html=True,
            )

    # Mapa
    st.markdown("---")
    st.markdown("<div class='section-title'>🗺 Mapa de resultados</div>", unsafe_allow_html=True)

    try:
        gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
        ov_gdf = filter_ov(gdf)
        map_gdf = _build_map_gdf(ov_gdf, enriched_df, predictions_df)

        col_mode, col_base = st.columns([2, 1])
        with col_mode:
            map_mode = st.selectbox(
                "Modo de visualización",
                options=["riesgo", "impacto_economico", "encharcamiento", "pendiente", "uso_sigpac"],
                format_func=lambda x: {
                    "riesgo": "🎯 Predicción de riesgo",
                    "impacto_economico": "💶 Impacto económico",
                    "encharcamiento": "💧 Encharcamiento estimado",
                    "pendiente": "⛰️ Pendiente del terreno",
                    "uso_sigpac": "🗺 Uso SIGPAC",
                }[x],
                index=0,
                label_visibility="collapsed",
                key="modelado_map_mode",
            )
        with col_base:
            basemap = st.selectbox(
                "Mapa base",
                options=list(BASEMAPS.keys()),
                index=0,
                label_visibility="collapsed",
                key="modelado_basemap",
            )

        folium_map = build_parcels_map(map_gdf, filter_ov=False, mode=map_mode,
                                       predictions_df=None, basemap=basemap)
        from streamlit_folium import st_folium
        st_folium(folium_map, use_container_width=True, height=500, key="modelado_map")
    except Exception as e:
        st.warning(f"No se pudo renderizar el mapa: {str(e)}")

    # Ranking de parcelas
    st.markdown("---")
    st.markdown("<div class='section-title'>📋 Parcelas prioritarias</div>", unsafe_allow_html=True)

    table_col_map = {
        "parcel_id": "Parcela",
        "pct_perdida_pred_pct": "Pérdida (%)",
        "nivel_riesgo": "Predicción de riesgo",
        "impacto_eur_ha_pred": "Impacto €/ha",
        "impacto_total_eur": "Impacto total €",
        "rain_7d_mm": "Lluvia 7d (mm)",
        "humedad_suelo_%": "Humedad (%)",
        "pendiente_%": "Pendiente (%)",
        "duracion_encharcamiento_dias": "Encharcamiento (días)",
    }
    avail = [c for c in table_col_map if c in modeling_df.columns]
    table_df = modeling_df[avail].copy()

    risk_order = {"muy_alto": 0, "alto": 1, "medio": 2, "bajo": 3}
    if "nivel_riesgo" in table_df.columns:
        table_df["_order"] = table_df["nivel_riesgo"].map(risk_order).fillna(9)
        table_df = table_df.sort_values(["_order", "impacto_total_eur", "pct_perdida_pred_pct"],
                                        ascending=[True, False, False]).drop(columns=["_order"])
    table_df.columns = [table_col_map.get(c, c) for c in table_df.columns]

    def _color_row(row):
        r = row.get("Predicción de riesgo", "")
        if r == "muy_alto":
            return ["background:#FFCDD2"] * len(row)
        if r == "alto":
            return ["background:#FFE0B2"] * len(row)
        if r == "medio":
            return ["background:#FFF9C4"] * len(row)
        return [""] * len(row)

    st.dataframe(
        table_df.style.apply(_color_row, axis=1),
        use_container_width=True,
        height=min(460, 42 + len(table_df) * 36),
        hide_index=True,
    )

    # Descarga
    col_dl, _ = st.columns([1, 2])
    with col_dl:
        export_df = modeling_df[avail].copy()
        st.download_button(
            "⬇️ Descargar resultados",
            data=to_csv_bytes(export_df),
            file_name=f"prediccion_{selected_client}.csv",
            mime="text/csv",
            type="primary",
        )


# ---------------------------------------------------------------------------
# Estado B: detalle individual (con parcela seleccionada)
# ---------------------------------------------------------------------------

def _render_parcel_detail(selected_client: str, selected_parcel_id: str,
                          enriched_df: pd.DataFrame | None, predictions_df: pd.DataFrame | None) -> None:
    """Vista de detalle para una parcela seleccionada."""

    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("← General", key="btn_back_to_general"):
            st.session_state["selected_parcel_id"] = None
            st.rerun()
    with col_title:
        st.markdown(
            f"<h2 style='color:#2D5016;margin-bottom:0'>🤖 Modelado · {selected_parcel_id}</h2>",
            unsafe_allow_html=True,
        )

    if enriched_df is None or enriched_df.empty:
        st.error("No hay datos enriquecidos disponibles.")
        return

    predictions_df = predictions_df if predictions_df is not None else pd.DataFrame()
    modeling_df = _build_modeling_df(predictions_df, enriched_df) if not predictions_df.empty else pd.DataFrame()

    # Obtener fila de la parcela
    parcel_rows = enriched_df[enriched_df["parcel_id"].astype(str) == str(selected_parcel_id)]
    if parcel_rows.empty:
        st.error(f"Parcela {selected_parcel_id} no encontrada.")
        return
    row = parcel_rows.iloc[0].to_dict()

    # Agregar predicciones si existen
    if not modeling_df.empty:
        pred_rows = modeling_df[modeling_df["parcel_id"].astype(str) == str(selected_parcel_id)]
        if not pred_rows.empty:
            for k, v in pred_rows.iloc[0].to_dict().items():
                if k not in row:
                    row[k] = v

    # 1. Encabezado de parcela
    st.markdown("---")
    st.markdown("<div class='section-title'>📋 Identificación de la parcela</div>", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Superficie", f"{_fv(row.get('superficie_ha') or row.get('area_ha_calc'), '.4f')} ha")
        st.metric("Tipo de olivar", row.get("tipo_olivar", "—"))
    with col2:
        st.metric("Variedad", row.get("variedad", "—"))
        st.metric("Riego", row.get("riego", "—"))
    with col3:
        st.metric("Fenología", row.get("estado_fenologico", "—"))
        st.metric("Provincia", row.get("zona_provincia", row.get("provincia", "—")))
    with col4:
        st.metric("Rendimiento esperado", f"{_fv(row.get('rendimiento_esperado_kg_ha'), '.0f')} kg/ha")
        st.metric("Precio mercado", f"€{_fv(row.get('precio_mercado_eur_kg'), '.2f')}/kg")

    # 2. Resultado del modelo
    if not predictions_df.empty and "nivel_riesgo" in row:
        st.markdown("---")
        st.markdown("<div class='section-title'>🎯 Resultado del modelo</div>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            riesgo = str(row.get("nivel_riesgo", "—")).replace("_", " ").title()
            color_r = {"bajo": "#4CAF50", "medio": "#FFC107", "alto": "#FF9800", "muy alto": "#F44336"}.get(riesgo.lower(), "#999")
            st.markdown(
                f"<div style='text-align:center;background:#fff;padding:12px;border-radius:10px;"
                f"border-top:4px solid {color_r};box-shadow:0 2px 5px rgba(0,0,0,.06)'>"
                f"<div style='font-size:9px;color:#7A9A6E;text-transform:uppercase;font-weight:600'>Predicción de riesgo</div>"
                f"<div style='font-size:18px;font-weight:700;color:{color_r}'>{riesgo}</div></div>",
                unsafe_allow_html=True,
            )
        with col2:
            st.metric("Pérdida estimada", f"{_fv(row.get('pct_perdida_pred_pct'))}%")
        with col3:
            st.metric("Impacto €/ha", f"€{_fv(row.get('impacto_eur_ha_pred'))}")
        with col4:
            st.metric("Impacto total", f"€{_fv(row.get('impacto_total_eur'), '.0f')}")

        # Posición en ranking
        if not modeling_df.empty and "impacto_total_eur" in modeling_df.columns:
            ranking = modeling_df.sort_values("impacto_total_eur", ascending=False).reset_index(drop=True)
            pos = ranking[ranking["parcel_id"].astype(str) == str(selected_parcel_id)].index
            if len(pos) > 0:
                st.caption(f"Posición en ranking de impacto: #{pos[0]+1} de {len(ranking)}")

    # 3. Mapa enfocado
    st.markdown("---")
    st.markdown("<div class='section-title'>🗺 Mapa de la parcela</div>", unsafe_allow_html=True)
    try:
        gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
        ov_gdf = filter_ov(gdf)
        map_gdf = _build_map_gdf(ov_gdf, enriched_df, predictions_df if not predictions_df.empty else None)

        col_m, col_b = st.columns([2, 1])
        with col_m:
            map_mode_p = st.selectbox(
                "Modo mapa",
                options=["riesgo", "impacto_economico", "encharcamiento", "pendiente", "uso_sigpac"],
                format_func=lambda x: {
                    "riesgo": "🎯 Predicción de riesgo",
                    "impacto_economico": "💶 Impacto económico",
                    "encharcamiento": "💧 Encharcamiento",
                    "pendiente": "⛰️ Pendiente",
                    "uso_sigpac": "🗺 Uso SIGPAC",
                }[x],
                label_visibility="collapsed",
                key="detalle_map_mode",
            )
        with col_b:
            basemap_p = st.selectbox("Mapa base", list(BASEMAPS.keys()), label_visibility="collapsed", key="detalle_basemap")

        folium_map = build_parcels_map(
            map_gdf, filter_ov=False, mode=map_mode_p,
            predictions_df=None, basemap=basemap_p,
            selected_parcel_id=str(selected_parcel_id),
        )
        from streamlit_folium import st_folium
        st_folium(folium_map, use_container_width=True, height=420, key="detalle_map")
    except Exception as e:
        st.warning(f"No se pudo renderizar el mapa: {str(e)}")

    # 4. Variables ambientales
    st.markdown("---")
    st.markdown("<div class='section-title'>🌍 Variables ambientales</div>", unsafe_allow_html=True)

    tab_met, tab_suelo, tab_topo = st.tabs(["🌧 Meteorología", "🌱 Suelo", "⛰️ Topografía / Hidrología"])
    with tab_met:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Lluvia 72h", f"{_fv(row.get('rain_72h_mm'), '.1f')} mm")
            st.metric("Lluvia 7 días", f"{_fv(row.get('rain_7d_mm'), '.1f')} mm")
        with col2:
            st.metric("Temperatura media 7d", f"{_fv(row.get('temp_media_7d'), '.1f')} °C")
            st.metric("Humedad suelo", f"{_fv(row.get('humedad_suelo_%'), '.1f')}%")

    with tab_suelo:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Tipo de suelo", row.get("tipo_suelo", "—"))
            st.metric("Drenaje", row.get("drenaje", "—"))
        with col2:
            st.metric("Materia orgánica", f"{_fv(row.get('materia_organica_%'), '.2f')}%")
            st.metric("Profundidad suelo", f"{_fv(row.get('profundidad_suelo_cm'), '.0f')} cm")

    with tab_topo:
        col1, col2 = st.columns(2)
        with col1:
            slope_val = row.get("pendiente_%") or row.get("pendiente_pct")
            st.metric("Pendiente", f"{_fv(slope_val, '.0f')}%")
            st.metric("Altitud", f"{_fv(row.get('altitud_m'), '.0f')} m")
        with col2:
            st.metric("Distancia a cauce", f"{_fv(row.get('distancia_rio_m'), '.0f')} m")
            st.metric("Encharcamiento estimado", f"{_fv(row.get('duracion_encharcamiento_dias'), '.1f')} días")

    # 5. Factores de riesgo
    st.markdown("---")
    st.markdown("<div class='section-title'>⚠️ Factores principales de riesgo</div>", unsafe_allow_html=True)
    factors = _parcel_risk_factors(row)
    if factors:
        for f in factors:
            st.warning(f)
    else:
        st.success("No se detectaron factores de riesgo significativos bajo las condiciones actuales.")

    # 6. Interpretación rápida
    if "nivel_riesgo" in row:
        st.markdown("---")
        st.markdown("<div class='section-title'>💬 Interpretación rápida</div>", unsafe_allow_html=True)
        st.info(_quick_interpretation(row))


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def render_page_modeling(
    selected_client: str,
    enriched_df: pd.DataFrame | None,
    selected_parcel_id: str | None = None,
    predictions_df: pd.DataFrame | None = None,
) -> None:
    """Renderiza la pestaña Modelado según estado (general o parcela)."""

    if selected_parcel_id and selected_parcel_id != "— Ninguna —":
        _render_parcel_detail(selected_client, selected_parcel_id, enriched_df, predictions_df)
    else:
        _render_general(selected_client, enriched_df, predictions_df)
