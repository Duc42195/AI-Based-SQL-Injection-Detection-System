# GitHub Copilot instructions

**Nguồn hướng dẫn đầy đủ nằm ở [`AGENTS.md`](../AGENTS.md) ở gốc repo — hãy đọc file đó trước khi sinh/sửa code.**

Tóm tắt các quy tắc bắt buộc (chi tiết trong AGENTS.md):

- Không commit thẳng lên `main`; làm trên nhánh `feature/...`, merge qua PR. `main` luôn phải xanh.
- Không hardcode path/ngưỡng/timeout — đọc từ `configs/config.yaml` qua `src.utils.load_config`.
- Không dùng `print` trong code; dùng `from src.utils import get_logger`.
- Không commit dữ liệu/model lớn (`data/`, `models/*.pkl|*.pt` đã bị `.gitignore`).
- Không tự cài lib nặng (torch/transformers/...) hay đổi `pyproject.toml`/`uv.lock` khi chưa được duyệt.
- Dùng `uv` để quản môi trường; chạy `uv run pytest` phải xanh trước khi commit.
- Mọi hàm/class public: type hints + docstring.
