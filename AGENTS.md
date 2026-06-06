# AGENTS.md

## Run

```bash
# Streamlit app (primary UI) — run from repo root
streamlit run app/streamlit_app_new.py --server.port 8502

# Batch CLI pipeline (ML + LLM + PDF, no UI)
python main.py
```

No test framework, linter, or formatter is configured. No Makefile or CI.

## Two Execution Modes

The repo has **two co-existing architectures** sharing `src/`:

1. **Streamlit app** (`app/streamlit_app_new.py`) — 4-tab geospatial platform (Data, Enrichment, Modeling, IA/Report). Uses `app/components/page_*.py` per tab.
2. **Batch pipeline** (`main.py`) — sequential: load model -> predict -> LLM analysis per parcel -> PDF report. Uses `src/orquestador/olivar_agent.py`.

Both read the same ML model at `data/output/modelo_olivar.pkl`.

## ML Schema (Critical)

`SCHEMA_COLUMNS` in `src/features/build_input_from_parcels.py` defines exactly **22 columns in a fixed order**. The sklearn pipeline depends on this order. Never reorder or rename these columns.

- Internal enriched CSV: 25 cols (22 + `_ready_for_ml`, `_cols_complete`, `_n_parcelas_ov`)
- ML input CSV: exactly 22 cols in `SCHEMA_COLUMNS` order
- Merge key is always `parcel_id` (never `parcel_uid`, which is autoincremental)

## Environment

- `pip install -r requirements.txt` (no pyproject.toml)
- `.env` with `ANTHROPIC_API_KEY` enables Claude analysis; without it, the app falls back to rule-based agronomic analysis
- API cache in `data/api_cache/` with differential TTL: 24h weather, 30d hydrology, 180d soil

## ARCHITECTURE.md is Stale

`ARCHITECTURE.md` describes the original batch pipeline only. It references `gpt-5.5` / OpenAI as default — the Streamlit app now uses `claude-haiku-4-5` via Anthropic. Trust `README.md` and source code over `ARCHITECTURE.md` for the Streamlit app.

## Key Directories

| Path | Purpose |
|---|---|
| `app/streamlit_app_new.py` | Streamlit entrypoint (4 tabs) |
| `app/components/page_*.py` | One file per tab |
| `src/features/` | Enrichment, validation, ML prediction, LLM engine, PDF |
| `src/geo/` | Shapefile loading, parcel processing, map building |
| `src/config/llms.py` | Multi-provider LLM client (OpenAI/Gemini/Anthropic) |
| `src/prompts/analysis_prompt.txt` | 7-section agronomic analysis prompt |
| `data/clientes_shp/` | SIGPAC shapefiles per client |
| `data/reference/` | Local economic reference tables (no API) |
| `data/output/modelo_olivar.pkl` | Trained sklearn Pipeline |
