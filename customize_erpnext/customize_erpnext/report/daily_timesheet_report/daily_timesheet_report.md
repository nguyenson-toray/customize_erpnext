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

### Scheduled Jobs

**Function**: `daily_timesheet_auto_sync_and_calculate()`

Chạy **2 lần mỗi ngày** để đảm bảo coverage 100%:

#### 1. Morning Pre-Creation (06:00 hàng ngày) ⭐ NEW
**Mục đích**: Tạo sẵn Daily Timesheet TRƯỚC khi nhân viên bắt đầu làm việc

**Lợi ích**:
-  Nhân viên có record sẵn khi check-in (không cần đợi tạo real-time)
-  Reports sáng sớm đã có dữ liệu đầy đủ
-  Tránh race condition khi nhiều nhân viên check-in cùng lúc
-  Đảm bảo tất cả nhân viên active đều có record (kể cả sẽ vắng)

#### 2. Evening Finalization (22:45 hàng ngày)
**Mục đích**: Tổng hợp và finalize dữ liệu cuối ngày

**Lợi ích**:
-  Update lại tất cả records với dữ liệu đầy đủ từ cả ngày
-  Tính toán overtime, maternity benefit chính xác
-  Chuẩn bị dữ liệu cho báo cáo ngày hôm sau

**Tạo/cập nhật Daily Timesheet cho:**
-  **TẤT CẢ nhân viên Active** (có hoặc không có check-in)
-  **Nhân viên vắng** (không check-in) → Quan trọng cho chấm công
-  **Nhân viên Left** còn làm việc (`relieving_date > current_date`)

**Logic xử lý:**
```python
# Include employees if:
# 1. Status = Active AND date_of_joining <= current_date
# 2. Status = Left AND date_of_joining <= current_date
#    AND relieving_date > current_date

# relieving_date là ngày ĐÃ NGHỈ (không làm việc)
# VD: relieving_date = 2025-11-15
#     → Ngày 14/11: VẪN làm việc → Tạo Daily Timesheet 
#     → Ngày 15/11: ĐÃ NGHỈ → Không tạo ❌
```

**Performance**: ~100 records/sec với bulk data loading

#### 3. Monthly Recalculation (23:30 Chủ nhật hàng tuần)
**Function**: `monthly_timesheet_recalculation()`

**Tính toán lại toàn bộ Daily Timesheet cho kỳ tháng:**
- Từ ngày 26 tháng trước → 25 tháng hiện (hoặc hôm nay nếu chưa đến 25)
- Chạy background job với timeout 40 phút
- Batch size: 50 records/batch
- **Cleanup**: Tự động xóa Daily Timesheet không cần thiết
- Gửi email báo cáo kết quả

**Cleanup Logic** (sau khi recalculate):
Xóa các Daily Timesheet thỏa mãn TẤT CẢ điều kiện:
- Employee status = 'Left'
- attendance_date >= relieving_date (đã nghỉ việc rồi)
- working_hours = 0 (không có giờ làm việc)

**Example**:
```
Employee: TIQN-1562 (Phạm Thị Viết Phượng)
Relieving Date: 2025-10-20 (đã nghỉ từ ngày 20/10)

Daily Timesheet cho ngày 26/10, 27/10, 28/10... (sau khi nghỉ)
→ working_hours = 0
→  XÓA (không cần thiết)
```

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
-  Daily scheduled job (22:45) - **TẤT CẢ employees**
-  Weekly monthly recalculation (23:30 Chủ nhật)
-  **NEW**: Auto cleanup Left employee timesheets
-  Performance optimized (100+ rec/sec)
-  **NEW**: Include absent employees (no check-in)
-  **NEW**: Include Left employees (still working)
-  **NEW**: Respect relieving_date logic

### Auto-Recalculation Triggers
1. **Employee Checkin**: Real-time update
2. **Shift Registration**: Submit/Cancel/Update
3. **Overtime Registration**: Submit/Cancel/Update
4. **Employee Maternity**: Update maternity tracking
5. **Daily Morning Pre-Creation** (06:00): Create for ALL active employees ⭐ NEW
6. **Daily Evening Finalization** (22:45): Update ALL active employees
7. **Weekly Monthly Recalculation** (23:30 Sunday): Full period recalc

### Employee Coverage (Updated 2025-11-10)
**Daily Auto Sync bây giờ tạo Daily Timesheet cho:**

| Employee Type | Condition | Coverage |
|--------------|-----------|----------|
| Active (có check-in) | `status = 'Active'` |  Tạo/cập nhật |
| Active (vắng) | `status = 'Active'` |  **TẠO MỚI** |
| Left (còn làm việc) | `relieving_date > current_date` |  **TẠO MỚI** |
| Left (đã nghỉ) | `relieving_date <= current_date` | ❌ Không tạo |
| Chưa join | `date_of_joining > current_date` | ❌ Không tạo |

**Example**: Ngày 2025-11-10
- Total Active Employees: 815
- Left (still working): 3 (relieving dates: 15/11, 21/11, 26/11)
- Coverage: **818/818 (100%)** 

## 📝 Key Functions Reference

### Scheduler Functions (scheduler.py)

#### `get_all_active_employees(date)`
Lấy TẤT CẢ nhân viên eligible cho Daily Timesheet.

**Returns**: List of employees with full details
```python
[{
    'employee': 'TIQN-0001',
    'employee_name': 'Nguyễn Văn A',
    'department': 'Production',
    'custom_section': 'Assembly',
    'custom_group': 'Group 1',
    'company': 'TIQN',
    'date_of_joining': '2024-01-01',
    'relieving_date': None,  # or date if Left
    'status': 'Active'  # or 'Left'
}]
```

**Logic**:
- Include: Active employees (joined)
- Include: Left employees still working (`relieving_date > date`)
- Exclude: Left employees already relieved (`relieving_date <= date`)
- Exclude: Employees not yet joined (`date_of_joining > date`)

#### `daily_timesheet_auto_sync_and_calculate()`
Main scheduled function - runs daily at 22:45.

**Process**:
1. Get all active employees (via `get_all_active_employees()`)
2. Bulk load all required data (check-ins, shifts, OT, maternity)
3. Create Daily Timesheet for new employees (including absent)
4. Update existing Daily Timesheet records
5. Log results

**Performance**: ~100 records/sec

#### `monthly_timesheet_recalculation()`
Weekly full recalculation - runs Sunday at 23:30.

**Process**:
1. Calculate period (26th prev month → 25th or today)
2. Enqueue background job (timeout: 40 min)
3. Call `bulk_create_recalculate_hybrid()` with batch_size=50
4. **Cleanup** Left employee timesheets (date >= relieving_date, working_hours = 0)
5. Send email notification with results

#### `cleanup_left_employee_timesheets(from_date, to_date)`
Cleanup unnecessary Daily Timesheet records for Left employees.

**Deletes records where**:
- Employee status = 'Left'
- attendance_date >= relieving_date (already left)
- working_hours = 0 (no actual work)

**Returns**: Number of deleted records

**Example**:
```python
deleted = cleanup_left_employee_timesheets('2025-10-26', '2025-11-10')
# Returns: 48 (deleted 48 unnecessary records)
```

## 📨 Daily Report Email System

### Tổng Quan
Hệ thống gửi email báo cáo chấm công tự động hàng ngày với:
- **Email HTML**: 3 bảng thống kê (Vắng, Maternity Leave, Chấm công thiếu)
- **File Excel**: 2 sheets (Dữ liệu chính + Chấm công thiếu)
- **Thời điểm**: Có thể gửi thủ công hoặc tự động theo lịch

### Cách Sử Dụng

#### 1. Gửi Thủ Công
Daily Timesheet Report → Actions → **📨2. Send Daily Timesheet Report**

**Dialog Fields**:
- **Report Date**: Ngày cần gửi báo cáo
- **Email Recipients**: Danh sách email (mỗi email một dòng)
  ```
  it@tiqn.com.vn
  ni.nht@tiqn.com.vn
  hoanh.ltk@tiqn.com.vn
  loan.ptk@tiqn.com.vn
  ```

**UX Features**:
- ✅ Validate email format
- ✅ Disable button khi đang gửi ("Sending...")
- ✅ Freeze toàn màn hình với loading message
- ✅ Tự động đóng dialog khi thành công
- ✅ Re-enable dialog nếu có lỗi để thử lại

### Email Content Structure

#### Statistics Summary
```
Số lượng nhân viên (Active): 826 người
Tổng số nhân viên hiện diện: 824 người
Tổng số nhân viên vắng (không bao gồm Maternity Leave): 0 người
Tổng số nhân viên Maternity Leave: 2 người
Tổng số giờ làm việc: 6,475.50 giờ
Tổng số giờ tăng ca: 145.25 giờ

Thời điểm xử lý dữ liệu chấm công: 08:10:30 03/12/2025
```

#### Bảng 1: Nhân Viên Vắng (Không Bao Gồm Maternity Leave)
- Danh sách nhân viên có `status = 'Absent'`
- Columns: STT, Employee, Employee Name, Department, Group

#### Bảng 2: Nhân Viên Maternity Leave
- Danh sách nhân viên có `status = 'Maternity Leave'`
- Columns: STT, Employee, Employee Name, Department, Group

#### Bảng 3: Chấm Công Thiếu (Từ 26 Tháng Trước Đến Hôm Qua)
- **3 trường hợp incomplete**:
  1. Chỉ có 1 lần chấm công
  2. Tất cả lần chấm trước giờ vào ca
  3. Tất cả lần chấm sau giờ tan ca
- **Columns**: STT, Ngày, Employee, Employee Name, Department, Group, Số lần chấm, Đã xử lý

### Excel File Structure

#### Sheet 1: "Absent-Maternity Leave-Present"
Tất cả dữ liệu Daily Timesheet của ngày báo cáo.

**Columns**:
- STT, Ngày, Att ID, Employee, Employee Name
- Department, Group, Shift, Designation
- Check In, Check Out, Working Hours, Overtime, Status

**Sắp xếp**: Absent → Maternity Leave → Present

**Source Data**:
```python
all_employees = []
all_employees.extend(stats.get('absent_employees', []))
all_employees.extend(stats.get('maternity_employees', []))
all_employees.extend(stats.get('present_employees', []))
```

#### Sheet 2: "Missing DD-MM to DD-MM"
Dữ liệu chấm công thiếu từ ngày 26 tháng trước đến **hôm qua** (không phải hôm nay).

**Columns**:
- STT, Ngày, Att ID, Employee, Employee Name
- Department, Group, Shift, Designation
- Check-in, Check-out, Số lần chấm, Đã xử lý
- Reason, Other Reason

**Period Logic**:
```python
prev_month_26 = add_days(add_months(current_month_first, -1), 25)
yesterday = add_days(report_date, -1)  # Not today!
```

### API Reference

#### `send_daily_time_sheet_report(report_date=None, recipients=None)`
Gửi báo cáo Daily Timesheet qua email.

**Location**: `scheduler.py`

**Decorator**:
```python
@frappe.whitelist()
@only_for_sites("erp.tiqn.local")
```

**Parameters**:
- `report_date` (str/date, optional): Ngày báo cáo. Default = today
- `recipients` (str/list, optional): Email người nhận
  - Format: Newline-separated hoặc comma-separated
  - Example: `"email1@tiqn.com.vn\nemail2@tiqn.com.vn"`

**Returns**:
```python
{
    "status": "success",
    "message": "Report sent successfully to N recipients"
}
```

**Process Flow**:
1. Parse `report_date` (string hoặc date object)
2. Get data từ `get_data()` với filters:
   - `date_type`: "Single Date"
   - `single_date`: report_date
   - `summary`: 0
   - `detail_columns`: 1
3. Calculate statistics: `calculate_timesheet_statistics()`
4. Get incomplete check-ins (từ 26 tháng trước đến hôm qua)
5. Generate HTML email (3 tables)
6. Generate Excel file (2 sheets)
7. Send email với attachment
8. Cleanup temp Excel file

**Example Usage**:
```javascript
frappe.call({
    method: 'customize_erpnext.customize_erpnext.report.daily_timesheet_report.scheduler.send_daily_time_sheet_report',
    args: {
        report_date: '2025-12-03',
        recipients: 'it@tiqn.com.vn\nni.nht@tiqn.com.vn'
    },
    freeze: true,
    freeze_message: __('Sending Daily Timesheet Report...')
})
```

### Helper Functions

#### `calculate_timesheet_statistics(report_date, data)`
Tính toán thống kê từ dữ liệu Daily Timesheet.

**Returns**:
```python
{
    "total_employees": 826,           # Total Active employees
    "total_present": 824,             # Present + Sunday
    "total_absent": 0,                # Absent (excluding maternity)
    "maternity_count": 2,             # Maternity Leave count
    "total_working_hours": 6475.50,
    "total_overtime_hours": 145.25,
    "total_actual_overtime": 150.00,
    "total_approved_overtime": 145.25,
    "present_employees": [...],       # List of employee dicts
    "absent_employees": [...],
    "maternity_employees": [...]
}
```

**Status Classification**:
```python
if status == 'Present' or status == 'Sunday':
    present_employees.append(row)
elif status == 'Maternity Leave':
    maternity_employees.append(row)
elif status == 'Absent':
    absent_employees.append(row)
# Other statuses: Half Day, On Leave, etc. → NOT included!
```

**Deduplication**: Sử dụng `employee_data` dict để chỉ xử lý mỗi employee 1 lần (tránh duplicate).

**Maternity Leave Count**:
- Đếm số lượng nhân viên có `status = 'Maternity Leave'` trong Daily Timesheet
- `maternity_count = len(maternity_employees)`

#### `get_incomplete_checkins(start_date, end_date)`
Lấy danh sách nhân viên chấm công không đầy đủ.

**Query Source**: `tabEmployee Checkin` (docstatus <= 1)

**Incomplete Logic** (3 rules):
1. **Single check-in**: `checkin_count = 1`
2. **All before shift**: Tất cả lần chấm < shift `begin_time`
3. **All after shift**: Tất cả lần chấm > shift `end_time`

**Returns**: List of dicts
```python
[{
    'employee': 'TIQN-0001',
    'employee_name': 'Nguyễn Văn A',
    'department': 'Production',
    'custom_group': 'Group 1',
    'attendance_date': '2025-11-26',
    'checkin_count': 1,
    'first_check_in': datetime,
    'last_check_out': datetime,
    'begin_time': time,
    'end_time': time,
    'manual_checkins': 'Processed' hoặc ''
}]
```

#### `generate_email_content(report_date, stats, data, last_checkin_time=None)`
Tạo HTML content cho email.

**Structure**:
```html
<div style="font-family: Arial, sans-serif;">
    <h2>Báo cáo hiện diện / vắng ngày DD/MM/YYYY</h2>

    <!-- Statistics -->
    <div style="background-color: #f5f5f5; padding: 15px;">
        <p><strong>Số lượng nhân viên (Active):</strong> N người</p>
        ...
    </div>

    <!-- Table 1: Absent (excluding maternity) -->
    <h3>1. Nhân viên vắng (Không bao gồm Maternity Leave)</h3>
    <table border="1">...</table>

    <!-- Table 2: Maternity Leave -->
    <h3>2. Nhân viên Maternity Leave</h3>
    <table border="1">...</table>

    <!-- Table 3: Incomplete Check-ins -->
    <h3>3. Chấm công thiếu (từ DD/MM đến DD/MM)</h3>
    <table border="1">...</table>
</div>
```

**Encoding**: UTF-8 (hỗ trợ tiếng Việt có dấu)

#### `generate_excel_report(report_date, data, stats)`
Tạo file Excel với openpyxl.

**Returns**: `(file_path, file_name)`
- `file_path`: Temp file path
- `file_name`: `Daily_Timesheet_Report_DDMMYYYY.xlsx`

**Styling**:
- Header: Green background (#4CAF50), white bold text
- Borders: Thin black borders
- Alignment: Center for dates/numbers, left for text
- Column widths: Optimized
- Table style: TableStyleMedium1

**Temp File Handling**:
```python
temp_dir = tempfile.gettempdir()
file_path = os.path.join(temp_dir, file_name)
wb.save(file_path)
# ... send email ...
os.remove(file_path)  # Cleanup
```

#### `get_last_employee_checkin_time()`
Lấy thời gian Employee Checkin cuối cùng.

**Query**:
```sql
SELECT MAX(time) as last_time
FROM `tabEmployee Checkin`
```

**Returns**: `"HH:MM:SS DD/MM/YYYY"` hoặc `None`

### Email Recipient Parsing

**Client-side (JavaScript)**:
```javascript
// Split by newlines or commas, trim, filter empty
let emails = values.recipients
    .split(/[\n,]/)
    .map(e => e.trim())
    .filter(e => e.length > 0);

// Validate each email
let invalid_emails = emails.filter(e =>
    !frappe.utils.validate_type(e, 'email')
);
```

**Server-side (Python)**:
```python
import re

if isinstance(recipients, str):
    # Split by newlines and commas, remove empty strings
    recipient_list = [
        email.strip()
        for email in re.split(r'[\n,]', recipients)
        if email.strip()
    ]
else:
    recipient_list = recipients
```

**Supports**:
- ✅ Newline-separated (recommended)
- ✅ Comma-separated (backward compatible)
- ✅ Mixed format

### Known Issues & Limitations

#### 1. Status Support
**Vấn đề**: Chỉ 4 status được hỗ trợ trong email report:
- ✅ `Present`
- ✅ `Sunday`
- ✅ `Maternity Leave`
- ✅ `Absent`

**Not Supported**:
- ❌ `Half Day` → Không xuất hiện trong email/Excel
- ❌ `On Leave` → Không xuất hiện
- ❌ `Work From Home` → Không xuất hiện
- ❌ NULL/empty status → Không xuất hiện

**Impact**: Số lượng employees trong email có thể < Total Active.

#### 2. Department Filtering
**Vấn đề**: Report luôn loại bỏ 2 departments:
```python
# Line 646 in daily_timesheet_report.py
conditions.append(
    "emp.department NOT IN ('Head of Branch - TIQN', 'Operations Manager - TIQN')"
)
```

**Impact**: Employees trong 2 departments này sẽ KHÔNG xuất hiện trong báo cáo.

#### 3. Data Discrepancy
**Example**:
- Total Active Employees: 826
- Sheet 1 rows: 824
- Missing: 2 employees

**Possible Reasons**:
1. Department bị excluded
2. Status không được support
3. Không có Daily Timesheet record (filtered out by `dt.attendance_date IS NOT NULL`)

### Configuration

**Site Restriction**:
```python
@only_for_sites("erp.tiqn.local")
```

**Default Recipients**:
```python
recipient_list = [
    "it@tiqn.com.vn",
    "ni.nht@tiqn.com.vn",
    "hoanh.ltk@tiqn.com.vn",
    "loan.ptk@tiqn.com.vn"
]
```

**Incomplete Check-ins Period**:
- Start: Day 26 of previous month
- End: Yesterday (NOT today)

## 🔄 Update History

### 2025-12-03: Email Report System
**Added**:
- ✅ Send Daily Timesheet Report button in Actions menu
- ✅ Dialog với date picker + email recipients (one per line)
- ✅ Email HTML với 3 bảng thống kê
- ✅ Excel attachment với 2 sheets
- ✅ Loading/frozen dialog during send
- ✅ Auto-close dialog on success
- ✅ Support newline + comma separated emails

**Functions Added** (`scheduler.py`):
- `send_daily_time_sheet_report()` - Main email function
- `calculate_timesheet_statistics()` - Calculate stats from data
- `get_incomplete_checkins()` - Query incomplete check-ins
- `generate_email_content()` - Generate HTML with 3 tables
- `generate_excel_report()` - Generate Excel with 2 sheets
- `get_last_employee_checkin_time()` - Get last check-in time

**Dialog Features** (`daily_timesheet_report.js`):
- Validate email format (newline/comma separated)
- Disable button: `d.get_primary_btn().prop('disabled', true)`
- Change label: `d.get_primary_btn().html('Sending...')`
- Freeze screen: `freeze: true, freeze_message: '...'`
- Auto-close: `d.hide()` on success
- Re-enable on error

**Email Content**:
- Subject: "Báo cáo hiện diện / vắng ngày DD/MM/YYYY"
- 3 HTML tables: Absent, Maternity Leave, Incomplete Check-ins
- Statistics summary
- UTF-8 encoding

**Excel Format**:
- Sheet 1: All timesheet data (Absent → Maternity → Present)
- Sheet 2: Incomplete check-ins (26 prev month to yesterday)
- Green header (#4CAF50), borders, table format

### 2025-11-10: Full Employee Coverage + Cleanup + Morning Pre-Creation
**Changes**:
-  Daily sync now creates Daily Timesheet for ALL active employees
-  Include absent employees (no check-in) - critical for attendance tracking
-  Include Left employees still working (`relieving_date > current_date`)
-  Proper handling of `date_of_joining` and `relieving_date`
-  **NEW**: Morning pre-creation job (06:00) - create records before work starts
-  **NEW**: Automatic cleanup of unnecessary Daily Timesheet for Left employees
-  Performance: 100+ records/sec (88 new + 730 updated in 7.93s)

**Scheduled Jobs**:
- **06:00 Morning**: Pre-create Daily Timesheet for all active employees
- **22:45 Evening**: Finalize and update Daily Timesheet with full day data
- **23:30 Sunday**: Monthly full recalculation + cleanup

**Functions Added**:
- `get_all_active_employees()` - Get all eligible employees (not just with check-ins)
- `create_daily_timesheet_record_optimized_v2()` - More efficient, uses pre-loaded employee data
- `cleanup_left_employee_timesheets()` - **NEW**: Delete unnecessary records for Left employees

**Functions Updated**:
- `daily_timesheet_auto_sync_and_calculate()` - Use new `get_all_active_employees()`
- `monthly_timesheet_recalculation_worker()` - Added cleanup step after recalculation

**Functions Removed** (cleaned up):
- `get_employees_needing_sync()` - Replaced by `get_all_active_employees()`
- `create_daily_timesheet_record_optimized()` - Replaced by v2

**Test Results** (2025-11-10):
```
Daily Sync:
  Total Employees: 818 (815 Active + 3 Left still working)
  Coverage: 818/818 (100%)
  Created: 88 records (absent + Left employees)
  Updated: 730 records
  Errors: 0
  Processing Time: 7.93s
  Speed: 103.15 records/sec

Cleanup Test:
  Period: 2025-10-26 to 2025-11-10
  Found: 48 unnecessary records
  Deleted: 48 records
  Result:  SUCCESS
```

### 2025-10-08: Performance Optimization
- Skip HTML generation in bulk operations
- Pre-load employee joining dates
- Database indexes
- Performance: 3.5 → 20-30 rec/sec (6-8x faster)
