# Prompt cập nhật 02 — Contract 1.1.1 → 1.1.4 (tăng ca gộp vào chấm công, tổng hợp lấy từ bảng công, ảnh nhân viên)

> Gửi kèm `API_CONTRACT.md` **bản 1.1.4**. Copy toàn bộ phần dưới đường kẻ vào phiên Claude Code của dự án
> Mini App. Bao gồm cả câu trả lời cho `QUESTIONS_FOR_BACKEND.md` mục 15–19 và 2 yêu cầu "Overtime
> Integration into Attendance", "get_attendance_summary — provisional flag".

---

## Thay đổi backend (contract 1.1 → 1.1.4)

Đọc lại trong contract: changelog cuối file, `get_attendance_calendar`, `get_attendance_day`,
`get_attendance_summary`, `get_overtime`, `get_home`, khối `Employee`, bảng `login.result`.

### 1. Tăng ca gộp vào chấm công (1.1.3 — theo yêu cầu của Mini App)
- `get_attendance_calendar` thêm:
  - `overtime_summary: { actual_hours, approved_hours }` — tổng giờ tăng ca **thực tính** / **được duyệt** của
    **tháng dương lịch** `month`, cộng từ bảng công;
  - `days[].overtime_hours` — giờ tăng ca thực tính của ngày, `null` khi không có.
- `get_attendance_day` thêm:
  - `approved_overtime_hours` — `null` khi ngày chưa có bảng công;
  - `overtime_registrations[]: { id, date, weekday_label, begin, end, hours, reason, status, status_label }`.
- **Khác với đề xuất của Mini App:** phiếu tăng ca lấy từ `Overtime Registration` (TIQN không dùng doctype
  `Overtime Request` — 0 bản ghi). Trạng thái: `APPROVED` (Đã duyệt) · `PENDING` (Chờ duyệt) · `REGISTERED`
  (Đã đăng ký — phiếu nháp mà hệ thống **đang tính công**; hiện là **toàn bộ** phiếu) · `DRAFT` (Bản nháp —
  chỉ khi TIQN tắt tính phiếu nháp). Dùng `status_label` của server, đừng tự dịch.
- `get_config().features.overtime = false` ⇒ `overtime_summary: null`, mọi `days[].overtime_hours: null`,
  `overtime_registrations: []`. Ẩn phần tăng ca khi cờ này tắt.
- `get_overtime` không còn dùng (vẫn chạy). Xoá code gọi nó khi đã bỏ tab "Tăng ca".

### 2. Tổng hợp công luôn lấy từ bảng công (1.1.4)
- `get_attendance_summary` và `get_home.attendance` / `get_home.overtime` **luôn cộng từ bảng công của kỳ
  26 → 25**, kể cả khi kỳ đã có phiếu lương. Trước đây kỳ đã phát hành phiếu thì lấy số từ phiếu — đã bỏ.
- `source` (`payable_days.source`, `overtime.source`, `attendance.source`, `overtime.source` của `get_home`)
  **luôn `"ERP"`**. Xoá mọi nhánh xử lý `"PAYSLIP"` (vd. nhãn "Theo phiếu lương").
- `provisional` định nghĩa lại: `true` khi C&B **còn được điều chỉnh** công của kỳ — hôm nay ≤ `adjust_until`
  (mùng 4 tháng sau). Sau đó `false`. Không còn phụ thuộc phiếu lương.
  Ví dụ ngày 15/10/2026: kỳ 2026-10 → `true`; kỳ 2026-09 trở về trước → `false`.
- Badge: `provisional = true` → "Tạm tính đến {as_of}"; `false` → "Đã chốt công". Câu gợi ý dưới tổng hợp:
  "Số liệu chấm công. Số được trả lương xem ở phiếu lương." (hai nơi có thể lệch nếu C&B điều chỉnh khi tính
  lương — đó là số thật, đừng che).
- Trả lời yêu cầu "provisional flag": không phải lỗi — kỳ 07/08/09 trả `false` vì đang có phiếu lương **số
  giả** để test. Với 1.1.4 thì cờ này không còn dính tới phiếu lương nữa.

### 3. Hồ sơ nhân viên (1.1.1, 1.1.2)
- `employee.designation` = **chức danh tiếng Việt** (vd. "Tổ phó IT"); `group` = tổ/nhóm. Áp dụng `login`,
  `me`, `get_home`, `approver.designation`.
- `employee.avatar_url` = **URL tuyệt đối** tới ảnh nhân viên (đã mã hoá URL, có `?v=` đổi khi chụp lại ảnh),
  tải trực tiếp không cần header. **Đừng tự ghép tên tệp** `{employee_id} {employee_name}.jpg` — đuôi có thể
  `.png`. `null` hoặc ảnh tải lỗi → hiện `initials`.

### 4. Đơn nghỉ (trả lời mục 15, 16)
- `get_leave_form` thuộc M3, **chưa có**. Chỉ hiện nút "Tạo đơn nghỉ" khi `get_config().features.leave_create
  = true` (đang `false`).
- `approver` của đơn có thể **`null`** (đơn phòng Nhân sự nhập tay — hiện là toàn bộ đơn) → ẩn dòng "Người duyệt".

### 5. Đăng nhập trên simulator (trả lời mục 19)
- Simulator/browser không có `access_token` ⇒ `login` luôn trả `ZALO_TOKEN_INVALID` "Thiếu mã truy cập Zalo"
  (không phải `NO_PHONE`). **Đừng gọi `login` khi `getAccessToken()` rỗng**; trong build dev dùng
  `dev_login(zalo_user_id)` (prompt cập nhật 01, mục C).
- Trong Zalo thật, `login(access_token)` không kèm `phone_token` dùng SĐT phòng Nhân sự gán (kể cả
  `Phone Source = Manual`) → `ACTIVE`.

### 6. Khác
- `READ_ONLY` (đã nghỉ việc, chỉ xem) mặc định **30 ngày** từ ngày nghỉ (trước 60). Đọc từ
  `get_config().read_only_days`, đừng hard-code.
- Request chạy song song sau khi phiên bị thu hồi giờ trả **cùng** `details.reason` / `details.result`
  (trước có thể ra `REVOKED` lẫn `STATUS_CHANGED`) — không cần sửa gì, chỉ để biết.

## Việc cần làm ở Mini App
1. Kiểu dữ liệu: thêm `overtime_summary`, `days[].overtime_hours`, `approved_overtime_hours`,
   `overtime_registrations[]`; `OvertimeStatus` thêm `"DRAFT"`; `source` chỉ còn `"ERP"`.
2. Màn Chấm công & tăng ca: dùng `overtime_summary`; chấm/nhãn giờ tăng ca theo `days[].overtime_hours`;
   ẩn khi `features.overtime = false`.
3. Màn chi tiết ngày: hiện `overtime_hours`, `approved_overtime_hours`, danh sách `overtime_registrations`
   (giờ bắt đầu–kết thúc, số giờ, lý do, `status_label`).
4. Màn tổng hợp + thẻ công ở trang chủ: bỏ xử lý `PAYSLIP`; badge theo `provisional` mới.
5. Ảnh đại diện từ `avatar_url`, rơi về `initials`.
6. Mock: cập nhật theo contract 1.1.4.

## Trạng thái server
Đã code + test ở backend (210 test). Có hiệu lực qua HTTP **sau lần `bench restart` tới** — phía ERP sẽ báo.
Trước đó dựng UI bằng mock theo contract 1.1.4.

Sau khi làm xong: liệt kê thay đổi, và ghi mọi thắc mắc vào `QUESTIONS_FOR_BACKEND.md`.
