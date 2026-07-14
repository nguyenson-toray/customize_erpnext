# Overtime Registration - Tài liệu

> Cập nhật 2026-07-14: redesign dialog "Get Employees" (1 dialog 2 cột + ledger giờ công),
> đổi tên hàm entry để tránh xung đột global scope, fix bug lệch ngày `toISOString()`.

## Tổng quan

Doctype đăng ký tăng ca theo lô: tổ trưởng chọn nhóm → tuần → ngày → khung giờ → danh sách
nhân viên, hệ thống sinh các dòng chi tiết vào bảng con `ot_employees`
(Overtime Registration Detail). Trước khi lưu có kiểm tra chế độ thai sản và xung đột
với OT đã duyệt (server-side).

## Dialog "Get Employees" (redesign 2026-07-14)

Nút **Actions → Get Employees** mở **một** dialog duy nhất (trước đây là 2 dialog lồng nhau).
Entry point: `show_ot_registration_dialog(frm)` trong `overtime_registration.js`.

### Bố cục 2 cột

```
┌───────────────────────────────────────────────────────────────┐
│  Select Employees for Overtime Registration                   │
├──────────────────────────┬────────────────────────────────────┤
│ Group    [Link, reqd]    │ Employee Selection                 │
│ Week     [3 nút tuần]    │ [🔍 tìm theo tên / mã NV]          │
│ Days     [6 ô lịch T2-T7]│ ┌────────────────────────────────┐ │
│ Begin | End Time         │ │ ☐ Select All   Showing N       │ │
│ Reason   [Small Text]    │ │ ☑ TIQN-0148  Nguyễn Văn A      │ │
│                          │ └────────────────────────────────┘ │
│                          │ Selected: 12   [chip ×][chip ×]…   │
├──────────────────────────┴────────────────────────────────────┤
│ 12 employees × 3 days × 2 h/day = 72 man-hours  [Add Selected]│
└───────────────────────────────────────────────────────────────┘
```

- **Cột trái (kế hoạch)**: Group (Link) → Week (segmented 3 tuần, kèm khoảng ngày) →
  Day tiles (ô kiểu tờ lịch: thứ + số ngày, chấm đánh dấu hôm nay, nút "Select All") →
  Begin/End Time (nằm cạnh nhau) → Reason (bắt buộc).
- **Cột phải (nhân viên)**: chọn Group là roster **tự tải ngay** (không cần dialog thứ 2);
  ô tìm kiếm lọc realtime có highlight; "Select All" áp dụng theo kết quả đang lọc;
  nhân viên đã chọn hiển thị thành chip có nút × và bộ đếm. Chọn được nhiều nhóm:
  đổi Group thì roster tải lại nhưng danh sách đã chọn (Map) giữ nguyên.
- **Ledger footer** (điểm nhấn): dòng tổng sống
  `{người} × {ngày} × {giờ/ngày} = {tổng giờ công}` cập nhật theo từng click;
  giờ sai (begin ≥ end) báo đỏ ngay tại footer.

### Hành vi quan trọng

| Hành vi | Chi tiết |
|---|---|
| Đổi tuần | **Xóa toàn bộ ngày đã chọn** (quyết định 2026-07-14, tránh đăng ký nhầm tuần); bấm lại tuần đang chọn thì không làm gì |
| Group bị khóa | `filter_employee_by = 'custom_group'` + `request_by_group` → Group pre-fill, khóa query, tự tải roster |
| Phân quyền | `get_user_filter_value()` đọc `filter_employee_by` (custom field, không nằm trong JSON doctype); sai nhóm → chặn kèm alert |
| Ngày của dòng con | Format local `ot_format_ymd()` — **không dùng** `toISOString()` (UTC làm lệch ngày trước 07:00 giờ VN) |
| Dòng con | Set đủ `employee`, `employee_name`, `group` (từ `custom_group`), `date`, `begin_time`, `end_time`, `reason` |
| State | `frm._ot_dialog_state` (Map nhân viên, Set ngày, weekOffset…); reset mỗi lần mở dialog |
| Giới hạn | Roster tải tối đa 500 nhân viên/nhóm (limit_page_length) |

### Kỹ thuật UI

- CSS inject 1 lần qua `<style id="ot-reg-dialog-css">`, scope class `.ot-reg-modal`.
- Màu lấy từ theme vars của desk (tự động light/dark qua `html[data-theme="dark"]`);
  1 màu nhấn hổ phách `#b45309` (light) / `#f5b83d` (dark) cho trạng thái chọn + số tổng.
- Số liệu (ngày, giờ, đếm, ledger) dùng font mono (`--ot-mono`).
- A11y: day tiles là `<button>` có `aria-pressed`, ledger `aria-live="polite"`,
  focus-visible outline, transition tôn trọng `prefers-reduced-motion`.
- **UI English-first** + dịch qua `translations/vi.csv`
  (mục "# Overtime Registration dialog (redesign 2026-07-14)").

### ⚠ Global scope của doctype JS

Doctype JS được eval vào **global scope** của desk. `overtime_request.js` có hàm
`show_employee_selection_dialog` riêng, nên hàm của Overtime Registration được đổi tên thành
`show_ot_registration_dialog` (2026-07-14) để 2 form không ghi đè lẫn nhau khi mở trong cùng
phiên. **Quy tắc**: hàm global mới trong file này phải có prefix `ot_` hoặc tên riêng biệt.

## Luồng lưu (before_save)

1. `before_save` → nếu chưa check: chặn save, gọi `check_all_before_save(frm)`.
2. Gọi song song 2 API server:
   - `check_employees_with_maternity_benefits` — NV mang thai/nuôi con nhỏ bắt đầu OT
     đúng giờ tan ca → đề nghị lùi giờ sớm hơn (`adjust_hours` từ Attendance Calculation Setting).
   - `check_overtime_conflicts` — trùng với OT đã submit ở phiếu khác.
3. Có kết quả → mở dialog "Kiểm tra trước khi lưu" với 2 checkbox:
   điều chỉnh giờ thai sản / xóa dòng trùng → rồi `frm.save()`.
4. Không có gì → save thẳng. Lỗi server → vẫn cho save (không chặn người dùng).

## Các hàm xác thực client (event `validate`)

| Hàm | Mục đích |
|---|---|
| `remove_empty_overtime_rows` | Tự xóa dòng không có employee (silent khi validate) |
| `validate_required_fields` | Bắt buộc employee, date, begin_time, end_time từng dòng |
| `validate_time_order` | `begin_time < end_time` |
| `validate_duplicate_rows` | Cùng NV + ngày không được chồng chéo giờ (dùng `times_overlap`, O(n²)) |
| `validate_single_post_shift_entry` | Cùng NV + ngày chỉ nên 1 dòng OT liên tục; nhiều dòng → cảnh báo gộp |
| `calculate_totals_and_apply_reason` | Đếm NV riêng biệt (`total_employees`), tổng giờ (`total_hours`); đồng bộ `reason_general` ↔ reason dòng con |
| `update_registered_groups` | Gom các `group` riêng biệt của dòng con vào `registered_groups` |

### times_overlap(from1, to1, from2, to2)

```javascript
// Chồng chéo khi: start1 < end2 && start2 < end1
// Khoảng kề nhau (16:00-18:00 và 18:00-20:00) KHÔNG tính là chồng chéo
```

| Khoảng 1 | Khoảng 2 | Chồng chéo |
|----------|----------|------------|
| 16:00-18:00 | 18:00-20:00 | ❌ kề nhau |
| 16:00-18:00 | 17:00-19:00 | ✔ |
| 16:00-18:00 | 14:00-16:00 | ❌ kề nhau |
| 16:00-18:00 | 17:00-17:30 | ✔ chứa nhau |

## Cấu trúc dữ liệu

### Overtime Registration (parent)
- `requested_by` / `requested_by_full_name`: tự điền theo user hiện tại khi tạo mới
- `approver` / `approver_full_name`: tự điền theo pattern Leave Application (HRMS department approver)
- `reason_general`, `total_employees`, `total_hours`, `registered_groups`: tự tính
- `request_by_group`, `filter_employee_by` (custom field): khóa/lọc phạm vi chọn nhân viên

### Overtime Registration Detail (child `ot_employees`)
- `employee`, `employee_name`, `group`, `date`, `begin_time`, `end_time`, `reason`

## Kiến trúc hybrid

- **JavaScript (client)**: phản hồi tức thì — validate trong form, tính tổng, dialog chọn nhân viên.
- **Python (server)**: kiểm tra cần quyền đọc DB đầy đủ — xung đột với phiếu đã submit,
  chế độ thai sản, validate khi submit.
- Thông báo lỗi đa ngôn ngữ (`__()`), kèm số dòng và link tới document xung đột.
