# Bulk Attendance Processing — Architecture & Logic Guide

**Last Updated:** 2026-08-06 (timeout fix: checkin index + batched updates + background jobs;
`mark_auto_attendance_on_holidays` honored; post-relieving days with checkins counted)

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
   - working hours = morning + afternoon (break excluded; maternity: end −`maternity_benefit_hours`, afternoon credited).
   - **OT per-segment** (`calculate_overtime_segments`, LEGACY_APP_TIMESHEET_ALGORITHM.md §7): final = Σ min(actual, approved) per pre/lunch/post segment — NO global clamp; pre actual capped at registered span, min `min_pre_shift_ot_minutes`; post actual uncapped, min `min_ot_minutes`; everything floored to `ot_block_minutes`; lunch counted only when `allow_ot_in_rest_time` is ON.
   - **Sunday** (§8): shift boundaries ← OT registration span; ALL worked hours → `actual_overtime_duration`, `working_hours` = 0 (status still from real hours); no register → approved/final = 0 but actual still shown.
   - 0/1-log days: approved OT still shown from registrations (§7.9), actual/final = 0.
   - **`half_day_status` is always written** — payroll ignores a Half Day without it (`get_half_absent_days` needs status `Half Day` **and** `half_day_status = "Absent"`; NULL reads as a fully paid day). The value comes from `overrides/leave_rules.resolve_half_day_status()` — shared with the Leave Application flow, see the table below.
   - New inserts and updates both apply Leave Applications through the same helper; two half-day LAs on one date become a **`Half Day`** (never `On Leave`) whose `leave_type` is the `is_lwp` half.
   - `custom_note` anomalies (§9-10): Left-with-checkins, ±threshold without same-zone OT registration, Sunday work (+meal allowance > 4h spanning break), female checkout window without Employee Maternity (only shifts ending at window end), single-checkin / no-IN / no-OUT.
   - Values stored rounded: working_hours 2dp, OT 1dp.
3b. **ABSENCE PASS** (FULL only, runs ONCE after all shifts) — every existing attendance whose (employee, date) had no checkins processed by ANY shift is re-resolved: Maternity Leave → skip, Leave → On Leave/Half Day, else Absent. Global `processed_keys` prevents cross-shift Absent overwrites when the stored shift is stale.
4. **Mark absent** — days with no attendance at all (skip before-joining/after-relieving, holidays and Sundays); same resolution helper as 3b; bulk INSERT (32 columns incl. half_day/dual-leave/custom_note).
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

Test: `test_attendance_status.py` — 27 case, không ghi DB, giả lập thời điểm bằng
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
- **Maternity & Leave**: maternity_benefit_hours=1.0, full_day_leave_block_hours=8.
- **Anomaly note**: note_early_late_threshold_minutes=60, female_checkout_check_from/to=16:00/17:00.

Access helpers (settings controller): `get_attendance_settings()`, `get_force_update_hours()`,
`get_excluded_employee_ids()`, `get_ot_docstatus_condition()`, `is_peak_time()`,
`floor_ot_to_block()`, `floor_working_to_block()`.

Performance tuning (batch sizes) stays hardcoded in `shift_type_optimized.py`.

## Files

| File | Purpose |
|------|---------|
| `shift_type_optimized.py` | Core engine + Sunday + notes + absence pass + background hand-off |
| `shift_type.py` | Legacy per-shift path + last_sync (still monkey-patched for `process_auto_attendance`) |
| `../../patches/index_checkin_attendance_field.py` | Keeps `Employee Checkin.attendance` indexed across migrations (see Performance) |
| `../employee_checkin/employee_checkin.py` | working-hours calc, `calculate_overtime_segments`, checkin sync |
| `../../customize_erpnext/doctype/attendance_calculation_setting/` | settings + helpers |
| `LEGACY_APP_TIMESHEET_ALGORITHM.md` | Reference algorithm of the legacy Dart app (source of truth for the rules) |
| `attendance_config.py` | Legacy feature-flag/benchmark helpers (used by attendance_list.js only) |

## Design Trade-offs (intentional)

- ORM bypassed for insert/update (no validate/on_submit/Comments; Attendance names are hashes). Updates go through a `TEMPORARY TABLE ... LIKE tabAttendance` staging table + one JOIN UPDATE per batch; a batch that fails is retried row by row. The DDL runs on `frappe.db._cursor` because `frappe.db.sql()` rejects CREATE/DROP once the transaction has writes — MariaDB exempts TEMPORARY tables from implicit commits, so that guard is a false positive here.
- `mark_auto_attendance_on_holidays` does **not** create attendance on empty holidays, and must not be made to. Its own field description is *"auto attendance will be marked on holidays **if Employee Checkins exist**"*, and upstream HRMS only calls `should_mark_attendance()` from inside the checkin groupby loop (`hrms/.../shift_type.py:145`); the no-checkin path (`mark_absent_for_dates_with_no_attendance` → `get_dates_for_attendance`) skips holidays unconditionally. Days WITH checkins are already always counted here, which is exactly the flag-enabled behaviour. **Wiring the flag into the no-checkin path on 2026-08-06 created 28,798 bogus Sunday `Absent` records in one afternoon** (all 5 shifts have it ticked) — reverted the same day. Half-holiday thresholds are still not implemented.
- A day WITH checkins is always calculated, even past the relieving date — the relieving date may simply be wrong. `custom_note` says so and asks HR to verify; only no-checkin days after relieving are deleted.
- Single log (IN only) → status Present, hours 0 — `resolve_attendance_status()`. Cùng hàm đó
  hoãn ngưỡng vắng khi ca chưa tan; xem mục *Attendance status* ở trên trước khi sửa.
- Checkin insert/update hooks for per-checkin recalc are disabled in hooks.py (queue-flood protection); corrections land at the next FULL run.
- Shift Assignment changes do NOT trigger recalc (override deleted 2026-07-04) — corrected at the next FULL run or manual Bulk Update.

## Testing

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
