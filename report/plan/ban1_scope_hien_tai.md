# Report — AI-Based SQL Injection Detection System

## (Version 1 — current experimental scope: Branch 1 + Branch 2)

> Submission: Saturday, 25 Jul 2026. Scope: the 2 branches with real experimental results
> (Branch 1 supervised multi-class, Branch 2 anomaly detection) + demo notebook. Doesn't
> cover Branch 3/the full system in detail — see `ban2_hoan_chinh.md` (Version 2) for the
> full vision. *(Note: this file's target, previously at `report/final/ban2_hoan_chinh.md`,
> no longer exists on disk after the repo restructure — link left as a filename reference.)*

---

## 1. Problem Statement and Objectives

*(TODO — Diep: reuse Section 1 of `De_xuat_SQLi_Detection_AI.md`, drop the part framing Branch 3 as the focus)*

## 2. Related Work

*(TODO — reuse the existing survey as-is)*

## 3. Proposed Architecture (2 branches)

*(TODO — Branch 1 + Branch 2 diagram + simple verdict, see `train/notebooks/demo_detect.ipynb` section 2)*

## 4. Data and Preprocessing

*(TODO — D1/D4/D7 for Branch 1, D1/D3/D7 for Branch 2; canonicalization; see `data_contract.md`)*

## 5. Methodology

### 5.1 Branch 1 — Supervised multi-class
*(TODO — compare 4 architectures, chose TF-IDF+LogReg, rationale)*

### 5.2 Branch 2 — Anomaly Detection
*(TODO — Isolation Forest vs One-Class SVM, chose OCSVM, rationale)*

## 6. Experiments and Results

### 6.1 Branch 1
*(TODO — F1-macro=0.982, per-class, confusion matrix — see `report/metrics/branch1_eval.json`)*

### 6.2 Branch 2
*(TODO — FPR=0.3%, detection rate=20.7%, AUC=0.90 (OCSVM); ROC curve — see `report/metrics/branch2_eval.json`)*

### 6.3 Illustrative demo
*(TODO — results from `train/notebooks/demo_detect.ipynb`: sample input/output, sanity-check 19/20 correct on a 20-row sample)*

## 7. Discussion and Limitations

*(TODO — ~13% label noise in `boolean_blind`, D1 license unclear, adversarial testing not yet complete — see `data_contract.md`)*

## 8. Conclusion and Future Work

*(TODO — summarize the 2 completed branches; Branch 3 + the full system + Continual Learning are the next steps, see Version 2)*

## References

*(TODO — reuse from the existing survey)*
