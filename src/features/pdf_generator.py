"""
PDF report generation for RAIN-OLIVAR.

The general report keeps the current visual language, but restores the full
content sequence from the previous complete report:
summary, risk distribution, top parcels, general risks, recommendations,
parcel-by-parcel agronomic analysis, and the full prediction table.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fpdf import FPDF

REPORTS_DIR = Path("data/reports")

# RAIN-OLIVAR palette
C_HEADER_BG = (45, 80, 22)
C_SECTION_BG = (74, 124, 89)
C_SECTION_TXT = (255, 255, 255)
C_TEXT = (30, 58, 47)
C_SUBTEXT = (100, 130, 100)
C_ROW_ALT = (240, 248, 240)

RISK_COLORS = {
    "bajo": (76, 175, 80),
    "medio": (255, 193, 7),
    "alto": (255, 152, 0),
    "muy_alto": (244, 67, 54),
}
RISK_TEXT_COLORS = {
    "bajo": (255, 255, 255),
    "medio": (50, 50, 50),
    "alto": (255, 255, 255),
    "muy_alto": (255, 255, 255),
}


def _s(text: Any) -> str:
    """Sanitize text for FPDF core fonts."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        "€": "EUR",
        "º": " grados",
        "°": " grados",
        "–": "-",
        "—": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "\u2022": "-",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _normalize_risk(val: Any) -> str:
    if val is None:
        return "sin_dato"
    risk = str(val).lower().strip().replace(" ", "_").replace("-", "_")
    return risk if risk in RISK_COLORS else "sin_dato"


def _to_float(val: Any, default: float | None = None) -> float | None:
    try:
        parsed = pd.to_numeric(val, errors="coerce")
        if pd.isna(parsed):
            return default
        return float(parsed)
    except (TypeError, ValueError):
        return default


def _fmt(val: Any, decimals: int = 2, default: str = "No disponible") -> str:
    num = _to_float(val)
    if num is None:
        return default
    return f"{num:,.{decimals}f}"


def _value(row: pd.Series | dict, keys: str | list[str], default: Any = None) -> Any:
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        if key in row:
            val = row.get(key)
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val
    return default


def _clean_record(row: pd.Series | dict) -> dict:
    data = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    clean = {}
    for key, val in data.items():
        if hasattr(val, "item"):
            val = val.item()
        if isinstance(val, float) and pd.isna(val):
            val = None
        clean[key] = val
    return clean


def _risk_distribution(df: pd.DataFrame) -> list[dict]:
    n = len(df)
    rows = []
    thresholds = [
        ("bajo", "BAJO", "<5%"),
        ("medio", "MEDIO", "5-15%"),
        ("alto", "ALTO", "15-30%"),
        ("muy_alto", "MUY ALTO", ">30%"),
    ]
    for key, label, threshold in thresholds:
        count = int((df["nivel_riesgo"].astype(str).str.lower() == key).sum()) if "nivel_riesgo" in df else 0
        rows.append({
            "nivel": key,
            "label": label,
            "count": count,
            "pct": f"{100 * count / n:.1f}%" if n else "0.0%",
            "umbral": threshold,
        })
    return rows


def _sort_parcels(df: pd.DataFrame, max_parcels: int | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    sort_cols = [c for c in ["impacto_total_eur", "pct_perdida_pred_pct"] if c in df.columns]
    ordered = df.copy()
    if sort_cols:
        ordered = ordered.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")
    ordered = ordered.reset_index(drop=True)
    if max_parcels is not None:
        return ordered.head(max_parcels)
    return ordered


class _RainFpdf(FPDF):
    def header(self):
        self.set_fill_color(*C_HEADER_BG)
        self.rect(0, 0, 210, 16, "F")
        self.set_xy(15, 4)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(255, 255, 255)
        self.cell(130, 8, "INFORME AGRONOMICO - OLIVAR  |  RAIN-OLIVAR", ln=False)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 8, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align="R")
        self.set_y(20)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*C_SUBTEXT)
        self.cell(0, 5, "RAIN-OLIVAR | Informe generado automaticamente por IA Agronomica", ln=False)
        self.cell(0, 5, f"Pagina {self.page_no()}", ln=True, align="R")


class RainOlivarPDF:
    PAGE_W = 210
    PAGE_H = 297
    MARGIN = 15
    CONTENT_W = PAGE_W - 2 * MARGIN
    FOOTER_MARGIN = 20

    def __init__(self):
        self.pdf = _RainFpdf()
        self.pdf.set_auto_page_break(auto=True, margin=self.FOOTER_MARGIN)
        self.pdf.set_margins(self.MARGIN, self.MARGIN, self.MARGIN)
        if hasattr(self.pdf, "set_compression"):
            self.pdf.set_compression(False)
        self.pdf.alias_nb_pages()

    def add_page(self):
        self.pdf.add_page()

    def ensure_space(self, height_needed: float):
        if self.pdf.page_no() == 0:
            self.add_page()
        trigger = getattr(self.pdf, "page_break_trigger", self.PAGE_H - self.FOOTER_MARGIN)
        if self.pdf.get_y() + height_needed > trigger:
            self.add_page()

    def section_title(self, text: str):
        self.ensure_space(16)
        p = self.pdf
        p.ln(4)
        p.set_fill_color(*C_SECTION_BG)
        p.set_text_color(*C_SECTION_TXT)
        p.set_font("Helvetica", "B", 10)
        p.cell(self.CONTENT_W, 8, _s(f"  {text}"), fill=True, ln=True)
        p.set_text_color(*C_TEXT)
        p.ln(2)

    def cover(self, client_id: str):
        p = self.pdf
        self.ensure_space(50)
        p.ln(8)
        p.set_text_color(*C_TEXT)
        p.set_font("Helvetica", "B", 28)
        p.cell(0, 14, "RAIN-OLIVAR", ln=True, align="C")
        p.set_font("Helvetica", "", 13)
        p.cell(0, 8, "Informe agronomico de riesgo en olivar", ln=True, align="C")
        p.ln(6)
        p.set_fill_color(240, 248, 240)
        p.set_font("Helvetica", "B", 10)
        p.cell(50, 8, "Cliente", border=1, fill=True)
        p.set_font("Helvetica", "", 10)
        p.cell(0, 8, _s(client_id.replace("_", " ").title()), border=1, ln=True)
        p.set_font("Helvetica", "B", 10)
        p.cell(50, 8, "Fecha", border=1, fill=True)
        p.set_font("Helvetica", "", 10)
        p.cell(0, 8, datetime.now().strftime("%d/%m/%Y"), border=1, ln=True)
        p.ln(8)

    def subsection_header(self, text: str, risk: str | None = None):
        self.ensure_space(14)
        p = self.pdf
        p.ln(3)
        risk_key = _normalize_risk(risk)
        bg = RISK_COLORS.get(risk_key, (180, 180, 180))
        fg = RISK_TEXT_COLORS.get(risk_key, (255, 255, 255))
        p.set_fill_color(*bg)
        p.set_text_color(*fg)
        p.set_font("Helvetica", "B", 8)
        p.cell(self.CONTENT_W, 7, _s(f"  {text}"), fill=True, ln=True)
        p.set_text_color(*C_TEXT)
        p.ln(1)

    def body_text(self, text: str, indent: int = 0):
        if not str(text or "").strip():
            text = "No disponible."
        self.ensure_space(12)
        p = self.pdf
        p.set_font("Helvetica", "", 9)
        p.set_text_color(*C_TEXT)
        p.set_x(self.MARGIN + indent)
        p.multi_cell(self.CONTENT_W - indent, 5, _s(text))
        p.set_x(self.MARGIN)
        p.ln(1)

    def bullet(self, text: str):
        self.ensure_space(8)
        p = self.pdf
        p.set_font("Helvetica", "", 9)
        p.set_text_color(*C_TEXT)
        p.set_x(self.MARGIN + 4)
        p.multi_cell(self.CONTENT_W - 4, 5, _s(f"- {text}"))
        p.set_x(self.MARGIN)

    def kv_row(self, key: str, val: Any, fill: bool = False):
        self.ensure_space(7)
        p = self.pdf
        p.set_fill_color(*(C_ROW_ALT if fill else (255, 255, 255)))
        p.set_font("Helvetica", "", 9)
        p.set_text_color(*C_TEXT)
        p.cell(80, 6, _s(key), border=1, fill=fill)
        p.set_font("Helvetica", "B", 9)
        p.cell(self.CONTENT_W - 80, 6, _s(val), border=1, fill=fill, ln=True)

    def table_header(self, cols: list[tuple[str, float]]):
        self.ensure_space(12)
        p = self.pdf
        p.set_fill_color(*C_SECTION_BG)
        p.set_text_color(255, 255, 255)
        p.set_font("Helvetica", "B", 8)
        for label, width in cols:
            p.cell(width, 7, _s(label), border=1, fill=True, align="C")
        p.ln()
        p.set_text_color(*C_TEXT)

    def table_row(self, cells: list[tuple[Any, float]], i: int = 0, risk: str | None = None):
        self.ensure_space(7)
        p = self.pdf
        risk_key = _normalize_risk(risk)
        if risk_key in RISK_COLORS:
            p.set_fill_color(*RISK_COLORS[risk_key])
            p.set_text_color(*RISK_TEXT_COLORS[risk_key])
        else:
            p.set_fill_color(*(C_ROW_ALT if i % 2 == 0 else (255, 255, 255)))
            p.set_text_color(*C_TEXT)
        p.set_font("Helvetica", "", 8)
        for val, width in cells:
            p.cell(width, 6, _s(val), border=1, fill=True, align="C")
        p.ln()
        p.set_text_color(*C_TEXT)

    def label(self, text: str):
        self.ensure_space(8)
        self.pdf.set_font("Helvetica", "B", 9)
        self.pdf.set_text_color(*C_TEXT)
        self.pdf.cell(0, 5, _s(text), ln=True)

    def labelled_text(self, label: str, text: str):
        self.label(label)
        self.body_text(text)

    def output(self) -> bytes:
        out = self.pdf.output(dest="S")
        if isinstance(out, str):
            return out.encode("latin-1")
        return bytes(out)


def _build_real_parcel_sections(row: pd.Series, parcel_out: dict | None) -> dict:
    parcel_out = parcel_out or {}
    parcel_id = _value(row, "parcel_id", "sin_id")
    risk = str(_value(row, "nivel_riesgo", "sin dato")).replace("_", " ").lower()
    loss = _fmt(_value(row, "pct_perdida_pred_pct"), 2, "No disponible")
    impact_ha = _fmt(_value(row, "impacto_eur_ha_pred"), 2, "No disponible")
    impact_total = _fmt(_value(row, "impacto_total_eur"), 2, "No disponible")
    yield_kg = _fmt(_value(row, "rendimiento_esperado_kg_ha"), 0, "No disponible")
    price = _fmt(_value(row, "precio_mercado_eur_kg"), 3, "No disponible")
    rain = _fmt(_value(row, "rain_7d_mm"), 1, "No disponible")
    humidity = _fmt(_value(row, "humedad_suelo_%"), 1, "No disponible")
    slope = _fmt(_value(row, ["pendiente_%", "pendiente_pct"]), 1, "No disponible")
    flooding = _fmt(_value(row, "duracion_encharcamiento_dias"), 1, "No disponible")
    drainage = _value(row, "drenaje", "No disponible")
    variety = _value(row, "variedad", "No disponible")
    olive_type = _value(row, "tipo_olivar", "No disponible")

    evaluation = (
        f"La parcela {parcel_id} presenta riesgo {risk}.\n"
        f"Perdida actual: {loss}%\n"
        f"Impacto actual: {impact_ha} EUR/ha\n"
        f"Impacto total actual: {impact_total} EUR\n"
        f"Rendimiento esperado: {yield_kg} kg/ha\n"
        f"Precio de mercado: {price} EUR/kg\n"
        f"Lluvia 7d: {rain} mm\n"
        f"Humedad del suelo: {humidity}%\n"
        f"Pendiente: {slope}%\n"
        f"Encharcamiento estimado: {flooding} dias\n"
        f"El manejo corresponde a olivar {olive_type} de variedad {variety}, con drenaje {drainage}."
    )
    loss_text = (
        f"El modelo estima una perdida del {loss}% para esta parcela.\n"
        f"Rendimiento usado: {yield_kg} kg/ha\n"
        f"Precio usado: {price} EUR/kg\n"
        f"Impacto resultante: {impact_ha} EUR/ha"
    )
    economic = (
        f"Impacto total actual: {impact_total} EUR\n"
        f"Impacto unitario actual: {impact_ha} EUR/ha\n"
        "Estos importes se calculan desde la fila real de prediccion y la superficie disponible."
    )

    risks = parcel_out.get("detected_risks") or []
    if not isinstance(risks, list):
        risks = [risks]
    if not risks:
        risks = ["No se detectaron riesgos especificos adicionales en el analisis disponible."]

    recs = parcel_out.get("technical_recommendations") or []
    if not isinstance(recs, list):
        recs = [recs]
    if not recs:
        recs = ["Mantener seguimiento agronomico y actualizar la prediccion tras cambios climaticos relevantes."]

    action = parcel_out.get("suggested_action") or "Mantener seguimiento tecnico y revisar la parcela si cambian las condiciones."

    return {
        "evaluation": evaluation,
        "risks": risks,
        "loss": loss_text,
        "economic": economic,
        "recommendations": recs,
        "action": action,
        "risk": risk,
    }


def _ensure_general_output(client_id: str, modeling_df: pd.DataFrame, llm_output: dict | None) -> dict:
    if llm_output and (llm_output.get("summary") or llm_output.get("risks") or llm_output.get("recommendations")):
        return llm_output
    from src.features.llm_engine import generate_general_analysis, load_llm_output

    saved = load_llm_output(client_id, None)
    if saved:
        return saved
    try:
        return generate_general_analysis(client_id, modeling_df)
    except PermissionError:
        from src.features.llm_engine import _rule_based_general_analysis

        result = _rule_based_general_analysis(modeling_df)
        return {
            "client_id": client_id,
            "parcel_id": None,
            "mode": "general",
            "summary": result.get("resumen_ejecutivo", ""),
            "risks": result.get("riesgos_principales", []),
            "recommendations": result.get("recomendaciones", {}),
            "priority_parcels": result.get("parcelas_prioritarias", []),
            "report_sections": result,
            "source": "rules_no_cache",
        }


def _render_recommendations(doc: RainOlivarPDF, recs: Any):
    labels = [
        ("corto_plazo", "Corto plazo"),
        ("medio_plazo", "Medio plazo"),
        ("seguimiento", "Seguimiento"),
    ]
    if isinstance(recs, dict):
        for key, title in labels:
            items = recs.get(key, [])
            if not isinstance(items, list):
                items = [items]
            doc.ensure_space(14)
            doc.label(f"{title}:")
            for item in items:
                if str(item).strip():
                    doc.bullet(item)
        extra_keys = [k for k in recs.keys() if k not in {k for k, _ in labels}]
        for key in extra_keys:
            items = recs.get(key, [])
            if not isinstance(items, list):
                items = [items]
            doc.label(f"{str(key).replace('_', ' ').title()}:")
            for item in items:
                doc.bullet(item)
    elif isinstance(recs, list):
        for item in recs:
            doc.bullet(item)
    elif recs:
        doc.body_text(str(recs))
    else:
        doc.body_text("No hay recomendaciones generales disponibles.")


def get_pdf_report_path(client_id: str, mode: str = "general", parcel_id: str | None = None) -> Path:
    if mode == "general":
        return REPORTS_DIR / f"{client_id}_report.pdf"
    safe_pid = str(parcel_id or "unknown").replace("/", "_")
    return REPORTS_DIR / f"{client_id}_{safe_pid}_report.pdf"


def count_pdf_detail_blocks(pdf_bytes: bytes, client_id: str) -> int:
    text = pdf_bytes.decode("latin-1", errors="ignore")
    return text.count(f"Parcela: {client_id}_")


def validate_general_pdf(pdf_bytes: bytes, client_id: str, expected_parcels: int) -> int:
    detailed_count = count_pdf_detail_blocks(pdf_bytes, client_id)
    if detailed_count != expected_parcels:
        raise ValueError(
            f"PDF general incompleto: analisis detallado {detailed_count}/{expected_parcels} parcelas."
        )
    return detailed_count


def _build_pdf_general(
    client_id: str,
    modeling_df: pd.DataFrame,
    llm_output: dict | None,
    llm_parcel_outputs: dict | None = None,
    max_parcels: int | None = None,
) -> bytes:
    doc = RainOlivarPDF()
    doc.add_page()
    llm_output = _ensure_general_output(client_id, modeling_df, llm_output or {})

    n = len(modeling_df) if modeling_df is not None and not modeling_df.empty else 0
    perdida_media = _to_float(modeling_df["pct_perdida_pred_pct"].mean(), 0) if n and "pct_perdida_pred_pct" in modeling_df else 0
    perdida_max = _to_float(modeling_df["pct_perdida_pred_pct"].max(), 0) if n and "pct_perdida_pred_pct" in modeling_df else 0
    impacto_total = _to_float(modeling_df["impacto_total_eur"].sum(), 0) if n and "impacto_total_eur" in modeling_df else 0
    impacto_medio = _to_float(modeling_df["impacto_eur_ha_pred"].mean(), 0) if n and "impacto_eur_ha_pred" in modeling_df else 0
    n_alto = int(modeling_df["nivel_riesgo"].isin(["alto", "muy_alto"]).sum()) if n and "nivel_riesgo" in modeling_df else 0
    if n and "impacto_total_eur" in modeling_df:
        parcela_critica = str(modeling_df.loc[modeling_df["impacto_total_eur"].idxmax(), "parcel_id"])
    else:
        parcela_critica = "No disponible"

    doc.cover(client_id)

    doc.section_title("1. RESUMEN EJECUTIVO")
    kpis = [
        ("Total parcelas analizadas", n),
        ("Impacto total estimado (EUR)", f"{impacto_total:,.2f}"),
        ("Impacto promedio (EUR/ha)", f"{impacto_medio:,.2f}"),
        ("Perdida maxima (%)", f"{perdida_max:.2f}%"),
        ("Perdida media (%)", f"{perdida_media:.2f}%"),
        ("Parcelas en riesgo alto/muy alto", n_alto),
        ("Parcela critica", parcela_critica),
    ]
    for i, (key, val) in enumerate(kpis):
        doc.kv_row(key, val, fill=i % 2 == 1)
    doc.pdf.ln(4)
    doc.body_text(llm_output.get("summary") or "No hay resumen ejecutivo disponible.")

    doc.section_title("2. DISTRIBUCION DE RIESGO POR PERDIDA")
    risk_cols = [("Nivel de riesgo", 45), ("Numero parcelas", 35), ("% del total", 50), ("Umbral", 50)]
    doc.table_header(risk_cols)
    for i, row in enumerate(_risk_distribution(modeling_df)):
        doc.table_row(
            [(row["label"], 45), (row["count"], 35), (row["pct"], 50), (row["umbral"], 50)],
            i=i,
            risk=row["nivel"],
        )

    doc.section_title("3. TOP PARCELAS MAS AFECTADAS")
    top_cols = [("Parcela", 50), ("Perdida %", 30), ("EUR/ha", 35), ("EUR total", 40), ("Riesgo", 25)]
    doc.table_header(top_cols)
    top_df = _sort_parcels(modeling_df, 10)
    for i, (_, row) in enumerate(top_df.iterrows()):
        risk = _normalize_risk(row.get("nivel_riesgo"))
        doc.table_row(
            [
                (row.get("parcel_id", "No disponible"), 50),
                (_fmt(row.get("pct_perdida_pred_pct"), 2, "-"), 30),
                (_fmt(row.get("impacto_eur_ha_pred"), 2, "-"), 35),
                (_fmt(row.get("impacto_total_eur"), 2, "-"), 40),
                (str(row.get("nivel_riesgo", "-")).upper().replace("_", " "), 25),
            ],
            i=i,
            risk=risk,
        )

    doc.section_title("4. RIESGOS PRINCIPALES DETECTADOS")
    risks = llm_output.get("risks") or []
    if not isinstance(risks, list):
        risks = [risks]
    if risks:
        for risk in risks:
            doc.bullet(risk)
    else:
        doc.body_text("No se detectaron riesgos agregados bajo las condiciones actuales.")

    doc.section_title("5. RECOMENDACIONES GENERALES")
    _render_recommendations(doc, llm_output.get("recommendations"))

    doc.add_page()
    doc.section_title("6. ANALISIS DETALLADO POR PARCELA (IA AGRONOMICA)")
    parcel_rows = _sort_parcels(modeling_df, max_parcels)

    if parcel_rows.empty:
        doc.body_text("No hay parcelas disponibles para el analisis detallado.")
    for _, row in parcel_rows.iterrows():
        parcel_id = str(row.get("parcel_id", "sin_id"))
        risk_level = str(row.get("nivel_riesgo", "sin dato"))
        header = (
            f"Parcela: {parcel_id} | Riesgo: {risk_level.upper().replace('_', ' ')} | "
            f"Perdida: {_fmt(row.get('pct_perdida_pred_pct'), 2, '-')}% | "
            f"Impacto: {_fmt(row.get('impacto_eur_ha_pred'), 2, '-')} EUR/ha"
        )
        doc.subsection_header(header, risk=risk_level)
        sections = _build_real_parcel_sections(row, None)
        doc.labelled_text("1. EVALUACION AGRONOMICA", sections["evaluation"])
        doc.label("2. RIESGOS DETECTADOS")
        for item in sections["risks"]:
            doc.bullet(item)
        doc.labelled_text("3. ESTIMACION DE PERDIDA", sections["loss"])
        doc.labelled_text("4. IMPACTO ECONOMICO", sections["economic"])
        doc.label("5. RECOMENDACIONES TECNICAS")
        for item in sections["recommendations"]:
            doc.bullet(item)
        doc.labelled_text("6. ACCION AUTOMATICA SUGERIDA", sections["action"])
        doc.labelled_text("7. NIVEL DE RIESGO", sections["risk"])
        doc.pdf.ln(3)

    doc.add_page()
    doc.section_title("7. TABLA COMPLETA DE PREDICCIONES")
    table_cols = [
        ("Parcela", 44),
        ("Perdida %", 22),
        ("Riesgo", 24),
        ("EUR/ha", 24),
        ("EUR total", 26),
        ("Lluvia 7d", 20),
        ("Humedad %", 20),
    ]
    table_data = [
        ("parcel_id", 44, None),
        ("pct_perdida_pred_pct", 22, 2),
        ("nivel_riesgo", 24, None),
        ("impacto_eur_ha_pred", 24, 2),
        ("impacto_total_eur", 26, 2),
        ("rain_7d_mm", 20, 1),
        ("humedad_suelo_%", 20, 1),
    ]
    available = [(col, width, decimals) for col, width, decimals in table_data if col in modeling_df.columns]
    visible_cols = [(label, width) for (label, width), (col, _, _) in zip(table_cols, table_data) if col in modeling_df.columns]
    if available:
        doc.table_header(visible_cols)
        sorted_df = _sort_parcels(modeling_df)
        for i, (_, row) in enumerate(sorted_df.iterrows()):
            if doc.pdf.get_y() + 7 > getattr(doc.pdf, "page_break_trigger", 277):
                doc.add_page()
                doc.table_header(visible_cols)
            cells = []
            for col, width, decimals in available:
                val = row.get(col)
                if decimals is not None:
                    val = _fmt(val, decimals, "-")
                elif col == "nivel_riesgo":
                    val = str(val).replace("_", " ").upper()
                cells.append((val, width))
            doc.table_row(cells, i=i, risk=row.get("nivel_riesgo"))
    else:
        doc.body_text("No hay columnas de prediccion disponibles.")

    return doc.output()


def _build_pdf_parcel(
    client_id: str,
    parcel_id: str,
    parcel_data: dict,
    llm_output: dict,
) -> bytes:
    doc = RainOlivarPDF()
    doc.add_page()

    risk = _normalize_risk(parcel_data.get("nivel_riesgo"))
    perdida_pct = _fmt(parcel_data.get("pct_perdida_pred_pct"), 2)
    impacto_ha = _fmt(parcel_data.get("impacto_eur_ha_pred"), 2)

    doc.section_title(f"FICHA DE PARCELA: {parcel_id}")
    for i, (key, val) in enumerate([
        ("Parcela", parcel_id),
        ("Cliente", client_id.replace("_", " ").title()),
        ("Superficie (ha)", _fmt(parcel_data.get("superficie_ha"), 4)),
        ("Provincia / Municipio", parcel_data.get("zona_provincia", parcel_data.get("provincia", "No disponible"))),
        ("Uso SIGPAC", parcel_data.get("uso_sigpac", "No disponible")),
    ]):
        doc.kv_row(key, val, fill=i % 2 == 1)

    doc.section_title("2. DATOS PRODUCTIVOS")
    for i, (key, val) in enumerate([
        ("Tipo de olivar", parcel_data.get("tipo_olivar", "No disponible")),
        ("Riego", parcel_data.get("riego", "No disponible")),
        ("Variedad", parcel_data.get("variedad", "No disponible")),
        ("Estado fenologico", parcel_data.get("estado_fenologico", "No disponible")),
        ("Rendimiento esperado (kg/ha)", _fmt(parcel_data.get("rendimiento_esperado_kg_ha"), 0)),
        ("Precio de mercado (EUR/kg)", _fmt(parcel_data.get("precio_mercado_eur_kg"), 3)),
        ("Coste variable (EUR/ha)", _fmt(parcel_data.get("coste_variable_ha"), 0)),
    ]):
        doc.kv_row(key, val, fill=i % 2 == 1)

    doc.section_title("3. VARIABLES AMBIENTALES")
    for i, (key, val) in enumerate([
        ("Lluvia 72h (mm)", _fmt(parcel_data.get("rain_72h_mm"), 1)),
        ("Lluvia 7 dias (mm)", _fmt(parcel_data.get("rain_7d_mm"), 1)),
        ("Temperatura media 7d (C)", _fmt(parcel_data.get("temp_media_7d"), 1)),
        ("Humedad del suelo (%)", _fmt(parcel_data.get("humedad_suelo_%"), 1)),
        ("Tipo de suelo", parcel_data.get("tipo_suelo", "No disponible")),
        ("Drenaje", parcel_data.get("drenaje", "No disponible")),
        ("Materia organica (%)", _fmt(parcel_data.get("materia_organica_%"), 2)),
        ("Pendiente (%)", _fmt(_value(parcel_data, ["pendiente_%", "pendiente_pct"]), 1)),
        ("Encharcamiento estimado (dias)", _fmt(parcel_data.get("duracion_encharcamiento_dias"), 1)),
    ]):
        doc.kv_row(key, val, fill=i % 2 == 1)

    doc.section_title("4. RESULTADO DEL MODELO ML")
    for i, (key, val) in enumerate([
        ("Prediccion de riesgo", str(parcel_data.get("nivel_riesgo", "No disponible")).upper().replace("_", " ")),
        ("Perdida predicha (%)", perdida_pct),
        ("Impacto economico (EUR/ha)", impacto_ha),
        ("Impacto economico total (EUR)", _fmt(parcel_data.get("impacto_total_eur"), 2)),
    ]):
        doc.kv_row(key, val, fill=i % 2 == 1)

    doc.add_page()
    header = (
        f"Parcela: {parcel_id} | Riesgo: {str(parcel_data.get('nivel_riesgo', '-')).upper().replace('_', ' ')} | "
        f"Perdida: {perdida_pct}% | Impacto: {impacto_ha} EUR/ha"
    )
    doc.subsection_header(header, risk=risk)

    row = pd.Series(parcel_data)
    sections = _build_real_parcel_sections(row, llm_output)
    doc.labelled_text("1. EVALUACION AGRONOMICA", sections["evaluation"])
    doc.label("2. RIESGOS DETECTADOS")
    for item in sections["risks"]:
        doc.bullet(item)
    doc.labelled_text("3. ESTIMACION DE PERDIDA", sections["loss"])
    doc.labelled_text("4. IMPACTO ECONOMICO", sections["economic"])
    doc.label("5. RECOMENDACIONES TECNICAS")
    for item in sections["recommendations"]:
        doc.bullet(item)
    doc.labelled_text("6. ACCION AUTOMATICA SUGERIDA", sections["action"])
    doc.labelled_text("7. NIVEL DE RIESGO", sections["risk"])

    return doc.output()


def generate_pdf_report(
    client_id: str,
    mode: str = "general",
    parcel_id: str | None = None,
    modeling_df: pd.DataFrame | None = None,
    parcel_data: dict | None = None,
    llm_output: dict | None = None,
    llm_parcel_outputs: dict | None = None,
    max_parcels: int | None = None,
) -> bytes:
    """
    Generate and save a PDF report.

    For the general report, max_parcels defaults to None so every parcel from
    modeling_df is included in the detailed agronomic section.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if modeling_df is None:
        modeling_df = pd.DataFrame()

    if mode == "general":
        expected_parcels = len(modeling_df)
        pdf_bytes = _build_pdf_general(
            client_id=client_id,
            modeling_df=modeling_df,
            llm_output=llm_output or {},
            llm_parcel_outputs=llm_parcel_outputs,
            max_parcels=max_parcels,
        )
        validate_general_pdf(pdf_bytes, client_id, expected_parcels)
        save_path = get_pdf_report_path(client_id, mode="general")
    else:
        pdf_bytes = _build_pdf_parcel(
            client_id=client_id,
            parcel_id=parcel_id or "unknown",
            parcel_data=parcel_data or {},
            llm_output=llm_output or {},
        )
        save_path = get_pdf_report_path(client_id, mode="parcel", parcel_id=parcel_id)

    if save_path.exists():
        save_path.unlink()
    with open(save_path, "wb") as f:
        f.write(pdf_bytes)

    return pdf_bytes
