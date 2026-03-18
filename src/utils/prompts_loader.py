import os


BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_txt(relative_path: str) -> str:
    path = os.path.join(BASE_PATH, relative_path)
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontró el archivo: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return f.read()