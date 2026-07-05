# Bulk Attendance Processing — Architecture & Logic Guide

**Last Updated:** 2026-07-05 (per-segment OT, Sunday→OT, custom_note, Attendance Calculation Setting)

## Performance

| Metric | Value |
|--------|-------|
| Processing Time | ~30s (30 days × 800 employees, full mode) |
| DB Queries | ~500 (all reference data preloaded, OT lookups in-memory) |
| Batch Size | 100 employees / 500 insert / 1000 checkin-update |

## Entry Points (all funnel into `_core_process_attendance_logic_optimized`)

```
HRMS hourly_long hook ──(monkey patch)──► custom_process_auto_attendance_for_all_shifts
UI "Bulk Update"      ──────────────────► bulk_update_attendance_optimized (lock + backup/restore shift params)
OT Registration submit/cancel ──(bg job)─► overtime_registration_hooks._process_attendance_background
Employee Maternity save/trash ──(bg job)─► employee_maternity.background_update_attendance_for_maternity
Checkin delete hook (recalc)  ──(bg job)─► employee_checkin._recalculate_attendance_background
```

Mode detection (`fore_get_logs`):
- **FULL** — web request, or hour ∈ `force_update_hours` setting (default 8, 23), or callers passing `fore_get_logs=True`. Reprocesses every checkin in range, updates existing attendance.
- **INCREMENTAL** — other hourly runs. Only unlinked checkins (`attendance is not set`).

## Processing Steps

1. **Preload** — employees (+gender), shifts, shift assignments (sorted desc), holidays, existing attendance (all compare fields incl. `custom_note`), leave applications (per-day index, dual-leave aware), maternity periods, OT registrations `{(employee, date): [entries]}`.
   - `exclude_employee_ids` setting filters the employee list first (empty result → early return).
2. **Checkin sync** — `bulk_update_employee_checkin`: shift from Shift Assignment → default_shift → `default_shift` setting; first log = IN, last = OUT; SQL CASE WHEN batches (no per-doc `get_doc`).
2b. **Maternity cleanup** (FULL only) — delete attendance inside Maternity Leave phases (Employee Maternity is source of truth), unlink checkins.
3. **Per-shift checkin processing** — group by (employee, shift_start):
   - working hours = morning + afternoon (break excluded; maternity: end −`maternity_benefit_hours`, afternoon credited).
   - **OT per-segment** (`calculate_overtime_segments`, LEGACY_APP_TIMESHEET_ALGORITHM.md §7): final = Σ min(actual, approved) per pre/lunch/post segment — NO global clamp; pre actual capped at registered span, min `min_pre_shift_ot_minutes`; post actual uncapped, min `min_ot_minutes`; everything floored to `ot_block_minutes`; lunch counted only when `allow_ot_in_rest_time` is ON.
   - **Sunday** (§8): shift boundaries ← OT registration span; ALL worked hours → `actual_overtime_duration`, `working_hours` = 0 (status still from real hours); no register → approved/final = 0 but actual still shown.
   - 0/1-log days: approved OT still shown from registrations (§7.9), actual/final = 0.
   - New inserts apply Leave Applications (Half Day + checkin → half_day_status Present); updates preserve leave from the old record.
   - `custom_note` anomalies (§9-10): Left-with-checkins, ±threshold without same-zone OT registration, Sunday work (+meal allowance > 4h spanning break), female checkout window without Employee Maternity (only shifts ending at window end), single-checkin / no-IN / no-OUT.
   - Values stored rounded: working_hours 2dp, OT 1dp.
3b. **ABSENCE PASS** (FULL only, runs ONCE after all shifts) — every existing attendance whose (employee, date) had no checkins processed by ANY shift is re-resolved: Maternity Leave → skip, Leave → On Leave/Half Day, else Absent. Global `processed_keys` prevents cross-shift Absent overwrites when the stored shift is stale.
4. **Mark absent** — days with no attendance at all (skip holidays/Sundays/before-joining/after-relieving); same resolution helper as 3b; bulk INSERT (32 columns incl. half_day/dual-leave/custom_note).
4b. **Left-employee cleanup** — delete attendance ≥ relieving_date without checkins; tag `custom_note` on ones WITH checkins.
5. **Stats** — per-shift before/after counts, skipped-employee classification.

## Configuration — "Attendance Calculation Setting" (Single DocType)

`/app/attendance-calculation-setting` — all business rules live here (code falls back to DEFAULTS when blank):
min_ot_minutes=30, min_pre_shift_ot_minutes=60, ot_block_minutes=1, working_block_minutes=1,
allow_ot_in_rest_time=0, exclude_employee_ids, maternity_benefit_hours=1.0,
full_day_leave_block_hours=8, default_shift=Day, employee_id_prefix=TIQN,
force_update_hours="8,23", note_early_late_threshold_minutes=60,
female_checkout_check_from/to=16:00/17:00.

Access: `get_attendance_settings()` (get_cached_doc + DEFAULTS), `get_force_update_hours()`,
`get_excluded_employee_ids()`, `floor_ot_to_block()`, `floor_working_to_block()`.

Performance tuning (batch sizes) stays hardcoded in `shift_type_optimized.py`.

## Files

| File | Purpose |
|------|---------|
| `shift_type_optimized.py` | Core engine + Sunday + notes + absence pass |
| `shift_type.py` | Legacy per-shift path + last_sync + bulk backup/restore (still monkey-patched for `process_auto_attendance`) |
| `../employee_checkin/employee_checkin.py` | working-hours calc, `calculate_overtime_segments`, checkin sync |
| `../../customize_erpnext/doctype/attendance_calculation_setting/` | settings + helpers |
| `LEGACY_APP_TIMESHEET_ALGORITHM.md` | Reference algorithm of the legacy Dart app (source of truth for the rules) |
| `attendance_config.py` | Legacy feature-flag/benchmark helpers (used by attendance_list.js only) |

## Design Trade-offs (intentional)

- ORM bypassed for insert/update (no validate/on_submit/Comments; Attendance names are hashes).
- `mark_auto_attendance_on_holidays` flag and half-holiday thresholds are NOT honored — no attendance on holidays/Sundays without checkins, ever.
- Single log (IN only) → status Present, hours 0.
- Checkin insert/update hooks for per-checkin recalc are disabled in hooks.py (queue-flood protection); corrections land at the next FULL run.
- Shift Assignment changes do NOT trigger recalc (override deleted 2026-07-04) — corrected at the next FULL run or manual Bulk Update.

## Testing

```python
# bench --site <site> console
from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized
bulk_update_attendance_optimized("2026-07-01", "2026-07-04", employees='["TIQN-0001"]', force_sync=1)
```
