"""
Generación de informes PDF para RAIN-OLIVAR.

Diseño híbrido:
- Diseño visual limpio del informe actual (colores RAIN-OLIVAR, tipografía clara).
- Contenido estructural del informe_olivar.pdf de referencia (análisis agronómico completo).

Nota: fuentes Helvetica/core sólo soportan latin-1.
Todos los textos pasan por _s() antes de entrar a fpdf.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

REPORTS_DIR = Path("data/reports")

# Paleta RAIN-OLIVAR
C_HEADER_BG = (45, 80, 22)        # Verde oscuro — header página
C_SECTION_BG = (74, 124, 89)      # Verde medio — títulos de sección
C_SECTION_TXT = (255, 255, 255)   # Blanco — texto sobre sección
C_TEXT = (30, 58, 47)             # Verde muy oscuro — texto principal
C_SUBTEXT = (100, 130, 100)       # Verde gris — subtextos
C_ROW_ALT = (240, 248, 240)       # Verde muy claro — filas alternas

# Colores de riesgo
RISK_COLORS = {
    "bajo":    (76, 175, 80),      # Verde
    "medio":   (255, 193, 7),      # Amarillo
    "alto":    (255, 152, 0),      # Naranja
    "muy_alto":(244, 67, 54),      # Rojo
}
RISK_TEXT_COLORS = {
    "bajo":    (255, 255, 255),
    "medio":   (50, 50, 50),
    "alto":    (255, 255, 255),
    "muy_alto":(255, 255, 255),
}


def _s(text) -> str:
    """Sanitiza texto para latin-1: reemplaza caracteres no soportados."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    return (
        text.replace("€", "EUR")
            .replace("°", " grad")
            .replace("–", "-")
            .replace("—", "-")
            .replace("’", "'")
            .replace("“", '"')
            .replace("”", '"')
            .encode("latin-1", errors="replace")
            .decode("latin-1")
    )


def _normalize_risk(val) -> str:
    """Normaliza nivel de riesgo a clave interna."""
    if val is None:
        return "sin_dato"
    s = str(val).lower().strip().replace(" ", "_")
    if s in RISK_COLORS:
        return s
    return "sin_dato"


def _fv(data: dict, key: str, fmt: str = ".2f", default: str = "No disponible") -> str:
    """Formatea un valor del dict de forma segura."""
    v = data.get(key)
    if v is None:
        return default
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return str(v) if str(v) not in ("nan", "None") else default


class RainOlivarPDF:
    """Clase constructora del PDF con diseño RAIN-OLIVAR."""

    PAGE_W = 210
    PAGE_H = 297
    MARGIN = 15
    CONTENT_W = PAGE_W - 2 * MARGIN   # 180 mm
    FOOTER_H = 15

    def __init__(self):
        from fpdf import FPDF
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=self.FOOTER_H + 5)
        self.pdf.set_margins(self.MARGIN, self.MARGIN, self.MARGIN)
        self._page_num = 0

    def add_page(self):
        self.pdf.add_page()
        self._page_num += 1
        self._draw_header()

    def _draw_header(self):
        """Dibuja el encabezado verde en todas las páginas."""
        p = self.pdf
        r, g, b = C_HEADER_BG
        p.set_fill_color(r, g, b)
        p.rect(0, 0, self.PAGE_W, 16, "F")

        p.set_xy(self.MARGIN, 4)
        p.set_font("Helvetica", "B", 11)
        p.set_text_color(255, 255, 255)
        p.cell(130, 8, "INFORME AGRONOMICO - OLIVAR  |  RAIN-OLIVAR", ln=False)

        p.set_font("Helvetica", "", 9)
        p.cell(0, 8, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align="R")
        p.set_y(20)

    def _draw_footer(self):
        """Dibuja el pie de página."""
        p = self.pdf
        p.set_y(-self.FOOTER_H)
        p.set_font("Helvetica", "I", 8)
        p.set_text_color(*C_SUBTEXT)
        p.cell(0, 5, "RAIN-OLIVAR  |  Informe generado automaticamente por IA Agronomica", ln=False)
        p.cell(0, 5, f"Pagina {self._page_num}", ln=True, align="R")

    def section_title(self, text: str):
        """Título de sección con fondo verde."""
        p = self.pdf
        p.ln(4)
        r, g, b = C_SECTION_BG
        p.set_fill_color(r, g, b)
        p.set_text_color(*C_SECTION_TXT)
        p.set_font("Helvetica", "B", 10)
        p.cell(self.CONTENT_W, 8, _s(f"  {text}"), fill=True, ln=True)
        p.set_text_color(*C_TEXT)
        p.ln(2)

    def subsection_header(self, text: str, risk: str = None):
        """Encabezado de parcela coloreado por riesgo."""
        p = self.pdf
        p.ln(3)
        risk_key = _normalize_risk(risk)
        if risk_key in RISK_COLORS:
            bg = RISK_COLORS[risk_key]
            fg = RISK_TEXT_COLORS[risk_key]
        else:
            bg = (180, 180, 180)
            fg = (255, 255, 255)
        r, g, b = bg
        p.set_fill_color(r, g, b)
        p.set_text_color(*fg)
        p.set_font("Helvetica", "B", 9)
        p.cell(self.CONTENT_W, 7, _s(f"  {text}"), fill=True, ln=True)
        p.set_text_color(*C_TEXT)
        p.ln(1)

    def body_text(self, text: str, indent: int = 0):
        """Texto de cuerpo normal."""
        p = self.pdf
        p.set_font("Helvetica", "", 9)
        p.set_text_color(*C_TEXT)
        if indent:
            p.set_x(self.MARGIN + indent)
        p.multi_cell(self.CONTENT_W - indent, 5, _s(text))
        p.ln(1)

    def bullet(self, text: str):
        """Ítem de lista con viñeta."""
        p = self.pdf
        p.set_font("Helvetica", "", 9)
        p.set_text_color(*C_TEXT)
        p.set_x(self.MARGIN + 4)
        p.multi_cell(self.CONTENT_W - 4, 5, _s(f"- {text}"))

    def kv_row(self, key: str, val: str, fill: bool = False):
        """Fila clave:valor en tabla."""
        p = self.pdf
        if fill:
            p.set_fill_color(*C_ROW_ALT)
        p.set_font("Helvetica", "", 9)
        p.set_text_color(*C_TEXT)
        p.cell(80, 6, _s(key), border=1, fill=fill)
        p.set_font("Helvetica", "B", 9)
        p.cell(self.CONTENT_W - 80, 6, _s(str(val)), border=1, fill=fill, ln=True)

    def table_header(self, cols: list[tuple[str, float]]):
        """Encabezado de tabla con fondo verde oscuro."""
        p = self.pdf
        r, g, b = C_SECTION_BG
        p.set_fill_color(r, g, b)
        p.set_text_color(255, 255, 255)
        p.set_font("Helvetica", "B", 8)
        for label, w in cols:
            p.cell(w, 7, _s(label), border=1, fill=True, align="C")
        p.ln()
        p.set_text_color(*C_TEXT)

    def table_row_risk(self, cells: list[tuple[str, float]], risk: str, i: int = 0):
        """Fila de tabla coloreada por nivel de riesgo."""
        p = self.pdf
        risk_key = _normalize_risk(risk)
        if risk_key in RISK_COLORS:
            r, g, b = RISK_COLORS[risk_key]
        else:
            r, g, b = (245, 245, 245) if i % 2 else (255, 255, 255)
        p.set_fill_color(r, g, b)

        if risk_key in RISK_TEXT_COLORS:
            p.set_text_color(*RISK_TEXT_COLORS[risk_key])
        else:
            p.set_text_color(*C_TEXT)

        p.set_font("Helvetica", "", 8)
        for val, w in cells:
            p.cell(w, 6, _s(str(val)), border=1, fill=True, align="C")
        p.ln()
        p.set_text_color(*C_TEXT)

    def table_row(self, cells: list[tuple[str, float]], i: int = 0):
        """Fila de tabla con alternancia."""
        p = self.pdf
        if i % 2 == 0:
            p.set_fill_color(*C_ROW_ALT)
        else:
            p.set_fill_color(255, 255, 255)
        p.set_font("Helvetica", "", 8)
        p.set_text_color(*C_TEXT)
        for val, w in cells:
            p.cell(w, 6, _s(str(val)), border=1, fill=True, align="C")
        p.ln()

    def labelled_text(self, label: str, text: str):
        """Texto con etiqueta en negrita + contenido."""
        p = self.pdf
        p.set_font("Helvetica", "B", 9)
        p.set_text_color(*C_TEXT)
        p.cell(0, 5, _s(label), ln=True)
        p.set_font("Helvetica", "", 9)
        p.multi_cell(self.CONTENT_W, 5, _s(text))
        p.ln(1)

    def output(self) -> bytes:
        """Devuelve bytes del PDF con footers añadidos."""
        # Añadir footers manualmente a cada página
        total = self._page_num
        for i in range(1, total + 1):
            self.pdf.page = i
            self._draw_footer()
        return bytes(self.pdf.output())


# ---------------------------------------------------------------------------
# Helpers de datos
# ---------------------------------------------------------------------------

def _risk_distribution(df: pd.DataFrame) -> list[dict]:
    """Calcula distribución de riesgo."""
    n = len(df)
    rows = []
    for nivel, (umbral, label) in {
        "bajo": ("<5%", "BAJO"),
        "medio": ("5-15%", "MEDIO"),
        "alto": ("15-30%", "ALTO"),
        "muy_alto": (">30%", "MUY ALTO"),
    }.items():
        count = int((df["nivel_riesgo"] == nivel).sum()) if "nivel_riesgo" in df.columns else 0
        pct = f"{100*count/n:.1f}%" if n > 0 else "0%"
        rows.append({"nivel": nivel, "label": label, "count": count, "pct": pct, "umbral": umbral})
    return rows


def _top_parcels(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top N parcelas por impacto económico."""
    if "impacto_total_eur" not in df.columns:
        return df.head(n)
    return df.nlargest(n, "impacto_total_eur").reset_index(drop=True)


# ---------------------------------------------------------------------------
# PDF General del cliente
# ---------------------------------------------------------------------------

def _build_pdf_general(
    client_id: str,
    modeling_df: pd.DataFrame,
    llm_output: dict,
    llm_parcel_outputs: dict | None = None,
) -> bytes:
    """
    Construye PDF general del cliente con:
    1. Portada
    2. Resumen ejecutivo
    3. Indicadores principales
    4. Distribución de riesgo
    5. Top parcelas afectadas
    6. Análisis detallado por parcela (top 5)
    7. Tabla completa de predicciones
    """
    doc = RainOlivarPDF()
    doc.add_page()

    n = len(modeling_df) if not modeling_df.empty else 0
    perdida_media = modeling_df["pct_perdida_pred_pct"].mean() if n and "pct_perdida_pred_pct" in modeling_df.columns else 0
    perdida_max = modeling_df["pct_perdida_pred_pct"].max() if n and "pct_perdida_pred_pct" in modeling_df.columns else 0
    impacto_total = modeling_df["impacto_total_eur"].sum() if n and "impacto_total_eur" in modeling_df.columns else 0
    impacto_medio = modeling_df["impacto_eur_ha_pred"].mean() if n and "impacto_eur_ha_pred" in modeling_df.columns else 0
    n_alto = int(modeling_df["nivel_riesgo"].isin(["alto", "muy_alto"]).sum()) if n and "nivel_riesgo" in modeling_df.columns else 0
    parcela_critica = modeling_df.loc[modeling_df["impacto_total_eur"].idxmax(), "parcel_id"] if n and "impacto_total_eur" in modeling_df.columns else "—"

    # ── 1. RESUMEN EJECUTIVO ──────────────────────────────────────────────────
    doc.section_title(f"1. RESUMEN EJECUTIVO  -  {client_id.replace('_', ' ').title()}")
    doc.kv_row("Total parcelas analizadas", str(n), fill=False)
    doc.kv_row("Impacto total estimado (EUR)", f"{impacto_total:,.2f}", fill=True)
    doc.kv_row("Impacto promedio (EUR/ha)", f"{impacto_medio:,.2f}", fill=False)
    doc.kv_row("Perdida maxima (%)", f"{perdida_max:.2f}%", fill=True)
    doc.kv_row("Porcentaje de perdida medio", f"{perdida_media:.1f}%", fill=False)
    doc.kv_row("Parcelas en riesgo alto/muy alto", str(n_alto), fill=True)
    doc.kv_row("Parcela critica (mayor impacto)", str(parcela_critica), fill=False)
    doc.pdf.ln(4)

    # Texto del resumen ejecutivo
    if llm_output.get("summary"):
        doc.body_text(llm_output["summary"])

    # ── 2. DISTRIBUCIÓN DE RIESGO ────────────────────────────────────────────
    doc.section_title("2. DISTRIBUCION DE RIESGO POR PERDIDA")
    cols = [("Nivel de Riesgo", 45), ("N. Parcelas", 35), ("% del Total", 50), ("Umbral (pct_perdida)", 50)]
    doc.table_header(cols)

    dist = _risk_distribution(modeling_df)
    for row in dist:
        doc.table_row_risk(
            [(row["label"], 45), (str(row["count"]), 35), (row["pct"], 50), (row["umbral"], 50)],
            risk=row["nivel"],
        )

    # ── 3. TOP PARCELAS ───────────────────────────────────────────────────────
    doc.section_title("3. TOP PARCELAS MAS AFECTADAS")
    top_cols = [("Parcela", 50), ("Perdida (%)", 30), ("Impacto (EUR/ha)", 40), ("Impacto total (EUR)", 40), ("Nivel de Riesgo", 20)]
    doc.table_header(top_cols)

    top_df = _top_parcels(modeling_df, 10)
    for i, (_, row) in enumerate(top_df.iterrows()):
        risk = _normalize_risk(row.get("nivel_riesgo"))
        perdida_p = row.get("pct_perdida_pred_pct", 0)
        impacto_ha = row.get("impacto_eur_ha_pred", 0)
        impacto_t = row.get("impacto_total_eur", 0)
        try:
            perdida_str = f"{float(perdida_p):.1f} %"
        except (TypeError, ValueError):
            perdida_str = "—"
        try:
            impacto_ha_str = f"{float(impacto_ha):.2f}"
        except (TypeError, ValueError):
            impacto_ha_str = "—"
        try:
            impacto_t_str = f"{float(impacto_t):.2f}"
        except (TypeError, ValueError):
            impacto_t_str = "—"

        doc.table_row_risk(
            [
                (str(row.get("parcel_id", "—")), 50),
                (perdida_str, 30),
                (impacto_ha_str, 40),
                (impacto_t_str, 40),
                (str(row.get("nivel_riesgo", "—")).upper().replace("_", " "), 20),
            ],
            risk=risk, i=i,
        )

    # ── 4. RIESGOS PRINCIPALES ────────────────────────────────────────────────
    doc.section_title("4. RIESGOS PRINCIPALES DETECTADOS")
    risks = llm_output.get("risks", [])
    if risks:
        for r in risks:
            doc.bullet(str(r))
    else:
        doc.body_text("No se detectaron riesgos criticos bajo las condiciones actuales.")
    doc.pdf.ln(2)

    # ── 5. RECOMENDACIONES GENERALES ────────────────────────────────────────
    recs = llm_output.get("recommendations", {})
    if recs:
        doc.section_title("5. RECOMENDACIONES GENERALES")
        if isinstance(recs, dict):
            for grupo, items in recs.items():
                doc.pdf.set_font("Helvetica", "B", 9)
                doc.pdf.cell(doc.CONTENT_W, 5, _s(grupo.replace("_", " ").title() + ":"), ln=True)
                for item in (items if isinstance(items, list) else [items]):
                    doc.bullet(str(item))
        elif isinstance(recs, list):
            for item in recs:
                doc.bullet(str(item))
        doc.pdf.ln(2)

    # ── 6. ANÁLISIS DETALLADO POR PARCELA ────────────────────────────────────
    doc.add_page()
    doc.section_title("6. ANALISIS DETALLADO POR PARCELA (IA Agronomica)")

    if llm_parcel_outputs:
        for parcel_id, parcel_out in llm_parcel_outputs.items():
            # Siempre leer riesgo/pérdida/impacto desde modeling_df (no del cache LLM)
            mrow = modeling_df[modeling_df["parcel_id"].astype(str) == str(parcel_id)]
            if not mrow.empty:
                risk_level = str(mrow.iloc[0].get("nivel_riesgo", "—"))
                try:
                    perdida_v = float(mrow.iloc[0].get("pct_perdida_pred_pct", 0))
                    impacto_v = float(mrow.iloc[0].get("impacto_eur_ha_pred", 0))
                    header_text = (
                        f"Parcela: {parcel_id}  |  Riesgo: {risk_level.upper().replace('_',' ')}"
                        f"  |  Perdida: {perdida_v:.2f}%  |  Impacto: {impacto_v:.2f} EUR/ha"
                    )
                except (TypeError, ValueError):
                    header_text = f"Parcela: {parcel_id}  |  Riesgo: {risk_level}"
            else:
                risk_level = "—"
                header_text = f"Parcela: {parcel_id}"

            risk_key = _normalize_risk(risk_level)
            doc.subsection_header(header_text, risk=risk_key)

            # Evaluación agronómica
            if parcel_out.get("agronomic_evaluation"):
                doc.labelled_text("1. EVALUACION AGRONOMICA", parcel_out["agronomic_evaluation"])

            # Riesgos detectados
            det_risks = parcel_out.get("detected_risks", [])
            if det_risks:
                doc.pdf.set_font("Helvetica", "B", 9)
                doc.pdf.cell(doc.CONTENT_W, 5, "2. RIESGOS DETECTADOS", ln=True)
                for r in det_risks:
                    doc.bullet(str(r))
                doc.pdf.ln(2)

            # Estimación pérdida
            if parcel_out.get("loss_estimation"):
                doc.labelled_text("3. ESTIMACION DE PERDIDA", parcel_out["loss_estimation"])

            # Impacto económico
            if parcel_out.get("economic_impact"):
                doc.labelled_text("4. IMPACTO ECONOMICO", parcel_out["economic_impact"])

            # Recomendaciones
            p_recs = parcel_out.get("technical_recommendations", [])
            if p_recs:
                doc.pdf.set_font("Helvetica", "B", 9)
                doc.pdf.cell(doc.CONTENT_W, 5, "5. RECOMENDACIONES TECNICAS", ln=True)
                for r in p_recs:
                    doc.bullet(str(r))
                doc.pdf.ln(2)

            # Acción sugerida
            if parcel_out.get("suggested_action"):
                doc.labelled_text("6. ACCION AUTOMATICA SUGERIDA", parcel_out["suggested_action"])

            # Nivel de riesgo
            doc.pdf.set_font("Helvetica", "B", 9)
            doc.pdf.cell(doc.CONTENT_W, 5, "7. NIVEL DE RIESGO", ln=True)
            doc.pdf.set_font("Helvetica", "", 9)
            doc.pdf.cell(doc.CONTENT_W, 5, _s(str(risk_level).replace("_", " ").lower()), ln=True)
            doc.pdf.ln(4)
    else:
        doc.body_text("No hay analisis IA detallado por parcela. Genere los analisis desde la pestana 'IA e Informe'.")

    # ── 7. TABLA COMPLETA DE PREDICCIONES ────────────────────────────────────
    doc.add_page()
    doc.section_title("7. TABLA COMPLETA DE PREDICCIONES")

    if not modeling_df.empty:
        t_cols = [
            ("Parcela", 48), ("Perdida %", 20), ("Riesgo", 22),
            ("EUR/ha", 25), ("EUR total", 25), ("Lluvia 7d", 20), ("Humedad %", 20),
        ]
        data_cols = [
            "parcel_id", "pct_perdida_pred_pct", "nivel_riesgo",
            "impacto_eur_ha_pred", "impacto_total_eur", "rain_7d_mm", "humedad_suelo_%",
        ]
        available = [c for c in data_cols if c in modeling_df.columns]
        display_t_cols = [(lbl, w) for (lbl, w), c in zip(t_cols, data_cols) if c in modeling_df.columns]

        # Ordenar por impacto
        sort_col = next((c for c in ["impacto_total_eur", "pct_perdida_pred_pct"] if c in modeling_df.columns), None)
        sorted_df = modeling_df.sort_values(sort_col, ascending=False).reset_index(drop=True) if sort_col else modeling_df

        doc.table_header(display_t_cols)
        for i, (_, row) in enumerate(sorted_df.iterrows()):
            risk = _normalize_risk(row.get("nivel_riesgo"))
            cells = []
            for col, (_, w) in zip(available, display_t_cols):
                v = row.get(col, "—")
                if isinstance(v, float):
                    v = f"{v:.2f}" if abs(v) < 10000 else f"{v:,.0f}"
                cells.append((_s(str(v)), w))
            doc.table_row_risk(cells, risk=risk, i=i)

    return doc.output()


# ---------------------------------------------------------------------------
# PDF Individual de parcela
# ---------------------------------------------------------------------------

def _build_pdf_parcel(
    client_id: str,
    parcel_id: str,
    parcel_data: dict,
    llm_output: dict,
) -> bytes:
    """
    Construye PDF individual de parcela con:
    1. Ficha de identificación
    2. Datos productivos
    3. Variables ambientales
    4. Resultado del modelo
    5. Análisis agronómico completo (estructura analysis_prompt.txt)
    """
    doc = RainOlivarPDF()
    doc.add_page()

    def fv(key, fmt=".2f", default="No disponible"):
        return _fv(parcel_data, key, fmt, default)

    risk = _normalize_risk(parcel_data.get("nivel_riesgo"))
    perdida_pct = fv("pct_perdida_pred_pct")
    impacto_ha = fv("impacto_eur_ha_pred")

    # ── 1. IDENTIFICACIÓN ────────────────────────────────────────────────────
    doc.section_title(f"FICHA DE PARCELA: {parcel_id}")
    fill = False
    for key, val in [
        ("Parcela", parcel_id),
        ("Cliente", client_id.replace("_", " ").title()),
        ("Superficie (ha)", fv("superficie_ha", ".4f")),
        ("Provincia / Municipio", f"{parcel_data.get('zona_provincia', parcel_data.get('provincia', 'No disponible'))}"),
        ("Uso SIGPAC", parcel_data.get("uso_sigpac", "No disponible")),
    ]:
        doc.kv_row(key, str(val), fill=fill)
        fill = not fill
    doc.pdf.ln(3)

    # ── 2. DATOS PRODUCTIVOS ─────────────────────────────────────────────────
    doc.section_title("2. DATOS PRODUCTIVOS")
    fill = False
    for key, val in [
        ("Tipo de olivar", parcel_data.get("tipo_olivar", "No disponible")),
        ("Riego", parcel_data.get("riego", "No disponible")),
        ("Variedad", parcel_data.get("variedad", "No disponible")),
        ("Estado fenologico", parcel_data.get("estado_fenologico", "No disponible")),
        ("Rendimiento esperado (kg/ha)", fv("rendimiento_esperado_kg_ha", ".0f")),
        ("Precio de mercado (EUR/kg)", fv("precio_mercado_eur_kg", ".3f")),
        ("Coste variable (EUR/ha)", fv("coste_variable_ha", ".0f")),
    ]:
        doc.kv_row(key, str(val), fill=fill)
        fill = not fill
    doc.pdf.ln(3)

    # ── 3. VARIABLES AMBIENTALES ─────────────────────────────────────────────
    doc.section_title("3. VARIABLES AMBIENTALES")

    # Meteorología
    doc.pdf.set_font("Helvetica", "B", 8)
    doc.pdf.cell(doc.CONTENT_W, 5, "Meteorologia:", ln=True)
    fill = False
    for key, val in [
        ("Lluvia 72h (mm)", fv("rain_72h_mm", ".1f")),
        ("Lluvia 7 dias (mm)", fv("rain_7d_mm", ".1f")),
        ("Temperatura media 7d (C)", fv("temp_media_7d", ".1f")),
        ("Humedad del suelo (%)", fv("humedad_suelo_%", ".1f")),
    ]:
        doc.kv_row(key, val, fill=fill)
        fill = not fill

    # Suelo
    doc.pdf.ln(2)
    doc.pdf.set_font("Helvetica", "B", 8)
    doc.pdf.cell(doc.CONTENT_W, 5, "Suelo:", ln=True)
    fill = False
    for key, val in [
        ("Tipo de suelo", parcel_data.get("tipo_suelo", "No disponible")),
        ("Drenaje", parcel_data.get("drenaje", "No disponible")),
        ("Materia organica (%)", fv("materia_organica_%", ".2f")),
        ("Profundidad del suelo (cm)", fv("profundidad_suelo_cm", ".0f")),
    ]:
        doc.kv_row(key, val, fill=fill)
        fill = not fill

    # Topografía/Hidrología
    doc.pdf.ln(2)
    doc.pdf.set_font("Helvetica", "B", 8)
    doc.pdf.cell(doc.CONTENT_W, 5, "Topografia e Hidrologia:", ln=True)
    fill = False
    # Resolver columna de pendiente
    slope_val = parcel_data.get("pendiente_%") or parcel_data.get("pendiente_pct")
    for key, val in [
        ("Pendiente (%)", _fv({"v": slope_val}, "v", ".0f") if slope_val else "No disponible"),
        ("Altitud (m)", fv("altitud_m", ".0f")),
        ("Distancia a cauce (m)", fv("distancia_rio_m", ".0f")),
        ("Encharcamiento estimado (dias)", fv("duracion_encharcamiento_dias", ".1f")),
    ]:
        doc.kv_row(key, val, fill=fill)
        fill = not fill
    doc.pdf.ln(3)

    # ── 4. RESULTADO DEL MODELO ──────────────────────────────────────────────
    doc.section_title("4. RESULTADO DEL MODELO ML")
    risk_label = str(parcel_data.get("nivel_riesgo", "—")).upper().replace("_", " ")
    fill = False
    for key, val in [
        ("Prediccion de riesgo", risk_label),
        ("Perdida predicha (%)", perdida_pct),
        ("Impacto economico (EUR/ha)", impacto_ha),
        ("Impacto economico total (EUR)", fv("impacto_total_eur", ".2f")),
    ]:
        doc.kv_row(key, val, fill=fill)
        fill = not fill
    doc.pdf.ln(3)

    # ── 5. ANÁLISIS AGRONÓMICO IA ─────────────────────────────────────────────
    doc.add_page()
    risk_label_full = str(parcel_data.get("nivel_riesgo", "—")).upper().replace("_", " ")
    try:
        header_txt = (f"Parcela: {parcel_id}  |  Riesgo: {risk_label_full}"
                      f"  |  Perdida: {perdida_pct}%  |  Impacto: {impacto_ha} EUR/ha")
    except Exception:
        header_txt = f"Parcela: {parcel_id}"
    doc.subsection_header(header_txt, risk=risk)

    # 1. Evaluación agronómica
    if llm_output.get("agronomic_evaluation"):
        doc.labelled_text("1. EVALUACION AGRONOMICA", llm_output["agronomic_evaluation"])

    # 2. Riesgos detectados
    det_risks = llm_output.get("detected_risks", [])
    if det_risks:
        doc.pdf.set_font("Helvetica", "B", 9)
        doc.pdf.cell(doc.CONTENT_W, 5, "2. RIESGOS DETECTADOS", ln=True)
        for r in det_risks:
            doc.bullet(str(r))
        doc.pdf.ln(2)

    # 3. Estimación de pérdida
    if llm_output.get("loss_estimation"):
        doc.labelled_text("3. ESTIMACION DE PERDIDA", llm_output["loss_estimation"])

    # 4. Impacto económico
    if llm_output.get("economic_impact"):
        doc.labelled_text("4. IMPACTO ECONOMICO", llm_output["economic_impact"])

    # 5. Recomendaciones técnicas
    recs = llm_output.get("technical_recommendations", [])
    if recs:
        doc.pdf.set_font("Helvetica", "B", 9)
        doc.pdf.cell(doc.CONTENT_W, 5, "5. RECOMENDACIONES TECNICAS", ln=True)
        for r in recs:
            doc.bullet(str(r))
        doc.pdf.ln(2)

    # 6. Acción automática
    if llm_output.get("suggested_action"):
        doc.labelled_text("6. ACCION AUTOMATICA SUGERIDA", llm_output["suggested_action"])

    # 7. Nivel de riesgo
    doc.pdf.set_font("Helvetica", "B", 9)
    doc.pdf.cell(doc.CONTENT_W, 5, "7. NIVEL DE RIESGO", ln=True)
    doc.pdf.set_font("Helvetica", "", 9)
    doc.pdf.cell(doc.CONTENT_W, 5, _s(str(parcel_data.get("nivel_riesgo", "—")).replace("_", " ").lower()), ln=True)

    return doc.output()


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def generate_pdf_report(
    client_id: str,
    mode: str = "general",
    parcel_id: str | None = None,
    modeling_df: pd.DataFrame | None = None,
    parcel_data: dict | None = None,
    llm_output: dict | None = None,
    llm_parcel_outputs: dict | None = None,
) -> bytes:
    """
    Genera informe PDF.

    Args:
        client_id: ID del cliente
        mode: "general" | "parcel"
        parcel_id: ID parcela (mode="parcel")
        modeling_df: DataFrame predicciones + enriquecimiento (mode="general")
        parcel_data: dict con datos de parcela (mode="parcel")
        llm_output: análisis LLM previo
        llm_parcel_outputs: dict {parcel_id: llm_output} para análisis detallado (mode="general")

    Returns:
        bytes del PDF
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if llm_output is None:
        llm_output = {}
    if modeling_df is None:
        modeling_df = pd.DataFrame()

    if mode == "general":
        pdf_bytes = _build_pdf_general(client_id, modeling_df, llm_output, llm_parcel_outputs)
        save_path = REPORTS_DIR / f"{client_id}_report.pdf"
    else:
        pdf_bytes = _build_pdf_parcel(
            client_id,
            parcel_id or "unknown",
            parcel_data or {},
            llm_output,
        )
        safe_pid = str(parcel_id or "unknown").replace("/", "_")
        save_path = REPORTS_DIR / f"{client_id}_{safe_pid}_report.pdf"

    with open(save_path, "wb") as f:
        f.write(pdf_bytes)

    return pdf_bytes
