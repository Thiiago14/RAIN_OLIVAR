import geopandas as gpd

USO_COLUMN_ALIASES = ["uso_sigpac", "uso", "USO_SIGPAC", "USO", "uso_sigpac_"]
OV_CODE = "OV"


def detect_uso_column(gdf: gpd.GeoDataFrame) -> str | None:
    for col in USO_COLUMN_ALIASES:
        if col in gdf.columns:
            return col
    return None


def filter_ov(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    uso_col = detect_uso_column(gdf)
    if uso_col is None:
        return gdf
    return gdf[gdf[uso_col] == OV_CODE].copy().reset_index(drop=True)


def get_usage_stats(gdf: gpd.GeoDataFrame) -> dict:
    uso_col = detect_uso_column(gdf)
    total = len(gdf)

    if uso_col is None or "area_ha_calc" not in gdf.columns:
        return {
            "uso_col": None,
            "total": total,
            "n_ov": 0,
            "n_non_ov": total,
            "ha_total": round(gdf["area_ha_calc"].sum(), 2) if "area_ha_calc" in gdf.columns else 0,
            "ha_ov": 0,
            "ha_non_ov": 0,
            "pct_ov": 0,
            "by_uso": {},
            "error": "No se encontró columna de uso SIGPAC",
        }

    ov_mask = gdf[uso_col] == OV_CODE
    ha_ov = float(gdf.loc[ov_mask, "area_ha_calc"].sum())
    ha_non_ov = float(gdf.loc[~ov_mask, "area_ha_calc"].sum())
    ha_total = ha_ov + ha_non_ov

    return {
        "uso_col": uso_col,
        "total": total,
        "n_ov": int(ov_mask.sum()),
        "n_non_ov": int((~ov_mask).sum()),
        "ha_total": round(ha_total, 2),
        "ha_ov": round(ha_ov, 2),
        "ha_non_ov": round(ha_non_ov, 2),
        "pct_ov": round(ha_ov / ha_total * 100, 1) if ha_total > 0 else 0,
        "by_uso": gdf[uso_col].value_counts().to_dict(),
        "error": None,
    }
