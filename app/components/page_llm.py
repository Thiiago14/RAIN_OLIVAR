"""Página de recomendaciones IA."""
import streamlit as st


def render_page_llm(selected_parcel_id: str | None = None) -> None:
    """Página de recomendaciones IA por parcela."""
    st.markdown('<div class="section-title">🧠 Recomendaciones IA</div>', unsafe_allow_html=True)

    if not selected_parcel_id or selected_parcel_id == "— Ninguna —":
        st.info("Selecciona una parcela para ver recomendaciones IA.")
        return

    st.info("Página de recomendaciones IA. Implementación pendiente.")
    st.write(f"**Parcela seleccionada:** {selected_parcel_id}")
    st.markdown("""
    ### Próximas integraciones:
    - 🤖 Análisis LLM por parcela
    - 📋 Recomendaciones agrícolas personalizadas
    - 📊 Análisis de riesgos específicos
    """)
