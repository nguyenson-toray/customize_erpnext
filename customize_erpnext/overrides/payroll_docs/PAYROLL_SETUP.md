# Tính lương TIQN trên ERPNext — tài liệu thi công

Công thức dò ngược và kiểm chứng từ **9 phiếu lương thật** kỳ 07/2026 (dữ liệu gốc ở mục 8)
cùng bảng lương Excel của HR (16 nhân viên). Nguồn pháp lý nội bộ:
[`QUY_CHE_LUONG_2025.md`](QUY_CHE_LUONG_2025.md) — **khi hai tài liệu mâu thuẫn, quy chế thắng**.

Kỳ lương: **26 tháng trước → 25 tháng này**.

---

## 0. Trạng thái

| Hạng mục | |
|---|---|
| Công thức lương, phụ cấp, OT, thuế | ✅ kiểm chứng khớp phiếu thật |
| `TIQN - Standard (ALL components)` — 19 earnings | ✅ |
| Khấu trừ BHXH/BHYT/BHTN · đoàn phí · TNCN qua hook Python | ✅ |
| Mốc 14 ngày đóng BH (Luật BHXH 2024) | ✅ |
| Giờ OT tự nạp từ Attendance + tách phần vượt trần | ✅ |
| `TIQN Payroll Settings` · `Employee Dependent` | ✅ |
| Báo cáo `OT Compliance` | ✅ |
| **Sync chấm công từ app HR sang ERP** | 🔴 chưa có |
| Ngày lễ không còn bị trừ lương (mục 4.8) | ✅ sửa 10/08/2026 |
| **Rà soát lượt quẹt thiếu trước khi chốt lương (mục 4.10)** | ⚠ **quy trình BẮT BUỘC của HR** |
| `custom_salary_month` (mục 4.9) | ✅ |
| **Dữ liệu nghỉ phép** | 🟠 đã import **7.097 đơn ở dạng draft**, chờ submit — xem `../leave_application/PLAN_IMPORT_AL_2026.md` |
| **Dữ liệu không lương / hưởng BH** | 🟠 nằm trong 7.097 đơn trên |
| **Dữ liệu người phụ thuộc** | 🔴 chưa có — thuế đang tính với 0 NPT |
| **Lương HĐLĐ của ~1.036 NV Active** | 🔴 mới có 16 người |

Việc còn phải làm: **mục 7**.

---

## 1. Ánh xạ phiếu lương → ERPNext

| Phiếu lương TIQN | ERPNext |
|---|---|
| Mã NV, họ tên, bộ phận, chức vụ | `Employee` |
| Lương HĐLĐ + phụ cấp cố định | `Salary Structure Assignment` (SSA) |
| Ngày công chuẩn / thực tế | `Salary Slip.total_working_days` / `payment_days` |
| Từng dòng tiền | `Salary Detail` trong `Salary Slip` |
| Tổng `f` · `g` · `j` | `gross_pay` · `total_deduction` · `net_pay` |

---

## 2. Công thức

### 2.1. Căn cứ đóng bảo hiểm (`custom_si_base`)

Tổng **8 khoản** — HR xác nhận, và khớp **16/16** dòng cột *"Salary for SI & HI"* trong file Excel:

```
base (lương HĐLĐ)
+ custom_technical_allowance          Phụ cấp kỹ thuật
+ custom_position_allowance           Phụ cấp chức vụ
+ custom_pccc_allowance               Phụ cấp PCCC
+ custom_atvs_allowance               Phụ cấp ATVS
+ custom_supporting_stages_allowance  Phụ cấp hỗ trợ công đoạn
+ custom_attendance_incentive         Thưởng chuyên cần
+ custom_responsibility_incentive     Thưởng trách nhiệm
```

**KHÔNG gồm:** xăng xe · điện thoại · nhà ở · KPI · hỗ trợ con nhỏ · các khoản 7.x.

Tự tính trên SSA (`overrides/salary_structure_assignment/`). Tick `custom_si_base_override`
để nhập tay theo mức đã đăng ký với cơ quan BHXH — khi đó hệ thống **cảnh báo mọi mức lệch**
(8 khoản đều là Currency số nguyên đồng nên không có sai số làm tròn để bỏ qua).

> Ca cá biệt `TIQN-0006`: căn cứ BH thật lệch **−773.965** so với công thức. Chưa rõ nguyên nhân,
> dùng `custom_si_base_override` để khai đúng số đăng ký.

### 2.2. Ngày công chuẩn

```
total_working_days = số ngày trong kỳ − số Chủ Nhật
```

🔴 **Ngày lễ nhà nước VẪN tính công và trả lương** dù không đi làm → **không** trừ.
Bản gốc HRMS trừ mọi dòng trong Holiday List; kỳ Tết sẽ ra 18 ngày thay vì 27.

Override một method duy nhất — `CustomSalarySlip.get_holidays_for_employee()` chỉ trả về
dòng có `weekly_off = 1`.

| Kỳ | Tổng ngày | Chủ Nhật | Ngày công chuẩn |
|---|---:|---:|---:|
| 26/12/2025 → 25/01/2026 | 31 | 5 | 26 |
| 26/01 → 25/02/2026 | 31 | 4 | **27** |
| 26/06 → 25/07/2026 | 30 | 4 | 26 |

**Holiday List khai trùng NĂM LƯƠNG** — `26/12 → 25/12`, giống `Payroll Period`. Nhờ vậy không
kỳ lương nào vắt qua ranh giới hai list, và tra một list là đủ.

> Khai đủ **cả hai loại** trong cùng list, phân biệt bằng cờ `Holiday.weekly_off`
> (1 = Chủ Nhật, 0 = ngày lễ). Ngày lễ trùng Chủ Nhật thì HR phải thêm ngày nghỉ bù.
>
> ⚠ Tạo Holiday List năm mới nhớ đặt phạm vi `26/12 → 25/12` và `Holiday List Assignment.from_date = 26/12`.

### 2.3. Lương theo ngày công

```
Lương cơ bản = base × payment_days / total_working_days
```

Quy tắc prorate **khác nhau theo từng khoản** — theo quy chế, không phải một cờ chung:

| Khoản | Quy tắc |
|---|---|
| Lương cơ bản · PC kỹ thuật · PC xăng xe · thưởng chuyên cần | **luôn** theo ngày công |
| PC chức vụ · PCCC · ATVS · hỗ trợ công đoạn | nguyên mức — **trừ khi ngày công < 8** |
| PC nhà ở | nguyên mức — **< 14 ngày → ½ tháng** (bậc, không phải tỷ lệ) |
| Thưởng trách nhiệm | nguyên mức — trừ khi thử việc / thôi việc |
| PC điện thoại | cố định |

### 2.4. Tăng ca

```
Đơn giá giờ = custom_si_base / (total_working_days × 8)
OT = đơn_giá_giờ × số_giờ × hệ_số
```

Hệ số **150% ngày thường · 200% cuối tuần · 300% ngày lễ**.
Mẫu số là ngày công chuẩn **của tháng đó**, không phải hằng số 26.

> Phiếu `TIQN-0047` là ca quyết định: Basic 7.300.000, căn cứ BH 11.720.000, Basic+mọi khoản
> 12.020.000 — chỉ **căn cứ BH** cho ra đúng 3.051.144.

**Nguồn giờ OT: `Attendance.custom_final_overtime_duration`** (`docstatus = 1`).
KHÔNG dùng `custom_approved_overtime_duration` — ca `TIQN-0047` có approved 66h nhưng final 36,1h,
và chỉ `final` mới khớp phiếu.

Phân loại 3 loại OT bằng chính Holiday List: không có trong list → thường · `weekly_off = 1` →
cuối tuần · `weekly_off = 0` → lễ.

Tick `custom_ot_override` trên Salary Slip để giữ số nhập tay.

#### Giờ OT vượt trần → chuyển sang KPI

Trần: **4h/ngày · 40h/tháng · 300h/năm** (BLLĐ Đ.107 + NĐ 145/2020 — ngành dệt may).

Tiền OT **trong trần** được miễn thuế; phần **vượt trần** chịu thuế (NĐ 253/2026 Đ.26).
Để chung một dòng là khai sai thuế.

Option `move_excess_ot_to_kpi` (mặc định **bật**) chuyển phần vượt sang dòng `4.3 KPI`.
Trần đếm theo **tháng dương lịch**; cắt từ hệ số thấp lên cao (thường → cuối tuần → lễ).

> Khớp cách HR làm: `TIQN-0019` chấm công 55h → phiếu ghi OT 35h + phần còn lại ở KPI.
> Tổng tiền hai cách chênh 537đ (0,017%) do HR làm tròn từng phần.
>
> ⚠ `custom_kpi_incentive` **do hệ thống quản lý**, bị ghi đè kể cả về 0. Nhập KPI thủ công
> thì dùng `Additional Salary`.

### 2.5. Thử việc

Nhận diện qua `Employee.employment_type` ∈ `TIQN Payroll Settings.probation_employment_types`.

| | |
|---|---|
| Lương thử việc | **100%** mức HĐLĐ (quy chế Phần I) |
| BHXH/BHYT/BHTN · đoàn phí | **không đóng** — ký HĐ thử việc riêng, không thuộc diện bắt buộc |
| Dòng `7.6` | hoàn **21,5%** phần công ty đóng, bằng tiền |
| Thuế TNCN | **thuế suất cố định 10%**, không giảm trừ gia cảnh, ngưỡng chi trả 2.000.000 |

> ⚠ Phụ thuộc `Employee.employment_type` được đồng bộ đúng lúc. Hợp đồng chính thức đánh dấu
> `Signed` trễ ⇒ vẫn bị coi là thử việc ⇒ không trừ bảo hiểm.

### 2.6. Bảo hiểm bắt buộc — mốc 14 ngày (Luật BHXH 2024)

```
nghỉ KHÔNG hưởng lương >= 14 ngày làm việc trong THÁNG DƯƠNG LỊCH  ->  không đóng
dưới 14 ngày                                                       ->  đóng đủ cả tháng
```

🔴 Đếm theo **tháng dương lịch**, không theo kỳ lương — cơ quan BHXH tính từ ngày 01 đến cuối
tháng, còn kỳ lương là 26 → 25. Lấy tháng của `end_date`.

| Tính là không hưởng lương | Không tính |
|---|---|
| Ngoài thời gian làm việc (chưa vào / đã nghỉ việc) | **Chủ Nhật** — không phải ngày làm việc |
| `Absent` | **Ngày lễ** — ngày làm việc **có hưởng lương** |
| `On Leave` với `Leave Type.is_lwp = 1` | `On Leave` loại nghỉ có lương |
| `Half Day` + `half_day_status = "Absent"` → **0,5** | `Half Day` + `Present` |
| Không có bản ghi chấm công (theo `consider_unmarked_attendance_as`) | |

Khi không đóng BH thì **cũng không thu đoàn phí** — không có lương để trừ.

Ngưỡng khai ở `unpaid_days_to_skip_insurance`; để **0** là tắt quy tắc.

TIQN **không áp trần** đóng BH — phiếu `TIQN-0002` có căn cứ 47.652.438, cao hơn trần
20 × lương cơ sở, vẫn đóng trên toàn bộ. Nhánh áp trần vẫn có (`apply_si_ceiling`) vì luật quy định.

### 2.7. Đoàn phí

Số tiền **cố định**, giống nhau mọi nhân viên: `38.948`. Khai ở Settings, không prorate.

### 2.8. Thuế thu nhập cá nhân

**Thu nhập chịu thuế = tổng earnings có `is_tax_applicable = 1`** — đọc cờ, không liệt kê tên
khoản, nên thêm/bớt phụ cấp không phải sửa code.

```
thu nhập tính thuế = thu nhập chịu thuế − BH − giảm trừ bản thân − N × giảm trừ NPT
PIT = biểu luỹ tiến 7 bậc THÁNG, dùng số trừ nhanh
```

Miễn thuế: **toàn bộ tiền làm thêm giờ** (Điều 4 Luật TNCN 2025 + Đ.26 NĐ 253/2026 — không còn
tách phần chênh lệch như TT 111/2013) · PC điện thoại, xăng xe trong mức khoán ·
tiền ăn giữa ca ≤ 730.000/tháng.

Chịu thuế: PC chức vụ · kỹ thuật · nhà ở · PCCC · ATVS · hỗ trợ công đoạn · chuyên cần ·
trách nhiệm · KPI · hỗ trợ con nhỏ · khoản hoàn 21,5%.

Được trừ: BHXH/BHYT/BHTN + giảm trừ gia cảnh. **Không** được trừ đoàn phí.

Giảm trừ từ kỳ tính thuế 2026: bản thân **15.500.000** · mỗi NPT **6.200.000** (NQ 110/2025).

🔴 **KHÔNG dùng `Income Tax Slab` của ERPNext** — HRMS tính trên thu nhập cả năm rồi chia cho số
kỳ còn lại (mô hình Ấn Độ). Việt Nam khấu trừ theo **biểu tháng**, quyết toán lại cuối năm.

Kiểm chứng `TIQN-0148`: `(16.551.924 + 1.200.000 − 1.933.470 − 15.500.000) × 5% = 15.923` ✓

### 2.9. Tổng

```
c = a + b          lương tháng
f = c + d + e      -> gross_pay
j = f − g + h + i  -> net_pay
```

---

## 3. Kiến trúc — cái gì tính ở đâu

Ràng buộc gốc: **formula của Salary Structure không đọc được Settings/DB**.
`COMPONENT_EVAL_GLOBALS` (`hrms/payroll/utils.py:34`) chỉ có `int/float/round/date/min/max`.

| Tầng | Nơi tính | Gồm |
|---|---|---|
| **Formula** trong Salary Structure | `Salary Detail.formula` | Lương cơ bản · OT · phụ cấp · ngưỡng ngày công · tiền cơm · dòng `7.6` |
| **Python** — hook `apply_regional_deductions` | `overrides/payroll/vn_deductions.py` | BHXH/BHYT/BHTN · đoàn phí · thuế TNCN · mốc 14 ngày |
| **Python** — override Salary Slip | `overrides/salary_slip/salary_slip.py` | Ngày công chuẩn · nạp giờ OT · tách OT vượt trần · đặt tên phiếu |
| **SSA** | `overrides/salary_structure_assignment/` | `custom_si_base` tự tính |

Hook `apply_regional_deductions` là **điểm móc có sẵn của HRMS** (`salary_slip.py:877`,
decorator `@hrms.allow_regional`), khớp region qua `Company.country = "Vietnam"`.
Cách làm học từ `frappe/india-payroll`.

⚠ Hook chạy **sau** khi `gross_pay` đã chốt ⇒ chỉ thêm được **deduction**.
Dòng `7.6` là *earning* nên phải nằm trong Salary Structure.

**Đặt tên phiếu:** `Sal Slip/{mã NV}/{YYYYMM}`, tháng lấy từ `end_date`.

---

## 4. GOTCHA — đọc trước khi sửa

### 4.1. Cờ `depends_on_payment_days` / `is_tax_applicable` phải đặt ở **Salary Component**

`SalaryStructure.set_missing_values()` (`salary_structure.py:57`) **luôn ghi đè** 4 cờ này từ
Salary Component mỗi lần save. Đặt ở dòng structure là công cốc — và **im lặng**, không báo lỗi.

| Component | `dep_days` | `is_tax_applicable` |
|---|:---:|:---:|
| 1 Basic Salary | 1 | 1 |
| 2.1 / 2.2 / 2.3 OT | 0 | **0** |
| 3.2 Kỹ thuật · 3.5 Xăng xe · 4.1 Chuyên cần | **1** | 1 / **0** / 1 |
| 3.3 Chức vụ · 3.4 Nhà ở · 3.7 PCCC · 3.8 ATVS · 3.9 Công đoạn | 0 | 1 |
| 3.6 Điện thoại · 7.1 Tiền cơm | 0 | **0** |
| 4.2 Trách nhiệm · 4.3 KPI · 4.5 Hỗ trợ ca · 4.6 Con nhỏ · 7.6 21,5% | 0 | 1 |

### 4.2. `condition` được eval bằng dữ liệu SSA, không phải dữ liệu tháng

`get_evaluated_components()` chạy **mỗi lần lập phiếu** (không cache) nên field của **Employee**
luôn là hiện tại. Nhưng lúc eval, `payment_days = total_working_days` và các custom field lấy từ
**SSA** (thường = 0).

- ❌ **KHÔNG** đặt điều kiện phụ thuộc dữ liệu tháng (giờ OT, ngày công) vào `condition`
- ✅ Đưa vào **`formula`** dạng biểu thức điều kiện
- ✅ `condition` dùng được cho field của Employee — ví dụ `employment_type`

Đã kiểm chứng: đổi `employment_type` sang thử việc → kỳ sau tự ngừng trừ bảo hiểm, không cần tạo lại SSA.

### 4.3. Custom field dùng trong formula phải có trên **cả SSA lẫn Salary Slip**

`SALARY_SLIP_EVAL_DEFAULTS` chỉ liệt kê field chuẩn → thiếu là `NameError` khi SSA validate.
Khai trên SSA để eval được; khai thêm trên Salary Slip thì giá trị nhập theo tháng **ghi đè**
(`salary_slip.py:1286` — `data.update(self.as_dict())` chạy sau khi nạp SSA).

⇒ **SSA giữ giá trị ổn định · Salary Slip giữ giá trị theo tháng.**

### 4.4. Khoản PHÁT SINH dùng `Additional Salary`, không khai trong Structure

Quà cưới · thanh toán phép năm · phụ cấp kinh nguyệt · quyết toán thuế · bồi thường HĐ ·
huấn luyện PCCC · hỗ trợ nhà in · hỗ trợ xăng xe.

Salary Slip **tự nhặt** vào kể cả khi component không có trong Salary Structure.

🔴 Additional Salary **vẫn áp** `depends_on_payment_days` của component — quà cưới 1.000.000
cho NV đi làm 25/26 ngày sẽ ra 961.538. Mọi component dùng qua Additional Salary phải để cờ đó = **0**.

Danh sách khoản phát sinh (nhóm **7 Others/Các khoản khác**), tất cả `depends_on_payment_days = 0`:

| Mã | Khoản | `is_tax_applicable` |
|---|---|:--:|
| 7.2 | Marriage gift / Quà kết hôn | 1 |
| 7.3 | PIT Finalization / Quyết toán thuế | 1 |
| 7.4 | Annual leave payment / Thanh toán phép năm | 1 |
| 7.5 | Menstrual allowance / Phụ cấp kinh nguyệt | 1 |
| **7.7** | **Public holiday bonus / Thưởng lễ** *(thêm 10/08/2026)* | **1** |

`7.7` dùng cho thưởng 30/4 · 1/5 · 2/9 · Tết. Đã kiểm A/B trên phiếu 24/25 ngày công với mức
thưởng 1.000.000: cờ `= 0` trả **đủ 1.000.000**, cờ `= 1` chỉ còn **960.000**. Khoản này **có**
vào thu nhập chịu thuế nhưng **không** vào căn cứ đóng BHXH (Additional Salary nằm ngoài 8 field
tính `custom_si_base` trên SSA — đúng quy định: tiền thưởng không tính đóng BHXH).

### 4.5. Mọi thao tác ghi phải idempotent

Salary Slip được tính lại nhiều lần. **Xoá dòng cũ trước rồi mới append**; gán giá trị thì
**luôn gán kể cả 0**. Không làm vậy là **nhân đôi tiền** — lỗi câm, không ai phát hiện cho tới
khi NLĐ thắc mắc.

### 4.6. `half_day_status` — `Half Day` một mình chưa đủ

HRMS chỉ trừ nửa ngày khi có **thêm** cờ `half_day_status = "Absent"` (`salary_slip.py:588`).

| `half_day_status` | Nghĩa của nửa còn lại | payment_days |
|---|---|:--:|
| `Absent` | nghỉ **không hưởng lương** | **0,5** |
| `Present` | vẫn **hưởng lương** | 1,0 |
| `NULL` | không khai → HRMS coi như *không phải* Absent | 1,0 |

🔴 **Nghỉ nửa ngày CÓ ĐƠN luôn phải là `Present`**, kể cả loại nghỉ không lương — vì
`salary_slip.py:791` đã cộng `equivalent_lwp = 1 − 0.5`, gắn `Absent` nữa là trừ **hai lần**.
HRMS core làm đúng vậy (`leave_application.py:317`).

Khớp quy chế: **làm 4h + nghỉ phép 4h = hưởng đủ lương**.

### 4.7. Data Import treo khi `developer_mode = 1`

`data_import.py:123` — `run_now = frappe.in_test or frappe.conf.developer_mode` ⇒ import chạy
inline và treo với >1000 dòng.

Thứ tự đúng: **bật dev mode → tạo doctype → tắt dev mode → import dữ liệu**.

---
### 4.8. 🔴 HRMS dùng MỘT danh sách ngày nghỉ cho hai mục đích trái nhau

`get_working_days_details()` (`hrms/salary_slip.py:497`) gọi `get_holidays_for_employee()`
**một lần** rồi truyền cùng một danh sách đi khắp nơi:

| Mục đích | Cần danh sách nào |
|---|---|
| (a) `working_days -= len(holidays)` → ngày công chuẩn | **chỉ Chủ Nhật** (mục 2.2: ngày lễ vẫn tính công) |
| (b) bỏ qua `Absent` / `Half Day` rơi vào ngày nghỉ | **cả ngày lễ** |

Override `get_holidays_for_employee()` của ta trả **chỉ Chủ Nhật** để phục vụ (a) — nếu trả đủ
thì ngày công chuẩn kỳ Tết ra 18 thay vì 27 và sai đơn giá ngày. Nhưng khi đó (b) **không nhìn
thấy ngày lễ**, nên một bản ghi Attendance `Absent` rơi vào ngày lễ sẽ **trừ lương thật**.

**Đo được (10/08/2026)** trên `Sal Slip/TIQN-0148/202602`, kỳ Tết 26/01 → 25/02/2026:
9 ngày Tết bị chấm `Absent` ⇒ trả **18/27** ngày, net **11.005.883** thay vì **16.694.856**
— mất **5.688.973 đ** cho một người trong một tháng.

**Đã sửa** ở `overrides/salary_slip/salary_slip.py`: thêm `all_holidays_in_period()` (Chủ Nhật
+ ngày lễ) và override đúng hai hàm tiêu thụ mục đích (b):

```python
calculate_lwp_ppl_and_absent_days_based_on_attendance()   # -> all_holidays_in_period()
get_half_absent_days()                                    # -> all_holidays_in_period()
get_holidays_for_employee()                               # giữ nguyên: CHỈ Chủ Nhật
```

⚠ **Cố ý KHÔNG đụng `get_unmarked_days()`.** Nó đếm ngày *chưa chấm công* bằng
`total_working_days − đã chấm`; đưa ngày lễ vào sẽ loại các bản ghi ngày lễ khỏi nhóm "đã chấm"
rồi tính chúng thành vắng mặt **lần nữa**. Đúng cái bẫy đã ghi ở `PLAN_ATTENDANCE_VS_QUYCHE.md`
mục A3: **xoá bản ghi Absent ngày lễ KHÔNG phải là cách sửa**, vì
`consider_unmarked_attendance_as = Absent` sẽ tính lại chúng thành vắng.

Nhờ sửa ở tầng lương, payroll **đúng bất kể dữ liệu Attendance** — không phải chờ dọn 11.065
bản ghi `Absent` ngày lễ.

### 4.9. `custom_salary_month` — nhãn kỳ lương lấy theo `end_date`

`CustomSalarySlip.set_salary_month()` điền `custom_salary_month` dạng **`Jul-2026`** mỗi lần
validate. Lấy theo **`end_date`**: kỳ 26/06 → 25/07 là **tháng 7**; dùng `start_date` ra
`Jun-2026`, lệch đúng một tháng.

Bốn chỗ nay dùng chung mốc `end_date`: `autoname()` · `custom_salary_month` · đếm người phụ
thuộc (`get_dependent_count`) · tra tham số theo ngày hiệu lực.

⚠ Phiếu **đã submit** không nhận giá trị này qua `save()` (field không `allow_on_submit`, và
`validate()` không chạy lại) — phải `frappe.db.set_value`. Phiếu mới thì không lo: giá trị gán
lúc validate, tức trước khi submit.

### 4.10. 🔴 BẮT BUỘC: HR rà soát lượt quẹt thiếu TRƯỚC khi chốt lương

Ngày chỉ có **lượt quẹt vào**, không có lượt ra hợp lệ, được tính `Present` với
`working_hours = 0`. Đó là **chủ ý** — người lao động đã đến làm, để `Absent` là cắt trọn ngày
lương của họ (xem `../shift_type/OPTIMIZATION_GUIDE.md`).

Cái giá phải trả: **trả đủ ngày mà không có giờ nào ghi nhận**, và **OT của ngày đó = 0** vì
không có mốc kết thúc. Hệ thống không được phép tự đoán giờ ra.

⇒ **Quy trình bắt buộc: HR rà soát và bổ sung lượt quẹt thiếu trước khi tính lương.**

`CustomSalarySlip.warn_incomplete_attendance()` liệt kê các ngày đó ngay khi lưu phiếu, kèm link
mở từng bản ghi Attendance.

🔴 **Cố ý bỏ qua khi lập hàng loạt qua Payroll Entry** (`if self.payroll_entry: return`).
`create_salary_slips_for_employees()` (`payroll_entry.py:1560`) gọi `insert()` cho **từng** nhân
viên và **không** mute message. Đo kỳ 26/07-25/08: **938** nhân viên có ngày thiếu lượt quẹt ⇒ 938
`msgprint` dồn vào `frappe.message_log` của một background job mà **không ai đọc**, chỉ tốn bộ nhớ.
Đường chính để HR rà vẫn là sheet "Important Note" — cảnh báo ở đây chỉ là lưới an toàn khi lập
hoặc sửa **một** phiếu bằng tay.

> Chi phí truy vấn không đáng kể: đo 1.036 nhân viên hết **0,7 giây** nhờ index
> `idx_att_emp_date_docstatus`.

**Cảnh báo, không chặn** — kỳ **đang diễn ra** thì thiếu lượt ra là bình thường. Đo 12/08/2026:

| Kỳ lương | Bản ghi thiếu | Nhân viên |
|---|---:|---:|
| 02/2026 → 07/2026 (đã đóng) | **1–4 mỗi kỳ** | 1–4 |
| **08/2026 (đang diễn ra)** | **936** | 930 |

Chặn cứng sẽ làm không lập nổi phiếu nháp giữa kỳ. Với kỳ đã đóng thì số lượng nhỏ, rà tay được.

#### Thứ tự bắt buộc của một kỳ lương

```
1. Report "Shift Attendance Customize" → nút Export Excel
      → sheet "Important Note" liệt kê mọi ca dị thường của kỳ
2. HR hoàn thiện lượt quẹt thiếu  (bổ sung Employee Checkin)
3. Bulk Update Attendance cho toàn kỳ  → tính lại ngày công + OT
4. MỚI lập Salary Slip / Payroll Entry
```

🔴 **Không được đảo bước 3 và 4.** Bổ sung checkin mà chưa tính lại thì Attendance vẫn giữ
`working_hours = 0` và `OT = 0` của lần chạy trước — phiếu lương sẽ lấy đúng số cũ đó.

Sheet **"Important Note"** (`report/shift_attendance_customize/standard_export.py`) là bản sao
của app cũ, gom sẵn toàn bộ dị thường từ `Attendance.custom_note`, nên HR không phải tự truy vấn.
`warn_incomplete_attendance()` chỉ là lớp chặn cuối, nhắc lại đúng nhóm "thiếu lượt quẹt" khi lưu
từng phiếu.

Hai nhóm nguyên nhân của nhóm thiếu lượt quẹt, phân biệt bằng `custom_note`:

| Note | Nghĩa |
|---|---|
| `Only one check-in record` | thật sự chỉ quẹt một lần — quên quẹt ra |
| `No check-OUT (all logs before shift start)` | quẹt **đúp** ở cửa lúc vào; `out_time` giả đã bị loại bỏ |

### 4.11. `total_in_words` phải là **tiếng Việt**

HRMS `set_net_total_in_words()` (`hrms/salary_slip.py:192-198`) gọi
`frappe.utils.money_in_words()` — trả về **tiếng Anh**:
*"VND Seventeen Million, Four Hundred Thousand… only."* Không dùng được cho chứng từ trả lương
tại Việt Nam.

`CustomSalarySlip.set_net_total_in_words()` gọi `super()` trước (giữ nguyên hành vi cho mọi đồng
tiền khác) rồi **ghi đè khi `currency == "VND"`** bằng
`api/vn_number_words.money_in_words_vi()`:

> Mười bảy triệu bốn trăm nghìn tám trăm bảy mươi tám đồng

`money_in_words_vi()` thuần stdlib, **không import `frappe`**, nên
`tests/test_vn_number_words.py` chạy được không cần bench/site. Cùng module còn có
`format_vnd()`; cả hai đã đăng ký Jinja trong `hooks.py` để dùng trong Print Format.

⚠ Phiếu **đã submit** không nhận giá trị mới qua `save()` — phải `frappe.db.set_value`,
giống `custom_salary_month` ở mục 4.9.

🔴 **Đừng dùng `frappe.format` cho tiền trên chứng từ**: `System Settings.number_format` đang là
`"# ###,##"` (dấu cách) → ra `17 400 878`; chứng từ VN cần dấu chấm. Dùng `format_vnd()`.

## 5. Nhập liệu

### 5.1. Salary Structure Assignment

🔴 `Bulk Salary Structure Assignment` của HRMS **không đủ** — grid chỉ sửa được `base` và
`variable`, trong khi SSA của TIQN cần thêm **11 field phụ cấp**.

Dùng `overrides/payroll/import_ssa.py` (mặc định **dry-run**):

```bash
# 1. Trích Excel HR ra CSV phẳng (giữ lại để đối chiếu về sau)
bench --site erp.tiqn.local execute customize_erpnext.overrides.payroll.import_ssa.to_csv \
  --kwargs "{'xlsx_path': '.../Salary.xlsx', 'csv_path': '.../salary_contract_YYYYMM.csv'}"

# 2. Import
bench --site erp.tiqn.local execute customize_erpnext.overrides.payroll.import_ssa.run \
  --kwargs "{'path': '.../salary_contract_YYYYMM.csv', 'commit': True}"
```

Chỉ lấy nhóm cột **"Salary in Labour Contract"**. Nhóm *"Actual Salary in the Month"* là số thực
trả của riêng kỳ đó — thuộc về Salary Slip.

`from_date` mặc định = ngày vào làm. SSA **không phải việc hàng tháng** — quy chế ghi
*"xem xét lương hằng năm vào tháng Tư"*.

### 5.2. Loại hợp đồng

`import_ssa.sync_employment_type()` đọc cột `contract_style`;
`import_ssa.sync_inferred_employment_type()` suy ra từ ngày vào làm theo chuỗi
`thử việc → 1 năm → 3 năm → không xác định`, độ dài từng chặng lấy từ `Employment Type.custom_period`.

⚠ Suy luận, không phải hồ sơ — giả định chuỗi chạy liên tục từ ngày vào làm.

---

## 6. Kiểm chứng

### 6.1. Đã khớp phiếu lương thật

| Ca | Kết quả |
|---|---|
| `TIQN-0148` — đủ dữ liệu | **10/10 dòng**, net **17.430.045** |
| `TIQN-0019` | mọi dòng khớp; OT lệch **537đ (0,017%)** do HR làm tròn khi tách OT/KPI |
| `TIQN-2181` · `TIQN-2231` | ngày công **0,5** khớp HR |
| `TIQN-2236` | ngày công 1,0, lương + phụ cấp khớp từng đồng |

### 6.2. 🔴 Không dùng file Excel/PDF của HR làm thước đo

| Sự thật | Hệ quả |
|---|---|
| HR **chưa dùng ERP**; file là bảng tổng hợp riêng, **đã điều chỉnh tay** | không phải "đáp án đúng" |
| HR dùng **app chấm công khác**, không sync ERP | số giờ, số ngày công khác nguồn |
| HR có dữ liệu nghỉ; **ERP chưa có** | ERP không biết nửa ngày còn lại có lương hay không |

⇒ So từng dòng chỉ đo được **độ lệch dữ liệu nguồn**, không đo được đúng/sai công thức.

### 6.3. Danh sách kiểm khi có đủ dữ liệu

> ⚠ So ngày công dùng ngưỡng **0,01**, không dùng 1 — ngưỡng 1 (hợp cho tiền VNĐ)
> **che mất chênh lệch 0,5 ngày**.

**A. Ngày công**

| # | Kiểm | Kỳ vọng |
|:--:|---|---|
| A1 | Làm 4h + nghỉ phép có lương 4h | `half_day_status = Present` · +1,0 ngày · **đủ lương** |
| A2 | Làm 4h, không có đơn | `half_day_status = Absent` · +0,5 ngày |
| A3 | Nghỉ không lương cả ngày | `On Leave` · `leave_without_pay` tăng · `absent_days` **không** tăng |
| A4 | Ngày lễ không đi làm | vẫn tính công |
| A5 | Ngày công chuẩn từng kỳ | tổng ngày − Chủ Nhật |

**B. Bảo hiểm**

| # | Kiểm | Kỳ vọng |
|:--:|---|---|
| B1 | NV thử việc | không BH, không đoàn phí; có dòng `7.6` |
| B2 | Nghỉ không lương ≥ 14 ngày trong tháng dương lịch | không đóng BH tháng đó |
| B3 | NV làm 1 ngày rồi nghỉ việc | `net_pay` **không âm** |
| B4 | Kỳ chạm 2 tháng dương lịch | xét theo **tháng**, không theo kỳ |

**C. Thuế TNCN**

| # | Kiểm | Kỳ vọng |
|:--:|---|---|
| C1 | NV chính thức, 0 NPT | `TIQN-0148` phải ra **15.923** |
| C2 | Có N người phụ thuộc | giảm trừ thêm N × 6.200.000 |
| C3 | Thử việc, thu nhập ≥ 2.000.000 | **10% cố định**, không giảm trừ gia cảnh |
| C4 | Thử việc, thu nhập < 2.000.000 | **0** |
| C5 | Tiền OT | **miễn thuế** |

**D. Tăng ca**

| # | Kiểm | Kỳ vọng |
|:--:|---|---|
| D1 | OT thường / CN / lễ | 150% / 200% / 300% |
| D2 | OT vượt trần tháng | chuyển sang `4.3 KPI` |
| D3 | Bật/tắt `move_excess_ot_to_kpi` | **tổng tiền không đổi** |
| D4 | Tính lại phiếu nhiều lần | KPI **không nhân đôi** |
| D5 | OT chủ nhật > 4h | tự phát sinh `7.1` tiền cơm 50.000 |

**E. Phụ cấp**

| # | Kiểm | Kỳ vọng |
|:--:|---|---|
| E1 | Ngày công < 8 | chức vụ · PCCC · ATVS · hỗ trợ công đoạn cắt theo ngày công |
| E2 | Ngày công < 14 | nhà ở = **½ tháng** |
| E3 | Ngày công ≥ 8 | các khoản trên nguyên mức |
| E4 | Kỹ thuật · xăng xe · chuyên cần | **luôn** prorate |
| E5 | Căn cứ BH | = tổng 8 khoản; cảnh báo nếu nhập tay lệch |

**F. Khoản trả một lần**

| # | Kiểm | Kỳ vọng |
|:--:|---|---|
| F1 | PC kinh nguyệt ở kỳ ≠ tháng 12 | **cảnh báo** (không chặn) |
| F2 | Quà cưới · phép năm · quyết toán thuế | qua `Additional Salary`, **không** prorate |

---

## 7. Việc cần làm

### 7.1. 🔴 Chặn việc chạy lương thật

| # | Việc | Ghi chú |
|:--:|---|---|
| 1 | **Sync chấm công** từ app HR sang ERP | không thì ngày công luôn lệch |
| 2 | **Nhập dữ liệu nghỉ** (phép · không lương · hưởng BH) | chặn tính nửa ngày và mốc 14 ngày BH |
| 3 | **Lương HĐLĐ ~1.036 NV Active** | mới có 16 người |
| 4 | **Dữ liệu người phụ thuộc** | thuế đang tính 0 NPT ⇒ nhóm lương cao bị tính thừa |

### 7.2. 🔴 Chờ HR chốt

| # | Câu hỏi | Ảnh hưởng |
|:--:|---|---|
| 1 | Dòng `7.6` hoàn 21,5% trả **khi nào**? | ERP trả hàng tháng; file HR để **0** |
| 2 | Thưởng chuyên cần có áp cho NV **thử việc** không? | ERP prorate; file HR để **0** |
| 3 | NV nghỉ việc giữa tháng có vẫn thu **BHYT** không? | file HR thu 102.000 dù không thu BHXH/BHTN |
| 4 | Quy tắc **nửa ngày công** — đưa vào quy chế | hiện là quy tắc bất thành văn |
| 5 | **Thưởng chuyên cần** theo 2 bảng bậc (quy chế mục 1.k) | chưa mô hình hoá |
| 6 | `TIQN-0006` lệch căn cứ BH −773.965 | đang dùng override tạm |

### 7.3. Chưa làm — không chặn

| # | Việc |
|:--:|---|
| 1 | Disable 8 component "dòng tổng" + 7 component rác ERPNext — chưa hại vì không nằm trong structure, nhưng chọn nhầm là cộng tiền hai lần |
| 2 | Thưởng chuyên cần theo 2 bảng bậc — cần API đếm đi trễ/về sớm từ module chấm công |
| 3 | `TIQN-2250` không có phiếu trong Payroll Entry — nghi bộ lọc `date_of_joining <= start_date` |
| 4 | Ngày lễ 2027 — Holiday List đã tạo, chưa khai ngày lễ (chờ lịch nghỉ chính thức) |
| 5 | Dọn Attendance `Absent` rơi vào ngày lễ — thuộc phiên chấm công |
| 6 | `bench migrate` hỏng vì frappe thiếu `pyarrow` (doctype `DuckDB Sync`) — phải dùng `reload_doc` |
| 7 | Print format phiếu lương theo mẫu TIQN (43 dòng, song ngữ) |
| 8 | Bảng kê làm thêm giờ / làm ban đêm — NĐ 253/2026 Đ.26 bắt buộc lập, xuất trình khi cơ quan thuế yêu cầu |
| 9 | `vi.csv` + README — làm sau khi user test OK |

---

## 8. Dữ liệu gốc — 9 phiếu lương kỳ 07/2026 (đã trích, PDF gốc đã xoá)

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


### 8.1. Kiểm chứng công thức trên tập dữ liệu này

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

### 8.2. Hai ca chưa giải thích được bằng dữ liệu này

1. **`TIQN-0006`** — căn cứ BH thật 28.939.100, công thức ra 28.165.135, lệch **−773.965**.
   Nghi "lương trên HĐLĐ" khác dòng Basic trên phiếu, hoặc có phụ cấp ghi 0 trong tháng nhưng
   vẫn có trong hợp đồng. Không chặn — dùng `custom_si_base_override`.
2. **`TIQN-0002` và `TIQN-0044`** — lương cao nhưng PIT = 0. Theo công thức phải nộp
   ~2.625.386 và ~3.697.423; chỉ về 0 nếu có **≥ 4** và **≥ 5** người phụ thuộc.
   HR xác nhận *"họ có nhiều NPT nhưng không có con số cụ thể"* ⇒ củng cố về định tính,
   **không kiểm chứng được bằng số**. PIT giữ mức khớp **7/9 phiếu**.
