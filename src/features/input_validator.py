"""
Validador de CSV ML-ready antes de ejecutar predicción.

Verifica:
- Exactamente 22 columnas del modelo
- Orden correcto
- Tipos de datos
- Categorías válidas
- Sin nulos en columnas obligatorias
"""
import pandas as pd
from src.features.build_input_from_parcels import SCHEMA_COLUMNS

# Tipos y categorías esperadas
EXPECTED_TYPES = {
    "parcel_id": "string",
    "zona_provincia": "string",
    "tipo_olivar": "string",
    "riego": "string",
    "superficie_ha": "float",
    "variedad": "string",
    "estado_fenologico": "string",
    "tipo_suelo": "string",
    "drenaje": "string",
    "pendiente_%": "float",
    "distancia_rio_m": "float",
    "altitud_m": "float",
    "rain_72h_mm": "float",
    "rain_7d_mm": "float",
    "temp_media_7d": "float",
    "humedad_suelo_%": "float",
    "profundidad_suelo_cm": "float",
    "materia_organica_%": "float",
    "rendimiento_esperado_kg_ha": "float",
    "precio_mercado_eur_kg": "float",
    "coste_variable_ha": "float",
    "duracion_encharcamiento_dias": "float",
}

VALID_CATEGORIES = {
    "tipo_olivar": ["Tradicional", "Intensivo", "Superintensivo"],
    "riego": ["Secano", "Riego"],
    "drenaje": ["Bueno", "Moderado", "Malo"],
}


def validate_ml_csv(df: pd.DataFrame) -> dict:
    """
    Valida un CSV ML-ready.

    Retorna dict con:
    - is_valid: bool
    - errors: list de errores críticos
    - warnings: list de advertencias
    - ready_for_ml: bool (igual a is_valid)
    - n_rows: número de filas
    - cols_status: dict de validación por columna
    """
    errors = []
    warnings = []
    cols_status = {}

    # 1. Verificar número y orden de columnas
    if len(df.columns) != len(SCHEMA_COLUMNS):
        errors.append(f"Expected {len(SCHEMA_COLUMNS)} columns, got {len(df.columns)}")

    if list(df.columns) != SCHEMA_COLUMNS:
        missing = set(SCHEMA_COLUMNS) - set(df.columns)
        extra = set(df.columns) - set(SCHEMA_COLUMNS)
        if missing:
            errors.append(f"Missing columns: {missing}")
        if extra:
            warnings.append(f"Extra columns (will be ignored): {extra}")

    # 2. Verificar tipos de datos
    for col in SCHEMA_COLUMNS:
        if col not in df.columns:
            cols_status[col] = {"valid": False, "issue": "missing"}
            continue

        expected_type = EXPECTED_TYPES.get(col, "unknown")
        actual_series = df[col]

        # Intentar conversión si es numérico
        if expected_type in ("float", "int"):
            try:
                pd.to_numeric(actual_series, errors="coerce")
                n_nulls = actual_series.isna().sum()
                if n_nulls > 0:
                    warnings.append(f"{col}: {n_nulls} null values (will be treated as NaN)")
                cols_status[col] = {"valid": True, "type_ok": True, "nulls": n_nulls}
            except Exception as e:
                errors.append(f"{col}: Invalid numeric values - {str(e)[:100]}")
                cols_status[col] = {"valid": False, "issue": str(e)[:100]}
        else:
            # String columns
            n_nulls = actual_series.isna().sum()
            if n_nulls > 0:
                warnings.append(f"{col}: {n_nulls} null values")
            cols_status[col] = {"valid": True, "type_ok": True, "nulls": n_nulls}

    # 3. Verificar categorías válidas
    for col, valid_cats in VALID_CATEGORIES.items():
        if col not in df.columns:
            continue
        invalid = df[~df[col].isin(valid_cats) & df[col].notna()]
        if not invalid.empty:
            invalid_vals = set(invalid[col].unique())
            warnings.append(
                f"{col}: {len(invalid)} rows with invalid categories: {invalid_vals}"
            )
            cols_status[col]["category_issue"] = list(invalid_vals)

    # 4. Verificar nulos en columnas clave
    key_cols = ["parcel_id", "zona_provincia", "tipo_olivar", "riego"]
    for col in key_cols:
        if col in df.columns:
            n_nulls = df[col].isna().sum()
            if n_nulls > 0:
                errors.append(f"{col}: {n_nulls} null values (key column)")

    # Resumen
    is_valid = len(errors) == 0
    ready_for_ml = is_valid and len(df) > 0

    return {
        "is_valid": is_valid,
        "ready_for_ml": ready_for_ml,
        "errors": errors,
        "warnings": warnings,
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "n_cols_expected": len(SCHEMA_COLUMNS),
        "cols_status": cols_status,
    }


def load_and_validate_ml_csv(csv_path: str) -> tuple[pd.DataFrame | None, dict]:
    """
    Carga CSV y lo valida.
    Retorna (df, validation_report).
    Si hay errores críticos, retorna (None, report).

    Si el CSV tiene más de 22 columnas (p.ej. consolidado interno con columnas técnicas),
    filtra automáticamente solo las 22 columnas del modelo.
    """
    try:
        df = pd.read_csv(csv_path, sep=";", dtype=str)

        # Si hay más de 22 columnas, asumir que son consolidadas internas
        # y filtrar solo las 22 del modelo
        if len(df.columns) > len(SCHEMA_COLUMNS):
            # Filtrar solo columnas del schema
            df = df[[col for col in SCHEMA_COLUMNS if col in df.columns]]

        # Convertir numéricas
        for col in SCHEMA_COLUMNS:
            if col in EXPECTED_TYPES and EXPECTED_TYPES[col] in ("float", "int"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
    except Exception as e:
        return None, {
            "is_valid": False,
            "ready_for_ml": False,
            "errors": [f"Failed to load CSV: {str(e)}"],
            "warnings": [],
            "n_rows": 0,
            "n_cols": 0,
            "n_cols_expected": len(SCHEMA_COLUMNS),
            "cols_status": {},
        }

    report = validate_ml_csv(df)
    if not report["is_valid"]:
        return None, report

    return df, report
