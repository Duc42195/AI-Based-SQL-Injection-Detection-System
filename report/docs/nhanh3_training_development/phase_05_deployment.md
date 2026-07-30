# Phase 5: Deployment

> **Master plan**: [plan.md](plan.md)
>
> **Context**: [branch3_context.md](branch3_context.md)
>
> **Phụ thuộc**: Phase 4 pass (hard eval confirms B3 signal)

**Mục tiêu**: Wire B3 vào FastAPI deploy pipeline — router, registry, schemas,
config, integration test.

---

## Các bước

### 5.1 Tạo `deploy/routers/branch3.py`

```python
router = APIRouter(prefix="/branch3", tags=["branch3"])

@router.post("/session", response_model=Branch3Response)
def classify_session(request: SessionRequest) -> Branch3Response:
    """Classify a session (list of queries)."""
    # 1. Canonicalize + score từng query qua B1, B2
    # 2. Build feature matrix (n_steps x 7)
    # 3. Predict với B3 model
    # 4. Return label + is_attack + confidence
```

**Response shape** (giữ nguyên contract cũ cho frontend):

```python
class Branch3Response(BaseModel):
    status: BranchStatus
    session_label: str | None = None
    is_attack: bool | None = None
    confidence: float | None = None
```

### 5.2 Sửa `deploy/schemas.py`

- [ ] Thêm lại `Branch3Response` (đã xóa trước đó)
- [ ] Thêm lại `SessionRequest`
- [ ] Thêm `branch3: Branch3Response | None` vào `DetectResponse`
- [ ] Thêm `branch3: Branch3Response | None` vào `DemoExecuteResponse`

### 5.3 Sửa `deploy/registry.py`

- [ ] Load B3 model từ `models/branch3_v2/` theo `active_version` trong config
- [ ] Trả về `status: "ready"` nếu model tồn tại, `"not_ready"` nếu không

### 5.4 Sửa `deploy/main.py`

- [ ] Import `branch3` router
- [ ] `app.include_router(branch3.router, prefix=prefix)`

### 5.5 Sửa `deploy/routers/detect.py`

- [ ] Import `run_branch3`
- [ ] Cập nhật `fuse_decision(b1, b2, b3)` — B3 escalation:
      ```
      if b3.status == "ready" and b3.is_attack:
          → BLOCK (session-level)
      elif b1.is_sqli:
          → BLOCK
      elif b2.is_anomaly:
          → OVERKILL
      else:
          → ALLOW
      ```
- [ ] Trả về `branch3` trong `DetectResponse`

### 5.6 Sửa `deploy/routers/demo.py`

- [ ] Import `run_branch3`
- [ ] Nếu `protected=True` và nhiều hơn 1 step, chạy B3
- [ ] Trả về `branch3` trong `DemoExecuteResponse`

### 5.7 Sửa `deploy/routers/data.py`

- [ ] Thêm `branch3` annotation pool (nếu cần)

### 5.8 Sửa `deploy/tasks.py`

- [ ] Thêm `branch3` vào `VALID_TASKS`
- [ ] Thêm `branch3` vào `label_options`

### 5.9 Sửa `app/` (Streamlit frontend)

- [ ] `app/ui.py`: thêm `branch3` vào `TASKS`, `render_branch3`
- [ ] `app/streamlit_app.py`: render B3 khi có kết quả
- [ ] `app/api_client.py`: thêm `branch3_session`
- [ ] `app/state.py`: thêm `branch3` vào type hint

### 5.10 Integration test

- [ ] `tests/test_api.py`:
      - `test_branch3_session_ready` — POST `/api/v1/branch3/session`
      - `test_detect_returns_all_branches` — verify `branch3` in response
      - `test_detect_b3_escalates` — B1 normal + B3 attack → BLOCK

### 5.11 Chạy full test suite

- [ ] `uv run pytest -q`

---

## Đầu ra

| File | Mô tả |
|------|-------|
| `deploy/routers/branch3.py` | B3 FastAPI router |
| `deploy/schemas.py` (sửa) | Thêm `Branch3Response`, `SessionRequest` |
| `deploy/registry.py` (sửa) | Load B3 model |
| `deploy/main.py` (sửa) | Register B3 router |
| `deploy/routers/detect.py` (sửa) | `fuse_decision` includes B3 |
| `deploy/routers/demo.py` (sửa) | B3 in demo protected mode |
| `deploy/routers/data.py` (sửa) | B3 annotation pool |
| `deploy/tasks.py` (sửa) | `VALID_TASKS` includes B3 |
| `app/ui.py` (sửa) | `render_branch3` |
| `app/streamlit_app.py` (sửa) | B3 display |
| `app/api_client.py` (sửa) | `branch3_session` |
| `tests/test_api.py` (sửa) | B3 integration tests |

## Verification checklist

- [ ] `uv run pytest -q` green (full suite)
- [ ] POST `/api/v1/branch3/session` returns `{"status": "ready", ...}`
- [ ] POST `/api/v1/detect` returns `branch3` in response
- [ ] B1 normal + B3 attack → decision `BLOCK` (escalation)
- [ ] B1 attack → decision `BLOCK` (B1 precedence)
- [ ] B3 not ready → decision phải degrade gracefully

## Final step

→ [Plan tổng thể](plan.md) — đánh dấu Phase 5 complete
