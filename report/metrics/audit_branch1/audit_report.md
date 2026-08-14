# Audit Day 1 — Branch 1 (Supervised Multi-class SQLi Classifier)

> Người thực hiện: Bách | Sprint 1 | `train/audit_branch1_data_validity.py`
> Mục đích: xác nhận data pipeline hợp lệ (không leakage/trùng/giả/nhiễu) để con số báo cáo (`report/metrics/branch1_eval.json`) đáng tin trước khi nộp/bàn giao.
> Số liệu chi tiết: `report/metrics/audit_branch1/findings.json` (chạy lại bằng `uv run python train/audit_branch1_data_validity.py`).

---

## Mảng 1 — Phân phối data: ✅ 5 lớp, cân bằng, không còn `stacked`

File kiểm: `data/processed/branch1_train.csv` (67,796 dòng; train 54,236 / test 13,560, split stratified seed 42).

| label_name | số dòng |
|---|---:|
| normal | 15,000 |
| union_based | 15,000 |
| error_based | 7,796 |
| boolean_blind | 15,000 |
| time_blind | 15,000 |

**Kết luận:** đúng 5 lớp, không còn phantom `stacked` (config `exclude_labels: [5]`). Source: `d7_srbh2020` 50,959 / `d1_sqliv3` 12,607 / `d7_srbh2020_normal` 4,206 / `d4_payloadbox` 24.

---

## Mảng 2 — Duplicate / leakage cross-split: ❌ CÓ cross-split leakage (cần dedup)

| Metric | Giá trị |
|---|---:|
| Tổng rows | 67,796 |
| distinct `query_canonical` | 63,519 |
| **extra copies (duplicate)** | **4,277** |
| distinct duplicate texts | 2,741 |
| **duplicate texts straddle train & test** | **949** |

**Chẩn đoán:** 4,277 dòng là bản copy của 2,741 text trùng nhau; trong đó **949 text xuất hiện ở CẢ train lẫn test** trong cùng file. Đây là **leakage vector** cho eval Branch 1 — model có thể "học thuộc" text ở train và nhận lại đúng nó ở test.

**Lưu ý:** con số 4,277 **khớp chính xác** rule dedup trong `train/build_mlops_split.py` ("corpus has 4,277 repeated texts that otherwise straddle train and golden"). Với Branch 1 eval tại chính file này, cần dedup theo `query_canonical` **trước khi split train/test** để loại vector trùng này.

---

## Mảng 3 — SSRF/OS-cmd mislabel & benign-pool contamination: ⚠️ CÓ — nhưng theo note mentor, SSRF trong `normal` là *acceptable for Branch 1*

| Pattern | Total | normal | boolean_blind |
|---|---:|---:|---:|
| `owasp.org` | 1,079 | 989 | 90 |
| `/etc/passwd` | 364 | 164 | 200 |
| `shellshock` | 197 | 0 | 197 |
| **Tổng SSRF** | **1,640** | **1,153** | **487** |

**Chẩn đoán:**
- **487 dòng SSRF/OS-cmd bị gán nhầm vào `boolean_blind`** (lớp SQLi) — label noise, **đã được ghi nhận là measured limitation (~13%)** trong `data_contract.md` §3.1.
- **1,153 dòng SSRF/OS-cmd nằm trong `normal`** (pool benign) — nhiễm bẩn tương tự vấn đề Nhánh 2 (chi tiết: `report/metrics/zeroday_experiment/branch2_ssrf_impact.json`).

**⚠️ Lưu ý quan trọng từ note mentor (`data_contract.md` §3.1):**
> *"SSRF callbacks (`owasp.org`) still leak into the `normal` pool. **Acceptable for Branch 1 (SQLi-only concern)**, but needs more rigor when building the benign pool for Branch 2."*

Tức là: **SSRF trong `normal` được mentor chấp nhận cho Branch 1** (Branch 1 chỉ quan tâm phân biệt SQLi vs not-SQLi, không phải benchmark benign). Việc **lọc SSRF nghiêm túc là ưu tiên của Branch 2** (anomaly detector nhạy với benign noise) — và đã được làm cho Branch 2.

**Vì vậy KHÔNG mặc định lọc SSRF cho Branch 1.** Đây là quyết định **cần mentor chốt**:
- **Không lọc** (mặc định theo note): giữ nguyên 1,153 SSRF trong `normal` — chấp nhận như limitation đã ghi. Chỉ cần re-caveat con số eval.
- **Có lọc** (nếu mentor muốn sạch khái niệm như Branch 2): dùng `src/utils/ssrf.py` (`is_leaky_row`) bỏ SSRF khỏi `normal` và `boolean_blind`, rebuild dataset — nhưng sẽ làm giảm một phần `normal` pool.

---

## Mảng 4 — Content-format duplication `/blog/index.php/2020/03`: ⚠️ rất nặng (17.6%)

| Metric | Giá trị |
|---|---:|
| Rows chứa `/blog/index.php/2020/03` | **11,920** (17.58%) |
| distinct canonical | 11,326 |
| Theo label | union_based 5,327 / error_based 3,444 / time_blind 2,076 / boolean_blind 962 / normal 111 |

**Chẩn đoán:** hơn 1/6 dataset là WordPress request-format (`/blog/index.php/2020/03/...`) — chủ yếu rơi vào `union_based`/`error_based`/`time_blind`. Đây là **content-format duplication** nặng: model có thể "ăn may" nhờ format chung thay vì học đa dạng payload thật. **Không phải lỗi** ở bản thân data (là request thật), nhưng làm giảm độ đa dạng per-class và làm lệch tỷ trọng đánh giá.

---

## Tổng kết & re-caveat trước khi nộp

1. **Con số cần re-caveat:** `branch1_eval.json` (F1-macro ~0.9822) chưa dedup cross-split (Mảng 2) → con số **lạc quan nhẹ**; chưa phản ánh label noise (Mảng 3) và content-format trùng (Mảng 4).
2. **Sạch & đáng tin:** phân phối 5 lớp cân bằng (Mảng 1), không phantom `stacked`.
3. **Hướng xử lý tiếp (cần mentor chốt):**
   - **Mảng 2 (cross-split dup):** đề xuất dedup `query_canonical` trước split — đây là điểm cần sửa rõ ràng (949 text trùng cả train & test là leakage vector).
   - **Mảng 3 (SSRF):** theo note mentor, SSRF trong `normal` là *acceptable for Branch 1* — **không lọc mặc định**; chỉ lọc nếu mentor muốn sạch khái niệm giống Branch 2. `boolean_blind` ~13% noise là measured limitation đã ghi nhận.
   - **Mảng 4 (`/blog` 17.6%):** content-format duplication — không phải lỗi data; cần ghi nhận để tránh đánh giá sai độ đa dạng.

**Deliverable Day 1:** báo cáo này + `findings.json`. Chưa sửa model; chỉ báo cáo & đề xuất để làm sạch data trước vòng train tiếp.
