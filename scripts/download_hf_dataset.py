"""Download all CSV files from HF dataset individually.

The repo has 3 CSVs with different schemas, so load each file explicitly.
"""
from pathlib import Path
from datasets import load_dataset

OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    "nhanh1_train.csv": "Branch 1 — 68K rows, 6 classes (for supervised training)",
    "nhanh2_normal.csv": "Branch 2 — normal traffic (for unsupervised training)",
    "nhanh2_anomalous_eval.csv": "Branch 2 — anomalous eval set (all attack types)",
}

for fname, desc in FILES.items():
    print(f"\n=== Loading {fname} ({desc}) ===")
    ds = load_dataset("Jason-42195/VNU-SQLi-Detection", data_files=fname, split="train")
    df = ds.to_pandas()
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    out_path = OUT / fname
    df.to_csv(out_path, index=False)
    print(f"Saved to {out_path} OK")

print("\n=== All files downloaded ===")
