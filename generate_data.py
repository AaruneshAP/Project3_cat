"""
generate_data.py
================
Generates synthetic maintenance ticket descriptions using the Google Gemini API
for 8 failure categories. Produces a CSV with columns: text, category.

Design choices
--------------
- Batch size of 30 tickets per API call  (~17 calls/category, ~136 total)
- Exponential backoff with jitter on rate-limit (429) and overload (503) errors
- Checkpoint file (data/checkpoint.json) so the script can resume after interruption
- Two-pass deduplication:
    1. Exact:  normalise whitespace/case, dedupe via set
    2. Near:   difflib.SequenceMatcher -- tickets with similarity > 0.85 are dropped
- Auto top-up: keeps generating until exactly TARGET tickets survive dedup per category"""

from google import genai
from google.api_core import exceptions as google_exceptions
import csv
import difflib
import json
import os
import random
import re
import time
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

TARGET_PER_CATEGORY = 500
BATCH_SIZE = 30          # tickets requested per API call
SIMILARITY_THRESHOLD = 0.85
MODEL = "models/gemini-flash-lite-latest"  # fast + cheap for bulk generation

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)
CSV_PATH = OUTPUT_DIR / "tickets_raw.csv"
CHECKPOINT_PATH = OUTPUT_DIR / "checkpoint.json"

CATEGORIES = [
    "bearing_failure",
    "hydraulic_leak",
    "electrical_fault",
    "overheating",
    "corrosion",
    "sensor_malfunction",
    "software_control_fault",
    "wear_and_tear",
]

CATEGORY_CONTEXT = {
    "bearing_failure":       "rolling element or sleeve bearings seizing, spalling, vibrating excessively, or making noise",
    "hydraulic_leak":        "hydraulic fluid leaks from seals, hoses, fittings, cylinders, or reservoirs",
    "electrical_fault":      "wiring faults, blown fuses, tripped breakers, motor winding failures, insulation breakdown",
    "overheating":           "equipment running above rated temperature — motors, gearboxes, hydraulic fluid, pumps",
    "corrosion":             "rust, galvanic corrosion, pitting, scale build-up on metal surfaces or pipe internals",
    "sensor_malfunction":    "faulty temperature, pressure, flow, position, or vibration sensors giving bad readings or no signal",
    "software_control_fault":"PLC faults, SCADA errors, firmware crashes, erroneous control logic, HMI communication loss",
    "wear_and_tear":         "gradual material degradation -- worn belts, seals, gaskets, bushings, impellers, gears",
}

# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------
def call_with_retry(fn, max_retries=6):
    """Call fn(), retrying on rate-limit or server overload with exponential back-off."""
    base_delay = 5
    for attempt in range(max_retries):
        try:
            return fn()
        except google_exceptions.ResourceExhausted as e:
            # 429 rate limit
            wait = base_delay * (2 ** attempt) + random.uniform(0, 2)
            print(f"  [rate-limit] waiting {wait:.1f}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
        except (google_exceptions.ServiceUnavailable,
                google_exceptions.InternalServerError) as e:
            # 503 / 500 overload
            wait = base_delay * (2 ** attempt) + random.uniform(0, 2)
            print(f"  [overload] waiting {wait:.1f}s (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(wait)
        except google_exceptions.DeadlineExceeded as e:
            wait = base_delay * (2 ** attempt) + random.uniform(0, 2)
            print(f"  [timeout] waiting {wait:.1f}s (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(wait)
    raise RuntimeError(f"Max retries ({max_retries}) exceeded")

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def build_prompt(category: str, n: int) -> str:
    ctx = CATEGORY_CONTEXT[category]
    label = category.replace("_", " ")
    return (
        f"You are a maintenance technician logging equipment faults in a CMMS system.\n"
        f"Generate exactly {n} distinct, realistic maintenance ticket descriptions for the "
        f"failure category: **{label}** ({ctx}).\n\n"
        f"Rules:\n"
        f"- Each ticket: 1-3 sentences, technician voice (abbreviations OK, e.g. 'temp', 'psi', 'RPM')\n"
        f"- Mix terse entries (e.g. 'Pump shaft bearing seized, unit 4') with more descriptive ones\n"
        f"- Vary the equipment referenced: pumps, motors, compressors, conveyors, valves, fans, gearboxes, etc.\n"
        f"- Vary severity: minor, moderate, critical\n"
        f"- Do NOT number the entries\n"
        f"- Output ONLY the ticket descriptions, one per line, no blank lines between them\n"
        f"- Do NOT include category labels or any other text\n"
    )

def parse_response(text: str) -> list[str]:
    """Extract non-empty lines from the model response."""
    lines = [ln.strip() for ln in text.strip().splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]

def generate_batch(model_client, category: str, n: int) -> list[str]:
    prompt = build_prompt(category, n)
    def _call():
        response = model_client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        return response.text
    raw = call_with_retry(_call)
    return parse_response(raw)

# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------
def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())

def deduplicate(tickets: list[str]) -> list[str]:
    """Exact dedup first, then near-duplicate filtering."""
    # Pass 1: exact
    seen_norm = set()
    unique = []
    for t in tickets:
        n = normalise(t)
        if n not in seen_norm:
            seen_norm.add(n)
            unique.append(t)

    # Pass 2: near-duplicate (O(n^2) — fine for n<=600)
    kept = []
    kept_norm = []
    for t in unique:
        n = normalise(t)
        too_similar = any(
            difflib.SequenceMatcher(None, n, kn).ratio() > SIMILARITY_THRESHOLD
            for kn in kept_norm
        )
        if not too_similar:
            kept.append(t)
            kept_norm.append(n)
    return kept

# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------
def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text())
    return {}

def save_checkpoint(data: dict):
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2))

# ---------------------------------------------------------------------------
# Prompt documentation
# ---------------------------------------------------------------------------
PROMPT_DOC_PATH = Path("data_generation_prompt.md")

def save_prompt_doc():
    """Write the actual prompt template to data_generation_prompt.md.

    Renders a concrete example (bearing_failure, n=30) so the file shows
    exactly what was sent to the model — not a paraphrase.
    This is the transparency artifact that makes the synthetic-data choice
    defensible in an interview or peer review.
    """
    example_category = "bearing_failure"
    example_n = BATCH_SIZE
    example_prompt = build_prompt(example_category, example_n)

    category_table_rows = "\n".join(
        f"| `{cat}` | {ctx} |"
        for cat, ctx in CATEGORY_CONTEXT.items()
    )

    doc = f"""# Synthetic Data Generation — Prompt Template

## Overview

This file documents the **exact prompt** sent to the Google Gemini API
(`{MODEL}`) to generate synthetic maintenance ticket descriptions for
Project 3 (NLP Maintenance Log Classification).

Synthetic data was chosen deliberately: no public dataset of free-text
maintenance logs exists at the required scale. This approach is disclosed
openly as an engineering tradeoff, not hidden.

## Generation Parameters

| Parameter | Value |
|-----------|-------|
| Model | `{MODEL}` |
| Target tickets per category | {TARGET_PER_CATEGORY} |
| Batch size (tickets per API call) | {BATCH_SIZE} |
| Near-duplicate similarity threshold | {SIMILARITY_THRESHOLD} |
| Deduplication | Exact normalise + difflib SequenceMatcher |
| Total categories | {len(CATEGORIES)} |
| Total target tickets | {TARGET_PER_CATEGORY * len(CATEGORIES):,} |

## Categories & Context Descriptions

Each category was accompanied by a short context string fed into the
prompt to constrain the model to domain-appropriate vocabulary.

| Category | Context given to model |
|----------|------------------------|
{category_table_rows}

## Prompt Template

The prompt below is rendered for `{example_category}` with `n={example_n}`.
The `category` and `n` fields vary per batch; everything else is identical.

```
{example_prompt}
```

## Retry & Rate-Limit Strategy

- **ResourceExhausted (429)**: exponential back-off, base 5 s × 2^attempt + uniform jitter [0, 2 s]
- **ServiceUnavailable / InternalServerError (503/500)**: same back-off schedule
- **DeadlineExceeded (timeout)**: same back-off schedule
- **Max retries**: 6 per batch call before raising

## Deduplication Strategy

1. **Exact pass**: normalise (lowercase, collapse whitespace) → dedupe via `set`
2. **Near-duplicate pass**: `difflib.SequenceMatcher.ratio() > {SIMILARITY_THRESHOLD}` → drop
3. **Auto top-up**: loop continues generating batches until exactly
   {TARGET_PER_CATEGORY} unique tickets survive dedup per category

## Checkpoint / Resume

Progress is saved to `data/checkpoint.json` after each category completes.
Re-running the script skips already-finished categories automatically.

---
*Auto-generated by `generate_data.py` at the start of each run.*
"""
    PROMPT_DOC_PATH.write_text(doc, encoding="utf-8")
    print(f"Prompt template documented -> {PROMPT_DOC_PATH}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    client = genai.Client(api_key=API_KEY)

    # Document the prompt template before generation starts
    save_prompt_doc()

    checkpoint = load_checkpoint()
    all_tickets: list[tuple[str, str]] = []   # (text, category)

    # Re-load already-completed categories from checkpoint
    for cat, tickets in checkpoint.items():
        for t in tickets:
            all_tickets.append((t, cat))
        print(f"[resume] {cat}: {len(tickets)} tickets loaded from checkpoint")

    for category in CATEGORIES:
        if category in checkpoint:
            continue    # already done

        print(f"\n{'='*60}")
        print(f"Category: {category}")
        collected: list[str] = []
        batch_num = 0

        while len(collected) < TARGET_PER_CATEGORY:
            needed = TARGET_PER_CATEGORY - len(collected)
            # Request slightly more to absorb dedup losses
            request_n = min(BATCH_SIZE, needed + max(0, needed // 4))
            batch_num += 1
            print(f"  Batch {batch_num}: requesting {request_n} tickets "
                  f"(have {len(collected)}/{TARGET_PER_CATEGORY} after dedup)...")

            batch = generate_batch(client, category, request_n)
            combined = deduplicate(collected + batch)
            added = len(combined) - len(collected)
            collected = combined
            print(f"  -> got {len(batch)} raw, {added} new unique "
                  f"(total unique: {len(collected)})")

            # Polite delay between batches
            if len(collected) < TARGET_PER_CATEGORY:
                time.sleep(1.5)

        # Trim to exactly TARGET
        collected = collected[:TARGET_PER_CATEGORY]
        checkpoint[category] = collected
        save_checkpoint(checkpoint)

        for t in collected:
            all_tickets.append((t, category))

        print(f"  DONE: {len(collected)} unique tickets saved for '{category}'")

    # Write CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "category"])
        writer.writerows(all_tickets)

    print(f"\n{'='*60}")
    print(f"CSV written to: {CSV_PATH}")
    print(f"Total tickets : {len(all_tickets)}")
    for cat in CATEGORIES:
        count = sum(1 for _, c in all_tickets if c == cat)
        print(f"  {cat:<30} {count}")

if __name__ == "__main__":
    main()
