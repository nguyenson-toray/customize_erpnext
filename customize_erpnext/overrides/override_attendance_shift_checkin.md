# Attendance, Shift & Check-in Override Documentation

## 📋 Tổng Quan

Module này override logic xử lý attendance từ HRMS để:
- ✅ Tự động tạo attendance từ check-in logs
- ✅ Đánh absent cho nhân viên không check-in
- ✅ Đánh maternity leave cho nhân viên mang thai/nghỉ thai sản
- ✅ Hỗ trợ xử lý bulk attendance qua UI
- ✅ Monkey patch Attendance để cho phép status "Maternity Leave"

---

## 🎯 Core Processing Logic

### `_core_process_attendance_logic(employees, days, from_date, to_date)`

**Mục đích:** Hàm core xử lý attendance, dùng chung cho tất cả execution paths

**Luồng xử lý:**

```
STEP 1: Fix checkins with null shift
   └─> get_employee_checkins_name_with_null_shift()
   └─> update_fields_for_employee_checkins()

STEP 2: Process auto-enabled shifts
   └─> Loop through shifts (enable_auto_attendance = 1)
       └─> Count before
       └─> doc.process_auto_attendance(employees, days)
       └─> Count after
       └─> Store stats

STEP 3: Mark absent/maternity leave
   └─> mark_bulk_attendance_absent_maternity_leave(employees, days)
       ├─> Check maternity status
       ├─> Determine shift for each employee/date
       └─> Create attendance records

STEP 4: Recount ALL shifts
   └─> Query all shifts in date range
   └─> Update stats with final counts
   └─> Include non-auto-enabled shifts

STEP 5: Calculate metrics
   └─> Processing time
   └─> Records created/updated
   └─> Employees with/without attendance
   └─> Throughput (records/sec)
```

**Return:**
```python
{
    "shifts_processed": int,
    "per_shift": {
        "Shift Name": {
            "before": int,
            "after": int,
            "new_or_updated": int,
            "records": int
        }
    },
    "total_employees": int,
    "total_days": int,
    "errors": int,
    "processing_time": float,
    "actual_records": int,
    "total_records_in_db": int,
    "employees_with_attendance": int,
    "employees_skipped": int,
    "records_per_second": float
}
```

---

## 🔄 Execution Paths

### Path 1: Console / Hourly Hook

```python
# Console
from hrms.hr.doctype.shift_type.shift_type import process_auto_attendance_for_all_shifts
process_auto_attendance_for_all_shifts()

# Hook (hourly_long)
hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
```

**Flow:**
```
Monkey Patch
    ↓
custom_process_auto_attendance_for_all_shifts()
    ↓
_core_process_attendance_logic()
```

**Đặc điểm:**
- ✅ Xử lý tất cả nhân viên active
- ✅ Dùng default date range từ shift settings
- ✅ Tự động chạy mỗi giờ

---

### Path 2 & 3: UI Bulk Update (All Dataset Sizes)

```javascript
// UI: Attendance List > 🔄 Bulk Update Attendance
execute_bulk_update_attendance_v2()
```

**Flow:**
```
User clicks button
    ↓
execute_bulk_update_attendance_v2()
    ↓
Set force_sync based on dataset size:
    - Small (≤300): force_sync=1
    - Large (>300): force_sync=0
    ↓
bulk_update_attendance(force_sync)
    ↓
_bulk_update_attendance_worker()
        ↓
    1. Backup shift parameters
        ↓
    2. Set temporary parameters
        ↓
    3. Build days list
        ↓
    4. Build employees list
        ↓
    5. _core_process_attendance_logic()
        ↓
    6. Restore shift parameters (try/finally)
```

**Đặc điểm:**
- ✅ **Auto backup/restore** shift parameters (try/finally)
- ✅ Hỗ trợ filter theo employee/group
- ✅ **Unified logic** cho cả small và large datasets
- ⚡ Small dataset: Sync processing (force_sync=1)
- 🚀 Large dataset: Auto async detection

---

## 🔧 Key Functions

### `mark_bulk_attendance_absent_maternity_leave(employees, days)`

**Mục đích:** Đánh absent/maternity leave cho nhân viên không có check-in

**Logic:**
```python
For each employee:
    For each day:
        1. Check if attendance exists → Skip
        2. Check if has check-in → Skip
        3. Get maternity status:
           - If pregnant → Maternity Leave
           - If maternity leave → Maternity Leave
           - Else → Absent
        4. Determine shift (assignment or default)
        5. Create attendance record
```

**Maternity Detection:**
```sql
-- Pregnant
SELECT 1 FROM \`tabMaternity Benefit Checklist\`
WHERE employee = %s
  AND type = 'Pregnant'
  AND from_date <= %s
  AND to_date >= %s
  AND docstatus = 1

-- Maternity Leave
SELECT 1 FROM \`tabMaternity Benefit Checklist\`
WHERE employee = %s
  AND type = 'Maternity Leave'
  AND from_date <= %s
  AND to_date >= %s
  AND docstatus = 1
```

**Batch Processing:**
- Tạo attendance records theo batch
- Batch size: 100 records
- Commit sau mỗi batch để tránh timeout

---

### Monkey Patches

#### 1. Attendance Validation

**File:** \`customize_erpnext/overrides/attendance/__init__.py\`

```python
from hrms.hr.doctype.attendance.attendance import Attendance
Attendance.validate = custom_attendance_validate

def custom_attendance_validate(self):
    # Allow "Maternity Leave" status
    validate_status(self.status, [
        "Present", "Absent", "On Leave",
        "Half Day", "Work From Home",
        "Maternity Leave"  # ← Added
    ])
    # ... rest of validation
```

#### 2. Shift Type Processing

**File:** \`customize_erpnext/overrides/shift_type/__init__.py\`

```python
import hrms.hr.doctype.shift_type.shift_type as hrms_st

# Override module-level function
hrms_st.process_auto_attendance_for_all_shifts = \\
    custom_process_auto_attendance_for_all_shifts
```

---

## 📊 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    2 EXECUTION PATHS                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Console/Hook                    UI (All Sizes)             │
│      │                               │                      │
│      │                               │                      │
│      ▼                               ▼                      │
│  custom_process            _bulk_update_attendance          │
│  _auto_attendance                _worker                    │
│  _for_all_shifts         (with auto backup/restore)        │
│      │                               │                      │
│      └───────────────────────────────┤                      │
│                                      │                      │
│                                      ▼                      │
│               _core_process_attendance_logic()             │
│                                      │                      │
│      ┌───────────────────────────────┴───────────┐          │
│      │                                           │          │
│      ▼                                           ▼          │
│  Process Auto          Mark Absent/          Recount       │
│  Attendance            Maternity            All Shifts     │
│  (Step 1-2)            (Step 3)             (Step 4)       │
│      │                     │                    │          │
│      └─────────────────────┴────────────────────┘          │
│                            │                               │
│                            ▼                               │
│                     Calculate Metrics                      │
│                        (Step 5)                            │
│                            │                               │
│                            ▼                               │
│                      Return Stats                          │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Configuration

### Shift Type Settings

**Auto-Attendance Enabled Shifts:**
```sql
SELECT name FROM \`tabShift Type\`
WHERE enable_auto_attendance = 1
```

**Parameters:**
- \`process_attendance_after\`: Ngày bắt đầu xử lý
- \`last_sync_of_checkin\`: Thời điểm sync cuối cùng

### Thresholds

**Bulk Update:**
- Small dataset: ≤ 300 records → Sync processing
- Large dataset: > 300 records → Background job
- Configurable: \`frappe.conf.bulk_attendance_async_threshold\`

---

## 🐛 Debugging

### Log Levels

**Important logs only (production):**
```python
frappe.logger().info("Processing attendance...")
frappe.logger().error("Error: ...")
```

**Console output removed:**
```python
# Removed excessive print statements
# Only critical info logged via frappe.logger()
```

### Common Issues

1. **Type Error: 'datetime.date' instead of 'str'**
   - ✅ Fixed: Auto-convert dates to strings
   - Location: \`shift_type.py:519-520\`

2. **Total count mismatch**
   - ✅ Fixed: Recount all shifts after marking absent
   - Location: STEP 4 in core logic

3. **Maternity Leave status rejected**
   - ✅ Fixed: Monkey patch Attendance.validate
   - Location: \`attendance/__init__.py\`

---

## 📈 Performance

### Metrics

**Typical throughput:**
- Console/Hook: ~50-100 records/sec
- UI Small: ~50-100 records/sec
- UI Large (background): ~30-50 records/sec

**Optimization:**
- Batch processing (100 records/batch)
- Cached shift documents
- Single recount query at end
- Efficient SQL queries

---

## 🧪 Testing

### Test Console Path

```python
bench --site erp-sonnt.tiqn.local console

from hrms.hr.doctype.shift_type.shift_type import process_auto_attendance_for_all_shifts
process_auto_attendance_for_all_shifts()
```

### Test UI Path

```
1. Go to Attendance List
2. Click "🔄 Bulk Update Attendance"
3. Select date range
4. Click "Update Attendance"
```

### Verify Results

```sql
-- Check attendance by shift
SELECT
    shift,
    status,
    COUNT(*) as count
FROM \`tabAttendance\`
WHERE attendance_date = '2025-12-20'
GROUP BY shift, status
ORDER BY shift, status;

-- Check maternity leave records
SELECT
    employee,
    attendance_date,
    status,
    shift
FROM \`tabAttendance\`
WHERE status = 'Maternity Leave'
  AND attendance_date >= '2025-12-01'
ORDER BY employee, attendance_date;
```

---

## 📝 Change Log

### v2.1 - Unified UI Paths (2025-12-20)

- ✅ **Consolidated UI paths** - Both small and large datasets now use \`execute_bulk_update_attendance_v2\`
- ✅ **Removed manual backup/restore** - Eliminated \`execute_sequential_attendance_update\` function (~280 lines)
- ✅ **Auto backup/restore** - All UI operations now use try/finally pattern
- ✅ **Simplified codebase** - Reduced from 3 execution paths to 2
- ✅ **Updated documentation** - Reflects new unified architecture

### v2.0 - Refactored (2025-12-20)

- ✅ Created \`_core_process_attendance_logic()\` shared function
- ✅ Refactored all paths to use core logic
- ✅ Cleaned up debug statements
- ✅ Added comprehensive documentation
- ✅ Fixed type conversion issues
- ✅ Fixed total count mismatch

### v1.0 - Initial Implementation

- Added maternity leave support
- Override Attendance validation
- Bulk update UI functionality

---

## 👥 Maintainers

**Code Location:**
- \`/customize_erpnext/overrides/shift_type/shift_type.py\`
- \`/customize_erpnext/overrides/attendance/\`

**Key Files:**
- \`shift_type.py\`: Core processing logic
- \`attendance/__init__.py\`: Monkey patches
- \`attendance_list.js\`: UI integration

---

## 🔗 Related Doctypes

- \`Shift Type\`: Shift configuration
- \`Attendance\`: Attendance records
- \`Employee Checkin\`: Check-in logs
- \`Maternity Benefit Checklist\`: Maternity tracking
- \`Shift Assignment\`: Employee shift assignments

---

**Last Updated:** 2025-12-20
**Version:** 2.1 - Unified UI Paths
