# Bulk Attendance — Quick Reference

**Updated:** 2026-07-05

## Settings (change here, not in code)

`/app/attendance-calculation-setting` — Attendance Calculation Setting (Single):

| Setting | Default | Meaning |
|---|---|---|
| Minimum OT Minutes | 30 | Post-shift OT below this → 0 |
| Minimum Pre-Shift OT Minutes | 60 | Pre-shift OT below this → 0 |
| OT Block Minutes | 1 | Floor OT to block (30 → 45'→30') |
| Working Block Minutes | 1 | 1 = no rounding of working hours |
| Allow OT In Rest Time | OFF | OFF = registered lunch-break OT ignored |
| Exclude Employee IDs | — | CSV, skipped from processing entirely |
| Maternity Benefit Hours | 1.0 | Shift end reduced, hours still credited |
| Full Day Leave Block Hours | 8 | Block full-day LA when already worked ≥ this |
| Default Shift | Day | Fallback when no assignment/default |
| Employee ID Prefix | TIQN | Fallback employee query filter |
| Full Update Hours | 8,23 | Hours when hourly job does FULL reprocess |
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
- **custom_note** (Attendance) is auto-written every run — do NOT let HR edit it by hand.
- Attendance for Maternity-Leave-phase employees is deleted (Employee Maternity = source of truth).
- No attendance on holidays/Sundays without checkins.

## Gotchas

- Code changes need `bench restart` (workers cache monkey patches).
- Attendance names are random hashes (bulk INSERT bypasses naming series) — by design.
- Historical ranges only match the legacy app after: OT Registrations entered in ERP + a full Bulk Update rerun.
- Shift Assignment edits don't auto-recalc attendance — run Bulk Update or wait for the 8h/23h run.
