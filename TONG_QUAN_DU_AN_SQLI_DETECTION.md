# BÁO CÁO ĐỌC HIỂU & TỔNG QUAN TOÀN BỘ DỰ ÁN AI-BASED SQL INJECTION DETECTION SYSTEM

> **Ngày tổng hợp:** 23/07/2026  
> **Dự án:** AI-Based SQL Injection Detection System  
> **Repository:** [AI-Based-SQL-Injection-Detection-System](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System)  
> **Môi trường & Công cụ:** Python 3.12, `uv` package manager, PyTest, Scikit-learn, Hugging Face Hub.

---

## 1. TỔNG QUAN DỰ ÁN & BỐI CẢNH (EXECUTIVE SUMMARY)

### 1.1 Mục tiêu Đề tài
Dự án nhằm xây dựng một **Hệ thống phát hiện SQL Injection (SQLi) thông minh dựa trên AI**, đóng vai trò như một **Database Proxy (Vị trí B)** — đứng sau khi Web Backend tạo xong câu lệnh SQL và trước khi gửi tới Database Server. 

Khác với các WAF truyền thống dựa trên luật tĩnh (Signature/Regex Rules) dễ bị qua mặt bằng các kỹ thuật né tránh (Evasion/Obfuscation) hoặc gây ra tỷ lệ cảnh báo giả cao (High False Positives), hệ thống này kết hợp **học máy có giám sát (Supervised Learning)**, **phát hiện bất thường không giám sát (Unsupervised Anomaly Detection)** và **mô hình chuỗi theo phiên làm việc (Session-level Sequence Model)**.

```
[User Request] ──> [Web Backend] ──> [Database Proxy / AI Agent (Vị trí B)] ──> [Database]
                                                    │
                                        (Canonicalization & Phân tích)
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            ▼                       ▼                       ▼
                      [Nhánh 1: SQLi]        [Nhánh 2: Anomaly]      [Nhánh 3: Session]
                      (Per-query ML)         (Per-query Unsupervised) (Multi-query Sequence)
                            │                       │                       │
                            └───────────────────────┴───────────────────────┘
                                             ▼
                                  [Bộ Xử Lý Trung Tâm]
                        - Nhánh 1 = Attack           ──> BLOCK & Log
                        - Nhánh 1 sạch + Anomaly=1   ──> OVERKILL (Hold cho Admin / Deny Timeout)
                        - Nhánh 1+2 sạch + Session=1 ──> HOLD Session (Overkill mở rộng)
                        - Tất cả sạch                ──> ALLOW
```

### 1.2 Mốc Thời Gian Khẩn Cấp & Phạm Vi Thực Nghiệm (Cập nhật 21/07/2026)
* **Thứ 7, 25/07/2026 (Hạn nộp báo cáo đồ án):**
  * **Scope thực nghiệm (Đã hoàn tất 100%):** Hoàn thiện và đánh giá đầy đủ **Nhánh 1 (Supervised Multi-class)** và **Nhánh 2 (Anomaly Detection)** trên dữ liệu thực tế + **Notebook demo tương tác** ([demo_detect.ipynb](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/notebooks/demo_detect.ipynb)).
  * **Hai bản báo cáo song song:**
    1. [report/ban1_scope_hien_tai.md](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/report/ban1_scope_hien_tai.md): Báo cáo tập trung đúng phạm vi thực nghiệm đã làm (Nhánh 1 + Nhánh 2 + Demo Notebook).
    2. [report/ban2_hoan_chinh.md](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/report/ban2_hoan_chinh.md): Tầm nhìn kiến trúc đầy đủ 3 nhánh + MLOps-lite (Nhánh 3 và API Server được ghi nhận dưới dạng thiết kế / Future Work).
* **31/07/2026 (Hội nghị RIVF 2026):** Hạn nộp bài báo khoa học 6 trang (IEEE format).

---

## 2. KIẾN TRÚC HỆ THỐNG 3 NHÁNH (3-BRANCH ARCHITECTURE)

### 2.1 Nhánh 1 — Phân loại Đa lớp (Supervised Multi-Class Classification)
* **Nhiệm vụ:** Đánh giá từng truy vấn đơn lẻ (`per-query`), phân loại vào 6 nhãn: `Normal (0)`, `Union-based (1)`, `Error-based (2)`, `Boolean-blind (3)`, `Time-blind (4)`, `Stacked (5)`.
* **Kết quả So sánh 4 Kiến trúc (Thực hiện ngày 16/07/2026):**

| Kiến trúc | F1-Macro | Latency p50 | Dung lượng Model | Thời gian Train | Đánh giá & Lý do lựa chọn |
|---|:---:|:---:|:---:|:---:|---|
| **TF-IDF + Logistic Regression** *(CHỌN)* | **0.9822** | **0.5 ms** | **3.9 MB** | **~10 s** | **Tối ưu nhất** về trade-off Latency/Accuracy/Size cho proxy real-time. |
| **TF-IDF + LightGBM** | 0.9930 | ~60.0 ms | 6.0 MB | 264 s | F1 cao nhất nhưng Latency 60ms quá chậm cho Database Proxy. |
| **DistilBERT** | 0.9920 | 2.8 ms (GPU) | 256.0 MB | 1443 s | Tốn tài nguyên GPU, không cải thiện F1 đáng kể so với TF-IDF. |
| **CNN + SQL Tokenizer** | 0.9870 | 0.3 ms | 116 KB | 10 s | Ứng viên dự phòng siêu nhẹ (28K params) cho nhúng/edge. |

* **Lưu ý kỹ thuật quan trọng:**
  * Lớp `Stacked` query (363 mẫu synthetic từ [synthetic_stacked.py](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/src/preprocessing/synthetic_stacked.py)) bị tạm thời loại khỏi dataset huấn luyện chính (`exclude_labels: [5]`) vì dữ liệu tự tạo quá dễ phân biệt (đạt 100% Recall trên mọi model), tránh gây lạm phát giả F1-macro.
  * Model chính thức `nhanh1_v1` được đóng gói tại `models/nhanh1_v1/` (`model.joblib`, `vectorizer.joblib`, `metadata.json`).

### 2.2 Nhánh 2 — Phát hiện Bất thường (Unsupervised Anomaly Detection)
* **Nhiệm vụ:** Học "vùng an toàn" (Benign Profile) **chỉ từ 100% traffic bình thường**, xuất ra điểm bất thường liên tục (Continuous Anomaly Score) để bắt các cuộc tấn công Zero-day hoặc cú pháp lạ.
* **Kết quả Đánh giá & Kiểm toán (Training Audit 16/07/2026):**
  * So sánh **Isolation Forest (IF)** vs **One-Class SVM (OCSVM)**.
  * **Thuật toán được chọn:** **One-Class SVM (nu=0.005, gamma=0.01)** đạt **AUC = 0.887 / 0.90**, **FPR = 0.4%**, **Detection Rate = 19.98%**.
  * **4 Phát hiện Audit Quan trọng (xem [reports/nhanh2_training_audit.md](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/reports/nhanh2_training_audit.md)):**
    1. *Không dùng `StandardScaler`:* Việc chuẩn hóa tất cả đặc trưng làm giảm AUC từ 0.805 xuống 0.533 do làm pha loãng đặc trưng độ dài (`length` chiếm ~80% sức mạnh phân biệt).
    2. *`log1p` Transform cho Length:* Áp dụng `np.log1p` lên đặc trưng `length` để nén các outlier cực trị (độ dài max 5,370 vs mean 47).
    3. *Tách biệt Contamination Param:* IF dùng `contamination=0.01`, OCSVM dùng `ocsvm_nu=0.005`.
    4. *Bộ 4 đặc trưng cấu trúc:* `length`, `special_char_ratio`, `sql_keyword_count`, `entropy` (được trích xuất tại [statistical_features.py](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/src/preprocessing/statistical_features.py)).

### 2.3 Nhánh 3 — Phân tích Phiên Làm Việc (Session-Level Sequence Model — Thiết Kế)
* **Nhiệm vụ:** Xâu chuỗi K câu lệnh SQL gần nhất trong cùng Session ID hoặc IP Client trong một cửa sổ thời gian (Window).
* **Đầu vào từng bước:** Vector ghép `[Content Embedding (từ Nhánh 1) ⊕ Anomaly Score (từ Nhánh 2)]`.
* **Mục tiêu:** Bắt các kỹ thuật **Boolean/Time-based Blind SQLi** và **Temporal Query-Splitting** (khi từng truy vấn đơn lẻ hoàn toàn hợp lệ, nhưng trình tự truy vấn bộc lộ hành vi dò quét/trích xuất dữ liệu).

### 2.4 Cơ chế Ra Quyết Định (Decision Logic & Overkill Policy)

Ma trận kết hợp 2 nhánh (đang áp dụng trong Demo):

| Nhánh 1 (Supervised) | Nhánh 2 (Anomaly) | Verdict | Hành Động |
|:---:|:---:|:---:|:---|
| Attack (1-5) | Any | **BLOCK** | Ngăn chặn truy vấn ngay lập tức, ghi log cảnh báo. |
| Normal (0) | Anomaly (1) | **OVERKILL** | Tạm dừng thực thi, đưa vào hàng đợi SQLite Queue chờ Admin xác minh. Sau `overkill_timeout_seconds` (300s) không duyệt -> **Deny-by-default**. |
| Normal (0) | Normal (0) | **ALLOW** | Chấp nhận và cho phép truy vấn tới Database Server. |

---

## 3. QUY TRÌNH TIỀN XỬ LÝ & DỮ LIỆU (DATA ENGINEERING PIPELINE)

### 3.1 Nguồn Dữ Liệu Công Khai (Datasets D1 – D7)
* **D1 (SQLiV3):** ~30.9K câu lệnh SQL (Normal + SQLi).
* **D3 (CSIC 2010):** 97.065 HTTP requests thô (72k Normal, 25k Anomalous).
* **D4 (payload-box):** 177 payload SQLi phân theo DBMS.
* **D7 (SR-BH 2020 - Harvard Dataverse):** Honeypot thật với 527.813 dòng, gắn đa nhãn CAPEC (cung cấp 250k SQLi, 152k Normal).

> 📦 **Lưu trữ Remote trên Hugging Face:**  
> Toàn bộ data và model binary được lưu trên HF Hub (không commit file lớn vào git):  
> - Dataset: [Jason-42195/VNU-SQLi-Detection](https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection)  
> - Models: [Jason-42195/VNU-SQLi-Detection-Models](https://huggingface.co/Jason-42195/VNU-SQLi-Detection-Models)

### 3.2 Pipeline Canonicalization (Chống Né Tránh / Evasion)
Mọi câu lệnh trước khi đưa vào mô hình đều trải qua pipeline chuẩn hóa tại [canonicalize.py](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/src/preprocessing/canonicalize.py):
1. **Iterative URL-Decoding:** Giải mã URL lặp (tối đa 3 lượt) xử lý URL encoding lồng nhau.
2. **Hex Literal Decoding:** Chuyển đổi các chuỗi Hex (`0x4142...`) về dạng ASCII hiển thị.
3. **`CHAR()` Function Decoding:** Giải mã các hàm `CHAR(65, 66, ...)` về chuỗi ký tự tương ứng.
4. **Preserve Comment Marker:** Phát hiện comment `/* */` và `--` nhưng **KHÔNG xóa comment** mà gắn cờ `has_comment_marker = 1` (giữ lại feature để nhận diện kỹ thuật né tránh qua comment insertion).
5. **Lowercasing:** Chuyển toàn bộ về chữ thường.

### 3.3 Multiclass Tagging & Lọc Nhiễu Nhãn (Label Cleaning Audit)
* **Quy trình Tagging:** [multiclass_tagger.py](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/src/preprocessing/multiclass_tagger.py) áp dụng tập Regex quy chuẩn để phân loại các dạng tấn công SQLi.
* **Sửa lỗi Nhiễu Nhãn Nguồn SR-BH 2020:**  
  Qua kiểm tra thủ công (Sanity-check), phát hiện 2.731 dòng trong SR-BH 2020 mang nhãn gốc `Normal=1` thực chất chứa payload tấn công Shellshock (`() { :; }; /bin/sleep 15`), OS Command Injection (`cat /etc/passwd`), và SSI Injection.  
  -> Đã xây dựng hàm `matches_any_attack_signature()` để lọc sạch 2.731 dòng nhiễu này khỏi tập huấn luyện `Normal`.
* **Dataset Huấn luyện Cuối cùng (`nhanh1_train.csv`):** 68.159 dòng (Stratified split: 54.527 train / 13.632 test).

---

## 4. BẢN NỒ DỰ ÁN & CẤU TRÚC CODEBASE (CODEBASE MAP)

```
AI-Based-SQL-Injection-Detection-System/
├── configs/
│   └── config.yaml               # Cấu hình trung tâm (Thresholds, Paths, Model options)
├── src/
│   ├── preprocessing/            # Tiền xử lý dữ liệu
│   │   ├── canonicalize.py       # URL/Hex/CHAR decoding, comment detection
│   │   ├── multiclass_tagger.py  # Tagging regex 5 lớp SQLi & rule lọc nhiễu
│   │   ├── statistical_features.py # Trích xuất 4 đặc trưng cấu trúc cho Nhánh 2
│   │   ├── synthetic_stacked.py  # Generator dữ liệu synthetic cho Stacked queries
│   │   └── data_sources.py       # Data loaders cho D1, D3, D4, D7
│   ├── models/
│   │   └── nhanh2_anomaly.py     # Class wrapper AnomalyDetector (IF / OCSVM)
│   ├── decision/                 # Overkill Queue logic (SQLite backend)
│   ├── continual_learning/       # Pipeline Rehearsal & Validation Gate (MLOps-lite)
│   ├── monitoring/               # Drift monitoring (PSI/KL divergence)
│   └── utils/
│       ├── config.py             # ConfigLoader (Hỗ trợ override qua ENV SQLIDS_*)
│       └── logging_setup.py      # Logger chuẩn không dùng print
├── scripts/                      # CLI Scripts huấn luyện & xử lý dữ liệu
│   ├── build_nhanh1_dataset.py   # Pipeline build dataset Nhánh 1 từ raw D1/D4/D7
│   ├── build_nhanh2_dataset.py   # Pipeline build dataset Nhánh 2 từ benign pool
│   ├── compare_nhanh1_architectures.py # Script benchmark 4 kiến trúc Nhánh 1
│   ├── train_nhanh1.py           # Train & export model Nhánh 1 (tfidf_logreg)
│   ├── train_nhanh2.py           # Train & export model Nhánh 2 (ocsvm tuned)
│   ├── generate_metrics.py       # Sinh báo cáo JSON & biểu đồ kết quả
│   └── download_hf_dataset.py    # Script tải dataset từ Hugging Face
├── notebooks/                    # Thực nghiệm Jupyter Notebooks
│   ├── demo_detect.ipynb         # Interactive Notebook demo nhận diện SQLi & Anomaly
│   ├── model_comparison_nhanh1.ipynb # Notebook phân tích so sánh 4 mô hình Nhánh 1
│   └── nhanh2_eval.ipynb         # Notebook đánh giá ROC curve & audit Nhánh 2
├── reports/                      # Artifacts kết quả & báo cáo json/md
│   ├── nhanh1_architecture_comparison.json
│   ├── nhanh1_eval.json
│   ├── nhanh2_eval.json
│   └── nhanh2_training_audit.md  # Chi tiết audit 4 vấn đề của Nhánh 2
├── report/                       # Báo cáo nộp đồ án
│   ├── ban1_scope_hien_tai.md    # Bản báo cáo 2 nhánh thực nghiệm
│   └── ban2_hoan_chinh.md        # Bản báo cáo tầm nhìn 3 nhánh đầy đủ
├── tests/                        # Bộ kiểm thử PyTest (47 tests passed)
│   ├── test_canonicalize.py
│   ├── test_config.py
│   ├── test_multiclass_tagger.py
│   ├── test_nhanh2_anomaly.py
│   ├── test_statistical_features.py
│   └── test_synthetic_stacked.py
├── AGENTS.md                     # Hướng dẫn dành cho AI & Coder
├── data_contract.md              # Quy chuẩn Schema & Data specification
├── pyproject.toml                # Khai báo dependency với uv
└── main.py                       # Health check entrypoint
```

---

## 5. HƯỚNG DẪN DÀNH CHO LẬP TRÌNH VIÊN (DEVELOPER GUIDE)

### 5.1 Cài Đặt Môi Trường
Dự án sử dụng `uv` quản lý môi trường ảo Python 3.12:

```bash
# 1. Cài đặt các gói core + dev (PyTest, Scikit-learn)
uv sync --extra dev

# 2. (Tùy chọn) Cài đặt bổ sung gói GBM nếu cần chạy XGBoost/LightGBM
uv sync --extra gbm --extra dev

# 3. (Tùy chọn) Cài đặt bổ sung PyTorch/Transformers nếu chạy DistilBERT
uv sync --extra transformer --extra inference
```

### 5.2 Kiểm Thử (Testing)
Chạy PyTest để xác nhận toàn bộ hệ thống hoạt động chính xác (Bắt buộc green trước mọi commit):

```bash
uv run pytest
```
*Kết quả hiện tại:* **47 passed** (100% pass rate).

### 5.3 Chạy Tải Model & Demo
Tải pretrained model weights từ Hugging Face và khởi chạy Notebook demo:

```bash
# Tải model weights về thư mục models/
uv run python -c "from huggingface_hub import snapshot_download; snapshot_download('Jason-42195/VNU-SQLi-Detection-Models', local_dir='models')"

# Chạy main.py health check
uv run python main.py
```

Mở notebook [notebooks/demo_detect.ipynb](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/notebooks/demo_detect.ipynb) để trải nghiệm việc đưa một câu SQL ngẫu nhiên qua Canonicalization -> Nhánh 1 -> Nhánh 2 -> Verdict (ALLOW / BLOCK / OVERKILL).

---

## 6. QUY TẮC PHÁT TRIỂN & ĐÓNG GÓP (PROJECT RULES SUMMARY)

Theo hướng dẫn tại [AGENTS.md](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/AGENTS.md):
1. **Tuyệt đối KHÔNG commit trực tiếp lên `main`:** Mọi tính năng thực hiện trên nhánh `feature/...` và merge qua Pull Request.
2. **KHÔNG Hardcode:** Mọi ngưỡng, đường dẫn, timeout đọc từ [configs/config.yaml](file:///C:/Users/minhq/Documents/GitHub/AI-Based-SQL-Injection-Detection-System/configs/config.yaml) thông qua `src.utils.load_config`.
3. **Logging thay cho `print`:** Sử dụng `from src.utils import get_logger`.
4. **Không commit file dữ liệu/model lớn:** Dữ liệu và weights lưu trên Hugging Face.
5. **Chạy `uv run pytest`:** Đảm bảo test xanh trước khi thực hiện bất kỳ commit hay pull request nào.

---
*Bản báo cáo đọc hiểu này cung cấp bức tranh toàn cảnh và chi tiết kỹ thuật minh bạch cho toàn bộ codebase của hệ thống phát hiện SQL Injection dựa trên AI.*
