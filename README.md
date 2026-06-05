# LLM Rain Olivar

Sistema inteligente para analizar el impacto de lluvias intensas en parcelas de olivar combinando:

* Modelos de Machine Learning (predicción de pérdida)
* LLM (análisis agronómico experto)
* Base documental (buenas prácticas y recomendaciones)
* Generación automática de reportes
* Sistema de alertas vía MQTT

---

## ¿Qué hace este proyecto?

Dado un dataset de parcelas de olivar:

1. Predice la **pérdida de producción (%)**
2. Calcula el **impacto económico (€ / ha)**
3. Analiza cada parcela con un **LLM experto**
4. Usa **conocimiento agronómico real (RAG)**
5. Publica **alertas automáticas por MQTT**
6. Genera resultados estructurados y listos para reporte

---

## Instalación

### 1. Clonar repositorio

```bash
git clone <repo_url>
cd LLM_RAIN_OLIVAR
```

---

### 2. Crear entorno virtual

```bash
python -m venv .venv
```

Activar:

**Windows**

```bash
.venv\Scripts\activate
```

**Linux/Mac**

```bash
source .venv/bin/activate
```

---

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

---

### 4. Configurar variables de entorno

Crear archivo `.env` con las claves del proveedor LLM que se quiera usar:

```env
OPENAI_API_KEY=tu_api_key
GEMINI_API_KEY=tu_api_key
ANTHROPIC_API_KEY=tu_api_key
GLM_API_KEY=tu_api_key
```

Solo es necesaria la clave del proveedor seleccionado en `src/config/models_config.py`.

Proveedores soportados: **OpenAI**, **Gemini**, **Anthropic**, **GLM (Zhipu AI)**.

---

## Ejecución

### App Streamlit (Recomendado)

```bash
streamlit run app/streamlit_app.py
```

Flujo interactivo:
1. **Seleccionar cliente** (cliente_1, cliente_2, etc.)
2. **Filtrar parcelas OV** (usar solo Olivar)
3. **Completar datos del agricultor** (tipo_olivar, riego, variedad, fenología)
4. **Enriquecer meteorología** (Open-Meteo: lluvias, temperatura, humedad suelo)
5. **Enriquecer suelo** (SoilGrids: textura, drenaje, materia orgánica, profundidad)
6. **Enriquecer hidrología** (Overpass: distancia a cauces, distancia_rio_m)
7. **Enriquecimiento económico** (tablas de referencia locales: rendimiento, precio, coste)
8. **CSV consolidado** (22 columnas completas, listo para ML)
9. **Validación ready_for_ml** (bloquea si hay datos faltantes)

### Script Python (Legacy)

```bash
python -m main
```

---

## Pipeline completo

El sistema ejecuta automáticamente:

### 1. Predicción ML

* Carga modelo entrenado (`.pkl`)
* Predice `pct_perdida_pred`
* Calcula impacto económico

### 2. Generación de dataset final

Se guarda en:

```text
data/output/submission_olivar.csv
```

---

### 3. Análisis con LLM

Para cada parcela:

* Evalúa riesgos (encharcamiento, erosión, etc.)
* Interpreta impacto económico
* Genera recomendaciones técnicas

---

### 4. RAG (Base de conocimiento)

El sistema usa documentos en:

```text
data/Base documental/resumenes/
```

Incluye:

* Buenas prácticas
* Manejo agronómico
* Enfermedades (repilo, etc.)
* Recomendaciones técnicas

---

### 5. Alertas MQTT

Tras cada análisis se construye y publica una alerta estructurada en el topic `hackathon/olivia` con:

* Nivel de riesgo (bajo / medio / alto)
* Riesgos detectados (encharcamiento, erosión)
* Acción recomendada
* Impacto económico por hectárea

---

## Estructura del proyecto

```text
LLM_RAIN_OLIVAR/
│
├── app/
│   └── streamlit_app.py       # Dashboard geoespacial interactivo
│
├── data/
│   ├── clientes_shp/          # Shapefiles SIGPAC por cliente (cliente_1/, cliente_2/, ...)
│   ├── client_inputs/         # Datos del agricultor por cliente (agricultor_inputs/*.csv)
│   ├── api_cache/             # Cache local de APIs externas
│   │   ├── weather/           # Open-Meteo (meteorología)
│   │   ├── soil/              # SoilGrids (edafología)
│   │   └── hydrology/         # Overpass/OSM (hidrología)
│   ├── reference/             # Tablas de referencia económica
│   │   ├── rendimiento_olivar_reference.csv
│   │   ├── precios_olivar_reference.csv
│   │   └── costes_olivar_reference.csv
│   ├── enriched/              # CSV consolidados (22 cols, listo para ML)
│   │   ├── cliente_1_input_enriched.csv
│   │   └── cliente_2_input_enriched.csv
│   ├── input/                 # Dataset de entrada (legacy)
│   ├── output/                # Predicciones y resultados
│   └── Base documental/       # PDFs + resúmenes (RAG)
│
├── src/
│   ├── geo/                   # Módulos geoespaciales
│   │   ├── geodata_loader.py      # Carga shapefiles por cliente
│   │   ├── parcels_processor.py    # Procesa parcelas (calcula superficies, etc.)
│   │   ├── usage_filter.py         # Filtra parcelas OV
│   │   └── map_builder.py          # Crea mapas interactivos
│   │
│   ├── features/              # Enriquecimiento de datos
│   │   ├── build_input_from_parcels.py    # CSV base + schema
│   │   ├── persistence.py                 # Guarda/carga inputs agricultor
│   │   ├── farmer_inputs.py               # Opciones y validación
│   │   ├── weather_enrichment.py          # Open-Meteo (meteo + conserva datos válidos)
│   │   ├── soil_enrichment.py             # SoilGrids (suelo + recuperación de errores)
│   │   ├── hydrology_enrichment.py        # Overpass (hidrología + recuperación de errores)
│   │   ├── economic_enrichment.py         # Tablas locales (rendimiento, precio, coste)
│   │   ├── waterlogging_calculator.py     # Cálculo encharcamiento
│   │   └── enrichment_assembler.py        # Integración + ready_for_ml
│   │
│   ├── integrations/          # Clientes de APIs externas
│   │   ├── open_meteo_client.py           # Open-Meteo REST API
│   │   ├── soilgrids_client.py            # SoilGrids v2 REST API
│   │   └── overpass_client.py             # Overpass/OSM API
│   │
│   ├── config/
│   │   ├── llms.py            # Cliente LLM multi-proveedor
│   │   └── models_config.py   # Configuración y selección de modelos
│   │
│   ├── features_ml/
│   │   ├── prediction_perdida.py   # Pipeline ML (legacy)
│   │   ├── resumen_pdfs.py         # Generación de resúmenes
│   │   └── build_alert.py          # Construcción de alertas MQTT
│   │
│   ├── orquestador/
│   │   └── olivar_agent.py         # Agente LLM
│   │
│   ├── prompts/               # Prompt engineering
│   ├── roles/                 # Rol experto agrónomo
│   │
│   └── utils/
│       ├── data_loader.py     # Carga y validación de datos
│       ├── knowledge_base.py  # RAG simple
│       ├── llm_client.py      # Cliente LLM
│       ├── model_loader.py    # Carga modelo ML
│       ├── mqtt_client.py     # Publicación de alertas MQTT
│       ├── prompts_loader.py  # Carga de prompts
│       └── report_generator.py # Generación PDF
│
├── docs/
│   └── DICCIONARIO_VARIABLES_OLIVAR.md    # Documentación de variables + schema
│
├── main.py                    # Pipeline principal (legacy)
├── requirements.txt
├── .env
└── README.md
```

---

## Manejo robusto de errores en APIs

### Estrategia por fuente

| Fuente | TTL | Modo actualización | Fallback |
|---|---|---|---|
| **SoilGrids** | 180 días | errors_only (reintenta con error) o force_all | Conserva dato previo válido, marca como "stale" |
| **Overpass** | 30 días | errors_only o force_all | Conserva dato previo válido, marca como "stale" |
| **Open-Meteo** | 24 horas | all (actualiza siempre) | Conserva dato previo válido, marca como "stale_weather" |
| **Tablas locales** | sin vencimiento | directo | Sin reintentos (valores por defecto) |

### Estados de datos

- **ok**: Dato nuevo exitoso de API / cálculo interno correcto
- **stale**: Dato anterior válido mantenido porque consulta API falló
- **error**: Consulta falló y sin dato previo válido
- **no_data**: Sin dato y sin intento anterior

### Flag ready_for_ml

El CSV consolidado NO está listo para modelo ML si:

* Falta alguna de las 22 columnas obligatorias
* Alguna parcela OV tiene variables incompletas
* Hay status "error" o "no_data" sin datos válidos previos

Cuando todas las 22 columnas estén 100% completas para todas las parcelas OV:
```
ready_for_ml = True → ✓ Listo para ejecutar predicción ML
ready_for_ml = False → ✗ Completar datos o reintentar APIs
```

### Advertencias de pendiente extrema

Se muestran advertencias (sin bloqueo) para:
- **Pendiente > 60%**: ADVERTENCIA (revisar dato SIGPAC)
- **Pendiente > 100%**: ALERTA FUERTE (posible error SIGPAC)

Estas parcelas salen en tabla de advertencias pero no bloquean `ready_for_ml`.

### Exportación para modelo ML

**CSV interno (app)**: 25 columnas (22 modelo + 3 técnicas)
- `_ready_for_ml`: flag booleano
- `_cols_complete`: count de columnas 100% completas
- `_n_parcelas_ov`: número de parcelas OV

**CSV para modelo ML** (botón descarga "CSV para modelo ML"): **22 columnas exactas**
- Sin columnas técnicas
- Orden correcto según SCHEMA_COLUMNS
- Listo para alimentar directamente al modelo

---

## Input esperado

Archivo:

```text
data/input/test_olivar.csv
```

Columnas típicas:

* `parcel_id`
* `zona_provincia`
* `tipo_olivar`
* `riego`
* `superficie_ha`
* `variedad`
* `rendimiento_esperado_kg_ha`
* `precio_mercado_eur_kg`
* variables climáticas

---

## Output generado

### CSV final

```text
data/output/submission_olivar.csv
```

Columnas:

* `parcel_id`
* `pct_perdida_pred`
* `impacto_eur_ha_pred`

---

### Output LLM (por parcela)

Ejemplo:

```
1. Evaluación agronómica
2. Riesgos detectados
3. Estimación de pérdida
4. Impacto económico
5. Recomendaciones técnicas
6. Acción automática sugerida
7. Nivel de riesgo
```

---

### Informe PDF

Se genera automáticamente en:

```text
data/output/informe_olivar_<timestamp>.pdf
```

Incluye el análisis LLM de cada parcela junto con las predicciones del modelo.

---

## Arquitectura

```text
ML Model → Predicción → LLM → RAG → MQTT Alert → Reporte PDF
```

---

## Estado actual

* Pipeline ML completo
* Integración con LLM multi-proveedor (OpenAI / Gemini / Anthropic / GLM)
* RAG básico con documentos reales
* Generación de recomendaciones agronómicas
* Sistema de alertas MQTT por parcela
* Generación automática de informes PDF
* Arquitectura modular (features, utils, agent)

---

## Mejoras futuras

* Embeddings + búsqueda semántica (FAISS)
* Ranking de documentos más relevante
* Dashboard interactivo
* API REST
* Automatización de ingestión de datos climáticos

---

## Notas

* Ejecutar siempre desde la raíz del proyecto
* Asegurarse de que `.env` está configurado con la clave del proveedor LLM elegido
* Verificar que el modelo `.pkl` existe en:

```text
data/output/modelo_olivar.pkl
```

---

## Caso de uso

Este sistema permite:

* Anticipar pérdidas en producción
* Reducir impacto económico
* Tomar decisiones agronómicas basadas en datos + conocimiento experto
* Emitir alertas automáticas en tiempo real sobre parcelas en riesgo

---
