"""Página de preparación y carga de datos de parcelas."""
import streamlit as st
from streamlit_folium import st_folium

from src.geo.geodata_loader import load_client_geodataframe
from src.geo.parcels_processor import process_parcels, get_kpis
from src.geo.usage_filter import filter_ov, get_usage_stats
from src.geo.map_builder import build_parcels_map
from src.features.build_input_from_parcels import build_base_input, to_csv_bytes
from src.features.persistence import (
    FARMER_COLS,
    save_farmer_inputs, load_farmer_inputs, merge_saved_with_gdf,
)
from src.features.farmer_inputs import (
    init_farmer_data, build_editor_df, calc_completeness,
    TIPO_OLIVAR_OPTIONS, RIEGO_OPTIONS, VARIEDAD_OPTIONS,
    ESTADO_FENOLOGICO_OPTIONS,
)


def _farmer_key(client_id: str) -> str:
    return f"farmer_v2_{client_id}"


def _editor_ver_key(client_id: str) -> str:
    return f"editor_ver_{client_id}"


def _init_session(client_id: str, ov_gdf) -> None:
    """Carga o inicializa session_state para el editor del cliente."""
    fk = _farmer_key(client_id)
    vk = _editor_ver_key(client_id)

    if fk not in st.session_state:
        saved = load_farmer_inputs(client_id)
        if saved is not None and not saved.empty:
            merged = merge_saved_with_gdf(saved, ov_gdf)
            st.session_state[f"_load_msg_{client_id}"] = "loaded"
        else:
            merged = init_farmer_data(ov_gdf)
            st.session_state[f"_load_msg_{client_id}"] = "init"
        st.session_state[fk] = merged
        st.session_state[vk] = st.session_state.get(vk, 0) + 1
    else:
        # Si el shapefile cambió, re-merge
        current_uids = set(ov_gdf["parcel_uid"].tolist())
        saved_uids = set(
            st.session_state[fk]["parcel_uid"].tolist()
            if "parcel_uid" in st.session_state[fk].columns
            else []
        )
        if current_uids != saved_uids:
            saved_file = load_farmer_inputs(client_id)
            st.session_state[fk] = merge_saved_with_gdf(saved_file, ov_gdf)
            st.session_state[vk] = st.session_state.get(vk, 0) + 1


def _comp_bar_html(pct: int) -> str:
    css = "danger" if pct < 50 else ("warn" if pct < 100 else "")
    return (
        f'<div class="comp-bar-wrap">'
        f'<div class="comp-bar {css}" style="width:{pct}%"></div>'
        f'</div>'
    )


def render_page_data_parcela(selected_client: str | None = None) -> None:
    """Página inicial: carga de parcelas y datos del agricultor."""
    st.markdown('<div class="section-title">📍 Data parcela</div>', unsafe_allow_html=True)

    if not selected_client:
        st.error("No hay cliente seleccionado.")
        return

    # === CARGA DE PARCELAS ===
    try:
        gdf = process_parcels(load_client_geodataframe(selected_client), selected_client)
        ov_gdf = filter_ov(gdf)
    except Exception as e:
        st.error(f"Error cargando shapefile: {str(e)}")
        return

    stats = get_usage_stats(gdf)
    filter_ov_active = st.checkbox("🫒 Solo parcelas de olivar (OV)", value=True)
    display_gdf = ov_gdf if filter_ov_active else gdf

    # Inicializar session state del editor
    _init_session(selected_client, ov_gdf)
    fk = _farmer_key(selected_client)

    load_msg = st.session_state.pop(f"_load_msg_{selected_client}", None)
    if load_msg == "loaded":
        st.info("Datos del agricultor cargados desde archivo local.")

    # === KPIs ===
    try:
        kpis_all = get_kpis(gdf)
        editor_df_for_comp = build_editor_df(ov_gdf, st.session_state[fk])
        comp = calc_completeness(
            editor_df_for_comp[[c for c in ["parcel_id"] + FARMER_COLS if c in editor_df_for_comp.columns]]
        )
        pct = comp["pct"]
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total polígonos", kpis_all["n_parcelas"])
        with col2:
            st.metric("Parcelas OV", stats["n_ov"], delta=f"{stats['pct_ov']}% del total")
        with col3:
            st.metric("Superficie OV", f"{stats['ha_ov']:,.2f} ha")
        with col4:
            st.metric("Completitud agricultor", f"{pct}%", delta="completo" if pct == 100 else f"{comp['pending_fields']} pendientes")
    except Exception as e:
        st.warning(f"No se pudieron calcular KPIs: {str(e)}")

    # === MAPA + TABLA ===
    col_map, col_table = st.columns([3, 2], gap="large")

    with col_map:
        st.markdown('<div class="section-title">Mapa de parcelas</div>', unsafe_allow_html=True)
        try:
            selected_parcel_id = st.session_state.get("selected_parcel_id")
            folium_map = build_parcels_map(
                display_gdf,
                filter_ov=filter_ov_active,
                selected_parcel_id=selected_parcel_id,
                mode="uso_sigpac",
            )
            st_folium(folium_map, use_container_width=True, height=450)
        except Exception as e:
            st.warning(f"No se pudo renderizar el mapa: {str(e)}")

    with col_table:
        st.markdown('<div class="section-title">Parcelas cargadas</div>', unsafe_allow_html=True)
        try:
            table_cols = [
                "parcel_id", "client_id", "area_ha_calc", "uso_sigpac",
                "pendiente_pct", "altitud_m", "provincia", "municipio",
            ]
            existing_cols = [c for c in table_cols if c in display_gdf.columns]
            table_df = display_gdf[existing_cols].copy()
            rename_map = {
                "parcel_id": "Parcela", "client_id": "Cliente",
                "area_ha_calc": "Sup. (ha)", "uso_sigpac": "Uso",
                "pendiente_pct": "Pendiente (%)", "altitud_m": "Altitud (m)",
                "provincia": "Provincia", "municipio": "Municipio",
            }
            table_df.columns = [rename_map.get(c, c) for c in table_df.columns]
            st.dataframe(table_df, use_container_width=True,
                         height=min(450, 40 + len(table_df) * 35), hide_index=True)
        except Exception as e:
            st.warning(f"No se pudo mostrar la tabla: {str(e)}")

    # === EDITOR DEL AGRICULTOR ===
    st.markdown("---")
    st.markdown('<div class="section-title">✏️ Completar datos del agricultor</div>',
                unsafe_allow_html=True)

    try:
        if len(ov_gdf) == 0:
            st.warning("No hay parcelas OV para editar.")
            return

        st.info(
            f"Completa los 4 campos obligatorios para las **{len(ov_gdf)} parcelas OV**. "
            "Guardar borrador permite guardar aunque esté incompleto. "
            "Confirmar datos requiere 100% de completitud."
        )

        editor_df = build_editor_df(ov_gdf, st.session_state[fk])
        readonly_in_editor = [c for c in editor_df.columns if c not in FARMER_COLS]
        editor_ver = st.session_state.get(_editor_ver_key(selected_client), 0)

        edited = st.data_editor(
            editor_df,
            column_config={
                "parcel_uid":        st.column_config.TextColumn("UID Estable", disabled=True),
                "parcel_id":         st.column_config.TextColumn("Parcela", disabled=True),
                "client_id":         st.column_config.TextColumn("Cliente", disabled=True),
                "uso_sigpac":        st.column_config.TextColumn("Uso", disabled=True),
                "superficie_ha":     st.column_config.NumberColumn("Sup. (ha)", format="%.4f", disabled=True),
                "pendiente_%":       st.column_config.NumberColumn("Pendiente", format="%d", disabled=True),
                "altitud_m":         st.column_config.NumberColumn("Altitud (m)", format="%d", disabled=True),
                "tipo_olivar":       st.column_config.SelectboxColumn("Tipo Olivar ✱", options=TIPO_OLIVAR_OPTIONS, required=False),
                "riego":             st.column_config.SelectboxColumn("Riego ✱", options=RIEGO_OPTIONS, required=False),
                "variedad":          st.column_config.SelectboxColumn("Variedad ✱", options=VARIEDAD_OPTIONS, required=False),
                "estado_fenologico": st.column_config.SelectboxColumn("Fenología ✱", options=ESTADO_FENOLOGICO_OPTIONS, required=False),
            },
            disabled=readonly_in_editor,
            use_container_width=True,
            hide_index=True,
            key=f"editor_{selected_client}_v{editor_ver}",
            height=min(450, 55 + len(ov_gdf) * 38),
        )

        # Completitud en vivo
        comp_live = calc_completeness(
            edited[[c for c in ["parcel_id"] + FARMER_COLS if c in edited.columns]]
        )
        pct_live = comp_live["pct"]
        st.markdown(
            f'{_comp_bar_html(pct_live)}'
            f'<span style="font-size:12px;color:#555">'
            f'<b>{pct_live}%</b> completitud · '
            f'{comp_live["filled_fields"]}/{comp_live["total_fields"]} campos · '
            f'{comp_live["pending_fields"]} pendientes</span>',
            unsafe_allow_html=True,
        )

        if comp_live["missing_parcels"]:
            with st.expander(f"⚠️ {len(comp_live['missing_parcels'])} parcelas con datos faltantes"):
                for mp in comp_live["missing_parcels"]:
                    st.markdown(f"- **{mp['parcel_id']}** → faltan: `{'`, `'.join(mp['missing_cols'])}`")

        # Botones
        col_draft, col_confirm, col_dl = st.columns(3, gap="medium")

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
                    st.success(f"Datos confirmados → `{path}`")
                    st.rerun()
            else:
                st.button("✅ Confirmar datos", use_container_width=True, disabled=True,
                          help=f"Faltan {comp_live['pending_fields']} campos. Complete el 100%.")

        with col_dl:
            farmer_export = edited[["parcel_id"] + [c for c in FARMER_COLS if c in edited.columns]].copy()
            base_df = build_base_input(ov_gdf, farmer_export)
            st.download_button(
                label="⬇️ CSV base",
                data=to_csv_bytes(base_df),
                file_name=f"parcelas_base_{selected_client}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    except Exception as e:
        st.error(f"Error en editor del agricultor: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
