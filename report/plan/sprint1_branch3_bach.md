# Kế hoạch Sprint 1 — Branch 3 (Bách)

> Người thực hiện: Bách | Branch (git): `feature/feat-branch3-eval-s1`
> Căn cứ: `report/plan/plan.csv` (Sprint 1, task #76/#80/#84/#88/#92)
> Vai trò: Researcher — Branch 3 data + model end-to-end
> Lưu ý: không commit thẳng `main`, mọi thay đổi qua branch + PR, `uv run pytest` xanh trước khi commit.

---

## Hiểu hệ thống Branch 3 HIỆN TẠI (quan trọng — đừng nhầm với GRU cũ)

Branch 3 **KHÔNG phải model có train**. Nó là `SessionCorrelator` (`src/models/branch3_session.py`):

1. **Không có weights riêng.** Tái sử dụng model có sẵn, không train gradient:
   - **Content check:** nối (concatenate) toàn bộ `query_canonical` của session, đưa qua Branch 1 (`branch1_v1`) dựng sẵn → attack_prob = 1 − P(normal), so với `content_threshold`.
   - **Behavior check:** lấy điểm anomaly `branch2_v1` (Branch 2) cho TỪNG query, gộp theo session (mean_score, fraction_above), so với 2 threshold.
   - Kết hợp = **OR** 2 check trên.
2. **"Train Branch 3" thực chất = `calibrate_branch3.py`**:
   - Nạp Cách A session (train/test) từ `branch3_sessions_cach_a.csv`.
   - `correlator.calibrate(train_sessions)` → chỉ chọn **3–4 scalar threshold** (per_query từ benign percentile; mean/fraction/content bằng TPR−FPR trên nhãn TRAIN).
   - Đánh giá ablation (content-only / behavior-only / combined) trên **split TEST**.
   - Ghi `models/branch3_v2/metadata.json` (chỉ threshold) + `report/metrics/branch3_eval.json`.
3. **Live API:** `POST /branch3/session` body `{queries: [..]}` → `correlator.score(queries)` → `session_label` / `is_attack` / `detail`. Không có logic nhóm session tư đâu trong `deploy/` — client tự truyền danh sách query theo thứ tự.
4. **Session definition** (`config branch3_session.session_idle_gap_seconds: 1800`): 1 session = `session_id` có sẵn (CSIC cookie) HOẶC `(client_ip, idle_gap <= 1800s)`. HIỆN ĐANG **DEAD CODE** — không có logic ranh giới session trong `deploy/` (chỉ `deploy/registry.py` + router đơn).

### Hệ quả cho các ngày làm việc
- **Day 1 audit:** rò rỉ train/test là rò rỉ giữa **CALIBRATION (train) và EVAL (test)** — không phải "model memorize". Vì không có weights, `DR=1.0` thực chất nói lên: threshold được calibrate rồi eval trên **cùng data generator + target trùng lặp** (same-target leakage) → **KHÔNG phải bằng chứng generalization**. Đây chính là lý do Cách B quan trọng (Day 2-3).
- **Day 4 (task #88):** mọi lỗ hổng liên quan **live hệ thống** (grouping, concurrency, idle-gap) đều ở tầng `deploy/`, không phải data.

---

## Day 1 — Audit dữ liệu & tính hợp lệ kết quả (task #76)

**Loại công việc:** audit DATA (không train, không sửa model).
Mục đích: xác nhận data pipeline hợp lệ (không leakage/trùng/giả) thì con số báo cáo mới đáng tin.

### Mảng 1 — Branch 3 train/test leakage
- File cần: `data/processed/branch3_sessions_cach_a.csv` (split 1,120/280 session)
- Check:
  - Session near-duplicate giữa train vs test (trùng hoặc quá giống `query_canonical`)
  - Same-target leakage: session train/test cùng chung target/ground-truth
- **Góc nhìn đúng kiến trúc:** đây là rò rỉ giữa **calibration (train) và eval (test)** của `SessionCorrelator`. Nếu test trùng gần với train → threshold calibrate rồi eval trên data overlap → `DR/FPR` trở nên lạc quan, KHÔNG phải bằng chứng generalization. Cách B sau đó chính là để kiểm tra threshold có transfer sang traffic thật không.
- Kết luận: có/không, cần sửa hoặc re-caveat con số nào.

### Mảng 2 — Continual Learning stacked-class leakage
- File cần: 363 template stacked + cách sample-with-replacement → 727
- Check: template overlap giữa training pool và phần eval/replay.

### Mảng 3 — Re-tagger noise rate (zero-day)
- Các label: `union_based`, `error_based`, `time_blind` trong leave-one-out
- Đối chiếu: `report/metrics/zeroday_experiment/zeroday_report.md`

### Deliverable Day 1
- Báo cáo audit ngắn: đã check gì, phát hiện gì, con số nào cần sửa/re-caveat trước khi nộp.

**⛔ Phụ thuộc trước khi làm:** file `branch3_sessions_cach_a.csv` hiện **thiếu local** → xin từ Duc (hoặc pull HF) trước. Nếu không có, gen lại bằng `build_session_dataset.py` (khác bản gốc → cảnh báo khi đối chiếu số).

---

## Day 2 — Dựng lab Cách B (task #80)

**Loại công việc:** setup + chuẩn bị DATA mới (capture thật).

- Docker DVWA/WebGoat (`docker-compose.yml`) — lưu `docker/dvwa/`
- Cài sqlmap + mitmproxy (host hoặc container)
- Dựng pipeline capture traffic giữa attacker (sqlmap) và lab (qua proxy)

### Deliverable Day 2
- `docker/dvwa/docker-compose.yml`
- Script capture traffic

---

## Day 3 — Capture data thật (task #84) + CHECKPOINT

- Chạy `sqlmap --technique=B` và `--technique=T` xuyên proxy vào lab
- Chỉ giữ session có extract thành công → `data/raw/branch3_cach_b_sessions/`

**⛔ CHECKPOINT:** hết ngày Day 3 không ra dữ liệu dùng được → **dừng Cách B**, pivot Day 4-5 sang robustness track.

### Deliverable Day 3
- `data/raw/branch3_cach_b_sessions/` (nếu có)

---

## Day 4 — Parse + Cross-validate + Vá API (task #88)

- (a) Nếu có data Cách B:
  - Parse sang schema session Cách A
  - Cross-validate threshold `SessionCorrelator` (đã calibrate trên Cách A) bằng `train/calibrate_branch3.py` eval path
  - So sánh Cách A vs Cách B — câu hỏi then chốt: **threshold Cách A có transfer sang traffic thật không?** (Day 1 cho thấy Cách A eval bị same-target lạc quan nên đây là kiểm chứng bắt buộc)
- (b) Luôn làm — vá lỗ hổng live-API (đều ở tầng `deploy/`, không phải data; tham chiếu `report/conf/outline.md`):
  - Session rỗng (empty session) — hiện `SessionRequest.queries` yêu cầu `min_length=1`
  - Single-query session gọi qua endpoint live
  - Session chứa hỗn hợp nhiều loại tấn công (mixed attack types) trong 1 session
  - Nhiều session đồng thời / chồng lấn (concurrent/overlapping sessions)
  - Input dị dạng / adversarial vào `/branch3/session`
  - Thread-safety của registry lazy-loader khi chạy đồng thời
  - Quyết định + document: `session_idle_gap_seconds` nên wire hay đánh dấu dead/future-work
  - Test end-to-end qua `/detect` và `/branch3/session`

### Deliverable Day 4
- Kết quả so sánh Cách A vs Cách B (nếu có)
- Robustness-test findings

---

## Day 5 — Tổng hợp & bàn giao (task #92)

- Báo cáo audit Day 1
- Cập nhật `report/metrics/branch3_eval.json` (số Cách A + so sánh Cách B nếu có)
- Báo cáo robustness

### Deliverable Day 5
- Bàn giao Duc: audit report + `branch3_eval.json` (final Sprint 2) + robustness report

---

## Checklist điều kiện tiên quyết

| Thứ cần | Trạng thái | Ghi chú |
|---|---|---|
| Models `branch1_v1` / `branch2_v1` | ✅ có | dùng lại, không train lại |
| Model `branch3_v2` (metadata.json) | ✅ có | SessionCorrelator = thresholds, không có weights riêng |
| `data/processed/branch1_train.csv` | ✅ có | dùng cho query_splitting fragments |
| `data/raw/branch3_sessions/*` | ✅ có | đối chiếu audit |
| **`data/processed/branch3_sessions_cach_a.csv`** | ❌ **thiếu** | **xin Duc / HF** — input bắt buộc cho audit Day 1 |
| 363 template stacked → 727 | ❌ cần hỏi Duc | cho CL leakage check |
| Docker + DVWA/WebGoat + sqlmap + mitmproxy | ❌ chưa có | tự setup Day 2 |

---

## Lưu ý (từ data_contract.md / AGENTS.md)
- Branch 3 hiện là `SessionCorrelator` (content check OR behavior check), KHÔNG train gradient — đừng dùng `model.pt` (GRU cũ đã superseded).
- Không hardcode → thêm tham số vào `configs/config.yaml`.
- Không dùng `print` → dùng `from src.utils import get_logger`.
- Môi trường: `uv` + Python 3.12, chạy `uv sync --extra gbm --extra transformer --extra dev` nếu cần.