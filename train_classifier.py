"""
train_classifier.py
===================
Stage 3: Preprocessing + Baseline Classifier Training & Evaluation

Workflow:
1. Load data/tickets_raw.csv (4,000 tickets, 8 categories)
2. Stratified 70/15/15 Train / Validation / Test split
3. Text cleaning & TF-IDF vectorization (1-2 ngrams, max 5000 features)
4. Train & compare 3 models: Logistic Regression, Linear SVM, XGBoost
5. Evaluate on Validation set (Macro F1, Precision, Recall, Per-category breakdown)
6. Generate & save confusion matrix heatmaps to results/
7. Save model comparison table to results/model_comparison.csv
8. Save best model, vectorizer, and label encoder to models/
"""

import os
import re
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from xgboost import XGBClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    accuracy_score,
)

# ---------------------------------------------------------------------------
# Directories setup
# ---------------------------------------------------------------------------
DATA_PATH = Path("data/tickets_raw.csv")
RESULTS_DIR = Path("results")
MODELS_DIR = Path("models")
RESULTS_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# Set plot style
sns.set_theme(style="whitegrid")
plt.rcParams.update({"font.size": 10})

# ---------------------------------------------------------------------------
# Text Preprocessing
# ---------------------------------------------------------------------------
def clean_text(text: str) -> str:
    """
    Clean technician log text while preserving domain terms and numbers.
    - Convert to lowercase
    - Replace non-alphanumeric chars (except hyphen) with spaces
    - Collapse extra whitespace
    """
    if not isinstance(text, str):
        return ""
    text = text.lower()
    # Replace symbols except alphanumeric and spaces/hyphens with space
    text = re.sub(r"[^\w\s-]", " ", text)
    # Replace multiple hyphens or standalone hyphens
    text = re.sub(r"\s-\s", " ", text)
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ---------------------------------------------------------------------------
# Main Training & Evaluation Pipeline
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("STAGE 3: PREPROCESSING & CLASSIFIER EVALUATION")
    print("=" * 70)

    # 1. Load Data
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"{DATA_PATH} not found. Run generate_data.py first.")

    df = pd.read_csv(DATA_PATH)
    print(f"\nLoaded {len(df):,} tickets across {df['category'].nunique()} categories.")

    # Apply text cleaning
    df["clean_text"] = df["text"].apply(clean_text)

    # 2. Encode Labels
    label_encoder = LabelEncoder()
    df["label"] = label_encoder.fit_transform(df["category"])
    class_names = list(label_encoder.classes_)

    # 3. Stratified Train / Validation / Test Split (70% / 15% / 15%)
    # First split: 70% Train, 30% Temp
    X_train_raw, X_temp, y_train, y_temp = train_test_split(
        df["clean_text"],
        df["label"],
        test_size=0.30,
        random_state=42,
        stratify=df["label"]
    )
    # Second split: Split 30% Temp equally into 15% Val and 15% Test
    X_val_raw, X_test_raw, y_val, y_test = train_test_split(
        X_temp,
        y_temp,
        test_size=0.50,
        random_state=42,
        stratify=y_temp
    )

    print(f"Dataset Split:")
    print(f"  Train set      : {len(X_train_raw):,} samples ({len(X_train_raw)/len(df):.0%})")
    print(f"  Validation set : {len(X_val_raw):,} samples ({len(X_val_raw)/len(df):.0%})")
    print(f"  Test set       : {len(X_test_raw):,} samples ({len(X_test_raw)/len(df):.0%})")

    # Save splits for downstream reproducibility
    df.iloc[X_train_raw.index].to_csv(RESULTS_DIR / "train_split.csv", index=False)
    df.iloc[X_val_raw.index].to_csv(RESULTS_DIR / "val_split.csv", index=False)
    df.iloc[X_test_raw.index].to_csv(RESULTS_DIR / "test_split.csv", index=False)

    # 4. TF-IDF Vectorization
    print("\nVectorizing text with TF-IDF (1-2 ngrams, max_features=5000)...")
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=5000,
        stop_words="english",
        sublinear_tf=True
    )

    X_train = vectorizer.fit_transform(X_train_raw)
    X_val = vectorizer.transform(X_val_raw)
    X_test = vectorizer.transform(X_test_raw)

    print(f"TF-IDF Matrix Shape (Train): {X_train.shape}")

    # 5. Model Definitions
    # Note: We wrap LinearSVC with CalibratedClassifierCV so it provides probability estimates
    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000, C=1.0, random_state=42),
        "Linear SVM": CalibratedClassifierCV(LinearSVC(C=1.0, random_state=42)),
        "XGBoost": XGBClassifier(
            n_estimators=200,
            learning_rate=0.1,
            max_depth=5,
            random_state=42,
            eval_metric="mlogloss"
        )
    }

    # Storage for results
    summary_results = []
    category_metrics_list = []
    best_model_name = None
    best_f1 = -1.0
    trained_models = {}

    print("\n" + "=" * 70)
    print("TRAINING & EVALUATION ON VALIDATION SET")
    print("=" * 70)

    # 6. Train & Evaluate Models
    for name, model in models.items():
        print(f"\n[Training {name}...]")
        model.fit(X_train, y_train)
        trained_models[name] = model

        # Validation Predictions
        val_preds = model.predict(X_val)

        # Overall Metrics
        acc = accuracy_score(y_val, val_preds)
        macro_f1 = f1_score(y_val, val_preds, average="macro")
        macro_prec = precision_score(y_val, val_preds, average="macro")
        macro_rec = recall_score(y_val, val_preds, average="macro")
        weighted_f1 = f1_score(y_val, val_preds, average="weighted")

        summary_results.append({
            "Model": name,
            "Accuracy": round(acc, 4),
            "Macro F1": round(macro_f1, 4),
            "Macro Precision": round(macro_prec, 4),
            "Macro Recall": round(macro_rec, 4),
            "Weighted F1": round(weighted_f1, 4)
        })

        if macro_f1 > best_f1:
            best_f1 = macro_f1
            best_model_name = name

        # Per-Category Metrics
        rep = classification_report(y_val, val_preds, target_names=class_names, output_dict=True)
        for cat in class_names:
            category_metrics_list.append({
                "Model": name,
                "Category": cat,
                "Precision": round(rep[cat]["precision"], 4),
                "Recall": round(rep[cat]["recall"], 4),
                "F1-Score": round(rep[cat]["f1-score"], 4),
                "Support": int(rep[cat]["support"])
            })

        # Generate & Save Confusion Matrix
        cm = confusion_matrix(y_val, val_preds)
        plt.figure(figsize=(9, 7))
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            xticklabels=class_names,
            yticklabels=class_names
        )
        plt.title(f"Confusion Matrix: {name} (Val Macro F1 = {macro_f1:.4f})", fontsize=12, fontweight="bold")
        plt.xlabel("Predicted Category", fontweight="bold")
        plt.ylabel("True Category", fontweight="bold")
        plt.xticks(rotation=45, ha="right")
        plt.yticks(rotation=0)
        plt.tight_layout()

        # Format filename
        filename_str = name.lower().replace(" ", "_")
        cm_path = RESULTS_DIR / f"confusion_matrix_{filename_str}.png"
        plt.savefig(cm_path, dpi=300)
        plt.close()
        print(f"  -> Confusion matrix saved to: {cm_path}")

    # 7. Model Comparison Output
    comp_df = pd.DataFrame(summary_results).sort_values(by="Macro F1", ascending=False)
    comp_csv_path = RESULTS_DIR / "model_comparison.csv"
    comp_df.to_csv(comp_csv_path, index=False)

    cat_df = pd.DataFrame(category_metrics_list)
    cat_csv_path = RESULTS_DIR / "per_category_metrics.csv"
    cat_df.to_csv(cat_csv_path, index=False)

    print("\n" + "=" * 70)
    print("MODEL COMPARISON SUMMARY (VALIDATION SET)")
    print("=" * 70)
    print(comp_df.to_string(index=False))
    print("=" * 70)

    # Display breakdown per model
    print("\nPER-CATEGORY METRICS BREAKDOWN (VALIDATION SET):")
    for name in models.keys():
        print(f"\n--- {name} ---")
        m_df = cat_df[cat_df["Model"] == name][["Category", "Precision", "Recall", "F1-Score", "Support"]]
        print(m_df.to_string(index=False))

    # Evaluate best model on test set for final unbiased metric
    best_model = trained_models[best_model_name]
    test_preds = best_model.predict(X_test)
    test_f1 = f1_score(y_test, test_preds, average="macro")
    test_acc = accuracy_score(y_test, test_preds)

    print("\n" + "=" * 70)
    print(f"WINNING MODEL: {best_model_name}")
    print(f"Validation Macro F1 : {best_f1:.4f}")
    print(f"Test Set Macro F1   : {test_f1:.4f} (Accuracy: {test_acc:.4f})")
    print("=" * 70)

    # 8. Save Artifacts for FastAPI / Dashboard
    joblib.dump(best_model, MODELS_DIR / "best_model.joblib")
    joblib.dump(vectorizer, MODELS_DIR / "tfidf_vectorizer.joblib")
    joblib.dump(label_encoder, MODELS_DIR / "label_encoder.joblib")
    
    print(f"\nArtifacts saved to {MODELS_DIR}/:")
    print(f"  - best_model.joblib ({best_model_name})")
    print(f"  - tfidf_vectorizer.joblib")
    print(f"  - label_encoder.joblib")
    print(f"Summary saved to {comp_csv_path}")

if __name__ == "__main__":
    main()
