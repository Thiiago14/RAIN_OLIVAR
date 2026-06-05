"""
Construcción de mapas interactivos con múltiples modos de visualización.

Modos:
- uso_sigpac: Colorización por uso SIGPAC (OV vs otros)
- riesgo: Colorización por nivel de predicción de riesgo
- impacto_economico: Colorización por impacto económico estimado
- encharcamiento: Colorización por duración de encharcamiento estimado
- pendiente: Colorización por pendiente del terreno
"""
import folium
import geopandas as gpd
import pandas as pd

# Paleta por tipo de uso (SIGPAC)
STYLE_OV = {"fillColor": "#5C8A4A", "color": "#2D5016", "weight": 2.0, "fillOpacity": 0.50}
STYLE_OTHER = {"fillColor": "#C8C8A0", "color": "#888870", "weight": 1.0, "fillOpacity": 0.20}
STYLE_SELECTED = {"fillColor": "#F4A261", "color": "#C0392B", "weight": 3.0, "fillOpacity": 0.80}
STYLE_HOVER = {"fillColor": "#FFD580", "color": "#E67E22", "weight": 2.5, "fillOpacity": 0.70}

# Paleta de predicción de riesgo
RISK_COLORS = {
    "bajo": "#4CAF50",
    "medio": "#FFC107",
    "alto": "#FF9800",
    "muy_alto": "#F44336",
    "sin_prediccion": "#BDBDBD",
}

# Paleta de encharcamiento
WATERLOG_COLORS = {
    "sin_riesgo": "#4CAF50",
    "bajo": "#81D4FA",
    "moderado": "#FFD54F",
    "alto": "#FF9800",
}

# Basemaps disponibles
BASEMAPS = {
    "Claro": {"tiles": "CartoDB positron", "attr": None},
    "OpenStreetMap": {"tiles": "OpenStreetMap", "attr": None},
    "Satélite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Esri World Imagery",
    },
    "Topográfico": {
        "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attr": "OpenTopoMap contributors",
    },
}


def _resolve_slope_col(row: dict) -> str | None:
    """Devuelve el nombre de la columna de pendiente disponible."""
    for col in ["pendiente_%", "pendiente_pct", "pendiente_", "pendiente"]:
        if col in row and row[col] is not None:
            return col
    return None


def _fv(v, fmt=".2f", default="—"):
    """Formatea un valor numérico de forma segura."""
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return default


def _normalize_riesgo(val) -> str:
    """Normaliza nivel_riesgo a claves del diccionario RISK_COLORS."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "sin_prediccion"
    return str(val).lower().strip().replace(" ", "_")


def _get_color_for_value(value: float, breakpoints: list[tuple[float, str]]) -> str:
    """Interpola color por rangos: [(threshold, color), ...]."""
    for threshold, color in breakpoints:
        if value <= threshold:
            return color
    return breakpoints[-1][1]


def _get_style_by_mode(row: dict, mode: str, is_selected: bool) -> dict:
    """Determina estilo según el modo de visualización."""
    if is_selected:
        return STYLE_SELECTED

    if mode == "uso_sigpac":
        uso = row.get("uso_sigpac", "") or ""
        return STYLE_OV if uso == "OV" else STYLE_OTHER

    elif mode == "riesgo":
        nivel = _normalize_riesgo(row.get("nivel_riesgo"))
        color = RISK_COLORS.get(nivel, RISK_COLORS["sin_prediccion"])
        return {"fillColor": color, "color": "#2D5016", "weight": 1.5, "fillOpacity": 0.75}

    elif mode == "impacto_economico":
        try:
            impacto = float(row.get("impacto_total_eur") or 0)
        except (TypeError, ValueError):
            impacto = 0.0
        color = _get_color_for_value(impacto, [
            (50, "#4CAF50"),
            (250, "#FFC107"),
            (500, "#FF9800"),
            (float("inf"), "#F44336"),
        ])
        return {"fillColor": color, "color": "#333", "weight": 1.5, "fillOpacity": 0.72}

    elif mode == "encharcamiento":
        try:
            duracion = float(row.get("duracion_encharcamiento_dias") or 0)
        except (TypeError, ValueError):
            duracion = 0.0
        if pd.isna(duracion) or duracion == 0:
            color = WATERLOG_COLORS["sin_riesgo"]
        elif duracion <= 1:
            color = WATERLOG_COLORS["bajo"]
        elif duracion <= 3:
            color = WATERLOG_COLORS["moderado"]
        else:
            color = WATERLOG_COLORS["alto"]
        return {"fillColor": color, "color": "#333", "weight": 1.5, "fillOpacity": 0.68}

    elif mode == "pendiente":
        # Resolver columna de pendiente disponible en el row
        slope_col = _resolve_slope_col(row)
        if slope_col is None:
            return {"fillColor": "#BDBDBD", "color": "#aaa", "weight": 1.0, "fillOpacity": 0.4}
        try:
            pendiente = float(row[slope_col] or 0)
        except (TypeError, ValueError):
            pendiente = float("nan")
        if pd.isna(pendiente):
            color = "#BDBDBD"
        elif pendiente <= 30:
            color = "#4CAF50"
        elif pendiente <= 60:
            color = "#FFD54F"
        else:
            color = "#F44336"
        return {"fillColor": color, "color": "#333", "weight": 1.5, "fillOpacity": 0.68}

    # Por defecto
    return STYLE_OV


def _build_tooltip(row: dict, mode: str) -> str:
    """Tooltip corto para hover (1–2 líneas)."""
    pid = row.get("parcel_id", "?")
    ha = _fv(row.get("area_ha_calc", row.get("superficie_ha")), ".2f", "?")

    if mode == "riesgo":
        nivel = _normalize_riesgo(row.get("nivel_riesgo")).replace("_", " ").title()
        perdida = _fv(row.get("pct_perdida_pred_pct"), ".2f")
        return f"{pid} · Riesgo: {nivel} · Pérdida: {perdida}%"
    elif mode == "impacto_economico":
        impacto = _fv(row.get("impacto_total_eur"), ".0f")
        return f"{pid} · Impacto: €{impacto}"
    elif mode == "encharcamiento":
        dias = _fv(row.get("duracion_encharcamiento_dias"), ".1f")
        return f"{pid} · Encharcamiento: {dias} días"
    elif mode == "pendiente":
        slope_col = _resolve_slope_col(row)
        pct = _fv(row.get(slope_col) if slope_col else None, ".0f")
        return f"{pid} · Pendiente: {pct}%"
    else:
        return f"{pid} · {ha} ha"


def _build_popup_html(row: dict, mode: str) -> str:
    """Popup HTML completo para click según modo."""
    pid = row.get("parcel_id", "—")
    ha = _fv(row.get("area_ha_calc", row.get("superficie_ha")), ".4f")
    uso = row.get("uso_sigpac", "—") or "—"

    lines = [
        f"<b style='color:#2D5016;font-size:13px'>{pid}</b>",
        "<hr style='margin:4px 0;border-color:#c8dfc0'>",
        f"<b>Superficie:</b> {ha} ha",
        f"<b>Uso SIGPAC:</b> {uso}",
    ]

    if mode == "riesgo":
        nivel = _normalize_riesgo(row.get("nivel_riesgo")).replace("_", " ").title()
        lines.append(f"<b>Predicción de riesgo:</b> {nivel}")
        lines.append(f"<b>Pérdida estimada:</b> {_fv(row.get('pct_perdida_pred_pct'))}%")
        lines.append(f"<b>Impacto económico total:</b> €{_fv(row.get('impacto_total_eur'), '.0f')}")
        lines.append(f"<b>Impacto económico:</b> €{_fv(row.get('impacto_eur_ha_pred'))}/ha")
        lines.append(f"<b>Lluvia 7 días:</b> {_fv(row.get('rain_7d_mm'), '.1f')} mm")
        lines.append(f"<b>Humedad suelo:</b> {_fv(row.get('humedad_suelo_%'), '.1f')}%")
        slope_col = _resolve_slope_col(row)
        lines.append(f"<b>Pendiente:</b> {_fv(row.get(slope_col) if slope_col else None, '.0f')}%")
        lines.append(f"<b>Encharcamiento:</b> {_fv(row.get('duracion_encharcamiento_dias'), '.1f')} días")

    elif mode == "impacto_economico":
        lines.append(f"<b>Impacto total estimado:</b> €{_fv(row.get('impacto_total_eur'), '.0f')}")
        lines.append(f"<b>Impacto estimado:</b> €{_fv(row.get('impacto_eur_ha_pred'))}/ha")
        lines.append(f"<b>Pérdida estimada:</b> {_fv(row.get('pct_perdida_pred_pct'))}%")
        nivel = _normalize_riesgo(row.get("nivel_riesgo")).replace("_", " ").title()
        lines.append(f"<b>Predicción de riesgo:</b> {nivel}")
        lines.append(f"<b>Rendimiento esperado:</b> {_fv(row.get('rendimiento_esperado_kg_ha'), '.0f')} kg/ha")
        lines.append(f"<b>Precio mercado:</b> €{_fv(row.get('precio_mercado_eur_kg'), '.2f')}/kg")

    elif mode == "encharcamiento":
        lines.append(f"<b>Encharcamiento estimado:</b> {_fv(row.get('duracion_encharcamiento_dias'), '.1f')} días")
        lines.append(f"<b>Lluvia 72h:</b> {_fv(row.get('rain_72h_mm'), '.1f')} mm")
        lines.append(f"<b>Lluvia 7 días:</b> {_fv(row.get('rain_7d_mm'), '.1f')} mm")
        lines.append(f"<b>Drenaje:</b> {row.get('drenaje', '—')}")
        slope_col = _resolve_slope_col(row)
        lines.append(f"<b>Pendiente:</b> {_fv(row.get(slope_col) if slope_col else None, '.0f')}%")
        lines.append(f"<b>Distancia a río:</b> {_fv(row.get('distancia_rio_m'), '.0f')} m")

    elif mode == "pendiente":
        slope_col = _resolve_slope_col(row)
        pct_val = row.get(slope_col) if slope_col else None
        try:
            pct_num = float(pct_val)
        except (TypeError, ValueError):
            pct_num = float("nan")
        lines.append(f"<b>Pendiente:</b> {_fv(pct_val, '.0f')}%")
        if not pd.isna(pct_num):
            if pct_num > 100:
                nivel_p, obs = "Alerta fuerte", "Valor superior a 100%. Posible error SIGPAC."
            elif pct_num > 60:
                nivel_p, obs = "Alta", "Pendiente elevada. Revisar condición del terreno."
            elif pct_num > 30:
                nivel_p, obs = "Moderada", ""
            else:
                nivel_p, obs = "Normal", ""
            lines.append(f"<b>Nivel:</b> {nivel_p}")
            if obs:
                lines.append(f"<span style='color:#C0392B'><b>Observación:</b> {obs}</span>")
        lines.append(f"<b>Altitud:</b> {_fv(row.get('altitud_m'), '.0f')} m")

    else:  # uso_sigpac
        zona = row.get("zona_provincia") or row.get("provincia", "—")
        lines.append(f"<b>Provincia:</b> {zona}")
        lines.append(f"<b>Municipio:</b> {row.get('municipio', '—')}")
        slope_col = _resolve_slope_col(row)
        if slope_col:
            lines.append(f"<b>Pendiente:</b> {_fv(row.get(slope_col), '.0f')}%")
        if row.get("altitud_m"):
            lines.append(f"<b>Altitud:</b> {_fv(row.get('altitud_m'), '.0f')} m")

    return (
        "<div style='font-family:sans-serif;font-size:12px;min-width:220px;line-height:1.7'>"
        + "<br>".join(lines)
        + "</div>"
    )


def _add_legend_by_mode(m: folium.Map, mode: str) -> None:
    """Agrega leyenda dinámica coherente con los colores del mapa."""
    if mode == "uso_sigpac":
        items = [
            ("#5C8A4A", "OV · Olivar"),
            ("#C8C8A0", "Otros usos"),
        ]
        title = "Uso SIGPAC"
    elif mode == "riesgo":
        items = [
            (RISK_COLORS["bajo"], "Bajo"),
            (RISK_COLORS["medio"], "Medio"),
            (RISK_COLORS["alto"], "Alto"),
            (RISK_COLORS["muy_alto"], "Muy alto"),
            (RISK_COLORS["sin_prediccion"], "Sin predicción"),
        ]
        title = "Predicción de riesgo"
    elif mode == "impacto_economico":
        items = [
            ("#4CAF50", "0 – 50 €"),
            ("#FFC107", "50 – 250 €"),
            ("#FF9800", "250 – 500 €"),
            ("#F44336", "> 500 €"),
        ]
        title = "Impacto económico"
    elif mode == "encharcamiento":
        items = [
            (WATERLOG_COLORS["sin_riesgo"], "0 días"),
            (WATERLOG_COLORS["bajo"], "0 – 1 días"),
            (WATERLOG_COLORS["moderado"], "1 – 3 días"),
            (WATERLOG_COLORS["alto"], "> 3 días"),
        ]
        title = "Encharcamiento estimado"
    elif mode == "pendiente":
        items = [
            ("#4CAF50", "0 – 30%"),
            ("#FFD54F", "30 – 60%"),
            ("#F44336", "> 60%"),
            ("#BDBDBD", "Sin dato"),
        ]
        title = "Pendiente del terreno"
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
        f"color:#2D3748;min-width:170px'>"
        f"<div style='font-weight:700;margin-bottom:8px;color:#2D5016'>{title}</div>"
        f"{rows_html}</div>"
    )
    m.get_root().html.add_child(folium.Element(legend_html))


def build_parcels_map(
    gdf: gpd.GeoDataFrame,
    filter_ov: bool = False,
    selected_parcel_id: str | None = None,
    mode: str = "uso_sigpac",
    predictions_df: pd.DataFrame | None = None,
    basemap: str = "Claro",
) -> folium.Map:
    """
    Construye mapa interactivo con múltiples modos de visualización.

    Args:
        gdf: GeoDataFrame con parcelas
        filter_ov: Si True, mostrar solo OV
        selected_parcel_id: ID de parcela seleccionada para resaltar
        mode: uso_sigpac | riesgo | impacto_economico | encharcamiento | pendiente
        predictions_df: DataFrame con predicciones (para modos de análisis)
        basemap: Claro | OpenStreetMap | Satélite | Topográfico

    Retorna:
        Mapa folium
        # TODO: Añadir PNOA/IGN WMS para ortofoto oficial de España.
    """
    # Merge con predicciones si existen y el modo lo requiere
    display_gdf = gdf.copy()
    if predictions_df is not None and not predictions_df.empty and mode != "uso_sigpac":
        if "parcel_uid" in display_gdf.columns and "parcel_uid" in predictions_df.columns:
            display_gdf["parcel_uid"] = display_gdf["parcel_uid"].astype(str)
            preds = predictions_df.copy()
            preds["parcel_uid"] = preds["parcel_uid"].astype(str)
            extra = [c for c in preds.columns if c not in display_gdf.columns]
            display_gdf = display_gdf.merge(preds[["parcel_uid"] + extra], on="parcel_uid", how="left")
        else:
            display_gdf["parcel_id"] = display_gdf["parcel_id"].astype(str)
            preds = predictions_df.copy()
            preds["parcel_id"] = preds["parcel_id"].astype(str)
            extra = [c for c in preds.columns if c not in display_gdf.columns]
            display_gdf = display_gdf.merge(preds[["parcel_id"] + extra], on="parcel_id", how="left")

    if filter_ov:
        display_gdf = display_gdf[display_gdf["uso_sigpac"] == "OV"]

    bounds = display_gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    # Construir mapa con basemap seleccionado
    bm = BASEMAPS.get(basemap, BASEMAPS["Claro"])
    if bm["attr"]:
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=14,
            tiles=bm["tiles"],
            attr=bm["attr"],
            control_scale=True,
        )
    else:
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=14,
            tiles=bm["tiles"],
            control_scale=True,
        )

    for _, row in display_gdf.iterrows():
        is_selected = row.get("parcel_id") == selected_parcel_id
        row_dict = row.to_dict()
        style = _get_style_by_mode(row_dict, mode, is_selected)
        tooltip = _build_tooltip(row_dict, mode)
        popup = _build_popup_html(row_dict, mode)

        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _, s=style: s,
            highlight_function=lambda _, sel=is_selected: (
                STYLE_HOVER if not sel else STYLE_SELECTED
            ),
            tooltip=folium.Tooltip(tooltip, sticky=False),
            popup=folium.Popup(popup, max_width=310),
        ).add_to(m)

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    _add_legend_by_mode(m, mode)

    return m
