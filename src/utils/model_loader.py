import joblib

def load_model(path="data/output/modelo_olivar.pkl"):
    return joblib.load(path)