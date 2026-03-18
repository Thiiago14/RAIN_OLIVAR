import os
from datetime import datetime
from fpdf import FPDF

# ---------------------------------------------------------------------------
# Paleta de colores agronomica (RGB)
# ---------------------------------------------------------------------------
C_GREEN_DARK  = (44, 95, 45)      # encabezados principales
C_GREEN_MID   = (82, 140, 84)     # encabezados de secciones
C_GREEN_LIGHT = (198, 224, 180)   # filas de tabla (par)
C_OLIVE       = (107, 142, 35)    # acento
C_WHEAT       = (245, 222, 179)   # fila resaltada / alerta leve
C_RED_SOFT    = (220, 80, 60)     # riesgo muy alto
C_ORANGE      = (210, 120, 30)    # riesgo alto
C_YELLOW      = (200, 170, 20)    # riesgo medio
C_WHITE       = (255, 255, 255)
C_LIGHT_BG    = (248, 250, 245)   # fondo suave de pagina
C_TEXT        = (30, 30, 30)
C_GRAY        = (110, 110, 110)

RISK_COLORS = {
    "bajo":      C_GREEN_MID,
    "medio":     C_YELLOW,
    "alto":      C_ORANGE,
    "muy alto":  C_RED_SOFT,
}


def _l(text: str) -> str:
    """Convierte texto a latin-1 seguro."""
    return str(text).encode("latin-1", errors="replace").decode("latin-1")


def _clasificar_riesgo(x: float) -> str:
    if x < 0.05:
        return "bajo"
    elif x < 0.15:
        return "medio"
    elif x < 0.30:
        return "alto"
    return "muy alto"


# ---------------------------------------------------------------------------
# Clase PDF personalizada
# ---------------------------------------------------------------------------
class AgroPDF(FPDF):
    def __init__(self, title: str = "INFORME AGRONOMICO"):
        super().__init__()
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=20)

    # ---- Header de pagina -------------------------------------------------
    def header(self):
        # Banda verde superior
        self.set_fill_color(*C_GREEN_DARK)
        self.rect(0, 0, 210, 18, "F")

        # Franja decorativa mas clara
        self.set_fill_color(*C_GREEN_MID)
        self.rect(0, 18, 210, 3, "F")

        # Titulo en banda
        self.set_font("Arial", "B", 13)
        self.set_text_color(*C_WHITE)
        self.set_xy(10, 3)
        self.cell(0, 12, _l(self.report_title), ln=False, align="L")

        # Fecha en esquina derecha
        self.set_font("Arial", "", 8)
        fecha = datetime.now().strftime("%d/%m/%Y")
        self.set_xy(140, 6)
        self.cell(60, 8, _l(f"Fecha: {fecha}"), align="R")

        self.set_text_color(*C_TEXT)
        self.ln(10)

    # ---- Footer de pagina -------------------------------------------------
    def footer(self):
        self.set_y(-14)
        self.set_fill_color(*C_GREEN_DARK)
        self.rect(0, self.get_y(), 210, 14, "F")
        self.set_font("Arial", "I", 8)
        self.set_text_color(*C_WHITE)
        self.set_x(10)
        self.cell(0, 14, _l("RAIN-OLIVAR | Informe generado automaticamente por IA Agronomica"), align="L")
        self.set_x(10)
        self.cell(0, 14, _l(f"Pagina {self.page_no()}"), align="R")
        self.set_text_color(*C_TEXT)

    # ---- Titulo de seccion ------------------------------------------------
    def section_title(self, text: str):
        self.ln(4)
        self.set_fill_color(*C_GREEN_MID)
        self.set_text_color(*C_WHITE)
        self.set_font("Arial", "B", 11)
        self.cell(0, 9, _l(f"  {text}"), ln=True, fill=True)
        self.set_text_color(*C_TEXT)
        self.ln(2)

    # ---- Subtitulo de parcela ---------------------------------------------
    def parcel_header(self, parcel_id, riesgo: str, pct: float, impacto: float):
        color = RISK_COLORS.get(riesgo, C_GREEN_MID)
        self.set_fill_color(*color)
        self.set_text_color(*C_WHITE)
        self.set_font("Arial", "B", 10)
        self.cell(
            0, 8,
            _l(f"  Parcela: {parcel_id}   |   Riesgo: {riesgo.upper()}   |"
               f"   Perdida: {pct*100:.1f}%   |   Impacto: {impacto:.2f} EUR/ha"),
            ln=True, fill=True,
        )
        self.set_text_color(*C_TEXT)

    # ---- Texto envuelto (LLM output) --------------------------------------
    def llm_block(self, text: str):
        self.set_fill_color(*C_LIGHT_BG)
        self.set_font("Arial", "", 9)
        self.set_draw_color(*C_OLIVE)
        # Borde izquierdo decorativo
        x0 = self.get_x()
        y0 = self.get_y()
        self.multi_cell(0, 5, _l(text), border=0, fill=True)
        y1 = self.get_y()
        # Linea vertical verde oliva
        self.set_draw_color(*C_OLIVE)
        self.line(x0 - 1, y0, x0 - 1, y1)
        self.ln(3)


# ---------------------------------------------------------------------------
# Helpers de tabla
# ---------------------------------------------------------------------------
def _table_header(pdf: AgroPDF, cols: list, widths: list):
    pdf.set_fill_color(*C_GREEN_DARK)
    pdf.set_text_color(*C_WHITE)
    pdf.set_font("Arial", "B", 9)
    for col, w in zip(cols, widths):
        pdf.cell(w, 7, _l(col), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(*C_TEXT)


def _table_row(pdf: AgroPDF, values: list, widths: list, fill: bool = False, fill_color=None):
    if fill_color:
        pdf.set_fill_color(*fill_color)
    elif fill:
        pdf.set_fill_color(*C_GREEN_LIGHT)
    else:
        pdf.set_fill_color(*C_WHITE)
    pdf.set_font("Arial", "", 9)
    for val, w in zip(values, widths):
        pdf.cell(w, 6, _l(val), border=1, align="C", fill=True)
    pdf.ln()


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------
def generate_pdf_report(
    df,
    llm_results: list[dict] | None = None,
    output_path: str = "data/output/informe_olivar.pdf",
):
    """
    Genera un informe PDF agronómico.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame con columnas parcel_id, pct_perdida_pred, impacto_eur_ha_pred.
    llm_results : list[dict], opcional
        Lista de dicts con claves 'parcel_id' y 'analysis' (texto del LLM).
    output_path : str
        Ruta de salida del PDF.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    df = df.copy()
    df["riesgo"] = df["pct_perdida_pred"].apply(_clasificar_riesgo)

    llm_map: dict[str, str] = {}
    if llm_results:
        for item in llm_results:
            llm_map[str(item["parcel_id"])] = item["analysis"]

    pdf = AgroPDF(title="INFORME AGRONOMICO - OLIVAR  |  RAIN-OLIVAR")
    pdf.add_page()

    # ------------------------------------------------------------------
    # 1. RESUMEN EJECUTIVO
    # ------------------------------------------------------------------
    pdf.section_title("1. RESUMEN EJECUTIVO")

    impacto_total    = df["impacto_eur_ha_pred"].sum()
    impacto_promedio = df["impacto_eur_ha_pred"].mean()
    impacto_max      = df["impacto_eur_ha_pred"].max()
    n_parcelas       = len(df)
    pct_media        = df["pct_perdida_pred"].mean()

    metricas = [
        ("Total parcelas analizadas",        str(n_parcelas)),
        ("Impacto total estimado (EUR)",      f"{impacto_total:.2f}"),
        ("Impacto promedio (EUR/ha)",         f"{impacto_promedio:.2f}"),
        ("Impacto maximo (EUR/ha)",           f"{impacto_max:.2f}"),
        ("Porcentaje de perdida medio",       f"{pct_media*100:.1f} %"),
    ]

    pdf.set_font("Arial", "", 9)
    for i, (label, valor) in enumerate(metricas):
        fill = i % 2 == 0
        pdf.set_fill_color(*(C_GREEN_LIGHT if fill else C_WHITE))
        pdf.cell(110, 7, _l(f"  {label}"), border="LRB", fill=True)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(70, 7, _l(valor), border="LRB", fill=True, align="C")
        pdf.set_font("Arial", "", 9)
        pdf.ln()

    pdf.ln(3)

    # ------------------------------------------------------------------
    # 2. DISTRIBUCION DE RIESGO
    # ------------------------------------------------------------------
    pdf.section_title("2. DISTRIBUCION DE RIESGO POR PERDIDA")

    riesgo_counts = df["riesgo"].value_counts()
    total = riesgo_counts.sum()

    _table_header(pdf, ["Nivel de Riesgo", "N. Parcelas", "% del Total", "Umbral (pct_perdida)"], [50, 40, 45, 55])

    umbrales = {
        "bajo":     "< 5 %",
        "medio":    "5 % - 15 %",
        "alto":     "15 % - 30 %",
        "muy alto": "> 30 %",
    }
    orden = ["bajo", "medio", "alto", "muy alto"]
    for i, nivel in enumerate(orden):
        count = riesgo_counts.get(nivel, 0)
        pct   = count / total * 100 if total else 0
        color = RISK_COLORS.get(nivel)
        _table_row(
            pdf,
            [nivel.upper(), str(count), f"{pct:.1f} %", umbrales[nivel]],
            [50, 40, 45, 55],
            fill_color=(*color, ) if color else None,
        )

    pdf.ln(3)

    # ------------------------------------------------------------------
    # 3. TOP PARCELAS CRITICAS
    # ------------------------------------------------------------------
    pdf.section_title("3. TOP 10 PARCELAS MAS AFECTADAS")

    top = df.sort_values("impacto_eur_ha_pred", ascending=False).head(10)

    _table_header(
        pdf,
        ["Parcela", "Perdida (%)", "Impacto (EUR/ha)", "Nivel de Riesgo"],
        [45, 45, 55, 45],
    )
    for i, (_, row) in enumerate(top.iterrows()):
        nivel  = row["riesgo"]
        color  = RISK_COLORS.get(nivel, C_WHITE)
        _table_row(
            pdf,
            [
                str(row["parcel_id"]),
                f"{row['pct_perdida_pred']*100:.1f} %",
                f"{row['impacto_eur_ha_pred']:.2f}",
                nivel.upper(),
            ],
            [45, 45, 55, 45],
            fill_color=color if i % 2 == 0 else None,
        )

    pdf.ln(3)

    # ------------------------------------------------------------------
    # 4. ANALISIS POR PARCELA (LLM)
    # ------------------------------------------------------------------
    if llm_map:
        pdf.section_title("4. ANALISIS DETALLADO POR PARCELA (IA Agronomica)")

        df_sorted = df.sort_values("impacto_eur_ha_pred", ascending=False)

        for _, row in df_sorted.iterrows():
            pid    = str(row["parcel_id"])
            riesgo = row["riesgo"]
            pct    = row["pct_perdida_pred"]
            imp    = row["impacto_eur_ha_pred"]
            texto  = llm_map.get(pid, "(Sin analisis disponible)")

            pdf.parcel_header(pid, riesgo, pct, imp)
            pdf.llm_block(texto)

    # ------------------------------------------------------------------
    # GUARDAR
    # ------------------------------------------------------------------
    pdf.output(output_path)
    print(f"PDF generado en: {output_path}")
