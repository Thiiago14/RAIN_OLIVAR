# Arquitectura actual — LLM_RAIN_OLIVAR

## Pipeline (flujo de ejecución)

```
data/input/test_olivar.csv
        │
        ▼
┌─────────────────────┐
│  1. ML Prediction   │  model_loader + prediction_perdida
│  modelo_olivar.pkl  │  → pct_perdida_pred
│                     │  → impacto_eur_ha_pred
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  2. LLM Analysis    │  OlivarAgent (por cada parcela)
│  gpt-5.5 (OpenAI)   │  ├── Role: olivar_expert.txt
│                     │  ├── Prompt: analysis_prompt.txt
│                     │  └── RAG: knowledge_base (top 3 chunks)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  3. PDF Report      │  report_generator
│  informe_olivar.pdf │  ├── Resumen ejecutivo
│                     │  ├── Distribución de riesgo
│                     │  ├── Top 10 parcelas críticas
│                     │  └── Análisis LLM por parcela
└─────────────────────┘
```

---

## Módulos activos

| Archivo | Función |
|---|---|
| `main.py` | Orquestador: ejecuta los 3 pasos en secuencia |
| `src/config/models_config.py` | Catálogo de modelos LLM con precios; default `gpt-5.5` |
| `src/config/llms.py` | Cliente HTTP unificado para OpenAI / Gemini / Anthropic / GLM; retry 3x ante timeout |
| `src/utils/model_loader.py` | Carga `modelo_olivar.pkl` con joblib |
| `src/features/prediction_perdida.py` | Predice pérdida (%), calcula impacto €/ha, guarda CSV |
| `src/orquestador/olivar_agent.py` | Construye prompt con datos + RAG, llama al LLM, devuelve análisis |
| `src/utils/knowledge_base.py` | RAG por palabras clave: carga resúmenes TXT, puntúa y devuelve top 3 chunks |
| `src/utils/prompts_loader.py` | Carga `analysis_prompt.txt` y `olivar_expert.txt` desde disco |
| `src/utils/report_generator.py` | Genera PDF con FPDF2, colores por nivel de riesgo |
| `src/utils/llm_client.py` | Factory (devuelve instancia `OpenAI`) |

---

## Datos

| Ruta | Contenido |
|---|---|
| `data/input/test_olivar.csv` | 10 parcelas con variables climáticas y agronómicas |
| `data/output/modelo_olivar.pkl` | Modelo scikit-learn entrenado |
| `data/Base documental/resumenes/` | 6 TXTs para RAG (plagas, inundaciones, repilo, buenas prácticas) |
| `data/output/submission_olivar.csv` | Output ML: pérdida e impacto por parcela |
| `data/output/informe_olivar.pdf` | Informe final con análisis LLM |

---

## Proveedores LLM configurados

| Modelo | Proveedor | $/M tokens in | $/M tokens out |
|---|---|---|---|
| `gpt-5.5` *(default)* | OpenAI | 5.00 | 30.00 |
| `gpt-5.4` | OpenAI | 2.50 | 15.00 |
| `gpt-5.4-mini` | OpenAI | 0.75 | 4.50 |
| `gpt-5.2` | OpenAI | 1.75 | 14.00 |
| `gpt-4o` / `gpt-4o-mini` | OpenAI | 2.50 / 0.15 | 10.00 / 0.60 |
| `gemini-2.5-flash` | Google | 0.30 | 2.50 |
| `glm-5` | Zhipu AI | 0.50 | 2.00 |

---

## Estructura del proyecto

```
LLM_RAIN_OLIVAR/
│
├── data/
│   ├── input/                        # Dataset de entrada
│   ├── output/                       # Predicciones, modelo y PDF
│   └── Base documental/
│       ├── *.pdf                     # Documentos agronómicos originales
│       └── resumenes/*.txt           # Resúmenes para RAG
│
├── notebooks/
│   └── modelo_olivar.ipynb           # Entrenamiento del modelo ML
│
├── src/
│   ├── config/
│   │   ├── llms.py                   # Cliente LLM multi-proveedor
│   │   └── models_config.py          # Catálogo de modelos y selección
│   │
│   ├── features/
│   │   ├── prediction_perdida.py     # Pipeline ML
│   │   └── resumen_pdfs.py           # Generación de resúmenes de PDFs
│   │
│   ├── orquestador/
│   │   └── olivar_agent.py           # Agente LLM principal
│   │
│   ├── prompts/
│   │   └── analysis_prompt.txt       # Prompt de análisis agronómico
│   │
│   ├── roles/
│   │   └── olivar_expert.txt         # System prompt del experto
│   │
│   └── utils/
│       ├── data_loader.py            # Carga de datos JSON
│       ├── knowledge_base.py         # RAG por palabras clave
│       ├── llm_client.py             # Factory del cliente LLM
│       ├── model_loader.py           # Carga modelo .pkl
│       ├── prompts_loader.py         # Carga de prompts desde disco
│       └── report_generator.py      # Generación de informe PDF
│
├── main.py                           # Pipeline principal
├── requirements.txt
├── .env                              # Claves API (no versionar)
└── ARCHITECTURE.md                   # Este archivo
```

---

## Niveles de riesgo

| Nivel | Umbral (pct_perdida) | Color en PDF |
|---|---|---|
| bajo | < 5% | Verde |
| medio | 5% – 15% | Amarillo |
| alto | 15% – 30% | Naranja |
| muy alto | > 30% | Rojo |

---

## Eliminado

- ~~MQTT~~ — `mqtt_client.py`, `build_alert.py` y dependencia `paho-mqtt` eliminados completamente
