# Phase 2 vs Phase 4 — B3 Training Pipeline

> So sánh trực quan quy trình xử lý dữ liệu và training Branch 3

---

## Phase 2: Feature Engineering (tạo dataset train B3)

B1 **đầy đủ 5 class** — mục đích: tạo feature vectors chuẩn cho B3 học.

```mermaid
flowchart LR
    subgraph "RAW CSV per class"
        F1[benign_train.csv]
        F2[boolean_blind_train.csv]
        F3[time_blind_train.csv]
        F4[query_splitting_train.csv]
    end

    subgraph "Step 1: Score từng câu với B1 (5 class)"
        B1M["branch1_v1<br/>5 class probabilities"]
        F1 --> B1M
        F2 --> B1M
        F3 --> B1M
        F4 --> B1M
    end

    subgraph "Step 2: Score từng câu với B2"
        B2M["branch2_v1<br/>1 anomaly score"]
        F1 --> B2M
        F2 --> B2M
        F3 --> B2M
        F4 --> B2M
    end

    subgraph "Step 3: Build session vectors"
        B1M --> BUILD["build_session_dataset.py<br/>5(B1) + 1(B2) + 1(timing) = 7-dim"]
        B2M --> BUILD
        TIME["timing_seconds"] --> BUILD
        BUILD --> NPY["branch3_session_features.npy<br/>(2000, 64, 7)"]
    end

    subgraph "Step 4: Train B3"
        NPY --> TRAIN["train_branch3.py<br/>GRU(7→32→4)"]
        TRAIN --> B3["branch3_v2.pt"]
    end
```

**Ví dụ 1 câu boolean_blind trong Phase 2:**

| step | B1_normal | B1_union | B1_error | B1_boolean | B1_time | B2_score | gap |
|------|-----------|----------|----------|------------|---------|----------|-----|
| 1 | 0.02 | 0.01 | 0.00 | **0.85** | 0.12 | -2.90 | 0.015 |
| 2 | 0.03 | 0.01 | 0.00 | **0.82** | 0.14 | -2.88 | 0.016 |
| 3 | 0.02 | 0.00 | 0.00 | **0.88** | 0.10 | -2.92 | 0.014 |

→ B1 cho boolean_blind probability cao → B3 dễ dàng học "cột này = boolean"

---

## Phase 4: Zero-Day Test (hard evaluation)

B1 **thiếu 1 class** — mục đích: test B3 có còn bắt được attack khi B1 mù không.

```mermaid
flowchart LR
    subgraph "RAW CSV (giống Phase 2)"
        G1[boolean_blind_test.csv]
        G2[benign_test.csv]
        G3[time_blind_test.csv]
        G4[query_splitting_test.csv]
    end

    subgraph "Step 1: Score với B1 variant"
        B1V["branch1_no_boolean_blind<br/>chỉ có 4 class probabilities<br/>boolean_blind luôn = 0.0"]
        G1 --> B1V
        G2 --> B1V
        G3 --> B1V
        G4 --> B1V
    end

    subgraph "Step 2: Score với B2 (giống Phase 2)"
        B2M2["branch2_v1"]
        G1 --> B2M2
        G2 --> B2M2
        G3 --> B2M2
        G4 --> B2M2
    end

    subgraph "Step 3: Build session vectors"
        B1V --> BUILD2
        B2M2 --> BUILD2
        TIME2["timing_seconds"] --> BUILD2
        BUILD2["eval_branch3_hard.py<br/>5(B1) + 1(B2) + 1(timing) = 7-dim<br/>nhưng B1_boolean luôn = 0"]
    end

    subgraph "Step 4: Train B3 từ đầu"
        BUILD2 --> TRAIN2["train NEW GRU<br/>trên data đã re-score"]
        TRAIN2 --> B3NEW["model tạm (chỉ để đo recall)"]
    end
```

**Ví dụ 1 câu boolean_blind trong Phase 4:**

| step | B1_normal | B1_union | B1_error | B1_boolean | B1_time | B2_score | gap |
|------|-----------|----------|----------|------------|---------|----------|-----|
| 1 | **0.70** | 0.12 | 0.08 | **0.00** | 0.10 | -2.90 | 0.015 |
| 2 | **0.68** | 0.14 | 0.09 | **0.00** | 0.09 | -2.88 | 0.016 |
| 3 | **0.72** | 0.11 | 0.07 | **0.00** | 0.10 | -2.92 | 0.014 |

→ B1 đẩy probability vào **normal** (0.70), không còn biết đây là boolean_blind nữa → B3 phải dựa vào B2 score + timing để đoán

---

## Tổng quan 2 Phase

```mermaid
flowchart TD
    subgraph "Phase 2 (Easy)"
        A["Query boolean_blind"] --> B["B1: phát hiện boolean=0.85"]
        A --> C["B2: score = -2.9"]
        B --> D["B3 input có tín hiệu boolean mạnh"]
        C --> D
        D --> E["B3: 'dễ, class 1'"]
    end
    
    subgraph "Phase 4 (Hard — zero-day)"
        F["Query boolean_blind"] --> G["B1 variant: boolean=0.0, normal=0.7"]
        F --> H["B2: score = -2.9"]
        G --> I["B3 input: mất tín hiệu boolean<br/>chỉ còn B2 + timing"]
        H --> I
        I --> J["B3: ???"]
        J --> K{"Nếu recall > 90%<br/>= B3 thực sự aggregate<br/>weak signal từ B2 + timing"}
        J --> L{"Nếu recall ≈ 0%<br/>= B3 chỉ dựa vào B1<br/>(= synthetic artifact)"}
    end
```

## Tại sao Phase 4 quan trọng?

Trong production, attacker có thể dùng kỹ thuật mới mà B1 chưa thấy bao giờ (zero-day). Nếu B3 chỉ dựa vào B1 thì vô dụng. Phase 4 kiểm tra: **B3 có thực sự aggregate weak signal từ B2 và timing pattern không?**

Kết quả thực tế: **không** — B3 chỉ đạt 0% recall cho boolean_blind khi B1 mù. Chứng tỏ B3 trên synthetic data hiện tại không có zero-day robustness.
