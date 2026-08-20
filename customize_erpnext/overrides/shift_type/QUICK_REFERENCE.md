# Bulk Attendance — Quick Reference

> **Mục đích:** Tra nhanh khi vận hành engine tính công: chỉnh ở đâu, chạy lệnh gì, lỗi thường gặp.
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-07

**Updated:** 2026-08-06

## Settings (change here, not in code)

`/app/attendance-calculation-setting` — Attendance Calculation Setting (Single).
The form has a built-in Vietnamese algorithm reference (collapsible section
"Thuật toán tính công (tra cứu)").

| Setting | Default | Meaning |
|---|---|---|
| Minimum OT Minutes | 30 | Post-shift OT below this → 0 |
| Minimum Pre-Shift OT Minutes | 60 | Pre-shift OT below this → 0 |
| OT Block Minutes | 1 | Floor OT to block (30 → 45'→30') |
| Working Block Minutes | 1 | 1 = no rounding of working hours |
| Allow OT In Rest Time | OFF | OFF = registered lunch-break OT ignored |
| Include Draft OT Registrations | OFF | ON = count Draft OTRs too; same-zone overlaps merged min(begin)-max(end) |
| Recalc Attendance on OT Submit/Cancel | OFF | ON = queue recalc when OTR submitted/cancelled; +draft flag ON = draft save/delete recalc too |
| Recalc Attendance on Maternity Save/Delete | OFF | ON = recalc that employee's affected dates on Employee Maternity save/delete |
| Recalc Attendance on Checkin Save/Delete | OFF | ON = recalc that employee+date on checkin insert/update/delete (deduped) |
| Exclude Employee IDs | — | CSV, skipped from processing entirely |
| Maternity Benefit Hours | 1.0 | Shift end reduced, hours still credited |
| Full Day Leave Block Hours | 8 | Block full-day LA when already worked ≥ this |
| Default Shift | Day | Fallback when no assignment/default |
| Employee ID Prefix | TIQN | Fallback employee query filter |
| Full Update Hours | 8,23 | Hours when hourly job does FULL reprocess |
| Peak Times / Window Minutes | 07:40,16:00,17:00,19:00,20:00 / 20 | AUTOMATIC calculation skipped in these windows (manual Bulk Update never blocked); clear Peak Times to disable |
| Early/Late Threshold Minutes | 60 | custom_note anomaly threshold |
| Female Checkout From/To | 16:00–17:00 | Maternity-suspect window (Day-shift only) |

## Commands

```python
# bench --site erp.tiqn.local console

# Full reprocess of a range (what the UI button does)
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized
bulk_update_attendance_optimized("2026-07-01", "2026-07-05", employees='["TIQN-0001"]', force_sync=1)

# Hourly-hook path (incremental unless run at 8h/23h)
from customize_erpnext.overrides.shift_type.shift_type_optimized import custom_process_auto_attendance_for_all_shifts
custom_process_auto_attendance_for_all_shifts()

# Read effective settings
from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import get_attendance_settings
get_attendance_settings()
```

## Key Rules (aligned with legacy app — LEGACY_APP_TIMESHEET_ALGORITHM.md)

- **OT Final = Σ min(actual, approved) PER SEGMENT** (pre / lunch / post) — never `min(total, total)`.
- **Sunday**: worked hours go to OT fields; `working_hours` = 0. Payroll must read OT columns for Sundays.
- **custom_note** (Attendance) is auto-written every run — do NOT let HR edit it by hand. It is the
  persisted anomaly channel (reports/exports read it); the Attendance form's "Additional
  Information" panel is computed live and must not repeat what custom_note already says.
- Attendance for Maternity-Leave-phase employees is deleted (Employee Maternity = source of truth).
- **No attendance on holidays/Sundays without checkins — ever.** `mark_auto_attendance_on_holidays`
  does NOT change this: its description is *"marked on holidays if Employee Checkins exist"*, and
  HRMS only consults it on the checkin path. Wiring it into the no-checkin path on 2026-08-06
  produced 28,798 bogus Sunday `Absent` records (all 5 shifts have it ticked) — do not retry.
- Ngày nghỉ/lễ lấy từ **Holiday List Assignment → Applicable For: Company** qua API gốc HRMS
  `get_assigned_holiday_lists_to_employee_and_company()` (payroll dùng chung API này). Không dùng
  `get_assigned_holiday_list(as_on=from_date)` — kỳ vắt qua năm sẽ lấy nhầm list năm cũ.
- **A day with checkins is always counted, even after the relieving date** — the relieving date
  may be wrong. custom_note flags it for HR. Only post-relieving days *without* checkins are
  deleted.

## Gotchas

- Code changes need `bench restart` (workers cache monkey patches). Restart only when the `long`
  queue is idle — a restart SIGKILLs a running Bulk Update mid-write.
- **Never add a single-column index with a bare `CREATE INDEX`.** The field's `search_index = 0`
  makes frappe's schema sync drop it on the next `bench migrate`. Set `search_index = 1` via
  Property Setter as well — see `patches/index_checkin_attendance_field.py`. Losing the index on
  `Employee Checkin.attendance` alone turns Bulk Update into a timeout (1949 ms → 0.29 ms per
  unlink query).
- A Bulk Update above 1000 estimated records runs as a background job; results arrive over
  realtime, and there is only **one** long worker, so a second run queues behind the first.
- A killed job used to leave Shift Type pinned to temporary `process_attendance_after` /
  `last_sync_of_checkin` values (the `finally` never ran) — starving the incremental hourly job.
  Those temp writes are gone; if you still see an old `last_sync_of_checkin`, it self-heals after
  the shift ends that day.
- Attendance names are random hashes (bulk INSERT bypasses naming series) — by design.
- Historical ranges only match the legacy app after: OT Registrations entered in ERP + a full Bulk Update rerun.
- Shift Assignment edits don't auto-recalc attendance — run Bulk Update or wait for the 8h/23h run.
