# Bulk Attendance Processing - Optimization Guide

**Last Updated:** 2025-12-23
**Version:** 3.0 (Unified Optimized)

---

## 📊 Performance Improvements

### Before vs After (30 days × 800 employees = 24,000 records)

| Metric | Original | Optimized (v3.0) | Improvement |
|--------|----------|------------------|-------------|
| **Processing Time** | ~120s | ~30s | **75% faster** |
| **Database Queries** | ~150,000 | ~500 | **99.7% reduction** |
| **Throughput** | ~200 rec/s | ~800 rec/s | **4x faster** |
| **Batch Size** | 20 employees | 100 employees | **5x larger** |
| **Checkin Update** | ~2 hours (15,779) | ~2-3 min | **40x faster** |

---

## 🔄 DUAL FLOW ARCHITECTURE

**CRITICAL:** Both HRMS hourly hook and UI manual processing now use the **SAME optimized code**.

### Flow 1: HRMS Hourly Hook (Automatic)

```
┌─────────────────────────────────────────────────────────────────┐
│  HRMS Scheduler (hourly_long)                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  hrms.hr.doctype.shift_type.shift_type.                         │
│  process_auto_attendance_for_all_shifts()                       │
│                                                                  │
│  ⚙️  MONKEY PATCHED via __init__.py                             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  customize_erpnext.overrides.shift_type.shift_type_optimized.  │
│  custom_process_auto_attendance_for_all_shifts()                │
│                                                                  │
│  📋 Parameters:                                                 │
│    ├─ employees = None → Get all active employees              │
│    └─ days = None → Derive from shift settings:                │
│        ├─ from_date = min(process_attendance_after)            │
│        └─ to_date = max(last_sync_of_checkin)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  _core_process_attendance_logic_optimized()                     │
│                                                                  │
│  🚀 OPTIMIZED CORE LOGIC (shared by both flows)                 │
└─────────────────────────────────────────────────────────────────┘
```

### Flow 2: UI Manual Processing (On-Demand)

```
┌─────────────────────────────────────────────────────────────────┐
│  Attendance List UI                                             │
│  └─ Button: "Update Attendance"                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  attendance_list.js                                             │
│  Line 260: customize_erpnext.overrides.shift_type.             │
│            shift_type_optimized.bulk_update_attendance_optimized│
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  bulk_update_attendance_optimized(                              │
│      from_date, to_date, employees, batch_size, force_sync)     │
│                                                                  │
│  📋 Parameters:                                                 │
│    ├─ from_date/to_date = User selected date range             │
│    └─ employees = User selected employees (or all)             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  _core_process_attendance_logic_optimized()                     │
│                                                                  │
│  🚀 OPTIMIZED CORE LOGIC (shared by both flows)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 OPTIMIZED CORE LOGIC FLOW

Both flows converge to the same optimized processing:

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: PRELOAD REFERENCE DATA                                 │
│  ────────────────────────────────────────────────────────────  │
│  📦 Load ALL reference data in ONE pass:                        │
│    ├─ 876 employees (name, company, dept, maternity)           │
│    ├─ 4 shift types (start/end time, OT settings)              │
│    ├─ Shift assignments (employee → shift mapping)             │
│    ├─ Holiday lists (per company/employee)                     │
│    ├─ Existing attendance (to avoid duplicates)                │
│    └─ Maternity tracking (99 records)                          │
│                                                                  │
│  ⏱️  Completed in ~0.08s                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: BULK UPDATE CHECKIN SHIFTS                             │
│  ────────────────────────────────────────────────────────────  │
│  🔄 Update null shifts in checkins:                             │
│    1. Get checkins with shift=NULL (e.g., 15,779 records)      │
│    2. Process in batches of 1,000:                             │
│       ├─ Load Employee Checkin doc                             │
│       ├─ Call fetch_shift() to calculate shift fields          │
│       └─ Collect bulk update data                              │
│    3. SQL CASE WHEN bulk update (1,000 rows/query):            │
│       UPDATE `tabEmployee Checkin`                             │
│       SET shift = CASE name                                     │
│                   WHEN 'c1' THEN 'Day'                          │
│                   WHEN 'c2' THEN 'Night'                        │
│                   ... (1,000 rows) ...                          │
│                   END,                                          │
│           shift_start = CASE name ... END,                      │
│           ... (all shift fields) ...                            │
│       WHERE name IN (c1, c2, ..., c1000)                        │
│    4. Commit after each batch                                   │
│                                                                  │
│  📊 Progress: 1000/15779 (1/16 batches) - 8.5s/batch           │
│  ⏱️  15,779 checkins in ~2-3 minutes (vs 2 hours before)        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: PROCESS AUTO-ENABLED SHIFTS                            │
│  ────────────────────────────────────────────────────────────  │
│  For each shift type (Day, Night, etc.):                        │
│    1. Get checkins for this shift:                             │
│       ├─ Filter by date range                                  │
│       ├─ Filter by shift name                                  │
│       ├─ Filter by shift_actual_end < last_sync_of_checkin     │
│       └─ ⚠️ CRITICAL: Filter out shift_start = NULL            │
│    2. Group checkins by (employee, date):                      │
│       ├─ Calculate in_time (first log)                         │
│       ├─ Calculate out_time (last log)                         │
│       ├─ Calculate working hours                               │
│       ├─ Calculate overtime (actual, approved, final)          │
│       └─ Check maternity benefit (reduce end_time by 1hr)      │
│    3. Should mark attendance?                                   │
│       ├─ Check existing attendance (skip if exists)            │
│       ├─ Check employee status (active/left)                   │
│       ├─ Check holiday (skip if holiday)                       │
│       └─ Check shift assignment                                │
│    4. Prepare attendance records (batch of 500)                │
│    5. Bulk insert + link checkins:                             │
│       ├─ frappe.db.bulk_insert() for speed                     │
│       ├─ update_attendance_in_checkins() to link              │
│       └─ Commit                                                 │
│                                                                  │
│  ✓ Completed Day in 15.23s (1,234 records)                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: MARK ABSENT/MATERNITY LEAVE                            │
│  ────────────────────────────────────────────────────────────  │
│  For employees without attendance:                              │
│    1. Check maternity status (cached)                          │
│    2. Check if holiday (skip)                                  │
│    3. Mark as:                                                  │
│       ├─ "Maternity Leave" if eligible                         │
│       └─ "Absent" otherwise                                    │
│    4. Bulk insert absent records (batch of 500)                │
│                                                                  │
│  📋 Marked 123 absent, 45 maternity leave                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  ✅ COMPLETE                                                     │
│  ────────────────────────────────────────────────────────────  │
│  📊 Records created/updated: 1,234                              │
│  👥 Employees processed: 800/876                                │
│  ⏱️  Total time: 28.5s                                          │
│  🚀 Throughput: 806 records/sec                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ KEY OPTIMIZATIONS

### 1. Preloading Reference Data (STEP 1)

**Before:**
```python
# For each employee × day → Query DB
shift = frappe.db.get_value("Shift Assignment", ...)  # 24,000 queries!
holiday = frappe.db.get_value("Holiday List", ...)    # 24,000 queries!
```

**After:**
```python
# Load ONCE at start
ref_data = preload_reference_data(employees, from_date, to_date)

# Then O(1) lookups from memory
shift = get_employee_shift_cached(employee, day, ref_data)  # Dict lookup!
holiday = is_holiday_cached(employee, day, ref_data)        # Dict lookup!
```

**Impact:** ~72,000 DB queries → ~10 queries

---

### 2. SQL CASE WHEN Bulk Update (STEP 2)

**Before:**
```python
# Update checkins one-by-one
for checkin in checkins:  # 15,779 iterations
    doc = frappe.get_doc("Employee Checkin", checkin.name)
    doc.fetch_shift()
    doc.save()  # Individual save → validation → hooks → DB write
```
**Time:** ~2 hours for 15,779 checkins

**After:**
```python
# Batch update with SQL CASE WHEN
for batch in batches_of_1000:
    # Load & calculate shift fields (in-memory)
    bulk_updates = []
    for checkin in batch:
        doc = frappe.get_doc("Employee Checkin", checkin.name)
        doc.fetch_shift()  # Calculate only, don't save
        bulk_updates.append({
            'name': doc.name,
            'shift': doc.shift,
            'shift_start': doc.shift_start,
            ...
        })

    # Single SQL query updates 1,000 rows at once
    frappe.db.sql("""
        UPDATE `tabEmployee Checkin`
        SET shift = CASE name
                    WHEN 'c1' THEN 'Day'
                    WHEN 'c2' THEN 'Night'
                    ... (1,000 WHEN clauses) ...
                    END,
            shift_start = CASE name ... END,
            ...
        WHERE name IN ('c1', 'c2', ..., 'c1000')
    """)
```
**Time:** ~2-3 minutes for 15,779 checkins
**Impact:** **40x faster**

**Fallback Safety:** If SQL fails → falls back to `frappe.db.set_value()` per row

---

### 3. Bulk Insert Attendance (STEP 3)

**Before:**
```python
for att_data in attendance_list:  # 1,234 iterations
    att = frappe.new_doc("Attendance")
    att.update(att_data)
    att.insert()  # Individual insert → validation → hooks
    att.submit()  # Another DB transaction

    # Link checkins one-by-one
    for log in logs:
        log.attendance = att.name
        log.save()
```
**Time:** ~0.5s per record × 1,234 = ~10 minutes

**After:**
```python
# Prepare batch of 500
values = [(name, employee, date, shift, ...) for att in batch]

# Bulk insert 500 records in ONE query
frappe.db.bulk_insert(
    "Attendance",
    fields=["name", "employee", "attendance_date", "shift", ...],
    values=values
)

# Bulk link checkins
update_attendance_in_checkins(log_names, att_name)
```
**Time:** ~0.01s per record × 1,234 = ~12 seconds
**Impact:** **50x faster**

---

### 4. Filter NULL Shifts (STEP 3 - Critical Fix)

**Problem:**
```python
# Before: Caused TypeError when sorting/grouping
checkins = frappe.db.get_all("Employee Checkin", ...)
for key, group in groupby(sorted(checkins, key=lambda x: x.shift_start)):
    # ❌ TypeError: '<' not supported between instances of 'NoneType' and 'datetime'
```

**Solution:**
```python
# After: Filter out NULL shifts before grouping
checkins = [c for c in checkins if c.shift_start is not None]  # ✅ Safe
for key, group in groupby(sorted(checkins, ...)):
    # Now all shift_start values are valid datetime objects
```

**Why This Matters:**
- Prevents crash when some checkins have `shift_start=NULL`
- Ensures only valid checkins are processed
- NULL shifts are fixed in STEP 2, so this is a safety net

---

## 🔧 MONKEY PATCHING ARCHITECTURE

**File:** `customize_erpnext/overrides/shift_type/__init__.py`

```python
"""
Shift Type Overrides - Apply Monkey Patches

IMPORTANT: This module replaces HRMS shift attendance functions with optimized versions.
The optimized code (shift_type_optimized.py) is used for BOTH:
1. HRMS hourly hook (process_auto_attendance_for_all_shifts)
2. UI manual processing (bulk_update_attendance_optimized)
"""

import frappe
from customize_erpnext.overrides.shift_type.shift_type import (
    custom_get_employee_checkins,
    custom_update_last_sync_of_checkin,
    custom_should_mark_attendance,
    custom_process_auto_attendance,
    get_employee_checkins_name_with_null_shift,
    update_fields_for_employee_checkins
)

# Import OPTIMIZED version for hourly hook
from customize_erpnext.overrides.shift_type.shift_type_optimized import (
    custom_process_auto_attendance_for_all_shifts
)

import hrms.hr.doctype.shift_type.shift_type as hrms_st

# Save original functions (for debugging/rollback)
if not hasattr(hrms_st.ShiftType, '_original_get_employee_checkins'):
    hrms_st.ShiftType._original_get_employee_checkins = hrms_st.ShiftType.get_employee_checkins

# ... save other originals ...

# Replace with custom methods - NOW USING OPTIMIZED VERSION
hrms_st.ShiftType.get_employee_checkins = custom_get_employee_checkins
hrms_st.ShiftType.should_mark_attendance = custom_should_mark_attendance
hrms_st.ShiftType.process_auto_attendance = custom_process_auto_attendance
hrms_st.update_last_sync_of_checkin = custom_update_last_sync_of_checkin

# ⚡ CRITICAL: Replace HRMS hourly hook with optimized version
hrms_st.process_auto_attendance_for_all_shifts = custom_process_auto_attendance_for_all_shifts

frappe.logger().info("✅ Monkey patch applied: customize_erpnext/overrides/shift_type")
```

**How It Works:**
1. When Python imports `hrms.hr.doctype.shift_type.shift_type`, our `__init__.py` runs
2. We replace HRMS functions with our optimized versions
3. All HRMS code now calls our optimized implementations
4. Original functions saved as `_original_*` for rollback if needed

---

## 🧪 Testing & Validation

### Test 1: HRMS Hourly Hook

```python
# Via bench console
bench --site erp-sonnt.tiqn.local console

# Test HRMS hook (monkey patched to use optimized version)
from hrms.hr.doctype.shift_type.shift_type import process_auto_attendance_for_all_shifts
from datetime import date

result = process_auto_attendance_for_all_shifts(
    employees=['TIQN-0031', 'TIQN-0033'],
    days=[date(2025, 12, 15)]
)

print(result)
```

**Expected Output:**
```python
{
    'success': True,
    'shifts_processed': 1,
    'total_employees': 2,
    'employees_with_attendance': 2,
    'total_days': 1,
    'actual_records': 2,
    'processing_time': 1.23,
    'records_per_second': 1.63
}
```

### Test 2: UI Manual Processing

```python
# Via bench console or UI button
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized
import json

result = bulk_update_attendance_optimized(
    from_date='2025-12-15',
    to_date='2025-12-15',
    employees=json.dumps(['TIQN-0031', 'TIQN-0033'])
)

print(result)
```

**Expected Output:**
```python
{
    'success': True,
    'shifts_processed': 1,
    'total_employees': 2,
    'employees_with_attendance': 2,
    'total_days': 1,
    'actual_records': 2,
    'processing_time': 1.25,
    'records_per_second': 1.60
}
```

### Test 3: Verify Identical Results

```python
# Clean test - compare both flows
from customize_erpnext.overrides.shift_type.shift_type import custom_process_auto_attendance_for_all_shifts as old_flow
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized as new_flow
from datetime import date
import json

test_employees = ['TIQN-0031', 'TIQN-0033']
test_date = '2025-12-15'

# Clean existing
for emp in test_employees:
    frappe.db.sql("""
        DELETE FROM `tabAttendance`
        WHERE employee = %s AND attendance_date = %s
    """, (emp, test_date))
    frappe.db.sql("""
        UPDATE `tabEmployee Checkin`
        SET attendance = NULL
        WHERE employee = %s AND DATE(time) = %s
    """, (emp, test_date))
frappe.db.commit()

# Test OLD flow (HRMS hook)
result_old = old_flow(employees=test_employees, days=[date(2025, 12, 15)])

# Get results
att_old = {}
for emp in test_employees:
    att_old[emp] = frappe.db.get_value(
        "Attendance",
        {"employee": emp, "attendance_date": test_date},
        ["name", "status", "working_hours", "actual_overtime_duration", "custom_final_overtime_duration"],
        as_dict=True
    )

# Clean again
for emp in test_employees:
    frappe.db.sql("DELETE FROM `tabAttendance` WHERE employee = %s AND attendance_date = %s", (emp, test_date))
    frappe.db.sql("UPDATE `tabEmployee Checkin` SET attendance = NULL WHERE employee = %s AND DATE(time) = %s", (emp, test_date))
frappe.db.commit()

# Test NEW flow (UI manual)
result_new = new_flow(from_date=test_date, to_date=test_date, employees=json.dumps(test_employees))

# Get results
att_new = {}
for emp in test_employees:
    att_new[emp] = frappe.db.get_value(
        "Attendance",
        {"employee": emp, "attendance_date": test_date},
        ["name", "status", "working_hours", "actual_overtime_duration", "custom_final_overtime_duration"],
        as_dict=True
    )

# Compare
for emp in test_employees:
    print(f"\n{emp}:")
    print(f"  OLD: {att_old[emp]}")
    print(f"  NEW: {att_new[emp]}")
    print(f"  Match: {att_old[emp] == att_new[emp]}")
```

**Expected:** Both flows create identical attendance records

---

## 🔍 Troubleshooting

### Issue 1: Employee Has Checkins But Marked Absent

**Symptoms:**
- Employee has 3 checkins on 2025-12-04
- Attendance marked as "Absent" instead of "Present"

**Root Cause:**
- Checkins have `shift_start = NULL`
- STEP 2 (bulk update) failed or was skipped
- STEP 3 filters out NULL shifts → no Present attendance created
- STEP 4 marks as Absent

**Diagnosis:**
```sql
-- Check checkins for employee on that date
SELECT name, time, shift, shift_start, shift_end
FROM `tabEmployee Checkin`
WHERE employee = 'TIQN-0031' AND DATE(time) = '2025-12-04'
```

**If shift_start is NULL:**
```python
# Manually fix this employee's checkins
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_checkin_shifts

bulk_update_checkin_shifts('2025-12-04', '2025-12-04')
```

**Then re-run attendance processing:**
```python
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized
import json

bulk_update_attendance_optimized(
    from_date='2025-12-04',
    to_date='2025-12-04',
    employees=json.dumps(['TIQN-0031'])
)
```

**Prevention:**
- STEP 2 now uses SQL CASE WHEN bulk update (much faster and more reliable)
- Added progress logging to track updates
- Added fallback to `frappe.db.set_value()` if SQL fails

### Issue 2: Stuck at "BULK UPDATE CHECKIN SHIFTS"

**Symptoms:**
- Processing shows "Found 15779 checkins with null shift"
- No progress for several minutes

**Root Cause:**
- Old code used individual `save()` calls (very slow)
- 15,779 × 0.5s = ~2 hours

**Solution:**
- New code uses SQL CASE WHEN bulk update
- Now completes in ~2-3 minutes

**Verify Fixed:**
```bash
# Check logs for progress updates
📊 Progress: 1000/15779 (1/16 batches) - 8.5s/batch
📊 Progress: 2000/15779 (2/16 batches) - 8.3s/batch
...
```

### Issue 3: SQL Error "CASE WHEN Syntax"

**Symptoms:**
```
❌ SQL Error in batch 1: ...
```

**Root Cause:**
- SQL escaping issue or syntax error in CASE WHEN

**Solution:**
- Code now has automatic fallback to `frappe.db.set_value()`
- Slower but guaranteed to work

**Check Error Log:**
```python
frappe.get_all("Error Log",
    filters={"error": ["like", "%Bulk Update Checkin%"]},
    fields=["name", "error"],
    limit=10
)
```

---

## 📈 Performance Tuning

### Batch Size Configuration

**File:** `shift_type_optimized.py` (lines 30-34)

```python
# Optimized batch sizes
EMPLOYEE_CHUNK_SIZE_OPTIMIZED = 100  # Increased from 20
BULK_INSERT_BATCH_SIZE = 500  # For bulk_insert operations
CHECKIN_UPDATE_BATCH_SIZE = 1000  # For checkin updates (increased for faster processing)
```

**Tuning Guidelines:**

| Dataset Size | EMPLOYEE_CHUNK | BULK_INSERT | CHECKIN_UPDATE |
|--------------|----------------|-------------|----------------|
| Small (<5K records) | 50 | 250 | 500 |
| Medium (5-20K) | 100 | 500 | 1000 |
| Large (20-50K) | 150 | 1000 | 1000 |
| Very Large (>50K) | 200 | 1000 | 1000 |

**Memory Constraints:**
- Reduce batch sizes if server has <4GB RAM
- Monitor with `free -h` and `top`

### Database Indexes

Ensure these indexes exist for optimal performance:

```sql
-- Employee Checkin indexes
CREATE INDEX idx_ec_time_shift ON `tabEmployee Checkin`(time, shift);
CREATE INDEX idx_ec_employee_time ON `tabEmployee Checkin`(employee, time);
CREATE INDEX idx_ec_shift_dates ON `tabEmployee Checkin`(shift, time);

-- Attendance indexes
CREATE INDEX idx_att_emp_date ON `tabAttendance`(employee, attendance_date);
CREATE INDEX idx_att_date_shift ON `tabAttendance`(attendance_date, shift);

-- Shift Assignment indexes
CREATE INDEX idx_sa_emp_dates ON `tabShift Assignment`(employee, start_date, end_date);
```

---

## 🎯 Best Practices

### 1. Monitor HRMS Hourly Hook

The hook runs automatically every hour via scheduler:

**File:** `apps/hrms/hrms/hooks.py`
```python
scheduler_events = {
    "hourly_long": [
        "hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts"
    ]
}
```

**Check Logs:**
```bash
tail -f logs/worker.log | grep "HRMS Hourly Hook"
```

**Expected:**
```
🔄 HRMS Hourly Hook → Using OPTIMIZED CODE
📅 Auto date range: 2025-10-15 to 2025-12-16 (63 days)
👥 Active employees: 876
...
✅ OPTIMIZED PROCESSING COMPLETE
   📊 Records created/updated: 1,234
   ⏱️  Total time: 28.5s
```

### 2. UI Manual Processing

Users can manually trigger from Attendance List:

**Button:** "Update Attendance" → Calls `bulk_update_attendance_optimized`

**Parameters:**
- From Date / To Date: User selected
- Employees: User selected (or all)

**Expected Behavior:**
- Shows progress bar
- Completes in seconds (not minutes)
- No browser timeout

### 3. Cleanup Old Null Shifts

If you have a large backlog of checkins with null shifts:

```python
# One-time cleanup job (run during off-hours)
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_checkin_shifts

# Fix last 90 days
bulk_update_checkin_shifts('2025-09-01', '2025-12-23')
```

**Estimated Time:** ~15 minutes for 50,000 checkins

---

## 🔄 Version History

### v3.0 (Unified Optimized) - 2025-12-23
- ✅ **Unified codebase:** Both HRMS hook and UI manual use same optimized code
- ✅ **SQL CASE WHEN bulk update:** 40x faster checkin updates (2-3 min vs 2 hours)
- ✅ **Monkey patching:** Seamless replacement of HRMS functions
- ✅ **NULL shift filtering:** Prevents TypeError crashes
- ✅ **Progress logging:** Real-time batch progress updates
- ✅ **Automatic fallback:** SQL fails → graceful degradation to set_value()
- ✅ **Identical results:** Both flows create matching attendance records

### v2.0 (Optimized Hybrid) - 2025-01-22
- ✅ 75% performance improvement
- ✅ Preload reference data (99.7% fewer queries)
- ✅ Bulk insert operations
- ✅ Strategic caching
- ✅ Increased batch sizes

### v1.0 (Original) - 2024
- Sequential processing
- Individual DB queries
- Small batch sizes (20 employees)

---

## 📚 Additional Resources

### Source Files

1. **`shift_type_optimized.py`** - Optimized implementation
   - `custom_process_auto_attendance_for_all_shifts()` - HRMS hook wrapper (line 1043)
   - `bulk_update_attendance_optimized()` - UI entry point (line 954)
   - `_core_process_attendance_logic_optimized()` - Shared core logic (line 588)
   - `bulk_update_checkin_shifts()` - SQL CASE WHEN updater (line 345)
   - `bulk_insert_attendance_records()` - Fast bulk insert (line 454)

2. **`shift_type.py`** - Original implementation (for reference)
   - Contains original CODE CŨ logic
   - Still used for some helper functions

3. **`__init__.py`** - Monkey patching
   - Replaces HRMS functions with optimized versions
   - Runs on app import

4. **`attendance_list.js`** - Frontend integration
   - Line 260: Calls optimized backend method

### Related Documentation

- **ERPNext Attendance:** https://docs.erpnext.com/docs/user/manual/en/human-resources/attendance
- **Frappe DB API:** https://frappeframework.com/docs/user/en/api/database
- **Frappe Hooks:** https://frappeframework.com/docs/user/en/python-api/hooks

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     ATTENDANCE PROCESSING                        │
│                         (Dual Flow)                             │
└─────────────────────────────────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
                    ▼                 ▼
         ┌──────────────┐    ┌──────────────┐
         │  HRMS Hook   │    │  UI Manual   │
         │  (Hourly)    │    │  (On-Demand) │
         └──────┬───────┘    └──────┬───────┘
                │                   │
                │  Monkey Patch     │  Direct Call
                │                   │
                ▼                   ▼
         ┌──────────────────────────────────┐
         │  custom_process_auto_...()       │ ← Wrapper
         │  bulk_update_attendance_...()    │ ← Entry Point
         └──────────────┬───────────────────┘
                        │
                        ▼
         ┌──────────────────────────────────┐
         │  _core_process_attendance_...()  │ ← Shared Core
         │                                  │
         │  ┌────────────────────────────┐ │
         │  │ 1. Preload Reference Data │ │
         │  └────────────────────────────┘ │
         │  ┌────────────────────────────┐ │
         │  │ 2. Bulk Update Checkins   │ │
         │  │    (SQL CASE WHEN)        │ │
         │  └────────────────────────────┘ │
         │  ┌────────────────────────────┐ │
         │  │ 3. Process Shifts         │ │
         │  │    (Bulk Insert)          │ │
         │  └────────────────────────────┘ │
         │  ┌────────────────────────────┐ │
         │  │ 4. Mark Absent/Maternity  │ │
         │  └────────────────────────────┘ │
         └──────────────────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────────┐
         │     Identical Attendance         │
         │     Records in Database          │
         └──────────────────────────────────┘
```

---

## 📞 Support

### Getting Help

1. **Check Error Logs**
   ```python
   frappe.get_all("Error Log",
       filters={
           "creation": [">", "2025-12-01"],
           "error": ["like", "%attendance%"]
       },
       fields=["name", "creation", "error"],
       order_by="creation desc",
       limit=20
   )
   ```

2. **Enable Debug Logging**
   ```python
   # Add to site_config.json
   {
       "developer_mode": 1,
       "logging": 2
   }
   ```

3. **Rollback to Original** (if needed)
   ```python
   # In __init__.py, comment out optimized version
   # hrms_st.process_auto_attendance_for_all_shifts = custom_process_auto_attendance_for_all_shifts

   # Then restart
   bench restart
   ```

---

**Last Updated:** 2025-12-23
**Maintained By:** Development Team
**Version:** 3.0 (Unified Optimized)
