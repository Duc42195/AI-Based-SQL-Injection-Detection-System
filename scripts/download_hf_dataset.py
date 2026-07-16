from datasets import load_dataset
import pandas as pd

ds = load_dataset("Jason-42195/VNU-SQLi-Detection", split="train")
df = ds.to_pandas()

print("Shape:", df.shape)
print("Columns:", list(df.columns))
print()
print("=== Label distribution ===")
print(df["label_name"].value_counts())
print()
print("=== Split distribution ===")
print(df["split"].value_counts())
print()
print("=== Normal rows (Branch 2) ===")
normal = df[df["label"] == 0]
print(f"Total normal: {len(normal)}")
print(f"  Train: {(normal['split']=='train').sum()}")
print(f"  Test: {(normal['split']=='test').sum()}")
print()
print("=== Sample normal rows ===")
cols = ["id", "query_raw", "source", "split"]
print(normal[cols].head(5).to_string(index=False))

df.to_csv("data/processed/nhanh1_train.csv", index=False)
print()
print("Saved to data/processed/nhanh1_train.csv OK")
