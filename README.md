# RAIN-OLIVAR

**Plataforma geoespacial para análisis de riesgo en olivar mediterráneo.**

Combina enriquecimiento de datos multifuente, predicción ML, análisis IA agronómico e informes PDF en una aplicación Streamlit modular de 4 pestañas.

---

## ¿Qué hace este proyecto?

A partir de shapefiles SIGPAC de parcelas de olivar:

1. **Enriquece** cada parcela con datos meteorológicos, edafológicos, hidrológicos y económicos desde APIs públicas y tablas de referencia locales.
2. **Valida** que el CSV tiene las 22 columnas requeridas por el modelo ML.
3. **Predice** la pérdida de producción (%) y el impacto económico (EUR/ha) usando un modelo sklearn entrenado.
4. **Analiza** cada parcela con IA agronómica (Claude o reglas) siguiendo el prompt estructurado de 7 secciones.
5. **Genera** informes PDF descargables: informe general del cliente o informe individual por parcela.

---

## Instalación

### 1. Clonar repositorio

```bash
git clone <repo_url>
cd LLM_RAIN_OLIVAR
```

### 2. Crear y activar entorno virtual

```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**Linux / Mac:**
```bash
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variable de entorno (opcional)

Para habilitar el análisis IA con Claude, crear un archivo `.env` en la raíz con:

```env
ANTHROPIC_API_KEY=tu_api_key
```

Si no se configura, la app usa análisis basado en reglas agronómicas automáticamente.

---

## Ejecución

```bash
streamlit run app/streamlit_app_new.py --server.port 8502
```

La app queda disponible en:

- **Local URL:** http://localhost:8502
- **Network URL:** la que indique Streamlit en consola

> Ejecutar siempre desde la raíz del proyecto (`LLM_RAIN_OLIVAR/`).

---

## Flujo de uso

### Pestaña 1 — 📍 Data

1. Seleccionar cliente en el selector lateral.
2. Revisar mapa de parcelas y tabla base (datos SIGPAC).
3. Completar los 4 campos agronómicos obligatorios por parcela OV:
   - Tipo de olivar, Riego, Variedad, Fenología.
4. Guardar borrador o confirmar datos (100% completitud habilita siguiente fase).
5. Revisar advertencias de calidad de dato (pendiente extrema SIGPAC).

### Pestaña 2 — 🌦️ Enriquecimiento

Obtiene y combina datos de 4 fuentes externas:

| Fuente | Variables | TTL |
|---|---|---|
| **Open-Meteo** | rain_72h_mm, rain_7d_mm, temp_media_7d, humedad_suelo_% | 24 h |
| **SoilGrids ISRIC** | tipo_suelo, drenaje, materia_organica_%, profundidad_suelo_cm | 180 días |
| **Overpass / OSM** | distancia_rio_m | 30 días |
| **Tablas locales** | rendimiento_esperado_kg_ha, precio_mercado_eur_kg, coste_variable_ha | sin vencimiento |

El encharcamiento (`duracion_encharcamiento_dias`) se calcula internamente a partir de lluvia, drenaje y suelo.

Al completarse las 22 columnas, la app muestra el estado **LISTO para ML** y habilita la descarga del CSV para el modelo.

### Pestaña 3 — 🤖 Modelado

1. **Vista general** (sin parcela seleccionada):
   - Estado del modelo (22/22 columnas, parcelas listas, última predicción).
   - Botón **Generar predicción** → ejecuta el modelo sklearn.
   - KPIs: pérdida media, impacto total, parcelas en riesgo.
   - Nota interpretativa automática (condiciones climáticas).
   - Mapa de resultados con 5 modos: Predicción de riesgo, Impacto económico, Encharcamiento estimado, Pendiente, Uso SIGPAC.
   - Selector de mapa base: Claro, OpenStreetMap, Satélite (Esri), Topográfico.
   - Ranking de parcelas prioritarias.

2. **Vista por parcela** (parcela seleccionada en el selector lateral):
   - Ficha completa: datos productivos, resultado ML, mapa centrado.
   - Variables meteorológicas, de suelo y topografía por tabs.
   - Factores de riesgo detectados por reglas.
   - Interpretación rápida automática.

### Pestaña 4 — 🧠 IA e Informe

1. **Vista general**:
   - Resumen ejecutivo, riesgos principales, parcelas prioritarias, recomendaciones (corto/medio plazo/seguimiento).
   - **Botón PDF** → genera informe completo del cliente.

2. **Vista por parcela**:
   - Análisis agronómico completo (7 secciones del prompt estándar).
   - **Botón PDF** → genera informe individual de la parcela.

---

## Colores de riesgo

| Nivel | Color | Umbral pérdida |
|---|---|---|
| Bajo | 🟢 Verde | < 5% |
| Medio | 🟡 Amarillo | 5 – 15% |
| Alto | 🟠 Naranja | 15 – 30% |
| Muy alto | 🔴 Rojo | > 30% |

---

## Estructura del proyecto

```text
LLM_RAIN_OLIVAR/
│
├── app/
│   ├── streamlit_app_new.py       # Orquestador principal (4 pestañas)
│   └── components/
│       ├── page_data_parcela.py   # Pestaña Data
│       ├── page_enrichment.py     # Pestaña Enriquecimiento
│       ├── page_modeling.py       # Pestaña Modelado (general + por parcela)
│       ├── page_ia_informe.py     # Pestaña IA e Informe
│       ├── charts.py              # Gráficos Plotly
│       └── kpi_cards.py           # Tarjetas KPI
│
├── data/
│   ├── clientes_shp/              # Shapefiles SIGPAC por cliente
│   ├── client_inputs/             # Datos del agricultor guardados
│   ├── api_cache/                 # Cache local de APIs
│   │   ├── weather/               # Open-Meteo
│   │   ├── soil/                  # SoilGrids
│   │   └── hydrology/             # Overpass/OSM
│   ├── reference/                 # Tablas de referencia económica
│   ├── enriched/                  # CSV consolidados (25 cols interno / 22 cols ML)
│   ├── predictions/               # Resultados del modelo ML por cliente
│   ├── llm_outputs/               # Análisis IA guardados (JSON)
│   ├── reports/                   # Informes PDF generados
│   └── output/
│       └── modelo_olivar.pkl      # Modelo ML entrenado (sklearn Pipeline)
│
├── src/
│   ├── geo/
│   │   ├── geodata_loader.py      # Carga shapefiles SIGPAC
│   │   ├── parcels_processor.py   # Calcula superficies y parcel_id
│   │   ├── usage_filter.py        # Filtra parcelas OV
│   │   └── map_builder.py         # Mapas Folium con 5 modos y basemaps
│   │
│   └── features/
│       ├── build_input_from_parcels.py    # CSV base + SCHEMA_COLUMNS (22 cols)
│       ├── persistence.py                 # Persistencia datos agricultor
│       ├── farmer_inputs.py               # Validación y opciones agronómicas
│       ├── weather_enrichment.py          # Open-Meteo con cache y fallback
│       ├── soil_enrichment.py             # SoilGrids con cache y fallback
│       ├── hydrology_enrichment.py        # Overpass con cache y fallback
│       ├── economic_enrichment.py         # Enriquecimiento económico local
│       ├── waterlogging_calculator.py     # Cálculo encharcamiento estimado
│       ├── enrichment_assembler.py        # Integración + flag ready_for_ml
│       ├── input_validator.py             # Validación CSV 22 columnas
│       ├── prediction_perdida.py          # Predicción ML (joblib)
│       ├── llm_engine.py                  # Análisis IA (Claude o reglas)
│       └── pdf_generator.py              # Generación informes PDF (fpdf2)
│
├── docs/
│   └── DICCIONARIO_VARIABLES_OLIVAR.md   # Documentación del schema
│
├── src/prompts/
│   └── analysis_prompt.txt               # Prompt agronómico (7 secciones)
│
├── requirements.txt
├── .env                                  # ANTHROPIC_API_KEY (opcional)
└── README.md
```

---

## Variables del modelo ML (22 columnas)

| Columna | Tipo | Fuente |
|---|---|---|
| parcel_id | string | SIGPAC |
| zona_provincia | string | SIGPAC |
| tipo_olivar | string | Agricultor |
| riego | string | Agricultor |
| superficie_ha | float | SIGPAC (calculado) |
| variedad | string | Agricultor |
| estado_fenologico | string | Agricultor |
| tipo_suelo | string | SoilGrids |
| drenaje | string | SoilGrids |
| pendiente_% | float | SIGPAC |
| distancia_rio_m | float | Overpass |
| altitud_m | float | SIGPAC |
| rain_72h_mm | float | Open-Meteo |
| rain_7d_mm | float | Open-Meteo |
| temp_media_7d | float | Open-Meteo |
| humedad_suelo_% | float | Open-Meteo |
| profundidad_suelo_cm | float | SoilGrids |
| materia_organica_% | float | SoilGrids |
| rendimiento_esperado_kg_ha | float | Tablas locales |
| precio_mercado_eur_kg | float | Tablas locales |
| coste_variable_ha | float | Tablas locales |
| duracion_encharcamiento_dias | float | Calculado |

---

## Manejo de errores en APIs

Cuando una API falla, el dato anterior válido se conserva y se marca como `stale`.
El flag `ready_for_ml` solo se activa cuando las 22 columnas están completas sin errores.

| Estado | Descripción |
|---|---|
| `ok` | Dato fresco desde API |
| `stale` | Dato anterior conservado (API falló) |
| `stale_weather` | Dato meteorológico anterior conservado |
| `error` | API falló sin dato previo |
| `no_data` | Sin dato y sin intento previo |

---

## Outputs generados

| Archivo | Descripción |
|---|---|
| `data/enriched/{client_id}_input_enriched.csv` | CSV consolidado interno (25 cols) |
| `data/predictions/{client_id}_predictions.csv` | Resultados del modelo ML |
| `data/llm_outputs/{client_id}_general.json` | Análisis IA general guardado |
| `data/llm_outputs/{client_id}_{parcel_id}.json` | Análisis IA por parcela guardado |
| `data/reports/{client_id}_report.pdf` | Informe PDF general |
| `data/reports/{client_id}_{parcel_id}_report.pdf` | Informe PDF individual |

---

## Modelo ML

El modelo está en:

```text
data/output/modelo_olivar.pkl
```

Es un `sklearn.pipeline.Pipeline` cargado con `joblib`. Predice `pct_perdida_pred` (fracción 0–1, se muestra como % en la UI). Los valores negativos se recortan a 0.

---

## Análisis IA (7 secciones)

El análisis agronómico sigue el prompt en `src/prompts/analysis_prompt.txt`:

1. Evaluación agronómica
2. Riesgos detectados
3. Estimación de pérdida
4. Impacto económico
5. Recomendaciones técnicas
6. Acción automática sugerida
7. Nivel de riesgo

Si `ANTHROPIC_API_KEY` está configurada, usa Claude (claude-haiku-4-5). Si no, usa análisis basado en reglas agronómicas.

---

## Notas de desarrollo

- Los datos del agricultor se guardan en `data/client_inputs/` por cliente.
- El cache de APIs usa TTL diferencial (24h meteo, 30d hidrología, 180d suelo).
- La clave de merge entre shapefiles y predicciones es siempre `parcel_id` (nunca `parcel_uid`, que es autoincremental en el CSV de predicciones).
- El CSV para el modelo ML exporta exactamente 22 columnas en el orden correcto según `SCHEMA_COLUMNS`.
- El CSV interno guarda 25 columnas (22 + `_ready_for_ml`, `_cols_complete`, `_n_parcelas_ov`).
