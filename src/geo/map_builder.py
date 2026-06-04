import folium
import geopandas as gpd

# Paleta por tipo de uso
STYLE_OV = {"fillColor": "#5C8A4A", "color": "#2D5016", "weight": 2.0, "fillOpacity": 0.50}
STYLE_OTHER = {"fillColor": "#C8C8A0", "color": "#888870", "weight": 1.0, "fillOpacity": 0.20}
STYLE_SELECTED = {"fillColor": "#F4A261", "color": "#C0392B", "weight": 3.0, "fillOpacity": 0.80}
STYLE_HOVER = {"fillColor": "#FFD580", "color": "#E67E22", "weight": 2.5, "fillOpacity": 0.70}


def _parcel_style(uso: str, is_selected: bool) -> dict:
    if is_selected:
        return STYLE_SELECTED
    return STYLE_OV if uso == "OV" else STYLE_OTHER


def _popup_html(row) -> str:
    uso = row.get("uso_sigpac", "—") or "—"
    pendiente = row.get("pendiente_pct", None)
    altitud = row.get("altitud_m", None)
    zona = row.get("zona_provincia", None)

    lines = [
        f"<b style='color:#2D5016;font-size:13px'>{row['parcel_id']}</b>",
        "<hr style='margin:4px 0;border-color:#c8dfc0'>",
        f"<b>Cliente:</b> {row['client_id']}",
        f"<b>Superficie:</b> {row['area_ha_calc']:.4f} ha",
        f"<b>Uso SIGPAC:</b> {uso}",
    ]
    if zona:
        lines.append(f"<b>Provincia:</b> {zona}")
    if pendiente is not None and str(pendiente) != "nan":
        lines.append(f"<b>Pendiente:</b> {int(pendiente)}")
    if altitud is not None and str(altitud) != "nan":
        lines.append(f"<b>Altitud:</b> {int(altitud)} m")

    return (
        "<div style='font-family:sans-serif;font-size:12px;min-width:190px;line-height:1.7'>"
        + "<br>".join(lines)
        + "</div>"
    )


def _add_legend(m: folium.Map, show_non_ov: bool) -> None:
    items = [
        ("#5C8A4A", "OV · Olivar"),
        ("#F4A261", "Parcela seleccionada"),
    ]
    if show_non_ov:
        items.insert(1, ("#C8C8A0", "Otros usos SIGPAC"))

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
) -> folium.Map:
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="CartoDB positron",
        control_scale=True,
    )

    for _, row in gdf.iterrows():
        uso = row.get("uso_sigpac", "") or ""
        is_selected = (row["parcel_id"] == selected_parcel_id)
        style = _parcel_style(uso, is_selected)
        tooltip_text = f"{row['parcel_id']} · {row['area_ha_calc']:.2f} ha · {uso}"

        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _, s=style: s,
            highlight_function=lambda _, sel=is_selected: (
                STYLE_HOVER if not sel else STYLE_SELECTED
            ),
            tooltip=folium.Tooltip(tooltip_text, sticky=False),
            popup=folium.Popup(_popup_html(row), max_width=270),
        ).add_to(m)

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    _add_legend(m, show_non_ov=not filter_ov)

    return m
