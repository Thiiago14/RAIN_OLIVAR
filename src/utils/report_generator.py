from fpdf import FPDF


def generate_pdf_report(df, output_path="data/output/informe_olivar.pdf"):
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", size=10)

    # TÍTULO
    pdf.set_font("Arial", style="B", size=14)
    pdf.cell(200, 10, txt="INFORME AGRONÓMICO - OLIVAR", ln=True)

    pdf.ln(5)

    # MÉTRICAS GLOBALES
    impacto_total = df["impacto_eur_ha_pred"].sum()
    impacto_promedio = df["impacto_eur_ha_pred"].mean()

    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, txt=f"Impacto total (€): {impacto_total:.2f}", ln=True)
    pdf.cell(200, 8, txt=f"Impacto promedio (€ / ha): {impacto_promedio:.2f}", ln=True)

    pdf.ln(5)

    # DISTRIBUCIÓN DE RIESGO
    def clasificar(x):
        if x < 0.05:
            return "bajo"
        elif x < 0.15:
            return "medio"
        elif x < 0.30:
            return "alto"
        else:
            return "muy alto"

    df["riesgo"] = df["pct_perdida_pred"].apply(clasificar)
    riesgo_counts = df["riesgo"].value_counts()

    pdf.set_font("Arial", style="B", size=11)
    pdf.cell(200, 8, txt="Distribución de riesgo:", ln=True)

    pdf.set_font("Arial", size=10)
    for nivel, count in riesgo_counts.items():
        pdf.cell(200, 6, txt=f"{nivel}: {count} parcelas", ln=True)

    pdf.ln(5)

    # TOP PARCELAS CRÍTICAS
    pdf.set_font("Arial", style="B", size=11)
    pdf.cell(200, 8, txt="Parcelas más afectadas:", ln=True)

    top = df.sort_values("impacto_eur_ha_pred", ascending=False).head(5)

    pdf.set_font("Arial", size=10)
    for _, row in top.iterrows():
        pdf.cell(
            200,
            6,
            txt=f"{row['parcel_id']} → {row['impacto_eur_ha_pred']:.2f} €",
            ln=True,
        )

    # GUARDAR
    pdf.output(output_path)

    print(f"PDF generado en: {output_path}")