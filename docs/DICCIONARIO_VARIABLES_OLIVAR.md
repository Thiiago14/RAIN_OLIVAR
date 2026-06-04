# Diccionario de variables — RAIN-OLIVAR

> **Versión:** MVP Geoespacial v2 — Filtro OV + Editor agricultor  
> **Última actualización:** 2026-06-04  
> **Módulos implicados:** `src/geo/`, `src/features/`, `app/streamlit_app.py`

---

## 1. Propósito del documento

Este documento describe la **trazabilidad completa de las variables** utilizadas y generadas por la aplicación geoespacial RAIN-OLIVAR.

El proyecto parte de **shapefiles de parcelas y recintos SIGPAC** por cliente, ubicados en `data/clientes_shp/`. A partir de ellos, la aplicación:

1. Lee los polígonos y sus atributos.
2. Calcula superficie en hectáreas desde la geometría.
3. Asigna un identificador único a cada parcela.
4. Genera un **CSV base** compatible con el esquema del modelo ML/LLM.
5. Deja columnas vacías para datos que aún no se pueden completar automáticamente.

El objetivo final es alimentar el modelo ML con todas las variables necesarias para predecir el porcentaje de pérdida de producción y el impacto económico por hectárea ante eventos de lluvia intensa.

---

## 2. Fuentes de datos actuales

| Fuente | Ruta / Módulo | Estado | Descripción |
|---|---|---|---|
| Shapefile cliente 1 | `data/clientes_shp/cliente_1/` | ✅ Implementado | 33 recintos SIGPAC, CRS EPSG:32630, provincia 18 (Granada) |
| Shapefile cliente 2 | `data/clientes_shp/cliente_2/` | ✅ Implementado | 8 recintos SIGPAC, CRS EPSG:32630, provincia 18 (Granada) |
| Geometría del polígono | campo `geometry` del shapefile | ✅ Implementado | Base para cálculo de área, visualización en mapa y centroides |
| CSV base exportado | generado por `build_input_from_parcels.py` | ✅ Implementado | 22 columnas; esquema compatible con modelo ML |
| Datos del agricultor | formulario futuro en la app | ⏳ Pendiente | Variedad, tipo de riego, estado fenológico, precios, etc. |
| API meteorológica | integración futura | ⏳ Pendiente | Precipitación, temperatura, humedad de suelo |
| API edafológica / suelo | integración futura | ⏳ Pendiente | Profundidad de suelo, materia orgánica, textura, drenaje |
| Análisis geoespacial | cálculo futuro desde geometría | ⏳ Pendiente | Distancia al río más cercano, DEM/MDT para pendiente verificada |

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
