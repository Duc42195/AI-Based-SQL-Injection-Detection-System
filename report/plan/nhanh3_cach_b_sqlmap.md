# Plan B — sqlmap + Docker lab (Cách B)

> Mục tiêu: thu thập session data thật từ sqlmap tấn công web app trong Docker.

## 1. Tổng quan

```
sqlmap → HTTP request → vulnerable web app (Docker) → SQL → DBMS (MySQL)
                           │
                           └── capture traffic → extract SQL → session sequences
```

## 2. Các bước

### Bước 1: Docker compose — vulnerable web app

Chọn 1 trong các image:

| Image | DB | Loại SQLi | Độ khó setup |
|-------|----|-----------|-------------|
| `vulnerables/web-dvwa` | MySQL | boolean + union + error | Dễ — port 80 |
| `webgoat/goatandwolf` | HSQLDB | đa dạng | Trung bình — nhiều lesson |
| `bkimminich/juice-shop` | SQLite | hiện đại | Dễ — nhưng khác SQL syntax |

Cần:
- `docker/docker-compose.yml` (file mới)
- Network config để sqlmap container (hoặc host) reach được web app

### Bước 2: Chạy sqlmap, capture traffic

Tùy chọn capture:
- **mitmproxy** — chạy proxy, sqlmap qua `--proxy=http://127.0.0.1:8080`, ghi .har
- **sqlmap --file-write** — sqlmap tự log request/response
- **Web app log** — web app tự ghi SQL query vào file

Sqlmap command mẫu:
```bash
sqlmap -u "http://localhost:80/vulnerabilities/sqli/?id=1&Submit=Submit" \
  --cookie="security=low; PHPSESSID=..." \
  --batch \
  --technique=BT \
  --level=3 \
  --flush-session
```

### Bước 3: Parse HTTP → SQL queries

Từ HTTP request cần extract:
- Request URL + POST body → URL decode → SQL injection payload
- Thời gian gửi (timestamp) → gap_seconds
- Response time → time-blind oracle

Khó khăn: sqlmap gửi thêm health check, retry, thread pool → cần heuristic để lọc.

### Bước 4: Ghép session sequences

- Mỗi lần sqlmap extract được 1 ký tự → 1 session
- Cần ground truth (password thật của user trong DB) để gán label
- Nếu dùng DVWA: login trước, đọc table `users` để biết password hash → ground truth

### Bước 5: Chạy B1 + B2 → GRU

Giống pipeline Cách A:
- Mỗi SQL query → Branch 1 (TF-IDF + LogReg) → 5 probabilities
- Mỗi SQL query → Branch 2 (OCSVM) → anomaly score
- Ghép 7-dim feature vector → GRU predict

## 3. Effort

| Task | Thời gian | Chi tiết |
|------|-----------|---------|
| Docker compose + setup DVWA | 2-3h | Image pull, config MySQL, login cookie |
| Chạy sqlmap + capture | 1-2h | Tuning technique, thu thập ~100 sessions |
| Parse HTTP → SQL sequences | 4-6h | Phần khó nhất — lọc noise, ghép session |
| Ground truth labeling | 1h | So sánh kết quả sqlmap với hash trong DB |
| Build dataset → train GRU | 1h | Code tương tự Cách A |
| **Tổng** | **~10-14h (2-3 ngày)** | **Không tính waiting time** |

## 4. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|--------|-----|-----------|
| DVWA MySQL khác SQLite syntax → B1/B2 không đánh giá đúng | Cao | Thêm DVWA SQL vào training data của B1? |
| Không extract được ground truth (password hash) | Trung bình | Dùng `--dbs` + `--tables` + `--dump` của sqlmap |
| sqlmap traffic quá nhiễu (retry, thread) | Cao | Chạy single-thread (`--threads=1`), parse heuristic |
| Phải login được DVWA (cookie, token) | Thấp | Dùng requests session + sqlmap `--cookie` |
| Cách B data vẫn cho F1=1.0 | Cao | DVWA boolean-blind cũng deterministic → có thể lại memorization trap |

## 5. Output

- `docker/docker-compose.yml` — infrastructure code
- `train/capture_sqlmap_sessions.py` — script run sqlmap + parse traffic
- Dataset CSV (~100-200 sessions từ sqlmap)
- So sánh Cách A vs Cách B: F1, ablation khác nhau không?

## 6. Note quan trọng

- Cách B **không guarantee** giải quyết được memorization trap — sqlmap cũng chạy bisection deterministic trên 1 target, có thể cho pattern giống hệt Cách A
- Giá trị thực sự của Cách B là HTTP-level realism — deployment validation, không phải model generalization
- Nếu muốn attack memorization, Plan A (pool mở rộng + noise) hiệu quả hơn với ~1/10 effort
