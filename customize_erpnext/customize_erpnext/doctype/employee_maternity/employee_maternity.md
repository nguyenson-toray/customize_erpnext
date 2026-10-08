# Employee Maternity

> **Mục đích:** Quản lý chu kỳ thai sản của nhân viên nữ: mang thai → nghỉ thai sản → nuôi con nhỏ.
> **Phạm vi:** DocType tự phát triển · **Cập nhật:** 2026-10-07

1 hồ sơ = 1 chu kỳ thai sản (con thứ 2 = hồ sơ thứ 2, tên `HR-EM-{employee}`, `-1`, `-2`…).
Mỗi hồ sơ chứa 3 giai đoạn dưới dạng 3 cặp ngày, **luôn liên tục** (không hở, không chồng).

## Field

| Field | Type | Ghi chú |
|---|---|---|
| `employee` | Link Employee (reqd) | **Chỉ nhân viên nữ** — JS `set_query` + server `validate_employee_gender()` (chặn cả Data Import) |
| `full_name`, `group`, `designation`, `date_of_joining` | fetch | Từ Employee |
| `child_order` | Int | Con thứ mấy. Form gợi ý = max hồ sơ trước của NV + 1 (NV chưa có hồ sơ → để trống) |
| `is_twins` | Check | Sinh đôi |
| `status` | Select, read-only | `Pregnant` / `Maternity Leave` / `Young Child` / `Inactive` / rỗng — tự tính |
| `note` | Small Text | |
| `apply_hour_reduction` | Check | Giảm 1 giờ ở giai đoạn mang thai |
| `pregnant_from_date` | Date, **reqd** | HR nhập |
| `pregnancy_notified_date` | Date | Ngày HR nhận thông tin — chỉ lưu |
| `pregnant_to_date` | Date, **reqd** | Xem quy tắc ngày |
| `estimated_due_date` | Date | Ngày dự sinh |
| `is_miscarriage` | Check | Sẩy thai |
| `gestational_age` | Data | Tuổi thai (tháng), chỉ khi `Pregnant`. **Phải là `Data`**: Float bị Frappe ép `None → 0.0` |
| `seniority` | Int | Thâm niên (tháng) |
| `maternity_from_date` | Date | Read-only khi sẩy thai |
| `leave_months` | Int, **reqd** | Số tháng nghỉ thai sản |
| `maternity_to_date` | Date, read-only | Derived |
| `date_of_birth` | Date | Ngày sinh con — HR nhập |
| `youg_child_from_date` | Date, read-only | Derived |
| `youg_child_to_date` | Date, read-only | Derived |

## Quy tắc ngày — `calculate_derived_dates()` (mirror `employee_maternity.js`)

| Field | Quy tắc |
|---|---|
| `pregnant_to_date` | HR nhập; trống → copy `estimated_due_date`; `maternity_from_date` vừa đổi → `maternity_from_date − 1` |
| `maternity_from_date` | `pregnant_to_date + 1` |
| `maternity_to_date` | `maternity_from_date + leave_months − 1 ngày` (`maternity_end_date()`; nghỉ 19/01, 6 tháng → hết 18/07) |
| `youg_child_from_date` | `maternity_to_date + 1` |
| `youg_child_to_date` | `date_of_birth + 364`; chưa có ngày sinh → trống |

- Khi cả `pregnant_to_date` và `maternity_from_date` cùng có giá trị, bên **vừa đổi** (`has_value_changed`) thắng.
- `maternity_from_date` chỉ **tự điền** khi: tạo hồ sơ mới, HR sửa `pregnant_to_date`, hoặc bỏ tick sẩy thai.
  **`maternity_from_date` trống = không có nghỉ thai sản** (sẩy thai / không sinh — HR ghi Note) → các giai đoạn sau không được tính.
  HR xoá trống ô này thì tôn trọng, kể cả khi cùng lúc sửa `pregnant_to_date`.
- Data Import đi qua cùng quy tắc.

### `leave_months` — `apply_default_leave_months()` / `default_leave_months(child_order, is_twins)`

| | Một con | Sinh đôi |
|---|---|---|
| Con thứ 1, thứ 3 trở đi | 6 | 7 |
| Con thứ 2 | 7 | 8 |

(Luật Dân số 2025 + Luật BHXH 2024, hiệu lực 01/07/2026 — nội dung do HR cung cấp. Áp mặc định, không xét
mốc ngày; hồ sơ quá khứ HR tự rà soát.)

- Hồ sơ đã có: tính lại chỉ khi `child_order` hoặc `is_twins` **đổi**; mở ra lưu lại không bị đụng.
- Hồ sơ mới: tính khi `leave_months` đang là 0 hoặc 6 (số khác = HR cố ý nhập).
- HR sửa tay sau đó được giữ.
- `doc.flags.keep_leave_months = True` → bỏ qua quy tắc (script nạp dữ liệu lịch sử lấy số tháng theo ngày thực tế).

### Sẩy thai — `apply_miscarriage()`

Tick trên form → dialog nhập ngày sẩy thai (≥ `pregnant_from_date`, ≤ hôm nay; Huỷ → tự bỏ tick):

1. `pregnant_to_date` = ngày sẩy thai
2. Xoá `maternity_from_date`, `maternity_to_date`, `date_of_birth`, `youg_child_from_date`, `youg_child_to_date`
3. Note có dòng đầu `Sẩy thai ngày dd/mm/yyyy` (`miscarriage_note()`; mọi dòng cũ bắt đầu bằng "sẩy thai",
   không phân biệt hoa/thường, bị thay — không lặp)

Server áp lại khi lưu và khi Data Import. Bỏ tick → hỏi xác nhận rồi tính lại `maternity_from_date`.

### Validation

- `employee` phải là nữ
- Mỗi cặp ngày `from ≤ to` (giai đoạn có thể 1 ngày); 3 giai đoạn không chồng nhau trong cùng hồ sơ

## Status — `calculate_status()`

1. Nhân viên **đã nghỉ việc** → `Inactive` (kể cả khi giai đoạn còn ở tương lai). `_has_left()` ưu tiên
   `relieving_date` (ngày **bắt đầu** nghỉ việc: còn làm tại X ⇔ `relieving_date > X`), `Employee.status`
   chỉ là fallback và **phải `.strip()`** — trên site có status `"Left "` có dấu cách.
2. Hôm nay rơi vào giai đoạn nào → status đó; nhiều giai đoạn → giai đoạn có ngày bắt đầu muộn nhất.
3. **Chưa có ngày sinh con → chưa tính là `Young Child`.**
4. Qua `youg_child_to_date`, hoặc sẩy thai đã qua `pregnant_to_date` → `Inactive`. Còn lại → rỗng.

Tính lại hằng đêm 00:10 (`scheduled_calculate_all_maternity_statuses`) — **phải sau**
`auto_mark_employees_as_left` (00:00). `calculate_derived_metrics()` tính `seniority` + `gestational_age` cùng lúc.

## Cờ `Employee.custom_is_maternity_leave` (`employee_status_sync.py`)

- Check read-only, cột thật trên Employee (Number Card / Dashboard Chart chỉ lọc được field của chính doctype).
- Nguồn: `Employee Maternity.status == "Maternity Leave"` — cùng nguồn với `api/headcount.py::maternity_leave_employees()`
  (Net Headcount, daily email). Cờ chỉ mang nghĩa **hôm nay**; tính theo kỳ phải đọc khoảng ngày.
- Ghi bởi `on_update`, `on_trash` và `sync_all_maternity_flags()` (job 00:10, khẳng định lại toàn bộ).
- **Không** đổi `Employee.status` (Inactive chặn tạo Employee Checkin, engine/Export/Leave Control Panel bỏ qua).
- `get_employee_sub_status()` / `get_current_maternity_record()`: badge trên form Employee (HTML, không lưu DB).
  Màu: Pregnant xanh dương · Maternity Leave cam · Young Child xanh lá · Inactive xám — **phải khớp**
  `PHASE_INDICATOR` và `employee_maternity_list.js` (`formatters.status`, không dùng `get_indicator`).

## Các nơi đọc Employee Maternity

| File | Ghi chú |
|---|---|
| `overrides/shift_type/shift_type_optimized.py` | Engine tính công: preload mọi hồ sơ → `check_maternity_status_cached()`. Ngày nghỉ thai sản không tạo Attendance (kể cả có check-in) |
| `api/employee/employee_utils.py` | `get_employee_maternity_phase()` → `(status, benefit, record)`; `check_employee_maternity_status()` là wrapper. Duyệt **mọi** hồ sơ, ưu tiên Maternity Leave → Young Child → Pregnant |
| `overrides/employee_checkin/employee_checkin.py` | Tính công khi check-in thêm/sửa — dùng hàm trên |
| `customize_erpnext/doctype/overtime_registration/` | `check_maternity_benefit()` — khoảng ngày lấy từ đúng hồ sơ đang phủ ngày đó |
| `overrides/attendance/attendance.py` | Ghi chú thai sản trên form Attendance (duyệt mọi hồ sơ) |
| `api/headcount.py`, `api/hr_overview_cards.py` | Headcount trừ người đang nghỉ thai sản; card mở report với From = To = hôm nay, `show = Maternity Leave` |
| `customize_erpnext/report/shift_attendance_customize/` | Report + Export Excel (nhãn `[Thai sản + Att]` khi có quẹt thẻ trong kỳ nghỉ) |
| `health_check_up/` | Xác định mang thai khi khám sức khoẻ |

Giảm giờ (`Attendance.custom_hour_reduction`): `Maternity Leave`, `Young Child` luôn có; `Pregnant` khi `apply_hour_reduction = 1`.
Giai đoạn thiếu ngày kết thúc (Young Child chưa có ngày sinh) không được giảm giờ.

## Tính lại Attendance khi lưu / xoá

Gated bởi Attendance Calculation Setting → `recalc_attendance_on_maternity_change` (mặc định **OFF**).
Khi ON: `before_save` thu thập ngày bị ảnh hưởng (cả NV cũ khi đổi employee) → `on_update` / `on_trash`
enqueue job (`enqueue_after_commit=True`, queue long); bỏ qua giờ cao điểm check-in. Không đăng ký
`after_insert` (Frappe chạy `on_update` sau cả insert → queue đôi).

## Hooks

```python
doc_events["Employee Maternity"] = {
    "on_update": "...employee_maternity.on_maternity_update",
    "on_trash":  "...employee_maternity.on_maternity_delete",
}
scheduler_events["cron"]["10 0 * * *"] = ["...employee_maternity.scheduled_calculate_all_maternity_statuses"]
```

## List view

- **Calculate Status** — `calculate_all_maternity_statuses(names=None)`: status + metrics + cờ cho tất cả / hồ sơ được chọn.
  Trả `{updated, total, closed_for_left, metrics_updated, flags_set, flags_cleared}`.
- **Show Invalid Records** — `get_invalid_maternity_records()`: khoảng hở ≠ 1 ngày giữa các giai đoạn, hoặc
  đã nghỉ thai sản ≥ `MISSING_DOB_GRACE_DAYS` (14) ngày mà chưa có ngày sinh con.

## Employee Maternity Report

`report/employee_maternity_report/` — 1 màn hình theo khoảng ngày, **1 dòng / hồ sơ**.

- Filter: From Date, To Date (mặc định tháng này; nút **Today**), **Compact View** (mặc định bật),
  **Maternity Status** (`show`), Department, Group (Link Group). Nút **Help**: dialog tiếng Việt viết thẳng trong JS
  (ngoại lệ English-first, theo yêu cầu).
- 5 thẻ `report_summary` đếm DISTINCT employee, bấm để lọc (`after_refresh`), luôn đếm kiểu **chạm kỳ**:

  | `show` | Điều kiện |
  |---|---|
  | `Pregnant` / `Maternity Leave` | Giai đoạn chạm kỳ |
  | `Young Child` | Chạm kỳ **và** có ngày sinh con |
  | `Returned to Work` (nhãn "Return to Work") | `maternity_to_date + 1` ∈ kỳ, chưa nghỉ việc tới ngày đó — tính cả tương lai |
  | `Left` | `Employee.status = Left` và `relieving_date` ∈ kỳ |

- Mọi giai đoạn bị cắt tại `relieving_date − 1`. Cột `left_during` ("Left at Phase"): Before Pregnancy /
  Pregnant / Maternity Leave / Did Not Return / Young Child / After Young Child Period. Sự kiện nghỉ việc gán cho
  hồ sơ mới nhất bắt đầu trước ngày nghỉ việc (`_left_record_by_employee`).
- **Compact View**: 4 mốc (Pregnant From, Maternity From, Young Child From = ngày đi làm lại, Young Child To = hết chu kỳ) + Relieving Date. Tên cột **giống nhau ở 2 chế độ** — Rút gọn chỉ bớt cột. Bỏ tick: đủ cặp
  Từ–Đến cho mỗi giai đoạn + Department, Pregnancy Notified Date, Estimated Due Date, Gestational Age.
- ⚠ `query_report.js` **không gửi filter có giá trị falsy** (Check bỏ tick) → thiếu key = 0:
  `cint(filters.get("compact"))`, không được `filters.get("compact", 1)`.
- Test: `test_employee_maternity_period.py`.

## API

### `get_employee_maternity_for_excel` (Power Query / Excel)

`@frappe.whitelist()`, **cần đăng nhập hoặc API key** (`Authorization: token <api_key>:<api_secret>`) — không `allow_guest`.
Params: `employee`, `status`, `group`, `page`, `page_size` (0 = tất cả), `lang` (`en` / `vi`).
Trả `{data, columns, col_keys, total, page, page_size, total_pages}`. 4 cột cuối: `child_order`, `is_twins`,
`pregnancy_notified_date`, `leave_months` (để cuối cho Power Query map theo vị trí không lệch).
