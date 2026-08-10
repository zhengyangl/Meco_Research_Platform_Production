# MEco Research Data Platform

**"Nature Is Not Optional."**

An interactive research dashboard exploring how biomimetics and bio-inspired
technologies replace, enhance, or support the 22 ecosystem services people
depend on — built on LLM-annotated classifications of Web of Science
literature, following the framework of Jacobs et al. (2025).

The dashboard is the visible face of a larger **Living Data Asset**: an
automated pipeline (ingestion → LLM classification → human review for
uncertain cases → NLP feature extraction → aggregation) that keeps the
underlying research corpus growing and versioned over time.

---

## Where to go next

This README is a map, not the full explanation. Start here, then go to whichever of these actually answers your question:

| Document | Read this when you need to know... |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | How the whole system fits together, and why it's built this way |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | What the data *means* — the 22 ecosystem services, R/E/S, confidence levels, technology clusters |
| [`docs/data_schema_supplement.md`](docs/data_schema_supplement.md) | Field-by-field database reference |
| [`docs/prompt_specification.md`](docs/prompt_specification.md) | The exact LLM classification prompt, and its version history |
| [`docs/environment_setup.md`](docs/environment_setup.md) | One-time setup — AWS, PostgreSQL, OpenRouter, Google Cloud (start here if you're standing this up from scratch) |
| [`docs/handover.md`](docs/handover.md) | Day-to-day operation, troubleshooting, credential rotation |

---

## What's in the dashboard

| Page | File | Description |
|---|---|---|
| **Narrative** | `app.py` | The main landing page — a guided story through the corpus: funnel metrics, R/E/S (Replace/Enhance/Support) breakdown across ecosystem services, and framing analysis. Loads instantly from pre-computed static files, and its numbers are intentionally locked to the original published corpus — see `architecture.md` Section 3.3 for why. |
| **Data Explorer** | `pages/explorer.py` | A full interactive database of every classified paper currently in the system, with multi-dimensional filtering (ecological focus, time/impact, publication details, geography/institutions, technology/funding), quick search, shareable URL state, impact-tier cards, and linked visualizations. Unlike the narrative page, this queries the live database directly and grows as new papers are added. |

## Repository layout

```
.
├── app.py                          # Narrative page
├── pages/
│   └── explorer.py
├── pipeline/
│   ├── ingest_initial.py           # One-time historical load — disaster recovery only
│   ├── ingest_incremental.py       # Ongoing ingestion of new/reviewed papers
│   ├── classify.py                 # LLM classification with confidence routing
│   ├── text_analysis.py            # NLP feature extraction
│   ├── aggregate.py                # Database → dashboard_data/
│   └── run_pipeline.py             # Orchestrates the pipeline — the actual entry point
├── dashboard_data/                 # Pre-computed JSON & Parquet, checked into git
│   └── discovery_data/             # Reference material from chart curation, not read by the dashboard
├── llm_validation/                 # Model-selection notebooks — historical reference only
├── docs/
│   ├── README.md                   # This file
│   ├── architecture.md
│   ├── data_dictionary.md
│   ├── data_schema_supplement.md
│   ├── prompt_specification.md
│   ├── environment_setup.md
│   └── handover.md
├── .streamlit/config.toml
├── .devcontainer/devcontainer.json
├── .env.example
├── .gitignore
├── schema.sql                      # One-time database setup — see docs/environment_setup.md
├── requirements.txt                 # Dashboard dependencies
└── requirements_pipeline.txt        # Pipeline dependencies (heavier — LLM client, embedding model, Drive API)
```

## Running the dashboard locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The Data Explorer page (`pages/explorer.py`) is picked up automatically by Streamlit's multi-page app support once the main app is running.

The Explorer connects to PostgreSQL directly (see `docs/environment_setup.md` for database setup) and falls back to a local snapshot in `dashboard_data/` if the database is unreachable — either way, `requirements.txt` has what you need; `psycopg2` is already included.

> `requirements_pipeline.txt` is separate and heavier — only needed to run the scripts in `pipeline/`, not to run the dashboard itself.

## Data pipeline, briefly

New papers flow in through Google Drive, get classified by an LLM, and — depending on how confident the model is — either go straight into the database or get checked by a person first via a review spreadsheet. `pipeline/run_pipeline.py` is what actually runs this; see `docs/architecture.md` Section 2 for the full diagram and `docs/handover.md` for the day-to-day operating rhythm.

Every classification and derived feature is versioned and traceable back to its source dataset batch, model version, and prompt version — full detail in `docs/architecture.md` and `docs/data_schema_supplement.md`.

## Corpus snapshot

The narrative page's numbers are locked to the original published corpus and don't change as new papers are added (see `docs/architecture.md` Section 3.3):

- **68,917** total papers ingested (original batch)
- **59,599** non-review papers
- **31,559** classified as relevant (biomimetic/nature-inspired) — the "target corpus"
- **22** ecosystem services tracked across 4 service families

The Data Explorer shows everything currently in the database, which grows over time — check the Explorer itself for the current live count, not this README.

## Tech stack

**Dashboard:** Streamlit · Plotly · pandas · NumPy · PyArrow · streamlit-aggrid
**Pipeline:** PostgreSQL · Qwen-2.5-72B via OpenRouter (ongoing classification; the original corpus was classified with GPT-4.1) · sentence-transformers (technology clustering) · Google Sheets & Drive APIs (human review queue, misclassification feedback, new-data detection)
