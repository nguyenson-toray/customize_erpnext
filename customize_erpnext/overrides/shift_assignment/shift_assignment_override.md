# Shift Assignment Override

## Tổng quan

Tự động tính toán lại Attendance khi Shift Assignment thay đổi.

## Hook Functions

| Hook | Function | Trigger |
|------|----------|---------|
| `on_submit` | `recalculate_attendance_on_submit` | Shift Assignment submitted |
| `on_cancel` | `recalculate_attendance_on_cancel` | Shift Assignment cancelled |
| `before_save` | `capture_old_dates_before_save` | Before save (for date change) |
| `on_update_after_submit` | `recalculate_attendance_on_date_change` | Dates changed after submit |

## Logic

### On Submit/Cancel

Tính toán lại Attendance từ `start_date` đến `end_date` (hoặc today nếu null).

### On Date Change

Tính toán lại từ `min(old_start, new_start)` đến `max(old_end, new_end)`.

## Dynamic Timeout

```python
def _calculate_job_timeout(from_date, to_date):
    """
    BASE_TIMEOUT = 30 seconds
    SECONDS_PER_DAY = 2 seconds
    MIN_TIMEOUT = 60 seconds
    MAX_TIMEOUT = 600 seconds
    """
```

## Leave Data Preservation

Khi recalculate, preserve:
- `leave_type`, `leave_application`
- `custom_leave_type_2`, `custom_leave_application_2`
- `custom_leave_application_abbreviation`

## Hooks Configuration

```python
# hooks.py
doc_events = {
    "Shift Assignment": {
        "on_submit": "customize_erpnext.overrides.shift_assignment.shift_assignment.recalculate_attendance_on_submit",
        "on_cancel": "customize_erpnext.overrides.shift_assignment.shift_assignment.recalculate_attendance_on_cancel",
        "before_save": "customize_erpnext.overrides.shift_assignment.shift_assignment.capture_old_dates_before_save",
        "on_update_after_submit": "customize_erpnext.overrides.shift_assignment.shift_assignment.recalculate_attendance_on_date_change"
    }
}
```
