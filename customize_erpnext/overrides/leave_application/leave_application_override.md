# Leave Application Override

**Last Updated:** 2026-02-05

## Tổng quan

Override HRMS Leave Application để hỗ trợ:
1. Validate attendance với logic mới (chỉ block Full Day + working_hours >= 8)
2. Attendance status logic: Half Day / Present / On Leave
3. 2 Half Day LAs riêng biệt cùng ngày (dual leave)

## Custom Fields (Attendance)

| Field | Type | Description |
|-------|------|-------------|
| `custom_leave_type_2` | Link (Leave Type) | Leave type của LA thứ 2 |
| `custom_leave_application_2` | Link (Leave Application) | LA thứ 2 |
| `custom_leave_application_abbreviation` | Data | Abbreviation (P/2, OP/2, etc.) |

## Configuration

```python
# leave_application.py
FULL_DAY_WORKING_HOURS_THRESHOLD = 8  # Chỉ block khi >= 8h
```

## Attendance Status Logic

### validate_attendance()

| Leave Type | Working Hours | Kết quả |
|------------|---------------|---------|
| Half Day | Any | ✅ Cho phép |
| Full Day | < 8h | ✅ Cho phép |
| Full Day | >= 8h | ❌ Block |

### create_or_update_attendance()

| Leave Type | Has Check-in | Attendance Status |
|------------|--------------|-------------------|
| Half Day | Any | **Half Day** |
| Full Day | Yes (wh > 0) | **Present** |
| Full Day | No (wh = 0) | **On Leave** |

## Override Functions

### 1. `custom_validate_attendance()`

```python
# Logic mới
- Half Day leave: LUÔN cho phép
- Full Day leave + working_hours >= 8: BLOCK
- Full Day leave + working_hours < 8: Cho phép
```

### 2. `custom_create_or_update_attendance()`

Status logic:
```python
if is_half_day:
    status = "Half Day"
elif has_checkin:  # working_hours > 0 or in_time
    status = "Present"
else:
    status = "On Leave"
```

Hỗ trợ dual leave:
- LA1: `leave_type`, `leave_application`
- LA2: `custom_leave_type_2`, `custom_leave_application_2`

### 3. `on_leave_application_cancel()` (Hook)

Xử lý cancel khi có dual leave:
- LA1 cancel + LA2 exists → Swap LA2 → LA1
- LA2 cancel → Clear LA2 fields
- LA only → Let HRMS handle

## Abbreviation

| LA1 | LA2 | Display |
|-----|-----|---------|
| Sick | - | O/2 |
| Annual | - | P/2 |
| Sick | Annual | OP/2 |

## Files

```
overrides/
├── leave_application/
│   ├── __init__.py              # Monkey patches
│   ├── leave_application.py     # Override functions
│   └── leave_application_override.md
└── leave_utils.py               # Helper functions
```

## Monkey Patches

```python
# __init__.py
LeaveApplication.validate_attendance = custom_validate_attendance
LeaveApplication.create_or_update_attendance = custom_create_or_update_attendance
```

## Doc Events (hooks.py)

```python
"Leave Application": {
    "on_cancel": "customize_erpnext.overrides.leave_application.leave_application.on_leave_application_cancel"
}
```

## Related: shift_type_optimized.py

`_core_process_attendance_logic_optimized()` cũng sử dụng cùng logic status:

```python
# Khi update attendance có leave
if old_status == 'Half Day':
    status = 'Half Day'
    half_day_status = 'Present' if has_checkin else 'Absent'
elif old_status == 'On Leave':
    status = 'Present' if has_checkin else 'On Leave'
```
