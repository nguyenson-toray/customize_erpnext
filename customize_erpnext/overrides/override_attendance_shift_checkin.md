# Attendance, Shift & Check-in Override Documentation

**Last Updated:** 2026-02-04

## Tổng Quan

Module override xử lý attendance từ HRMS:
- Tự động tạo attendance từ check-in logs
- Đánh absent/maternity leave cho nhân viên không check-in
- Hỗ trợ bulk attendance qua UI
- Preserve leave data khi recalculate

## Core Function

### `_core_process_attendance_logic_optimized()`

```
STEP 1: Preload Reference Data
   └─> employees, shifts, assignments, holidays, existing attendance

STEP 2: Bulk Update Checkin Shifts
   └─> SQL CASE WHEN for checkins with shift=NULL

STEP 3: Process Auto-Enabled Shifts
   └─> Calculate working hours, overtime
   └─> Bulk insert attendance
   └─> Preserve leave fields

STEP 4: Mark Absent/Maternity Leave
   └─> Check maternity status
   └─> Create attendance records
```

## Execution Paths

### Path 1: HRMS Hourly Hook

```python
# Hook (hourly_long) → Monkey patched
hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
    ↓
custom_process_auto_attendance_for_all_shifts()
    ↓
_core_process_attendance_logic_optimized()
```

### Path 2: UI Bulk Update

```javascript
// Attendance List > Update Attendance
execute_bulk_update_attendance_v2()
    ↓
bulk_update_attendance_optimized()
    ↓
_core_process_attendance_logic_optimized()
```

## Monkey Patches

### Attendance Validation

```python
# attendance/__init__.py
from hrms.hr.doctype.attendance.attendance import Attendance
Attendance.validate = custom_attendance_validate

# Allows "Maternity Leave" status
```

### Shift Type Processing

```python
# shift_type/__init__.py
import hrms.hr.doctype.shift_type.shift_type as hrms_st

hrms_st.process_auto_attendance_for_all_shifts = custom_process_auto_attendance_for_all_shifts
hrms_st.ShiftType.get_employee_checkins = custom_get_employee_checkins
hrms_st.ShiftType.should_mark_attendance = custom_should_mark_attendance
hrms_st.ShiftType.process_auto_attendance = custom_process_auto_attendance
```

## Leave Data Preservation

Khi recalculate attendance, preserve:
- `leave_type`
- `leave_application`
- `custom_leave_type_2`
- `custom_leave_application_2`
- `custom_leave_application_abbreviation`

## Maternity Detection

```sql
-- Check pregnant/maternity leave status
SELECT 1 FROM `tabMaternity Benefit Checklist`
WHERE employee = %s
  AND type IN ('Pregnant', 'Maternity Leave')
  AND from_date <= %s AND to_date >= %s
  AND docstatus = 1
```

## Files

| Path | Description |
|------|-------------|
| `overrides/shift_type/shift_type_optimized.py` | Core optimized logic |
| `overrides/shift_type/shift_type.py` | Helper functions |
| `overrides/shift_type/__init__.py` | Monkey patches |
| `overrides/attendance/__init__.py` | Attendance validation |
| `public/js/attendance_list.js` | UI integration |

## Related Doctypes

- `Shift Type`: Shift configuration
- `Attendance`: Attendance records
- `Employee Checkin`: Check-in logs
- `Maternity Benefit Checklist`: Maternity tracking
- `Shift Assignment`: Employee shift assignments
- `Leave Application`: Leave records
