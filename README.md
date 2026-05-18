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
├── data/
│   ├── input/                 # dataset de entrada
│   ├── output/                # predicciones y resultados
│   ├── Base documental/       # PDFs + resúmenes (RAG)
│
├── notebooks/
│   └── modelo_olivar.ipynb    # entrenamiento del modelo
│
├── src/
│   ├── config/
│   │   ├── llms.py            # cliente LLM multi-proveedor
│   │   └── models_config.py   # configuración y selección de modelos
│   │
│   ├── features/
│   │   ├── prediction_perdida.py   # pipeline ML
│   │   ├── resumen_pdfs.py         # generación de resúmenes
│   │   └── build_alert.py          # construcción de alertas MQTT
│   │
│   ├── orquestador/
│   │   └── olivar_agent.py    # agente LLM
│   │
│   ├── prompts/               # prompt engineering
│   ├── roles/                 # rol experto agrónomo
│   │
│   ├── utils/
│   │   ├── data_loader.py     # carga y validación de datos
│   │   ├── knowledge_base.py  # RAG simple
│   │   ├── llm_client.py      # cliente LLM
│   │   ├── model_loader.py    # carga modelo ML
│   │   ├── mqtt_client.py     # publicación de alertas MQTT
│   │   ├── prompts_loader.py  # carga de prompts
│   │   └── report_generator.py # generación PDF
│
├── main.py                    # pipeline principal
├── requirements.txt
├── .env
```

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
