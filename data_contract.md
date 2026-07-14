# Data Contract — Nhánh 1 (đa lớp) & Nhánh 3 (session)

> Chốt Ngày 1 (13/7). Định nghĩa schema đích cho dữ liệu đã xử lý, để mọi thành viên (và code sau này) dùng chung một chuẩn. Số liệu dưới đây đã verify thực tế trên dữ liệu vừa tải, không phải ước tính.

---

## 1. Dữ liệu thô đã tải (Ngày 1)

| File | Nguồn | Số liệu verify thực tế |
|---|---|---|
| `data/raw/d1_sqliv3_raw.csv` | [nidnogg/sqliv5-dataset](https://github.com/nidnogg/sqliv5-dataset) (mirror của Kaggle SQLiV3) | 30.918 dòng parse được (1 dòng lỗi do dấu phẩy không escape — dòng gốc thứ 19293); nhãn gốc: **19.517** label=0, **11.347** label=1; phát hiện **15 dòng null** text, **46 text trùng lặp**, **15 dòng trùng hoàn toàn** |
| `data/raw/csic2010/normalTrafficTraining.txt` | [GSI/UdelaR GitLab mirror](https://gitlab.fing.edu.uy/gsi/web-application-attacks-datasets) | **36.000** HTTP request thô |
| `data/raw/csic2010/normalTrafficTest.txt` | nt. | **36.000** HTTP request thô |
| `data/raw/csic2010/anomalousTrafficTest.txt` | nt. | **25.065** HTTP request thô |
| `data/raw/d3_csic2010_raw.csv` | Đóng gói 3 file trên bằng `scripts/fetch_and_wrap_d3_csic2010.py` | **97.065** dòng (72.000 normal + 25.065 anomalous), cột: `id, split, label, raw_request`. Có header `Cookie: JSESSIONID=...` → dùng để nhóm session ở Nhánh 3 (Cách B benign). |

**Lưu ý D1 (cần xử lý ở Ngày 2 — canonicalization/cleaning):**
- Dòng lỗi CSV (dấu phẩy/quote không đúng chuẩn trong text) → phải parse bằng `csv` module với `quoting=csv.QUOTE_ALL` hoặc sửa tay dòng lỗi, không dùng `pd.read_csv` mặc định.
- Khử 15 dòng null + 15 dòng trùng hoàn toàn.
- Tỷ lệ lớp gốc (63%/37%) không phản ánh traffic thật (<1% tấn công) → báo cáo Precision/Recall tại FPR thấp, không chỉ Accuracy.

**Lưu ý D3:** đây là HTTP request thô (có header, cookie, body), **không phải câu SQL thuần**. Cần bước trích tham số (query string / POST body) trước khi đưa vào canonicalization giống D1.

---

## 2. Schema đích — Nhánh 1 (Supervised, đa lớp)

File: `data/processed/nhanh1_train.csv` (sản phẩm Ngày 2).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | int | ID duy nhất, tăng dần |
| `query_raw` | str | Text gốc, chưa xử lý (giữ để audit) |
| `query_canonical` | str | Sau canonicalization: decode encoding (URL/hex/CHAR), fold case keyword SQL |
| `has_comment_marker` | int (0/1) | Cờ đánh dấu có `/* */` hoặc `--` (KHÔNG xóa comment, chỉ đánh dấu — feature chống evasion) |
| `label` | int (0-5) | Nhãn đa lớp — xem bảng nhãn Mục 3 |
| `label_name` | str | Tên nhãn dạng người đọc (`normal`, `union_based`, ...) |
| `source` | str | Nguồn gốc dòng: `d1_sqliv3`, `d1_benign_enriched_csic`, `d4_payloadbox` |
| `split` | str | `train` / `test` / `adversarial_test` — **cố định ngay từ đầu, không random lại giữa các lần chạy** (dùng seed=42, xem `configs/config.yaml: project.random_seed`) |

**Nguyên tắc:** `query_canonical` được sinh bởi `src/preprocessing/canonicalize.py` (Ngày 2) — một hàm thuần (pure function) để test dễ, không phụ thuộc I/O.

---

## 3. Bảng nhãn đa lớp (Nhánh 1) — áp dụng bằng rule-based tagger

Thứ tự ưu tiên khi một payload khớp nhiều dấu hiệu: **stacked > time_blind > error_based > union_based > boolean_blind**.

| Mã | Tên | Ý nghĩa | Dấu hiệu chính (regex, không phân biệt hoa/thường) |
|---|---|---|---|
| `0` | `normal` | Query hợp lệ | Không khớp luật 1-5 nào |
| `1` | `union_based` | Ghép dữ liệu bảng khác qua `UNION SELECT` | `UNION\s+(ALL\s+)?SELECT` |
| `2` | `error_based` | Ép DB lộ dữ liệu qua lỗi | `EXTRACTVALUE\|UPDATEXML\|FLOOR\(RAND\|CAST\(.*AS\|CONVERT\(` |
| `3` | `boolean_blind` | Suy luận qua điều kiện đúng/sai | `(OR\|AND)\s+\d+\s*=\s*\d+`, `'\s*OR\s*'?1'?\s*=\s*'?1` (rổ chứa cuối cho các payload tấn công còn lại không khớp luật khác) |
| `4` | `time_blind` | Suy luận qua độ trễ phản hồi | `SLEEP\(\|BENCHMARK\(\|WAITFOR\s+DELAY\|PG_SLEEP\(` |
| `5` | `stacked` | Nối câu lệnh thứ 2 qua `;` | `;\s*(DROP\|INSERT\|UPDATE\|DELETE\|EXEC)` |

**Sanity-check bắt buộc (Ngày 2):** lấy mẫu ngẫu nhiên ~100 payload/lớp, kiểm tra tay tỷ lệ tagger gán đúng — ghi số liệu vào báo cáo (Mục 6.2). Nhãn tự động, không phải nhãn "vàng" (gold), phải minh bạch điều này.

**Dự kiến mất cân bằng:** `stacked` và `time_blind` nhiều khả năng hiếm trong D1 → bổ sung bằng cách lọc D4 (payload-box, chia theo DBMS) qua cùng bộ regex trên, và ghi rõ trong data_contract khi bổ sung xong.

---

## 4. Schema đích — Nhánh 3 (Session-level)

File: `data/processed/nhanh3_sessions_labeled.csv` (Ngày 8, sau khi có D1 gán nhãn + capture sqlmap).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `session_id` | str | `session_id` gốc (nếu có) hoặc `f"{client_ip}_{window_start}"` |
| `step_index` | int | Thứ tự query trong session (bắt đầu từ 0) |
| `query_raw` / `query_canonical` | str | Giống schema Nhánh 1 |
| `branch1_label` | int (0-5) | Nhãn per-query kế thừa từ Nhánh 1 (không tự đoán lại) |
| `branch2_anomaly_score` | float | Điểm bất thường liên tục từ Nhánh 2 (train benign-only) |
| `timestamp` | float/ISO8601 | Thời điểm request — dùng để tính session window |
| `session_label` | int (0-3) | Nhãn **cấp session** — chỉ có giá trị ở dòng cuối session hoặc lặp lại mọi dòng (quyết định khi code) |
| `session_source` | str | `A_simulated` (script mô phỏng) hoặc `B_sqlmap_docker` (traffic thật) |

**Định nghĩa session:** `session_id` có sẵn (cookie CSIC) HOẶC `(client_ip, idle_gap <= 1800s)` — theo đúng `configs/config.yaml: branch3_session.session_idle_gap_seconds`.

**Bảng nhãn session** (đối chiếu `configs/config.yaml: branch3_session.session_classes`):

| Mã | Tên | Ý nghĩa |
|---|---|---|
| `0` | `benign` | Session không có ý đồ tấn công |
| `1` | `boolean_blind` | Chuỗi query dò đúng/sai (binary search qua nhiều request) |
| `2` | `time_blind` | Chuỗi query dò qua độ trễ |
| `3` | `query_splitting` | Payload tấn công bị chia nhỏ qua nhiều request liên tiếp |

---

## 5. Việc còn lại liên quan tới contract này (không thuộc phạm vi Ngày 1)

- [ ] Viết `src/preprocessing/canonicalize.py` theo đúng cột `query_canonical` + `has_comment_marker` ở trên (Ngày 2).
- [ ] Viết rule-based tagger đa lớp (Mục 3) + sanity-check tay (Ngày 2, trước khi train Ngày 3).
- [ ] Trích tham số từ `raw_request` của D3 (query string/POST body) trước khi canonicalize (Ngày 2, phần Nhánh 2 — Bách).
- [ ] Bổ sung D4 (payload-box) cho lớp hiếm sau khi đo phân phối thực tế.
