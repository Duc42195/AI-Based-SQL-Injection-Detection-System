# AGENTS.md — Hướng dẫn cho AI & người mới

> File này là **nguồn hướng dẫn chung** cho mọi trợ lý AI (Copilot, Cursor, Claude, Codex, Aider...) và cho lập trình viên mới clone repo. **Đọc hết file này trước khi sửa code.** Mục tiêu: đóng góp đúng chuẩn và **không phá vỡ project**.

---

## ⛔ Quy tắc TỐI QUAN TRỌNG (đọc trước)

1. **KHÔNG commit thẳng lên `main`.** Mỗi thay đổi làm trên nhánh riêng (`feature/...`), merge qua PR. `main` luôn phải chạy được (tests pass).
2. **KHÔNG hardcode** đường dẫn / ngưỡng / timeout. Mọi thứ nằm ở [`configs/config.yaml`](configs/config.yaml), đọc qua `src.utils.load_config`.
3. **KHÔNG dùng `print`** trong code `src/`, `api/`, `scripts/`. Dùng logging: `from src.utils import get_logger`.
4. **KHÔNG commit dữ liệu / model lớn.** `data/` và `models/*.pkl|*.pt|...` đã bị `.gitignore`. Chỉ commit code + config + `.gitkeep`.
5. **KHÔNG tự cài thư viện nặng** (torch, transformers, ctranslate2...) hay đổi phiên bản trong `pyproject.toml` mà chưa hỏi chủ repo. Xem mục [Dependencies](#dependencies).
6. **KHÔNG sửa schema** trong `config.yaml` (đổi tên/xoá key) mà không cập nhật nơi dùng nó — sẽ vỡ chỗ khác.
7. **Chạy `uv run pytest` trước khi commit.** Đỏ test = không commit.

---

## Bối cảnh dự án

Hệ thống phát hiện **SQL Injection** dựa trên AI, đặt tại Database Proxy. Kiến trúc **3 nhánh** (chi tiết ở [README.md](README.md)):
- **Nhánh 1** — Supervised đa lớp (Normal + các loại SQLi).
- **Nhánh 2** — Anomaly detection (train chỉ trên benign).
- **Nhánh 3** — Session-level sequence model (đóng góp chính).

Deadline gấp (14 ngày) → **ưu tiên MVP chạy end-to-end**, không cầu toàn từng phần.

---

## Setup môi trường

Dự án dùng [`uv`](https://docs.astral.sh/uv/) (không dùng pip/venv thủ công). Python **3.12**.

```bash
uv sync --extra dev                              # stack lõi + pytest
uv sync --extra gbm --extra transformer --extra dev   # thêm XGBoost/LightGBM + torch/transformers
```
- Có **GPU NVIDIA** → torch tự dùng CUDA. Không có GPU vẫn chạy được (chậm hơn).
- **Không tự chạy `pip install`** ngoài `uv`.

## Chạy & test

```bash
uv run python main.py    # health check: load config + log banner
uv run pytest            # chạy toàn bộ test (phải xanh trước khi commit)
uv run pytest tests/test_config.py -q   # chạy 1 file
```

---

## Cấu trúc thư mục (đừng đặt file sai chỗ)

```
configs/config.yaml      # TẤT CẢ tham số cấu hình
src/preprocessing/       # canonicalization + tokenization
src/models/              # Nhánh 1 / 2 / 3
src/decision/            # decision logic + hàng đợi Overkill
src/continual_learning/  # gán nhãn, retrain, validation gate
src/monitoring/          # drift, versioning, rollback
src/utils/               # config loader + logging (DÙNG LẠI, đừng viết mới)
api/                     # FastAPI service
tests/                   # pytest — mỗi module 1 file test_*.py
scripts/                 # CLI: retrain, benchmark, check_drift
notebooks/               # thực nghiệm (prefix nhánh: exp/...)
data/  models/           # KHÔNG commit nội dung (chỉ .gitkeep)
```

---

## Coding conventions

- **Type hints + docstring** cho mọi hàm/class public.
- Import config: `from src.utils import load_config; cfg = load_config()`; đọc bằng `cfg.get_path("section.key")`.
- Import logger: `from src.utils import get_logger; logger = get_logger(__name__)`.
- Bước tốn thời gian (train/retrain/benchmark) → **log tiến trình rõ ràng**.
- Viết **pytest** cho logic mới; bắt buộc cho: canonicalization, decision logic, validation gate.
- Thêm tham số mới → **thêm vào `config.yaml`**, không hardcode. Có thể override khi chạy bằng biến môi trường `SQLIDS_<SECTION>_<KEY>`.

---

## Git workflow (trunk-based nhẹ)

1. `git switch main && git pull`
2. `git switch -c feature/<tên-phase>` (vd. `feature/branch2-anomaly`)
3. Code, commit nhiều lần nhỏ; commit message rõ nghĩa (tiếng Việt hoặc Anh đều được).
4. `git push -u origin feature/<tên-phase>`
5. Mở **PR trên GitHub** → review → **Squash and merge** → xoá nhánh.
6. Prefix nhánh: `feature/` (tính năng), `fix/` (sửa lỗi), `exp/` (notebook thử nghiệm có thể bỏ).

**Không** merge khi test đỏ. **Không** force-push lên `main`.

---

## Dependencies

- Thêm lib **nhẹ** (sklearn utils, tiện ích nhỏ) → thêm vào `[project.dependencies]` trong `pyproject.toml` + `uv sync`, ghi rõ lý do trong PR.
- Thêm lib **nặng** (torch, transformers, ctranslate2, model weights lớn) → **hỏi chủ repo trước**. Đặt vào `[project.optional-dependencies]` (nhóm `transformer`/`inference`), không nhét vào core.
- Commit `uv.lock` cùng thay đổi dependency để tái lập được môi trường.

---

## Dữ liệu

- Dataset là **public** (xem bảng D1–D6 trong [README.md](README.md)); **không commit** file dữ liệu vào repo.
- Chưa có dữ liệu thật cho phần nào → dùng public tạm, **ghi rõ nguồn** và đánh dấu `TODO` để thay sau.

## Model đã train

- **Không tự retrain nếu không cần** — model thật (`nhanh1_v1`, `nhanh2_v1`) đã có sẵn trên HF: `hf download Jason-42195/VNU-SQLi-Detection-Models --local-dir models/`. Xem README.md mục "Model đã train — tải ở đâu".
- Nếu retrain (vd. sửa code training), **nhớ push bản mới lên HF** (`hf upload Jason-42195/VNU-SQLi-Detection-Models models/nhanh1_v1 nhanh1_v1 --repo-type model`) để cả nhóm dùng chung 1 bản, tránh mỗi người có model khác nhau.

---

## "Definition of done" cho một thay đổi

- [ ] Code có type hints + docstring, dùng logging (không `print`).
- [ ] Tham số mới đã đưa vào `config.yaml` (không hardcode).
- [ ] Có/cập nhật test tương ứng; `uv run pytest` xanh.
- [ ] Không commit file lớn (`git status` sạch phần `data/`, `models/`).
- [ ] Làm trên nhánh riêng, mở PR về `main`.
