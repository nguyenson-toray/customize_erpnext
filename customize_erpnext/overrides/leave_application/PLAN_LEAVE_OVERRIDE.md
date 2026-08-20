# Plan — Rà soát & sửa override Nghỉ phép

> **Mục đích:** Rà soát **10/08/2026**, sau khi số hoá quy định gốc thành
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Kế hoạch · **Cập nhật:** 2026-08-12

> Rà soát **10/08/2026**, sau khi số hoá quy định gốc thành
> [`QUY_DINH_NGHI_PHEP_2025.md`](QUY_DINH_NGHI_PHEP_2025.md).
>
> Nền: một bản audit trước đó đã liệt kê 6 điểm mâu thuẫn giữa override Leave Application
> (viết ~02–04/2026) và engine tính công bulk attendance (sửa 06–07/08/2026).
> **Trạng thái: ✅ GĐ 1–8 ĐÃ CODE (10/08/2026), test 39/39 đạt.**
> Chưa import LA, chưa dịch `vi.csv`, chưa commit — ba việc đó chỉ làm khi user yêu cầu.

---

## 0. Kết luận ngắn

Việc số hoá quy định gốc đã **giải quyết được câu hỏi nghiệp vụ** mà bản audit định đi hỏi, và
đồng thời **phát hiện một lỗi nặng hơn** tất cả 6 điểm đã liệt kê.

| # | Vấn đề | Mức | Trạng thái |
|:--:|---|:--:|---|
| **7** | Dual leave ghi `On Leave` trọn ngày + phụ thuộc thứ tự query | 🔴🔴 | ✅ **xong** — GĐ 2, có ở **cả** engine lẫn `leave_utils` |
| 1 | `half_day_status` — 3 nơi 3 kiểu | 🔴 | ✅ **xong** — GĐ 3, gom về `leave_rules.py` |
| 2 | Công thức mã dual leave khác nhau | 🟠 | ✅ **xong** — bảng tra `HALF_DAY_CODE` |
| 3 | `modify_half_day_status` đảo ngược | 🟠 | ✅ **xong** — GĐ 4, LA hook không ghi field này nữa |
| 4 | `leave_utils.py`: 6 hàm chết, 2 dict lệch, field không tồn tại | 🟡 | ✅ **xong** — GĐ 5, 496 → **128** dòng |
| 5 | Docstring/MD nói sai | 🟡 | ✅ **xong** — GĐ 7 |
| 6 | `validate_attendance` đọc `working_hours` mà engine reset 0 ngày CN | 🟡 | ✅ **xong** — GĐ 6, đọc thêm `actual_overtime_duration` |
| **8** | 3 dòng quy định ERP **không thể** biểu diễn (ngày công lẻ 0,4 / 0,9) | 🟠 | ⏸ **ngoài phạm vi** — cần chốt thưởng chuyên cần trước |

## 1. Đính chính bản audit

### 1.1. ✅ `is_lwp` KHÔNG sai — không cần sửa Leave Type

Audit ghi *"9/10 Leave Type có `is_lwp=1`, kể cả Thai sản"*. Đo lại: **6/10**.

| `is_lwp = 0` (có lương) | `is_lwp = 1` (không lương / BHXH) |
|---|---|
| `P` `MC` `HS` `HL` | `O` `CO` `DS` `TS` `KL` `NB` |

Đối chiếu **10/10** dòng nghỉ trọn ngày của quy định: cấu hình hiện tại **tái tạo đúng** cột
"Thời gian tính công". Chi tiết ở [`QUY_DINH_NGHI_PHEP_2025.md`](QUY_DINH_NGHI_PHEP_2025.md) mục 5.1.

### 1.2. Vấn đề 1 không phải câu hỏi nghiệp vụ — quy định đã chốt

Audit đề nghị *"hỏi user, đừng tự chọn"* giữa `Absent` (engine) và `Present` (guide + LA hook).
**Cả hai đều sai** vì cùng là quy tắc vô điều kiện. Quy định mục 3.5 liệt kê 9 tổ hợp nửa ngày và
suy ra được **một** quy tắc có điều kiện:

```
half_day_status = 'Present'  nếu nửa còn lại ĐƯỢC CÔNG TY TRẢ LƯƠNG
                             (có checkin, HOẶC leave thứ 2 có is_lwp = 0)
                  'Absent'   nếu không
```

Kiểm chéo 9/9 dòng ra đúng cột "Tính công" — bảng đối chiếu ở mục 5.2 của file quy định.

Dòng bẻ mọi giả định đơn giản là **`OP/2`** (Ốm ½ + Phép năm ½): **không có checkin nào cả ngày**
nhưng `half_day_status` vẫn phải là `Present`, vì nửa còn lại là phép năm có lương.
Quy tắc *"không checkin → Absent"* của engine sai đúng ở dòng này.

### 1.3. Vấn đề 2: không có định dạng nào trong quy định khớp code

Audit đề xuất *"giữ semantic của engine"* (`O/P`). Quy định **không có** định dạng `abbr1/abbr2`.
Mã là **tập liệt kê sẵn**, và **không** suy ra được bằng nối chuỗi:

| Tổ hợp | Nối chuỗi cho ra | Quy định |
|---|---|---|
| Ốm + Con ốm | `OCO/2` | `OCO/2` ✅ |
| Ốm + Phép năm | `OP/2` | `OP/2` ✅ |
| Ốm + **Không lương** (`KL`) | `OKL/2` | **`OK/2`** ❌ |

→ Phải là **bảng tra**, không phải công thức. `leave_utils.py:149` (`OP/2`) gần đúng hơn engine
(`O/P`), nhưng vẫn sai dòng `OK/2` / `COK/2`.

## 2. 🔴 Vấn đề 7 (MỚI) — dual leave bị trừ trọn ngày, và không tất định

`check_leave_status_cached()` (`shift_type_optimized.py:678-690`) khi thấy 2 đơn nửa ngày cùng
ngày thì ghi:

```python
la1, la2 = active[0], active[1]
return {'status': 'On Leave', 'leave_type': la1['leave_type'], ...}
```

Hai sai độc lập:

**(a) `On Leave` = trọn ngày.** HRMS `calculate_lwp_ppl_and_absent_days_based_on_attendance()`
(`salary_slip.py:800-806`) với `status == "On Leave"` đặt `equivalent_lwp = 1` — trừ **cả ngày**.
Quy định nói `OP/2` = **0,5**.

**(b) `leave_type = la1` mà `la1` không tất định.** Hai query preload
(`shift_type_optimized.py:455-488`) **không có `ORDER BY`** → thứ tự do MySQL quyết định:

| `la1` rơi vào | HRMS thấy | payment_days | Quy định |
|---|---|:---:|:---:|
| `O` (`is_lwp=1`) | On Leave + lwp → trừ 1 | **0** | 0,5 |
| `P` (`is_lwp=0`) | leave_type ngoài `leave_type_map` → `continue`, **không trừ gì** | **1** | 0,5 |

⇒ Cùng một dữ liệu, chạy lại có thể ra **0 hoặc 1** ngày công. Sai theo cả hai chiều, và
lệch tới **một ngày lương** mỗi lần.

**Sửa:** dual leave phải là `status = 'Half Day'`, `leave_type` = **nửa `is_lwp = 1`**,
`half_day_status` theo quy tắc mục 1.2. Khi đó cả 5 tổ hợp `OP/2` `COP/2` `OCO/2` `OK/2` `COK/2`
ra đúng, và không còn phụ thuộc thứ tự.

> Chỉ ảnh hưởng tương lai: DB hiện có **0** bản ghi `custom_leave_application_2`.

## 3. 🟠 Vấn đề 8 (MỚI) — 3 dòng quy định ERP không biểu diễn được

`Attendance.status` chỉ cho `1 / 0,5 / 0` ngày. Quy định cần ngày công **lẻ**:

| Mã | Tính công |
|---|:---:|
| Đi trễ | `1 − giờ nghỉ/8` → vd **0,9** |
| Về sớm | `1 − giờ nghỉ/8` |
| `OL/2` · `COL/2` | **0,4** |

→ Không thể ép vào `Attendance.status`. Phải xử lý ở **tầng khoản lương**.
`late_entry` / `early_exit` đã có sẵn làm đầu vào (2.070 / 2.653 bản ghi năm 2026).
Nối với `payroll_docs/PLAN_ATTENDANCE_VS_QUYCHE.md` mục A4 + S5.

**Ngoài phạm vi plan này** — ghi lại để không bị coi là đã xong.

## 4. Kế hoạch

### GĐ 1 — `leave_rules.py`: một nguồn sự thật cho 2 luồng ghi

Gốc rễ của vấn đề 1 · 2 · 3 là **cùng một quyết định được viết ở hai nơi**. Tách ra module thuần,
không phụ thuộc `frappe.get_doc`, để cả LA hook và engine gọi:

```python
# overrides/leave_rules.py
HALF_DAY_CODE = {            # frozenset({abbr, abbr}) -> ma quy dinh
    frozenset({"O",  "P"}):  "OP/2",
    frozenset({"CO", "P"}):  "COP/2",
    frozenset({"O",  "CO"}): "OCO/2",
    frozenset({"O",  "KL"}): "OK/2",
    frozenset({"CO", "KL"}): "COK/2",
}

def combined_abbreviation(abbr1, abbr2=None) -> str
    # 1 don   -> f"{abbr1}/2"
    # 2 don   -> HALF_DAY_CODE, khong co trong bang -> f"{abbr1}{abbr2}/2"

def resolve_half_day_status(has_checkin: bool, other_leave_is_lwp: bool | None) -> str
    # 'Present' neu has_checkin or other_leave_is_lwp is False, nguoc lai 'Absent'

def primary_leave_type(lt1, lt2)   # tra ve nua is_lwp=1 -> gan vao Attendance.leave_type
```

Kèm **test bảng** dựng thẳng từ 21 dòng quy định (mục 6).

### GĐ 2 — 🔴 Sửa vấn đề 7 (dual leave)

`shift_type_optimized.py`: nhánh dual leave → `Half Day` + `primary_leave_type()` +
`resolve_half_day_status()` + `combined_abbreviation()`. Thêm `ORDER BY name` vào 2 query preload
để tất định kể cả khi logic sau này đổi.

⚠ **File này thuộc phiên chấm công** — xem mục 7.

### GĐ 3 — 🔴 Sửa vấn đề 1 (`half_day_status`) đồng bộ 3 nơi

| Nơi | Hiện tại | Sau |
|---|---|---|
| `leave_application.py:232` `:274` | `'Present'` vô điều kiện | `resolve_half_day_status()` |
| `shift_type_optimized.py:855` `:2014` | `'Absent'` khi không checkin | `resolve_half_day_status()` |
| `shift_type/OPTIMIZATION_GUIDE.md:64,79-88` | "luôn Present" | bảng có điều kiện |

LA hook phải **tra đơn nghỉ thứ hai cùng ngày** trước khi quyết định — hiện chỉ nhìn đơn của
chính nó, nên không thể biết nửa còn lại là gì.

### GĐ 4 — 🟠 Vấn đề 3 (`modify_half_day_status`)

Chỗ duy nhất HRMS **đọc** field này là `get_duplicate_attendance_record()` (`attendance.py:99`):
`modify_half_day_status = 0` làm bản ghi bị coi là **trùng**, chặn tạo Attendance thứ 2 cùng ngày.
(`attendance.py:199` chỉ **ghi**, không đọc.)
Trả LA hook về đúng semantic gốc HRMS (`leave_application.py:318`):
`1 if trạng thái cũ == "Absent" and trạng thái mới == "Half Day"`.
Bỏ hẳn cũng được — engine đã luôn ghi `0`. **Chốt: bỏ**, và bỏ khỏi danh sách compare
(`shift_type_optimized.py:1041`) để hết churn update mỗi FULL run.

### GĐ 5 — 🟡 Vấn đề 4: dọn `leave_utils.py` (496 → ~150 dòng)

Xoá 6 hàm chết (0 external ref): `get_working_days_for_leave` · `get_total_leave_days` ·
`find_other_half_day_leave` · `is_paid_leave_type` · `create_attendance_for_leave` ·
`remove_leave_from_attendance`.

Xoá 2 dict khoá tiếng Anh không khớp Leave Type thật: `LEAVE_TYPE_ABBREVIATIONS` ·
`PAID_LEAVE_TYPES`.

> 🔴 `is_paid_leave_type()` đọc `Leave Type.custom_is_paid_leave` — **field không tồn tại**, gọi
> vào là nổ. Thay bằng `is_lwp` (đó mới là cờ HRMS thật sự dùng để trừ lương).
>
> 🔴 `get_working_days_for_leave()` trả `P/2 → 0,5`; quy định là **1**. Hàm đang chết là điều may —
> **đừng hồi sinh nó**. Logic đúng nay nằm ở `leave_rules.py`.

Giữ 3 hàm đang dùng: `get_leave_type_abbreviation` · `get_combined_abbreviation` (chuyển sang gọi
`leave_rules`) · `update_attendance_with_dual_leave` · `find_attendance_for_leave`.

### GĐ 6 — 🟡 Vấn đề 6: `validate_attendance` bỏ sót ngày Chủ Nhật

Engine §8 reset `working_hours = 0` ngày CN và dồn vào `actual_overtime_duration`
⇒ CN làm 10h có `working_hours = 0` ⇒ đơn nghỉ nguyên ngày **lọt qua** validate và đè lên ngày đó.
Sửa: đọc thêm `custom_actual_overtime_duration`, hoặc loại trừ ngày trong Holiday List có
`weekly_off = 1`.

### GĐ 7 — 🟡 Vấn đề 5: sửa tài liệu

- `leave_application.py:33-34` + docstring class ~365: bỏ câu *"Maternity attendance recalc vẫn
  được xử lý qua Employee Maternity hooks"* — setting `recalc_attendance_on_maternity_change`
  **default OFF**, thực tế không có gì recalc tới FULL run kế tiếp. Ghi rõ giá trị còn lại của
  `cancel_attendance()` chỉ là **tránh timeout + tránh `LinkExistsError`**, vì engine bước 2b đã
  tự xoá attendance trong giai đoạn Maternity Leave.
- `leave_application_override.md`: `FULL_DAY_WORKING_HOURS_THRESHOLD = 8` đã thành setting
  `full_day_leave_block_hours` (`leave_application.py:99`).
- `leave_application_override.md` + `leave_summary_doc.md`: định dạng mã dual leave → theo
  bảng quy định.

### GĐ 8 — Property Setter Leave Application vào fixtures

`hooks.py:103-114` chỉ liệt kê `"Leave Type"`. Property Setter của **Leave Application** có trong
DB (`half_day.depends_on`, `field_order`, `naming_series HR-LAP-.YYYY.-`, 4 × `in_list_view`)
nhưng **không** trong fixtures → mất khi deploy site khác.

⚠ Sửa `hooks.py` **bắt buộc restart web** — hỏi trước, đây là production trong giờ làm việc.

## 4b. 🔴 GOTCHA — HRMS `validate()` tự ép `half_day_status = 'Absent'`

`attendance.py:197-200`:

```python
if self.status in ("On Leave", "Half Day"):
    if not leave_record:
        self.modify_half_day_status = 0
        self.half_day_status = "Absent"
```

Nghĩa là **mọi** đường ghi Attendance đi qua `validate()` sẽ bị HRMS ghi đè `half_day_status`
thành `Absent` nếu nó không tự tìm thấy đơn nghỉ. Hai hệ quả phải nhớ khi làm GĐ 2 + GĐ 3:

1. Giá trị ta tính chỉ **sống sót** khi ghi bằng `db_set` / SQL, hoặc khi đặt
   `flags.ignore_validate = True` (LA hook đang làm ở `leave_application.py:276`), hoặc khi HRMS
   thật sự tìm được leave record.
2. Đây là **chỗ dựa** cho trường hợp `Half Day` **không có** đơn nghỉ (thiếu giờ làm): HRMS core
   cũng chốt `Absent`. Quy tắc mục 1.2 và HRMS core **không** xung đột ở ca này.

⚠ Khi viết test đầu-cuối (mục 6), tạo Attendance bằng `insert()` bình thường sẽ đi qua validate và
làm sai lệch kết quả — phải dùng đúng đường ghi mà production dùng.

## 4c. GĐ 9 — Import dữ liệu nghỉ phép 2026 của HR

HR đưa `AL_data.xlsx` (9.745 dòng, 25/04/2025 → 25/08/2026) để import **sau khi** các GĐ trên xong.
Kế hoạch riêng: [`PLAN_IMPORT_AL_2026.md`](PLAN_IMPORT_AL_2026.md).

Hai điều file đó **đổi lại** plan này:

- ✅ **Vấn đề 7 đúng là tiềm ẩn:** 9 cột nghỉ ghép của quy định **rỗng hoàn toàn** trong 16 tháng
  dữ liệu thật (0/9.745). Vẫn phải sửa, nhưng **không chặn** import.
- ⚠️ **Vấn đề 1 đang chờ sẵn 1.723 dòng `P/2`** — nhưng đo lại thì **1.709/1.723** dòng đó ERP đã
  có checkin nên vẫn ra `Present` đúng; chỉ **14** dòng lệch (≈ 7 ngày lương), không phải con số
  861 mà bản plan đầu ước tính. Thứ tự "override trước" vẫn đúng, lý do là **tính đúng đắn và khả
  năng kiểm chứng**, không phải quy mô tiền. Chi tiết: `PLAN_IMPORT_AL_2026.md` mục 8.

## 4d. ✅ Đã thực hiện — 10/08/2026

| File | Thay đổi |
|---|---|
| `overrides/leave_rules.py` **(mới)** | `HALF_DAY_CODE` · `resolve_half_day_status()` · `order_leave_types()` · `combined_abbreviation()` · `run_regulation_selftest()` |
| `overrides/leave_utils.py` | 496 → **128** dòng; xoá 6 hàm chết + 2 dict; `update_attendance_with_dual_leave()` nay ghi `Half Day` |
| `overrides/leave_application/leave_application.py` | dùng `leave_rules`; tra đơn nửa ngày thứ 2; bỏ ghi `modify_half_day_status`; validate đọc thêm `actual_overtime_duration` |
| `overrides/shift_type/shift_type_optimized.py` | dual leave → `Half Day` + `leave_type` là nửa `is_lwp`; `ORDER BY name` cho 2 query preload; 3 nhánh `half_day_status` dùng `resolve_half_day_status()` |
| `overrides/shift_type/OPTIMIZATION_GUIDE.md` · `leave_application_override.md` · `leave_summary_doc.md` | bảng quy tắc có điều kiện thay cho "luôn Present" |
| `hooks.py` | thêm `"Leave Application"` vào fixtures Property Setter — ⚠ **cần restart web** mới có hiệu lực |

**Test: [`test_leave_rules.py`](test_leave_rules.py) — 39/39 đạt**, luôn `rollback`:
9 dòng quy định · nửa ngày có/không checkin · 4 tổ hợp dual leave · nghỉ trọn ngày · chặn nghỉ
nguyên ngày trên ngày đã làm đủ giờ · ngày Chủ Nhật dồn giờ sang OT · dual leave tất định.

```bash
cd /home/frappe/frappe-bench/sites && ../env/bin/python -c "
import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
exec(open('../apps/customize_erpnext/customize_erpnext/overrides/leave_application/test_leave_rules.py').read())"
```

### Còn lại (chỉ làm khi user yêu cầu)

- Chạy `bulk_update_attendance_optimized` **hai lần liên tiếp** trên dữ liệu thật → lần hai phải
  **0 thay đổi**. Đây là bước chứng minh hai luồng đã đồng thuận, **chưa chạy** vì ghi vào production
- `bench restart` để `hooks.py` có hiệu lực
- Import `AL_data.xlsx` · dịch `vi.csv` · commit

## 4e. Bổ sung ngoài plan — 10/08/2026

Phát sinh trong lúc làm, đã code xong:

| Việc | File | Ghi chú |
|---|---|---|
| **Leave Control Panel** chọn NV theo khoảng làm việc, không theo `status = Active` | `overrides/leave_control_panel/` | kỳ 26/12/2025 → 25/12/2026: **1.036 → 1.508** người (+447 Left nghỉ giữa kỳ, +25 Inactive); 893 người nghỉ trước kỳ vẫn bị loại |
| **Phép năm chia theo tỷ lệ** thay cho "tháng bonus" | `overrides/earned_leave/` | `annual/12` floor 1 chữ số, tháng 12 điều chỉnh; + mốc 14 ngày Điều 66 NĐ 145/2020 |
| **Ngày lễ không còn bị trừ lương** | `overrides/salary_slip/` | `PAYROLL_SETUP.md` mục 4.8 — đo được mất 5,69 triệu/người kỳ Tết |
| Import 7.097 đơn nghỉ | `import_leave.py` | `PLAN_IMPORT_AL_2026.md` mục 12 |

## 5. Thứ tự đề xuất

| Bước | GĐ | Vì sao trước |
|:--:|---|---|
| 1 | GĐ 1 + GĐ 5 | Không rủi ro (module mới + xoá code chết), tạo nền cho các bước sau |
| 2 | **GĐ 2** | Lỗi tiền nặng nhất, và không tất định |
| 3 | GĐ 3 | Lỗi tiền, cần GĐ 1 |
| 4 | GĐ 4 + GĐ 6 + GĐ 7 | Nhỏ, độc lập |
| 5 | GĐ 8 | Cần restart → gom vào một lần restart có kế hoạch |

Vấn đề 8 (ngày công lẻ) **không** nằm trong plan này — cần chốt cách tính thưởng chuyên cần trước.

## 6. Test — cách thoát bẫy "chưa từng được test"

Toàn hệ thống có **1** Leave Application, **0** dual leave, **0** Half Day có leave. Không thể
dựa vào dữ liệu thật, và cũng không nên chờ nó.

**Test bảng dựng từ quy định** — 21 dòng của mục 3, mỗi dòng một case:

```
(leave_type_1, leave_type_2, has_checkin) → (status, leave_type, half_day_status, abbr, payment_days)
```

Hai tầng:

1. **Thuần Python** trên `leave_rules.py` — không cần DB, chạy nhanh, chặn hồi quy.
2. **Đầu-cuối trên Salary Slip** — tạo Attendance cho 1 nhân viên test trong một kỳ lương, dựng
   Salary Slip, so `payment_days` với cột "Thời gian tính công". Đây là tầng duy nhất chứng minh
   được số học HRMS. Bọc `frappe.db.rollback()`.

> ⚠ So sánh ngày công phải dùng ngưỡng **0,01**, không phải `> 1` — kinh nghiệm cũ: ngưỡng `> 1`
> từng che mất chênh lệch 0,5 ngày và gần như báo "khớp" sai.

Chạy engine:

```
bench --site erp.tiqn.local console
bulk_update_attendance_optimized("2026-07-01","2026-07-04", employees='["TIQN-0001"]', force_sync=1)
```

> Console tách block nhiều dòng thành từng cell → script dài thì chạy file `.py` riêng trong
> `sites/`, đừng paste.

## 7. Ranh giới sở hữu file — phối hợp giữa 2 phiên

| Thư mục | Chủ |
|---|---|
| `overrides/leave_application/` · `overrides/leave_utils.py` · `overrides/leave_rules.py` (mới) | **phiên này** |
| `overrides/shift_type/` (engine + `OPTIMIZATION_GUIDE.md`) | **phiên chấm công** |
| `overrides/payroll/` · `overrides/salary_slip/` · `overrides/payroll_docs/` | phiên lương |

**GĐ 2 và GĐ 3 đều phải sửa `shift_type_optimized.py`** ⇒ cần bàn giao sang phiên chấm công,
hoặc xin phép sửa chéo. Engine **luôn ghi sau cùng** (`_check_attendance_changes()` +
`shift_type_optimized.py:352, 1036-1041`), nên sửa một mình luồng LA là **vô nghĩa** — FULL run kế
tiếp ghi đè lại.

Đây là lý do GĐ 1 tách ra module chung: hai phiên sửa hai file khác nhau nhưng dùng **cùng một**
hàm quyết định, không phải copy logic cho nhau.

## 8. Việc KHÔNG làm

- **Không** gửi email / tạo Notification cho bất kỳ chức năng nghỉ phép nào — Admin tự chọn người
  nhận. Đã có sự cố 154 mail thật bay đi.
- **Không** sửa `is_lwp` của Leave Type — đã kiểm khớp quy định 10/10 (mục 1.1).
- **Không** hồi sinh `get_working_days_for_leave()` — sai quy định ở dòng `P/2`.
- **Không** nhồi ngày công lẻ (0,4 / 0,9) vào `Attendance.status` — HRMS không có khái niệm đó.
- **Không** sửa ngược 956 bản `On Leave` thiếu `leave_type` của năm **2025** — user đã chốt bỏ qua.
- **Không** commit khi user chưa test OK trên UI thật.
