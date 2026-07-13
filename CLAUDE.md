# CLAUDE.md

**Đọc [`AGENTS.md`](AGENTS.md) ở gốc repo — đó là nguồn hướng dẫn đầy đủ cho dự án này.** File này chỉ trỏ về đó để tránh trùng lặp (chỉ maintain một chỗ: `AGENTS.md`).

Nhắc nhanh các guardrail: không commit thẳng `main`; không hardcode config (dùng `src.utils.load_config`); không `print` (dùng `get_logger`); không commit `data/`·`models/` lớn; không tự cài lib nặng; `uv run pytest` phải xanh trước khi commit.
