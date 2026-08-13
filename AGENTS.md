# Project 3: NLP Maintenance Log Classification — AGENTS.md

**Goal:** Classify free-text maintenance ticket descriptions into failure categories, store and analyze results in a live Postgres database, visualize trends on a dashboard, serve predictions via API, and automate ongoing classification with confidence-based alerting.

**Why this project (context):** Portfolio currently has three time-series/regression projects (Apple Stock ARIMA/SARIMA, Solar Power XGBoost, CMAPSS XGBoost+LSTM). This project diversifies into text classification, SQL analytics, and automation — skills on the resume (SQL, Power BI/Tableau-adjacent analytics) not yet demonstrated by any deployed project. Paired narratively with Project 1: numeric sensor data vs. free-text data, the two main data types a maintenance team deals with.

**Hard constraint:** Free tier only across all tools.

---

## Stage 1 — Repo & environment setup
- New repo: `Project3_cat` (separate from Project1_cat), scaffolded in Antigravity IDE
- `requirements.txt`, `.env` for secrets (Claude API key, Postgres connection string) — `.env` in `.gitignore` from commit #1
- Provision **Supabase or Neon free-tier Postgres** — get connection string, verify connectivity with a throwaway `SELECT 1`
- Empty repo pushed to GitHub as private (flip to public once no secrets are at risk of ever having been committed)

## Stage 2 — Synthetic data generation (Claude API)
- Define 6–8 failure categories (e.g. bearing failure, hydraulic leak, electrical fault, overheating, corrosion, sensor malfunction, software/control fault, wear and tear)
- Prompt Claude API to generate realistic short technician-style ticket descriptions per category — target ~500–800 per category (3,000–5,000 total)
- Save as CSV: `text, category`
- **Document the generation prompt itself** in the repo — this is the transparency artifact that makes the synthetic-data choice defensible in an interview
- Train/val/test split (e.g. 70/15/15), stratified by category

## Stage 3 — Preprocessing + baseline classifier
- Clean text (lowercase, strip noise, keep domain terms — don't over-strip)
- TF-IDF vectorization
- Train and compare: Logistic Regression, Linear SVM, XGBoost — pick winner by macro F1 (not just accuracy, since categories may be imbalanced)
- Confusion matrix to see which categories get confused (useful review-queue design signal for Stage 5)
- Document the model choice rationale, same pattern as the LSTM vs XGBoost writeup for Project 1

## Stage 4 — Database layer
- Schema (`tickets` table): `id, text, predicted_category, confidence, true_category (nullable), equipment_id (synthetic), created_at`
- Connect via SQLAlchemy or psycopg2
- Batch-write the classified train/val/test set as the initial seed data

## Stage 5 — Analytical SQL layer
- Category frequency over time
- Low-confidence review queue (`confidence < threshold`)
- Category breakdown by synthetic equipment_id
- Trending categories (window function comparing recent window vs. prior window)
- Save these as named views or a `queries.sql` file in the repo — this is your "SQL skill, demonstrated" artifact

## Stage 6 — Dashboard
- Streamlit or Gradio, reading from Postgres
- Category trend chart, volume over time, low-confidence flagged table, filter by date/category
- Deploy to Streamlit Community Cloud or Hugging Face Spaces

## Stage 7 — FastAPI serving layer
- `/predict` (text in → category + confidence out, writes to DB)
- `/health`
- Pydantic request/response schemas

## Stage 8 — Containerization & deployment
- Docker (reuse the CPU-only pattern and WSL2 disk-location fix from Project 1)
- FastAPI → Render free tier
- Dashboard → Streamlit Community Cloud or HF Spaces

## Stage 9 — Automation
- **Scheduled GitHub Actions workflow** (e.g. every few hours): generate a small new batch of synthetic tickets → classify → write to DB — simulates continuous ticket ingestion
- **Low-confidence alerting**: flag predictions below threshold, notify via free Slack webhook, email (free SMTP), or auto-created GitHub Issue

## Stage 10 — Stretch: CI/CD
- GitHub Actions: run tests, auto-deploy to Render/HF Spaces on push to main

## Stage 11 — README + interview prep
- README documenting: problem, synthetic-data rationale (stated openly, not hidden), architecture diagram, model choice, known limitations
- Rehearsable 2-minute verbal explanation of the full pipeline
- Talking points: TF-IDF vs. heavier model tradeoff, why Postgres over SQLite (real-system feel), what's missing for true production-grade (monitoring, drift detection, retraining triggers) — worth naming even if not built

---

## Known limitation to state upfront, always
No public dataset of real-world free-text maintenance logs exists (closest options are non-downloadable or tabular/sensor-based, not text). Synthetic data generation via LLM is a legitimate, documented technique — disclosed as a deliberate engineering tradeoff, not hidden.
