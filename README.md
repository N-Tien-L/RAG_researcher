# RAG_researcher

## Structure

- app/main.py - Streamlit entrypoint for ingestion demo
- app/rag/ - Chunking and pipeline stubs
- app/ingestion/ - PDF/YouTube extraction helpers
- app/core/ - Config and logging utilities
- app/utils/ - Shared helpers (text, files, time)
- tests/ - Unit/integration tests

## Quickstart

1. Install deps: `pip install -e .`
2. Run Streamlit: `streamlit run app/main.py`
3. Optionally set `DB_PATH` in `.env` for Chroma persistence.