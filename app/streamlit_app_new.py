"""
RAIN-OLIVAR: Aplicación Streamlit reorganizada en 4 pestañas.

Flujo:
1. 📍 Data        — Preparación de parcelas y datos del agricultor
2. 🌦️ Enriquecimiento — APIs, CSV para ML
3. 🤖 Modelado    — Predicciones, mapa, ranking, detalle de parcela
4. 🧠 IA e Informe — Análisis LLM, recomendaciones, PDF
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd

from src.geo.geodata_loader import get_available_clients, load_client_geodataframe
from src.geo.parcels_processor import process_parcels
from src.geo.usage_filter import filter_ov
from src.features.persistence import get_client_status
from src.features.prediction_perdida import load_predictions
from app.components import (
    render_page_data_parcela,
    render_page_enrichment,
    render_page_modeling,
    render_page_ia_informe,
)

# ── CONFIG ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RAIN-OLIVAR | Análisis de Riesgo",
    page_icon="🫒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html,body,[class*="css"]{font-family:'Segoe UI',sans-serif}
[data-testid="stAppViewContainer"]{background:#F7F9F5}

/* Texto oscuro en contenido principal */
[data-testid="stAppViewContainer"] .main .block-container,
[data-testid="stAppViewContainer"] .main p,
[data-testid="stAppViewContainer"] .main li,
[data-testid="stAppViewContainer"] .main label,
[data-testid="stAppViewContainer"] .main h1,
[data-testid="stAppViewContainer"] .main h2,
[data-testid="stAppViewContainer"] .main h3,
[data-testid="stAppViewContainer"] .main h4,
[data-testid="stAppViewContainer"] .main span,
[data-testid="stAppViewContainer"] .main .stMarkdown{color:#1f2933}

/* Sidebar oscuro */
[data-testid="stSidebar"]{background:#1E3A2F}
[data-testid="stSidebar"] *{color:#E8F0E6 !important}

/* Banner verde */
.main-header{background:linear-gradient(135deg,#2D5016 0%,#4A7C59 60%,#6B9E5E 100%);
  padding:18px 28px 14px;border-radius:12px;margin-bottom:14px;
  box-shadow:0 4px 18px rgba(45,80,22,.22)}
.main-header h1{color:#fff;font-size:22px;font-weight:700;margin:0 0 3px}
.main-header p{color:#C8E6C0;font-size:12px;margin:0}

/* Títulos de sección */
.section-title{font-size:13px;font-weight:700;color:#2D5016;
  border-bottom:2px solid #C8DFC0;padding-bottom:4px;margin-bottom:10px;margin-top:5px}

/* Barras de completitud */
.comp-bar-wrap{background:#E8F0E6;border-radius:8px;height:9px;margin:5px 0 3px}
.comp-bar{background:#4A7C59;border-radius:8px;height:9px}
.comp-bar.warn{background:#E67E22}
.comp-bar.danger{background:#C0392B}
</style>
""", unsafe_allow_html=True)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:14px 8px 16px;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:14px'>
      <h2 style='color:#fff !important;font-size:18px;font-weight:800;margin:0'>
        🫒 RAIN<span style='color:#8DC87B'>-OLIVAR</span></h2>
      <p style='color:#8DC87B !important;font-size:10px;margin:3px 0 0;letter-spacing:1px;text-transform:uppercase'>
        Plataforma Geoespacial</p>
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
        label_visibility="collapsed",
    )

    # Estado del cliente
    status = get_client_status(selected_client)
    status_label = {"sin_datos": "Sin datos", "borrador": "Borrador",
                    "completo": "Completo ✓", "listo_para_apis": "Listo para APIs ✓"}.get(status, status)
    color_s = "#27AE60" if status in ("completo", "listo_para_apis") else "#E67E22"
    st.markdown(
        f"<div style='font-size:11px;margin-bottom:8px'>"
        f"Estado: <b style='color:{color_s}'>{status_label}</b></div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Selector de parcela (por parcel_id)
    try:
        gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
        ov_gdf = filter_ov(gdf)
        parcel_ids = ["— Ninguna —"] + sorted(ov_gdf["parcel_id"].astype(str).tolist())
        current_sel = st.session_state.get("selected_parcel_id") or "— Ninguna —"
        if current_sel not in parcel_ids:
            current_sel = "— Ninguna —"
        sidebar_sel = st.selectbox(
            "Parcela activa",
            options=parcel_ids,
            index=parcel_ids.index(current_sel),
            label_visibility="collapsed",
        )
        st.session_state["selected_parcel_id"] = sidebar_sel if sidebar_sel != "— Ninguna —" else None
    except Exception as e:
        st.warning(f"Error parcelas: {str(e)[:80]}")
        st.session_state["selected_parcel_id"] = None

    st.markdown("---")
    st.markdown("""
    <div style='font-size:10px;color:#8DC87B;line-height:1.9'>
    ✅ Carga shapefile<br>✅ Editor agricultor<br>✅ Open-Meteo<br>
    ✅ SoilGrids<br>✅ Overpass API<br>✅ Enriquecimiento económico<br>
    ✅ Predicción ML<br>✅ Mapa interactivo<br>✅ Análisis IA<br>✅ Informe PDF
    </div>
    """, unsafe_allow_html=True)

# ── HEADER ────────────────────────────────────────────────────────────────────
sel_parcel = st.session_state.get("selected_parcel_id")
subtitle = f"Parcela activa: {sel_parcel}" if sel_parcel else "Enriquecimiento geoespacial → Modelado ML → Análisis IA"

st.markdown(f"""
<div class="main-header">
  <h1>🫒 RAIN-OLIVAR · {selected_client.replace('_', ' ').title()}</h1>
  <p>{subtitle}</p>
</div>
""", unsafe_allow_html=True)

# ── NAVEGACIÓN (4 pestañas) ───────────────────────────────────────────────────
PAGES = [
    ("📍 Data",          "data"),
    ("🌦️ Enriquecimiento","enrichment"),
    ("🤖 Modelado",       "modeling"),
    ("🧠 IA e Informe",   "ia_informe"),
]

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "data"

nav_cols = st.columns(len(PAGES))
for col, (label, page_id) in zip(nav_cols, PAGES):
    with col:
        is_active = st.session_state["active_page"] == page_id
        if st.button(label, use_container_width=True,
                     type="primary" if is_active else "secondary",
                     key=f"nav_{page_id}"):
            st.session_state["active_page"] = page_id
            st.rerun()

st.markdown("---")

# ── DATOS COMPARTIDOS ─────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_enriched(client_id: str) -> pd.DataFrame | None:
    path = f"data/enriched/{client_id}_input_enriched.csv"
    if os.path.exists(path):
        return pd.read_csv(path, sep=";")
    return None

enriched_df = _load_enriched(selected_client)
predictions_df = load_predictions(selected_client)
selected_parcel_id = st.session_state.get("selected_parcel_id")

# modeling_df (predictions + enriched, para IA y PDF)
modeling_df = None
if predictions_df is not None and enriched_df is not None:
    modeling_df = predictions_df.copy()
    modeling_df["parcel_id"] = modeling_df["parcel_id"].astype(str).str.strip()
    enrich_copy = enriched_df.copy()
    enrich_copy["parcel_id"] = enrich_copy["parcel_id"].astype(str).str.strip()
    extra = ["parcel_id"] + [c for c in enrich_copy.columns if c not in modeling_df.columns]
    modeling_df = modeling_df.merge(enrich_copy[extra], on="parcel_id", how="left")
    numeric_cols = [
        "pendiente_%", "rain_7d_mm", "humedad_suelo_%", "duracion_encharcamiento_dias",
        "pct_perdida_pred_pct", "impacto_total_eur", "impacto_eur_ha_pred",
    ]
    for col in numeric_cols:
        if col in modeling_df.columns:
            modeling_df[col] = pd.to_numeric(modeling_df[col], errors="coerce")

# ── RENDER ────────────────────────────────────────────────────────────────────
try:
    page = st.session_state["active_page"]

    if page == "data":
        render_page_data_parcela(selected_client)

    elif page == "enrichment":
        render_page_enrichment(selected_client)

    elif page == "modeling":
        render_page_modeling(
            selected_client,
            enriched_df,
            selected_parcel_id=selected_parcel_id,
            predictions_df=predictions_df,
        )

    elif page == "ia_informe":
        render_page_ia_informe(
            selected_client,
            enriched_df=enriched_df,
            modeling_df=modeling_df,
            selected_parcel_id=selected_parcel_id,
        )

except Exception as e:
    import traceback
    st.error(f"Error en página: {str(e)}")
    with st.expander("Detalles del error"):
        st.code(traceback.format_exc())

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("""
<hr style='margin-top:40px'>
<div style='text-align:center;padding:10px 0 4px;font-size:10px;color:#A0B89A'>
RAIN-OLIVAR · Plataforma geoespacial para análisis de riesgo en olivar mediterráneo
</div>
""", unsafe_allow_html=True)
