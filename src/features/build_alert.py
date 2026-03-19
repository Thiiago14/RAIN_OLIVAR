def build_alert(row: dict):
    pct_perdida = float(row["pct_perdida_pred"])
    
    if pct_perdida > 0.3:
        nivel = "alto"
        accion = "Mejorar drenaje inmediatamente"
    elif pct_perdida > 0.1:
        nivel = "medio"
        accion = "Monitorear humedad del suelo"
    else:
        nivel = "bajo"
        accion = "Sin acción inmediata"

    riesgos = []
    
    if pct_perdida > 0.2:
        riesgos.append("encharcamiento")
    if pct_perdida > 0.15:
        riesgos.append("erosion")

    return {
        "equipo": "OLIVIA",
        "tipo": "alerta_agronomica",
        "parcel_id": row["parcel_id"],
        "pct_perdida_pct": f"{round(pct_perdida * 100, 1)}%",
        "nivel_riesgo": nivel,
        "riesgos": riesgos,
        "impacto_eur_ha": round(row["impacto_eur_ha_pred"], 2),
        "accion": accion
    }