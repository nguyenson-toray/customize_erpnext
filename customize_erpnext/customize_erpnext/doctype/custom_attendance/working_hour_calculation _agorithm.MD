# Thuật Toán Tính Giờ Làm Việc - Chi Tiết Đầy Đủ

## 📋 Quy Tắc Cơ Bản

### 1. Các Loại Ca Làm Việc
| Shift Type | Giờ Làm | Nghỉ Trưa | Cho phép OT | Ghi chú |
|------------|---------|-----------|-------------|---------|
| **Day** | 8:00-17:00 | 12:00-13:00 | ✅ Có | Mặc định |
| **Canteen** | 7:00-16:00 | 11:00-12:00 | ✅ Có | Group = Canteen |
| **Shift 1** | 6:00-14:00 | 10:00-10:00 | ❌ Không | Đăng ký riêng |
| **Shift 2** | 14:00-22:00 | 18:00-18:00 | ❌ Không | Đăng ký riêng |

### 2. Thông Tin Output Đầy Đủ
```json
{
  "morning_hours": 4.0,           // Giờ làm buổi sáng
  "afternoon_hours": 4.0,         // Giờ làm buổi chiều
  "actual_overtime": 2.5,         // Tăng ca thực tế (pre + post)
  "approved_overtime": 3.0,       // Tăng ca được duyệt
  "final_overtime": 2.5,          // min(actual, approved)
  "total_hours": 10.5             // sáng + chiều + final_ot
}
```

## 🔄 Sơ Đồ Thuật Toán Chi Tiết

```mermaid
graph TD
    A[Bắt đầu: Check In/Out] --> B{Có đủ dữ liệu?}
    B -->|Không| Z[Tất cả = 0]
    B -->|Có| C[Xác định Shift Type]
    
    C --> D[Lấy thông tin ca]
    D --> E[Tính Giờ Buổi Sáng]
    E --> F[Tính Giờ Buổi Chiều]
    F --> G[Tính Tăng Ca Thực Tế]
    G --> H[Lấy Tăng Ca Được Duyệt]
    H --> I[Tính Final OT]
    I --> J[Tính Tổng]
    
    E --> E1{Check in trước<br/>giờ bắt đầu sáng?}
    E1 -->|Có| E2[Tính từ giờ bắt đầu ca]
    E1 -->|Không| E3[Tính từ check in]
    E2 --> E4[Morning = min(break_start - shift_start, check_out - shift_start)]
    E3 --> E4
    
    F --> F1{Check out sau<br/>giờ kết thúc chiều?}
    F1 -->|Có| F2[Tính đến giờ kết thúc ca]
    F1 -->|Không| F3[Tính đến check out]
    F2 --> F4[Afternoon = min(shift_end - break_end, check_out - break_end)]
    F3 --> F4
    
    G --> G1[Pre-shift OT:<br/>Giờ trước ca]
    G1 --> G2[Post-shift OT:<br/>Giờ sau ca]
    G2 --> G3[Actual OT = Pre + Post]
    
    H --> H1{Shift 1/2?}
    H1 -->|Có| H2[Approved OT = 0]
    H1 -->|Không| H3[Lấy từ OT Registration]
    
    I --> I1[Final OT = min(Actual, Approved)]
    J --> J1[Total = Morning + Afternoon + Final OT]
```

## ⚙️ Chi Tiết Thuật Toán

### Bước 1: Tính Giờ Buổi Sáng
```python
def calculate_morning_hours(check_in, check_out, shift_config):
    shift_start = shift_config["start_time"]
    break_start = shift_config["break_start"] 
    
    # Xử lý đi sớm: tính từ shift_start
    morning_start = max(check_in, shift_start)
    morning_end = min(check_out, break_start)
    
    if morning_end > morning_start:
        return (morning_end - morning_start).total_seconds() / 3600
    return 0.0
```

### Bước 2: Tính Giờ Buổi Chiều  
```python
def calculate_afternoon_hours(check_in, check_out, shift_config):
    break_end = shift_config["break_end"]
    shift_end = shift_config["end_time"]
    
    # Xử lý về trễ: chỉ tính đến shift_end cho giờ bình thường
    afternoon_start = max(check_in, break_end)
    afternoon_end = min(check_out, shift_end)
    
    if afternoon_end > afternoon_start:
        return (afternoon_end - afternoon_start).total_seconds() / 3600
    return 0.0
```

### Bước 3: Tính Tăng Ca Thực Tế
```python
def calculate_actual_overtime(check_in, check_out, shift_config):
    shift_start = shift_config["start_time"]
    shift_end = shift_config["end_time"]
    
    pre_shift_ot = 0.0
    post_shift_ot = 0.0
    
    # Pre-shift OT: Đi sớm hơn giờ bắt đầu ca
    if check_in < shift_start:
        pre_shift_ot = (shift_start - check_in).total_seconds() / 3600
    
    # Post-shift OT: Về trễ hơn giờ kết thúc ca  
    if check_out > shift_end:
        post_shift_ot = (check_out - shift_end).total_seconds() / 3600
    
    return pre_shift_ot + post_shift_ot
```

### Bước 4: Lấy Tăng Ca Được Duyệt
```python
def get_approved_overtime(employee, date, shift_type):
    # Shift 1, 2: Không bao giờ có approved OT
    if shift_type in ['Shift 1', 'Shift 2']:
        return 0.0
    
    # Day, Canteen: Lấy từ OT Registration
    ot_registrations = frappe.get_all(
        "Overtime Registration Detail",
        filters={"employee": employee, "date": date},
        fields=["begin_time", "end_time"]
    )
    
    total_approved = 0.0
    for ot in ot_registrations:
        hours = (ot.end_time - ot.begin_time).total_seconds() / 3600
        total_approved += hours
    
    return total_approved
```

### Bước 5: Tính Final OT và Tổng
```python
def calculate_final_results(morning, afternoon, actual_ot, approved_ot):
    final_overtime = min(actual_ot, approved_ot)
    total_hours = morning + afternoon + final_overtime
    
    return {
        "morning_hours": morning,
        "afternoon_hours": afternoon, 
        "actual_overtime": actual_ot,
        "approved_overtime": approved_ot,
        "final_overtime": final_overtime,
        "total_hours": total_hours
    }
```

## 📝 Ví Dụ Chi Tiết

### Ví Dụ 1: Ca Day - Đi Sớm, Về Trễ
```
Employee: John (Group: thường)
Shift: Day (8:00-17:00, Break: 12:00-13:00)
Check in: 7:00, Check out: 19:00
OT Registration: 7:00-8:00 (1h), 17:00-18:00 (1h) = Tổng 2h

Tính toán:
→ Morning: max(7:00, 8:00) to 12:00 = 8:00-12:00 = 4h
→ Afternoon: 13:00 to min(19:00, 17:00) = 13:00-17:00 = 4h  
→ Actual OT: (8:00-7:00) + (19:00-17:00) = 1h + 2h = 3h
→ Approved OT: 1h + 1h = 2h
→ Final OT: min(3h, 2h) = 2h
→ Total: 4h + 4h + 2h = 10h
```

### Ví Dụ 2: Ca Canteen - Đi Đúng Giờ, Về Trễ
```
Employee: Mary (Group: Canteen)
Shift: Canteen (7:00-16:00, Break: 11:00-12:00)  
Check in: 7:00, Check out: 18:00
OT Registration: 16:00-18:00 (2h) = Tổng 2h

Tính toán:
→ Morning: 7:00-11:00 = 4h
→ Afternoon: 12:00 to min(18:00, 16:00) = 12:00-16:00 = 4h
→ Actual OT: 0h + (18:00-16:00) = 2h
→ Approved OT: 2h  
→ Final OT: min(2h, 2h) = 2h
→ Total: 4h + 4h + 2h = 10h
```

### Ví Dụ 3: Shift 1 - Đi Sớm, Về Trễ (Không OT)
```
Employee: Peter (Đăng ký Shift 1)
Shift: Shift 1 (6:00-14:00, Break: 10:00-10:00)
Check in: 5:30, Check out: 15:00
OT Registration: Không có

Tính toán:
→ Morning: max(5:30, 6:00) to 10:00 = 6:00-10:00 = 4h
→ Afternoon: 10:00 to min(15:00, 14:00) = 10:00-14:00 = 4h
→ Actual OT: (6:00-5:30) + (15:00-14:00) = 0.5h + 1h = 1.5h
→ Approved OT: 0h (Shift 1 không được phép)
→ Final OT: min(1.5h, 0h) = 0h
→ Total: 4h + 4h + 0h = 8h
```

### Ví Dụ 4: Ca Day - Đi Muộn, Về Sớm
```
Employee: Anna (Group: thường)
Shift: Day (8:00-17:00, Break: 12:00-13:00)
Check in: 8:30, Check out: 16:30  
OT Registration: Không có

Tính toán:
→ Morning: 8:30-12:00 = 3.5h
→ Afternoon: 13:00-16:30 = 3.5h
→ Actual OT: 0h + 0h = 0h (không đi sớm, không về trễ)
→ Approved OT: 0h
→ Final OT: min(0h, 0h) = 0h  
→ Total: 3.5h + 3.5h + 0h = 7h
```

### Ví Dụ 5: Ca Day - OT Vượt Quá Approved
```
Employee: Tom (Group: thường)
Shift: Day (8:00-17:00, Break: 12:00-13:00)
Check in: 6:00, Check out: 20:00
OT Registration: 17:00-18:00 (1h) = Tổng 1h

Tính toán:
→ Morning: max(6:00, 8:00) to 12:00 = 8:00-12:00 = 4h
→ Afternoon: 13:00-17:00 = 4h
→ Actual OT: (8:00-6:00) + (20:00-17:00) = 2h + 3h = 5h
→ Approved OT: 1h
→ Final OT: min(5h, 1h) = 1h (chỉ tính theo approved)
→ Total: 4h + 4h + 1h = 9h
```

## 📊 Ma Trận Kết Quả Chi Tiết

### Ca Day (8:00-17:00, Break: 12:00-13:00)
| Scenario | Check In/Out | Morning | Afternoon | Actual OT | Approved OT | Final OT | Total |
|----------|--------------|---------|-----------|-----------|-------------|----------|-------|
| **Bình thường** | 8:00→17:00 | 4h | 4h | 0h | 0h | 0h | **8h** |
| **Đi sớm** | 7:00→17:00 | 4h | 4h | 1h | 1h* | 1h | **9h** |
| **Về trễ** | 8:00→19:00 | 4h | 4h | 2h | 2h* | 2h | **10h** |
| **Đi sớm + về trễ** | 7:00→19:00 | 4h | 4h | 3h | 2h* | 2h | **10h** |
| **Đi muộn** | 8:30→17:00 | 3.5h | 4h | 0h | 0h | 0h | **7.5h** |
| **Về sớm** | 8:00→16:00 | 4h | 3h | 0h | 0h | 0h | **7h** |
| **OT vượt** | 7:00→20:00 | 4h | 4h | 5h | 1h* | 1h | **9h** |

*\* Giả sử có đăng ký OT*

### Shift 1 (6:00-14:00, Break: 10:00-10:00) - Không OT
| Scenario | Check In/Out | Morning | Afternoon | Actual OT | Approved OT | Final OT | Total |
|----------|--------------|---------|-----------|-----------|-------------|----------|-------|
| **Bình thường** | 6:00→14:00 | 4h | 4h | 0h | 0h | 0h | **8h** |
| **Đi sớm** | 5:00→14:00 | 4h | 4h | 1h | 0h | 0h | **8h** |
| **Về trễ** | 6:00→16:00 | 4h | 4h | 2h | 0h | 0h | **8h** |
| **Cả hai** | 5:00→16:00 | 4h | 4h | 3h | 0h | 0h | **8h** |

## 🔧 Code Implementation Hoàn Chỉnh

```python
def calculate_attendance_full_details(employee, date, check_in, check_out):
    """
    Tính toán đầy đủ thông tin chấm công
    Returns: Dict với tất cả thông tin chi tiết
    """
    
    if not check_in or not check_out:
        return {
            "morning_hours": 0.0,
            "afternoon_hours": 0.0, 
            "actual_overtime": 0.0,
            "approved_overtime": 0.0,
            "final_overtime": 0.0,
            "total_hours": 0.0
        }
    
    # Bước 1: Xác định ca làm việc
    shift_type = get_employee_shift_type(employee, date)
    shift_config = SHIFT_CONFIGS[shift_type]
    
    # Bước 2: Tính giờ buổi sáng
    morning_hours = calculate_morning_hours(check_in, check_out, shift_config)
    
    # Bước 3: Tính giờ buổi chiều
    afternoon_hours = calculate_afternoon_hours(check_in, check_out, shift_config)
    
    # Bước 4: Tính tăng ca thực tế (pre + post shift)
    actual_overtime = calculate_actual_overtime(check_in, check_out, shift_config)
    
    # Bước 5: Lấy tăng ca được duyệt
    approved_overtime = get_approved_overtime(employee, date, shift_type)
    
    # Bước 6: Tính final overtime
    final_overtime = min(actual_overtime, approved_overtime)
    
    # Bước 7: Tính tổng
    total_hours = morning_hours + afternoon_hours + final_overtime
    
    return {
        "shift_type": shift_type,
        "morning_hours": round(morning_hours, 2),
        "afternoon_hours": round(afternoon_hours, 2),
        "actual_overtime": round(actual_overtime, 2),
        "approved_overtime": round(approved_overtime, 2), 
        "final_overtime": round(final_overtime, 2),
        "total_hours": round(total_hours, 2),
        "breakdown": f"{morning_hours:.1f}h sáng + {afternoon_hours:.1f}h chiều + {final_overtime:.1f}h OT = {total_hours:.1f}h"
    }

def calculate_morning_hours(check_in, check_out, shift_config):
    """Tính giờ làm buổi sáng"""
    shift_start = shift_config["start_time"]
    break_start = shift_config["break_start"]
    
    # Xử lý đi sớm: không tính trước shift_start vào giờ bình thường
    morning_start = max(check_in, shift_start)
    morning_end = min(check_out, break_start)
    
    if morning_end > morning_start:
        return (morning_end - morning_start).total_seconds() / 3600
    return 0.0

def calculate_afternoon_hours(check_in, check_out, shift_config):
    """Tính giờ làm buổi chiều"""  
    break_end = shift_config["break_end"]
    shift_end = shift_config["end_time"]
    
    # Xử lý về trễ: không tính sau shift_end vào giờ bình thường
    afternoon_start = max(check_in, break_end)
    afternoon_end = min(check_out, shift_end)
    
    if afternoon_end > afternoon_start:
        return (afternoon_end - afternoon_start).total_seconds() / 3600
    return 0.0

def calculate_actual_overtime(check_in, check_out, shift_config):
    """Tính tăng ca thực tế (pre-shift + post-shift)"""
    shift_start = shift_config["start_time"] 
    shift_end = shift_config["end_time"]
    
    pre_shift_ot = 0.0
    post_shift_ot = 0.0
    
    # Pre-shift OT: làm trước giờ bắt đầu ca
    if check_in < shift_start:
        pre_shift_ot = (shift_start - check_in).total_seconds() / 3600
    
    # Post-shift OT: làm sau giờ kết thúc ca
    if check_out > shift_end:
        post_shift_ot = (check_out - shift_end).total_seconds() / 3600
    
    return pre_shift_ot + post_shift_ot

def get_approved_overtime(employee, date, shift_type):
    """Lấy tổng tăng ca được duyệt"""
    
    # Shift 1, 2: Không bao giờ có approved OT
    if shift_type in ['Shift 1', 'Shift 2']:
        return 0.0
    
    # Day, Canteen: Tính tổng từ OT Registration
    ot_registrations = frappe.get_all(
        "Overtime Registration Detail",
        filters={
            "employee": employee, 
            "date": date,
            "parenttype": "Overtime Registration"
        },
        fields=["begin_time", "end_time"]
    )
    
    total_approved = 0.0
    for ot in ot_registrations:
        duration = (ot.end_time - ot.begin_time).total_seconds() / 3600
        total_approved += duration
    
    return total_approved

# Hook vào Attendance doctype
def before_save(doc, method):
    """Auto-calculate với thông tin đầy đủ khi save"""
    if doc.check_in and doc.check_out:
        result = calculate_attendance_full_details(
            doc.employee,
            doc.attendance_date, 
            doc.check_in,
            doc.check_out
        )
        
        # Update các fields
        doc.shift_type = result["shift_type"]
        doc.custom_morning_hours = result["morning_hours"]
        doc.custom_afternoon_hours = result["afternoon_hours"] 
        doc.custom_actual_overtime = result["actual_overtime"]
        doc.custom_approved_overtime = result["approved_overtime"]
        doc.custom_final_overtime = result["final_overtime"]
        doc.working_hours = result["total_hours"]
        doc.custom_breakdown = result["breakdown"]
```

## 📋 Custom Fields Cần Tạo

### Trong Attendance DocType:
```python
custom_fields = [
    {
        "fieldname": "custom_morning_hours",
        "fieldtype": "Float", 
        "label": "Morning Hours",
        "precision": 2
    },
    {
        "fieldname": "custom_afternoon_hours", 
        "fieldtype": "Float",
        "label": "Afternoon Hours", 
        "precision": 2
    },
    {
        "fieldname": "custom_actual_overtime",
        "fieldtype": "Float",
        "label": "Actual Overtime",
        "precision": 2
    },
    {
        "fieldname": "custom_approved_overtime",
        "fieldtype": "Float", 
        "label": "Approved Overtime",
        "precision": 2
    },
    {
        "fieldname": "custom_final_overtime",
        "fieldtype": "Float",
        "label": "Final Overtime", 
        "precision": 2
    },
    {
        "fieldname": "custom_breakdown",
        "fieldtype": "Data",
        "label": "Hours Breakdown"
    }
]
``` 