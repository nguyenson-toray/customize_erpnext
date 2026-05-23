"""
Performance indexes for bulk attendance processing.

These indexes target the hot queries in _core_process_attendance_logic_optimized:
  - preload_reference_data: Leave Application, Shift Assignment, Attendance, Employee Maternity
  - bulk_insert_attendance_records: Attendance dedup check
  - Checkin unlink updates: Employee Checkin.attendance FK

Safe to run multiple times — each statement checks existence before creating.
"""

import frappe


def execute():
    _add_index_if_missing(
        table="tabAttendance",
        index_name="idx_att_emp_date_docstatus",
        columns="employee, attendance_date, docstatus",
        comment="Dedup check + existing_attendance preload"
    )

    _add_index_if_missing(
        table="tabShift Assignment",
        index_name="idx_shift_assign_lookup",
        columns="employee, docstatus, status, start_date",
        comment="Shift assignment preload filter"
    )

    _add_index_if_missing(
        table="tabLeave Application",
        index_name="idx_leave_app_date_range",
        columns="employee, status, docstatus, from_date, to_date",
        comment="Leave application preload date-range query"
    )

    _add_index_if_missing(
        table="tabEmployee Checkin",
        index_name="idx_checkin_attendance_fk",
        columns="attendance",
        comment="Unlink checkins after attendance cancel/delete"
    )

    _add_index_if_missing(
        table="tabEmployee Maternity",
        index_name="idx_emp_maternity_employee",
        columns="employee",
        comment="Maternity tracking preload per employee"
    )

    _add_index_if_missing(
        table="tabEmployee Maternity",
        index_name="idx_emp_maternity_mat_dates",
        columns="maternity_from_date, maternity_to_date",
        comment="Maternity leave date-overlap check"
    )

    _add_index_if_missing(
        table="tabOvertime Registration Detail",
        index_name="idx_ot_detail_emp_date",
        columns="employee, date",
        comment="Overtime registration preload by employee+date"
    )

    _add_index_if_missing(
        table="tabEmployee",
        index_name="idx_employee_status_relieving",
        columns="status, relieving_date",
        comment="Cleanup query for left employees"
    )


def _add_index_if_missing(table, index_name, columns, comment=""):
    """Add a DB index only if it does not already exist."""
    exists = frappe.db.sql("""
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE table_schema = DATABASE()
          AND table_name   = %s
          AND index_name   = %s
    """, (table, index_name))[0][0]

    if exists:
        print(f"   ⏭  Index already exists: {index_name} on {table}")
        return

    frappe.db.sql(f"CREATE INDEX `{index_name}` ON `{table}` ({columns})")
    frappe.db.commit()
    print(f"   ✅ Created index: {index_name} on {table} ({columns})"
          + (f" — {comment}" if comment else ""))
