# Plan & Báo cáo — Audit dữ liệu Branch 1

> Người thực hiện: Bách | 14/08/2026 | theo chỉ đạo mentor "làm tiếp audit nhánh 1"
> Trạng thái: audit/báo cáo đã xong. CHƯA sửa data Branch 1 (chờ mentor chốt hướng).

## Báo cáo chi tiết

- Báo cáo đầy đủ: `report/metrics/audit_branch1/audit_report.md`
- Số liệu thô: `report/metrics/audit_branch1/findings.json`
- Notebook trực quan (4 fig IEEE, đã chạy sẵn): `train/notebooks/branch1_audit_visualization.ipynb`
- Script chạy lại: `train/audit_branch1_data_validity.py` -> `uv run python train/audit_branch1_data_validity.py`
- Test: `tests/test_audit_branch1_data_validity.py`

## Tóm tắt kết quả

| Mảng | Kiểm tra | Kết quả |
|---|---|---|
| 1 | Phân phối | 5 lớp cân bằng (normal/union/error/boolean/time), không phantom `stacked` |
| 2 | Duplicate cross-split | 4,277 extra copies; 949 text trùng ở cả train & test (leakage vector) |
| 3 | SSRF / OS-cmd | 1,640 dòng: 1,153 trong `normal`, 487 gán nhầm `boolean_blind` |
| 4 | Content-format `/blog/index.php/2020/03` | 11,920 dòng (17.58%), chủ yếu union/error/time_blind |

## Phân tích từng mảng

### Mảng 1 — Phân phối (không có vấn đề)

Dataset `data/processed/branch1_train.csv` (67,796 dòng; train 54,236 / test 13,560, stratified seed 42):

| label_name | số dòng |
|---|---:|
| normal | 15,000 |
| union_based | 15,000 |
| error_based | 7,796 |
| boolean_blind | 15,000 |
| time_blind | 15,000 |

Đúng 5 lớp, không còn phantom `stacked` (config `exclude_labels: [5]`). Nền tảng tốt để train.

### Mảng 2 — Duplicate / cross-split leakage (có vấn đề, cần sửa)

| Metric | Giá trị |
|---|---:|
| Tổng rows | 67,796 |
| distinct `query_canonical` | 63,519 |
| extra copies (duplicate) | 4,277 |
| distinct duplicate texts | 2,741 |
| duplicate texts trùng ở cả train & test | 949 |

949 text xuất hiện ở cả train lẫn test trong cùng file -> leakage vector cho eval Branch 1.
Con số 4,277 khớp chính xác rule dedup trong `train/build_mlops_split.py`
("corpus has 4,277 repeated texts that otherwise straddle train and golden").

**Đề xuất:** dedup `query_canonical` trước khi split train/test để loại 949 text trùng.

### Mảng 3 — SSRF / OS-cmd (có vấn đề, nhưng theo note mentor không lọc mặc định)

| Pattern | Total | normal | boolean_blind |
|---|---:|---:|---:|
| `owasp.org` | 1,079 | 989 | 90 |
| `/etc/passwd` | 364 | 164 | 200 |
| `shellshock` | 197 | 0 | 197 |
| Tổng SSRF | 1,640 | 1,153 | 487 |

- 487 dòng gán nhầm vào `boolean_blind` (lớp SQLi): label noise, đã ghi nhận là measured
  limitation (~13%) trong `data_contract.md` §3.1.
- 1,153 dòng nằm trong `normal`: nhiễm bẩn benign pool, tương tự vấn đề Branch 2.

Lưu ý từ note mentor (`data_contract.md` §3.1):
> "SSRF callbacks (owasp.org) still leak into the normal pool. Acceptable for Branch 1
> (SQLi-only concern), but needs more rigor when building the benign pool for Branch 2."

Tức là SSRF trong `normal` được mentor chấp nhận cho Branch 1 (Branch 1 chỉ quan tâm
SQLi vs not-SQLi); việc lọc SSRF nghiêm túc là ưu tiên của Branch 2 (đã làm xong cho Branch 2).

**Kết luận:** KHÔNG lọc SSRF mặc định cho Branch 1. Chỉ lọc bằng `src/utils/ssrf.py`
nếu mentor chốt muốn sạch khái niệm giống Branch 2. `boolean_blind` ~13% noise là
measured limitation đã ghi nhận.

### Mảng 4 — Content-format duplication `/blog/index.php/2020/03` (ghi nhận)

| Metric | Giá trị |
|---|---:|
| Rows chứa `/blog/index.php/2020/03` | 11,920 (17.58%) |
| distinct canonical | 11,326 |
| Theo label | union_based 5,327 / error_based 3,444 / time_blind 2,076 / boolean_blind 962 / normal 111 |

Hơn 1/6 dataset là WordPress request-format -> content-format duplication nặng, model có
thể "ăn may" nhờ format chung thay vì học đa dạng payload thật. Không phải lỗi data (là
request thật) nhưng làm giảm độ đa dạng per-class.

## Re-caveat con số báo cáo

`report/metrics/branch1_eval.json` (F1-macro ~0.9822) cần re-caveat vì:
1. Chưa dedup cross-split (Mảng 2) -> con số lạc quan nhẹ.
2. Chưa phản ánh label noise `boolean_blind` (Mảng 3) và content-format trùng (Mảng 4).

## Hướng xử lý tiếp (chờ mentor chốt)

1. Mảng 2 (cross-split dup): đề xuất dedup `query_canonical` trước split — điểm sửa rõ ràng.
2. Mảng 3 (SSRF): theo note mentor là acceptable for Branch 1 — không lọc mặc định.
3. Mảng 4 (`/blog` 17.6%): không phải lỗi data; ghi nhận để tránh đánh giá sai độ đa dạng.
4. Nếu mentor đồng ý: rebuild `branch1_train.csv` + re-train + re-eval -> cập nhật `branch1_eval.json`.
