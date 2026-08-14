"""
load_predictions.py
===================
Stage 4: Database Layer Seed Script

Workflow:
1. Load trained model, TF-IDF vectorizer, and label encoder from models/
2. Load full data/tickets_raw.csv (4,000 synthetic tickets)
3. Vectorize text and generate predictions + confidence scores (max probability)
4. Assign synthetic equipment_ids (EQ-101 to EQ-120)
5. Generate synthetic timestamps distributed randomly over the past 90 days
6. Batch-insert into Neon Postgres `tickets` table
7. Verify DB record count and print a sample of ingested tickets
"""

import os
import re
import random
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Setup & Config
# ---------------------------------------------------------------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env file")

DATA_PATH = Path("data/tickets_raw.csv")
MODELS_DIR = Path("models")

EQUIPMENT_POOL = [f"EQ-{i}" for i in range(101, 121)]  # EQ-101 to EQ-120

# ---------------------------------------------------------------------------
# Text Preprocessing (matching train_classifier.py)
# ---------------------------------------------------------------------------
def clean_text(text_val: str) -> str:
    if not isinstance(text_val, str):
        return ""
    t = text_val.lower()
    t = re.sub(r"[^\w\s-]", " ", t)
    t = re.sub(r"\s-\s", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("STAGE 4: DATABASE INGESTION & SEEDING")
    print("=" * 70)

    # 1. Load Artifacts
    print("\nLoading trained model, vectorizer, and label encoder...")
    model = joblib.load(MODELS_DIR / "best_model.joblib")
    vectorizer = joblib.load(MODELS_DIR / "tfidf_vectorizer.joblib")
    encoder = joblib.load(MODELS_DIR / "label_encoder.joblib")
    print("Model artifacts loaded successfully.")

    # 2. Load Raw Tickets
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"{DATA_PATH} not found.")
    
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df):,} tickets from {DATA_PATH}.")

    # 3. Clean Text & Vectorize
    cleaned_texts = df["text"].apply(clean_text)
    X_tfidf = vectorizer.transform(cleaned_texts)

    # 4. Predict Categories & Confidence Scores
    print("Running model predictions and calculating confidence scores...")
    probs = model.predict_proba(X_tfidf)
    pred_indices = np.argmax(probs, axis=1)
    confidences = np.max(probs, axis=1)

    predicted_categories = encoder.inverse_transform(pred_indices)

    df["predicted_category"] = predicted_categories
    df["confidence"] = np.round(confidences, 4)
    df["true_category"] = df["category"]  # original ground truth

    # 5. Assign Equipment IDs
    random.seed(42)
    np.random.seed(42)
    df["equipment_id"] = [random.choice(EQUIPMENT_POOL) for _ in range(len(df))]

    # 6. Assign Synthetic Timestamps across past 90 days
    now = datetime.now(timezone.utc)
    random_seconds = np.random.randint(0, 90 * 24 * 3600, size=len(df))
    created_timestamps = [now - timedelta(seconds=int(sec)) for sec in random_seconds]
    df["created_at"] = created_timestamps

    # Prepare DataFrame for DB insertion
    db_df = df[["text", "predicted_category", "confidence", "true_category", "equipment_id", "created_at"]]

    # 7. Connect to Postgres & Batch Insert
    print(f"\nConnecting to Postgres database...")
    engine = create_engine(DATABASE_URL)

    # Clear table if existing (or insert into clean state)
    with engine.begin() as conn:
        print("Trimming/Clearing existing records in `tickets` table if any...")
        conn.execute(text("TRUNCATE TABLE tickets RESTART IDENTITY;"))

    print(f"Batch writing {len(db_df):,} records into `tickets` table...")
    db_df.to_sql("tickets", con=engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print("Batch write complete!")

    # 8. Verification Query
    with engine.connect() as conn:
        count_res = conn.execute(text("SELECT COUNT(*) FROM tickets;")).fetchone()
        total_in_db = count_res[0]
        
        sample_rows = conn.execute(text("""
            SELECT id, text, predicted_category, confidence, true_category, equipment_id, created_at
            FROM tickets
            ORDER BY id ASC
            LIMIT 5;
        """)).fetchall()

    print("\n" + "=" * 70)
    print("VERIFICATION RESULT")
    print("=" * 70)
    print(f"Total rows currently in `tickets` table: {total_in_db:,}")

    print("\nSample records from Postgres:")
    for r in sample_rows:
        print(f"  [ID {r[0]}] {r[5]} | Pred: {r[2]:<22} (Conf: {r[3]:.4f}) | True: {r[4]:<22} | Date: {r[6].strftime('%Y-%m-%d %H:%M')}")
        print(f"         Text: {r[1][:80]}...")

    print("\n[SUCCESS] Database seed complete and verified!")

if __name__ == "__main__":
    main()
