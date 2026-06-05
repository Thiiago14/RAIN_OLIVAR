"""
Tarjetas KPI para dashboard de predicción.
"""
import streamlit as st
import pandas as pd


def show_prediction_kpis(predictions_df: pd.DataFrame | None) -> None:
    """Muestra tarjetas KPI principales de predicción."""
    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones para mostrar KPIs")
        return

    n_parcelas = len(predictions_df)
    perdida_media = predictions_df["pct_perdida_pred"].mean() * 100
    perdida_max = predictions_df["pct_perdida_pred"].max() * 100
    impacto_total = predictions_df["impacto_total_eur"].sum()
    impacto_medio_ha = predictions_df["impacto_eur_ha_pred"].mean()

    n_alto_muy_alto = int(
        predictions_df["nivel_riesgo"].isin(["alto", "muy_alto"]).sum()
    )

    # Parcela más crítica
    if not predictions_df.empty:
        idx_critica = predictions_df["impacto_total_eur"].idxmax()
        parcela_critica = predictions_df.loc[idx_critica, "parcel_id"]
    else:
        parcela_critica = "—"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Parcelas analizadas", n_parcelas)
    with col2:
        st.metric("Pérdida media estimada", f"{perdida_media:.2f}%")
    with col3:
        st.metric("Pérdida máxima", f"{perdida_max:.2f}%")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Impacto total estimado", f"EUR {impacto_total:,.0f}")
    with col2:
        st.metric("Impacto medio €/ha", f"EUR {impacto_medio_ha:,.2f}")
    with col3:
        st.metric("Parcelas en riesgo alto/muy alto", n_alto_muy_alto)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Parcela más crítica", parcela_critica)
    with col2:
        riesgo_dist = {
            "bajo": int((predictions_df["nivel_riesgo"] == "bajo").sum()),
            "medio": int((predictions_df["nivel_riesgo"] == "medio").sum()),
            "alto": int((predictions_df["nivel_riesgo"] == "alto").sum()),
            "muy_alto": int((predictions_df["nivel_riesgo"] == "muy_alto").sum()),
        }
        riesgo_str = " / ".join([f"{k}:{v}" for k, v in riesgo_dist.items()])
        st.metric("Distribución riesgo", riesgo_str, label_visibility="collapsed")
