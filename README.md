# 🌿 LLM Rain Olivar

Sistema inicial basado en LLM para analizar el impacto de lluvias intensas en parcelas de olivar.

---

## Instalación

### 1. Clonar el repositorio

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

* Windows:

```bash
.venv\Scripts\activate
```

* Linux/Mac:

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

Crear archivo `.env` en la raíz del proyecto:

```env
OPENAI_API_KEY=tu_api_key
GEMINI_API_KEY=tu_api_key
```

---

## Ejecución

Ejecutar el sistema:

```bash
python main.py
```

---

## 📂 Estructura básica

```text
LLM_RAIN_OLIVAR/
│
├── data/               # escenarios de entrada (JSON)
├── src/
│   ├── config/        # configuración de modelos
│   ├── orquestador/   # agente principal
│   ├── prompts/       # plantillas
│   ├── roles/         # conocimiento experto
│   ├── utils/         # helpers (loader, cliente LLM)
│
├── main.py            # punto de entrada
├── .env               # claves API
```

---

## Estado actual

* ✔ Agente funcional
* ✔ Análisis de eventos de lluvia
* ✔ Soporte multi-modelo (OpenAI / Gemini)
* ✔ Entrada desde JSON

---

## Nota

Asegúrate de que:

* El archivo `.env` está correctamente configurado
* Ejecutas desde la raíz del proyecto
* El entorno virtual está activado

---

## Ejemplo

El sistema usa escenarios desde:

```text
data/escenarios/test_1.json
```

Puedes modificar o añadir nuevos casos.

---
