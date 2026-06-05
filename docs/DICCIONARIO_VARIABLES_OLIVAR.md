# Diccionario de variables — RAIN-OLIVAR

> **Versión:** MVP Geoespacial v3 — Manejo robusto de errores + ready_for_ml  
> **Última actualización:** 2026-06-05  
> **Módulos implicados:** `src/geo/`, `src/features/`, `src/integrations/`, `app/streamlit_app.py`

---

## 0. Introducción: Manejo robusto de errores y conservación de datos

Esta versión implementa una **estrategia de recuperación ante fallos de APIs** que garantiza que el CSV consolidado nunca pierde datos válidos previos.

### Principio fundamental

**Nunca sobrescribir un dato válido con NaN/error.**

Si una consulta a API falla:
- Se **mantiene el dato anterior válido** (marcado como "stale")
- Se **reintenta solo la parcela fallida** (en modo "errors_only")
- Se **permite forzar actualización completa** (modo "force_all" conservando fallidas)

---

## 1. Propósito del documento

Este documento describe la **trazabilidad completa de las variables** utilizadas y generadas por la aplicación geoespacial RAIN-OLIVAR.

El proyecto parte de **shapefiles de parcelas y recintos SIGPAC** por cliente, ubicados en `data/clientes_shp/`. A partir de ellos, la aplicación:

1. Lee los polígonos y sus atributos.
2. Calcula superficie en hectáreas desde la geometría.
3. Asigna un identificador único a cada parcela.
4. Enriquece con datos del agricultor, APIs externas y tablas locales.
5. Genera un **CSV consolidado (22 columnas)** listo para modelo ML.
6. Valida con **flag ready_for_ml** que bloquea predicción si hay datos incompletos.

El objetivo final es alimentar el modelo ML con todas las variables necesarias para predecir el porcentaje de pérdida de producción y el impacto económico por hectárea ante eventos de lluvia intensa.

---

## 2. Estrategia de cache y recuperación ante errores

### Estados de datos por fuente

Cada variable en el CSV consolidado puede tener estos estados (guardados en columnas de status):

| Estado | Significado | Incluido en CSV | Acción |
|---|---|---|---|
| **ok** | Dato nuevo exitoso de API / cálculo correcto | SÍ | Usar tal cual |
| **stale** | Dato anterior válido mantenido tras fallo de API | SÍ | Usar pero marcar en UI |
| **error** | Consulta falló y sin dato previo válido | NO | Bloquea ready_for_ml |
| **no_data** | Sin dato y sin intento anterior | NO | Bloquea ready_for_ml |

### Estrategia por fuente de datos

| Fuente | Cache TTL | Ubicación | Modo | Fallback |
|---|---|---|---|---|
| **SoilGrids** | 180 días | `data/api_cache/soil/` | "errors_only" / "force_all" | Conserva previo, marca "stale" |
| **Overpass** | 30 días | `data/api_cache/hydrology/` | "errors_only" / "force_all" | Conserva previo, marca "stale" |
| **Open-Meteo** | 24 horas | `data/api_cache/weather/` | "all" (actualiza siempre) | Conserva previo, marca "stale_weather" |
| **Tablas locales** | sin vencimiento | `data/reference/` | directo | Valor por defecto |

### Flujo de recuperación

1. **Consulta → OK**: Guarda dato nuevo, status="ok"
2. **Consulta → ERROR** + dato previo válido: Mantiene previo, status="stale"
3. **Consulta → ERROR** + sin dato previo: Status="error", bloquea ready_for_ml
4. **Reintentar (errors_only)**: Solo parcelas con error o sin dato
5. **Forzar actualización (force_all)**: Todas, pero conserva fallidas anteriores

---

## 2.2. Fuentes de datos actuales

| Fuente | Ruta / Módulo | Estado | Descripción |
|---|---|---|---|
| Shapefile cliente 1 | `data/clientes_shp/cliente_1/` | ✅ Implementado | 33 recintos SIGPAC, CRS EPSG:32630, provincia 18 (Granada) |
| Shapefile cliente 2 | `data/clientes_shp/cliente_2/` | ✅ Implementado | 8 recintos SIGPAC, CRS EPSG:32630, provincia 18 (Granada) |
| Geometría del polígono | campo `geometry` del shapefile | ✅ Implementado | Base para cálculo de área, visualización en mapa y centroides |
| CSV base exportado | generado por `build_input_from_parcels.py` | ✅ Implementado | 22 columnas; esquema compatible con modelo ML |
| Datos del agricultor | app Streamlit (persistencia en `data/client_inputs/`) | ✅ Implementado | Variedad, riego, fenología, estado |
| API meteorológica | Open-Meteo REST API | ✅ Implementado | Precipitación 72h/7d, temperatura media 7d, humedad suelo |
| API edafológica / suelo | SoilGrids v2 REST API | ✅ Implementado | Tipo suelo, drenaje, materia orgánica, profundidad |
| Análisis hidrológico | Overpass API / OpenStreetMap | ✅ Implementado | Distancia al cauce más cercano |
| Tablas de referencia | CSV locales en `data/reference/` | ✅ Implementado | Rendimiento esperado, precios mercado, costes variables |
| Cálculo interno | `waterlogging_calculator.py` | ✅ Implementado | Duración encharcamiento (días) |

---

## 3. Variables extraídas directamente del shapefile

Estas variables **ya existen en el shapefile** y la aplicación las lee, renombra o mapea. **No se calculan en la app**; se toman tal cual del atributo SIGPAC.

### 3.1 Columnas completas del shapefile SIGPAC (ambos clientes)

| Campo original en shapefile | Tipo | Descripción SIGPAC |
|---|---|---|
| `dn_oid` | numérico | Identificador interno SIGPAC del recinto |
| `provincia` | entero | Código INE de provincia. Ambos clientes: `18` (Granada) |
| `municipio` | entero | Código INE de municipio. Ambos clientes: `116` |
| `agregado` | entero | Código de agregado catastral |
| `zona` | entero | Código de zona catastral |
| `poligono` | entero | Número de polígono catastral |
| `parcela` | entero | Número de parcela catastral |
| `recinto` | entero | Número de recinto dentro de la parcela |
| `dn_surface` | float | Superficie del recinto en m² declarada en SIGPAC |
| `pendiente_` | entero | Valor de pendiente asociado al recinto (ver sección 3.2) |
| `altitud` | entero | Altitud en metros del recinto (ver sección 3.3) |
| `csp` | float/nulo | Campo SIGPAC. En los datos actuales aparece como nulo |
| `coef_regad` | entero | Coeficiente de regadío SIGPAC (0 = secano, 100 = regadío pleno) |
| `uso_sigpac` | texto | Código de uso del recinto SIGPAC (ver sección 7) |
| `incidencia` | texto | Códigos de incidencias SIGPAC asociadas al recinto (ver nota) |
| `region` | float | Código de región o zona SIGPAC |
| `geometry` | geometría | Polígono en CRS EPSG:32630 |

> **Nota sobre `incidencia`:** Contiene códigos de incidencias SIGPAC como `'199'`, `'14'`, `'12,74'`, `'199,231,74'`. Pueden indicar restricciones, solapamientos o condicionantes del recinto. Actualmente no se usan en la app. Pendiente de interpretación con tabla oficial SIGPAC.

### 3.2 Variable `pendiente_`

| Atributo | Detalle |
|---|---|
| **Campo original** | `pendiente_` |
| **Variable en app / CSV** | `pendiente_%` |
| **Tipo** | Entero |
| **Rango observado** | cliente_1: 18–108 · cliente_2: 31–100 |
| **Estado** | ✅ Implementada (leída y renombrada) |

La app lee este campo directamente del shapefile y lo renombra a `pendiente_%` en el CSV base. **No se calcula en la app.**

> ⚠️ **Pendiente de validación:** Los valores enteros observados (18–108) necesitan contraste con la documentación oficial SIGPAC para confirmar si representan:
> - Porcentaje directo (18 = 18%, 108 = 108%) — valores posibles para olivar en sierra
> - Valor en por-mil (108 = 10.8%) — interpretación alternativa más habitual en cartografía
> - Un código de clasificación de pendiente
>
> Se recomienda contrastar con la ficha técnica del FEGA o la comunidad autónoma correspondiente antes de usarlo como entrada directa al modelo ML.

### 3.3 Variable `altitud`

| Atributo | Detalle |
|---|---|
| **Campo original** | `altitud` |
| **Variable en app / CSV** | `altitud_m` |
| **Tipo** | Entero |
| **Rango observado** | cliente_1: 1106–1212 m · cliente_2: 1192–1195 m |
| **Estado** | ✅ Implementada (leída y renombrada) |

Altitud en metros del recinto según el shapefile SIGPAC. **No se calcula en la app.**

> **Nota:** El atributo `altitud` en SIGPAC suele representar la altitud media o representativa del recinto asignada durante la digitalización. No proviene de un MDT calculado por la app. Si se requiere mayor precisión, deberá cruzarse con un modelo digital del terreno (MDT).

### 3.4 Variable `provincia` → `zona_provincia`

| Atributo | Detalle |
|---|---|
| **Campo original** | `provincia` |
| **Variable en app / CSV** | `zona_provincia` |
| **Tipo** | Entero → texto |
| **Valores observados** | `18` → `"Granada"` |
| **Estado** | ✅ Implementada (mapeada a nombre) |

La app mapea el código INE de provincia a su nombre mediante un diccionario en `build_input_from_parcels.py`. Provincias actualmente mapeadas: Granada (18), Córdoba (14), Sevilla (41), Jaén (23), Cádiz (11), Málaga (29), Huelva (21), Almería (4).

### 3.5 Variable `dn_surface`

| Atributo | Detalle |
|---|---|
| **Campo original** | `dn_surface` |
| **Variable en app / CSV** | No exportada directamente; usada como referencia interna |
| **Tipo** | Float |
| **Unidad** | Metros cuadrados (m²) |
| **Rango observado** | cliente_1: 108.68–27129.57 m² · cliente_2: 58.15–18390.00 m² |
| **Estado** | Disponible en shapefile, no exportada al CSV base actualmente |

> **Validación realizada:** La diferencia entre `area_ha_calc` (calculada desde geometría) y `dn_surface / 10000` es **exactamente 0.0000** para todos los recintos de ambos clientes. Las geometrías son consistentes con las superficies declaradas en SIGPAC. La app utiliza el área calculada desde la geometría como fuente primaria.

---

## 4. Variables calculadas por la aplicación

Estas variables **no existen en el shapefile** y son generadas internamente por la app.

### 4.1 `parcel_id`

| Atributo | Detalle |
|---|---|
| **Fuente** | Índice interno del GeoDataFrame + nombre del cliente |
| **Método** | `f"{client_id}_P{str(i+1).zfill(3)}"` |
| **Ejemplos** | `cliente_1_P001`, `cliente_1_P033`, `cliente_2_P008` |
| **Estado** | ✅ Implementado |

Identificador único generado para cada polígono/recinto cargado. Se construye concatenando el identificador del cliente y un número consecutivo con tres dígitos y cero a la izquierda.

> ⚠️ **Pendiente de revisión:** Valorar si el `parcel_id` definitivo debería construirse a partir de campos SIGPAC (provincia + municipio + polígono + parcela + recinto) para garantizar unicidad real entre campañas y clientes. El consecutivo actual puede repetirse si se añaden recintos o se reordena el shapefile.

### 4.2 `client_id`

| Atributo | Detalle |
|---|---|
| **Fuente** | Nombre de la carpeta seleccionada en la sidebar |
| **Método** | Valor del selector de cliente |
| **Ejemplos** | `cliente_1`, `cliente_2` |
| **Estado** | ✅ Implementado |

### 4.3 `area_ha_calc`

| Atributo | Detalle |
|---|---|
| **Fuente** | Geometría del polígono en CRS métrico |
| **Unidad** | Hectáreas (ha) |
| **Estado** | ✅ Implementado |

**Proceso de cálculo:**

La superficie se calcula a partir de la geometría del polígono. Para garantizar resultados correctos, el cálculo **no se realiza en coordenadas geográficas** (WGS84 / EPSG:4326), donde las unidades son grados y el área sería incorrecta.

El proceso es:

1. Se verifica que el CRS del shapefile sea métrico. Si no lo es, se reproyecta a `EPSG:32630`.
2. Se calcula el área en metros cuadrados directamente desde la geometría.
3. Se divide entre 10.000 para convertir a hectáreas.

```
area_ha_calc = geometry.area [m²] / 10.000
```

Luego, para la **visualización en el mapa**, los polígonos se convierten a `EPSG:4326` (WGS84). Los centroides también se calculan en el CRS métrico y se reproyyectan, no en el geográfico.

> **Nota técnica:** El CRS métrico utilizado actualmente es **EPSG:32630** (WGS84 / UTM zona 30N), que es el sistema nativo de los shapefiles SIGPAC de estos clientes. Existe también **EPSG:25830** (ETRS89 / UTM zona 30N), que es el sistema oficial en la cartografía española desde 2015. Ambos son UTM zona 30N pero con datum diferente (WGS84 vs ETRS89). La diferencia es milimétrica para uso práctico, pero se recomienda validar cuál corresponde exactamente a la fuente SIGPAC utilizada.

### 4.4 KPIs geoespaciales

| Variable KPI | Cálculo | Estado |
|---|---|---|
| `n_parcelas` | `len(gdf)` | ✅ Implementado |
| `superficie_total_ha` | `gdf["area_ha_calc"].sum().round(2)` | ✅ Implementado |
| `superficie_media_ha` | `gdf["area_ha_calc"].mean().round(2)` | ✅ Implementado |
| `superficie_max_ha` | `gdf["area_ha_calc"].max().round(2)` | ✅ Implementado |
| `superficie_min_ha` | `gdf["area_ha_calc"].min().round(2)` | ✅ Implementado |

---

## 5. Variables a completar por el agricultor / usuario

Estas variables **no se pueden extraer del shapefile ni de APIs automáticas**. Requieren un formulario o input directo del agricultor. Actualmente aparecen vacías en el CSV base exportado.

| Variable CSV | Fuente prevista | Estado | Descripción |
|---|---|---|---|
| `tipo_olivar` | Agricultor / formulario | ⏳ Pendiente | Sistema productivo: Tradicional, Intensivo, Superintensivo |
| `riego` | Agricultor / formulario | ⏳ Pendiente | Condición hídrica: Secano, Regadío (también puede inferirse de `coef_regad`) |
| `variedad` | Agricultor / formulario | ⏳ Pendiente | Variedad principal de olivo: Picual, Manzanilla, Hojiblanca, Arbequina, etc. |
| `estado_fenologico` | Agricultor / formulario | ⏳ Pendiente | Estado del cultivo al momento del análisis: Brotación, Floración, Cuajado, Engorde, etc. |
| `tipo_suelo` | Agricultor o API edafológica | ⏳ Pendiente | Textura del suelo: Franco, Arcilloso, Arenoso, Franco-arcilloso, Limoso |
| `drenaje` | Agricultor o API edafológica | ⏳ Pendiente | Condición de drenaje: Bueno, Moderado, Malo |
| `rendimiento_esperado_kg_ha` | Agricultor / histórico de campaña | ⏳ Pendiente | Producción esperada en kg/ha en condiciones normales |
| `precio_mercado_eur_kg` | Agricultor / cotización de mercado | ⏳ Pendiente | Precio estimado del aceite o aceituna en €/kg |
| `coste_variable_ha` | Agricultor / análisis económico | ⏳ Pendiente | Coste variable de producción por hectárea en € |

> **Nota sobre `riego`:** El shapefile incluye el campo `coef_regad` (coeficiente de regadío SIGPAC). Valor 0 = secano, 100 = regadío pleno. Esto podría permitir inferir automáticamente la variable `riego` sin necesidad del formulario del agricultor. **Pendiente de implementar este mapeo.**

---

## 6. Variables previstas desde APIs externas

Estas variables **requieren integración con servicios externos** en fases futuras. Actualmente aparecen vacías en el CSV base.

| Variable CSV | Fuente futura | Estado | Descripción |
|---|---|---|---|
| `rain_72h_mm` | API meteorológica (AEMET, ERA5, OpenWeatherMap) | ⏳ Pendiente | Precipitación acumulada en las últimas 72 horas en el punto de la parcela |
| `rain_7d_mm` | API meteorológica | ⏳ Pendiente | Precipitación acumulada en los últimos 7 días |
| `temp_media_7d` | API meteorológica | ⏳ Pendiente | Temperatura media de los últimos 7 días en °C |
| `humedad_suelo_%` | API de satélite / sensores / SMOS-SMAP | ⏳ Pendiente | Humedad volumétrica del suelo estimada en % |
| `profundidad_suelo_cm` | API edafológica (ESDAC, SoilGrids, BDBC) | ⏳ Pendiente | Profundidad efectiva del suelo en cm |
| `materia_organica_%` | API edafológica o análisis de laboratorio | ⏳ Pendiente | Porcentaje de materia orgánica del suelo |
| `distancia_rio_m` | Análisis geoespacial + Red Hidrográfica Nacional | ⏳ Pendiente | Distancia en metros desde el centroide o borde de la parcela al cauce fluvial más cercano |
| `duracion_encharcamiento_dias` | Modelo heurístico / reglas / API hidrológica | ⏳ Pendiente | Estimación de la duración del encharcamiento tras el evento de lluvia |

> **Nota sobre `distancia_rio_m`:** Es calculable geoespacialmente cruzando los polígonos con la Red Hidrográfica Nacional (RHN) del IGN o el conjunto de datos del MITERD. El centroide de cada parcela ya está calculado en la app (`lat`, `lon`), lo que facilita esta operación en una fase futura.

---

## 7. Códigos de Uso SIGPAC

El campo `uso_sigpac` representa el **uso asignado al recinto SIGPAC**. Un recinto SIGPAC es la unidad básica de gestión: una parte de una parcela catastral con un uso homogéneo. Si una parcela tiene distintos usos, se divide en varios recintos.

### Códigos encontrados en los clientes actuales

| Código | Encontrado en | Significado oficial SIGPAC | Relevancia para el modelo |
|---|---|---|---|
| `OV` | cliente_1 (100%), cliente_2 | Olivar | ✅ Principal — uso de interés agrícola del proyecto |
| `FS` | cliente_2 | Frutal de cáscara (frutos secos: almendro, avellano, etc.) | ℹ️ No olivar — puede excluirse del análisis si se filtra solo OV |
| `TA` | cliente_2 | Tierra arable | ℹ️ Tierra de cultivo arable, no olivar |
| `IM` | cliente_2 | Improductivo | ⚠️ Zona no productiva — excluir del análisis de pérdida |
| `CA` | cliente_2 | Viales / Caminos | ⚠️ Infraestructura — excluir del análisis agrícola |

> **Nota:** La tabla anterior solo incluye los códigos presentes en los shapefiles actuales de `cliente_1` y `cliente_2`. La tabla completa de usos SIGPAC contiene más de 40 códigos y debe contrastarse con la **tabla oficial del FEGA (Fondo Español de Garantía Agraria / MAPA)** o con la documentación de la comunidad autónoma correspondiente (en este caso, Junta de Andalucía - Consejería de Agricultura).

> **Recomendación:** Filtrar los recintos por `uso_sigpac == 'OV'` antes de enviar datos al modelo ML para garantizar que solo se analizan polígonos de olivar. Actualmente la app carga **todos los recintos** del shapefile sin filtrar por uso.

---

## 8. Esquema del CSV base exportado

El CSV base se genera desde `src/features/build_input_from_parcels.py` y se exporta con **separador `;`** (punto y coma), compatible con la configuración regional española de Excel.

> **Importante para el modelo ML:** El archivo `data/input/test_olivar.csv` también usa separador `;`. Asegurar consistencia al completar el CSV base antes de enviarlo al pipeline.

### Columnas del CSV base

| # | Columna CSV | Fuente actual | Estado en export | Observaciones |
|---|---|---|---|---|
| 1 | `parcel_id` | Calculado por app | ✅ Completo | ID único: `cliente_X_PYYY` |
| 2 | `superficie_ha` | Calculado desde geometría | ✅ Completo | Área en ha — idéntica a `dn_surface` validado |
| 3 | `pendiente_%` | Shapefile: `pendiente_` | ✅ Completo si existe | Valor entero SIGPAC — validar unidad |
| 4 | `altitud_m` | Shapefile: `altitud` | ✅ Completo si existe | Altitud media del recinto en metros |
| 5 | `zona_provincia` | Shapefile: `provincia` | ✅ Completo | Mapeado a nombre: `18` → `"Granada"` |
| 6 | `tipo_olivar` | Agricultor | ⬜ Vacío | Pendiente formulario |
| 7 | `riego` | Agricultor / `coef_regad` | ⬜ Vacío | Podría inferirse de `coef_regad` |
| 8 | `variedad` | Agricultor | ⬜ Vacío | Pendiente formulario |
| 9 | `estado_fenologico` | Agricultor | ⬜ Vacío | Pendiente formulario |
| 10 | `tipo_suelo` | Agricultor / API suelo | ⬜ Vacío | Pendiente |
| 11 | `drenaje` | Agricultor / API suelo | ⬜ Vacío | Pendiente |
| 12 | `rendimiento_esperado_kg_ha` | Agricultor / histórico | ⬜ Vacío | Pendiente |
| 13 | `precio_mercado_eur_kg` | Agricultor / mercado | ⬜ Vacío | Pendiente |
| 14 | `coste_variable_ha` | Agricultor | ⬜ Vacío | Pendiente |
| 15 | `rain_72h_mm` | API meteorológica | ⬜ Vacío | Pendiente integración |
| 16 | `rain_7d_mm` | API meteorológica | ⬜ Vacío | Pendiente integración |
| 17 | `temp_media_7d` | API meteorológica | ⬜ Vacío | Pendiente integración |
| 18 | `humedad_suelo_%` | API suelo / satélite | ⬜ Vacío | Pendiente integración |
| 19 | `profundidad_suelo_cm` | API edafológica | ⬜ Vacío | Pendiente integración |
| 20 | `materia_organica_%` | API edafológica / análisis | ⬜ Vacío | Pendiente integración |
| 21 | `distancia_rio_m` | Análisis geoespacial | ⬜ Vacío | Pendiente integración |
| 22 | `duracion_encharcamiento_dias` | Modelo / reglas | ⬜ Vacío | Pendiente integración |

**Total:** 22 columnas · 5 completas automáticamente · 17 pendientes de completar

---

## 9. Estado actual de implementación

| Componente | Estado | Módulo |
|---|---|---|
| Carga de shapefiles por cliente | ✅ Implementado | `geodata_loader.py` |
| Validación de archivos requeridos (.shp, .dbf, .shx, .prj) | ✅ Implementado | `geodata_loader.py` |
| Validación de CRS definido | ✅ Implementado | `geodata_loader.py` |
| Corrección de geometrías inválidas | ✅ Implementado | `parcels_processor.py` |
| Reproyección a CRS métrico para cálculo | ✅ Implementado | `parcels_processor.py` |
| Cálculo de área en hectáreas | ✅ Implementado | `parcels_processor.py` |
| Generación de `parcel_id` | ✅ Implementado | `parcels_processor.py` |
| Cálculo de centroides (métrico → WGS84) | ✅ Implementado | `parcels_processor.py` |
| KPIs geoespaciales | ✅ Implementado | `parcels_processor.py` |
| Visualización de polígonos en mapa Folium | ✅ Implementado | `map_builder.py` |
| Popup con datos de parcela | ✅ Implementado | `map_builder.py` |
| Tabla de parcelas en Streamlit | ✅ Implementado | `streamlit_app.py` |
| Exportación CSV base (separador `;`) | ✅ Implementado | `build_input_from_parcels.py` |
| Filtrado por `uso_sigpac` (solo OV) | ⏳ Pendiente | — |
| Inferencia de `riego` desde `coef_regad` | ⏳ Pendiente | — |
| Formularios de variables del agricultor | ⏳ Pendiente | — |
| APIs meteorológicas | ⏳ Pendiente | — |
| APIs de suelo / edafología | ⏳ Pendiente | — |
| Distancia al río (análisis geoespacial) | ⏳ Pendiente | — |
| Ejecución del modelo ML desde la app | ⏳ Pendiente | — |
| Visualización de riesgo por parcela | ⏳ Pendiente | — |
| Informe PDF desde la app | ⏳ Pendiente | — |

---

## 10. Validaciones pendientes

1. **`pendiente_`:** Confirmar si los valores enteros (ej. 18, 108) representan porcentaje directo, por-mil, o un código de clasificación. Contrastar con la documentación oficial del FEGA/SIGPAC.

2. **`altitud`:** Confirmar si el valor representa altitud media, mínima, máxima o un valor puntual asignado al recinto durante la digitalización SIGPAC.

3. **CRS para cálculo de área:** Ambos shapefiles vienen en EPSG:32630 (WGS84 / UTM 30N). Valorar si debería usarse EPSG:25830 (ETRS89 / UTM 30N), sistema oficial en cartografía española desde 2015. La diferencia práctica es milimétrica para este uso.

4. **`dn_surface` vs `area_ha_calc`:** Diferencia validada como 0.0000 para ambos clientes. Las geometrías son consistentes con las superficies SIGPAC declaradas. Mantener `area_ha_calc` como valor primario.

5. **`parcel_id`:** Evaluar si el identificador consecutivo es suficiente o si debe construirse desde campos SIGPAC (provincia + municipio + polígono + parcela + recinto) para garantizar unicidad permanente entre campañas.

6. **Filtrado por `uso_sigpac`:** El modelo ML está pensado para olivar (OV). Implementar filtro para excluir recintos con `uso_sigpac` distinto de OV antes de ejecutar el modelo (IM, CA, TA, FS no son olivar).

7. **Inferencia de `riego`:** El campo `coef_regad` está disponible en el shapefile (0 = secano, 100 = regadío). Implementar mapeo automático a la variable `riego` del CSV base.

8. **Separador del CSV:** Actualmente la app exporta con `;`. Verificar que el pipeline ML también espera `;` como separador. El archivo `test_olivar.csv` actual usa `;`.

9. **Códigos de `incidencia`:** Documentar los códigos observados (`199`, `14`, `12`, `74`, `231`, `235`) con la tabla oficial SIGPAC de incidencias para evaluar si condicionan el análisis agrícola.

---

## 11. Reglas de documentación del proyecto

- Redactar en **español técnico** claro.
- No documentar variables que no existan en el código o los datos.
- Si una variable viene del shapefile, indicarlo **explícitamente** — no decir que "se calcula".
- Si una variable se calcula en la app, explicar la **fórmula o proceso**.
- Si una variable depende del agricultor, marcarla como **dato de usuario**.
- Si una variable depende de una API futura, marcarla como **pendiente de integración**.
- No modificar el pipeline ML/LLM (`main.py`, `olivar_agent.py`, `prediction_perdida.py`).
- Actualizar este documento cuando se implementen nuevas fuentes de datos o se validen las pendientes.

---

## 12. Filtro operativo por uso SIGPAC

### Por qué es necesario filtrar

Los shapefiles SIGPAC contienen **todos los recintos de una parcela catastral**, independientemente de su uso. Un mismo expediente puede incluir recintos de olivar (OV), tierra arable (TA), improductivo (IM), caminos (CA) o frutos secos (FS). Solo los recintos con `uso_sigpac = "OV"` son relevantes para el modelo ML de predicción de pérdida en olivar.

**Datos observados en los clientes actuales:**

| Cliente | Total recintos | Recintos OV | % superficie OV |
|---|---|---|---|
| cliente_1 | 33 | 33 | 100% |
| cliente_2 | 8 | 1 | 9% |

En `cliente_2`, si no se filtra, se exportarían al modelo 7 recintos que no son olivar.

### Comportamiento del filtro en la app

| Estado del switch | Mapa | Tabla | KPIs | CSV exportado |
|---|---|---|---|---|
| **Activo (solo OV)** | Solo polígonos OV en verde | Solo parcelas OV | Calculados sobre OV | Solo filas OV |
| **Inactivo (todos)** | OV en verde · Otros en gris | Todos los recintos | Calculados sobre total | Todos los recintos |

### Lógica de detección de la columna de uso

El módulo `src/geo/usage_filter.py` detecta la columna de uso probando los siguientes nombres en orden:
`uso_sigpac`, `uso`, `USO_SIGPAC`, `USO`, `uso_sigpac_`

Si no se encuentra ninguna columna de uso, la app muestra una advertencia y continúa sin filtrar.

### Regla de exportación al modelo ML

> Los recintos con `uso_sigpac ≠ OV` **no deben exportarse** al CSV de entrada del modelo ML cuando el filtro OV está activo. Pueden conservarse como contexto visual en el mapa, pero no deben alimentar la predicción de pérdida en olivar.

---

## 13. Variables editables por el agricultor

### Contexto

El CSV base generado desde la app tiene 22 columnas. Solo 5 se rellenan automáticamente desde el shapefile. Las restantes quedan vacías. En esta fase, el agricultor puede completar **4 variables clave** directamente en el editor de la app, sin necesidad de editar el CSV manualmente.

### Variables que completa el agricultor en esta fase

| Variable | Tipo | Opciones disponibles | Por qué la completa el agricultor |
|---|---|---|---|
| `tipo_olivar` | Selector | Tradicional, Intensivo, Superintensivo | Define el sistema productivo; no derivable del shapefile |
| `riego` | Selector | Secano, Riego | Puede confirmarse desde `coef_regad` (pendiente de implementar) |
| `variedad` | Selector | Picual, Hojiblanca, Arbequina, Manzanilla, Cornicabra, Otra, Desconocida | Dato de gestión que no consta en SIGPAC |
| `estado_fenologico` | Selector | Brotacion, Floracion, Cuajado, Engorde, Envero, Maduracion, Reposo, Desconocido | Depende del momento del año; se puede estimar con GDD en fases futuras |

### Variables que NO se piden al agricultor en esta fase

Estas se obtendrán automáticamente en fases futuras desde el shapefile o APIs externas:

| Variable | Fuente prevista |
|---|---|
| `zona_provincia` | Shapefile (ya implementado) |
| `superficie_ha` | Geometría (ya implementado) |
| `pendiente_%` | Shapefile / IGN MDT |
| `altitud_m` | Shapefile / Open-Elevation |
| `tipo_suelo`, `drenaje` | SoilGrids |
| `profundidad_suelo_cm`, `materia_organica_%` | SoilGrids |
| `rain_72h_mm`, `rain_7d_mm`, `temp_media_7d` | Open-Meteo / AEMET |
| `humedad_suelo_%` | Open-Meteo / SoilGrids / satélite |
| `distancia_rio_m` | Overpass API / Red Hidrográfica Nacional IGN |
| `rendimiento_esperado_kg_ha` | ESYRCE MAPA por provincia + tipo_olivar |
| `precio_mercado_eur_kg` | MAPA Precios |
| `coste_variable_ha` | Tabla de referencia por tipo_olivar + riego |
| `duracion_encharcamiento_dias` | Modelo heurístico desde lluvia + drenaje + ETo |

### Persistencia de los datos editados

En el MVP actual, los datos del agricultor se guardan en `st.session_state` mientras la app está abierta. Al cerrar la app o recargar la página, se pierden. Para persistir ediciones entre sesiones, se deberá implementar en una fase futura:
- Guardado en archivo JSON/CSV local por cliente
- O base de datos ligera (SQLite) o en la nube

---

## 14. Variables previstas por API externa

Referencia técnica: documento *AgriAI_Arquitectura*

### Fuentes mapeadas por variable

| Variable CSV | API / Fuente | Endpoint / Dataset | Notas |
|---|---|---|---|
| `rain_72h_mm` | Open-Meteo | `hourly=precipitation` últimas 72h | Gratuita, sin clave API |
| `rain_7d_mm` | Open-Meteo | `hourly=precipitation` últimos 7 días | Idem |
| `temp_media_7d` | Open-Meteo | `hourly=temperature_2m` | Media de los últimos 7 días |
| `humedad_suelo_%` | Open-Meteo | `hourly=soil_moisture_0_to_7cm` | Capa superficial |
| `tipo_suelo` | SoilGrids (ISRIC) | `wrb` clasificación WRB a 250m | Requiere lat/lon del centroide |
| `drenaje` | SoilGrids | Derivado de textura + Ksat | Cálculo combinado |
| `profundidad_suelo_cm` | SoilGrids | `bdod`, `cfvo` profiles | Profundidad efectiva estimada |
| `materia_organica_%` | SoilGrids | `soc` (carbono orgánico) | Conversión a MO × 1.724 |
| `altitud_m` | Open-Elevation / IGN MDT | `/lookup?locations=lat,lon` | Alternativa al valor SIGPAC |
| `pendiente_%` | IGN MDT25 / SRTM | Cálculo a partir del MDT | Más fiable que `pendiente_` SIGPAC |
| `distancia_rio_m` | Overpass API (OpenStreetMap) | `waterway=river|stream` | Distancia desde centroide al cauce |
| `rendimiento_esperado_kg_ha` | ESYRCE (MAPA) | Por provincia + tipo_olivar + riego | Media histórica de la encuesta |
| `precio_mercado_eur_kg` | MAPA Precios | Precio medio semanal aceite/aceituna | Requiere scraping o descarga |
| `coste_variable_ha` | Tabla de referencia | Por tipo_olivar + riego | Estimación basada en datos sectoriales |
| `duracion_encharcamiento_dias` | Modelo interno | Función de lluvia, ETo, drenaje, pendiente | A desarrollar en módulo propio |

### Entradas necesarias para las APIs

Todas las APIs meteorológicas y edafológicas requieren las coordenadas del centroide de cada parcela. Estos ya están calculados en la app (columnas `lat`, `lon` en el GeoDataFrame procesado).


---

## 15. Identificador estable de parcela: `parcel_uid`

### Por qué no es suficiente `parcel_id`

`parcel_id` es un identificador visual (e.g., `cliente_1_P001`) generado por orden de aparición en el shapefile. Si el shapefile se actualiza, cambia el orden de los recintos o se añaden nuevos registros, el consecutivo puede desplazarse y asociar datos de agricultor a la parcela incorrecta.

### Definición de `parcel_uid`

`parcel_uid` es el identificador estable construido a partir de los campos SIGPAC que identifican unívocamente un recinto en el sistema catastral español:

```
parcel_uid = {provincia:02d}-{municipio:03d}-{poligono:05d}-{parcela:05d}-{recinto:03d}
```

**Ejemplo:** `18-116-00503-00065-004`

Este código identifica: provincia 18 (Granada) · municipio 116 · polígono 503 · parcela 65 · recinto 4.

Si los campos SIGPAC no están disponibles (shapefile sin atributos catastrales), se genera un hash SHA-256 de la geometría WKB como fallback: `geo_<16 hex chars>`.

### Comparativa

| Identificador | Generación | Estable | Uso recomendado |
|---|---|---|---|
| `parcel_id` | Consecutivo por shapefile | ❌ Puede cambiar | Visualización en UI, labels en mapa |
| `parcel_uid` | Campos SIGPAC o hash geometría | ✅ Estable | Merge con datos guardados, persistencia |

### Módulo responsable

`src/geo/parcels_processor.py` → función `make_parcel_uid(row)`. Se genera como columna del GeoDataFrame en `process_parcels()`, antes de la conversión a WGS84.

---

## 16. Persistencia de datos del agricultor por cliente

### Ruta de almacenamiento

```
data/client_inputs/
    cliente_1_farmer_inputs.csv
    cliente_2_farmer_inputs.csv
```

Un archivo CSV por cliente. Se usa separador `;` consistente con el resto del proyecto.

### Columnas del archivo persistido

| Columna | Descripción |
|---|---|
| `parcel_uid` | Identificador estable del recinto SIGPAC |
| `parcel_id` | Identificador visual (`cliente_1_P001`) |
| `client_id` | Nombre del cliente |
| `uso_sigpac` | Código de uso del recinto |
| `tipo_olivar` | Dato del agricultor |
| `riego` | Dato del agricultor |
| `variedad` | Dato del agricultor |
| `estado_fenologico` | Dato del agricultor |
| `updated_at` | Timestamp ISO de la última actualización |
| `completion_status` | `"borrador"` o `"completo"` |

### Módulo responsable

`src/features/persistence.py`:
- `save_farmer_inputs(client_id, edited_df, ov_gdf, status)` → guarda el archivo
- `load_farmer_inputs(client_id)` → carga el archivo, devuelve `None` si no existe
- `merge_saved_with_gdf(saved_df, ov_gdf)` → hace merge por `parcel_uid`; las parcelas nuevas se inicializan vacías, las eliminadas del shapefile se descartan
- `get_client_status(client_id)` → devuelve el estado del cliente

### Merge de datos al recargar

```
GDF actual (parcel_uid)  +  CSV guardado (parcel_uid)
            ↓
merge por parcel_uid (left join)
            ↓
Parcelas en GDF pero no en CSV → campos vacíos
Parcelas en CSV pero no en GDF → descartadas
```

---

## 17. Estados del cliente y flujo de validación

### Estados posibles

| Estado | Condición | Acción disponible |
|---|---|---|
| `sin_datos` | No existe `data/client_inputs/{client}_farmer_inputs.csv` | Solo "Guardar borrador" |
| `borrador` | Archivo existe con `completion_status = "borrador"` | "Guardar borrador" siempre; "Confirmar" solo si 100% |
| `completo` | Archivo existe con `completion_status = "completo"` | Listo para fase de APIs |

### Cálculo de completitud

```
completitud (%) = campos_rellenos / (parcelas_OV × 4) × 100
```

Los 4 campos obligatorios por parcela OV son: `tipo_olivar`, `riego`, `variedad`, `estado_fenologico`.

Un campo se considera relleno si su valor es distinto de cadena vacía `""`.

### Reglas de confirmación

- **Guardar borrador**: siempre disponible, guarda aunque esté incompleto.
- **Confirmar datos**: solo disponible cuando `completitud == 100%`. Al confirmar, `completion_status` cambia a `"completo"`.
- El CSV enriquecido descargable muestra el estado ("borrador" o "confirmado") en el nombre del archivo.

### Siguiente fase

Cuando un cliente está en estado `completo`, el archivo `data/client_inputs/{client}_farmer_inputs.csv` + el shapefile son la entrada para la fase de APIs externas que completará automáticamente:
- Variables meteorológicas (Open-Meteo / AEMET)
- Variables de suelo (SoilGrids)
- Distancia al río (Overpass API)
- Rendimiento esperado (ESYRCE MAPA)
- Precio de mercado (MAPA Precios)
- Coste variable (tabla de referencia)
- Duración de encharcamiento (modelo interno)

---

## 18. Estado actualizado de implementación (v2)

| Componente | Estado | Módulo |
|---|---|---|
| `parcel_uid` estable desde campos SIGPAC | ✅ Implementado | `parcels_processor.py` |
| Fallback hash geometría para `parcel_uid` | ✅ Implementado | `parcels_processor.py` |
| Validación de completitud (%) | ✅ Implementado | `farmer_inputs.py` |
| Listado de parcelas con campos faltantes | ✅ Implementado | `farmer_inputs.py` |
| Guardar borrador (siempre) | ✅ Implementado | `persistence.py` + app |
| Confirmar datos (solo 100%) | ✅ Implementado | `persistence.py` + app |
| Persistencia en `data/client_inputs/` | ✅ Implementado | `persistence.py` |
| Carga automática al seleccionar cliente | ✅ Implementado | `streamlit_app.py` |
| Merge por `parcel_uid` en recarga | ✅ Implementado | `persistence.py` |
| Aislamiento entre clientes | ✅ Implementado | `persistence.py` |
| Estado del cliente (sin_datos/borrador/completo) | ✅ Implementado | `persistence.py` + sidebar |
| Barra de completitud visual en tiempo real | ✅ Implementado | `streamlit_app.py` |
| APIs meteorológicas (Open-Meteo/AEMET) | ⏳ Pendiente | — |
| APIs de suelo (SoilGrids) | ⏳ Pendiente | — |
| Distancia al río (Overpass API) | ⏳ Pendiente | — |
| Rendimiento esperado (ESYRCE MAPA) | ⏳ Pendiente | — |
| Precio de mercado (MAPA Precios) | ⏳ Pendiente | — |
| Ejecución ML desde la app | ⏳ Pendiente | — |
| Informe PDF desde la app | ⏳ Pendiente | — |

---

## 19. Enriquecimiento meteorológico — Open-Meteo

### Variables completadas en esta fase

| Variable CSV | Fuente | Cálculo | Unidad |
|---|---|---|---|
| `rain_72h_mm` | Open-Meteo · `hourly.precipitation` | Suma de las últimas 72 entradas horarias | mm |
| `rain_7d_mm` | Open-Meteo · `daily.precipitation_sum` | Suma de los últimos 7 días diarios | mm |
| `temp_media_7d` | Open-Meteo · `daily.temperature_2m_mean` | Media de los últimos 7 días diarios | °C |
| `humedad_suelo_%` | Open-Meteo · `hourly.soil_moisture_0_to_7cm` | Media de las últimas 24 horas válidas × 100 | % |

### Fuente: Open-Meteo

- URL base: `https://api.open-meteo.com/v1/forecast`
- No requiere API key.
- Parámetros usados: `past_days=8`, `forecast_days=1`, `timezone=auto`
- Resolución temporal: horaria para precipitación y humedad de suelo; diaria para temperatura y precipitación acumulada.
- Cobertura global con buena resolución para Andalucía (modelos ERA5-Land y GFS).

> **Nota sobre `humedad_suelo_%`:** Open-Meteo devuelve la humedad volumétrica del suelo 0-7 cm en m³/m³ (rango típico 0.0–0.5). La app la multiplica × 100 para expresarla como porcentaje. No equivale a un porcentaje de capacidad de campo; es una aproximación funcional para el modelo. Se documenta como variable parcial hasta que se integre SoilGrids para contexto edafológico.

### Consulta por centroide de parcela

Cada parcela OV tiene calculados `lat` y `lon` (centroide reproyectado a WGS84) en el GeoDataFrame procesado. Open-Meteo se consulta individualmente para cada centroide, lo que permite capturar variación microclimática entre parcelas.

### Paralelismo

Las consultas se ejecutan en paralelo con `ThreadPoolExecutor(max_workers=5)`. Para 33 parcelas (cliente_1), el tiempo estimado es ~10–20 segundos frente a ~60–90 segundos en secuencial.

### Persistencia del cache meteorológico

```
data/api_cache/weather/
    cliente_1_weather.csv
    cliente_2_weather.csv
```

| Columna | Descripción |
|---|---|
| `parcel_uid` | Identificador estable SIGPAC |
| `parcel_id` | Identificador visual |
| `client_id` | Cliente al que pertenece |
| `lat`, `lon` | Coordenadas WGS84 del centroide |
| `rain_72h_mm` | Precipitación últimas 72 h |
| `rain_7d_mm` | Precipitación últimos 7 días |
| `temp_media_7d` | Temperatura media 7 días |
| `humedad_suelo_%` | Humedad suelo 0-7 cm × 100 |
| `weather_source` | `"open-meteo"` |
| `weather_updated_at` | Timestamp ISO de la consulta |
| `weather_status` | `"ok"` o `"error"` |
| `weather_error` | Mensaje de error si falló |

### Reglas operativas

- La consulta meteorológica solo se habilita si el cliente tiene estado **Completo** (datos del agricultor confirmados al 100%).
- Si una parcela falla (timeout, error HTTP), se registra en `weather_error` y se continúa con las demás.
- El cache se sobrescribe solo para el cliente actualmente seleccionado.
- Los datos del agricultor (`data/client_inputs/`) no se modifican al actualizar el cache meteorológico.
- El CSV completo descargable combina: shapefile + datos agricultor confirmados + datos meteorológicos (solo parcelas con `weather_status = "ok"`).

### Valores de referencia observados (Granada, junio 2026)

| Variable | Valor observado | Interpretación |
|---|---|---|
| `rain_72h_mm` | 0.0 mm | Sin lluvia reciente (temporada seca) |
| `rain_7d_mm` | 0.0 mm | Sin lluvia en la última semana |
| `temp_media_7d` | 24.5 °C | Temperatura de verano típica de Andalucía |
| `humedad_suelo_%` | 7.1% | Suelo seco — condición estival habitual |

### Fuentes alternativas futuras

| Variable | Fuente alternativa | Ventaja |
|---|---|---|
| `rain_72h_mm`, `rain_7d_mm` | AEMET API | Datos oficiales para España |
| `temp_media_7d` | AEMET API | Mayor resolución local |
| `humedad_suelo_%` | SoilGrids, SMOS/SMAP | Contexto edafológico real |

---

## 20. Estado actualizado de implementación (v3 — Meteorología)

| Componente | Estado | Módulo |
|---|---|---|
| Cliente HTTP Open-Meteo | ✅ Implementado | `src/integrations/open_meteo_client.py` |
| Enriquecimiento por parcela (paralelo) | ✅ Implementado | `src/features/weather_enrichment.py` |
| Cache por cliente en `data/api_cache/weather/` | ✅ Implementado | `src/features/weather_enrichment.py` |
| Merge meteo → CSV base | ✅ Implementado | `src/features/build_input_from_parcels.py` |
| Sección meteorológica en app | ✅ Implementado | `app/streamlit_app.py` |
| Control de acceso (solo cliente confirmado) | ✅ Implementado | `app/streamlit_app.py` |
| Gestión de errores parciales por parcela | ✅ Implementado | `src/features/weather_enrichment.py` |
| CSV completo (shapefile + agricultor + meteo) | ✅ Implementado | `app/streamlit_app.py` |
| AEMET como fuente alternativa | ⏳ Pendiente | — |
| SoilGrids (suelo) | ⏳ Pendiente | — |
| Overpass API (distancia río) | ⏳ Pendiente | — |
| ESYRCE MAPA (rendimiento) | ⏳ Pendiente | — |
| MAPA Precios | ⏳ Pendiente | — |
| Ejecución ML desde app | ⏳ Pendiente | — |
| Informe PDF desde app | ⏳ Pendiente | — |

---

## 21. Enriquecimiento de suelo — SoilGrids ISRIC

### Variables completadas en esta fase

| Variable CSV | Fuente | Derivación |
|---|---|---|
| `tipo_suelo` | SoilGrids · clay, sand, silt | Triángulo textural USDA simplificado → términos del modelo |
| `drenaje` | SoilGrids · textura + shapefile pendiente | Clasificación base por textura ajustada por pendiente |
| `materia_organica_%` | SoilGrids · SOC (g/kg) | SOC × 1.724 / 10 (factor Van Bemmelen) |
| `profundidad_suelo_cm` | SoilGrids · cfvo 30-60cm | Proxy por pedregosidad a media profundidad |

### Fuente: SoilGrids v2.0 (ISRIC)

- URL: `https://rest.isric.org/soilgrids/v2.0/properties/query`
- Sin clave API. Gratuito.
- Propiedades consultadas: `clay`, `sand`, `silt`, `soc`, `cfvo`
- Profundidades: `0-5cm`, `5-15cm`, `30-60cm`
- Resolución espacial: ~250 m (modelo global)
- Unidades raw → target: raw / d_factor (d_factor=10 para todas las propiedades)

### Clasificaciones derivadas

**Textura (tipo_suelo):**

| Condición | Término modelo |
|---|---|
| clay ≥ 40% | Arcilloso |
| clay 27-40% | Franco-arcilloso |
| silt ≥ 50%, clay < 27% | Limoso / Franco-limoso |
| sand ≥ 70%, clay < 15% | Arenoso |
| sand 45-70% | Franco-arenoso |
| Resto | Franco |

**Drenaje:**
- Arcilloso → Malo · ajustado a Moderado si pendiente > 15%
- Franco-arcilloso, Limoso → Moderado · ajustado a Bueno si pendiente > 15%
- Franco, Franco-arenoso, Arenoso → Bueno

**Profundidad efectiva (proxy por CFVO a 30-60cm):**

| CFVO 30-60cm | Profundidad estimada |
|---|---|
| ≥ 50% | 35 cm (suelo muy pedregoso) |
| 30-50% | 60 cm |
| 15-30% | 85 cm |
| < 15% | 110 cm |
| Sin dato | 80 cm (valor por defecto) |

**Materia orgánica:**
```
MO% = SOC (g/kg) × 1.724 / 10
```
Factor Van Bemmelen = 1.724 (relación C/MO estándar).

### Valores observados en Granada (jun 2026)

| Variable | Valor | Interpretación |
|---|---|---|
| clay% (0-15cm) | 21.85% | Textura Franco |
| sand% (0-15cm) | 39.95% | Franco |
| silt% (0-15cm) | 38.20% | Franco |
| soc (0-5cm) | 21.7 g/kg | MO ≈ 3.74% — buen contenido para olivar |
| cfvo (30-60cm) | 13.7% | Moderadamente pedregoso → ~85-110 cm |
| tipo_suelo | Franco | Coherente con suelo de olivar mediterráneo |
| drenaje | Bueno | Esperado con textura franca y pendiente media |

### Limitaciones de SoilGrids

- Resolución 250m: una sola parcela pequeña puede caer en un píxel representativo de la zona general, no de su suelo específico.
- Los valores son estadísticos (media del modelo) — no reemplazan análisis de suelo de laboratorio.
- `profundidad_suelo_cm` es un proxy, no una medición directa.
- `drenaje` es una clasificación simplificada — puede diferir del drenaje real medido en campo.
- Se recomienda validar con análisis de suelo reales cuando sea posible.

### Cache de suelo

```
data/api_cache/soil/
    cliente_1_soil.csv
    cliente_2_soil.csv
```

| Columna | Descripción |
|---|---|
| `parcel_uid` | Identificador estable SIGPAC |
| `parcel_id` | Identificador visual |
| `clay_%` / `sand_%` / `silt_%` | Textura 0-15cm promedio (%) |
| `soc_g_kg` | SOC 0-5cm (g/kg) |
| `materia_organica_%` | MO derivada (%) |
| `cfvo_%` | Fragmentos gruesos 30-60cm (%) |
| `tipo_suelo` | Textura clasificada |
| `drenaje` | Drenaje estimado |
| `profundidad_suelo_cm` | Profundidad efectiva estimada |
| `soil_status` | `"ok"` o `"error"` |
| `soil_error` | Mensaje si falló |

---

## 22. CSV consolidado por cliente

### Arquitectura de caches y salidas

```
Fuentes:
  data/client_inputs/{client}_farmer_inputs.csv  ← agricultor confirmado
  data/api_cache/weather/{client}_weather.csv    ← Open-Meteo
  data/api_cache/soil/{client}_soil.csv          ← SoilGrids

Salida consolidada:
  data/enriched/{client}_input_enriched.csv      ← 22 columnas modelo
```

### Módulo responsable

`src/features/enrichment_assembler.py` → función `assemble_enriched_csv()`.

El ensamblador:
1. Construye el CSV base desde el shapefile + agricultor + meteorología (`build_base_input`)
2. Fusiona los datos de suelo por `parcel_id`
3. Guarda en `data/enriched/{client_id}_input_enriched.csv`
4. Retorna el DataFrame con las 22 columnas del modelo

### Cobertura por fuente (cliente_2, jun 2026)

| Fuente | Columnas | Completitud |
|---|---|---|
| Shapefile | parcel_id, superficie_ha, pendiente_%, altitud_m, zona_provincia | 100% |
| Agricultor | tipo_olivar, riego, variedad, estado_fenologico | 100% (si confirmado) |
| Meteorología | rain_72h_mm, rain_7d_mm, temp_media_7d, humedad_suelo_% | 100% |
| Suelo | tipo_suelo, drenaje, profundidad_suelo_cm, materia_organica_% | 100% |
| APIs pendientes | rendimiento_esperado_kg_ha, precio_mercado_eur_kg, coste_variable_ha, distancia_rio_m, duracion_encharcamiento_dias | 0% (pendiente) |

**Total implementado: 17/22 columnas (77%). Quedan 5 columnas para fases futuras.**

---

## 23. Estado actualizado de implementación (v4 — Suelo + Consolidado)

| Componente | Estado | Módulo |
|---|---|---|
| Cliente HTTP SoilGrids v2 | ✅ Implementado | `src/integrations/soilgrids_client.py` |
| Clasificación textural USDA | ✅ Implementado | `src/features/soil_enrichment.py` |
| Clasificación drenaje | ✅ Implementado | `src/features/soil_enrichment.py` |
| Cálculo MO% desde SOC | ✅ Implementado | `src/features/soil_enrichment.py` |
| Proxy profundidad desde CFVO | ✅ Implementado | `src/features/soil_enrichment.py` |
| Cache suelo por cliente | ✅ Implementado | `src/features/soil_enrichment.py` |
| Ensamblador CSV consolidado | ✅ Implementado | `src/features/enrichment_assembler.py` |
| Cobertura por fuente | ✅ Implementado | `src/features/enrichment_assembler.py` |
| Sección suelo en app | ✅ Implementado | `app/streamlit_app.py` |
| Descarga CSV consolidado | ✅ Implementado | `app/streamlit_app.py` |
| 17/22 columnas del modelo rellenas automáticamente | ✅ Implementado | Pipeline completo |
| Overpass API (distancia_rio_m) | ⏳ Pendiente | — |
| ESYRCE MAPA (rendimiento) | ⏳ Pendiente | — |
| MAPA Precios | ⏳ Pendiente | — |
| duracion_encharcamiento_dias (modelo interno) | ⏳ Pendiente | — |
| Ejecución ML desde app | ⏳ Pendiente | — |
| Informe PDF desde app | ⏳ Pendiente | — |

---

## 24. Enriquecimiento hidrológico — Overpass / OpenStreetMap

### Variable completada

| Variable CSV | Fuente | Método |
|---|---|---|
| `distancia_rio_m` | Overpass API · OSM | Haversine desde centroide parcela al agua más cercana |

### Estrategia de consulta

Una sola consulta Overpass cubre **todas las parcelas del cliente** usando la bbox expandida:
```
bbox_expandida = bounds(OV parcelas) + radio_5km en cada dirección
```
Esto evita N llamadas individuales y respeta los rate limits del servicio.

Tags OSM consultados: `waterway=river|stream|ditch`, `natural=water`

Servidores disponibles (fallback):
1. `overpass-api.de`
2. `lz4.overpass-api.de`
3. `overpass.kumi.systems`

### Cálculo de distancia

Se usa la fórmula de Haversine para calcular la distancia desde el centroide de la parcela (en WGS84) hasta el centro de cada elemento OSM encontrado:

```
distancia_rio_m = haversine(lat_parcela, lon_parcela, lat_water, lon_water)
```

La distancia se calcula al **centro del bounding box** del elemento más cercano (para ways/ríos). Para nodos (fuentes, balsas), se usa la posición directa.

### Estados posibles

| `hydrology_status` | Significado |
|---|---|
| `ok` | Elemento de agua encontrado dentro del radio |
| `beyond_radius` | Encontrado pero a más de 5km |
| `no_water_found` | No se encontró ningún cauce en el bbox |
| `error` | Fallo de red o API |

### Cache hidrológico

```
data/api_cache/hydrology/
    cliente_1_hydrology.csv
    cliente_2_hydrology.csv
```

| Columna | Descripción |
|---|---|
| `distancia_rio_m` | Distancia al agua más cercana (m) |
| `nearest_water_type` | Tipo OSM: river, stream, ditch, basin, water... |
| `nearest_water_name` | Nombre del cauce si está etiquetado en OSM |
| `overpass_radius_m` | Radio de búsqueda usado (5000 m por defecto) |
| `hydrology_status` | ok / no_water_found / error |

### Valores observados (cliente_2, Granada)

- `distancia_rio_m` = 346 m (`type=basin` sin nombre)
- Coherente con zona de la sierra granadina (pequeñas balsas y cauces estacionales)

---

## 25. Cálculo de duración de encharcamiento

### Variable completada

| Variable CSV | Fuente | Método |
|---|---|---|
| `duracion_encharcamiento_dias` | Cálculo interno | Reglas basadas en lluvia, suelo, pendiente, distancia al agua |

### Fórmula

```
duracion = base_rain × factor_drenaje × factor_pendiente + ajuste_humedad + ajuste_rio
duracion = clip(duracion, 0, 7)
```

**Base por lluvia 72h (mm):**

| Rango | Base (días) |
|---|---|
| < 20 mm | 0.0 |
| 20–50 mm | 0.5 |
| 50–100 mm | 1.5 |
| ≥ 100 mm | 3.0 |

**Factor drenaje:** Bueno=0.5 · Moderado=1.0 · Malo=1.5

**Factor pendiente:** >10%=0.6 · 3-10%=1.0 · <3%=1.3

**Ajuste humedad suelo:** >60%=+1.0 · 30-60%=+0.5 · <30%=+0.0

**Ajuste proximidad al río:** < 100m = +0.5 días

**Máximo:** 7 días

### Clasificación de riesgo

| Duración | Nivel |
|---|---|
| 0 días | Sin riesgo |
| 0–1 días | Bajo |
| 1–3 días | Moderado |
| > 3 días | Alto |

### Limitaciones importantes

> Esta fórmula es una **aproximación heurística para MVP**. No es un modelo hidrológico certificado. Los valores se basan en relaciones físicas razonables pero simplificadas. En producción debería validarse con:
> - Datos históricos de encharcamiento de campo
> - Modelos hidrológicos como HEC-RAS o similar
> - Datos de ETo (evapotranspiración de referencia)
> - Conductividad hidráulica saturada del suelo (Ksat)

El módulo `src/features/waterlogging_calculator.py` tiene todas las constantes agrupadas para facilitar su ajuste.

---

## 26. Enriquecimiento económico-productivo

Fase final de completitud: relleno de las 3 variables económicas mediante lookup en tablas de referencia locales.

### Tablas de referencia

| Archivo | Propósito | Lookup |
|---|---|---|
| `data/reference/rendimiento_olivar_reference.csv` | Rendimiento esperado por zona, tipo, riego y variedad | zona + tipo + riego + variedad → zona + tipo + riego → tipo solo |
| `data/reference/precios_olivar_reference.csv` | Precios de mercado por zona y variedad | zona + variedad → variedad → defecto |
| `data/reference/costes_olivar_reference.csv` | Costes variables de operación | tipo + riego → tipo solo |

### Variables completadas

| Variable | Fuente | Tipo | Ejemplo (cliente_2) |
|---|---|---|---|
| `rendimiento_esperado_kg_ha` | Tabla rendimientos | int | 2950 (Tradicional Riego Arbequina) |
| `precio_mercado_eur_kg` | Tabla precios | float | 4.20 (Arbequina Granada) |
| `coste_variable_ha` | Tabla costes | int | 780 (Tradicional Riego) |

### Proceso de lookup

**Rendimiento:** 4 niveles fallback
1. Zona + tipo + riego + variedad exacta
2. Zona + tipo + riego (promedio por variedad)
3. Tipo solo (default by tipo_olivar)
4. Sin match → NULL

**Precio:** 3 niveles fallback
1. Zona + variedad exacta
2. Variedad solo (mercado general)
3. "Desconocida" (precio default)
4. Sin match → NULL

**Coste:** 2 niveles fallback
1. Tipo + riego exacto
2. Tipo solo
3. Sin match → NULL

### Implementación

Módulo: `src/features/economic_enrichment.py`
- Función: `enrich_economic_for_client(df)` → DataFrame con 3 nuevas columnas
- Función: `get_economic_stats(df)` → dict con cobertura
- Carga automática en `src/features/enrichment_assembler.py` (paso 5 del ensamblador)

### Estado actual (2026-06-05)

- cliente_1: 33/33 parcelas con valores económicos completados (100%)
- cliente_2: 1/1 parcela con valores económicos completados (100%)
- CSV consolidado: **22/22 columnas completas** en ambos clientes

---

## 27. Advertencias de validación

### Pendiente extrema

Se emiten advertencias (sin bloqueo de ready_for_ml) para:

| Condición | Nivel | Acción |
|---|---|---|
| `pendiente_% > 100%` | ALERTA FUERTE | Revisar dato SIGPAC, posible error |
| `60% < pendiente_% <= 100%` | ADVERTENCIA | Revisar dato SIGPAC |
| `pendiente_% <= 60%` | Sin advertencia | OK |

Motivo: Valores extremos suelen indicar errores en la digitalización SIGPAC o características geomorfológicas inusuales. La app muestra estas parcelas en tabla de advertencias para revisión manual, pero no bloquean `ready_for_ml` ni impiden exportar al modelo.

---

## 28. Exportación del CSV para modelo ML

### Dos formatos de exportación

**CSV Consolidado Interno** (25 columnas):
- 22 columnas modelo
- 3 columnas técnicas: `_ready_for_ml`, `_cols_complete`, `_n_parcelas_ov`
- Uso: Auditoría, seguimiento en app, debug

**CSV para Modelo ML** (22 columnas exactas):
- Solo las 22 columnas esperadas por el modelo
- Sin columnas técnicas
- Orden: Exactamente SCHEMA_COLUMNS
- Archivo: `input_ml_{client_id}.csv`
- Uso: Alimentar directamente al modelo sin procesamiento adicional

### Función exportadora

```python
from src.features.enrichment_assembler import get_ml_ready_csv
ml_df = get_ml_ready_csv(enriched_df)  # Retorna 22 columnas exactas
```

---

## 29. Estado de implementación v7 — Listo para modelo ML

| Columna | Fuente | Estado |
|---|---|---|
| `parcel_id` | Shapefile | ✅ |
| `zona_provincia` | SIGPAC shapefile | ✅ |
| `tipo_olivar` | Agricultor | ✅ |
| `riego` | Agricultor | ✅ |
| `superficie_ha` | Geometría | ✅ |
| `variedad` | Agricultor | ✅ |
| `estado_fenologico` | Agricultor | ✅ |
| `tipo_suelo` | SoilGrids | ✅ |
| `drenaje` | SoilGrids + pendiente | ✅ |
| `pendiente_%` | SIGPAC shapefile | ✅ (⚠️ advertencias extremas) |
| `distancia_rio_m` | Overpass OSM | ✅ |
| `altitud_m` | SIGPAC shapefile | ✅ |
| `rain_72h_mm` | Open-Meteo | ✅ (🔄 stale si falla) |
| `rain_7d_mm` | Open-Meteo | ✅ (🔄 stale si falla) |
| `temp_media_7d` | Open-Meteo | ✅ (🔄 stale si falla) |
| `humedad_suelo_%` | Open-Meteo | ✅ (🔄 stale si falla) |
| `profundidad_suelo_cm` | SoilGrids proxy | ✅ (🔄 stale si falla) |
| `materia_organica_%` | SoilGrids SOC | ✅ (🔄 stale si falla) |
| `rendimiento_esperado_kg_ha` | Tabla local referencias | ✅ |
| `precio_mercado_eur_kg` | Tabla local referencias | ✅ |
| `coste_variable_ha` | Tabla local referencias | ✅ |
| `duracion_encharcamiento_dias` | Cálculo interno | ✅ |

**Total implementado: 22/22 columnas (100%) — CSV listo para modelo ML.**

**Características implementadas:**
- ✅ Manejo robusto de errores (conserva datos válidos previos, marca como "stale")
- ✅ Exportación estricta (22 columnas exactas, sin técnicas)
- ✅ Advertencias de validación (pendiente extrema, sin bloqueo)
- ✅ Flag ready_for_ml (bloquea si datos incompletos)
- ✅ Aislamiento por cliente (cliente_1, cliente_2 independientes)
