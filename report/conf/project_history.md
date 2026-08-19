# Lịch sử dự án — theo từng phần

> Chuyển thể từ các khối STATUS rải rác trong [`outline.md`](outline.md) (24/7, 7/8, 9/8) thành 1 file duy nhất, tổ chức theo **từng phần của dự án** thay vì theo mục bài báo, để dễ tra cứu "phần này đã làm gì". `outline.md` vẫn giữ nguyên làm kế hoạch viết bài — file này chỉ tổng hợp lại lịch sử thực tế, không thay thế.
>
> Quy ước: mỗi phần liệt kê ngắn gọn (a) đã làm gì, (b) kết quả/số liệu chốt, (c) còn thiếu/đang làm. Cập nhật bằng cách **thêm mục mới có ngày**, không xoá lịch sử cũ.

---

## 1. Data pipeline & datasets (D1–D7)

- **13/7**: Chốt data contract (`report/plan/data_contract.md`) — D1 SQLiV3 (30.918 dòng, nhãn nhị phân SQLi), D3 CSIC2010 (97.065 dòng, nhị phân normal/anomalous, **không phải SQL thuần** — là HTTP request đầy đủ), D4 payload-box (177 payload), D7 SR-BH2020 (527.813 dòng, multi-label CAPEC, cột "66 - SQL Injection"=250.285).
- **15/7**: `load_d3()` thêm bước trích tham số từ raw HTTP request (bỏ header/cookie, giữ URL+body).
- Phát hiện label noise thật: D7 có dòng gắn nhãn `Normal=1` nhưng nội dung là tấn công thật (`sleep(15)`, Shellshock) — tagger tự xây chưa đủ tin cậy để lọc sạch loại tấn công ngoài SQLi khỏi D3.
- **16/8 (bug lớn nhất phiên)**: `train/build_branch2_data.py` load nhầm `branch1_train.csv` (pool bị undersample, chỉ D1+D7, 15K dòng) thay vì đúng `branch2_normal.csv` (91.935 dòng, đủ D1+D3+D7, không cap). Sửa xong — mọi kết quả Branch 2 từ 16/7 đến 16/8 (1 tháng) từng train trên 1/6 dữ liệu benign đáng lẽ có.
- **17-19/8 (đang tiến hành, chưa merge)**: Điều tra sâu tại sao D3/D7 vẫn khó hơn D1 dù đã sửa bug trên — phát hiện D3/D7 là **HTTP request nguyên khối** (URL+path+tham số), không phải câu SQL thuần như thiết kế hệ thống yêu cầu (hệ thống đặt ở DB proxy, chỉ nhận câu SQL đã build xong). Thêm bước lọc bỏ scheme/host/path, chỉ giữ phần query-string/body — nâng DR@FPR5% từ 26,2% lên 80,0% khi kết hợp với thuật toán mới (xem mục Branch 2).

## 2. Branch 1 — Supervised multi-class classifier

- Thuật toán chốt: TF-IDF + Logistic Regression, 5 lớp (normal, union_based, error_based, boolean_blind, time_blind). Lý do chọn LogReg: chênh F1 giữa 4 kiến trúc thử nghiệm không đáng kể (0,982–0,991), LightGBM chậm hơn ~115 lần (~92ms — quá chậm cho proxy real-time), DistilBERT tốn 256MB + cần GPU.
- **Kết quả chốt**: F1-macro = 0,982, n=13.560 (test set), 68.159 dòng train, lớp `stacked` bị loại (100% synthetic, không đáng tin).
- Trọng số CNN + DistilBERT (5 lớp) công bố thêm trên HF (`Jason-42195/VNU-SQLi-Detection-Models/branch1_comparison/`) làm đối chứng, không dùng production.
- Artifact: `report/metrics/branch1_eval.json`, `branch1_architecture_comparison.json`, `figures/branch1_roc_per_class.png`.

## 3. Branch 2 — Anomaly detector (unsupervised)

Nhiều lần đổi hướng, ghi theo mốc thời gian:

- **Ban đầu**: OCSVM/IsolationForest trên 4 feature thống kê (length, special_char_ratio, sql_keyword_count, entropy). AUC~0,90 nhưng dùng đúng bộ data bị bug (mục 1).
- **15/8**: Thêm `bigram_entropy` — về sau (16-17/8) xác định đây là **domain-confound artifact** (đo được "văn bản từ nguồn nào" chứ không phải "có phải tấn công"), không phải tín hiệu thật.
- **16/8**: Sửa bug nguồn data (mục 1). DR rơi mạnh khi thêm D3-benign vào train đúng thiết kế — lộ ra bigram_entropy là giả.
- **17/8**: Thêm `quote_imbalance` (đếm dấu nháy chưa đóng cặp) thay bigram_entropy. Bộ chính thức: `special_char_ratio + entropy + quote_imbalance`, OCSVM nu=0,001/gamma=0,01. **DR@FPR-khớp-5% = 26,2%, AUC = 0,792** (số hiện đang là baseline trên `main`).
- **17-19/8 (nhánh `fix/branch2-use-uncapped-pool`, đang làm, CHƯA merge)**: Điều tra tại sao D3 vẫn khó hơn D1/D7 dù đã sửa bug domain-confound — phát hiện chuỗi nguyên nhân:
  1. D3/D7's "anomalous" set chỉ ~8,7-14,8% khớp được signature SQLi/XSS/OS-cmd đã biết → phần lớn là loại tấn công khác CSIC2010, không phải SQLi thuần.
  2. D3/D7 là **HTTP request đầy đủ**, không phải câu SQL — sai lệch với thiết kế hệ thống (đặt ở DB proxy, chỉ nhận SQL đã build). Thêm bước lọc scheme/host/path, chỉ giữ tham số.
  3. Test nhiều kiến trúc: 1 model gộp 3 nguồn (OCSVM/IsolationForest, tệ hơn train riêng từng nguồn), ensemble OR 3 model riêng theo domain (thất bại, FPR ~41%), model nặng hơn nhiều chiều (IsolationForest 12 feature × 500 cây × max_samples=1.0: DR=61,4%/AUC=0,837), rồi **LocalOutlierFactor** (mật độ cục bộ, n_neighbors=5): **DR@FPR5% = 80,0%, AUC = 0,900** — tốt nhất từ trước đến nay.
  4. Thêm 6 feature cấu trúc mới vào `statistical_features.py`: `same_type_run_ratio, max_token_length, token_count, max_special_run, max_digit_run, paren_imbalance` — các feature "đỉnh cục bộ" thay vì tỉ lệ toàn chuỗi, giải quyết đúng vấn đề D3/D7 dài (payload bị pha loãng trong URL/tham số dài).
  - **19/8, chính thức hoá xong, đã merge**: thêm hỗ trợ LOF vào `AnomalyDetector`, cập nhật `build_branch2_dataset.py` (lọc URL + gộp attack cả 3 nguồn D1+D3+D7), retrain chính thức trên `local_outlier_factor` (n_neighbors=5, 12 feature) → **DR@FPR5%=80,6%, AUC=0,929** (`report/metrics/branch2_eval.json`), hiệu chỉnh lại Branch 3 (`content_threshold=0,3383`, giữ nguyên FPR=0,0/DR=1,0), cập nhật MLOps drift monitor (`FEATURES` còn 4 tín hiệu tổng quát, giảm `baseline_windows` 5→2 do pool co lại), `uv run pytest` xanh (248 test), xem chi tiết `report/plan/data_contract.md` §3.4.
  - **19-20/8, sửa biểu đồ + xác nhận thành phần benign pool**:
    - `report/metrics/figures/branch2_score_dist.png` và `branch2_threshold_tradeoff.png` bị hỏng do đặc tính LOF: điểm số là tỉ số mật độ không bị chặn trên, ~1-3% dòng (rơi vào vùng train có nhiều điểm gần-trùng-lặp) có giá trị cực lớn (hàng tỷ), kéo trục biểu đồ giãn ra khiến toàn bộ phần thông tin thật bị nén thành 1 lát mỏng sát 0. Sửa: cắt viewport hiển thị về percentile 0,5-97 (`train/generate_metrics.py`), số liệu CSV/JSON gốc giữ nguyên đầy đủ, không đổi.
    - Thử `density=True` để so 2 nhãn công bằng dù n chênh lệch (benign=7.929 vs anomalous=270.002) — theo phản hồi, đổi sang **undersampling** thay vì chuẩn hoá density: lấy ngẫu nhiên (seed=42) 7.929 dòng anomalous để n bằng benign, vẽ tần suất thô — mỗi điểm trên biểu đồ vẫn là 1 quan sát thật, không bị "nhân tạo" qua chuẩn hoá.
    - Xác nhận lại benign pool (`branch2_data_clean.csv`, 36.502 dòng) vẫn lấy từ cả 3 nguồn: D1=16.214, D7=10.979, D3=9.309. Số nhỏ hơn nhiều so với bản gốc (91.935) vì bước lọc URL wrapper (19/8) loại **114.926/121.521 (~95%) dòng bị loại đến từ D3/D7** — phần lớn traffic "benign" trong 2 bộ này là request tĩnh (ảnh/JS/CSS, không tham số) nên sau khi bỏ path thì không còn nội dung nào để tính feature — đúng scope, không phải bug.

## 4. Branch 3 — Session Correlator

- **Thiết kế đầu**: GRU sequence-model trên chuỗi `[xác suất Branch 1 ⊕ điểm Branch 2]` mỗi bước. Báo cáo ban đầu F1-macro = 1,0.
- **Điều tra lại**: F1=1,0 nghi bị thổi phồng do 2 bug thật trong pipeline train/eval + vấn đề gốc: cho GRU ăn *xác suất* (đã qua softmax) thay vì tín hiệu thô làm mất tín hiệu phân biệt giữa các bước session (đo được: cosine similarity TF-IDF giữa 2 bước = 0,961 trong khi xác suất sau phân loại gần như giống hệt nhau — bottleneck thông tin thật).
- **Thiết kế lại (chốt, đang dùng)**: `SessionCorrelator` (`src/models/branch3_session.py`) — KHÔNG phải model train riêng, mà tái dùng Branch 1 (content check, ghép toàn bộ query trong session) OR với Branch 2 (behavior check, gộp điểm bất thường từng query), 4 ngưỡng hiệu chỉnh riêng.
- **Kết quả thật** (test set 280 session, tách biệt hoàn toàn train): FPR (benign) = 0,0; detection rate = 1,0 cho `boolean_blind`/`time_blind`/`query_splitting`, cả 3 cấu hình ablation (content-only/behavior-only/kết hợp).
- **8/8**: `content_threshold` chuyển từ dùng chung ngưỡng 0,5 của Branch 1 sang hiệu chỉnh riêng theo session trên tập TRAIN — nâng content-only `query_splitting` từ 0,971 lên 1,0.
- **Zero-day ablation**: content-check rơi về DR=0,0 khi Branch 1 bị làm "mù" hoàn toàn với `boolean_blind` — hạn chế thật, được báo cáo công khai chứ không giấu.
- **Đã nối API thật**: `POST /api/v1/branch3/session` trả verdict thật (trước đó chỉ trả `not_ready`).
- **Cách B (sqlmap thật + DVWA/WebGoat Docker + mitmproxy)**: chưa làm — vẫn là giới hạn generalization đã nêu rõ, không phải blocker.
- **17/8 (phiên hiện tại)**: Recalibrate lại `content_threshold`/ngưỡng theo phân phối điểm Branch 2 mới (sau khi B2 đổi feature/data) — `models/branch3_v2/metadata.json` cập nhật `content_threshold=0,3383`.

## 5. Central decision engine

- Chính sách quyết định (Block/Overkill/Allow) đã thiết kế, mô tả được trong README — **chưa có đánh giá tích hợp thật** (chưa đo end-to-end trên luồng hỗn hợp thật).

## 6. Continual Learning / MLOps

- Pipeline offline đầy đủ: `train/build_mlops_split.py` (golden/stream/train/valid, kiểm tra bất biến), `train/run_continual_learning_experiment.py` (giám sát drift qua PSI trên 5 tín hiệu, các thực nghiệm ACT1/ACT2/CONTROL/NEGATIVE-CONTROL/SHADOW).
- **Kết quả thật**: chạy đầy đủ 1 vòng offline, ghi vào `report/metrics/continual_learning/RESULTS.md`, đã đưa thẳng vào bản thảo bài báo (`rivf2026_paper.tex` §V "Continual Learning") — không chỉ là thiết kế nữa.
- Shadow deployment: 98,85% đồng thuận giữa candidate và champion, chỉ 13 query lệch (candidate cho qua cái champion chặn) — không phát hiện lệch nguy hiểm trước khi promote.
- **16/8**: pool benign dùng cho MLOps co lại mạnh (~76,8K → ~15,4K dòng) sau khi sửa bug data Branch 2 (mục 1) — vì các dòng đó giờ đúng ra được Branch 2 dùng để train. Gây lỗi "Baseline period reaches into phase B" — sửa bằng cách giảm `mlops.drift.baseline_windows` từ 10 xuống 5.
- **Còn thiếu**: nối queue/dashboard drift vào `deploy/` thật (mới có cơ chế offline, chưa production).
- **Cần làm lại (do LOF/feature mới, mục 3)**: cập nhật `FEATURES` hardcode trong `deploy/routers/mlops.py` và `run_continual_learning_experiment.py`, rerun toàn bộ pipeline.

## 7. Kiểm thử (leakage / label-noise audit)

- Audit riêng (rẻ hơn re-run thực nghiệm, làm trước khi tin số liệu): (a) kiểm tra rò rỉ session gần-trùng giữa TRAIN/TEST 1.120/280 của Branch 3; (b) kiểm tra template `stacked` (363 mẫu, lấy lại có hoàn lại thành 727 lần xuất hiện) có lặp giữa train/eval Continual Learning không; (c) spot-check tỷ lệ nhiễu của re-tagger trên đúng các lớp dùng trong zero-day leave-one-out (không chỉ `boolean_blind` đã audit trước đó).
- Giao Bách, Sprint 1 Day 1, trước cả Cách B.

## 8. Bài báo (RIVF 2026)

- **Khung bài (framing)**: chốt (B) — đủ 3 nhánh, không phải (A) chỉ 2 nhánh — từ 7/8 khi Branch 3 có kết quả thật.
- Đã viết được ngay (không blocker): Abstract, Introduction, Related Work, Discussion & Limitations, Conclusion, toàn bộ Methodology (A-F), toàn bộ Results (A-D), toàn bộ Dataset (A-E).
- Còn thiếu trước khi nộp (deadline 30/8, dời từ 31/7): (1) đo latency end-to-end thật; (2) danh mục tài liệu tham khảo thật (đang là placeholder); (3) hình kiến trúc hệ thống (đang dùng khung placeholder); (4) điền metadata tác giả (khoa/email/thành phố còn TODO).
- Chi tiết lịch làm theo người/sprint: `report/plan/plan.csv` (dùng skill `/check-plan` để tra theo người hỏi).

---

*Lần cập nhật gần nhất: 19/8 — Branch 2 (mục 3) đã chính thức hoá và merge vào `main` (nhánh `fix/branch2-use-uncapped-pool`). Số liệu DR=80,6%/AUC=0,929 là số chính thức hiện hành.*
