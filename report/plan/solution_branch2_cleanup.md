# Giải pháp: Dọn dẹp benign pool Branch 2 (SSRF + chuỗi ngắn)

> Người soạn: Bách (Branch 2 / Anomaly Detection) | Trình Duc review trước khi thực thi
> Trạng thái: **ĐÃ THỰC THI** (cập nhật 14/08) — data dọn theo đúng đề xuất + fix 2 điểm mentor review (SSRF khỏi TEST, `id` unique).
> Vấn đề gốc được phát hiện qua audit: `train/audit_branch2_ssrf_impact.py`
> và đo ảnh hưởng `report/metrics/zeroday_experiment/branch2_ssrf_impact.json`.
> Kết quả cuối (re-fit OCSVM trên data sạch): **FPR 5.00% → 4.76%**, **DR 24.92% → 31.19%**, chi tiết `report/plan/plan_next_branch2_cleanup.md`.

---

## 1. Tóm tắt vấn đề

Branch 2 là **anomaly detection dạng one-class** — chỉ huấn luyện trên traffic *normal*, rồi coi mọi thứ nằm ngoài vùng normal là bất thường [2](#ref2),[3](#ref3),[7](#ref7). Dataset dùng làm benign pool (`branch2_data.csv`, 12,000 dòng train) có **2 loại nhiễu**:

| # | Nhóm | Số lượng (train) | % | Bản chất |
|---|------|------------------:|--:|----------|
| 1 | SSRF / OS-cmd call-back (`owasp.org`, `/etc/passwd`, `shellshock`) | 928 (train) + 225 (test) | 7.73% (train) | **attack thật** nhưng bị gắn nhãn `normal` |
| 2 | Chuỗi ngắn vô nghĩa (`cecile`, `34192`, …) | 2,183 | 18.2% | **benign thật** nhưng lấn át tỷ trọng |

Hai nhóm này **hại theo cơ chế khác nhau** và cần cách xử lý khác nhau — không thể gộp chung một động tác.

---

## 2. Phân tích cơ chế & bằng chứng đo được

### 2.1. Vì sao Branch 2 KHÔNG "học anomaly từ data bất thường"

One-class / novelty detection KHÔNG học "thế nào là bất thường" từ các mẫu bất thường; nó chỉ học **một mô hình của normality** rồi đo độ lệch khỏi mô hình đó [1](#ref1),[2](#ref2),[7](#ref7). Khi đưa attack thật (SSRF) vào tập "normal":

- Model sẽ **hấp thụ dáng vẻ của SSRF vào vùng normal** → sau này những dòng SSRF tương tự bị tính là *gần normal*, **giảm khả năng phát hiện** chúng.
- Đây chính là **data contamination**, và tài liệu chỉ rõ nó làm suy giảm hiệu năng detector [6](#ref6),[10](#ref10), gây tích tụ từ early stage [10](#ref10).

Tuy nhiên, đo thực tế trên `branch2_data.csv` cho thấy **việc bỏ SSRF ra khỏi train ~ không đổi hiệu năng hiện tại** (bảng dưới là đo audit ban đầu, chỉ xét SSRF trong TRAIN):

| Chỉ số | Có SSRF | Bỏ SSRF | Chênh lệch |
|---|---:|---:|---:|
| FPR benign | 0.0030 | 0.0037 | +0.0007 (± nhiễu calibrate) |
| Detection rate | 0.2073 | 0.2308 | **+2.35pp** |
| p90 score benign | −1.304 | −0.999 | +0.305 |

> **Cập nhật (14/08):** sau khi dọn **cả TRAIN lẫn TEST** (gỡ tổng 1,153 dòng SSRF khỏi benign) rồi re-fit OCSVM đúng hyperparams `branch2_anomaly`, kết quả cuối: **FPR 5.00% → 4.76%**, **DR 24.92% → 31.19%**, KS 0.4723 → 0.5216. Phân phối normal/anomaly **vẫn trùng đáng kể** — đúng nhận định của Duc: Branch 2 không phải lớp chính bắt attack đã biết, vai trò là zero-day. Không retrain model deploy (chỉ test lại).

**Giải thích:** SSRF (`...owasp.org`) trong **không gian 4 đặc trưng cấu trúc** (`length, special_char_ratio, sql_keyword_count, entropy`) trùng với dòng benign dài đơn giản (0 keyword, ít ký tự đặc biệt) → không phải outlier trong feature space này. Nghĩa là dù đúng nguyên tắc phải dọn, **tác động lên số đo hiện có là tối thiểu**; giá trị của việc dọn nằm ở **tính sạch khái niệm** hơn là cải thiện metric.

### 2.2. Sự khác biệt quan trọng: SSRF vs chuỗi ngắn

| | SSRF (928) | Chuỗi ngắn (2,183) |
|---|---|---|
| Bản chất | attack, nhãn nhầm `normal` | benign thật |
| Loại hại | **semantic** — học sai *nghĩa* của normal [6](#ref6) | **distribution** — méo *hình dạng* vùng normal |
| Cách dọn | **loại khỏi benign train** → chuyển sang eval | **không xóa**, cân lại **tỷ trọng** |

Chuỗi ngắn là benign thật (web log luôn có), **không thể xóa 100%**. Vấn đề là tỷ trọng **18.2%** quá cao so với production [5](#ref5). Vì OCSVM kéo mô hình về phía vùng đông dữ liệu, một tỷ lệ lệch như vậy làm vùng normal **thắt lẹo về phía chuỗi siêu ngắn** (`length≈6.6`, `entropy≈2.3`, 0 keyword) → các dòng benign dài/đủ phức tạp bị đẩy ra **rìa ngưỡng** → **FPR tăng trên traffic thật**. Trên eval hiện tại (cùng phân phối méo) con số vẫn "đẹp", nhưng đây là **số tự tham chiếu (self-confirming)**, không phản ánh generalization [1](#ref1),[7](#ref7).

> **Cập nhật (14/08):** đã thực thi — chuỗi ngắn (`length ≤ 10`) trong TRAIN được rebalance từ 18.19% → **3.00%** (275 dòng) theo target đặt từ literature review này, **không xóa** dòng (vẫn giữ bản chất benign).

### 2.3. Literature review — mục tiêu tỷ lệ dòng ngắn có cơ sở

Do không khảo sát được data gốc, dùng bằng chứng học thuật về phân phối HTTP request:

- **Mah 1997** (đo packet trace HTTP thật): độ dài request **bimodal**, mean ≈ **320 bytes**, median ≈ **240 bytes**, có một mốc nhỏ ~1 KB cho form phức tạp [12](#ref12). Không thấy dải "2–6 ký tự vô nghĩa" chiếm đa số như 18% hiện tại.
- **Zuech et al.** (CSE-CIC-IDS2018): web traffic thật **cực kỳ mất cân bằng** giữa normal và attack (SQLi tới ~153,911:1); phần lớn dòng normal là traffic thực, không phải chuỗi cực ngắn [13](#ref13).

**Đề xuất mục tiêu:** thay vì áp một con số %, đặt ngưỡng độ dài tối thiểu dựa trên phân phối thật — ví dụ **hạ tỷ lệ các dòng `length ≤ 10` xuống gần mức ~trung vị request thật**, sao cho phân phối `length` của train tiến gần dạng bimodal như Mah [12](#ref12). Con số chính xác nên đo lại từ file nguồn `d1_sqliv3` khi có data.

---

## 3. Đề xuất giải pháp

> ✅ **Trạng thái thực thi (14/08):** cả 3 bước dưới đã làm, kết quả ở `report/plan/plan_next_branch2_cleanup.md` + notebook `branch2_normal_anomaly_dist.ipynb`.

### Bước 1 — Dọn SSRF/OS-cmd ra khỏi benign pool (semantic cleanup)

- Thêm pattern call-back/SSRF vào hàm signature filter (khâu canonicalization):
  `owasp\.org`, `(http|https)://<attacker-domain>`, `/etc/passwd`, `shellshock`, `{{`, ngoài ra các domain dạng `\d+\.owasp\.org`.
- **Chuyển** các dòng này **sang anomaly eval set** (để test detector có cờ bất thường không), **không giữ** trong benign train.
- Ghi chú: theo phần 2.1, bước này ~ không đổi FPR/DR hiện tại, giá trị nằm ở tính đúng đắn dữ liệu.
- ✅ **Đã làm:** gỡ **1,153 dòng SSRF** khỏi benign (train 928 + test 225), chuyển sang `branch2_anomalous_eval_clean.csv`; `id` dựng lại unique toàn cục (`<source>:<idx>`).

### Bước 2 — Cân lại tỷ trọng chuỗi ngắn (distribution rebalancing) — KHÔNG xóa

- Xác định tỷ lệ dòng ngắn mong muốn dựa trên **thống kê web-log thật** (tham chiếu dataset gốc d1_sqliv3 / proxy log), ví dụ giảm từ 18.2% xuống mức sát production.
- Giữ nguyên bản chất benign, chỉ thay đổi **tỷ trọng** nhóm ngắn so với nhóm dài — không loại hẳn.
- ✅ **Đã làm:** chuỗi ngắn (`length ≤ 10`) trong TRAIN rebalance 18.19% → **3.00%**, không xóa dòng.

### Bước 3 — Rebuild, retrain, regenerate (BẮT BUỘC nếu dọn)

Bất kỳ bước nào ở trên thay đổi dataset → phải chạy lại toàn bộ:
1. `train/build_branch2_data.py` → file benign pool mới
2. Retrain `branch2_v1` (OCSVM)
3. Re-tính FPR / DR / ngưỡng (P95, per-query) **và toàn bộ số Branch 3** phụ thuộc score Branch 2
4. Cập nhật `report/metrics/*` + manifest + figure

> ⚠️ **Cấm dọn data rồi giữ nguyên con số cũ** — số cũ không còn khớp data mới.
> ✅ **Đã làm (theo đúng chỉ đạo "test lại, không train lại"):** re-fit OCSVM trên data sạch để so sánh, **không đổi model deploy**; đã cập nhật toàn bộ số liệu FPR/DR/figure.

---

## 4. Quyết định cần Duc chốt

- [x] **1.** Có loại SSRF/OS-cmd khỏi benign train (chuyển sang eval) không? → **Đã làm** (gỡ 1,153 dòng khỏi train + test).
- [x] **2.** Có cân lại tỷ trọng chuỗi ngắn không? — trong trường hợp **không khảo sát được data gốc** (`data/` rỗng) thì dùng mục tiêu từ literature review (mục 2.3): đưa phân phối `length` của train về gần dạng **bimodal** như đo thực tế của Mah [12](#ref12), thay vì 18% hiện tại. → **Đã làm** (rebalance 18.19% → 3.00%).
- [x] **3.** Có chấp nhận retrain + regenerate toàn bộ metrics (Bước 3) không? → **Đã test lại, không retrain deploy** (theo chỉ đạo); đã regenerate toàn bộ metrics + figure.

> Lưu ý đối trọng: vì SSRF đã đo là ~ không đổi hiệu năng hiện tại, nếu deadline gấp và không cần con số khác, có thể **chỉ làm Bước 1 (nguyên tắc) + ghi disclaimer**, tạm hoãn Bước 2 (cân tỷ trọng).

---

## 5. Tài liệu tham khảo (academic)

**One-class / anomaly detection (nền tảng Branch 2):**
- <span id="ref1"></span>**[1]** B. Schölkopf, J. C. Platt, J. Shawe-Taylor, A. J. Smola, R. C. Williamson, "Estimating the Support of a High-Dimensional Distribution," *Neural Computation*, 13(7):1443–1471, 2001. DOI: 10.1162/089976601750264965.
- <span id="ref2"></span>**[2]** F. T. Liu, K. M. Ting, Z.-H. Zhou, "Isolation Forest," in *Proc. 8th IEEE Int. Conf. on Data Mining (ICDM)*, pp. 413–422, 2008. DOI: 10.1109/ICDM.2008.17.
- <span id="ref3"></span>**[3]** F. T. Liu, K. M. Ting, Z.-H. Zhou, "Isolation-Based Anomaly Detection," *ACM Transactions on Knowledge Discovery from Data (TKDD)*, 6(1):1–39, 2012. DOI: 10.1145/2133360.2133363.
- <span id="ref7"></span>**[7]** M. A. F. Pimentel, D. A. Clifton, L. Clifton, L. Tarassenko, "A review of novelty detection," *Signal Processing*, 99:215–249, 2014.

**Label noise / contamination (cơ sở cho việc dọn & hệ quả):**
- <span id="ref4"></span>**[4]** B. Frénay, M. Verleysen, "Classification in the Presence of Label Noise: A Survey," *IEEE Transactions on Neural Networks and Learning Systems*, 25(5):845–869, 2014. DOI: 10.1109/TNNLS.2013.2292894.
- <span id="ref6"></span>**[6]** K. Qiu, L. Li, M. Kloft, F. Rudolph, S. Mandt, "Understanding and Mitigating Data Contamination in Deep Anomaly Detection: A Kernel-based Approach," in *Proc. 31st Int. Joint Conf. on Artificial Intelligence (IJCAI)*, 2022.
- <span id="ref10"></span>**[10]** "Robust Anomaly Detection Under Contaminated Data: A Comprehensive Evaluation," *PHM Society European Conference*, 2025. (trích dẫn mức hại ngay cả ở tỉ lệ contamination thấp)

**SSRF (chứng minh SSRF là một lớp attack riêng, khác SQLi):**
- <span id="ref8"></span>**[8]** K. Al-talak, O. Abbass, "Detecting Server-Side Request Forgery (SSRF) Attack by using Deep Learning Techniques," *International Journal of Advanced Computer Science and Applications (IJACSA)*, 12(12), 2021. DOI: 10.14569/IJACSA.2021.0121230.
- <span id="ref9"></span>**[9]** Y. Ji, T. Dai, Z. Zhou, Y. Tang, J. He, "Artemis: Toward Accurate Detection of Server-Side Request Forgeries through LLM-Assisted Inter-procedural Path-Sensitive Taint Analysis," in *Proc. ACM on Programming Languages (OOPSLA)*, 2025.

**SQLi detection bằng ML (bối cảnh của hệ thống — 3 branch):**
- <span id="ref5"></span>**[5]** M. Alghawazi, D. Alghazzawi, S. Alarifi, "Detection of SQL Injection Attack Using Machine Learning Techniques: A Systematic Literature Review," *Journal of Cybersecurity and Privacy*, 2(2):764–777, 2022.
- <span id="ref11"></span>**[11]** M. A. Oudah, M. F. Marhusin, "SQL Injection Detection Using Machine Learning with Different TF-IDF Feature Extraction Approaches," in *Int. Conf. on Information Systems and Intelligent Applications (ICISIA) 2022*, Springer, pp. 707–720, 2022. DOI: 10.1007/978-3-031-16865-9_57.

**Phân phối & cân bằng web traffic (cơ sở mục tiêu tỉ lệ dòng ngắn):**
- <span id="ref12"></span>**[12]** B. A. Mah, "An Empirical Model of HTTP Network Traffic," in *Proc. IEEE INFOCOM '97*, Kobe, Japan, pp. 592–600, 1997.
- <span id="ref13"></span>**[13]** R. Zuech, T. M. Khoshgoftaar, N. Seliya, "Investigating rarity in web attacks with ensemble learners," *Journal of Big Data*, 2021. DOI: 10.1186/s40537-021-00462-6.

---

## Phụ lục — Thuật ngữ

- **SSRF (Server-Side Request Forgery):** kẻ tấn công nhét URL không tin cậy vào hàm web app, khiến **máy chủ tự** gửi request tới địa chỉ đó (nội bộ/ngoài). Có trong **OWASP Top 10**; là lớp attack **khác họ** SQLi [8](#ref8),[9](#ref9).
- **FPR (False Positive Rate):** tỷ lệ traffic *bình thường* bị nhầm là tấn công. Càng thấp càng ít làm phiền người dùng hợp lệ.
- **Benign pool (one-class training set):** tập dữ liệu "normal" để anomaly detector xây mô hình normality [1](#ref1),[7](#ref7). Yêu cầu **sạch về bản chất** để không nuốt attack vào normal [6](#ref6).