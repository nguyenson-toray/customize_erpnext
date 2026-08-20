# Employee Maternity

> **Mục đích:** Doctype quản lý các giai đoạn thai sản của nhân viên.
> **Phạm vi:** DocType tự phát triển
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-17

Doctype quản lý các giai đoạn thai sản của nhân viên. Mỗi nhân viên 1 record cho 1 chu kỳ thai sản, chứa **cả 3 giai đoạn** dưới dạng 3 cặp ngày (không còn kiểu 1 record / 1 type như bản cũ).

## Cấu trúc field

| Field | Type | Mô tả |
|-------|------|-------|
| `employee` | Link → Employee | Nhân viên (reqd) |
| `full_name`, `group`, `designation`, `date_of_joining` | fetch | Fetch từ Employee |
| `status` | Select (read-only) | `Pregnant` / `Maternity Leave` / `Young Child` / `Inactive` / rỗng — **tự tính**, xem bên dưới |
| `apply_benefit` | Check (default 1) | Áp dụng giảm 1 giờ làm việc |
| `pregnant_from_date` | Date | Bắt đầu thai kỳ (HR nhập) |
| `pregnant_to_date` | Date (read-only) | **Derived** |
| `estimated_due_date` | Date | Ngày dự sinh |
| `maternity_from_date` | Date | Bắt đầu nghỉ thai sản (thực tế) |
| `maternity_from_date_estimate` | Date | Bắt đầu nghỉ thai sản (dự kiến — fallback khi chưa có ngày thực tế) |
| `maternity_to_date` | Date | Kết thúc nghỉ thai sản |
| `date_of_birth` | Date | Ngày sinh con |
| `youg_child_from_date` | Date (read-only) | **Derived** |
| `youg_child_to_date` | Date (read-only) | **Derived** |
| `gestational_age` | Float (virtual) | Tuổi thai (tháng), clamp [0, 9.5] |
| `seniority` | Int (virtual) | Thâm niên (tháng) từ date_of_joining |

## Derived dates (server `calculate_derived_dates()` — mirror client JS)

`effective_mat_from = maternity_from_date || maternity_from_date_estimate`

| Field | Công thức |
|-------|-----------|
| `pregnant_to_date` | `effective_mat_from - 1 ngày` (fallback: `estimated_due_date`; không bao giờ bị clear) |
| `maternity_to_date` | `effective_mat_from + 6 tháng` (chỉ khi đang trống) |
| `youg_child_from_date` | `maternity_to_date + 1 ngày` |
| `youg_child_to_date` | `date_of_birth + 364 ngày` |

**Data Import:** giá trị import không bao giờ bị xóa — chỉ bị ghi đè khi có source field để derive (record legacy có thể import trực tiếp phase dates mà không có source fields).

## Status

`calculate_status()`: hôm nay rơi vào giai đoạn nào → status đó. Giai đoạn Maternity dùng `effective_mat_from` (fallback estimate). Nếu rơi vào nhiều giai đoạn (data legacy) → chọn giai đoạn có from_date muộn nhất. Qua hết `youg_child_to_date` → `Inactive`. Không rơi vào đâu → rỗng.

- **Tự tính lại hàng ngày** — scheduler cron 00:00: `scheduled_calculate_all_maternity_statuses()`
- **List view** có nút **Calculate Status** (tất cả hoặc records được chọn) và **Show Invalid Records** (tìm record có gap ≠ 1 ngày giữa các giai đoạn)

## Đồng bộ sang Employee.status (`employee_status_sync.py`)

Chỉ `Maternity Leave` là nghỉ thật. `Pregnant` và `Young Child` vẫn đi làm bình
thường (chỉ hưởng chế độ về sớm 1 giờ) nên employee giữ `Active`.

| Chuyển tiếp status của record | `Employee.status` |
|---|---|
| `* → Maternity Leave` | `Inactive` |
| `Maternity Leave → *` | `Active` |
| còn lại | không đụng |

**4 guard rail — đừng bỏ khi refactor:**

1. **Chỉ chạy khi có chuyển tiếp** (`old != new`). Scheduler quét lại toàn bộ record
   mỗi ngày; nếu khẳng định lại status ở trạng thái ổn định thì sẽ ghi đè thay đổi
   thủ công của HR.
2. **Chỉ lật `Active` ⇄ `Inactive`.** `Left` / `Suspended` là quyết định nhân sự vì
   lý do khác — không bao giờ ghi đè.
3. **Trước khi trả về `Active`**, kiểm tra không còn record maternity nào KHÁC của
   employee đó đang `Maternity Leave` (một nhân viên có thể có 2–3 chu kỳ).
4. **Ghi bằng `frappe.db.set_value`**, không `doc.save()` — lifecycle của Employee
   clear cache toàn site và disable User trên mỗi lần save.

**3 điểm gọi** (thiếu 1 là sync coi như hỏng):

| Điểm | Vì sao |
|---|---|
| `on_maternity_update` | HR save trên UI / Data Import. Có xử lý đổi employee: employee CŨ được trả về Active |
| `calculate_all_maternity_statuses()` | Dùng `db_set(update_modified=False)` → **bypass hook**, phải gọi tay. Đây là đường của scheduler 00:00 + nút Calculate Status, tức là nơi hầu hết chuyển tiếp thật xảy ra |
| `on_maternity_delete` | Xoá record = giai đoạn biến mất |

Mỗi lần lật đều ghi 1 Comment trên Employee (`Status Active → Inactive — Maternity phase ...`).

### Employee.custom_sub_status — CHỈ HIỂN THỊ

Fieldtype **HTML** → **không có cột trong DB**, không lưu gì. `get_employee_sub_status()`
suy ra tại chỗ mỗi lần mở form; `employee.js::render_sub_status()` vẽ badge + link
tới record. Vì không lưu nên **không filter / report theo sub-status được**.

`get_current_maternity_record()` chọn record "hiện hành" **xác định** — ưu tiên
`Maternity Leave` → `Pregnant` → `Young Child` → `Inactive`, đồng hạng thì lấy ngày
bắt đầu giai đoạn muộn nhất, rồi `modified`. Đừng thay bằng `LIMIT 1` trần: 18 nhân
viên đang có 2–3 record.

### Hệ quả đã biết của việc thành Inactive

- **Không còn được tính Attendance** — engine (`shift_type_optimized.py:1652`) chỉ lấy
  `Active` + `Left`. Đây là **cố ý**: người đang nghỉ thai sản không cần bản ghi công.
- **User không bị khoá** — `overrides/employee/employee_override.py::CustomEmployee`
  chặn `update_user_status()` của core. Class này kế thừa `EmployeeMaster` của HRMS
  (HRMS cũng chiếm `override_doctype_class["Employee"]`), đừng kế thừa thẳng core.
- **Card HR Overview** — `maternity_leave()` phải đếm cả `Inactive` nếu không sẽ về 0;
  `net_headcount()` vẫn chỉ trừ người còn `Active` (nếu nới ra `Inactive` sẽ trừ 2 lần).
- **Chưa xử lý:** Labor Contract (3 chỗ chặn `status != Active`), Uniform, Self-Update,
  Employee Photos, biometric_sync, daily_attendance_metrics — các module này sẽ bỏ qua
  người đang nghỉ thai sản.

## Validation

- Mỗi cặp: `from <= to` (cho phép phase 1 ngày)
- 3 giai đoạn không được overlap trong cùng record; giai đoạn thiếu to_date được coi là open-ended (vô hạn) khi check overlap

## Ảnh hưởng đến Attendance

**Gated by Attendance Calculation Setting → "Recalc Attendance on Maternity Save/Delete"** (`recalc_attendance_on_maternity_change`, mặc định **OFF**). Khi OFF, attendance chỉ được cập nhật ở lần chạy full kế tiếp hoặc Bulk Update thủ công.

Khi ON, mỗi lần tạo/sửa/xóa record:

1. `before_save` so sánh old vs new → thu thập các ngày bị ảnh hưởng theo employee (đổi employee → recalc cho **cả** employee cũ và mới)
2. Giới hạn đến hôm nay và `relieving_date - 1`
3. `on_update` / `on_trash` → queue background job (`enqueue_after_commit=True`, queue long) gọi `_core_process_attendance_logic_optimized()` cho đúng những ngày đó
4. Job skip nếu đang giờ cao điểm check-in/out (`is_peak_time()`) — lần chạy full kế tiếp bù

Lưu ý: Frappe chạy `on_update` sau **cả insert lẫn save** → không đăng ký hook `after_insert` (sẽ bị queue đôi).

### Maternity Benefit trong Attendance

- Attendance field `custom_maternity_benefit` = 1 khi employee có benefit → **giảm 1 giờ** khỏi standard working hours
- Benefit theo giai đoạn (dựa trên ngày attendance rơi vào cặp from/to nào):
  - `Maternity Leave`, `Young Child`: luôn benefit
  - `Pregnant`: chỉ khi `apply_benefit = 1`

### Các nơi đọc Employee Maternity

| File | Mô tả |
|------|-------|
| `overrides/shift_type/shift_type_optimized.py` | `check_maternity_status_cached()` + preload — tính attendance |
| `api/employee/employee_utils.py` | `check_employee_maternity_status()` |
| `overrides/attendance/attendance.py` | Info hiển thị trên Attendance form |
| `customize_erpnext/report/employee_maternity_report/` | Report thai sản |
| `customize_erpnext/report/shift_attendance_customize/` | Report + scheduler + standard export |
| `health_check_up/doctype/health_check_up/` | Xác định pregnant theo khoảng ngày khi khám sức khỏe |

## Hooks (hooks.py)

```python
"Employee Maternity": {
    "on_update": "...employee_maternity.on_maternity_update",   # chạy sau cả insert lẫn save
    "on_trash":  "...employee_maternity.on_maternity_delete",
}

# Scheduler: daily 00:00
"...employee_maternity.scheduled_calculate_all_maternity_statuses"
```

(Không còn LA → Employee Maternity auto-sync; record do HR quản lý thủ công / Data Import.)

## API

### `get_employee_maternity_for_excel` (Power Query / Excel)

`@frappe.whitelist()` — **yêu cầu đăng nhập hoặc API key** (`Authorization: token <api_key>:<api_secret>`). Không mở `allow_guest` vì dữ liệu thai sản nhạy cảm.

Params: `employee`, `status`, `group`, `page`, `page_size` (0 = all), `lang` (`en`/`vi`).
Trả về `{ data, columns, col_keys, total, page, page_size, total_pages }` kèm 2 virtual field `gestational_age`, `seniority`.

### `calculate_all_maternity_statuses(names=None)`

Batch recalc status (dùng bởi nút list view + scheduler). `names=None` → tất cả.

### `get_invalid_maternity_records()`

Tìm record có gap giữa các giai đoạn ≠ 1 ngày (dùng bởi nút "Show Invalid Records").
