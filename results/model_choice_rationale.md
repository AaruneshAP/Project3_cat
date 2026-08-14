# Model Selection & Architecture Tradeoffs: NLP Maintenance Log Classifier

## Executive Summary

For free-text maintenance log classification (8 target categories across 4,000 synthetic ticket descriptions), three standard baseline algorithms were evaluated using a stratified 70/15/15 train/validation/test split and a 5,000-feature unigram+bigram TF-IDF vectorization:

1. **Linear SVM (`LinearSVC` wrapped in Platt Calibration)**: **Winner** (Val Macro F1 = `0.9649`, Test Macro F1 = `0.9463`)
2. **Logistic Regression**: 2nd place (Val Macro F1 = `0.9446`)
3. **XGBoost Classifier**: 3rd place (Val Macro F1 = `0.9128`)

---

## Validation Performance Comparison

| Model | Accuracy | Macro F1 | Macro Precision | Macro Recall | Weighted F1 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Linear SVM** | **0.9650** | **0.9649** | **0.9650** | **0.9650** | **0.9649** |
| **Logistic Regression** | 0.9450 | 0.9446 | 0.9454 | 0.9450 | 0.9446 |
| **XGBoost** | 0.9133 | 0.9128 | 0.9130 | 0.9133 | 0.9128 |

---

## Per-Category Performance Breakdown (Linear SVM)

| Category | Precision | Recall | F1-Score | Support |
| :--- | :---: | :---: | :---: | :---: |
| `hydraulic_leak` | 0.9868 | 1.0000 | **0.9934** | 75 |
| `corrosion` | 0.9737 | 0.9867 | **0.9801** | 75 |
| `bearing_failure` | 0.9610 | 0.9867 | **0.9737** | 75 |
| `electrical_fault` | 0.9730 | 0.9600 | **0.9664** | 75 |
| `sensor_malfunction` | 0.9481 | 0.9733 | **0.9605** | 75 |
| `wear_and_tear` | 0.9726 | 0.9467 | **0.9595** | 75 |
| `software_control_fault` | 0.9467 | 0.9467 | **0.9467** | 75 |
| `overheating` | 0.9583 | 0.9200 | **0.9388** | 75 |

---

## Key Technical Insights & Model Choice Rationale

### 1. High-Dimensional Sparse Text Space favors Linear Margins
TF-IDF representations yield extremely sparse, high-dimensional feature vectors (5,000 features). 
Linear models like **Linear SVM** excel because they find a maximum-margin linear hyper-plane in sparse vector spaces without greedy axis-aligned decision trees struggling with feature fragmentation.

### 2. Why XGBoost Underperformed Relative to SVM
Tree-based ensembles (XGBoost) split features orthogonally across single axes. When text signals are distributed across thousands of sparse n-grams (e.g., `temp high`, `overheating motor`, `thermal trip`), tree splitting requires excessive depth and iterations to capture sparse word combinations, leading to slight underfitting compared to linear dot-product representations.

### 3. Production Deployment & Calibration Considerations
While raw `LinearSVC` does not output probabilities natively, we wrapped it in **`CalibratedClassifierCV` (Platt Scaling)**. This provides calibrated confidence probabilities ($p \in [0.0, 1.0]$), enabling low-confidence thresholding (`confidence < 0.70`) for Stage 5 & 9 automated review queues.

---

## Limitations

1. **Synthetic Data Separability**:
   These classification metrics (e.g., ~96.5% Macro F1) reflect synthetic, LLM-generated ticket data (`gemini-flash-lite-latest`). LLM-generated text tends to maintain higher vocabulary consistency and structural coherence than real-world technician logs, which often feature extreme typos, unstandardized shorthand, and incomplete fragments. Consequently, synthetic datasets exhibit higher linear separability than noisy real-world industrial log streams.

2. **Domain Overlap in Physical Failure Modes**:
   The misclassifications observed for `overheating` (confused with `bearing_failure` and `electrical_fault` 2 times each) represent a genuine domain overlap in physical industrial equipment rather than pure model weakness. Overheating is frequently a secondary or downstream symptom of mechanical friction (bearing seizure) or electrical breakdown (winding faults/phase loss). In real-world CMMS triage, multi-label classification or root-cause tagging would be required for such symptom-level categories.

---

## Artifacts Generated

- **Model Binary**: `models/best_model.joblib` (Calibrated Linear SVM)
- **Vectorizer**: `models/tfidf_vectorizer.joblib` (5,000 TF-IDF features)
- **Encoder**: `models/label_encoder.joblib` (8 target classes)
- **Confusion Matrices**: 
  - `results/confusion_matrix_linear_svm.png`
  - `results/confusion_matrix_logistic_regression.png`
  - `results/confusion_matrix_xgboost.png`
- **Tables**:
  - `results/model_comparison.csv`
  - `results/per_category_metrics.csv`
