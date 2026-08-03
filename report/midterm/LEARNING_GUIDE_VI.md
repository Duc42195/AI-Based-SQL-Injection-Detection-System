# Hướng Dẫn Học Tập Dự Án SQLi Detection — Từ Dễ Đến Khó

> Tài liệu này giúp bạn hiểu toàn bộ dự án từ nền tảng (concept cơ bản) đến chi tiết (thuật toán, kỹ thuật).

---

## **PHẦN 0: NỀN TẢNG (Foundation)**

### **0.1 Mô Hình Đe Dọa & Vị Trí Triển Khai**

#### **Database Proxy Placement (Vị Trí B)**

Hệ thống phát hiện SQLi được đặt **giữa backend application và database**, tại một layer gọi là "Database Proxy".

```
User HTTP Request
    ↓
Web Application (backend)
    ↓
[SQL Query Assembly]  ← Query được xây dựng từ user input
    ↓
>>> DATABASE PROXY (Vị Trí B) <<<  ← SQLi Detection xảy ra ở đây
    ├─ Branch 1: Supervised Classification
    ├─ Branch 2: Anomaly Detection
    └─ Decision Engine: ALLOW / BLOCK / HOLD
    ↓
Database Server
    ↓
Results → Web Application → User
```

**Lý do chọn Vị Trí B:**
- ✅ Được tất cả các query sau khi assembled (kết hợp user input + template)
- ✅ Không cần xem upstream (raw HTTP parameters, headers)
- ✅ Không cần xem downstream (result sets, out-of-band channels)
- ❌ Không thể ngăn **parameter pollution** trước khi query build
- ❌ Không thể phát hiện **out-of-band SQLi** (dữ liệu leak qua DNS/HTTP riêng)
- ❌ Không thể thấy **second-order attacks** (payload lưu ở một request, trigger ở request khác sau vài ngày)

#### **In-Scope Attacks (Phạm Vi Bao Phủ)**

| Attack Type | Ví Dụ | Có Thể Phát Hiện? |
| :---- | :---- | :---- |
| **Union-based SQLi** | `' UNION SELECT username, password FROM admin--` | ✅ Có |
| **Error-based SQLi** | `' AND 1=CONVERT(int, (SELECT @@version))--` | ✅ Có |
| **Boolean-blind SQLi** | `' AND SUBSTRING(database(),1,1)='m'--` | ✅ Có (Nhánh 1) |
| **Time-blind SQLi** | `' AND IF(1=1,SLEEP(5),0)--` | ✅ Có (Nhánh 1) |
| **Stacked Queries** | `SELECT * FROM users; DROP TABLE users;--` | ⏳ Thiết kế chưa triển khai |

#### **Out-of-Scope Attacks (Không Bao Phủ)**

| Attack Type | Lý Do Không Bao Phủ |
| :---- | :---- |
| **Out-of-Band (OOB) SQLi** | Proxy không thấy DNS/HTTP requests mà attacker gây ra |
| **Second-Order SQLi** | Payload lưu an toàn ngày hôm trước, trigger hôm nay — cần session tracking dài hạn |
| **XSS, CSRF** | Không phải SQL Injection |
| **HTTP Parameter Pollution** | Xảy ra trước khi query assembled |

---

### **0.2 Bài Toán Class Imbalance (Mất Cân Bằng Lớp) & F1-macro**

#### **Vấn Đề: Tại Sao Không Dùng Accuracy?**

Giả sử dataset có:
- 10,000 mẫu **normal** (bình thường)
- 100 mẫu **union_based** (tấn công)

Một mô hình **đơn giản** có thể:
- Dự đoán tất cả là `normal`
- Accuracy = 10,000 / 10,100 = **99%** ✅ (vẻ tốt)
- Nhưng **không phát hiện được tấn công nào** ❌ (thực tế tệ)

**Giải pháp: Dùng F1-macro**

F1-macro = trung bình F1-score của **tất cả các lớp** (bình đẳng)

```
F1 = 2 × (Precision × Recall) / (Precision + Recall)

F1-macro = (F1_normal + F1_union + F1_error + F1_boolean + F1_time) / 5
```

- Nếu mô hình bỏ qua một lớp → F1 của lớp đó = 0 → F1-macro sụt xuống
- **Ép mô hình phải học tất cả các lớp**, không bỏ lơ lớp nhỏ

#### **Kết Quả Thực Tế Dự Án**

- **Dataset**: 5 lớp (normal, union_based, error_based, boolean_blind, time_blind)
- **Class distribution** (trước khi undersampling):
  - normal: ~30,000
  - union_based: ~25,000
  - boolean_blind: ~150,000 (lớn nhất)
  - time_blind: ~40,000
  - error_based: ~7,000 (lớp nhỏ nhất)

- **Lý do F1-macro quan trọng**: Để mô hình không bỏ qua `error_based` (lớp nhỏ)

---

### **0.3 Label Noise (Nhiễu Nhãn)**

Khi xây dựng dataset, chúng ta phát hiện ra **một số mẫu bị gán nhãn sai**:

#### **Noise trong `normal` class (~9.8%)**
Ví dụ: Một query ghi nhãn là "normal" nhưng thực tế chứa:
- `sleep(15)` → Đây là **time-blind SQLi**, không phải normal
- Shellshock payload → Không phải SQLi, nhưng cũng không normal
- `&cat /etc/passwd&` → Command injection, không normal

**Cách phát hiện:** Đọc tay 30 mẫu từ "normal" pool, phát hiện 3 lỗi → ~10% noise

**Hệ quả:**
- Model train trên dữ liệu nhiễu → không thể đạt 100% accuracy
- F1-macro = 0.9822 **không phải "perfect"**, chỉ là tốt nhất có thể với dữ liệu nhiễu

#### **Noise trong `boolean_blind` class (~13%)**
`boolean_blind` là lớp "catch-all" (bất cứ SQLi nào không match 4 quy tắc rõ ràng)

Manual audit 30 mẫu: phát hiện 4 mẫu sai (~13%)
- SSRF payload (không phải SQLi)
- CRLF injection (không phải SQLi)
- 1 mẫu hoàn toàn bình thường

**Kết luận:** Noise là bottleneck, không phải model yếu

---

### **0.4 Supervised vs Unsupervised Learning**

#### **Branch 1: Supervised (Học Có Giám Sát)**

```
Input: SQL query string
         ↓
[Model trained on 54,236 labeled examples]
         ↓
Output: Class label (normal / union_based / error_based / boolean_blind / time_blind)
```

**Đặc điểm:**
- ✅ Học từ nhãn **đã biết** (labeled data)
- ✅ Có thể phát hiện **các loại tấn công đã training**
- ❌ KHÔNG thể phát hiện loại tấn công **mới chưa từng thấy**
- Ví dụ: Nếu không training trên `stacked` queries → mô hình không biết cách detect nó

**Khi nào dùng:**
- Có nhiều dữ liệu đã gán nhãn
- Biết trước các loại attack

---

#### **Branch 2: Unsupervised (Học Không Giám Sát)**

**Training Phase (Học):**
```
Query 1 (benign): "SELECT * FROM users WHERE id = 1"
Query 2 (benign): "SELECT name FROM users"
Query 3 (benign): "SELECT * FROM users WHERE id = 1"
...
Query N (benign): "SELECT id, name, email FROM users WHERE active = 1"
    ↓
[Extract 4 statistical features]
    ├─ Query 1: [length=40, special_ratio=0.05, sql_keywords=4, entropy=4.2]
    ├─ Query 2: [length=28, special_ratio=0.04, sql_keywords=3, entropy=4.0]
    └─ Query N: [length=58, special_ratio=0.06, sql_keywords=5, entropy=4.3]
    ↓
[One-Class SVM Model]
    ├─ Learn the "normal cluster" shape
    ├─ Draw boundary around normal data
    └─ Everything inside = normal, outside = anomalous
    ↓
Model trained (learn normal distribution, NO LABELS USED)
```

**Inference Phase (Dự Đoán):**
```
Input Query (unknown): "SELECT * FROM users WHERE id = 1' OR '1'='1"
    ↓
[Extract 4 statistical features]
    ↓
[length=53, special_ratio=0.11, sql_keywords=4, entropy=4.5]
    ↓
[One-Class SVM Model]
    ├─ Calculate distance to normal cluster
    └─ Output: Anomaly Score = +0.3 (positive = anomalous)
    ↓
Decision: 
├─ If score < threshold (-0.5) → Normal
└─ If score ≥ threshold (-0.5) → Anomalous ⚠️
    ↓
Output: Anomaly_score=0.3, Flag=ANOMALOUS
```

**Đặc điểm:**
- ✅ KHÔNG cần nhãn → dễ thu thập dữ liệu (tất cả query bình thường)
- ✅ Có thể phát hiện **bất cứ loại anomaly nào**, kể cả attack mới chưa thấy
- ❌ Có **false positive cao** (query lạ không phải attack, mà là query đặc biệt của system)
- ❌ Không biết **loại attack nào** cụ thể
- ❌ Cần **chuẩn hóa dữ liệu** (scaling features để SVM hoạt động tốt)

**Khi nào dùng:**
- Muốn catch **zero-day attacks** (tấn công mới)
- Có dữ liệu benign dễ thu thập

---

#### **So Sánh Trực Tiếp (Branch 1 vs Branch 2)**

| Tiêu Chí | Branch 1 (Supervised) | Branch 2 (Unsupervised) |
| :---- | :---- | :---- |
| **Dữ liệu train** | Labeled (normal + attacks) | Unlabeled (benign only) |
| **Output** | Class label (5 categories) | Anomaly score + flag |
| **Phát hiện attack cũ** | ✅ Tốt (0.9822 F1-macro) | ⚠️ Tốt (0.902 AUC) |
| **Phát hiện attack mới** | ❌ Không | ✅ Có (high AUC) |
| **False positive** | Thấp (0.5%) | Thấp nếu tune tốt (0.3% at deploy) |
| **Yêu cầu tài nguyên** | Nhỏ (3.9 MB) | Nhỏ (<1 MB) |

#### **Tại Sao Cần Cả Hai?**

```
Decision Rule:
├─ If Branch 1 predicts ATTACK → BLOCK (ngay lập tức)
├─ If Branch 1 predicts NORMAL + Branch 2 predicts ANOMALY → HOLD (xin admin confirm)
└─ If Branch 1 predicts NORMAL + Branch 2 predicts NORMAL → ALLOW
```

**Lợi ích:**
- Catch **known attacks** via Branch 1 (nhanh, chính xác)
- Catch **zero-day attacks** via Branch 2 (không cần nhãn)
- Giảm false positive bằng cách require cả hai điều kiện

---

## **PHẦN 1: CÁC LOẠI TẤN CÔNG SQL INJECTION (Easy)**

Tham khảo: **Chapter 1 của report**

### **1.1 Union-based SQLi**
```sql
-- Normal:
SELECT name, email FROM users WHERE id = 1

-- Attack:
SELECT name, email FROM users WHERE id = 1 UNION SELECT username, password FROM admin
-- → Attacker lấy được 2 cột từ table khác
```

**Nhận biết:** Chứa từ khóa UNION + SELECT + số cột match

---

### **1.2 Error-based SQLi**
```sql
-- Attack:
SELECT * FROM users WHERE id = 1 AND EXTRACTVALUE(1, CONCAT(0x7e, (SELECT @@version)))
-- → Database throw error, error message chứa @@version
```

**Nhận biết:** Cố ý tạo syntax error để leak thông tin từ error message

---

### **1.3 Boolean-blind SQLi**
```sql
-- Attack:
SELECT * FROM users WHERE id = 1 AND SUBSTRING(database(), 1, 1) = 'm'
-- → Nếu condition true → page render bình thường
-- → Nếu condition false → page render khác
-- Attacker đoán từng ký tự: m, y, s, q, l, ...
```

**Nhận biết:** Chứa conditional logic (AND, OR) + comparison operators

---

### **1.4 Time-blind SQLi**
```sql
-- Attack:
SELECT * FROM users WHERE id = 1 AND IF(1=1, SLEEP(5), 0)
-- → Nếu condition true → response delay 5 seconds
-- → Nếu condition false → response immediate
-- Attacker phát hiện bằng timing, không cần xem content
```

**Nhận biết:** Chứa SLEEP(), DBMS_LOCK.SLEEP(), WAITFOR DELAY(), v.v.

---

### **1.5 Stacked Queries (Chưa Triển Khai)**
```sql
-- Attack:
SELECT * FROM users; DROP TABLE users; --
-- → 2 statements, attacker thực thi cả 2
```

**Nhận biết:** Chứa `;` (statement delimiter) + SQL commands khác nhau

---

## **PHẦN 2: KIẾN TRÚC HỆ THỐNG (System Architecture)**

Tham khảo: **Section 2.1, 2.6 của report**

```
┌─────────────────────────────────────────────────┐
│  Web Application (Backend)                      │
│  - Receives user input                          │
│  - Builds SQL query: "SELECT * FROM users..."   │
└────────────────┬────────────────────────────────┘
                 │
        SQL String (canonicalized)
                 ↓
     ┌───────────────────────────┐
     │   DATABASE PROXY          │
     │  (SQLi Detection Engine)  │
     ├───────────────────────────┤
     │ Step 1: Canonicalization  │
     │ - Normalize case          │
     │ - Remove excess spaces    │
     │ - Normalize comments      │
     ├───────────────────────────┤
     │ Step 2: Branch 1          │
     │ - Supervised classifier   │
     │ - TF-IDF + Logistic Reg   │
     │ → Predict: class label    │
     ├───────────────────────────┤
     │ Step 3: Branch 2          │
     │ - Anomaly detector        │
     │ - One-Class SVM           │
     │ → Predict: anomaly score  │
     ├───────────────────────────┤
     │ Step 4: Decision Engine   │
     │ - Apply decision rules    │
     │ → ALLOW / BLOCK / HOLD    │
     └───────────────────────────┘
                 │
          Decision: ALLOW/BLOCK/HOLD
                 ↓
     ┌─────────────────────────────────┐
     │ ALLOW → Pass to Database        │
     │ BLOCK → Reject, log incident    │
     │ HOLD → Admin review (Overkill)  │
     └─────────────────────────────────┘
```

---

## **PHẦN 3: NGUỒN DỮ LIỆU (Data Sources)**

Tham khảo: **Section 2.3, 2.4, 2.5 của report**

### **3 Nguồn Chính**

| Nguồn | Số Mẫu | Dùng Cho | Đặc Điểm |
| :---- | :---- | :---- | :---- |
| **SQLiV3** | ~30.9K | Branch 1 + Branch 2 | Dữ liệu Kaggle, license chưa rõ |
| **payload-box** | ~13K | Branch 1 enrichment | MIT license, phân loại theo loại attack |
| **SR-BH 2020** | 527.8K | Branch 1 + Branch 2 | Harvard Dataverse honeypot, multi-label CAPEC |
| **CSIC 2010** | 113K benign + 25K attack | Branch 2 eval | HTTP traffic, balanced for eval |

### **3.1 Phân Bố Lớp trong Mỗi Nguồn**

#### **SQLiV3 (~30.9K mẫu)**

| Lớp | Số Mẫu | Ghi Chú |
| :---- | :---- | :---- |
| normal | ~8K | Benign queries |
| union_based | ~5K | SQLi with UNION |
| error_based | ~1K | SQLi with intentional errors |
| boolean_blind | ~8K | Blind SQLi logic |
| time_blind | ~5K | Blind SQLi with SLEEP |
| stacked | 0 | ❌ Không có mẫu tự nhiên |

**Vấn đề:** 
- Lớp imbalanced (union vs error 5:1)
- Không có stacked → cần synthetic hoặc dùng nguồn khác
- Không có benign traffic phức tạp (chỉ simple SELECT)

---

#### **payload-box (~13K payload strings)**

| Lớp | Số Mẫu | Ví Dụ |
| :---- | :---- | :---- |
| union_based | ~3.5K | `' UNION SELECT ...` |
| error_based | ~2K | `' AND EXTRACTVALUE(1, ...)` |
| time_blind | ~4K | `' AND SLEEP(5)--` |
| boolean_blind | ~2.5K | `' AND 1=1--` |
| stacked | ~0.5K | `; DROP TABLE ...` |

**Tác dụng:** Enrichment chứ không phải primary source
- Payload **rõ ràng phân loại** theo type (dễ verify)
- Dùng để **supplement** SQLiV3 (add diversity)
- MIT licensed → safe to use

---

#### **SR-BH 2020 Honeypot (527.8K mẫu gốc)**

**Cấu trúc thô:**
- 250.3K mẫu gắn nhãn `SQL Injection=1` (multi-label CAPEC)
- 277.5K mẫu gắn nhãn `Normal=1`

**Sau re-tagging bằng rule-based sub-type matching:**

| Lớp | Số Mẫu Được Tag | Ghi Chú |
| :---- | :---- | :---- |
| union_based | ~83K | `UNION` keyword detected |
| error_based | ~7.4K | Intentional syntax errors |
| time_blind | ~32.7K | `SLEEP()`, `DBMS_LOCK.SLEEP()` |
| boolean_blind | ~126.9K | Catch-all (conditional logic) |
| normal (benign) | ~277.5K | HTTP requests, no SQLi |
| multi-label (unknown) | ~69K | Couldn't re-tag → discarded |

**Re-tagging logic:**
```python
if 'UNION' in query and 'SELECT' in query:
    tag = 'union_based'
elif 'SLEEP' in query or 'WAITFOR' in query:
    tag = 'time_blind'
elif error_pattern.match(query):
    tag = 'error_based'
elif conditional_pattern.match(query):
    tag = 'boolean_blind'
else:
    tag = 'unknown'  # Discarded
```

**Lợi ích:**
- ✅ 250K+ attack samples (thực tế)
- ✅ 277K benign samples (HTTP traffic thật, có JOIN, subquery)
- ✅ Multi-attack-type diversity
- ❌ Cần re-tag (original CAPEC labels quá coarse)

---

#### **CSIC 2010 (Riêng dùng cho Branch 2 Evaluation)**

**Benign pool (113K mẫu):**
- GET/POST requests từ real HTTP session
- Complex queries (JOIN, subquery, aggregate)
- Thực tế workflow → dùng train/eval Branch 2

**Anomalous pool (25K mẫu, held-out evaluation):**
- Multiple attack types (không SQLi-exclusive):
  - SQLi: ~8K
  - XSS: ~5K
  - Path traversal: ~4K
  - Buffer overflow: ~3K
  - Other: ~5K

**Tại sao mixed?**
- CSIC 2010 designed cho general web security
- Branch 2 phải detect **bất cứ anomaly nào**, không chỉ SQLi
- Mixed evaluation set → "general anomaly detection rate", không SQLi-specific

---

### **3.2 Tổng Hợp: Mỗi Lớp Từ Đâu?**

| Lớp | Source | Số Mẫu Gốc | Sau Filtering | Sau Undersampling | Note |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **normal** | SQLiV3 + SR-BH 2020 + CSIC benign | ~305K | ~302K (2.8K filtered) | 15K | Filtered 9.8% noise |
| **union_based** | SQLiV3 + payload-box + SR-BH | ~91.5K | ~91.5K | 15K | Good diversity |
| **error_based** | SQLiV3 + payload-box + SR-BH | ~10.4K | ~10.4K | 7.8K | Smallest, kept full |
| **boolean_blind** | SQLiV3 + payload-box + SR-BH | ~137.4K | ~137.4K | 15K | Catch-all (~13% noise) |
| **time_blind** | SQLiV3 + payload-box + SR-BH | ~41.7K | ~41.7K | 15K | Good precision |
| **stacked** | None (0 natural) → synthetic | 0 | 73 (test only) | Excluded | Imbalanced + trivial |

---

### **Tại Sao 3 Nguồn?**

SQLiV3 một mình **không đủ**:
- ❌ Lớp `stacked`: 0 mẫu tự nhiên
- ❌ Lớp `error_based`: quá ít
- ❌ `boolean_blind`: quá rộng, không rõ
- ❌ Không có benign traffic phức tạp (JOIN, subquery)

**SR-BH 2020 giải quyết:**
- ✅ 250K+ mẫu SQLi (thô)
- ✅ 300K+ benign traffic từ thật (với JOIN, subquery)

**payload-box giải quyết:**
- ✅ Payload rõ ràng phân loại theo type

---

## **PHẦN 4: TIỀN XỬ LÝ (Preprocessing)**

Tham khảo: **Section 2.2, 2.4, 2.5 của report**

### **4.1 Canonicalization (Chuẩn Hóa)**

**Mục tiêu:** Loại bỏ biến thể **bề ngoài**, giữ nguyên **semantic**.

#### **Các biến thể bề ngoài**
```sql
SELECT * FROM users        -- Normal
select*from users          -- Excess spaces, lowercase
SELECT /* comment */ * FROM users  -- Embedded comment
SELECT 0x48 FROM users     -- Hex encoding for 'H'
```

**Tất cả đều normalize thành:**
```sql
select * from users
```

#### **Canonicalization Pipeline**
1. **Case normalization** → `select` (lowercase)
2. **Whitespace normalization** → Collapse multiple spaces to 1
3. **Comment removal** → Strip `/* */`, `--`, `#` comments
4. **Literal normalization** → `0x48` → `'H'` (để đơn giản)
5. **Entity decoding** → `%20` → ` ` (URL decode)

**Công cụ:** `src/preprocessing/canonicalize.py`

**Giới hạn:** Canonicalization **không xử lý**:
- Semantic evasion: `UNION SELECT` vs `UNION/**/SELECT` (cùng logic)
- Encoding sâu (iterative decoding có giới hạn)
- → Cần adversarial testing (phần Future Work)

---

### **4.2 Lọc Nhiễu & Cân Bằng Lớp (Class Balancing)**

#### **Bước 1: Lọc Nhiễu ở `normal` class**

Dataset gốc có nhiễu:
- `sleep(15)` bị gán `normal` (sai)
- Shellshock payload bị gán `normal` (sai)

**Giải pháp:**
- Viết content-based filter (regex + keyword matching)
- Chạy 3 lần filter, mỗi lần phát hiện biến thể mới
- Xóa **2,892 mẫu** (~9.8% của normal pool)

**Kết quả:** Normal pool sạch hơn, nhưng **không 100% sạch** (luôn có edge case)

#### **Bước 2: Cân Bằng Lớp (Undersampling)**

**Trước undersampling:**
- boolean_blind: ~150K mẫu (biggest)
- normal: ~30K
- time_blind: ~40K
- union_based: ~25K
- error_based: ~7K (smallest)

**Vấn đề:** Lớp lớn dominate training, lớp nhỏ bị bỏ qua

**Giải pháp:** Undersample 3 lớp lớn → mỗi lớp ~15K
```
Trước: 150K + 30K + 40K + 25K + 7K = 252K
Sau:    15K + 15K + 15K + 15K + 7K = 67K (keep error_based full)
```

**Tại sao không oversample?** Oversample tạo duplicate → overfitting

**Tại sao không balance perfectly?** error_based có 7K → nếu balance mỗi lớp 7K sẽ quá nhỏ

---

### **4.3 Các Mẫu Loại Trừ**

#### **Stacked Class: Excluded**
- 0 mẫu tự nhiên trong 3 dataset
- Generated 363 synthetic (11×11×3 templates)
- **Vấn đề 1:** Extreme imbalance → 73 test mẫu = 0.54% dataset
- **Vấn đề 2:** Synthetic template trivial → mô hình đạt 100% recall (artifact capture, không real learning)
- **Vấn đề 3:** Template không đại diện production traffic
- **→ Excluded từ training, moved to Future Work**

---

## **PHẦN 5: KỸ THUẬT TRÍCH ĐẶC TRƯNG (Feature Engineering)**

### **5.1 TF-IDF (Branch 1: Supervised)**

**Mục tiêu:** Chuyển text SQL → vector số (để machine learning mô hình hiểu được)

#### **Ý tưởng cơ bản**

```
TF (Term Frequency) = Tần suất từ trong doc
IDF (Inverse Document Frequency) = Độ hiếm của từ trong toàn dataset

TF-IDF = TF × IDF
```

**Ví dụ:**
```sql
Query 1: "SELECT * FROM users WHERE id = 1"
Query 2: "SELECT username FROM admin"
Query 3: "SELECT * FROM users WHERE id = 1' OR '1'='1"
```

**Tính TF:**
- Query 1: SELECT (1), FROM (1), WHERE (1), ...
- Query 3: SELECT (1), FROM (1), WHERE (1), OR (1), ...

**Tính IDF:**
- "SELECT": xuất hiện 3/3 docs → hiếm → IDF thấp
- "OR": xuất hiện 1/3 docs → hiếm → IDF cao (signal tốt cho attack)
- "1": xuất hiện 2/3 docs → trung bình → IDF trung bình

**TF-IDF vector:**
- Từ hiếm ("OR") có weight cao
- Từ phổ biến ("SELECT") có weight thấp
- → Mô hình học: attack thường dùng các từ/ký tự hiếm

#### **TF-IDF Implementation**

```python
from sklearn.feature_extraction.text import TfidfVectorizer

vectorizer = TfidfVectorizer(
    analyzer='char',        # Character-level (không word-level)
    ngram_range=(1, 3),     # 1 char, 2 char, 3 char sequences
    max_features=1000       # Top 1000 important features
)

# Train: học từ training set
X_train = vectorizer.fit_transform(train_queries)

# Test: transform test set (không fit lại)
X_test = vectorizer.transform(test_queries)
```

**Lý do character-level không word-level:**
- SQL syntax không rõ ràng (operators: `=`, `'`, `--` có ý nghĩa)
- Attack code cơ bản: `' OR '1'='1` (5 tokens character-level)
- Word-level sẽ miss ký tự tấn công quan trọng

---

### **5.2 Statistical Features (Branch 2: Unsupervised)**

**Mục tiêu:** Tính độ "lạ" (anomalousness) của một query

**Tại sao không dùng TF-IDF cho Branch 2?**
- TF-IDF tied to **vocabulary seen during training**
- Nếu train trên benign traffic → TF-IDF learns benign vocab
- Một attack mới nhưng **chỉ dùng benign keywords** → TF-IDF không phát hiện được
- Ví dụ: `SELECT * FROM users WHERE name='admin' OR 1=1` (tất cả keywords benign)

**Giải pháp: 4 Generic Statistical Features**

| Feature | Tính Toán | Giải Thích |
| :---- | :---- | :---- |
| **Length** | `len(query)` | Query dài → có khả năng lạ |
| **Special Char Ratio** | `(count of '!@#$%^&*') / len(query)` | Attack dùng ký tự đặc biệt: `'`, `--`, `;` |
| **SQL Keyword Count** | Count `SELECT, FROM, WHERE, UNION, DROP, ...` | Benign thường 2-5 keywords, attack có thể >10 |
| **Entropy** | Shannon entropy of character distribution | Random/obfuscated code → high entropy |

**Ví dụ:**
```sql
Normal:  SELECT * FROM users WHERE id = 1
├─ Length: 40
├─ Special Ratio: 2/40 = 5% (2 chars: *, =)
├─ SQL Keywords: 4 (SELECT, FROM, WHERE)
└─ Entropy: 4.2 (fairly uniform distribution)

Attack:  SELECT * FROM users WHERE id = 1' OR '1'='1
├─ Length: 52
├─ Special Ratio: 6/52 = 11.5% (6 chars: *, =, ', ', ', =)
├─ SQL Keywords: 4 (SELECT, FROM, WHERE)
└─ Entropy: 4.5 (more variation due to OR, quotes)
```

**Model learns:**
- Normal queries cluster around (len=40, ratio=5%, keywords=4, entropy=4.2)
- Attack queries scatter or cluster differently
- Query nằm **ngoài normal cluster** → flagged as anomalous

---

## **PHẦN 6: BRANCH 1 - SUPERVISED CLASSIFICATION (Phân Loại Có Giám Sát)**

Tham khảo: **Section 2.8 của report**

### **6.1 Logistic Regression + TF-IDF**

**Thuật toán:** Logistic Regression (hồi quy logistic)

**Input:** TF-IDF vector (1000 features)
**Output:** Probability cho mỗi lớp (5 classes)

```
Query "SELECT * FROM users WHERE id=1' OR '1'='1"
    ↓
[TF-IDF Vectorizer]
    ↓
Vector: [0.1, 0.0, 0.3, ..., 0.05]  (1000 numbers)
    ↓
[Logistic Regression Model]
    ├─ P(normal) = 0.05
    ├─ P(union_based) = 0.02
    ├─ P(error_based) = 0.01
    ├─ P(boolean_blind) = 0.89  ← Highest
    └─ P(time_blind) = 0.03
    ↓
Predict: boolean_blind (class with highest probability)
```

**Lý do chọn Logistic Regression (không Neural Network):**
- ✅ Nhỏ (3.9 MB vs 256 MB cho DistilBERT)
- ✅ Nhanh (0.5 ms vs 2.8 ms cho DistilBERT)
- ✅ F1-macro chỉ kém 0.5% (0.9849 vs 0.9927)
- ✅ Có thể training nhanh (10 giây vs 1400 giây)
- ❌ Mất một chút accuracy

**Trade-off:** Chọn **speed + size** hơn 0.5% accuracy (vì deployment priority)

---

### **6.2 Kết Quả**

**F1-macro = 0.9822** (5-class, test set n=13,560)

| Class | Precision | Recall | F1 | Ý Nghĩa |
| :---- | :---- | :---- | :---- | :---- |
| normal | 96.6% | 94.7% | 95.6% | 1 trên 20 false positive |
| union_based | 99.9% | 99.0% | 99.5% | Tuyệt vời |
| error_based | 99.8% | 100% | 99.9% | Perfect |
| boolean_blind | 94.8% | 97.4% | 96.1% | OK (noise in this class) |
| time_blind | 100% | 100% | 100% | Perfect |

**Confusion:**
- 157 mẫu `normal` bị dự đoán `boolean_blind`
- 74 mẫu `boolean_blind` bị dự đoán `normal`
- Kết quả: **normal ↔ boolean_blind** mất cân bằng (do ~13% noise ở boolean_blind)

---

## **PHẦN 7: BRANCH 2 - UNSUPERVISED ANOMALY DETECTION (Phát Hiện Anomaly)**

Tham khảo: **Section 2.9 của report**

### **7.1 Feature Engineering & Model Architecture (One-Class SVM)**

#### **7.1.1 Feature Engineering: 4 Statistical Features**

**Tại sao 4 features này?**

Unsupervised anomaly detection **không thể dùng TF-IDF** vì:
- TF-IDF tied to **vocabulary từ training data**
- Nếu training trên benign → học benign vocab
- Attack với **benign keywords** → TF-IDF miss nó
- Ví dụ: `SELECT * FROM users WHERE name='admin' OR 1=1`
  - Tất cả keywords: SELECT, FROM, WHERE, OR, 1 đều benign
  - TF-IDF: Score benign (sai!)
  - Statistical features: Ratio cao (đúng!)

**4 Features Tính Toán:**

```python
def extract_statistical_features(query: str):
    features = {}
    
    # Feature 1: Query Length (độ dài)
    features['length'] = len(query)
    # Normal: 30-80 chars
    # Attack: thường 50-150+ (do injection payload dài)
    
    # Feature 2: Special Character Ratio (tỷ lệ ký tự đặc biệt)
    special_chars = set("'\"`;=-!<>*&|()[]{}\\~")
    features['special_char_ratio'] = sum(
        1 for c in query if c in special_chars
    ) / len(query)
    # Normal: 3-8% (chủ yếu =, ', ")
    # Attack: 8-15% (thêm ', --, ;, \, |)
    
    # Feature 3: SQL Keyword Count (đếm từ khóa SQL)
    sql_keywords = {
        'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 
        'UNION', 'INSERT', 'UPDATE', 'DELETE', 'DROP',
        'CREATE', 'ALTER', 'SLEEP', 'WAITFOR', 'IF', 'CASE'
    }
    features['sql_keyword_count'] = sum(
        1 for keyword in sql_keywords 
        if keyword in query.upper()
    )
    # Normal: 2-6 keywords
    # Attack: 4-15+ keywords (do inject multiple keywords)
    
    # Feature 4: Shannon Entropy (entropy)
    from collections import Counter
    freq = Counter(query)
    entropy = -sum(
        (count/len(query)) * log2(count/len(query)) 
        for count in freq.values()
    )
    # Normal: 4.0-4.5 (fairly uniform distribution)
    # Attack: 4.5-5.0+ (more variation, obfuscation)
    
    return features
```

**Ví dụ Tính Toán Chi Tiết:**

```
Query A (Normal):   "SELECT * FROM users WHERE id = 1"
├─ Length: 40 chars
├─ Special chars: * = (2 chars) → 2/40 = 5%
├─ SQL keywords: SELECT, FROM, WHERE (3)
└─ Entropy: 4.2

Query B (Attack):   "SELECT * FROM users WHERE id = 1' OR '1'='1"
├─ Length: 50 chars
├─ Special chars: * = ' ' ' = ' = (7 chars) → 7/50 = 14%
├─ SQL keywords: SELECT, FROM, WHERE, OR (4)
└─ Entropy: 4.6

Difference (B - A):
├─ Length: +10 (query more complex)
├─ Special Ratio: +9% (dấu ngoặc + quotes)
├─ Keywords: +1 (thêm OR)
└─ Entropy: +0.4 (more randomness từ quotes + numbers)
```

---

#### **7.1.2 Model Architecture: One-Class SVM**

**Input:** 4-dimensional feature vectors (length, special_ratio, keyword_count, entropy)
**Output:** Anomaly score + binary classification

**Workflow:**

```
┌─────────────────────────────────────────────────────────────┐
│ TRAINING: Learn normal data distribution                    │
└─────────────────────────────────────────────────────────────┘

Training queries (benign only):
  Q1: [40, 0.05, 3, 4.2]
  Q2: [45, 0.04, 3, 4.1]
  Q3: [38, 0.06, 2, 4.3]
  ...
  Q1000: [52, 0.07, 4, 4.5]
           ↓
    [Visualize in 4D space]
    
    Feature space (2D projection):
    
    Y-axis (special_ratio)
          │
      0.07│     ●●●●
           │    ●●●●●●    ← Normal queries cluster
      0.06│   ●●●●●●●
           │  ●●●●●●●●
      0.05│ ●●●●●●●
           │●●●●●●
      0.04│
           │
      0.03└─────────────────────────── X-axis (length)
           35  40  45  50  55  60
           
    One-Class SVM draws boundary:
           │
      0.07│     ╱────╲
           │    │ ●●● │  ← Everything inside = normal
      0.06│   │●●●●●●│
           │  │●●●●●●│
      0.05│ │●●●●●● │
           │ │●●●●● │
      0.04│ ╲────╱
           │      (attack would be outside)
      0.03└─────────────────────────
           35  40  45  50  55  60
           
    Model learns:
    - Center of normal cluster
    - Radius/shape of normal region
    - Distance metric (how to measure "far from normal")
```

**Decision Function:**

```python
from sklearn.svm import OneClassSVM

model = OneClassSVM(kernel='rbf', gamma='auto', nu=0.005)
model.fit(X_train_features)  # Train on benign data only

# Scoring (inference)
anomaly_score = model.score_samples(X_test)  # Continuous value
prediction = model.predict(X_test)  # -1 (anomaly) or +1 (normal)

# Interpretation:
# score_samples < 0: Outside normal boundary → Anomalous
# score_samples > 0: Inside normal boundary → Normal
```

---

#### **7.1.3 Principles: Tại Sao One-Class SVM Hoạt Động?**

**Principle 1: Support Vector Boundary**
- SVM tìm **simplest boundary** separating normal from outside
- Không học "malicious patterns" (không có label attack)
- Chỉ học "normal region shape"

**Principle 2: Generalization to Unknown Attacks**
```
Dataset Training (benign):
  ●●●●●●●●●
  ●●●●●●●●●
  ●●●●●●●●●
  
After training, boundary learned:
  ╱─────────╲
  │●●●●●●●●●│  ← Model knows this is "normal"
  │●●●●●●●●●│
  │●●●●●●●●●│
  ╲─────────╱

New attack (never seen):
  
  ╱─────────╲
  │●●●●●●●●●│
  │●●●●●●●●●│  ⬅ ✖ Attack here
  │●●●●●●●●●│   (Outside boundary)
  ╲─────────╱

→ Detected as anomalous (even though we never trained on this attack!)
```

**Principle 3: Statistical Independence**
- 4 features independent → SVM sees multi-dimensional signature
- Attack that hides one feature (e.g., normal length) → caught by other 3 (special ratio, keywords)
- Example: Short attack
  ```
  Query: "'; DROP TABLE users; --"
  ├─ Length: 30 (short, benign-like)
  ├─ Special Ratio: 20% (HIGH → anomalous signal!)
  ├─ Keywords: SELECT 0, DROP 1 (unusual combo)
  └─ Result: Still detected by multi-feature combination
  ```

**Principle 4: Threshold Flexibility**
```
Anomaly scores on test set:

Normal queries:    ████████       (centered ~-3 to -4)
                   ████████

Anomalous queries:      ██████████  (scattered -1 to +1)
                        ████████

By adjusting threshold:
├─ Threshold -4.0: Catch 100% attacks, 100% false positive
├─ Threshold -2.0: Catch 60% attacks, 20% false positive  
├─ Threshold -0.5: Catch 20% attacks, 0.3% false positive (deployed)
└─ Threshold +1.0: Catch ~5% attacks, almost no false positive
```

---

### **7.3 Isolation Forest vs One-Class SVM**

#### **7.3.1 Isolation Forest Detailed**

**Đầu Vào: TẤT CẢ 4 Features (KHÔNG chỉ độ dài)**

```python
# Mỗi query: 4 features
Query 1 (benign): [length=40, special_ratio=0.05, keywords=3, entropy=4.2]
Query 2 (attack): [length=53, special_ratio=0.14, keywords=5, entropy=4.6]
Query 3 (benign): [length=38, special_ratio=0.06, keywords=2, entropy=4.1]
...
Query N (benign): [length=62, special_ratio=0.08, keywords=4, entropy=4.3]

# Input: 100+ queries × 4 features = 100+ points in 4D space
```

**Ý Tưởng: Anomaly Dễ Tách Riêng Hơn Normal**

```
Intuition:
- Normal queries gần nhau → cần NHIỀU random splits để tách từng cái
- Anomaly queries lẻ loi → cần ÍT splits để tách riêng

Visualization (simplified to 2D):

┌──────────────────────────────────────────┐
│ Y-axis: special_ratio                     │
│                                          │
│   ●●●●●●● (benign cluster, tight)      │
│   ●●●●●●●                              │
│                                          │
│         ✖ (anomaly, standalone)         │
│                                          │
└──────────────────────────────────────────┘
  X-axis: length
```

**Quá Trình Xây Dựng (Random Forest of Isolation Trees):**

```
TREE 1: Random split by special_ratio at threshold 0.10
────────────────────────────────────────────────────────
         All 100 queries
              │
        special_ratio < 0.10?
         /              \
    LEFT (90)        RIGHT (10)
  (mostly            ← Query 2 (anomaly)
   benign)              alone here!
                        (0 more splits needed)

Query 2: Isolated in 1 split


TREE 2: Random split by keywords at threshold 3.5
──────────────────────────────────────────────────
         All 100 queries
              │
        keywords < 3.5?
         /              \
    LEFT (60)        RIGHT (40)
                    ├─ Query 2 here
                    ├─ Some benign too
                    
        Split again → ...
                    
Query 2: Isolated in 2 splits


TREE 3: Random split by entropy at threshold 4.3
──────────────────────────────────────────────────
Query 2: Isolated in 1 split


TREE 4-100: More random splits
──────────────────────────────
Track how many splits needed to isolate Query 2 in each tree
```

**Anomaly Score = Average Isolation Depth**

```
Aggregate across 100 trees:

Tree 1: Query 2 needs 1 split
Tree 2: Query 2 needs 2 splits
Tree 3: Query 2 needs 1 split
Tree 4: Query 2 needs 3 splits
...
Tree 100: Query 2 needs 2 splits

Average depth = (1 + 2 + 1 + 3 + ... + 2) / 100 = 1.8 splits

For normal query (Query 1):
Tree 1: Query 1 needs 2 splits
Tree 2: Query 1 needs 3 splits
Tree 3: Query 1 needs 4 splits
...
Average depth = 3.2 splits

Anomaly Score = f(average_depth)
- Shorter depth = more anomalous
- Longer depth = more normal

Query 2: 1.8 splits (average) → HIGH anomaly score ✓
Query 1: 3.2 splits (average) → LOW anomaly score ✓
```

**Tại Sao Không Phải Split ở Length < 50 vs >= 50?**

```
Trong thực tế, Isolation Forest:
- KHÔNG cố định threshold ở 50
- KHÔNG cố định feature ở "length"
- MỖI tree chọn:
  ├─ Feature ngẫu nhiên (length? special_ratio? keywords? entropy?)
  ├─ Threshold ngẫu nhiên (không phải round numbers)
  └─ Tách recursively cho tới khi từng query alone

Ví dụ:
Tree 1: length < 47.3
Tree 2: special_ratio < 0.087
Tree 3: entropy < 4.25
...

Không fixed ở 50 - đó chỉ là ví dụ đơn giản hóa!
```

**Visualization: Cách IT Thực Tế Hoạt Động**

```
4D Feature Space (hạ xuống 2D để vẽ):

X-axis: Length
Y-axis: Special_Ratio

Iteration 1: Split by special_ratio < 0.10
┌────────────────────────────────────────┐
│   0.15 │                               │
│        │  ╱─ Threshold                 │
│  0.10 ├─╱ Query 2 (✖) here            │
│        │ ╱                             │
│  0.05 │●●●●●●●●● (●●● benign)        │
│        │●●●●●●●●●                     │
│  0.00 └───┴──────────────────────────  │
│        30  50  70  90  110   Length   │
│                                       │
│ Result: Query 2 immediately isolated  │
│ (needs only 1 split)                  │
└────────────────────────────────────────┘

Iteration 2: In LEFT subtree, split by length < 60
┌────────────────────────────────────────┐
│   0.08 │ ●●●●●●● │                    │
│        │ ●●●●●●● │ (Query 1 area)    │
│  0.05 ├ ●●●●●●●  │                    │
│        │ ●●●●●  │                      │
│  0.03 └─────────┴──────────────────    │
│        30  60  70  90     Length       │
│         ^ split point                  │
│ Result: Query 1 needs 2 total splits   │
└────────────────────────────────────────┘

Query 1: 2 splits
Query 2: 1 split
→ Query 2 is "easier" to isolate = Anomaly
```

**Kết Quả Isolation Forest:**
- FPR: 0.63%
- Detection Rate: 3.19% ← **Quá thấp!**
- AUC: 0.670 ← **Thấp!**

**Tại Sao Isolation Forest Kém Hơn One-Class SVM?**

```
Isolation Forest:
- Phụ thuộc vào random splits
- Không học "shape" của normal cluster
- Khi anomaly/normal features overlap
  → cần nhiều splits để separate
  → depth similar for both
  → AUC thấp

One-Class SVM:
- Explicitly learns boundary around normal
- Sử dụng kernel trick (RBF) để capture non-linear shapes
- Toán học tối ưu (convex problem)
- Kết quả: AUC 0.902 (vs 0.670)
```

---

#### **7.3.2 Isolation Forest - Kiến Trúc & Thuật Toán**

**Architecture: Random Forest of Isolation Trees**

```
Isolation Forest = Ensemble của 100 trees
├─ Input: 73,548 benign queries × 4 features
├─ Tree 1: Random splits → path length
├─ Tree 2: Random splits → path length
├─ ...
├─ Tree 100: Random splits → path length
└─ Output: Average path length → Anomaly score
```

**Algorithm: Random Isolation Tree**

```python
def build_isolation_tree(data, current_depth=0):
    if len(data) <= 1 or depth > max_depth:
        return Leaf(size=len(data), depth=current_depth)
    
    # Random feature & threshold
    feature = random_choice([length, special_ratio, keywords, entropy])
    threshold = random_uniform(min_val, max_val)
    
    # Split
    left = data[feature < threshold]
    right = data[feature >= threshold]
    
    # Recursively build left & right
    return Node(
        left_tree = build_isolation_tree(left, depth+1),
        right_tree = build_isolation_tree(right, depth+1)
    )
```

**Anomaly Score Calculation**

```
For each query:
├─ Run through all 100 trees
├─ Count: "how many splits until isolated?"
│   Normal query: 3-4 splits (clustered with others)
│   Anomaly query: 1-2 splits (immediately separated)
└─ Average path length → Anomaly score

Formula: score = 2^(-avg_length / c)
├─ avg_length = 1.8 (anomaly) → score = 0.56 (anomalous)
└─ avg_length = 3.2 (normal) → score = 0.41 (normal)
```

**Result: FPR 0.63%, DR 3.19%, AUC 0.670 ← Poor**

---

#### **7.3.3 One-Class SVM - Kiến Trúc & Thuật Toán**

**Architecture: Support Vector Machine with RBF Kernel**

```
One-Class SVM = Optimization problem
├─ Input: 73,548 benign queries × 4 features (NO anomalies in training)
├─ Kernel: RBF (Radial Basis Function) - learns non-linear boundary
├─ Solve: Find optimal hyperplane that encloses benign data
└─ Output: Decision function f(x) → Anomaly score
```

**Algorithm: Optimization Problem**

```
Mathematical formulation:

minimize: (1/2)||w||² + (1/ν·n)Σξᵢ - ρ

subject to:
  w·φ(xᵢ) ≥ ρ - ξᵢ  for all i
  ξᵢ ≥ 0

Interpretation:
├─ w = boundary normal vector
├─ φ(x) = RBF kernel feature map (4D → higher dimension)
├─ ν = 0.005 (allow ~0.5% outliers)
├─ ξᵢ = slack (penalty for violating boundary)
└─ ρ = threshold offset

Result: Support vectors (key benign queries defining boundary)
```

**RBF Kernel: Non-Linear Boundary**

```
Linear boundary (too simple):
┌─────────────────────┐
│  ●●●●│             │
│  ●●●│ (straight)   │
│  ●● │ can't fit    │
│  ● │  cluster      │
└─┴───┴───────────────┘

RBF boundary (curves around cluster):
┌─────────────────────┐
│  ●●●●╱╲            │
│  ●●●│  │ (curves)  │
│  ●● ╲──╱ tight     │
│  ●      cluster    │
└─────────────────────┘

RBF formula: K(x, x') = exp(-γ || x - x' ||²)

Distances:
├─ Query vs nearby query: γ=0.1, distance=5 → K ≈ 0.082 (similar)
└─ Query vs far query: γ=0.1, distance=13 → K ≈ 0 (different!)

Result: Tight boundary around benign cluster
```

**Anomaly Score: Decision Function**

```python
# After training, for each test query:
decision_score = Σ(αᵢ × K(x, support_vector_i)) - ρ

Example:
├─ Benign query: decision_score = -4.8 (deep inside)
│  → Very confidently normal
└─ Anomaly query: decision_score = +0.3 (outside)
   → Anomalous

Threshold: score > 0 = anomaly, score < 0 = normal
Distance to boundary: |score| = confidence level
```

**Result: FPR 0.30%, DR 20.7%, AUC 0.902 ← Excellent!**

---

#### **7.3.4 So Sánh Chi Tiết: Isolation Forest vs One-Class SVM**

```
2D Space: X=Keyword_Count, Y=Special_Char_Ratio

Normal queries cluster:  ●●●●
                        ●●●●●●
                       ●●●●●●

ISOLATION FOREST learns:
(Random axis-aligned splits)
    │
    ├─ length < 50
    │   ├─ keywords < 3: ✓ benign here
    │   └─ keywords ≥ 3: ✗ benign also here
    └─ length ≥ 50: (anomaly mixed with benign)

Problem: Random splits don't learn cluster shape
→ Overlap between isolation paths for benign & anomaly
→ AUC = 0.670 (poor)


ONE-CLASS SVM learns:
(RBF kernel, curved boundary)
                        ╱────╲
                        │ ●●● │  ← Tight boundary
                        │●●●●●│     around cluster
                        ╲────╱
                            ↓
                    Anomalies outside

Advantage: Explicitly learns boundary shape
→ Separates benign & anomaly clearly
→ AUC = 0.902 (excellent)
```

**Why One-Class SVM Wins:**

| Aspect | Isolation Forest | One-Class SVM |
| :---- | :---- | :---- |
| **Learning** | No learning, random splits | Explicitly learns boundary |
| **Boundary** | Axis-aligned, rigid | Non-linear (RBF), adaptive |
| **Feature interaction** | None | Captures via kernel trick |
| **Overlap handling** | Poor (random) | Good (convex optimization) |
| **AUC** | 0.670 | 0.902 |
| **DR @ 0.3% FPR** | 3.19% | 20.7% |

**One-Class SVM (7.3.3) achieves 0.30% FPR & 20.7% DR because:**

2D Space: X=Keyword_Count, Y=Special_Char_Ratio

Normal queries cluster:  ●●●●
                        ●●●●●●
                       ●●●●●●

One-Class SVM learns:   ╱────╲
                        │ ●●● │  ← Everything inside = normal
                        │●●●●●│
                        ╲────╱
                            ↓
Anomaly outside boundary = attack
```

**Kết quả:**
- FPR: 0.30%
- Detection Rate: 20.73%
- AUC: 0.902

**Tại sao One-Class SVM tốt hơn?**
- Isolation Forest: naive (chỉ dùng depth)
- One-Class SVM: learns actual distribution shape
- OCSVM AUC (0.902) >> Isolation Forest (0.670)

---

### **7.2 Data Distribution & Threshold Operating Points**

#### **7.2.1 Phân Bố Dữ Liệu (Data Distribution)**

**Training Set (Benign Only):**
- 73,548 queries từ SQLiV3 + CSIC 2010 + SR-BH 2020
- Tất cả gắn nhãn "benign" (sau content filtering)
- Không chứa attack payload

**4 Feature Statistics trên Benign Pool:**

```
Feature Distribution (Benign queries):

1. LENGTH (độ dài):
   Min: 15 chars
   Q1:  38 chars  ┐
   Q2:  50 chars  │ Interquartile range
   Q3:  72 chars  │ (50% of data)
   Max: 500+ chars
   
   Visualization:
   Count │
         │              ╱╲
         │             ╱  ╲
         │            ╱    ╲
         │           ╱      ╲      ← Normal distribution
         │          ╱        ╲       (Gaussian-like)
         │         ╱          ╲
         │        ╱            ╲
         └───────┴──────────────┴──────
           15    38  50  72    150   500
           Length (chars)

2. SPECIAL_CHAR_RATIO (tỷ lệ ký tự đặc biệt):
   Min:  0.5%
   Q1:   4%     ┐
   Q2:   5.2%   │ Most benign queries: 4-7%
   Q3:   7%     │
   Max:  15%    ┘
   
   Visualization:
   Count │
         │
         │        ████████
         │        ████████  ← Peak at 5%
         │      ██████████
         │      ██████████
         │   ██████████████
         └───┴──────┴──────┴──────
         0.5% 4%  5.2%  7%  15%
         Special Char Ratio

3. SQL_KEYWORD_COUNT (đếm từ khóa):
   Min:  0 (không có keyword)
   Q1:   2
   Q2:   3     ┐
   Q3:   4     │ Most benign: 2-5 keywords
   Max:  15    ┘
   
   Visualization:
   Count │
         │
         │     ███████
         │     ███████   ← Peak at 3
         │   ███████████
         │   ███████████
         │ █████████████
         └─┴─┴──┴──┴──┴──┴──┴──
         0 1 2  3  4  5  6  7  15
         SQL Keyword Count

4. ENTROPY (Shannon entropy):
   Min:  2.5
   Q1:   4.0    ┐
   Q2:   4.2    │ Most benign: 4.0-4.4
   Q3:   4.4    │
   Max:  5.2    ┘
   
   Visualization:
   Count │
         │
         │              ╱╲
         │             ╱  ╲
         │            ╱    ╲  ← Normal distribution
         │           ╱      ╲   (centered ~4.2)
         │          ╱        ╲
         │         ╱          ╱
         │        ╱          ╱
         └───────┴──────────┴───────
         2.5   4.0  4.2  4.4  5.2
         Entropy
```

**Evaluation Set (Anomalous, Multi-Attack-Type):**
- 25,065 queries từ CSIC 2010
- Mix attack types: SQLi, XSS, path traversal, buffer overflow
- Re-labeled as "anomalous" (không SQLi-specific)

**4 Feature Statistics trên Anomalous Pool:**

```
Feature Comparison:

Metric              │ Benign Pool    │ Anomalous Pool  │ Difference
────────────────────┼────────────────┼─────────────────┼───────────
LENGTH              │ 50 (median)    │ 75 (median)     │ +50% longer
SPECIAL_CHAR_RATIO  │ 5.2% (median)  │ 8.5% (median)   │ +63% more special
SQL_KEYWORD_COUNT   │ 3 (median)     │ 3.2 (median)    │ +6% keywords
ENTROPY             │ 4.2 (median)   │ 4.4 (median)    │ +4.7% entropy

Visualized in 2D (Length vs Special Ratio):

┌──────────────────────────────────────────────────┐
│ Y-axis: Special_Char_Ratio (%)                   │
│                                                   │
│  15%  ├─ ╱╲ ╱╲
│       ├─╱ ╱╲╱ ╲        ← Anomalous queries
│  10%  ├─    ╱╱╲╲╱╲      (scattered, higher ratio)
│       ├─  ╱╱ ╱╱ ╲╱
│   5%  ├─●●●●●●●●●●     ← Benign cluster
│       ├─●●●●●●●●●
│       ├─ ●●●●●●●●      (tight, centered)
│  0.5% ├──────────────────
│       └──────┴────┴────┴──────
│       15    50   75  150  500
│       Length (chars) → X-axis
│
└──────────────────────────────────────────────────┘

→ Benign (●) forms tight cluster ở (50-70 length, 4-7% ratio)
→ Anomalous (╱╲) scattered ở periphery (length vary, ratio 8-15%)
```

---

#### **7.2.2 Threshold & Operating Points (Điểm Hoạt Động)**

**Vấn đề:** Tính anomaly score là liên tục, nhưng cần **quyết định binary** (normal vs anomaly)

```
Anomaly Score Distribution:

Normal queries:    ███████████         (Centered ~-4.5)
                  ███████
                 ███

Anomalous queries:        ██████████  (Spread from -2 to +1)
                          ███████
                         ███
```

**Threshold = -0.5** (ví dụ):
- Score < -0.5 → Normal
- Score ≥ -0.5 → Anomaly

**Nhưng threshold khác nhau → kết quả khác:**

| Threshold | FPR | Detection Rate | Precision | Ứng Dụng |
| :---- | :---- | :---- | :---- | :---- |
| **-0.8** (deployed) | 0.3% | 20.7% | 99.8% | Conservative (ít false alarm) |
| -0.5 | 3.2% | 33.2% | 98.9% | Balanced |
| -0.2 | 13.4% | 65.6% | 97.6% | Aggressive |
| +0.2 | 30.6% | 97.1% | 96.4% | Very aggressive |

**Tại sao detection rate chỉ 20.7% ở deployed point?**

→ **Cố ý chọn conservative** (threshold cao) để:
- Giảm false positive (0.3% = 9 false alarms per 3000 benign queries)
- Admin overhead từ Overkill policy (HOLD xin confirm)
- Prioritize security (không bỏ qua attack) > convenience (không false alarm)

**Nếu muốn detection rate 97% → phải chấp nhận 30.6% false positive**
→ **Not practical** (3,000 benign queries → 918 false alarms)

---

## **PHẦN 8: CÁC LỰA CHỌN KHÁC (Alternative Approaches)**

Tham khảo: **Section 1.5.1 (CNN), 1.7.1 (Isolation Forest) của report**

### **8.1 CNN + SQL-Specific Tokenizer**

#### **8.1.1 Tokenization: Raw String → Tokens**

**SQL-Specific Tokenizer:**

```python
query = "SELECT * FROM users WHERE id=1' OR '1'='1"

Tokenized:
[SELECT] [*] [FROM] [users] [WHERE] [id] [=] [1] ['] [OR] ['] [1] ['] [=] ['] [1]
  ↓      ↓    ↓      ↓       ↓      ↓    ↓   ↓    ↓   ↓    ↓   ↓    ↓   ↓    ↓   ↓
 T1     T2   T3     T4      T5     T6   T7  T8   T9  T10  T11 T12  T13 T14  T15 T16

Token ID mapping (Vocabulary):
├─ SELECT = 1
├─ * = 2
├─ FROM = 3
├─ WHERE = 5
├─ OR = 10
├─ ' = 50 (quote)
└─ [UNK] = 999 (unknown/rare tokens)

Result: [1, 2, 3, 4, 5, 6, 7, 8, 50, 10, 50, 8, 50, 7, 50, 8]
        (Numerical representation)

Why SQL-specific?
- Handles SQL operators: =, <>, <, >, <=, >=, IN, LIKE, BETWEEN
- Handles SQL keywords: SELECT, FROM, WHERE, AND, OR, UNION, DROP, SLEEP
- Preserves quote/comment structure: ', ", --, /*, */
- More precise than generic word tokenizer
```

---

#### **8.1.2 Embedding Layer: Tokens → Dense Vectors**

**Ý tưởng Chính:**
```
Token = Integer ID (sparse, one dimension)
       ↓
Embedding Layer
       ↓
Dense Vector in N-dimensional space (dense, many dimensions)
```

**Embedding Table (Learned during training):**

```python
embedding_layer = tf.keras.layers.Embedding(
    input_dim=1000,      # Vocabulary size (1000 unique tokens)
    output_dim=64,       # Each token → 64-dimensional vector
    input_length=50      # Max query length (pad/truncate to 50 tokens)
)

Embedding matrix (1000 × 64):
        dim1  dim2  dim3  ... dim64
┌─────────────────────────────────┐
│ Token 1 (SELECT):   [0.2, -0.1, 0.5, ..., 0.3]
│ Token 2 (*):        [0.1,  0.3, -0.2, ..., -0.1]
│ Token 3 (FROM):     [-0.4, 0.2, 0.3, ..., 0.2]
│ ...
│ Token 50 ('):       [0.5, 0.7, 0.1, ..., 0.6]  ← Quote has HIGH values
│ Token 10 (OR):      [0.3, -0.2, 0.4, ..., 0.2]
└─────────────────────────────────┘

During training:
- Attack queries have quotes + OR → embedding learns to associate them
- These tokens' vectors move CLOSER together
- Model learns: "quotes + OR" = attack pattern
```

**Example Transformation:**

```
Input token IDs:     [1, 2, 3, 4, 5, 6, 7, 8, 50, 10, 50, 8, 50, 7, 50, 8, ...]
                      SELECT  * FROM users WHERE id = 1 '  OR  '  1  '  =  '  1

                      ↓ (Embedding lookup)

Output vectors (64D each):
[
  [0.2, -0.1, 0.5, ..., 0.3],    # SELECT embedding
  [0.1,  0.3, -0.2, ..., -0.1],  # * embedding
  [-0.4, 0.2, 0.3, ..., 0.2],    # FROM embedding
  [0.15, 0.25, 0.1, ..., 0.15],  # users embedding
  [0.3, -0.15, 0.4, ..., 0.25],  # WHERE embedding
  [0.05, 0.1, 0.2, ..., 0.1],    # id embedding
  [0.1, 0.2, 0.15, ..., 0.05],   # = embedding
  [-0.2, 0.1, 0.3, ..., 0.2],    # 1 embedding
  [0.5, 0.7, 0.1, ..., 0.6],     # ' embedding (QUOTE)
  [0.3, -0.2, 0.4, ..., 0.2],    # OR embedding
  [0.5, 0.7, 0.1, ..., 0.6],     # ' embedding (QUOTE)
  ... (more 64D vectors)
]

Shape: (16 tokens, 64 dimensions)
       = 1024 float values total

→ Sequence of embeddings is input to Conv1D
```

---

#### **8.1.3 CNN Architecture (Conv1D Filters)**

**Filters học local patterns:**

```
Input sequence (16 × 64):
┌────────────────────────────────────────┐
│ [SELECT]  64D vector
│ [*]       64D vector
│ [FROM]    64D vector          ← Conv1D Filter 1 (window size 3)
│ [users]   64D vector             examines these 3 consecutive
│ [WHERE]   64D vector             tokens at a time
│ [id]      64D vector
│ [=]       64D vector          ← Conv1D Filter 2 (window size 4)
│ [1]       64D vector             looks at 4-token patterns
│ [']       64D vector
│ [OR]      64D vector
│ ...
└────────────────────────────────────────┘

Filter 1 (Size 3, learns 3-token patterns):
┌─────────────────────────────────────────┐
│ Convolution kernels (3 × 64 = 192 weights)
│
│ Location 1: [SELECT, *, FROM]
│ Location 2: [*, FROM, users]
│ Location 3: [FROM, users, WHERE]
│ Location 4: [users, WHERE, id]
│ ...
│ Location 14: [', =, ', 1]
│ → 14 output values from filter 1
│
│ Each output = "how much does this 3-token window look like 'attack'?"
└─────────────────────────────────────────┘

Filter 2 (Size 4, learns 4-token patterns):
├─ Looks at [SELECT, *, FROM, users]
├─ Looks at [*, FROM, users, WHERE]
├─ ...
├─ Looks at [=, ', 1, OR]  ← Attack pattern detected here!
└─ → 13 output values from filter 2

Multiple filters (e.g., 100 filters):
├─ Filter 1-10: Capture SQL syntax patterns
├─ Filter 11-50: Capture attack keywords (OR, UNION, DROP)
├─ Filter 51-100: Capture quote/comment patterns
└─ Total: 100 filters × different window sizes

Output from all filters:
[
  score_filter_1 = 0.2,  # "Not very attack-like"
  score_filter_2 = 0.8,  # "Very attack-like" (found ' OR ' pattern)
  score_filter_3 = 0.1,
  ...
  score_filter_100 = 0.9,
]
→ 100-dimensional representation
```

**Max Pooling (Extract Important Features):**

```
From 14 outputs of Filter 1: [0.2, 0.3, 0.5, 0.4, 0.6, 0.1, 0.7, ...]
Max Pooling → Take maximum: 0.7 (the most attack-like 3-token window)

From 13 outputs of Filter 2: [0.4, 0.8, 0.3, 0.9, 0.2, ...]
Max Pooling → Take maximum: 0.9 (found a very attack-like 4-token window)

Result:
[0.7, 0.9, ..., 0.6]  (100 values, one per filter)

Meaning:
- Filter 1 found something mildly attack-like (max=0.7)
- Filter 2 found something very attack-like (max=0.9)
- ...
→ Overall: Query is likely an attack
```

**Dense Layer (Final Decision):**

```
Input (100D): [0.7, 0.9, 0.6, 0.3, ..., 0.8]

Dense Layer: 100 → 5 classes
├─ Fully connected neurons
├─ Learn weights to combine filter outputs
└─ Output logits for each class

Softmax:
[logit_normal, logit_union, logit_error, logit_boolean, logit_time]
              ↓
[P(normal)=0.05, P(union)=0.02, P(error)=0.01, P(boolean)=0.89, P(time)=0.03]
              ↓
Predict: boolean_blind (highest probability)
```

**Training Process:**

```
Loss = Cross-Entropy(predicted_class, true_class)

Backpropagation:
1. Update Dense layer weights (which filter outputs matter most?)
2. Update Conv1D filter weights (what patterns indicate attack?)
3. Update Embedding layer (which tokens should cluster together?)

After training:
- Embeddings for quote+OR cluster together (attack signal)
- Filters learn to detect quote+OR sequences
- Dense layer learns to combine signals
- Model can classify new queries correctly
```

---

**Tại Sao CNN Không Được Chọn?**
- F1-macro: 0.9871 (kém LogReg 0.9849 chỉ 0.002 = negligible)
- Latency: 0.29 ms (nhanh nhất, nhưng LogReg 0.51 ms cũng acceptable)
- Model size: 118 KB (nhỏ nhất, nhưng LogReg 3.9 MB cũng reasonable)
- **Trade-off không đáng**: Tiết kiệm 0.2 ms + 3.8 MB **để đánh đổi với phức tạp hơn**
- LogReg: dễ deploy, dễ debug, stable
- CNN: yêu cầu TensorFlow, khó tune hyperparameter, overfitting risk cao

---

**Kết quả:**
- F1-macro: 0.9871
- Latency: 0.29 ms (fastest)
- Model size: 118 KB (smallest)

**Tại sao không chọn?**
- F1-macro kém 0.9% vs TF-IDF LogReg (0.9871 vs 0.9849) ← Trớn lằm
- Tuy nhanh nhất nhưng trade-off không đáng (chỉ tiết kiệm 0.2 ms)

---

### **8.2 DistilBERT (Fine-tuned Transformer)**

**Ý tưởng:**

```
Query: "SELECT * FROM users WHERE id=1' OR '1'='1"
    ↓
[BERT Tokenizer: subword tokens]
    ↓
[DistilBERT: 6 transformer layers]
    ├─ Layer 1: Learn character-level patterns
    ├─ Layer 2-5: Learn context (what comes before/after)
    └─ Layer 6: Learn semantic meaning
    ↓
[Classification Head]
    ↓
Output: [P(normal), P(union), ...]
```

**Kết quả:**
- F1-macro: 0.9919 (best!)
- Latency: 2.8 ms (GPU) / >50 ms (CPU)
- Model size: 256 MB (largest)
- Cost: Needs GPU

**Tại sao không chọn?**
- F1-macro cao nhất (+0.007%) → **không đáng với trade-off**
- Tốc độ 5× chậm hơn TF-IDF
- Model 65× lớn hơn
- Cần GPU (infrastructure cost)

**Kết luận:** Overkill cho bài toán này

---

## **PHẦN 9: KIỂM ĐỊNH & PHÂN TÍCH**

### **9.1 Tại Sao F1-macro 0.9822 Không Phải "Perfect"?**

**Lý do:**
- ~13% noise ở `boolean_blind` → model train trên dữ liệu sai
- ~10% noise ở `normal` → nhiễu này còn lại sau 3 vòng filtering
- Test set sạch hơn train set (phân vân nhưng vẫn còn noise)
- → True ceiling có thể là 0.96-0.97, không phải 0.99+

**Kết luận:** 0.9822 là tốt nhất có thể với dữ liệu hiện tại, không phải model perfection

---

### **9.2 Adversarial Robustness Gap**

**Vấn đề:** Tất cả kết quả trên **clean test set**

**Không test với:**
- Obfuscated payloads (payload bị encode/mangle)
- Semantic evasion (cùng logic, khác cách viết)
- Morphing attack (attacker biết model → cố tình bypass)

**→ Cần WAF-A-MoLE tool để generate adversarial examples (Future Work)**

---

## **PHẦN 10: ROADMAP HỌC TẬP ĐẦU ĐỦ**

Nếu bạn muốn hiểu **TOÀN BỘ**:

1. ✅ **Đọc Phần 0** (Foundation)
2. ✅ **Đọc Phần 1** (Types of SQLi)
3. ✅ **Đọc Phần 2** (System Architecture)
4. ✅ **Đọc Phần 3** (Data Sources)
5. ✅ **Đọc Phần 4** (Preprocessing)
6. ✅ **Đọc Phần 5** (Feature Engineering)
7. ✅ **Đọc Phần 6** (Branch 1)
8. ✅ **Đọc Phần 7** (Branch 2)
9. ⏳ **Đọc Phần 8** (Alternatives) — Optional, chỉ nếu muốn biết tại sao không chọn CNN/DistilBERT
10. ✅ **Đọc Phần 9** (Limitations)
11. ✅ **Đọc Chapter 1-2 của Report** (Đầy đủ chi tiết, references)

---

## **TỌC TẮT THUẬT NGỮ**

| Thuật Ngữ | Viết Tắt | Ý Nghĩa |
| :---- | :---- | :---- |
| False Positive Rate | FPR | Tỷ lệ benign bị phát hiện là attack |
| Detection Rate | DR | Tỷ lệ attack được phát hiện |
| Area Under ROC Curve | AUC | Đo lường chất lượng mô hình (0=tệ, 1=tốt) |
| Term Frequency - Inverse Doc Freq | TF-IDF | Phương pháp trích đặc trưng văn bản |
| One-Class Support Vector Machine | OCSVM | Anomaly detector |
| F1-macro | F1 | Trung bình F1 của tất cả lớp |
| Precision | PRE | Trong những predict là attack, bao nhiêu đúng? |
| Recall (Sensitivity) | REC | Trong những attack thật, bao nhiêu được phát hiện? |

---

**Hết. Chúc bạn học tốt!**
