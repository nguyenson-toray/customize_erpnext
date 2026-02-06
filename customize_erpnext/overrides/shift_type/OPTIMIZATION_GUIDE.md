# Bulk Attendance Processing - Optimization Guide

**Last Updated:** 2026-02-05

## Performance

| Metric | Value |
|--------|-------|
| Processing Time | ~30s (30 days × 800 employees) |
| Throughput | ~800 records/sec |
| Batch Size | 100 employees |

## Architecture

### Dual Flow (Same Core Logic)

```
┌──────────────────┐    ┌──────────────────┐
│  HRMS Hook       │    │  UI Manual       │
│  (hourly_long)   │    │  (On-Demand)     │
└────────┬─────────┘    └────────┬─────────┘
         │  Monkey Patch          │  Direct Call
         └───────────┬────────────┘
                     ▼
    ┌────────────────────────────────────────┐
    │  _core_process_attendance_logic_optimized()  │
    │                                        │
    │  1. Preload Reference Data             │
    │  2. Bulk Update Checkin Shifts         │
    │  3. Process Auto-Enabled Shifts        │
    │  4. Mark Absent/Maternity Leave        │
    └────────────────────────────────────────┘
```

## Processing Steps

### Step 1: Preload Reference Data

Load ALL reference data in ONE pass:
- Employees (name, company, dept, maternity)
- Shift Types (start/end time, OT settings)
- Shift Assignments (employee → shift mapping)
- Holiday Lists
- Existing Attendance
- Leave Type Abbreviations

### Step 2: Bulk Update Checkin Shifts

Update checkins with `shift=NULL` using SQL CASE WHEN:
```sql
UPDATE `tabEmployee Checkin`
SET shift = CASE name
    WHEN 'c1' THEN 'Day'
    WHEN 'c2' THEN 'Night'
    ...
END
WHERE name IN ('c1', 'c2', ...)
```

### Step 3: Process Auto-Enabled Shifts

For each shift type:
1. Get checkins for date range
2. Filter out `shift_start = NULL`
3. Group by (employee, date)
4. Calculate working hours, overtime
5. Bulk insert attendance records

### Step 4: Mark Absent/Maternity Leave

For employees without attendance:
- Check maternity status → "Maternity Leave"
- Otherwise → "Absent"

## Key Optimizations

### 1. Preloading Reference Data

```python
# Before: 24,000 queries per run
shift = frappe.db.get_value("Shift Assignment", ...)

# After: ~10 queries total
ref_data = preload_reference_data(employees, from_date, to_date)
shift = get_employee_shift_cached(employee, day, ref_data)
```

### 2. SQL CASE WHEN Bulk Update

```python
# Before: ~2 hours for 15,779 checkins
for checkin in checkins:
    doc = frappe.get_doc("Employee Checkin", checkin.name)
    doc.fetch_shift()
    doc.save()

# After: ~2-3 minutes
frappe.db.sql("""
    UPDATE `tabEmployee Checkin`
    SET shift = CASE name ... END,
        shift_start = CASE name ... END
    WHERE name IN (...)
""")
```

### 3. Preserve Leave Data

When recalculating attendance, preserve leave fields:
```python
if old_att.get('leave_type'):
    att_data['leave_type'] = old_att.get('leave_type')
    att_data['leave_application'] = old_att.get('leave_application')
    att_data['custom_leave_type_2'] = old_att.get('custom_leave_type_2')
    att_data['custom_leave_application_2'] = old_att.get('custom_leave_application_2')
    att_data['custom_leave_application_abbreviation'] = old_att.get('custom_leave_application_abbreviation')
```

### 4. Attendance Status Logic (Leave + Checkin)

When attendance has leave AND checkin data:

| Leave Type | Has Checkin | Status |
|------------|-------------|--------|
| Half Day | Any | **Half Day** |
| Full Day (On Leave) | Yes (wh > 0) | **Present** |
| Full Day (On Leave) | No (wh = 0) | **On Leave** |

```python
has_checkin = att_data.get('working_hours', 0) > 0 or att_data.get('in_time')

if old_att.get('status') == 'Half Day':
    att_data['status'] = 'Half Day'
    if has_checkin:
        att_data['half_day_status'] = 'Present'
        att_data['modify_half_day_status'] = 1
elif old_att.get('status') == 'On Leave':
    if has_checkin:
        att_data['status'] = 'Present'  # Has checkin → Present
    else:
        att_data['status'] = 'On Leave'  # No checkin → On Leave
```

**Đồng bộ với:** `leave_application.py:custom_create_or_update_attendance()`

## Configuration

### Batch Sizes

```python
EMPLOYEE_CHUNK_SIZE_OPTIMIZED = 100
BULK_INSERT_BATCH_SIZE = 500
CHECKIN_UPDATE_BATCH_SIZE = 1000
```

## Files

| File | Description |
|------|-------------|
| `shift_type_optimized.py` | Optimized core logic |
| `shift_type.py` | Helper functions |
| `__init__.py` | Monkey patches |
| `attendance_list.js` | UI integration |

## Monkey Patches

```python
# __init__.py
import hrms.hr.doctype.shift_type.shift_type as hrms_st

hrms_st.process_auto_attendance_for_all_shifts = custom_process_auto_attendance_for_all_shifts
hrms_st.ShiftType.get_employee_checkins = custom_get_employee_checkins
hrms_st.ShiftType.should_mark_attendance = custom_should_mark_attendance
hrms_st.ShiftType.process_auto_attendance = custom_process_auto_attendance
```

## Testing

```python
# Console test
from hrms.hr.doctype.shift_type.shift_type import process_auto_attendance_for_all_shifts
from datetime import date

result = process_auto_attendance_for_all_shifts(
    employees=['TIQN-0031'],
    days=[date(2026, 2, 3)]
)
print(result)
```

## Troubleshooting

### Checkins with NULL shift

```sql
SELECT name, time, shift, shift_start
FROM `tabEmployee Checkin`
WHERE employee = 'TIQN-0031' AND shift IS NULL
```

Fix:
```python
from customize_erpnext.overrides.employee_checkin.employee_checkin import bulk_update_employee_checkin
bulk_update_employee_checkin('2026-02-01', '2026-02-04')
```
