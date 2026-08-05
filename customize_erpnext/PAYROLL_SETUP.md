# Hướng dẫn setup Payroll TIQN (theo mẫu Payment Slip hiện hành)

Tài liệu dò ngược từ **2 phiếu lương thật** kỳ Jul 2026, kiểm chứng số học khớp 100% cả hai:
- `TIQN-0148` Nguyễn Thái Sơn — IT Subleader, đi làm **25/26** ngày, OT **cuối tuần** 8h
- `TIQN-0019` Cao Thị Cẩm — Sewing Worker, đi làm **26/26** ngày, OT **ngày thường** 35h

Hai phiếu bổ sung cho nhau: NV thứ nhất có PC chức vụ + PC điện thoại, NV thứ hai có PC kỹ thuật +
PC xăng xe + thưởng chuyên cần + KPI — nhờ vậy tách bạch được khoản nào vào căn cứ BH.

Kỳ lương: **26 tháng trước → 25 tháng này** (phiếu Jul 2026 = 26 Jun đến 25 Jul).

---

## 1. Ánh xạ phiếu lương → ERPNext

| Phiếu | Giá trị mẫu | Trong ERPNext |
|---|---:|---|
| `1 Basic Salary (a)` | 17,214,001 | **`SSA.base`** — mức lương hợp đồng |
| `1.1 Standard working days` | 26 | `total_working_days` (thống kê, không phải tiền) |
| `1.2 Actual working days` | 25 → 16,551,924 | `payment_days` + số tiền do ERPNext tự prorate |
| `2 Overtime (b)` | 1,416,462 | Component có formula |
| `3 Monthly Salary (c=a+b)` | 17,968,386 | **KHÔNG tạo component** — là tổng trung gian |
| `3.x Allowance (d)` | 1,400,000 | Các component phụ cấp |
| `4.x Incentive (e)` | 0 | Các component thưởng |
| `5 Sub total (f=c+d+e)` | 19,368,386 | **= `gross_pay`**, ERPNext tự tính |
| `6.x Deductions (g)` | 1,988,341 | **= `total_deduction`**, ERPNext tự tính |
| `7.x Others (h)` | 50,000 | Earning không tính thuế/BH |
| `9 Net Salary (j=f-g+h+i)` | 17,430,045 | **= `net_pay`**, ERPNext tự tính |

---

## 2. Công thức đã dò ra (đã kiểm chứng)

### 2.1. Căn cứ đóng bảo hiểm (`SI_BASE`) — **LÀ SỐ ĐĂNG KÝ RIÊNG, KHÔNG TÍNH TỪ PHIẾU**

> 🔴 **Đây là kết luận quan trọng nhất của tài liệu.** Ban đầu tôi tưởng `SI_BASE` = Basic + một số
> phụ cấp, vì 2 phiếu đầu khớp chính xác. **Phiếu TIQN-0006 bác bỏ điều đó.**

Giả thuyết tốt nhất tìm được: `Basic + mọi khoản TRỪ (xăng xe, điện thoại, KPI)`.
Đối chiếu trên **5 phiếu có đóng BH**:

| Phiếu | Công thức tính ra | Căn cứ BH thật (suy từ BHXH) | Lệch | |
|---|---:|---:|---:|---|
| TIQN-0148 | 18,414,001 | 18,414,000 | +1 | ✓ |
| TIQN-0019 | 7,757,895 | 7,757,900 | −5 | ✓ |
| TIQN-0047 | 11,720,000 | 11,720,000 | 0 | ✓ |
| **TIQN-0006** | 28,165,135 | **28,939,100** | **−773,965** | ❌ |
| **TIQN-0002** | 52,652,433 | **47,652,438** | **+4,999,995** | ❌ |

**3/5 khớp tuyệt đối, 2/5 lệch nặng** — và lệch theo **hai chiều ngược nhau**, nên không phải
do thiếu/thừa một khoản cố định nào. Riêng TIQN-0006, căn cứ BH còn **lớn hơn cả tổng mọi khoản
có trên phiếu** (28,365,135) → về mặt số học không tổ hợp cộng nào ra được.

→ **Không tồn tại công thức đúng cho mọi nhân viên.** Ba phiếu khớp chỉ là do HR tình cờ đăng ký
mức đóng đúng bằng tổng đó.

**Kết luận: `SI_BASE` là "mức lương đóng BHXH" đăng ký riêng với cơ quan BHXH cho từng NV,
do HR quản lý, không phái sinh từ các dòng lương hàng tháng.** Đây cũng là thực tế phổ biến ở VN:
mức đóng đăng ký một lần, chỉ thay đổi khi làm thủ tục điều chỉnh.

**Cách khai trong ERPNext:**
- Thêm custom field `custom_si_base` (Currency) trên **`Salary Structure Assignment`** — đúng chỗ,
  vì SSA đã gắn với NV + có `from_date` nên tự có lịch sử khi mức đóng thay đổi
- Đã xác minh: `get_component_eval_context()` nạp **toàn bộ field của SSA** vào context công thức
  (`data.update(ssa_as_dict)` trong `apps/hrms/hrms/payroll/utils.py`) → formula dùng thẳng
  `custom_si_base`

```
6.1 BHXH  = custom_si_base * 0.08
6.2 BHYT  = custom_si_base * 0.015
6.3 BHTN  = custom_si_base * 0.01
```

Kiểm chứng cả 3 phiếu (làm tròn thường):

| | TIQN-0148 | TIQN-0019 | TIQN-0006 |
|---|---:|---:|---:|
| `custom_si_base` | 18,414,000 | 7,757,895 | 28,939,100 |
| 6.1 BHXH 8% | 1,473,120 ✓ | 620,632 ✓ | 2,315,128 ✓ |
| 6.2 BHYT 1.5% | 276,210 ✓ | 116,368 ✓ | 434,087 ✓ |
| 6.3 BHTN 1% | 184,140 ✓ | 77,579 ✓ | 289,391 ✓ |

> ⚠ **Không prorate theo ngày công.** TIQN-0148 đi làm 25/26 và TIQN-0006 đi làm 24/26, nhưng
> tiền BH vẫn tính trên nguyên mức đăng ký.

> 📋 **Việc nhập liệu phát sinh:** phải lấy được mức lương đóng BHXH của **toàn bộ ~1038 NV** từ
> hồ sơ BHXH của HR. Đây là cột dữ liệu thứ hai (cùng với `base`) cần import.

### 2.2. Ngày công chuẩn (`total_working_days`) — KHÔNG cố định 26

```
Ngày công chuẩn = số ngày trong chu kỳ (26 tháng n-1 → 25 tháng n) − số Chủ Nhật
Ngày lễ theo quy định nhà nước VẪN TÍNH là ngày công (nghỉ có lương).
```

Kiểm chứng công thức trên các chu kỳ thật:

| Chu kỳ | Số ngày | Trừ CN | Ngày công |
|---|---:|---:|---:|
| **26/06 → 25/07/2026** (phiếu mẫu) | 30 | 4 | **26** ✓ khớp phiếu |
| 26/05 → 25/06/2026 | 31 | 4 | 27 |
| 26/07 → 25/08/2026 | 31 | 5 | 26 |
| 26/08 → 25/09/2026 | 31 | 4 | 27 |

### Holiday List — khai CẢ HAI loại, phân biệt bằng `weekly_off`

Holiday List `2026` dùng chung cho công ty, chứa **67 dòng**:

| Loại | Cờ `Holiday.weekly_off` | Số dòng | Có trừ khỏi ngày công? |
|---|---|---:|---|
| Chủ Nhật | **1** | 52 | ✅ CÓ trừ |
| Ngày lễ nhà nước | **0** | 15 | ❌ KHÔNG trừ (vẫn tính công, có lương) |

**Quy tắc ngày lễ trùng Chủ Nhật:** ngày đó chỉ tính là **Chủ Nhật** (`weekly_off = 1`), và
**HR phải thêm một ngày nghỉ bù** vào Holiday List (`weekly_off = 0`) — không để ngày lễ nằm
trên Chủ Nhật, vì như vậy sẽ bị trừ hai lần.

> Ví dụ 2026: Giỗ Tổ 26/04 rơi Chủ Nhật → 26/04 gắn `weekly_off = 1`, ngày bù **02/05**
> (thứ Bảy) là dòng riêng `weekly_off = 0`. Sau khi sửa: đúng 52 Chủ Nhật, 15 ngày lễ,
> không ngày lễ nào nằm trên Chủ Nhật.

⚠ **HRMS gốc trừ TẤT CẢ dòng trong Holiday List** khỏi `total_working_days`, không phân biệt
`weekly_off`. Kỳ Tết sẽ ra **18 ngày** thay vì 27 → đơn giá ngày (`base / total_working_days`)
sai hoàn toàn. Vì vậy cần override — xem mục 5b.6.

Kiểm chứng thực tế sau khi override:

| Kỳ lương | Ngày | Chủ Nhật | Ngày lễ | Ngày công chuẩn |
|---|---:|---:|---:|---:|
| 26/06 → 25/07 | 30 | 4 | 0 | **26** ✓ |
| 26/04 → 25/05 | 30 | 5 | 3 | **25** ✓ |
| 26/01 → 25/02 (Tết) | 31 | 4 | 9 | **27** ✓ |
| 26/08 → 25/09 | 31 | 4 | 2 | **27** ✓ |

### 2.3. Lương theo ngày công
```
Lương thực tế = base / ngày_công_chuẩn * ngày_công_thực_tế
              = 17,214,001 / 26 * 25 = 16,551,924 ✓
```
ERPNext làm sẵn việc này khi component bật `depends_on_payment_days`. **Không cần viết formula.**

### 2.4. Tăng ca

```
Đơn giá giờ = custom_si_base / (total_working_days × 8)
OT = đơn_giá_giờ × số_giờ × hệ_số
```
Hệ số: **ngày thường 150% · cuối tuần 200% · lễ 300%**

> ⚠ **Mẫu số là ngày công chuẩn CỦA THÁNG ĐÓ, không phải hằng số 26** (HR đã xác nhận) —
> dùng chung `total_working_days` với công thức prorate lương cơ bản ở mục 2.3, nên thay đổi
> theo tháng (26 hoặc 27, xem bảng mục 2.2).
> Cả 6 phiếu mẫu đều là tháng 7/2026 (26 ngày) nên **tự chúng không phân biệt được** điều này.

| | TIQN-0148 (cuối tuần) | TIQN-0019 (ngày thường) | TIQN-0047 (ngày thường) |
|---|---:|---:|---:|
| `custom_si_base` | 18,414,001 | 7,757,895 | 11,720,000 |
| Đơn giá giờ = /(26×8) | 88,528.85 | 37,297.57 | 56,346.15 |
| Số giờ × hệ số | 8h × 200% | 35h × 150% | 36.1h × 150% |
| **Tính ra** | **1,416,462** | **1,958,123** | **3,051,144** |
| Phiếu | 1,416,462 ✓ | 1,958,123 ✓ | 3,051,144 ✓ |

> ✅ **TIQN-0047 là phiếu quyết định.** NV này có 3 con số khác hẳn nhau — Basic 7,300,000,
> căn cứ BH 11,720,000, Basic+mọi khoản 12,020,000 — nên phân biệt được dứt khoát:
>
> | Nếu đơn giá OT dùng | Ra | |
> |---|---:|---|
> | Basic | 1,900,457 | ✗ |
> | **Căn cứ BH** | **3,051,144** | ✓ |
> | Basic + mọi khoản | 3,129,245 | ✗ |
>
> ⚠ Không prorate theo ngày công. Đối chứng TIQN-0148 (25/26 ngày): nếu tính trên lương đã
> prorate thì ra 1,365,533, lệch so với phiếu.

### 2.5. Thử việc — quy tắc 21.5% (dòng 7.6)

Khi NV **đang thử việc**, công ty không đóng BHXH mà **trả lại phần công ty phải đóng bằng tiền**:

```
7.6 = 21.5% × SI_BASE     (BHXH 17.5% + BHYT 3% + BHTN 1% — phần công ty đóng)
```

Kéo theo: **trong tháng thử việc thì KHÔNG trừ 6.1/6.2/6.3.** Hai nhóm này loại trừ nhau.

**Cách khai trong ERPNext — dùng field `condition` trên từng dòng Salary Structure.**
Đã xác minh: `get_component_eval_context()` (`apps/hrms/hrms/payroll/utils.py`) nạp **toàn bộ field
của Employee** vào context, nên `employment_type` dùng trực tiếp được:

```python
PROBATION = ("30 Days Probationary Contract", "60 Days Probationary Contract")

# dòng 6.1 / 6.2 / 6.3 (BHXH / BHYT / BHTN)
condition: employment_type not in PROBATION

# dòng 7.6 (21.5%)
condition: employment_type in PROBATION
```

> ⚙ **Đây chính là lý do module Labor Contract đồng bộ `Employee.employment_type`.**
> Field đó là gương của hợp đồng hiện hành (HĐ `Signed` mới nhất đã tới ngày bắt đầu) —
> xem `doctype/labor_contract/README.md` mục 5. Payroll đọc thẳng field này để biết
> NV có đang thử việc hay không, không cần logic riêng.
>
> ⚠ Nghĩa là: **hợp đồng phải được đánh dấu `Signed` đúng lúc**, nếu không payroll sẽ
> trừ/không trừ bảo hiểm sai. Đây là ràng buộc vận hành cần nói rõ với HR.

### 2.6. Phí công đoàn (6.4)
**Số tiền cố định, giống nhau cho mọi nhân viên** — mẫu: `38,948`.
→ Khai thẳng `amount` trong Salary Structure, **không dùng formula**,
và **tắt `depends_on_payment_days`** (không cắt theo ngày công).

### 2.7. Tổng
```
c = a + b          (lương tháng)
f = c + d + e      → gross_pay
j = f - g + h + i  → net_pay
```

---

## 3. Vấn đề của 50 Salary Component hiện tại

Các component **đã tạo đủ tên** nhưng **chưa cấu hình gì** — tất cả đang để mặc định
(`depends_on_payment_days = 1`, `is_tax_applicable = 1`, không có formula). Cần sửa:

### 3.1. ❌ Xoá/disable các component là DÒNG TỔNG
ERPNext tự tính tổng. Để nguyên sẽ **cộng tiền hai lần**:

| Component | Lý do |
|---|---|
| `3 Monthly Salary (c=a+b)` | tổng trung gian |
| `5 Sub total (f=c+d+e)` | = `gross_pay` |
| `6 Deductions (g)` | = `total_deduction` |
| `9 Net Salary (j=...)` | = `net_pay` |
| `2 Overtime (b)`, `3.1 Allowance (d)`, `4 Incentive (e)`, `7 Others (h)` | tiêu đề nhóm |

→ Giữ lại làm **nhãn nhóm trên mẫu in**, không phải component tính tiền.

### 3.2. ⚙ Đặt `statistical_component = 1` cho các dòng KHÔNG PHẢI TIỀN
`1.1 Standard working days`, `1.2 Actual working days`,
`2.1/2.2/2.3 OT working hours` — đây là **số ngày / số giờ**, không được cộng vào lương.

### 3.3. ⚙ `depends_on_payment_days` — **KHÔNG đồng nhất, phải hỏi HR từng khoản**

Bằng chứng từ 6 phiếu cho thấy **có khoản prorate, có khoản không**:

| Khoản | Bằng chứng | Kết luận |
|---|---|---|
| `1 Basic Salary` | mọi phiếu | ✅ **CÓ** prorate |
| `3.2 Technical` | TIQN-2352: 7,692 = 100,000 × 2/26 | ✅ **CÓ** prorate |
| `3.5 Commuting` | TIQN-2352: 23,077 = 300,000 × 2/26 | ✅ **CÓ** prorate |
| `4.1 Attendance` | TIQN-2352: 76,923 = 1,000,000 × 2/26 | ✅ **CÓ** prorate |
| `3.6 Phone` | = 200,000 ở CẢ TIQN-0148 (25/26) LẪN TIQN-0006 (24/26) | ❌ **KHÔNG** prorate |
| `3.7 PCCC` | = 772,000 ở CẢ TIQN-0006 (24/26) LẪN TIQN-0002 (26/26) | ❌ **KHÔNG** prorate |
| `3.8 ATVS` | = 20,000 ở CẢ TIQN-0006 (24/26) LẪN TIQN-0047 (26/26) | ❌ **KHÔNG** prorate |
| `3.3 Position`, `3.4 Accomodation`, `4.2 Responsibility` | chưa đủ dữ liệu | ❓ **hỏi HR** |

Hiện **tất cả đang = 1** → các khoản cột "KHÔNG" sẽ bị cắt sai theo ngày nghỉ.

### 3.3b. 🆕 Nhân viên mới — chưa đóng BH

Phiếu **TIQN-2352** (vào làm giữa kỳ, chỉ 2/26 ngày): **toàn bộ khấu trừ = 0** — không BHXH/BHYT/BHTN,
**kể cả phí công đoàn 38,948** mà mọi NV khác đều đóng. Dòng `7.6 (21.5%)` cũng = 0.

→ Cần hỏi HR quy tắc: BH và phí công đoàn **bắt đầu từ tháng nào** sau khi vào làm? Đây là điều kiện
`condition` thứ hai trên các dòng 6.x, bên cạnh điều kiện thử việc ở mục 2.5.

### 3.4. ⚙ Thuế TNCN
`6.5 PIT/Thuế TNCN` phải bật **`variable_based_on_taxable_salary = 1`** thì ERPNext mới tự tính
theo Income Tax Slab. Hiện đang = 0.

`is_tax_applicable` chỉ có nghĩa với **Earning** — hiện đang bật cả trên Deduction, nên tắt đi.

### 3.5. 🗑 7 component rác của ERPNext mặc định
`Arrear`, `Basic`, `House Rent Allowance`, `Income Tax`, `Leave Encashment`, `Professional Tax`,
`Provident Fund` → disable để khỏi chọn nhầm.

---

## 4. Thứ tự setup

### Bước 1 — Dọn Salary Component (mục 3)
Sửa cấu hình 43 component TIQN + disable 7 component rác.

### Bước 2 — Payroll Period + Income Tax Slab
- `Payroll Period`: đã có 1 record — kiểm tra khớp năm tài chính
- `Income Tax Slab`: **đang có 0 record** → phải tạo theo biểu thuế luỹ tiến VN
  (5% / 10% / 15% / 20% / 25% / 30% / 35%), kèm giảm trừ bản thân 11 triệu và
  người phụ thuộc 4.4 triệu/người
- Cần field lưu **số người phụ thuộc** của từng NV (hiện `custom_number_of_childrens` = 0%)

### Bước 3 — Salary Structure
Tạo theo **bộ phụ cấp** (xem README Labor Contract mục 10.1 — 16 structure = top-15 chức danh +
1 fallback). Mỗi structure gồm:
- Earnings: Basic (formula `base`) + các phụ cấp áp dụng cho nhóm đó + OT
- Deductions: BHXH/BHYT/BHTN (formula theo `SI_BASE`), Phí công đoàn, PIT

### Bước 4 — Salary Structure Assignment
Dùng **`Bulk Salary Structure Assignment`** (có sẵn từ HRMS v16.15.0):
lọc theo chức danh → nhập `base` từng người (mồi sẵn từ `Employee Grade.default_base_pay`) → Assign.
Chi tiết ở README Labor Contract mục 10.1.

### Bước 5 — Nguồn ngày công thực tế
`payment_days` lấy từ Attendance (site đã có ~248k bản ghi). Kiểm tra `Payroll Settings`:
- "Consider Unmarked Attendance As" (Present/Absent)
- Cách tính `total_working_days` — phiếu đang dùng **26 ngày cố định**, cần xác nhận có phải
  mọi tháng đều 26 không, hay thay đổi theo tháng

---

## 5. Cần HR xác nhận trước khi khai công thức

Đã chốt: ngày công chuẩn · quy tắc thử việc 21.5% · phí công đoàn · cách prorate lương ·
**căn cứ BH là số đăng ký riêng** (không tính từ phiếu).

Còn lại:

1. 🔴 **Mức lương đóng BHXH của toàn bộ ~1038 NV** — lấy từ hồ sơ BHXH của HR.
   Đây là cột dữ liệu **bắt buộc**, không suy ra được từ đâu cả. Cùng với `base`, đây là
   2 cột phải import.
2. 🔴 **Khoản nào prorate theo ngày công** — xem bảng mục 3.3. Đã xác định được 7 khoản,
   còn `3.3 chức vụ`, `3.4 nhà ở`, `4.2 trách nhiệm` chưa đủ dữ liệu.
3. 🔴 **BH và phí công đoàn bắt đầu từ tháng nào** với NV mới (xem mục 3.3b).
4. **Thuế TNCN (6.5)** — cần **số người phụ thuộc** của từng NV để dựng biểu thuế
   (`Income Tax Slab` đang có 0 record, và chưa có field lưu số người phụ thuộc).
5. **Nguồn số liệu giờ OT** — lấy từ module Overtime Registration sẵn có hay nhập tay?

---

## 5b. ✅ ĐÃ TEST THẬT — TIQN-0148 kỳ 26/06→25/07/2026 khớp 14/14 dòng

Đã dựng Salary Structure `TIQN - TEST TIQN-0148`, gán SSA, sinh Salary Slip nháp trên ERP.
Kết quả **trùng khít phiếu lương thật từng đồng**: Basic 16,551,924 · OT 1,416,462 ·
PC chức vụ 1,200,000 · PC điện thoại 200,000 · Hỗ trợ cơm 50,000 · BHXH 1,473,120 ·
BHYT 276,210 · BHTN 184,140 · Công đoàn 38,948 · TNCN 15,923 · ngày công 26/25 ·
tổng khấu trừ 1,988,341 · **thực lĩnh 17,430,045**.

### 5b.1. 🔴 GOTCHA — Holiday List: HRMS bản này KHÔNG dùng `Employee.holiday_list` nữa

Từ v16.15.0, `get_holiday_list_for_employee()` (`hrms/utils/holiday_list.py`) đọc doctype
**`Holiday List Assignment`** (submittable), không đọc field `Employee.holiday_list`.
Set field cũ **không có tác dụng** với payroll/leave.

⚠ **Nhưng module chấm công custom vẫn đọc field cũ** (`overrides/shift_type/shift_type_optimized.py`
dòng 190/267/699) — và chỉ **376/1038 NV** có set field đó. Tức là đang tồn tại **hai cơ chế
holiday song song, lệch nhau**. Cần thống nhất trước khi chạy payroll thật.

### 5b.2. 🔴 GOTCHA — `condition` được eval ở thời điểm SSA, KHÔNG phải Salary Slip

`SalaryStructureAssignment._evaluate_component_table()` (dòng ~367) có comment rõ:
*"Rows whose condition is falsey are skipped (not added to the slip)"* — dòng bị **loại hẳn**
ngay lúc gán SSA. Salary Slip chỉ nhận các dòng còn sống, rồi **eval lại formula** cho số tiền.

Hệ quả:
- ❌ **KHÔNG** đặt điều kiện phụ thuộc dữ liệu theo tháng (giờ OT, ngày công) vào `condition`
- ✅ Đưa vào **`formula`** dạng biểu thức điều kiện — formula được eval lại ở cấp slip

```python
# ❌ SAI: condition eval lúc SSA (giờ OT = 0) -> dòng bị loại vĩnh viễn
condition: custom_ot_weekend_hours > 4
amount: 50000

# ✅ ĐÚNG: formula eval lại mỗi kỳ lương
amount_based_on_formula: 1
formula: 50000 if custom_ot_weekend_hours > 4 else 0
```

`condition` **vẫn dùng được** cho dữ liệu không đổi theo tháng — ví dụ quy tắc thử việc ở mục 2.5
(`employment_type`) hoàn toàn hợp lệ.

### 5b.3. GOTCHA — custom field dùng trong formula phải có trên CẢ SSA lẫn Salary Slip

`SALARY_SLIP_EVAL_DEFAULTS` (`hrms/payroll/utils.py`) chỉ liệt kê field **chuẩn** của Salary Slip.
Custom field như `custom_ot_weekend_hours` không có trong đó → SSA validate sẽ báo
`NameError: name 'custom_ot_weekend_hours' is not defined`.

→ Khai custom field **cùng tên trên cả 2 doctype**: trên SSA để ẩn/mặc định 0 (chỉ để eval được),
trên Salary Slip là giá trị thật. Salary Slip ghi đè vì `data.update(self.as_dict())` chạy sau.

### 5b.4. Hỗ trợ tiền cơm (7.1)
**Chỉ phát sinh khi OT ngày chủ nhật > 4 giờ** — đúng với cả 6 phiếu mẫu
(chỉ TIQN-0148 có OT cuối tuần 8h nên được 50,000; 5 phiếu còn lại đều = 0).
Đã test 3 mốc: 0h → 0 · 3h → 0 · 8h → 50,000.

> ❓ Chưa rõ: nếu làm OT >4h trong **nhiều** chủ nhật thì được 50,000 mỗi lần hay vẫn một lần?

### 5b.6. ⚙ Override `Salary Slip` — chỉ trừ Chủ Nhật khỏi ngày công

`customize_erpnext/overrides/salary_slip/salary_slip.py` → `CustomSalarySlip`
(đăng ký ở `hooks.py` → `override_doctype_class`).

Override đúng **một** method: `get_holidays_for_employee()` — chỉ trả về dòng có
`weekly_off = 1`, nên `total_working_days` = số ngày trong kỳ − số Chủ Nhật; ngày lễ
nhà nước vẫn nằm trong ngày công (nghỉ có lương).

```python
rows = get_holiday_dates_between(holiday_list, start, end, as_dict=True, select_weekly_off=True)
return [r.holiday_date for r in rows if r.weekly_off]
```

> `get_holiday_dates_between()` của HRMS có sẵn tham số `skip_weekly_offs` nhưng đó là
> **loại bỏ Chủ Nhật** — ngược với thứ cần, nên buộc phải tự lọc.

### 5b.7. 🔴 Hai cơ chế Holiday List đang chạy SONG SONG, lệch nhau

| | Đọc từ đâu | Ảnh hưởng |
|---|---|---|
| **HRMS** (payroll, nghỉ phép) | doctype `Holiday List Assignment` | cấp Company → list `2026` |
| **Chấm công custom** | field cũ `Employee.holiday_list` | chỉ **377/1036 NV** có set |

Chứng cứ trong `customize_erpnext/overrides/shift_type/shift_type_optimized.py`:
- **dòng ~190** — `frappe.get_all("Employee", fields=[..., "holiday_list", ...])`
- **dòng ~267** — `unique_holiday_lists = set(emp.holiday_list for emp in emp_data if emp.holiday_list)`
- **dòng ~699** — `if not emp_data or not emp_data.holiday_list: return False`

→ **659/1036 NV không set field này nên `is_holiday()` luôn trả `False`**: với họ, ngày lễ và
Chủ Nhật đều bị coi là ngày làm việc bình thường. Đây là lý do 30/04, 01/05, 02/05/2026 bị chấm
`Absent` cho 700 người.

**Cần làm trước khi chạy payroll thật:** hoặc sửa module chấm công dùng
`get_holiday_list_for_employee()` (API mới của HRMS), hoặc set `Employee.holiday_list = "2026"`
cho toàn bộ NV. Nếu không, ngày lễ vẫn bị chấm Absent → dù ngày công chuẩn đã đúng, `payment_days`
vẫn bị trừ oan.

### 5b.5. Đối tượng đã tạo trên ERP (dọn được nếu cần)
`Salary Structure: TIQN - TEST TIQN-0148` · `Holiday List: TIQN Sundays 2026 (TEST)` ·
`Holiday List Assignment: HR-HLA-2026-00019` · SSA + Salary Slip nháp của TIQN-0148 ·
custom field `custom_si_base` + `custom_ot_*_hours` trên SSA/Salary Slip.
**Đã tắt `Payroll Settings.email_salary_slip_to_employee`** (mặc định ERPNext là BẬT).

---

## 6. Lưu ý kỹ thuật

- Sau khi sửa Salary Component/Structure: **tạo 1 Salary Slip thử cho TIQN-0148 tháng 07/2026**
  và đối chiếu từng dòng với phiếu thật trước khi chạy Payroll Entry hàng loạt.
- Salary Structure Assignment là **submittable** — gán sai phải cancel + amend, nên kiểm tra kỹ
  `base` trước khi Assign.
- Không bật `variable_based_on_taxable_salary` trên component nào khác ngoài PIT, nếu không
  SSA sẽ bị ép phải có Income Tax Slab.
