import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
from shapely.geometry import Point

from src.geo.geodata_loader import get_available_clients, load_client_geodataframe
from src.geo.parcels_processor import process_parcels, get_kpis
from src.geo.map_builder import build_parcels_map
from src.geo.usage_filter import filter_ov, get_usage_stats
from src.features.build_input_from_parcels import build_base_input, to_csv_bytes
from src.features.farmer_inputs import (
    TIPO_OLIVAR_OPTIONS, RIEGO_OPTIONS, VARIEDAD_OPTIONS,
    ESTADO_FENOLOGICO_OPTIONS, FARMER_COLS,
    init_farmer_data, build_editor_df, calc_completeness,
)
from src.features.persistence import (
    get_client_status,
    save_farmer_inputs, load_farmer_inputs, merge_saved_with_gdf,
)
from src.features.weather_enrichment import (
    load_weather_cache, enrich_weather_for_client, get_weather_stats,
)
from src.features.soil_enrichment import (
    load_soil_cache, enrich_soil_for_client, get_soil_stats,
)
from src.features.hydrology_enrichment import (
    load_hydrology_cache, enrich_hydrology_for_client, get_hydrology_stats,
)
from src.features.economic_enrichment import get_economic_stats
from src.features.waterlogging_calculator import get_waterlogging_risk_distribution
from src.features.enrichment_assembler import (
    assemble_enriched_csv, get_enrichment_coverage, SOURCE_COLUMNS, get_ml_readiness,
    get_ml_ready_csv, get_slope_warnings,
)

# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="RAIN-OLIVAR | Plataforma Geoespacial",
    page_icon="🫒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
html,body,[class*="css"]{font-family:'Segoe UI',sans-serif}
[data-testid="stAppViewContainer"]{background:#F7F9F5}
[data-testid="stSidebar"]{background:#1E3A2F}
[data-testid="stSidebar"] *{color:#E8F0E6 !important}

.main-header{background:linear-gradient(135deg,#2D5016 0%,#4A7C59 60%,#6B9E5E 100%);
  padding:22px 32px 16px 32px;border-radius:14px;margin-bottom:18px;
  box-shadow:0 4px 20px rgba(45,80,22,.25)}
.main-header h1{color:#fff;font-size:23px;font-weight:700;margin:0 0 4px}
.main-header p{color:#C8E6C0;font-size:13px;margin:0}
.hbadge{display:inline-block;background:rgba(255,255,255,.15);color:#fff;
  font-size:10px;font-weight:600;padding:3px 10px;border-radius:20px;
  margin-bottom:7px;letter-spacing:1px;text-transform:uppercase}

.kpi-row{display:grid;gap:12px;margin-bottom:14px}
.kpi4{grid-template-columns:repeat(4,1fr)}
.kpi3{grid-template-columns:repeat(3,1fr)}
.kpi-card{background:#fff;border-radius:12px;padding:14px 16px;
  box-shadow:0 2px 8px rgba(0,0,0,.07);border-left:4px solid #4A7C59}
.kpi-card.ov{border-left-color:#4A7C59}
.kpi-card.warn{border-left-color:#E67E22}
.kpi-card.info{border-left-color:#2980B9}
.kpi-card.ok{border-left-color:#27AE60}
.klabel{font-size:10px;font-weight:600;color:#7A9A6E;text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:4px}
.kval{font-size:24px;font-weight:700;color:#1E3A2F;line-height:1;margin-bottom:3px}
.ksub{font-size:11px;color:#8FA882}

.section-title{font-size:14px;font-weight:700;color:#2D5016;
  border-bottom:2px solid #C8DFC0;padding-bottom:5px;margin-bottom:11px;margin-top:6px}
.sel-badge{display:inline-block;background:#FEF3E2;color:#C0392B;
  border:1px solid #F4A261;border-radius:8px;padding:5px 12px;
  font-size:13px;font-weight:600;margin-bottom:10px}

/* Completeness */
.comp-bar-wrap{background:#E8F0E6;border-radius:8px;height:10px;margin:6px 0 3px}
.comp-bar{background:#4A7C59;border-radius:8px;height:10px;transition:width .4s}
.comp-bar.warn{background:#E67E22}
.comp-bar.danger{background:#C0392B}

/* Status chips */
.chip{display:inline-block;padding:3px 12px;border-radius:20px;font-size:12px;font-weight:600}
.chip-sin{background:#F5F5F5;color:#666;border:1px solid #DDD}
.chip-bor{background:#FFF3E0;color:#E65100;border:1px solid #FFB74D}
.chip-comp{background:#E8F5E9;color:#1B5E20;border:1px solid #81C784}
.chip-listo{background:#E3F2FD;color:#0D47A1;border:1px solid #64B5F6}

.info-box{background:#EBF5E6;border:1px solid #A8D49A;border-radius:10px;
  padding:10px 14px;font-size:12px;color:#2D5016;margin-bottom:12px}
.warn-box{background:#FFF8E1;border:1px solid #FFD54F;border-radius:10px;
  padding:10px 14px;font-size:12px;color:#6D4C00;margin-bottom:12px}
.err-box{background:#FFEBEE;border:1px solid #EF9A9A;border-radius:10px;
  padding:10px 14px;font-size:12px;color:#B71C1C;margin-bottom:12px}

.sidebar-brand{text-align:center;padding:16px 8px 18px;
  border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:16px}
.sidebar-brand h2{color:#fff !important;font-size:19px;font-weight:800;margin:0}
.sidebar-brand span{color:#8DC87B !important}
.sidebar-brand p{color:#8DC87B !important;font-size:11px;margin:3px 0 0;
  letter-spacing:1px;text-transform:uppercase}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _farmer_key(client: str) -> str:
    return f"farmer_v2_{client}"


def _editor_ver_key(client: str) -> str:
    return f"editor_ver_{client}"


def _status_chip(status: str) -> str:
    labels = {
        "sin_datos": ("Sin datos", "chip-sin"),
        "borrador": ("Borrador", "chip-bor"),
        "completo": ("Completo ✓", "chip-comp"),
        "listo_para_apis": ("Listo para APIs ✓", "chip-listo"),
    }
    label, css = labels.get(status, ("Desconocido", "chip-sin"))
    return f'<span class="chip {css}">{label}</span>'


def _comp_bar_html(pct: int) -> str:
    css = "danger" if pct < 50 else ("warn" if pct < 100 else "")
    return (
        f'<div class="comp-bar-wrap">'
        f'<div class="comp-bar {css}" style="width:{pct}%"></div>'
        f'</div>'
    )


@st.cache_data(show_spinner=False)
def load_and_process(client_id: str):
    raw = load_client_geodataframe(client_id)
    return process_parcels(raw, client_id)


def _init_session_for_client(client_id: str, ov_gdf):
    """Inicializa session_state para este cliente; carga datos guardados si existen."""
    fk = _farmer_key(client_id)
    vk = _editor_ver_key(client_id)

    if fk not in st.session_state:
        saved = load_farmer_inputs(client_id)
        if saved is not None and not saved.empty:
            merged = merge_saved_with_gdf(saved, ov_gdf)
            msg = "loaded"
        else:
            merged = init_farmer_data(ov_gdf)
            msg = "init"
        st.session_state[fk] = merged
        st.session_state[vk] = st.session_state.get(vk, 0) + 1
        st.session_state[f"_load_msg_{client_id}"] = msg
    else:
        # Verificar que las parcelas del shapefile coinciden con las del estado
        current_uids = set(ov_gdf["parcel_uid"].tolist())
        saved_uids = set(st.session_state[fk]["parcel_uid"].tolist()) if "parcel_uid" in st.session_state[fk].columns else set()
        if current_uids != saved_uids:
            # Shapefile cambió → re-merge
            saved_file = load_farmer_inputs(client_id)
            st.session_state[fk] = merge_saved_with_gdf(saved_file, ov_gdf)
            st.session_state[vk] = st.session_state.get(vk, 0) + 1


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <h2>🫒 RAIN<span>-OLIVAR</span></h2>
        <p>Plataforma Geoespacial</p>
    </div>
    """, unsafe_allow_html=True)

    clients = get_available_clients()
    if not clients:
        st.error("No se encontraron clientes en data/clientes_shp/")
        st.stop()

    selected_client = st.selectbox(
        "Cliente",
        options=clients,
        format_func=lambda x: x.replace("_", " ").title(),
    )

    # Estado del cliente
    raw_status = get_client_status(selected_client)
    st.markdown(
        f"**Estado:** {_status_chip(raw_status)}",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    filter_ov_active = st.checkbox("🫒 Solo parcelas de olivar (OV)", value=True)

    # Cargar GDF para poblar el selector de parcela
    try:
        gdf = load_and_process(selected_client)
        load_ok, load_error = True, None
    except Exception as e:
        load_ok, load_error = False, str(e)

    if load_ok:
        stats = get_usage_stats(gdf)
        display_gdf = filter_ov(gdf) if filter_ov_active else gdf
        parcel_ids = ["— Ninguna —"] + display_gdf["parcel_id"].tolist()
        current_sel = st.session_state.get("selected_parcel_id", "— Ninguna —")
        if current_sel not in parcel_ids:
            current_sel = "— Ninguna —"

        st.markdown("**Parcela activa**")
        sidebar_sel = st.selectbox(
            "Seleccionar", options=parcel_ids,
            index=parcel_ids.index(current_sel),
            label_visibility="collapsed",
        )
        if sidebar_sel != "— Ninguna —":
            st.session_state["selected_parcel_id"] = sidebar_sel
        elif st.session_state.get("selected_parcel_id") not in parcel_ids:
            st.session_state["selected_parcel_id"] = None

    st.markdown("---")
    show_sigpac = st.checkbox("Columnas SIGPAC en tabla", value=False)

    st.markdown("---")
    st.markdown("""
    <div style='font-size:11px;color:#8DC87B;line-height:1.9'>
    ✅ Visualización shapefiles<br>✅ Filtro OV<br>✅ Cálculo superficie<br>
    ✅ parcel_uid estable<br>✅ Persistencia por cliente<br>
    ✅ Validación completitud<br>✅ Editor agricultor<br>
    ✅ Borrador / Confirmado<br>✅ Exportación CSV<br><br>
    <span style='opacity:.5'>Próximamente:</span><br>
    🌧 Open-Meteo / AEMET<br>🌱 SoilGrids<br>📍 Overpass API<br>
    🤖 Predicción ML<br>📄 Informe PDF
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
active_label = ("Solo OV" if filter_ov_active else "Todos los usos") if load_ok else ""
st.markdown(f"""
<div class="main-header">
  <div class="hbadge">🛰 Geoespacial · {selected_client.replace("_"," ").title()} · {active_label}</div>
  <h1>Plataforma de análisis de parcelas de olivar</h1>
  <p>Visualización · Filtro OV · Datos del agricultor · Validación · Persistencia por cliente</p>
</div>
""", unsafe_allow_html=True)

if not load_ok:
    st.markdown(f'<div class="err-box">⚠️ <b>Error al cargar shapefile</b><br>{load_error}</div>',
                unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------------------
# OV GDF + Session State
# ---------------------------------------------------------------------------
ov_gdf = filter_ov(gdf)

if stats["n_ov"] == 0 and filter_ov_active:
    st.markdown('<div class="warn-box">⚠️ No hay parcelas OV para este cliente.</div>',
                unsafe_allow_html=True)

_init_session_for_client(selected_client, ov_gdf)
fk = _farmer_key(selected_client)

# Mostrar mensaje si se cargaron datos persistidos
load_msg = st.session_state.pop(f"_load_msg_{selected_client}", None)
if load_msg == "loaded":
    st.markdown('<div class="info-box">📂 Datos del agricultor cargados desde archivo local.</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI Fila 1 — General
# ---------------------------------------------------------------------------
kpis_all = get_kpis(gdf)
st.markdown(f"""
<div class="kpi-row kpi4">
  <div class="kpi-card info">
    <div class="klabel">🗂 Cliente</div>
    <div class="kval" style="font-size:17px">{selected_client.replace("_"," ").title()}</div>
    <div class="ksub">shapefile cargado ✓</div>
  </div>
  <div class="kpi-card info">
    <div class="klabel">📦 Total polígonos</div>
    <div class="kval">{kpis_all["n_parcelas"]}</div>
    <div class="ksub">recintos en shapefile</div>
  </div>
  <div class="kpi-card info">
    <div class="klabel">📐 Superficie total</div>
    <div class="kval">{kpis_all["superficie_total_ha"]:,.2f} ha</div>
    <div class="ksub">todos los usos</div>
  </div>
  <div class="kpi-card info">
    <div class="klabel">📊 Media / recinto</div>
    <div class="kval">{kpis_all["superficie_media_ha"]:,.2f} ha</div>
    <div class="ksub">rango {kpis_all["superficie_min_ha"]:.2f}–{kpis_all["superficie_max_ha"]:.2f}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI Fila 2 — OV + Estado agricultor
# ---------------------------------------------------------------------------
editor_df_for_comp = build_editor_df(ov_gdf, st.session_state[fk])
comp = calc_completeness(editor_df_for_comp[[c for c in ["parcel_id"] + FARMER_COLS if c in editor_df_for_comp.columns]])
pct = comp["pct"]
pct_color = "#27AE60" if pct == 100 else ("#E67E22" if pct >= 50 else "#C0392B")

st.markdown(f"""
<div class="kpi-row kpi4">
  <div class="kpi-card ov">
    <div class="klabel">🫒 Parcelas OV</div>
    <div class="kval">{stats["n_ov"]}</div>
    <div class="ksub">{stats["ha_ov"]:,.2f} ha · {stats["pct_ov"]}% del total</div>
  </div>
  <div class="kpi-card warn">
    <div class="klabel">⚠️ Otros usos</div>
    <div class="kval">{stats["n_non_ov"]}</div>
    <div class="ksub">{stats["ha_non_ov"]:,.2f} ha · no van al modelo</div>
  </div>
  <div class="kpi-card {'ok' if pct==100 else 'warn'}">
    <div class="klabel">✏️ Completitud agricultor</div>
    <div class="kval" style="color:{pct_color}">{pct}%</div>
    <div class="ksub">{comp["filled_fields"]}/{comp["total_fields"]} campos · {comp["pending_fields"]} pendientes</div>
  </div>
  <div class="kpi-card {'ok' if raw_status=='completo' else 'warn'}">
    <div class="klabel">📋 Estado cliente</div>
    <div class="kval" style="font-size:14px">{_status_chip(raw_status)}</div>
    <div class="ksub">{'Listo para APIs' if raw_status=='completo' else 'Completar datos del agricultor'}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# Parcela seleccionada
selected_parcel_id = st.session_state.get("selected_parcel_id")
if selected_parcel_id and selected_parcel_id != "— Ninguna —":
    st.markdown(
        f'<div class="sel-badge">📍 Parcela activa: <b>{selected_parcel_id}</b></div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Mapa + Tabla
# ---------------------------------------------------------------------------
col_map, col_table = st.columns([3, 2], gap="large")

with col_map:
    st.markdown('<div class="section-title">🗺 Mapa de parcelas</div>', unsafe_allow_html=True)
    folium_map = build_parcels_map(
        display_gdf,
        filter_ov=filter_ov_active,
        selected_parcel_id=selected_parcel_id,
    )
    map_result = st_folium(
        folium_map,
        use_container_width=True,
        height=480,
        returned_objects=["last_object_clicked"],
    )
    # Click detection
    if map_result and map_result.get("last_object_clicked"):
        click = map_result["last_object_clicked"]
        coords = (click.get("lat"), click.get("lng"))
        if coords != st.session_state.get("_last_click_coords") and coords[0] is not None:
            st.session_state["_last_click_coords"] = coords
            pt = Point(coords[1], coords[0])
            for _, row in display_gdf.iterrows():
                if row.geometry.contains(pt) or row.geometry.buffer(1e-6).contains(pt):
                    st.session_state["selected_parcel_id"] = row["parcel_id"]
                    st.rerun()
                    break

with col_table:
    st.markdown('<div class="section-title">📋 Parcelas cargadas</div>', unsafe_allow_html=True)
    tcols = ["parcel_id", "client_id", "area_ha_calc"]
    if show_sigpac:
        for c in ["uso_sigpac", "pendiente_pct", "altitud_m"]:
            if c in display_gdf.columns:
                tcols.append(c)

    tdf = display_gdf[tcols].copy()
    tdf.columns = [c.replace("_pct", " (%)").replace("_", " ").title() for c in tdf.columns]
    tdf = tdf.rename(columns={"Area Ha Calc": "Área (ha)"})

    def _hl(row):
        if "Parcel Id" in row.index and selected_parcel_id and row["Parcel Id"] == selected_parcel_id:
            return ["background:#FEF3E2;font-weight:bold"] * len(row)
        return [""] * len(row)

    st.dataframe(tdf.style.apply(_hl, axis=1),
                 use_container_width=True, height=450, hide_index=True)

# ---------------------------------------------------------------------------
# DISTRIBUCIÓN POR USO
# ---------------------------------------------------------------------------
if not filter_ov_active and stats["by_uso"]:
    uso_labels = {"OV": "Olivar", "TA": "Tierra arable", "FS": "Frutos secos",
                  "IM": "Improductivo", "CA": "Viales/Caminos"}
    with st.expander("📊 Distribución por uso SIGPAC", expanded=False):
        rows = []
        for uso, cnt in sorted(stats["by_uso"].items()):
            ha = gdf[gdf["uso_sigpac"] == uso]["area_ha_calc"].sum()
            rows.append({
                "Código": uso, "Descripción": uso_labels.get(uso, "Otro"),
                "Recintos": cnt, "Superficie (ha)": round(ha, 2),
                "Al modelo": "✅" if uso == "OV" else "❌",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# EDITOR DEL AGRICULTOR
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown('<div class="section-title">✏️ Completar datos del agricultor</div>', unsafe_allow_html=True)

if len(ov_gdf) == 0:
    st.markdown('<div class="warn-box">⚠️ No hay parcelas OV para editar.</div>', unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div class="info-box">
    Completa los 4 campos obligatorios para las <b>{len(ov_gdf)} parcelas OV</b>.
    Columnas calculadas (superficie, pendiente, altitud) no son editables.<br>
    <b>Guardar borrador</b> permite guardar aunque esté incompleto.
    <b>Confirmar datos</b> requiere 100% de completitud y habilita la siguiente fase.
    </div>
    """, unsafe_allow_html=True)

    editor_df = build_editor_df(ov_gdf, st.session_state[fk])
    readonly_in_editor = [c for c in editor_df.columns if c not in FARMER_COLS]
    editor_ver = st.session_state.get(_editor_ver_key(selected_client), 0)

    edited = st.data_editor(
        editor_df,
        column_config={
            "parcel_uid": st.column_config.TextColumn("UID Estable", disabled=True),
            "parcel_id": st.column_config.TextColumn("Parcela", disabled=True),
            "client_id": st.column_config.TextColumn("Cliente", disabled=True),
            "uso_sigpac": st.column_config.TextColumn("Uso", disabled=True),
            "superficie_ha": st.column_config.NumberColumn("Sup. (ha)", format="%.4f", disabled=True),
            "pendiente_%": st.column_config.NumberColumn("Pendiente", format="%d", disabled=True),
            "altitud_m": st.column_config.NumberColumn("Altitud (m)", format="%d", disabled=True),
            "tipo_olivar": st.column_config.SelectboxColumn(
                "Tipo Olivar ✱", options=TIPO_OLIVAR_OPTIONS, required=False),
            "riego": st.column_config.SelectboxColumn(
                "Riego ✱", options=RIEGO_OPTIONS, required=False),
            "variedad": st.column_config.SelectboxColumn(
                "Variedad ✱", options=VARIEDAD_OPTIONS, required=False),
            "estado_fenologico": st.column_config.SelectboxColumn(
                "Fenología ✱", options=ESTADO_FENOLOGICO_OPTIONS, required=False),
        },
        disabled=readonly_in_editor,
        use_container_width=True,
        hide_index=True,
        key=f"editor_{selected_client}_v{editor_ver}",
        height=min(450, 55 + len(ov_gdf) * 38),
    )

    # Calcular completitud con el estado actual del editor
    comp_live = calc_completeness(
        edited[[c for c in ["parcel_id"] + FARMER_COLS if c in edited.columns]]
    )
    pct_live = comp_live["pct"]
    bar_css = "" if pct_live == 100 else ("warn" if pct_live >= 50 else "danger")

    st.markdown(
        f'{_comp_bar_html(pct_live)}'
        f'<span style="font-size:12px;color:#555">'
        f'<b>{pct_live}%</b> completitud · '
        f'{comp_live["filled_fields"]}/{comp_live["total_fields"]} campos · '
        f'{comp_live["pending_fields"]} pendientes</span>',
        unsafe_allow_html=True,
    )

    # Parcelas con datos faltantes
    if comp_live["missing_parcels"]:
        with st.expander(f"⚠️ {len(comp_live['missing_parcels'])} parcelas con datos faltantes", expanded=False):
            for mp in comp_live["missing_parcels"]:
                st.markdown(
                    f"- **{mp['parcel_id']}** → faltan: `{'`, `'.join(mp['missing_cols'])}`"
                )

    st.markdown("")

    col_draft, col_confirm, col_dl = st.columns([1, 1, 1], gap="medium")

    with col_draft:
        if st.button("💾 Guardar borrador", use_container_width=True):
            farmer_to_save = edited[["parcel_id"] + [c for c in FARMER_COLS if c in edited.columns]].copy()
            path = save_farmer_inputs(selected_client, farmer_to_save, ov_gdf, status="borrador")
            st.session_state[fk] = merge_saved_with_gdf(
                load_farmer_inputs(selected_client), ov_gdf
            )
            st.success(f"Borrador guardado → `{path}`")
            st.rerun()

    with col_confirm:
        if comp_live["is_complete"]:
            if st.button("✅ Confirmar datos", use_container_width=True, type="primary"):
                farmer_to_save = edited[["parcel_id"] + [c for c in FARMER_COLS if c in edited.columns]].copy()
                path = save_farmer_inputs(selected_client, farmer_to_save, ov_gdf, status="completo")
                st.session_state[fk] = merge_saved_with_gdf(
                    load_farmer_inputs(selected_client), ov_gdf
                )
                st.success(f"✅ Datos confirmados → `{path}` · Cliente listo para APIs.")
                st.rerun()
        else:
            st.button("✅ Confirmar datos", use_container_width=True, disabled=True)
            st.markdown(
                f'<div class="err-box" style="margin-top:4px">'
                f'Faltan {comp_live["pending_fields"]} campos. Complete el 100% para confirmar.</div>',
                unsafe_allow_html=True,
            )

    with col_dl:
        farmer_export = edited[["parcel_id"] + [c for c in FARMER_COLS if c in edited.columns]].copy()
        base_df = build_base_input(ov_gdf, farmer_export)
        status_label = "confirmado" if comp_live["is_complete"] else "borrador"
        csv_bytes = to_csv_bytes(base_df)
        st.download_button(
            label=f"⬇️ CSV enriquecido ({status_label})",
            data=csv_bytes,
            file_name=f"input_ov_{selected_client}_{status_label}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.markdown(
            f"<div style='font-size:11px;color:#7A9A6E;text-align:center;margin-top:4px'>"
            f"{len(ov_gdf)} parcelas OV · 22 cols · sep ;</div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# EXPORTACIÓN CSV BASE (todas las parcelas del display)
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown('<div class="section-title">📤 Exportar CSV base</div>', unsafe_allow_html=True)

col_info, col_btn = st.columns([3, 1], gap="large")
with col_info:
    label_exp = "solo OV" if filter_ov_active else "todos los recintos"
    st.markdown(f"""
    <div class="info-box">
    CSV base de las <b>{len(display_gdf)} parcelas ({label_exp})</b> con variables del shapefile rellenas.<br>
    Para el modelo ML usa el <b>CSV enriquecido confirmado</b> de la sección anterior.
    </div>
    """, unsafe_allow_html=True)

with col_btn:
    base_csv = to_csv_bytes(build_base_input(display_gdf))
    st.download_button(
        label="⬇️ CSV base",
        data=base_csv,
        file_name=f"input_base_{selected_client}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.markdown(
        f"<div style='font-size:11px;color:#7A9A6E;text-align:center;margin-top:4px'>"
        f"{len(display_gdf)} parcelas · 22 cols · sep ;</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# ENRIQUECIMIENTO METEOROLÓGICO
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown('<div class="section-title">🌧 Enriquecimiento meteorológico (Open-Meteo)</div>',
            unsafe_allow_html=True)

if raw_status != "completo":
    st.markdown("""
    <div class="warn-box">
    ⚠️ <b>Confirma primero los datos del agricultor</b> antes de consultar meteorología.<br>
    El estado del cliente debe ser <b>Completo</b> para habilitar esta sección.
    </div>
    """, unsafe_allow_html=True)
else:
    # Cargar cache existente
    weather_df = load_weather_cache(selected_client)
    w_exists = weather_df is not None and not weather_df.empty

    # Estado del cache
    if w_exists:
        wstats = get_weather_stats(weather_df)
        updated = wstats.get("updated_at", "—")
        bar_col = "#27AE60" if wstats["pct_ok"] == 100 else "#E67E22"
        st.markdown(f"""
        <div class="kpi-row kpi3">
          <div class="kpi-card ok">
            <div class="klabel">🌦 Parcelas con datos</div>
            <div class="kval">{wstats["ok"]}/{wstats["total"]}</div>
            <div class="ksub" style="color:{bar_col}">{wstats["pct_ok"]}% completitud</div>
          </div>
          <div class="kpi-card info">
            <div class="klabel">📡 Fuente</div>
            <div class="kval" style="font-size:14px">Open-Meteo</div>
            <div class="ksub">Sin API key · gratuito</div>
          </div>
          <div class="kpi-card {'ok' if wstats['errors']==0 else 'warn'}">
            <div class="klabel">⚠️ Errores</div>
            <div class="kval">{wstats["errors"]}</div>
            <div class="ksub">Última actualización: {str(updated)[:16]}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="info-box">
        No hay datos meteorológicos para este cliente.<br>
        Haz clic en <b>Obtener datos meteorológicos</b> para consultar Open-Meteo.
        </div>
        """, unsafe_allow_html=True)

    # Botón de acción
    col_fetch, col_dl_w = st.columns([1, 2], gap="medium")
    with col_fetch:
        btn_label = "🔄 Actualizar datos meteorológicos" if w_exists else "🌧 Obtener datos meteorológicos"
        if st.button(btn_label, use_container_width=True, type="primary"):
            progress_bar = st.progress(0, text="Iniciando consultas a Open-Meteo...")
            status_text = st.empty()

            def _progress(done, total):
                pct = int(done / total * 100)
                progress_bar.progress(pct, text=f"Consultando parcela {done}/{total}...")
                status_text.markdown(f"*Consultando parcela {done} de {total}...*")

            try:
                weather_df = enrich_weather_for_client(
                    selected_client, ov_gdf, max_workers=5,
                    progress_callback=_progress,
                )
                progress_bar.progress(100, text="Completado.")
                status_text.empty()
                wstats = get_weather_stats(weather_df)
                st.success(
                    f"Datos meteorológicos actualizados: "
                    f"{wstats['ok']}/{wstats['total']} parcelas OK"
                    + (f" · {wstats['errors']} con error" if wstats["errors"] else "")
                )
                st.rerun()
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"Error al consultar Open-Meteo: {e}")

    # Errores parciales
    if w_exists:
        err_df = weather_df[weather_df["weather_status"] != "ok"]
        if not err_df.empty:
            with st.expander(f"⚠️ {len(err_df)} parcelas con error en meteorología", expanded=False):
                st.dataframe(
                    err_df[["parcel_id", "weather_error"]],
                    use_container_width=True, hide_index=True,
                )

        # Tabla resumen de variables meteorológicas
        st.markdown('<div class="section-title" style="margin-top:14px">📊 Variables meteorológicas por parcela</div>',
                    unsafe_allow_html=True)
        ok_df = weather_df[weather_df["weather_status"] == "ok"].copy()
        if not ok_df.empty:
            display_w = ok_df[["parcel_id", "lat", "lon",
                                "rain_72h_mm", "rain_7d_mm",
                                "temp_media_7d", "humedad_suelo_%"]].copy()
            display_w = display_w.rename(columns={
                "rain_72h_mm": "Lluvia 72h (mm)",
                "rain_7d_mm": "Lluvia 7d (mm)",
                "temp_media_7d": "T media 7d (°C)",
                "humedad_suelo_%": "Humedad suelo (%)",
                "lat": "Lat", "lon": "Lon",
            })
            for col in ["Lluvia 72h (mm)", "Lluvia 7d (mm)", "T media 7d (°C)", "Humedad suelo (%)"]:
                if col in display_w.columns:
                    display_w[col] = pd.to_numeric(display_w[col], errors="coerce").round(2)
            st.dataframe(display_w, use_container_width=True, hide_index=True, height=300)

        # Descarga CSV completo con meteorología
        with col_dl_w:
            if w_exists:
                # Cargar datos del agricultor confirmados
                saved_farmer = load_farmer_inputs(selected_client)
                farmer_subset = None
                if saved_farmer is not None:
                    farmer_subset = saved_farmer[
                        ["parcel_id"] + [c for c in ["tipo_olivar", "riego", "variedad", "estado_fenologico"]
                                         if c in saved_farmer.columns]
                    ]
                enriched_df = build_base_input(ov_gdf, farmer_subset, weather_df)
                enriched_bytes = to_csv_bytes(enriched_df)
                st.download_button(
                    label="⬇️ CSV completo (agricultor + meteo)",
                    data=enriched_bytes,
                    file_name=f"input_completo_{selected_client}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                n_weather_filled = int(
                    weather_df[weather_df["weather_status"] == "ok"].shape[0]
                )
                st.markdown(
                    f"<div style='font-size:11px;color:#7A9A6E;margin-top:4px'>"
                    f"{len(ov_gdf)} parcelas OV · 22 cols · {n_weather_filled} con meteo · sep ;</div>",
                    unsafe_allow_html=True,
                )

# ---------------------------------------------------------------------------
# ENRIQUECIMIENTO DE SUELO (SoilGrids)
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown('<div class="section-title">🌱 Enriquecimiento de suelo (SoilGrids ISRIC)</div>',
            unsafe_allow_html=True)

if raw_status != "completo":
    st.markdown("""
    <div class="warn-box">
    ⚠️ <b>Confirma primero los datos del agricultor</b> antes de consultar datos de suelo.
    </div>
    """, unsafe_allow_html=True)
else:
    soil_df = load_soil_cache(selected_client)
    soil_exists = soil_df is not None and not soil_df.empty

    if soil_exists:
        sstats = get_soil_stats(soil_df)
        soil_col = "#27AE60" if sstats["pct_ok"] == 100 else "#E67E22"
        st.markdown(f"""
        <div class="kpi-row kpi3">
          <div class="kpi-card ok">
            <div class="klabel">🌱 Parcelas con datos de suelo</div>
            <div class="kval">{sstats["ok"]}/{sstats["total"]}</div>
            <div class="ksub" style="color:{soil_col}">{sstats["pct_ok"]}% completitud</div>
          </div>
          <div class="kpi-card info">
            <div class="klabel">📡 Fuente</div>
            <div class="kval" style="font-size:13px">SoilGrids v2</div>
            <div class="ksub">ISRIC · resolución 250m</div>
          </div>
          <div class="kpi-card {'ok' if sstats['errors']==0 else 'warn'}">
            <div class="klabel">⚠️ Errores</div>
            <div class="kval">{sstats["errors"]}</div>
            <div class="ksub">Actualizado: {str(sstats.get("updated_at","—"))[:16]}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="info-box">
        No hay datos de suelo para este cliente.<br>
        Haz clic en <b>Obtener datos de suelo</b> para consultar SoilGrids.
        </div>
        """, unsafe_allow_html=True)

    col_soil_btn, col_soil_dl = st.columns([1, 2], gap="medium")
    with col_soil_btn:
        soil_btn_label = "🔄 Actualizar datos de suelo" if soil_exists else "🌱 Obtener datos de suelo"
        if st.button(soil_btn_label, use_container_width=True, type="primary"):
            soil_progress = st.progress(0, text="Conectando con SoilGrids...")
            soil_status_txt = st.empty()

            def _soil_progress(done, total):
                pct = int(done / total * 100)
                soil_progress.progress(pct, text=f"Consultando parcela {done}/{total}...")
                soil_status_txt.markdown(f"*Parcela {done} de {total}...*")

            try:
                soil_df = enrich_soil_for_client(
                    selected_client, ov_gdf, max_workers=3,
                    progress_callback=_soil_progress,
                )
                soil_progress.progress(100, text="Completado.")
                soil_status_txt.empty()
                sstats = get_soil_stats(soil_df)
                st.success(
                    f"Datos de suelo actualizados: {sstats['ok']}/{sstats['total']} parcelas OK"
                    + (f" · {sstats['errors']} con error" if sstats["errors"] else "")
                )
                st.rerun()
            except Exception as e:
                soil_progress.empty()
                soil_status_txt.empty()
                st.error(f"Error al consultar SoilGrids: {e}")

    # Errores parciales de suelo
    if soil_exists:
        err_soil = soil_df[soil_df["soil_status"] != "ok"]
        if not err_soil.empty:
            with st.expander(f"⚠️ {len(err_soil)} parcelas con error en suelo", expanded=False):
                st.dataframe(err_soil[["parcel_id", "soil_error"]],
                             use_container_width=True, hide_index=True)

        # Tabla resumen variables de suelo
        ok_soil = soil_df[soil_df["soil_status"] == "ok"].copy()
        if not ok_soil.empty:
            st.markdown('<div class="section-title" style="margin-top:14px">🪨 Variables de suelo por parcela</div>',
                        unsafe_allow_html=True)
            disp_soil = ok_soil[["parcel_id", "tipo_suelo", "drenaje",
                                  "materia_organica_%", "profundidad_suelo_cm",
                                  "clay_%", "sand_%", "silt_%"]].copy()
            for col in ["materia_organica_%", "clay_%", "sand_%", "silt_%"]:
                if col in disp_soil.columns:
                    disp_soil[col] = pd.to_numeric(disp_soil[col], errors="coerce").round(2)
            st.dataframe(disp_soil, use_container_width=True, hide_index=True, height=280)

# ---------------------------------------------------------------------------
# ENRIQUECIMIENTO HIDROLÓGICO (Overpass API)
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown('<div class="section-title">🌊 Enriquecimiento hidrológico (Overpass / OSM)</div>',
            unsafe_allow_html=True)

if raw_status != "completo":
    st.markdown('<div class="warn-box">⚠️ Confirma primero los datos del agricultor.</div>',
                unsafe_allow_html=True)
else:
    hydro_df = load_hydrology_cache(selected_client)
    hydro_exists = hydro_df is not None and not hydro_df.empty

    if hydro_exists:
        hstats = get_hydrology_stats(hydro_df)
        h_color = "#27AE60" if hstats["pct_ok"] == 100 else "#E67E22"
        st.markdown(f"""
        <div class="kpi-row kpi3">
          <div class="kpi-card ok">
            <div class="klabel">🌊 Parcelas con distancia</div>
            <div class="kval">{hstats["ok"]}/{hstats["total"]}</div>
            <div class="ksub" style="color:{h_color}">{hstats["pct_ok"]}% completitud</div>
          </div>
          <div class="kpi-card info">
            <div class="klabel">📡 Fuente</div>
            <div class="kval" style="font-size:13px">Overpass / OSM</div>
            <div class="ksub">Radio: 5000 m · sin API key</div>
          </div>
          <div class="kpi-card {'ok' if hstats['errors']+hstats['no_water']==0 else 'warn'}">
            <div class="klabel">⚠️ Sin agua / errores</div>
            <div class="kval">{hstats['no_water'] + hstats['errors']}</div>
            <div class="ksub">Actualizado: {str(hstats.get("updated_at","—"))[:16]}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="info-box">No hay datos hidrológicos. Una sola consulta Overpass cubre todas las parcelas del cliente.</div>
        """, unsafe_allow_html=True)

    col_h_btn, col_h_tbl = st.columns([1, 3], gap="medium")
    with col_h_btn:
        h_btn = "🔄 Actualizar hidrología" if hydro_exists else "🌊 Obtener distancia a cauces"
        if st.button(h_btn, use_container_width=True, type="primary"):
            with st.spinner("Consultando Overpass API (una sola petición para todas las parcelas)..."):
                try:
                    hydro_df = enrich_hydrology_for_client(selected_client, ov_gdf, radius_m=5000)
                    hstats = get_hydrology_stats(hydro_df)
                    st.success(
                        f"Hidrología actualizada: {hstats['ok']}/{hstats['total']} parcelas con distancia"
                        + (f" · {hstats['no_water']} sin agua en radio" if hstats["no_water"] else "")
                        + (f" · {hstats['errors']} errores" if hstats["errors"] else "")
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error Overpass: {e}")

    if hydro_exists:
        ok_h = hydro_df[hydro_df["hydrology_status"] == "ok"].copy()
        err_h = hydro_df[hydro_df["hydrology_status"] != "ok"]
        if not err_h.empty:
            with st.expander(f"⚠️ {len(err_h)} parcelas con error / sin agua", expanded=False):
                st.dataframe(err_h[["parcel_id", "hydrology_status", "hydrology_error"]],
                             use_container_width=True, hide_index=True)
        with col_h_tbl:
            if not ok_h.empty:
                disp_h = ok_h[["parcel_id", "distancia_rio_m",
                               "nearest_water_type", "nearest_water_name"]].copy()
                disp_h["distancia_rio_m"] = pd.to_numeric(disp_h["distancia_rio_m"], errors="coerce").round(0)
                st.dataframe(disp_h, use_container_width=True, hide_index=True, height=260)

# ---------------------------------------------------------------------------
# CSV CONSOLIDADO + ENCHARCAMIENTO — integra todas las fuentes disponibles
# ---------------------------------------------------------------------------
if raw_status == "completo":
    st.markdown("---")
    st.markdown('<div class="section-title">📦 CSV consolidado · 💧 Encharcamiento estimado</div>',
                unsafe_allow_html=True)

    # Cargar todos los caches disponibles
    _w_df = load_weather_cache(selected_client)
    _s_df = load_soil_cache(selected_client)
    _h_df = load_hydrology_cache(selected_client)
    _farmer = load_farmer_inputs(selected_client)
    _farmer_sub = (
        _farmer[["parcel_id"] + [c for c in ["tipo_olivar", "riego", "variedad", "estado_fenologico"]
                                 if c in _farmer.columns]]
        if _farmer is not None else None
    )

    # Assembler (calcula encharcamiento internamente)
    enriched_df = assemble_enriched_csv(
        selected_client, ov_gdf, _farmer_sub, _w_df, _s_df, _h_df
    )
    coverage = get_enrichment_coverage(enriched_df)

    # Cobertura por fuente
    src_labels = {
        "shapefile": ("🗺", "Shapefile"),
        "agricultor": ("👨‍🌾", "Agricultor"),
        "meteorologia": ("🌧", "Meteorología"),
        "suelo": ("🌱", "Suelo"),
        "hidrologia": ("🌊", "Hidrología + Encharcam."),
        "economico": ("💶", "Económico"),
    }
    cov_cols = st.columns(len(coverage))
    for (src, cov), col in zip(coverage.items(), cov_cols):
        if not cov:
            continue
        pct_vals = [v["pct"] for v in cov.values()]
        avg_pct = round(sum(pct_vals) / len(pct_vals)) if pct_vals else 0
        icon, label = src_labels.get(src, ("•", src))
        card_css = "ok" if avg_pct == 100 else ("warn" if avg_pct > 0 else "info")
        with col:
            st.markdown(f"""
            <div class="kpi-card {card_css}" style="padding:10px 12px">
              <div class="klabel">{icon} {label}</div>
              <div class="kval" style="font-size:20px">{avg_pct}%</div>
              <div class="ksub">{len(cov)} col.</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")

    # Advertencias de pendiente extrema
    slope_warnings = get_slope_warnings(enriched_df)
    if slope_warnings:
        st.markdown('<div class="section-title" style="margin-top:8px">⚠️ Advertencias - Pendiente extrema SIGPAC</div>',
                    unsafe_allow_html=True)
        warning_df = pd.DataFrame(slope_warnings)
        # Colorear por nivel
        def color_nivel(val):
            if val == "ALERTA FUERTE":
                return ["background:#FFEBEE"] * len(warning_df.columns)
            elif val == "ADVERTENCIA":
                return ["background:#FFF8E1"] * len(warning_df.columns)
            return [""] * len(warning_df.columns)

        display_df = warning_df[["parcel_id", "pendiente_%", "nivel"]].copy()
        display_df.columns = ["Parcela", "Pendiente (%)", "Nivel"]
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=min(200, 40 + len(warning_df) * 35))
        st.markdown(
            '<div style="font-size:11px;color:#C0392B">Nota: Valores extremos (>100%) pueden indicar error SIGPAC. '
            'Revisar antes de usar en modelo.</div>',
            unsafe_allow_html=True
        )

    # Distribución de riesgo de encharcamiento
    wlog_dist = get_waterlogging_risk_distribution(enriched_df)
    if any(v > 0 for v in wlog_dist.values() if v is not None):
        st.markdown('<div class="section-title" style="margin-top:8px">💧 Distribución de riesgo de encharcamiento</div>',
                    unsafe_allow_html=True)
        r_cols = st.columns(5)
        risk_items = [
            ("Sin riesgo", wlog_dist.get("sin_riesgo", 0), "ok", "0 días"),
            ("Riesgo bajo", wlog_dist.get("bajo", 0), "info", "0–1 días"),
            ("Moderado", wlog_dist.get("moderado", 0), "warn", "1–3 días"),
            ("Alto", wlog_dist.get("alto", 0), "warn", "> 3 días"),
            ("Sin datos", wlog_dist.get("sin_datos", 0), "info", "lluvia faltante"),
        ]
        for (label, val, css, sub), col in zip(risk_items, r_cols):
            with col:
                st.markdown(f"""
                <div class="kpi-card {css}" style="padding:10px 12px">
                  <div class="klabel">💧 {label}</div>
                  <div class="kval" style="font-size:22px">{val}</div>
                  <div class="ksub">{sub}</div>
                </div>
                """, unsafe_allow_html=True)

        # Tabla encharcamiento
        if "duracion_encharcamiento_dias" in enriched_df.columns:
            with st.expander("Ver tabla de encharcamiento por parcela", expanded=False):
                wlog_tbl = enriched_df[["parcel_id", "rain_72h_mm", "drenaje",
                                        "pendiente_%", "distancia_rio_m",
                                        "duracion_encharcamiento_dias"]].copy()
                for col in ["rain_72h_mm", "pendiente_%", "distancia_rio_m", "duracion_encharcamiento_dias"]:
                    if col in wlog_tbl.columns:
                        wlog_tbl[col] = pd.to_numeric(wlog_tbl[col], errors="coerce").round(2)
                st.dataframe(wlog_tbl, use_container_width=True, hide_index=True)

    # Descarga consolidado
    col_dl_cons, col_cons_info = st.columns([1, 3], gap="medium")
    with col_dl_cons:
        from src.features.build_input_from_parcels import SCHEMA_COLUMNS
        n_complete_cols = int(enriched_df[SCHEMA_COLUMNS].notna().all(axis=0).sum())

        # CSV ESTRICTO PARA MODELO (solo 22 cols)
        ml_df = get_ml_ready_csv(enriched_df)
        ml_bytes = to_csv_bytes(ml_df)
        st.download_button(
            label=f"⬇️ CSV para modelo ML (22 cols)",
            data=ml_bytes,
            file_name=f"input_ml_{selected_client}.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )
        st.markdown(
            f"<div style='font-size:11px;color:#7A9A6E;text-align:center;margin-top:4px'>"
            f"{len(ml_df)} parcelas OV · 22 cols exactas · sep ;</div>",
            unsafe_allow_html=True,
        )
    with col_cons_info:
        econ_stats = get_economic_stats(enriched_df)
        econ_pct = econ_stats.get("pct_all", 0)
        ml_ready = get_ml_readiness(enriched_df)
        ready_badge = "LISTO para ML" if ml_ready["ready"] else f"Incompleto: {ml_ready['reason']}"
        ready_color = "#27AE60" if ml_ready["ready"] else "#E67E22"
        st.markdown(f"""
        <div class="info-box">
        <b>CSV consolidado</b> → <code>data/enriched/{selected_client}_input_enriched.csv</code><br>
        Integra: shapefile + agricultor + Open-Meteo + SoilGrids + Overpass + económico + encharcamiento.<br>
        <b>Variables económicas:</b> {econ_stats['all_filled']}/{econ_stats['total']} parcelas ({econ_pct}%) ·
        rendimiento ({econ_stats['yield_filled']}) · precio ({econ_stats['price_filled']}) · coste ({econ_stats['cost_filled']})<br>
        <b style="color:{ready_color}">Estado modelo ML:</b> {ready_badge} ({ml_ready['cols_complete']}/{ml_ready['cols_total']} cols)
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("""
<div style='text-align:center;padding:24px 0 6px;font-size:11px;color:#A0B89A'>
RAIN-OLIVAR · Plataforma geoespacial para análisis de riesgo en olivar mediterráneo
</div>
""", unsafe_allow_html=True)
