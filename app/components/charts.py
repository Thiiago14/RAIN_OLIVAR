"""
Gráficos interactivos para análisis de predicciones.
Usa Plotly si está disponible, si no usa Altair.
"""
import streamlit as st
import pandas as pd
import numpy as np

try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import altair as alt
    HAS_ALTAIR = True
except ImportError:
    HAS_ALTAIR = False


def show_risk_distribution(predictions_df: pd.DataFrame | None) -> None:
    """Gráfico de distribución de riesgo por nivel."""
    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones")
        return

    risk_counts = predictions_df["nivel_riesgo"].value_counts().sort_index()

    if HAS_PLOTLY:
        fig = px.bar(
            x=risk_counts.index,
            y=risk_counts.values,
            labels={"x": "Nivel de riesgo", "y": "Número de parcelas"},
            color=risk_counts.index,
            color_discrete_map={
                "bajo": "#4CAF50",
                "medio": "#FFC107",
                "alto": "#FF9800",
                "muy_alto": "#F44336",
            },
            title="Distribución de riesgo por nivel",
        )
        fig.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(risk_counts, use_container_width=True)


def show_top_parcels_by_loss(predictions_df: pd.DataFrame | None, top_n: int = 10) -> None:
    """Top parcelas por pérdida estimada."""
    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones")
        return

    top_df = (
        predictions_df.nlargest(top_n, "pct_perdida_pred_pct")[
            ["parcel_id", "pct_perdida_pred_pct"]
        ]
        .reset_index(drop=True)
    )

    if HAS_PLOTLY:
        fig = px.bar(
            top_df,
            x="pct_perdida_pred_pct",
            y="parcel_id",
            orientation="h",
            labels={"pct_perdida_pred_pct": "Pérdida (%)", "parcel_id": "Parcela"},
            title=f"Top {top_n} parcelas por pérdida estimada",
            color="pct_perdida_pred_pct",
            color_continuous_scale="RdYlGn_r",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(top_df.set_index("parcel_id"), use_container_width=True)


def show_top_parcels_by_impact(predictions_df: pd.DataFrame | None, top_n: int = 10) -> None:
    """Top parcelas por impacto económico total."""
    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones")
        return

    top_df = (
        predictions_df.nlargest(top_n, "impacto_total_eur")[
            ["parcel_id", "impacto_total_eur"]
        ]
        .reset_index(drop=True)
    )

    if HAS_PLOTLY:
        fig = px.bar(
            top_df,
            x="impacto_total_eur",
            y="parcel_id",
            orientation="h",
            labels={"impacto_total_eur": "Impacto (EUR)", "parcel_id": "Parcela"},
            title=f"Top {top_n} parcelas por impacto económico",
            color="impacto_total_eur",
            color_continuous_scale="Reds",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(top_df.set_index("parcel_id"), use_container_width=True)


def show_scatter_loss_vs_rain(predictions_df: pd.DataFrame | None) -> None:
    """Scatter: Lluvia 7d vs Pérdida estimada."""
    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones")
        return

    # Validar columnas necesarias
    required_cols = ["parcel_id", "rain_7d_mm", "pct_perdida_pred_pct"]
    missing_cols = [col for col in required_cols if col not in predictions_df.columns]
    if missing_cols:
        st.info("No hay datos de lluvia disponibles para este gráfico.")
        return

    df_plot = predictions_df[required_cols].copy()
    df_plot = df_plot.dropna()

    if df_plot.empty:
        st.info("Sin datos completos para gráfico")
        return

    if HAS_PLOTLY:
        fig = px.scatter(
            df_plot,
            x="rain_7d_mm",
            y="pct_perdida_pred_pct",
            hover_name="parcel_id",
            labels={"rain_7d_mm": "Lluvia 7d (mm)", "pct_perdida_pred_pct": "Pérdida (%)"},
            title="Relación: Lluvia vs Pérdida estimada",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.scatter_chart(df_plot.set_index("parcel_id"), use_container_width=True)


def show_scatter_waterlogging_vs_loss(predictions_df: pd.DataFrame | None) -> None:
    """Scatter: Duración encharcamiento vs Pérdida."""
    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones")
        return

    # Validar columnas necesarias
    required_cols = ["parcel_id", "duracion_encharcamiento_dias", "pct_perdida_pred_pct"]
    missing_cols = [col for col in required_cols if col not in predictions_df.columns]
    if missing_cols:
        st.info("No hay datos de encharcamiento disponibles para este gráfico.")
        return

    df_plot = predictions_df[required_cols].copy()
    df_plot.columns = ["parcel_id", "Encharcamiento (días)", "Pérdida (%)"]
    df_plot = df_plot.dropna()

    if df_plot.empty:
        st.info("Sin datos completos para gráfico")
        return

    if HAS_PLOTLY:
        fig = px.scatter(
            df_plot,
            x="Encharcamiento (días)",
            y="Pérdida (%)",
            hover_name="parcel_id",
            title="Relación: Encharcamiento vs Pérdida",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.scatter_chart(df_plot.set_index("parcel_id"), use_container_width=True)


def show_loss_by_parcel_bars(predictions_df: pd.DataFrame | None) -> None:
    """Barras de pérdida para todas las parcelas."""
    if predictions_df is None or predictions_df.empty:
        st.info("Sin predicciones")
        return

    df_plot = (
        predictions_df[["parcel_id", "pct_perdida_pred_pct"]]
        .sort_values("pct_perdida_pred_pct", ascending=False)
        .reset_index(drop=True)
    )

    if HAS_PLOTLY:
        fig = px.bar(
            df_plot,
            x="parcel_id",
            y="pct_perdida_pred_pct",
            labels={"pct_perdida_pred_pct": "Pérdida (%)", "parcel_id": "Parcela"},
            title="Pérdida estimada por parcela (ordenado desc.)",
            color="pct_perdida_pred_pct",
            color_continuous_scale="RdYlGn_r",
        )
        fig.update_layout(xaxis_tickangle=-45, height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(df_plot.set_index("parcel_id"), use_container_width=True)
