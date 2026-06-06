"""
Motor LLM para análisis agronómico de parcelas.
Usa la API de Anthropic (claude-haiku) para generar análisis e recomendaciones.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

LLM_OUTPUTS_DIR = Path("data/llm_outputs")
MODEL_ID = "claude-haiku-4-5-20251001"


def _get_client():
    """Devuelve cliente Anthropic si está disponible."""
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        return None


def _save_output(client_id: str, parcel_id: str | None, data: dict) -> Path:
    """Guarda análisis en data/llm_outputs/."""
    LLM_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    if parcel_id:
        fname = LLM_OUTPUTS_DIR / f"{client_id}_{parcel_id}.json"
    else:
        fname = LLM_OUTPUTS_DIR / f"{client_id}_general.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return fname


def load_llm_output(client_id: str, parcel_id: str | None = None) -> dict | None:
    """Carga análisis previo si existe."""
    if parcel_id:
        fname = LLM_OUTPUTS_DIR / f"{client_id}_{parcel_id}.json"
    else:
        fname = LLM_OUTPUTS_DIR / f"{client_id}_general.json"
    if fname.exists():
        with open(fname, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# Análisis general (sin parcela)
# ---------------------------------------------------------------------------

def _build_hms_context(hms_data: dict) -> str:
    """
    Construye sección textual de datos hidrológicos HMS para el prompt del LLM.
    Solo se incluye si hay datos significativos.
    """
    if not hms_data:
        return ""

    caudal = hms_data.get("caudal_pico_m3s")
    tiempo = hms_data.get("tiempo_pico_h")
    escorrentia = hms_data.get("escorrentia_acumulada_mm")
    cn = hms_data.get("CN")
    amc = hms_data.get("AMC")
    tc = hms_data.get("Tc_horas") or (hms_data.get("params", {}) or {}).get("Tc_horas")
    eto = hms_data.get("eto_acumulada_7d") or hms_data.get("eto_penman_mm")
    origen = hms_data.get("origen_variables", {})

    # Solo generar sección si hay al menos caudal o escorrentía
    if caudal is None and escorrentia is None:
        return ""

    lines = ["ANÁLISIS HIDROLÓGICO (Modelo HMS - SCS Curve Number):"]

    if cn is not None:
        lines.append(f"- Número de Curva SCS (CN): {cn}")
    if amc:
        amc_desc = {"I": "seco", "II": "normal", "III": "húmedo"}.get(amc, amc)
        lines.append(f"- Condición de humedad antecedente: AMC-{amc} ({amc_desc})")
    if tc is not None:
        lines.append(f"- Tiempo de concentración: {tc:.2f} horas")
    if escorrentia is not None:
        lines.append(f"- Escorrentía acumulada del evento: {escorrentia:.2f} mm")
    if caudal is not None:
        lines.append(f"- Caudal pico estimado: {caudal:.4f} m³/s")
    if tiempo is not None:
        lines.append(f"- Tiempo al pico: {tiempo:.2f} horas")
    if eto is not None:
        lines.append(f"- Evapotranspiración de referencia (ETo): {eto:.2f} mm/día")

    # Evaluación de riesgo hidrológico
    if caudal is not None and escorrentia is not None:
        if caudal > 0.1 or escorrentia > 20:
            lines.append("")
            lines.append(
                "⚠️ RIESGO HIDROLÓGICO ELEVADO: El caudal pico y la escorrentía "
                "indican riesgo de erosión y posible inundación en zonas bajas. "
                "Se recomienda revisar infraestructuras de drenaje y protección de suelo."
            )
        elif caudal > 0.01 or escorrentia > 5:
            lines.append("")
            lines.append(
                "⚡ RIESGO HIDROLÓGICO MODERADO: Escorrentía significativa que puede "
                "generar erosión superficial. Considerar cubiertas vegetales en parcelas "
                "con pendiente elevada."
            )

    if origen:
        lines.append("")
        lines.append(f"Fuentes de datos meteorológicos: {json.dumps(origen, ensure_ascii=False)}")

    return "\n".join(lines)

def _build_general_context(
    client_id: str,
    modeling_df: pd.DataFrame,
    hms_data: dict | None = None,
) -> str:
    """Construye contexto textual para el análisis general."""
    n = len(modeling_df)
    if n == 0:
        return "No hay datos disponibles."

    perdida_media = modeling_df["pct_perdida_pred_pct"].mean() if "pct_perdida_pred_pct" in modeling_df.columns else 0
    impacto_total = modeling_df["impacto_total_eur"].sum() if "impacto_total_eur" in modeling_df.columns else 0
    impacto_medio = modeling_df["impacto_eur_ha_pred"].mean() if "impacto_eur_ha_pred" in modeling_df.columns else 0

    riesgo_dist = {}
    if "nivel_riesgo" in modeling_df.columns:
        riesgo_dist = modeling_df["nivel_riesgo"].value_counts().to_dict()

    rain_media = modeling_df["rain_7d_mm"].mean() if "rain_7d_mm" in modeling_df.columns else 0
    humedad_media = modeling_df["humedad_suelo_%"].mean() if "humedad_suelo_%" in modeling_df.columns else 0
    ench_media = modeling_df["duracion_encharcamiento_dias"].mean() if "duracion_encharcamiento_dias" in modeling_df.columns else 0

    # Top 3 parcelas críticas
    if "impacto_total_eur" in modeling_df.columns:
        top3 = modeling_df.nlargest(3, "impacto_total_eur")[
            ["parcel_id", "pct_perdida_pred_pct", "nivel_riesgo", "impacto_total_eur"]
        ].to_dict("records")
    else:
        top3 = []

    ctx = f"""
CLIENTE: {client_id}
ANÁLISIS GENERAL - {datetime.now().strftime('%Y-%m-%d')}

RESUMEN NUMÉRICO:
- Parcelas analizadas: {n}
- Pérdida media estimada: {perdida_media:.2f}%
- Impacto económico total estimado: €{impacto_total:,.2f}
- Impacto económico medio por hectárea: €{impacto_medio:.2f}
- Distribución de riesgo: {riesgo_dist}

CONDICIONES CLIMÁTICAS Y EDÁFICAS (promedios):
- Lluvia acumulada 7 días: {rain_media:.1f} mm
- Humedad media del suelo: {humedad_media:.1f}%
- Encharcamiento estimado promedio: {ench_media:.2f} días

TOP 3 PARCELAS POR IMPACTO ECONÓMICO:
{json.dumps(top3, indent=2, ensure_ascii=False)}
""".strip()

    # Inyectar datos HMS si están disponibles
    if hms_data:
        hms_section = _build_hms_context(hms_data)
        if hms_section:
            ctx += f"\n\n{hms_section}"

    return ctx


def generate_general_analysis(
    client_id: str,
    modeling_df: pd.DataFrame,
    hms_data: dict | None = None,
) -> dict:
    """
    Genera análisis agronómico general para el cliente.
    Si no hay API key, usa análisis basado en reglas.

    Args:
        client_id: identificador del cliente
        modeling_df: DataFrame con predicciones
        hms_data: dict opcional con resultados HMS (caudal_pico, escorrentía, etc.)
    """
    ctx = _build_general_context(client_id, modeling_df, hms_data)
    client = _get_client()

    if client:
        prompt = f"""Eres un agrónomo experto en olivar mediterráneo. Analiza los datos de este cliente y genera:

1. RESUMEN_EJECUTIVO: 2-3 párrafos sobre el estado general de sus parcelas de olivar.
2. RIESGOS_PRINCIPALES: Lista de 3-5 riesgos identificados.
3. PARCELAS_PRIORITARIAS: Top 3-5 parcelas que requieren atención inmediata y por qué.
4. RECOMENDACIONES: Lista de 5-8 acciones concretas divididas en corto, medio y seguimiento.

Responde en JSON con exactamente estas claves: resumen_ejecutivo, riesgos_principales, parcelas_prioritarias, recomendaciones.

DATOS:
{ctx}"""

        try:
            import anthropic
            msg = client.messages.create(
                model=MODEL_ID,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            text = msg.content[0].text
            # Intentar parsear JSON
            try:
                # Extraer JSON del texto si está entre ```json ... ```
                import re
                match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
                if match:
                    text = match.group(1)
                result = json.loads(text)
            except json.JSONDecodeError:
                result = {"resumen_ejecutivo": text, "riesgos_principales": [], "parcelas_prioritarias": [], "recomendaciones": []}
        except Exception as e:
            result = _rule_based_general_analysis(modeling_df, error=str(e))
    else:
        result = _rule_based_general_analysis(modeling_df)

    output = {
        "client_id": client_id,
        "parcel_id": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "general",
        "summary": result.get("resumen_ejecutivo", ""),
        "risks": result.get("riesgos_principales", []),
        "recommendations": result.get("recomendaciones", []),
        "priority_parcels": result.get("parcelas_prioritarias", []),
        "report_sections": result,
        "source": "llm" if client else "rules",
    }
    _save_output(client_id, None, output)
    return output


def _rule_based_general_analysis(df: pd.DataFrame, error: str = None) -> dict:
    """Análisis basado en reglas cuando LLM no está disponible."""
    n = len(df)
    perdida_media = df["pct_perdida_pred_pct"].mean() if "pct_perdida_pred_pct" in df.columns else 0
    rain_media = df["rain_7d_mm"].mean() if "rain_7d_mm" in df.columns else 0
    ench_media = df["duracion_encharcamiento_dias"].mean() if "duracion_encharcamiento_dias" in df.columns else 0
    humedad_media = df["humedad_suelo_%"].mean() if "humedad_suelo_%" in df.columns else 0
    impacto_total = df["impacto_total_eur"].sum() if "impacto_total_eur" in df.columns else 0

    # Resumen ejecutivo basado en condiciones
    if rain_media < 5 and ench_media == 0 and perdida_media < 5:
        summary = (
            f"Se analizaron {n} parcelas de olivar. Las pérdidas estimadas son bajas ({perdida_media:.2f}% de media), "
            f"lo que se explica principalmente por la ausencia de lluvia acumulada reciente ({rain_media:.1f} mm en 7 días) "
            f"y encharcamiento nulo. El impacto económico total estimado es de €{impacto_total:,.2f}.\n\n"
            f"Las condiciones climáticas actuales son secas, con humedad media del suelo del {humedad_media:.1f}%. "
            f"Este escenario es favorable para el olivar desde el punto de vista de enfermedades fúngicas, "
            f"aunque debe vigilarse el estrés hídrico si la sequía persiste durante el período de crecimiento del fruto."
        )
    elif rain_media > 50 or ench_media > 1:
        summary = (
            f"Se analizaron {n} parcelas de olivar. Las condiciones de alta pluviometría "
            f"({rain_media:.1f} mm acumulados en 7 días) y encharcamiento estimado de {ench_media:.1f} días "
            f"representan un factor de riesgo relevante. La pérdida media estimada es del {perdida_media:.2f}%."
        )
    else:
        summary = (
            f"Se analizaron {n} parcelas de olivar. La pérdida media estimada es del {perdida_media:.2f}%, "
            f"con un impacto económico total de €{impacto_total:,.2f}. "
            f"Las condiciones actuales son moderadas."
        )

    # Riesgos
    risks = []
    if rain_media > 30:
        risks.append(f"Lluvia acumulada elevada ({rain_media:.1f} mm/7d): riesgo de encharcamiento y enfermedades fúngicas.")
    if ench_media > 0.5:
        risks.append(f"Encharcamiento estimado ({ench_media:.1f} días): posible daño radicular en parcelas con drenaje limitado.")
    if humedad_media > 60:
        risks.append(f"Humedad del suelo elevada ({humedad_media:.1f}%): condiciones favorables para Phytophthora y Verticillium.")
    if "pendiente_%" in df.columns:
        n_extreme = int((pd.to_numeric(df["pendiente_%"], errors="coerce") > 60).sum())
        if n_extreme > 0:
            risks.append(f"{n_extreme} parcelas con pendiente >60%: riesgo de erosión y posibles anomalías SIGPAC a revisar.")
    if not risks:
        risks.append("No se detectan riesgos climáticos o hidrológicos significativos en las condiciones actuales.")

    # Recomendaciones
    recs = {
        "corto_plazo": [],
        "medio_plazo": [],
        "seguimiento": [],
    }
    if rain_media > 30 or ench_media > 0.5:
        recs["corto_plazo"].append("Revisar sistemas de drenaje en parcelas con drenaje moderado o malo.")
        recs["corto_plazo"].append("Evitar laboreo en condiciones de alta humedad para prevenir compactación.")
    if humedad_media < 30 and rain_media < 5:
        recs["corto_plazo"].append("Valorar riego de apoyo en parcelas con tensión hídrica si está disponible.")
    recs["medio_plazo"].append("Actualizar datos fenológicos antes de la próxima predicción para mayor precisión.")
    recs["seguimiento"].append("Monitorizar evolución climática los próximos 14 días.")
    recs["seguimiento"].append("Repetir predicción tras eventos de lluvia significativos.")

    # Top parcelas
    priority = []
    if "impacto_total_eur" in df.columns:
        for _, row in df.nlargest(3, "impacto_total_eur").iterrows():
            priority.append({
                "parcela": row.get("parcel_id", "—"),
                "riesgo": str(row.get("nivel_riesgo", "—")),
                "perdida_%": f"{row.get('pct_perdida_pred_pct', 0):.2f}%",
                "impacto_total": f"€{row.get('impacto_total_eur', 0):.2f}",
                "motivo": "Mayor impacto económico estimado",
            })

    return {
        "resumen_ejecutivo": summary,
        "riesgos_principales": risks,
        "parcelas_prioritarias": priority,
        "recomendaciones": recs,
    }


# ---------------------------------------------------------------------------
# Análisis por parcela
# ---------------------------------------------------------------------------

def generate_parcel_analysis(
    client_id: str,
    parcel_id: str,
    parcel_data: dict,
    hms_data: dict | None = None,
) -> dict:
    """
    Genera análisis agronómico para una parcela individual.
    Si no hay API key, usa análisis basado en reglas.

    Args:
        hms_data: dict opcional con resultados HMS para esta parcela
    """
    client = _get_client()

    # Inyectar datos HMS al contexto de la parcela
    if hms_data:
        parcel_data = {**parcel_data, "_hms": hms_data}

    ctx = json.dumps(parcel_data, ensure_ascii=False, indent=2)

    if client:
        prompt = f"""Eres un agrónomo experto en olivar mediterráneo. Analiza los datos de esta parcela y genera:

1. EVALUACION_AGRONOMICA: Evaluación del estado de la parcela (2 párrafos).
2. RIESGOS_DETECTADOS: Lista de riesgos específicos de esta parcela.
3. ESTIMACION_PERDIDA: Explicación de la pérdida predicha y sus causas.
4. IMPACTO_ECONOMICO: Análisis del impacto económico estimado en contexto.
5. RECOMENDACIONES_TECNICAS: Lista de 5-7 acciones técnicas concretas.
6. ACCION_SUGERIDA: Una frase clara sobre la acción prioritaria.

Responde en JSON con estas claves exactas.

DATOS DE PARCELA:
{ctx}"""

        try:
            import anthropic
            msg = client.messages.create(
                model=MODEL_ID,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            text = msg.content[0].text
            try:
                import re
                match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
                if match:
                    text = match.group(1)
                result = json.loads(text)
            except json.JSONDecodeError:
                result = _rule_based_parcel_analysis(parcel_data)
        except Exception:
            result = _rule_based_parcel_analysis(parcel_data)
    else:
        result = _rule_based_parcel_analysis(parcel_data)

    output = {
        "client_id": client_id,
        "parcel_id": parcel_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "parcel",
        "agronomic_evaluation": result.get("evaluacion_agronomica", result.get("EVALUACION_AGRONOMICA", "")),
        "detected_risks": result.get("riesgos_detectados", result.get("RIESGOS_DETECTADOS", [])),
        "loss_estimation": result.get("estimacion_perdida", result.get("ESTIMACION_PERDIDA", "")),
        "economic_impact": result.get("impacto_economico", result.get("IMPACTO_ECONOMICO", "")),
        "technical_recommendations": result.get("recomendaciones_tecnicas", result.get("RECOMENDACIONES_TECNICAS", [])),
        "suggested_action": result.get("accion_sugerida", result.get("ACCION_SUGERIDA", "")),
        "risk_level": parcel_data.get("nivel_riesgo", "—"),
        "source": "llm" if client else "rules",
    }
    _save_output(client_id, parcel_id, output)
    return output


def _rule_based_parcel_analysis(data: dict) -> dict:
    """Análisis basado en reglas para una parcela."""
    def _fv(k, default=0):
        try:
            return float(data.get(k) or default)
        except (TypeError, ValueError):
            return default

    perdida = _fv("pct_perdida_pred_pct")
    impacto_total = _fv("impacto_total_eur")
    impacto_ha = _fv("impacto_eur_ha_pred")
    rain_7d = _fv("rain_7d_mm")
    humedad = _fv("humedad_suelo_%")
    ench = _fv("duracion_encharcamiento_dias")
    pendiente = _fv("pendiente_%")
    drenaje = str(data.get("drenaje", "—"))
    riesgo = str(data.get("nivel_riesgo", "bajo")).replace("_", " ").lower()
    variedad = data.get("variedad", "—")
    tipo = data.get("tipo_olivar", "—")
    riego_tipo = data.get("riego", "—")
    mo = _fv("materia_organica_%")

    # Evaluación agronómica
    eval_text = (
        f"La parcela presenta riesgo {riesgo} de pérdida productiva, con una pérdida estimada del {perdida:.2f}% "
        f"y un impacto económico de €{impacto_ha:.2f}/ha (€{impacto_total:.2f} total). "
    )
    if rain_7d < 5 and ench == 0:
        eval_text += (
            f"Las condiciones climáticas actuales son secas ({rain_7d:.1f} mm en 7 días), lo que limita el riesgo de "
            f"enfermedades fúngicas pero puede generar estrés hídrico en {tipo.lower()} de {variedad.lower()} "
            f"con {'riego por ' + riego_tipo.lower() if 'Secano' not in riego_tipo else 'manejo en secano'}."
        )
    else:
        eval_text += (
            f"Se registraron {rain_7d:.1f} mm de lluvia en 7 días con encharcamiento estimado de {ench:.1f} días, "
            f"factores que incrementan el riesgo de enfermedades fúngicas en este olivar."
        )

    eval_text2 = (
        f"La humedad del suelo es del {humedad:.1f}%, la materia orgánica del {mo:.2f}% "
        f"y el drenaje es {drenaje.lower()}. "
    )
    if pendiente > 60:
        eval_text2 += f"La pendiente del {pendiente:.0f}% es elevada, lo que puede favorecer la escorrentía y erosión superficial."
    elif pendiente > 30:
        eval_text2 += f"La pendiente del {pendiente:.0f}% es moderada; considerar prácticas de conservación de suelo."
    else:
        eval_text2 += f"La pendiente del {pendiente:.0f}% es adecuada para el manejo mecanizado."

    # Riesgos
    risks = []
    if rain_7d > 50:
        risks.append(f"Lluvia elevada: {rain_7d:.1f} mm acumulados en 7 días.")
    if ench > 1:
        risks.append(f"Encharcamiento de {ench:.1f} días: riesgo de asfixia radicular.")
    if drenaje in ("Malo", "Moderado"):
        risks.append(f"Drenaje {drenaje.lower()}: limita la evacuación del agua en exceso.")
    if humedad > 60:
        risks.append(f"Humedad del suelo elevada ({humedad:.1f}%): condiciones para Verticillium y Phytophthora.")
    if pendiente > 60:
        risks.append(f"Pendiente >60% ({pendiente:.0f}%): riesgo de erosión y posible anomalía SIGPAC.")
    if mo < 1.5:
        risks.append(f"Materia orgánica baja ({mo:.2f}%): menor capacidad de retención hídrica y nutrientes.")
    if not risks:
        risks.append("No se detectaron factores de riesgo significativos bajo las condiciones actuales.")

    # Estimación pérdida
    loss_txt = (
        f"El modelo estima una pérdida del {perdida:.2f}% de la producción esperada para esta parcela. "
        f"Con un rendimiento esperado de {data.get('rendimiento_esperado_kg_ha', '—')} kg/ha, esto representa "
        f"un impacto de €{impacto_ha:.2f}/ha, equivalente a €{impacto_total:.2f} totales para esta parcela."
    )

    # Impacto económico
    econ_txt = (
        f"Impacto estimado: €{impacto_total:.2f} (€{impacto_ha:.2f}/ha). "
        f"Con precio de mercado de €{data.get('precio_mercado_eur_kg', '—')}/kg, "
        f"cualquier mejora en drenaje o manejo hídrico puede mitigar este impacto."
    )

    # Recomendaciones
    recs = []
    if ench > 0 or drenaje in ("Malo", "Moderado"):
        recs.append("Revisar y mejorar el sistema de drenaje de la parcela.")
    if rain_7d > 30:
        recs.append("Suspender temporalmente cualquier labor de suelo hasta que drene el exceso de agua.")
    if humedad > 60:
        recs.append("Aplicar tratamiento preventivo antifúngico si la humedad persiste.")
    if mo < 1.5:
        recs.append("Incorporar materia orgánica mediante compost o cubiertas vegetales.")
    recs.append(f"Actualizar estado fenológico en la plataforma para refinar la predicción.")
    recs.append("Monitorizar evolución climática los próximos 14 días.")
    recs.append("Repetir análisis tras siguiente evento de lluvia significativo.")

    # Acción sugerida
    if riesgo in ("alto", "muy alto"):
        action = "Actuar con prioridad alta: revisar drenaje y aplicar medidas preventivas inmediatas."
    elif rain_7d < 5 and humedad < 30:
        action = "Evaluar necesidad de riego de apoyo durante el período de maduración del fruto."
    else:
        action = "Mantener seguimiento meteorológico semanal y revisar fenología del cultivo."

    return {
        "evaluacion_agronomica": f"{eval_text}\n\n{eval_text2}",
        "riesgos_detectados": risks,
        "estimacion_perdida": loss_txt,
        "impacto_economico": econ_txt,
        "recomendaciones_tecnicas": recs,
        "accion_sugerida": action,
    }
