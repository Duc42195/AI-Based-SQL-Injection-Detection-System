# Tổng hợp comment của thầy Linh Dinh-Van — bản review RIVF 2026

> Nguồn: `report/conf/RVIF_2026___AI_for_SQLi_Linh comment.pdf` (annotate bằng Edge, ngày 24/08/2026).
> Trích xuất từ PDF annotations (author = "Van Linh"). Vị trí được đối chiếu với
> `report/conf/rivf2026_paper.tex` (số dòng theo bản tex hiện tại).
> Các mục đánh dấu ⚠️ là yêu cầu **rà soát toàn paper**, không chỉ một chỗ.
> Cột **Tiến độ**: `☐` = chưa làm, `🔄` = đang làm, `✅` = xong, `⏭️` = bỏ qua/không áp dụng.

---

## 1. Comment theo từng vị trí trong bài

### Trang 1 — Title / Authors / Abstract

| # | Vị trí | Comment của thầy | Ghi chú | Tiến độ |
|---|---|---|---|---|
| 1 | **Abstract** — highlight mở đầu "Abstract—SQL Injection (SQLi) remains one of the most…" (tex 59–61) | *"Nên viết ngắn gọn hơn. Chỉ khoảng 200–250 words thôi."* | Abstract hiện ~380 words | ☐ |
| 2 | **Khối tác giả** — vùng highlight quanh `[TODO: dept] … International School, Vietnam National University, Hanoi` (tex 21–54) | *"Bỏ ':', có thể ghi 'including'."* | Anchor chính xác chưa rõ từ extract — khả năng cao là câu có dấu hai chấm ở trang 1; cần mở PDF đối chiếu trực tiếp | ☐ |
| 3 | **Abstract — chỗ dùng dấu gạch ngang** — câu `"…a validation gate --- backed by an ablation confirming the gain is attributable to the class itself, not merely to more data --- promotes…"` (tex 60) | *"Hạn chế các dấu '-' vì người đọc sẽ nghĩ rằng mình đang dùng ChatGPT để viết hộ."* | | ✅ |
| 4 | **Abstract — câu có dấu hai chấm** — khả năng: `"…unseen at training time: supervised classification remains robust…"` hoặc `"…rather than a synthetic stand-in: a review queue and…"` (tex 60) | *"Including."* | Thay cấu trúc hai chấm bằng cách viết dùng "including"; cần đối chiếu PDF để biết đúng câu | ☐ |
| 5 | **Introduction — đoạn thứ nhất** — tex 68: "Web applications store increasingly sensitive data… escalate privileges." | *"Đoạn thứ nhất này nên có trích dẫn."* | | ☐ |
| 6 | **Abstract / trang 1 — một câu khác có dấu hai chấm** | *"Including."* | Như mục 4; cần đối chiếu PDF để biết đúng câu | ☐ |

### Trang 2 — Introduction / Related Work

| # | Vị trí | Comment của thầy | Ghi chú | Tiến độ |
|---|---|---|---|---|
| 7 | **Introduction — đoạn trước danh sách contributions** (tex 72–80) | *"Mô tả tóm tắt thêm 1 chút về proposed method của mình. Sau đó thêm 1–2 câu tóm tắt kết quả đạt được trước khi nói về main contributions của paper này."* | | ☐ |
| 8 | **Fig. 1 (kiến trúc hệ thống)** (tex 97–103, caption dòng 101) | *"Figure này khá mờ. Caption dài quá. Nên để hình này trải dài trên double column (`figure*`) và phần mô tả hình nên để ở đoạn văn."* | Tex hiện vẫn là placeholder box `[Architecture diagram --- TODO]`; ảnh thật nằm ở `report/conf/diagrams/` | ☐ |
| 9 | **Danh sách Contributions** (tex 74–80, hiện 5 bullet) | *"Contributions quá dài. Ngắn gọn lại — đâu mới thực sự là cái mới, cái đóng góp khoa học của paper. Paper hội thảo chỉ nên để 3 contributions và viết ngắn gọn hơn."* | | ☐ |
| 10 | ⚠️ **Toàn paper — dấu gạch ngang** (`---` / em-dash, ví dụ tex dòng 79, 145, 151, 159…) | *"Rà soát toàn bộ paper, chỗ nào có '-' thì bỏ và viết lại câu, để tránh người đọc bảo mình dùng ChatGPT."* | | ✅ |
| 11 | ⚠️ **Toàn paper — từ viết tắt** | *"Rà soát lại từ viết tắt. Nếu xuất hiện lần đầu thì phải ghi tên đầy đủ."* | Ví dụ cần kiểm tra: WAF, ML, FPR, DR, PSI, TF-IDF, LOF, CNN, GRU, LSTM, CAPEC… | ☐ |
| 12 | **Related Work — câu có ':' giữa câu** (tex 85–88, đoạn "Traditional SQLi defenses rely on input validation…" và "ML-based detectors extract features from queries—bag-of-words, TF-IDF, or character/word n-grams—and train classifiers…") | *"Nên rà soát lại các câu này. Tại sao lại ':' ở giữa câu. Câu này nên tách thành các câu nhỏ hoặc viết đơn giản hơn cho dễ hiểu."* | | ☐ |
| 13 | **Related Work — toàn đoạn** (tex 84–89) | *"Các related works đưa ra này phải phân tích được những ưu điểm và nhược điểm của nó, để từ đó làm nổi bật lên research gap mà mình cần giải quyết trong bài này là gì."* | | ☐ |
| 14 | **Related Work — đoạn traditional defenses** (tex 85) | *"Tìm thêm các bài về traditional SQLi defenses, phân tích qua 1 chút ưu điểm, nhược điểm của nó, sau đó kết luận phương pháp này không còn hiệu quả nên mới chuyển sang ML-based methods."* | Cần bổ sung tham khảo [refs] cho WAF/rule-based | ☐ |
| 15 | **Fig. 1 — vị trí đặt hình** (tex 97) | *"Theo format của IEEE thì Figure phải xuất hiện sau đoạn văn nhắc đến nó. Vì vậy các em nên đặt lại Fig. 1."* | | ☐ |
| 16 | **Section III Proposed System (toàn section)** (tex 91–137) | *"Nên viết proposed method dưới dạng cấu trúc giải thuật (pseudo-code). Các đoạn văn mô tả proposed method khá dài, toàn chữ. Nên dùng cấu trúc giải thuật hoặc mô hình toán học hoặc hình vẽ để paper có hàm lượng khoa học cao hơn."* | | ☐ |

### Trang 4 — Dataset & Experimental Setup

| # | Vị trí | Comment của thầy | Ghi chú | Tiến độ |
|---|---|---|---|---|
| 17 | ⚠️ **In đậm trong đoạn văn** — ví dụ tex dòng 151: `\textbf{Blind-SQLi sessions}`, `\textbf{Query-splitting sessions}` | *"Không nên in đậm các chữ trong đoạn văn. Đây là cách viết của ChatGPT. Rà soát lại toàn bộ bài báo, chỗ nào in đậm thì sửa lại."* | | ☐ |
| 18 | **Session Correlator Dataset — ký tự "/"** — tex dòng 151: "split 1,120 train / 280 test" | *"'train/280 tests' — rà soát lại trong bài nhiều chỗ ký tự '/' đang không sát với ngữ cảnh chữ."* | Viết bằng chữ: "1,120 training and 280 test sessions" | ☐ |
| 19 | ⚠️ **Toàn paper — thì của động từ** | *"Các câu tiếng Anh trong paper nên để ở thì hiện tại đơn. Hạn chế để ở quá khứ. Rà soát lại toàn bộ paper."* | | ☐ |
| 20 | **Data Sources** (tex 141–142: SQLiV3 / CSIC 2010 / payload-box / SR-BH 2020) | *"Check lại xem các tập dữ liệu này có mới không? Nếu từ những năm 2010 thì nó đã quá cũ. Check xem các tập dữ liệu này có đủ lớn không? Bình thường các paper khác họ đang dùng tập dữ liệu nào, độ lớn thế nào?"* | Cần so sánh với datasets mà các paper gần đây dùng + biện luận tại sao vẫn chọn bộ này | ☐ |

### Trang 5 — Experimental Results (Branch 1 / Branch 2)

| # | Vị trí | Comment của thầy | Ghi chú | Tiến độ |
|---|---|---|---|---|
| 21 | **Table II (Branch 1 architecture comparison)** — highlight "Table II compares the four candidate architectures…" (tex 159–163) | *"Lưu ý cách trình bày. Table và figures phải xuất hiện sau khi đã nhắc tới trong đoạn văn."* | | ☐ |
| 22 | **Fig. 3 (Branch 2 threshold trade-off)** — vùng highlight caption Fig. 2/Fig. 3 (tex 224–228) | *"Phân tích chi tiết hơn kết quả Figure 3. Chú ý rà soát lại kết quả của các Figure, cần phân tích chi tiết."* | | ☐ |
| 23 | ⚠️ **Phần Results nói chung** (tex 156–305) | *"Nhiều đoạn nên viết ngắn gọn hơn hoặc cắt bớt đi. Nếu có dùng ChatGPT để phân tích kết quả thì nên viết lại cho ngắn gọn hơn. Thế mới đủ được 6 trang đôi."* | | ☐ |

### Trang 6 — Session Correlator results

| # | Vị trí | Comment của thầy | Ghi chú | Tiến độ |
|---|---|---|---|---|
| 24 | **Table III (Session Correlator ablation)** — caption tex dòng 256: "Session Correlator ablation on held-out self-hosted sessions (n=280; 70 benign, 70 per attack class)…" | *"Tên các table đang dài quá."* | | ☐ |

### Trang 8 — Discussion/Limitations (phần cuối)

| # | Vị trí | Comment của thầy | Ghi chú | Tiến độ |
|---|---|---|---|---|
| 25 | **Phần nội dung trang 8** | *"Phần này nên lồng ghép vào nội dung trên hoặc bỏ thì mới co lại đủ 6 trang đôi được."* | | ☐ |

### Trang 9 — Conclusion

| # | Vị trí | Comment của thầy | Ghi chú | Tiến độ |
|---|---|---|---|---|
| 26 | **Conclusion and Future Work** (tex 326+) | *"Nên viết ngắn gọn hơn. Chỉ cần bảo paper này chúng tôi đề xuất gì, kết quả đạt được ra sao, future work thế nào."* | | ☐ |

---

## 2. Comment chung (yêu cầu rà soát TOÀN BỘ paper)

| # | Yêu cầu | Ghi chú thực thi | Tiến độ |
|---|---|---|---|
| G1 | **Bỏ hết dấu gạch ngang câu (`---`/em-dash), viết lại câu** | Tránh bị coi là viết bằng ChatGPT. Tìm `---` trong tex | ✅ |
| G2 | **Bỏ in đậm (\textbf/\emph nhấn mạnh) trong đoạn văn body** | Chỉ giữ đậm ở header bảng/cột | ☐ |
| G3 | **Từ viết tắt lần đầu xuất hiện phải ghi tên đầy đủ** | WAF, FPR, DR, PSI, LOF, TF-IDF, CAPEC… | ☐ |
| G4 | **Dùng thì hiện tại đơn, hạn chế quá khứ** | Đổi "was measured/were generated/attained" → hiện tại | ☐ |
| G5 | **Table/Figure phải nằm SAU đoạn văn first-reference** | Kiểm tra float placement của tất cả figure/table | ☐ |
| G6 | **Tránh kiểu văn ChatGPT**: dấu `-`, in đậm, câu dài nhiều mệnh đề, dấu `:` và `/` giữa câu | Viết câu ngắn, đơn giản | ☐ |
| G7 | **Giới hạn độ dài: 6 trang đôi (IEEE)** | Cắt bớt Results/Discussion, gộp phần trang 8 | ☐ |

---

## 3. Việc cần làm ngoài sửa chữ (action items)

| # | Việc | Liên quan | Tiến độ |
|---|---|---|---|
| A1 | Thay placeholder Fig. 1 bằng ảnh thật từ `report/conf/diagrams/`, dựng `figure*` double-column, viết caption ngắn + chuyển mô tả vào đoạn văn (mục 8). | #8, #15 | ☐ |
| A2 | Bổ sung references cho traditional SQLi defenses + phân tích ưu/nhược điểm trước khi chuyển sang ML (mục 13–14). | #13, #14 | ☐ |
| A3 | Viết pseudo-code (algorithm environment) cho Session Correlator / decision engine (mục 16). | #16 | ☐ |
| A4 | Rút gọn Abstract xuống 200–250 words (mục 1). | #1, #3, #4, #6 | ☐ |
| A5 | Rút contributions còn 3 bullet (mục 9). | #9 | ☐ |
| A6 | Thêm citations cho Introduction đoạn 1 (mục 5). | #5 | ☐ |
| A7 | So sánh dataset với các paper gần đây (độ lớn, độ mới) và biện luận (mục 20). | #20 | ☐ |
| A8 | Co paper về đúng 6 trang đôi. | #23, #25, #26, G7 | ☐ |