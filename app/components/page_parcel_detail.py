"""
Página de análisis detallado por parcela.
Muestra datos completos de una parcela seleccionada.
"""
import streamlit as st
import pandas as pd


def render_page_parcel_detail(
    selected_parcel_id: str | None,
    enriched_df: pd.DataFrame | None,
    predictions_df: pd.DataFrame | None,
) -> None:
    """Página de detalle de parcela."""

    st.markdown('<div class="section-title">🔎 Análisis por parcela</div>', unsafe_allow_html=True)

    # Obtener datos de la parcela
    if enriched_df is None or enriched_df.empty:
        st.error("No hay datos de parcelas cargados.")
        return

    # Crear DataFrame combinado con predicciones si existen
    merged_df = enriched_df.copy()
    if predictions_df is not None and not predictions_df.empty:
        merge_key = "parcel_uid" if "parcel_uid" in enriched_df.columns and "parcel_uid" in predictions_df.columns else "parcel_id"
        merged_df[merge_key] = merged_df[merge_key].astype(str)
        pred_copy = predictions_df.copy()
        pred_copy[merge_key] = pred_copy[merge_key].astype(str)
        merged_df = merged_df.merge(pred_copy, on=merge_key, how="left", suffixes=("", "_pred"))

    # Selector de parcela dentro de la página
    parcel_options = sorted(merged_df["parcel_id"].unique().tolist())
    if not parcel_options:
        st.error("No hay parcelas disponibles.")
        return

    # Usar selected_parcel_id de session_state si existe y es válido
    if selected_parcel_id is None or selected_parcel_id not in parcel_options or selected_parcel_id == "— Ninguna —":
        selected_parcel_id = parcel_options[0]

    selected_parcel_id = st.selectbox(
        "Selecciona parcela",
        options=parcel_options,
        index=parcel_options.index(selected_parcel_id) if selected_parcel_id in parcel_options else 0,
        label_visibility="collapsed",
    )

    # Guardar en session_state
    st.session_state["selected_parcel_id"] = selected_parcel_id

    # Obtener datos de la parcela seleccionada
    parcel_data = merged_df[merged_df["parcel_id"] == selected_parcel_id]
    if parcel_data.empty:
        st.error(f"Parcela {selected_parcel_id} no encontrada.")
        return

    parcel_row = parcel_data.iloc[0]

    # === IDENTIFICACIÓN ===
    st.markdown("### Identificación")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Parcela ID", selected_parcel_id)
    with col2:
        st.metric("Cliente", parcel_row.get("client_id", "—"))
    with col3:
        st.metric("Provincia", parcel_row.get("zona_provincia", "—"))
    with col4:
        st.metric("Uso SIGPAC", parcel_row.get("uso_sigpac", "—"))

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Superficie", f"{parcel_row.get('superficie_ha', 0):.4f} ha")
    with col2:
        st.metric("Altitud", f"{int(parcel_row.get('altitud_m', 0))} m")

    # === DATOS PRODUCTIVOS ===
    st.markdown("### Datos productivos")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Tipo olivar", parcel_row.get("tipo_olivar", "—"))
    with col2:
        st.metric("Riego", parcel_row.get("riego", "—"))
    with col3:
        st.metric("Variedad", parcel_row.get("variedad", "—"))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Fenología", parcel_row.get("estado_fenologico", "—"))
    with col2:
        st.metric("Rendimiento", f"{parcel_row.get('rendimiento_esperado_kg_ha', 0):.0f} kg/ha")
    with col3:
        st.metric("Precio mercado", f"€ {parcel_row.get('precio_mercado_eur_kg', 0):.2f}/kg")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Coste variable", f"€ {parcel_row.get('coste_variable_ha', 0):.0f}/ha")

    # === VARIABLES AMBIENTALES ===
    st.markdown("### Variables ambientales")

    tab1, tab2, tab3 = st.tabs(["Meteorología", "Suelo", "Topografía"])

    with tab1:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Lluvia 72h", f"{parcel_row.get('rain_72h_mm', 0):.1f} mm")
        with col2:
            st.metric("Lluvia 7d", f"{parcel_row.get('rain_7d_mm', 0):.1f} mm")
        with col3:
            st.metric("Temp media 7d", f"{parcel_row.get('temp_media_7d', 0):.1f}°C")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Humedad suelo", f"{parcel_row.get('humedad_suelo_%', 0):.1f}%")

    with tab2:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Tipo suelo", parcel_row.get("tipo_suelo", "—"))
        with col2:
            st.metric("Drenaje", parcel_row.get("drenaje", "—"))
        with col3:
            st.metric("Materia orgánica", f"{parcel_row.get('materia_organica_%', 0):.2f}%")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Profundidad suelo", f"{int(parcel_row.get('profundidad_suelo_cm', 0))} cm")

    with tab3:
        col1, col2, col3 = st.columns(3)
        with col1:
            pendiente = parcel_row.get("pendiente_%", 0)
            st.metric("Pendiente", f"{pendiente:.0f}%")
            if pendiente > 100:
                st.error("⚠️ Valor extremo - revisar SIGPAC")
            elif pendiente > 60:
                st.warning("⚠️ Pendiente elevada")
        with col2:
            st.metric("Distancia a cauce", f"{parcel_row.get('distancia_rio_m', 0):.0f} m")
        with col3:
            st.metric("Encharcamiento", f"{parcel_row.get('duracion_encharcamiento_dias', 0):.1f} días")

    # === RESULTADO ML ===
    if predictions_df is not None and not predictions_df.empty:
        pred_row = predictions_df[predictions_df["parcel_id"] == selected_parcel_id]
        if not pred_row.empty:
            st.markdown("### Resultado del modelo ML")

            pred = pred_row.iloc[0]
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Pérdida predicha", f"{pred.get('pct_perdida_pred_pct', 0):.2f}%")
            with col2:
                st.metric("Nivel riesgo", pred.get("nivel_riesgo", "—"))
            with col3:
                st.metric("Impacto /ha", f"€ {pred.get('impacto_eur_ha_pred', 0):.2f}")
            with col4:
                st.metric("Impacto total", f"€ {pred.get('impacto_total_eur', 0):.2f}")

            # === FACTORES DE RIESGO ===
            st.markdown("### Factores principales de riesgo")

            risk_factors = []

            rain_7d = parcel_row.get("rain_7d_mm", 0)
            if rain_7d > 30:
                risk_factors.append(("🌧️", f"Lluvia acumulada elevada ({rain_7d:.1f} mm)"))

            humedad = parcel_row.get("humedad_suelo_%", 0)
            if humedad > 60:
                risk_factors.append(("💧", f"Humedad suelo elevada ({humedad:.1f}%)"))

            drenaje = parcel_row.get("drenaje", "")
            if drenaje in ("Moderado", "Malo"):
                risk_factors.append(("🌊", f"Drenaje comprometido ({drenaje})"))

            pendiente = parcel_row.get("pendiente_%", 0)
            if pendiente > 60:
                risk_factors.append(("⛰️", f"Pendiente extrema ({pendiente:.0f}%)"))

            encharcamiento = parcel_row.get("duracion_encharcamiento_dias", 0)
            if encharcamiento > 3:
                risk_factors.append(("💦", f"Encharcamiento alto ({encharcamiento:.1f} días)"))

            distancia_rio = parcel_row.get("distancia_rio_m", float("inf"))
            if distancia_rio < 100:
                risk_factors.append(("🏞️", f"Proximidad a cauce ({distancia_rio:.0f} m)"))

            if risk_factors:
                for emoji, factor in risk_factors:
                    st.warning(f"{emoji} {factor}")
            else:
                st.success("✓ No se detectaron factores de riesgo significativos")
