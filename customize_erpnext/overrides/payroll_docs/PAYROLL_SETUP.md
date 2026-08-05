# Hướng dẫn setup Payroll TIQN (theo mẫu Payment Slip hiện hành)

Tài liệu dò ngược công thức từ **9 phiếu lương thật** kỳ 07/2026 — dữ liệu gốc lưu ở **mục 7**
(PDF đã xoá khỏi repo). Các phiếu bổ sung cho nhau về cơ cấu (công nhân ↔ quản lý, có/không OT,
đủ loại phụ cấp), nhờ vậy tách bạch được khoản nào vào căn cứ BH và khoản nào chịu thuế.

Kỳ lương: **26 tháng trước → 25 tháng này** (kỳ mẫu = 26/06 → 25/07/2026).

Đã test thật trên ERP: Salary Slip khớp phiếu lương thật **20/20 dòng** trên 2 nhân viên có cơ cấu
lương khác hẳn nhau, dùng **chung một** Salary Structure (mục 5b8.4).

---

## 0. Trạng thái (cập nhật 05/08/2026)

| Hạng mục | Trạng thái |
|---|---|
| Công thức lương dò từ 9 phiếu thật | ✅ kiểm chứng xong (mục 2, 7) |
| Quy chế lương gốc | ✅ trích xuất → [`QUY_CHE_LUONG_2025.md`](QUY_CHE_LUONG_2025.md) |
| Salary Component (cờ prorate / cờ thuế) | ✅ đã cấu hình 23 component (mục 5b8.1) |
| Salary Structure `TIQN - Standard (ALL components)` | ✅ **19 earnings · 4 deductions**, khớp phiếu thật 20/20 (mục 5b8) |
| Holiday List + override ngày công chuẩn | ✅ xong (mục 5b.6, 5b.7) |
| Salary Structure Assignment | ⏳ mới có 2 bản ghi thử; chờ Excel lương của HR |
| Thuế TNCN tự động | ⏳ chờ `Employee Dependent` → [`PLAN_EMPLOYEE_DEPENDENT.md`](PLAN_EMPLOYEE_DEPENDENT.md) |
| Hằng số lương gom vào Settings | ⏳ → [`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md) |
| Sửa Attendance 30/04 · 01/05 · 02/05/2026 (~700 NV bị Absent oan) | 🔴 **chưa làm** |
| Disable 8 component "dòng tổng" + 7 component rác ERPNext | 🔴 **chưa làm** (mục 3.1, 3.5) |
| Dọn Salary Structure `Salary Structure All - TEST` (đang `is_active = Yes`) | 🔴 **chưa làm** |

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

### 2.1. Căn cứ đóng bảo hiểm (`SI_BASE`) — HR ĐÃ XÁC NHẬN danh sách khoản

```
SI_BASE = Lương trên HĐLĐ (Basic salary in labour contract)
        + Phụ cấp kỹ thuật          (Technical allowance)
        + Phụ cấp chức vụ           (Position allowance)
        + Phụ cấp PCCC              (Fire prevention and fighting)
        + Phụ cấp ATVS viên         (Safety and hygiene)
        + Phụ cấp hỗ trợ công đoạn  (Supporting stages)
        + Thưởng chuyên cần         (Attendance incentive)
        + Thưởng trách nhiệm        (Responsibility incentive)

  ❌ KHÔNG gồm: xăng xe · điện thoại · NHÀ Ở · huấn luyện PCCC · KPI · các khoản 7.x
```

Đối chiếu công thức này trên **7 phiếu** (6/7 khớp):

| Phiếu | Công thức tính ra | Căn cứ BH thật | Lệch | |
|---|---:|---:|---:|---|
| TIQN-0148 | 18,414,001 | 18,414,000 | +1 | ✓ |
| TIQN-0019 | 7,757,895 | 7,757,900 | −5 | ✓ |
| TIQN-0047 | 11,720,000 | 11,720,000 | 0 | ✓ |
| TIQN-0002 | 47,652,433 | 47,652,438 | −4 | ✓ |
| TIQN-1405 | 13,900,000 | 13,900,000 | 0 | ✓ |
| TIQN-2087 | 12,000,000 | 12,000,000 | 0 | ✓ |
| **TIQN-0006** | 28,165,135 | **28,939,100** | **−773,965** | ❌ |

Hai phiếu TIQN-1405 / TIQN-2087 bổ sung thêm bằng chứng loại trừ:
**`4.6 Hỗ trợ con nhỏ` cũng KHÔNG vào căn cứ BH** (TIQN-2087 có 20.000 nhưng căn cứ BH
đúng bằng Basic).

> 💡 **Phụ cấp NHÀ Ở không vào căn cứ BH** là mấu chốt — trước khi HR xác nhận, tôi tính nhầm
> nó vào nên TIQN-0002 lệch đúng 5.000.000 (= tiền nhà ở).

**Còn TIQN-0006 lệch −773,965.** Nguyên nhân nằm ở chữ **"trên HĐLĐ"**: căn cứ BH tính theo giá
trị **hợp đồng**, không phải con số hiển thị trên phiếu tháng đó. Với NV này, hoặc lương HĐLĐ là
14,359,469 (thay vì 13,585,504 trên phiếu), hoặc có một phụ cấp thuộc danh sách trên đang ghi 0
trên phiếu nhưng vẫn có trong hợp đồng. → **Cần HR đối chiếu hồ sơ BHXH của TIQN-0006.**

### 2.1b. `custom_si_base` — TỰ TÍNH, cho phép điều chỉnh (ĐÃ TRIỂN KHAI)

Field `custom_si_base` (Currency) trên **`Salary Structure Assignment`** — đúng chỗ, vì SSA gắn
với NV + có `from_date` nên tự có lịch sử khi mức đóng thay đổi.

| Trạng thái | Hành vi |
|---|---|
| Mặc định | **Tự tính** = tổng 8 khoản ở mục 2.1. Field read-only |
| Tick `custom_si_base_override` | Nhập tay theo mức đã đăng ký với BHXH; hệ thống không ghi đè, chỉ **cảnh báo mức lệch** |

Cho phép ghi đè vì mức đăng ký với cơ quan BHXH **có thể lệch** khỏi tổng lương thực tế — đăng ký
chậm sau khi tăng lương, hoặc ca như TIQN-0006. Cảnh báo (ngưỡng 1.000đ) giúp HR phát hiện sớm
thay vì để lệch âm thầm nhiều tháng.

Code: `overrides/salary_structure_assignment/salary_structure_assignment.py` (server, nguồn chuẩn)
+ `public/js/custom_scripts/salary_structure_assignment.js` (tính ngay trên form).

> Đã xác minh: `get_component_eval_context()` nạp **toàn bộ field của SSA** vào context công thức
> (`data.update(ssa_as_dict)` trong `apps/hrms/hrms/payroll/utils.py`) → formula dùng thẳng
> `custom_si_base`.

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

### 2.4b. ✅ CHỐT — nguồn giờ OT là **Attendance** (HR xác nhận 05/08/2026)

Không nhập tay, không lấy từ Overtime Registration. Field đã có sẵn trên Attendance:

| Field | Kiểu | Dùng |
|---|---|---|
| `custom_approved_overtime_duration` | Float | giờ OT đăng ký/duyệt |
| **`custom_final_overtime_duration`** | Float | **giờ OT chốt để trả lương** ← dùng field này |

**Tách 3 loại OT bằng chính Holiday List**, không cần field phân loại riêng — đây là lý do thứ hai
khiến cờ `weekly_off` ở mục 2.2 quan trọng:

| Loại | Điều kiện ngày | Hệ số |
|---|---|---|
| Ngày thường | không có trong Holiday List | 150% |
| Cuối tuần | có trong Holiday List, `weekly_off = 1` | 200% |
| Ngày lễ | có trong Holiday List, `weekly_off = 0` | 300% |

**Đối chiếu thử kỳ 26/06→25/07/2026** (tổng `custom_final_overtime_duration` theo NV):

| NV | Phiếu lương | Attendance | |
|---|---|---|---|
| TIQN-0002 · 0006 · 1405 · 2087 · 2352 | 0 | 0 | ✓ |
| TIQN-0044 | 12h thường | 12.00 thường | ✓ |
| TIQN-0047 | 36.1h thường | 36.10 thường | ✓ |
| **TIQN-0148** | **8h cuối tuần** | **8.00 cuối tuần** | ✓ tách loại đúng |
| TIQN-0019 | 35h thường | **55.00** thường | ✗ lệch 20h |

→ **8/9 khớp**, và ca TIQN-0148 chứng minh cơ chế tách theo `weekly_off` chạy đúng.
Ca TIQN-0019 lệch 20h (chi tiết ngày: 11 ngày × 3h + 8 ngày × 2h + 2 ngày × 3h = 55h) —
**HR xác nhận dữ liệu OT trên Attendance chưa chuẩn, nhưng nguyên tắc vẫn lấy từ nguồn này.**
Việc làm sạch dữ liệu OT là một đợt riêng, không chặn thiết kế.

> ⚠ Lưu ý khi lấy `custom_approved_overtime_duration` nhầm chỗ: TIQN-0047 có approved = 66h
> nhưng final = 36.1h, và **chỉ final mới khớp phiếu lương**.

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

> ✅ **Mục 3.2 → 3.4 đã thực hiện xong ngày 05/08/2026** — xem kết quả ở mục **5b8.1**
> (bảng cờ chuẩn cho 23 component). Giữ lại phần dưới để biết *vì sao* cấu hình như vậy.

Ban đầu 50 component **đã tạo đủ tên** nhưng **chưa cấu hình gì** — tất cả để mặc định
(`depends_on_payment_days = 1`, `is_tax_applicable = 1`, không có formula).

### 3.1. 🔴 CHƯA LÀM — disable các component là DÒNG TỔNG

Kiểm tra 05/08/2026: **cả 8 component dưới đây vẫn `disabled = 0`.**
Chưa gây hại vì không dòng nào được khai trong Salary Structure, nhưng để nguyên thì
**ai đó chọn nhầm là cộng tiền hai lần**. ERPNext tự tính tổng:

| Component | Lý do |
|---|---|
| `3 Monthly Salary (c=a+b)` | tổng trung gian |
| `5 Sub total (f=c+d+e)` | = `gross_pay` |
| `6 Deductions (g)` | = `total_deduction` |
| `9 Net Salary (j=...)` | = `net_pay` |
| `2 Overtime (b)`, `3.1 Allowance (d)`, `4 Incentive (e)`, `7 Others (h)` | tiêu đề nhóm |

→ Giữ lại làm **nhãn nhóm trên mẫu in**, không phải component tính tiền.

### 3.2. ⚠ `statistical_component` — CHỈ cho 1.1 và 1.2, KHÔNG áp cho 2.1/2.2/2.3

`1.1 Standard working days` và `1.2 Actual working days` là **số ngày** → nếu đưa vào Salary
Structure thì phải `statistical_component = 1`. Hiện **không** khai chúng trong structure
(đã có sẵn `total_working_days` / `payment_days` của Salary Slip) nên không cần đụng.

> 🔴 **Đừng áp cho `2.1/2.2/2.3`.** Bản đầu của tài liệu này xếp chúng vào nhóm "số giờ" — **sai**.
> Trong Salary Structure hiện tại, ba dòng đó giữ **SỐ TIỀN tăng ca** (số giờ nằm ở custom field
> `custom_ot_*_hours`). Đặt `statistical_component = 1` sẽ **loại toàn bộ tiền OT khỏi lương**.

### 3.3. 🔴 MỤC NÀY ĐÃ LỖI THỜI — xem `QUY_CHE_LUONG_2025.md` mục B

> Quy chế lương gốc (`TIQN-2025-HR/GA-QĐ-0001`) đã được trích xuất sang
> [`QUY_CHE_LUONG_2025.md`](QUY_CHE_LUONG_2025.md). Văn bản đó cho quy tắc prorate **chính xác
> theo từng khoản**, và **bác bỏ** mô hình "hai tầng / ngày thuộc biên chế" suy đoán dưới đây.
>
> **Quy tắc thật là theo NGƯỠNG NGÀY CÔNG:** phần lớn phụ cấp hưởng nguyên mức, chỉ cắt theo ngày
> công khi **ngày công thực tế < 8** (riêng PC nhà ở: < 14 ngày → **½ tháng**); riêng PC kỹ thuật,
> PC xăng xe, thưởng chuyên cần thì **luôn** theo ngày công thực tế.
>
> Giữ lại phần dưới vì các **bằng chứng đối chiếu từ phiếu lương** vẫn đúng và hữu ích.

### 3.3-bằng-chứng. Ba ca phiếu lương làm chỗ dựa cho quy tắc ngưỡng

*(Mô hình "hai tầng / ngày thuộc biên chế" và ý tưởng field `custom_employed_days` từng ghi ở đây
đã bị quy chế bác bỏ — đã xoá để không ai làm nhầm. Giữ lại bảng bằng chứng vì vẫn dùng để hồi quy.)*

| Ca | Quan sát | Khớp quy tắc ngưỡng |
|---|---|---|
| **TIQN-0006** — đi làm **24/26** | Basic bị cắt (13.585.504 → 12.540.465) nhưng chức vụ **5.000.000**, trách nhiệm **5.000.000** đều tròn số | 24 ≥ 8 ⇒ phụ cấp nguyên mức ✓ |
| **TIQN-0006** — chuyên cần **500.000** | không phải prorate | trúng **bậc "nghỉ 2 lần → 500.000"** của quy chế ✓ |
| **TIQN-2352** — vào giữa kỳ, **2/26** | mọi khoản × 2/26: kỹ thuật 7.692 · xăng xe 23.077 · chuyên cần 76.923 | 2 < 8 ⇒ cắt theo ngày công ✓ |
| **TIQN-0148** — **25/26** | Basic bị cắt; chức vụ 1.200.000 + điện thoại 200.000 tròn số | 25 ≥ 8 ✓ |

### 3.3b. ✅ CHỐT — BH + phí công đoàn bắt đầu SAU KHI KẾT THÚC THỬ VIỆC

HR xác nhận: cả BHXH/BHYT/BHTN **và phí công đoàn** đều bắt đầu từ **sau khi hết thử việc**.

→ **Không cần điều kiện riêng cho "nhân viên mới"** như tài liệu này từng phỏng đoán. Chỉ có
**một** điều kiện duy nhất, dùng lại `employment_type` ở mục 2.5:

| Dòng | `condition` |
|---|---|
| `6.1/6.2/6.3` BHXH·BHYT·BHTN | `employment_type not in PROBATION` |
| `6.4` Phí công đoàn | `employment_type not in PROBATION` ← **bổ sung** |
| `7.6` hoàn 21.5% | `employment_type in PROBATION` |

Kiểm chứng: **TIQN-2352** đang thử việc → toàn bộ 6.x = 0, **kể cả phí công đoàn 38,948**. ✓
8 NV còn lại đã chính thức → đều đóng đủ. ✓

> ⚠ Ràng buộc vận hành nhắc lại: `Employee.employment_type` do module Labor Contract đồng bộ.
> Hợp đồng chính thức **đánh dấu `Signed` trễ** ⇒ NV vẫn bị coi là thử việc ⇒ **không trừ bảo hiểm
> và không trừ phí công đoàn** trong kỳ đó.

### 3.4. 🔴 Thuế TNCN — KHÔNG bật `variable_based_on_taxable_salary`

> Bản đầu tài liệu này khuyên bật cờ đó để ERPNext tự tính theo `Income Tax Slab`. **Đã bác bỏ.**

HRMS tính thuế theo mô hình **thu nhập cả năm** rồi chia cho số kỳ còn lại (mô hình Ấn Độ).
Việt Nam khấu trừ theo **biểu luỹ tiến THÁNG**. Bật cờ đó sẽ ra **số khác phiếu lương thật**.
→ Tự tính trong hook `apply_regional_deductions`, xem
[`PLAN_EMPLOYEE_DEPENDENT.md`](PLAN_EMPLOYEE_DEPENDENT.md) mục 5.2.

`is_tax_applicable` chỉ có nghĩa với **Earning** → đã tắt trên toàn bộ Deduction (mục 5b8.1).

### 3.5. 🔴 CHƯA LÀM — 7 component rác của ERPNext mặc định
`Arrear` · `Basic` · `House Rent Allowance` · `Income Tax` · `Leave Encashment` ·
`Professional Tax` · `Provident Fund` → disable để khỏi chọn nhầm.
Kiểm tra 05/08/2026: **cả 7 vẫn `disabled = 0`.**

> ⚠ `Basic` và `Income Tax` đặc biệt dễ nhầm với `1 Basic Salary` và `6.5 PIT` của TIQN.

---

## 4. Thứ tự setup — trạng thái

| Bước | Việc | Trạng thái |
|:--:|---|---|
| 1 | Cấu hình Salary Component (cờ prorate, cờ thuế, dòng tổng) | ✅ xong — mục 5b8.1 |
| 2 | `Payroll Period` | ✅ có 1 record. **`Income Tax Slab` KHÔNG dùng** — xem mục 3.4 |
| 3 | Salary Structure | ✅ **một** structure `TIQN - Standard (ALL components)` dùng chung cho mọi cơ cấu lương — mục 5b8 |
| 4 | Salary Structure Assignment | ⏳ chờ Excel lương HR — cách import ở dưới |
| 5 | Nguồn ngày công thực tế | ✅ Attendance + override ngày công chuẩn (mục 5b.6); còn nợ sửa dữ liệu 30/04–02/05 |

> ❌ **Bỏ ý tưởng cũ "16 Salary Structure theo top-15 chức danh".** Đã chứng minh **một** structure
> phủ được mọi cơ cấu lương: giá trị khác nhau nằm ở SSA từng người, dòng có giá trị 0 tự ẩn nhờ
> `remove_if_zero_valued`. Test: TIQN-0148 ra 11 dòng, TIQN-0019 ra 9 dòng — cùng một structure.

### Bước 4 — cách tạo Salary Structure Assignment hàng loạt

🔴 **`Bulk Salary Structure Assignment` của HRMS KHÔNG đủ.** Grid của nó chỉ sửa được **2 cột**
`base` và `variable`; SSA của TIQN cần thêm **11 field phụ cấp** (`custom_technical_allowance`,
`custom_position_allowance`, …) ⇒ dùng tool đó sẽ tạo SSA với toàn bộ phụ cấp = 0.

→ **Dùng Data Import** (nhận mọi cột custom, có `submit_after_import`).

⚠ Phải **tắt `site_config.developer_mode`** trước: `data_import.py:123` có
`run_now = frappe.in_test or frappe.conf.developer_mode` ⇒ import chạy inline và treo với 1036 dòng.

> SSA **không phải việc hàng tháng** — quy chế ghi *"xem xét lương hằng năm vào tháng Tư"*.
> Import một lần, sau đó sửa lẻ; mỗi tháng 4 import lại. Không cần viết tool riêng.
>
> Giá trị **biến động theo tháng** (giờ OT, KPI, số ngày làm ca) nhập trên **Salary Slip**, không
> phải SSA — đã xác minh `salary_slip.py:1286` (`data.update(self.as_dict())` chạy **sau** khi nạp
> SSA nên giá trị trên phiếu ghi đè).

---

## 5. Câu hỏi cho HR — đã trả lời gì, còn nợ gì

Đã chốt: ngày công chuẩn · quy tắc thử việc 21.5% · phí công đoàn · cách prorate lương ·
**căn cứ BH tính được từ 8 khoản** (mục 2.1, khớp 7/8 phiếu) — không còn phải import cột riêng,
chỉ cần cho phép ghi đè khi mức đăng ký với BHXH lệch (mục 2.1b).

**HR đã trả lời ngày 05/08/2026:**

| Câu hỏi | Trả lời | Ghi ở mục |
|---|---|---|
| Chức vụ / nhà ở / trách nhiệm có prorate theo ngày công? | **Không** → dẫn tới quy tắc **ngưỡng ngày công** trong quy chế | 3.3 |
| BH + phí công đoàn bắt đầu khi nào? | **Sau khi kết thúc thử việc** | 3.3b |
| Nguồn giờ OT? | **Từ Attendance** (dữ liệu chưa chuẩn nhưng nguyên tắc là nguồn này) | 2.4b |
| Định nghĩa thu nhập chịu thuế? | **Cứ theo luật** → luật mới miễn **toàn bộ** tiền OT ⇒ khớp phiếu; nhưng phát sinh **trần giờ OT** | 5d.2b |
| Số NPT của TIQN-0002 / TIQN-0044? | **"Họ có nhiều NPT, không có con số cụ thể"** | dưới đây |
| TIQN-0006 lệch căn cứ BH −773.965? | **Để sau** | 7.2 |

**Còn lại — chặn việc chạy kỳ lương thật:**

1. 🔴 **Lương HĐLĐ + phụ cấp cố định của ~1038 NV** — lấy từ Excel của HR. Đây là dữ liệu
   **bắt buộc**, không suy ra được từ đâu; căn cứ BH sẽ tự tính từ các cột này.
2. 🔴 **Số NPT thực tế của từng NV** — HR xác nhận TIQN-0002/0044 "có nhiều NPT" nhưng không có
   con số. Nghĩa là **không thể kiểm chứng PIT ngược từ 2 phiếu này**, và cũng nghĩa là dữ liệu NPT
   **chưa tồn tại ở dạng có thể tính toán được** → bắt buộc phải thu thập qua doctype
   `Employee Dependent` ([plan](PLAN_EMPLOYEE_DEPENDENT.md)) trước khi bật PIT tự động.
3. 🔴 **Làm sạch MST** — 28% độ phủ, 18 cặp MST trùng giữa 2 nhân viên khác nhau, 16 ô ghi chữ
   ([plan](PLAN_EMPLOYEE_DEPENDENT.md) mục 6.1).
4. ⚠ **Khoản nào nhận phần giờ OT vượt trần** — HR xác nhận có chuyển sang "một loại lương khác";
   nghi là dòng `4.3 KPI` (lệch 0,05%). Cần xác nhận đích danh (mục 5d.2b).

**Đã đóng:** trần OT (**4h/ngày · 40h/tháng · 300h/năm**) · **không có làm việc ban đêm**
(kiểm chứng bằng dữ liệu quẹt thẻ 2026) · **không cần cơ chế luỹ kế OT theo năm để tính thuế**
(mục 5d.2b) · **mô hình prorate phụ cấp** — nay có văn bản gốc, xem
[`QUY_CHE_LUONG_2025.md`](QUY_CHE_LUONG_2025.md) mục B.

---

## 5b. Các GOTCHA phát hiện khi dựng Salary Structure

> Lần test đầu (structure thử `TIQN - TEST TIQN-0148`) khớp 14/14 dòng và **thực lĩnh 17.430.045**
> đúng phiếu thật. Structure thử đó **đã xoá**; kết quả cuối cùng trên structure chính thức là
> **20/20 dòng trên 2 nhân viên** — xem mục **5b8.4**.
>
> Phần dưới giữ lại vì các **gotcha kỹ thuật** vẫn còn nguyên giá trị.

### 5b.1. 🔴 GOTCHA — Holiday List: HRMS bản này KHÔNG dùng `Employee.holiday_list` nữa

Từ v16.15.0, `get_holiday_list_for_employee()` (`hrms/utils/holiday_list.py`) đọc doctype
**`Holiday List Assignment`** (submittable), không đọc field `Employee.holiday_list`.
Set field cũ **không có tác dụng** với payroll/leave.

> ✅ **ĐÃ XỬ LÝ.** `shift_type_optimized.py` đã chuyển sang `get_assigned_holiday_list()` cấp
> company, và `Employee.holiday_list` đã xoá sạch (**0 bản ghi**). Chi tiết ở mục 5b.7.

### 5b.2. 🔴 GOTCHA — `condition` được eval ở thời điểm SSA, KHÔNG phải Salary Slip

`SalaryStructureAssignment._evaluate_component_table()` (dòng ~367):
*"Rows whose condition is falsey are skipped (not added to the slip)"*.

⚠ **Chính xác hơn:** không phải "đóng băng lúc gán SSA". `get_evaluated_components()` được gọi
**mỗi lần lập phiếu** (`salary_slip.py:1184`), **không cache**, và context nạp `Employee` bằng
`frappe.get_cached_doc` ⇒ dữ liệu **Employee luôn là hiện tại**.

Cái bị đóng băng là **dữ liệu theo tháng**: lúc eval, `payment_days = total_working_days` và các
custom field lấy từ **SSA** (thường = 0), **không** phải giá trị trên phiếu.

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

`condition` **vẫn dùng được** cho field của **Employee** — ví dụ quy tắc thử việc ở mục 2.5
(`employment_type`).

✅ **Đã kiểm chứng thực nghiệm (05/08/2026)** trên TIQN-0148, cùng một SSA:

| `employment_type` | Khấu trừ trên phiếu | Dòng 7.6 |
|---|---|---|
| Chính thức | 6.1 · 6.2 · 6.3 · 6.4 | không có |
| Đổi sang thử việc | **rỗng** | **3.959.010** = 18.414.001 × 21,5% |

⇒ NV chuyển từ thử việc sang chính thức thì kỳ lương sau **tự** bắt đầu trừ bảo hiểm,
không phải tạo lại SSA.

### 5b.3. GOTCHA — custom field dùng trong formula phải có trên CẢ SSA lẫn Salary Slip

`SALARY_SLIP_EVAL_DEFAULTS` (`hrms/payroll/utils.py`) chỉ liệt kê field **chuẩn** của Salary Slip.
Custom field như `custom_ot_weekend_hours` không có trong đó → SSA validate sẽ báo
`NameError: name 'custom_ot_weekend_hours' is not defined`.

→ Khai custom field **cùng tên trên cả 2 doctype**: trên SSA để ẩn/mặc định 0 (chỉ để eval được),
trên Salary Slip là giá trị thật. Salary Slip ghi đè vì `data.update(self.as_dict())` chạy sau.

### 5b.4. Hỗ trợ tiền cơm (7.1)
**Chỉ phát sinh khi OT ngày chủ nhật > 4 giờ** — đúng với cả **9 phiếu mẫu**
(chỉ TIQN-0148 có OT cuối tuần 8h nên được 50.000; 8 phiếu còn lại đều = 0).
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

### 5b.7. ✅ ĐÃ XỬ LÝ — hai cơ chế Holiday List từng chạy song song

**Vấn đề cũ:** HRMS đọc `Holiday List Assignment`, còn module chấm công custom đọc field cũ
`Employee.holiday_list` mà chỉ 377/1036 NV có set ⇒ 659 NV luôn `is_holiday() = False`,
ngày lễ và Chủ Nhật bị coi là ngày làm việc.

**Đã sửa** (commit `3d86851`):
- `overrides/shift_type/shift_type_optimized.py` dùng `get_assigned_holiday_list(company, as_on=…)`
  — nạp holiday **theo company**, không theo từng NV
- Xoá sạch `Employee.holiday_list` → **0 bản ghi**
- Bỏ hook `set_default_holiday_list` khỏi `Employee.after_insert`

**Hiện trạng đã kiểm tra (05/08/2026):** `Holiday List Assignment` cấp Company đủ **2021–2026**;
list `2026` có **52 Chủ Nhật** (`weekly_off = 1`) + **15 ngày lễ**, gồm cả ngày nghỉ bù Tết.

> 🔴 **Còn nợ — dữ liệu lịch sử:** Attendance ngày **30/04, 01/05, 02/05/2026** vẫn đang `Absent`
> cho ~700 NV (hậu quả của bug cũ). Không sửa thì `payment_days` bị trừ oan 3 ngày.
> Đây là việc **sửa dữ liệu**, độc lập với code đã fix.

### 5b.5. Đối tượng thử nghiệm — đã dọn

`Salary Structure: TIQN - TEST TIQN-0148` và `Holiday List: TIQN Sundays 2026 (TEST)`
**đã xoá**.

🔴 **Còn 2 Salary Structure đang `is_active = Yes`:**

| Structure | Xử lý |
|---|---|
| `TIQN - Standard (ALL components)` | ✅ dùng chính thức |
| `Salary Structure All - TEST` | 🔴 **chưa dọn** — 16 dòng có shape *bảng tính lương* (Overtime, Monthly Salary c=a+b, Net Salary), không phải điều khoản lương. Nên `is_active = No` để khỏi gán nhầm |

Còn giữ: 2 SSA thử của TIQN-0148 / TIQN-0019 (dùng để hồi quy), custom field trên SSA + Salary Slip.

> ⚙ **Đã tắt `Payroll Settings.email_salary_slip_to_employee`** (mặc định ERPNext là BẬT).
> Đây là rule dự án: không tự động gửi mail cho NLĐ.

---

## 5b8. ✅ ĐÃ SỬA XONG Salary Structure `TIQN - Standard (ALL components)` (05/08/2026)

Structure được **dựng lại từ đầu** theo quy chế lương gốc. Kết quả: **22 earnings + 5 deductions**.

> ⚠ Vì sao phải dựng lại chứ không sửa tại chỗ: trên Salary Detail chỉ `formula` và `condition` có
> `allow_on_submit = 1`. `depends_on_payment_days`, `is_tax_applicable` và **việc thêm dòng mới**
> đều không sửa được sau khi submit. Tại thời điểm sửa có **0 Salary Slip, 0 Payroll Entry** nên
> huỷ + tạo lại là an toàn (2 SSA thử nghiệm đã được tạo lại y nguyên).

### Đã sửa

| Nhóm | Nội dung |
|---|---|
| **Thiếu dòng chi trả** | Thêm `3.7 PCCC`, `3.8 ATVS`, `3.9 hỗ trợ công đoạn` — 3 khoản này nằm trong `custom_si_base` nên trước đó NLĐ **đóng BH trên tiền không được trả** |
| **Điều kiện thử việc** | `6.1/6.2/6.3/6.4` thêm `condition: employment_type not in [...]`; thêm dòng `7.6 = custom_si_base * 0.215` với điều kiện ngược lại |
| **Prorate** | `3.2 kỹ thuật`, `3.5 xăng xe`, `4.1 chuyên cần` → `depends_on_payment_days = 1`. `3.3 chức vụ`, `3.7`, `3.8` → nhánh **< 8 ngày**. `3.4 nhà ở` → nhánh **< 14 ngày = ½ tháng**. `3.9`, `4.2` → nhánh thử việc |
| **Cờ thuế** | 3 dòng OT + `7.1 tiền cơm` + `3.5 xăng xe` + `3.6 điện thoại` → `is_tax_applicable = 0` (miễn thuế theo mục 5d.2b) |
| **Component mới** | `4.3 KPI`, `4.5 hỗ trợ làm ca`, `4.6 hỗ trợ con nhỏ`, `7.2 quà cưới`, `7.4 thanh toán phép năm`, `7.5 phụ cấp kinh nguyệt` |

### Custom field mới

| Field | Kiểu | Trên |
|---|---|---|
| `custom_kpi_incentive` · `custom_children_support` · `custom_marriage_gift` · `custom_annual_leave_payment` · `custom_menstrual_allowance` | Currency | **SSA + Salary Slip** |
| `custom_shift_days` | Float | **SSA + Salary Slip** |
| ~~`custom_pit`~~ | Currency | 🔴 **đã xoá khỏi cả 2 doctype** — PIT chuyển sang `Additional Salary`, xem mục 5b8.2 |

> Quy tắc: field dùng trong formula **bắt buộc có trên SSA** (không thì SSA validate `NameError`);
> có thêm trên **Salary Slip** thì giá trị nhập theo tháng sẽ **ghi đè** SSA — đã xác minh ở
> `salary_slip.py:1286` (`data.update(self.as_dict())` chạy **sau** khi nạp SSA).
> → **SSA giữ giá trị ổn định · Salary Slip giữ giá trị theo tháng.**

### Kiểm chứng sau khi sửa

**Đối chiếu phiếu lương thật kỳ 26/06→25/07/2026 — khớp 20/20 dòng:**

| | TIQN-0148 | TIQN-0019 |
|---|---:|---:|
| Lương cơ bản | 16.551.924 ✓ | 5.859.095 ✓ |
| Tăng ca | 1.416.462 ✓ | 1.958.123 ✓ |
| Phụ cấp | chức vụ 1.200.000 ✓ · điện thoại 200.000 ✓ | kỹ thuật 898.800 ✓ · xăng xe 300.000 ✓ · chuyên cần 1.000.000 ✓ |
| Hỗ trợ cơm | 50.000 ✓ | – |
| BHXH/BHYT/BHTN | 1.473.120 · 276.210 · 184.140 ✓ | 620.632 · 116.368 · 77.579 ✓ |
| Công đoàn · TNCN | 38.948 ✓ · 15.923 ✓ | 38.948 ✓ |
| **Net** | **17.430.045** = đúng phiếu | 9.162.491 |

> TIQN-0019 lệch **1.119.464** so với phiếu — **đúng bằng dòng `4.3 KPI`** chưa nhập, tức phần giờ
> OT vượt trần đã bàn ở mục 5d.2b. Không phải lỗi công thức.

**Test 5 kịch bản nhánh mới — đều đúng:**

| Kịch bản | Kết quả |
|---|---|
| Đủ ngày công, chính thức | mọi phụ cấp nguyên mức, trừ đủ BH |
| **Ngày công 5/26** (< 8) | PCCC 148.462 · ATVS 3.846 · hỗ trợ công đoạn 96.154 (= × 5/26) · nhà ở ½ |
| **Ngày công 12/26** (< 14, ≥ 8) | chức vụ/PCCC/ATVS **nguyên mức** · nhà ở **½ = 2.000.000** |
| **Đang thử việc** | **không** trừ BHXH/BHYT/BHTN **lẫn phí công đoàn** · `7.6` = si_base × 21,5% |
| Khoản theo tháng | KPI · hỗ trợ làm ca (si_base × ngày ca × 20% / ngày chuẩn) · con nhỏ · quà cưới · phép năm · kinh nguyệt |

### 5b8.1. 🔴 GOTCHA — cờ `depends_on_payment_days` / `is_tax_applicable` KHÔNG đặt ở Salary Structure

`SalaryStructure.set_missing_values()` (`salary_structure.py:57`) **luôn ghi đè** 4 cờ này từ
Salary Component mỗi lần save, bất kể giá trị đặt trên dòng:

```python
overwritten_fields = ["depends_on_payment_days", "variable_based_on_taxable_salary",
                      "is_tax_applicable", "is_flexible_benefit"]
...
if d.get(fieldname) != value:
    d.set(fieldname, value)      # gia tri tren dong bi vut di
```

→ **Phải đặt ở `Salary Component`.** Đặt ở dòng structure là công cốc — và **im lặng**, không báo lỗi.
Đây là bẫy đã dính một lần: lần sửa đầu tôi set trên dòng, test TIQN-0148 vẫn ra 20/20 vì kỳ đó
không có ai nghỉ đủ nhiều để lộ sai lệch prorate.

**Bảng cờ chuẩn (đã áp dụng ở cấp Component):**

| Component | `dep_days` | `is_tax_applicable` |
|---|:---:|:---:|
| 1 Basic Salary | 1 | 1 |
| 2.1 / 2.2 / 2.3 OT | 0 | **0** |
| 3.2 Kỹ thuật · 3.5 Xăng xe · 4.1 Chuyên cần | **1** | 1 / **0** / 1 |
| 3.3 Chức vụ · 3.4 Nhà ở · 3.7 PCCC · 3.8 ATVS · 3.9 Công đoạn | 0 | 1 |
| 3.6 Điện thoại · 7.1 Tiền cơm | 0 | **0** |
| 4.2 Trách nhiệm · 4.3 KPI · 4.5 Hỗ trợ ca · 4.6 Con nhỏ · 7.6 21,5% | 0 | 1 |
| 6.1–6.4 (khấu trừ) | 0 | 0 |

### 5b8.2. ✅ Khoản PHÁT SINH → dùng `Additional Salary`, KHÔNG khai trong Salary Structure

Các khoản không trả đều hằng tháng cho mọi người thì **không** thuộc Salary Structure.
ERPNext có sẵn doctype `Additional Salary` đúng cho việc này: submittable · gắn `payroll_date` ·
gắn đúng Salary Component · có `is_recurring` + from/to date · Salary Slip **tự nhặt** vào
(`get_additional_salaries`), kể cả khi component **không** có trong Salary Structure.

**Đã chuyển sang Additional Salary** (đã bỏ khỏi structure, đã xoá custom field tương ứng):

| Component | Khi nào |
|---|---|
| `7.2 Quà kết hôn` | phát sinh, 1.000.000 lần cưới đầu |
| `7.4 Thanh toán phép năm` | cuối năm hoặc khi thôi việc |
| `7.5 Phụ cấp kinh nguyệt` | 1 lần/năm, cùng lương tháng 12 |
| `6.5 PIT/Thuế TNCN` | chỉ NLĐ vượt ngưỡng — 7/9 phiếu mẫu = 0 |
| `7.3 Quyết toán thuế` · `6.6 Bồi thường HĐ` · `3.10 Huấn luyện PCCC` · `4.4 Hỗ trợ nhà in` · `4.7 Hỗ trợ xăng xe` | phát sinh |

> 🔴 **GOTCHA đi kèm:** Additional Salary **vẫn áp** `depends_on_payment_days` của Salary Component.
> Quà cưới 1.000.000 cho NV đi làm 25/26 ngày ra **961.538**. → mọi component dùng qua
> Additional Salary phải để `depends_on_payment_days = 0` (đã set cho cả 9 component trên).

### 5b8.3. Bố cục form Salary Structure Assignment

Sắp lại bằng Property Setter `field_order` (Frappe dùng verbatim khi danh sách phủ đủ mọi field —
`meta.py: sort_fields`, nhánh *"all fields match, best case scenario"*).

| Cột | Nội dung | Ý nghĩa |
|---|---|---|
| 1 | `base` · `custom_si_base_override` · `custom_si_base` | Lương HĐLĐ và căn cứ đóng BH |
| 2 | kỹ thuật · chức vụ · PCCC · ATVS · hỗ trợ công đoạn · chuyên cần · trách nhiệm | **7 khoản TÍNH VÀO** căn cứ BH (cùng `base` thành `custom_si_base`) |
| 3 | nhà ở · xăng xe · điện thoại · con nhỏ · số ngày làm ca · KPI | **KHÔNG** tính vào căn cứ BH |
| 4 | `variable` · `annual_gross_earning` · `ctc` · `leave_encashment_amount_per_day` | Trường chuẩn ERPNext, không dùng |

Section cuối *"OT Hours / Số giờ tăng ca"* (thu gọn được) chứa 3 field giờ OT — chúng chỉ có mặt
để công thức chạy được lúc lưu Assignment, **giá trị thật nhập trên Salary Slip**.

### 5b8.4. Kết quả cuối — **19 earnings · 4 deductions**

Chạy lại Salary Slip TIQN-0148 kỳ 26/06→25/07/2026 sau toàn bộ thay đổi: **0 dòng lệch**.
`net_pay = 17.445.968` = đúng phiếu thật `17.430.045` **+ 15.923 PIT** (nay tách sang
Additional Salary nên không còn trừ trong structure).

### 🔴 Còn nợ: PIT vẫn là số nhập tay

`6.5 PIT` nay nhập qua **Additional Salary** cho từng NLĐ có phát sinh thuế (field `custom_pit`
đã xoá khỏi cả SSA lẫn Salary Slip). Cách này đúng ở chỗ **chỉ tạo bản ghi cho người thực sự nộp
thuế**, có docstatus + `payroll_date` để truy vết.

Nhưng vẫn là **giải pháp tạm**: số tiền do người dùng tự tính. Muốn tự động cần **2** thứ:
`Employee Dependent` ([plan](PLAN_EMPLOYEE_DEPENDENT.md)) và `TIQN Payroll Settings`
([plan](PLAN_PAYROLL_SETTINGS.md)). **Không** cần `Income Tax Slab` — xem mục 3.4.
Công thức luỹ tiến đã kiểm chứng đúng đến từng đồng (mục 5d.1), chỉ chờ hạ tầng dữ liệu.

---

## 5c. ❌ Phương án đã cân nhắc và LOẠI: import bảng lương final từ Excel

**Ý tưởng:** HR vẫn tính lương trên Excel, ERPNext chỉ chứa và in con số cuối cùng
(Salary Structure rỗng, import thẳng dòng `earnings`/`deductions` vào Salary Slip).

Đã xác minh ERPNext **hỗ trợ được**: `validate()` không nạp đè khi `earnings` đã có dòng;
`get_amount_based_on_payment_days()` giữ nguyên `amount` khi `default_amount` rỗng;
tổng vẫn tự tính. Ràng buộc: `salary_structure` là `reqd`, vẫn phải có SSA cho từng NV,
và Data Import **không pivot** được dạng rộng (1 cột = 1 component) nên phải viết importer riêng.

### 🔴 KHÔNG chọn hướng này

Structure đã dựng xong và **khớp phiếu thật 20/20 dòng** (mục 5b8), phủ được cả ca đơn giản lẫn
ca nhiều phụ cấp. Lý do ban đầu để cân nhắc import — *"sợ không mô hình hoá nổi"* — đã bị bác bỏ
bằng kết quả thật.

| Nếu import | |
|---|---|
| ❌ | ERPNext không còn là nguồn tính lương — sai ở Excel là sai vào hệ thống |
| ❌ | Không giảm việc cho HR: mỗi kỳ vẫn phải làm Excel thủ công |
| ❌ | Khó truy vết *"vì sao ra số này"* |

> Ghi lại ở đây để **không phải khảo sát lại**. Nếu sau này gặp nhóm khoản quá phức tạp để mô hình
> hoá, có thể dùng `Additional Salary` cho riêng nhóm đó — không cần quay lại phương án import.

## 5d. Thuế TNCN (PIT) — công thức ĐÃ XÁC MINH, còn vướng người phụ thuộc

Tham khảo: [`mrhuychien/erpnextvn`](https://github.com/mrhuychien/erpnextvn/tree/claude/erpnext-vietnam-localization-fgwuC/erpnextvn/payroll)
— 3 file `pit_calculator.py`, `insurance_calculator.py`, `utils.py`.

### 5d.1. ✅ Công thức PIT khớp phiếu thật đến từng đồng

Biểu thuế 7 bậc luỹ tiến, phương pháp **giảm trừ nhanh**:

| Bậc | Thu nhập tính thuế/tháng | Thuế suất | Giảm trừ nhanh |
|---:|---:|---:|---:|
| 1 | ≤ 5.000.000 | 5% | 0 |
| 2 | ≤ 10.000.000 | 10% | 250.000 |
| 3 | ≤ 18.000.000 | 15% | 750.000 |
| 4 | ≤ 32.000.000 | 20% | 1.650.000 |
| 5 | ≤ 52.000.000 | 25% | 3.250.000 |
| 6 | ≤ 80.000.000 | 30% | 5.850.000 |
| 7 | > 80.000.000 | 35% | 9.850.000 |

```
Thu nhập tính thuế = Thu nhập chịu thuế − BH nhân viên đóng
                     − Giảm trừ bản thân − (số NPT × giảm trừ NPT)
Thuế = Thu nhập tính thuế × thuế suất − giảm trừ nhanh
```

**Kiểm chứng với TIQN-0148** (phiếu thật PIT = 15.923):
```
(16.551.924 Basic + 1.200.000 PC chức vụ − 1.933.470 BH − 15.500.000) × 5% = 15.922,7 → 15.923 ✓
```

Hai điều được xác nhận từ phép thử này:
- **Giảm trừ bản thân = 15.500.000** (Nghị quyết 110/2025/UBTVQH15, áp dụng từ kỳ tính thuế 2026)
  — không phải mức cũ 11.000.000. Giảm trừ NPT tương ứng **6.200.000**.
- **TIQN-0148 có 0 người phụ thuộc.**

### 5d.2. Thu nhập CHỊU THUẾ — mô hình nhất quán với cả 7 phiếu

Giả thuyết: **Thu nhập chịu thuế = Basic (đã prorate) + PC chức vụ**
(không gồm OT · điện thoại · xăng xe · tiền cơm · hỗ trợ con nhỏ · các khoản 7.x).

Đối chiếu toàn bộ 7 phiếu, giả định **0 người phụ thuộc**:

| Phiếu | TN chịu thuế | BH đóng | TN tính thuế | PIT tính ra | PIT thật | |
|---|---:|---:|---:|---:|---:|---|
| TIQN-0148 | 17.751.924 | 1.933.470 | 318.454 | **15.923** | **15.923** | ✓ |
| TIQN-0019 | 5.859.095 | 814.579 | âm | 0 | 0 | ✓ |
| TIQN-0047 | 8.500.000 | 1.175.379 | âm | 0 | 0 | ✓ |
| TIQN-0006 | 17.540.465 | 3.038.606 | âm | 0 | 0 | ✓ |
| TIQN-1405 | 13.900.000 | 1.459.500 | âm | 0 | 0 | ✓ |
| TIQN-2087 | 12.000.000 | 1.260.000 | âm | 0 | 0 | ✓ |
| **TIQN-0002** | 41.880.433 | 5.003.505 | 21.376.928 | 2.625.386 | **0** | ⚠ |

**6/7 khớp.** Riêng TIQN-0002 chỉ ra 0 khi NV này có **≥ 4 người phụ thuộc**
(4 × 6.200.000 = 24.800.000 > 21.376.928) → cần HR xác nhận số NPT đã đăng ký.

> 💡 **Vì sao gần như mọi phiếu đều PIT = 0:** giảm trừ bản thân **15.500.000** đã cao hơn
> thu nhập chịu thuế của phần lớn công nhân. Chỉ nhóm lương cao và ít NPT mới phát sinh thuế.
> Đây là kiểm chứng gián tiếp mạnh cho cả mức giảm trừ lẫn định nghĩa thu nhập chịu thuế.

⚠ **Vẫn còn điểm chưa phân định:** 6 phiếu cho PIT = 0 sẽ **vẫn = 0** dù có tính thêm
điện thoại/xăng xe/tiền cơm vào thu nhập chịu thuế (vì vẫn dưới ngưỡng giảm trừ). Nên bằng chứng
loại trừ các khoản đó **chỉ đến từ TIQN-0148**. Muốn chắc chắn cần phiếu của NV **lương cao,
ít NPT, có OT và nhiều phụ cấp**.

> ✅ Riêng khoản **OT thì đã hết nghi vấn**: luật miễn toàn bộ (mục 5d.2b), không cần thêm bằng
> chứng từ phiếu. Ba khoản còn phải dựa vào TIQN-0148 là **điện thoại · xăng xe · tiền cơm** —
> cả ba đều thuộc diện miễn theo luật, nên rủi ro thấp.

Trong ERPNext việc này chỉ là bật/tắt cờ `Salary Component.is_tax_applicable` trên từng khoản —
không phải sửa code, nhưng đặt sai là sai thuế toàn nhà máy.

### 5d.2b. ✅ HR CHỐT: "cứ theo luật" — luật MỚI (2025/2026) miễn TOÀN BỘ tiền OT

> 🔄 **Mục này đã viết lại 05/08/2026.** Bản cũ áp Thông tư 111/2013/TT-BTC (chỉ miễn **phần
> trả cao hơn** đơn giá giờ thường) và kết luận phiếu lương TIQN đang tính sai — **kết luận đó sai**.
> Quy định hiện hành là **Điều 4 Luật Thuế TNCN 2025** + **Điều 26 Nghị định 253/2026/NĐ-CP**:
> miễn **toàn bộ** tiền lương làm thêm giờ / làm ban đêm, không còn tách phần chênh lệch.

**✅ Không còn mâu thuẫn.** Phiếu lương TIQN loại trừ toàn bộ OT khỏi thu nhập chịu thuế —
đúng luật. PIT của TIQN-0148 giữ nguyên **15.923**, mô hình ở mục 5d.2 vẫn đứng.

#### Khoản MIỄN thuế

| Khoản | Căn cứ | Khớp phiếu? |
|---|---|---|
| **Toàn bộ tiền lương làm thêm giờ / làm ban đêm** — trong phạm vi pháp luật lao động cho phép | Điều 4 Luật TNCN 2025 · Đ.26 NĐ 253/2026 | ✅ |
| PC điện thoại, xăng xe — trong mức khoán tại quy chế | khoán chi | ✅ |
| Tiền ăn giữa ca ≤ **730.000đ/tháng** (chi bằng tiền) | | ✅ (phiếu 50.000) |

#### Khoản CHỊU thuế
Bản chất tiền lương, không thuộc danh mục miễn: PC chức vụ · kỹ thuật · nhà ở · PCCC · ATVS ·
hỗ trợ công đoạn · thưởng chuyên cần · trách nhiệm · KPI · hỗ trợ con nhỏ · khoản hoàn 21.5% (7.6).

**Được TRỪ:** BHXH/BHYT/BHTN bắt buộc · giảm trừ bản thân + NPT.
**KHÔNG được trừ:** 🔴 **đoàn phí công đoàn (6.4)** — là khoản khấu trừ vào lương nhưng
không phải khoản giảm trừ thuế.

#### 🔴 Điều kiện kèm theo: OT VƯỢT ĐỊNH MỨC thì phần vượt BẮT ĐẦU chịu thuế

Điểm mới so với cách hiểu cũ — miễn thuế **có điều kiện**:

> *"Trường hợp tiền lương làm việc ban đêm, làm thêm giờ vượt mức quy định của pháp luật thì
> phần vượt mức quy định tính vào thu nhập chịu thuế."* — Đ.26 NĐ 253/2026

✅ **Trần đã chốt (HR xác nhận 05/08/2026)** — BLLĐ 2019 Đ.107 + NĐ 145/2020 Đ.61.
TIQN thuộc nhóm **sản xuất/gia công may mặc** → được áp mức đặc thù **300 giờ/năm**:

| Giới hạn | Mức áp dụng tại TIQN |
|---|---|
| Theo ngày | ≤ 50% giờ làm bình thường → **4 giờ/ngày** (ca 8h) |
| Theo ngày, tổng cộng | giờ thường + OT ≤ **12 giờ/ngày** |
| Theo tháng | ≤ **40 giờ** |
| Theo năm | ≤ **300 giờ** (ngành đặc thù, thay cho mức 200h thông thường) |

> ⚙ **Khai 4 con số này thành hằng số cấu hình**, không hardcode — cùng chỗ với mức giảm trừ
> gia cảnh (mục 5d.5). Trần năm đã đổi 200→300 theo ngành, trần tháng từng được nâng lên 60h
> trong một số giai đoạn; đây là loại tham số phải sửa được mà không cần deploy.

#### 🔴 Dữ liệu thực tế đang VƯỢT TRẦN trên diện rộng

Thống kê từ Attendance năm 2026 (đến 25/07), theo kỳ lương 26→25:

| Kiểm tra | Kết quả |
|---|---|
| Vượt **4h/ngày** | 46 lượt · 10 NV · cao nhất **9h/ngày** |
| Vượt **40h/tháng** | T3: 11 NV · T4: 145 · T5: 136 · T6: **371** · T7: **393** — cao nhất **71h** |
| Luỹ kế năm > **300h** | **3 NV** đã vượt (cao nhất 307h) |
| Luỹ kế năm 250–300h | **89 NV** — sẽ vượt trần trước cuối năm nếu giữ nhịp hiện tại |

→ Đây **không chỉ là vấn đề thuế mà là vấn đề tuân thủ pháp luật lao động** (vượt trần là hành vi
bị xử phạt). Cần báo cáo cho HR/Ban giám đốc, độc lập với việc chạy payroll.

#### ✅ ĐÃ RÕ: giờ OT vượt trần được CHUYỂN SANG một loại lương khác

HR xác nhận (05/08/2026): với ca TIQN-0019 — Attendance **55h**, phiếu trả OT **35h** —
**phần chênh 20h được HR điều chỉnh sang một loại lương khác**, không phải bị bỏ.

Đối chiếu số: phiếu TIQN-0019 có dòng **`4.3 KPI` = 1.119.464**, trong khi
20h × đơn giá 37.297,6 × 150% = **1.118.928** — **lệch 536đ (0,05%)**.
→ Rất nhiều khả năng chính là khoản chênh, chỉ khác chút do làm tròn/đơn giá HR dùng.
**Cần HR xác nhận đích danh khoản nào nhận phần chênh.**

**Hệ quả — thực ra làm mọi thứ ĐƠN GIẢN hơn:**

| | |
|---|---|
| Giờ ghi ở dòng OT (2.1/2.2/2.3) | **luôn nằm trong trần** ⇒ **miễn thuế toàn bộ**, không cần tính phần vượt |
| Phần vượt trần | đã nằm ở component khác (KPI/thưởng), vốn **đã chịu thuế** |
| Bảng kê OT theo NĐ 253/2026 | chỉ kê phần trong trần → **sạch, đúng mẫu** |

→ **Không cần cơ chế luỹ kế OT theo năm để tính thuế.** Vẫn cần 2 component như đã nói, nhưng
component thứ hai **không phải "OT chịu thuế"** mà là khoản thưởng thông thường HR đang dùng.

> ⚠ Vẫn phải giữ **cảnh báo vượt trần** (4h/ngày · 40h/tháng · 300h/năm): đó là nghĩa vụ tuân thủ
> pháp luật lao động, độc lập với việc khoản tiền được trả dưới tên gọi nào. Số liệu ở bảng trên
> cho thấy mức vượt là **đáng kể và đang tăng**.

**Hệ quả thiết kế — phức tạp hơn cách cũ:** ngưỡng miễn thuế **không tính được trong phạm vi
một phiếu lương** — trần năm đòi **số giờ OT luỹ kế từ đầu năm**:

```
ot_thang       = tổng giờ OT trong kỳ lương
ot_luyke_nam   = tổng giờ OT từ 01/01 đến hết kỳ
gio_mien_thue  = min(ot_thang, tran_thang, max(0, tran_nam - ot_luyke_truoc_ky))
gio_chiu_thue  = ot_thang - gio_mien_thue
```

→ Vẫn phải tách **2 component OT** (một `is_tax_applicable = 0`, một `= 1`), nhưng tiêu chí tách
là **định mức giờ**, không phải phần chênh lệch đơn giá. Cần custom field lưu giờ OT luỹ kế năm
trên Salary Slip — **không suy ra được từ riêng kỳ đang tính.**

> 💡 Dữ liệu thực tế cho thấy đây **không phải tình huống lý thuyết**: Attendance của
> **TIQN-0019** ghi **55 giờ OT** trong kỳ 26/06→25/07 — **vượt trần 40h**, tuy chưa vượt trần 60h. Phiếu chỉ trả 35h. Dù con số nào đúng thì cơ chế kiểm trần vẫn phải có.

#### 📋 Nghĩa vụ mới: BẢNG KÊ làm thêm giờ / làm ban đêm

Đ.26 NĐ 253/2026 bắt buộc doanh nghiệp **lập bảng kê** phản ánh rõ **thời gian** làm đêm/làm thêm
và **số tiền** đã trả, lưu tại doanh nghiệp và xuất trình khi cơ quan thuế yêu cầu.

→ **Thêm một deliverable**: report *"Bảng kê tiền lương làm thêm giờ, làm ban đêm"* — theo kỳ
lương, mỗi NV một dòng: số giờ từng loại (thường/CN/lễ/đêm) · đơn giá · hệ số · số tiền ·
luỹ kế năm · phần miễn/phần chịu thuế. Nguồn dữ liệu đã có đủ (mục 2.4b), chỉ là việc kết xuất.
Không làm bảng kê thì phải chứng minh bằng bảng lương + bảng chấm công + HĐLĐ — tốn công hơn nhiều.

#### ✅ Làm việc ban đêm — KHÔNG phát sinh tại TIQN (đã kiểm chứng bằng dữ liệu chấm công)

**Nguyên tắc pháp lý** (BLLĐ 2019 Đ.106): giờ làm việc ban đêm tính theo **khung giờ thực tế
22:00 → 06:00**, không căn cứ tên gọi ca. Ca giao thoa thì **chỉ phần giờ rơi vào khung đó** mới
là giờ ban đêm.

**Ca làm việc đang khai trong hệ thống:**

| Shift Type | Giờ | Giờ rơi vào 22:00–06:00 |
|---|---|---|
| Shift 1 | 06:00 – 14:00 | **0** |
| Shift 2 | 14:00 – 22:00 | **0** — kết thúc *đúng* mốc 22:00 |
| Day | 08:00 – 17:00 | 0 |
| Canteen · Canteen 6:30 | 07:00–16:00 · 06:30–15:30 | 0 |

**Kiểm chứng bằng giờ quẹt thẻ thật (toàn bộ năm 2026):**

| Kiểm tra | Kết quả |
|---|---|
| Ra sau 22:15 | **2 dòng / cả năm** (22:16, và cả hai đều **OT = 0**) |
| Vào trước 06:00 | 666 lượt, nhưng sớm nhất là **05:15–05:59** — là giờ *đến cổng* chờ ca 06:00, không phải giờ làm |
| OT của Shift 2 (223 lượt, 471h) | Quẹt vào **~11:57**, ra **~22:05** → **OT làm TRƯỚC ca (12:00–14:00), ban ngày** |
| OT của ca Day | Ra ~22:00, tức làm thêm 17:00→22:00 — vẫn **kết thúc đúng mốc**, chưa vào khung đêm |

→ **Kết luận: công ty KHÔNG có làm việc ban đêm.** Không cần khai phụ cấp ca đêm 30% (Đ.98 kh.2)
lẫn khoản cộng thêm 20% cho OT ban đêm (Đ.98 kh.3). **Phiếu lương không thiếu cấu phần nào** —
nghi vấn ở bản trước của tài liệu này đã được loại bỏ.

> ⚠ **Nhưng biên độ rất mỏng.** Cả Shift 2 lẫn OT ca Day đều kết thúc **đúng 22:00**. Chỉ cần
> tăng ca thêm 30 phút là phát sinh giờ ban đêm, và khi đó mỗi giờ phải trả **OT + 30% + 20%**.
> → Nên có **cảnh báo giám sát** (không cần cấu phần lương): báo khi có bản ghi chấm công
> `out_time > 22:00` hoặc `in_time < 06:00` kèm giờ làm thực tế. Rẻ, và chặn được rủi ro
> trả thiếu lương ban đêm nếu nhà máy đổi lịch sản xuất.

### 5d.3. 🔴 KHÔNG dùng `insurance_calculator.py` của repo

Repo áp **trần đóng BH** = 20 × lương cơ sở 2.340.000 = 46.800.000. TIQN **không áp trần**:

| Phiếu | Căn cứ BH | Repo (có trần) | Phiếu thật | |
|---|---:|---:|---:|---|
| TIQN-0006 | 28.939.100 | 2.315.128 | 2.315.128 | khớp (dưới trần) |
| **TIQN-0002** | **47.652.438** | **3.744.000** | **3.812.195** | ❌ lệch 68.195 |

Ngoài ra `union_fee` của repo là **KPCĐ 2% do doanh nghiệp đóng**, khác hẳn dòng 6.4 trên phiếu
TIQN (**đoàn phí NLĐ, 38.948 cố định**). → Chỉ lấy `pit_calculator.py`, giữ nguyên cách tính BH
hiện tại (`custom_si_base × tỷ lệ`).

### 5d.4. Người phụ thuộc (NPT)

**Mức giảm trừ từ kỳ tính thuế 2026** (Nghị quyết 110/2025):
bản thân **15.500.000**/tháng · mỗi NPT **6.200.000**/tháng
*(mức cũ 11.000.000 / 4.400.000 áp dụng đến hết kỳ 2025)*.

**Bốn nguyên tắc chi phối thiết kế:**
1. NNT phải có MST cá nhân; NPT được cấp MST NPT **nếu đã từng đăng ký**
2. Mỗi NPT chỉ tính cho **01** NNT trong **cùng năm tính thuế**
3. **Không giới hạn** số lượng NPT
4. Áp dụng **từ THÁNG phát sinh nghĩa vụ nuôi dưỡng**

→ Nguyên tắc 4 khiến **một field Int trên Employee là SAI**: số NPT đổi giữa năm, tính lại kỳ cũ
sẽ ra sai. Nguyên tắc 2 đòi kiểm tra chống trùng **giữa các nhân viên**.

> HRMS có sẵn `Employee Tax Exemption Declaration` nhưng theo **năm** và theo **số tiền**,
> không theo tháng/số người → không dùng được cho VN. Site đang có **0 record**.

📄 **Thiết kế doctype `Employee Dependent`, quy tắc validate, cách nhập liệu, thứ tự triển khai:
[`PLAN_EMPLOYEE_DEPENDENT.md`](PLAN_EMPLOYEE_DEPENDENT.md).**

### 5d.5. Nơi lưu mức giảm trừ

Không hardcode — hai mức này đổi theo nghị quyết Quốc hội, và **phiếu lương cũ phải tính lại ra
số cũ** ⇒ cần **ngày hiệu lực**.

📄 **Thiết kế `TIQN Payroll Settings` + kiểm kê toàn bộ hằng số lương:
[`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md).**

---

## 6. Lưu ý kỹ thuật

### 6.0. 🔴 Số tiền bằng chữ trên phiếu lương phải là TIẾNG VIỆT
`money_in_words` / filter `in_words` của Frappe ra tiếng Anh — không dùng cho chứng từ VNĐ.
Dùng `so_tien_bang_chu()` / `format_vnd()` (đã đăng ký Jinja trong `hooks.py`).
Chi tiết ở [`README.md`](README.md) mục *Quy ước bắt buộc khi in ấn*.


- Sau khi sửa Salary Component/Structure: **tạo 1 Salary Slip thử cho TIQN-0148 tháng 07/2026**
  và đối chiếu từng dòng với phiếu thật trước khi chạy Payroll Entry hàng loạt.
- Salary Structure Assignment là **submittable** — gán sai phải cancel + amend, nên kiểm tra kỹ
  `base` trước khi Assign.
- **Không bật `variable_based_on_taxable_salary` trên bất kỳ component nào** — kể cả PIT
  (xem mục 3.4). Bật là SSA bị ép phải có `Income Tax Slab`, mà ta không dùng doctype đó.
- Cờ `depends_on_payment_days` / `is_tax_applicable` phải đặt ở **Salary Component**, đặt ở dòng
  Salary Structure sẽ bị ghi đè **im lặng** (mục 5b8.1).

---

## 7. Dữ liệu gốc — 9 phiếu lương kỳ 07/2026 (đã trích, PDF gốc đã xoá)

> Toàn bộ công thức trong tài liệu này được dò ngược và kiểm chứng từ 9 phiếu lương thật dưới đây.
> File PDF gốc **đã xoá khỏi repo** (dữ liệu lương nhạy cảm) — bảng này là bản lưu để tra cứu và
> để hồi quy khi sửa công thức sau này.
>
> Kỳ lương: **26/06/2026 → 25/07/2026** · ngày công chuẩn 26 (30 ngày − 4 Chủ Nhật, không có lễ).

| Dòng | TIQN-0002 | TIQN-0006 | TIQN-0019 | TIQN-0044 | TIQN-0047 | TIQN-0148 | TIQN-1405 | TIQN-2087 | TIQN-2352 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Họ tên** | Lê Thanh Phong | Trần Văn Ân | Cao Thị Cẩm | Nguyễn Thị Yến Ni | Lê Ngọc Vỹ | Nguyễn Thái Sơn | Nguyễn Thành Vinh | Nguyễn Phỉ Vinh | Nguyễn Thị Vãng |
| **Chức vụ** | Production Department Manager | Engineering Manager | Sewing Worker | Office Department Manager | Cutting Supervisor | IT Subleader | IT Engineer | HSE staff | QC worker |
| **Bộ phận** | Production-Control | Engineering-Engineering | Sewing-Line 01 | Office-Accounting | Preparation-Cutting | HR-GA-HR-GA | HR-GA-HR-GA | HR-GA-HR-GA | QC-QC |
| **1 Lương cơ bản (a)** | 34,880,433 | 13,585,504 | 5,859,095 | 40,192,308 | 7,300,000 | 17,214,001 | 13,900,000 | 12,000,000 | 5,200,000 |
| 1.1 Ngày công chuẩn | 26 | 26 | 26 | 26 | 26 | 26 | 26 | 26 | 26 |
| 1.2 Ngày công thực tế | 26 → 34,880,433 | 24 → 12,540,465 | 26 → 5,859,095 | 26 → 40,192,308 | 26 → 7,300,000 | 25 → 16,551,924 | 26 → 13,900,000 | 26 → 12,000,000 | 2 → 400,000 |
| 2 Tăng ca (b) | – | – | 1,958,123 | 4,083,950 | 3,051,144 | 1,416,462 | – | – | – |
| 2.1 OT ngày thường (h) | 0 | 0 | 35 → 1,958,123 | 12 → 4,083,950 | 36.1 → 3,051,144 | 0 | 0 | 0 | 0 |
| 2.2 OT cuối tuần (h) | 0 | 0 | 0 | 0 | 0 | 8 → 1,416,462 | 0 | 0 | 0 |
| 3 Lương tháng (c=a+b) | 34,880,433 | 12,540,465 | 7,817,218 | 44,276,258 | 10,351,144 | 17,968,386 | 13,900,000 | 12,000,000 | 400,000 |
| 3.1 Phụ cấp (d) | 13,072,000 | 9,279,631 | 1,198,800 | 7,000,000 | 3,020,000 | 1,400,000 | 200,000 | 500,000 | 30,769 |
| 3.2 PC kỹ thuật | – | 3,287,631 | 898,800 | – | 1,500,000 | – | – | – | 7,692 |
| 3.3 PC chức vụ | 7,000,000 | 5,000,000 | – | 7,000,000 | 1,200,000 | 1,200,000 | – | – | – |
| 3.4 PC nhà ở | 5,000,000 | – | – | – | – | – | – | – | – |
| 3.5 PC xăng xe | 300,000 | – | 300,000 | – | 300,000 | – | – | 300,000 | 23,077 |
| 3.6 PC điện thoại | – | 200,000 | – | – | – | 200,000 | 200,000 | 200,000 | – |
| 3.7 PC PCCC | 772,000 | 772,000 | – | – | – | – | – | – | – |
| 3.8 PC ATVS | – | 20,000 | – | – | 20,000 | – | – | – | – |
| 4 Thưởng (e) | 5,000,000 | 5,500,000 | 2,119,464 | 20,000 | 1,700,000 | – | – | 20,000 | 76,923 |
| 4.1 Chuyên cần | – | 500,000 | 1,000,000 | – | 1,000,000 | – | – | – | 76,923 |
| 4.2 Trách nhiệm | 5,000,000 | 5,000,000 | – | – | 700,000 | – | – | – | – |
| 4.3 KPI | – | – | 1,119,464 | – | – | – | – | – | – |
| 4.6 HT con nhỏ | – | – | – | 20,000 | – | – | – | 20,000 | – |
| **5 TỔNG (f=c+d+e)** | 52,952,433 | 27,320,096 | 11,135,482 | 51,296,258 | 15,071,144 | 19,368,386 | 14,100,000 | 12,520,000 | 507,692 |
| **6 Khấu trừ (g)** | 5,042,453 | 3,077,554 | 853,527 | 4,994,141 | 1,269,548 | 1,988,341 | 1,498,448 | 1,298,948 | – |
| 6.1 BHXH 8% | 3,812,195 | 2,315,128 | 620,632 | 3,775,385 | 937,600 | 1,473,120 | 1,112,000 | 960,000 | – |
| 6.2 BHYT 1.5% | 714,786 | 434,087 | 116,368 | 707,885 | 175,800 | 276,210 | 208,500 | 180,000 | – |
| 6.3 BHTN 1% | 476,524 | 289,391 | 77,579 | 471,923 | 117,200 | 184,140 | 139,000 | 120,000 | – |
| 6.4 Phí công đoàn | 38,948 | 38,948 | 38,948 | 38,948 | 38,948 | 38,948 | 38,948 | 38,948 | – |
| 6.5 Thuế TNCN | – | – | – | – | – | 15,923 | – | – | – |
| 7 Khác (h) | – | – | – | – | – | 50,000 | – | – | – |
| 7.1 HT tiền cơm | – | – | – | – | – | 50,000 | – | – | – |
| **9 THỰC LĨNH (j)** | 47,909,980 | 24,242,542 | 10,281,955 | 46,302,117 | 13,801,596 | 17,430,045 | 12,601,552 | 11,221,052 | 507,692 |


### 7.1. Kiểm chứng công thức trên tập dữ liệu này

| Công thức | Kết quả |
|---|---|
| Ngày công chuẩn = tổng ngày − Chủ Nhật | 9/9 (đều = 26) |
| Lương thực tế = base / ngày chuẩn × ngày thực tế | 9/9 |
| **Căn cứ BH** = Lương HĐLĐ + kỹ thuật + chức vụ + PCCC + ATVS + hỗ trợ công đoạn + chuyên cần + trách nhiệm | **7/8** (TIQN-2352 không đóng BH; TIQN-0006 lệch −773.965) |
| Đơn giá OT = căn cứ BH / (ngày chuẩn × 8); hệ số 150/200/300% | 4/4 phiếu có OT |
| Hỗ trợ cơm 50.000 khi OT chủ nhật > 4h | 9/9 |
| Phí công đoàn 38.948 cố định | 8/8 (TIQN-2352 mới vào, chưa đóng) |
| **PIT** = (Basic prorate + PC chức vụ − BH − 15.500.000 − NPT×6.200.000) theo biểu 7 bậc | **7/9 khớp với 0 NPT** |

**Các khoản KHÔNG vào căn cứ BH** (bằng chứng từ tập này): xăng xe · điện thoại · nhà ở ·
KPI · hỗ trợ con nhỏ · các khoản 7.x.

### 7.2. Ba điểm còn tồn — trạng thái sau khi HR trả lời (05/08/2026)

1. ⏸ **TIQN-0006** — căn cứ BH thật 28.939.100, công thức ra 28.165.135, lệch **−773.965**.
   Nghi do "lương trên HĐLĐ" khác dòng Basic trên phiếu, hoặc có phụ cấp ghi 0 trong tháng
   nhưng vẫn có trong hợp đồng. → **HR quyết định để sau.** Không chặn: đã có cơ chế
   `custom_si_base_override` (mục 2.1b) để khai đúng mức đăng ký cho ca cá biệt.
2. ⏸ **TIQN-0002 và TIQN-0044** — lương cao nhưng PIT = 0. Theo công thức phải nộp lần lượt
   ~2.625.386 và ~3.697.423. Chỉ về 0 nếu có **≥ 4** và **≥ 5** người phụ thuộc.
   → HR xác nhận **"họ có nhiều NPT nhưng không có con số cụ thể"**. Giả thuyết được củng cố về
   mặt định tính, **không kiểm chứng được bằng số**. Chấp nhận: PIT giữ mức khớp **7/9 phiếu**.
3. ✅ **Định nghĩa thu nhập chịu thuế** — HR chốt **"cứ theo luật"**; luật hiện hành (Điều 4 Luật
   TNCN 2025 · Đ.26 NĐ 253/2026) **miễn toàn bộ tiền OT** ⇒ phiếu lương TIQN đang tính **đúng**,
   PIT của TIQN-0148 giữ nguyên 15.923. Điểm mới cần xử lý là **trần giờ OT** (mục 5d.2b).
