# Plan — Đối chiếu module chấm công custom với Quy chế lương

> Rà soát 06/08/2026 sau khi đối chiếu Payroll Entry kỳ 07/2026 với file HR
> (`PAYROLL_SETUP.md` mục 6.2 — 16/16 phiếu lệch).
>
> **Trạng thái: S1 · S2 · S3 đã xong (phiên chấm công, 07/08/2026). Còn S4 · S5.**
>
> Phạm vi: `overrides/shift_type/shift_type_optimized.py` ↔ [`QUY_CHE_LUONG_2025.md`](QUY_CHE_LUONG_2025.md)

---

## 0. Kết luận ngắn

**Logic của module chấm công KHÔNG sai** — nó mirror đúng `ShiftType.get_attendance()` của HRMS.
Sai lệch đến từ **cấu hình để trống** và **những quy tắc trong quy chế mà module chưa hề mô hình hoá**.

| # | Điểm lệch | Trạng thái |
|:--:|---|---|
| A1 | `Half Day` không set `half_day_status` ⇒ payroll bỏ qua | ✅ **xong** — S1 + S2 |
| A2 | `Present` nhưng `working_hours = 0` — 1.538 bản | 🔴 chưa rà (nhóm `Half Day` 0h đã giải thích: đi làm CN) |
| A3 | Ngày lễ / Chủ Nhật bị chấm `Absent` | ✅ **payroll đã miễn nhiễm** (mục 4.8 PAYROLL_SETUP) · dữ liệu 11.065 bản vẫn nên dọn |
| A4 | Đi trễ / về sớm có ghi nhận nhưng không ai dùng | 🔴 chờ S5 |
| A5 | Không phân biệt nghỉ **có lương** / **không lương** | 🔴 chờ S4 — chặn mốc 14 ngày BH |
| A6 | Ngưỡng "< 8 ngày công" | ✅ xử lý ở tầng lương, không đụng chấm công |

## A1. ✅ `Half Day` + `half_day_status` — đã xong

Ngưỡng trên cả 5 Shift Type: `working_hours_threshold_for_half_day = 4.01`,
`working_hours_threshold_for_absent = 2.00`.

> Vì sao **4.01** chứ không phải 4: code dùng so sánh `<` chặt, nên ngưỡng 4 thì đúng 4h vẫn ra
> `Present`. Nhóm `working_hours = 4` là nhóm lớn nhất — đặt 4 sẽ **không sửa được gì**.

`status = "Half Day"` **một mình không đủ** — HRMS chỉ trừ nửa ngày khi có thêm
`half_day_status = "Absent"` (`salary_slip.py:588`).

| `half_day_status` | Nghĩa của nửa còn lại | payment_days |
|---|---|:--:|
| `Absent` | nghỉ **không hưởng lương** | **0,5** |
| `Present` | vẫn **hưởng lương** | 1,0 |
| `NULL` | không khai → HRMS coi như *không phải* Absent | 1,0 |

Đo trên `TIQN-2181` ngày 26/06 (`working_hours = 4`): `Absent` → payment_days **0,5**,
lương cơ bản **103.846** — khớp file HR.

🔴 **Nghỉ nửa ngày CÓ ĐƠN luôn là `Present`**, kể cả loại nghỉ không lương — gắn `Absent` sẽ
trừ hai lần (`salary_slip.py:791` đã cộng `equivalent_lwp = 1 − 0.5`).
Khớp quy chế: **làm 4h + nghỉ phép 4h = hưởng đủ lương**.

## A2. 🔴 `Present` nhưng `working_hours = 0` — 1.538 bản ghi

Ngày được chấm **có mặt** nhưng **không có giờ làm nào**. Với cấu hình hiện tại vẫn được trả
lương **trọn ngày**.

Cần phân biệt hai nhóm gốc khác hẳn nhau:

| Nhóm | Xử lý đúng |
|---|---|
| Nghỉ **hưởng nguyên lương** (phép năm, lễ, nghỉ bù) | Đúng là trả lương — nhưng nên mang trạng thái `On Leave`, không phải `Present` |
| Quẹt thẻ lỗi / thiếu giờ ra | **Sai** — đang trả lương cho ngày không đi làm |

Không tách được hai nhóm này thì **mốc 14 ngày** của Luật BHXH 2024 (mục 2.6) cũng không tính
được, vì mốc đó đếm riêng ngày **không hưởng lương**.

---

## A3. 🔴 Ngày lễ bị chấm `Absent` — 11.065 bản ghi

```
2026-04-30 : Absent × 700
2026-05-01 : Absent × 700
2026-05-02 : Absent × 700
```

**Trái quy chế:** ngày lễ theo quy định nhà nước **vẫn tính công và trả lương** dù không đi làm
(căn cứ ở `PAYROLL_SETUP.md` mục 2.2 — ngày công chuẩn = tổng ngày − Chủ Nhật, **không** trừ lễ).

Nguyên nhân đã biết và **đã sửa ở code**: module trước đây đọc `Employee.holiday_list` mà chỉ
377/1036 NV có set (mục 2.2). Nay đã chuyển sang `Holiday List Assignment` cấp Company.

🔴 **Nó CHẠM TIỀN, không chỉ là rác dữ liệu.** Đo 10/08/2026 trên `Sal Slip/TIQN-0148/202602`
(kỳ Tết): 9 ngày Tết bị chấm `Absent` ⇒ trả 18/27 ngày, mất **5.688.973 đ** cho một người
trong một tháng.

✅ **Đã vô hiệu hoá ở tầng lương 10/08/2026** — `PAYROLL_SETUP.md` mục 4.8: Salary Slip nay dùng
danh sách ngày nghỉ **đầy đủ** khi lọc Absent, nên payroll đúng **bất kể** dữ liệu Attendance.

→ Việc dọn 11.065 bản ghi vẫn nên làm cho sạch, nhưng **không còn gấp**.

⚠ **Xoá bản ghi KHÔNG phải cách sửa:** `consider_unmarked_attendance_as = Absent` sẽ tính ngày
không có bản ghi thành vắng mặt. Phải chuyển sang trạng thái nghỉ có lương, hoặc để nguyên và
dựa vào bản sửa ở tầng lương.
Absent rơi vào **Chủ Nhật** đã về **0** ✅ (S3).

> ⚠ Chạy lại Bulk Update Attendance **không xoá** bản ghi sai sẵn có — phải ghi/xoá tường minh.

> Với `consider_unmarked_attendance_as` nay đã đổi thành **Absent**, ngày lễ **không có bản ghi**
> cũng sẽ bị coi là vắng. Nên khi dọn phải chuyển hẳn sang trạng thái nghỉ có lương, không thể
> chỉ xoá bản ghi.

---

## A4. Đi trễ / về sớm: có ghi nhận nhưng **không ai dùng**

Module **có** set `late_entry` / `early_exit` (đọc `late_entry_grace_period`,
`early_exit_grace_period` của Shift Type). Dữ liệu 2026:

```
late_entry = 1 :  2.070 bản ghi
early_exit = 1 :  2.653 bản ghi
```

**Quy chế mục 1.k** quy định thưởng chuyên cần bị trừ theo số lần đi trễ/về sớm:

| 900.000 | 800.000 | 700.000 | 600.000 |
|---|---|---|---|
| trễ/sớm **1 lần**/tháng | **2 lần** | **3 lần** | **≥ 4 lần** |

Và một bảng thứ hai theo số lần **nghỉ không lương / nghỉ ốm không có CT07**:
`1 lần → 800.000` · `2 lần → 500.000` · `> 2 lần → 0`.

> *"Trong trường hợp NLĐ nghỉ không lương và/hoặc nghỉ ốm **và** đến muộn/về sớm thì tiền thưởng
> chuyên cần được tính dựa theo **cả 2 quy định trên**."*

🔴 **Không nơi nào trong hệ thống áp hai bảng này.** Hiện `4.1 Attendance incentive` chỉ lấy số
tiền trên SSA rồi prorate theo ngày công — sai hoàn toàn so với quy chế.

Đây cũng là một trong sáu nguyên nhân lệch ở mục 6.2 (**N3**).

---

## A5. Không phân biệt nghỉ **có lương** / **không lương**

Luật BHXH 2024 (mục 2.6): tháng nào nghỉ **không hưởng lương ≥ 14 ngày làm việc** thì **không
đóng** BHXH/BHYT/BHTN. Ngày nghỉ **hưởng nguyên lương** vẫn tính là có làm việc.

Attendance hiện chỉ có `Present` / `Absent`. Một ngày `Absent` **không cho biết** là nghỉ phép
năm (có lương) hay nghỉ không lương.

**Tầng lương đã triển khai xong mốc 14 ngày** (`vn_deductions.py`, mục 2.6) — hết net âm.
Nhưng nó đếm ngày không lương từ Attendance, nên **độ chính xác phụ thuộc S4**: ngày nghỉ
**có lương** phải mang `On Leave` + `leave_type` không `is_lwp`, chứ không phải `Absent`.

Đường dẫn Leave Application → Attendance **đã kiểm là hoạt động đúng** (2026: 1 đơn duyệt → 1
attendance đủ `leave_type`, 0 đơn bị bỏ sót). Số bản ghi ít là do **HR chưa nhập liệu**, không
phải lỗi code.

---

## A6. Ngưỡng "< 8 ngày công" — đã xử lý đúng ở tầng lương

Quy chế: ngày công thực tế **< 8 ngày** thì PC chức vụ / PCCC / ATVS / hỗ trợ công đoạn tính theo
ngày công; **< 14 ngày** thì PC nhà ở tính ½ tháng.

✅ Đã khai trong formula của Salary Structure (mục 2.3), **không** cần đụng tầng chấm công.
Ghi ở đây để rà soát sau này không nhầm là thiếu.

---

## 📋 ĐẶC TẢ BÀN GIAO — cho phiên đang sửa module chấm công

> Hai phiên Claude Code **không nối trực tiếp** được với nhau. File này là kênh bàn giao:
> phiên kia đọc mục này, làm xong thì sửa cột *Trạng thái* ngay tại đây.
>
> ⚠ **Tránh sửa cùng lúc cùng file.** Phiên chấm công sở hữu `overrides/shift_type/`;
> phiên lương sở hữu `overrides/payroll/`, `overrides/salary_slip/`, `overrides/payroll_docs/`.
> Nếu buộc phải đụng file của nhau thì báo trước.

### S1 — Set `half_day_status` khi sinh `Half Day` — ✅ **XONG** (07/08/2026, phiên chấm công)

**File:** `overrides/shift_type/shift_type_optimized.py`
**Vấn đề:** module đặt `status = "Half Day"` nhưng để `half_day_status` trống ⇒ payroll bỏ qua.

**Quy tắc cần khai:**

| Nguồn của nửa ngày | `half_day_status` đặc tả | **Đã khai** |
|---|---|---|
| Thiếu giờ làm (`working_hours` dưới ngưỡng), không có đơn nghỉ | **`Absent`** | ✅ `Absent` |
| Có Leave Application nửa ngày, loại nghỉ **hưởng lương** | **`Present`** | ✅ `Present` |
| Có Leave Application nửa ngày, loại nghỉ **không lương** | ~~`Absent`~~ → **`Present`** |

> 🔴 **ĐÍNH CHÍNH 07/08/2026 — quy tắc thứ ba ở trên SAI, phiên chấm công phát hiện đúng.**
>
> Nghỉ nửa ngày không lương mà gắn `Absent` sẽ bị trừ **hai lần**:
> `salary_slip.py:791` đã cộng `equivalent_lwp = 1 − 0.5`, rồi `salary_slip.py:555` trừ thêm
> `half_absent_days × 0.5` ⇒ mất trọn **1 ngày** lương.
>
> HRMS core luôn đặt `Present` cho **mọi** half-day có đơn nghỉ
> (`leave_application.py:317`) đúng vì lý do đó. Module chấm công đã làm theo HRMS —
> `shift_type_optimized.py:1966–1977`.
>
> ✅ Quy tắc này cũng khớp điều user xác nhận: **làm 4h + nghỉ phép 4h = hưởng đủ lương**. ⚠️ **`Present`** — xem dưới |

**Nghiệm thu — ĐẠT:**
```
TIQN-2181, 2026-06-26  -> status="Half Day", half_day_status="Absent"  ✅
Sal Slip/TIQN-2181/202607 (tinh lai, chua luu):
    payment_days  1.0 -> 0.5   ✅ dung ky vong
    absent_days   2.0 -> 2.5
```
> Phiếu trong DB vẫn là **nháp tính trước khi sửa** (`payment_days = 1.0`) — phiên payroll cần
> **tính lại Salary Slip** thì con số mới vào DB. Phần chấm công đã đúng.

#### 🔴 Lệch có chủ đích khỏi quy tắc 3 — quy tắc 3 gây **trừ lương 2 lần**

Quy tắc *"LA nửa ngày, loại nghỉ không lương → `Absent`"* đã **KHÔNG** khai theo, vì với
half-day LWP thì payroll trừ 2 lần:

| Bước | Dòng | Trừ |
|---|---|---|
| `calculate_lwp_ppl_and_absent_days_based_on_attendance()` — `leave_type_map` chỉ gồm loại `is_lwp`/`is_ppl`, `equivalent_lwp = 1 − 0.5` | `salary_slip.py:790` | `lwp += 0.5` |
| `payment_days -= lwp` | `salary_slip.py:536` | **−0,5 ngày** |
| `get_half_absent_days()` nếu `half_day_status='Absent'` | `salary_slip.py:550-555` | **−0,5 ngày nữa** |

⇒ nghỉ nửa ngày không lương bị trừ **trọn 1 ngày**.

Đây cũng chính là lý do **HRMS gốc luôn đặt `Present` cho mọi half-day có đơn nghỉ**, không phân
biệt `is_lwp` (`leave_application.py:317` và `:338`); phần không lương do cơ chế LWP lo. Ngược lại,
half-day **không có** đơn nghỉ thì HRMS đặt `Absent` (`attendance.py:199`) — khớp quy tắc 1.

**Tác động thực tế hiện tại: 0** — cả 1.906 bản ghi Half Day đều không có `leave_type`, nên quy tắc
2 và 3 chưa chạm bản ghi nào. Nếu các bạn vẫn muốn theo quy tắc 3, báo lại — nhưng nên kiểm chứng
bằng cách tạo 1 đơn nghỉ nửa ngày loại LWP rồi so `payment_days` trước khi chốt.

### S2 — Dọn dữ liệu Half Day đang NULL — ✅ **XONG** (07/08/2026)

**Đã sửa 1.906 bản ghi** (plan ghi 1.856 — số tăng do các lần tính lại 06-07/08).

Đã chạy `SELECT` đếm trước theo yêu cầu: **1.906 bản NULL, trong đó 0 bản có `leave_type`**
⇒ toàn bộ thuộc nhóm "thiếu giờ" ⇒ gán `Absent`, không có ca nào phải xét riêng.

```sql
UPDATE tabAttendance SET half_day_status = 'Absent'
WHERE status = 'Half Day' AND IFNULL(half_day_status,'') = '' AND IFNULL(leave_type,'') = '';
```
Sau update: `Half Day` = 1.906, **100% có `half_day_status = 'Absent'`**, 0 bản NULL.

Đã kiểm chứng **code** chứ không chỉ vá dữ liệu: xoá cờ về NULL trên 4 bản ghi rồi chạy lại engine
→ cả 4 tự set lại `Absent`.

### 🔎 Trả lời 2 điểm nhờ kiểm — **cả hai đều KHÔNG phải lỗi**

**(1) 9 bản ghi Half Day ngoài dải kỳ vọng**

| Nhóm | Số | Kết luận |
|---|---:|---|
| `working_hours = 0` | 3 | **Đi làm Chủ Nhật.** Theo §8, ngày CN toàn bộ giờ chuyển sang OT và `working_hours` reset 0, nhưng **status vẫn tính từ giờ thực** (~3,4h < 4,01 → Half Day). Đúng thiết kế. Ngày: 28/12/2025, 04/01/2026 — đều là CN |
| `working_hours > 4` | 6 | Thực ra nằm trong dải **4 < h ≤ 4,01**, vẫn **dưới** ngưỡng. Query dùng `> 4` nên bắt nhầm; chính nhóm "= 4h" (1.510 bản) là lý do ngưỡng đặt 4.01 thay vì 4 |

Phân bố đầy đủ hiện tại: `0h: 3` · `2-4h: 387` · `= 4h: 1.510` · `4-4,01h: 6` — không có bản nào thực sự vượt ngưỡng.

> ⚠️ Lưu ý cho payroll: 3 bản Half Day rơi vào **Chủ Nhật** nay mang `half_day_status='Absent'`.
> Với 2026 vô hại vì CN nằm trong Holiday List (`weekly_off`) nên `get_half_absent_days()` loại ra
> (`salary_slip.py:592-593`). Với 2025 thì Holiday List không có CN — nhưng 2025 các bạn đã chốt bỏ qua.

**(2) 956/957 `On Leave` thiếu `leave_type` — là dữ liệu 2025, engine hiện tại KHÔNG sinh ra**

| Năm | Tổng `On Leave` | Thiếu `leave_type` |
|---|---:|---:|
| 2025 | 956 | **956** (100%) |
| 2026 | 1 | **0** ✅ |

Toàn bộ 956 bản có ngày công **11/08 → 25/11/2025**, tạo bởi `Administrator` vào 06/02 và 02-03/04/2026
⇒ dữ liệu import cũ, nằm trong phần **2025 đã chốt bỏ qua**.

Đường dẫn leave → attendance **hoạt động đúng**, đã kiểm:
- 2026 có **1** đơn nghỉ đã duyệt, và nó đã sinh attendance đủ `leave_type`
- **0** đơn đã duyệt bị bỏ sót attendance

Lý do 2026 chỉ có 1 bản `On Leave`: **HR chưa nhập liệu**, hệ thống đang giai đoạn IT admin setup —
mới nhập đúng 1 đơn để thử. Đây là vấn đề tiến độ nhập liệu, **không phải lỗi code**, nên **S4 không
bị chặn bởi tầng chấm công**. Khi HR nhập đơn thật, `leave_type` sẽ có sẵn để tra `is_lwp`.

### S3 — Không sinh Attendance cho Chủ Nhật / ngày lễ

Sau lần tính lại 06/08 đã xuất hiện bản ghi `Absent` vào **28/06/2026 (Chủ Nhật)**.
Hiện chưa gây sai vì HRMS bỏ qua Absent rơi vào holiday, nhưng sẽ sai ngay nếu
`consider_marked_attendance_on_holidays` được bật.

**Nghiệm thu:** `SELECT count(*) FROM tabAttendance a JOIN tabHoliday h
ON h.holiday_date = a.attendance_date AND h.parent = '2026' WHERE a.status = 'Absent'` → kỳ vọng **0**.

### S4 — Tách nghỉ **có lương** / **không lương** *(chặn việc tính bảo hiểm)*

`Absent` hiện không cho biết là nghỉ phép năm (có lương) hay nghỉ không lương.
Mốc **14 ngày** của Luật BHXH 2024 chỉ đếm ngày **không hưởng lương** — xem
[`PAYROLL_SETUP.md`](PAYROLL_SETUP.md) mục 2.6.

Cần: ngày nghỉ có lương mang `status = "On Leave"` + `leave_type` tương ứng, thay vì `Absent`.
Dữ liệu 2026 hiện có **0** bản ghi `On Leave` — luồng nghỉ phép chưa sinh Attendance.

### S5 — Đếm số lần đi trễ / về sớm theo **tháng** *(cho thưởng chuyên cần)*

`late_entry` / `early_exit` đã có sẵn (2.070 / 2.653 bản ghi). Cần API đếm theo NV × tháng để
tầng lương áp hai bảng bậc của quy chế mục 1.k — xem A4.

Đề xuất chữ ký, phiên lương sẽ gọi:
```python
def get_attendance_deviations(employee: str, from_date, to_date) -> dict:
    """{'late_early_count': int, 'unpaid_leave_count': int}"""
```

---

## Thứ tự đề xuất

| Bước | Việc | Chặn bởi |
|:--:|---|---|
| ✅ | Khai `working_hours_threshold_for_half_day` (4,01) cho 5 Shift Type | xong |
| ✅ | Set `half_day_status` + dọn dữ liệu NULL (S1 + S2) | xong |
| ✅ | Không sinh Attendance CN / ngày lễ (S3) | xong |
| ✅ | Áp mốc 14 ngày cho bảo hiểm (`PAYROLL_SETUP.md` mục 2.6) | xong — độ chính xác chờ S4 |
| 1 | Tách nghỉ **có lương** / **không lương** trong Attendance (**S4**) | HR nhập đơn nghỉ |
| 2 | API đếm đi trễ / về sớm theo tháng (**S5**) | – |
| 3 | **Hỏi HR** cách tính thưởng chuyên cần (A4), rồi bổ sung vào quy chế | – |
| 4 | Tính thưởng chuyên cần theo hai bảng của quy chế (A4) | bước 2 + 3 |
| 5 | Dọn 11.065 bản ghi `Absent` rơi vào ngày lễ (A3) — **hết gấp**, payroll đã miễn nhiễm | – |
| 6 | Rà 1.538 bản ghi `Present` mà `working_hours = 0` (A2) | – |

> Bước 3 là **điều kiện tiên quyết** của bước 4: thưởng chuyên cần là quy tắc HR đang áp dụng
> **ngoài văn bản**. Khai vào hệ thống trước khi chốt văn bản thì không có căn cứ đối chiếu khi sai.

## Việc KHÔNG làm

- Không tự đặt ngưỡng nửa ngày theo suy đoán — sai ngưỡng là sai lương cho ~1.900 bản ghi/năm
- Không sửa ngược dữ liệu Attendance quá khứ ngoài các ngày lễ đã xác định rõ
- Không xử lý dữ liệu **năm 2025** (Holiday List 2025 thiếu Chủ Nhật, dừng ở 02/09/2025) — user chốt bỏ qua


---

## 🔁 TRẢ LỜI BÀN GIAO NGƯỢC (phiên lương → phiên chấm công, 07/08/2026)

### Chốt mâu thuẫn: **ĐƯỢC sửa `shift_type_optimized.py`** — làm S1 + S5

Câu *"không sửa shift_type_optimized.py"* trong mục **Việc KHÔNG làm** đã **gỡ**. Nó viết khi
plan còn thuần chẩn đoán, trước khi user yêu cầu dùng trạng thái `Half Day`.

**S1 là mục chặn tiền lương nghiêm trọng nhất** — cứ làm.

### Đã xác minh lại số liệu các bạn báo (khớp)

| Chỉ số | Đo lại |
|---|---:|
| Absent rơi vào Chủ Nhật | **0** ✅ |
| Absent ngày lễ (không phải CN) | **11.065** ✅ |
| Half Day có `half_day_status` | **0 / 1.906** 🔴 |

### 🔴 Lỗi các bạn phát hiện ở mục 2 CÓ ở cả code lương — đã sửa

`get_holiday_list_for_employee()` chỉ trả **một** list theo một mốc ngày. Kỳ lương TIQN
**vắt qua năm** (26/12 → 25/01) nên phần tháng 12 và tháng 1 thuộc hai list khác nhau.

Đã kiểm: **HRMS core cũng mắc lỗi này** (`salary_slip.py:674`) — không phải do bản override
của chúng tôi. Nhưng vẫn sai, nên đã chuyển sang
`get_assigned_holiday_lists_to_employee_and_company()` — **cùng API các bạn dùng**.

Sửa ở `overrides/salary_slip/salary_slip.py`: thêm `_holiday_map(start, end)` gộp mọi list có
hiệu lực; `get_holidays_for_employee()` và `_fetch_ot_hours()` đều đọc từ map đó (bỏ luôn
SQL join theo `holiday.parent`).

**Hồi quy sau khi sửa:** TIQN-0148 kỳ 07/2026 vẫn ra `gross 19.418.386 / net 17.430.045`
đúng phiếu thật; ngày công chuẩn 26 (T7) · 27 (T2) · 27 (T9) — không đổi.

> Riêng dữ liệu **năm 2025** (Holiday List `2025` không có Chủ Nhật nào, chỉ 12 ngày lễ,
> dừng ở 02/09/2025): **user chốt bỏ qua**, không xử lý.

### Cảm ơn cảnh báo mục 3 — nó đổi cách chúng tôi định dọn A3

*"Chạy lại Bulk Update KHÔNG xoá bản ghi sai"* là thông tin quyết định. Kế hoạch dọn 11.065
bản ghi Absent ngày lễ sẽ là **ghi/xoá tường minh**, không trông vào việc chạy lại engine.

### Việc phía chúng tôi đang chờ các bạn

| Mục | Vì sao chặn |
|---|---|
| **S1 + S2** | `payment_days` vẫn đếm Half Day = 1 ngày ⇒ lương cơ bản gấp đôi thực tế. Đã đo: TIQN-2181 ra 207.692, đúng phải là **103.846** |
| **S4** | Không tách nghỉ có lương / không lương thì **không áp được mốc 14 ngày** của Luật BHXH 2024 ⇒ đang trừ BH cho người làm 1 ngày, ra **net âm** |
| **S5** | Không có API đếm đi trễ/về sớm thì thưởng chuyên cần không tính theo quy chế được (A4) |

