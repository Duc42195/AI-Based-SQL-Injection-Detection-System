# BẢN ĐỀ XUẤT ĐỀ TÀI: HỆ THỐNG PHÁT HIỆN SQL INJECTION DỰA TRÊN TRÍ TUỆ NHÂN TẠO
### (AI-Based SQL Injection Detection System) — Bản sửa đổi V5 (phân công lại: Tôi=Nhánh1&3, Bách=Nhánh2 độc lập, Minh=Streamlit, Diệp=Support)
### Hạn nộp: 28/7 — Mục tiêu hoàn thành: 26/7

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

## 11. KẾ HOẠCH CHI TIẾT 2 TUẦN (13/7 – 26/7) — 4 người, chạy song song

**Nhân sự (cập nhật):**
- **Tôi** — Dữ liệu + Huấn luyện **Nhánh 1 và Nhánh 3** (gộp cả 2 việc, đây là track nặng nhất/đường găng chính).
- **Bách** — **Nhánh 2 (Anomaly Detection)**, hoàn toàn độc lập, không phụ thuộc dữ liệu của ai (dùng D3-CSIC2010 công khai). Sau khi xong Nhánh 2, chuyển sang xây Bộ xử lý trung tâm + API.
- **Minh** — Xây **giao diện demo bằng Streamlit** (không đụng vào huấn luyện mô hình), kết nối API thật của từng nhánh khi lần lượt sẵn sàng.
- **Diệp** — Support: đọc survey, viết báo cáo, kiểm định chéo nhãn.

> ⚠️ Vì "Tôi" giờ gánh cả dữ liệu lẫn huấn luyện cho 2 nhánh, đây là đường găng (critical path) của cả dự án — không có ai san sẻ nếu trễ. Nếu thiếu thời gian, hạng mục ưu tiên lùi lại đầu tiên là Continual Learning (Ngày 13), không ảnh hưởng phần lõi (3 nhánh + Overkill + demo).

**Bảng chi tiết theo từng ngày/từng người, kèm sản phẩm bàn giao (deliverable) và trạng thái, nằm trong file đi kèm `ke_hoach_2_tuan.csv`** — dùng file này để theo dõi tiến độ hàng ngày (xem Mục 13 để biết cách cập nhật tự động bằng Claude Code).

**Tóm tắt luồng chính (chi tiết đầy đủ xem CSV):**
- *Tuần 1:* Tôi lo D1 → train Nhánh 1 → đánh giá → dựng Docker lab → chạy sqlmap thu traffic Nhánh 3 → parse & gán nhãn. Bách lo D3 → train/đánh giá Nhánh 2 song song, không chờ ai. Minh dựng khung Streamlit + các trang UI bằng dữ liệu mock. Diệp viết Mục 1-4 báo cáo theo tiến độ.
- *Tuần 2:* Tôi train/đánh giá Nhánh 3 → đóng gói API, bàn giao cho Bách tích hợp. Bách xây Bộ xử lý trung tâm + Overkill + Session Store + API tổng + benchmark. Minh nối API thật của từng nhánh vào Streamlit ngay khi có (Nhánh 2 trước, Nhánh 1&3 sau). Diệp viết Mục 5-9 + tổng hợp báo cáo cuối.

---

## 12. Vì sao Bách không còn bị "block", và rủi ro giờ nằm ở đâu

**Bách (Nhánh 2): hoàn toàn không bị chặn.** D3 (CSIC2010) là dataset công khai tải trong vài phút, không phụ thuộc "Tôi" hay bất kỳ ai — Bách có thể chạy toàn bộ track của mình độc lập từ Ngày 1 đến khi tích hợp ở Tuần 2.

**Minh (Streamlit): cũng không bị chặn**, vì xây UI trước bằng dữ liệu/API giả lập (mock), chỉ cần đổi endpoint sang API thật khi từng nhánh lần lượt sẵn sàng (Nhánh 2 xong sớm ở Ngày 5, Nhánh 1&3 xong muộn hơn ở Ngày 11).

**Rủi ro thật sự giờ nằm ở "Tôi":** vì gộp cả dữ liệu lẫn huấn luyện cho 2 nhánh vào một người, việc này buộc phải làm **tuần tự** (dữ liệu Nhánh 1 → train Nhánh 1 → dữ liệu Nhánh 3 → train Nhánh 3), không có ai chia sẻ tải. Đây là điểm cần theo dõi sát nhất:
- Nếu Nhánh 1 xong đúng hạn (Ngày 4), vẫn còn đủ thời gian cho Nhánh 3 (Ngày 5–10).
- Nếu Nhánh 1 trễ, toàn bộ Nhánh 3 và cả việc bàn giao API cho Bách/Minh đều trễ theo — nên **Ngày 4 (đánh giá Nhánh 1)** là mốc kiểm tra quan trọng nhất của cả kế hoạch.
- Gợi ý giảm rủi ro: nếu tới Ngày 4 chưa xong Nhánh 1, có thể nhờ Bách (đã quen pipeline Nhánh 2 tương tự) hỗ trợ song song ở phần dữ liệu Nhánh 3 (Docker lab/sqlmap) trong lúc "Tôi" tập trung hoàn thiện Nhánh 1 — đây là lý do nên dùng chung `data_contract.md` ngay từ Ngày 1, để bất kỳ ai cũng có thể tiếp quản một phần việc khi cần.

---

## 13. File theo dõi tiến độ và cách cập nhật tự động

Kế hoạch chi tiết (14 ngày × 4 người, kèm sản phẩm bàn giao) nằm trong `ke_hoach_2_tuan.csv` — mỗi dòng là 1 task với cột: `Ngay, NgayThang, Thu, NguoiPhuTrach, VaiTro, CongViec, PhuThuoc, SanPham, TrangThai`. Dùng lệnh trong file `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md` để nhờ Claude Code tự hỏi vai trò, tự xác định ngày hiện tại, tự kiểm tra deliverable đã tồn tại trong repo chưa, và tự cập nhật cột `TrangThai` + đồng bộ tóm tắt vào file đề xuất này.

---

## 14. Nhật ký cập nhật tiến độ (tự động — Claude Code ghi vào đây)

*(Mục này để trống, sẽ được Claude Code tự động thêm dòng mỗi khi chạy lệnh cập nhật kế hoạch — xem `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md`. Mỗi lần chạy, thêm 1 dòng dạng: `[YYYY-MM-DD, Vai trò: X] Việc hôm nay: ... | Đã xong: ... | Trễ hạn: ...`)*

[2026-07-14, Vai trò: Toi] Việc hôm nay: Làm sạch D1 đầy đủ; viết pipeline canonicalization; chốt kiến trúc Nhánh 1 (đang bị chặn bởi Ngày 1 - Toi chưa hoàn thành) | Đã xong: Không có | Trễ hạn: Ngày 1 - Toi (Chốt data contract; tải D1 thô; test nhanh kiến trúc Nhánh 1) — không sản phẩm nào tồn tại (`data_contract.md`, `data/raw/d1_sqliv3_raw.csv`, `notebooks/model_comparison_nhanh1.ipynb`)
