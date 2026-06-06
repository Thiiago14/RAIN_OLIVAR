"""
FastAPI backend para AgriAI — endpoints de hidrología y meteorología.

Ejecutar con:
    uvicorn src.api.main:app --reload --port 8000

Documentación interactiva:
    http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.hidrologico import router as hidrologico_router

app = FastAPI(
    title="AgriAI — Olivar Prediction Platform",
    description="API de hidrología y meteorología para fincas de olivar",
    version="1.0.0",
)

# CORS para el frontend Streamlit (mismo host, distinto puerto)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(hidrologico_router, prefix="/api", tags=["hidrologico"])


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "AgriAI"}
