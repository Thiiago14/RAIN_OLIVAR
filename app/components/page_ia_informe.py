"""
Pestaña IA e Informe.

Estado A (sin parcela): análisis ejecutivo general + PDF del cliente.
Estado B (con parcela): análisis completo 7-secciones + PDF de parcela.
"""
import streamlit as st
import pandas as pd

from src.features.llm_engine import (
    generate_general_analysis,
    generate_parcel_analysis,
    load_llm_output,
)
from src.features.pdf_generator import generate_pdf_report


def _fv(v, fmt=".2f", default="—"):
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return str(default)


def _risk_color(nivel: str) -> str:
    return {"bajo": "#4CAF50", "medio": "#FFC107", "alto": "#FF9800",
            "muy_alto": "#F44336"}.get(str(nivel).lower().strip(), "#999")


def _risk_badge(nivel: str) -> str:
    color = _risk_color(nivel)
    label = str(nivel).replace("_", " ").title()
    return (f"<span style='background:{color};color:#fff;padding:3px 10px;"
            f"border-radius:20px;font-size:11px;font-weight:700'>{label}</span>")


# ---------------------------------------------------------------------------
# Estado A: vista general (sin parcela)
# ---------------------------------------------------------------------------

def _render_general_ia(selected_client: str, modeling_df: pd.DataFrame | None) -> None:
    """Vista general IA del cliente."""

    st.markdown(
        "<h2 style='color:#2D5016;margin-bottom:2px'>🧠 Análisis IA del cliente</h2>"
        "<p style='color:#7A9A6E;font-size:13px;margin-top:0'>"
        "Evaluación agronómica, riesgos y recomendaciones para el conjunto de parcelas.</p>",
        unsafe_allow_html=True,
    )

    if modeling_df is None or modeling_df.empty:
        st.warning("No hay predicciones disponibles. Genera predicciones en la pestaña Modelado primero.")
        return

    prev = load_llm_output(selected_client, None)
    has_prev = prev is not None

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        lbl = "🔄 Regenerar análisis IA" if has_prev else "🧠 Generar análisis IA"
        if st.button(lbl, use_container_width=True, type="primary", key="btn_gen_general"):
            with st.spinner("Analizando datos agronómicos..."):
                prev = generate_general_analysis(selected_client, modeling_df)
                st.success("Análisis generado.")
                st.rerun()
    with col_info:
        if has_prev:
            st.caption(f"Análisis previo del {prev.get('created_at','—')[:16]}. "
                       f"Fuente: {'LLM (Claude)' if prev.get('source')=='llm' else 'Reglas agronómicas'}. "
                       f"Pulsa para actualizar.")
        else:
            st.caption("Pulsa el botón para generar el análisis agronómico.")

    if not prev:
        return

    st.markdown("---")

    # A. Resumen ejecutivo
    if prev.get("summary"):
        st.markdown("#### A. Resumen ejecutivo")
        st.info(prev["summary"])

    # B. Riesgos principales
    risks = prev.get("risks", [])
    st.markdown("#### B. Riesgos principales detectados")
    if risks:
        for r in risks:
            st.warning(str(r))
    else:
        st.success("No se detectaron riesgos significativos bajo las condiciones actuales.")

    # C. Parcelas prioritarias (cards)
    priority = prev.get("priority_parcels", [])
    if priority:
        st.markdown("#### C. Parcelas prioritarias")
        cols = st.columns(min(len(priority), 3))
        for i, p in enumerate(priority[:3]):
            pid = p.get("parcela", p.get("parcel_id", "—"))
            nivel = str(p.get("riesgo", "—"))
            perdida = p.get("perdida_%", "—")
            impacto = p.get("impacto_total", "—")
            motivo = p.get("motivo", "—")
            color = _risk_color(nivel)
            with cols[i % 3]:
                st.markdown(
                    f"<div style='background:#fff;border-radius:10px;padding:12px;"
                    f"border-left:4px solid {color};box-shadow:0 2px 5px rgba(0,0,0,.07);margin-bottom:8px'>"
                    f"<div style='font-weight:700;color:#1E3A2F;font-size:12px'>{pid}</div>"
                    f"<div style='font-size:11px;color:#7A9A6E;margin-top:2px'>"
                    f"Riesgo: <b>{nivel}</b> · Pérdida: <b>{perdida}</b></div>"
                    f"<div style='font-size:11px;color:#7A9A6E'>Impacto: <b>{impacto}</b></div>"
                    f"<div style='font-size:10px;color:#aaa;margin-top:4px'>{motivo}</div></div>",
                    unsafe_allow_html=True,
                )

    # D. Recomendaciones
    recs = prev.get("recommendations", {})
    if recs:
        st.markdown("#### D. Recomendaciones")
        if isinstance(recs, dict):
            for grupo, items in recs.items():
                lbl = grupo.replace("_", " ").title()
                icon = {"Corto Plazo": "⚡", "Medio Plazo": "📅", "Seguimiento": "👁️"}.get(lbl, "•")
                with st.expander(f"{icon} {lbl}", expanded=(grupo == "corto_plazo")):
                    for item in (items if isinstance(items, list) else [items]):
                        st.markdown(f"- {item}")
        elif isinstance(recs, list):
            for item in recs:
                st.markdown(f"- {item}")

    # E. Acción prioritaria general (del report_sections si existe)
    report = prev.get("report_sections", {})
    action = None
    for key in ("accion_sugerida", "accion_automatica", "suggested_action"):
        if report.get(key):
            action = report[key]
            break
    if action:
        st.markdown("#### E. Acción prioritaria general")
        st.success(action)

    # F. Botón PDF
    st.markdown("---")
    st.markdown("#### Generar informe PDF general")
    col_pdf, col_info2 = st.columns([1, 2])
    with col_pdf:
        if st.button("📄 Generar y descargar PDF", use_container_width=True, key="btn_pdf_general"):
            with st.spinner("Generando informe PDF completo..."):
                try:
                    # Reunir análisis de parcelas prioritarias (top 5)
                    llm_parcel_outputs = {}
                    if "impacto_total_eur" in modeling_df.columns:
                        top_pids = modeling_df.nlargest(5, "impacto_total_eur")["parcel_id"].astype(str).tolist()
                        for pid in top_pids:
                            parcel_out = load_llm_output(selected_client, pid)
                            if parcel_out:
                                llm_parcel_outputs[pid] = parcel_out

                    pdf_bytes = generate_pdf_report(
                        client_id=selected_client,
                        mode="general",
                        modeling_df=modeling_df,
                        llm_output=prev,
                        llm_parcel_outputs=llm_parcel_outputs or None,
                    )
                    st.download_button(
                        label="⬇️ Descargar informe PDF",
                        data=pdf_bytes,
                        file_name=f"informe_{selected_client}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as e:
                    import traceback
                    st.error(f"Error generando PDF: {str(e)}")
                    with st.expander("Detalle"):
                        st.code(traceback.format_exc())
    with col_info2:
        st.caption(
            "El informe incluye: resumen ejecutivo, KPIs, distribución de riesgo, "
            "top parcelas, riesgos, recomendaciones, análisis detallado de parcelas "
            "prioritarias y tabla completa de predicciones."
        )


# ---------------------------------------------------------------------------
# Estado B: vista por parcela
# ---------------------------------------------------------------------------

def _render_parcel_ia(
    selected_client: str,
    selected_parcel_id: str,
    enriched_df: pd.DataFrame | None,
    modeling_df: pd.DataFrame | None,
) -> None:
    """Vista de análisis IA para una parcela individual."""

    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("← General", key="btn_back_ia"):
            st.session_state["selected_parcel_id"] = None
            st.rerun()
    with col_title:
        st.markdown(
            f"<h2 style='color:#2D5016;margin-bottom:0'>🧠 Análisis IA · {selected_parcel_id}</h2>",
            unsafe_allow_html=True,
        )

    if enriched_df is None or enriched_df.empty:
        st.error("No hay datos enriquecidos.")
        return

    # Construir parcel_data con TODOS los datos (enriquecimiento + predicciones)
    parcel_row = enriched_df[enriched_df["parcel_id"].astype(str) == str(selected_parcel_id)]
    if parcel_row.empty:
        st.error(f"Parcela {selected_parcel_id} no encontrada.")
        return

    parcel_data = parcel_row.iloc[0].to_dict()

    # Siempre añadir valores de predicción desde modeling_df (clave correcta)
    if modeling_df is not None and not modeling_df.empty:
        pred_row = modeling_df[modeling_df["parcel_id"].astype(str) == str(selected_parcel_id)]
        if not pred_row.empty:
            for col in ["nivel_riesgo", "pct_perdida_pred_pct", "pct_perdida_pred",
                        "impacto_eur_ha_pred", "impacto_total_eur"]:
                if col in pred_row.columns:
                    parcel_data[col] = pred_row.iloc[0][col]

    # Normalizar tipos serializables
    parcel_data_clean = {}
    for k, v in parcel_data.items():
        if hasattr(v, "item"):
            parcel_data_clean[k] = v.item()
        elif isinstance(v, float) and pd.isna(v):
            parcel_data_clean[k] = None
        else:
            parcel_data_clean[k] = v

    # Ficha rápida superior
    st.markdown("---")
    nivel = str(parcel_data.get("nivel_riesgo", "—")).replace("_", " ")
    color_r = _risk_color(nivel.lower().replace(" ", "_"))
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tipo de olivar", parcel_data.get("tipo_olivar", "—"))
        st.metric("Variedad", parcel_data.get("variedad", "—"))
        st.metric("Riego", parcel_data.get("riego", "—"))
    with col2:
        st.metric("Fenología", parcel_data.get("estado_fenologico", "—"))
        st.metric("Superficie", f"{_fv(parcel_data.get('superficie_ha'), '.4f')} ha")
        st.metric("Rendimiento", f"{_fv(parcel_data.get('rendimiento_esperado_kg_ha'), '.0f')} kg/ha")
    with col3:
        st.metric("Pérdida predicha", f"{_fv(parcel_data.get('pct_perdida_pred_pct'))}%")
        st.metric("Impacto €/ha", f"€{_fv(parcel_data.get('impacto_eur_ha_pred'))}")
        st.metric("Impacto total", f"€{_fv(parcel_data.get('impacto_total_eur'), '.0f')}")
    with col4:
        st.markdown(
            f"<div style='background:{color_r};color:#fff;border-radius:10px;padding:14px;"
            f"text-align:center;margin-top:4px'>"
            f"<div style='font-size:9px;text-transform:uppercase;font-weight:600;opacity:.8'>Nivel de riesgo</div>"
            f"<div style='font-size:20px;font-weight:700;margin-top:4px'>{nivel.title()}</div></div>",
            unsafe_allow_html=True,
        )

    # Botón generar análisis
    st.markdown("---")
    prev = load_llm_output(selected_client, selected_parcel_id)
    has_prev = prev is not None

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        lbl = "🔄 Regenerar análisis" if has_prev else "🧠 Generar análisis IA"
        if st.button(lbl, use_container_width=True, type="primary",
                     key=f"btn_gen_{selected_parcel_id}"):
            with st.spinner("Analizando datos de la parcela..."):
                prev = generate_parcel_analysis(
                    selected_client, selected_parcel_id, parcel_data_clean
                )
                st.success("Análisis generado.")
                st.rerun()
    with col_info:
        if has_prev:
            st.caption(
                f"Análisis del {prev.get('created_at','—')[:16]}. "
                f"Fuente: {'LLM (Claude)' if prev.get('source')=='llm' else 'Reglas agronómicas'}."
            )
        else:
            st.caption("Genera el análisis IA para obtener evaluación agronómica completa.")

    if not prev:
        return

    # Las 7 secciones del prompt agronómico
    st.markdown("---")
    st.markdown("#### Análisis agronómico completo")

    # 1. Evaluación agronómica
    with st.expander("1. Evaluación agronómica", expanded=True):
        text = prev.get("agronomic_evaluation", "")
        if text:
            st.info(text)
        else:
            st.caption("Sin datos.")

    # 2. Riesgos detectados
    with st.expander("2. Riesgos detectados", expanded=True):
        risks = prev.get("detected_risks", [])
        if risks:
            for r in risks:
                st.warning(str(r))
        else:
            st.success("No se detectaron riesgos significativos.")

    # 3. Estimación de pérdida
    with st.expander("3. Estimación de pérdida"):
        text = prev.get("loss_estimation", "")
        if text:
            st.write(text)
        else:
            st.caption("Sin datos.")

    # 4. Impacto económico
    with st.expander("4. Impacto económico"):
        text = prev.get("economic_impact", "")
        if text:
            st.write(text)
        else:
            st.caption("Sin datos.")

    # 5. Recomendaciones técnicas
    with st.expander("5. Recomendaciones técnicas", expanded=True):
        recs = prev.get("technical_recommendations", [])
        if recs:
            for r in recs:
                st.markdown(f"- {r}")
        else:
            st.caption("Sin recomendaciones generadas.")

    # 6. Acción automática sugerida
    with st.expander("6. Acción automática sugerida", expanded=True):
        action = prev.get("suggested_action", "")
        if action:
            st.success(action)
        else:
            st.caption("Sin acción sugerida.")

    # 7. Nivel de riesgo (siempre desde modeling_df, no del cache)
    nivel_real = str(parcel_data.get("nivel_riesgo", prev.get("risk_level", "—")))
    nivel_display = nivel_real.replace("_", " ").title()
    color_final = _risk_color(nivel_real.lower().replace(" ", "_"))
    with st.expander("7. Nivel de riesgo", expanded=True):
        st.markdown(
            f"<div style='display:inline-block;background:{color_final};color:#fff;"
            f"padding:6px 18px;border-radius:20px;font-weight:700;font-size:14px'>"
            f"{nivel_display}</div>",
            unsafe_allow_html=True,
        )

    # Botón PDF individual
    st.markdown("---")
    col_pdf, col_pdf_info = st.columns([1, 2])
    with col_pdf:
        if st.button("📄 Generar PDF de parcela", use_container_width=True,
                     key=f"btn_pdf_{selected_parcel_id}"):
            with st.spinner("Generando informe..."):
                try:
                    pdf_bytes = generate_pdf_report(
                        client_id=selected_client,
                        mode="parcel",
                        parcel_id=selected_parcel_id,
                        parcel_data=parcel_data_clean,
                        llm_output=prev,
                    )
                    st.download_button(
                        label="⬇️ Descargar informe de parcela",
                        data=pdf_bytes,
                        file_name=f"informe_{selected_client}_{selected_parcel_id}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as e:
                    import traceback
                    st.error(f"Error: {str(e)}")
                    with st.expander("Detalle"):
                        st.code(traceback.format_exc())
    with col_pdf_info:
        st.caption(
            "El PDF de parcela incluye: identificación, datos productivos, "
            "variables ambientales, resultado del modelo y análisis agronómico completo."
        )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def render_page_ia_informe(
    selected_client: str,
    enriched_df: pd.DataFrame | None = None,
    modeling_df: pd.DataFrame | None = None,
    selected_parcel_id: str | None = None,
) -> None:
    """Renderiza la pestaña IA e Informe según estado."""
    if selected_parcel_id and selected_parcel_id != "— Ninguna —":
        _render_parcel_ia(selected_client, selected_parcel_id, enriched_df, modeling_df)
    else:
        _render_general_ia(selected_client, modeling_df)
