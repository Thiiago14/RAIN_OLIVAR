"""
Enriquecimiento económico-productivo con tablas de referencia locales.
MVP: rendimiento, precios y costes desde CSV. Producción: integrar ESYRCE/MAPA.
"""
import os
from datetime import datetime

import pandas as pd

REFERENCE_DIR = "data/reference"


def _load_reference_table(filename: str) -> pd.DataFrame | None:
    path = os.path.join(REFERENCE_DIR, filename)
    try:
        return pd.read_csv(path, sep=";", dtype=str).fillna("")
    except FileNotFoundError:
        return None


def enrich_economic_for_client(df: pd.DataFrame) -> pd.DataFrame:
    """Enriquece rendimiento, precios y costes. Retorna df con nuevas columnas."""
    now = datetime.now().isoformat(timespec="seconds")
    rendimiento_table = _load_reference_table("rendimiento_olivar_reference.csv")
    precios_table = _load_reference_table("precios_olivar_reference.csv")
    costes_table = _load_reference_table("costes_olivar_reference.csv")

    out = df.copy()
    out["rendimiento_esperado_kg_ha"] = None
    out["yield_match_level"] = ""
    out["precio_mercado_eur_kg"] = None
    out["price_match_level"] = ""
    out["coste_variable_ha"] = None
    out["cost_match_level"] = ""
    out["economic_updated_at"] = now
    out["economic_status"] = "no_reference"

    for idx, row in out.iterrows():
        zona = str(row.get("zona_provincia", "")).strip()
        tipo = str(row.get("tipo_olivar", "")).strip()
        riego = str(row.get("riego", "")).strip()
        variedad = str(row.get("variedad", "")).strip()

        # Rendimiento: 4 niveles
        if rendimiento_table is not None:
            yield_val, yield_level = _lookup_yield(rendimiento_table, zona, tipo, riego, variedad)
            out.at[idx, "rendimiento_esperado_kg_ha"] = yield_val
            out.at[idx, "yield_match_level"] = yield_level

        # Precio: 2 niveles
        if precios_table is not None:
            price_val, price_level = _lookup_price(precios_table, zona, variedad)
            out.at[idx, "precio_mercado_eur_kg"] = price_val
            out.at[idx, "price_match_level"] = price_level

        # Coste: 2 niveles
        if costes_table is not None:
            cost_val, cost_level = _lookup_cost(costes_table, tipo, riego)
            out.at[idx, "coste_variable_ha"] = cost_val
            out.at[idx, "cost_match_level"] = cost_level

        # Status general
        if yield_val and price_val and cost_val:
            out.at[idx, "economic_status"] = "ok"

    return out


def _lookup_yield(df: pd.DataFrame, zona: str, tipo: str, riego: str, variedad: str) -> tuple:
    """Busca rendimiento: zona+tipo+riego+variedad → zona+tipo+riego → default."""
    if df.empty:
        return None, "no_table"

    # Nivel 1: zona+tipo+riego+variedad
    match = df[
        (df["zona_provincia"].str.strip() == zona)
        & (df["tipo_olivar"].str.strip() == tipo)
        & (df["riego"].str.strip() == riego)
        & (df["variedad"].str.strip() == variedad)
    ]
    if not match.empty:
        return float(match.iloc[0]["rendimiento_esperado_kg_ha"]), "exact_variedad"

    # Nivel 2: zona+tipo+riego
    match = df[
        (df["zona_provincia"].str.strip() == zona)
        & (df["tipo_olivar"].str.strip() == tipo)
        & (df["riego"].str.strip() == riego)
    ]
    if not match.empty:
        return float(match.iloc[0]["rendimiento_esperado_kg_ha"]), "zona_tipo_riego"

    # Nivel 3: default
    default_row = df[
        (df["zona_provincia"].str.strip() == zona)
        & (df["tipo_olivar"].str.strip() == tipo)
    ]
    if not default_row.empty:
        return float(default_row.iloc[0]["rendimiento_esperado_kg_ha"]), "tipo_default"

    return None, "no_match"


def _lookup_price(df: pd.DataFrame, zona: str, variedad: str) -> tuple:
    """Busca precio: zona+variedad → variedad → default."""
    if df.empty:
        return None, "no_table"

    # Nivel 1: zona+variedad
    match = df[
        (df["zona_provincia"].str.strip() == zona)
        & (df["variedad"].str.strip() == variedad)
    ]
    if not match.empty:
        return float(match.iloc[0]["precio_mercado_eur_kg"]), "exact_zona_variedad"

    # Nivel 2: variedad solo
    match = df[df["variedad"].str.strip() == variedad]
    if not match.empty:
        return float(match.iloc[0]["precio_mercado_eur_kg"]), "variedad_only"

    # Nivel 3: default
    default = df[df["variedad"].str.strip() == "Desconocida"]
    if not default.empty:
        return float(default.iloc[0]["precio_mercado_eur_kg"]), "default_price"

    return None, "no_match"


def _lookup_cost(df: pd.DataFrame, tipo: str, riego: str) -> tuple:
    """Busca coste: tipo+riego → tipo → default."""
    if df.empty:
        return None, "no_table"

    # Nivel 1: tipo+riego
    match = df[
        (df["tipo_olivar"].str.strip() == tipo)
        & (df["riego"].str.strip() == riego)
    ]
    if not match.empty:
        return float(match.iloc[0]["coste_variable_ha"]), "exact_tipo_riego"

    # Nivel 2: tipo solo
    match = df[df["tipo_olivar"].str.strip() == tipo]
    if not match.empty:
        return float(match.iloc[0]["coste_variable_ha"]), "tipo_only"

    return None, "no_match"


def get_economic_stats(df: pd.DataFrame) -> dict:
    """Estadísticas de cobertura económica."""
    n = len(df)
    return {
        "total": n,
        "yield_filled": int(df["rendimiento_esperado_kg_ha"].notna().sum()),
        "price_filled": int(df["precio_mercado_eur_kg"].notna().sum()),
        "cost_filled": int(df["coste_variable_ha"].notna().sum()),
        "all_filled": int(
            (df["rendimiento_esperado_kg_ha"].notna()
             & df["precio_mercado_eur_kg"].notna()
             & df["coste_variable_ha"].notna()).sum()
        ),
        "pct_all": round(
            (df["rendimiento_esperado_kg_ha"].notna()
             & df["precio_mercado_eur_kg"].notna()
             & df["coste_variable_ha"].notna()).sum() / n * 100
        ) if n > 0 else 0,
    }
