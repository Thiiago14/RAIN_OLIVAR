"""Página de enriquecimiento de variables."""
import streamlit as st


def render_page_enrichment(selected_client: str | None = None) -> None:
    """Página de enriquecimiento: meteo, suelo, hidrología, económico."""
    st.markdown('<div class="section-title">🌦️ Enriquecimiento</div>', unsafe_allow_html=True)

    if not selected_client:
        st.error("No hay cliente seleccionado.")
        return

    st.info("Página de enriquecimiento de datos. Contenido será migrado desde streamlit_app.py")
    st.write(f"Cliente seleccionado: **{selected_client}**")
    st.markdown("""
    ### Próximas integraciones:
    - 🌧️ Open-Meteo (meteorología)
    - 🌍 SoilGrids (suelo)
    - 🏞️ Overpass API (hidrología)
    - 💰 Enriquecimiento económico
    - ✓ Estado ready_for_ml
    """)
