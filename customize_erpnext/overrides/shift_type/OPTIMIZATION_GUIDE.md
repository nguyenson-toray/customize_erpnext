# Bulk Attendance Processing — Architecture & Logic Guide

> **Mục đích:** Giải thích kiến trúc và logic của engine tính công hàng loạt: nạp dữ liệu nền một lần, xử lý theo lô, các nhánh quyết định trạng thái.
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-18

**Last Updated:** 2026-08-15 (no attendance created before a shift starts — ca 2 was being marked
absent every morning; see "Ca CHƯA TỚI GIỜ VÀO")

## Performance

| Metric | Value |
|--------|-------|
| Processing Time | ~27s (31 days × ~1030 employees, full mode) |
| DB Queries | ~500 preloaded + batched writes (500 rows/UPDATE, 1000 names/unlink) |
| Batch Size | 100 employees / 500 insert / 500 update / 1000 checkin-link |

**The `attendance` column on `tabEmployee Checkin` MUST stay indexed.** Unlinking checkins
(`WHERE attendance = %s`) is a full scan without it — measured 1949 ms per statement on ~860k
rows, run once per attendance record, which is what used to blow past the 120s gunicorn timeout
and get the worker SIGKILLed mid-write. The field is `search_index = 0` in the DocType, so
frappe's schema sync **drops any single-column index on it at every `bench migrate`** unless a
Property Setter says otherwise — that is why `patches/index_checkin_attendance_field.py` sets
`search_index = 1` instead of just issuing `CREATE INDEX` (the older
`add_attendance_performance_indexes` patch did, and lost the index every migration).
Verify with `EXPLAIN`: must be `type=ref`, not `type=ALL`.

## Entry Points (all funnel into `_core_process_attendance_logic_optimized`)

```
HRMS hourly_long hook ──(monkey patch)──► custom_process_auto_attendance_for_all_shifts
UI "Bulk Update"      ──────────────────► bulk_update_attendance_optimized (lock; > threshold → background job)
    └─ background ─────────────────────► run_bulk_update_attendance_background → publish_realtime
weekly_recalculate_attendance_scheduled ► bulk_update_attendance_optimized(force_sync=1)
OT Registration submit/cancel ──(bg job)─► overtime_registration_hooks._process_attendance_background
Employee Maternity save/trash ──(bg job)─► employee_maternity.background_update_attendance_for_maternity
Checkin delete hook (recalc)  ──(bg job)─► employee_checkin._recalculate_attendance_background
```

Runs above `BULK_ATTENDANCE_ASYNC_THRESHOLD` (1000 estimated records, shared with
`attendance_list.js`) are enqueued on the `long` queue and the request returns immediately;
the UI listens for `bulk_update_attendance_complete`. Callers already inside a worker pass
`force_sync=1` to stay inline. `bench` has **one** long worker, so jobs queue behind each other —
the result dialog reports queue wait and run time separately for that reason, and the time
estimate is derived from the throughput of recent runs rather than a hardcoded divisor.

Mode detection (`fore_get_logs`):
- **FULL** — web request, or hour ∈ `force_update_hours` setting (default 8, 23), or callers passing `fore_get_logs=True`. Reprocesses every checkin in range, updates existing attendance.
- **INCREMENTAL** — other hourly runs. Only unlinked checkins (`attendance is not set`).

## Processing Steps

0. **Employee list** (when the caller passes none) — Active, plus `Left` employees whose
   `relieving_date >= from_date`, **plus `Left` employees with any checkin inside the range**
   regardless of relieving date (a punch after it means either they really worked or the
   relieving date is wrong; days without checkins are still untouched, so this cannot
   manufacture Absent records). Then filtered by `employee_id_prefix` and `exclude_employee_ids`.
1. **Preload** — employees (+gender), shifts, shift assignments (sorted desc), **holidays via `get_assigned_holiday_lists_to_employee_and_company()`** (HRMS's own API, the one payroll uses — Holiday List Assignment with *Applicable For: Company*, one assignment covering the whole company), existing attendance (all compare fields incl. `custom_note`), leave applications (per-day index, dual-leave aware), maternity periods, OT registrations `{(employee, date): [entries]}`.
   - `exclude_employee_ids` setting filters the employee list first (empty result → early return).
2. **Checkin sync** — `bulk_update_employee_checkin`: shift from Shift Assignment → default_shift → `default_shift` setting; first log = IN, last = OUT; SQL CASE WHEN batches (no per-doc `get_doc`).
2b. **Maternity cleanup** (FULL only) — delete attendance inside Maternity Leave phases (Employee Maternity is source of truth), unlink checkins.
3. **Per-shift checkin processing** — group by (employee, shift_start):
   - Employment gate here is **joining date only**. `relieving_date` is deliberately NOT a gate on this path: a day with checkins is always calculated, even after the employee left (STEP 4b keeps it and explains it in `custom_note`). Only the no-checkin paths (3b, 4) stop at the relieving date.
   - working hours = morning + afternoon (break excluded; maternity: end −`hour_reduction_hours`, afternoon credited).
   - **OT per-segment** (`calculate_overtime_segments`, LEGACY_APP_TIMESHEET_ALGORITHM.md §7): final = Σ min(actual, approved) per pre/lunch/post segment — NO global clamp; pre actual capped at registered span, min `min_pre_shift_ot_minutes`; post actual uncapped, min `min_ot_minutes`; everything floored to `ot_block_minutes`; lunch counted only when `allow_ot_in_rest_time` is ON.
   - **Sunday** (§8): shift boundaries ← OT registration span; ALL worked hours → `actual_overtime_duration`, `working_hours` = 0 (status still from real hours); no register → approved/final = 0 but actual still shown.
   - 0/1-log days: approved OT still shown from registrations (§7.9), actual/final = 0.
   - **`half_day_status` is always written** — payroll ignores a Half Day without it (`get_half_absent_days` needs status `Half Day` **and** `half_day_status = "Absent"`; NULL reads as a fully paid day). The value comes from `overrides/leave_rules.resolve_half_day_status()` — shared with the Leave Application flow, see the table below.
   - New inserts and updates both apply Leave Applications through the same helper; two half-day LAs on one date become a **`Half Day`** (never `On Leave`) whose `leave_type` is the `is_lwp` half.
   - `custom_note` anomalies (§9-10): Left-with-checkins, ±threshold without same-zone OT registration, Sunday work (+meal allowance > 4h spanning break), female checkout window without Employee Maternity (only shifts ending at window end), single-checkin / no-IN / no-OUT.
   - Values stored rounded: working_hours 2dp, OT 1dp.
3b. **ABSENCE PASS** (FULL only, runs ONCE after all shifts) — every existing attendance whose (employee, date) had no checkins processed by ANY shift is re-resolved: Maternity Leave → skip, Leave → On Leave/Half Day, **ca chưa tới giờ vào → skip**, else Absent. Global `processed_keys` prevents cross-shift Absent overwrites when the stored shift is stale.
4. **Mark absent** — days with no attendance at all (skip before-joining/after-relieving, holidays and Sundays, **và ca chưa tới giờ vào**); same resolution helper as 3b; bulk INSERT (32 columns incl. half_day/dual-leave/custom_note).
4b. **Left-employee cleanup** — delete attendance ≥ relieving_date **without** checkins; for ones WITH checkins, PREPEND the left-employee sentence to `custom_note` if not already there (it normally arrives from step 3 — this is a safety net). It must not overwrite: doing so used to wipe the other anomalies of that day.
5. **Stats** — per-shift before/after counts, skipped-employee classification (`Maternity Leave` → `No shift assigned` → `Not yet joined` → `Already left` (`relieving_date <= from_date`, matching the calculation rule) → `No checkins / Holiday`).

## Attendance status — ngưỡng vắng chỉ áp **SAU KHI TAN CA** (11/08/2026)

Engine chạy hourly nên một ngày **đang diễn ra** cũng bị đem ra kết luận. App cũ không gặp vấn đề
này vì chỉ tính cho ngày đã trọn.

Sự cố đo được **11/08/2026 lúc 16:44**: **264** bản `Absent` (mức nền ngày thường 65–95), trong đó
**262 thuộc ca chưa tan**. Nguyên nhân: công nhân **quẹt đúp** ở cửa lúc vào (hai log cách nhau
1–7 giây), engine ghép thành cặp IN/OUT ⇒ `working_hours = 0` ⇒ dưới
`working_hours_threshold_for_absent = 2,0` ⇒ `Absent`.

Hai hàm thuần, tách khỏi vòng lặp để test được:

| Hàm | Việc |
|---|---|
| `is_shift_in_progress(attendance_date, shift_data)` | ca của **người này** đã tan chưa — đọc `end_time` của chính ca đó |
| `is_shift_not_started(attendance_date, shift_data)` | ca của **người này** đã tới giờ vào chưa — đọc `start_time` |
| `resolve_attendance_status(status_hours, in_time, out_time, attendance_date, shift_data)` | quyết định trạng thái cuối cùng |

```
không có in_time                → Absent
ca CHƯA tan  (có quẹt)          → Present   (tạm; lần chạy sau khi tan ca chốt lại)
có in_time, KHÔNG có out_time   → Present   (đã đến làm, quên/sót log ra)
còn lại                         → áp ngưỡng absent / half-day như cũ
```

⚠ **Ca chưa tan phải bỏ qua CẢ HAI ngưỡng.** Cả 5 ca đều `absent = 2,0`, `half_day = 4,01`; chỉ bỏ
ngưỡng vắng thì `0 < 4,01` rơi tiếp xuống `Half Day` — tệ hơn, vì kéo theo `half_day_status` và
trừ **nửa ngày lương**.

⚠ Giờ tan **theo từng ca**, không dùng mốc chung: `Shift 1` 14:00 · `Canteen 6:30` 15:30 ·
`Canteen` 16:00 · `Day` 17:00 · `Shift 2` 22:00. Lúc 16:44 Shift 1 đã tan còn Shift 2 còn 5 tiếng.

🔴 **Đừng bỏ nhánh `not out_time → Present`.** Ngày 11/08/2026 nhánh này bị xoá vì **đo nhầm**: mẫu
khảo sát lọc `status = 'Absent'`, mà mọi bản nhánh này xử lý đều đã thành `Present` nên không nằm
trong mẫu — đo ra 0 và kết luận "nhánh chết". Đo đúng (không lọc status): **728 bản** đang ở
`Present` nhờ nhánh đó. Xoá nó là cắt trọn ngày lương của người quên quẹt ra.

**Đánh đổi có chủ ý:** ngày **đang diễn ra** đổi kết quả theo giờ chạy (16h `Present`, 20h
`Absent`). Ngày đã qua thì `is_shift_in_progress()` luôn False nên **tất định** — vì vậy nghiệm thu
*"chạy hai lần → 0 thay đổi"* phải chạy trên **ngày đã trọn**.

### Ca CHƯA TỚI GIỜ VÀO ⇒ không tạo attendance (15/08/2026)

Mặt còn lại của cùng vấn đề "ngày đang diễn ra". `is_shift_in_progress()` chỉ cứu được người **có**
chấm công. Người **chưa có log nào** đi thẳng xuống nhánh vắng — và lúc 08:00 sáng thì cả ca 2
(vào 14:00) đương nhiên chưa ai quẹt.

Đo trên production **15/08/2026**: engine chạy lúc **08:00:15** tạo **8 bản `Absent`**
(`working_hours = 0`, `in_time = NULL`) cho đúng 8 người ca 2 — toàn bộ nhân sự ca đó.

`resolve_no_checkin_attendance()` giờ trả `None` khi ca chưa tới giờ vào, dùng lại đúng hợp đồng
"`None` = không tạo attendance" vốn có sẵn cho giai đoạn Thai sản. Một chỗ sửa phủ **cả hai** đường
sinh Absent (3b ABSENCE PASS và 4 Mark absent) vì cả hai đều đã `if resolved is None: continue`.

🔴 **Guard đặt ĐÚNG nhánh `Absent`, không đặt ở đầu hàm.** Đơn nghỉ đã duyệt biết trước, không phụ
thuộc giờ vào ca — chặn sớm thì mất luôn `On Leave`. Thứ tự bắt buộc:

```
Thai sản        → None          (không phụ thuộc giờ)
Đơn nghỉ duyệt  → On Leave / Half Day   ← PHẢI được xét TRƯỚC guard
ca chưa vào giờ → None          ← guard nằm ở đây
còn lại         → Absent
```

Nghiệm thu (giả lập đồng hồ qua `frappe.flags.current_datetime`, nhân viên ca 2, ca vào 14:00):

| Đồng hồ | Không có đơn nghỉ | Có đơn nghỉ duyệt |
|---|---|---|
| 08:20 | `no attendance` | `On Leave` |
| 14:30 | `Absent` | `On Leave` |

Ngày đã qua luôn cho `False` (giờ vào nằm trước `now`) nên **kết quả ngày cũ vẫn tất định** — nghiệm
thu *"chạy hai lần → 0 thay đổi"* không bị ảnh hưởng.

Sau khi sửa, xoá 1.011 bản của 15/08 rồi chạy lại: Absent **78 → 70**, ca 2 còn **0** bản ghi,
Present giữ nguyên **933**, 1.125 checkin nối lại đủ.

### `out_time` giả khi quẹt đúp trước giờ vào ca

Engine ghép `in_time` = log đầu, `out_time` = log cuối, **bỏ qua `log_type`** — field
`Shift Type.determine_check_in_and_check_out` KHÔNG được đọc ở đâu cả (32% checkin không có
`log_type` nên không tin được).

Hệ quả: quẹt đúp ở cửa lúc vào sinh ra `out_time` nằm **trước cả giờ vào ca**:

```
TIQN-1168  12/08  ca Day 08:00-17:00   in 07:52:44   out 07:52:46
```

`discard_pre_shift_checkout()` bỏ `out_time` khi `out_time <= shift_start` ⇒ bản ghi rơi đúng
nhánh *"đã đến làm, chưa/quên quẹt ra"* → `Present`.

Đo 26/07–12/08 (13.155 bản có đủ in+out, bỏ Chủ Nhật): **163 bản** dính, khoảng cách in→out từ
**1 giây tới 630 giây**.

> ❌ **Đã cân nhắc và bác bỏ:** quy tắc *"gộp hai log cách nhau < 60 giây"*. Nó **bỏ sót 8/163**
> bản (khoảng cách tới 4 phút), và tệ hơn — nó giữ log **đầu** của cặp, nên ở **cửa ra** lại xén
> mất vài giây của `out_time` thật (`17:01:39` → `17:01:21`), làm **2.119** bản ghi bị ghi lại
> mỗi FULL run mà không giải quyết gì. Điều kiện `out_time <= shift_start` hẹp hơn nhiều: chỉ cần
> quẹt ra lúc tan ca là không kích hoạt ⇒ **0 churn** trên ngày đã trọn.

⚠ Bỏ qua **Chủ Nhật** — §8 lấy ranh giới ca từ đăng ký OT, không phải `Shift Type`.
⚠ Chỉ đụng `out_time`; `in_time` = log đầu luôn đúng.
⚠ **KHÔNG** áp cho chiều ngược lại (toàn bộ log **sau** giờ tan ca — 1 bản trong 18 ngày): đến
sau khi ca đã kết thúc không phải là "quên quẹt ra". `custom_note` đánh dấu để HR xử lý.

Test: `test_attendance_status.py` — 39 case, không ghi DB, giả lập thời điểm bằng
`frappe.flags.current_datetime`.

## Half Day ↔ payroll — never leave `half_day_status` NULL

`status = "Half Day"` alone changes nothing in payroll. `SalarySlip.get_half_absent_days()`
(`salary_slip.py:588`) filters on `half_day_status == "Absent"`, so a NULL is read as a full paid
day — 1,906 records sat that way until 2026-08-07 and every half day was being paid double.

🔴 Quy tắc **KHÔNG phải** "có checkin hay không", mà là **nửa còn lại có được công ty trả lương
hay không**. Nguồn duy nhất: `overrides/leave_rules.resolve_half_day_status()`; căn cứ nghiệp vụ
`overrides/leave_application/QUY_DINH_NGHI_PHEP_2025.md` mục 3.5 và 5.2.

| Nửa còn lại là… | `half_day_status` | Ngày công |
|---|---|:--:|
| Đi làm (có checkin) | `Present` | `P/2` → 1 · `O/2` → 0,5 |
| Nghỉ phép **có lương** (`P` `MC` `HS` `HL`, `is_lwp = 0`) | `Present` | `OP/2` `COP/2` → 0,5 |
| Nghỉ **không lương / BHXH** (`is_lwp = 1`) | `Absent` | `OCO/2` `OK/2` `COK/2` → 0 |
| Không có gì (không đi làm, không đơn thứ 2) | `Absent` | HRMS `attendance.py:199` cũng chốt vậy |

⚠ **`OP/2` (Ốm ½ + Phép năm ½) cả ngày không có checkin nào mà vẫn là `Present`** — vì nửa còn lại
là phép năm có lương. Quy tắc cũ *"không checkin → Absent"* sai đúng ở dòng này.

⚠ Ngược lại, **không** được đặt `Present` vô điều kiện cho mọi half-day có đơn nghỉ: payroll trừ
từ **hai** nguồn độc lập — `calculate_lwp_ppl_and_absent_days_based_on_attendance()`
(`salary_slip.py:790`) trừ 0,5 khi `leave_type.is_lwp = 1`, và `get_half_absent_days()`
(`salary_slip.py:578`) trừ thêm 0,5 khi `half_day_status = 'Absent'`. Đặt sai theo chiều nào cũng
lệch nửa ngày lương.

### Hai đơn nửa ngày cùng ngày → `Half Day`, không phải `On Leave`

| Trước | Sau |
|---|---|
| `status = 'On Leave'` (trọn ngày) | **`Half Day`** |
| `leave_type = active[0]`, hai query preload **không có `ORDER BY`** | `leave_type` = nửa `is_lwp = 1`; thêm `ORDER BY name` |
| mã tổ hợp `f"{abbr1}/{abbr2}"` | `combined_abbreviation()` — tra bảng của quy định |

`'On Leave'` làm HRMS trừ **trọn ngày** (`salary_slip.py:800` đặt `equivalent_lwp = 1`), trong khi
quy định cho `OP/2` = **0,5** ngày công. Và vì thiếu `ORDER BY`, cùng dữ liệu chạy lại có thể ra
**0 hoặc 1** ngày công tuỳ thứ tự MySQL trả về — sai theo cả hai chiều.

`leave_type` phải là nửa `is_lwp = 1`: HRMS chỉ trừ lương theo loại nằm ở field đó. Đặt nửa có
lương vào thì HRMS bỏ qua cả ngày ⇒ trả đủ lương cho ngày chỉ làm nửa buổi.

Kiểm chứng: `overrides/leave_application/test_leave_rules.py` (39 case, đối chiếu thẳng 9 dòng
nửa ngày của quy định).

Ngày Chủ Nhật có thể ra Half Day (§8 reset `working_hours` = 0 nhưng status vẫn tính từ giờ thực).
Vô hại với payroll vì `get_half_absent_days()` loại ngày nằm trong Holiday List
(`salary_slip.py:592`) — miễn là Chủ Nhật có trong list (list 2026 có, list 2025 không).

## Holidays — one company-level source, resolved per date

Non-working days come from **Holiday List Assignment** with *Applicable For: Company* (one
assignment for the whole company), read through HRMS's
`get_assigned_holiday_lists_to_employee_and_company()` so attendance and payroll agree on what a
holiday is. `Employee.holiday_list` is dead (only 377/1036 employees ever had it set) and HRMS
v16.15+ dropped it.

**Never resolve one list for the whole range** (`get_assigned_holiday_list(as_on=from_date)` does
exactly that): a period crossing a year boundary then uses the previous year's list. That is why
the 26/12/2025–25/01/2026 run read list "2025", missed 01/01/2026 which lives in list "2026", and
marked **848 employees Absent on New Year's Day**. The HRMS API returns each assignment's
effective range clipped to the period, so every date is looked up against the list actually in
force on it; the preload flattens that into `company_holidays = {company: set(dates)}`.

Sundays: the 2026 list carries them as `weekly_off` rows, so `is_holiday_cached()` already covers
them — but older lists do not (2025 has none), which is why the explicit `weekday() == 6` guard in
the no-checkin paths stays. Removing it would carpet pre-2026 Sundays with `Absent`.

## Configuration — "Attendance Calculation Setting" (Single DocType)

`/app/attendance-calculation-setting` — all business rules live here (code falls back to DEFAULTS when blank). The form embeds a Vietnamese algorithm quick-reference (HTML section).

- **OT**: min_ot_minutes=30, min_pre_shift_ot_minutes=60, ot_block_minutes=1, allow_ot_in_rest_time=0, include_draft_ot=0 (ON = Draft OTRs count; same-zone overlaps merged as span min→max).
- **Auto Recalc Triggers** (all default OFF — changes wait for the next full run): recalc_attendance_on_ot_change (OTR submit/cancel; with include_draft_ot also draft save/delete, deduped, quiet on save), recalc_attendance_on_maternity_change (that employee only), recalc_attendance_on_checkin_change (that employee+date, deduped, skipped on Data Import).
- **Shift & Processing**: default_shift=Day, employee_id_prefix=TIQN, working_block_minutes=1, force_update_hours="8,23", exclude_employee_ids, peak_times="07:40,16:00,17:00,19:00,20:00" + peak_window_minutes=20 (**is_peak_time()** skips the hourly hook and all 3 recalc background jobs during these windows; manual Bulk Update never blocked).
- **Maternity & Leave**: hour_reduction_hours=1.0, full_day_leave_block_hours=8, **include_draft_leave_application=0** (ON = Draft Leave Applications count too — for when leave is approved on paper but HR has not submitted the documents before the payroll cut-off).
- **Anomaly note**: note_early_late_threshold_minutes=60, female_checkout_check_from/to=16:00/17:00.

### Chặn `working_hours` theo đơn nghỉ phép (18/08/2026)

Quy tắc TIQN chốt — **ba field, đừng nhầm**:

| Field | Nghĩa |
|---|---|
| `standard_working_hours` | độ dài danh nghĩa của **ca** (8,0 ở mọi bản ghi). Không đụng |
| `custom_actual_working_hours` | giờ **thực tế** theo check in/out — **không bao giờ** bị chặn |
| `working_hours` | **cơ sở chốt lương** — bị chặn theo bảng dưới |

| Loại đơn | `working_hours` |
|---|---|
| `KL` | **giữ nguyên** giờ thực tế (theo in/out) |
| Đơn TRỌN ngày (≠ KL) | **0** |
| Đơn NỬA ngày | **min(thực tế, 4)** |
| Hai đơn nửa ngày cùng ngày (dual) | **0** — phủ kín cả ngày |
| Không có đơn | giữ nguyên |

Code: `overrides/shift_type/leave_hour_cap.py`, gọi từ **cả hai** nhánh ghi Attendance
(`apply_leave_hour_cap`) — nhánh UPDATE và nhánh INSERT.

⚠ **Phải gọi TRƯỚC `_check_attendance_changes()`.** Gọi sau thì bản ghi bị coi là "không đổi"
nên cap không bao giờ được ghi xuống DB.

🔴 **KHÔNG đụng tới tăng ca.** 638 bản ghi vừa có nghỉ nửa ngày vừa có OT, tổng **1.320,8 giờ
OT final**. Hàm chỉ sửa `working_hours`; **không** sửa `in_time`/`out_time`/các field OT — cắt
`out_time` để chặn giờ sẽ xoá sạch số OT đó. (Chủ Nhật engine đặt `actual_overtime =
working_hours`, nhưng hiện **0 ngày nghỉ nào rơi vào Chủ Nhật** nên hai nhánh không giao nhau.)

**Nghỉ đã duyệt thì KHÔNG đánh đi trễ / về sớm.** Nghỉ nửa ngày buổi sáng rồi vào lúc 12:03
không phải vi phạm — engine chỉ so `in_time` với giờ vào ca nên không biết. Quy chế mục 3.3 trừ
**100.000đ mỗi lần**, nên gắn nhầm là mất tiền thật: đo 18/08/2026 có **918** bản ghi nghỉ nửa
ngày bị gắn `late_entry` và **737** bị gắn `early_exit`. `KL` là ngoại lệ (trễ/sớm chính là một
dạng nghỉ không lương, mục 3.3 mã `<1`).
⚠ Leave Application **không có** field cho biết nghỉ nửa nào (`custom_half_day_period` không tồn
tại) nên phải bỏ **cả hai** cờ. Có field đó rồi thì siết lại `should_suppress_late_early()`.

**Phát hiện "xin nghỉ nhưng vẫn đi làm"** — điều kiện `custom_actual_working_hours >
working_hours`, hiện ở 4 chỗ:

| Chỗ | Nội dung |
|---|---|
| `Attendance.custom_note` | `Half-day leave (P/2) but worked 8.00h - capped to 4.00h - check if LA should be cancelled` |
| Excel: Detail `Note Checkin` + sheet `Important Note` | Important Note là Excel Table 8 cột, sắp xếp Type → Date → Employee: Type · Info · Working Hour · Working Hour Actual · Leave Application Abbreviation · Attendance · Leave Application · Note |

⚠ `standard_export._build_notes()` **chỉ dịch những chuỗi đã khai**. Thêm note mới ở engine mà
quên khai ở đó thì note **biến mất khỏi cột Note Checkin mà không báo lỗi** — đã cắn một lần.

> Đã cân nhắc thêm ô Check `Leave but worked` **và** cột `Actual Working Hours` lên report —
> **bỏ cả hai** (user chốt 18/08/2026): note trong Excel đã đủ cho quy trình của HR. Giờ thực tế
> chỉ hiện ở cột `Actual (hour)` sheet Detail và sheet Important Note.

⚠ Bug CÓ SẴN đã sửa cùng lúc (không liên quan tính năng này, giữ lại): vòng lặp filter trong
`shift_attendance_customize.get_query()` chỉ xét **key**, không xét **giá trị** — nên
`late_entry = 0` (bỏ tick) lọc y hệt `= 1`, ra 291 dòng thay vì 24.408. Mọi ô Check phải dùng
`cint(filters.get(...))`.

### Option của dialog Export Excel

| Option | Kiểu | Mặc định |
|---|---|---|
| `only_resigned` | Check | tắt — chỉ NV có `relieving_date` **trong kỳ** |
| `leave_gap_minutes` | Select 0/15/30/60/120/180/240/240+ | **15** |
| 6 ô chọn sheet | Check | tất cả bật |

⚠ `only_resigned` **THAY THẾ** điều kiện trạng thái, không AND thêm. Điều kiện gốc dùng
`relieving_date > from_date` \(lớn hơn **hẳn**\) nên nếu chỉ AND thêm sẽ rơi mất người nghỉ đúng
ngày đầu kỳ — đo tháng 6/2026: 57/59, thiếu `TIQN-1653` và `TIQN-2144` đều nghỉ 01/06.

⚠ Bỏ sheet "Important Note" thì phải `wb.remove(wb.active)`, nếu không file có tab rỗng tên
"Sheet". Không chọn sheet nào thì openpyxl không lưu được workbook rỗng.

Kiểm thử: `test_leave_hour_cap.py` — 78 assert, 8 phần.

### `include_draft_leave_application` — tính cả đơn nghỉ Draft

Mặc định **OFF** = chỉ đơn đã Submit, đúng hành vi cũ. Bật khi tới kỳ chốt lương mà đơn cuối
tháng còn nằm ở Draft, khiến bảng công thiếu ngày nghỉ.

`get_leave_docstatus_condition(alias="")` sinh mệnh đề SQL — `docstatus = 1` khi tắt,
`docstatus IN (0, 1)` khi bật. **Chỉ nới `docstatus`**: điều kiện `status = 'Approved'` ở chỗ gọi
giữ nguyên, nên đơn Draft bị Rejected/Cancelled không lọt vào.

Hai đường ghi Attendance **phải dùng chung cờ này**, nếu không cặp *đơn submit + đơn draft* cùng
ngày sẽ giải sai `half_day_status`:

| Đường | Nơi áp |
|---|---|
| Engine (`preload_reference_data`) | 2 truy vấn `tabLeave Application` |
| Luồng Leave Application | `overrides/leave_utils.find_other_half_day_leave_type()` |

Đo trên production kỳ 26/07→25/08/2026 (0 đơn submitted, 349 draft):
**OFF → 0 đơn / 0 ngày · ON → 349 đơn / 487 ngày.**

⚠ **Nhân viên đã nghỉ việc vẫn được tính** — truy vấn dựng danh sách nhân viên (mục "Get employee
list") cố ý gồm `Left` có `relieving_date >= from_date`, nên đơn cho những ngày họ còn đi làm
không bị bỏ. Nhưng ngày **từ `relieving_date` trở đi** thì không sinh chấm công: chặn hai lớp ở
`should_mark_attendance()` và bước dọn cuối. Đã xác minh trên `TIQN-1414` (nghỉ việc 01/08, có
đơn 04/08): 0 bản ghi từ 01/08.

Kiểm thử: `test_include_draft_leave.py` — 13 assert, tự `rollback()` nên không đổi cờ thật.

Access helpers (settings controller): `get_attendance_settings()`, `get_force_update_hours()`,
`get_excluded_employee_ids()`, `get_ot_docstatus_condition()`, `get_leave_docstatus_condition()`, `is_peak_time()`,
`floor_ot_to_block()`, `floor_working_to_block()`.

Performance tuning (batch sizes) stays hardcoded in `shift_type_optimized.py`.

## File liên quan

| File | Purpose |
|------|---------|
| `shift_type_optimized.py` | Core engine + Sunday + notes + absence pass + background hand-off |
| `shift_type.py` | Legacy per-shift path + last_sync (still monkey-patched for `process_auto_attendance`) |
| `../../patches/index_checkin_attendance_field.py` | Keeps `Employee Checkin.attendance` indexed across migrations (see Performance) |
| `../employee_checkin/employee_checkin.py` | working-hours calc, `calculate_overtime_segments`, checkin sync |
| `../../customize_erpnext/doctype/attendance_calculation_setting/` | settings + helpers |
| `LEGACY_APP_TIMESHEET_ALGORITHM.md` | Reference algorithm of the legacy Dart app (source of truth for the rules) |
| `attendance_config.py` | Legacy feature-flag/benchmark helpers (used by attendance_list.js only) |

## ⚠ Ràng buộc cấu hình: ca KHÔNG được kết thúc sau nửa đêm

Với mỗi Shift Type phải giữ:

```
end_time + allow_check_out_after_shift_end_time  <  24:00
```

Ở chế độ FULL (chạy từ UI), query lấy checkin lọc `shift_actual_end < cuối ngày to_date`
(`shift_type_optimized.py`, khối `if fore_get_logs`). Ca nào có `shift_actual_end` rơi sang
**hôm sau** thì **toàn bộ checkin của ca đó bị loại** — engine báo *"Found 0 checkins"*, rồi bước
"Mark absent" tạo bản ghi `Absent` với `in_time = NULL`. Người đi làm cả ngày bị cắt trọn ngày
lương, **không có cảnh báo nào**.

Đã xảy ra 12/08/2026: `Shift 2` tan 22:00 + cho ra muộn **180 phút** = **01:00 hôm sau**
⇒ **27 bản ghi** `in_time = NULL` dù có quẹt thẻ (25 `Absent` + 2 `Half Day`).
Khắc phục bằng cách hạ xuống **90 phút** (22:00 + 90 = 23:30) rồi chạy lại bulk update.

Kiểm nhanh khi thêm/sửa ca:

```sql
SELECT name, end_time, allow_check_out_after_shift_end_time
FROM `tabShift Type`
WHERE TIME_TO_SEC(end_time)/3600 + IFNULL(allow_check_out_after_shift_end_time,0)/60 >= 24;
-- kỳ vọng: 0 dòng
```

> `shift_actual_end` **lưu cứng trên từng Employee Checkin**. Đổi Shift Type không cập nhật bản
> ghi cũ — phải chạy Bulk Update Attendance cho khoảng ngày liên quan; STEP 2
> (`bulk_update_employee_checkin`) tính lại toàn bộ checkin trong khoảng **trước** vòng lặp theo ca.

## Design Trade-offs (intentional)

- ORM bypassed for insert/update (no validate/on_submit/Comments; Attendance names are hashes). Updates go through a `TEMPORARY TABLE ... LIKE tabAttendance` staging table + one JOIN UPDATE per batch; a batch that fails is retried row by row. The DDL runs on `frappe.db._cursor` because `frappe.db.sql()` rejects CREATE/DROP once the transaction has writes — MariaDB exempts TEMPORARY tables from implicit commits, so that guard is a false positive here.
- `mark_auto_attendance_on_holidays` does **not** create attendance on empty holidays, and must not be made to. Its own field description is *"auto attendance will be marked on holidays **if Employee Checkins exist**"*, and upstream HRMS only calls `should_mark_attendance()` from inside the checkin groupby loop (`hrms/.../shift_type.py:145`); the no-checkin path (`mark_absent_for_dates_with_no_attendance` → `get_dates_for_attendance`) skips holidays unconditionally. Days WITH checkins are already always counted here, which is exactly the flag-enabled behaviour. **Wiring the flag into the no-checkin path on 2026-08-06 created 28,798 bogus Sunday `Absent` records in one afternoon** (all 5 shifts have it ticked) — reverted the same day. Half-holiday thresholds are still not implemented.
- A day WITH checkins is always calculated, even past the relieving date — the relieving date may simply be wrong. `custom_note` says so and asks HR to verify; only no-checkin days after relieving are deleted.
- Single log (IN only) → status Present, hours 0 — `resolve_attendance_status()`. Cùng hàm đó
  hoãn ngưỡng vắng khi ca chưa tan; xem mục *Attendance status* ở trên trước khi sửa.
- Checkin insert/update hooks for per-checkin recalc are disabled in hooks.py (queue-flood protection); corrections land at the next FULL run.
- Shift Assignment changes do NOT trigger recalc (override deleted 2026-07-04) — corrected at the next FULL run or manual Bulk Update.

## Kiểm thử

```python
# bench --site <site> console
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized
# force_sync=1 → run inline and get the result back; without it a large range is enqueued
# and the return value is just {"background_job": True, ...}
bulk_update_attendance_optimized("2026-07-01", "2026-07-04", employees='["TIQN-0001"]', force_sync=1)
```

The console splits multi-line blocks into separate cells, so functions defined there lose their
globals. For anything longer than a one-liner, run a script against the site instead:

```bash
cd /home/frappe/frappe-bench/sites && ../env/bin/python my_script.py   # frappe.init(site=...) + frappe.connect()
```

To verify a change without writing new data, perturb a few records, recalculate, and assert they
come back identical (snapshot first, restore on mismatch) — a plain rerun on correct data updates
nothing and proves nothing.
