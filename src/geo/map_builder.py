"""
Construcción de mapas interactivos con múltiples modos de visualización.

Modos:
- uso_sigpac: Colorización por uso SIGPAC (OV vs otros)
- riesgo_ml: Colorización por nivel de riesgo del modelo ML
- impacto_economico: Colorización por impacto económico
- encharcamiento: Colorización por duración de encharcamiento
- pendiente: Colorización por pendiente del terreno
"""
import folium
import geopandas as gpd
import pandas as pd
import numpy as np

# Paleta por tipo de uso (SIGPAC)
STYLE_OV = {"fillColor": "#5C8A4A", "color": "#2D5016", "weight": 2.0, "fillOpacity": 0.50}
STYLE_OTHER = {"fillColor": "#C8C8A0", "color": "#888870", "weight": 1.0, "fillOpacity": 0.20}
STYLE_SELECTED = {"fillColor": "#F4A261", "color": "#C0392B", "weight": 3.0, "fillOpacity": 0.80}
STYLE_HOVER = {"fillColor": "#FFD580", "color": "#E67E22", "weight": 2.5, "fillOpacity": 0.70}

# Paleta de riesgo ML
RISK_COLORS = {
    "bajo": "#4CAF50",        # Verde
    "medio": "#FFC107",       # Amarillo
    "alto": "#FF9800",        # Naranja
    "muy_alto": "#F44336",    # Rojo
}

# Paleta de encharcamiento
WATERLOG_COLORS = {
    "sin_riesgo": "#4CAF50",  # Verde
    "bajo": "#81D4FA",        # Azul claro
    "moderado": "#FFD54F",    # Amarillo
    "alto": "#FF9800",        # Naranja
}


def _get_color_for_value(value: float, vmin: float, vmax: float) -> str:
    """Interpola color entre rojo (vmin) y verde (vmax) para un valor."""
    if pd.isna(value):
        return "#CCCCCC"
    norm = (value - vmin) / (vmax - vmin) if vmax > vmin else 0.5
    norm = max(0, min(1, norm))
    # Rojo → Amarillo → Verde
    if norm < 0.5:
        r, g, b = 255, int(255 * norm * 2), 0
    else:
        r, g, b = int(255 * (1 - norm)), 255, 0
    return f"#{r:02x}{g:02x}{b:02x}"


def _get_style_by_mode(row: dict, mode: str, is_selected: bool) -> dict:
    """Determina estilo según el modo de visualización."""
    if is_selected:
        return STYLE_SELECTED

    if mode == "uso_sigpac":
        uso = row.get("uso_sigpac", "") or ""
        return STYLE_OV if uso == "OV" else STYLE_OTHER

    elif mode == "riesgo_ml":
        nivel_riesgo = row.get("nivel_riesgo")
        color = RISK_COLORS.get(nivel_riesgo, "#CCCCCC")
        return {"fillColor": color, "color": "#333", "weight": 1.5, "fillOpacity": 0.65}

    elif mode == "impacto_economico":
        impacto = row.get("impacto_total_eur")
        if pd.isna(impacto):
            color = "#CCCCCC"
        else:
            # Rango dinámico 0 a max observado
            vmax = 500  # Valor máximo para saturar color
            color = _get_color_for_value(impacto, 0, vmax)
        return {"fillColor": color, "color": "#333", "weight": 1.5, "fillOpacity": 0.70}

    elif mode == "encharcamiento":
        duracion = row.get("duracion_encharcamiento_dias")
        if pd.isna(duracion):
            color = "#CCCCCC"
        elif duracion == 0:
            color = WATERLOG_COLORS["sin_riesgo"]
        elif duracion <= 1:
            color = WATERLOG_COLORS["bajo"]
        elif duracion <= 3:
            color = WATERLOG_COLORS["moderado"]
        else:
            color = WATERLOG_COLORS["alto"]
        return {"fillColor": color, "color": "#333", "weight": 1.5, "fillOpacity": 0.65}

    elif mode == "pendiente":
        pendiente = row.get("pendiente_%")
        if pd.isna(pendiente):
            color = "#CCCCCC"
        else:
            # Rango 0-100%
            color = _get_color_for_value(pendiente, 0, 100)
        return {"fillColor": color, "color": "#333", "weight": 1.5, "fillOpacity": 0.65}

    # Por defecto
    return STYLE_OV


def _popup_html_by_mode(row: dict, mode: str) -> str:
    """Genera popup HTML según el modo de visualización."""
    lines = [
        f"<b style='color:#2D5016;font-size:13px'>{row.get('parcel_id', '—')}</b>",
        "<hr style='margin:4px 0;border-color:#c8dfc0'>",
    ]

    # Información base
    lines.append(f"<b>Cliente:</b> {row.get('client_id', '—')}")
    lines.append(f"<b>Superficie:</b> {row.get('area_ha_calc', row.get('superficie_ha', 0)):.4f} ha")

    # Información según modo
    if mode == "uso_sigpac":
        uso = row.get("uso_sigpac", "—") or "—"
        lines.append(f"<b>Uso SIGPAC:</b> {uso}")
        zona = row.get("zona_provincia", None)
        if zona:
            lines.append(f"<b>Provincia:</b> {zona}")

    elif mode == "riesgo_ml":
        lines.append(f"<b>Perdida predicha:</b> {row.get('pct_perdida_pred_pct', 0):.2f}%")
        lines.append(f"<b>Nivel riesgo:</b> {row.get('nivel_riesgo', '—')}")
        lines.append(f"<b>Impacto/ha:</b> EUR {row.get('impacto_eur_ha_pred', 0):.2f}")
        lines.append(f"<b>Impacto total:</b> EUR {row.get('impacto_total_eur', 0):.2f}")
        lines.append(f"<b>Lluvia 7d:</b> {row.get('rain_7d_mm', 0):.1f} mm")
        lines.append(f"<b>Humedad suelo:</b> {row.get('humedad_suelo_%', 0):.1f}%")

    elif mode == "impacto_economico":
        lines.append(f"<b>Impacto/ha:</b> EUR {row.get('impacto_eur_ha_pred', 0):.2f}")
        lines.append(f"<b>Impacto total:</b> EUR {row.get('impacto_total_eur', 0):.2f}")
        lines.append(f"<b>Rendimiento:</b> {row.get('rendimiento_esperado_kg_ha', 0):.0f} kg/ha")
        lines.append(f"<b>Precio:</b> EUR {row.get('precio_mercado_eur_kg', 0):.2f}/kg")

    elif mode == "encharcamiento":
        duracion = row.get("duracion_encharcamiento_dias", 0)
        lines.append(f"<b>Duracion encharcamiento:</b> {duracion:.1f} días")
        lines.append(f"<b>Drenaje:</b> {row.get('drenaje', '—')}")
        lines.append(f"<b>Pendiente:</b> {row.get('pendiente_%', 0):.0f}%")
        lines.append(f"<b>Lluvia 72h:</b> {row.get('rain_72h_mm', 0):.1f} mm")

    elif mode == "pendiente":
        pendiente = row.get("pendiente_%", 0)
        lines.append(f"<b>Pendiente:</b> {pendiente:.0f}%")
        if pendiente > 100:
            lines.append("<span style='color:#C0392B'><b>ALERTA: Valor extremo</b></span>")
        elif pendiente > 60:
            lines.append("<span style='color:#E67E22'><b>Advertencia: Pendiente alta</b></span>")
        lines.append(f"<b>Altitud:</b> {row.get('altitud_m', 0):.0f} m")

    return (
        "<div style='font-family:sans-serif;font-size:12px;min-width:200px;line-height:1.6'>"
        + "<br>".join(lines)
        + "</div>"
    )


def _add_legend_by_mode(m: folium.Map, mode: str) -> None:
    """Agrega leyenda dinámica según el modo."""
    if mode == "uso_sigpac":
        items = [
            ("#5C8A4A", "OV · Olivar"),
            ("#C8C8A0", "Otros usos"),
        ]
    elif mode == "riesgo_ml":
        items = [
            (RISK_COLORS["bajo"], "Bajo"),
            (RISK_COLORS["medio"], "Medio"),
            (RISK_COLORS["alto"], "Alto"),
            (RISK_COLORS["muy_alto"], "Muy Alto"),
        ]
    elif mode == "impacto_economico":
        items = [
            ("#4CAF50", "EUR 0 (bajo)"),
            ("#FFD54F", "EUR ~250 (medio)"),
            ("#F44336", "EUR 500+ (alto)"),
        ]
    elif mode == "encharcamiento":
        items = [
            (WATERLOG_COLORS["sin_riesgo"], "0 días"),
            (WATERLOG_COLORS["bajo"], "0–1 días"),
            (WATERLOG_COLORS["moderado"], "1–3 días"),
            (WATERLOG_COLORS["alto"], "> 3 días"),
        ]
    elif mode == "pendiente":
        items = [
            ("#4CAF50", "0–30%"),
            ("#FFD54F", "30–60%"),
            ("#F44336", "> 60%"),
        ]
    else:
        return

    rows_html = "".join(
        f"<div style='display:flex;align-items:center;margin-bottom:5px'>"
        f"<span style='display:inline-block;width:14px;height:14px;border-radius:3px;"
        f"background:{color};border:1px solid rgba(0,0,0,0.2);margin-right:8px;flex-shrink:0'></span>"
        f"<span>{label}</span></div>"
        for color, label in items
    )
    legend_html = (
        f"<div style='position:fixed;bottom:24px;left:24px;z-index:9999;"
        f"background:rgba(255,255,255,0.95);border-radius:10px;padding:12px 16px;"
        f"box-shadow:0 2px 10px rgba(0,0,0,0.18);font-family:sans-serif;font-size:12px;"
        f"color:#2D3748;min-width:160px'>"
        f"<div style='font-weight:700;margin-bottom:8px;color:#2D5016'>Leyenda</div>"
        f"{rows_html}</div>"
    )
    m.get_root().html.add_child(folium.Element(legend_html))


def build_parcels_map(
    gdf: gpd.GeoDataFrame,
    filter_ov: bool = False,
    selected_parcel_id: str | None = None,
    mode: str = "uso_sigpac",
    predictions_df: pd.DataFrame | None = None,
) -> folium.Map:
    """
    Construye mapa interactivo con múltiples modos de visualización.

    Args:
        gdf: GeoDataFrame con parcelas
        filter_ov: Si True, mostrar solo OV
        selected_parcel_id: ID de parcela seleccionada para resaltar
        mode: Modo de visualización (uso_sigpac, riesgo_ml, impacto_economico, encharcamiento, pendiente)
        predictions_df: DataFrame con predicciones del modelo (para modos ML)

    Retorna:
        Mapa folium
    """
    # Merge con predicciones si existen
    display_gdf = gdf.copy()
    if predictions_df is not None and not predictions_df.empty and mode != "uso_sigpac":
        # Merge por parcel_id o parcel_uid (convertir tipos si es necesario)
        if "parcel_uid" in display_gdf.columns and "parcel_uid" in predictions_df.columns:
            # Convertir a string ambos para asegurar compatibilidad
            display_gdf["parcel_uid"] = display_gdf["parcel_uid"].astype(str)
            predictions_df = predictions_df.copy()
            predictions_df["parcel_uid"] = predictions_df["parcel_uid"].astype(str)
            merged = display_gdf.merge(
                predictions_df, on="parcel_uid", how="left", suffixes=("", "_pred")
            )
        else:
            # Fallback a parcel_id
            display_gdf["parcel_id"] = display_gdf["parcel_id"].astype(str)
            predictions_df = predictions_df.copy()
            predictions_df["parcel_id"] = predictions_df["parcel_id"].astype(str)
            merged = display_gdf.merge(
                predictions_df, on="parcel_id", how="left", suffixes=("", "_pred")
            )
        display_gdf = merged

    # Filtrar OV si aplica
    if filter_ov:
        display_gdf = display_gdf[display_gdf["uso_sigpac"] == "OV"]

    bounds = display_gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="CartoDB positron",
        control_scale=True,
    )

    for _, row in display_gdf.iterrows():
        is_selected = row.get("parcel_id") == selected_parcel_id
        style = _get_style_by_mode(row.to_dict(), mode, is_selected)
        tooltip_text = f"{row.get('parcel_id', '?')} · {row.get('area_ha_calc', row.get('superficie_ha', 0)):.2f} ha"

        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _, s=style: s,
            highlight_function=lambda _, sel=is_selected: (
                STYLE_HOVER if not sel else STYLE_SELECTED
            ),
            tooltip=folium.Tooltip(tooltip_text, sticky=False),
            popup=folium.Popup(_popup_html_by_mode(row.to_dict(), mode), max_width=300),
        ).add_to(m)

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    _add_legend_by_mode(m, mode)

    return m
