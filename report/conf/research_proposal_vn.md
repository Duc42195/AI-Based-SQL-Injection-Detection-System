# Đề xuất nghiên cứu: Hệ thống AI đa nhánh phát hiện SQL Injection tại Database Proxy

**Chuẩn bị cho:** RIVF 2026 (IEEE, VinUniversity, Hà Nội).
**Vai trò của tài liệu:** bản tóm tắt tiếng Việt, **không phải** yêu cầu nộp bắt buộc của RIVF (RIVF chỉ yêu cầu bài báo IEEE 6 trang qua EDAS). Đây là bản rút gọn (~3 trang) của bản đầy đủ tiếng Anh [`research_proposal.md`](research_proposal.md) — dùng để nhóm/giảng viên đọc nhanh toàn bộ phạm vi dự án.

**Quan hệ với bài báo:** [`rivf2026_paper.tex`](rivf2026_paper.tex) chỉ báo cáo kết quả đã có thật — Nhánh 1, Nhánh 2, và nghiên cứu zero-day (**Phương án (A)** đã chốt) — Nhánh 3 và hệ thống tích hợp trình bày là *future work*. Tài liệu này mô tả **toàn bộ tầm nhìn hệ thống**, gắn nhãn rõ mỗi phần đã làm/đang thiết kế.

---

## 1. Bối cảnh và Vấn đề

SQL Injection (SQLi) là một trong những lỗ hổng web nguy hiểm và phổ biến nhất: kẻ tấn công chèn lệnh SQL độc hại qua input không được làm sạch, có thể đọc/sửa/xóa dữ liệu hoặc leo thang đặc quyền. WAF dựa trên luật (rule-based) — giải pháp phổ biến nhất — có hai điểm yếu cấu trúc: (1) **không bắt được tấn công zero-day/obfuscated** vì phụ thuộc chữ ký định sẵn; (2) **phân tích theo từng truy vấn đơn lẻ không thể phát hiện tấn công nhiều bước** — Boolean-blind, Time-blind, và query-splitting SQLi rải tín hiệu độc hại qua nhiều truy vấn *trông vô hại khi xét riêng lẻ* trong cùng một session; chỉ khi xem cả chuỗi truy vấn mới lộ ra mẫu tấn công.

## 2. Mục tiêu nghiên cứu

1. Phát hiện các loại SQLi đã biết với độ chính xác cao, FPR thấp (supervised, theo từng truy vấn).
2. Phát hiện tấn công **zero-day** bằng anomaly detection huấn luyện **chỉ trên traffic benign**.
3. Phát hiện tấn công **đa bước ở mức session** (blind SQLi, query-splitting) mà phân tích đơn truy vấn bỏ lọt.
4. Kết hợp 3 tín hiệu vào một cơ chế quyết định "an toàn khi nghi ngờ" (giữ lại chờ xác nhận thay vì âm thầm cho qua).
5. Khép vòng học liên tục (Continual Learning) từ xác nhận của Admin + giám sát concept drift theo thời gian.
6. **Đo lường thực nghiệm** (không chỉ giả định) khoảng trống mà phát hiện theo truy vấn để lại — đây là cơ sở thực nghiệm cho Nhánh 3.

## 3. Phạm vi

**Trong phạm vi:** Union-based, Error-based, Boolean-blind, Time-blind, Stacked-query SQLi (theo truy vấn); và query-splitting theo thời gian trong một session (theo thiết kế).

**Ngoài phạm vi:** Second-order SQLi (payload lưu ở request A, kích hoạt ở request B — có thể khác session/nhiều ngày sau); Out-of-band SQLi (rò rỉ dữ liệu qua kênh phụ DNS/HTTP mà proxy không quan sát được); XSS/CSRF; phát hiện xâm nhập tầng mạng.

## 4. Kiến trúc đề xuất

Đặt tại **"Vị trí B"**: proxy nhận câu SQL *sau khi* backend đã build xong, *trước khi* tới database — nhìn thấy dạng cuối cùng sẽ thực thi, và giảm rủi ro HTTP Parameter Pollution như một hệ quả phụ.

```
[Request] → [Backend] → [DB Proxy: Canonicalize → Nhánh 1/2/3] → [Database]
                                    │
                        [Bộ xử lý trung tâm / Overkill]
        Nhánh 1 = tấn công          → BLOCK ngay
        Nhánh 1 sạch + Nhánh 2 bất thường → OVERKILL (giữ, chờ Admin, timeout → deny)
        Nhánh 1+2 sạch + Nhánh 3 phát hiện chuỗi bất thường → giữ cả session
        Mọi thứ sạch                → ALLOW
                                    │
                [Continual Learning: nhãn từ Admin → retrain có gate kiểm định]
```

| Nhánh | Vai trò | Trạng thái |
|---|---|---|
| **Nhánh 1** — Supervised đa lớp | Phân loại `normal` + 4 loại SQLi. Đã so sánh 4 kiến trúc, chọn **TF-IDF + Logistic Regression** (F1-macro tốt nhất/độ trễ/kích thước) | ✅ Đã train, đánh giá |
| **Nhánh 2** — Anomaly detection | Chỉ học từ benign; 4 đặc trưng thống kê (độ dài, tỉ lệ ký tự đặc biệt, số từ khóa SQL, entropy). Chọn **One-Class SVM** | ✅ Đã train, đánh giá |
| **Nhánh 3** — Session-level sequence model | Kiến trúc 2 tầng: Tầng 1 tái dùng embedding Nhánh 1; Tầng 2 là **GRU 1 lớp** trên `[embedding Nhánh 1 ⊕ điểm Nhánh 2]` mỗi bước, phân loại 4 lớp (benign/boolean_blind/time_blind/query_splitting) | ✅ **Đã train + đánh giá offline** — F1-macro = **1.0** trên tập test 280 session, kể cả ở chế độ "hard" (chấm bằng biến thể Nhánh 1 chưa từng thấy boolean_blind). Dữ liệu là tấn công bisection **thật** (thuật toán y hệt sqlmap) nhắm vào DB SQLite tự host thật — không phải template — nhưng vẫn là **Cách A**; **Cách B (sqlmap thật + DVWA/WebGoat qua Docker) chưa làm.** ⚠️ F1=1.0 tuyệt đối trên tập test nhỏ, tự sinh — là bằng chứng proof-of-concept mạnh, chưa phải bằng chứng tổng quát hóa |

**Bộ xử lý trung tâm (fuse_decision):** ✅ đã cài đặt thật trong `deploy/routers/detect.py`, không phải logic khái niệm — nhưng nhánh Nhánh 3 trong API (`deploy/routers/branch3.py`) **vẫn là stub**, luôn trả `not_ready`, nên đường leo thang session hiện chưa hoạt động trên hệ thống chạy thật.

**Continual Learning + Concept Drift:** ✅ **đã cài đặt và chạy thực nghiệm offline đầy đủ** (`src/continual_learning/`, `src/monitoring/drift.py`, `src/decision/queue.py`, 198 test pass). Phát hiện chính: drift monitor **không** bắt được lớp mới hiếm (~1% traffic), nhưng review queue bắt được toàn bộ; cân bằng lại pool nhãn đã xác nhận trước khi retrain mới là điều giúp model được promote (F1 tăng, FPR giảm 64%); ablation xác nhận lợi ích đến từ việc học lớp mới, không chỉ từ có thêm dữ liệu. Gán nhãn **mô phỏng** (chưa phải người thật), traffic là **replay** dữ liệu cũ chứ không phải traffic production thật. Riêng 3 router API — Admin queue, drift dashboard, Nhánh 3 serving — **vẫn là stub/mock**, chưa nối vào các module `src/` thật ở trên.

**Kế hoạch dữ liệu Cách B (chưa thực hiện):** dựng lab dễ tổn thương cô lập mạng (DVWA/WebGoat qua Docker), tấn công thật bằng `sqlmap --technique=B/T`, bắt traffic qua mitmproxy/Burp. Chỉ giữ session mà sqlmap **báo trích xuất dữ liệu thành công** làm nhãn dương. Session benign lấy từ cookie có sẵn của CSIC 2010 hoặc crawl bình thường trên cùng lab. Session Store production (Redis/TTL) vẫn cần để phục vụ Nhánh 3 trên hệ thống chạy thật — chưa làm.

## 5. Kết quả thực nghiệm đã có

| Chỉ số | Nhánh 1 (TF-IDF+LogReg) | Nhánh 2 (One-Class SVM) |
|---|---|---|
| F1-macro / AUC | **0.982** | **0.90** |
| FPR | — | **0.3%** |
| Detection rate | — | 20.7% |
| Độ trễ p50 | 0.5 ms | dưới 1 ms (ước tính) |

**Nghiên cứu zero-day (leave-one-out)** — bỏ từng lớp SQLi khỏi tập train Nhánh 1, đo tỉ lệ Nhánh 1 bỏ lọt (miss rate) và tỉ lệ Nhánh 2 bắt được độc lập:

| Lớp bị loại | Nhánh 1 miss rate | Nhánh 2 detection rate |
|---|---|---|
| union_based | 2.5% | 0.5% |
| error_based | 0.0% | 89.7% |
| **boolean_blind** | **90.2%** | 5.4% |
| time_blind | 0.3% | 12.7% |

**Ý nghĩa:** với các lớp có cấu trúc khác biệt rõ, Nhánh 1 vẫn nhận ra "có tấn công" dù chưa từng học đúng loại đó. Nhưng `boolean_blind` gần giống truy vấn hợp lệ về mặt từ vựng → bị bỏ lọt 90.2%, và Nhánh 2 chỉ bắt độc lập được 5.4%. Đây chính là bằng chứng thực nghiệm cho việc cần Nhánh 3: tín hiệu của blind SQLi nằm ở *chuỗi truy vấn*, không nằm ở một truy vấn đơn lẻ.

> Lưu ý: trường `combined_coverage` trong `summary.json` gốc không nhất quán với 2 cột trên (không tái dựng lại được bằng phép hợp) — cần tính lại từ dự đoán thô trước khi trích dẫn ở bất kỳ đâu.

**Hạn chế dữ liệu đã đo được:** ~13% nhãn sai trong lớp catch-all `boolean_blind` (kiểm tra thủ công 30 mẫu); lớp `stacked` không có mẫu thật nào ở cả 3 nguồn dữ liệu (D1/D4/D7) → 363 mẫu tổng hợp, nhưng bị tách biệt dễ dàng 100% ở mọi kiến trúc (dấu hiệu template lặp lại, không phải tín hiệu chất lượng thật) nên bị loại khỏi tập train được báo cáo. Giấy phép D1 (SQLiV3) chưa rõ ràng.

## 6. Dữ liệu

| Dữ liệu | Dùng cho | Giấy phép |
|---|---|---|
| D1 — SQLiV3 | Nhánh 1 | Chưa rõ |
| D3 — CSIC 2010 | Nhánh 2 (benign + tập eval bất thường) | Public |
| D4 — payload-box | Nhánh 1 | MIT |
| D7 — SR-BH 2020 (honeypot, 527.813 dòng) | Nhánh 1 + Nhánh 2 (đa số khối lượng) | CC0 1.0 |

Dữ liệu đã xử lý public trên Hugging Face (`Jason-42195/VNU-SQLi-Detection`), không commit vào repo. **Dữ liệu session cho Nhánh 3 chưa tồn tại.**

## 7. Trạng thái triển khai tổng thể

| Thành phần | Trạng thái |
|---|---|
| Canonicalization | ✅ Xong, có test |
| Nhánh 1 + Nhánh 2 | ✅ Xong, đã đánh giá |
| Nghiên cứu zero-day | ✅ Xong |
| Demo query→verdict | ✅ `demo_detect.ipynb` (19/20 đúng) |
| **Nhánh 3 (GRU session-level)** | ✅ **Đã train + đánh giá offline** (F1-macro=1.0, Cách A) — xem mục 4. Cách B chưa làm; tập test còn nhỏ/tự sinh |
| **Bộ xử lý trung tâm (fuse_decision)** | ✅ Đã cài đặt và nối thật trong `deploy/routers/detect.py` — đường leo thang Nhánh 3 có sẵn nhưng "ngủ" vì router Nhánh 3 còn stub |
| **Continual Learning / Concept Drift** | ✅ Đã cài đặt + chạy thực nghiệm offline đầy đủ (198 test pass) — xem mục 4. Gán nhãn còn mô phỏng, traffic là replay |
| API sống: phục vụ Nhánh 3, hàng đợi Admin, dashboard drift | ⛔ Cả 3 router này vẫn là stub/mock, chưa nối vào các module `src/` đã có ở trên |
| Session Store production (Redis/TTL) | ⛔ Chưa bắt đầu — chỉ cần cho việc phục vụ Nhánh 3 trên hệ thống sống, không cần cho pipeline train offline |
| Đánh giá adversarial (WAF-A-MoLE) | ⛔ Chưa chạy — số liệu hiện tại là cận trên, chưa chứng minh độ bền vững trước né tránh |

## 8. Lộ trình / mốc thời gian

**RIVF (bên ngoài, cố định):** nộp bài **31/7/2026** (EDAS) → thông báo kết quả **15/10** → camera-ready **11/11** (nên có ít nhất kết quả sơ bộ Nhánh 3 trước mốc này) → hội nghị **18–20/12/2026** tại VinUniversity, Hà Nội.

**Nội bộ:** Nhánh 1+2 + báo cáo môn học chốt **25/7**; ngày đệm chỉnh số liệu cho báo cáo hội nghị **26/7**; **hạn cuối toàn bộ mã nguồn (Nhánh 3 + hệ thống tích hợp + Continual Learning + Concept Drift): 31/12/2026** — còn xa nhưng là hạn cứng, không phải "làm khi rảnh".

## 9. Nhóm thực hiện

- **Bách Lương-Chi** (RMIT) — Nhánh 2, và Nhánh 3 (chủ trì tới đây).
- **Đức Đỗ-Xuân Minh** — Nhánh 1 + tích hợp/MLOps.
- **Diệp Đinh-Ngọc** — Viết báo cáo, hỗ trợ chung.
- **Minh Nguyễn-Quang** — Giao diện demo Streamlit.
- **Giảng viên hướng dẫn:** Linh Đinh-Văn, Thái Kim-Đính.

## 10. Rủi ro chính

- **Nhánh 3 mới chỉ chứng minh được ở quy mô nhỏ** — F1-macro=1.0 nhưng trên tập test 280 session tự sinh (Cách A); chưa có bằng chứng tổng quát hóa với traffic thật độc lập (Cách B). Cần nêu rõ giới hạn này ở bất kỳ đâu trích dẫn kết quả.
- **Rủi ro tích hợp:** Nhánh 3, hàng đợi review, và drift monitoring đều đã kiểm chứng offline nhưng 3 router API tương ứng vẫn là stub — đây là việc tích hợp có phạm vi rõ ràng trên các thành phần đã chạy tốt, không phải rủi ro nghiên cứu mở.
- **Giấy phép D1 chưa rõ** — coi dữ liệu gộp là "chưa rõ nguồn gốc" cho tới khi xác minh, không công bố như MIT/CC0 sạch.
- **Chưa đánh giá adversarial** — nêu rõ là hạn chế trong bài báo, không mặc định đã giải quyết.
- **Trần F1 thật của Nhánh 1 chưa rõ** do nhiễu nhãn đo được ở `boolean_blind` và pool `normal` gốc — đã báo cáo là hạn chế đo được, không giấu.
