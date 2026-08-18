# Quy định nghỉ phép TIQN — TB-TIQN/2025-0018

> **Nguồn:** Thông báo `TB-TIQN/2025-0018` ngày **01/07/2025**, Công ty TNHH Toray
> International Việt Nam – Chi nhánh Quảng Ngãi. Ký: Trưởng chi nhánh **Kitajima Motoharu**
> + Chủ tịch Công đoàn **Lê Thanh Phong**.
> Bản PDF gốc (scan) nằm cùng thư mục này.
>
> **Hiệu lực:** từ ngày ký cho đến khi có thông báo khác thay thế.
> **Đối tượng:** toàn bộ người lao động tại công ty.
>
> 🔴 **Đây là nguồn sự thật cho toàn bộ logic nghỉ phép.** Khi code hoặc tài liệu khác mâu
> thuẫn với file này thì **file này thắng**. Xem [`PLAN_LEAVE_OVERRIDE.md`](PLAN_LEAVE_OVERRIDE.md)
> để biết chỗ nào code đang lệch.

---

## 1. Căn cứ

Nội quy + quy chế công ty hiện hành, và **Luật Bảo hiểm xã hội số 41/2024/QH15**
(sửa đổi, bổ sung, hiệu lực **01/07/2025**).

## 2. Mức hưởng trợ cấp ốm đau do cơ quan BHXH chi trả

Theo **Điều 45 Luật BHXH 41/2024/QH15**, hiệu lực 01/07/2025:

| | Công thức |
|---|---|
| Trợ cấp ốm đau **một ngày** | mức trợ cấp ốm đau **theo tháng ÷ 24** |
| Trợ cấp ốm đau **nửa ngày** | **½** mức trợ cấp một ngày |

> Đây là tiền **cơ quan BHXH** chi trả, **không phải** công ty. Vì vậy ngày nghỉ BHXH có
> `Thời gian tính công = 0` ở bảng mục 3 — công ty không trả lương cho ngày đó.
> Hệ quả trong ERP: các Leave Type nhóm BHXH phải để `is_lwp = 1`.

## 3. Bảng quy định nghỉ phép (phụ lục)

Bốn cột nghiệp vụ, giữ nguyên tên gốc của phụ lục:

- **Thời gian tính công (ngày)** — số ngày công công ty trả lương. Đây chính là phần đóng góp
  vào `payment_days` của Salary Slip.
- **Thể hiện trên bảng công** — mã viết tắt in trên bảng công.
- **Trừ tiền thưởng chuyên cần/tháng** — khấu trừ vào khoản `4.1 Attendance incentive`.
- **Ghi chú**.

### 3.1. Phép năm / *Annual leave*

| Nội dung | Tính công | Mã | Trừ chuyên cần |
|---|:---:|:---:|---|
| Phép năm 1 ngày | **1** | `P` | – |
| Phép năm ½ ngày | **1** | `P/2` | – |

> 🔴 **Nghỉ phép năm nửa ngày vẫn tính công TRỌN 1 NGÀY.** Nửa còn lại đi làm → đủ lương.
> Đây là quy tắc bị code hiểu sai nhiều nhất.

### 3.2. Nghỉ hưởng lương / *Paid leave*

| Nội dung | Tính công | Mã | Trừ chuyên cần |
|---|:---:|:---:|---|
| Ma chay / *Funeral* | **1** | `MC` | – |
| Hỉ sự / *Wedding* | **1** | `HS` | – |
| Khác 1 ngày / *Other 1 day* | **1** | `HL` | – |
| Khác ½ ngày / *Other 1/2 day* | **1** | `HL/2` | – |

### 3.3. Nghỉ không lương / *Unpaid leave*

| Nội dung | Tính công | Mã | Trừ chuyên cần | Ghi chú |
|---|:---:|:---:|---|---|
| Đi trễ / *Late* | **1 − (số giờ nghỉ / 8)** | `<1` | 100.000đ/lần | Làm tròn 1 số thập phân |
| Về sớm / *Leaving early* | **1 − (số giờ nghỉ / 8)** | `<1` | 100.000đ/lần | Làm tròn 1 số thập phân |
| Nghỉ không lương 1 ngày | **0** | `KL` | lần 1: 200.000đ · lần 2: 500.000đ · **lần 3 trở lên: toàn bộ** thưởng chuyên cần | |
| Nghỉ bù / *Compensatory leave* | **0** | `NB` | – | |

### 3.4. Nghỉ hưởng BHXH — trọn ngày / *1-day social insurance leave*

| Nội dung | Tính công | Mã | Trừ chuyên cần |
|---|:---:|:---:|---|
| Nghỉ thai sản / *Maternity* | **0** | `TS` | theo tỷ lệ ngày nghỉ thực tế (**trừ ngày khám thai**) |
| Nghỉ dưỡng sức / *Rest* | **0** | `DS` | theo tỷ lệ ngày nghỉ thực tế |
| Ốm 1 ngày / *1-day sick* | **0** | `O` | theo tỷ lệ ngày nghỉ thực tế |
| Con ốm 1 ngày / *1-day sick child* | **0** | `CO` | theo tỷ lệ ngày nghỉ thực tế |

### 3.5. Nghỉ hưởng BHXH — nửa ngày / *1/2-day social insurance leave*

Nửa ngày BHXH **luôn ghép với** một trạng thái khác cho nửa còn lại. Mã là **tổ hợp**:

| Nửa ngày BHXH + nửa còn lại là… | Tính công | Mã | Trừ chuyên cần |
|---|:---:|:---:|---|
| Ốm + **đi làm** | **0,5** | `O/2` | theo tỷ lệ ngày nghỉ thực tế |
| Con ốm + **đi làm** | **0,5** | `CO/2` | theo tỷ lệ ngày nghỉ thực tế |
| Ốm + **phép năm** | **0,5** | `OP/2` | theo tỷ lệ ngày nghỉ thực tế |
| Con ốm + **phép năm** | **0,5** | `COP/2` | theo tỷ lệ ngày nghỉ thực tế |
| Ốm + **con ốm** | **0** | `OCO/2` | theo tỷ lệ ngày nghỉ thực tế |
| Ốm + **đi trễ/về sớm** (số giờ nghỉ **≤ 1h**) | **0,4** | `OL/2` | 100.000đ/lần — **có giấy bộ phận Y tế xác nhận khám bệnh thì KHÔNG trừ** |
| Con ốm + **đi trễ/về sớm** (≤ 1h) | **0,4** | `COL/2` | 100.000đ/lần |
| Ốm + **không lương** *hoặc* Ốm + đi trễ/về sớm (**1h < giờ nghỉ < 4h**) | **0** | `OK/2` | lần 1: 200.000đ · lần 2: 500.000đ · **lần 3+: toàn bộ** |
| Con ốm + **không lương** *hoặc* Con ốm + đi trễ/về sớm (1h < giờ nghỉ < 4h) | **0** | `COK/2` | lần 1: 200.000đ · lần 2: 500.000đ · **lần 3+: toàn bộ** |

> Ghi chú `OL/2` · `COL/2`: làm tròn 1 số thập phân.

## 4. Phê duyệt và xử lý vi phạm

- Thời gian nghỉ phép **phải có phê duyệt** của quản lý / bộ phận nhân sự.
- Nghỉ **không phép**, tự ý nghỉ mà không có sự chấp thuận → xử lý theo nội quy công ty và
  Bộ luật Lao động hiện hành.

---

## 5. Ánh xạ sang ERP

### 5.1. Leave Type ↔ mã quy định — rà soát 10/08/2026

Đã khai đủ 10 Leave Type, `custom_abbreviation` khớp mã quy định.

| Mã | `is_lwp` | `include_holiday` | `allow_negative` | Tính công | Leave Type |
|:--:|:--:|:--:|:--:|:--:|---|
| `P` | 0 | 0 | **1** | 1 | Phép năm/ Annual leave |
| `MC` | 0 | 0 | **1** | 1 | Paid leave - Ma chay |
| `HS` | 0 | 0 | **1** | 1 | Paid leave - Hỉ sự |
| `HL` | 0 | 0 | **1** | 1 | Paid leave - Nghỉ hưởng lương khác |
| `O` | 1 | 0 | 0 | 0 | BHXH - Ốm đau |
| `CO` | 1 | 0 | 0 | 0 | BHXH - Con ốm |
| `DS` | 1 | **1** | 0 | 0 | BHXH - Nghỉ dưỡng sức |
| `TS` | 1 | **1** | 0 | 0 | BHXH - Thai sản |
| `KL` | 1 | 0 | 0 | 0 | Nghỉ không lương |
| `NB` | 1 | 0 | 0 | 0 | Nghỉ không lương - Nghỉ bù |

✅ **`is_lwp` đúng 10/10** — tái tạo chính xác cột *"Thời gian tính công"* của mục 3.

#### `include_holiday` — ai được tính cả ngày nghỉ

| | Vì sao |
|---|---|
| `TS` = 1 | Thai sản nghỉ **liên tục**, tính cả Chủ Nhật và ngày lễ |
| **`DS` = 1** | Luật BHXH: thời gian nghỉ **dưỡng sức, phục hồi sức khoẻ** *"bao gồm cả ngày nghỉ lễ, nghỉ Tết, ngày nghỉ hằng tuần"* |
| `O` · `CO` = 0 | Ốm đau tính theo **ngày làm việc**, không kể lễ/Tết/nghỉ hằng tuần |
| còn lại = 0 | nghỉ theo ngày làm việc |

> 🔴 `DS` trước đây để **0**, khiến 15 dòng dưỡng sức rơi vào Chủ Nhật/ngày lễ **không tạo được**
> đơn nghỉ (HRMS tính ra 0 ngày rồi `throw`). Đã sửa 10/08/2026 — cần thiết vì `DS` là **căn cứ
> đối chiếu với phần BHYT/BHXH chi trả cho người lao động**, phải theo dõi đủ số ngày dù không
> ảnh hưởng tiền lương.

#### `allow_negative` — nghỉ phát sinh không có quota năm

`HS` · `MC` · `HL` là nghỉ **cấp theo sự việc** (cưới, tang, việc khác), **không có quy tắc
mỗi năm bao nhiêu ngày** như phép năm ⇒ không lập Leave Allocation. Nhưng
`validate_dates_across_allocation()` (`leave_application.py:203-214`) chỉ chạy cho loại
`is_lwp = 0` và chỉ thoát sớm khi `allow_negative = 1` — để 0 thì **mọi đơn đều bị chặn**
*"Application period cannot be outside leave allocation period"*.

⇒ đặt `allow_negative = 1` cho ba loại đó, giống `P`. Nhóm `is_lwp = 1` không cần vì HRMS
bỏ qua kiểm số dư cho chúng.

#### Còn tồn — chưa đổi, cần HR chốt

| Mã | Field | Hiện tại | Ghi chú |
|---|---|:--:|---|
| `MC` | `max_leaves_allowed` | 0 | BLLĐ Đ.115: tang cha/mẹ/vợ/chồng/con **3 ngày**. `HS` đã đặt 3 |
| `DS` | `max_leaves_allowed` | 0 | Luật BHXH: **5–10 ngày/năm** |
| `O` | `max_leaves_allowed` | 0 | Ốm đau 30/40/60 ngày tuỳ thâm niên đóng BH — một con số không đủ diễn tả |
| `P` | `applicable_after` | **30** | NV mới phải làm 30 ngày mới được nghỉ phép; quy chế **không nói** điều này |
| tất cả | `earned_leave_frequency` | Monthly | Chỉ có tác dụng khi `is_earned_leave = 1` (chỉ `P`). Vô hại nhưng gây hiểu nhầm |

> `max_leaves_allowed` chỉ có hiệu lực khi có Leave Allocation. Với `allow_negative = 1` và
> không cấp allocation thì nó chỉ mang tính tham khảo.

#### Phép năm — tích luỹ theo tháng

`Phép năm` là **earned leave** (`is_earned_leave = 1`, `Monthly`, `allocate_on_day = 15th of
Month`, `max_leaves_allowed = 14`), cộng **+1 ngày mỗi 5 năm thâm niên** (BLLĐ Đ.114).

> 🔴 **Nguồn sự thật cho phần này là [`earned_leave_override.md`](../earned_leave/earned_leave_override.md)**
> (cập nhật 15/08/2026), kèm `test_earned_leave_law.py` — 47 assert. Mục dưới đây chỉ tóm tắt để
> đọc liền mạch với quy định nghỉ phép; **khi hai bên lệch thì file kia thắng**.

##### Ba quy tắc

**① Tháng nào được tính là "01 tháng làm việc"** — Điều 65 khoản 2 NĐ 145/2020: làm
**≥ 50% số ngày làm việc bình thường** của tháng đó. Hiện thực tất định:

> Tháng được tính **⟺** người lao động **còn trong biên chế vào NGÀY 15** của tháng đó.

| | Ngày 15 có trong biên chế? | Tính tháng |
|---|---|---|
| Vào làm 15/01 | có | **CÓ** |
| Vào làm 16/01 | không | **KHÔNG** |
| Nghỉ việc 20/01 | có | **CÓ** |
| Nghỉ việc 10/01 | không | **KHÔNG** |

Mốc này trùng khít `allocate_on_day = "15th of Month"`, nên ngày xét điều kiện và ngày cấp là
**một**. Code: `is_working_month()` · `count_qualifying_months()`.

**② Mức một tháng** = `annual / 12`, giữ **2 chữ số** (14 → **1,17**). **Không** làm tròn ở
từng tháng — luật làm tròn trên **tổng cả kỳ**, làm tròn từng tháng sẽ tích luỹ sai số.
Code: `get_monthly_rate()`.

**③ Tổng quyền lợi** = `LÀM_TRÒN_LUẬT( annual/12 × số tháng đủ điều kiện )` — Điều 113 khoản 2
BLLĐ 2019 (chưa đủ 12 tháng thì tính theo tỷ lệ) + Điều 66 NĐ 145/2020 (thập phân **≥ 0,5 lên
1 ngày**, `< 0,5` cắt bỏ). Kỳ cấp cuối gánh phần dư để tổng khớp tuyệt đối.
Code: `get_period_entitlement()` · `round_leaves_by_law()`.

⚠ `round_leaves_by_law()` **không** dùng `round()` của Python — đó là làm tròn ngân hàng
(`round(2.5)` ra **2**), sai luật đúng một nửa số trường hợp `.5`.

##### Thử việc — HOÃN cấp, KHÔNG mất

Trong thử việc không cấp và không cho dùng phép. Hết thử việc thì **truy thu toàn bộ** các tháng
đã đủ điều kiện, cấp gộp vào kỳ cấp đầu tiên sau đó.

| Nhận việc | Thử việc | Tháng đầu tính? | Kỳ cấp đầu | Truy thu |
|---|---|---|---|---|
| ≤ 15 | 30 ngày | **CÓ** | 15 của tháng 2 | T1 + T2 |
| > 15 | 30 ngày | **KHÔNG** | 15 của tháng 3 | T2 + T3 |
| ≤ 15 | 60 ngày | **CÓ** | 15 của tháng 3 | T1 + T2 + T3 |
| > 15 | 60 ngày | **KHÔNG** | 15 của tháng 4 | T2 + T3 + T4 |

Số ngày thử việc lấy từ `Employee.custom_probation_days`, thiếu thì fallback
`Leave Type.applicable_after` (= 30).

##### ❌ Hai lỗi của bản trước (10/08/2026) — đừng làm lại

Bản 10/08/2026 dùng `floor(annual/12, 1)` = **1,1** và cho **kỳ tháng 12 gánh phần chênh vô điều
kiện**. Cả hai đều sai, sai về **hai phía ngược nhau**:

| Lỗi | Hậu quả |
|---|---|
| Mức tháng `1,1` thay vì `1,17` | thiếu 0,067 ngày/tháng, chỉ bù ở tháng 12 ⇒ **ai nghỉ việc trước tháng 12 là mất thật** |
| `_true_up_december()` đặt tháng 12 = `annual − tổng các kỳ khác` **không xét số tháng** | người làm **5 tháng vẫn nhận đủ 14 ngày**. Đo production 15/08/2026: **379 NV, thừa ~2.022 ngày** |

Cũng đừng dùng lại `count_worked_days_in_month() >= 14` (đếm **ngày dương lịch**): tháng 31
ngày, vào làm 16/17/18 vẫn đủ 14 ngày dương lịch nhưng chỉ làm **48%** số ngày làm việc — trái
quy tắc ≥50%. Ví dụ thật: DOJ **17/07/2026** có 15 ngày dương lịch nhưng chỉ **13/27 = 48%**
ngày làm việc ⇒ **không** tính tháng 7.

#### `KL` rơi vào ngày nghỉ — chấp nhận tính 0

2 dòng `KL` rơi vào Chủ Nhật. `KL` **không ảnh hưởng tiền lương** (đã là 0 ngày công) nên
để `include_holiday = 0` và chấp nhận 2 dòng đó không tạo đơn — không đổi cấu hình.

### 5.2. Nửa ngày — quy tắc `half_day_status`

HRMS tính `payment_days` cho một ngày `Half Day` bằng **hai** nguồn trừ độc lập:

| Nguồn | Điều kiện | Trừ |
|---|---|---|
| `calculate_lwp_ppl_and_absent_days_based_on_attendance()` (`salary_slip.py:790`) | `status = Half Day` **và** `leave_type.is_lwp = 1` | 0,5 |
| `get_half_absent_days()` (`salary_slip.py:578`) | `status = Half Day` **và** `half_day_status = 'Absent'` | 0,5 |

Từ đó suy ra quy tắc duy nhất tái tạo đúng cả 9 dòng mục 3.5:

```
leave_type        = nửa ngày thuộc nhóm is_lwp = 1  (BHXH / không lương)
half_day_status   = 'Present'  nếu nửa còn lại ĐƯỢC CÔNG TY TRẢ LƯƠNG
                    'Absent'   nếu không
```

Nửa còn lại được công ty trả lương khi: **có checkin** (đi làm), **hoặc** là nghỉ phép có lương
(`P` · `MC` · `HS` · `HL`, tức `is_lwp = 0`).

Đối chiếu từng dòng:

| Mã | `leave_type` | nửa còn lại | `half_day_status` | payment_days | Quy định |
|---|---|---|:---:|:---:|:---:|
| `P/2` | `P` (lwp=0) | đi làm | Present | 1 | 1 ✅ |
| `HL/2` | `HL` (lwp=0) | đi làm | Present | 1 | 1 ✅ |
| `O/2` | `O` (lwp=1) | đi làm | Present | 0,5 | 0,5 ✅ |
| `CO/2` | `CO` | đi làm | Present | 0,5 | 0,5 ✅ |
| `OP/2` | `O` | phép năm (**trả lương**) | Present | 0,5 | 0,5 ✅ |
| `COP/2` | `CO` | phép năm | Present | 0,5 | 0,5 ✅ |
| `OCO/2` | `O` | con ốm (lwp=1) | Absent | 0 | 0 ✅ |
| `OK/2` | `O` | không lương | Absent | 0 | 0 ✅ |
| `COK/2` | `CO` | không lương | Absent | 0 | 0 ✅ |

> 🔴 **`OP/2` là dòng bẻ mọi giả định đơn giản.** Cả ngày **không có checkin nào**, nhưng
> `half_day_status` vẫn phải là `Present` vì nửa còn lại là phép năm có lương.
> Quy tắc "không checkin → Absent" là **sai** ở đúng dòng này.

### 5.3. 🔴 Ba dòng ERP CHƯA thể hiện được

`Attendance.status` của HRMS chỉ có `1 / 0,5 / 0` ngày. Ba dòng sau cần **ngày công lẻ**:

| Mã | Tính công | Vì sao HRMS không làm được |
|---|:---:|---|
| Đi trễ | `1 − giờ nghỉ/8` → vd **0,9** | không có trạng thái ngày công phân số |
| Về sớm | `1 − giờ nghỉ/8` | như trên |
| `OL/2` · `COL/2` | **0,4** | như trên |

→ Phải xử lý ở **tầng khoản lương** (Salary Component / Additional Salary), **không** ở
`Attendance.status`. `late_entry` / `early_exit` đã có sẵn trên Attendance để làm đầu vào.

### 5.4. Trừ thưởng chuyên cần — bảng bậc

Quy định cho **hai** thang trừ, cộng dồn với thang đi trễ/về sớm của quy chế lương:

| Nhóm | Lần 1 | Lần 2 | Lần 3+ |
|---|---|---|---|
| Đi trễ / Về sớm / `OL/2` / `COL/2` | 100.000đ | 100.000đ | 100.000đ (mỗi lần) |
| Nghỉ không lương (`KL`, `OK/2`, `COK/2`) | 200.000đ | 500.000đ | **toàn bộ** thưởng chuyên cần |
| Nghỉ BHXH (`TS` `DS` `O` `CO` và các mã `/2`) | theo **tỷ lệ ngày nghỉ thực tế** | | |

Miễn trừ: `OL/2` **không bị trừ** nếu có giấy bộ phận Y tế xác nhận đi khám bệnh.
Thai sản: **không trừ** cho ngày đi khám thai.

> Đây là dữ liệu mà `4.1 Attendance incentive` đang thiếu — hiện khoản này chỉ prorate theo
> ngày công. Xem `overrides/payroll_docs/PLAN_ATTENDANCE_VS_QUYCHE.md` mục A4.
