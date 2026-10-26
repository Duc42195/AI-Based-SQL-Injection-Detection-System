# RIVF 2026 — Response to Reviewers

> **Paper:** *Complementary Supervised and Benign-Only Anomaly Detection for Unseen SQL Injection Families at the Database Proxy*
> **Manuscript:** [[rivf_manuscript.pdf]]
> **Reviews:** [[comment]]
> **Quy ước:** `[TODO: …]` = số liệu/thí nghiệm chưa có, phải chạy xong mới được điền. Không gửi bản rebuttal còn `TODO`.

---

## 0. Ghi chú nội bộ (không gửi cho reviewer)

**Điểm trung bình:** Novelty 2.7 · Rigour 3.0 · Presentation 3.3 · Relevance 3.3. Cả 3 reviewer đều khen giao thức leave-one-attack-family-out và phát hiện về boolean-blind; cả 3 đều chê "limited contribution".

**6 chủ đề lặp lại giữa các reviewer** (trả lời gộp ở mục 2, mục 3 chỉ trỏ về):

| Mã | Chủ đề | R1 | R2 | R3 | Cần thí nghiệm mới? |
| -- | ------ | :-: | :-: | :-: | :-: |
| T1 | Novelty / đóng góp hạn chế | ✔ | ✔ | ✔ | Có (kiểm tra lại dữ liệu; viết rõ quy trình gán nhãn bằng regex vào bài, xem Phụ lục A) |
| T2 | Proxy vs. dữ liệu HTTP-derived | ✔ | ✔ | ✔ | Có (tách kết quả theo representation) |
| T3 | FPR 5.27% và decision policy đầy đủ | ✔ | ✔ | ✔ | Có (chạy cả 2 branch trên cùng tập benign). Hệ thống trade-off FPR/DR **đã có sẵn**, cần viết rõ hơn trong bài, xem Phụ lục B |
| T4 | Residual 11.2% và label noise boolean-blind | ✔ | ✔ | ✔ | Có (đếm theo nguồn, chạy lại chỉ với nhãn D3) |
| T5 | Latency / throughput | ✔ | ✔ | ✔ | Không (chỉ sửa cách diễn đạt) |
| T6 | Leakage theo template / nguồn | ✔ |  |  | Có (grouped split / leave-one-source-out) |

**⚠️ Việc gấp không liên quan nội dung:** Reviewer 2 báo danh sách tác giả trong PDF **không khớp** với EDAS. Đây là thiếu sót khi submit; danh sách nào là đúng do **first author (Minh-Duc Do-Xuan) quyết định** (xem mục 4).

**⚠️ Giới hạn trang:** thêm bảng mới (T2, T3, T4, T6) sẽ tốn chỗ. Ưu tiên gộp vào Table VI/VII hiện có và cắt bớt Section VI.

---

## 1. Cover letter

We thank the three reviewers for their careful reading and constructive comments. All reviewers recognized the paired leave-one-attack-family-out protocol and the contrast between the near-perfect closed-set F1 of boolean-blind SQLi and its high supervised miss rate when withheld. The main concerns were (i) the size of the methodological contribution, (ii) the gap between the intended database-proxy deployment and the HTTP-derived part of the data, (iii) the operational false-positive rate and the absence of a full decision-policy evaluation, (iv) label quality for the boolean-blind class, and (v) possible template-level leakage under row-level splits. Section 2 answers these shared concerns once; Section 3 answers every comment point by point. We have [TODO: "carried out" hoặc "will carry out"] the additional analyses requested and revised the manuscript accordingly.

---

## 2. Responses to shared concerns

| Theme | Raised in | Response | Revision |
| ----- | --------- | -------- | -------- |
| **T1. Novelty / limited contribution** | comment_2, comment_8, comment_9, comment_14, comment_15, comment_18 | We agree that DistilBERT and LOF are established models, and we do not claim a new detector. The contribution is the **evaluation design and its finding**. Prior hybrid SQLi work reports an aggregate score of the fused system, so it cannot show *which* branch catches an unseen family. Our paired protocol makes both branches score the **identical withheld queries**, which separates three cases: supervised transfer, anomaly-only recovery, and joint failure. This exposes a result that closed-set benchmarks hide: boolean-blind SQLi reaches 0.994 F1 when seen, yet 86.5% of it is classified as normal when unseen. The same protocol can be applied to any supervised and benign-only pair. We also recognize that part of the technical contribution, the construction of the six-class benchmark, was under-described. Sources without per-technique metadata are assigned SQLi subtypes by a deterministic regular-expression tagger, and the same signatures are used to remove mislabeled attacks from the benign pool. The submitted version mentions this step only briefly. | (a) Reword the contribution list and abstract so the paper is framed as an evaluation study of complementarity, not as a new architecture. State explicitly in Section II what the paired protocol measures that aggregate hybrid evaluations do not.<br>(b) Describe the labeling procedure in Section IV: the signature for each subtype, the fixed priority order (stacked, time-blind, error-based, union-based, boolean-blind), the fallback of unmatched SQLi payloads to boolean-blind, and the additional signatures used to filter the benign pool. Report how many rows each rule assigns per source. [TODO: số dòng theo rule và theo nguồn, sau khi kiểm tra lại dữ liệu] |
| **T2. Proxy deployment vs. HTTP-derived data** | comment_6 (1), comment_12a, comment_18 | We agree. D1 and D3 contain SQL statements, while D2 and D4 contribute parameter content extracted from HTTP requests. Section VI already notes this, but the claim in the title and abstract is stronger than the evidence. The experiments evaluate the detection logic intended for a proxy, not a live proxy deployment. | (a) Add a column or table splitting Branch 1 F1, Branch 2 FPR/DR, and leave-one-family-out coverage by input representation: SQL statements (D1, D3) vs. HTTP-derived (D2, D4). [TODO: số liệu]<br>(b) Qualify the wording in the abstract, Section III-A and the conclusion to "intended for deployment at the database proxy" and state that no native proxy traffic is evaluated. |
| **T3. FPR of 5.27% and the full decision policy** | comment_6 (4), comment_12a, comment_18 | The 5.27% figure is LOF alone (782 of 14,841 benign test queries) at one operating point. The system treats this as a configurable trade-off rather than a fixed property, through two mechanisms.<br>**(i) Adjustable operating point.** Branch 2 outputs a continuous anomaly score, and the alarm threshold is a single configuration value. The 21-point threshold sweep in Section V-B measures FPR and detection rate across the whole range. An operator can therefore choose a lower-FPR point according to the cost of false alarms, without retraining.<br>**(ii) Graded response.** Immediate blocking is decided only by Branch 1. A Branch-2-only alarm leads to *hold/review* (Table II): the query enters a review queue, and if it is not reviewed within a configurable timeout it is denied by default. A Branch 2 false positive therefore costs review effort and delay, not an instant block. Without review it falls back to denial, which we now state explicitly.<br>We agree that the operational picture requires both branches on the same benign queries. | (a) Run both branches on the same benign test set and report the share of queries that are blocked, held for review, and allowed. [TODO: % block / % hold / % allow trên 14,841 benign]<br>(b) Describe both mechanisms in Section III-C and V-B. Turn the threshold sweep into a short table listing several operating points (threshold, FPR, DR), including lower-FPR points such as 1% and 2%. [TODO: lấy từ sweep của model trong manuscript]<br>(c) State the review timeout and the deny-by-default behaviour in the decision policy. |
| **T4. Boolean-blind residual and label noise** | comment_6 (3), comment_12a, comment_18 | The 11.2% residual is a reported finding, not a hidden weakness. It marks a shared failure region where an isolated query is too close to benign traffic for either branch. We agree that label quality must be verified for this class. D3 labels come from sqlmap's own `attack_technique` metadata, so they are generator-verified. D4 subtypes are assigned by rules, and our 30-sample audit estimated about 13% noise. | (a) Report the number of boolean-blind samples from each source in train, test, and the withheld fold. [TODO: bảng đếm D1/D2/D3/D4]<br>(b) Repeat the boolean-blind fold using only generator-verified D3 labels and report B1 miss, B2 DR and combined coverage. [TODO: 3 số]<br>(c) State whether the main finding (high B1 miss, large B2 recovery) holds on verified labels. |
| **T5. Latency and throughput** | comment_6 (5), comment_12a, comment_18 | We agree that the reported 18–21 ms per query is a component-level estimate measured on one RTX 3050 workstation, not end-to-end proxy latency. Most of it comes from LOF's nearest-neighbour lookup (about 15–18 ms). Because Branch 2 only changes the decision when Branch 1 outputs normal, it does not need to run on queries that Branch 1 already blocks. Approximate nearest-neighbour search or a smaller reference set can further reduce the cost; we leave measurement of these options to future work. | Rename "latency budget" to "component-level latency estimate" throughout, state the hardware, and add end-to-end proxy throughput explicitly as a limitation. |
| **T6. Template-level leakage under row splits** | comment_6 (2), comment_12 | Exact duplicates are removed on canonical query text before splitting, and D3 is split by complete sqlmap campaign. We agree that near-identical templates may still cross the split for D1, D2 and D4, which use row-level splits. We also note that the benign source-removal diagnostic (Section IV-A) already shows that source shift strongly affects Branch 2 (FPR rises to 64.8–79.8% on a removed source). | (a) Compute a template signature by masking literals and numbers in the canonical text, and report how many test templates also appear in training. [TODO]<br>(b) Re-split D1, D2 and D4 grouped by template and report Branch 1 macro-F1 and the leave-one-family-out table under that split. [TODO]<br>(c) If space allows, add a leave-one-source-out result. [TODO]<br>(d) Replace "eliminate near-duplicate leakage" with "reduce" wherever it appears. |

---

## 3. Point-by-point responses

### Reviewer 1

| ID | Comment (summary) | Response | Change in manuscript |
| -- | ----------------- | -------- | -------------------- |
| comment_1, comment_5 | Paired evaluation and the boolean-blind contrast are informative; limitations are acknowledged. | We thank the reviewer for recognizing the paired design and the boolean-blind contrast. | — |
| comment_2 | Valid work but limited contribution. | See **T1**. | Contribution list and abstract reframed. |
| comment_3 | Readable, but revision needed in some parts. | We revised the presentation following the specific points below and tightened Sections V and VI. | Language and layout pass over Sections III–VI. |
| comment_4 | Relevance: Good. | Thank you. | — |
| comment_6 (1) | D2 and D4 are HTTP-derived, not SQL at the proxy. Separate results by representation and qualify the deployment claim. | See **T2**. | Results split by representation; deployment claim qualified. |
| comment_6 (2) | Row-level splits may leave similar templates in train and test. Evaluate grouped by template or held-out source. | See **T6**. | Template overlap reported; template-grouped split added. |
| comment_6 (3) | Report boolean-blind counts per source and test whether the result holds with verified labels. | See **T4**. | Per-source counts and a D3-only boolean-blind fold added. |
| comment_6 (4) | FPR is LOF only. Test both branches on the same benign queries; report block, hold and allow. | See **T3**. | Benign outcome breakdown under the full policy added. |
| comment_6 (5) | Explain which data selected the models and the LOF threshold; compare detectors at the same FPR; call latency component-level. | **Model selection:** [TODO: xác nhận lại pipeline — Branch 1 chọn kiến trúc trên tập nào (validation tách từ train hay test split)? LOF dùng contamination = 0.05 cố định hay có tune?] The withheld attack queries of the leave-one-family-out experiment are never used for selection.<br>**Equal-FPR comparison:** we agree that Table VI compares detectors at different operating points. We will report the detection rate of One-Class SVM, Isolation Forest and LOF at the same FPR, read from their score curves. [TODO]<br>**Latency:** see **T5**. | Selection procedure described in Section IV-C; Table VI extended with DR at equal FPR; latency wording changed. |
| comment_7 | Submission policy: No. | — | — |

### Reviewer 2

| ID | Comment (summary) | Response | Change in manuscript |
| -- | ----------------- | -------- | -------------------- |
| comment_8 | Minor variations on a well-investigated subject. | See **T1**. The subject is well studied in the closed-set setting; our point is that closed-set accuracy does not predict unseen-family transfer, which the paired protocol measures directly. | Contribution reframed. |
| comment_9 | Valid work but limited contribution. | See **T1**. | — |
| comment_10 | Readable, but revision needed. | See the response to comment_3. | Presentation pass. |
| comment_11 | Relevance: Good. | Thank you. | — |
| comment_12 | Strong aspects: paired evaluation, campaign-aware split, boolean-blind recovery from 13.5% to 88.8%. | We thank the reviewer. One clarification: the campaign-aware split applies to D3 only, so it *reduces* rather than eliminates near-duplicate leakage. We address the remaining sources under **T6**. | Wording "eliminate" changed to "reduce". |
| comment_12a | Boolean-blind residual 11.2%. | See **T4**. The residual is the largest among the four families and we report it as the main limitation of query-level detection. Repeated probes with changing comparison bounds are more visible across a session than in a single statement, which motivates session-level correlation as future work. | Section VI states this explicitly. |
| comment_12a | LOF FPR 5.27% and 18–21 ms latency. | See **T3** and **T5**. The FPR/DR operating point is adjustable along the measured threshold sweep, and Branch-2-only alarms are held for review rather than blocked immediately. | Full-policy benign breakdown and lower-FPR operating points added; latency called component-level. |
| comment_12a | HTTP parameters instead of native proxy logs; 13% label noise; no session-level correlation, out-of-band SQLi or adversarial evasion. | HTTP-derived input: see **T2**. Label noise: see **T4**. Session-level correlation, out-of-band SQLi and adversarial transformations (e.g. WAF-A-MoLE) are outside the scope of this query-level study and are already listed in Section VI. We agree they matter for deployment and keep them as explicit limitations. | Scope statement moved earlier (Section III-A) so the reader sees it before the results. |
| comment_12b | Authors in the PDF do not match EDAS. | We thank the reviewer for pointing this out and apologize for the oversight made at submission time. [TODO: chọn 1 câu theo quyết định của first author, xem mục 4] | [TODO: tùy quyết định ở mục 4] |

### Reviewer 3

| ID | Comment (summary) | Response | Change in manuscript |
| -- | ----------------- | -------- | -------------------- |
| comment_14 | Some interesting ideas on a well-investigated subject. | Thank you. See **T1** for how we position the contribution. | — |
| comment_15 | Valid work but limited contribution. | See **T1**. | Contribution reframed. |
| comment_16 | Well written. | Thank you. | — |
| comment_17 | Strong aspects: motivated integration, leave-one-family-out insight, multiple datasets, campaign-aware split. | We thank the reviewer. | — |
| comment_18 | Novelty limited; combines established DistilBERT and LOF. | See **T1**. | Contribution reframed. |
| comment_18 | Heterogeneous public data, not real proxy traffic. | See **T2**. Results are now separated by input representation and the deployment claim is qualified. | Results split; claim qualified. |
| comment_18 | 5.27% FPR may be problematic in production; 11.2% residual is significant. | See **T3** (adjustable FPR/DR operating point; Branch-2-only alarms are held for review rather than blocked immediately; full-policy breakdown and lower-FPR operating points added) and **T4** (residual analysed with verified labels). | As in T3 and T4. |
| comment_18 | No adversarial robustness or end-to-end throughput evaluation. | We agree. Both require a live proxy and an adversarial generator, which go beyond this query-level study. We state them explicitly as limitations and describe latency as a component-level estimate (see **T5**). | Limitations and latency wording updated. |
| comment_20 | Relevance: Good. | Thank you. | — |
| comment_19 | Submission policy: yes. | — | — |

---

## 4. Submission policy (Reviewer 2, comment_12b)

**Tình trạng:** danh sách tác giả trong manuscript và trên EDAS không giống nhau do thiếu sót khi submit. **Quyết định danh sách nào là đúng thuộc về first author (Minh-Duc Do-Xuan).** Không ai khác tự sửa EDAS hay PDF trước khi first author chốt.

PDF hiện có 6 tác giả theo thứ tự: Minh-Duc Do-Xuan, Bach Luong-Chi, Diep Dinh-Ngoc, Minh Nguyen-Quang, Linh Dinh-Van, Thai Dinh Kim (corresponding).

| Việc | Chi tiết | Người làm | Trạng thái |
| ---- | -------- | --------- | :--------: |
| Liệt kê chênh lệch PDF và EDAS | Ghi rõ khác ở đâu: thiếu/thừa tác giả, thứ tự, chính tả tên, affiliation. | [TODO] | ☐ |
| Chốt danh sách tác giả đúng | First author quyết định giữ theo PDF, theo EDAS, hay một danh sách khác. | Minh-Duc Do-Xuan | ☐ |
| Sửa nguồn bị sai | Sửa EDAS và/hoặc PDF cho khớp danh sách đã chốt. Nếu hội nghị không cho tự sửa EDAS thì liên hệ chair. | First author | ☐ |
| Điền câu trả lời comment_12b | Chọn một trong các câu mẫu bên dưới, chỉ dùng thì hiện tại hoàn thành khi đã sửa xong thật. | [TODO] | ☐ |

**Câu mẫu cho comment_12b** (chọn một, dán vào bảng Reviewer 2):

| Trường hợp | Câu trả lời |
| ---------- | ----------- |
| PDF đúng, sửa EDAS | The EDAS registration has been updated so that it lists exactly the same authors, in the same order, as the manuscript. |
| EDAS đúng, sửa PDF | The author block of the manuscript has been corrected to match the EDAS registration. |
| Sửa cả hai | Both the manuscript and the EDAS registration have been updated to the same author list. |

---

## 5. Action items (nội bộ)

| # | Việc | Phục vụ | Số liệu cần điền | Trạng thái |
| - | ---- | ------- | ---------------- | :--------: |
| A1 | Tách kết quả Branch 1, Branch 2 và leave-one-family-out theo representation: SQL (D1, D3) vs. HTTP-derived (D2, D4) | T2 | F1, FPR, DR, coverage cho mỗi nhóm | ☐ |
| A2 | Chạy cả 2 branch trên cùng 14,841 benign test, đếm block / hold / allow | T3 | 3 tỷ lệ | ☐ |
| A3 | DR của OCSVM, Isolation Forest, LOF tại cùng FPR (1%, 2%, 5%) | T3, comment_6 (5) | Bảng 3 × 3 | ☐ |
| A3b | Viết rõ hệ thống trade-off FPR/DR vào bài: ngưỡng cấu hình được, bảng vài operating point từ threshold sweep, hold/review + timeout deny-by-default (Phụ lục B) | T3 | Bảng threshold, FPR, DR | ☐ |
| A0 | Kiểm tra lại dữ liệu: nguồn nào đi qua regex tagger, mỗi rule gán bao nhiêu dòng, bao nhiêu dòng rơi vào fallback boolean-blind; rồi viết quy trình regex vào Section IV (Phụ lục A) | T1, T4 | Bảng rule × nguồn | ☐ |
| A4 | Đếm boolean-blind theo nguồn (train, test, fold bị loại) | T4 | Bảng đếm D1–D4 | ☐ |
| A5 | Chạy lại fold boolean-blind chỉ với nhãn D3 (sqlmap metadata) | T4 | B1 miss, B2 DR, combined | ☐ |
| A6 | Tính template signature (mask literal, số), đo overlap train/test; split lại theo template | T6 | % overlap, macro-F1, bảng LOAFO mới | ☐ |
| A7 | (Nếu đủ trang) leave-one-source-out | T6 | Macro-F1 theo nguồn bị loại | ☐ |
| A8 | Xác nhận quy trình chọn model và ngưỡng LOF (dữ liệu nào, có dùng test không) | comment_6 (5) | Mô tả 2–3 câu | ☐ |
| A9 | Sửa câu chữ: reframe contribution, "intended for", "reduce" leakage, "component-level latency", đưa scope lên Section III-A | T1, T2, T5, comment_12 | — | ☐ |
| A10 | First author chốt danh sách tác giả, rồi sửa EDAS và/hoặc PDF cho khớp | comment_12b | Câu trả lời theo mục 4 | ☐ |
| A11 | Điền hết `[TODO]` trong mục 1–3, đổi thì "will" thành "have" cho các việc đã làm xong | Tất cả | — | ☐ |

---

## Phụ lục A — Quy trình gán nhãn bằng regex (nội bộ, phục vụ T1/T4)

Nguồn code: `src/preprocessing/multiclass_tagger.py`. Đây là nội dung cần viết lại thành văn xuôi hoặc bảng nhỏ trong Section IV của bài.

**A.1. Gán subtype cho payload đã biết là SQLi** (`tag_attack_payload`). Các rule được thử **theo đúng thứ tự dưới đây, rule đầu tiên khớp sẽ thắng**:

```text
1. stacked        ;\s*(DROP|INSERT|UPDATE|DELETE|EXEC|TRUNCATE|CREATE|GRANT|ALTER)
2. time_blind     SLEEP\(|BENCHMARK\(|WAITFOR\s+DELAY|PG_SLEEP\(
3. error_based    EXTRACTVALUE|UPDATEXML|FLOOR\(RAND|CAST\(.*AS|CONVERT\(
4. union_based    UNION\s+(ALL\s+)?SELECT
5. boolean_blind  (OR|AND)\s+\d+\s*=\s*\d+|'\s*OR\s*'?1'?\s*=\s*'?1
   (không khớp rule nào) -> boolean_blind   <- fallback catch-all
```

Tất cả rule đều không phân biệt hoa thường. Dòng normal giữ nhãn normal từ nguồn (`tag_query` với `is_attack = False`).

**A.2. Lọc pool benign** (`matches_any_attack_signature`). Một dòng nguồn gán "normal" vẫn bị loại nếu khớp bất kỳ rule SQLi ở trên, hoặc một trong các signature sau:

```text
OS command injection   [;&|]\s*(cat|whoami|ping|wget|curl|nc)\s|\$\(|`[^`]+`|\(\)\s*\{\s*:;\s*\}
SSI injection          <!--#(exec|include|echo)\s
XSS                    <script[^>]*>|javascript:|on(error|load)\s*=
```

SSRF callback (ví dụ `owasp.org`, oastify) **không** có signature chung nên không bị lọc. Đây là giới hạn đã biết.

**A.3. Điểm phải nói thẳng trong bài:**
- **Fallback về boolean-blind** là nguồn chính của nhiễu nhãn: payload SQLi nào không khớp rule nào đều thành boolean-blind. Điều này giải thích ~13% noise trong audit 30 mẫu, và liên quan trực tiếp đến kết quả boolean-blind mà reviewer hỏi (T4).
- **Thứ tự ưu tiên** quyết định nhãn khi một payload khớp nhiều rule (ví dụ có cả `UNION SELECT` và `SLEEP(` thì thành time-blind).
- D3 **không** dùng tagger này, vì `attack_technique` lấy từ metadata của sqlmap.

**A.4. Cần kiểm tra lại dữ liệu trước khi viết** (việc A0):

| Câu hỏi | Kết quả |
| ------- | ------- |
| Nguồn nào đi qua tagger: chỉ D4, hay cả D1, D2? | [TODO] |
| Số dòng mỗi rule gán, theo từng nguồn | [TODO] |
| Số dòng rơi vào fallback (không khớp rule nào) | [TODO] |
| Số dòng bị loại khỏi pool benign theo từng signature | [TODO] |
| Code hiện tại có khớp đúng phiên bản đã dùng để ra số trong manuscript không | [TODO] |

---

## Phụ lục B — Hệ thống trade-off FPR/DR đã có (nội bộ, phục vụ T3)

Những thành phần sau **đã có trong hệ thống**, chỉ cần mô tả rõ hơn trong bài:

| Thành phần | Hiện trạng trong repo | Cần viết gì vào bài |
| ---------- | --------------------- | ------------------- |
| Ngưỡng của Branch 2 | Một giá trị cấu hình duy nhất: `branch2_anomaly.lof_contamination` = 0.05 trong `configs/config.yaml` | Ngưỡng là tham số vận hành, đổi được mà không sửa code |
| Threshold sweep | `train/generate_metrics.py` quét ngưỡng trên anomaly score, ghi FPR, DR, precision, FP/TP cho mỗi điểm vào `report/metrics/branch2_threshold_sweep.csv`. Manuscript đã có câu mô tả sweep 21 điểm (Section V-B) | Đổi đoạn mô tả thành bảng nhỏ vài operating point, để reviewer thấy có điểm FPR thấp hơn 5.27% và DR tương ứng |
| Phản hồi phân cấp | Branch 1 = attack thì block ngay. Branch 1 = normal và Branch 2 = anomalous thì vào Overkill queue chờ admin review | Nói rõ Branch-2-only alarm không bị block ngay |
| Timeout | `decision.overkill_timeout_seconds` = 300, quá hạn thì deny-by-default | Phải nói thật: không ai review thì query bị chặn. Đừng viết "Branch 2 không bao giờ block" |

⚠️ File `branch2_threshold_sweep.csv` trong repo là của lần chạy cũ (7,929 benign), **không khớp** với manuscript (14,841 benign). Phải chạy lại sweep trên đúng model của manuscript trước khi lấy số đưa vào bảng.
