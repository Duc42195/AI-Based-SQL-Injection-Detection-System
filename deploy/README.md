# API Backend — Hướng dẫn cho Streamlit (Minh)

> 📄 **Spec giao diện 4 trang (Test / Monitor / Data / Train) + hợp đồng API đầy đủ:**
> [`docs/streamlit_ui_spec.md`](../docs/streamlit_ui_spec.md). File dưới đây là phần
> lõi (health / detect / nhánh 1-3 / metrics / admin).

> Backend FastAPI cho hệ thống phát hiện SQLi. **Nhánh 1 chạy THẬT** ngay bây giờ;
> Nhánh 2/3 trả `status:"not_ready"` (HTTP 200, **không phải lỗi**) cho tới khi
> Bach/Toi train xong. **Hình dạng response giữ nguyên** → Minh dựng UI 1 lần,
> sau này model thật xong là tự có dữ liệu, **không phải sửa code**.

## 1. Chạy backend

```bash
# từ gốc repo
uv run uvicorn deploy.main:app --reload --port 8000
```

- Swagger UI (thử tay, xem schema): <http://localhost:8000/docs>
- Health check nhanh: `curl localhost:8000/health`

CORS đã mở (`api.cors_origins: ["*"]` trong `configs/config.yaml`) nên Streamlit
gọi từ port khác (mặc định 8501) không bị chặn.

## 2. Endpoint

| Method | Path | Body | Dùng cho trang Streamlit |
|---|---|---|---|
| GET  | `/health` | – | badge trạng thái 3 nhánh |
| POST | `/api/v1/detect` | `{"query": "..."}` | **trang test query + trang kết quả 3 nhánh** (gọi 1 lần, có verdict) |
| POST | `/api/v1/nhanh1/predict` | `{"query": "..."}` | debug riêng Nhánh 1 |
| POST | `/api/v1/nhanh2/score` | `{"query": "..."}` | (stub) Nhánh 2 |
| POST | `/api/v1/nhanh3/session` | `{"queries": ["...","..."]}` | (stub) Nhánh 3 |
| GET  | `/api/v1/metrics/nhanh1` | – | **trang Metrics** (P/R/F1) |
| GET  | `/api/v1/admin/overkill-queue` | – | **trang Admin** (hàng đợi — hiện rỗng) |
| POST | `/api/v1/admin/overkill/{id}/confirm` | – | nút Duyệt (stub) |
| POST | `/api/v1/admin/overkill/{id}/reject` | – | nút Từ chối (stub) |

> **Khuyến nghị:** dùng `POST /api/v1/detect` làm endpoint chính. Nó chạy cả 3 nhánh
> + áp ma trận quyết định và trả **1 verdict** (`BLOCK` / `OVERKILL` / `ALLOW` / `UNKNOWN`).

## 3. Hình dạng response

### `POST /api/v1/detect`

```json
{
  "query_canonical": "admin' or 1=1 union select password from users --",
  "nhanh1": {
    "status": "ready",
    "label_name": "boolean_blind",
    "is_sqli": true,
    "confidence": 0.48,           // xác suất lớp cao nhất
    "attack_probability": 0.97,   // = 1 - P(normal); is_sqli so với threshold cái này
    "threshold": 0.5,
    "probabilities": {"normal": 0.03, "union_based": 0.46, "boolean_blind": 0.48, ...}
  },
  "nhanh2": {"status": "not_ready", "anomaly_score": null, "is_anomaly": null},
  "nhanh3": {"status": "not_ready", "session_label": null, "is_attack": null},
  "decision": {"action": "BLOCK", "reason": "Branch-1 detected attack class 'boolean_blind' ..."}
}
```

**Lưu ý hiển thị:** cờ `is_sqli` dựa trên `attack_probability` (tổng xác suất các lớp
tấn công = `1 - P(normal)`), **không phải** `confidence`. Nên `confidence` có thể < `threshold`
mà `is_sqli` vẫn `true` (khi xác suất bị chia đều cho nhiều lớp tấn công). Hiển thị
`attack_probability` cạnh `threshold` cho rõ ràng.

`decision.action`:
- `BLOCK` — Nhánh 1 phát hiện lớp tấn công (hoặc Nhánh 3 báo session tấn công).
- `OVERKILL` — Nhánh 1 = Normal nhưng Nhánh 2 báo bất thường → chờ Admin (chỉ có khi Nhánh 2 sẵn sàng).
- `ALLOW` — bình thường.
- `UNKNOWN` — Nhánh 1 chưa load được.

### `GET /api/v1/metrics/nhanh1`

```json
{"status": "ready", "source": "report/metrics/nhanh1_eval.json", "metrics": { ...F1/precision/recall... }}
```
Nếu chưa có report → `{"status": "not_ready", "detail": "..."}`. UI nên check `status` trước.

## 4. Gọi từ Streamlit (mẫu)

```python
import requests

API = "http://localhost:8000"

def detect(query: str) -> dict:
    r = requests.post(f"{API}/api/v1/detect", json={"query": query}, timeout=10)
    r.raise_for_status()
    return r.json()

res = detect("admin' OR 1=1 --")
st.write("Hành động:", res["decision"]["action"])
st.write("Lý do:", res["decision"]["reason"])

n1 = res["nhanh1"]
if n1["status"] == "ready":
    st.metric("Loại", n1["label_name"])
    st.progress(n1["attack_probability"])
else:
    st.info("Nhánh 1 chưa sẵn sàng")

# Nhánh 2/3 — render placeholder khi not_ready, không cần sửa lại khi có model
for name in ("nhanh2", "nhanh3"):
    b = res[name]
    if b["status"] == "not_ready":
        st.caption(f"{name}: chưa train")
```

## 5. Quy ước cho backend dev (Toi/Bach)

- Mỗi nhánh 1 file router trong `deploy/routers/` (`nhanh2.py` → Bach, `nhanh3.py` → Toi).
- Khi model thật xong: load qua `deploy/registry.py` (thêm hàm giống `nhanh1`) và điền
  các field trong response — **đừng đổi tên/kiểu field** đã có (Minh phụ thuộc vào chúng).
- Chọn/rollback model bằng cách đổi `<branch>.active_version` trong `configs/config.yaml`
  (không hardcode đường dẫn model).
- `uv run pytest tests/test_api.py` phải xanh trước khi commit.
