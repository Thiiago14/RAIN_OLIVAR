"""
RAIN-OLIVAR: Aplicación Streamlit reorganizada en módulos.

Estructura de navegación:
- 📍 Data parcela: Preparación de datos
- 🌦️ Enriquecimiento: APIs y enriquecimiento
- 🤖 Modelado y predicciones: Dashboard ML
- 🔎 Análisis por parcela: Detalle individual
- 🧠 Recomendaciones IA: (pendiente)
- 📄 Informe PDF: (pendiente)
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd

from src.geo.geodata_loader import get_available_clients, load_client_geodataframe
from src.geo.parcels_processor import process_parcels
from src.geo.usage_filter import filter_ov, get_usage_stats
from src.features.persistence import (
    get_client_status,
    save_farmer_inputs, load_farmer_inputs, merge_saved_with_gdf,
)
from src.features.prediction_perdida import load_predictions

from app.components import (
    render_page_data_parcela,
    render_page_enrichment,
    render_page_modeling,
    render_page_parcel_detail,
    render_page_llm,
    render_page_report,
)

# === CONFIGURACIÓN ===
st.set_page_config(
    page_title="RAIN-OLIVAR | Plataforma Geoespacial",
    page_icon="🫒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS
st.markdown("""
<style>
html,body,[class*="css"]{font-family:'Segoe UI',sans-serif}
[data-testid="stAppViewContainer"]{background:#F7F9F5}

/* Texto oscuro en el contenido principal (NO en sidebar) */
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

/* Sidebar oscuro con texto claro */
[data-testid="stSidebar"]{background:#1E3A2F}
[data-testid="stSidebar"] *{color:#E8F0E6 !important}

/* Banner verde con texto blanco */
.main-header{background:linear-gradient(135deg,#2D5016 0%,#4A7C59 60%,#6B9E5E 100%);
  padding:22px 32px 16px 32px;border-radius:14px;margin-bottom:18px;
  box-shadow:0 4px 20px rgba(45,80,22,.25)}
.main-header h1{color:#fff !important;font-size:23px;font-weight:700;margin:0 0 4px}
.main-header p{color:#E8F0E6 !important;margin:0}
.section-title{font-size:14px;font-weight:700;color:#2D5016 !important;
  border-bottom:2px solid #C8DFC0;padding-bottom:5px;margin-bottom:11px;margin-top:6px}
</style>
""", unsafe_allow_html=True)

# === SIDEBAR ===
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:16px 8px 18px;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:16px'>
        <h2 style='color:#fff !important;font-size:19px;font-weight:800;margin:0'>🫒 RAIN<span style='color:#8DC87B'>-OLIVAR</span></h2>
        <p style='color:#8DC87B !important;font-size:11px;margin:3px 0 0;letter-spacing:1px;text-transform:uppercase'>Plataforma Geoespacial</p>
    </div>
    """, unsafe_allow_html=True)

    clients = get_available_clients()
    if not clients:
        st.error("No se encontraron clientes en data/clientes_shp/")
        st.stop()

    selected_client = st.selectbox("Cliente", options=clients, format_func=lambda x: x.replace("_", " ").title())

    st.markdown("---")
    raw_status = get_client_status(selected_client)
    st.write(f"**Estado:** {raw_status}")

    st.markdown("---")

    # Selector de parcela
    try:
        gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
        ov_gdf = filter_ov(gdf)
        parcel_ids = ["— Ninguna —"] + ov_gdf["parcel_id"].tolist()
        current_sel = st.session_state.get("selected_parcel_id", "— Ninguna —")
        if current_sel not in parcel_ids:
            current_sel = "— Ninguna —"
        sidebar_sel = st.selectbox(
            "Parcela activa",
            options=parcel_ids,
            index=parcel_ids.index(current_sel),
            label_visibility="collapsed",
        )
        if sidebar_sel != "— Ninguna —":
            st.session_state["selected_parcel_id"] = sidebar_sel
        else:
            st.session_state["selected_parcel_id"] = None
    except Exception as e:
        st.error(f"Error cargando parcelas: {str(e)[:100]}")

# === NAVEGACIÓN PRINCIPAL ===
st.markdown("""
<div class="main-header">
  <h1>RAIN-OLIVAR · Análisis de Riesgo en Olivar</h1>
  <p>Enriquecimiento geoespacial → Modelado ML → Análisis integrado</p>
</div>
""", unsafe_allow_html=True)

# Navegación en segmented_control o radio (simulado con columns + buttons)
st.markdown("### Navegación")

nav_cols = st.columns(6)
pages = [
    ("📍 Data", "data_parcela"),
    ("🌦️ Enriquecimiento", "enrichment"),
    ("🤖 Modelado", "modeling"),
    ("🔎 Detalle", "parcel_detail"),
    ("🧠 IA", "llm"),
    ("📄 PDF", "report"),
]

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "data_parcela"

for col, (label, page_id) in zip(nav_cols, pages):
    with col:
        if st.button(label, use_container_width=True, type=("primary" if st.session_state["active_page"] == page_id else "secondary")):
            st.session_state["active_page"] = page_id
            st.rerun()

st.markdown("---")

# === CARGAR DATOS ===
try:
    gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
    ov_gdf = filter_ov(gdf)
except Exception as e:
    st.error(f"Error: {str(e)}")
    st.stop()

# Cargar CSV consolidado si existe
try:
    import os
    enriched_path = f"data/enriched/{selected_client}_input_enriched.csv"
    if os.path.exists(enriched_path):
        enriched_df = pd.read_csv(enriched_path, sep=";")
    else:
        enriched_df = None
except Exception:
    enriched_df = None

# === RENDER PÁGINA ACTIVA ===
try:
    predictions_df = load_predictions(selected_client)
    selected_parcel_id = st.session_state.get("selected_parcel_id")

    if st.session_state["active_page"] == "data_parcela":
        render_page_data_parcela(selected_client)

    elif st.session_state["active_page"] == "enrichment":
        render_page_enrichment(selected_client)

    elif st.session_state["active_page"] == "modeling":
        render_page_modeling(selected_client, enriched_df)

    elif st.session_state["active_page"] == "parcel_detail":
        render_page_parcel_detail(selected_parcel_id, enriched_df, predictions_df)

    elif st.session_state["active_page"] == "llm":
        render_page_llm(selected_parcel_id)

    elif st.session_state["active_page"] == "report":
        render_page_report()

except Exception as e:
    import traceback
    st.error(f"Error en página: {str(e)}")
    st.error(traceback.format_exc())

# === FOOTER ===
st.markdown("""
---
<div style='text-align:center;padding:24px 0 6px;font-size:11px;color:#A0B89A'>
RAIN-OLIVAR · Plataforma geoespacial para análisis de riesgo en olivar mediterráneo
</div>
""", unsafe_allow_html=True)
