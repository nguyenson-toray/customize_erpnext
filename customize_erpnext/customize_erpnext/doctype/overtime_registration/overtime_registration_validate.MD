# Overtime Registration - Validation Rules

## Tổng quan

Tài liệu này mô tả các quy tắc validation cho Overtime Registration, bao gồm cả client-side (JavaScript) và server-side (Python).

---

## 1. Client-side Validation (JavaScript)

### 1.1. before_save - Kiểm tra thai sản

**Hàm:** `check_maternity_benefit_adjustment(frm)`

**Mô tả:** Kiểm tra nhân viên có chế độ thai sản và hỏi điều chỉnh giờ OT.

**Điều kiện:**
- Nhân viên có Maternity Tracking với:
  - `type = 'Pregnant'` và `apply_pregnant_benefit = 1`
  - `type = 'Young Child'`
  - `type = 'Maternity Leave'`
- Giờ bắt đầu OT = giờ kết thúc ca bình thường (VD: 17:00 cho ca Day)

**Kết quả:**
- Hiện dialog hỏi có muốn điều chỉnh giờ sớm hơn 1h không
- Nếu "Có": điều chỉnh begin_time và end_time -1h
- Nếu "Không": giữ nguyên

**Ví dụ:**
```
Nhân viên mang thai, OT 17:00-19:00
→ Dialog: "Có muốn điều chỉnh thành 16:00-18:00?"
```

---

### 1.2. validate - Các trường bắt buộc

**Hàm:** `validate_required_fields(frm)`

**Mô tả:** Kiểm tra các trường bắt buộc.

**Điều kiện:**
- `employee` không được trống
- `date` không được trống
- `begin_time` không được trống
- `end_time` không được trống

**Thông báo lỗi:**
```
Row #1: Employee, Date, Begin Time, and End Time are required.
```

---

### 1.3. validate - Giờ bắt đầu < Giờ kết thúc

**Hàm:** `validate_time_order(frm)`

**Mô tả:** Kiểm tra thứ tự thời gian.

**Điều kiện:**
- `begin_time < end_time`

**Thông báo lỗi:**
```
Row #1: Giờ bắt đầu (19:00:00) phải nhỏ hơn giờ kết thúc (17:00:00)
```

---

### 1.4. validate - Trùng lặp trong form

**Hàm:** `validate_duplicate_rows(frm)`

**Mô tả:** Kiểm tra trùng lặp hoặc overlap thời gian trong cùng form.

**Điều kiện:**
- Cùng employee + cùng date
- Thời gian overlap

**Thông báo lỗi:**
```
Row 1 và 2: Trùng lặp OT cho nhân viên Nguyễn Văn A ngày 2025-11-24
```

---

### 1.5. validate - Một dòng OT mỗi nhân viên mỗi ngày

**Hàm:** `validate_single_post_shift_entry(frm)`

**Mô tả:** Không cho phép nhiều dòng OT cho cùng nhân viên trong cùng ngày.

**Điều kiện:**
- Mỗi employee chỉ có 1 dòng cho mỗi date trong form

**Thông báo lỗi:**
```
Rows 1, 2: Nhân viên Nguyễn Văn A có 2 dòng OT trong ngày 2025-11-24.
Nên gộp thành 1 dòng liên tục.
```

**Lý do:** Thay vì tạo nhiều dòng riêng (17:00-19:00, 19:00-21:00), nên gộp thành 1 dòng (17:00-21:00).

---

## 2. Server-side Validation (Python)

### 2.1. Kiểm tra OT nằm ngoài giờ làm việc

**Hàm:** `validate_ot_outside_working_hours()`

**Mô tả:** OT phải nằm ngoài giờ làm việc của ca.

**Cấu hình ca:**

| Ca | Bắt đầu | Kết thúc | Nghỉ trưa | Cho phép OT |
|----|---------|----------|-----------|-------------|
| Day | 08:00 | 17:00 | 12:00-13:00 | Có |
| Canteen | 07:00 | 16:00 | 11:00-12:00 | Có |
| Shift 1 | 06:00 | 14:00 | - | Không |
| Shift 2 | 14:00 | 22:00 | - | Không |

**Điều kiện hợp lệ:**
- **Trước ca:** OT kết thúc trước hoặc đúng lúc ca bắt đầu
- **Giờ nghỉ trưa:** OT trong khoảng break_start - break_end
- **Sau ca:** OT bắt đầu từ hoặc sau giờ kết thúc ca
  - Nhân viên có chế độ thai sản: shift_end - 1h

**Thông báo lỗi:**
```
Row #1: Giờ tăng ca phải nằm ngoài giờ làm việc
(trước 08:00, trong giờ nghỉ trưa 12:00-13:00, hoặc sau 17:00)
```

```
Row #1: Ca Shift 1 không được phép đăng ký tăng ca
```

---

### 2.2. Kiểm tra trùng lặp trong form

**Hàm:** `validate_duplicate_employees()`

**Mô tả:** Không cho phép trùng lặp hoặc overlap trong cùng form.

**Điều kiện:**
- Cùng employee + cùng date
- Thời gian overlap

**Thông báo lỗi:**
```
Row 1 and 2: Duplicate overtime for employee Nguyễn Văn A on 2025-11-24
```

---

### 2.3. Kiểm tra xung đột với OT đã submit

**Hàm:** `validate_conflicting_ot_requests()`

**Mô tả:** Kiểm tra overlap và tính liên tục với OT đã submit.

#### 2.3.1. Kiểm tra Overlap

**Điều kiện:**
- Không được overlap thời gian với OT đã submit (docstatus = 1)

**Thông báo lỗi:**
```
Row 1: Employee Nguyễn Văn A already has overtime on 2025-11-24 (17:00-19:00).
Conflicts with OTR-251124-0001
```

#### 2.3.2. Kiểm tra Liên tục

**Điều kiện:**
- OT mới phải liên tục với OT đã submit:
  - Bắt đầu ngay sau OT đã submit kết thúc, HOẶC
  - Kết thúc ngay trước OT đã submit bắt đầu, HOẶC
  - Bắt đầu đúng giờ kết thúc ca (nếu là OT đầu tiên)

**Thông báo lỗi:**
```
Row 1: OT 19:00-20:00 không liên tục với OT đã đăng ký (16:00:00-18:00:00).
Xem: OTR-251124-0068
```

**Ví dụ:**

| OT đã submit | OT mới | Kết quả |
|--------------|--------|---------|
| 16:00-18:00 | 18:00-20:00 | ✓ Hợp lệ |
| 16:00-18:00 | 19:00-20:00 | ✗ Không liên tục |
| 16:00-18:00 | 20:00-21:00 | ✗ Không liên tục |
| - | 17:00-19:00 | ✓ Hợp lệ (bắt đầu từ shift end) |

---

### 2.4. Kiểm tra liên tục với OT cùng ngày trong form

**Hàm:** `validate_ot_continuity_same_day()`

**Mô tả:** Nếu có nhiều OT entries cho cùng employee cùng ngày trong form, chúng phải liên tục.

**Điều kiện:**
- OT đầu tiên phải bắt đầu đúng giờ kết thúc ca
- Các OT tiếp theo phải bắt đầu ngay sau OT trước kết thúc

**Thông báo lỗi:**
```
Row #1: Giờ tăng ca đầu tiên phải bắt đầu ngay sau ca (17:00)
```

```
Row #2: Giờ tăng ca phải liên tục với OT trước đó (Row #1 kết thúc lúc 19:00)
```

---

## 3. Flow Validation

```
┌─────────────────────────────────────┐
│         User clicks Save            │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│    JS: before_save                  │
│    - Maternity dialog check         │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│    JS: validate                     │
│    1. Required fields               │
│    2. Time order                    │
│    3. Duplicate rows                │
│    4. Single entry per emp/day      │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│    Python: validate                 │
│    1. OT outside working hours      │
│    2. Duplicate in form             │
│    3. Conflict with submitted OT    │
│    4. Continuity with same day OT   │
│    5. Calculate totals              │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│           Save Success              │
└─────────────────────────────────────┘
```

---

## 4. Ví dụ tổng hợp

### 4.1. Trường hợp hợp lệ

```
Employee: TIQN-0160 (Ca Day)
Date: 2025-11-24

Row 1: 17:00 - 21:00  ✓
```

### 4.2. Trường hợp không hợp lệ

**Nhiều dòng cùng employee cùng ngày:**
```
Row 1: TIQN-0160 | 2025-11-24 | 17:00 - 19:00
Row 2: TIQN-0160 | 2025-11-24 | 19:00 - 21:00
→ Lỗi: Nên gộp thành 1 dòng
```

**OT trong giờ làm việc:**
```
Row 1: TIQN-0160 | 2025-11-24 | 15:00 - 17:00
→ Lỗi: Giờ tăng ca phải nằm ngoài giờ làm việc
```

**Không liên tục với OT đã submit:**
```
Đã submit: TIQN-0160 | 2025-11-24 | 16:00 - 18:00
Mới: TIQN-0160 | 2025-11-24 | 19:00 - 20:00
→ Lỗi: OT 19:00-20:00 không liên tục với OT đã đăng ký (16:00-18:00)
```

**Ca không cho phép OT:**
```
Row 1: TIQN-0161 (Shift 1) | 2025-11-24 | 14:00 - 16:00
→ Lỗi: Ca Shift 1 không được phép đăng ký tăng ca
```

---

## 5. Lưu ý

1. **Maternity benefit:** Nhân viên có chế độ thai sản được kết thúc ca sớm hơn 1h, nên giờ OT cũng bắt đầu sớm hơn 1h.

2. **Gộp OT:** Thay vì tạo nhiều dòng OT riêng biệt (17:00-19:00, 19:00-21:00), nên gộp thành 1 dòng liên tục (17:00-21:00).

3. **Liên tục:** OT mới phải liên tục với OT đã submit trước đó để đảm bảo không có khoảng trống.

4. **Link tham chiếu:** Khi có xung đột với OT đã submit, hệ thống sẽ hiển thị link đến document đó để user kiểm tra.
