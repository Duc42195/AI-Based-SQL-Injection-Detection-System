# BẢN ĐỀ XUẤT ĐỀ TÀI: HỆ THỐNG PHÁT HIỆN SQL INJECTION DỰA TRÊN TRÍ TUỆ NHÂN TẠO
### (AI-Based SQL Injection Detection System) — Bản sửa đổi V7 (17/7: thu gọn scope theo 3 mốc — xem Mục 0)
### Phân công: Tôi=MLOps/API (rút gọn), Bách=Train tất cả Nhánh 1+2+3, Minh=Streamlit, Diệp=Support + Bài RIVF

## 0. Mốc thời gian (cập nhật 17/7 — QUAN TRỌNG, đọc trước khi xem các mục khác)

| Mốc | Ngày | Nội dung | Phạm vi |
|---|---|---|---|
| **MVP kỹ thuật** | **28/7** | Train xong 3 nhánh (Nhánh 1 ✅, Nhánh 2 ✅, Nhánh 3 đang làm) + demo Streamlit chạy được end-to-end | **Rút gọn**: KHÔNG bắt buộc Continual Learning đầy đủ, Concept Drift monitoring, Session Store production-grade, benchmark toàn hệ thống dưới tải — các mục này chuyển vào **Future Work** (Mục 13) |
| **Nộp bài RIVF 2026** | **31/7 23:59** | Bài báo 6 trang, IEEE format, nộp qua EDAS (https://edas.info/N35414). Track phù hợp: **Track 4 — Cyber-Security** ("Security and privacy in AI/data systems") hoặc Track 1 — AI Foundations | Dùng đúng kết quả MVP (28/7), không chờ Future Work |
| Thông báo kết quả | 15/10 | — | — |
| Camera-ready | 11/11 | Bản final nếu được chấp nhận | Nên hoàn thiện Future Work xong trước mốc này |
| **Hội nghị RIVF 2026** | **18-20/12** | VinUniversity, Hà Nội | **Toàn bộ hệ thống (kể cả Future Work) phải xong trước ngày này** |

**Nguyên tắc xuyên suốt từ 17/7:** ưu tiên tuyệt đối cho 28/7 (MVP) và 31/7 (nộp bài) — bất kỳ hạng mục nào không phục vụ trực tiếp 2 mốc này đều lùi vào khoảng 31/7→18/12 (5 tháng, không cần lên kế hoạch ngày-theo-ngày ngay bây giờ).

---

## 1. Đặt vấn đề và Mục tiêu đề tài

**Bối cảnh:** SQL Injection (SQLi) là một trong những lỗ hổng bảo mật web nguy hiểm và phổ biến nhất. Các giải pháp truyền thống (WAF luật cứng) gặp khó khăn với biến thể tấn công mới (zero-day) và dễ gây False Positive.

**Mục tiêu:** Xây dựng hệ thống gác cổng thông minh tại tầng Database, dùng mô hình **3 nhánh song song** (supervised, anomaly detection theo từng câu, và **session-level/sequence** theo chuỗi câu), kết hợp cơ chế **Continual Learning** và chính sách **Overkill (giữ & xác minh)**.

**Đóng góp dự kiến (đã cập nhật):**
1. Kết hợp 2 nhánh phân loại/anomaly theo từng câu trên cùng backbone embedding (như V2).
2. **Nhánh 3 — mô hình phân cấp (hierarchical) theo session/chuỗi câu**, giải quyết khoảng trống mà toàn bộ 11 nguồn khảo sát ở Related Work đều bỏ qua: tấn công dạng **temporal query splitting** (Blind SQLi Boolean/Time-based) mà từng câu riêng lẻ trông hợp lệ, chỉ lộ pattern khi nhìn theo chuỗi.
3. Vòng lặp Continual Learning từ phản hồi Admin (chính sách Overkill).

---

## 2. Công trình liên quan
*(Xem file riêng "Khảo sát công trình liên quan" — đã có trích dẫn đầy đủ [1]-[11]. Điểm mấu chốt: không nguồn nào mô hình hóa mối quan hệ giữa nhiều query trong cùng session cho bài toán SQLi — đây là khoảng trống mà Nhánh 3 lấp vào.)*

---

## 3. Kiến trúc hệ thống và Luồng dữ liệu (Real-time Pipeline) — cập nhật 3 nhánh

```
[User Request] ──> [Web Backend] ──> [Database Proxy / AI Agent] ──> [Database]
                                            │
                                (Canonicalization → Đánh chặn & Phân tích)
                                            │
                    ┌───────────────┬───────────────┬────────────────┐
                    ▼               ▼               ▼
              [Nhánh 1: SQLi]  [Nhánh 2: Anomaly] [Nhánh 3: Session]
              (per-query,       (per-query,        (chuỗi K query gần nhất
               supervised)       unsupervised)       theo session/IP/time-window)
                    │               │               │
                    └───────────────┴───────────────┘
                                     ▼
                          [Bộ xử lý trung tâm]
              - Nhánh 1 = Tấn công            → Chặn ngay, ghi log
              - Nhánh 1 sạch + Nhánh 2 bất thường
                → HOLD (Overkill), chờ Admin xác nhận
              - Nhánh 1+2 sạch + Nhánh 3 phát hiện pattern chuỗi bất thường
                → HOLD session (Overkill mở rộng), có thể chặn toàn bộ session
              - Tất cả sạch                    → Cho phép
                                     │
                          [Fail-safe nếu AI service timeout/lỗi]
                                     │
                          [Continual Learning: nhãn từ hàng đợi Admin
                           → kho dữ liệu mới → retrain định kỳ]
```

**Session Store (thành phần kỹ thuật mới cho Nhánh 3):** cần bộ nhớ đệm (in-memory cache hoặc Redis) lưu K câu SQL/embedding gần nhất theo khóa session/IP, có TTL để tự xóa session cũ. Đây là điểm khác biệt kỹ thuật so với V2 — hệ thống trước đó hoàn toàn stateless theo từng request, giờ cần giữ trạng thái ngắn hạn.

---

## 4. Khoanh vùng dữ liệu và Giải pháp công nghệ

### 4.1 Lựa chọn kiến trúc mô hình cho Nhánh 1 (per-query)
Giữ nguyên như V2: so sánh DistilBERT vs. TF-IDF/char n-gram + Gradient Boosting vs. CNN nhẹ kiểu tokenizer-riêng-cho-SQL (tham khảo kiến trúc nhẹ trong khảo sát Related Work — ~69K tham số, nhanh hơn DistilBERT hàng chục lần). Chọn theo F1/latency đo thực tế, không mặc định chọn transformer.

**Kết quả thực nghiệm (16/7) — đã chốt: TF-IDF + Logistic Regression.** So sánh 4 candidate trên tập test 13.632 dòng, **6 lớp gồm cả `stacked`** (`scripts/compare_nhanh1_architectures.py`, kết quả đầy đủ ở `reports/nhanh1_architecture_comparison.json` + `notebooks/model_comparison_nhanh1.ipynb`):

| Model | F1-macro | p50 latency | Size | Train time |
|---|---|---|---|---|
| **TF-IDF + LogReg** (chọn) | 0.985 | **0,5 ms** | 3,9 MB | 10 s |
| TF-IDF + LightGBM | **0,993** | 60 ms | 6,0 MB | 264 s |
| DistilBERT | 0,992 | 2,8 ms (GPU) | 256 MB | 1443 s |
| CNN + SQL-tokenizer | 0,987 | **0,3 ms** | **116 KB** (28K params) | 10 s |

Lý do chọn LogReg: chênh lệch F1 giữa 4 model không đáng kể (0.985–0.993), trong khi LightGBM chậm gấp ~120 lần (60 ms — quá cao cho proxy real-time), DistilBERT tốn 256 MB + cần GPU + train 24 phút mà không hơn F1. CNN là ứng viên dự phòng tốt (nhanh/nhỏ nhất) nếu sau này cần học đặc trưng mạnh hơn.

**⚠️ Phát hiện sau khi train (16/7) — đã bỏ lớp `stacked` khỏi dataset:** cả 4 model đạt F1 ~0.99 và lớp `stacked` (363 mẫu synthetic) đạt **100% recall ở cả 4** → dấu hiệu dữ liệu **quá dễ phân biệt** (template lặp cấu trúc), KHÔNG phải tín hiệu chất lượng thật. Quyết định: **loại `stacked` khỏi training** (`branch1_supervised.balance.exclude_labels: [5]` trong `config.yaml`), giữ code sinh (`synthetic_stacked.py`) để dùng lại khi có data thật từ Docker lab/sqlmap (Ngày 5-6). Dataset còn **5 lớp, 67.796 dòng**.

**F1-macro đúng sau khi bỏ `stacked`: 0.9822** (`models/nhanh1_v1/`, kiến trúc không đổi — TF-IDF+LogReg). Lưu ý: lần retrain đầu tiên báo nhầm F1=0.8185 do bug tính `classification_report` (hardcode đủ 6 nhãn dù `stacked` không còn trong data → sklearn tính điểm 0 cho nhãn không tồn tại, kéo macro-average sai) — đã sửa ở cả `train_nhanh1.py` và `compare_nhanh1_architectures.py` (chi tiết: `data_contract.md` Mục 3.3). Confusion matrix cho thấy nhầm lẫn duy nhất đáng kể là `normal ↔ boolean_blind` (khớp với ~13% nhiễu nhãn đã đo ở rổ `boolean_blind`) — con số F1 này vẫn không nên hiểu là hệ thống "gần hoàn hảo", thước đo thật là tập test adversarial (Ngày 7).

### 4.2 Nhánh 2: Phát hiện bất thường theo từng câu (giữ nguyên V2)

### 4.3 Nhánh 3 (MỚI): Session-level / Sequence Model

**Kiến trúc phân cấp (Hierarchical):**
```
Query 1 ─┐
Query 2 ─┼─> [Tầng 1: Encoder nhẹ mỗi query] ─> embedding q1, q2, q3...
Query 3 ─┘   (tái sử dụng encoder đã chọn ở Nhánh 1 — không train lại)
                                    │
                                    ▼
                     [Tầng 2: Sequence Model nhẹ]
                     (học trên chuỗi embedding theo session)
                                    │
                                    ▼
                     Session-level anomaly score
```

**Lựa chọn mô hình cho Tầng 2 — cần thử nghiệm so sánh (xem Kế hoạch 2 tuần):**
| Lựa chọn | Ưu điểm | Nhược điểm |
|---|---|---|
| GRU 1 lớp | Nhẹ, xử lý chuỗi độ dài thay đổi tự nhiên | Xử lý tuần tự, khó song song hóa |
| 1D-CNN theo thời gian (temporal conv) | Rất nhanh, song song hóa tốt | Cửa sổ ngữ cảnh cố định, kém hơn với chuỗi dài |
| Transformer encoder nhỏ (2 lớp, self-attention) | Bắt được quan hệ xa giữa các query trong chuỗi | Nặng hơn 2 lựa chọn trên |

### 4.4 Dữ liệu cho Nhánh 3 — thu thập bằng công cụ tấn công thật (đáng tin hơn script mô phỏng)
- **Docker lab dễ tổn thương:** dựng DVWA/WebGoat trong container cục bộ, chỉ dùng nội bộ cho mục đích thu thập dữ liệu huấn luyện.
- **Malicious session (thật, không mô phỏng):** chạy `sqlmap --technique=B` (boolean-blind) và `--technique=T` (time-blind) nhắm vào lab, bắt toàn bộ traffic bằng proxy trung gian (mitmproxy/Burp Suite) đặt giữa sqlmap và lab app → có log request/response đầy đủ, đúng định dạng thật, kèm timestamp.
- **Sanity check ground truth:** chỉ giữ lại session mà sqlmap **báo trích xuất dữ liệu thành công** — tránh gán nhãn 1 cho session tấn công thất bại.
- **Malicious session bổ sung (từ WAF-A-MoLE):** khi chạy WAF-A-MoLE để sinh tập test adversarial cho Mục 7 (Nhánh 1/2), log lại toàn bộ chuỗi các lần thử biến đổi liên tiếp — tận dụng lại, không tốn thêm công thu thập.
- **Benign session:** group theo cookie có sẵn trong CSIC 2010 (D3), hoặc crawler đơn giản duyệt DVWA ở chế độ bình thường — thực tế hơn ghép ngẫu nhiên các câu rời rạc.
- **Ranh giới session:** định nghĩa tường minh = session ID (hoặc IP) + ngưỡng nghỉ 30 phút — cần ghi rõ trong báo cáo vì đây là điểm phản biện thường gặp.

**Schema nhãn 2 tầng (Hierarchical Labeling) — điểm mới cần nêu trong Phương pháp:**
Vì chưa dataset SQLi nào có sẵn nhãn theo session, đề tài tự định nghĩa schema 2 tầng, khớp với kiến trúc phân cấp:
- Tầng câu (per-query, giữ như D1): 0 = Normal, 1 = SQLi.
- Tầng session (mới): 0 = Benign, 1 = Blind Boolean-based, 2 = Blind Time-based, 3 = Query-splitting/multi-step.

### 4.5 Cập nhật nguồn dữ liệu Nhánh 1 — bổ sung D7, xử lý mất cân bằng lớp (15/7)

Verify thực tế trên D1 (SQLiV3) cho thấy dataset quá nghèo để phân loại đa lớp: **0 mẫu `stacked`**, và lớp `boolean_blind` chỉ là "rổ chứa" các payload không khớp 4 luật kia (gồm cả DDL không liên quan). Cần bổ sung nguồn:

- **D7 — SR-BH 2020** ([Harvard Dataverse](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/OGOIXX)): honeypot thật, thu 12 ngày (2020), đa nhãn CAPEC. 527.813 dòng, 250.285 dòng gắn nhãn gốc `SQL Injection`.
- Sau khi tự tag lại (không tin nhãn gốc — phát hiện nhiễu nhãn, có dòng static asset bị gắn nhầm SQLi): bổ sung thêm `union_based` +83.189, `error_based` +7.423, `boolean_blind` +126.926, `time_blind` +32.747.
- **`stacked` = 0 mẫu ở cả D1+D4+D7** (đã thử cả regex chặt lẫn lỏng) → không có nguồn public nào chứa kỹ thuật này. Xử lý: **sinh tổng hợp 363 mẫu duy nhất** (template hoá 11 prefix × 11 câu lệnh phá hoại/leo thang quyền × 3 hậu tố comment — con số thực tế, không phải ước tính ban đầu ~1-2K), gắn nguồn `synthetic_stacked` và nêu rõ trong Hạn chế (Mục 7) — đây là dữ liệu tự tạo, không phải thu thập thật. Quy mô nhỏ hơn nhiều so với các lớp khác (~15K) là hạn chế cần nêu rõ.
- **Chiến lược cân bằng:** undersample các lớp lớn (`union_based`, `boolean_blind`, `time_blind`) về cùng bậc độ lớn (~15.000/lớp), giữ nguyên toàn bộ `error_based` (~7.800, không đủ để undersample). Dùng **F1-macro** làm metric chính cho Nhánh 1 (Accuracy không phản ánh đúng do mất cân bằng gốc).
- Chi tiết số liệu đầy đủ (bảng theo từng nguồn, ví dụ nhiễu nhãn cụ thể): xem `data_contract.md`.

**Cập nhật 15/7 — đã build xong `data/processed/nhanh1_train.csv`:** kiểm tra chéo cờ nhãn gốc D7 (dataset đa nhãn) cho kết quả tốt ở mức tổng hợp (99,1% `SQL Injection=1` không dính cờ khác; 0% `Normal=1` mâu thuẫn cờ khác) — **nhưng đọc tay trực tiếp nội dung mẫu `Normal=1` phát hiện vấn đề nghiêm trọng hơn**: có dòng chứa `sleep(15)` (time-blind SQLi thật) và payload Shellshock (`() {{ :;}}; /bin/sleep 15`) bị SR-BH tự gắn nhầm `Normal=1`, dù không mâu thuẫn cờ nào của chính nó. So cờ chéo là không đủ — phải đọc nội dung mới bắt được.
- Xử lý: thêm lưới lọc nội dung (`matches_any_attack_signature`, độc lập với nhãn nguồn) áp cho mọi dòng dự kiến `normal` trước khi chấp nhận.
- **3 vòng sanity-check liên tiếp phát hiện thêm biến thể lọt lưới mỗi vòng:** vòng 1 loại 1.561 dòng; soi tay vòng 2 phát hiện `&cat /etc/passwd&` (dùng `&` thay `;`) và SSI injection lọt qua → mở rộng regex, tổng loại **2.731 dòng** (~9,8%); vòng 3 phát hiện **fuzzer né tránh có chủ đích** (`cat$jj $jj/etc$jj/passwd`, chèn token rác giữa từ khóa) vẫn lọt. **Quyết định dừng vá regex** — đây là bài toán evasion vô hạn biến thể, đúng chỗ xử lý là canonicalization + tập adversarial (Ngày 7), không phải lặp vá filter tĩnh dataset. Ghi nhận là rủi ro chấp nhận được cho MVP.
- **Nhiễu nhãn không chỉ ở phía `normal`:** soi tay 30 mẫu `boolean_blind` (rổ chứa cuối) phát hiện **~13% (4/30) sai hẳn** — SSRF, CRLF/header injection, 1 dòng benign hoàn toàn bị SR-BH tự gắn `SQL Injection=1`. Đây là con số **đo được**, không phải ước tính, cần đưa vào Hạn chế (Mục 7) của báo cáo.
- Giới hạn còn lại: filter chỉ nhắm SQLi + OS command injection/SSI, **chưa phủ hết 12 loại tấn công của SR-BH** (XSS, SSRF vẫn có thể lọt vào `normal`) — chấp nhận được cho Nhánh 1 (chỉ cần SQLi), nhưng **Nhánh 2 (anomaly, cần benign pool sạch hơn nhiều) phải làm kỹ hơn** khi tới lượt (Ngày 5-6).
- Kết quả cuối: **68.159 dòng** (train 54.527 / test 13.632, stratified, seed=42), 15.000/lớp cho 3 lớp lớn, giữ nguyên `error_based` (7.796) và `stacked` (363). Sanity-check tay đầy đủ ~100 mẫu/lớp vẫn chưa làm (mới soi mẫu nhỏ 15-20/lớp) — nên bổ sung trước khi chốt số liệu chính thức cho báo cáo.
- Đã thêm XSS vào filter dùng chung (`<script>`, `javascript:`, `onerror=/onload=`) sau khi phát hiện thêm trong mẫu — rebuild Nhánh 1 loại tổng **2.892 dòng** normal nhiễu (tăng từ 2.731).
- Dataset đã public trên Hugging Face: [Jason-42195/VNU-SQLi-Detection](https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection). License đã verify: D4 (payload-box) = MIT, D7 (SR-BH 2020) = CC0 1.0 (xác nhận trực tiếp từ Harvard Dataverse); riêng **D1 (SQLiV3) chưa rõ ràng** — trang Kaggle gốc không gán license, mirror GitHub tự gắn MIT cho repo của họ nhưng không chắc có quyền trên chính data. Toàn bộ dataset (gộp D1) nên coi là **provenance-unclear**, không phải MIT/CC0 sạch, cho tới khi xác minh thêm.

**Cập nhật 15/7 (tiếp) — bắt đầu dữ liệu Nhánh 2:** tái cấu trúc code — tách các hàm load D1/D3/D4/D7 ra module dùng chung `src/preprocessing/data_sources.py` (tránh 2 nhánh có 2 định nghĩa "normal sạch" khác nhau). Nhánh 2 dùng **đặc trưng thống kê/cấu trúc** (length, tỷ lệ ký tự đặc biệt, số từ khóa SQL, entropy — `src/preprocessing/statistical_features.py`), không dùng TF-IDF, vì cần tổng quát hoá tới cú pháp chưa từng thấy (zero-day). Không cap số lượng (khác Nhánh 1) — lấy hết normal sạch từ D1+D3+D7.
- Kết quả: **91.935 dòng benign** (train 73.548/test 18.387) sau khi lọc (~7,4% ứng viên bị loại) + dedup (loại thêm ~113K dòng trùng — nhiều asset tĩnh lặp lại trong D3/D7); giữ riêng **25.065 dòng anomalous (D3)** để đánh giá FPR/detection rate sau (chưa dùng để train).
- ⚠️ Phát hiện quan trọng cho lúc đánh giá: tập D3-anomalous có **nhiều loại tấn công** (không chỉ SQLi — buffer overflow, XSS, path traversal...), nên `sql_keyword_count` trung bình của nó **thấp hơn** cả tập normal (0,13 vs 0,35). Cần lọc riêng phần SQLi trong D3-anomalous nếu muốn đo đúng khả năng bắt SQLi zero-day, hoặc chấp nhận benchmark này là "phát hiện bất thường nói chung".
- **Nhánh 3: chưa bắt đầu** — phụ thuộc traffic thật từ Docker lab + sqlmap (Ngày 8-9), quyết định không build data giả trước khi có traffic thật.

---

## 5. Cơ chế kết hợp và Ra quyết định — cập nhật 3 nhánh

| Nhánh 1 | Nhánh 2 | Nhánh 3 (session) | Hành động |
|---|---|---|---|
| Tấn công (1) | — | — | **Chặn ngay lập tức**, ghi log |
| Hợp lệ (0) | Bất thường | — | **HOLD** truy vấn, chờ Admin xác nhận (Overkill) |
| Hợp lệ (0) | Bình thường | Chuỗi bất thường | **HOLD toàn bộ session**, cờ khả nghi, chờ Admin xác nhận |
| Hợp lệ (0) | Bình thường | Bình thường | **Cho phép** |

---

## 6. Đánh giá mô hình
Như V2 (P/R/F1, FPR, latency, test adversarial), bổ sung: **đánh giá riêng Nhánh 3** trên tập session thu thập được (Mục 4.4) theo schema nhãn 2 tầng — đặc biệt đo khả năng phát hiện đúng từng loại (Boolean-based/Time-based/Query-splitting) mà Nhánh 1+2 bỏ lọt (đây là số liệu "chứng minh giá trị" của Nhánh 3, nên làm kỹ, và cũng là chỉ số chứng minh giá trị của bộ dữ liệu tự thu thập — một đóng góp riêng có thể trình bày tách khỏi phần mô hình).

---

## 7. Rủi ro, hạn chế và Threat Model mở rộng

### 7.1 Query Splitting — 2 dạng cần phân biệt

**Dạng 1 — Horizontal split (chia theo tham số, cùng 1 request):** phần lớn đã được xử lý bởi vị trí đặt hệ thống (Vị trí B — Proxy nhìn câu SQL SAU khi backend đã build), vì Nhánh 1/2 luôn thấy câu hoàn chỉnh sau khi nối tham số. Chỉ nguy hiểm với kiến trúc lọc ở tầng input/WAF trước khi build — không phải kiến trúc của đề tài này.

**Dạng 2 — Temporal split (chia theo thời gian, qua nhiều request):** đây là dạng thật sự nguy hiểm với kiến trúc 2 nhánh cũ, vì từng câu riêng lẻ hợp lệ về cú pháp. Ví dụ: Blind Boolean-based (dò nhị phân từng ký tự qua hàng trăm request liên tiếp, literal value thay đổi có hệ thống), Time-based Blind (dò qua độ trễ phản hồi thay vì nội dung). Dấu hiệu chỉ lộ ra khi nhìn theo chuỗi — **đây là lý do cần Nhánh 3.**

### 7.2 Threat model mở rộng — các case khác cần lưu ý phạm vi

| Loại tấn công | Mô tả | Có thuộc phạm vi giải quyết? |
|---|---|---|
| Second-order SQLi | Payload lưu an toàn ở request A, kích hoạt ở request B không cùng session, có thể cách nhau nhiều ngày | **Ngoài phạm vi** (kể cả Nhánh 3) — ghi rõ trong Hạn chế |
| Out-of-band (OOB) SQLi | Dữ liệu exfiltrate qua kênh DNS/HTTP khác, không qua response | **Ngoài phạm vi** — cần giám sát network/DNS riêng |
| HTTP Parameter Pollution | Backend/WAF đọc giá trị tham số trùng tên khác nhau | Giảm rủi ro nhờ Vị trí B của Proxy — nêu rõ lý do chọn vị trí này |
| Stacked queries (`; DROP...`) | Chèn câu lệnh thứ 2 sau `;` trong 1 request | Đã thuộc khả năng Nhánh 1 — chỉ cần canonicalization không xóa nhầm `;` |

### 7.3 Dữ liệu được soạn để né 2 nhánh (giữ từ V2)
4 nhóm: biến đổi cú pháp tương đương, encoding, mô phỏng thống kê, chia nhỏ payload. Xem WAF-A-MoLE [7] để có đặc tả kỹ thuật chi tiết và công cụ sinh tự động.

### 7.4 Rủi ro khác
Single point of failure tại Proxy, chi phí độ trễ, và **rủi ro mới của Nhánh 3:** cần đảm bảo Session Store không bị đầy/tràn bộ nhớ nếu số lượng session đồng thời lớn — cần chính sách TTL/eviction rõ ràng.

---

## 8. Continual Learning (giữ nguyên V2, mở rộng nhận nhãn từ cả Nhánh 3)
Khi Admin xác nhận HOLD (từ Nhánh 2 hoặc Nhánh 3), gán nhãn và lưu vào kho dữ liệu mới → retrain định kỳ (rehearsal) → validation gate trước khi promote.

## 9. Concept Drift — MLOps rút gọn theo Google (giữ nguyên V2)

## 10. Kế hoạch triển khai kỹ thuật (Deployment)
Như V2 (FastAPI + CTranslate2 nếu dùng transformer). Bổ sung: cần chọn công nghệ Session Store (in-memory dict/LRU cho MVP, hoặc Redis nếu cần chia sẻ giữa nhiều instance Proxy).

---

## 11. KẾ HOẠCH CHI TIẾT (13/7 – 31/7) — 4 người, chạy song song

**Nhân sự — Ngày 1-4 (đã xảy ra):**
- **Tôi** — Dữ liệu + Huấn luyện Nhánh 1 (xong: `models/nhanh1_v1/`, F1-macro=0.9822, 5 lớp).
- **Bách** — Nhánh 2 (Anomaly), độc lập (xong sớm: cả Isolation Forest lẫn One-Class SVM, audit đầy đủ, chọn OCSVM AUC=0.887).
- **Minh** — Streamlit (khung + trang mock).
- **Diệp** — Support/báo cáo.

**Phân công Ngày 5-16 (17-28/7) — MVP, scope đã rút gọn:**

| Vai trò | Việc |
|---|---|
| **Tôi** | **MLOps rút gọn**: Bộ xử lý trung tâm CƠ BẢN (decision logic 3 nhánh), hàng đợi Overkill đơn giản (không TTL/eviction phức tạp), đóng gói API (`api/main.py`, `api/routers/` — đang làm), tích hợp Nhánh 3 khi Bách bàn giao, test end-to-end. **KHÔNG làm** Session Store production/Continual Learning/Concept Drift/benchmark tải — dời vào Future Work (Mục 15) |
| **Bách** | **Train tất cả**: giữ Nhánh 1+2 đã xong, **Nhánh 3 đầy đủ** (Docker lab, sqlmap, session data, gán nhãn, so sánh kiến trúc Tầng 2, train + đánh giá), bàn giao model cho Tôi ở Ngày 10 |
| **Minh** | Streamlit — đây chính là "**mẫu thử**" (demo) của MVP, nối API thật ngay khi từng nhánh sẵn sàng |
| **Diệp** | Support báo cáo đồ án **+ bắt đầu SỚM viết bài RIVF** (Intro/Related Work/Method) song song ngay từ Ngày 5, không chờ đến 28/7 |

**Ngày 17-19 (29-31/7) — Sprint viết & nộp bài RIVF 2026:** cả 4 người chuyển hẳn sang hoàn thiện bài báo 6 trang (ghép các phần đã viết dần từ Ngày 5-16 + số liệu MVP thật) → format IEEE → nộp qua EDAS trước 31/7.

**Bảng chi tiết theo từng ngày/từng người nằm trong `ke_hoach_2_tuan.csv`** (76 dòng, Ngày 1-19) — xem Mục 13 để biết cách cập nhật tự động bằng Claude Code.

**Tóm tắt luồng chính (chi tiết đầy đủ xem CSV):**
- *Tuần 1 (đã xong):* Tôi lo D1 → train Nhánh 1 → đánh giá. Bách lo D3 → train/đánh giá Nhánh 2. Minh dựng khung Streamlit. Diệp viết Mục 1-4 báo cáo.
- *Tuần 2 (17-28/7, MVP):* Tôi xây Bộ xử lý trung tâm cơ bản + API (Nhánh 1+2 trước) → tích hợp Nhánh 3 khi Bách bàn giao (Ngày 10) → test end-to-end (Ngày 11-14) → buffer + polish (Ngày 15) → **chốt MVP Ngày 16 (28/7)**. Bách dựng Docker lab + sqlmap → thu traffic → gán nhãn 2 tầng → chọn kiến trúc Tầng 2 → train + đánh giá Nhánh 3. Minh nối API thật ngay khi có. Diệp viết dần bài RIVF song song mỗi ngày (không dồn vào cuối).
- *29-31/7 (sprint bài báo):* Ghép các phần đã viết dần thành bản thảo hoàn chỉnh, thêm hình/bảng số liệu MVP, format IEEEtran 6 trang, rà soát, nộp EDAS.

---

## 12. Rủi ro (cập nhật 17/7 theo scope mới)

**Bách là đường găng chính (critical path) cho MVP 28/7:** Nhánh 3 (Docker lab → sqlmap → gán nhãn → train) là track dài nhất (Ngày 5-10, 6 ngày), làm tuần tự. Mốc kiểm tra quan trọng nhất: **Ngày 10 (Bách bàn giao model Nhánh 3)** — trễ mốc này kéo trễ tích hợp (Ngày 11) và toàn bộ buffer (Ngày 12-15) trước hạn 28/7.

**Tôi (MLOps rút gọn) ít phụ thuộc Bách hơn trước** — vì đã cắt Session Store/Continual Learning/Concept Drift/benchmark khỏi phạm vi MVP, khối lượng việc giảm đáng kể, chỉ còn: decision logic cơ bản + API + tích hợp cuối cùng khi Nhánh 3 sẵn sàng.

**Minh (Streamlit): không bị chặn** — nối API thật ngay khi có (Nhánh 1+2 từ Ngày 4-7), chỉ chờ Nhánh 3 ở Ngày 11.

**Rủi ro mới — dồn việc viết bài vào 29-31/7 nếu Diệp không viết dần:** đã né bằng cách giao Diệp viết từng phần (Intro/Method/Experiments/Discussion) rải đều Ngày 5-14 thay vì chỉ bắt đầu ở Ngày 17 — Ngày 17-19 chỉ còn việc ghép + format + rà soát, không phải viết từ đầu.

**Gợi ý giảm rủi ro Nhánh 3:** nếu tới Ngày 8 Bách chưa xong thu thập traffic thật, ưu tiên cắt bớt Cách B (sqlmap) và dùng Cách A (script mô phỏng) để không trễ MVP 28/7 — chấp nhận giảm độ tin cậy dữ liệu Nhánh 3 hơn là trễ deadline. Việc hoàn thiện Cách B đầy đủ có thể dời vào Future Work.

---

## 13. Future Work — hoàn thiện toàn bộ hệ thống trước Hội nghị (31/7 → 18/12)

**Bối cảnh:** MVP (28/7) và bài RIVF (31/7) chỉ cần **3 nhánh train xong + demo chạy được**. Các hạng mục dưới đây bị cắt khỏi phạm vi gần (xem Mục 0, Mục 11) nhưng vẫn **bắt buộc phải hoàn thành trước Hội nghị 18/12** — đặc biệt nên nhắm mốc **camera-ready 11/11** để có bản trình bày đầy đủ. Không cần lên kế hoạch ngày-theo-ngày ngay bây giờ (còn ~4 tháng từ 31/7), nhưng liệt kê rõ ở đây để không quên phạm vi đã hứa trong bài báo (mục Future Work của chính bài RIVF nên tham chiếu lại danh sách này).

1. **Continual Learning đầy đủ** — hiện tại (MVP) chỉ có decision logic cơ bản, chưa có: pipeline gán nhãn từ hàng đợi Overkill → retrain có rehearsal (trộn dữ liệu mới/cũ) → validation gate (F1/FPR không giảm mới được promote). Cần chạy thật ít nhất 1-2 vòng retrain có dữ liệu drift thật, không chỉ mô tả lý thuyết.
2. **Concept Drift monitoring production** — log định kỳ PSI/KL-divergence trên phân phối feature theo thời gian, FPR/Recall theo thời gian, ngưỡng trigger retrain, versioning model theo `models/vN/`, khả năng rollback nhanh. MVP chưa implement phần theo dõi liên tục này.
3. **Session Store production-grade** — MVP dùng cấu trúc đơn giản trong bộ nhớ; cần nâng cấp TTL/eviction thật (vd. Redis), chịu tải nhiều session đồng thời.
4. **Benchmark latency/throughput toàn hệ thống dưới tải thật** — MVP chỉ test end-to-end chức năng (đúng/sai), chưa đo throughput dưới tải cao (concurrent requests, stress test).
5. **Mở rộng dữ liệu Nhánh 3 (Cách B quy mô lớn)** — MVP có thể phải cắt bớt sqlmap thật nếu trễ (xem Mục 12), dùng tạm Cách A (mô phỏng). Future Work: chạy đầy đủ Cách B trên nhiều CMS/DBMS khác nhau, so sánh A↔B kỹ hơn.
6. **Adversarial hardening nhiều vòng** — MVP chỉ sinh 1 tập adversarial (WAF-A-MoLE) áp dụng cơ bản. Future Work: lặp lại nhiều vòng sinh-test-retrain, đo độ bền vững tăng dần.
7. **Sanity-check nhãn tay quy mô lớn** — MVP mới soi mẫu nhỏ (15-30/lớp). Future Work: đủ ~100+/lớp, có kiểm định chéo giữa nhiều người (đã có draft trong `ke_hoach_2_tuan.csv` cũ, Diệp phối hợp Toi).
8. **Publish dataset chính thức** — dataset hiện public trên HF (Jason-42195/VNU-SQLi-Detection) nhưng license D1 (SQLiV3) chưa rõ ràng (xem `data_contract.md`). Cần xác minh/thay thế nguồn trước khi coi là "chính thức" để trích dẫn rộng rãi.
9. **So sánh với nhiều baseline SOTA hơn** — cho phiên bản mở rộng (journal) sau hội nghị, nếu muốn nâng tầm công bố (hiện tại ở mức phù hợp Q3-Q4/hội nghị, xem trao đổi trước đó).

---

## 14. File theo dõi tiến độ và cách cập nhật tự động

Kế hoạch chi tiết (19 ngày × 4 người, kèm sản phẩm bàn giao) nằm trong `ke_hoach_2_tuan.csv` — mỗi dòng là 1 task với cột: `Ngay, NgayThang, Thu, NguoiPhuTrach, VaiTro, CongViec, PhuThuoc, SanPham, TrangThai`. Dùng lệnh trong file `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md` để nhờ Claude Code tự hỏi vai trò, tự xác định ngày hiện tại, tự kiểm tra deliverable đã tồn tại trong repo chưa, và tự cập nhật cột `TrangThai` + đồng bộ tóm tắt vào file đề xuất này.

---

## 15. Nhật ký cập nhật tiến độ (tự động — Claude Code ghi vào đây)

*(Mục này để trống, sẽ được Claude Code tự động thêm dòng mỗi khi chạy lệnh cập nhật kế hoạch — xem `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md`. Mỗi lần chạy, thêm 1 dòng dạng: `[YYYY-MM-DD, Vai trò: X] Việc hôm nay: ... | Đã xong: ... | Trễ hạn: ...`)*

[2026-07-14, Vai trò: Toi] Việc hôm nay: Làm sạch D1 đầy đủ; viết pipeline canonicalization; chốt kiến trúc Nhánh 1 (đang bị chặn bởi Ngày 1 - Toi chưa hoàn thành) | Đã xong: Không có | Trễ hạn: Ngày 1 - Toi (Chốt data contract; tải D1 thô; test nhanh kiến trúc Nhánh 1) — không sản phẩm nào tồn tại (`data_contract.md`, `data/raw/d1_sqliv3_raw.csv`, `notebooks/model_comparison_nhanh1.ipynb`)

[2026-07-16, Vai trò: Toi] Việc hôm nay (Ngày 4): Đánh giá Nhánh 1 (P/R/F1) + bắt đầu setup Docker lab | Đã xong: (bù các ngày trước) so sánh 4 kiến trúc Nhánh 1 → chốt TF-IDF+LogReg (F1-macro 0.985, p50 0.5ms), train `models/nhanh1_v1/`, `reports/nhanh1_eval.json`, `notebooks/model_comparison_nhanh1.ipynb`; ngoài kế hoạch: đã build xong `data/processed/nhanh2_normal.csv` (91.935 dòng benign) cho Nhánh 2 | Trễ hạn/còn lại: `docker/dvwa/docker-compose.yml` (setup Docker lab cho Nhánh 3 — chưa làm); sanity-check tay đầy đủ 100 mẫu/lớp; lưu ý F1 cao đáng ngờ (dữ liệu quá dễ, chưa test adversarial)

[2026-07-16, Vai trò: Toi] Thông báo cho Bách: Ngày 1-2 của Bách (`data/raw/d3_csic2010_raw.csv`, `data/processed/nhanh2_normal.csv`) **đã có sẵn** — Toi làm chung khi build data Nhánh 1+2 (xem Mục 3.2 `data_contract.md`). Bách KHÔNG cần làm lại, có thể bắt đầu thẳng từ Ngày 3. Lưu ý: 4 đặc trưng thống kê (length, special_char_ratio, sql_keyword_count, entropy — `src/preprocessing/statistical_features.py`) đã có sẵn làm cột trong `nhanh2_normal.csv`, có thể dùng luôn cho Ngày 3 (trích đặc trưng) thay vì tự làm TF-IDF/embedding riêng, hoặc vẫn tự làm hướng khác nếu muốn so sánh. `nhanh2_anomalous_eval.csv` (25.065 dòng D3 anomalous) đã chuẩn bị sẵn để đánh giá FPR/detection rate ở Ngày 5. Toàn bộ data đã public trên HF: https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection

[2026-07-17, Vai trò: Toi] Phân công lại từ Ngày 5: hoán đổi track giữa Toi và Bách — Toi chuyển sang toàn bộ MLOps (Bo xu ly trung tam, Session Store, API, benchmark, Continual Learning, Concept Drift), Bách nhận thêm toàn bộ Nhánh 3 (Docker lab, sqlmap, session data, train) ngoài Nhánh 1+2 đã xong. Minh (Streamlit) và Diệp (Support) không đổi. Đã cập nhật `ke_hoach_2_tuan.csv` (Ngày 5-13) và Mục 11-12 tài liệu này. Lý do: Bách đã xong Nhánh 2 sớm + có kinh nghiệm train, Toi đang chủ động làm API rồi (nhánh `feature/api-backend-mlops`).

[2026-07-17, Vai trò: Toi] THU GỌN SCOPE (yêu cầu người dùng): xác nhận RIVF 2026 (đã tra trang thật) — hạn nộp 31/7/2026, 6 trang IEEE, EDAS, hội nghị 18-20/12 tại VinUniversity. 3 mốc mới: (1) 28/7 = train xong 3 nhánh + demo (KHÔNG bắt buộc Continual Learning/Concept Drift/Session Store production/benchmark tải — dời Future Work), (2) 31/7 = nộp bài RIVF, (3) trước 18/12 (nhắm camera-ready 11/11) = hoàn thiện toàn bộ hệ thống. Đã thêm Mục 0 (mốc thời gian), viết lại Mục 11-12, thêm Mục 13 (Future Work, 9 hạng mục). Cập nhật `ke_hoach_2_tuan.csv` từ 56 lên 76 dòng (Ngày 1-19): rút gọn Ngày 5-14, thêm Ngày 15-16 (chốt MVP), Ngày 17-19 (sprint viết + nộp bài — Diệp bắt đầu viết từng phần từ Ngày 5, không dồn cuối).
