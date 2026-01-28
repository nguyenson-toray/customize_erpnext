# Thuật Toán Chấm Công  

## 🎯 Tổng Quan

### Mục Tiêu
Tính toán **đầy đủ và chính xác** các thông tin chấm công:
- ✅ Giờ làm buổi sáng
- ✅ Giờ làm buổi chiều  
- ✅ Giờ tăng ca thực tế (pre + post shift)
- ✅ Giờ tăng ca được duyệt
- ✅ Tổng giờ = sáng + chiều + min(approved, actual) OT

### Nguyên Tắc Đơn Giản
1. **Chỉ 2 ca được phép OT**: Day và Canteen
2. **Shift 1, 2 không bao giờ OT**: Dù làm việc đến mấy giờ
3. **Maternity benefit**: Pregnant/Young child được về sớm 1h

## 📋 Quy Tắc Cơ Bản

| Shift Type | Giờ Làm | Nghỉ Trưa | OT | Maternity Benefit |
|------------|---------|-----------|----|--------------------|
| **Day** | 8:00-17:00 | 12:00-13:00 | ✅ | ✅ Về 16:00 = 8h |
| **Canteen** | 7:00-16:00 | 11:00-12:00 | ✅ | ✅ Về 15:00 = 8h |
| **Shift 1** | 6:00-14:00 | 10:00=10:00 | ❌ | ✅ Về 13:00 = 8h |
| **Shift 2** | 14:00-22:00 | 18:00=18:00 | ❌ | ✅ Về 21:00 = 8h |

## 🔄 Sơ Đồ Thuật Toán

```
1. INPUT: Employee, Date, Check In, Check Out
           ↓
2. Xác định Shift Type (Registration > Group > Default)
           ↓
3. Check Maternity Benefit (Pregnant/Young Child trong date range)
           ↓
4. Tính Morning Hours (từ shift_start đến break_start)
           ↓
5. Tính Afternoon Hours (từ break_end đến shift_end, có áp dụng maternity)
           ↓
6. Tính Actual OT (pre-shift + post-shift, theo original shift time)
           ↓
7. Lấy Approved OT (từ OT Registration, Shift 1/2 = 0)
           ↓
8. Final OT = min(Actual, Approved)
           ↓
9. Total = Morning + Afternoon + Final OT
```

## ⚙️ Logic Chi Tiết

### 1. Xác Định Shift Type
```python
if có shift_registration_detail:
    return registered_shift_type
elif employee.custom_group == "Canteen":
    return "Canteen" 
else:
    return "Day"  # Mặc định
```

### 2. Check Maternity Benefit
```python
def has_maternity_benefit(employee, date):
    records = get_maternity_tracking(employee, date)
    return any(r.type in ["Pregnant", "Young child"] for r in records)
```

### 3. Tính Morning Hours
```python
morning_start = max(check_in, shift_start)  # Không tính đi sớm
morning_end = min(check_out, break_start)
morning_hours = max(0, morning_end - morning_start)
```

### 4. Tính Afternoon Hours (Có Maternity)
```python
afternoon_start = max(check_in, break_end)

if has_maternity_benefit:
    # Được về sớm 1h mà vẫn tính đủ giờ
    if check_out >= (shift_end - 1h):
        afternoon_end = shift_end  # Tính đủ giờ
    else:
        afternoon_end = min(check_out, shift_end)  # Tính thực tế
else:
    afternoon_end = min(check_out, shift_end)

afternoon_hours = max(0, afternoon_end - afternoon_start)
```

### 5. Tính Actual OT
```python
pre_shift_ot = max(0, shift_start - check_in)    # Đi sớm
post_shift_ot = max(0, check_out - shift_end)    # Về trễ
actual_ot = pre_shift_ot + post_shift_ot
```

### 6. Tính Approved OT
```python
if shift_type in ["Shift 1", "Shift 2"]:
    approved_ot = 0  # Không bao giờ được phép OT
else:
    approved_ot = sum(ot_registrations)  # Từ bảng đăng ký
```

### 7. Kết Quả Final
```python
final_ot = min(actual_ot, approved_ot)
total_hours = morning_hours + afternoon_hours + final_ot
```

## 📊 Ma Trận Kết Quả

### Ca Day (8:00-17:00) - Các Trường Hợp Chính

| Scenario | Check In/Out | Maternity | Morning | Afternoon | Actual OT | Approved OT | Final OT | Total |
|----------|--------------|-----------|---------|-----------|-----------|-------------|----------|-------|
| **Bình thường** | 8:00→17:00 | ❌ | 4h | 4h | 0h | 0h | 0h | **8h** |
| **Pregnant benefit** | 8:00→16:00 | ✅ | 4h | **4h** ✨ | 0h | 0h | 0h | **8h** |
| **Có OT** | 7:00→19:00 | ❌ | 4h | 4h | 3h | 2h* | 2h | **10h** |
| **Pregnant + OT** | 7:00→18:00 | ✅ | 4h | **4h** ✨ | 2h | 2h* | 2h | **10h** |
| **Đi muộn** | 8:30→17:00 | ❌ | 3.5h | 4h | 0h | 0h | 0h | **7.5h** |
| **Về sớm** | 8:00→15:00 | ❌ | 4h | 2h | 0h | 0h | 0h | **6h** |

*✨ = Áp dụng Maternity Benefit*  
*\* = Có đăng ký OT*

### So Sánh Shift 1/2 vs Day/Canteen

| Shift Type | Employee | Check In/Out | Actual OT | Approved OT | Final OT | Total |
|------------|----------|--------------|-----------|-------------|----------|-------|
| **Day** | Bình thường | 8:00→19:00 | 2h | 2h* | 2h | **10h** |
| **Shift 1** | Bình thường | 6:00→16:00 | 2h | **0h** | **0h** | **8h** |
| **Canteen** | Bình thường | 7:00→18:00 | 2h | 2h* | 2h | **10h** |
| **Shift 2** | Bình thường | 14:00→24:00 | 2h | **0h** | **0h** | **8h** |

## 🤱 Maternity Benefit - Chi Tiết

### Điều Kiện Áp Dụng
```sql
SELECT * FROM `tabMaternity Tracking` 
WHERE parent = employee
  AND type IN ('Pregnant', 'Young child')
  AND from_date <= attendance_date 
  AND to_date >= attendance_date
```

### Cách Hoạt Động
```
Ca Day: 8:00-17:00 → Pregnant employee được về 16:00

Normal Employee: 8:00→16:00 = 7h (thiếu 1h)
Pregnant Employee: 8:00→16:00 = 8h (đủ giờ) ✨

Nhưng:
Pregnant Employee: 8:00→15:00 = 6h (vẫn thiếu vì về quá sớm)
```

### Không Ảnh Hưởng OT
```
Pregnant Employee: 8:00→18:00 với OT 17:00-18:00

→ Morning: 4h
→ Afternoon: 4h (benefit applied)  
→ Actual OT: 1h (18:00 - 17:00, theo original shift)
→ Approved OT: 1h
→ Final OT: 1h
→ Total: 9h
```

## ⚙️ Constants & Configuration (Latest Update)

### Minimum Thresholds
```python
# Constants for minimum thresholds
MIN_MINUTES_OT = 15                    # Tổng OT < 15 phút → Set = 0
MIN_MINUTES_WORKING_HOURS = 10         # Working hours < 10 phút → Set = 0  
MIN_MINUTES_PRE_SHIFT_OT = 60          # OT trước ca < 60 phút → Set = 0
MIN_MINUTES_CHECKIN_FILTER = 10        # Filter checkin < 10 phút (thay vì 30 phút)
```

### Enhanced Logic Improvements

#### 1. Multiple Checkin Handling
```python
# OLD: Filter < 30 phút (quá strict, loại bỏ checkin hợp lệ)
if time_diff >= 30:  # Too strict!

# NEW: Filter < 10 phút (ít strict hơn, giữ lại checkin hợp lệ)
if time_diff >= MIN_MINUTES_CHECKIN_FILTER:  # More flexible!

# Logic: Sớm nhất = Check In, Muộn nhất = Check Out
check_in = filtered_checkins[0].check_time      # Sớm nhất
check_out = filtered_checkins[-1].check_time    # Muộn nhất
```

#### 2. Special Working Hours Case
```python
def calculate_morning_hours(check_in, check_out, shift_config):
    """Special case: Check in trước ca & check out trước nghỉ trưa"""
    
    # Special case logic
    if check_in < shift_start and check_out <= break_start:
        # Working hours = check out - bắt đầu ca (KHÔNG phải check in)
        if check_out > shift_start:
            return time_diff_in_hours(check_out, shift_start)
        else:
            return 0
    
    # Normal case: logic cũ
    morning_start = max(check_in, shift_start)
    morning_end = min(check_out, break_start)
    return time_diff_in_hours(morning_end, morning_start)
```

#### 3. Constants-Based Thresholds
```python
# OT Calculation với constants
def calculate_actual_overtime(...):
    pre_shift_ot = time_diff_in_hours(shift_start, check_in)
    
    # OLD: Hardcode if pre_shift_ot < 1:
    # NEW: Constants-based
    if pre_shift_ot * 60 < MIN_MINUTES_PRE_SHIFT_OT:
        pre_shift_ot = 0
    
    total_ot = pre_shift_ot + post_shift_ot
    
    # Apply minimum OT threshold
    if total_ot * 60 < MIN_MINUTES_OT:
        total_ot = 0
    
    return total_ot

# Working Hours với constants  
def calculate_all_fields(...):
    total_working_hours = morning_hours + afternoon_hours
    
    # Apply minimum working hours threshold
    if total_working_hours * 60 < MIN_MINUTES_WORKING_HOURS:
        total_working_hours = 0
    
    self.working_hours = self.decimal_round(total_working_hours)
```

#### 4. Real-time Algorithm Dialog
```javascript
// JavaScript gets constants from server
frappe.call({
    method: "...get_algorithm_constants",
    callback: function(r) {
        const constants = r.message;
        
        // Use in dialog template
        `<li><strong>Ngưỡng tối thiểu:</strong> Working hours < ${constants.MIN_MINUTES_WORKING_HOURS} phút → Set = 0</li>`
        `<li><strong>OT trước ca tối thiểu:</strong> ${constants.MIN_MINUTES_PRE_SHIFT_OT} phút</li>`
        `<li><strong>Filter checkin:</strong> < ${constants.MIN_MINUTES_CHECKIN_FILTER} phút</li>`
        `<li><strong>Ngưỡng OT:</strong> < ${constants.MIN_MINUTES_OT} phút → Set = 0</li>`
    }
});
```

## 💻 Implementation Code

```python
def calculate_attendance_simple(employee, date, check_in, check_out):
    """Main function - tính toán đầy đủ thông tin"""
    
    # 1. Xác định shift type
    shift_type = get_shift_type(employee, date)
    shift_config = SHIFTS[shift_type]
    
    # 2. Check maternity benefit  
    has_maternity = check_maternity_benefit(employee, date)
    
    # 3. Tính morning hours
    morning = calculate_morning(check_in, check_out, shift_config)
    
    # 4. Tính afternoon hours (có maternity)
    afternoon = calculate_afternoon(check_in, check_out, shift_config, has_maternity)
    
    # 5. Tính actual OT
    actual_ot = calculate_actual_ot(check_in, check_out, shift_config)
    
    # 6. Lấy approved OT
    approved_ot = get_approved_ot(employee, date, shift_type)
    
    # 7. Final calculation
    final_ot = min(actual_ot, approved_ot)
    total = morning + afternoon + final_ot
    
    return {
        "morning_hours": morning,
        "afternoon_hours": afternoon,
        "actual_overtime": actual_ot, 
        "approved_overtime": approved_ot,
        "final_overtime": final_ot,
        "total_hours": total,
        "maternity_benefit": has_maternity
    }

# Configuration
SHIFTS = {
    "Day": {
        "start": "08:00", "end": "17:00",
        "break_start": "12:00", "break_end": "13:00",
        "allows_ot": True
    },
    "Canteen": {
        "start": "07:00", "end": "16:00", 
        "break_start": "11:00", "break_end": "12:00",
        "allows_ot": True
    },
    "Shift 1": {
        "start": "06:00", "end": "14:00",
        "break_start": "10:00", "break_end": "10:00",  # No break
        "allows_ot": False
    },
    "Shift 2": {
        "start": "14:00", "end": "22:00",
        "break_start": "18:00", "break_end": "18:00",  # No break  
        "allows_ot": False
    }
}
```

## ✅ Validation Rules

```python
def validate_attendance(employee, date, check_in, check_out):
    # 1. Basic validation
    if not check_in or not check_out or check_out <= check_in:
        raise ValueError("Invalid check in/out times")
    
    # 2. Shift type validation
    shift_type = get_shift_type(employee, date)
    if not shift_type:
        raise ValueError("Cannot determine shift type")
    
    # 3. OT registration validation
    if shift_type in ["Shift 1", "Shift 2"]:
        ot_regs = get_ot_registrations(employee, date)
        if ot_regs:
            raise ValueError("Shift 1/2 cannot have OT registrations")
    
    return True

def validate_maternity_tracking(employee, tracking_record):
    # 1. Date range validation
    if tracking_record.to_date < tracking_record.from_date:
        raise ValueError("Invalid date range")
    
    # 2. Type validation  
    if tracking_record.type not in ["Pregnant", "Maternity Leave", "Young child"]:
        raise ValueError("Invalid maternity type")
    
    # 3. No overlap validation
    existing = get_overlapping_maternity_records(employee, tracking_record)
    if existing:
        raise ValueError("Maternity tracking periods cannot overlap")
    
    return True
```
 

## 📊 Testing Checklist

### Test Cases Cơ Bản
- [ ] Day shift bình thường: 8:00→17:00 = 8h
- [ ] Day shift có OT: 7:00→19:00 với reg = 10h  
- [ ] Shift 1 không OT: 6:00→16:00 = 8h
- [ ] Canteen có OT: 6:00→18:00 với reg = 10h
- [ ] Shift 2 không OT: 14:00→24:00 = 8h

### Test Cases Maternity
- [ ] Pregnant về sớm: 8:00→16:00 = 8h (Day)
- [ ] Young child về sớm: 7:00→15:00 = 8h (Canteen)  
- [ ] Hết benefit: 8:00→16:00 = 7h
- [ ] Pregnant + OT: 8:00→18:00 = 9h

### Edge Cases
- [ ] Đi muộn + về sớm
- [ ] OT vượt approved
- [ ] Multiple OT registrations
- [ ] Thay đổi shift trong tháng
- [ ] Maternity overlap periods

 