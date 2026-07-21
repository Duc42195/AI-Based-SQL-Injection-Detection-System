# BẢN ĐỀ XUẤT ĐỀ TÀI: HỆ THỐNG PHÁT HIỆN SQL INJECTION DỰA TRÊN TRÍ TUỆ NHÂN TẠO
### (AI-Based SQL Injection Detection System) — Bản sửa đổi V8 (21/7: ĐỔI HẠN, thu gọn scope quyết liệt — xem Mục 0)
### Phân công: Tôi=làm mượt Nhánh 1 + tích hợp, Bách=Nhánh 2 (đã train xong, đang verify), Minh=Streamlit, Diệp=Support/Báo cáo

## 0. Mốc thời gian (cập nhật 21/7 — QUAN TRỌNG, đọc trước khi xem các mục khác)

**⚠️ Đổi hạn khẩn cấp:** hạn thật là **Thứ 7 tuần này — 25/7/2026** (không phải 28/7 như bản trước). Chỉ còn **5 ngày kể từ hôm nay (Thứ 3 21/7)**.

| Mốc | Ngày | Nội dung | Phạm vi |
|---|---|---|---|
| **HẠN NỘP** | **Thứ 7, 25/7** | Chỉ cần: **metric đầy đủ Nhánh 1 + Nhánh 2** (đã train xong cả hai) + **notebook demo** (`notebooks/demo_detect.ipynb` — load model, nhập query, trả verdict) + **2 bản báo cáo** | **Cắt hẳn khỏi phạm vi (21/7, lần 2)**: KHÔNG chỉ Nhánh 3 mà cả **toàn bộ hệ thống** (API, Bộ xử lý trung tâm, Streamlit demo) — dời hết sang "làm sau". Thay demo hệ thống bằng 1 notebook đơn giản. Chi tiết Future Work ở Mục 13 |
| Nộp bài RIVF 2026 | 31/7 23:59 | Bài báo 6 trang IEEE qua EDAS — **kế hoạch chi tiết sẽ làm lại sau 25/7**, khi biết rõ còn bao nhiêu thời gian/nhân lực | Không lên kế hoạch ngày-theo-ngày trong file này nữa cho tới khi qua hạn 25/7 |
| Thông báo kết quả RIVF | 15/10 | — | — |
| Camera-ready RIVF | 11/11 | — | Nhánh 3 + Future Work nên xong trước mốc này nếu muốn trình bày đầy đủ |
| Hội nghị RIVF 2026 | 18-20/12 | VinUniversity, Hà Nội | — |

**Vì sao cắt Nhánh 3:** xác nhận thực tế (21/7) — Nhánh 3 hiện **chưa có gì** (không Docker lab, không session data, không model), trong khi chỉ còn 5 ngày. Cố giữ Nhánh 3 trong phạm vi sẽ khiến cả 3 nhánh đều dở dang. Quyết định: **làm chắc 2 nhánh** hơn là làm dở cả 3. Nhánh 3 vẫn giữ nguyên trong thiết kế/đóng góp lý thuyết của đề tài (Mục 1, 3, 4.3) nhưng ghi rõ là **chưa triển khai thực nghiệm** trong bản nộp 25/7 — xem Mục 13 (Future Work).

**Tin tốt về Nhánh 2:** kiểm tra thực tế (21/7) cho thấy Nhánh 2 **không phải nút thắt** — toàn bộ pipeline (build data từ HF + train Isolation Forest/OCSVM) chạy xong trong **~75 giây**. Vấn đề "thiếu model" trước đó chỉ do file `.joblib` không commit (đúng chủ đích, tránh file lớn trong git), không phải do thiếu thời gian huấn luyện.

**Đổi lần 2 (cùng ngày 21/7) — bỏ luôn hệ thống, viết 2 bản báo cáo:** sau khi xác nhận Nhánh 1+2 đã ổn, quyết định **không xây API/Bộ xử lý trung tâm/Streamlit** cho bản nộp 25/7 nữa — thay bằng `notebooks/demo_detect.ipynb` (đã viết + chạy thử, load model thật, nhập query trả verdict, sanity-check 19/20 đúng trên mẫu ngẫu nhiên). Đồng thời viết **2 bản báo cáo song song**:
- **[`report/ban1_scope_hien_tai.md`](report/ban1_scope_hien_tai.md)** — đúng những gì đã làm thật (2 nhánh + notebook), nộp 25/7.
- **[`report/ban2_hoan_chinh.md`](report/ban2_hoan_chinh.md)** — tầm nhìn đầy đủ (3 nhánh + hệ thống tích hợp), Nhánh 3/API đánh dấu rõ là thiết kế/Future Work.

---

## 1. Đặt vấn đề và Mục tiêu đề tài

**Bối cảnh:** SQL Injection (SQLi) là một trong những lỗ hổng bảo mật web nguy hiểm và phổ biến nhất. Các giải pháp truyền thống (WAF luật cứng) gặp khó khăn với biến thể tấn công mới (zero-day) và dễ gây False Positive.

**Mục tiêu:** Xây dựng hệ thống gác cổng thông minh tại tầng Database. Thiết kế đầy đủ gồm **3 nhánh song song** (supervised, anomaly detection theo từng câu, và **session-level/sequence** theo chuỗi câu) kết hợp cơ chế **Continual Learning** và chính sách **Overkill (giữ & xác minh)** — nhưng **bản nộp 25/7 chỉ triển khai thực nghiệm 2 nhánh đầu** (xem Mục 0 lý do).

**Đóng góp — phân biệt rõ đã làm (25/7) vs. thiết kế/Future Work:**
1. **[ĐÃ TRIỂN KHAI]** Nhánh 1 (supervised đa lớp, F1-macro=0.982) + Nhánh 2 (anomaly detection, OCSVM AUC=0.90) kết hợp trên cùng pipeline canonicalization, minh hoạ qua notebook demo (`notebooks/demo_detect.ipynb`) — API/hệ thống tích hợp là Future Work (xem Mục 13).
2. **[THIẾT KẾ — Future Work]** Nhánh 3 — mô hình phân cấp (hierarchical) theo session/chuỗi câu, giải quyết khoảng trống mà toàn bộ 11 nguồn khảo sát ở Related Work đều bỏ qua: tấn công dạng **temporal query splitting** (Blind SQLi Boolean/Time-based) mà từng câu riêng lẻ trông hợp lệ, chỉ lộ pattern khi nhìn theo chuỗi. Kiến trúc đã thiết kế đầy đủ (Mục 4.3) nhưng **chưa có dữ liệu/thực nghiệm** tại thời điểm nộp 25/7.
3. **[THIẾT KẾ — Future Work]** Vòng lặp Continual Learning từ phản hồi Admin (chính sách Overkill) — decision logic cơ bản 2 nhánh đã có, vòng lặp retrain đầy đủ chưa triển khai.

---

## 2. Công trình liên quan
*(Xem file riêng "Khảo sát công trình liên quan" — đã có trích dẫn đầy đủ [1]-[11]. Điểm mấu chốt: không nguồn nào mô hình hóa mối quan hệ giữa nhiều query trong cùng session cho bài toán SQLi — đây là khoảng trống mà Nhánh 3 lấp vào.)*

---

## 3. Kiến trúc hệ thống và Luồng dữ liệu (Real-time Pipeline) — cập nhật 3 nhánh

> ⚠️ **Sơ đồ dưới đây là thiết kế đầy đủ 3 nhánh.** Bản nộp 25/7 chỉ triển khai thực nghiệm **Nhánh 1 + Nhánh 2** và nhánh quyết định rút gọn tương ứng (2 dòng đầu của "Bộ xử lý trung tâm"); **Nhánh 3 và dòng quyết định thứ 3 ("Nhánh 1+2 sạch + Nhánh 3...") là Future Work**, chưa có thực nghiệm.

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

## 11. KẾ HOẠCH CHI TIẾT (13/7 – 25/7) — 4 người, chạy song song

**Nhân sự — Ngày 1-8 (13-20/7, đã xảy ra):**
- **Tôi** — Dữ liệu + Huấn luyện Nhánh 1 (xong: `models/nhanh1_v1/`, F1-macro=0.9822, 5 lớp) → xây khung API (`api/main.py`, `api/routers/`).
- **Bách** — Nhánh 2 (Anomaly), độc lập (Isolation Forest + One-Class SVM, tuning, audit).
- **Minh** — Streamlit (khung + các trang demo/admin).
- **Diệp** — Support/báo cáo (tạm dừng bài RIVF — xem Mục 0).

**Phân công Ngày 9-13 (21-25/7) — CHỈ 5 NGÀY, scope tối thiểu (đổi lần 2, bỏ luôn hệ thống):**

| Vai trò | Việc chính |
|---|---|
| **Tôi** | **Metric sâu hơn** (thêm ROC curve đầy đủ cho Nhánh 2) + viết & chạy thử **`notebooks/demo_detect.ipynb`** (load model thật, nhập query, trả verdict — đã xong, 19/20 đúng trên mẫu) + hỗ trợ Diệp số liệu/hình cho 2 bản báo cáo |
| **Bách** | Verify kỹ kết quả Nhánh 2 (OCSVM: FPR=0,3%, detection rate=20,7%, AUC=0,90) — đủ thuyết phục cho báo cáo chưa; cung cấp số liệu/giải thích chi tiết cho Diệp |
| **Minh** | Hệ thống/Streamlit **hoãn lại** — chuyển sang hỗ trợ vẽ biểu đồ/trực quan hoá (ROC curve, confusion matrix, sơ đồ kiến trúc) cho báo cáo |
| **Diệp** | Viết **2 bản báo cáo song song**: [`ban1_scope_hien_tai.md`](report/ban1_scope_hien_tai.md) (đúng 2 nhánh đã làm) + [`ban2_hoan_chinh.md`](report/ban2_hoan_chinh.md) (tầm nhìn đầy đủ 3 nhánh, Nhánh 3 đánh dấu Future Work) |

**Bảng chi tiết theo từng ngày/từng người nằm trong `ke_hoach_2_tuan.csv`** (52 dòng, Ngày 1-13, kết thúc đúng 25/7) — xem Mục 14 để biết cách cập nhật tự động bằng Claude Code.

**Tóm tắt luồng chính (chi tiết đầy đủ xem CSV):**
- *Ngày 1-8 (đã xong):* Tôi lo D1 → train Nhánh 1 → xây API. Bách lo D3 → train/đánh giá Nhánh 2. Minh dựng khung Streamlit. Diệp viết báo cáo phần đầu.
- *Ngày 9 (21/7, hôm nay):* Verify Nhánh 2 (fix model thiếu + thêm ROC curve); viết + chạy thử notebook demo; viết lại dàn ý 2 bản báo cáo (đã duyệt).
- *Ngày 10-11 (22-23/7):* Hỗ trợ số liệu/hình cho báo cáo; Diệp viết Bản 1 (Method/Kết quả) rồi bắt đầu Bản 2.
- *Ngày 12 (24/7):* Buffer sửa lỗi, hoàn thiện Bản 2 (Threat model/Thảo luận/Kết luận), rà soát cả 2 bản.
- *Ngày 13 (25/7, THỨ 7 — HẠN NỘP):* Nộp notebook + 2 bản báo cáo.

**Về bài RIVF 2026 (31/7):** tạm dừng lại (Mục 0) — sẽ lên kế hoạch chi tiết lại **sau khi qua hạn 25/7**, khi biết rõ còn bao nhiêu thời gian/nhân lực và Nhánh 3 có kịp làm thêm hay không trước 31/7.

---

## 12. Rủi ro (cập nhật 21/7 theo hạn mới)

**Rủi ro lớn nhất đã được loại bỏ:** trước đây lo Bách bị chặn bởi Nhánh 3 (Docker lab/sqlmap mất nhiều ngày) — nay **Nhánh 3 đã cắt hẳn khỏi phạm vi**, nên không còn đường găng (critical path) đó nữa.

**Rủi ro cũng giảm thêm (đổi lần 2):** bỏ luôn API/Bộ xử lý trung tâm/Streamlit khỏi scope 25/7 (thay bằng notebook demo đơn giản, đã viết + chạy thử xong) — không còn rủi ro tích hợp hệ thống phức tạp trong thời gian ngắn. Rủi ro chính giờ chỉ còn: **viết đủ 2 bản báo cáo chất lượng trong 4 ngày**.

**Nhánh 2 không còn là rủi ro** — đã verify thực tế (21/7): toàn bộ pipeline build+train chạy trong ~75 giây, đã thêm ROC curve đầy đủ. Việc còn lại chỉ là kiểm tra số liệu có đủ thuyết phục cho báo cáo.

**Gợi ý nếu vẫn thiếu thời gian tới Ngày 12 (24/7):** ưu tiên cắt theo thứ tự — (1) Bản 2 (hoàn chỉnh) có thể sơ sài hơn ở phần Future Work nếu gấp; (2) không cắt: Bản 1 (scope hiện tại) phải đầy đủ, notebook demo phải chạy đúng, nộp đúng hạn 25/7.

---

## 13. Future Work — những gì bị cắt khỏi bản nộp 25/7

**Bối cảnh:** để kịp hạn 25/7 với chỉ 5 ngày, đề tài **thu hẹp phạm vi thực nghiệm xuống 2 nhánh** (Nhánh 1 + Nhánh 2). Các hạng mục dưới đây vẫn là một phần thiết kế/đóng góp của đề tài (xem Mục 1, 3, 4.3) nhưng **chưa có thực nghiệm** trong bản nộp này. Nếu còn theo đuổi bài RIVF 2026 (hạn 31/7, xem Mục 0), nên hoàn thiện ít nhất một phần trước khi nộp; phần còn lại có thể hoàn thiện dần tới camera-ready (11/11) / hội nghị (18-20/12).

1. **Hệ thống tích hợp (API + Bộ xử lý trung tâm + Streamlit demo) — mới cắt (21/7, đổi lần 2).** Trước đó dự định làm cho 25/7, nay thay bằng `notebooks/demo_detect.ipynb` (load model, nhập query, trả verdict — logic gộp đơn giản, không phải Bộ xử lý trung tâm thật). Cần: đóng gói FastAPI (`api/main.py`, `api/routers/` — đã có khung từ trước, cần hoàn thiện), Bộ xử lý trung tâm đầy đủ (Overkill queue thật), Streamlit demo kết nối API thật.
2. **Nhánh 3 (Session-level / Sequence Model) — toàn bộ.** Đây là đóng góp lý thuyết chính của đề tài (giải quyết khoảng trống về temporal query splitting mà Related Work bỏ qua) nhưng **chưa triển khai bất kỳ phần nào** tại 21/7: chưa Docker lab, chưa session data, chưa model. Cần: dựng lab (DVWA/WebGoat) → sqlmap thu traffic thật → gán nhãn 2 tầng → so sánh kiến trúc Tầng 2 (GRU/CNN/Transformer nhẹ) → train + đánh giá.
3. **Continual Learning đầy đủ** — pipeline gán nhãn từ hàng đợi Overkill → retrain có rehearsal → validation gate. Bản 25/7 chỉ có decision logic cơ bản (BLOCK/OVERKILL/ALLOW), không có vòng lặp học liên tục.
4. **Concept Drift monitoring production** — log định kỳ PSI/KL-divergence, FPR/Recall theo thời gian, versioning + rollback model.
5. **Session Store production-grade** (TTL/eviction, Redis) — cần thiết khi có Nhánh 3.
6. **Benchmark latency/throughput dưới tải thật** — bản 25/7 chỉ test chức năng đúng/sai, chưa đo throughput dưới tải cao.
7. **Adversarial hardening nhiều vòng** (WAF-A-MoLE lặp lại nhiều vòng sinh-test-retrain cho Nhánh 1).
8. **Sanity-check nhãn tay quy mô lớn** (~100+/lớp, kiểm định chéo nhiều người) — hiện mới soi mẫu nhỏ (15-30/lớp).
9. **Publish dataset chính thức** — license D1 (SQLiV3) chưa rõ ràng (xem `data_contract.md`), cần xác minh/thay thế trước khi trích dẫn rộng rãi.
10. **So sánh với nhiều baseline SOTA hơn** — cho phiên bản mở rộng (journal) nếu muốn nâng tầm công bố sau hội nghị.

---

## 14. File theo dõi tiến độ và cách cập nhật tự động

Kế hoạch chi tiết (13 ngày × 4 người, 13/7-25/7, kèm sản phẩm bàn giao) nằm trong `ke_hoach_2_tuan.csv` — mỗi dòng là 1 task với cột: `Ngay, NgayThang, Thu, NguoiPhuTrach, VaiTro, CongViec, PhuThuoc, SanPham, TrangThai`. Dùng lệnh trong file `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md` để nhờ Claude Code tự hỏi vai trò, tự xác định ngày hiện tại, tự kiểm tra deliverable đã tồn tại trong repo chưa, và tự cập nhật cột `TrangThai` + đồng bộ tóm tắt vào file đề xuất này.

---

## 15. Nhật ký cập nhật tiến độ (tự động — Claude Code ghi vào đây)

*(Mục này để trống, sẽ được Claude Code tự động thêm dòng mỗi khi chạy lệnh cập nhật kế hoạch — xem `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md`. Mỗi lần chạy, thêm 1 dòng dạng: `[YYYY-MM-DD, Vai trò: X] Việc hôm nay: ... | Đã xong: ... | Trễ hạn: ...`)*

[2026-07-14, Vai trò: Toi] Việc hôm nay: Làm sạch D1 đầy đủ; viết pipeline canonicalization; chốt kiến trúc Nhánh 1 (đang bị chặn bởi Ngày 1 - Toi chưa hoàn thành) | Đã xong: Không có | Trễ hạn: Ngày 1 - Toi (Chốt data contract; tải D1 thô; test nhanh kiến trúc Nhánh 1) — không sản phẩm nào tồn tại (`data_contract.md`, `data/raw/d1_sqliv3_raw.csv`, `notebooks/model_comparison_nhanh1.ipynb`)

[2026-07-16, Vai trò: Toi] Việc hôm nay (Ngày 4): Đánh giá Nhánh 1 (P/R/F1) + bắt đầu setup Docker lab | Đã xong: (bù các ngày trước) so sánh 4 kiến trúc Nhánh 1 → chốt TF-IDF+LogReg (F1-macro 0.985, p50 0.5ms), train `models/nhanh1_v1/`, `reports/nhanh1_eval.json`, `notebooks/model_comparison_nhanh1.ipynb`; ngoài kế hoạch: đã build xong `data/processed/nhanh2_normal.csv` (91.935 dòng benign) cho Nhánh 2 | Trễ hạn/còn lại: `docker/dvwa/docker-compose.yml` (setup Docker lab cho Nhánh 3 — chưa làm); sanity-check tay đầy đủ 100 mẫu/lớp; lưu ý F1 cao đáng ngờ (dữ liệu quá dễ, chưa test adversarial)

[2026-07-16, Vai trò: Toi] Thông báo cho Bách: Ngày 1-2 của Bách (`data/raw/d3_csic2010_raw.csv`, `data/processed/nhanh2_normal.csv`) **đã có sẵn** — Toi làm chung khi build data Nhánh 1+2 (xem Mục 3.2 `data_contract.md`). Bách KHÔNG cần làm lại, có thể bắt đầu thẳng từ Ngày 3. Lưu ý: 4 đặc trưng thống kê (length, special_char_ratio, sql_keyword_count, entropy — `src/preprocessing/statistical_features.py`) đã có sẵn làm cột trong `nhanh2_normal.csv`, có thể dùng luôn cho Ngày 3 (trích đặc trưng) thay vì tự làm TF-IDF/embedding riêng, hoặc vẫn tự làm hướng khác nếu muốn so sánh. `nhanh2_anomalous_eval.csv` (25.065 dòng D3 anomalous) đã chuẩn bị sẵn để đánh giá FPR/detection rate ở Ngày 5. Toàn bộ data đã public trên HF: https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection

[2026-07-17, Vai trò: Toi] Phân công lại từ Ngày 5: hoán đổi track giữa Toi và Bách — Toi chuyển sang toàn bộ MLOps (Bo xu ly trung tam, Session Store, API, benchmark, Continual Learning, Concept Drift), Bách nhận thêm toàn bộ Nhánh 3 (Docker lab, sqlmap, session data, train) ngoài Nhánh 1+2 đã xong. Minh (Streamlit) và Diệp (Support) không đổi. Đã cập nhật `ke_hoach_2_tuan.csv` (Ngày 5-13) và Mục 11-12 tài liệu này. Lý do: Bách đã xong Nhánh 2 sớm + có kinh nghiệm train, Toi đang chủ động làm API rồi (nhánh `feature/api-backend-mlops`).

[2026-07-17, Vai trò: Toi] THU GỌN SCOPE (yêu cầu người dùng): xác nhận RIVF 2026 (đã tra trang thật) — hạn nộp 31/7/2026, 6 trang IEEE, EDAS, hội nghị 18-20/12 tại VinUniversity. 3 mốc mới: (1) 28/7 = train xong 3 nhánh + demo (KHÔNG bắt buộc Continual Learning/Concept Drift/Session Store production/benchmark tải — dời Future Work), (2) 31/7 = nộp bài RIVF, (3) trước 18/12 (nhắm camera-ready 11/11) = hoàn thiện toàn bộ hệ thống. Đã thêm Mục 0 (mốc thời gian), viết lại Mục 11-12, thêm Mục 13 (Future Work, 9 hạng mục). Cập nhật `ke_hoach_2_tuan.csv` từ 56 lên 76 dòng (Ngày 1-19): rút gọn Ngày 5-14, thêm Ngày 15-16 (chốt MVP), Ngày 17-19 (sprint viết + nộp bài — Diệp bắt đầu viết từng phần từ Ngày 5, không dồn cuối).

[2026-07-21, Vai trò: Toi] ĐỔI HẠN KHẨN CẤP (yêu cầu người dùng): hạn thật là Thứ 7 tuần này (25/7), không phải 28/7. Thu gọn scope quyết liệt: chỉ Nhánh 1 (làm mượt) + Nhánh 2 (đã kiểm tra — kiểm tra thực tế cho thấy KHÔNG phải nút thắt, toàn bộ pipeline build+train chạy ~75 giây; đã fix xong model.joblib bị thiếu, retrain lại: OCSVM FPR=0,3%, detection rate=20,7%, AUC=0,90). Nhánh 3 CẮT HẲN khỏi phạm vi 25/7 (xác nhận chưa có Docker lab/session data/model nào) — chuyển toàn bộ vào Future Work, giữ nguyên trong thiết kế/đóng góp lý thuyết của đề tài. Bài RIVF 2026 (31/7) tạm dừng kế hoạch chi tiết, sẽ làm lại sau 25/7. Đã cập nhật: header (V8), Mục 0 (mốc thời gian mới), Mục 1 (đóng góp — phân biệt đã làm/Future Work), Mục 3 (ghi chú sơ đồ), Mục 11-13 (kế hoạch/rủi ro/Future Work viết lại), Mục 14 (số dòng CSV). `ke_hoach_2_tuan.csv`: 76 → 52 dòng (Ngày 1-13, xóa Ngày 14-19 cũ).

[2026-07-21, Vai trò: Toi] ĐỔI KẾ HOẠCH LẦN 2 (cùng ngày, sau khi duyệt dàn ý): bỏ luôn toàn bộ hệ thống (API/Bộ xử lý trung tâm/Streamlit) khỏi scope 25/7, không chỉ Nhánh 3. Thay bằng: (1) metric sâu hơn — thêm ROC curve đầy đủ cho Nhánh 2 (`scripts/train_nhanh2.py`), (2) `notebooks/demo_detect.ipynb` — đã viết VÀ CHẠY THỬ THÀNH CÔNG (load model Nhánh 1+2 thật, nhập query, trả verdict; bắt được 1 bug thật — AnomalyDetector cần numpy array không phải list thường; sanity-check 19/20 đúng trên mẫu ngẫu nhiên, ca sai khớp hạn chế đã biết), (3) 2 bản báo cáo song song — `report/ban1_scope_hien_tai.md` (khung đã tạo, scope 2 nhánh) và `report/ban2_hoan_chinh.md` (khung đã tạo, tầm nhìn đầy đủ 3 nhánh + hệ thống, đánh dấu rõ phần nào là Future Work). Cập nhật Mục 0, 11, 12, 13 (thêm mục Future Work mới "Hệ thống tích hợp"). `ke_hoach_2_tuan.csv` Ngày 9-13 viết lại theo scope này.
