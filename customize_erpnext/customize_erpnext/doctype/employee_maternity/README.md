# Employee Maternity

Standalone doctype quản lý các giai đoạn thai sản của nhân viên. Thay thế child table `custom_maternity_tracking` cũ trong Employee.

## Cấu trúc

| Field | Type | Mô tả |
|-------|------|-------|
| `employee` | Link → Employee | Nhân viên |
| `type` | Select | `Pregnant` / `Maternity Leave` / `Young Child` |
| `from_date` | Date | Ngày bắt đầu |
| `to_date` | Date | Ngày kết thúc |
| `apply_benefit` | Check | Áp dụng giảm 1 giờ làm việc |
| `leave_application` | Link → Leave Application | Chỉ có khi type = "Maternity Leave" |
| `note` | Small Text | Ghi chú |
| `estimated_due_date` | Date | Ngày dự sinh (chỉ hiển thị khi Pregnant) |
| `date_of_birth` | Date | Ngày sinh con (chỉ hiển thị khi Young Child) |

## 3 loại type

### 1. Pregnant (Mang thai)
- Tạo thủ công bởi HR
- `apply_benefit` mặc định = 1, có thể tắt
- Chỉ khi `apply_benefit = 1` mới được giảm giờ

### 2. Maternity Leave (Nghỉ thai sản)
- **Tự động tạo** khi submit Leave Application có leave type = `"Nghỉ hưởng BHXH/ Social insurance leave - Thai sản"`
- **Tự động xóa** khi cancel Leave Application
- **Tự động cập nhật** from_date/to_date khi LA được amend
- Các field readonly, không cho phép sửa thủ công
- `apply_benefit` luôn = 1

### 3. Young Child (Nuôi con nhỏ)
- Tạo thủ công bởi HR
- `apply_benefit` luôn áp dụng (auto benefit)

## Ảnh hưởng đến Attendance

Khi tạo/sửa/xóa Employee Maternity record, hệ thống tự động:

1. Thu thập các ngày bị ảnh hưởng (so sánh old vs new dates)
2. Giới hạn đến ngày hôm nay và relieving_date của employee
3. Queue background job gọi `bulk_update_attendance_optimized()` để recalculate attendance

### Maternity Benefit trong Attendance
- Attendance field `custom_maternity_benefit` = 1 khi employee có benefit
- Khi có benefit: **giảm 1 giờ** khỏi standard working hours (cho phép về sớm 1 giờ)
- Logic check benefit (dùng chung cho tất cả nơi tính attendance):

```
if type in ('Young Child', 'Maternity Leave'):
    benefit = True  # Luôn được hưởng
elif type == 'Pregnant' and apply_benefit == 1:
    benefit = True  # Chỉ khi được tick
```

### Các file tham chiếu Employee Maternity để tính attendance

| File | Function | Mô tả |
|------|----------|-------|
| `api/employee/employee_utils.py` | `check_employee_maternity_status()` | Check maternity status + benefit |
| `overrides/employee_checkin/employee_checkin.py` | `check_maternity_benefit()` | Check benefit khi tính checkin |
| `overrides/shift_type/shift_type_optimized.py` | `preload_reference_data()` | Bulk load maternity data |
| `overrides/shift_type/shift_type_optimized.py` | `check_maternity_status_cached()` | Check từ preloaded data |
| `overrides/attendance/attendance.py` | `get_attendance_custom_additional_info()` | Hiển thị info trên Attendance form |
| `report/maternity_tracking_report/` | `get_data()` | Report thai sản |

## Hooks (hooks.py)

```python
# Employee Maternity Events
"Employee Maternity": {
    "validate": "...employee_maternity.validate_maternity",
    "on_update": "...employee_maternity.on_maternity_update",
    "after_insert": "...employee_maternity.on_maternity_insert",
    "on_trash": "...employee_maternity.on_maternity_delete",
}

# Leave Application → Employee Maternity sync
"Leave Application": {
    "on_submit": "...leave_application.sync_maternity_leave_on_submit",
    "on_cancel": "...leave_application.sync_maternity_leave_on_cancel",
    "on_update_after_submit": "...leave_application.sync_maternity_leave_on_update",
}
```

## Validation

- `from_date` phải trước `to_date`
- Không cho phép overlap ngày giữa các record cùng employee
- Record type "Maternity Leave" không thể tạo/sửa thủ công (chỉ từ Leave Application)

## Data flow

```
Leave Application (submit/cancel/amend)
    │ leave_type == "Nghỉ hưởng BHXH/... Thai sản"
    ▼
Employee Maternity (auto sync, type="Maternity Leave")
    │
    ├── on_update / after_insert / on_trash
    ▼
Background Job: bulk_update_attendance_optimized()
    │
    ▼
Attendance records (custom_maternity_benefit = 0 hoặc 1)
    │
    ▼
Working hours calculation: standard_hours - 1 (nếu benefit = 1)
```

## SQL Query Pattern

Tất cả nơi query maternity đều dùng pattern:

```sql
SELECT type, from_date, to_date, apply_benefit
FROM `tabEmployee Maternity`
WHERE employee = %(employee)s
  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
  AND from_date <= %(date)s
  AND to_date >= %(date)s
```
