"""
Carga de modelo ML entrenado usando joblib.
"""
from pathlib import Path
import joblib


def load_model(path="data/output/modelo_olivar.pkl"):
    """
    Carga modelo ML entrenado con joblib.

    Args:
        path: Ruta al archivo .pkl (str o Path)

    Retorna:
        Modelo sklearn cargado

    Raises:
        FileNotFoundError: Si el archivo no existe
        ValueError: Si hay error al cargar
    """
    path = Path(path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")

    try:
        model = joblib.load(path)
        return model
    except Exception as e:
        raise ValueError(f"Failed to load model from {path}: {str(e)}")
