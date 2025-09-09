# Daily Timesheet - Hệ Thống Chấm Công Tự Động

## 🎯 Tổng Quan

**Daily Timesheet** tự động tính chấm công từ:
- Employee Checkin/Checkout (máy chấm công)
- Shift Registration (đăng ký ca)
- Overtime Registration (đăng ký tăng ca)
- Maternity Tracking (nhân viên nữ)

### Quy Tắc Cơ Bản

| Shift | Giờ Làm | Nghỉ Trưa | OT | Maternity |
|-------|---------|-----------|----|---------__|
| **Day** | 8:00-17:00 | 12:00-13:00 | ✅ | ✅ Về 16:00 |
| **Canteen** | 7:00-16:00 | 11:00-12:00 | ✅ | ✅ Về 15:00 |
| **Shift 1** | 6:00-14:00 | No break | ❌ | ✅ Về 13:00 |
| **Shift 2** | 14:00-22:00 | No break | ❌ | ✅ Về 21:00 |

## ⚙️ Thuật Toán Tính Toán

```
1. Xác định Shift Type (Registration > Group > Default)
2. Check Maternity Benefit (từ Maternity Tracking)
3. Tính Working Hours = Morning + Afternoon (không bao gồm OT)
4. Tính Actual OT = Pre-shift + Post-shift
5. Lấy Approved OT từ registrations
6. Final OT = min(Actual, Approved)
7. Overtime Coefficient (1.5/2.0/3.0)
8. Final OT - With Coefficient = Final OT × Coefficient
```

### Overtime Coefficient
- **Ngày thường (T2-T7)**: 1.5
- **Chủ nhật**: 2.0
- **Ngày lễ**: 3.0

### Sunday Logic Đặc Biệt
Chủ nhật có logic riêng:
```python
if is_sunday:
    # Chuyển Working Hours → Actual OT
    actual_ot = working_hours
    working_hours = 0
    status = "Sunday"
    overtime_coefficient = 2.0
```

### Maternity Benefit
Được hưởng về sớm 1h mà vẫn tính đủ giờ:
- **Pregnant**: Cần `apply_pregnant_benefit = 1` trong Maternity Tracking
- **Maternity Leave**: Tự động được hưởng
- **Young Child**: Tự động được hưởng

## 📊 Kết Quả Tính Toán

### Ví Dụ Ca Day (8:00-17:00)

| Trường Hợp | Check In/Out | Working Hours | Final OT | Coefficient | Final OT - With Coeff |
|-------------|--------------|---------------|----------|-------------|---------------------|
| Bình thường | 8:00→17:00 | 8h | 0h | 1.5 | 0h |
| Có OT | 8:00→19:00 | 8h | 2h | 1.5 | **3h** |
| Sunday | 8:00→17:00 | 0h | 8h | 2.0 | **16h** |
| Sunday + OT | 7:00→18:00 | 0h | 2h | 2.0 | **4h** |
| Maternity | 8:00→16:00 | **8h** ✨ | 0h | 1.5 | 0h |

*✨ = Maternity benefit: về sớm 1h mà vẫn tính đủ giờ*

## 🔄 Auto Sync System

### Real-time Hooks
```python
# Employee Checkin hooks
"after_insert": auto_sync_on_checkin_update
"on_update": auto_sync_on_checkin_update  
"on_trash": auto_cleanup_on_checkin_delete
```

### Scheduled Job
- **21:00 hàng ngày**: Tự động sync và calculate tất cả Daily Timesheet
- Tạo records cho employees có checkin nhưng chưa có timesheet
- Update tất cả existing records

### Cleanup Logic
Khi xóa Employee Checkin:
- **Nếu không còn checkin nào khác trong ngày** → Xóa Daily Timesheet
- **Nếu còn checkin khác** → Chỉ update lại Daily Timesheet

## 📈 Daily Timesheet Report

### 🎯 Hiển Thị TẤT CẢ Employees
**Report sẽ hiển thị TẤT CẢ employees đang active trong period được chọn:**
- ✅ **Employees có checkin**: Hiển thị với dữ liệu thật
- ✅ **Employees KHÔNG có checkin**: Hiển thị với giá trị 0
- ✅ **Period validation**: Chỉ employees active trong period (dựa vào joining/relieving date)

### Cột Hiển Thị
**Luôn hiện**: Employee, Employee Name, Group, Check In/Out (HH:MM:SS), Working Hours, Actual OT, Registered OT, Final OT, Status

**Detail Columns** (chỉ khi checked):
- Department, Section
- **Overtime Coefficient, Final OT - With Coefficient**
- Late Entry, Early Exit, Maternity Benefit
- Date of Joining, Relieving Date

### Filter Options
- **Date**: Single Date / Date Range / Monthly
- Department, Section, Group, Employee, Status
- **Summary Mode**: Group by employee
- **Detail Columns**: Show/hide extra columns

## 🗃️ Database Fields

```json
{
  "employee": "Link to Employee",
  "attendance_date": "Date",
  "check_in": "Datetime",
  "check_out": "Datetime",
  "working_hours": "Float (không bao gồm overtime)",
  "actual_overtime": "Float",
  "approved_overtime": "Float", 
  "overtime_hours": "Float (= min(actual, approved))",
  "overtime_coefficient": "Float (1.5/2.0/3.0)",
  "final_ot_with_coefficient": "Float (Final OT × Coefficient)",
  "late_entry": "Check",
  "early_exit": "Check",
  "maternity_benefit": "Check",
  "status": "Select"
}
```

## 🚀 Implementation Status: ✅ HOÀN THÀNH

### ✅ Core Features
- Real-time sync từ Employee Checkin
- Auto calculation với maternity benefit
- Sunday logic đặc biệt
- Overtime coefficient system
- Intelligent cleanup khi xóa checkin

### ✅ Report Features  
- Multiple chart types
- Advanced filtering
- Detail Columns control
- HH:MM:SS time format
- Overtime coefficient columns

### ✅ Auto Sync
- Real-time hooks (create/update/delete)
- Daily scheduled job (21:00)
- Error handling & logging
- No duplicates, safe re-run

---

## 📝 Quick Commands

```bash
# Sau khi sửa hooks, chạy:
bench --site erp-sonnt.tiqn.local clear-cache
bench build
bench --site erp-sonnt.tiqn.local migrate  
bench restart

# Manual bulk sync:
bench --site erp-sonnt.tiqn.local execute "customize_erpnext.customize_erpnext.doctype.daily_timesheet.scheduler.manual_bulk_sync" --kwargs "{'from_date': '2025-01-01', 'to_date': '2025-01-31'}"
```

## ⚙️ Constants & Thresholds (Latest Update)

### Minimum Thresholds
```python
MIN_MINUTES_OT = 15                    # Ngưỡng tối thiểu tổng OT
MIN_MINUTES_WORKING_HOURS = 10         # Ngưỡng tối thiểu working hours
MIN_MINUTES_PRE_SHIFT_OT = 60          # Ngưỡng tối thiểu OT trước ca
MIN_MINUTES_CHECKIN_FILTER = 10        # Filter các lần chấm công < 10 phút
```

### Logic Improvements
- **Multiple Checkin Logic**: Sớm nhất = Check In, Muộn nhất = Check Out
- **OT Thresholds**: Sử dụng constants thay vì hardcode
- **Special Case**: Check in trước ca + Check out trước nghỉ trưa → Working hours = Check out - Bắt đầu ca
- **Algorithm Dialog**: Hiển thị constants real-time từ server
- **Employee Checkins HTML**: Thêm cột `custom_reason_for_manual_check_in`

## 📊 Enhanced UI Features

### Timesheet Algorithm Dialog
- **Button**: "Timesheet Algorithm" trong form
- **Dynamic Constants**: Lấy từ server real-time
- **Section Constants**: Hiển thị tất cả ngưỡng hiện tại
- **Comprehensive Guide**: Ca làm việc, working hours, overtime, coefficients

### Employee Check-ins Display
- **4 Columns**: Time, Check-in Record, Device, Manual Reason
- **Manual Reason Styling**: Màu đỏ nếu có, xám nếu không
- **Responsive Table**: Tự động điều chỉnh width

## 🎉 System Status: **FULLY OPERATIONAL + ENHANCED**

- ✅ Real-time sync working
- ✅ Daily job running at 21:00  
- ✅ Reports với overtime coefficient
- ✅ Maternity benefit logic correct
- ✅ Sunday logic implemented
- ✅ Cleanup hooks active
- ✅ **Constants-based thresholds**
- ✅ **Enhanced multiple checkin logic**
- ✅ **Dynamic algorithm dialog**
- ✅ **Manual checkin reason display**