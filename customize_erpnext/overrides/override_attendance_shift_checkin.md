# Attendance, Shift & Check-in Override Documentation

**Last Updated:** 2026-04-06

---

## Tổng Quan

Module override xử lý toàn bộ luồng chấm công từ HRMS, thay thế logic gốc bằng phiên bản tối ưu:

- Tự động tạo attendance từ check-in logs (hourly hook + manual UI)
- Đánh Absent cho nhân viên không check-in (trừ Maternity Leave)
- Xóa attendance cho nhân viên đang nghỉ thai sản (Maternity Leave phase)
- Hỗ trợ dual leave: 2 Half Day Leave Application cùng 1 ngày
- Bulk update qua UI với month preset và skipped employee summary

---

## Files

| File | Mô tả |
|------|-------|
| `overrides/shift_type/shift_type_optimized.py` | Core logic chính (preload + xử lý + bulk insert) |
| `overrides/shift_type/shift_type.py` | Helper functions (get_employee_checkins, should_mark_attendance, ...) |
| `overrides/shift_type/__init__.py` | Monkey patches vào HRMS |
| `overrides/employee_checkin/employee_checkin.py` | Hook checkin insert/update/delete → recalculate attendance |
| `overrides/leave_application/leave_application.py` | Hook LA submit/cancel → sync attendance |
| `overrides/leave_utils.py` | Dual leave utilities |
| `public/js/custom_scripts/attendance_list.js` | UI: Bulk Update Attendance dialog |
| `patches/add_attendance_performance_indexes.py` | DB indexes cho performance |

---

## Monkey Patches (`overrides/shift_type/__init__.py`)

```python
# Class methods
hrms_st.ShiftType.get_employee_checkins  = custom_get_employee_checkins
hrms_st.ShiftType.should_mark_attendance = custom_should_mark_attendance
hrms_st.ShiftType.process_auto_attendance = custom_process_auto_attendance

# Module-level functions
hrms_st.update_last_sync_of_checkin            = custom_update_last_sync_of_checkin
hrms_st.process_auto_attendance_for_all_shifts = custom_process_auto_attendance_for_all_shifts
```

---

## Execution Paths

### Path 1 — HRMS Hourly Hook (`hourly_long`)

```
hooks.py scheduler_events
    → hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
        (monkey patched)
    → custom_process_auto_attendance_for_all_shifts()
    → _core_process_attendance_logic_optimized(fore_get_logs=auto)
```

`fore_get_logs` tự động = `True` lúc 8h và 23h (`SPECIAL_HOUR_FORCE_UPDATE = [8, 23]`), = `False` các giờ còn lại (incremental mode).

### Path 2 — UI Bulk Update

```
Attendance List > "Bulk Update Attendance" button
    → show_bulk_update_attendance() [JS dialog]
    → bulk_update_attendance_optimized() [API, force_sync=1 nếu ≤1000 records]
    → _core_process_attendance_logic_optimized(fore_get_logs=True)
```

### Path 3 — Employee Checkin Hook

```
Employee Checkin.after_insert / on_update
    → update_attendance_on_checkin_insert/update()
    → (skip nếu frappe.flags.in_import)
    → enqueue _recalculate_attendance(employee, date)
    → _core_process_attendance_logic_optimized (single employee, single day)
```

---

## `_core_process_attendance_logic_optimized()` — Step-by-step

```
STEP 1: Preload Reference Data (1 lần, O(1) lookup cho toàn bộ xử lý)
   ├─ employees          → dict {emp_id: emp_data}
   ├─ shifts             → dict {shift_name: shift_data}
   ├─ shift_assignments  → dict {emp_id: [assignments]} — pre-sorted start_date DESC
   ├─ holidays           → dict {holiday_list: set(dates)}
   ├─ existing_attendance→ dict {(emp, date): att}
   │                      + existing_attendance_by_shift {shift: {(emp,date): att}}
   ├─ leave_applications → dict {(emp, date): [list]} — list để hỗ trợ dual leave
   ├─ maternity_tracking → dict {emp_id: [{type, from_date, effective_to_date}]}
   └─ overtime_regs      → dict {(emp, date): [{begin_time, end_time}]}

STEP 2: Bulk Update Checkin Shifts
   └─ SQL UPDATE checkins có shift=NULL hoặc offshift=1

STEP 2b: Cancel/Delete Maternity Leave Attendance (fore_get_logs only)
   ├─ Scan existing_attendance
   ├─ Tìm records của employees đang ở phase "Maternity Leave"
   ├─ Unlink checkins → DELETE attendance records
   └─ Remove khỏi existing_attendance cache

STEP 3: Process Auto-Enabled Shifts
   ├─ Lấy checkins từ DB (shift_start IS NOT NULL, trong date range)
   │   fore_get_logs=True  → filter shift_actual_end < end_of_to_date (SQL)
   │   fore_get_logs=False → filter shift_actual_end < last_sync (Python, OR condition)
   ├─ [Có checkins] Group by (employee, shift_start) → tính working_hours, OT
   │   ├─ Skip nếu maternity_status == "Maternity Leave"
   │   ├─ Preserve leave_type, leave_application, _2 fields từ old_att
   │   └─ Bulk insert / update
   └─ [Không có checkins, fore_get_logs=True] Update existing → Absent
       └─ Dùng existing_attendance_by_shift[shift_name] (O(1) per shift)

STEP 4: Mark Absent (employees không có attendance sau STEP 3)
   ├─ Skip: holiday, Sunday, maternity_status == "Maternity Leave"
   ├─ Check leave_status (dual leave aware)
   └─ Bulk insert Absent / On Leave / Half Day

STEP 4b: Cleanup — xóa attendance sau relieving_date

STEP 5: Calculate statistics từ DB

STEP 6: Classify skipped employees by reason
   ├─ "Maternity Leave"      — employee trong phase Maternity Leave
   ├─ "No shift assigned"    — không có shift assignment và không có default_shift
   ├─ "Not yet joined"       — date_of_joining > to_date
   ├─ "Already left"         — relieving_date < from_date
   └─ "No checkins / Holiday"— holiday, weekend, hoặc không check-in
```

---

## Constants

```python
# shift_type_optimized.py
EMPLOYEE_CHUNK_SIZE_OPTIMIZED = 100   # Batch size khi iterate employees
BULK_INSERT_BATCH_SIZE        = 500   # Batch size cho bulk INSERT
CHECKIN_UPDATE_BATCH_SIZE     = 1000  # Batch size khi update checkins
SPECIAL_HOUR_FORCE_UPDATE     = [8, 23]  # Giờ trigger fore_get_logs=True

# attendance_list.js
BULK_ATTENDANCE_ASYNC_THRESHOLD = 1000  # Records → force_sync=1 nếu ≤ ngưỡng
```

---

## Maternity Leave Handling

**Nguồn sự thật:** `tabEmployee Maternity` (không dùng Leave Application)

**3 phases:**

| Phase | Fields | Attendance |
|-------|--------|------------|
| Pregnant | `pregnant_from_date` → `pregnant_to_date` | Tạo bình thường (có check-in thì Present, không thì Absent) |
| **Maternity Leave** | `maternity_from_date` → `maternity_to_date` | **Không tạo** — xóa nếu tồn tại |
| Young Child | `youg_child_from_date` → `youg_child_to_date` | Tạo bình thường |

**Check cached:**
```python
def check_maternity_status_cached(employee, attendance_date, ref_data):
    # → (maternity_status, apply_pregnant_benefit)
    # maternity_status: 'Pregnant' | 'Maternity Leave' | 'Young Child' | None
```

**Bulk Update:** Khi chạy fore_get_logs=True, STEP 2b scan toàn bộ existing_attendance, xóa records của employees đang trong phase "Maternity Leave" trước khi processing bắt đầu.

---

## Dual Leave Support

Kịch bản: nhân viên có 2 Half Day Leave Application cùng 1 ngày (sáng + chiều).

**Preload:** `leave_applications[(emp, date)]` là **list** (không phải dict đơn) → giữ cả 2 LA.

**`check_leave_status_cached()`:**
- 1 LA active → `status='Half Day'` hoặc `'On Leave'` như thường
- 2 LA active (cả 2 half-day) → `status='On Leave'`, trả thêm `leave_type_2`, `leave_application_2`

**Attendance fields:**
```
leave_type             ← LA1
leave_application      ← LA1
custom_leave_type_2    ← LA2 (nếu có)
custom_leave_application_2 ← LA2 (nếu có)
custom_leave_application_abbreviation ← "KP/NP" (combined)
```

**Preserve khi update:** Khi employee có checkin + đang có dual leave trong old_att → preserve `_2` fields, không overwrite.

---

## Bulk Update UI (`attendance_list.js`)

### Dialog fields

| Field | Mô tả |
|-------|-------|
| **Month** (Select) | Chọn tháng theo MM/YYYY, giảm dần từ tháng hiện tại → 01/2025. Tự điền from/to_date. |
| **From Date** | 26 tháng trước (khi chọn Month), hoặc tùy chỉnh |
| **To Date** | 25 tháng này (khi chọn Month), hoặc tùy chỉnh |
| **Employee** | Lọc 1 nhân viên (mutual exclusive với Group) |
| **Employee Group** | Lọc theo nhóm |

Chọn Month → tự điền From/To. Sửa From/To thủ công → Month reset về blank.

### Result dialog

```
Operation Completed Successfully
Date range | N employees processed

Employee Summary (nếu có skipped):
  Total: X  |  With attendance: Y  |  Skipped: Z
```

Chi tiết skipped employees (reason + employee list) log ra browser console.

### API flow

```
force_sync = total_records <= 1000 ? 1 : 0

frappe.call → bulk_update_attendance_optimized()
    ├─ sync  → result trực tiếp → show_attendance_results_dialog_v2()
    └─ async → background job → realtime 'bulk_update_attendance_complete' event
                             → show_attendance_results_dialog_v2()
```

---

## DB Indexes (`patches/add_attendance_performance_indexes.py`)

Chạy: `bench --site erp.tiqn.local migrate`

| Index | Table | Columns |
|-------|-------|---------|
| `idx_att_emp_date_docstatus` | `tabAttendance` | `employee, attendance_date, docstatus` |
| `idx_shift_assign_lookup` | `tabShift Assignment` | `employee, docstatus, status, start_date` |
| `idx_leave_app_date_range` | `tabLeave Application` | `employee, status, docstatus, from_date, to_date` |
| `idx_checkin_attendance_fk` | `tabEmployee Checkin` | `attendance` |
| `idx_emp_maternity_employee` | `tabEmployee Maternity` | `employee` |
| `idx_emp_maternity_mat_dates` | `tabEmployee Maternity` | `maternity_from_date, maternity_to_date` |
| `idx_ot_detail_emp_date` | `tabOvertime Registration Detail` | `employee, date` |
| `idx_employee_status_relieving` | `tabEmployee` | `status, relieving_date` |

Patch idempotent — chạy nhiều lần không lỗi.

---

## Related Doctypes

| Doctype | Vai trò |
|---------|---------|
| `Shift Type` | Cấu hình ca làm việc, ngưỡng tính công |
| `Shift Assignment` | Phân công ca cho nhân viên theo ngày |
| `Attendance` | Record chấm công (1 record/ngày/nhân viên) |
| `Employee Checkin` | Log quẹt thẻ vào/ra |
| `Employee Maternity` | Theo dõi thai sản (Pregnant → Maternity Leave → Young Child) |
| `Leave Application` | Đơn nghỉ phép (dual leave: 2 Half Day/ngày) |
| `Overtime Registration` | Đăng ký tăng ca (ảnh hưởng working hours tính công Chủ Nhật) |
