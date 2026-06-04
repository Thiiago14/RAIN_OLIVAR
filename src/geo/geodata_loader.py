import os
import geopandas as gpd

SHP_BASE_DIR = "data/clientes_shp"
REQUIRED_EXTENSIONS = [".shp", ".dbf", ".shx", ".prj"]


def get_available_clients() -> list[str]:
    if not os.path.exists(SHP_BASE_DIR):
        return []
    return sorted([
        d for d in os.listdir(SHP_BASE_DIR)
        if os.path.isdir(os.path.join(SHP_BASE_DIR, d))
    ])


def find_shp_file(client_id: str) -> str | None:
    client_dir = os.path.join(SHP_BASE_DIR, client_id)
    for f in os.listdir(client_dir):
        if f.endswith(".shp"):
            return os.path.join(client_dir, f)
    return None


def validate_shapefile(client_id: str) -> list[str]:
    client_dir = os.path.join(SHP_BASE_DIR, client_id)
    if not os.path.exists(client_dir):
        return [f"Carpeta no encontrada: {client_dir}"]

    shp_file = find_shp_file(client_id)
    if not shp_file:
        return [f"No se encontró archivo .shp en {client_dir}"]

    base = os.path.splitext(shp_file)[0]
    errors = []
    for ext in REQUIRED_EXTENSIONS:
        if not os.path.exists(base + ext):
            errors.append(f"Falta archivo requerido: {base + ext}")
    return errors


def load_client_geodataframe(client_id: str) -> gpd.GeoDataFrame:
    errors = validate_shapefile(client_id)
    if errors:
        raise ValueError("\n".join(errors))

    shp_file = find_shp_file(client_id)
    gdf = gpd.read_file(shp_file)

    if gdf.crs is None:
        raise ValueError(
            "El shapefile no tiene CRS definido. "
            "Revisa el archivo .prj o asigna manualmente la proyección."
        )

    return gdf
