# Branch 3 — Session-Level SQL Injection Detection

## 1. Project Overview

3-branch architecture: **cả 3 nhánh đều chạy trên mọi request**, không phải routing chọn 1 nhánh.

```mermaid
flowchart TD
    subgraph Per-Request["Mỗi request đến → cả 3 nhánh cùng chạy"]
        R1["Request 1<br/>' OR 1=1 --"] --> P1["Preprocessing<br/>(canonicalize + features)"]
        P1 --> B1_1["Branch 1<br/>Supervised<br/>→ probs"]
        P1 --> B2_1["Branch 2<br/>Anomaly<br/>→ score"]
        P1 --> B3_1["Branch 3<br/>(chờ đủ steps)"]
    end
    
    subgraph Per-Request-2["Request 2 ... Request N"]
        R2["Request N<br/>' OR (ASCII('a')>65) --"] --> P2["Preprocessing"]
        P2 --> B1_2["Branch 1"]
        P2 --> B2_2["Branch 2"]
        P2 --> B3_2["Branch 3 (chờ)"]
    end
    
    B1_1 --> Store["Session Store<br/>(accumulate)"]
    B2_1 --> Store
    B1_2 --> Store
    B2_2 --> Store
    
    Store -->|"Đủ N steps hoặc idle timeout<br/>→ chạy B3"| B3["Branch 3<br/>Session Classifier<br/>→ session label"]
    
    B1_1 --> Decision["Decision Engine<br/>(tổng hợp B1 + B2 + B3)"]
    B2_1 --> Decision
    B1_2 --> Decision
    B2_2 --> Decision
    B3 --> Decision
    Decision --> Action["ALLOW / BLOCK / OVERKILL"]
```

**Giải thích:** B1 và B2 chạy real-time trên từng request (trả lời ngay). B3 là session-level — phải chờ gom đủ requests trong cùng session mới chạy. Decision engine chờ B3 xong mới ra quyết định cuối.

---

```mermaid
graph TB
    req["Raw Request"] --> c["Canonicalize &<br/>Feature Extract"]
    c --> B1["Branch 1<br/>Supervised Classifier<br/>TF-IDF + LogReg"]
    c --> B2["Branch 2<br/>Anomaly Detector<br/>One-Class SVM"]
    B1 --> B3["Branch 3<br/>Session-Level Classifier<br/>? (GRU vs LR)"]
    B2 --> B3
    B1 --> D["Decision Engine"]
    B2 --> D
    B3 --> D
```

| Branch | Input | Output | Algorithm |
|--------|-------|--------|-----------|
| B1 | Raw query text | 5-class probability vector | TF-IDF + LogisticRegression |
| B2 | Statistical features (length, special chars, entropy, keywords) | Anomaly score | One-Class SVM |
| B3 | Sequence of B1 + B2 scores across session steps | Session label (benign / attack type) | **GRU (current) → LR (proposed)** |

### 1.1. Ví dụ cụ thể — một session boolean-blind probing

Giả sử attacker đang dò ký tự đầu tiên của password bằng boolean-blind technique. Họ gửi 8 câu SQL vào hệ thống trong 3 giây:

**Dữ liệu đầu vào (3 nhánh đều nhận, song song):**

```
Request 1:  ' OR 1=1 --           (step 1)
Request 2:  ' OR 1=2 --           (step 2)
Request 3:  ' OR (ASCII('a')>65) --  (step 3)
... (8 requests tổng cộng)
```

**Step 1 — Canonicalize & Feature Extract** (chạy 1 lần cho cả 3 nhánh):

```mermaid
graph LR
    Raw["' OR 1=1 --"] --> Can["Canonical: or 1=1"]
    Raw --> Stats["length=7<br/>special_char_ratio=0.29<br/>sql_keyword_count=1<br/>entropy=1.25"]
```

**Step 2 — Cả 3 nhánh chạy song song trên cùng request:**

```mermaid
graph TD
    subgraph Input["Input: ' OR 1=1 -- (step 1 of 8)"]
        C["Canonical + Features"] --> B1
        C --> B2
    end
    
    B1["Branch 1: TF-IDF → LogReg"] --> B1_out["[normal: 0.92<br/>union: 0.01<br/>error: 0.02<br/>boolean: 0.04<br/>time: 0.01]"]
    B2["Branch 2: OCSVM<br/>on [length, char_ratio, keyword_count, entropy]"] --> B2_out["anomaly_score: -3.45<br/>is_anomaly: False"]
    
    B1_out --> Store["Session Store<br/>(accumulate per-step)"]
    B2_out --> Store
```

**Step 3 — Accumulate vào Session Store:**

```
Session ID: client_IP_1234
Steps gom lại bởi: client IP + idle_time < 30 phút

Step 1: B1=[0.92, 0.01, 0.02, 0.04, 0.01], B2=-3.45, gap=0.0s
Step 2: B1=[0.95, 0.01, 0.01, 0.02, 0.01], B2=-3.50, gap=0.4s
Step 3: B1=[0.88, 0.01, 0.01, 0.09, 0.01], B2=-3.30, gap=0.3s
... (8 steps)
```

**Step 4 — Khi session kết thúc (idle > 30 phút), B3 chạy:**

Per-step features (7-d) → aggregate → 16 session features:

```
mean(B1_probs)   = [0.91, 0.01, 0.01, 0.06, 0.01]
std(B1_probs)    = [0.03, 0.00, 0.00, 0.03, 0.00]
mean(B2_score)   = -3.40
std(B2_score)    = 0.10
mean(gap)        = 0.35
std(gap)         = 0.05
max(gap)         = 0.42
slope(gap)       = -0.02
```

**16 features** → LR classifier → **Session Label: boolean_blind (attack)**

**Step 5 — Decision Engine tổng hợp:**

| Branch | Output | Weight |
|--------|--------|--------|
| B1 | normal (confidence 0.92) | B1 bỏ sót — từng câu riêng trông normal |
| B2 | anomaly_score=-3.45 (normal) | B2 cũng bỏ sót — câu ngắn, ít ký tự đặc biệt |
| B3 | **boolean_blind attack** | **B3 phát hiện — vì cả session có pattern** |

→ Decision: **OVERKILL (HOLD for admin review)** vì B1=normal + B2=normal nhưng B3=attack.

**Điểm mấu chốt:** Từng câu riêng lẻ qua B1 trông vô hại, nhưng gom cả mớ requests nhanh + đều + cùng pattern → B3 phát hiện được.

---

## 2. Branch 3 — Chi tiết

### 2.1. Vấn đề

- B1 detect từng câu riêng lẻ → bỏ sót boolean-blind / time-blind probing vì mỗi câu riêng trông normal
- B2 detect bất thường từng câu → không có context về cả session
- Cần phát hiện: "1 câu bình thường, nhưng 50 câu giống nhau trong 5 giây là tấn công"

### 2.2. Data flow

```mermaid
flowchart LR
    subgraph Per-Step["Per Step (từng query)"]
        Q1["Query 1"] --> B1_1["B1: [5 probs]"]
        Q1 --> B2_1["B2: [1 score]"]
    end

    subgraph Session["Session (gom nhóm)"]
        S["Session: N steps"] --> F["Feature Aggregate<br/>16 features"]
        F --> M["Classifier<br/>GRU / LR / RF / XGB"]
        M --> Label["Session Label"]
    end

    PerStep --> Session
```

### 2.3. 7 per-step features → 16 session-level features

| # | Feature | Gốc |
|---|---------|-----|
| 1 | branch1_prob_normal | B1 probs |
| 2 | branch1_prob_union_based | B1 probs |
| 3 | branch1_prob_error_based | B1 probs |
| 4 | branch1_prob_boolean_blind | B1 probs |
| 5 | branch1_prob_time_blind | B1 probs |
| 6 | branch2_anomaly_score | B2 score |
| 7 | gap_seconds_log1p | Inter-request timing |

→ Mỗi session → `mean` + `std` cho 7 features (14) + `max` + `slope` cho gap (2) = **16 features**

```mermaid
graph LR
    P["Per-step (N × 7)"] --> A["mean(7)"]
    P --> S["std(7)"]
    P --> M["max(gap)"]
    P --> SL["slope(gap)"]
    A --> V["Session Vector<br/>16 features"]
    S --> V
    M --> V
    SL --> V
    V --> C["Classifier"]
```

### 2.4. 2 data sources

| Cách | Nguồn | Số sessions | Đặc điểm |
|------|-------|-------------|----------|
| **A** | Synthetic bisection simulation | 1,400 (350/class × 4) | Đều, sạch, dễ |
| **B** | sqlmap + Docker lab | 92 (20/36/36) | Real noise, không có class 3 |

**Vấn đề B2 polarity (cross-domain gap):**

```mermaid
graph TB
    subgraph A["Cách A (synthetic)"]
        A_ben["Benign<br/>B2 = -4.51"]
        A_att["Attack<br/>B2 = +2.31 ~ +10.98"]
    end
    subgraph B["Cách B (sqlmap)"]
        B_ben["Benign<br/>B2 = -3.60"]
        B_att["Attack<br/>B2 = -2.49 ~ -2.43"]
    end
```

Cùng attack type nhưng B2 score trái dấu vì data generation khác nhau → cross-domain chỉ đạt 0.47 dù LR là model tốt nhất.

### 2.5. Model comparison (5 architectures)

| Model | Test F1 | Cross A→B | Cross B→A | p50 Latency |
|--------|---------|-----------|-----------|-------------|
| GRU (current) | 1.0 | 0.2500 | 0.4367 | 1.20ms |
| **LogisticRegression** | **1.0** | **0.4722** | **0.4213** | **0.08ms** |
| RandomForest | 1.0 | 0.2500 | — | 31.24ms |
| LightGBM | 1.0 | 0.2500 | — | 1.15ms |
| XGBoost | 1.0 | 0.2500 | — | 0.79ms |

### 2.6. Tại sao GRU không cần thiết?

Shuffle test: xáo trộn thứ tự steps trong session → GRU **vẫn F1=1.0**

```mermaid
graph LR
    subgraph Original["Original Order"]
        S1["Step 1<br/>[B1, B2, gap]"] --> S2["Step 2"]
        S2 --> S3["Step 3"]
        S3 --> S4["Step 4"]
    end
    subgraph Shuffled["Shuffled Order"]
        T1["Step 3"] --> T2["Step 1"]
        T2 --> T3["Step 4"]
        T3 --> T4["Step 2"]
    end
    Original --> GRU["GRU → F1=1.0"]
    Shuffled --> GRU
```

**Cả Cách A lẫn Cách B đều không có sequence signal.** Autocorrelation step_n vs step\_{n-1} ≈ 0 cho cả 3 class.

### 2.7. Why not Deep Learning?

| Lý do | Evidence |
|-------|----------|
| No sequence signal | Shuffle test F1 drop = 0.0 |
| Feature space 16-dim, data ~1400 sessions | Small-data regime → DL overfit |
| Cross-domain: DL models = 0.25 (random), LR = 0.47 | DL capacity thừa → memorize pattern ảo |
| Giống B1: DistilBERT / CNN không better LR | Same conclusion across both branches |

---

## 3. Kế hoạch

```mermaid
graph TB
    A["P0: Confirm Architecture<br/>GRU → LR?"] -->|"Chờ mentor"| B["P1: Refactor<br/>branch3_session.py"]
    B --> C["P2: Train + push model<br/>lên HF"]
    C --> D["P3: Viết paper section<br/>(feature fusion narrative)"]
    D --> E["P4: Cross-domain research<br/>(improve A→B > 0.47)"]
```

| Priority | Task | Status |
|----------|------|--------|
| **P0** | Confirm swap GRU → LR với mentor | Chờ |
| P1 | Refactor code (nếu approved) | Chờ |
| P2 | Train model mới, push lên HF | Network blocked |
| P3 | Viết explanation cho paper | To do |
| P4 | Research cải thiện cross-domain | To do |

---

## 4. Files quan trọng

| File | Role |
|------|------|
| `src/models/branch3_session.py` | GRU model wrapper (cần refactor) |
| `src/models/branch3_features.py` | Shared helpers (feature extraction, eval) |
| `train/branch3_lr_features.py` | 16-dim session feature aggregator |
| `train/compare_branch3_architectures.py` | 5-model comparison |
| `train/analyze_cach_b_signal.py` | Cách B signal analysis |
| `configs/config.yaml` | Config (`branch3_session.*`) |
| `deploy/registry.py` | Model loading + inference (`Branch3Model`) |
| `report/metrics/branch3_architecture_comparison.json` | Comparison results |
| `report/metrics/cach_b_signal_analysis.json` | Signal analysis results |
| `report/metrics/branch3_final_report.json` | Consolidated final report |
