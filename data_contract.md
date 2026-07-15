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
| `data/raw/sr_bh_2020/data_capec_multilabel.csv` | **D7 — [SR-BH 2020](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/OGOIXX)** (honeypot thật, 12 ngày, 2020, đa nhãn CAPEC) | **527.813** dòng thật (không phải ~1 triệu như ước tính mẫu 10MB ban đầu — phân bố tấn công không đều theo thời gian trong file, ước tính bằng sampling đầu file bị sai lệch nặng). Cột `66 - SQL Injection`: **250.285** dòng (47,4% — **không phải tỷ lệ traffic thực tế**, đính chính lại nhận định trước đó). `000 - Normal`: 152.587 dòng. **Field cần decode URL-encoding trước khi tag** (`request_http_request`, `request_body`) — bỏ qua bước này làm sai lệch nghiêm trọng kết quả tagging ở lần chạy đầu. |
| `data/raw/payload_box/*.txt` | D4 — payload-box | 177 dòng payload thô (5 file theo DBMS + burp-intruder combined) |

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
| `source` | str | Nguồn gốc dòng: `d1_sqliv3`, `d1_benign_enriched_csic`, `d4_payloadbox`, `d7_srbh2020`, `synthetic_stacked` |
| `split` | str | `train` / `test` / `adversarial_test` — **cố định ngay từ đầu, không random lại giữa các lần chạy** (dùng seed=42, xem `configs/config.yaml: project.random_seed`) |

### 2.1. Phân phối tổng hợp thực tế (D1 + D4 + D7, đã tag bằng `src/preprocessing/multiclass_tagger.py`, decode URL trước khi tag)

| Nhãn | D1 | D4 | D7 (SR-BH) | **Tổng có sẵn** | **Target lấy cho train** |
|---|---:|---:|---:|---:|---:|
| `normal` | 19.517 | – | 152.587 (chưa gộp) | 19.517+ | ~15.000-20.000 |
| `union_based` | 2.213 | 16 | 83.189 | 85.418 | ~15.000 (undersample) |
| `error_based` | 373 | 0 | 7.423 | 7.796 | giữ hết (~7.800) |
| `boolean_blind` | 8.619 | 145 | 126.926 | 135.690 | ~15.000 (undersample) |
| `time_blind` | 141 | 16 | 32.747 | 32.904 | ~15.000 (undersample) |
| `stacked` | 0 | 0 | 0 | **0** | **363** (**sinh tổng hợp** — toàn bộ pool duy nhất từ `src/preprocessing/synthetic_stacked.py`, 11 prefix × 11 câu lệnh × 3 hậu tố, không nguồn thật nào có) |

**3 vấn đề đã xác nhận, cần xử lý ở Ngày 2:**
1. **`stacked` = 0 tuyệt đối** ở cả 3 nguồn (đã thử regex chặt lẫn lỏng) → phải tự viết payload tổng hợp theo template (`'; DROP TABLE...`, `'; EXEC xp_cmdshell...`), gắn `source=synthetic_stacked`, ghi rõ trong báo cáo đây là dữ liệu tự tạo không phải thu thập thật.
2. **`boolean_blind` là rổ chứa cuối, có nhiễu thật** — sanity-check tay trên mẫu SR-BH phát hiện dòng hoàn toàn benign (`/blog/wp-includes/js/comment-reply.min.js?ver=4.9.5`) vẫn mang nhãn gốc `SQL Injection=1` của SR-BH. **Không dùng nhãn gốc SR-BH làm chân lý tuyệt đối** — vẫn áp tagger của mình lên trên, và bắt buộc sanity-check tay ~100 mẫu/lớp trước khi train (Mục 3 gốc).
3. **Mất cân bằng nặng tự nhiên** (`boolean_blind`/`union_based` gấp 17-350 lần `error_based`) → undersample các lớp lớn về cùng bậc độ lớn (~15K), dùng **F1-macro** làm metric chính, không dùng Accuracy.

## 3.1. Kết quả build thực tế (`scripts/build_nhanh1_dataset.py`, chạy 15/7)

**Kiểm tra chất lượng nhãn gốc D7 trước khi gộp** (SR-BH là multi-label, 1 dòng có thể mang nhiều cờ tấn công cùng lúc):
- Trong 250.285 dòng `SQL Injection=1`: **99,1% "pure"** (không cờ tấn công khác nào bật cùng); **0,9% nhiễm chéo** (chủ yếu cùng bật `310 - Scanning for Vulnerable Software` — hợp lý, không phải lỗi).
- Trong 152.587 dòng `Normal=1`: **0% mâu thuẫn** với bất kỳ **cờ nhãn khác** trong SR-BH. Nhưng đây chỉ là so cờ, **không phải kiểm tra nội dung**.

**⚠️ Sanity-check tay đọc trực tiếp nội dung (không chỉ so cờ) phát hiện lỗi nghiêm trọng hơn:** trong mẫu 5-20 dòng `Normal=1` của D7 đọc tay, có dòng chứa `sleep(15)` (time-blind SQLi) và `cat /etc/passwd`, `() {{ :;}}; /bin/sleep 15` (Shellshock CVE-2014-6271) — **tấn công thật bị SR-BH tự gắn nhầm `Normal=1`**, dù không mâu thuẫn với cờ nào khác của chính nó. Đây là **nhiễu nhãn thật ở mức nội dung**, không phải chỉ nhiễm chéo giữa các cờ.
- **Xử lý:** thêm hàm `matches_any_attack_signature()` (`src/preprocessing/multiclass_tagger.py`) — lưới lọc độc lập với nhãn nguồn, kiểm tra nội dung canonical hoá có khớp bất kỳ regex tấn công SQLi (5 loại) hoặc OS command injection/Shellshock hay không. Áp cho mọi dòng được gắn `is_attack=False` trước khi chấp nhận vào pool `normal`.
- **Kết quả:** loại **1.561 dòng** (~5,6% pool normal ứng viên) bị gắn nhầm `Normal=1` nhưng nội dung thực chất là tấn công.
- **Giới hạn còn lại (không xử lý, ghi rõ vì ngoài phạm vi):** SR-BH có 12 loại tấn công (SSRF, path traversal...), filter hiện tại chỉ nhắm SQLi + OS command injection — các URL callback SSRF kiểu `owasp.org` vẫn có thể lọt vào pool `normal`. Chấp nhận được cho phạm vi Nhánh 1 (chỉ quan tâm SQLi), nhưng **cần làm kỹ hơn khi xây benign pool cho Nhánh 2** (anomaly detector nhạy với nhiễu benign hơn nhiều).

**Phân phối sau khi build + lọc (68.159 dòng, train=54.527 / test=13.632, stratified, seed=42):**

| Nhãn | Có sẵn (D1+D4+D7+synthetic, sau lọc) | Lấy vào train+test |
|---|---:|---:|
| `normal` | 27.941 (19.517 D1 + ~8.439 D7 normal sau khi loại 1.561 dòng nhiễu) | 15.000 |
| `union_based` | 85.826 | 15.000 |
| `error_based` | 7.796 | 7.796 (giữ hết) |
| `boolean_blind` | 134.057 | 15.000 |
| `time_blind` | 34.017 | 15.000 |
| `stacked` | 363 | 363 (giữ hết) |

File: `data/processed/nhanh1_train.csv` (68.159 dòng, cột đúng schema Mục 2). **Chưa qua sanity-check tay đầy đủ ~100 mẫu/lớp** (mới chỉ soi mẫu nhỏ 15-20/lớp) — nên làm thêm trước khi công bố số liệu chính thức trong báo cáo, nhưng đủ tin cậy để bắt đầu train baseline (Ngày 3).

⚠️ **Đính chính:** tỷ lệ SQLi trong toàn bộ SR-BH (527.813 dòng) là **47,4%**, không phải tỷ lệ thấp đại diện traffic thực như nhận định ban đầu (ước tính nhanh từ mẫu 10MB đầu file bị sai do tấn công phân bố không đều theo thời gian). SR-BH hữu ích vì **đa dạng payload thật**, không phải vì "tỷ lệ thực tế".

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
| `5` | `stacked` | Nối câu lệnh thứ 2 qua `;` | `;\s*(DROP\|INSERT\|UPDATE\|DELETE\|EXEC\|TRUNCATE\|CREATE\|GRANT\|ALTER)` |

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
