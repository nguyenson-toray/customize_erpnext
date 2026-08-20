# Earned Leave Override — phép năm theo Bộ luật Lao động 2019

> **Mục đích:** Tính phép năm theo Bộ luật Lao động 2019: tỷ lệ theo tháng thực làm, thử việc được hoãn chứ không mất, làm tròn trên tổng.
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-15

**Cập nhật:** 2026-08-15 — viết lại toàn bộ sau khi rà soát pháp lý.
Bản trước (2026-02-05) mô tả chiến lược "tháng bonus" đã bị bỏ từ 10/08/2026 và ghi
"không đủ điều kiện → bỏ qua, KHÔNG cộng dồn" như hành vi cố ý; điều đó **trái luật**.

---

## 1. Căn cứ pháp lý

| Nội dung | Căn cứ |
|---|---|
| Phép năm 12 / 14 / 16 ngày theo điều kiện làm việc | Điều 113 khoản 1 BLLĐ 2019 |
| Làm **chưa đủ 12 tháng** → phép **theo tỷ lệ** số tháng làm việc | Điều 113 khoản 2 BLLĐ 2019 |
| Cứ đủ 05 năm làm cho một NSDLĐ → **+01 ngày** | Điều 114 BLLĐ 2019 |
| Cách tính "01 tháng làm việc" và quy tắc làm tròn | Điều 65 khoản 2, Điều 66 NĐ 145/2020/NĐ-CP |

**Luật là mức SÀN.** Cấp nhiều hơn không phạm luật (là chính sách công ty), cấp **ít hơn** thì có.
Mọi thay đổi ở module này phải kiểm cả hai chiều.

---

## 2. Bốn quy tắc phải đúng

### 2.1. Tháng nào được tính là "01 tháng làm việc"

Luật: tổng số ngày làm việc thực tế trong tháng **≥ 50%** số ngày làm việc bình thường của tháng đó.

Cách hiện thực (tất định, khớp đúng mốc ngày 15 ở **cả hai đầu**):

> **Một tháng được tính khi và chỉ khi người lao động còn trong biên chế vào ngày 15 của tháng đó.**

| Tình huống | Ngày 15 có trong biên chế? | Tính tháng |
|---|---|---|
| Nhận việc 15/01 | có | **CÓ** |
| Nhận việc 16/01 | không | **KHÔNG** |
| Nghỉ việc 20/01 | có | **CÓ** |
| Nghỉ việc 10/01 | không | **KHÔNG** |

Quy tắc này trùng khít với `Leave Type.allocate_on_day = "15th of Month"`, nên ngày cấp và ngày
xét điều kiện là **một**, không sinh ra trường hợp lệch.

> ⚠ Bản cũ dùng `count_worked_days_in_month() >= 14` (đếm **ngày dương lịch**). Tháng 31 ngày,
> vào làm ngày 16/17/18 vẫn được tính — sai. Đã bỏ.

### 2.2. Thời gian thử việc — hoãn cấp, KHÔNG mất

- **Trong thử việc:** không cấp, không cho dùng phép năm.
- **Hết thử việc:** **truy thu toàn bộ** các tháng đã đủ điều kiện trong giai đoạn thử việc,
  cấp gộp vào kỳ cấp đầu tiên sau ngày hết thử việc.

| TH | Nhận việc | Thử việc | Tháng đầu tính? | Kỳ cấp đầu | Số tháng truy thu |
|---|---|---|---|---|---|
| 1 | ≤ 15 | 30 ngày | CÓ | 15 của tháng 2 | Tháng 1 + Tháng 2 |
| 2 | > 15 | 30 ngày | KHÔNG | 15 của tháng 3 | Tháng 2 + Tháng 3 |
| 3 | ≤ 15 | 60 ngày | CÓ | 15 của tháng 3 | Tháng 1 + 2 + 3 |
| 4 | > 15 | 60 ngày | KHÔNG | 15 của tháng 4 | Tháng 2 + 3 + 4 |

> ⚠ Bản cũ bỏ luôn các tháng trước ngày hết thử việc (`earned_leave_config.py` từng ghi
> *"If not eligible in a month, skip it (no accumulation)"*). Nhân viên nghỉ việc giữa kỳ
> mất thật số ngày đó. Đã sửa.

### 2.3. Công thức và mức cấp từng tháng

```
quyền lợi cả kỳ = LÀM_TRÒN_LUẬT( annual / 12 × số_tháng_đủ_điều_kiện )
mức mỗi tháng   = annual / 12          (làm tròn 2 chữ số để lưu)
kỳ CUỐI CÙNG    = quyền lợi cả kỳ − tổng các kỳ trước
```

`annual` = `Leave Type.max_leaves_allowed` + thâm niên (mục 2.4).

Kỳ cuối gánh phần dư để tổng khớp tuyệt đối với quyền lợi, kể cả khi có kỳ gộp (truy thu thử việc)
hoặc kỳ không trọn năm.

> ⚠ Bản cũ dùng `floor(annual/12, 1)` = **1,1** thay vì 14/12 = **1,1667** → thiếu 0,067
> ngày/tháng, chỉ bù ở tháng 12. Ai nghỉ trước tháng 12 là mất thật. Đã sửa.

### 2.4. Làm tròn (Điều 66 NĐ 145/2020)

| Phần thập phân | Xử lý |
|---|---|
| ≥ 0,5 | làm tròn **LÊN** 1 ngày |
| < 0,5 | **cắt bỏ** phần thập phân |

Áp dụng cho **tổng quyền lợi cả kỳ**, không áp cho từng tháng (làm tròn từng tháng sẽ tích luỹ sai số).

Ví dụ với annual = 14:

| Số tháng | annual/12 × tháng | Quyền lợi |
|---|---|---|
| 1 | 1,17 | 1 |
| 3 | 3,50 | **4** |
| 5 | 5,83 | **6** |
| 11 | 12,83 | **13** |
| 12 | 14,00 | 14 |

> ⚠ `Leave Type.rounding` đang để trống và hàm `round_earned_leaves()` **chưa từng được gọi ở đâu**
> — code chết. Quy tắc làm tròn nay nằm ở `round_leaves_by_law()`.

### 2.5. Thâm niên (Điều 114) — phần này bản cũ đã đúng

| Thâm niên | Bonus | Annual (base 14) |
|---|---|---|
| < 5 năm | 0 | 14 |
| 5–9 năm | +1 | 15 |
| 10–14 năm | +2 | 16 |
| 15–19 năm | +3 | 17 |

Tính từ DOJ (thời gian thử việc **được** tính vào thâm niên) đến ngày tham chiếu.

---

## 3. Ví dụ đối chiếu

### 3.1. TH1 — vào ngày 10/01, thử việc 30 ngày, làm hết kỳ

```
Đủ điều kiện từ 09/02. Tháng đủ điều kiện: 01→12 = 12 tháng.
Quyền lợi = LÀM_TRÒN(14/12 × 12) = 14,00 → 14 ngày

15/02   2,34   ← truy thu tháng 1 + tháng 2
15/03   1,17
 ...    1,17   (tháng 4..11)
15/12   1,30   ← kỳ cuối gánh phần dư
        ─────
        14,00
```

### 3.2. TH4 — vào ngày 20/01, thử việc 60 ngày

```
Tháng 1 KHÔNG tính (vào sau ngày 15). Đủ điều kiện từ 21/03.
Tháng đủ điều kiện: 02→12 = 11 tháng.
Quyền lợi = LÀM_TRÒN(14/12 × 11) = LÀM_TRÒN(12,83) = 13 ngày

15/04   4,68   ← truy thu tháng 2 + 3 + 4
15/05   1,17
 ...
15/12   1,29   ← kỳ cuối
        ─────
        13,00
```

### 3.3. Vào làm giữa kỳ — chỗ bản cũ sai nặng nhất

```
DOJ 11/08/2026, thử việc 30 ngày, kỳ phép 26/12/2025–25/12/2026.
Tháng 8 CÓ tính (vào ngày 11 ≤ 15). Tháng đủ điều kiện: 08,09,10,11,12 = 5 tháng.
Quyền lợi = LÀM_TRÒN(14/12 × 5) = LÀM_TRÒN(5,83) = 6 ngày

ĐÚNG (sau khi sửa)          SAI (bản cũ, đo trên production)
15/09   2,34  ← truy thu    15/09    1,1
15/10   1,17                15/10    1,1
15/11   1,17                15/11    1,1
15/12   1,32                15/12   10,7   ← _true_up_december dồn hết
        ─────                        ─────
         6,00                         14,0   → THỪA 8 ngày
```

Nguyên nhân: `_true_up_december()` cũ đặt kỳ tháng 12 = `annual − tổng các kỳ khác`
**vô điều kiện**, nên ai cũng nhận đủ 14 ngày bất kể làm mấy tháng.
Đo ngày 15/08/2026: **379 nhân viên vào làm năm 2026, tổng lịch 5.278 ngày, thừa ~2.022 ngày.**

---

## 4. Cấu trúc file

```
overrides/earned_leave/
├── __init__.py                    # monkey patch vào LeavePolicyAssignment + scheduler
├── earned_leave.py                # dựng lịch, scheduler, backfill
├── earned_leave_config.py         # tháng đủ điều kiện, tỷ lệ, làm tròn, thâm niên
├── earned_leave_eligibility.py    # mốc hết thử việc
└── earned_leave_override.md       # tài liệu này
```

### Hàm chính (`earned_leave_config.py`)

| Hàm | Vai trò |
|---|---|
| `is_working_month(date, doj, relieving)` | tháng này có tính không — mốc ngày 15 |
| `count_qualifying_months(from, to, doj, relieving)` | đếm số tháng đủ điều kiện trong kỳ |
| `round_leaves_by_law(value)` | ≥0,5 lên, <0,5 cắt (Điều 66) |
| `get_monthly_rate(annual)` | `annual / 12`, 2 chữ số |
| `get_period_entitlement(annual, from, to, doj, relieving)` | quyền lợi cả kỳ đã làm tròn |
| `get_annual_allocation_with_seniority(base, doj, ref)` | cộng thâm niên (Điều 114) |

---

## 5. Cấu hình Leave Type đang dùng

```
Phép năm/ Annual leave
├── is_earned_leave: ✓
├── earned_leave_frequency: Monthly
├── allocate_on_day: 15th of Month     ← phải giữ; mốc xét tháng bám vào đây
├── max_leaves_allowed: 14
├── applicable_after: 30               ← fallback khi Employee.custom_probation_days trống
└── rounding: (để trống)               ← KHÔNG dùng; làm tròn theo round_leaves_by_law()
```

`Employee.custom_probation_days`: 980 NV = 30 ngày, 62 NV = 60 ngày, 3 NV để trống (dùng fallback 30).

---

## 6. Lưu ý khi sửa tiếp

1. **Đổi `allocate_on_day` khỏi "15th of Month" sẽ phá quy tắc mốc ngày 15** ở mục 2.1 —
   ngày cấp và ngày xét điều kiện phải là một.
2. **Đừng làm tròn từng tháng.** Chỉ làm tròn tổng quyền lợi; kỳ cuối gánh phần dư.
3. **Kiểm cả hai chiều** sau mỗi thay đổi: người làm hết kỳ (không được thừa) và người nghỉ
   giữa kỳ (không được thiếu hơn luật).
4. **Thâm niên tính đến ngày tham chiếu**, không tính đến cuối kỳ — nhân viên đủ 5 năm giữa kỳ
   thì bonus áp từ lần dựng lịch kế tiếp.
5. Script đối chiếu nhanh: `test_earned_leave_law.py` cùng thư mục.
