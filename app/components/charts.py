"""
Gráficos interactivos para análisis de predicciones.
Usa Plotly si está disponible; si no, Streamlit nativo.
"""
import streamlit as st
import pandas as pd

try:
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# Mapa de colores por nivel de riesgo
RISK_COLOR_MAP = {
    "bajo": "#4CAF50",
    "medio": "#FFC107",
    "alto": "#FF9800",
    "muy_alto": "#F44336",
}

RISK_ORDER = ["bajo", "medio", "alto", "muy_alto"]


def _require_cols(df: pd.DataFrame, cols: list[str], context: str) -> bool:
    """Retorna True si todas las columnas existen, si no muestra info."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        st.info(f"No hay datos disponibles para este gráfico ({context}).")
        return False
    return True


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Distribución de riesgo
# ---------------------------------------------------------------------------
def show_risk_distribution(df: pd.DataFrame | None) -> None:
    """Bar chart: distribución por nivel de riesgo."""
    if df is None or df.empty or "nivel_riesgo" not in df.columns:
        st.info("Sin datos de riesgo disponibles.")
        return

    counts = (
        df["nivel_riesgo"]
        .value_counts()
        .reindex(RISK_ORDER, fill_value=0)
        .reset_index()
    )
    counts.columns = ["Nivel de riesgo", "Parcelas"]

    if HAS_PLOTLY:
        fig = px.bar(
            counts,
            x="Nivel de riesgo", y="Parcelas",
            color="Nivel de riesgo",
            color_discrete_map=RISK_COLOR_MAP,
            title="Distribución de riesgo por nivel",
            labels={"Nivel de riesgo": "", "Parcelas": "Número de parcelas"},
        )
        fig.update_layout(showlegend=False, height=360, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(counts.set_index("Nivel de riesgo"))


# ---------------------------------------------------------------------------
# Top parcelas por pérdida
# ---------------------------------------------------------------------------
def show_top_parcels_by_loss(df: pd.DataFrame | None, top_n: int = 10) -> None:
    """Bar chart horizontal: top N por pérdida estimada."""
    if not _require_cols(df, ["parcel_id", "pct_perdida_pred_pct"], "top pérdida"):
        return

    df = _to_numeric(df, ["pct_perdida_pred_pct"])
    plot_df = df.nlargest(top_n, "pct_perdida_pred_pct")[["parcel_id", "pct_perdida_pred_pct"]].copy()

    if HAS_PLOTLY:
        fig = px.bar(
            plot_df.sort_values("pct_perdida_pred_pct"),
            x="pct_perdida_pred_pct", y="parcel_id",
            orientation="h",
            title=f"Top {top_n} parcelas por pérdida estimada",
            labels={"pct_perdida_pred_pct": "Pérdida estimada (%)", "parcel_id": "Parcela"},
            color="pct_perdida_pred_pct",
            color_continuous_scale=["#4CAF50", "#FFC107", "#F44336"],
        )
        fig.update_layout(height=380, margin=dict(t=40, b=20), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(plot_df.set_index("parcel_id"))


# ---------------------------------------------------------------------------
# Top parcelas por impacto económico
# ---------------------------------------------------------------------------
def show_top_parcels_by_impact(df: pd.DataFrame | None, top_n: int = 10) -> None:
    """Bar chart horizontal: top N por impacto económico total."""
    if not _require_cols(df, ["parcel_id", "impacto_total_eur"], "top impacto"):
        return

    df = _to_numeric(df, ["impacto_total_eur"])
    plot_df = df.nlargest(top_n, "impacto_total_eur")[["parcel_id", "impacto_total_eur"]].copy()

    if HAS_PLOTLY:
        fig = px.bar(
            plot_df.sort_values("impacto_total_eur"),
            x="impacto_total_eur", y="parcel_id",
            orientation="h",
            title=f"Top {top_n} parcelas por impacto económico",
            labels={"impacto_total_eur": "Impacto total estimado (€)", "parcel_id": "Parcela"},
            color="impacto_total_eur",
            color_continuous_scale="Reds",
        )
        fig.update_layout(height=380, margin=dict(t=40, b=20), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(plot_df.set_index("parcel_id"))


# ---------------------------------------------------------------------------
# Barras de pérdida por todas las parcelas
# ---------------------------------------------------------------------------
def show_loss_by_parcel_bars(df: pd.DataFrame | None) -> None:
    """Bar chart: pérdida estimada de todas las parcelas."""
    if not _require_cols(df, ["parcel_id", "pct_perdida_pred_pct"], "pérdida por parcela"):
        return

    df = _to_numeric(df, ["pct_perdida_pred_pct"])
    plot_df = df[["parcel_id", "pct_perdida_pred_pct"]].sort_values(
        "pct_perdida_pred_pct", ascending=False
    )

    if HAS_PLOTLY:
        fig = px.bar(
            plot_df,
            x="parcel_id", y="pct_perdida_pred_pct",
            title="Pérdida estimada por parcela",
            labels={"parcel_id": "Parcela", "pct_perdida_pred_pct": "Pérdida estimada (%)"},
            color="pct_perdida_pred_pct",
            color_continuous_scale=["#4CAF50", "#FFC107", "#F44336"],
        )
        fig.update_layout(
            height=380, xaxis_tickangle=-45,
            margin=dict(t=40, b=60),
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(plot_df.set_index("parcel_id"))


# ---------------------------------------------------------------------------
# Scatter: lluvia 7d vs pérdida
# ---------------------------------------------------------------------------
def show_scatter_loss_vs_rain(df: pd.DataFrame | None) -> None:
    """Scatter: lluvia 7 días vs pérdida estimada."""
    required = ["parcel_id", "rain_7d_mm", "pct_perdida_pred_pct"]
    if not _require_cols(df, required, "lluvia vs pérdida"):
        return

    df = _to_numeric(df, ["rain_7d_mm", "pct_perdida_pred_pct", "superficie_ha"])
    plot_df = df[required + (["nivel_riesgo"] if "nivel_riesgo" in df.columns else [])
                 + (["superficie_ha"] if "superficie_ha" in df.columns else [])].dropna(
        subset=["rain_7d_mm", "pct_perdida_pred_pct"]
    )

    if plot_df.empty:
        st.info("Sin datos suficientes para el gráfico de lluvia vs pérdida.")
        return

    if HAS_PLOTLY:
        kwargs = dict(
            x="rain_7d_mm", y="pct_perdida_pred_pct",
            hover_name="parcel_id",
            title="Lluvia acumulada 7 días vs Pérdida estimada",
            labels={
                "rain_7d_mm": "Lluvia acumulada 7 días (mm)",
                "pct_perdida_pred_pct": "Pérdida estimada (%)",
            },
        )
        if "nivel_riesgo" in plot_df.columns:
            kwargs["color"] = "nivel_riesgo"
            kwargs["color_discrete_map"] = RISK_COLOR_MAP
        if "superficie_ha" in plot_df.columns:
            kwargs["size"] = "superficie_ha"
            kwargs["size_max"] = 20

        fig = px.scatter(plot_df, **kwargs)
        fig.update_layout(height=380, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.scatter_chart(plot_df.set_index("parcel_id")[["rain_7d_mm", "pct_perdida_pred_pct"]])


# ---------------------------------------------------------------------------
# Scatter: encharcamiento vs pérdida
# ---------------------------------------------------------------------------
def show_scatter_waterlogging_vs_loss(df: pd.DataFrame | None) -> None:
    """Scatter: duración de encharcamiento vs pérdida estimada."""
    required = ["parcel_id", "duracion_encharcamiento_dias", "pct_perdida_pred_pct"]
    if not _require_cols(df, required, "encharcamiento vs pérdida"):
        return

    df = _to_numeric(df, ["duracion_encharcamiento_dias", "pct_perdida_pred_pct", "superficie_ha"])
    plot_df = df[required + (["nivel_riesgo"] if "nivel_riesgo" in df.columns else [])
                 + (["superficie_ha"] if "superficie_ha" in df.columns else [])].dropna(
        subset=["duracion_encharcamiento_dias", "pct_perdida_pred_pct"]
    )

    if plot_df.empty:
        st.info("Sin datos suficientes para el gráfico de encharcamiento vs pérdida.")
        return

    if HAS_PLOTLY:
        kwargs = dict(
            x="duracion_encharcamiento_dias", y="pct_perdida_pred_pct",
            hover_name="parcel_id",
            title="Encharcamiento vs Pérdida estimada",
            labels={
                "duracion_encharcamiento_dias": "Encharcamiento (días)",
                "pct_perdida_pred_pct": "Pérdida estimada (%)",
            },
        )
        if "nivel_riesgo" in plot_df.columns:
            kwargs["color"] = "nivel_riesgo"
            kwargs["color_discrete_map"] = RISK_COLOR_MAP
        if "superficie_ha" in plot_df.columns:
            kwargs["size"] = "superficie_ha"
            kwargs["size_max"] = 20

        fig = px.scatter(plot_df, **kwargs)
        fig.update_layout(height=380, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.scatter_chart(
            plot_df.set_index("parcel_id")[["duracion_encharcamiento_dias", "pct_perdida_pred_pct"]]
        )


# ---------------------------------------------------------------------------
# Ficha resumen para una sola parcela
# ---------------------------------------------------------------------------
def show_single_parcel_summary(df: pd.DataFrame | None) -> None:
    """Ficha de resumen para cliente con una sola parcela."""
    if df is None or df.empty:
        return

    row = df.iloc[0]

    def _val(col, fmt=".2f", default="—"):
        v = row.get(col)
        try:
            return format(float(v), fmt)
        except (TypeError, ValueError):
            return default

    st.markdown("#### Resumen de la parcela")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Pérdida estimada", f"{_val('pct_perdida_pred_pct')}%")
        st.metric("Impacto total", f"€ {_val('impacto_total_eur', '.0f')}")
        st.metric("Impacto €/ha", f"€ {_val('impacto_eur_ha_pred')}")
        st.metric("Nivel de riesgo", str(row.get("nivel_riesgo", "—")).replace("_", " ").title())
    with col2:
        st.metric("Lluvia 7 días", f"{_val('rain_7d_mm', '.1f')} mm")
        st.metric("Humedad suelo", f"{_val('humedad_suelo_%', '.1f')}%")
        st.metric("Pendiente", f"{_val('pendiente_%', '.0f')}%")
        st.metric("Encharcamiento", f"{_val('duracion_encharcamiento_dias', '.1f')} días")

    if HAS_PLOTLY:
        # Barras individuales de las variables clave
        vars_to_plot = {
            "Pérdida estimada (%)": _val("pct_perdida_pred_pct"),
            "Lluvia 7d (mm)": _val("rain_7d_mm", ".1f"),
            "Humedad suelo (%)": _val("humedad_suelo_%", ".1f"),
            "Pendiente (%)": _val("pendiente_%", ".0f"),
            "Encharcamiento (días)": _val("duracion_encharcamiento_dias", ".1f"),
        }
        try:
            bar_df = pd.DataFrame([
                {"Variable": k, "Valor": float(v)}
                for k, v in vars_to_plot.items()
                if v != "—"
            ])
            if not bar_df.empty:
                fig = px.bar(
                    bar_df, x="Variable", y="Valor",
                    title="Variables clave de la parcela",
                    color="Variable",
                    color_discrete_sequence=["#4A7C59", "#6B9E5E", "#8DC87B",
                                             "#E67E22", "#2980B9"],
                )
                fig.update_layout(showlegend=False, height=320, margin=dict(t=40, b=60),
                                  xaxis_tickangle=-20)
                st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass
