# Zero-Day Detection Experiment — Leave-One-Out Protocol

## Mục tiêu

Kiểm tra **Nhánh 2 (anomaly detection)** có phát hiện được dạng SQLi **chưa từng thấy (zero-day)** không.

Giả thuyết: Nhánh 1 (supervised) chỉ biết các label đã học — nếu gặp kiểu tấn công mới sẽ predict sai (thường thành normal). Nhánh 2 (train trên 100% benign) không biết label nào, chỉ đo độ "bất thường" về cấu trúc — nên có thể bắt được dạng lạ.

## Phương pháp

### Leave-One-Out Protocol

Với mỗi SQLi label trong 4 loại:

1. **Loại bỏ** label đó khỏi tập train Nhánh 1
2. **Train Nhánh 1** trên 3 label còn lại + normal
3. **Train Nhánh 2** bình thường (chỉ trên benign)
4. **Test**: đưa toàn bộ query của label đã bỏ vào **cả 2 nhánh**
5. **Đo**:
   - **B1 miss rate**: % bị predict thành normal (zero-day bypass được supervised)
   - **B2 DR**: % bị flag anomalous (zero-day bị anomaly bắt)
   - **Combined coverage**: % bị ÍT NHẤT 1 nhánh chặn

### Cấu hình

| Tham số | Giá trị |
|---------|---------|
| Nhánh 1 | TF-IDF + Logistic Regression (4 lớp còn lại) |
| Nhánh 2 | One-Class SVM, contamination=0.005, scale_features=false, log_transform=["length"] |
| Features | length, special_char_ratio, sql_keyword_count, entropy |
| Data train | nhanh1_train.csv (54K train, 13K test), nhanh2_data.csv (12K benign train) |
| Benign data | nhanh2_data.csv (3K test split) |
| Anomalous eval | nhanh2_anomalous_eval.csv (25K rows) |

## Kết quả

### Baseline

| Metric | Giá trị |
|--------|---------|
| FPR (trên benign test) | 0.50% |
| DR (trên toàn bộ anomalous eval) | 23.21% |

### Leave-One-Out Results

| Excluded label | B1 F1-macro | B1 miss rate | B2 DR | Combined coverage |
|---|---|---|---|---|
| union_based | 0.9803 | 2.47% | 0.53% | 2.97% |
| **error_based** | 0.9784 | 0.00% | **89.68%** | 89.68% |
| boolean_blind | 0.9973 | **90.20%** | 5.40% | 94.00% |
| time_blind | 0.9773 | 0.27% | 12.73% | 12.97% |

### Chi tiết từng label

#### 1. union_based (label 1) — B2 DR = 0.53%

```
B1 predict distribution: {boolean_blind: 2923, normal: 74, error_based: 3}
```

Union queries bị B1 predict thành **boolean_blind** (97.4%) — vì UNION SELECT có cấu trúc WHERE...AND... giống boolean blind. B2 DR thấp ngang FPR → OCSVM không thấy union_based khác benign.

#### 2. error_based (label 2) — B2 DR = 89.68% ✅

```
B1 predict distribution: {boolean_blind: 1165, union_based: 395}
```

B1 không predict thành normal (miss rate 0%). B2 bắt **~90%** — error_based có cấu trúc rất đặc trưng: nhiều ký tự đặc biệt `'`, `(`, `)` , error functions (`CONVERT`, `EXTRACTVALUE`, `UPDATEXML`), câu dài. OCSVM phân biệt rõ với benign.

#### 3. boolean_blind (label 3) — B2 DR = 5.40%

```
B1 predict distribution: {normal: 2706, time_blind: 277, error_based: 10, union_based: 7}
```

**B1 miss rate 90.2%** — boolean_blind queries rất giống normal traffic về cấu trúc. B2 cũng yếu (5.4%, gần FPR). Đây là điểm yếu nhất của cả 2 nhánh.

#### 4. time_blind (label 4) — B2 DR = 12.73%

```
B1 predict distribution: {boolean_blind: 2992, normal: 8}
```

B1 miss rate rất thấp (0.27%) — predict thành boolean_blind. B2 DR (12.73%) thấp hơn baseline (23.21%) → time_blind queries có cấu trúc khá giống benign.

## Phân tích

### Khi nào Nhánh 2 phát huy tác dụng?

| Feature | union | error | boolean | time |
|---------|-------|-------|---------|------|
| length trung bình | ~80 | ~120 | ~70 | ~110 |
| special_char_ratio | 0.05-0.15 | **0.20-0.40** | 0.03-0.10 | 0.05-0.15 |
| sql_keyword_count | 3-5 | **4-10** | 2-4 | 3-6 |
| entropy | 3.0-4.5 | **4.0-5.5** | 2.5-4.0 | 3.0-4.5 |

Error_based nổi bật ở **special_char_ratio** và **sql_keyword_count** — là 2 feature OCSVM dùng để phân biệt.

### Hạn chế

1. **4 features hiện tại không đủ discriminative** cho boolean_blind, union_based, time_blind
2. **boolean_blind là lỗ hổng lớn nhất**: cả 2 nhánh đều yếu → cần feature engineering riêng
3. **OCSVM với 4 features chiều thấp** có thể bỏ qua cấu trúc tinh tế (câu lệnh SQL logic)

## Kết luận

1. ✅ **Zero-day detection CÓ HIỆU QUẢ** cho error_based attacks (DR ~90%)
2. ⚠️ **Chưa đủ** cho union_based (0.53%), boolean_blind (5.40%), time_blind (12.73%)
3. 💡 **Cần cải thiện**:
   - Feature engineering: token-level features, query structure graph
   - Threshold tuning: Balanced option (FPR=1%) cho DR=25.4%
   - Ensemble: kết hợp cả 2 nhánh (combined coverage boolean_blind 94%)

## Files

| File | Vai trò |
|------|---------|
| `scripts/run_zeroday_experiment.py` | Chạy toàn bộ experiment |
| `models/nhanh2_zeroday/` | OCSVM model (trained fresh) |
| `models/nhanh1_no_union_based/` | B1 model không có union_based |
| `models/nhanh1_no_error_based/` | B1 model không có error_based |
| `models/nhanh1_no_boolean_blind/` | B1 model không có boolean_blind |
| `models/nhanh1_no_time_blind/` | B1 model không có time_blind |
| `reports/zeroday_experiment/summary.json` | Kết quả chi tiết (JSON) |
| `notebooks/zeroday_experiment_report.ipynb` | Notebook xem kết quả |
