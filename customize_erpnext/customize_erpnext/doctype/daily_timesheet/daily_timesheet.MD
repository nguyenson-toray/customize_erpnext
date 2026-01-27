# Daily Timesheet - Hệ Thống Chấm Công Tự Động

## 🎯 Tổng Quan

**Daily Timesheet** tự động tính chấm công từ:
- Employee Checkin/Checkout (máy chấm công)
- Shift Registration (đăng ký ca)
- Overtime Registration (đăng ký tăng ca)
- Maternity Tracking (nhân viên nữ)

### Quy Tắc Ca Làm Việc

| Shift | Giờ Làm | Nghỉ Trưa | OT | Maternity |
|-------|---------|-----------|----|------------|
| **Day** | 8:00-17:00 | 12:00-13:00 |  |  Về 16:00 |
| **Canteen** | 7:00-16:00 | 11:00-12:00 |  |  Về 15:00 |
| **Shift 1** | 6:00-14:00 | No break | ❌ |  Về 13:00 |
| **Shift 2** | 14:00-22:00 | No break | ❌ |  Về 21:00 |

## ⚙️ Thuật Toán Tính Toán

```
1. Xác định Shift Type (Registration > Group > Default)
2. Check Maternity Benefit
3. Tính Working Hours = Morning + Afternoon
4. Tính Actual OT = Pre-shift + Lunch-break + Post-shift
5. Lấy Approved OT từ registrations
6. Final OT = min(Actual, Approved)
7. Overtime Coefficient (1.5/2.0/3.0)
8. Final OT With Coefficient = Final OT × Coefficient
```

### Overtime Coefficient
- **Ngày thường (T2-T7)**: 1.5
- **Chủ nhật**: 2.0
- **Ngày lễ**: 3.0

### Maternity Benefit
- **Pregnant**: Cần `apply_pregnant_benefit = 1` trong Maternity Tracking
- **Maternity Leave**: Tự động được hưởng
- **Young Child**: Tự động được hưởng

### Constants & Thresholds
```python
MIN_MINUTES_OT = 15                    # Ngưỡng tối thiểu tổng OT
MIN_MINUTES_WORKING_HOURS = 10         # Ngưỡng tối thiểu working hours
MIN_MINUTES_PRE_SHIFT_OT = 60          # Ngưỡng tối thiểu OT trước ca
MIN_MINUTES_CHECKIN_FILTER = 10        # Filter các lần chấm công < 10 phút
```

## 🔄 Auto Sync System

### Real-time Hooks
```python
# Employee Checkin
"after_insert": auto_sync_on_checkin_update
"on_update": auto_sync_on_checkin_update
"on_trash": auto_cleanup_on_checkin_delete

# Shift Registration
"on_submit": auto_recalc_on_shift_registration_change
"on_cancel": auto_recalc_on_shift_registration_change
"on_update_after_submit": auto_recalc_on_shift_registration_change

# Overtime Registration
"on_submit": auto_recalc_on_overtime_registration_change
"on_cancel": auto_recalc_on_overtime_registration_change
"on_update_after_submit": auto_recalc_on_overtime_registration_change

# Employee Maternity Tracking
"validate": check_maternity_tracking_changes
"on_update": auto_recalc_on_maternity_tracking_change
```

### Scheduled Job
- **22:45 hàng ngày**: Tự động sync và calculate tất cả Daily Timesheet

## 🔧 Bulk Operations API

### 1. Bulk Create + Recalculate (Recommended)
```python
frappe.call({
    method: "customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.bulk_create_recalculate_timesheet",
    args: {
        from_date: "2025-01-01",
        to_date: "2025-01-31",
        employee: null,     // optional
        batch_size: 100     // default 100, max 200
    }
})
```

### 2. Bulk Recalculate Only
```python
frappe.call({
    method: "customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.bulk_recalculate_smart",
    args: {
        employee: null,
        date_range: JSON.stringify({
            from_date: "2025-01-01",
            to_date: "2025-01-31"
        }),
        batch_size: 100
    }
})
```

### 3. Single Record Recalculate
```python
frappe.call({
    method: "customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.recalculate_timesheet",
    args: { docname: "DT-00001" }
})
```

## ⚡ Performance Optimization

### Latest Optimization (2025-10-08)

**Cải thiện: 3.5 rec/sec → 20-30 rec/sec (6-8x faster)**

#### 1. Skip HTML Generation trong Bulk Operations
```python
def calculate_all_fields_optimized(doc, bulk_data, skip_html_generation=False):
    if not skip_html_generation:
        doc.generate_additional_info_html()
```
- Loại bỏ 1,496 queries không cần thiết
- HTML được generate khi user mở form

#### 2. Pre-load Employee Joining Dates
```python
emp_joining_map = {ed.name: ed.date_of_joining for ed in emp_data}
date_of_joining = bulk_data["employee_joining_dates"].get(doc.employee)
```
- Thay 748 individual queries bằng 1 bulk query

#### 3. Database Indexes
```sql
CREATE INDEX idx_emp_checkin_emp_time ON `tabEmployee Checkin` (employee, time);
CREATE INDEX idx_maternity_tracking_lookup ON `tabMaternity Tracking` (parent, type, from_date, to_date);
CREATE INDEX idx_shift_reg_detail_lookup ON `tabShift Registration Detail` (employee, begin_date, end_date);
CREATE INDEX idx_overtime_reg_detail_lookup ON `tabOvertime Registration Detail` (employee, date);
```

### Performance Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Processing Time | 216.65s | 25-35s | **6-8x faster** |
| Throughput | 3.5 rec/sec | **20-30 rec/sec** | **6-8x** |
| DB Queries | 2,990 | **746** | **-75%** |

### Configuration
- Default batch_size: **100**
- Maximum batch_size: **200**
- Background job threshold: **500 operations**

## 🗄️ Database Indexes

### Installation
```bash
bench mariadb < apps/customize_erpnext/customize_erpnext/customize_erpnext/doctype/daily_timesheet/add_performance_indexes.sql
```

### Check Indexes
```sql
SHOW INDEX FROM `tabEmployee Checkin` WHERE Key_name LIKE 'idx_emp%';
SHOW INDEX FROM `tabMaternity Tracking` WHERE Key_name LIKE 'idx_mat%';
SHOW INDEX FROM `tabShift Registration Detail` WHERE Key_name LIKE 'idx_shift%';
SHOW INDEX FROM `tabOvertime Registration Detail` WHERE Key_name LIKE 'idx_over%';
```

## 📝 Quick Commands

```bash
# Clear cache sau khi sửa code
bench --site erp-sonnt.tiqn.local clear-cache
bench build
bench --site erp-sonnt.tiqn.local migrate
bench restart

# Apply database indexes (one-time)
bench mariadb < apps/customize_erpnext/customize_erpnext/customize_erpnext/doctype/daily_timesheet/add_performance_indexes.sql
```

## 📊 Database Fields

```json
{
  "employee": "Link to Employee",
  "attendance_date": "Date",
  "check_in": "Datetime",
  "check_out": "Datetime",
  "working_hours": "Float",
  "actual_overtime": "Float",
  "approved_overtime": "Float",
  "overtime_hours": "Float (= min(actual, approved))",
  "overtime_coefficient": "Float (1.5/2.0/3.0)",
  "final_ot_with_coefficient": "Float",
  "late_entry": "Check",
  "early_exit": "Check",
  "maternity_benefit": "Check",
  "status": "Select (Absent/Present/Present + OT/Sunday)"
}
```

## 🎉 System Status

### Core Functions
-  Real-time sync từ Employee Checkin
-  Auto calculation với maternity benefit
-  Sunday logic đặc biệt
-  Overtime coefficient system
-  Lunch break overtime
-  Smart auto-recalculation (Shift/OT/Maternity changes)
-  Daily scheduled job (22:45)
-  Performance optimized (20-30 rec/sec)

### Auto-Recalculation Triggers
1. **Employee Checkin**: Real-time update
2. **Shift Registration**: Submit/Cancel/Update
3. **Overtime Registration**: Submit/Cancel/Update
4. **Employee Maternity**: Update maternity tracking
5. **Scheduled Job**: Daily sync lúc 22:45
