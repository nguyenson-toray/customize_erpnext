# Employee Quiz (trắc nghiệm kiểu MS Forms)

Mục đích chính: nhân viên mới làm bài kiểm tra sau buổi đào tạo, **không đăng nhập**.
Plan + các quyết định D1–D10: `/home/frappe/frappe-bench/.claude/plans/employee_quiz_form.md`.

## Thành phần
| Phần | File |
|---|---|
| DocType | `doctype/tiqn_quiz` (bài) · `tiqn_quiz_question` (câu, 6 lựa chọn A–F trên dòng) · `tiqn_quiz_employee` (NV được làm + kết quả) · `tiqn_quiz_response` (1 lượt làm) · `tiqn_quiz_answer` |
| Chấm điểm (hàm thuần) | `grading.py` |
| Vòng đời lượt làm | `service.py` — start / save_progress / finalize; `eligible_employees` + `latest_results` cho tab Results và report |
| API guest | `api/employee_quiz/quiz_api.py` |
| API Desk | `api/employee_quiz/quiz_admin_api.py` |
| Chọn NV (Add Employees / Paste Codes) | `api/employee_quiz/employee_picker.py` — chỉ TRẢ dòng, form tự thêm vào bảng rồi user Save 1 lần |
| Report | **1 report** `report/tiqn_quiz_result` (user chốt 20/10, thay 2 report Detail/Summary cũ): 1 dòng/lượt, nhiều bài; tick **Detail** → thêm cột trả lời + điểm từng câu kiểu Excel MS Forms (cần chọn 1 bài, không chọn thì báo). Lọc theo **Section** (`custom_section` đóng dấu lên Response lúc làm bài). Query + dòng "chưa làm" ở `report/quiz_report_utils.py`. Có trong Sidebar *Employee Quiz* và nút *Results ▸ Result Report* trên form. Bộ lọc Check luôn đặt cuối |
| Trang làm bài | `www/quiz/` → `/quiz?f=<slug>` (HR xem thử: `&preview=1`) |
| Role | `Quiz Manager` (patch `create_quiz_manager_role`, pre_model_sync) |
| Test | `bench --site erp.tiqn.local execute customize_erpnext.employee_quiz.test_employee_quiz.run` (rollback, không ghi DB) |

## Luồng
1. HR tạo bài → câu hỏi → tick **All Active Employees** hoặc thêm NV (nút *Add Employees* lọc theo ngày vào làm, *Paste Codes*) → *Quiz ▸ Open Quiz*. QR hiện ngay dưới **Quiz Link** trên form (bấm để phóng to — chiếu lên màn hình; nút *Download QR* tải file .svg để in).
2. NV mở link → tìm mã/tên (lọc ngay trên máy, bỏ dấu) → nhập **2 số ngày sinh hoặc bypass code** → Start → làm → Submit.
3. Kết quả ghi vào `TIQN Quiz Response` và cột trạng thái/điểm của bảng Employees; tab Results có tổng hợp + % đúng từng câu.

## Quy tắc / bẫy
- **Chữ ký** (21/10): TIQN Quiz `require_signature` (mặc định tắt) + `commitment_text`. Bật → cuối trang làm bài có thẻ "Cam kết & chữ ký" (pad giống /employee-self-update-info: canvas + pointer events, PNG nền trắng ≤ 600px); server bắt buộc tick (nếu có câu cam kết) + chữ ký, TRỪ khi hết giờ (`service.time_is_up`, lệch ±5s) để không mất bài; lưu `signature` (Signature), `commitment_confirmed` trên Response; thời điểm ký = `submitted_at` (đã bỏ `signed_on` 20/10 vì luôn trùng). Chỉ nhận `data:image/png;base64,` ≤ 400 KB.
- **Tab Employees** (21/10): ô lọc ngay trên tab (Date of Joining, Department, Section, Group) + Add Employees / Clear All, như Employee Self Update Info Setting; nút trên bảng: Employee Join Today, Paste Codes; Save tự bỏ dòng trùng. Danh sách trống được phép (không ai làm được tới khi thêm người hoặc tick All Active Employees). API `employee_picker` kiểm quyền GHI trên form gọi (`doctype` = TIQN Quiz | Employee Self Update Info Setting).
- **Bypass code tuỳ chọn** (20/10): để trống = chỉ nhận ngày sinh; không tự sinh khi tạo bài; KHÔNG hiện trên hộp QR (HR đọc trên form). `code_ok` phải kiểm `quiz.bypass_code` có giá trị trước khi so — `"".zfill(2)` = `"00"` từng làm mã `00` lọt qua.
- **100% trắc nghiệm** (user 20/10): không có Short text (không chấm tự động được), không True-False (= câu 1 đáp án với 2 lựa chọn Đúng/Sai). Mỗi câu ≥ 2 lựa chọn A–F; đáp án đúng = checkbox `is_correct_a..f` dưới từng lựa chọn. `question_type` + `correct_options` là **dẫn xuất** (`grading.derive_type`, JS `derive_question_type`): 1 tick = Single, ≥ 2 = Multiple. Grading/khoá đề/report vẫn đọc `correct_options`. Patch `quiz_correct_checkboxes` đã chuyển dữ liệu cũ. Cột `accepted_answers` còn trong DB (Frappe không xoá cột) nhưng không dùng.
- Bài **Draft** được lưu khi câu còn thiếu đáp án đúng (chỉ cảnh báo) — để import đề trước, điền đáp án sau; chuyển **Open** thì bắt buộc đủ.
- **Verify by Birth Day** (`verify_by_dob`, mặc định bật, 20/10): tắt → NV chọn tên là vào làm, không nhập mã; bypass code ẩn và không bị kiểm tra. `service.code_ok` trả True ngay; trang đọc `require_code` từ `get_quiz` (chỉ bỏ bước mã khi giá trị là `false` đúng nghĩa).
- Câu hỏi là **Text Editor** (HTML, định dạng tự do — 20/10). Trang làm bài đổ HTML thẳng (`grading.question_html`: câu cũ dạng chữ thường được escape + `<br>`); report/Desk dùng `grading.question_text` (bỏ thẻ). Lựa chọn A–F vẫn là chữ thường.
- `make_attachments_public = 1` trên **TIQN Quiz** và **TIQN Quiz Question**: ảnh dán vào Text Editor được Frappe tách ra file khi lưu, mặc định là PRIVATE → NV (guest) không xem được. Đừng tắt cờ này.
- Mỗi NV làm trên **điện thoại riêng** (user 20/10): không có nút "Người tiếp theo"/"Người khác làm bài". Chọn nhầm tên thì tải lại trang (đã bỏ nút *Đổi* 20/10 theo user).
- Add Employees / Paste Codes **không được bắt lưu trước**: bài Open + bảng NV rỗng thì không lưu được → vòng luẩn quẩn (bug 20/10). Nút Open/Close cũng tự lưu luôn thay đổi đang dở.
- **Không có biện pháp bảo mật** (D9, user chốt): ai biết số Response cũng nộp được; bypass code dùng chung cả lớp. Đừng đề xuất lại.
- Đáp án đúng **không** gửi xuống trình duyệt vì server chấm — không phải vì bảo mật.
- **Khoá đề** khi đã có lượt Submitted/Expired: CHỈ khoá câu hỏi + đáp án (`question_signature`: chữ câu hỏi, loại, điểm, lựa chọn A–F, đáp án đúng, đáp án chấp nhận; không thêm/xoá câu). Mọi cấu hình khác (bypass, giờ mở, số lần, danh sách NV, giải thích, ảnh, định dạng chữ) vẫn sửa được. Giá trị được chuẩn hoá trước khi so (form gửi `1`, DB giữ `1.0`; Text Editor bọc lại HTML) — so chuỗi thô từng làm khoá chặn nhầm mọi lần lưu (bug 20/10). Đổi đề → menu *Duplicate*.
- **Rút gọn 21/10 (user chốt, ưu tiên đơn giản):** bảng Employees CHỈ là danh sách được làm (không cột kết quả, không tự thêm dòng khi tick All Active Employees) — kết quả xem ở tab Results/report; **lượt tính điểm = lượt nộp SAU CÙNG** (không Score Policy); câu nhiều đáp án **đúng hết mới có điểm** (không Partial); không hẹn giờ mở/đóng (chỉ Open/Close); không `response_count`; nút form chỉ còn Open/Close, Copy Link, Preview, Result Report (QR trên form bấm để phóng to). Cho làm lại = **xoá bài nộp** (attempt_no = max + 1 nên không trùng) hoặc tăng Max Attempts. Không có Void.
- 🔴 **Sửa DocType JSON bằng script: GIỮ `field_order` của user.** User tự sắp bố cục (thêm Column Break) qua giao diện; dựng lại `field_order` từ mảng `fields` đã từng dồn hết cột xuống cuối → tab Results vỡ (21/10). Lấy lại bố cục cũ từ `tabVersion` (ref_doctype='DocType') — mỗi lần user lưu DocType có đủ field kèm `idx`.
- Hết giờ: server nhận nộp tới `deadline + 60s` (`deadline` = started_at + thời lượng, chụp lúc bắt đầu, nằm ở mục Technical); quá hạn → `Expired`, chấm phần autosave (`draft_answers`), bỏ qua bài gửi muộn.
- Còn 1 phút (`WARN_SECONDS` trong quiz.js): đồng hồ đỏ + hộp "Còn 1 phút!" hiện 1 lần (rung trên điện thoại); đang có hộp thoại khác thì chỉ toast; mở lại bài khi đã còn ≤ 1 phút thì không bật hộp.
- **Trang làm bài 100% tiếng Việt, viết cứng, KHÔNG qua `__()`/vi.csv** (user chốt 20/10/2026 — ngoại lệ của quy tắc English-first). Áp dụng cho `www/quiz/quiz.js`, các thông báo guest trong `quiz_api.py`/`service.py`. Desk (form TIQN Quiz, Response) vẫn English + vi.csv như thường.
- Ảnh câu hỏi: field `image` có `make_attachment_public=1` — ảnh private thì NV (guest) không xem được.
- Không đặt `.md`/ghi chú trong `www/quiz/` — mọi file không phải `.py` ở đó là public.
